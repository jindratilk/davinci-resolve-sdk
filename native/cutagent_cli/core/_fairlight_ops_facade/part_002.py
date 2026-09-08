from __future__ import annotations

def _normalize_audio_source_patch_entry(
    raw: dict[str, Any],
    *,
    index: int,
    fps: float,
    timeline_start_frame: int,
    parse_record_refs: bool,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValidationError(
            "Each audio source patch entry must be a JSON object.",
            details={"index": index, "entry": raw},
            recoverability="not_applicable",
        )

    item_id = _first_present(raw, "item_id", "itemId", "Sm2TiItem_id")
    track_index = _first_present(raw, "track_index", "trackIndex")
    record_ref = _first_present(raw, "record_frame", "recordFrame", "record_start_frame", "record_start")
    record_duration_ref = _first_present(raw, "record_duration", "recordDuration", "record_duration_frames")
    record_end_ref = _first_present(raw, "record_end", "recordEnd", "record_end_frame")

    if item_id is None and (track_index is None or record_ref is None):
        raise ValidationError(
            "Audio source patch requires either item_id or track_index plus record_frame.",
            details={"index": index, "entry": raw},
            recoverability="not_applicable",
        )
    if item_id is not None and (track_index is not None or record_ref is not None):
        raise ValidationError(
            "Audio source patch selectors are mutually exclusive: use item_id or track_index plus record_frame.",
            details={"index": index, "item_id": item_id, "track_index": track_index, "record_frame": record_ref},
            recoverability="not_applicable",
        )
    if record_duration_ref is not None and record_end_ref is not None:
        raise ValidationError(
            "Use only one record duration selector: record_duration or record_end.",
            details={"index": index, "record_duration": record_duration_ref, "record_end": record_end_ref},
            recoverability="not_applicable",
        )

    source_start_ref = _first_present(raw, "source_start_frame", "source_start", "sourceStartFrame", "sourceStart")
    if source_start_ref is None:
        raise ValidationError(
            "Audio source patch requires source_start_frame/source_start.",
            details={"index": index, "entry": raw},
            recoverability="not_applicable",
        )
    source_start_frame = _parse_frame_count(source_start_ref, field="source_start_frame", fps=fps)
    if source_start_frame < 0:
        raise ValidationError(
            "source_start_frame must be greater than or equal to 0.",
            details={"index": index, "source_start_frame": source_start_frame},
            recoverability="not_applicable",
        )

    duration_ref = _first_present(raw, "duration_frames", "duration", "source_duration_frame", "source_duration")
    source_end_ref = _first_present(raw, "source_end_frame", "source_end", "sourceEndFrame", "sourceEnd")
    if duration_ref is not None and source_end_ref is not None:
        raise ValidationError(
            "Use only one source duration field: duration_frames/duration or source_end_frame/source_end.",
            details={"index": index, "duration_frames": duration_ref, "source_end_frame": source_end_ref},
            recoverability="not_applicable",
        )

    duration_frames = None
    source_end_frame = None
    if source_end_ref is not None:
        source_end_frame = _parse_frame_count(source_end_ref, field="source_end_frame", fps=fps)
        if source_end_frame <= source_start_frame:
            raise ValidationError(
                "source_end_frame must be greater than source_start_frame.",
                details={
                    "index": index,
                    "source_start_frame": source_start_frame,
                    "source_end_frame": source_end_frame,
                },
                recoverability="not_applicable",
            )
        duration_frames = source_end_frame - source_start_frame
    elif duration_ref is not None:
        duration_frames = _parse_frame_count(duration_ref, field="duration_frames", fps=fps)
        if duration_frames <= 0:
            raise ValidationError(
                "duration_frames must be greater than 0.",
                details={"index": index, "duration_frames": duration_frames},
                recoverability="not_applicable",
            )

    selector: dict[str, Any]
    if item_id is not None:
        selector = {"kind": "item_id", "item_id": str(item_id)}
    else:
        normalized_track_index = _coerce_int(track_index, field="track_index")
        if normalized_track_index < 1:
            raise ValidationError(
                "track_index must be 1 or greater.",
                details={"index": index, "track_index": normalized_track_index},
                recoverability="not_applicable",
            )
        if parse_record_refs:
            record_frame = parse_record_frame(str(record_ref), fps, timeline_start_frame)
            record_duration = (
                None
                if record_duration_ref is None
                else _parse_frame_count(record_duration_ref, field="record_duration", fps=fps)
            )
            record_end = (
                None
                if record_end_ref is None
                else parse_record_frame(str(record_end_ref), fps, timeline_start_frame)
            )
        else:
            record_frame = None
            record_duration = None
            record_end = None
        if record_duration is not None and record_duration <= 0:
            raise ValidationError(
                "record_duration must be greater than 0.",
                details={"index": index, "record_duration": record_duration},
                recoverability="not_applicable",
            )
        selector = {
            "kind": "track_record",
            "track_index": normalized_track_index,
            "record_frame": record_frame,
            "record_frame_ref": str(record_ref),
            "record_duration": record_duration,
            "record_duration_ref": None if record_duration_ref is None else str(record_duration_ref),
            "record_end": record_end,
            "record_end_ref": None if record_end_ref is None else str(record_end_ref),
        }

    return {
        "index": index,
        "selector": selector,
        "source_start_frame": int(source_start_frame),
        "source_end_frame": source_end_frame,
        "duration_frames": duration_frames,
        "raw": raw,
    }


def normalize_audio_source_patch_entries(
    entries: list[dict[str, Any]],
    *,
    conn=None,
    fps: float | None = None,
    timeline_start_frame: int | None = None,
    parse_record_refs: bool = True,
) -> list[dict[str, Any]]:
    """Normalize public audio source-offset patch requests."""
    if not entries:
        raise ValidationError(
            "Audio source patch batch must contain at least one entry.",
            details={"entries": entries},
            recoverability="not_applicable",
        )
    resolved_fps = float(fps if fps is not None else (_timeline_fps(conn) if conn is not None else 24.0))
    resolved_start = int(
        timeline_start_frame
        if timeline_start_frame is not None
        else (_timeline_start_frame(conn) if conn is not None else 0)
    )
    return [
        _normalize_audio_source_patch_entry(
            dict(entry),
            index=index,
            fps=resolved_fps,
            timeline_start_frame=resolved_start,
            parse_record_refs=parse_record_refs,
        )
        for index, entry in enumerate(entries)
    ]


def _audio_track_ids_for_sequence(cursor: sqlite3.Cursor, sequence: str) -> list[str]:
    rows = cursor.execute(
        """
        SELECT Sm2TiTrack_id
        FROM Sm2TiTrack
        WHERE Sequence = ? AND Type = 1
        ORDER BY rowid
        """,
        (sequence,),
    ).fetchall()
    return [str(row[0]) for row in rows if row and row[0] is not None]


def _fetch_source_patch_audio_item_by_id(
    cursor: sqlite3.Cursor,
    *,
    sequence: str,
    item_id: str,
    track_ids: list[str],
) -> dict[str, Any]:
    if not track_ids:
        raise ValidationError(
            "Target timeline has no audio tracks in the DaVinci Resolve Disk project database.",
            details={"timeline_sequence": sequence},
        )
    rows = cursor.execute(
        """
        SELECT rowid AS db_rowid, Sm2TiItem_id, Sm2TiTrack_id, Name, Start, Duration, "In"
        FROM Sm2TiItem
        WHERE Sm2TiItem_id = ?
        """,
        (item_id,),
    ).fetchall()
    if not rows:
        raise ValidationError(
            "Audio timeline item was not found in the target timeline.",
            details={"item_id": item_id, "timeline_sequence": sequence},
        )
    row = rows[0]
    track_id = str(row["Sm2TiTrack_id"] or "")
    if track_id not in track_ids and _table_exists(cursor, "Sm2TiItem_Sm2TiTrack"):
        owner_rows = cursor.execute(
            """
            SELECT DbOwner
            FROM Sm2TiItem_Sm2TiTrack
            WHERE DbAssociate = ? AND DbPropertyName = 'Items'
            ORDER BY DbIndex, rowid
            """,
            (item_id,),
        ).fetchall()
        for owner_row in owner_rows:
            owner = str(owner_row[0] or "")
            if owner in track_ids:
                track_id = owner
                break
    if track_id not in track_ids:
        raise ValidationError(
            "Audio timeline item was not found in the target timeline audio tracks.",
            details={"item_id": item_id, "timeline_sequence": sequence},
        )
    track_index = track_ids.index(track_id) + 1
    return {key: row[key] for key in row.keys()} | {"track_index": track_index}


def _record_frame_candidates(record_frame: int, timeline_start_frame: int) -> list[int]:
    candidates = [int(record_frame)]
    if timeline_start_frame:
        relative = int(record_frame) - int(timeline_start_frame)
        if relative not in candidates:
            candidates.append(relative)
    return candidates


def _fetch_audio_items_by_track_record(
    cursor: sqlite3.Cursor,
    *,
    track_ids: list[str],
    track_index: int,
    record_frame: int,
    record_duration: int | None,
    record_end: int | None,
    timeline_start_frame: int,
    allow_multiple: bool,
) -> list[dict[str, Any]]:
    if track_index < 1 or track_index > len(track_ids):
        raise ValidationError(
            "Audio track index does not exist in the DaVinci Resolve Disk project database.",
            details={"track_index": track_index, "audio_track_count": len(track_ids)},
        )
    track_id = track_ids[track_index - 1]
    rows = cursor.execute(
        """
        SELECT rowid AS db_rowid, Sm2TiItem_id, Sm2TiTrack_id, Name, Start, Duration, "In"
        FROM Sm2TiItem
        WHERE Sm2TiTrack_id = ?
        ORDER BY rowid
        """,
        (track_id,),
    ).fetchall()
    candidates = set(_record_frame_candidates(record_frame, timeline_start_frame))
    matched = []
    for row in rows:
        start_frame = _duration_frames(row["Start"])
        duration_frames = _duration_frames(row["Duration"])
        if start_frame not in candidates:
            continue
        if record_duration is not None and duration_frames != int(record_duration):
            continue
        if record_end is not None:
            row_end_candidates = {start_frame + duration_frames}
            if timeline_start_frame:
                row_end_candidates.add(start_frame + duration_frames + int(timeline_start_frame))
            if int(record_end) not in row_end_candidates:
                continue
        matched.append({key: row[key] for key in row.keys()} | {"track_index": track_index})

    if not matched:
        raise ValidationError(
            "No audio timeline item matched track_index and record_frame.",
            details={
                "track_index": track_index,
                "record_frame": record_frame,
                "record_frame_candidates": sorted(candidates),
                "record_duration": record_duration,
                "record_end": record_end,
                "items_on_track": len(rows),
            },
        )
    if len(matched) > 1 and not allow_multiple:
        raise ValidationError(
            "Multiple audio timeline items matched track_index and record_frame.",
            details={
                "track_index": track_index,
                "record_frame": record_frame,
                "matches": [
                    {
                        "item_id": str(row["Sm2TiItem_id"]),
                        "clip_name": str(row["Name"] or ""),
                        "start": _duration_frames(row["Start"]),
                        "duration": _duration_frames(row["Duration"]),
                        "db_rowid": int(row["db_rowid"] or 0),
                    }
                    for row in matched
                ],
                "use_allow_multiple": True,
            },
        )
    return matched


def _patch_audio_source_offsets_writer(
    *,
    timeline_name: str,
    patches: list[dict[str, Any]],
    timeline_start_frame: int,
    allow_multiple: bool,
):
    def _writer(connection: sqlite3.Connection, cursor: sqlite3.Cursor, session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        sequence = _fetch_timeline_sequence(cursor, timeline_name)
        track_ids = _audio_track_ids_for_sequence(cursor, sequence)
        patched: list[dict[str, Any]] = []
        for patch in patches:
            selector = patch["selector"]
            if selector["kind"] == "item_id":
                target_rows = [
                    _fetch_source_patch_audio_item_by_id(
                        cursor,
                        sequence=sequence,
                        item_id=str(selector["item_id"]),
                        track_ids=track_ids,
                    )
                ]
            else:
                target_rows = _fetch_audio_items_by_track_record(
                    cursor,
                    track_ids=track_ids,
                    track_index=int(selector["track_index"]),
                    record_frame=int(selector["record_frame"]),
                    record_duration=selector.get("record_duration"),
                    record_end=selector.get("record_end"),
                    timeline_start_frame=timeline_start_frame,
                    allow_multiple=allow_multiple,
                )

            for row in target_rows:
                previous_duration = _duration_frames(row["Duration"])
                duration_frames = patch.get("duration_frames")
                if duration_frames is None:
                    duration_frames = previous_duration - int(patch["source_start_frame"])
                duration_frames = int(duration_frames)
                if duration_frames <= 0:
                    raise ValidationError(
                        "Computed duration_frames must be greater than 0.",
                        details={
                            "item_id": str(row["Sm2TiItem_id"]),
                            "source_start_frame": int(patch["source_start_frame"]),
                            "previous_duration": previous_duration,
                            "duration_frames": duration_frames,
                        },
                        recoverability="not_applicable",
                    )

                item_id = str(row["Sm2TiItem_id"])
                cursor.execute(
                    """
                    UPDATE Sm2TiItem
                    SET "In" = ?, Duration = ?
                    WHERE Sm2TiItem_id = ?
                    """,
                    (str(int(patch["source_start_frame"])), str(duration_frames), item_id),
                )
                patched.append(
                    {
                        "item_id": item_id,
                        "track_index": int(row["track_index"]),
                        "clip_name": str(row["Name"] or ""),
                        "previous_in": None if row["In"] is None else str(row["In"]),
                        "previous_duration": None if row["Duration"] is None else str(row["Duration"]),
                        "source_start_frame": int(patch["source_start_frame"]),
                        "duration_frames": duration_frames,
                        "db_rowid": int(row["db_rowid"] or 0),
                    }
                )
        return {
            "timeline": timeline_name,
            "timeline_sequence": sequence,
            "patched_count": len(patched),
            "patched_items": patched,
        }

    return _writer


def _verify_audio_source_offsets():
    def _verifier(conn, mutation_result: dict[str, Any], session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        connection = sqlite3.connect(session.project_db_path, timeout=5.0)
        try:
            cursor = connection.cursor()
            checks = []
            for entry in mutation_result.get("patched_items") or []:
                row = cursor.execute(
                    'SELECT "In", Duration FROM Sm2TiItem WHERE Sm2TiItem_id = ?',
                    (entry["item_id"],),
                ).fetchone()
                in_value = str(row[0]) if row and row[0] is not None else None
                duration_value = _duration_frames(row[1]) if row else None
                expected_in = str(int(entry["source_start_frame"]))
                expected_duration = int(entry["duration_frames"])
                ok = in_value == expected_in and duration_value == expected_duration
                checks.append(
                    {
                        "name": f'audio_track_{entry["track_index"]}_source_offset_patched',
                        "ok": ok,
                        "item_id": entry["item_id"],
                        "clip_name": entry["clip_name"],
                        "in_value": in_value,
                        "duration_frames": duration_value,
                        "expected_in": expected_in,
                        "expected_duration_frames": expected_duration,
                    }
                )
        finally:
            connection.close()
        return {"status": "verified" if checks and all(item["ok"] for item in checks) else "failed", "checks": checks}

    return _verifier


def patch_audio_item_source_offsets(
    conn,
    *,
    timeline_name: str | None,
    patches: list[dict[str, Any]],
    allow_multiple: bool = False,
) -> dict[str, Any]:
    """Patch Sm2TiItem source In/Duration for audio timeline items through Disk DB."""
    target_timeline_name = timeline_name or _timeline_name(conn)
    if not target_timeline_name:
        raise APICallFailed("No target timeline is available for Fairlight item source patch.")
    fps = _timeline_fps(conn)
    timeline_start = _timeline_start_frame(conn)
    normalized = normalize_audio_source_patch_entries(
        patches,
        conn=conn,
        fps=fps,
        timeline_start_frame=timeline_start,
        parse_record_refs=True,
    )
    result = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Fairlight audio item source offset patch",
        writer=_patch_audio_source_offsets_writer(
            timeline_name=target_timeline_name,
            patches=normalized,
            timeline_start_frame=timeline_start,
            allow_multiple=allow_multiple,
        ),
        verifier=_verify_audio_source_offsets(),
        allow_project_name_inference=True,
    )
    return {
        **result,
        "timeline": target_timeline_name,
        "requested_patches": [
            {key: value for key, value in patch.items() if key != "raw"}
            for patch in normalized
        ],
        "allow_multiple": bool(allow_multiple),
        "timeline_start_frame": timeline_start,
        "fps": fps,
    }


def _patch_audio_track_subtypes_writer(
    *,
    timeline_name: str,
    subtype: int,
    expected_count: int | None = None,
):
    def _writer(connection: sqlite3.Connection, cursor: sqlite3.Cursor, session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        sequence = _fetch_timeline_sequence(cursor, timeline_name)
        cursor.execute(
            "UPDATE Sm2TiTrack SET SubType = ? WHERE Sequence = ? AND Type = 1",
            (int(subtype), sequence),
        )
        updated_rows = int(cursor.rowcount or 0)
        return {
            "timeline_name": timeline_name,
            "timeline_sequence": sequence,
            "db_subtype_patch": {
                "requested": True,
                "subtype": int(subtype),
                "updated_rows": updated_rows,
            },
        }

    return _writer


def _save_project_if_available(conn) -> bool:
    project_manager = getattr(conn, "project_manager", None)
    save_fn = getattr(project_manager, "SaveProject", None) if project_manager is not None else None
    if not callable(save_fn):
        return False
    try:
        return bool(save_fn())
    except Exception:
        return False


def _disk_audio_track_count(conn, *, timeline_name: str) -> int | None:
    try:
        current_database = db_session.resolve_current_disk_project_db(conn)
        db_path = str(current_database["project_db_path"])
    except Exception:
        return None
    try:
        connection = sqlite3.connect(db_path, timeout=5.0)
        try:
            cursor = connection.cursor()
            sequence = _fetch_timeline_sequence(cursor, timeline_name)
            row = cursor.execute(
                "SELECT COUNT(*) FROM Sm2TiTrack WHERE Sequence = ? AND Type = 1",
                (sequence,),
            ).fetchone()
            return int(row[0] or 0)
        finally:
            connection.close()
    except Exception:
        return None


def _wait_for_disk_audio_track_count(conn, *, timeline_name: str, expected_count: int, timeout_seconds: float = 2.0) -> int | None:
    observed = _disk_audio_track_count(conn, timeline_name=timeline_name)
    deadline = time.monotonic() + timeout_seconds
    while observed is not None and observed < expected_count and time.monotonic() < deadline:
        time.sleep(0.1)
        observed = _disk_audio_track_count(conn, timeline_name=timeline_name)
    return observed


def _restore_timeline_after_db_session(timeline_name: str | None) -> bool:
    if not timeline_name:
        return False
    try:
        from ..connection import ResolveConnection

        fresh_conn = ResolveConnection.get()
        if getattr(fresh_conn, "project", None) is None:
            fresh_conn.connect()
        return bool(_switch_timeline_by_name(fresh_conn, timeline_name))
    except Exception:
        return False


def _verify_audio_track_subtypes(
    *,
    timeline_name: str,
    subtype: int,
    expected_count: int | None = None,
):
    def _verifier(conn, mutation_result: dict[str, Any], session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        api_audio_track_count: int | None = None
        api_timeline_switch: dict[str, Any] | None = None
        try:
            api_timeline_switch = _switch_timeline_by_name(conn, timeline_name)
            api_audio_track_count = _audio_track_count(conn)
        except Exception:
            api_audio_track_count = None

        connection = sqlite3.connect(session.project_db_path, timeout=5.0)
        try:
            cursor = connection.cursor()
            sequence = _fetch_timeline_sequence(cursor, timeline_name)
            rows = cursor.execute(
                "SELECT SubType FROM Sm2TiTrack WHERE Sequence = ? AND Type = 1 ORDER BY rowid",
                (sequence,),
            ).fetchall()
        finally:
            connection.close()

        checks = [
            {"track_index": index, "subtype": int(row[0]), "ok": int(row[0]) == int(subtype)}
            for index, row in enumerate(rows, start=1)
        ]
        expected_count_ok = expected_count is None or len(checks) >= int(expected_count)
        api_count_ok = expected_count is None or api_audio_track_count is None or api_audio_track_count >= int(expected_count)
        ok = bool(checks) and all(check["ok"] for check in checks) and expected_count_ok
        verification = {
            "status": "verified" if ok else "failed",
            "timeline_name": timeline_name,
            "timeline_sequence": sequence,
            "expected_subtype": int(subtype),
            "expected_count": expected_count,
            "db_audio_track_count": len(checks),
            "api_audio_track_count": api_audio_track_count,
            "api_timeline_switch": api_timeline_switch,
            "count_ok": bool(expected_count_ok),
            "api_count_ok": bool(api_count_ok),
            "checks": checks,
        }
        if not ok:
            raise APICallFailed(
                "Stereo audio track DB verification failed after project reopen.",
                details={"verification": verification},
                recoverability="manual",
            )
        return verification

    return _verifier


FAIRLIGHT_AUDIO_SUBTYPE_BY_TRACK_TYPE: dict[str, int] = {
    "stereo": 0,
    "mono": 1,
    "5.1": 2,
    "7.1": 3,
    "5.1film": 4,
    "7.1film": 5,
    "lrc": 26,
    "5.0": 27,
    "7.0": 28,
    "lrcs": 30,
    "lcr": 31,
    "lcrs": 32,
    "5.0film": 33,
    "quad": 34,
    "7.0film": 35,
    **{f"adaptive{channels}": 256 + channels for channels in range(1, 37)},
}
FAIRLIGHT_TRACK_TYPE_BY_AUDIO_SUBTYPE: dict[int, str] = {
    subtype: track_type
    for track_type, subtype in FAIRLIGHT_AUDIO_SUBTYPE_BY_TRACK_TYPE.items()
}
FAIRLIGHT_MIXER_FADER_BASE_OFFSET = 201153
FAIRLIGHT_MIXER_FADER_MIN_DB = -100.0
FAIRLIGHT_MIXER_FADER_MAX_DB = 10.0
FAIRLIGHT_MIXER_PAN_BASE_OFFSET = 201249
FAIRLIGHT_MIXER_RECORD_FADER_PARAM = 1
FAIRLIGHT_MIXER_RECORD_PAN_PARAM = 4
FAIRLIGHT_MIXER_PAN_MIN = -100.0
FAIRLIGHT_MIXER_PAN_MAX = 100.0
FAIRLIGHT_MIXER_STEREO_PAN_WRITE_BLOCKER_EVIDENCE: dict[str, Any] = {
    "verified_set_scope": "mono_track_2d_pan_and_stereo_track_left_right",
    "stereo_track_pan_set_supported": True,
    "multichannel_track_pan_set_supported": False,
    "resolve_21_stereo_left_right_evidence": {
        "runtime": "DaVinci Resolve 21.0.0.47 Studio",
        "project": "A10 Stereo Pan worker-ff39893061",
        "timeline": "A10 Stereo Balance Differential",
        "fixture_audio": "stereo-440L-880R.wav",
        "gui_center_artifact": "worker-ff39893061/a10-stereo-pan/gui-run3/pan-dialog-lr-center-via-graph.png",
        "gui_right_artifact": "worker-ff39893061/a10-stereo-pan/gui-run3/pan-dialog-lr-right.png",
        "center_db_artifact": "worker-ff39893061/a10-stereo-pan/gui-run3/center-exact.db",
        "right_db_artifact": "worker-ff39893061/a10-stereo-pan/gui-run3/right.db",
        "render_artifact": "worker-ff39893061/a10-stereo-pan/gui-run3/right-100.wav",
        "storage": "second_consecutive_parameter_4_record_int32_x10",
        "center_raw_values": [0, 0],
        "right_raw_values": [1000, 1000],
        "render_visible": True,
        "render_result": "100R produced a 12.0 dB right-over-left RMS differential for the stereo acceptance fixture",
    },
    "resolve_21_live_recheck": {
        "runtime": "DaVinci Resolve 21.0.0.48 Free",
        "timeline": "CUTAGENT_STEREO_PAN_RENDER_PROBE_184651",
        "read_artifact": "/tmp/cutagent_mixer_pan_cz_read_stereo_20260619.json",
        "set_blocker_artifact": "/tmp/cutagent_mixer_pan_cz_set_stereo_blocker_20260619.json",
        "channel_count": 2,
        "channel_pan_values": [0.0, 0.0],
        "blocker": "write blocked before DB commit because stereo panner semantics are not verified",
        "recovery_status": "restored",
    },
    "resolve_21_render_negative_evidence": {
        "timeline": "CUTAGENT_STEREO_PAN_RENDER_PROBE_184651",
        "fixture_audio": "/tmp/cutagent_mixer_stereo_pan_render_ch/stereo_440L_880R_4s.wav",
        "baseline_read_artifact": "/tmp/cutagent_mixer_stereo_pan_render_ch/03_pan_read_a1_baseline.json",
        "experimental_db_write_artifact": "/tmp/cutagent_mixer_stereo_pan_render_ch/06_experimental_set_stereo_lanes_left.json",
        "experimental_read_artifact": "/tmp/cutagent_mixer_stereo_pan_render_ch/07_pan_read_after_experimental_left.json",
        "render_analysis_artifact": "/tmp/cutagent_mixer_stereo_pan_render_ch/09_render_channel_analysis.json",
        "experimental_raw_values": [-1000, -1000],
        "db_lane_readback_verified": True,
        "render_visible": False,
        "render_result": "baseline and experimental renders retained the same 440 Hz left / 880 Hz right channel distribution",
    },
}
FAIRLIGHT_TRACK_CHANNELS_BY_TYPE: dict[str, int] = {
    "mono": 1,
    "stereo": 2,
    "lrc": 3,
    "lcr": 3,
    "lrcs": 4,
    "lcrs": 4,
    "quad": 4,
    "5.0": 5,
    "5.0film": 5,
    "5.1": 6,
    "5.1film": 6,
    "7.0": 7,
    "7.0film": 7,
    "7.1": 8,
    "7.1film": 8,
    **{f"adaptive{channels}": channels for channels in range(1, 37)},
}


def _fetch_audio_track_rows(
    cursor: sqlite3.Cursor,
    *,
    sequence: str,
) -> list[dict[str, Any]]:
    columns = _table_columns(cursor, "Sm2TiTrack")
    name_expr = "COALESCE(t.UserDefinedName, '')" if "UserDefinedName" in columns else "''"
    subtype_expr = "COALESCE(t.SubType, 0)" if "SubType" in columns else "0"
    if _table_exists(cursor, "Sm2SequenceContainer_Sm2TiTrack"):
        relation_rows = cursor.execute(
            f"""
            SELECT
                t.Sm2TiTrack_id,
                {name_expr} AS UserDefinedName,
                {subtype_expr} AS SubType,
                rel.DbOwner AS SequenceContainerId,
                rel.DbIndex AS DbIndex,
                t.rowid AS TrackRowId
            FROM Sm2TiTrack t
            JOIN Sm2SequenceContainer_Sm2TiTrack rel
              ON rel.DbAssociate = t.Sm2TiTrack_id
             AND rel.DbPropertyName = 'AudioTrackVec'
            WHERE t.Sequence = ? AND t.Type = 1
            ORDER BY rel.DbIndex, t.rowid
            """,
            (sequence,),
        ).fetchall()
        if relation_rows:
            return [_row_to_dict(cursor, row) for row in relation_rows]

    name_expr = "COALESCE(UserDefinedName, '')" if "UserDefinedName" in columns else "''"
    subtype_expr = "COALESCE(SubType, 0)" if "SubType" in columns else "0"
    rows = cursor.execute(
        f"""
        SELECT
            Sm2TiTrack_id,
            {name_expr} AS UserDefinedName,
            {subtype_expr} AS SubType,
            NULL AS SequenceContainerId,
            rowid - 1 AS DbIndex,
            rowid AS TrackRowId
        FROM Sm2TiTrack
        WHERE Sequence = ? AND Type = 1
        ORDER BY rowid
        """,
        (sequence,),
    ).fetchall()
    return [_row_to_dict(cursor, row) for row in rows]


def _fetch_audio_track_ids(cursor: sqlite3.Cursor, *, sequence: str) -> list[str]:
    return [str(row["Sm2TiTrack_id"]) for row in _fetch_audio_track_rows(cursor, sequence=sequence)]


def _fetch_audio_track_item_counts(cursor: sqlite3.Cursor, *, track_ids: list[str]) -> dict[str, int]:
    if not track_ids:
        return {}
    counts = {track_id: 0 for track_id in track_ids}
    placeholders = ",".join("?" for _ in track_ids)
    if _table_exists(cursor, "Sm2TiItem_Sm2TiTrack"):
        try:
            rows = cursor.execute(
                f"""
                SELECT DbOwner AS track_id, COUNT(*) AS item_count
                FROM Sm2TiItem_Sm2TiTrack
                WHERE DbPropertyName = 'Items'
                  AND DbOwner IN ({placeholders})
                GROUP BY DbOwner
                """,
                track_ids,
            ).fetchall()
            for row in rows:
                counts[str(row["track_id"])] = int(row["item_count"] or 0)
        except sqlite3.Error:
            pass

    if _table_exists(cursor, "Sm2TiItem"):
        columns = _table_columns(cursor, "Sm2TiItem")
        for column in ("Sm2TiTrack_id", "Track"):
            if column not in columns:
                continue
            try:
                rows = cursor.execute(
                    f"""
                    SELECT {column} AS track_id, COUNT(*) AS item_count
                    FROM Sm2TiItem
                    WHERE {column} IN ({placeholders})
                    GROUP BY {column}
                    """,
                    track_ids,
                ).fetchall()
            except sqlite3.Error:
                continue
            for row in rows:
                track_id = str(row["track_id"])
                counts[track_id] = max(int(counts.get(track_id, 0)), int(row["item_count"] or 0))
    return counts


def _track_payload(row: dict[str, Any], *, index: int) -> dict[str, Any]:
    subtype = int(row.get("SubType") or 0)
    return {
        "index": int(index),
        "track_id": str(row.get("Sm2TiTrack_id") or ""),
        "name": str(row.get("UserDefinedName") or ""),
        "subtype": subtype,
        "format": FAIRLIGHT_TRACK_TYPE_BY_AUDIO_SUBTYPE.get(subtype, f"subtype:{subtype}"),
        "db_index": int(row.get("DbIndex") or 0),
    }


def _audio_subtype_channel_count(subtype: int) -> int:
    track_type = FAIRLIGHT_TRACK_TYPE_BY_AUDIO_SUBTYPE.get(int(subtype))
    if track_type:
        return FAIRLIGHT_TRACK_CHANNELS_BY_TYPE[track_type]
    if int(subtype) >= 257:
        return int(subtype) - 256
    raise ValidationError(
        "Unsupported Fairlight audio track subtype for mixer fader DB mapping.",
        details={
            "subtype": int(subtype),
            "known_subtypes": sorted(FAIRLIGHT_TRACK_TYPE_BY_AUDIO_SUBTYPE),
        },
        recoverability="manual",
    )


def _mixer_record_values(decomp: bytearray | bytes, *, record_offset: int, lane_count: int) -> list[int]:
    value_start = int(record_offset) + 12
    return [
        struct.unpack("<i", decomp[value_start + 4 * lane_index : value_start + 4 * lane_index + 4])[0]
        for lane_index in range(int(lane_count))
    ]


def _mixer_record_value_offsets(*, record_offset: int, channel_start: int, channel_count: int) -> list[int]:
    value_start = int(record_offset) + 12
    return [value_start + 4 * (int(channel_start) + lane_index) for lane_index in range(int(channel_count))]


def _mixer_record_table_candidate(
    decomp: bytearray | bytes,
    *,
    offset: int,
    min_lane_count: int,
) -> dict[str, Any] | None:
    if offset < 0 or offset + 24 > len(decomp):
        return None
    try:
        marker, param_id, lane_count = struct.unpack("<iii", decomp[offset : offset + 12])
    except struct.error:
        return None
    if marker != 1 or param_id != FAIRLIGHT_MIXER_RECORD_FADER_PARAM:
        return None
    if lane_count < min_lane_count or lane_count > 256:
        return None
    record_size = 12 + 4 * lane_count
    records: dict[int, list[int]] = {}
    record_offsets: dict[int, int] = {}
    cursor = offset
    for expected_param in (1, 2):
        if cursor + record_size > len(decomp):
            return None
        try:
            marker, param_id, current_lane_count = struct.unpack("<iii", decomp[cursor : cursor + 12])
        except struct.error:
            return None
        if marker != 1 or param_id != expected_param or current_lane_count != lane_count:
            return None
        records[param_id] = _mixer_record_values(decomp, record_offset=cursor, lane_count=lane_count)
        record_offsets[param_id] = cursor
        cursor += record_size

    # DaVinci Resolve 21 can materialize two consecutive parameter 2 records.
    # The first remains the canonical parameter 2 lane record; skip any exact
    # duplicate headers before requiring parameter 3.  Keeping this structural
    # (rather than accepting an arbitrary parameter order) avoids mistaking
    # unrelated serialized data for the mixer table.
    duplicate_param_two_count = 0
    while cursor + 12 <= len(decomp):
        try:
            marker, param_id, current_lane_count = struct.unpack("<iii", decomp[cursor : cursor + 12])
        except struct.error:
            return None
        if marker != 1 or param_id != 2 or current_lane_count != lane_count:
            break
        if cursor + record_size > len(decomp):
            return None
        duplicate_param_two_count += 1
        cursor += record_size

    # A sequence of single-lane compact records can otherwise resemble this
    # Resolve 21 table variant.  Leave it to the dedicated compact parser.
    if duplicate_param_two_count and lane_count == 1:
        return None

    if cursor + record_size > len(decomp):
        return None
    try:
        marker, param_id, current_lane_count = struct.unpack("<iii", decomp[cursor : cursor + 12])
    except struct.error:
        return None
    if marker != 1 or param_id != 3 or current_lane_count != lane_count:
        return None
    records[param_id] = _mixer_record_values(decomp, record_offset=cursor, lane_count=lane_count)
    record_offsets[param_id] = cursor
    cursor += record_size

    # The first parameter 4 record carries each input channel's horizontal
    # position. Stereo tracks can immediately follow it with another parameter
    # 4 record containing the track-level Left / Right position in int32 x10
    # units. Keep the records distinct: changing the first record merely
    # relocates the input-channel anchors and is not stereo balance/pan.
    if cursor + record_size > len(decomp):
        return None
    try:
        marker, param_id, current_lane_count = struct.unpack("<iii", decomp[cursor : cursor + 12])
    except struct.error:
        return None
    if marker != 1 or param_id != FAIRLIGHT_MIXER_RECORD_PAN_PARAM or current_lane_count != lane_count:
        return None
    records[param_id] = _mixer_record_values(decomp, record_offset=cursor, lane_count=lane_count)
    record_offsets[param_id] = cursor

    stereo_left_right_record_offset = None
    next_record_offset = cursor + record_size
    if next_record_offset + record_size <= len(decomp):
        try:
            next_marker, next_param_id, next_lane_count = struct.unpack(
                "<iii", decomp[next_record_offset : next_record_offset + 12]
            )
        except struct.error:
            pass
        else:
            if (
                next_marker == 1
                and next_param_id == FAIRLIGHT_MIXER_RECORD_PAN_PARAM
                and next_lane_count == lane_count
            ):
                stereo_left_right_record_offset = next_record_offset

    return {
        "format": "fairlight_mixer_record_table",
        "start_offset": int(offset),
        "lane_count": int(lane_count),
        "record_size": int(record_size),
        "record_offsets": record_offsets,
        "records": records,
        "stereo_left_right_record_offset": stereo_left_right_record_offset,
    }


def _find_mixer_record_table(
    decomp: bytearray | bytes,
    *,
    min_lane_count: int,
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_score = -1
    for offset in range(0, max(0, len(decomp) - 24)):
        candidate = _mixer_record_table_candidate(decomp, offset=offset, min_lane_count=min_lane_count)
        if candidate is None:
            continue
        fader_values = candidate["records"].get(FAIRLIGHT_MIXER_RECORD_FADER_PARAM, [])
        pan_values = candidate["records"].get(FAIRLIGHT_MIXER_RECORD_PAN_PARAM, [])
        fader_ok = sum(
            int(round(FAIRLIGHT_MIXER_FADER_MIN_DB * 10)) <= int(value) <= int(round(FAIRLIGHT_MIXER_FADER_MAX_DB * 10))
            for value in fader_values
        )
        pan_ok = sum(
            int(round(FAIRLIGHT_MIXER_PAN_MIN * 10)) <= int(value) <= int(round(FAIRLIGHT_MIXER_PAN_MAX * 10))
            for value in pan_values
        )
        score = fader_ok + pan_ok + int(candidate["start_offset"] > 100_000)
        if score > best_score:
            best = candidate
            best_score = score
    return best


def _mixer_lane_rows(
    cursor: sqlite3.Cursor,
    rows: list[dict[str, Any]],
    *,
    sequence: str,
    lane_count: int,
) -> tuple[list[dict[str, Any]], str]:
    total_channel_count = sum(_audio_subtype_channel_count(int(row.get("SubType") or 0)) for row in rows)
    if lane_count >= total_channel_count:
        return rows, "all_db_audio_tracks"

    track_ids = [str(row.get("Sm2TiTrack_id") or "") for row in rows]
    item_counts = _fetch_audio_track_item_counts(cursor, track_ids=track_ids)
    materialized_rows = [
        {**row, "item_count": int(item_counts.get(str(row.get("Sm2TiTrack_id") or ""), 0))}
        for row in rows
        if int(item_counts.get(str(row.get("Sm2TiTrack_id") or ""), 0)) > 0
    ]
    materialized_channel_count = sum(
        _audio_subtype_channel_count(int(row.get("SubType") or 0)) for row in materialized_rows
    )
    if materialized_rows and lane_count >= materialized_channel_count:
        return materialized_rows, "materialized_audio_item_tracks"
    return rows, "all_db_audio_tracks"


def validate_mixer_fader_level(level_db: float) -> float:
    try:
        normalized = float(level_db)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Fairlight mixer fader level must be a finite dB value.",
            details={"level_db": level_db},
            recoverability="not_applicable",
        ) from exc
    if not math.isfinite(normalized):
        raise ValidationError(
            "Fairlight mixer fader level must be a finite dB value.",
            details={"level_db": level_db},
            recoverability="not_applicable",
        )
    if normalized < FAIRLIGHT_MIXER_FADER_MIN_DB or normalized > FAIRLIGHT_MIXER_FADER_MAX_DB:
        raise ValidationError(
            "Fairlight mixer fader level is outside the supported DaVinci Resolve fader range.",
            details={
                "level_db": normalized,
                "min_db": FAIRLIGHT_MIXER_FADER_MIN_DB,
                "max_db": FAIRLIGHT_MIXER_FADER_MAX_DB,
            },
            recoverability="not_applicable",
        )
    return round(normalized, 1)


def _mixer_fader_raw(level_db: float) -> int:
    return int(round(validate_mixer_fader_level(level_db) * 10))


def _validate_mixer_fader_raw_values(raw_values: list[int], *, state_context: dict[str, Any]) -> None:
    min_raw = int(round(FAIRLIGHT_MIXER_FADER_MIN_DB * 10))
    max_raw = int(round(FAIRLIGHT_MIXER_FADER_MAX_DB * 10))
    invalid = [raw for raw in raw_values if int(raw) < min_raw or int(raw) > max_raw]
    if invalid:
        raise APICallFailed(
            "Fairlight mixer fader DB readback produced out-of-range lane values.",
            details={
                **state_context,
                "raw_values": raw_values,
                "invalid_raw_values": invalid,
                "allowed_raw_range": [min_raw, max_raw],
                "allowed_level_db_range": [FAIRLIGHT_MIXER_FADER_MIN_DB, FAIRLIGHT_MIXER_FADER_MAX_DB],
                "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
                "storage": "channel_lane_int32_x10",
                "reason": "The mapped DB offsets do not look like valid Fairlight fader lanes for this timeline.",
            },
            recoverability="manual",
        )


def validate_mixer_pan_value(pan: float) -> float:
    try:
        normalized = float(pan)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Fairlight mixer pan must be a finite value.",
            details={"pan": pan, "min_value": FAIRLIGHT_MIXER_PAN_MIN, "max_value": FAIRLIGHT_MIXER_PAN_MAX},
            recoverability="not_applicable",
        ) from exc
    if not math.isfinite(normalized):
        raise ValidationError(
            "Fairlight mixer pan must be a finite value.",
            details={"pan": pan, "min_value": FAIRLIGHT_MIXER_PAN_MIN, "max_value": FAIRLIGHT_MIXER_PAN_MAX},
            recoverability="not_applicable",
        )
    if normalized < FAIRLIGHT_MIXER_PAN_MIN or normalized > FAIRLIGHT_MIXER_PAN_MAX:
        raise ValidationError(
            f"Fairlight mixer pan must be between {FAIRLIGHT_MIXER_PAN_MIN:g} and {FAIRLIGHT_MIXER_PAN_MAX:g}.",
            details={"pan": normalized, "min_value": FAIRLIGHT_MIXER_PAN_MIN, "max_value": FAIRLIGHT_MIXER_PAN_MAX},
            recoverability="not_applicable",
        )
    return round(normalized, 1)


def _mixer_pan_raw(pan: float) -> int:
    return int(round(validate_mixer_pan_value(pan) * 10))


def _decode_mixer_stereo_pan_values(raw_values: list[int]) -> tuple[int, float]:
    if not raw_values:
        raise APICallFailed("Fairlight stereo Left / Right record has no channel values.")
    if any(raw < -1000 or raw > 1000 for raw in raw_values):
        raise APICallFailed(
            "Fairlight stereo Left / Right DB readback produced out-of-range values.",
            details={
                "raw_values": raw_values,
            },
            recoverability="manual",
        )
    primary_x10 = raw_values[0]
    if any(raw != primary_x10 for raw in raw_values[1:]):
        raise APICallFailed(
            "Fairlight stereo Left / Right channel records do not describe one track position.",
            details={
                "raw_values": raw_values,
            },
            recoverability="manual",
        )
    pan_raw = int(primary_x10)
    return pan_raw, pan_raw / 10.0


def _validate_mixer_pan_raw_values(raw_values: list[int], *, state_context: dict[str, Any]) -> None:
    min_raw = int(round(FAIRLIGHT_MIXER_PAN_MIN * 10))
    max_raw = int(round(FAIRLIGHT_MIXER_PAN_MAX * 10))
    invalid = [raw for raw in raw_values if int(raw) < min_raw or int(raw) > max_raw]
    if invalid:
        raise APICallFailed(
            "Fairlight mixer pan DB readback produced out-of-range lane values.",
            details={
                **state_context,
                "raw_values": raw_values,
                "invalid_raw_values": invalid,
                "allowed_raw_range": [min_raw, max_raw],
                "allowed_pan_range": [FAIRLIGHT_MIXER_PAN_MIN, FAIRLIGHT_MIXER_PAN_MAX],
                "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
                "storage": "channel_lane_pan_int32_x10",
                "reason": "The mapped DB offsets do not look like valid Fairlight pan lanes for this timeline.",
            },
            recoverability="manual",
        )


def _fetch_sequence_fields_blob(cursor: sqlite3.Cursor, *, sequence: str) -> bytes:
    columns = _table_columns(cursor, "Sm2Sequence")
    where = "Sm2Sequence_id = ?" if "Sm2Sequence_id" in columns else None
    row = None
    if where is not None:
        row = cursor.execute(
            f"SELECT FieldsBlob FROM Sm2Sequence WHERE {where}",
            (sequence,),
        ).fetchone()
    if row is None:
        rows = cursor.execute("SELECT FieldsBlob FROM Sm2Sequence").fetchall()
        if len(rows) == 1:
            row = rows[0]
    if row is None:
        raise APICallFailed(
            "Fairlight mixer model was not found for the active timeline.",
            details={"timeline_sequence": sequence, "table": "Sm2Sequence"},
            recoverability="manual",
        )
    blob = row["FieldsBlob"] if hasattr(row, "keys") else row[0]
    if not blob:
        raise APICallFailed(
            "Fairlight mixer model blob is empty for the active timeline.",
            details={"timeline_sequence": sequence, "table": "Sm2Sequence", "column": "FieldsBlob"},
            recoverability="manual",
        )
    return bytes(blob)


def _decode_fairlight_model(seq_blob: bytes) -> tuple[bytearray, int, int, bytes, int]:
    zlib_idx, size_field_offset, _ = dynamics_db._find_zlib_in_seq(seq_blob)
    dobj = zlib.decompressobj()
    decomp = bytearray(dobj.decompress(seq_blob[zlib_idx:]))
    unused = dobj.unused_data
    compressed_size = len(seq_blob[zlib_idx:]) - len(unused)
    size_field = struct.unpack(">I", seq_blob[size_field_offset : size_field_offset + 4])[0]
    overhead = size_field - compressed_size
    return decomp, zlib_idx, size_field_offset, unused, overhead


def _encode_fairlight_model(
    *,
    seq_blob: bytes,
    decomp: bytes,
    zlib_idx: int,
    size_field_offset: int,
    unused: bytes,
    overhead: int,
) -> bytes:
    seq = bytearray(seq_blob)
    compressor = zlib.compressobj(
        dynamics_db._ZLIB_LEVEL,
        zlib.DEFLATED,
        15,
        dynamics_db._ZLIB_MEMLEVEL,
        dynamics_db._ZLIB_STRATEGY,
    )
    compressed = compressor.compress(bytes(decomp)) + compressor.flush()
    struct.pack_into(">I", seq, size_field_offset, len(compressed) + overhead)
    return bytes(seq[:zlib_idx]) + compressed + unused


def _mixer_fader_target(
    rows: list[dict[str, Any]],
    *,
    index: int,
) -> dict[str, Any]:
    _validate_audio_track_db_index(rows, index)
    channel_offset = 0
    for row_index, row in enumerate(rows, start=1):
        subtype = int(row.get("SubType") or 0)
        channel_count = _audio_subtype_channel_count(subtype)
        if row_index == index:
            offsets = [
                FAIRLIGHT_MIXER_FADER_BASE_OFFSET + 4 * (channel_offset + lane_index)
                for lane_index in range(channel_count)
            ]
            track = _track_payload(row, index=row_index)
            return {
                "track": track,
                "channel_count": channel_count,
                "channel_start": channel_offset,
                "offsets": offsets,
            }
        channel_offset += channel_count
    raise AssertionError("validated Fairlight track index was not found")


def _mixer_pan_target(
    rows: list[dict[str, Any]],
    *,
    index: int,
) -> dict[str, Any]:
    _validate_audio_track_db_index(rows, index)
    channel_offset = 0
    for row_index, row in enumerate(rows, start=1):
        subtype = int(row.get("SubType") or 0)
        channel_count = _audio_subtype_channel_count(subtype)
        if row_index == index:
            offsets = [
                FAIRLIGHT_MIXER_PAN_BASE_OFFSET + 4 * (channel_offset + lane_index)
                for lane_index in range(channel_count)
            ]
            track = _track_payload(row, index=row_index)
            return {
                "track": track,
                "channel_count": channel_count,
                "channel_start": channel_offset,
                "offsets": offsets,
            }
        channel_offset += channel_count
    raise AssertionError("validated Fairlight track index was not found")


def _mixer_target_from_record_table(
    cursor: sqlite3.Cursor,
    rows: list[dict[str, Any]],
    *,
    sequence: str,
    index: int,
    decomp: bytearray | bytes,
    param_id: int,
) -> dict[str, Any] | None:
    full_target = _mixer_fader_target(rows, index=index)
    table = _find_mixer_record_table(decomp, min_lane_count=1)
    if table is None or param_id not in table["record_offsets"]:
        return None

    lane_rows, lane_scope = _mixer_lane_rows(
        cursor,
        rows,
        sequence=sequence,
        lane_count=int(table["lane_count"]),
    )
    requested_track_id = str(full_target["track"].get("track_id") or "")
    lane_start = 0
    lane_row: dict[str, Any] | None = None
    lane_public_index = None
    for row_index, row in enumerate(lane_rows, start=1):
        subtype = int(row.get("SubType") or 0)
        channel_count = _audio_subtype_channel_count(subtype)
        if str(row.get("Sm2TiTrack_id") or "") == requested_track_id:
            lane_row = row
            lane_public_index = row_index
            break
        lane_start += channel_count
    if lane_row is None:
        return {
            **full_target,
            "record_table": table,
            "record_table_lane_scope": lane_scope,
            "record_table_blocker": "target_track_not_present_in_materialized_mixer_lanes",
        }
    lane_channel_count = _audio_subtype_channel_count(int(lane_row.get("SubType") or 0))
    if int(lane_start) + int(lane_channel_count) > int(table["lane_count"]):
        return {
            **full_target,
            "record_table": table,
            "record_table_lane_scope": lane_scope,
            "record_table_blocker": "target_track_lanes_exceed_record_table_lane_count",
        }

    offsets = _mixer_record_value_offsets(
        record_offset=int(table["record_offsets"][param_id]),
        channel_start=int(lane_start),
        channel_count=int(lane_channel_count),
    )
    stereo_left_right_record_offset = (
        table.get("stereo_left_right_record_offset")
        if int(param_id) == FAIRLIGHT_MIXER_RECORD_PAN_PARAM and int(lane_channel_count) == 2
        else None
    )
    stereo_left_right_offsets = (
        _mixer_record_value_offsets(
            record_offset=int(stereo_left_right_record_offset),
            channel_start=int(lane_start),
            channel_count=int(lane_channel_count),
        )
        if stereo_left_right_record_offset is not None
        else None
    )
    return {
        **full_target,
        "db_channel_start": full_target["channel_start"],
        "channel_start": int(lane_start),
        "offsets": offsets,
        "record_table": table,
        "record_table_lane_scope": lane_scope,
        "record_table_lane_index": lane_public_index,
        "record_table_channel_start": int(lane_start),
        "record_table_param_id": int(param_id),
        "record_table_record_offset": int(table["record_offsets"][param_id]),
        "stereo_left_right_record_offset": stereo_left_right_record_offset,
        "stereo_left_right_offsets": stereo_left_right_offsets,
    }


def _find_mixer_compact_param_run(
    decomp: bytearray | bytes,
    *,
    param_id: int,
    min_lane_count: int,
    min_value: int,
    max_value: int,
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_score = -1
    offset = 0
    while offset + 16 <= len(decomp):
        try:
            marker, current_param_id, current_lane_count, value = struct.unpack("<iiii", decomp[offset : offset + 16])
        except struct.error:
            break
        if marker != 1 or current_param_id != int(param_id) or current_lane_count != 1:
            offset += 1
            continue
        start_offset = offset
        value_offsets: list[int] = []
        values: list[int] = []
        while offset + 16 <= len(decomp):
            marker, current_param_id, current_lane_count, value = struct.unpack("<iiii", decomp[offset : offset + 16])
            if marker != 1 or current_param_id != int(param_id) or current_lane_count != 1:
                break
            value_offsets.append(offset + 12)
            values.append(int(value))
            offset += 16
        valid_count = sum(int(min_value) <= int(item) <= int(max_value) for item in values)
        if len(values) >= int(min_lane_count) and valid_count == len(values):
            score = valid_count + int(start_offset > 100_000)
            if score > best_score:
                best = {
                    "format": "fairlight_mixer_compact_param_records",
                    "start_offset": int(start_offset),
                    "lane_count": len(values),
                    "param_id": int(param_id),
                    "record_size": 16,
                    "value_offsets": value_offsets,
                    "values": values,
                }
                best_score = score
        offset += 1
    return best


def _mixer_target_from_compact_param_records(
    cursor: sqlite3.Cursor,
    rows: list[dict[str, Any]],
    *,
    sequence: str,
    index: int,
    decomp: bytearray | bytes,
    param_id: int,
    min_value: int,
    max_value: int,
) -> dict[str, Any] | None:
    full_target = _mixer_fader_target(rows, index=index)
    compact = _find_mixer_compact_param_run(
        decomp,
        param_id=param_id,
        min_lane_count=1,
        min_value=min_value,
        max_value=max_value,
    )
    if compact is None:
        return None
    lane_rows, lane_scope = _mixer_lane_rows(
        cursor,
        rows,
        sequence=sequence,
        lane_count=int(compact["lane_count"]),
    )
    requested_track_id = str(full_target["track"].get("track_id") or "")
    lane_start = 0
    lane_row: dict[str, Any] | None = None
    lane_public_index = None
    for row_index, row in enumerate(lane_rows, start=1):
        subtype = int(row.get("SubType") or 0)
        channel_count = _audio_subtype_channel_count(subtype)
        if str(row.get("Sm2TiTrack_id") or "") == requested_track_id:
            lane_row = row
            lane_public_index = row_index
            break
        lane_start += channel_count
    if lane_row is None:
        return {
            **full_target,
            "compact_param_records": compact,
            "compact_param_lane_scope": lane_scope,
            "compact_param_blocker": "target_track_not_present_in_compact_param_lanes",
        }
    lane_channel_count = _audio_subtype_channel_count(int(lane_row.get("SubType") or 0))
    if int(lane_start) + int(lane_channel_count) > int(compact["lane_count"]):
        return {
            **full_target,
            "compact_param_records": compact,
            "compact_param_lane_scope": lane_scope,
            "compact_param_blocker": "target_track_lanes_exceed_compact_param_lane_count",
        }
    return {
        **full_target,
        "db_channel_start": full_target["channel_start"],
        "channel_start": int(lane_start),
        "offsets": list(compact["value_offsets"])[int(lane_start) : int(lane_start) + int(lane_channel_count)],
        "compact_param_records": compact,
        "compact_param_lane_scope": lane_scope,
        "compact_param_lane_index": lane_public_index,
        "compact_param_channel_start": int(lane_start),
        "compact_param_id": int(param_id),
        "compact_param_start_offset": int(compact["start_offset"]),
    }


def _read_mixer_fader_state_from_cursor(
    cursor: sqlite3.Cursor,
    *,
    timeline_name: str,
    index: int,
) -> dict[str, Any]:
    sequence = _fetch_timeline_sequence(cursor, timeline_name)
    rows = _fetch_audio_track_rows(cursor, sequence=sequence)
    seq_blob = _fetch_sequence_fields_blob(cursor, sequence=sequence)
    decomp, _, _, _, _ = _decode_fairlight_model(seq_blob)
    target = _mixer_target_from_record_table(
        cursor,
        rows,
        sequence=sequence,
        index=index,
        decomp=decomp,
        param_id=FAIRLIGHT_MIXER_RECORD_FADER_PARAM,
    )
    target_source = "record_table"
    if target is None:
        target = _mixer_fader_target(rows, index=index)
        target_source = "fixed_offset"
    elif target.get("record_table_blocker"):
        raise APICallFailed(
            "Fairlight mixer record table does not contain the requested track lanes.",
            details={
                "timeline_name": timeline_name,
                "timeline_sequence": sequence,
                "track": target["track"],
                "record_table_lane_scope": target.get("record_table_lane_scope"),
                "record_table_lane_count": (target.get("record_table") or {}).get("lane_count"),
                "record_table_blocker": target.get("record_table_blocker"),
                "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
            },
            recoverability="manual",
        )
    max_offset = max(target["offsets"]) + 4
    if len(decomp) < max_offset:
        raise APICallFailed(
            "Fairlight mixer model is too small for the mapped fader channel lanes.",
            details={
                "timeline_name": timeline_name,
                "timeline_sequence": sequence,
                "required_bytes": max_offset,
                "actual_bytes": len(decomp),
                "base_offset": FAIRLIGHT_MIXER_FADER_BASE_OFFSET,
            },
            recoverability="manual",
        )
    raw_values = [struct.unpack("<i", decomp[offset : offset + 4])[0] for offset in target["offsets"]]
    _validate_mixer_fader_raw_values(
        raw_values,
        state_context={
            "timeline_name": timeline_name,
            "timeline_sequence": sequence,
            "track": target["track"],
            "channel_count": target["channel_count"],
            "channel_offsets": target["offsets"],
            "base_offset": target.get("record_table_record_offset", FAIRLIGHT_MIXER_FADER_BASE_OFFSET),
            "offset_source": target_source,
        },
    )
    levels_db = [raw / 10.0 for raw in raw_values]
    common_level = levels_db[0] if levels_db and all(level == levels_db[0] for level in levels_db) else None
    return {
        "action": "fairlight.mixer.fader.read",
        "timeline_name": timeline_name,
        "timeline_sequence": sequence,
        "track": target["track"],
        "channel_count": target["channel_count"],
        "channel_start": target["channel_start"],
        "channel_offsets": target["offsets"],
        "raw_values": raw_values,
        "channel_levels_db": levels_db,
        "level_db": common_level,
        "route": "db_native",
        "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
        "storage": "fairlight_mixer_record_table_int32_x10" if target_source == "record_table" else "channel_lane_int32_x10",
        "offset_source": target_source,
        "record_table": {
            "lane_scope": target.get("record_table_lane_scope"),
            "lane_count": (target.get("record_table") or {}).get("lane_count"),
            "param_id": target.get("record_table_param_id"),
            "record_offset": target.get("record_table_record_offset"),
            "lane_index": target.get("record_table_lane_index"),
            "channel_start": target.get("record_table_channel_start"),
        }
        if target_source == "record_table"
        else None,
        "set_supported": True,
        "set_scope": "all_track_channel_lanes_equal_level",
        "verified_set_scope": "valid_track_channel_fader_lanes",
        "set_command": f"cutagent fairlight mixer fader --track {int(index)} --level <db> --json",
        "set_precondition": "Current timeline must expose in-range Fairlight fader lane values for every channel on the target track.",
    }


def read_audio_track_fader_db(conn, *, index: int) -> dict[str, Any]:
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed("No active timeline is available for Fairlight mixer fader read.")
    current_database = db_session.resolve_current_disk_project_db(
        conn,
        allow_project_name_inference=True,
    )
    connection = sqlite3.connect(str(current_database["project_db_path"]), timeout=5.0)
    connection.row_factory = sqlite3.Row
    try:
        state = _read_mixer_fader_state_from_cursor(
            connection.cursor(),
            timeline_name=timeline_name,
            index=int(index),
        )
    finally:
        connection.close()
    return {
        **state,
        "project_db_path": str(current_database["project_db_path"]),
        "read_consistency": "disk_project_db",
        "note": "Disk DB reads may lag unsaved GUI-only fader edits until DaVinci Resolve auto-saves.",
    }


def _read_mixer_pan_state_from_cursor(
    cursor: sqlite3.Cursor,
    *,
    timeline_name: str,
    index: int,
) -> dict[str, Any]:
    sequence = _fetch_timeline_sequence(cursor, timeline_name)
    rows = _fetch_audio_track_rows(cursor, sequence=sequence)
    seq_blob = _fetch_sequence_fields_blob(cursor, sequence=sequence)
    decomp, _, _, _, _ = _decode_fairlight_model(seq_blob)
    target = _mixer_target_from_record_table(
        cursor,
        rows,
        sequence=sequence,
        index=index,
        decomp=decomp,
        param_id=FAIRLIGHT_MIXER_RECORD_PAN_PARAM,
    )
    target_source = "record_table"
    if target is None:
        target = _mixer_target_from_compact_param_records(
            cursor,
            rows,
            sequence=sequence,
            index=index,
            decomp=decomp,
            param_id=FAIRLIGHT_MIXER_RECORD_PAN_PARAM,
            min_value=int(round(FAIRLIGHT_MIXER_PAN_MIN * 10)),
            max_value=int(round(FAIRLIGHT_MIXER_PAN_MAX * 10)),
        )
        target_source = "compact_param_records"
    if target is None:
        target = _mixer_pan_target(rows, index=index)
        target_source = "fixed_offset"
    elif target.get("record_table_blocker"):
        raise CapabilityNegotiationFailed(
            "Fairlight mixer record table does not contain the requested track lanes.",
            details={
                "capability_id": "fairlight.pan",
                "timeline_name": timeline_name,
                "timeline_sequence": sequence,
                "track": target["track"],
                "record_table_lane_scope": target.get("record_table_lane_scope"),
                "record_table_lane_count": (target.get("record_table") or {}).get("lane_count"),
                "record_table_blocker": target.get("record_table_blocker"),
                "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
                "supported_scope": "mono 2D pan on materialized tracks with present in-range mixer pan lanes",
            },
            recoverability="manual",
        )
    elif target.get("compact_param_blocker"):
        raise CapabilityNegotiationFailed(
            "Fairlight mixer compact pan records do not contain the requested track lanes.",
            details={
                "capability_id": "fairlight.pan",
                "timeline_name": timeline_name,
                "timeline_sequence": sequence,
                "track": target["track"],
                "compact_param_lane_scope": target.get("compact_param_lane_scope"),
                "compact_param_lane_count": (target.get("compact_param_records") or {}).get("lane_count"),
                "compact_param_blocker": target.get("compact_param_blocker"),
                "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
                "supported_scope": "mono 2D pan on materialized tracks with present in-range mixer pan lanes",
            },
            recoverability="manual",
        )
    max_offset = max(target["offsets"]) + 4
    if len(decomp) < max_offset:
        raise APICallFailed(
            "Fairlight mixer model is too small for the mapped pan channel lanes.",
            details={
                "timeline_name": timeline_name,
                "timeline_sequence": sequence,
                "required_bytes": max_offset,
                "actual_bytes": len(decomp),
                "base_offset": FAIRLIGHT_MIXER_PAN_BASE_OFFSET,
            },
            recoverability="manual",
        )
    raw_values = [struct.unpack("<i", decomp[offset : offset + 4])[0] for offset in target["offsets"]]
    _validate_mixer_pan_raw_values(
        raw_values,
        state_context={
            "timeline_name": timeline_name,
            "timeline_sequence": sequence,
            "track": target["track"],
            "channel_count": target["channel_count"],
            "channel_offsets": target["offsets"],
            "base_offset": target.get(
                "record_table_record_offset",
                target.get("compact_param_start_offset", FAIRLIGHT_MIXER_PAN_BASE_OFFSET),
            ),
            "offset_source": target_source,
        },
    )
    channel_pan_values = [raw / 10.0 for raw in raw_values]
    stereo_left_right_offsets = target.get("stereo_left_right_offsets")
    stereo_left_right_raw_values = (
        [struct.unpack("<i", decomp[offset : offset + 4])[0] for offset in stereo_left_right_offsets]
        if stereo_left_right_offsets
        else None
    )
    if int(target["channel_count"]) == 1:
        pan_raw_value = raw_values[0]
        common_pan = channel_pan_values[0]
        set_scope = "mono_track_2d_pan"
    elif int(target["channel_count"]) == 2 and stereo_left_right_raw_values is not None:
        pan_raw_value, common_pan = _decode_mixer_stereo_pan_values(stereo_left_right_raw_values)
        set_scope = "stereo_track_left_right"
    else:
        pan_raw_value = None
        common_pan = None
        set_scope = None
    set_supported = set_scope is not None
    return {
        "action": "fairlight.mixer.pan.read",
        "timeline_name": timeline_name,
        "timeline_sequence": sequence,
        "track": target["track"],
        "channel_count": target["channel_count"],
        "channel_start": target["channel_start"],
        "channel_offsets": target["offsets"],
        "raw_values": raw_values,
        "channel_pan_values": channel_pan_values,
        "pan": common_pan,
        "pan_raw_value": pan_raw_value,
        "stereo_left_right_raw_values": stereo_left_right_raw_values,
        "stereo_left_right_offsets": stereo_left_right_offsets,
        "route": "db_native",
        "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
        "storage": (
            "fairlight_mixer_record_table_pan_int32_x10"
            if target_source == "record_table"
            else "fairlight_mixer_compact_param_records_pan_int32_x10"
            if target_source == "compact_param_records"
            else "channel_lane_pan_int32_x10"
        ),
        "offset_source": target_source,
        "record_table": {
            "lane_scope": target.get("record_table_lane_scope"),
            "lane_count": (target.get("record_table") or {}).get("lane_count"),
            "param_id": target.get("record_table_param_id"),
            "record_offset": target.get("record_table_record_offset"),
            "stereo_left_right_record_offset": target.get("stereo_left_right_record_offset"),
            "lane_index": target.get("record_table_lane_index"),
            "channel_start": target.get("record_table_channel_start"),
        }
        if target_source == "record_table"
        else None,
        "compact_param_records": {
            "lane_scope": target.get("compact_param_lane_scope"),
            "lane_count": (target.get("compact_param_records") or {}).get("lane_count"),
            "param_id": target.get("compact_param_id"),
            "start_offset": target.get("compact_param_start_offset"),
            "lane_index": target.get("compact_param_lane_index"),
            "channel_start": target.get("compact_param_channel_start"),
        }
        if target_source == "compact_param_records"
        else None,
        "set_supported": set_supported,
        "verified_set_scope": set_scope or "mono_track_2d_pan",
        "set_command": f"cutagent fairlight mixer pan --track {int(index)} --pan <value> --json" if set_supported else None,
        "set_blocker": None
        if set_supported
        else "Fairlight mixer pan DB write requires a mono channel lane or the verified stereo Left / Right record; surround, adaptive, and 3D panner semantics remain unsupported.",
    }


def read_audio_track_pan_db(conn, *, index: int) -> dict[str, Any]:
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed("No active timeline is available for Fairlight mixer pan read.")
    current_database = db_session.resolve_current_disk_project_db(
        conn,
        allow_project_name_inference=True,
    )
    connection = sqlite3.connect(str(current_database["project_db_path"]), timeout=5.0)
    connection.row_factory = sqlite3.Row
    try:
        state = _read_mixer_pan_state_from_cursor(
            connection.cursor(),
            timeline_name=timeline_name,
            index=int(index),
        )
    finally:
        connection.close()
    return {
        **state,
        "project_db_path": str(current_database["project_db_path"]),
        "read_consistency": "disk_project_db",
        "note": "Disk DB reads may lag unsaved GUI-only pan edits until DaVinci Resolve auto-saves.",
    }


def _mixer_pan_set_writer(
    *,
    timeline_name: str,
    index: int,
    pan: float,
):
    target_raw = _mixer_pan_raw(pan)

    def _writer(connection: sqlite3.Connection, cursor: sqlite3.Cursor, session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        state = _read_mixer_pan_state_from_cursor(
            cursor,
            timeline_name=timeline_name,
            index=index,
        )
        if not state["set_supported"]:
            raise CapabilityNegotiationFailed(
                "Fairlight mixer pan DB write does not expose a verified track-level position for this track format.",
                details={
                    "capability_id": "fairlight.pan",
                    "requested": {"track": int(index), "pan": target_raw / 10.0},
                    "track": state["track"],
                    "channel_count": state["channel_count"],
                    "channel_pan_values": state["channel_pan_values"],
                    "verified_set_scope": "mono_track_2d_pan_and_stereo_track_left_right",
                    "stereo_write_blocker_evidence": FAIRLIGHT_MIXER_STEREO_PAN_WRITE_BLOCKER_EVIDENCE,
                    "api_note": "Mono 2D pan and stereo Left / Right are verified. Surround, adaptive, and 3D panner semantics require separate GUI/render mapping.",
                },
            )
        seq_blob = _fetch_sequence_fields_blob(cursor, sequence=str(state["timeline_sequence"]))
        decomp, zlib_idx, size_field_offset, unused, overhead = _decode_fairlight_model(seq_blob)
        if state["verified_set_scope"] == "stereo_track_left_right":
            write_offsets = list(state["stereo_left_right_offsets"])
            write_raw_value = target_raw
            write_raw_values = [write_raw_value] * len(write_offsets)
            previous_raw = list(state["stereo_left_right_raw_values"])
        else:
            write_offsets = list(state["channel_offsets"])
            write_raw_value = target_raw
            write_raw_values = [write_raw_value] * len(write_offsets)
            previous_raw = list(state["raw_values"])
        changed = state.get("pan_raw_value") != target_raw
        for offset, raw_value in zip(write_offsets, write_raw_values):
            struct.pack_into("<i", decomp, int(offset), raw_value)
        new_seq = _encode_fairlight_model(
            seq_blob=seq_blob,
            decomp=decomp,
            zlib_idx=zlib_idx,
            size_field_offset=size_field_offset,
            unused=unused,
            overhead=overhead,
        )
        cursor.execute(
            "UPDATE Sm2Sequence SET FieldsBlob = ? WHERE Sm2Sequence_id = ?",
            (new_seq, str(state["timeline_sequence"])),
        )
        if cursor.rowcount == 0:
            cursor.execute("UPDATE Sm2Sequence SET FieldsBlob = ?", (new_seq,))
        return {
            "action": "fairlight.mixer.pan",
            "changed": changed,
            "timeline_name": timeline_name,
            "timeline_sequence": state["timeline_sequence"],
            "track": state["track"],
            "pan": target_raw / 10.0,
            "raw_value": target_raw,
            "stored_raw_value": write_raw_value,
            "stored_raw_values": write_raw_values,
            "previous_raw_values": previous_raw,
            "previous_channel_pan_values": state["channel_pan_values"],
            "channel_count": state["channel_count"],
            "channel_start": state["channel_start"],
            "channel_offsets": state["channel_offsets"],
            "write_offsets": write_offsets,
            "stereo_left_right_offsets": state.get("stereo_left_right_offsets"),
            "route": "db_native",
            "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
            "storage": state.get("storage", "channel_lane_pan_int32_x10"),
            "offset_source": state.get("offset_source"),
            "record_table": state.get("record_table"),
            "set_supported": True,
            "verified_set_scope": state["verified_set_scope"],
        }

    return _writer


def _verify_mixer_pan_set(*, timeline_name: str, index: int, raw_value: int):
    def _verifier(conn, mutation_result: dict[str, Any], session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        connection = sqlite3.connect(session.project_db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            state = _read_mixer_pan_state_from_cursor(
                connection.cursor(),
                timeline_name=timeline_name,
                index=index,
            )
        finally:
            connection.close()
        actual_raw_value = state.get("pan_raw_value")
        raw_values = (
            list(state["stereo_left_right_raw_values"])
            if state.get("verified_set_scope") == "stereo_track_left_right"
            else list(state["raw_values"])
        )
        ok = actual_raw_value == raw_value
        verification = {
            "status": "verified" if ok else "failed",
            "timeline_name": timeline_name,
            "track_index": int(index),
            "expected_raw_value": raw_value,
            "actual_raw_values": raw_values,
            "actual_pan_raw_value": actual_raw_value,
            "actual_pan": state.get("pan"),
            "actual_channel_pan_values": state["channel_pan_values"],
            "db_blob": state["db_blob"],
            "checks": [
                {"name": "track_pan_position", "ok": ok},
            ],
            "native_api_readback": None,
            "native_api_note": "DaVinci Resolve does not expose Fairlight mixer pan readback through the scripting API; verification reads the reopened Disk DB Fairlight model.",
        }
        if not ok:
            raise APICallFailed(
                "Fairlight mixer pan verification failed after project reopen.",
                details={"verification": verification},
                recoverability="manual",
            )
        return verification

    return _verifier


def set_audio_track_pan_db(conn, *, index: int, pan: float) -> dict[str, Any]:
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed("No active timeline is available for Fairlight mixer pan set.")
    raw_value = _mixer_pan_raw(pan)
    return db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Fairlight mixer pan set",
        writer=_mixer_pan_set_writer(
            timeline_name=timeline_name,
            index=int(index),
            pan=pan,
        ),
        verifier=_verify_mixer_pan_set(
            timeline_name=timeline_name,
            index=int(index),
            raw_value=raw_value,
        ),
        allow_project_name_inference=True,
    )


def _mixer_fader_set_writer(
    *,
    timeline_name: str,
    index: int,
    level_db: float,
):
    target_raw = _mixer_fader_raw(level_db)

    def _writer(connection: sqlite3.Connection, cursor: sqlite3.Cursor, session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        state = _read_mixer_fader_state_from_cursor(
            cursor,
            timeline_name=timeline_name,
            index=index,
        )
        seq_blob = _fetch_sequence_fields_blob(cursor, sequence=str(state["timeline_sequence"]))
        decomp, zlib_idx, size_field_offset, unused, overhead = _decode_fairlight_model(seq_blob)
        previous_raw = list(state["raw_values"])
        changed = any(raw != target_raw for raw in previous_raw)
        for offset in state["channel_offsets"]:
            struct.pack_into("<i", decomp, int(offset), target_raw)
        new_seq = _encode_fairlight_model(
            seq_blob=seq_blob,
            decomp=decomp,
            zlib_idx=zlib_idx,
            size_field_offset=size_field_offset,
            unused=unused,
            overhead=overhead,
        )
        cursor.execute(
            "UPDATE Sm2Sequence SET FieldsBlob = ? WHERE Sm2Sequence_id = ?",
            (new_seq, str(state["timeline_sequence"])),
        )
        if cursor.rowcount == 0:
            cursor.execute("UPDATE Sm2Sequence SET FieldsBlob = ?", (new_seq,))
        return {
            "action": "fairlight.mixer.fader",
            "changed": changed,
            "timeline_name": timeline_name,
            "timeline_sequence": state["timeline_sequence"],
            "track": state["track"],
            "level_db": target_raw / 10.0,
            "raw_value": target_raw,
            "previous_raw_values": previous_raw,
            "previous_channel_levels_db": state["channel_levels_db"],
            "channel_count": state["channel_count"],
            "channel_start": state["channel_start"],
            "channel_offsets": state["channel_offsets"],
            "route": "db_native",
            "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
            "storage": state.get("storage", "channel_lane_int32_x10"),
            "offset_source": state.get("offset_source"),
            "record_table": state.get("record_table"),
            "set_supported": True,
            "set_scope": "all_track_channel_lanes_equal_level",
            "verified_set_scope": "valid_track_channel_fader_lanes",
        }

    return _writer


def _verify_mixer_fader_set(*, timeline_name: str, index: int, raw_value: int):
    def _verifier(conn, mutation_result: dict[str, Any], session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        connection = sqlite3.connect(session.project_db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            state = _read_mixer_fader_state_from_cursor(
                connection.cursor(),
                timeline_name=timeline_name,
                index=index,
            )
        finally:
            connection.close()
        raw_values = list(state["raw_values"])
        ok = bool(raw_values and all(raw == raw_value for raw in raw_values))
        verification = {
            "status": "verified" if ok else "failed",
            "timeline_name": timeline_name,
            "track_index": int(index),
            "expected_raw_value": raw_value,
            "actual_raw_values": raw_values,
            "actual_channel_levels_db": state["channel_levels_db"],
            "db_blob": state["db_blob"],
            "checks": [
                {"name": "channel_lane_raw_values", "ok": ok},
            ],
            "native_api_readback": None,
            "native_api_note": "DaVinci Resolve does not expose Fairlight mixer fader readback through the scripting API; verification reads the reopened Disk DB Fairlight model.",
        }
        if not ok:
            raise APICallFailed(
                "Fairlight mixer fader verification failed after project reopen.",
                details={"verification": verification},
                recoverability="manual",
            )
        return verification

    return _verifier


def set_audio_track_fader_db(conn, *, index: int, level_db: float) -> dict[str, Any]:
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed("No active timeline is available for Fairlight mixer fader set.")
    raw_value = _mixer_fader_raw(level_db)
    return db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Fairlight mixer fader set",
        writer=_mixer_fader_set_writer(
            timeline_name=timeline_name,
            index=int(index),
            level_db=level_db,
        ),
        verifier=_verify_mixer_fader_set(
            timeline_name=timeline_name,
            index=int(index),
            raw_value=raw_value,
        ),
        allow_project_name_inference=True,
    )


def _validate_audio_track_db_index(rows: list[dict[str, Any]], index: int) -> None:
    if index < 1 or index > len(rows):
        raise ValidationError(
            "Audio track index is out of range for the target timeline.",
            details={
                "track_type": "audio",
                "index": int(index),
                "available_audio_tracks": len(rows),
                "valid_range": f"1-{len(rows)}" if rows else "none",
                "readback_command": "cutagent fairlight tracks --json",
            },
            recoverability="not_applicable",
        )


def _track_format_set_writer(
    *,
    timeline_name: str,
    index: int,
    track_type: str,
    subtype: int,
):
    def _writer(connection: sqlite3.Connection, cursor: sqlite3.Cursor, session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        sequence = _fetch_timeline_sequence(cursor, timeline_name)
        rows = _fetch_audio_track_rows(cursor, sequence=sequence)
        _validate_audio_track_db_index(rows, index)
        target = rows[index - 1]
        previous = _track_payload(target, index=index)
        track_id = str(target["Sm2TiTrack_id"])
        cursor.execute(
            "UPDATE Sm2TiTrack SET SubType = ? WHERE Sm2TiTrack_id = ?",
            (int(subtype), track_id),
        )
        updated_rows = int(cursor.rowcount or 0)
        return {
            "action": "fairlight.track_format.set",
            "changed": updated_rows == 1 and previous["subtype"] != int(subtype),
            "timeline_name": timeline_name,
            "timeline_sequence": sequence,
            "index": int(index),
            "track_id": track_id,
            "previous_track": previous,
            "requested_track_type": track_type,
            "requested_subtype": int(subtype),
            "updated_rows": updated_rows,
        }

    return _writer


def _verify_track_format_set(
    *,
    timeline_name: str,
    index: int,
    track_id: str,
    track_type: str,
    subtype: int,
):
    def _verifier(conn, mutation_result: dict[str, Any], session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        api_timeline_switch: dict[str, Any] | None = None
        api_track_format: str | None = None
        try:
            api_timeline_switch = _switch_timeline_by_name(conn, timeline_name)
            api_track_format = _read_audio_track_subtype(conn, index)
        except Exception:
            api_track_format = None

        connection = sqlite3.connect(session.project_db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            cursor = connection.cursor()
            sequence = _fetch_timeline_sequence(cursor, timeline_name)
            rows = _fetch_audio_track_rows(cursor, sequence=sequence)
            _validate_audio_track_db_index(rows, index)
            row = rows[index - 1]
            db_subtype = int(row.get("SubType") or 0)
            db_track_id = str(row.get("Sm2TiTrack_id") or "")
        finally:
            connection.close()

        db_ok = db_track_id == str(track_id) and db_subtype == int(subtype)
        api_ok = api_track_format is None or str(api_track_format).strip().lower() == str(track_type).strip().lower()
        ok = bool(db_ok and api_ok)
        verification = {
            "status": "verified" if ok else "failed",
            "timeline_name": timeline_name,
            "index": int(index),
            "track_id": str(track_id),
            "expected_track_type": track_type,
            "expected_subtype": int(subtype),
            "db_track_id": db_track_id,
            "db_subtype": db_subtype,
            "api_track_format": api_track_format,
            "api_timeline_switch": api_timeline_switch,
            "checks": [
                {"name": "db_track_identity", "ok": db_track_id == str(track_id)},
                {"name": "db_subtype", "ok": db_subtype == int(subtype)},
                {"name": "api_format", "ok": api_ok, "skipped": api_track_format is None},
            ],
        }
        if not ok:
            raise APICallFailed(
                "Audio track format verification failed after project reopen.",
                details={"verification": verification},
                recoverability="manual",
            )
        return verification

    return _verifier


def set_audio_track_format_db(
    conn,
    *,
    index: int,
    track_type: str,
) -> dict[str, Any]:
    """Set an existing audio track format through DaVinci Resolve's Disk Project.db."""
    normalized_type = str(track_type).strip().lower()
    if normalized_type not in FAIRLIGHT_AUDIO_SUBTYPE_BY_TRACK_TYPE:
        raise ValidationError(
            "Unsupported Fairlight audio track format for DB subtype patch.",
            details={
                "track_type": track_type,
                "allowed": sorted(FAIRLIGHT_AUDIO_SUBTYPE_BY_TRACK_TYPE),
            },
            recoverability="not_applicable",
        )
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed("No active timeline is available for Fairlight track format set.")
    subtype = FAIRLIGHT_AUDIO_SUBTYPE_BY_TRACK_TYPE[normalized_type]
    return db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Fairlight audio track format set",
        writer=_track_format_set_writer(
            timeline_name=timeline_name,
            index=int(index),
            track_type=normalized_type,
            subtype=subtype,
        ),
        verifier=lambda fresh_conn, mutation_result, session: _verify_track_format_set(
            timeline_name=timeline_name,
            index=int(index),
            track_id=str(mutation_result.get("track_id") or ""),
            track_type=normalized_type,
            subtype=subtype,
        )(fresh_conn, mutation_result, session),
        allow_project_name_inference=True,
    )


def _track_order_move_writer(
    *,
    timeline_name: str,
    index: int,
    to_index: int,
):
    def _writer(connection: sqlite3.Connection, cursor: sqlite3.Cursor, session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        sequence = _fetch_timeline_sequence(cursor, timeline_name)
        rows = _fetch_audio_track_rows(cursor, sequence=sequence)
        _validate_audio_track_db_index(rows, index)
        _validate_audio_track_db_index(rows, to_index)
        before = [_track_payload(row, index=row_index) for row_index, row in enumerate(rows, start=1)]
        moved = rows.pop(index - 1)
        rows.insert(to_index - 1, moved)
        after = [_track_payload(row, index=row_index) for row_index, row in enumerate(rows, start=1)]
        changed = int(index) != int(to_index)
        container_ids = {str(row.get("SequenceContainerId") or "") for row in rows}
        container_ids.discard("")
        if len(container_ids) != 1:
            raise ValidationError(
                "Audio track order DB relation could not be resolved for the target timeline.",
                details={
                    "timeline_name": timeline_name,
                    "timeline_sequence": sequence,
                    "container_ids": sorted(container_ids),
                },
                recoverability="manual",
            )
        container_id = next(iter(container_ids))
        for temp_index, row in enumerate(rows, start=1):
            cursor.execute(
                """
                UPDATE Sm2SequenceContainer_Sm2TiTrack
                SET DbIndex = ?
                WHERE DbOwner = ? AND DbPropertyName = 'AudioTrackVec' AND DbAssociate = ?
                """,
                (1000000 + temp_index, container_id, str(row["Sm2TiTrack_id"])),
            )
        for final_index, row in enumerate(rows):
            cursor.execute(
                """
                UPDATE Sm2SequenceContainer_Sm2TiTrack
                SET DbIndex = ?
                WHERE DbOwner = ? AND DbPropertyName = 'AudioTrackVec' AND DbAssociate = ?
                """,
                (final_index, container_id, str(row["Sm2TiTrack_id"])),
            )
        return {
            "action": "fairlight.track_order.move",
            "changed": changed,
            "timeline_name": timeline_name,
            "timeline_sequence": sequence,
            "index": int(index),
            "to": int(to_index),
            "moved_track": _track_payload(moved, index=to_index),
            "before_order": before,
            "after_order": after,
        }

    return _writer


def _verify_track_order_move(
    *,
    timeline_name: str,
    expected_order: list[dict[str, Any]],
):
    def _verifier(conn, mutation_result: dict[str, Any], session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        api_timeline_switch: dict[str, Any] | None = None
        api_formats: list[str | None] = []
        try:
            api_timeline_switch = _switch_timeline_by_name(conn, timeline_name)
            api_formats = [_read_audio_track_subtype(conn, index) for index in range(1, len(expected_order) + 1)]
        except Exception:
            api_formats = []

        connection = sqlite3.connect(session.project_db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            cursor = connection.cursor()
            sequence = _fetch_timeline_sequence(cursor, timeline_name)
            db_rows = _fetch_audio_track_rows(cursor, sequence=sequence)
        finally:
            connection.close()

        db_order = [_track_payload(row, index=row_index) for row_index, row in enumerate(db_rows, start=1)]
        expected_ids = [str(row.get("track_id") or "") for row in expected_order]
        db_ids = [str(row.get("track_id") or "") for row in db_order]
        api_expected_formats = [str(row.get("format") or "") for row in expected_order]
        api_format_checks = [
            actual is None or str(actual).strip().lower() == expected_format
            for actual, expected_format in zip(api_formats, api_expected_formats)
        ]
        db_ok = db_ids == expected_ids
        api_ok = not api_formats or (len(api_formats) == len(api_expected_formats) and all(api_format_checks))
        ok = bool(db_ok and api_ok)
        verification = {
            "status": "verified" if ok else "failed",
            "timeline_name": timeline_name,
            "expected_track_ids": expected_ids,
            "db_track_ids": db_ids,
            "api_formats": api_formats,
            "expected_formats": api_expected_formats,
            "api_timeline_switch": api_timeline_switch,
            "checks": [
                {"name": "db_order", "ok": db_ok},
                {"name": "api_order_formats", "ok": api_ok, "skipped": not api_formats},
            ],
        }
        if not ok:
            raise APICallFailed(
                "Audio track order verification failed after project reopen.",
                details={"verification": verification},
                recoverability="manual",
            )
        return verification

    return _verifier


def move_audio_track_order_db(
    conn,
    *,
    index: int,
    to_index: int,
) -> dict[str, Any]:
    """Move an existing audio track in the Fairlight track order via Disk Project.db."""
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed("No active timeline is available for Fairlight track order move.")
    return db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Fairlight audio track reorder",
        writer=_track_order_move_writer(
            timeline_name=timeline_name,
            index=int(index),
            to_index=int(to_index),
        ),
        verifier=lambda fresh_conn, mutation_result, session: _verify_track_order_move(
            timeline_name=timeline_name,
            expected_order=list(mutation_result.get("after_order") or []),
        )(fresh_conn, mutation_result, session),
        allow_project_name_inference=True,
    )


def _audio_item_track_index(
    cursor: sqlite3.Cursor,
    row: dict[str, Any],
    *,
    audio_track_ids: list[str],
) -> int | None:
    direct_track_id = str(row.get("Sm2TiTrack_id") or "")
    if direct_track_id in audio_track_ids:
        return audio_track_ids.index(direct_track_id) + 1
    item_id = str(row.get("Sm2TiItem_id") or "")
    if not item_id or not _table_exists(cursor, "Sm2TiItem_Sm2TiTrack"):
        return None
    owner_rows = cursor.execute(
        """
        SELECT DbOwner
        FROM Sm2TiItem_Sm2TiTrack
        WHERE DbAssociate = ? AND DbPropertyName = 'Items'
        ORDER BY DbIndex, rowid
        """,
        (item_id,),
    ).fetchall()
    for owner_row in owner_rows:
        owner = str(owner_row[0] or "")
        if owner in audio_track_ids:
            return audio_track_ids.index(owner) + 1
    return None


def _table_exists(cursor: sqlite3.Cursor, table_name: str) -> bool:
    row = cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(cursor: sqlite3.Cursor, table_name: str) -> set[str]:
    return {
        str(row[1])
        for row in cursor.execute(f'PRAGMA table_info("{table_name}")').fetchall()
        if row and row[1] is not None
    }


def _fetch_audio_item_by_id(
    cursor: sqlite3.Cursor,
    *,
    item_id: str,
    audio_track_ids: list[str],
) -> dict[str, Any] | None:
    row = cursor.execute(
        """
        SELECT rowid AS _rowid_, *
        FROM Sm2TiItem
        WHERE Sm2TiItem_id = ? AND DbType = 'Sm2TiAudioClip'
        """,
        (item_id,),
    ).fetchone()
    if row is None:
        return None
    item = _row_to_dict(cursor, row)
    if _audio_item_track_index(cursor, item, audio_track_ids=audio_track_ids) is None:
        return None
    return item


def _fetch_audio_items_for_track(
    cursor: sqlite3.Cursor,
    *,
    track_id: str,
) -> list[dict[str, Any]]:
    if _table_exists(cursor, "Sm2TiItem_Sm2TiTrack"):
        rows = cursor.execute(
            """
            SELECT DISTINCT item.rowid AS _rowid_, item.*
            FROM Sm2TiItem item
            LEFT JOIN Sm2TiItem_Sm2TiTrack rel
              ON rel.DbAssociate = item.Sm2TiItem_id
             AND rel.DbPropertyName = 'Items'
            WHERE item.DbType = 'Sm2TiAudioClip'
              AND (rel.DbOwner = ? OR item.Sm2TiTrack_id = ?)
            ORDER BY CAST(COALESCE(item.Start, '0') AS INTEGER), item.rowid
            """,
            (track_id, track_id),
        ).fetchall()
    else:
        rows = cursor.execute(
            """
            SELECT rowid AS _rowid_, *
            FROM Sm2TiItem
            WHERE DbType = 'Sm2TiAudioClip' AND Sm2TiTrack_id = ?
            ORDER BY CAST(COALESCE(Start, '0') AS INTEGER), rowid
            """,
            (track_id,),
        ).fetchall()
    return [_row_to_dict(cursor, row) for row in rows]


def _range_candidates(
    *,
    start_frame: int | None,
    end_frame: int | None,
    timeline_start: int,
) -> set[tuple[int | None, int | None]]:
    candidates: set[tuple[int | None, int | None]] = {(start_frame, end_frame)}
    if timeline_start:
        candidates.add(
            (
                None if start_frame is None else int(start_frame) - int(timeline_start),
                None if end_frame is None else int(end_frame) - int(timeline_start),
            )
        )
    return candidates


def _point_candidates(*, record_frame: int, timeline_start: int) -> set[int]:
    candidates = {int(record_frame)}
    if timeline_start:
        candidates.add(int(record_frame) - int(timeline_start))
    return candidates


def _item_matches_selector(row: dict[str, Any], selector: AudioGainBatchSelector, *, timeline_start: int) -> bool:
    item_start = _int_cell(row.get("Start"))
    item_duration = _int_cell(row.get("Duration"))
    item_end = item_start + item_duration
    if selector.kind == "point" and selector.record_frame is not None:
        return any(item_start <= candidate < item_end for candidate in _point_candidates(record_frame=selector.record_frame, timeline_start=timeline_start))
    if selector.start_frame is not None and selector.end_frame is not None:
        for start_frame, end_frame in _range_candidates(
            start_frame=selector.start_frame,
            end_frame=selector.end_frame,
            timeline_start=timeline_start,
        ):
            if start_frame is None or end_frame is None:
                continue
            if item_start < end_frame and item_end > start_frame:
                return True
    return False


def _item_payload(
    cursor: sqlite3.Cursor,
    row: dict[str, Any],
    *,
    audio_track_ids: list[str],
    resulting_gain_db: float,
) -> dict[str, Any]:
    previous_gain = clip_effects_db.find_audio_gain_db(row.get("EffectFiltersBA"))
    return {
        "item_id": str(row.get("Sm2TiItem_id") or ""),
        "track_index": _audio_item_track_index(cursor, row, audio_track_ids=audio_track_ids),
        "clip_name": str(row.get("Name") or ""),
        "start": _int_cell(row.get("Start")),
        "duration": _int_cell(row.get("Duration")),
        "previous_gain_db": previous_gain,
        "resulting_gain_db": float(resulting_gain_db),
    }
