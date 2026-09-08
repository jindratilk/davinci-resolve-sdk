"""Fairlight Sound Library database helpers."""

from __future__ import annotations

def _normalize_sound_library_database(database: str | None) -> str:
    normalized = str(database or "project").strip().lower().replace(" ", "_")
    scope = _SOUND_LIBRARY_DATABASE_ALIASES.get(normalized)
    if scope is None:
        raise ValidationError(
            "Unsupported Sound Library database scope.",
            details={
                "database": database,
                "supported": ["project", "user"],
                "aliases": sorted(_SOUND_LIBRARY_DATABASE_ALIASES),
            },
            recoverability="not_applicable",
        )
    return scope


def _sound_library_database_target(scope: str) -> str:
    return "local_database_sound_library_index" if scope == "user" else "current_project_sound_library_index"


def _sound_library_database_label(scope: str) -> str:
    return "DaVinci Resolve Local Database User.db" if scope == "user" else "current project Project.db"


def _validate_sound_library_limit(limit: int) -> int:
    if limit < 1 or limit > 500:
        raise ValidationError(
            "Sound Library limit must be between 1 and 500.",
            details={"limit": limit, "min": 1, "max": 500},
            recoverability="not_applicable",
        )
    return limit


def _sound_library_missing_tables(cursor: sqlite3.Cursor) -> list[str]:
    placeholders = ", ".join("?" for _ in _SOUND_LIBRARY_REQUIRED_TABLES)
    rows = cursor.execute(
        f"SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ({placeholders})",
        _SOUND_LIBRARY_REQUIRED_TABLES,
    ).fetchall()
    existing = {str(row["name"] if hasattr(row, "keys") else row[0]) for row in rows}
    return [table for table in _SOUND_LIBRARY_REQUIRED_TABLES if table not in existing]


def _sound_library_table_columns(cursor: sqlite3.Cursor, table_name: str) -> set[str]:
    try:
        rows = cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
    except sqlite3.Error:
        return set()
    return {str(row["name"] if hasattr(row, "keys") else row[1]) for row in rows}


def _validate_sound_library_sqlite_db(
    db_path: str | Path,
    *,
    database_scope: str,
    validate_schema: bool = True,
) -> str:
    path = Path(db_path).expanduser()
    if not path.exists() or not path.is_file():
        raise ReadinessFailed(
            "Fairlight Sound Library database file is missing.",
            details={
                "database": database_scope,
                "db_path": str(path),
                "exists": path.exists(),
                "is_file": path.is_file(),
            },
            recoverability="manual",
        )
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA schema_version").fetchone()
        if validate_schema:
            missing_tables = _sound_library_missing_tables(connection.cursor())
            if missing_tables:
                raise ReadinessFailed(
                    "Fairlight Sound Library index tables are not present in the selected database.",
                    details={
                        "database": database_scope,
                        "db_path": str(path),
                        "missing_tables": missing_tables,
                        "required_tables": list(_SOUND_LIBRARY_REQUIRED_TABLES),
                    },
                    recoverability="manual",
                )
    except ReadinessFailed:
        raise
    except sqlite3.Error as exc:
        raise ReadinessFailed(
            "Fairlight Sound Library database is not a readable SQLite database.",
            details={
                "database": database_scope,
                "db_path": str(path),
                "sqlite_error_type": exc.__class__.__name__,
                "sqlite_error": str(exc),
            },
            recoverability="manual",
        ) from exc
    finally:
        if connection is not None:
            connection.close()
    return str(path)


def _resolve_sound_library_user_db_target(conn, *, validate_schema: bool = True) -> dict[str, Any]:
    from ..runtime_health import resolve_current_disk_project_db

    current_project_db = resolve_current_disk_project_db(conn, allow_project_name_inference=True)
    project_db_path = Path(str(current_project_db.get("project_db_path") or "")).expanduser()
    if project_db_path.name != "Project.db":
        raise ReadinessFailed(
            "Could not infer the DaVinci Resolve Local Database User.db path from the active Project.db path.",
            details={
                "project_db_path": str(project_db_path),
                "current_database": current_project_db,
                "expected_shape": ".../Resolve Projects/Users/<user>/Projects/<project>/Project.db",
            },
            recoverability="manual",
        )
    projects_dirs = [parent for parent in project_db_path.parents if parent.name == "Projects"]
    user_dir = (
        next(
            (
                projects_dir.parent
                for projects_dir in projects_dirs
                if (projects_dir.parent / "User.db").exists()
            ),
            projects_dirs[-1].parent if projects_dirs else project_db_path.parent.parent.parent,
        )
    )
    user_db_path = _validate_sound_library_sqlite_db(
        user_dir / "User.db",
        database_scope="user",
        validate_schema=validate_schema,
    )
    return {
        "database": "user",
        "target": _sound_library_database_target("user"),
        "db_path": user_db_path,
        "user_db_path": user_db_path,
        "project_db_path": str(project_db_path),
        "project_name": current_project_db.get("project_name"),
        "current_database": current_project_db,
        "database_label": "Local Database",
        "source": "active_project_disk_user_db",
    }


def _query_sound_library_database(
    conn,
    *,
    database_scope: str,
    query: str | None,
    clip_id: str | None = None,
    file_id: str | None = None,
    file_path: str | None = None,
    limit: int,
) -> tuple[list[dict[str, Any]], bool, dict[str, Any]]:
    if database_scope == "user":
        db_target = _resolve_sound_library_user_db_target(conn)
        connection = sqlite3.connect(f"file:{db_target['db_path']}?mode=ro", uri=True, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            results, truncated = _query_sound_library_rows(
                connection.cursor(),
                query=query,
                clip_id=clip_id,
                file_id=file_id,
                file_path=file_path,
                limit=limit,
            )
        finally:
            connection.close()
        return results, truncated, db_target

    cursor = conn.disk_db_cursor(allow_project_name_inference=True)
    results, truncated = _query_sound_library_rows(
        cursor,
        query=query,
        clip_id=clip_id,
        file_id=file_id,
        file_path=file_path,
        limit=limit,
    )
    return results, truncated, {
        "database": "project",
        "target": _sound_library_database_target("project"),
        "database_label": "current project",
        "source": "active_project_db_cursor",
    }


def _execute_sound_library_user_db_mutation(
    conn,
    *,
    context: str,
    writer,
    verifier=None,
) -> dict[str, Any]:
    db_target = _resolve_sound_library_user_db_target(conn)
    user_db_path = str(db_target["db_path"])
    backup_path = f"{user_db_path}.cutagent-sound-library.bak"
    steps: list[str] = []
    mutation_result: Any = None
    verification: Any = None
    with db_session._exclusive_disk_db_mutation_lock(  # type: ignore[attr-defined]
        context=context,
        project_db_path=user_db_path,
        timeout_seconds=60.0,
    ) as lock_path:
        steps.append("acquire_user_db_lock")
        shutil.copy2(user_db_path, backup_path)
        steps.append("backup_user_db")
        connection: sqlite3.Connection | None = None
        committed = False
        try:
            connection = sqlite3.connect(user_db_path, timeout=5.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 5000")
            cursor = connection.cursor()
            try:
                db_session._begin_disk_db_transaction(connection)  # type: ignore[attr-defined]
            except sqlite3.OperationalError as exc:
                if db_session._is_locked_operational_error(exc):  # type: ignore[attr-defined]
                    db_session._raise_disk_db_locked(  # type: ignore[attr-defined]
                        context=context,
                        project_db_path=user_db_path,
                        step="sqlite_begin",
                        error=exc,
                    )
                raise
            try:
                mutation_result = writer(connection, cursor, db_target)
                connection.commit()
                committed = True
            except sqlite3.OperationalError as exc:
                connection.rollback()
                if db_session._is_locked_operational_error(exc):  # type: ignore[attr-defined]
                    db_session._raise_disk_db_locked(  # type: ignore[attr-defined]
                        context=context,
                        project_db_path=user_db_path,
                        step="sqlite_write",
                        error=exc,
                    )
                raise
            except Exception:
                connection.rollback()
                raise
        except Exception as exc:
            if committed:
                try:
                    shutil.copy2(backup_path, user_db_path)
                    steps.append("restore_user_db_from_backup")
                except Exception as rollback_exc:
                    raise APICallFailed(
                        "DaVinci Resolve Local Database User.db mutation failed and rollback failed.",
                        details={
                            "reason": "sound_library_user_db_rollback_failed",
                            "context": context,
                            "user_db_path": user_db_path,
                            "backup_path": backup_path,
                            "steps": steps,
                            "original_error": {"type": exc.__class__.__name__, "message": str(exc)},
                            "rollback_error": {
                                "type": rollback_exc.__class__.__name__,
                                "message": str(rollback_exc),
                            },
                        },
                        recoverability="manual",
                    ) from rollback_exc
            raise
        finally:
            if connection is not None:
                connection.close()
        steps.append("sqlite_commit")

        if verifier is not None:
            try:
                verification = verifier(None, mutation_result, db_target)
            except Exception as exc:
                try:
                    shutil.copy2(backup_path, user_db_path)
                    steps.append("restore_user_db_from_backup")
                except Exception as rollback_exc:
                    raise APICallFailed(
                        "DaVinci Resolve Local Database User.db mutation committed, but verification and rollback failed.",
                        details={
                            "reason": "sound_library_user_db_verify_rollback_failed",
                            "context": context,
                            "user_db_path": user_db_path,
                            "backup_path": backup_path,
                            "steps": steps,
                            "original_error": {"type": exc.__class__.__name__, "message": str(exc)},
                            "rollback_error": {
                                "type": rollback_exc.__class__.__name__,
                                "message": str(rollback_exc),
                            },
                        },
                        recoverability="manual",
                    ) from rollback_exc
                raise
            steps.append("verify")

    set_execution_engine("db_workaround")
    verification_status = "verified"
    if isinstance(verification, dict) and verification.get("status"):
        verification_status = str(verification.get("status"))
    set_verification_status(verification_status)
    payload = mutation_result if isinstance(mutation_result, dict) else {"result": mutation_result}
    payload.update(
        {
            "route": "db_native",
            "database": "user",
            "db_target": db_target,
            "user_db_path": user_db_path,
            "backup_path": backup_path,
            "lock_path": lock_path,
            "steps": steps,
        }
    )
    if verification is not None:
        payload["verification"] = verification
    return payload


def _quote_sound_library_identifier(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


def _insert_sound_library_row(cursor: sqlite3.Cursor, table_name: str, values: dict[str, Any]) -> dict[str, Any]:
    columns = _sound_library_table_columns(cursor, table_name)
    if not columns:
        raise ReadinessFailed(
            "Fairlight Sound Library table is not present in the current project database.",
            details={"table": table_name, "precondition": "fairlight_sound_library_project_db_schema"},
        )
    selected = {key: value for key, value in values.items() if key in columns}
    if not selected:
        raise ReadinessFailed(
            "Fairlight Sound Library table does not expose any writable known columns.",
            details={"table": table_name, "available_columns": sorted(columns), "candidate_columns": sorted(values)},
        )
    quoted_table = _quote_sound_library_identifier(table_name)
    quoted_columns = ", ".join(_quote_sound_library_identifier(column) for column in selected)
    placeholders = ", ".join("?" for _ in selected)
    cursor.execute(
        f"INSERT INTO {quoted_table} ({quoted_columns}) VALUES ({placeholders})",
        tuple(selected.values()),
    )
    return {"table": table_name, "columns": list(selected), "row_id": values.get(f"{table_name}_id")}


def _sound_library_rows_for_path(cursor: sqlite3.Cursor, path: str, *, limit: int = 20) -> list[dict[str, Any]]:
    missing_tables = _sound_library_missing_tables(cursor)
    if missing_tables:
        raise ReadinessFailed(
            "Fairlight Sound Library index tables are not present in the current project database.",
            details={
                "missing_tables": missing_tables,
                "required_tables": list(_SOUND_LIBRARY_REQUIRED_TABLES),
                "precondition": "fairlight_sound_library_project_db_schema",
            },
        )
    rows = cursor.execute(
        """
        SELECT
            clip.FLAssetBaseClip_id AS clip_id,
            clip.name AS name,
            clip.filename AS clip_filename,
            library_file.FLAssetBaseFile_id AS file_id,
            library_file.filename AS file_filename,
            library_file.path AS file_path,
            container.FLAssetBaseContainer_id AS container_id,
            container.path AS container_path
        FROM FLAssetBaseFile library_file
        LEFT JOIN FLAssetBaseClip clip
          ON CAST(clip.file_cookie AS TEXT) = CAST(library_file.FLAssetBaseFile_id AS TEXT)
          OR CAST(clip.file_cookie AS TEXT) = CAST(library_file.cookie AS TEXT)
        LEFT JOIN FLAssetBaseContainer container
          ON CAST(container.FLAssetBaseContainer_id AS TEXT) = CAST(library_file.container_cookie AS TEXT)
          OR CAST(container.cookie AS TEXT) = CAST(library_file.container_cookie AS TEXT)
        WHERE lower(COALESCE(library_file.path, '')) = lower(?)
        ORDER BY COALESCE(clip.name, library_file.filename) COLLATE NOCASE
        LIMIT ?
        """,
        (str(path), int(limit)),
    ).fetchall()
    return [_sqlite_row_to_dict(cursor, row) for row in rows]


def _sound_library_audio_metadata(path: Path, *, timeline_fps: float | None = None) -> dict[str, Any]:
    info = audio_ops.info(str(path))
    if int(info.get("audio_stream_count") or 0) < 1:
        raise ValidationError(
            "Sound Library index-file requires an audio file with at least one audio stream.",
            details={"path": str(path), "audio_info": info},
            recoverability="not_applicable",
        )
    stream = (info.get("streams") or [{}])[0]

    def _coerce_int(value: Any, default: int = 0) -> int:
        try:
            return int(float(value))
        except Exception:
            return default

    def _coerce_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return default

    sample_rate = _coerce_int(stream.get("sample_rate") or info.get("sample_rate"), 0)
    duration_seconds = _coerce_float(stream.get("duration") or info.get("duration"), 0.0)
    duration_samples = int(round(duration_seconds * sample_rate)) if sample_rate > 0 and duration_seconds > 0 else 0
    return {
        "audio_info": info,
        "sample_rate": sample_rate,
        "channel_count": _coerce_int(stream.get("channels") or info.get("channels"), 0),
        "duration_seconds": duration_seconds,
        "duration_samples": duration_samples,
        "frame_rate": float(timeline_fps or 0.0) or None,
        "bit_depth": 0,
        "filetype": 0,
    }


def _normalize_sound_library_tags(tag: list[str] | None, *, workflow: str) -> list[str]:
    tags = [str(value).strip() for value in (tag or []) if str(value).strip()]
    if len(tags) > 4:
        raise ValidationError(
            f"Sound Library {workflow} supports at most four --tag values.",
            details={"tag_count": len(tags), "max": 4, "tags": tags},
            recoverability="not_applicable",
        )
    return tags


def _sound_library_index_row_payload(
    *,
    expanded_path: Path,
    metadata: dict[str, Any],
    clip_name: str,
    clip_category: str | None,
    clip_description: str | None,
    tags: list[str],
    rating: int,
    container_id: str,
    file_id: str,
    clip_id: str,
) -> dict[str, Any]:
    return {
        "target": {"kind": "sound_library_file", "path": str(expanded_path), "name": clip_name},
        "ids": {"container_id": container_id, "file_id": file_id, "clip_id": clip_id},
        "audio_metadata": {
            "sample_rate": metadata["sample_rate"],
            "channel_count": metadata["channel_count"],
            "duration_seconds": metadata["duration_seconds"],
            "duration_samples": metadata["duration_samples"],
            "frame_rate": metadata["frame_rate"],
        },
        "metadata": {
            "category": clip_category,
            "description": clip_description,
            "tags": tags,
            "rating": int(rating),
        },
    }


def _insert_sound_library_index_rows(
    cursor: sqlite3.Cursor,
    *,
    expanded_path: Path,
    metadata: dict[str, Any],
    clip_name: str,
    clip_category: str | None,
    clip_description: str | None,
    tags: list[str],
    rating: int,
    container_id: str,
    file_id: str,
    clip_id: str,
) -> list[dict[str, Any]]:
    tag_values = [*tags, None, None, None, None][:4]
    parent_path = str(expanded_path.parent)
    filename = expanded_path.name
    return [
        _insert_sound_library_row(
            cursor,
            "FLAssetBaseContainer",
            {
                "FLAssetBaseContainer_id": container_id,
                "DbType": "FLAssetBaseContainer",
                "description": clip_category or "CutAgent indexed audio",
                "cookie": 0,
                "path": parent_path,
                "data_path": parent_path,
                "FieldsBlob": None,
            },
        ),
        _insert_sound_library_row(
            cursor,
            "FLAssetBaseFile",
            {
                "FLAssetBaseFile_id": file_id,
                "DbType": "FLAssetBaseFile",
                "filename": filename,
                "cookie": 0,
                "filetype": int(metadata["filetype"]),
                "sample_rate": int(metadata["sample_rate"]),
                "frame_rate": metadata["frame_rate"],
                "duration": int(metadata["duration_samples"]),
                "channel_count": int(metadata["channel_count"]),
                "bit_depth": int(metadata["bit_depth"]),
                "container_cookie": container_id,
                "path": str(expanded_path),
                "file_comment": clip_description,
                "FieldsBlob": None,
            },
        ),
        _insert_sound_library_row(
            cursor,
            "FLAssetBaseClip",
            {
                "FLAssetBaseClip_id": clip_id,
                "DbType": "FLAssetBaseClip",
                "name": clip_name,
                "filename": filename,
                "file_cookie": file_id,
                "track": 1,
                "category": clip_category,
                "duration": int(metadata["duration_samples"]),
                "clip_type": 0,
                "description": clip_description,
                "user1": tag_values[0],
                "user2": tag_values[1],
                "user3": tag_values[2],
                "user4": tag_values[3],
                "ed_mark": 0,
                "ed_wave": 0,
                "ed_start": 0,
                "ed_stop": int(metadata["duration_samples"]),
                "ed_hook": 0,
                "ed_sync": 0.0,
                "ed_fadein": 0,
                "ed_fadeout": 0,
                "ed_pan0": 0,
                "ed_pan1": 0,
                "ed_abaseid": 0,
                "ed_fia": 0,
                "ed_fis": 0,
                "ed_foa": 0,
                "ed_fos": 0,
                "ed_fin": 0,
                "ed_fout": 0,
                "ed_wave2": 0,
                "ed_panin": 0,
                "ed_eqin": 0,
                "ed_level_db": 0,
                "eq_band0_freq": 0,
                "eq_band0_gain": 0,
                "eq_band0_qshelf": 0,
                "eq_band1_freq": 0,
                "eq_band1_gain": 0,
                "eq_band1_qshelf": 0,
                "eq_band2_freq": 0,
                "eq_band2_gain": 0,
                "eq_band2_qshelf": 0,
                "eq_band3_freq": 0,
                "eq_band3_gain": 0,
                "eq_band3_qshelf": 0,
                "ed_nlen": len(clip_name),
                "ed_text": "",
                "data": None,
                "FieldsBlob": None,
                "StarRating": int(rating),
            },
        ),
    ]


def _sound_library_registered_item_from_ids(
    cursor: sqlite3.Cursor,
    *,
    clip_id: str,
    file_id: str,
) -> dict[str, Any] | None:
    results, _truncated = _query_sound_library_rows(cursor, query=None, clip_id=clip_id, file_id=file_id, limit=1)
    return results[0] if results else None


def _verify_sound_library_index_file(
    *,
    project_db_path: str,
    clip_id: str,
    file_id: str,
    expected_path: str,
) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{project_db_path}?mode=ro", uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        item = _sound_library_registered_item_from_ids(cursor, clip_id=clip_id, file_id=file_id)
    finally:
        connection.close()
    path = _sound_library_result_path(item) if isinstance(item, dict) else None
    path_ok = bool(path) and str(Path(path).expanduser()) == str(Path(expected_path).expanduser())
    return {
        "status": "verified" if item and path_ok else "failed",
        "method": "sound_library_db_readback",
        "checks": [
            {"name": "registered_clip_found", "ok": bool(item), "clip_id": clip_id, "file_id": file_id},
            {"name": "registered_path_matches", "ok": path_ok, "expected_path": expected_path, "actual_path": path},
        ],
        "registered_item": item,
    }


def _verify_sound_library_index_records(
    *,
    project_db_path: str,
    indexed_records: list[dict[str, Any]],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    registered_items: list[dict[str, Any]] = []
    for record in indexed_records:
        ids = record.get("ids") if isinstance(record.get("ids"), dict) else {}
        target = record.get("target") if isinstance(record.get("target"), dict) else {}
        verification = _verify_sound_library_index_file(
            project_db_path=project_db_path,
            clip_id=str(ids.get("clip_id") or ""),
            file_id=str(ids.get("file_id") or ""),
            expected_path=str(target.get("path") or ""),
        )
        checks.append(
            {
                "name": "indexed_record_verified",
                "ok": verification.get("status") == "verified",
                "clip_id": ids.get("clip_id"),
                "file_id": ids.get("file_id"),
                "path": target.get("path"),
                "verification": verification,
            }
        )
        if isinstance(verification.get("registered_item"), dict):
            registered_items.append(verification["registered_item"])
    return {
        "status": "verified" if checks and all(bool(check["ok"]) for check in checks) else "failed",
        "method": "sound_library_db_readback",
        "checks": checks,
        "registered_items": registered_items,
    }


def _discover_sound_library_audio_files(
    folder: Path,
    *,
    recursive: bool,
    max_files: int,
) -> dict[str, Any]:
    iterator = folder.rglob("*") if recursive else folder.iterdir()
    candidates = sorted(
        (path.resolve() for path in iterator if path.is_file() and path.suffix.casefold() in _SOUND_LIBRARY_AUDIO_EXTENSIONS),
        key=lambda path: str(path).casefold(),
    )
    truncated = len(candidates) > max_files
    selected = candidates[:max_files]
    return {
        "folder": str(folder),
        "recursive": bool(recursive),
        "max_files": int(max_files),
        "candidate_count": len(candidates),
        "selected_count": len(selected),
        "truncated": truncated,
        "extensions": sorted(_SOUND_LIBRARY_AUDIO_EXTENSIONS),
        "files": selected,
    }


def _sound_library_row_exists(cursor: sqlite3.Cursor, table_name: str, id_column: str, value: str | None) -> bool:
    if not value:
        return False
    columns = _sound_library_table_columns(cursor, table_name)
    if id_column not in columns:
        return False
    row = cursor.execute(
        f"SELECT 1 FROM {_quote_sound_library_identifier(table_name)} "
        f"WHERE CAST({_quote_sound_library_identifier(id_column)} AS TEXT) = ? LIMIT 1",
        (str(value),),
    ).fetchone()
    return bool(row)


def _sound_library_reference_values(*values: Any) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for value in values:
        candidates = value if isinstance(value, (list, tuple, set)) else (value,)
        for candidate in candidates:
            text = str(candidate or "").strip()
            if text and text not in seen:
                seen.add(text)
                refs.append(text)
    return refs


def _sound_library_non_default_cookie_values(*values: Any) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for value in values:
        candidates = value if isinstance(value, (list, tuple, set)) else (value,)
        for candidate in candidates:
            text = str(candidate or "").strip()
            if not text or text in {"0", "0.0"} or text in seen:
                continue
            seen.add(text)
            refs.append(text)
    return refs


def _sound_library_reference_count(
    cursor: sqlite3.Cursor,
    *,
    table_name: str,
    column_name: str,
    value: str | None = None,
    values: list[str] | tuple[str, ...] | set[str] | None = None,
) -> int:
    refs = _sound_library_reference_values(values or (), value)
    if not refs:
        return 0
    columns = _sound_library_table_columns(cursor, table_name)
    if column_name not in columns:
        return 0
    placeholders = ", ".join("?" for _ in refs)
    row = cursor.execute(
        f"SELECT COUNT(*) AS count FROM {_quote_sound_library_identifier(table_name)} "
        f"WHERE CAST({_quote_sound_library_identifier(column_name)} AS TEXT) IN ({placeholders})",
        tuple(refs),
    ).fetchone()
    if not row:
        return 0
    return int(row["count"] if hasattr(row, "keys") else row[0])


def _normalize_sound_library_source_path(path: Path | str) -> str:
    return str(Path(path).expanduser().resolve(strict=False))


def _sound_library_source_filter_sql(
    *,
    alias: str = "source_path",
    source_path: str | None,
    recursive: bool,
) -> tuple[str, list[Any]]:
    filters = [f"{alias} IS NOT NULL", f"{alias} != ''"]
    params: list[Any] = []
    if source_path:
        normalized = _normalize_sound_library_source_path(source_path).rstrip("/")
        if recursive:
            filters.append(f"(lower({alias}) = lower(?) OR lower({alias}) LIKE lower(?))")
            params.extend([normalized, f"{normalized}/%"])
        else:
            filters.append(f"lower({alias}) = lower(?)")
            params.append(normalized)
    return " AND ".join(filters), params


def _query_sound_library_sources(
    cursor: sqlite3.Cursor,
    *,
    source_path: str | None = None,
    recursive: bool = True,
    limit: int = 100,
) -> tuple[list[dict[str, Any]], bool]:
    missing_tables = _sound_library_missing_tables(cursor)
    if missing_tables:
        raise ReadinessFailed(
            "Fairlight Sound Library index tables are not present in the selected database.",
            details={
                "missing_tables": missing_tables,
                "required_tables": list(_SOUND_LIBRARY_REQUIRED_TABLES),
                "precondition": "fairlight_sound_library_db_schema",
            },
        )
    where_sql, params = _sound_library_source_filter_sql(
        alias="source_path",
        source_path=source_path,
        recursive=recursive,
    )
    rows = cursor.execute(
        f"""
        WITH source_rows AS (
            SELECT
                container.FLAssetBaseContainer_id AS container_id,
                container.cookie AS container_cookie,
                container.description AS container_description,
                COALESCE(NULLIF(container.path, ''), NULLIF(container.data_path, '')) AS source_path,
                container.data_path AS data_path,
                library_file.FLAssetBaseFile_id AS file_id,
                library_file.path AS file_path,
                clip.FLAssetBaseClip_id AS clip_id
            FROM FLAssetBaseContainer container
            LEFT JOIN FLAssetBaseFile library_file
              ON CAST(library_file.container_cookie AS TEXT) = CAST(container.FLAssetBaseContainer_id AS TEXT)
              OR CAST(library_file.container_cookie AS TEXT) = CAST(container.cookie AS TEXT)
            LEFT JOIN FLAssetBaseClip clip
              ON CAST(clip.file_cookie AS TEXT) = CAST(library_file.FLAssetBaseFile_id AS TEXT)
              OR CAST(clip.file_cookie AS TEXT) = CAST(library_file.cookie AS TEXT)
        )
        SELECT
            source_path,
            GROUP_CONCAT(DISTINCT container_description) AS descriptions,
            GROUP_CONCAT(DISTINCT data_path) AS data_paths,
            COUNT(DISTINCT container_id) AS container_count,
            COUNT(DISTINCT file_id) AS file_count,
            COUNT(DISTINCT clip_id) AS clip_count,
            MIN(file_path) AS first_file_path,
            MAX(file_path) AS last_file_path
        FROM source_rows
        WHERE {where_sql}
        GROUP BY source_path
        ORDER BY source_path COLLATE NOCASE
        LIMIT ?
        """,
        [*params, int(limit) + 1],
    ).fetchall()
    source_rows = [_sqlite_row_to_dict(cursor, row) for row in rows]
    truncated = len(source_rows) > limit
    sources: list[dict[str, Any]] = []
    for row in source_rows[:limit]:
        path = str(row.get("source_path") or "")
        descriptions = [value for value in str(row.get("descriptions") or "").split(",") if value]
        data_paths = [value for value in str(row.get("data_paths") or "").split(",") if value]
        path_obj = Path(path).expanduser()
        sources.append(
            {
                "path": path,
                "data_paths": data_paths,
                "descriptions": descriptions,
                "container_count": int(row.get("container_count") or 0),
                "file_count": int(row.get("file_count") or 0),
                "clip_count": int(row.get("clip_count") or 0),
                "first_file_path": row.get("first_file_path"),
                "last_file_path": row.get("last_file_path"),
                "exists": path_obj.exists(),
                "is_dir": path_obj.is_dir(),
            }
        )
    return sources, truncated


def _sound_library_values_for_in(values: set[str] | list[str] | tuple[str, ...]) -> list[str]:
    return [str(value) for value in values if str(value)]


def _sound_library_fetch_rows_by_in(
    cursor: sqlite3.Cursor,
    *,
    table_name: str,
    column_name: str,
    values: set[str] | list[str] | tuple[str, ...],
    columns: tuple[str, ...],
) -> list[dict[str, Any]]:
    normalized = _sound_library_values_for_in(values)
    if not normalized:
        return []
    placeholders = ", ".join("?" for _ in normalized)
    quoted_columns = ", ".join(_quote_sound_library_identifier(column) for column in columns)
    rows = cursor.execute(
        f"SELECT {quoted_columns} FROM {_quote_sound_library_identifier(table_name)} "
        f"WHERE CAST({_quote_sound_library_identifier(column_name)} AS TEXT) IN ({placeholders})",
        normalized,
    ).fetchall()
    return [_sqlite_row_to_dict(cursor, row) for row in rows]


def _sound_library_delete_rows_by_in(
    cursor: sqlite3.Cursor,
    *,
    table_name: str,
    column_name: str,
    values: set[str] | list[str] | tuple[str, ...],
) -> int:
    normalized = _sound_library_values_for_in(values)
    if not normalized:
        return 0
    total = 0
    for offset in range(0, len(normalized), 400):
        chunk = normalized[offset : offset + 400]
        placeholders = ", ".join("?" for _ in chunk)
        cursor.execute(
            f"DELETE FROM {_quote_sound_library_identifier(table_name)} "
            f"WHERE CAST({_quote_sound_library_identifier(column_name)} AS TEXT) IN ({placeholders})",
            chunk,
        )
        total += max(int(cursor.rowcount or 0), 0)
    return total


def _delete_sound_library_source_rows(
    cursor: sqlite3.Cursor,
    *,
    source_path: str,
    recursive: bool,
    missing_ok: bool = False,
) -> dict[str, Any]:
    normalized_source = _normalize_sound_library_source_path(source_path)
    sources, truncated = _query_sound_library_sources(
        cursor,
        source_path=normalized_source,
        recursive=recursive,
        limit=500,
    )
    if truncated:
        raise ValidationError(
            "Sound Library source mutation refuses a truncated source match set.",
            details={
                "source_path": normalized_source,
                "recursive": bool(recursive),
                "limit": 500,
                "hint": "Use --no-recursive or a narrower source path.",
            },
            recoverability="not_applicable",
        )
    if not sources and not missing_ok:
        raise ValidationError(
            "Sound Library source path did not match any indexed source rows.",
            details={
                "source_path": normalized_source,
                "recursive": bool(recursive),
                "hint": "Use `fairlight sound-library source-list --database ...` to inspect indexed sources.",
            },
            recoverability="not_applicable",
        )
    where_sql, params = _sound_library_source_filter_sql(
        alias="source_path",
        source_path=normalized_source,
        recursive=recursive,
    )
    container_rows = cursor.execute(
        f"""
        WITH containers AS (
            SELECT
                FLAssetBaseContainer_id AS container_id,
                cookie AS container_cookie,
                COALESCE(NULLIF(path, ''), NULLIF(data_path, '')) AS source_path
            FROM FLAssetBaseContainer
        )
        SELECT container_id, container_cookie, source_path
        FROM containers
        WHERE {where_sql}
        """,
        params,
    ).fetchall()
    containers = [_sqlite_row_to_dict(cursor, row) for row in container_rows]
    container_ids = {str(row.get("container_id") or "") for row in containers if row.get("container_id")}
    container_refs = {
        *container_ids,
        *_sound_library_non_default_cookie_values([row.get("container_cookie") for row in containers]),
    }
    file_rows = _sound_library_fetch_rows_by_in(
        cursor,
        table_name="FLAssetBaseFile",
        column_name="container_cookie",
        values=container_refs,
        columns=("FLAssetBaseFile_id", "cookie", "path", "filename", "container_cookie"),
    )
    file_ids = {str(row.get("FLAssetBaseFile_id") or "") for row in file_rows if row.get("FLAssetBaseFile_id")}
    file_refs = {
        *file_ids,
        *_sound_library_non_default_cookie_values([row.get("cookie") for row in file_rows]),
    }
    clip_rows = _sound_library_fetch_rows_by_in(
        cursor,
        table_name="FLAssetBaseClip",
        column_name="file_cookie",
        values=file_refs,
        columns=("FLAssetBaseClip_id", "file_cookie", "name", "filename"),
    )
    clip_ids = {str(row.get("FLAssetBaseClip_id") or "") for row in clip_rows if row.get("FLAssetBaseClip_id")}
    clip_rows_deleted = _sound_library_delete_rows_by_in(
        cursor,
        table_name="FLAssetBaseClip",
        column_name="FLAssetBaseClip_id",
        values=clip_ids,
    )
    file_rows_deleted = _sound_library_delete_rows_by_in(
        cursor,
        table_name="FLAssetBaseFile",
        column_name="FLAssetBaseFile_id",
        values=file_ids,
    )
    container_rows_deleted = _sound_library_delete_rows_by_in(
        cursor,
        table_name="FLAssetBaseContainer",
        column_name="FLAssetBaseContainer_id",
        values=container_ids,
    )
    return {
        "source_path": normalized_source,
        "recursive": bool(recursive),
        "matched_sources": sources,
        "matched_source_count": len(sources),
        "matched_container_count": len(container_ids),
        "matched_file_count": len(file_ids),
        "matched_clip_count": len(clip_ids),
        "clip_rows_deleted": int(clip_rows_deleted),
        "file_rows_deleted": int(file_rows_deleted),
        "container_rows_deleted": int(container_rows_deleted),
        "deleted_files": [
            {"file_id": row.get("FLAssetBaseFile_id"), "path": row.get("path"), "filename": row.get("filename")}
            for row in file_rows
        ],
        "deleted_clips": [
            {"clip_id": row.get("FLAssetBaseClip_id"), "name": row.get("name"), "filename": row.get("filename")}
            for row in clip_rows
        ],
    }


def _verify_sound_library_source_absent(
    *,
    project_db_path: str,
    source_path: str,
    recursive: bool,
) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{project_db_path}?mode=ro", uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        sources, truncated = _query_sound_library_sources(
            cursor,
            source_path=source_path,
            recursive=recursive,
            limit=20,
        )
    finally:
        connection.close()
    return {
        "status": "verified" if not sources and not truncated else "failed",
        "method": "sound_library_source_db_readback",
        "checks": [
            {
                "name": "source_rows_absent",
                "ok": not sources and not truncated,
                "source_path": _normalize_sound_library_source_path(source_path),
                "recursive": bool(recursive),
                "remaining_source_count": len(sources),
                "truncated": truncated,
            }
        ],
        "remaining_sources": sources,
    }


def _sound_library_delete_target_summary(item: dict[str, Any]) -> dict[str, Any]:
    file_info = item.get("file") if isinstance(item.get("file"), dict) else {}
    container_info = item.get("container") if isinstance(item.get("container"), dict) else {}
    return {
        "clip_id": item.get("clip_id"),
        "clip_file_cookie": item.get("file_cookie"),
        "file_id": file_info.get("file_id"),
        "file_cookie": file_info.get("cookie"),
        "file_container_cookie": file_info.get("container_cookie"),
        "container_id": container_info.get("container_id"),
        "container_cookie": container_info.get("cookie"),
        "name": item.get("name"),
        "filename": item.get("filename") or file_info.get("filename"),
        "path": _sound_library_result_path(item),
    }


def _select_sound_library_delete_results(
    cursor: sqlite3.Cursor,
    *,
    query: str | None,
    clip_id: str | None,
    file_id: str | None,
    file_path: str | None,
    result_index: int | None,
    all_matches: bool,
    limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    if not query and not clip_id and not file_id and not file_path:
        set_verification_status("not_requested")
        raise ValidationError(
            "Sound Library delete requires a query, --clip-id, --file-id, or --file-path.",
            details={
                "example": "cutagent fairlight sound-library delete footsteps --result-index 1 --json",
                "required_one_of": ["query", "--clip-id", "--file-id", "--file-path"],
                "api_note": "Sound Library delete removes current-project DB index rows only; it does not delete media files from disk.",
            },
            recoverability="not_applicable",
        )
    if all_matches and result_index is not None:
        raise ValidationError(
            "Sound Library delete cannot combine --all with --result-index.",
            details={"all": bool(all_matches), "result_index": int(result_index)},
            recoverability="not_applicable",
        )
    results, truncated = _query_sound_library_rows(
        cursor,
        query=query,
        clip_id=clip_id,
        file_id=file_id,
        file_path=file_path,
        limit=limit,
    )
    matches = results
    if clip_id:
        matches = [item for item in matches if str(item.get("clip_id") or "") == str(clip_id)]
    if file_id:
        matches = [
            item
            for item in matches
            if str((item.get("file") if isinstance(item.get("file"), dict) else {}).get("file_id") or "") == str(file_id)
        ]
    if file_path:
        normalized_path = str(Path(file_path).expanduser())
        matches = [item for item in matches if str(_sound_library_result_path(item) or "") == normalized_path]
    summaries = [_sound_library_match_summary(item, index=index) for index, item in enumerate(matches, start=1)]
    if result_index is not None:
        if result_index < 1 or result_index > len(matches):
            set_verification_status("not_requested")
            raise ValidationError(
                "Sound Library result index is out of range.",
                details={"result_index": int(result_index), "match_count": len(matches), "matches": summaries},
                recoverability="not_applicable",
            )
        return [matches[result_index - 1]], summaries, truncated
    if not matches:
        set_verification_status("not_requested")
        raise ValidationError(
            "Sound Library delete query did not match any indexed results.",
            details={
                "query": query,
                "clip_id": clip_id,
                "file_id": file_id,
                "file_path": file_path,
                "truncated": truncated,
                "hint": "Use `fairlight sound-library search` first to inspect available indexed results.",
            },
            recoverability="not_applicable",
        )
    if all_matches:
        if truncated:
            set_verification_status("not_requested")
            raise ValidationError(
                "Sound Library delete refuses to delete a truncated match set.",
                details={
                    "match_count": len(matches),
                    "limit": int(limit),
                    "truncated": truncated,
                    "hint": "Increase --limit or choose a single --result-index/--clip-id/--file-id.",
                },
                recoverability="not_applicable",
            )
        return matches, summaries, truncated
    exact_selector = bool(clip_id or file_id or file_path or result_index is not None)
    if truncated and not exact_selector:
        set_verification_status("not_requested")
        raise ValidationError(
            "Sound Library delete refuses to delete a truncated match set.",
            details={
                "query": query,
                "clip_id": clip_id,
                "file_id": file_id,
                "file_path": file_path,
                "match_count": len(matches),
                "limit": int(limit),
                "truncated": truncated,
                "matches": summaries,
                "hint": "Increase --limit or choose a single --result-index/--clip-id/--file-id/--file-path.",
            },
            recoverability="not_applicable",
        )
    if len(matches) > 1:
        set_verification_status("not_requested")
        raise ValidationError(
            "Sound Library delete matched multiple indexed results.",
            details={
                "query": query,
                "clip_id": clip_id,
                "file_id": file_id,
                "file_path": file_path,
                "match_count": len(matches),
                "truncated": truncated,
                "matches": summaries,
                "hint": "Pass --result-index, --clip-id, --file-id, or --all.",
            },
            recoverability="not_applicable",
        )
    return [matches[0]], summaries, truncated


def _verify_sound_library_delete(*, project_db_path: str, deleted_targets: list[dict[str, Any]]) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{project_db_path}?mode=ro", uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    checks: list[dict[str, Any]] = []
    try:
        cursor = connection.cursor()
        for target in deleted_targets:
            clip_id = target.get("clip_id")
            file_id = target.get("file_id")
            container_id = target.get("container_id")
            file_expected_deleted = bool(target.get("file_row_deleted"))
            container_expected_deleted = bool(target.get("container_row_deleted"))
            clip_exists = _sound_library_row_exists(cursor, "FLAssetBaseClip", "FLAssetBaseClip_id", clip_id)
            file_exists = _sound_library_row_exists(cursor, "FLAssetBaseFile", "FLAssetBaseFile_id", file_id)
            container_exists = _sound_library_row_exists(
                cursor,
                "FLAssetBaseContainer",
                "FLAssetBaseContainer_id",
                container_id,
            )
            checks.extend(
                [
                    {"name": "clip_row_absent", "ok": not clip_exists, "clip_id": clip_id},
                    {
                        "name": "file_row_absence_matches_plan",
                        "ok": (not file_exists) if file_expected_deleted else True,
                        "file_id": file_id,
                        "expected_deleted": file_expected_deleted,
                        "still_exists": file_exists,
                    },
                    {
                        "name": "container_row_absence_matches_plan",
                        "ok": (not container_exists) if container_expected_deleted else True,
                        "container_id": container_id,
                        "expected_deleted": container_expected_deleted,
                        "still_exists": container_exists,
                    },
                ]
            )
    finally:
        connection.close()
    return {
        "status": "verified" if all(bool(check["ok"]) for check in checks) else "failed",
        "method": "sound_library_db_readback",
        "checks": checks,
    }


def _sound_library_clip_column_expr(available_columns: set[str], column: str, alias: str | None = None) -> str:
    output_alias = alias or column
    if column in available_columns:
        return f"clip.{column} AS {output_alias}"
    return f"NULL AS {output_alias}"


def _sound_library_item_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "clip_id": row.get("clip_id"),
        "file_cookie": row.get("file_cookie"),
        "name": row.get("name") or row.get("clip_filename") or row.get("file_filename"),
        "filename": row.get("clip_filename") or row.get("file_filename"),
        "category": row.get("category"),
        "duration": row.get("duration"),
        "clip_type": row.get("clip_type"),
        "track": row.get("track"),
        "description": row.get("description"),
        "star_rating": row.get("star_rating"),
        "metadata": {
            "user1": row.get("user1"),
            "user2": row.get("user2"),
            "user3": row.get("user3"),
            "user4": row.get("user4"),
        },
        "edit": {
            "mark": row.get("ed_mark"),
            "waveform": {
                "primary": row.get("ed_wave"),
                "secondary": row.get("ed_wave2"),
            },
            "range": {
                "start": row.get("ed_start"),
                "stop": row.get("ed_stop"),
                "hook": row.get("ed_hook"),
                "sync": row.get("ed_sync"),
            },
            "fade": {
                "in": row.get("ed_fadein"),
                "out": row.get("ed_fadeout"),
                "in_enabled": row.get("ed_fin"),
                "out_enabled": row.get("ed_fout"),
                "in_shape": row.get("ed_fis"),
                "out_shape": row.get("ed_fos"),
                "in_amount": row.get("ed_fia"),
                "out_amount": row.get("ed_foa"),
            },
            "pan": {
                "left_raw": row.get("ed_pan0"),
                "right_raw": row.get("ed_pan1"),
                "enabled": row.get("ed_panin"),
            },
            "level": {
                "db_raw": row.get("ed_level_db"),
            },
            "eq": {
                "enabled": row.get("ed_eqin"),
                "bands": [
                    {
                        "index": 0,
                        "freq_raw": row.get("eq_band0_freq"),
                        "gain_raw": row.get("eq_band0_gain"),
                        "q_shelf_raw": row.get("eq_band0_qshelf"),
                    },
                    {
                        "index": 1,
                        "freq_raw": row.get("eq_band1_freq"),
                        "gain_raw": row.get("eq_band1_gain"),
                        "q_shelf_raw": row.get("eq_band1_qshelf"),
                    },
                    {
                        "index": 2,
                        "freq_raw": row.get("eq_band2_freq"),
                        "gain_raw": row.get("eq_band2_gain"),
                        "q_shelf_raw": row.get("eq_band2_qshelf"),
                    },
                    {
                        "index": 3,
                        "freq_raw": row.get("eq_band3_freq"),
                        "gain_raw": row.get("eq_band3_gain"),
                        "q_shelf_raw": row.get("eq_band3_qshelf"),
                    },
                ],
            },
            "text": row.get("ed_text"),
        },
        "file": {
            "file_id": row.get("file_id"),
            "cookie": row.get("file_cookie_value"),
            "filename": row.get("file_filename"),
            "path": row.get("file_path"),
            "filetype": row.get("filetype"),
            "sample_rate": row.get("sample_rate"),
            "frame_rate": row.get("frame_rate"),
            "channel_count": row.get("channel_count"),
            "bit_depth": row.get("bit_depth"),
            "duration": row.get("file_duration"),
            "comment": row.get("file_comment"),
            "container_cookie": row.get("file_container_cookie"),
        },
        "container": {
            "container_id": row.get("container_id"),
            "cookie": row.get("container_cookie_value"),
            "path": row.get("container_path"),
            "data_path": row.get("container_data_path"),
            "description": row.get("container_description"),
        },
    }


def _query_sound_library_rows(
    cursor: sqlite3.Cursor,
    *,
    query: str | None,
    clip_id: str | None = None,
    file_id: str | None = None,
    file_path: str | None = None,
    limit: int,
) -> tuple[list[dict[str, Any]], bool]:
    missing_tables = _sound_library_missing_tables(cursor)
    if missing_tables:
        raise ReadinessFailed(
            "Fairlight Sound Library index tables are not present in the current project database.",
            details={
                "missing_tables": missing_tables,
                "required_tables": list(_SOUND_LIBRARY_REQUIRED_TABLES),
                "precondition": "fairlight_sound_library_project_db_schema",
            },
        )

    normalized_query = str(query or "").strip().casefold()
    where_clause = ""
    params: list[Any] = []
    conditions: list[str] = []
    if normalized_query:
        like_value = f"%{normalized_query}%"
        conditions.append(
            "("
            + " OR ".join(
                f"lower(COALESCE({column}, '')) LIKE ?" for column in _SOUND_LIBRARY_SEARCH_COLUMNS
            )
            + ")"
        )
        params.extend(like_value for _ in _SOUND_LIBRARY_SEARCH_COLUMNS)
    if clip_id:
        conditions.append("CAST(clip.FLAssetBaseClip_id AS TEXT) = ?")
        params.append(str(clip_id))
    if file_id:
        conditions.append("CAST(library_file.FLAssetBaseFile_id AS TEXT) = ?")
        params.append(str(file_id))
    if file_path:
        conditions.append("lower(COALESCE(library_file.path, '')) = lower(?)")
        params.append(str(file_path))
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    params.append(limit + 1)
    clip_columns = _sound_library_table_columns(cursor, "FLAssetBaseClip")
    edit_selects = ",\n            ".join(
        _sound_library_clip_column_expr(clip_columns, column) for column in _SOUND_LIBRARY_EDIT_COLUMNS
    )
    rows = cursor.execute(
        f"""
        SELECT DISTINCT
            clip.FLAssetBaseClip_id AS clip_id,
            clip.name AS name,
            clip.filename AS clip_filename,
            clip.file_cookie AS file_cookie,
            clip.track AS track,
            clip.category AS category,
            clip.duration AS duration,
            clip.clip_type AS clip_type,
            clip.description AS description,
            clip.user1 AS user1,
            clip.user2 AS user2,
            clip.user3 AS user3,
            clip.user4 AS user4,
            clip.StarRating AS star_rating,
            {edit_selects},
            library_file.FLAssetBaseFile_id AS file_id,
            library_file.filename AS file_filename,
            library_file.cookie AS file_cookie_value,
            library_file.filetype AS filetype,
            library_file.sample_rate AS sample_rate,
            library_file.frame_rate AS frame_rate,
            library_file.duration AS file_duration,
            library_file.channel_count AS channel_count,
            library_file.bit_depth AS bit_depth,
            library_file.container_cookie AS file_container_cookie,
            library_file.path AS file_path,
            library_file.file_comment AS file_comment,
            container.FLAssetBaseContainer_id AS container_id,
            container.cookie AS container_cookie_value,
            container.path AS container_path,
            container.data_path AS container_data_path,
            container.description AS container_description
        FROM FLAssetBaseClip clip
        LEFT JOIN FLAssetBaseFile library_file
          ON CAST(library_file.FLAssetBaseFile_id AS TEXT) = CAST(clip.file_cookie AS TEXT)
          OR CAST(library_file.cookie AS TEXT) = CAST(clip.file_cookie AS TEXT)
        LEFT JOIN FLAssetBaseContainer container
          ON CAST(container.FLAssetBaseContainer_id AS TEXT) = CAST(library_file.container_cookie AS TEXT)
          OR CAST(container.cookie AS TEXT) = CAST(library_file.container_cookie AS TEXT)
        {where_clause}
        ORDER BY
            COALESCE(clip.name, clip.filename, library_file.filename) COLLATE NOCASE,
            clip.FLAssetBaseClip_id
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()
    truncated = len(rows) > limit
    results = [_sound_library_item_from_row(_sqlite_row_to_dict(cursor, row)) for row in rows[:limit]]
    return results, truncated


def _sound_library_read_payload(*, action: str, query: str | None, limit: int, database_scope: str) -> dict[str, Any]:
    return {
        "action": action,
        "route": "db_workaround",
        "database": database_scope,
        "target": _sound_library_database_target(database_scope),
        "query": query,
        "limit": limit,
        "db_readback": {
            "database": _sound_library_database_label(database_scope),
            "tables": list(_SOUND_LIBRARY_REQUIRED_TABLES),
            "search_columns": list(_SOUND_LIBRARY_SEARCH_COLUMNS),
            "edit_metadata_columns": list(_SOUND_LIBRARY_EDIT_COLUMNS),
        },
        "limitations": {
            "audition": "not exposed by the DaVinci Resolve scripting API",
            "delete": "available through verified Disk DB writes for current-project Project.db or Local Database User.db indexed rows",
            "index_folder": "available through verified Disk DB writes for local audio folders",
            "index_file": "available through verified Disk DB writes for local audio files",
            "insert": "available only when the DB index resolves one result with a usable file path",
            "source_management": "available through FLAssetBaseContainer source-list/source-remove/source-rebuild DB routes",
            "sync_to_playhead": "available for insert placement through FLAssetBaseClip.ed_sync alignment; Sound Library audition sync preview is not exposed by the DaVinci Resolve scripting API",
        },
    }


_FAIRLIGHT_SOUND_LIBRARY_AUDITION_DB_BLOCKER_EVIDENCE = {
    "available_db_routes": [
        {
            "command": "cutagent fairlight sound-library list --database project --json",
            "route": "db_workaround",
            "scope": "current Project.db Sound Library index readback",
            "db_tables": ["FLAssetBaseClip", "FLAssetBaseFile", "FLAssetBaseContainer"],
        },
        {
            "command": "cutagent fairlight sound-library list --database user --json",
            "route": "db_workaround",
            "scope": "DaVinci Resolve Local Database User.db Sound Library index readback",
            "db_tables": ["FLAssetBaseClip", "FLAssetBaseFile", "FLAssetBaseContainer"],
        },
        {
            "command": "cutagent fairlight sound-library insert QUERY --sync-to-playhead --json",
            "route": "api_native",
            "scope": "indexed local file placement with optional DB sync-point alignment",
            "native_api": ["Project.InsertAudioToCurrentTrackAtPlayhead"],
        },
    ],
    "db_schema_evidence": {
        "source": "local DaVinci Resolve 20 Free Sound Library DB schema probes",
        "sampled_project_db_count": 5,
        "sampled_user_db_count": 1,
        "read_scope": "negative_sound_library_audition_playback_schema_probe",
        "index_tables_found_in_samples": [
            "FLAssetBaseClip",
            "FLAssetBaseFile",
            "FLAssetBaseContainer",
        ],
        "index_columns_supporting_read_insert": [
            "FLAssetBaseClip.name",
            "FLAssetBaseClip.duration",
            "FLAssetBaseClip.ed_sync",
            "FLAssetBaseClip.ed_start",
            "FLAssetBaseClip.ed_stop",
            "FLAssetBaseFile.path",
            "FLAssetBaseFile.sample_rate",
            "FLAssetBaseFile.channel_count",
            "FLAssetBaseFile.duration",
            "FLAssetBaseContainer.path",
            "FLAssetBaseContainer.data_path",
        ],
        "generic_panel_tables_seen": [
            "SM_PanelSetup",
            "SM_PanelSensitivity",
        ],
        "generic_panel_tables_are_audition_playback_schema": False,
        "audition_table_found_in_samples": False,
        "preview_table_found_in_samples": False,
        "sound_library_playback_state_schema_found_in_samples": False,
        "sound_library_stop_control_schema_found_in_samples": False,
        "sync_point_is_insert_alignment_not_preview_playback": True,
        "timeline_insert_readback_route_found": True,
        "audition_without_insert_readback_route_found": False,
    },
    "audition_model_evidence": {
        "index_read_supported": True,
        "project_db_index_supported": True,
        "user_db_index_supported": True,
        "native_insert_supported": True,
        "sync_to_playhead_insert_supported": True,
        "panel_audition_playback_supported": False,
        "preview_without_timeline_insert_supported": False,
        "audition_stop_supported": False,
        "audition_playback_state_readback_supported": False,
    },
    "native_probe_evidence": {
        "sampled_resolve_edition": "DaVinci Resolve 20 Free",
        "probe_targets": ["Resolve", "Project", "Timeline", "MediaPool", "MediaStorage"],
        "candidate_method_families_not_available": [
            "Sound Library panel audition playback",
            "Sound Library preview without insertion",
            "Sound Library sync-preview playback",
            "Sound Library audition stop control",
            "Sound Library audition playback state readback",
        ],
        "playback_mutation_candidates_not_called": [
            "audition Sound Library indexed audio without insertion",
            "preview Sound Library result through the panel",
            "stop Sound Library preview playback",
        ],
        "probe_result": "method not available",
        "blocked_scope": "Sound Library panel audition/preview playback",
        "resolve_21_embedded_recheck": {
            "runtime": "DaVinci Resolve 21.0.0.48 Free",
            "transport": "embedded_lua_http_poll",
            "artifact": "/tmp/cutagent_sound_external_cn_20260619/07_direct_sound_external_probe_after_allowlist.json",
            "candidate_methods_not_available": [
                "Resolve.GetSoundLibrary()",
                "Project.GetSoundLibrary()",
                "Project.GetSoundLibraryItems()",
                "Project.GetSoundLibraryPreviewState()",
                "Project.GetSoundLibraryAuditionState()",
            ],
            "unsupported_bridge_count": 0,
            "probe_result": "Sound Library panel playback getter candidates reached DaVinci Resolve and returned method_not_available",
        },
    },
    "db_blocker_note": (
        "Sound Library DB routes can read, index, delete, source-manage, and resolve local files for native "
        "timeline insertion, including sync-point placement. They do not expose or verify Fairlight panel "
        "audition playback, preview without insertion, stop control, or audition playback state."
    ),
}

