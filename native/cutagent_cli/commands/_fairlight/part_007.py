"""Fairlight Sound Library browse and index commands."""

from __future__ import annotations

@sound_library_app.command("audition")
@sound_library_app.command("preview")
@handle_errors
def sound_library_audition(
    query: str | None = typer.Argument(None, help="Search query or known library result name to audition"),
    clip_id: str | None = typer.Option(None, "--clip-id", help="Exact FLAssetBaseClip_id to audition"),
    file_id: str | None = typer.Option(None, "--file-id", help="Exact FLAssetBaseFile_id to audition"),
    result_index: int | None = typer.Option(None, "--result-index", min=1, help="1-based result index when the selector matches multiple rows"),
    sync_to_playhead: bool = typer.Option(False, "--sync-to-playhead/--no-sync-to-playhead", help="Request Sound Library panel sync-preview behavior when available"),
    database: str = typer.Option(
        "project",
        "--database",
        "--db",
        help="Sound Library DB scope: project/current-project or user/local-database",
    ),
):
    """Report Fairlight Sound Library audition/preview API availability."""
    database_scope = _normalize_sound_library_database(database)
    enforce_mutation_policy("fairlight.sound_library_audition", intended_engine="not_available", mutating=False)
    _raise_fairlight_native_unavailable(
        capability_id="fairlight.sound_library_audition",
        workflow="Fairlight Sound Library audition/preview",
        requested={
            "query": query,
            "clip_id": clip_id,
            "file_id": file_id,
            "result_index": int(result_index) if result_index is not None else None,
            "sync_to_playhead": bool(sync_to_playhead),
            "database": database_scope,
        },
        required_native_api=[
            "audition a Fairlight Sound Library indexed audio file without inserting it",
            "preview Sound Library playback through the Fairlight panel",
            "sync Sound Library audition preview to the current playhead",
            "stop or inspect Sound Library audition playback state",
        ],
        api_note=(
            "DaVinci Resolve's public scripting API exposes Project.InsertAudioToCurrentTrackAtPlayhead "
            "but no Sound Library audition or preview playback method. Local runtime probes against DaVinci Resolve, "
            "project, timeline, media pool, and media storage objects reached Lua/DaVinci Resolve and returned method not available."
        ),
        workaround=(
            "Use fairlight sound-library insert for native timeline placement, including --sync-to-playhead "
            "when an indexed sync point should align to the current playhead; audition/preview remains a manual DaVinci Resolve panel workflow."
        ),
        extra_details=_FAIRLIGHT_SOUND_LIBRARY_AUDITION_DB_BLOCKER_EVIDENCE,
    )


@sound_library_app.command("list")
@handle_errors
def sound_library_list(
    query: str | None = typer.Option(None, "--query", "-q", help="Optional search filter"),
    limit: int = typer.Option(50, "--limit", help="Maximum results to return, 1-500"),
    database: str = typer.Option(
        "project",
        "--database",
        "--db",
        help="Sound Library DB scope: project/current-project or user/local-database",
    ),
):
    """List Fairlight Sound Library index entries from Project.db or DaVinci Resolve Local Database User.db."""
    limit = _validate_sound_library_limit(limit)
    database_scope = _normalize_sound_library_database(database)
    enforce_mutation_policy("fairlight.sound_library_read", intended_engine="db_workaround", mutating=False)
    set_execution_engine("db_workaround")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    if is_dry_run():
        output(
            {
                **_sound_library_read_payload(
                    action="fairlight.sound_library.list",
                    query=query,
                    limit=limit,
                    database_scope=database_scope,
                ),
                "dry_run": True,
                "would_read": True,
            },
            title="Fairlight Sound Library List Plan",
        )
        return

    conn = get_connection(require_project=True)
    results, truncated, db_target = _query_sound_library_database(
        conn,
        database_scope=database_scope,
        query=query,
        limit=limit,
    )
    output(
        {
            **_sound_library_read_payload(
                action="fairlight.sound_library.list",
                query=query,
                limit=limit,
                database_scope=database_scope,
            ),
            "db_target": db_target,
            "found": bool(results),
            "count": len(results),
            "truncated": truncated,
            "results": results,
        },
        title="Fairlight Sound Library",
    )


@sound_library_app.command("search")
@handle_errors
def sound_library_search(
    query: str | None = typer.Argument(None, help="Search query"),
    limit: int = typer.Option(50, "--limit", help="Maximum results to return, 1-500"),
    database: str = typer.Option(
        "project",
        "--database",
        "--db",
        help="Sound Library DB scope: project/current-project or user/local-database",
    ),
):
    """Search Fairlight Sound Library index entries from Project.db or DaVinci Resolve Local Database User.db."""
    limit = _validate_sound_library_limit(limit)
    database_scope = _normalize_sound_library_database(database)
    enforce_mutation_policy("fairlight.sound_library_read", intended_engine="db_workaround", mutating=False)
    if not query:
        raise ValidationError(
            "Sound Library search query is required.",
            details={
                "example": "cutagent fairlight sound-library search footsteps --json",
                "required": ["query"],
                "api_note": "Fairlight Sound Library search is available through Project.db and Local Database User.db readback; local file indexing and DB-indexed insert have verified native/DB routes.",
            },
        )
    set_execution_engine("db_workaround")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    if is_dry_run():
        output(
            {
                **_sound_library_read_payload(
                    action="fairlight.sound_library.search",
                    query=query,
                    limit=limit,
                    database_scope=database_scope,
                ),
                "dry_run": True,
                "would_read": True,
            },
            title="Fairlight Sound Library Search Plan",
        )
        return

    conn = get_connection(require_project=True)
    results, truncated, db_target = _query_sound_library_database(
        conn,
        database_scope=database_scope,
        query=query,
        limit=limit,
    )
    output(
        {
            **_sound_library_read_payload(
                action="fairlight.sound_library.search",
                query=query,
                limit=limit,
                database_scope=database_scope,
            ),
            "db_target": db_target,
            "found": bool(results),
            "count": len(results),
            "truncated": truncated,
            "results": results,
        },
        title="Fairlight Sound Library Search",
    )


@sound_library_app.command("source-list")
@handle_errors
def sound_library_source_list(
    source_path: Path | None = typer.Option(None, "--path", "--source", help="Optional source/container path to inspect"),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive", help="When --path is set, include nested indexed source paths"),
    limit: int = typer.Option(100, "--limit", help="Maximum source rows to return, 1-500"),
    database: str = typer.Option(
        "project",
        "--database",
        "--db",
        help="Sound Library DB scope: project/current-project or user/local-database",
    ),
):
    """List indexed Fairlight Sound Library source/container paths."""
    limit = _validate_sound_library_limit(limit)
    database_scope = _normalize_sound_library_database(database)
    normalized_source_path = _normalize_sound_library_source_path(source_path) if source_path else None
    enforce_mutation_policy("fairlight.sound_library_read", intended_engine="db_workaround", mutating=False)
    if is_dry_run():
        set_execution_engine("db_workaround")
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.sound_library.source_list",
                "route": "db_workaround",
                "database": database_scope,
                "dry_run": True,
                "runtime_read_called": False,
                "target": _sound_library_database_target(database_scope),
                "source_path": normalized_source_path,
                "recursive": bool(recursive),
                "limit": limit,
                "db_target": {"database": database_scope, "target": _sound_library_database_target(database_scope)},
                "read_scope": "FLAssetBaseContainer source path aggregation",
            },
            title="Fairlight Sound Library Source List Plan",
        )
        return

    conn = get_connection(require_project=True)
    if database_scope == "user":
        db_target = _resolve_sound_library_user_db_target(conn)
        connection = sqlite3.connect(f"file:{db_target['db_path']}?mode=ro", uri=True, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            sources, truncated = _query_sound_library_sources(
                connection.cursor(),
                source_path=normalized_source_path,
                recursive=recursive,
                limit=limit,
            )
        finally:
            connection.close()
    else:
        cursor = conn.disk_db_cursor(allow_project_name_inference=True)
        sources, truncated = _query_sound_library_sources(
            cursor,
            source_path=normalized_source_path,
            recursive=recursive,
            limit=limit,
        )
        db_target = {
            "database": "project",
            "target": _sound_library_database_target("project"),
            "database_label": "current project",
            "source": "active_project_db_cursor",
        }
    set_execution_engine("db_workaround")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    output(
        {
            "action": "fairlight.sound_library.source_list",
            "route": "db_workaround",
            "database": database_scope,
            "runtime_read_called": False,
            "target": _sound_library_database_target(database_scope),
            "source_path": normalized_source_path,
            "recursive": bool(recursive),
            "limit": limit,
            "db_target": db_target,
            "found": bool(sources),
            "count": len(sources),
            "truncated": truncated,
            "sources": sources,
            "read_scope": "FLAssetBaseContainer source path aggregation",
            "limitations": {
                "audition": "not exposed by the DaVinci Resolve scripting API",
                "sync_to_playhead": "available for insert placement through FLAssetBaseClip.ed_sync alignment; Sound Library audition sync preview is not exposed by the DaVinci Resolve scripting API",
                "source_preference_store": (
                    "No separate Sound Library source-list preference store was found on this DaVinci Resolve 20 Free install; "
                    "indexed sources are derived from FLAssetBaseContainer.path/data_path."
                ),
            },
        },
        title="Fairlight Sound Library Sources",
    )


@sound_library_app.command("index-file")
@handle_errors
def sound_library_index_file(
    path: Path = typer.Argument(..., help="Local audio file path to register in the selected Sound Library index"),
    name: str | None = typer.Option(None, "--name", help="Sound Library clip name; defaults to file stem"),
    category: str | None = typer.Option(None, "--category", help="Optional Sound Library category"),
    description: str | None = typer.Option(None, "--description", help="Optional searchable description"),
    tag: list[str] | None = typer.Option(None, "--tag", help="Optional searchable user tag; repeat up to four times"),
    rating: int = typer.Option(0, "--rating", min=0, max=5, help="Star rating metadata, 0-5"),
    allow_duplicate: bool = typer.Option(False, "--allow-duplicate", help="Allow another Sound Library row for the same file path"),
    database: str = typer.Option(
        "project",
        "--database",
        "--db",
        help="Sound Library DB scope: project/current-project or user/local-database",
    ),
):
    """Register a local audio file in a Fairlight Sound Library DB index."""
    enforce_mutation_policy("fairlight.sound_library_index", intended_engine="db_workaround", mutating=not is_dry_run())
    database_scope = _normalize_sound_library_database(database)
    expanded_path = Path(path).expanduser().resolve()
    if not expanded_path.exists() or not expanded_path.is_file():
        raise ValidationError(
            "Sound Library index-file requires an existing local audio file.",
            details={"path": str(expanded_path), "exists": expanded_path.exists(), "is_file": expanded_path.is_file()},
            recoverability="not_applicable",
        )
    tags = _normalize_sound_library_tags(tag, workflow="index-file")
    clip_name = str(name or expanded_path.stem).strip() or expanded_path.name
    clip_category = str(category or "").strip() or None
    clip_description = str(description or "").strip() or None
    if is_dry_run():
        set_execution_engine("db_workaround")
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.sound_library.index_file",
                "route": "db_workaround",
                "database": database_scope,
                "dry_run": True,
                "would_write": True,
                "target": {"kind": "sound_library_file", "path": str(expanded_path), "name": clip_name},
                "requested": {
                    "category": clip_category,
                    "description": clip_description,
                    "tags": tags,
                    "rating": int(rating),
                    "allow_duplicate": bool(allow_duplicate),
                },
                "db_target": {"database": database_scope, "target": _sound_library_database_target(database_scope)},
                "db_write": {"tables": list(_SOUND_LIBRARY_REQUIRED_TABLES)},
                "verification": {"method": "sound_library_db_readback"},
            },
            title="Fairlight Sound Library Index File Plan",
        )
        return

    conn = get_connection(require_project=True)
    timeline_fps = float(getattr(conn, "fps", 0.0) or 0.0)
    metadata = _sound_library_audio_metadata(expanded_path, timeline_fps=timeline_fps)
    container_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())
    clip_id = str(uuid.uuid4())

    def _writer(_connection, cursor, _session):
        duplicate_rows = _sound_library_rows_for_path(cursor, str(expanded_path), limit=20)
        if duplicate_rows and not allow_duplicate:
            set_verification_status("not_requested")
            raise ValidationError(
                f"Sound Library file is already indexed in the {_sound_library_database_label(database_scope)} database.",
                details={
                    "database": database_scope,
                    "path": str(expanded_path),
                    "existing_count": len(duplicate_rows),
                    "existing": duplicate_rows,
                    "hint": "Pass --allow-duplicate to create another Sound Library clip row for the same file path.",
                },
                recoverability="not_applicable",
            )
        writes = _insert_sound_library_index_rows(
            cursor,
            expanded_path=expanded_path,
            metadata=metadata,
            clip_name=clip_name,
            clip_category=clip_category,
            clip_description=clip_description,
            tags=tags,
            rating=rating,
            container_id=container_id,
            file_id=file_id,
            clip_id=clip_id,
        )
        row_payload = _sound_library_index_row_payload(
            expanded_path=expanded_path,
            metadata=metadata,
            clip_name=clip_name,
            clip_category=clip_category,
            clip_description=clip_description,
            tags=tags,
            rating=rating,
            container_id=container_id,
            file_id=file_id,
            clip_id=clip_id,
        )
        return {
            "action": "fairlight.sound_library.index_file",
            "database": database_scope,
            "changed": True,
            "runtime_write_called": False,
            **row_payload,
            "db_write": {"tables": list(_SOUND_LIBRARY_REQUIRED_TABLES), "rows": writes},
            "duplicate_policy": {"allow_duplicate": bool(allow_duplicate), "existing_count_before": len(duplicate_rows)},
            "limitations": {
                "audition": "not exposed by the DaVinci Resolve scripting API",
                "sync_to_playhead": "available for insert placement through FLAssetBaseClip.ed_sync alignment; Sound Library audition sync preview is not exposed by the DaVinci Resolve scripting API",
            },
            "message": f"Indexed local audio file in the {_sound_library_database_label(database_scope)} Sound Library database.",
        }

    def _verifier(_fresh_conn, mutation_result, session):
        return _verify_sound_library_index_file(
            project_db_path=session.project_db_path if hasattr(session, "project_db_path") else session["db_path"],
            clip_id=mutation_result["ids"]["clip_id"],
            file_id=mutation_result["ids"]["file_id"],
            expected_path=str(expanded_path),
        )

    if database_scope == "user":
        data = _execute_sound_library_user_db_mutation(
            conn,
            context="Fairlight Sound Library index-file User.db write",
            writer=_writer,
            verifier=_verifier,
        )
    else:
        data = db_session.execute_sqlite_disk_db_mutation(
            conn,
            context="Fairlight Sound Library index-file DB write",
            writer=_writer,
            verifier=_verifier,
            allow_project_name_inference=True,
        )
    set_recoverability("manual")
    output(data, title="Fairlight Sound Library Index File")


@sound_library_app.command("index-folder")
@handle_errors
def sound_library_index_folder(
    folder: Path = typer.Argument(..., help="Local folder containing audio files to register in the selected Sound Library index"),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive", help="Scan nested folders for supported audio files"),
    max_files: int = typer.Option(200, "--max-files", min=1, max=5000, help="Maximum audio files to index in one DB mutation"),
    name_prefix: str | None = typer.Option(None, "--name-prefix", help="Optional prefix for generated Sound Library clip names"),
    category: str | None = typer.Option(None, "--category", help="Optional Sound Library category for all indexed files"),
    description: str | None = typer.Option(None, "--description", help="Optional searchable description for all indexed files"),
    tag: list[str] | None = typer.Option(None, "--tag", help="Optional searchable user tag; repeat up to four times"),
    rating: int = typer.Option(0, "--rating", min=0, max=5, help="Star rating metadata, 0-5"),
    allow_duplicate: bool = typer.Option(False, "--allow-duplicate", help="Allow additional Sound Library rows for file paths already indexed"),
    database: str = typer.Option(
        "project",
        "--database",
        "--db",
        help="Sound Library DB scope: project/current-project or user/local-database",
    ),
):
    """Register supported audio files from a local folder in a Fairlight Sound Library DB index."""
    enforce_mutation_policy("fairlight.sound_library_index", intended_engine="db_workaround", mutating=not is_dry_run())
    database_scope = _normalize_sound_library_database(database)
    expanded_folder = Path(folder).expanduser().resolve()
    if not expanded_folder.exists() or not expanded_folder.is_dir():
        raise ValidationError(
            "Sound Library index-folder requires an existing local folder.",
            details={
                "folder": str(expanded_folder),
                "exists": expanded_folder.exists(),
                "is_dir": expanded_folder.is_dir(),
            },
            recoverability="not_applicable",
        )
    tags = _normalize_sound_library_tags(tag, workflow="index-folder")
    clip_category = str(category or "").strip() or None
    clip_description = str(description or "").strip() or None
    prefix = str(name_prefix or "").strip()
    discovery = _discover_sound_library_audio_files(expanded_folder, recursive=recursive, max_files=max_files)
    discovered_files = list(discovery["files"])
    if not discovered_files:
        raise ValidationError(
            "Sound Library index-folder did not find supported audio files.",
            details={
                "folder": str(expanded_folder),
                "recursive": bool(recursive),
                "supported_extensions": sorted(_SOUND_LIBRARY_AUDIO_EXTENSIONS),
            },
            recoverability="not_applicable",
        )
    if is_dry_run():
        set_execution_engine("db_workaround")
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.sound_library.index_folder",
                "route": "db_workaround",
                "database": database_scope,
                "dry_run": True,
                "would_write": True,
                "target": {"kind": "sound_library_folder", "path": str(expanded_folder)},
                "discovery": {
                    **{key: value for key, value in discovery.items() if key != "files"},
                    "files": [str(path) for path in discovered_files[:50]],
                    "files_truncated_for_output": len(discovered_files) > 50,
                },
                "requested": {
                    "category": clip_category,
                    "description": clip_description,
                    "tags": tags,
                    "rating": int(rating),
                    "allow_duplicate": bool(allow_duplicate),
                    "name_prefix": prefix or None,
                },
                "db_target": {"database": database_scope, "target": _sound_library_database_target(database_scope)},
                "db_write": {"tables": list(_SOUND_LIBRARY_REQUIRED_TABLES)},
                "verification": {"method": "sound_library_db_readback"},
            },
            title="Fairlight Sound Library Index Folder Plan",
        )
        return

    conn = get_connection(require_project=True)
    timeline_fps = float(getattr(conn, "fps", 0.0) or 0.0)
    prepared: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for audio_path in discovered_files:
        try:
            metadata = _sound_library_audio_metadata(audio_path, timeline_fps=timeline_fps)
        except ValidationError as exc:
            skipped.append({"path": str(audio_path), "reason": "audio_metadata_failed", "details": exc.details})
            continue
        clip_name = f"{prefix}{audio_path.stem}".strip() or audio_path.name
        prepared.append(
            {
                "path": audio_path,
                "metadata": metadata,
                "clip_name": clip_name,
                "container_id": str(uuid.uuid4()),
                "file_id": str(uuid.uuid4()),
                "clip_id": str(uuid.uuid4()),
            }
        )
    if not prepared:
        raise ValidationError(
            "Sound Library index-folder did not find files with readable audio streams.",
            details={"folder": str(expanded_folder), "discovery_count": len(discovered_files), "skipped": skipped},
            recoverability="not_applicable",
        )

    def _index_folder_payload(
        *,
        changed: bool,
        indexed: list[dict[str, Any]],
        duplicate_skips: list[dict[str, Any]],
        message: str,
    ) -> dict[str, Any]:
        return {
            "action": "fairlight.sound_library.index_folder",
            "database": database_scope,
            "changed": bool(changed),
            "runtime_write_called": False,
            "target": {"kind": "sound_library_folder", "path": str(expanded_folder)},
            "discovery": {
                **{key: value for key, value in discovery.items() if key != "files"},
                "files": [str(path) for path in discovered_files],
            },
            "indexed_count": len(indexed),
            "skipped_count": len(skipped) + len(duplicate_skips),
            "indexed": indexed,
            "skipped": [*skipped, *duplicate_skips],
            "metadata": {
                "category": clip_category,
                "description": clip_description,
                "tags": tags,
                "rating": int(rating),
                "name_prefix": prefix or None,
            },
            "db_write": {"tables": list(_SOUND_LIBRARY_REQUIRED_TABLES)},
            "duplicate_policy": {"allow_duplicate": bool(allow_duplicate)},
            "limitations": {
                "audition": "not exposed by the DaVinci Resolve scripting API",
                "sync_to_playhead": "available for insert placement through FLAssetBaseClip.ed_sync alignment; Sound Library audition sync preview is not exposed by the DaVinci Resolve scripting API",
                "source_management": "source-list/source-remove/source-rebuild operate on FLAssetBaseContainer path/data_path rows; no separate Sound Library panel source preference store was found locally",
            },
            "message": message,
        }

    def _writer(_connection, cursor, _session):
        indexed: list[dict[str, Any]] = []
        duplicate_skips: list[dict[str, Any]] = []
        for item in prepared:
            audio_path = item["path"]
            duplicate_rows = _sound_library_rows_for_path(cursor, str(audio_path), limit=20)
            if duplicate_rows and not allow_duplicate:
                duplicate_skips.append(
                    {
                        "path": str(audio_path),
                        "reason": "already_indexed",
                        "existing_count": len(duplicate_rows),
                        "existing": duplicate_rows,
                    }
                )
                continue
            writes = _insert_sound_library_index_rows(
                cursor,
                expanded_path=audio_path,
                metadata=item["metadata"],
                clip_name=item["clip_name"],
                clip_category=clip_category,
                clip_description=clip_description,
                tags=tags,
                rating=rating,
                container_id=item["container_id"],
                file_id=item["file_id"],
                clip_id=item["clip_id"],
            )
            row_payload = _sound_library_index_row_payload(
                expanded_path=audio_path,
                metadata=item["metadata"],
                clip_name=item["clip_name"],
                clip_category=clip_category,
                clip_description=clip_description,
                tags=tags,
                rating=rating,
                container_id=item["container_id"],
                file_id=item["file_id"],
                clip_id=item["clip_id"],
            )
            indexed.append(
                {
                    **row_payload,
                    "db_write": {"rows": writes},
                    "duplicate_policy": {
                        "allow_duplicate": bool(allow_duplicate),
                        "existing_count_before": len(duplicate_rows),
                    },
                }
            )
        if not indexed:
            return _index_folder_payload(
                changed=False,
                indexed=[],
                duplicate_skips=duplicate_skips,
                message="No new Sound Library rows were indexed; readable files were already present or skipped.",
            )
        return _index_folder_payload(
            changed=True,
            indexed=indexed,
            duplicate_skips=duplicate_skips,
            message=f"Indexed local audio folder files in the {_sound_library_database_label(database_scope)} Sound Library database.",
        )

    def _verifier(_fresh_conn, mutation_result, session):
        db_path = session.project_db_path if hasattr(session, "project_db_path") else session["db_path"]
        indexed_records = mutation_result.get("indexed") if isinstance(mutation_result, dict) else None
        if not indexed_records:
            duplicate_paths = [
                str(entry.get("path"))
                for entry in (mutation_result.get("skipped") or [])
                if isinstance(entry, dict) and entry.get("reason") == "already_indexed" and entry.get("path")
            ]
            checks: list[dict[str, Any]] = []
            registered_items: list[dict[str, Any]] = []
            connection = sqlite3.connect(db_path)
            connection.row_factory = sqlite3.Row
            try:
                cursor = connection.cursor()
                for duplicate_path in duplicate_paths:
                    rows = _sound_library_rows_for_path(cursor, duplicate_path, limit=20)
                    registered_items.extend(rows)
                    checks.append(
                        {
                            "name": "duplicate_existing_record_found",
                            "ok": bool(rows),
                            "path": duplicate_path,
                            "existing_count": len(rows),
                        }
                    )
            finally:
                connection.close()
            return {
                "status": "verified" if checks and all(check["ok"] for check in checks) else "failed",
                "method": "sound_library_duplicate_db_readback",
                "checks": checks,
                "registered_items": registered_items,
            }
        return _verify_sound_library_index_records(
            project_db_path=db_path,
            indexed_records=indexed_records,
        )

    if database_scope == "user":
        data = _execute_sound_library_user_db_mutation(
            conn,
            context="Fairlight Sound Library index-folder User.db write",
            writer=_writer,
            verifier=_verifier,
        )
    else:
        data = db_session.execute_sqlite_disk_db_mutation(
            conn,
            context="Fairlight Sound Library index-folder DB write",
            writer=_writer,
            verifier=_verifier,
            allow_project_name_inference=True,
        )
    set_recoverability("manual")
    output(data, title="Fairlight Sound Library Index Folder")


@sound_library_app.command("source-remove")
@handle_errors
def sound_library_source_remove(
    source_path: Path = typer.Argument(..., help="Indexed Sound Library source/container folder path to remove from the DB index"),
    recursive: bool = typer.Option(False, "--recursive/--no-recursive", help="Also remove nested indexed source paths"),
    database: str = typer.Option(
        "project",
        "--database",
        "--db",
        help="Sound Library DB scope: project/current-project or user/local-database",
    ),
):
    """Remove all Fairlight Sound Library DB index rows for one indexed source path."""
    database_scope = _normalize_sound_library_database(database)
    normalized_source = _normalize_sound_library_source_path(source_path)
    enforce_mutation_policy("fairlight.sound_library_delete", intended_engine="db_workaround", mutating=not is_dry_run())
    if is_dry_run():
        set_execution_engine("db_workaround")
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.sound_library.source_remove",
                "route": "db_workaround",
                "database": database_scope,
                "dry_run": True,
                "would_delete": True,
                "runtime_write_called": False,
                "target": {"kind": "sound_library_source", "path": normalized_source},
                "recursive": bool(recursive),
                "db_target": {"database": database_scope, "target": _sound_library_database_target(database_scope)},
                "db_write": {"tables": list(_SOUND_LIBRARY_REQUIRED_TABLES)},
                "verification": {"method": "sound_library_source_db_readback"},
                "limitations": {
                    "media_file_delete": "not performed; only Sound Library DB index rows are removed",
                    "audition": "not exposed by the DaVinci Resolve scripting API",
                    "sync_to_playhead": "available for insert placement through FLAssetBaseClip.ed_sync alignment; Sound Library audition sync preview is not exposed by the DaVinci Resolve scripting API",
                },
            },
            title="Fairlight Sound Library Source Remove Plan",
        )
        return

    conn = get_connection(require_project=True)

    def _writer(_connection, cursor, _session):
        removed = _delete_sound_library_source_rows(
            cursor,
            source_path=normalized_source,
            recursive=recursive,
        )
        return {
            "action": "fairlight.sound_library.source_remove",
            "database": database_scope,
            "changed": bool(
                removed["clip_rows_deleted"]
                or removed["file_rows_deleted"]
                or removed["container_rows_deleted"]
            ),
            "runtime_write_called": False,
            "target": {"kind": "sound_library_source", "path": normalized_source},
            "recursive": bool(recursive),
            "removed": removed,
            "db_write": {"tables": list(_SOUND_LIBRARY_REQUIRED_TABLES)},
            "limitations": {
                "media_file_delete": "not performed; only Sound Library DB index rows are removed",
                "audition": "not exposed by the DaVinci Resolve scripting API",
                "sync_to_playhead": "available for insert placement through FLAssetBaseClip.ed_sync alignment; Sound Library audition sync preview is not exposed by the DaVinci Resolve scripting API",
            },
            "message": f"Removed Sound Library source index rows from the {_sound_library_database_label(database_scope)} database.",
        }

    def _verifier(_fresh_conn, mutation_result, session):
        return _verify_sound_library_source_absent(
            project_db_path=session.project_db_path if hasattr(session, "project_db_path") else session["db_path"],
            source_path=normalized_source,
            recursive=recursive,
        )

    if database_scope == "user":
        data = _execute_sound_library_user_db_mutation(
            conn,
            context="Fairlight Sound Library source-remove User.db write",
            writer=_writer,
            verifier=_verifier,
        )
    else:
        data = db_session.execute_sqlite_disk_db_mutation(
            conn,
            context="Fairlight Sound Library source-remove DB write",
            writer=_writer,
            verifier=_verifier,
            allow_project_name_inference=True,
        )
    set_recoverability("manual")
    output(data, title="Fairlight Sound Library Source Remove")


@sound_library_app.command("source-rebuild")
@handle_errors
def sound_library_source_rebuild(
    folder: Path = typer.Argument(..., help="Local Sound Library source folder to delete from the DB index and rescan"),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive", help="Rescan nested folders and clear nested indexed source paths"),
    max_files: int = typer.Option(200, "--max-files", min=1, max=5000, help="Maximum audio files to index in one DB mutation"),
    name_prefix: str | None = typer.Option(None, "--name-prefix", help="Optional prefix for generated Sound Library clip names"),
    category: str | None = typer.Option(None, "--category", help="Optional Sound Library category for all indexed files"),
    description: str | None = typer.Option(None, "--description", help="Optional searchable description for all indexed files"),
    tag: list[str] | None = typer.Option(None, "--tag", help="Optional searchable user tag; repeat up to four times"),
    rating: int = typer.Option(0, "--rating", min=0, max=5, help="Star rating metadata, 0-5"),
    allow_duplicate: bool = typer.Option(False, "--allow-duplicate", help="Allow additional Sound Library rows for file paths already indexed elsewhere"),
    database: str = typer.Option(
        "project",
        "--database",
        "--db",
        help="Sound Library DB scope: project/current-project or user/local-database",
    ),
):
    """Delete and rebuild one Fairlight Sound Library source folder in the selected DB index."""
    database_scope = _normalize_sound_library_database(database)
    enforce_mutation_policy("fairlight.sound_library_index", intended_engine="db_workaround", mutating=not is_dry_run())
    expanded_folder = Path(folder).expanduser().resolve()
    if not expanded_folder.exists() or not expanded_folder.is_dir():
        raise ValidationError(
            "Sound Library source-rebuild requires an existing local folder.",
            details={
                "folder": str(expanded_folder),
                "exists": expanded_folder.exists(),
                "is_dir": expanded_folder.is_dir(),
            },
            recoverability="not_applicable",
        )
    tags = _normalize_sound_library_tags(tag, workflow="source-rebuild")
    clip_category = str(category or "").strip() or None
    clip_description = str(description or "").strip() or None
    prefix = str(name_prefix or "").strip()
    discovery = _discover_sound_library_audio_files(expanded_folder, recursive=recursive, max_files=max_files)
    discovered_files = list(discovery["files"])
    if not discovered_files:
        raise ValidationError(
            "Sound Library source-rebuild did not find supported audio files.",
            details={
                "folder": str(expanded_folder),
                "recursive": bool(recursive),
                "supported_extensions": sorted(_SOUND_LIBRARY_AUDIO_EXTENSIONS),
            },
            recoverability="not_applicable",
        )
    if is_dry_run():
        set_execution_engine("db_workaround")
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.sound_library.source_rebuild",
                "route": "db_workaround",
                "database": database_scope,
                "dry_run": True,
                "would_delete": True,
                "would_write": True,
                "runtime_write_called": False,
                "target": {"kind": "sound_library_source", "path": str(expanded_folder)},
                "recursive": bool(recursive),
                "discovery": {
                    **{key: value for key, value in discovery.items() if key != "files"},
                    "files": [str(path) for path in discovered_files[:50]],
                    "files_truncated_for_output": len(discovered_files) > 50,
                },
                "requested": {
                    "category": clip_category,
                    "description": clip_description,
                    "tags": tags,
                    "rating": int(rating),
                    "allow_duplicate": bool(allow_duplicate),
                    "name_prefix": prefix or None,
                },
                "db_target": {"database": database_scope, "target": _sound_library_database_target(database_scope)},
                "db_write": {"tables": list(_SOUND_LIBRARY_REQUIRED_TABLES)},
                "verification": {"method": "sound_library_db_readback"},
            },
            title="Fairlight Sound Library Source Rebuild Plan",
        )
        return

    conn = get_connection(require_project=True)
    timeline_fps = float(getattr(conn, "fps", 0.0) or 0.0)
    prepared: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for audio_path in discovered_files:
        try:
            metadata = _sound_library_audio_metadata(audio_path, timeline_fps=timeline_fps)
        except ValidationError as exc:
            skipped.append({"path": str(audio_path), "reason": "audio_metadata_failed", "details": exc.details})
            continue
        clip_name = f"{prefix}{audio_path.stem}".strip() or audio_path.name
        prepared.append(
            {
                "path": audio_path,
                "metadata": metadata,
                "clip_name": clip_name,
                "container_id": str(uuid.uuid4()),
                "file_id": str(uuid.uuid4()),
                "clip_id": str(uuid.uuid4()),
            }
        )
    if not prepared:
        raise ValidationError(
            "Sound Library source-rebuild did not find files with readable audio streams.",
            details={"folder": str(expanded_folder), "discovery_count": len(discovered_files), "skipped": skipped},
            recoverability="not_applicable",
        )

    def _writer(_connection, cursor, _session):
        removed = _delete_sound_library_source_rows(
            cursor,
            source_path=str(expanded_folder),
            recursive=recursive,
            missing_ok=True,
        )
        indexed: list[dict[str, Any]] = []
        duplicate_skips: list[dict[str, Any]] = []
        for item in prepared:
            audio_path = item["path"]
            duplicate_rows = _sound_library_rows_for_path(cursor, str(audio_path), limit=20)
            if duplicate_rows and not allow_duplicate:
                duplicate_skips.append(
                    {
                        "path": str(audio_path),
                        "reason": "already_indexed_elsewhere",
                        "existing_count": len(duplicate_rows),
                        "existing": duplicate_rows,
                    }
                )
                continue
            writes = _insert_sound_library_index_rows(
                cursor,
                expanded_path=audio_path,
                metadata=item["metadata"],
                clip_name=item["clip_name"],
                clip_category=clip_category,
                clip_description=clip_description,
                tags=tags,
                rating=rating,
                container_id=item["container_id"],
                file_id=item["file_id"],
                clip_id=item["clip_id"],
            )
            row_payload = _sound_library_index_row_payload(
                expanded_path=audio_path,
                metadata=item["metadata"],
                clip_name=item["clip_name"],
                clip_category=clip_category,
                clip_description=clip_description,
                tags=tags,
                rating=rating,
                container_id=item["container_id"],
                file_id=item["file_id"],
                clip_id=item["clip_id"],
            )
            indexed.append(
                {
                    **row_payload,
                    "db_write": {"rows": writes},
                    "duplicate_policy": {
                        "allow_duplicate": bool(allow_duplicate),
                        "existing_count_before": len(duplicate_rows),
                    },
                }
            )
        changed = bool(
            indexed
            or removed["clip_rows_deleted"]
            or removed["file_rows_deleted"]
            or removed["container_rows_deleted"]
        )
        return {
            "action": "fairlight.sound_library.source_rebuild",
            "database": database_scope,
            "changed": changed,
            "runtime_write_called": False,
            "target": {"kind": "sound_library_source", "path": str(expanded_folder)},
            "recursive": bool(recursive),
            "removed": removed,
            "discovery": {
                **{key: value for key, value in discovery.items() if key != "files"},
                "files": [str(path) for path in discovered_files],
            },
            "indexed_count": len(indexed),
            "skipped_count": len(skipped) + len(duplicate_skips),
            "indexed": indexed,
            "skipped": [*skipped, *duplicate_skips],
            "metadata": {
                "category": clip_category,
                "description": clip_description,
                "tags": tags,
                "rating": int(rating),
                "name_prefix": prefix or None,
            },
            "db_write": {"tables": list(_SOUND_LIBRARY_REQUIRED_TABLES)},
            "duplicate_policy": {"allow_duplicate": bool(allow_duplicate)},
            "limitations": {
                "audition": "not exposed by the DaVinci Resolve scripting API",
                "sync_to_playhead": "available for insert placement through FLAssetBaseClip.ed_sync alignment; Sound Library audition sync preview is not exposed by the DaVinci Resolve scripting API",
                "media_file_delete": "not performed; source-rebuild only removes stale Sound Library DB index rows before rescan",
            },
            "message": f"Rebuilt Sound Library source rows in the {_sound_library_database_label(database_scope)} database.",
        }

    def _verifier(_fresh_conn, mutation_result, session):
        db_path = session.project_db_path if hasattr(session, "project_db_path") else session["db_path"]
        indexed_records = mutation_result.get("indexed") if isinstance(mutation_result, dict) else None
        if indexed_records:
            return _verify_sound_library_index_records(
                project_db_path=db_path,
                indexed_records=indexed_records,
            )
        return _verify_sound_library_source_absent(
            project_db_path=db_path,
            source_path=str(expanded_folder),
            recursive=recursive,
        )

    if database_scope == "user":
        data = _execute_sound_library_user_db_mutation(
            conn,
            context="Fairlight Sound Library source-rebuild User.db write",
            writer=_writer,
            verifier=_verifier,
        )
    else:
        data = db_session.execute_sqlite_disk_db_mutation(
            conn,
            context="Fairlight Sound Library source-rebuild DB write",
            writer=_writer,
            verifier=_verifier,
            allow_project_name_inference=True,
        )
    set_recoverability("manual")
    output(data, title="Fairlight Sound Library Source Rebuild")

