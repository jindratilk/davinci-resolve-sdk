def _connection_start_frame(conn) -> int:
    try:
        value = int(getattr(conn, "start_frame", 0) or 0)
        if value:
            return value
    except Exception:
        pass
    try:
        return int(conn.timeline.GetStartFrame())
    except Exception:
        return 0


def _absolute_record_frame_ref(conn: Any, frame: int) -> str:
    start_frame = _connection_start_frame(conn)
    relative = int(frame) - int(start_frame)
    if relative < 0:
        relative = int(frame)
    return f"{relative}f"


def _project_db_start_candidates(conn: Any, frame: int) -> list[int]:
    candidates = {int(frame)}
    start_frame = _connection_start_frame(conn)
    if start_frame:
        candidates.add(int(frame) - int(start_frame))
    return sorted(candidate for candidate in candidates if candidate >= 0)


def _timeline_max_item_end(conn: Any) -> int:
    """Legacy staging support for non-setting callers.

    Precise Fusion/Text+ setting insertion must use the isolated scratch route
    instead; it intentionally never calls this helper.
    """
    start_frame = _connection_start_frame(conn)
    max_end = start_frame
    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        return max_end
    for track_type in ("video", "audio", "subtitle"):
        try:
            track_count = int(timeline.GetTrackCount(track_type) or 0)
        except Exception:
            track_count = 0
        for track_index in range(1, track_count + 1):
            try:
                items = timeline.GetItemListInTrack(track_type, track_index) or []
            except Exception:
                items = []
            for item in items:
                end = _timeline_item_end(item)
                if end is not None:
                    absolute_end = int(end)
                    if start_frame and absolute_end < start_frame:
                        absolute_end += start_frame
                    max_end = max(max_end, absolute_end)
    return max_end


def _native_precise_staging_frame(conn: Any, *, target_record_frame: int, duration_frames: int) -> int:
    timeline_end = _timeline_max_item_end(conn)
    return max(timeline_end, int(target_record_frame) + int(duration_frames)) + max(24, int(duration_frames), 120)


def _insert_native_holder_at_frame(
    conn: Any,
    *,
    holder: str,
    holder_kind: str,
    record_frame: int,
) -> tuple[Any, dict[str, Any]]:
    normalized_holder_kind = str(holder_kind or "fusion").strip().lower().replace("_", "-")
    holder_name = str(holder or ("Text+" if normalized_holder_kind == "textplus" else "Fusion Composition")).strip()
    playhead = timeline_ops.set_playhead(conn, _absolute_record_frame_ref(conn, record_frame), return_details=True)
    if normalized_holder_kind == "textplus":
        inserter = require_api_method(
            conn.timeline,
            "InsertFusionTitleIntoTimeline",
            capability_id="timeline.insert_title",
            runtime_object="timeline",
        )
        item = inserter(holder_name or "Text+")
        route = ROUTE_NATIVE_TEXTPLUS_IMPORT_FUSION_COMP
        api_call = "Timeline.InsertFusionTitleIntoTimeline"
    else:
        inserter = require_api_method(
            conn.timeline,
            "InsertGeneratorIntoTimeline",
            capability_id="timeline.insert_generator",
            runtime_object="timeline",
        )
        item = inserter(holder_name or "Fusion Composition")
        route = ROUTE_NATIVE_HOLDER_IMPORT_FUSION_COMP
        api_call = "Timeline.InsertGeneratorIntoTimeline"
    if not item:
        raise APICallFailed(
            "Failed to insert native Fusion/Text+ holder.",
            details={"holder": holder_name, "holder_kind": normalized_holder_kind, "record_frame": record_frame, "api_call": api_call},
        )
    return item, {
        "holder": holder_name,
        "holder_kind": normalized_holder_kind,
        "record_frame": int(record_frame),
        "playhead": playhead,
        "route": route,
        "api_call": api_call,
    }


def _enumerated_video_items(conn: Any) -> list[dict[str, Any]]:
    """Read timeline placement from track enumeration, never requested values."""
    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        return []
    try:
        track_count = int(timeline.GetTrackCount("video") or 0)
    except Exception as exc:
        raise APICallFailed(
            "Could not enumerate video tracks for precise Fusion placement proof.",
            details={"error": {"type": exc.__class__.__name__, "message": str(exc)}},
        ) from exc

    rows: list[dict[str, Any]] = []
    for track_index in range(1, track_count + 1):
        try:
            items = timeline.GetItemListInTrack("video", track_index) or []
        except Exception as exc:
            raise APICallFailed(
                "Could not enumerate a video track for precise Fusion placement proof.",
                details={
                    "track_index": track_index,
                    "error": {"type": exc.__class__.__name__, "message": str(exc)},
                },
            ) from exc
        for item in items:
            readback = _timeline_item_readback(item)
            readback["track_type"] = "video"
            readback["track_index"] = int(track_index)
            readback["placement_proof"] = {
                "source": "Timeline.GetItemListInTrack",
                "track_type": "video",
                "track_index": int(track_index),
            }
            rows.append({"item": item, "readback": readback})
    return rows


def _unique_enumerated_video_item(
    conn: Any,
    *,
    track_index: int,
    start: int,
    duration: int | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for row in _enumerated_video_items(conn):
        readback = row["readback"]
        if readback.get("track_index") != int(track_index):
            continue
        if readback.get("start") != int(start):
            continue
        if duration is not None and readback.get("duration") != int(duration):
            continue
        if name and str(readback.get("name") or "") != str(name):
            continue
        matches.append(row)
    if len(matches) != 1:
        raise APICallFailed(
            "Precise Fusion placement did not enumerate exactly one matching timeline item.",
            details={
                "expected": {
                    "track_index": int(track_index),
                    "start": int(start),
                    "duration": None if duration is None else int(duration),
                    "name": name,
                },
                "match_count": len(matches),
                "matches": [row["readback"] for row in matches],
            },
        )
    return matches[0]


def _target_track_preservation_snapshot(rows: list[dict[str, Any]], *, track_index: int) -> list[dict[str, Any]]:
    preserved = [
        {
            "name": row["readback"].get("name"),
            "start": row["readback"].get("start"),
            "end": row["readback"].get("end"),
            "duration": row["readback"].get("duration"),
            "timeline_item_id": row["readback"].get("timeline_item_id"),
        }
        for row in rows
        if row["readback"].get("track_index") == int(track_index)
    ]
    return sorted(
        preserved,
        key=lambda row: (
            int(row.get("start") or 0),
            int(row.get("end") or 0),
            str(row.get("name") or ""),
            str(row.get("timeline_item_id") or ""),
        ),
    )


def _cleanup_native_precise_scratch_timeline(
    conn: Any,
    *,
    target_timeline_name: str,
    scratch_timeline_name: str,
    target_playhead: dict[str, Any] | None,
) -> dict[str, Any]:
    cleanup: dict[str, Any] = {
        "target_timeline": target_timeline_name,
        "scratch_timeline": scratch_timeline_name,
        "restored_target": False,
        "deleted_scratch": False,
        "restored_playhead": False,
        "errors": [],
    }
    try:
        timeline_ops.switch_timeline(conn, name=target_timeline_name)
        cleanup["restored_target"] = True
    except Exception as exc:
        cleanup["errors"].append(
            {"step": "restore_target_timeline", "type": exc.__class__.__name__, "message": str(exc)}
        )
        return cleanup

    try:
        timeline_names = _project_timeline_names(conn)
        cleanup["deleted_scratch"] = (
            True
            if timeline_names and scratch_timeline_name not in timeline_names
            else bool(timeline_ops.delete_timeline(conn, scratch_timeline_name))
        )
    except Exception as exc:
        cleanup["errors"].append(
            {"step": "delete_scratch_timeline", "type": exc.__class__.__name__, "message": str(exc)}
        )

    timecode = target_playhead.get("timecode") if isinstance(target_playhead, dict) else None
    if timecode:
        try:
            timeline_ops.set_playhead(conn, str(timecode))
            cleanup["restored_playhead"] = True
        except Exception as exc:
            cleanup["errors"].append(
                {"step": "restore_target_playhead", "type": exc.__class__.__name__, "message": str(exc)}
            )
    else:
        cleanup["restored_playhead"] = True
    cleanup["ok"] = bool(
        cleanup["restored_target"]
        and cleanup["deleted_scratch"]
        and cleanup["restored_playhead"]
        and not cleanup["errors"]
    )
    return cleanup


def _row_to_dict(cursor: Any, row: Any) -> dict[str, Any]:
    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}
    return {cursor.description[index][0]: value for index, value in enumerate(row)}


def _select_inserted_holder_db_row(
    cursor: Any,
    *,
    staging_start_candidates: list[int],
    staging_duration: int,
    expected_names: list[str],
    source_track_ids: list[str] | None = None,
    item_id: str | None = None,
) -> dict[str, Any]:
    normalized_source_track_ids = sorted(
        {
            str(track_id).strip()
            for track_id in (source_track_ids or [])
            if str(track_id or "").strip()
        }
    )
    if not normalized_source_track_ids:
        raise ValidationError(
            "Project.db holder lookup requires resolved source timeline track ids."
        )
    track_placeholders = ", ".join("?" for _value in normalized_source_track_ids)
    normalized_item_id = str(item_id or "").strip()
    if normalized_item_id:
        rows = cursor.execute(
            f"""
            SELECT
                item.*,
                rel.DbOwner AS relation_track_id,
                rel.DbIndex AS item_db_index,
                rel.rowid AS relation_rowid
            FROM Sm2TiItem item
            JOIN Sm2TiItem_Sm2TiTrack rel
              ON rel.DbAssociate = item.Sm2TiItem_id
             AND rel.DbPropertyName = 'Items'
            WHERE item.Sm2TiItem_id = ?
              AND rel.DbOwner IN ({track_placeholders})
            """,
            (normalized_item_id, *normalized_source_track_ids),
        ).fetchall()
        candidates = [_row_to_dict(cursor, row) for row in rows]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise ValidationError(
                "Native holder item id matched multiple Project.db rows.",
                details={"item_id": normalized_item_id, "matches": len(candidates)},
            )
    if not staging_start_candidates:
        raise ValidationError("Project.db holder lookup requires at least one staging start candidate.")
    placeholders = ", ".join("?" for _candidate in staging_start_candidates)
    expected_values = [str(name).strip() for name in expected_names if str(name or "").strip()]
    expected = {name.casefold() for name in expected_values}

    def _query_candidates(*, require_duration: bool, require_name: bool) -> list[dict[str, Any]]:
        clauses = [
            f"CAST(COALESCE(item.Start, '0') AS INTEGER) IN ({placeholders})",
            f"rel.DbOwner IN ({track_placeholders})",
        ]
        params: list[Any] = [
            *[int(candidate) for candidate in staging_start_candidates],
            *normalized_source_track_ids,
        ]
        if require_duration:
            clauses.append("CAST(COALESCE(item.Duration, '0') AS INTEGER) = ?")
            params.append(int(staging_duration))
        if require_name and expected_values:
            name_placeholders = ", ".join("?" for _value in expected_values)
            clauses.append(f"LOWER(TRIM(COALESCE(item.Name, ''))) IN ({name_placeholders})")
            params.extend(name.casefold() for name in expected_values)
        rows = cursor.execute(
            f"""
            SELECT
                item.*,
                rel.DbOwner AS relation_track_id,
                rel.DbIndex AS item_db_index,
                rel.rowid AS relation_rowid
            FROM Sm2TiItem item
            JOIN Sm2TiItem_Sm2TiTrack rel
              ON rel.DbAssociate = item.Sm2TiItem_id
             AND rel.DbPropertyName = 'Items'
            WHERE {" AND ".join(clauses)}
            """,
            tuple(params),
        ).fetchall()
        return [_row_to_dict(cursor, row) for row in rows]

    def _pick_unique(candidates: list[dict[str, Any]], *, attempt: str) -> dict[str, Any] | None:
        if not candidates:
            return None
        named = [row for row in candidates if str(row.get("Name") or "").strip().casefold() in expected]
        track_matched = [
            row
            for row in candidates
            if str(row.get("relation_track_id") or "") in normalized_source_track_ids
        ]
        named_track_matched = [row for row in named if str(row.get("relation_track_id") or "") in normalized_source_track_ids]
        if len(named_track_matched) == 1:
            return named_track_matched[0]
        if len(named) == 1:
            return named[0]
        if len(track_matched) == 1:
            return track_matched[0]
        if len(candidates) == 1:
            return candidates[0]
        raise ValidationError(
            "Native holder insertion matched multiple Project.db rows.",
            details={
                "attempt": attempt,
                "item_id": normalized_item_id or None,
                "staging_start_candidates": staging_start_candidates,
                "staging_duration": staging_duration,
                "expected_names": expected_names,
                "source_track_ids": normalized_source_track_ids,
                "matches": [
                    {
                        "item_id": row.get("Sm2TiItem_id"),
                        "name": row.get("Name"),
                        "start": row.get("Start"),
                        "duration": row.get("Duration"),
                        "track_id": row.get("relation_track_id") or row.get("Sm2TiTrack_id"),
                    }
                    for row in candidates
                ],
            },
        )

    lookup_attempts = [
        ("start_duration_source_track", {"require_duration": True, "require_name": False}),
        ("start_name_source_track", {"require_duration": False, "require_name": True}),
    ]
    attempted: list[dict[str, Any]] = []
    for attempt, options in lookup_attempts:
        if options["require_name"] and not expected_values:
            continue
        candidates = _query_candidates(**options)
        attempted.append({"attempt": attempt, "match_count": len(candidates)})
        selected = _pick_unique(candidates, attempt=attempt)
        if selected is not None:
            selected["_lookup_attempt"] = attempt
            return selected

    nearby_rows: list[dict[str, Any]] = []
    nearby_clauses = [
        f"CAST(COALESCE(item.Start, '0') AS INTEGER) IN ({placeholders})",
        "CAST(COALESCE(item.Duration, '0') AS INTEGER) = ?",
    ]
    nearby_params: list[Any] = [
        *[int(candidate) for candidate in staging_start_candidates],
        int(staging_duration),
    ]
    if expected_values:
        name_placeholders = ", ".join("?" for _value in expected_values)
        nearby_clauses.append(f"item.Name IN ({name_placeholders})")
        nearby_params.extend(expected_values)
    try:
        nearby_raw = cursor.execute(
            f"""
            SELECT
                item.Sm2TiItem_id,
                item.Name,
                item.Start,
                item.Duration,
                item.DbType,
                item.Sm2TiTrack_id,
                rel.DbOwner AS relation_track_id
            FROM Sm2TiItem item
            JOIN Sm2TiItem_Sm2TiTrack rel
              ON rel.DbAssociate = item.Sm2TiItem_id
             AND rel.DbPropertyName = 'Items'
            WHERE rel.DbOwner IN ({track_placeholders})
              AND ({" OR ".join(nearby_clauses)})
            ORDER BY CAST(COALESCE(item.Start, '0') AS INTEGER) DESC
            LIMIT 25
            """,
            (*normalized_source_track_ids, *nearby_params),
        ).fetchall()
        nearby_rows = [_row_to_dict(cursor, row) for row in nearby_raw]
    except Exception:
        nearby_rows = []
    raise ClipNotFound(
        "No Project.db row matched the native holder inserted for precise Fusion placement.",
        details={
            "staging_start_candidates": staging_start_candidates,
            "staging_duration": staging_duration,
            "expected_names": expected_names,
            "source_track_ids": normalized_source_track_ids,
            "lookup_attempts": attempted,
            "nearby_rows": nearby_rows,
        },
    )


def _wait_for_native_precise_holder_materialization(
    conn: Any,
    *,
    source_timeline_name: str,
    staging_readback: dict[str, Any],
    clip_name: str,
    holder: str,
    timeout_seconds: float = NATIVE_PRECISE_DB_MATERIALIZE_TIMEOUT_SECONDS,
    poll_seconds: float = NATIVE_PRECISE_DB_MATERIALIZE_POLL_SECONDS,
) -> dict[str, Any]:
    from ..runtime_health import resolve_current_disk_project_db
    from ..core import db_timeline_rows

    staging_start = staging_readback.get("start")
    staging_duration = staging_readback.get("duration")
    staging_track = staging_readback.get("track_index")
    if staging_start is None or staging_duration is None or staging_track is None:
        return {
            "status": "skipped",
            "reason": "missing_staging_identity",
            "staging_readback": staging_readback,
        }
    normalized_source_timeline_name = str(source_timeline_name or "").strip()
    if not normalized_source_timeline_name:
        return {
            "status": "skipped",
            "reason": "missing_source_timeline_name",
            "staging_readback": staging_readback,
        }

    try:
        current_database = resolve_current_disk_project_db(conn, allow_project_name_inference=True)
    except Exception as exc:
        return {
            "status": "skipped",
            "reason": "project_db_unavailable",
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }
    project_db_path = str(current_database["project_db_path"])
    staging_start_candidates = _project_db_start_candidates(conn, int(staging_start))
    expected_names = [
        clip_name,
        str(staging_readback.get("name") or ""),
        holder,
        "Text+",
        "Fusion Composition",
    ]

    deadline = time.monotonic() + max(0.0, float(timeout_seconds))
    attempts = 0
    last_error: dict[str, Any] | None = None
    last_clip_not_found: dict[str, Any] | None = None
    started = time.monotonic()

    while True:
        attempts += 1
        connection = None
        try:
            connection = sqlite3.connect(f"file:{project_db_path}?mode=ro", uri=True, timeout=1.0)
            cursor = connection.cursor()
            source_track_ids = db_timeline_rows._timeline_track_ids(
                cursor,
                timeline_name=normalized_source_timeline_name,
                track_type="video",
                track_index=int(staging_track),
            )
            row = _select_inserted_holder_db_row(
                cursor,
                staging_start_candidates=staging_start_candidates,
                staging_duration=int(staging_duration),
                expected_names=expected_names,
                source_track_ids=source_track_ids,
                item_id=staging_readback.get("timeline_item_id"),
            )
            elapsed_ms = int((time.monotonic() - started) * 1000)
            return {
                "status": "materialized",
                "project_db_path": project_db_path,
                "attempts": attempts,
                "elapsed_ms": elapsed_ms,
                "poll_seconds": float(poll_seconds),
                "timeout_seconds": float(timeout_seconds),
                "matched_row": {
                    "item_id": row.get("Sm2TiItem_id"),
                    "name": row.get("Name"),
                    "start": row.get("Start"),
                    "duration": row.get("Duration"),
                    "track_id": row.get("relation_track_id") or row.get("Sm2TiTrack_id"),
                },
            }
        except ClipNotFound as exc:
            last_clip_not_found = dict(getattr(exc, "details", {}) or {})
            last_error = {"type": exc.__class__.__name__, "message": str(exc)}
        except Exception as exc:
            last_error = {"type": exc.__class__.__name__, "message": str(exc)}
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass

        if time.monotonic() >= deadline:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            return {
                "status": "not_observed",
                "project_db_path": project_db_path,
                "attempts": attempts,
                "elapsed_ms": elapsed_ms,
                "poll_seconds": float(poll_seconds),
                "timeout_seconds": float(timeout_seconds),
                "staging_start_candidates": staging_start_candidates,
                "staging_duration": int(staging_duration),
                "expected_names": expected_names,
                "last_error": last_error,
                "last_clip_not_found": last_clip_not_found,
            }

        time.sleep(max(0.05, float(poll_seconds)))


def _move_native_precise_holder_via_db(
    conn: Any,
    *,
    timeline_name: str | None,
    source_timeline_name: str | None = None,
    staging_readback: dict[str, Any],
    target_track: int,
    target_record_frame: int,
    target_duration_frames: int,
    clip_name: str,
    holder: str,
    holder_kind: str,
    require_fusion_tools: bool = False,
) -> dict[str, Any]:
    from ..connection import ResolveConnection
    from ..core import db_session, db_timeline_rows, timeline_item_duration_db

    staging_start = staging_readback.get("start")
    staging_duration = staging_readback.get("duration")
    if staging_start is None or staging_duration is None:
        raise APICallFailed(
            "Inserted native holder did not expose readable timing for precise Project.db placement.",
            details={"staging_readback": staging_readback, "target_track": target_track, "target_record_frame": target_record_frame},
        )
    supplied_start_candidates = staging_readback.get("db_start_candidates")
    staging_start_candidates = (
        sorted({int(value) for value in supplied_start_candidates if int(value) >= 0})
        if isinstance(supplied_start_candidates, (list, tuple, set)) and supplied_start_candidates
        else _project_db_start_candidates(conn, int(staging_start))
    )
    target_timeline_name = timeline_name or _timeline_name(getattr(conn, "timeline", None))
    source_timeline_name = source_timeline_name or target_timeline_name
    if not target_timeline_name:
        raise APICallFailed("Cannot resolve active timeline name for precise Fusion placement.")
    if not source_timeline_name:
        raise APICallFailed("Cannot resolve source timeline name for precise Fusion placement.")
    staging_track = staging_readback.get("track_index")
    if staging_track is None:
        raise ValidationError(
            "Project.db holder transplant requires the source timeline track index.",
            details={"source_timeline": source_timeline_name},
        )
    target_track_before = _target_track_preservation_snapshot(
        _enumerated_video_items(conn),
        track_index=int(target_track),
    )

    expected_names = [
        clip_name,
        str(staging_readback.get("name") or ""),
        holder,
        "Text+",
        "Fusion Composition",
    ]

    def _writer(_connection: Any, cursor: Any, _session: Any) -> dict[str, Any]:
        target_track_ids = db_timeline_rows._timeline_track_ids(
            cursor,
            timeline_name=target_timeline_name,
            track_type="video",
            track_index=int(target_track),
        )
        if not target_track_ids:
            raise ClipNotFound(
                "No Project.db video track matched the requested precise Fusion track.",
                details={"timeline": target_timeline_name, "track": target_track},
            )
        target_track_id = str(target_track_ids[0])
        source_track_ids = db_timeline_rows._timeline_track_ids(
            cursor,
            timeline_name=source_timeline_name,
            track_type="video",
            track_index=int(staging_track),
        )
        source_track_ids = [
            str(track_id).strip()
            for track_id in source_track_ids
            if str(track_id or "").strip()
        ]
        if not source_track_ids:
            raise ClipNotFound(
                "No Project.db video track matched the precise Fusion scratch timeline.",
                details={
                    "source_timeline": source_timeline_name,
                    "track": int(staging_track),
                },
            )
        row = _select_inserted_holder_db_row(
            cursor,
            staging_start_candidates=staging_start_candidates,
            staging_duration=int(staging_duration),
            expected_names=expected_names,
            source_track_ids=source_track_ids,
            item_id=staging_readback.get("timeline_item_id"),
        )
        item_id = str(row.get("Sm2TiItem_id") or "")
        source_track_id = str(row.get("relation_track_id") or row.get("Sm2TiTrack_id") or "")
        relation_rowid = row.get("relation_rowid")
        if not item_id or relation_rowid is None:
            raise ValidationError(
                "Project.db row for native Fusion holder is missing required relation fields.",
                details={"item_id": item_id, "relation_rowid": relation_rowid, "row": {key: row.get(key) for key in ("Name", "Start", "Duration")}},
            )

        source_db_start = int(row.get("Start") or 0)
        start_domain_offset = int(staging_start) - source_db_start
        target_db_start = int(target_record_frame) - start_domain_offset
        if target_db_start < 0:
            target_db_start = int(target_record_frame)

        updates = timeline_item_duration_db._updates_for_duration(row, new_duration=int(target_duration_frames), fps=conn.fps)
        updates["Start"] = str(target_db_start)
        updates["Name"] = str(clip_name)
        updates["Sm2TiTrack_id"] = target_track_id
        db_timeline_rows.update_row(cursor, "Sm2TiItem", "Sm2TiItem_id", item_id, updates)
        target_relation_db_index = db_session.next_db_index(
            cursor,
            table_name="Sm2TiItem_Sm2TiTrack",
            owner_value=target_track_id,
            property_name="Items",
        )
        cursor.execute(
            "UPDATE Sm2TiItem_Sm2TiTrack SET DbOwner = ?, DbIndex = ? WHERE rowid = ?",
            (target_track_id, int(target_relation_db_index), relation_rowid),
        )
        if source_track_id:
            db_session.rebuild_track_item_indices(cursor, track_id=source_track_id)
        if target_track_id and target_track_id != source_track_id:
            db_session.rebuild_track_item_indices(cursor, track_id=target_track_id)

        return {
            "item_id": item_id,
            "timeline": target_timeline_name,
            "source_timeline": source_timeline_name,
            "holder": holder,
            "holder_kind": holder_kind,
            "old_track_id": source_track_id or None,
            "new_track_id": target_track_id,
            "new_relation_db_index": int(target_relation_db_index),
            "old_start": int(row.get("Start") or 0),
            "old_duration": int(row.get("Duration") or 0),
            "new_track": int(target_track),
            "new_start": int(target_record_frame),
            "new_db_start": int(target_db_start),
            "start_domain_offset": int(start_domain_offset),
            "new_duration": int(target_duration_frames),
            "new_end": int(target_record_frame) + int(target_duration_frames),
            "updated_columns": sorted(
                {
                    *updates.keys(),
                    "Sm2TiItem_Sm2TiTrack.DbOwner",
                    "Sm2TiItem_Sm2TiTrack.DbIndex",
                }
            ),
        }

    def _verifier(fresh_conn: Any, mutation_result: dict[str, Any], _session: Any) -> dict[str, Any]:
        if _timeline_name(getattr(fresh_conn, "timeline", None)) != target_timeline_name:
            timeline_ops.switch_timeline(fresh_conn, name=target_timeline_name)
        all_rows = _enumerated_video_items(fresh_conn)
        expected_item_id = str(mutation_result.get("item_id") or "")
        matches = [
            row
            for row in all_rows
            if str(row["readback"].get("timeline_item_id") or "") == expected_item_id
            and row["readback"].get("track_index") == int(target_track)
            and row["readback"].get("start") == int(target_record_frame)
            and row["readback"].get("duration") == int(target_duration_frames)
            and str(row["readback"].get("name") or "") in expected_names
        ]
        if len(matches) != 1:
            raise APICallFailed(
                "Precise Fusion placement did not enumerate exactly one matching timeline item.",
                details={
                    "expected": {
                        "track_index": int(target_track),
                        "start": int(target_record_frame),
                        "duration": int(target_duration_frames),
                        "name": str(clip_name),
                        "timeline_item_id": expected_item_id,
                        "accepted_native_names": expected_names,
                    },
                    "match_count": len(matches),
                    "matches": [row["readback"] for row in matches],
                    "observed": [row["readback"] for row in all_rows],
                },
            )
        enumerated = matches[0]
        readback = dict(enumerated["readback"])
        requested_name_read_back = str(readback.get("name") or "") == str(clip_name)
        target_track_after = _target_track_preservation_snapshot(
            [row for row in all_rows if row is not enumerated],
            track_index=int(target_track),
        )
        if target_track_after != target_track_before:
            raise APICallFailed(
                "Precise Fusion transplant changed pre-existing target-track items.",
                details={
                    "timeline": target_timeline_name,
                    "track": int(target_track),
                    "before": target_track_before,
                    "after": target_track_after,
                    "inserted": readback,
                },
            )
        tool_summary = _summarize_imported_fusion_tools(enumerated["item"])
        if require_fusion_tools and (
            tool_summary.get("accessible") is False
            or int(tool_summary.get("tool_count") or 0) <= 0
        ):
            raise APICallFailed(
                "Transplanted Fusion/Text+ holder did not expose imported Fusion tools.",
                details={
                    "timeline": target_timeline_name,
                    "track": int(target_track),
                    "readback": readback,
                    "fusion": tool_summary,
                },
            )
        return {
            "status": "verified",
            "checks": [
                {
                    "name": "precise_fusion_holder_readback",
                    "ok": True,
                    "expected": {
                        "track": int(target_track),
                        "start": int(target_record_frame),
                        "duration": int(target_duration_frames),
                        "timeline_item_id": expected_item_id,
                    },
                    "matches": [readback],
                    "requested_name_read_back": requested_name_read_back,
                    "native_name_retained": not requested_name_read_back,
                },
                {
                    "name": "pre_existing_target_track_items_preserved",
                    "ok": True,
                    "before": target_track_before,
                    "after": target_track_after,
                },
            ],
            "readback": readback,
            "fusion": tool_summary,
            "target_track_preservation": {
                "verified": True,
                "before": target_track_before,
                "after": target_track_after,
            },
        }

    result = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Precise Fusion/Text+ holder placement",
        writer=_writer,
        verifier=_verifier,
        allow_project_name_inference=True,
    )
    result["connection_reloaded"] = True
    ResolveConnection.reset()
    return result


def _insert_setting_precise_via_scratch_db(
    conn: Any,
    *,
    path: str,
    clip_name: str,
    duration: str,
    duration_frames: int,
    track: int,
    record_frame: int,
    holder: str,
    holder_kind: str,
    position_x: float | None,
    position_y: float | None,
    holder_lookup: dict[str, Any],
    track_summary: dict[str, Any],
    fresh_empty_timeline_settle: dict[str, Any] | None,
) -> dict[str, Any]:
    from ..connection import ResolveConnection

    normalized_holder_kind = str(holder_kind or "fusion").strip().lower().replace("_", "-")
    target_timeline = getattr(getattr(conn, "project", None), "GetCurrentTimeline", lambda: None)()
    target_timeline_name = _timeline_name(target_timeline or getattr(conn, "timeline", None))
    if not target_timeline_name:
        raise APICallFailed("Cannot resolve the target timeline for isolated precise Fusion insertion.")
    try:
        target_playhead = timeline_ops.get_playhead(conn)
    except Exception:
        target_playhead = None

    scratch_timeline_name = _unique_validate_scratch_timeline_name(conn)
    scratch_created = False
    scratch_cleanup: dict[str, Any] | None = None
    layout_prepared = None
    layout = None
    db_move = None
    db_attempted = False
    original_error: Exception | None = None
    try:
        scratch_format = _current_timeline_format(conn)
        timeline_ops.create_timeline(
            conn,
            scratch_timeline_name,
            width=scratch_format.get("width"),
            height=scratch_format.get("height"),
            fps=scratch_format.get("fps"),
        )
        scratch_created = True
        try:
            conn.refresh()
        except Exception:
            pass
        if _timeline_name(getattr(conn, "timeline", None)) != scratch_timeline_name:
            raise APICallFailed(
                "Scratch timeline did not become current for isolated Fusion insertion.",
                details={"scratch_timeline": scratch_timeline_name},
            )
        if _enumerated_video_items(conn):
            raise APICallFailed(
                "Scratch timeline was not empty before isolated Fusion insertion.",
                details={"scratch_timeline": scratch_timeline_name},
            )

        scratch_start = _connection_start_frame(conn)
        _returned_item, native_insert = _insert_native_holder_at_frame(
            conn,
            holder=holder,
            holder_kind=normalized_holder_kind,
            record_frame=scratch_start,
        )
        scratch_rows = _enumerated_video_items(conn)
        if len(scratch_rows) != 1:
            raise APICallFailed(
                "Native scratch insertion did not enumerate exactly one holder.",
                details={
                    "scratch_timeline": scratch_timeline_name,
                    "item_count": len(scratch_rows),
                    "items": [row["readback"] for row in scratch_rows],
                },
            )
        scratch_row = scratch_rows[0]
        item = scratch_row["item"]
        staging_readback = dict(scratch_row["readback"])
        if staging_readback.get("track_index") != 1 or staging_readback.get("start") != int(scratch_start):
            raise APICallFailed(
                "Native scratch holder placement did not verify on scratch V1.",
                details={
                    "scratch_timeline": scratch_timeline_name,
                    "expected": {"track_index": 1, "start": int(scratch_start)},
                    "readback": staging_readback,
                },
            )

        importer = getattr(item, "ImportFusionComp", None)
        if not callable(importer):
            raise APICallFailed(
                "Scratch holder clip does not support ImportFusionComp.",
                details={"holder": holder, "holder_kind": normalized_holder_kind},
            )
        layout_prepared = _prepare_setting_import(path)
        import_path = str(layout_prepared.get("import_path") or path)
        if not importer(import_path):
            raise APICallFailed(
                "ImportFusionComp failed in the isolated scratch timeline.",
                details={
                    "path": path,
                    "import_path": import_path,
                    "holder": holder,
                    "holder_kind": normalized_holder_kind,
                },
            )
        layout = _cleanup_prepared_setting(layout_prepared)
        layout_prepared = None

        item_props = _apply_timeline_item_name_and_duration(
            item,
            name=clip_name,
            duration_frames=duration_frames,
        )
        position_result = (
            _apply_timeline_item_position(item, position_x, position_y)
            if position_x is not None or position_y is not None
            else {"requested": {"x": position_x, "y": position_y}, "applied": False}
        )
        staging_row = _unique_enumerated_video_item(
            conn,
            track_index=1,
            start=int(scratch_start),
        )
        staging_readback = dict(staging_row["readback"])
        staging_readback["db_start_candidates"] = _project_db_start_candidates(
            conn,
            int(staging_readback["start"]),
        )
        tool_summary = _summarize_imported_fusion_tools(staging_row["item"])
        if tool_summary.get("accessible") is False or int(tool_summary.get("tool_count") or 0) <= 0:
            raise APICallFailed(
                "Imported .setting has no independently readable Fusion tools in the scratch timeline.",
                details={
                    "path": path,
                    "scratch_timeline": scratch_timeline_name,
                    "item": staging_readback,
                    "fusion": tool_summary,
                },
            )

        timeline_ops.switch_timeline(conn, name=target_timeline_name)
        if _timeline_name(getattr(conn, "timeline", None)) != target_timeline_name:
            raise APICallFailed(
                "Target timeline did not restore before precise Project.db transplant.",
                details={"target_timeline": target_timeline_name},
            )
        db_attempted = True
        db_move = _move_native_precise_holder_via_db(
            conn,
            timeline_name=target_timeline_name,
            source_timeline_name=scratch_timeline_name,
            staging_readback=staging_readback,
            target_track=track,
            target_record_frame=record_frame,
            target_duration_frames=duration_frames,
            clip_name=clip_name,
            holder=holder,
            holder_kind=normalized_holder_kind,
            require_fusion_tools=True,
        )
        verification_payload = db_move.get("verification") if isinstance(db_move, dict) else None
        readback = verification_payload.get("readback") if isinstance(verification_payload, dict) else None
        target_tool_summary = verification_payload.get("fusion") if isinstance(verification_payload, dict) else None
        if not isinstance(readback, dict) or not isinstance(target_tool_summary, dict):
            raise APICallFailed(
                "Precise Project.db transplant did not return exact target readback.",
                details={"target_timeline": target_timeline_name, "db_move": db_move},
            )

        cleanup_conn = ResolveConnection.get()
        cleanup_conn.connect()
        scratch_cleanup = _cleanup_native_precise_scratch_timeline(
            cleanup_conn,
            target_timeline_name=target_timeline_name,
            scratch_timeline_name=scratch_timeline_name,
            target_playhead=target_playhead,
        )
        if not scratch_cleanup.get("ok"):
            raise APICallFailed(
                "Precise Fusion insertion succeeded, but scratch timeline cleanup did not verify.",
                details={"cleanup": scratch_cleanup, "db_move": db_move},
                recoverability="manual",
            )

        route = (
            ROUTE_NATIVE_TEXTPLUS_SCRATCH_DB_IMPORT_FUSION_COMP
            if normalized_holder_kind == "textplus"
            else ROUTE_NATIVE_FUSION_SCRATCH_DB_IMPORT_FUSION_COMP
        )
        verification = {
            "imported": True,
            "track_requested": int(track),
            "track_readback": readback.get("track_index"),
            "record_frame_requested": int(record_frame),
            "start_readback": readback.get("start"),
            "duration_requested_frames": int(duration_frames),
            "duration_readback_frames": readback.get("duration"),
            "fusion_comp_accessible": bool(target_tool_summary.get("accessible")),
            "tool_count": target_tool_summary.get("tool_count"),
            "track_ok": readback.get("track_index") == int(track),
            "start_ok": readback.get("start") == int(record_frame),
            "duration_ok": readback.get("duration") == int(duration_frames),
            "node_status_verified": bool(target_tool_summary.get("node_status_verified")),
            "node_probe_verified": bool(target_tool_summary.get("node_probe_verified")),
            "visual_output_verified": False,
            "placement_proof": readback.get("placement_proof"),
        }
        if not all(verification[key] for key in ("track_ok", "start_ok", "duration_ok")):
            raise APICallFailed(
                "Precise Fusion transplant did not verify exact target placement.",
                details={"verification": verification, "item": readback},
            )
        # The native scratch holder can reject duration mutation even though the
        # subsequent Project.db transplant applies and independently verifies it.
        # Replace those scratch-only fields only after exact final readback proves
        # the requested duration; missing or mismatched readback remains fail-closed.
        item_props["duration_readback_frames"] = int(readback["duration"])
        item_props["duration_applied"] = True
        item_props["duration_property"] = "project_db_transplant_verified"
        set_verification_status("partial")
        return {
            "path": path,
            "import_path": import_path,
            "name": clip_name,
            "holder": holder,
            "holder_kind": normalized_holder_kind,
            "holder_lookup": holder_lookup,
            "track": int(track),
            "record_frame": int(record_frame),
            "duration": duration,
            "duration_frames": int(duration_frames),
            "position_requested": {"x": position_x, "y": position_y},
            "position_applied": position_result,
            "route": route,
            "fresh_empty_timeline_settle": fresh_empty_timeline_settle,
            "track_summary": track_summary,
            "append": None,
            "native_insert": native_insert,
            "native_direct": False,
            "native_track_lock_direct": False,
            "track_locks": None,
            "duration_native_trim": None,
            "db_materialization": None,
            "db_move": db_move,
            "duration_db_update": None,
            "connection_reloaded": True,
            "scratch_timeline": {
                "name": scratch_timeline_name,
                "source_item": staging_readback,
                "cleanup": scratch_cleanup,
            },
            "item": {**item_props, **readback},
            "fusion": target_tool_summary,
            "layout": layout,
            "verification": verification,
            "cleanup": scratch_cleanup,
        }
    except Exception as exc:
        original_error = exc
        raise
    finally:
        if layout_prepared is not None:
            layout = _cleanup_prepared_setting(layout_prepared)
        if scratch_created and not (scratch_cleanup or {}).get("ok"):
            cleanup_conn = conn
            if db_attempted:
                try:
                    cleanup_conn = ResolveConnection.get()
                    cleanup_conn.connect()
                except Exception:
                    cleanup_conn = conn
            try:
                scratch_cleanup = _cleanup_native_precise_scratch_timeline(
                    cleanup_conn,
                    target_timeline_name=target_timeline_name,
                    scratch_timeline_name=scratch_timeline_name,
                    target_playhead=target_playhead,
                )
            except Exception as cleanup_exc:
                scratch_cleanup = {
                    "ok": False,
                    "errors": [
                        {
                            "step": "scratch_cleanup",
                            "type": cleanup_exc.__class__.__name__,
                            "message": str(cleanup_exc),
                        }
                    ],
                }
            if original_error is not None and not scratch_cleanup.get("ok"):
                raise APICallFailed(
                    "Precise Fusion insertion failed and scratch timeline cleanup did not verify.",
                    details={
                        "scratch_timeline": scratch_timeline_name,
                        "cleanup": scratch_cleanup,
                        "original_error": {
                            "type": original_error.__class__.__name__,
                            "message": str(original_error),
                            "details": getattr(original_error, "details", None),
                        },
                    },
                    recoverability="manual",
                ) from original_error
