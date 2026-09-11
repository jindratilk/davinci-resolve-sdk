from __future__ import annotations

from collections import Counter


def ensure_stereo_audio_tracks(
    conn,
    *,
    count: int,
    timeline_name: str | None = None,
    patch_db_subtype: bool = True,
    db_subtype: int = 0,
    allow_existing: bool = True,
) -> dict[str, Any]:
    """Ensure a timeline has at least *count* stereo audio tracks and optionally patch DB subtypes."""
    if count < 1:
        raise ValidationError(
            "--count must be 1 or greater.",
            details={"count": count, "min": 1},
            recoverability="not_applicable",
        )

    original_timeline_name = _timeline_name(conn)
    timeline_switch: dict[str, Any] | None = None
    restored_original_timeline = False
    if timeline_name:
        timeline_switch = _switch_timeline_by_name(conn, timeline_name)

    target_timeline_name = _timeline_name(conn)
    if not target_timeline_name:
        raise APICallFailed("No target timeline is available for Fairlight track management.")

    before_count = _audio_track_count(conn)
    created_count = 0
    native_add_results: list[dict[str, Any]] = []
    if before_count < count or not allow_existing:
        while _audio_track_count(conn) < count:
            current_count = _audio_track_count(conn)
            result = _add_stereo_audio_track_with_fallback(conn, before_count=current_count)
            native_add_results.append(result)
            created_count += 1

    after_native_count = _audio_track_count(conn)
    if after_native_count < count:
        raise APICallFailed(
            "Audio track count is still below the requested count after native add attempts.",
            details={
                "timeline_name": target_timeline_name,
                "requested_count": count,
                "audio_tracks_before": before_count,
                "audio_tracks_after": after_native_count,
                "created_count": created_count,
            },
        )

    saved_after_native_add = False
    if created_count > 0:
        saved_after_native_add = _save_project_if_available(conn)
        if patch_db_subtype:
            persisted_count = _wait_for_disk_audio_track_count(conn, timeline_name=target_timeline_name, expected_count=count)
            if persisted_count is not None and persisted_count < count:
                raise APICallFailed(
                    "DaVinci Resolve did not persist native audio track additions to the Disk Project.db before subtype patching.",
                    details={
                        "timeline_name": target_timeline_name,
                        "requested_count": int(count),
                        "api_audio_track_count": after_native_count,
                        "disk_audio_track_count": persisted_count,
                        "saved_after_native_add": saved_after_native_add,
                        "recovery_hint": "Run with --no-patch-db-subtype for session-only native track creation, or save/reopen the project and retry subtype patching after DaVinci Resolve persists the new tracks.",
                    },
                    recoverability="manual",
                )

    db_patch_result: dict[str, Any] | None = None
    if patch_db_subtype:
        db_patch_result = patch_audio_track_db_subtypes(
            conn,
            timeline_name=target_timeline_name,
            subtype=db_subtype,
            expected_count=count,
        )

    if timeline_name and original_timeline_name and original_timeline_name != target_timeline_name:
        restored_original_timeline = _restore_timeline_after_db_session(original_timeline_name)

    if created_count > 0 or patch_db_subtype:
        set_verification_status("verified")

    db_subtype_patch = {
        "requested": bool(patch_db_subtype),
        "subtype": int(db_subtype),
        "updated_rows": None,
    }
    verification = None
    if db_patch_result is not None:
        db_subtype_patch = dict(db_patch_result.get("db_subtype_patch") or db_subtype_patch)
        verification = db_patch_result.get("verification")

    return {
        "target": {"kind": "timeline", "name": target_timeline_name},
        "timeline_name": target_timeline_name,
        "requested_count": int(count),
        "allow_existing": bool(allow_existing),
        "audio_tracks_before": before_count,
        "audio_tracks_after": after_native_count,
        "created_count": created_count,
        "native_add_results": native_add_results,
        "native_subtype_supported": all(result.get("native_subtype_supported") for result in native_add_results) if native_add_results else None,
        "timeline_switch": timeline_switch,
        "original_timeline": original_timeline_name,
        "restored_original_timeline": restored_original_timeline,
        "saved_after_native_add": saved_after_native_add,
        "db_subtype_patch": db_subtype_patch,
        "verification": verification,
        "db_session": {
            key: db_patch_result.get(key)
            for key in ("route", "project_db_path", "backup_path", "steps")
        } if db_patch_result is not None else None,
    }


def ensure_audio_tracks(
    conn,
    *,
    count: int,
    track_type: str = "stereo",
    timeline_name: str | None = None,
    allow_existing: bool = True,
) -> dict[str, Any]:
    """Ensure a timeline has at least *count* audio tracks of *track_type* using native AddTrack."""
    if count < 1:
        raise ValidationError(
            "--count must be 1 or greater.",
            details={"count": count, "min": 1},
            recoverability="not_applicable",
        )

    normalized_type = str(track_type).strip().lower()
    original_timeline_name = _timeline_name(conn)
    timeline_switch: dict[str, Any] | None = None
    restored_original_timeline = False
    if timeline_name:
        timeline_switch = _switch_timeline_by_name(conn, timeline_name)

    target_timeline_name = _timeline_name(conn)
    if not target_timeline_name:
        raise APICallFailed("No target timeline is available for Fairlight track management.")

    before_rows = list_audio_tracks(conn)
    before_count = _audio_track_count(conn)
    before_format_readback_supported = any("format" in row for row in before_rows)
    matching_before = [row for row in before_rows if row.get("format") == normalized_type]
    existing_credit = len(matching_before) if allow_existing and before_format_readback_supported else 0
    tracks_to_create = max(0, int(count) - existing_credit) if allow_existing else int(count)

    native_add_results: list[dict[str, Any]] = []
    for _ in range(tracks_to_create):
        current_count = _audio_track_count(conn)
        add_audio_track(conn, normalized_type)
        after_count = _wait_for_audio_track_count(conn, previous_count=current_count)
        if after_count <= current_count:
            raise APICallFailed(
                "Audio track add did not appear in timeline readback.",
                details={
                    "track_type": normalized_type,
                    "audio_tracks_before": current_count,
                    "audio_tracks_after": after_count,
                },
            )
        created_index = int(after_count)
        readback_format = _read_audio_track_subtype(conn, created_index)
        if readback_format is not None and readback_format != normalized_type:
            set_verification_status("failed")
            raise APICallFailed(
                "Audio track format readback did not match requested format.",
                details={
                    "requested_track_type": normalized_type,
                    "readback_track_type": readback_format,
                    "created_track_index": created_index,
                    "audio_tracks_before": current_count,
                    "audio_tracks_after": after_count,
                },
            )
        native_add_results.append(
            {
                "requested_track_type": normalized_type,
                "api_call": 'Timeline.AddTrack("audio", track_type)',
                "audio_tracks_before": current_count,
                "audio_tracks_after": after_count,
                "created_track_index": created_index,
                "readback_track_type": readback_format,
                "format_verified": readback_format is not None,
                "verified": True,
            }
        )

    after_rows = list_audio_tracks(conn)
    after_count = _audio_track_count(conn)
    after_format_readback_supported = any("format" in row for row in after_rows)
    matching_after = [row for row in after_rows if row.get("format") == normalized_type]
    matching_after_count = len(matching_after) if after_format_readback_supported else None
    if matching_after_count is not None and matching_after_count < int(count):
        set_verification_status("failed")
        raise APICallFailed(
            "Audio track format count is still below the requested count after native add attempts.",
            details={
                "timeline_name": target_timeline_name,
                "requested_count": int(count),
                "requested_track_type": normalized_type,
                "matching_tracks_after": matching_after_count,
                "audio_tracks_after": after_count,
            },
        )

    if timeline_name and original_timeline_name and original_timeline_name != target_timeline_name:
        restored_original_timeline = _restore_timeline_after_db_session(original_timeline_name)

    if native_add_results:
        set_verification_status(
            "verified"
            if all(result.get("format_verified") for result in native_add_results)
            else "pending_manual"
        )

    return {
        "target": {"kind": "timeline", "name": target_timeline_name},
        "timeline_name": target_timeline_name,
        "requested_count": int(count),
        "requested_track_type": normalized_type,
        "allow_existing": bool(allow_existing),
        "format_readback_supported": after_format_readback_supported,
        "matching_tracks_before": len(matching_before) if before_format_readback_supported else None,
        "matching_tracks_after": matching_after_count,
        "audio_tracks_before": before_count,
        "audio_tracks_after": after_count,
        "created_count": len(native_add_results),
        "native_add_results": native_add_results,
        "timeline_switch": timeline_switch,
        "original_timeline": original_timeline_name,
        "restored_original_timeline": restored_original_timeline,
    }


def _canonical_fairlight_bus_name(bus_name: str | None) -> str:
    value = str(bus_name or "").strip()
    folded = value.casefold().replace(" ", "")
    if folded in {"bus1", "main", "main1"}:
        return "Bus 1"
    raise ValidationError(
        "Fairlight bus name is not supported by the verified DB route.",
        details={
            "bus": bus_name,
            "supported": ["Bus 1"],
            "hint": "The verified DB route currently supports the default DaVinci Resolve timeline output bus.",
        },
        recoverability="not_applicable",
    )


def _extract_fairlight_model_bus_names(fields_blob: bytes | None) -> list[str]:
    if not fields_blob:
        return []
    try:
        import re

        blob = bytes(fields_blob)
        marker = "FLStudioModelBA".encode("utf-16-be")
        marker_offset = blob.find(marker)
        if marker_offset < 0:
            return []
        zlib_offset = blob.find(b"\x78\x9c", marker_offset)
        if zlib_offset < 0:
            return []
        model = zlib.decompress(blob[zlib_offset:])
        names = set()
        for match in re.finditer(rb"Bus\s*\d+", model):
            raw = match.group(0).decode("ascii", "ignore")
            suffix = "".join(ch for ch in raw if ch.isdigit())
            if suffix:
                names.add(f"Bus {int(suffix)}")
        return sorted(names)
    except Exception:
        return []


def _read_fairlight_bus_model_from_cursor(cursor: sqlite3.Cursor, *, timeline_name: str) -> dict[str, Any]:
    sequence = _fetch_timeline_sequence(cursor, timeline_name)
    row = cursor.execute(
        """
        SELECT Sm2Sequence_id, OutputAudioGain, NumOutputAudioChannels, FieldsBlob
        FROM Sm2Sequence
        WHERE Sm2Sequence_id = ?
        """,
        (sequence,),
    ).fetchone()
    if row is None:
        raise APICallFailed(
            "Timeline sequence was not found for Fairlight bus DB route.",
            details={"timeline_name": timeline_name, "sequence": sequence},
        )
    bus_names = _extract_fairlight_model_bus_names(row["FieldsBlob"] if isinstance(row, sqlite3.Row) else row[3])
    if "Bus 1" not in bus_names:
        bus_names.append("Bus 1")
    output_gain = row["OutputAudioGain"] if isinstance(row, sqlite3.Row) else row[1]
    output_channels = row["NumOutputAudioChannels"] if isinstance(row, sqlite3.Row) else row[2]
    return {
        "timeline_name": timeline_name,
        "timeline_sequence": sequence,
        "buses": [{"name": name, "kind": "timeline_output"} for name in sorted(set(bus_names))],
        "output_audio_gain_db": float(output_gain or 0.0),
        "output_audio_channels": int(output_channels or 0),
    }


def read_fairlight_bus_model(conn, *, timeline_name: str | None = None) -> dict[str, Any]:
    """Read the verified Fairlight bus model subset from the Disk DB."""
    target_timeline_name = timeline_name or _timeline_name(conn)
    if not target_timeline_name:
        raise APICallFailed("No active timeline is available for Fairlight bus DB route.")
    current_database = db_session.resolve_current_disk_project_db(conn, allow_project_name_inference=True)
    db_path = str(current_database["project_db_path"])
    connection = sqlite3.connect(db_path, timeout=5.0)
    connection.row_factory = sqlite3.Row
    try:
        return _read_fairlight_bus_model_from_cursor(connection.cursor(), timeline_name=target_timeline_name)
    finally:
        connection.close()


_CHANNEL_MAP_STEREO_NORMAL_MARKER = bytes.fromhex("0200004001000040")
_CHANNEL_MAP_STEREO_LEFT_MARKER = bytes.fromhex("0100004001000040")
_CHANNEL_MAP_STEREO_RIGHT_MARKER = bytes.fromhex("0100004002000040")
_CHANNEL_MAP_STEREO_MARKERS = {
    (1, 2): _CHANNEL_MAP_STEREO_NORMAL_MARKER,
    (1,): _CHANNEL_MAP_STEREO_LEFT_MARKER,
    (2,): _CHANNEL_MAP_STEREO_RIGHT_MARKER,
}


def _normalize_timeline_channel_mapping_request(mapping: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(mapping, dict):
        raise ValidationError(
            "--mapping-json must decode to an object.",
            details={"mapping_type": type(mapping).__name__},
            recoverability="not_applicable",
        )
    track_mapping = mapping.get("track_mapping")
    if not isinstance(track_mapping, dict) or set(track_mapping.keys()) != {"1"}:
        raise ValidationError(
            "Fairlight channel-map set currently supports exactly track_mapping.1 on one timeline item.",
            details={
                "supported_scope": "timeline_item_virtual_audio_track_track_1",
                "track_mapping_keys": sorted(str(key) for key in track_mapping.keys()) if isinstance(track_mapping, dict) else None,
            },
            recoverability="not_applicable",
        )
    track = track_mapping.get("1")
    if not isinstance(track, dict):
        raise ValidationError(
            "track_mapping.1 must be an object.",
            details={"track_mapping_1_type": type(track).__name__},
            recoverability="not_applicable",
        )
    requested_mute = track.get("mute", False)
    if requested_mute is not False:
        raise ValidationError(
            "Fairlight channel-map set does not yet support muting mapped source channels.",
            details={"requested_mute": requested_mute, "supported_mute": False},
            recoverability="not_applicable",
        )
    track_type = str(track.get("type", "stereo")).lower()
    if track_type != "stereo":
        raise ValidationError(
            "Fairlight channel-map set currently supports only stereo timeline item mappings.",
            details={"requested_type": track.get("type"), "supported_type": "stereo"},
            recoverability="not_applicable",
        )
    channel_idx = track.get("channel_idx")
    if not isinstance(channel_idx, list):
        raise ValidationError(
            "track_mapping.1.channel_idx must be a JSON array.",
            details={"channel_idx": channel_idx},
            recoverability="not_applicable",
        )
    try:
        normalized_channels = tuple(int(value) for value in channel_idx)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "track_mapping.1.channel_idx values must be integers.",
            details={"channel_idx": channel_idx},
            recoverability="not_applicable",
        ) from exc
    if normalized_channels not in _CHANNEL_MAP_STEREO_MARKERS:
        raise ValidationError(
            "Fairlight channel-map set supports only [1], [2], or [1,2] for the verified stereo timeline-item route.",
            details={
                "requested_channel_idx": list(normalized_channels),
                "supported_channel_idx": [[1], [2], [1, 2]],
                "supported_scope": "single timeline item Sm2TiItem.VirtualAudioTrackBA stereo source mapping",
            },
            recoverability="not_applicable",
        )
    embedded_channels = mapping.get("embedded_audio_channels")
    if embedded_channels is not None:
        try:
            normalized_embedded_channels = int(embedded_channels)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "embedded_audio_channels must be an integer when provided.",
                details={"embedded_audio_channels": embedded_channels},
                recoverability="not_applicable",
            ) from exc
        if normalized_embedded_channels != 2:
            raise ValidationError(
                "Fairlight channel-map set currently supports only two-channel embedded audio.",
                details={"embedded_audio_channels": embedded_channels, "supported_embedded_audio_channels": 2},
                recoverability="not_applicable",
            )
    return {
        "track_mapping": {
            "1": {
                "channel_idx": list(normalized_channels),
                "mute": False,
                "type": "stereo",
            }
        },
        "embedded_audio_channels": 2,
        "linked_audio": {},
    }


def _fetch_channel_map_item_row(
    cursor: sqlite3.Cursor,
    *,
    sequence: str,
    clip: str,
) -> dict[str, Any]:
    track_ids = _audio_track_ids_for_sequence(cursor, sequence)
    if not track_ids:
        raise ValidationError(
            "Target timeline has no audio tracks in the DaVinci Resolve Disk project database.",
            details={"timeline_sequence": sequence},
        )
    rows = cursor.execute(
        """
        SELECT rowid AS db_rowid, Sm2TiItem_id, Sm2TiTrack_id, Name, VirtualAudioTrackBA
        FROM Sm2TiItem
        WHERE Sm2TiItem_id = ? OR Name = ?
        ORDER BY rowid
        """,
        (clip, clip),
    ).fetchall()
    matches = []
    for row in rows:
        track_id = str(row["Sm2TiTrack_id"] or "")
        if track_id not in track_ids:
            continue
        matches.append({key: row[key] for key in row.keys()} | {"track_index": track_ids.index(track_id) + 1})
    if not matches:
        raise ValidationError(
            "Audio timeline item was not found in the target timeline.",
            details={"clip": clip, "timeline_sequence": sequence},
            recoverability="manual",
        )
    if len(matches) > 1:
        raise ValidationError(
            "Fairlight channel-map set requires a unique current-timeline audio item.",
            details={
                "clip": clip,
                "matches": [
                    {
                        "item_id": str(row["Sm2TiItem_id"]),
                        "clip_name": str(row["Name"] or ""),
                        "track_index": int(row["track_index"]),
                        "db_rowid": int(row["db_rowid"] or 0),
                    }
                    for row in matches
                ],
            },
            recoverability="not_applicable",
        )
    return matches[0]


def _replace_verified_channel_map_marker(blob: bytes, *, target_channels: tuple[int, ...]) -> tuple[bytes, tuple[int, ...], bool]:
    target_marker = _CHANNEL_MAP_STEREO_MARKERS[target_channels]
    found: list[tuple[tuple[int, ...], bytes]] = []
    for channels, marker in _CHANNEL_MAP_STEREO_MARKERS.items():
        if marker in blob:
            found.append((channels, marker))
    if len(found) != 1:
        raise ReadinessFailed(
            "Fairlight channel mapping blob is not in the verified stereo timeline-item format.",
            details={
                "supported_scope": "single Sm2TiItem.VirtualAudioTrackBA stereo marker replacement",
                "marker_count": len(found),
                "blob_length": len(blob),
                "available_markers": [list(channels) for channels, _ in found],
            },
            recoverability="manual",
        )
    current_channels, current_marker = found[0]
    changed = current_channels != target_channels
    if not changed:
        return blob, current_channels, False
    return blob.replace(current_marker, target_marker, 1), current_channels, True


def _timeline_channel_mapping_set_writer(
    *,
    timeline_name: str,
    clip: str,
    normalized_mapping: dict[str, Any],
):
    target_channels = tuple(normalized_mapping["track_mapping"]["1"]["channel_idx"])

    def _writer(connection: sqlite3.Connection, cursor: sqlite3.Cursor, session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        sequence = _fetch_timeline_sequence(cursor, timeline_name)
        row = _fetch_channel_map_item_row(cursor, sequence=sequence, clip=clip)
        previous_blob = bytes(row["VirtualAudioTrackBA"] or b"")
        if not previous_blob:
            raise ReadinessFailed(
                "Fairlight channel mapping requires an existing VirtualAudioTrackBA blob on the target audio item.",
                details={
                    "clip": clip,
                    "item_id": str(row["Sm2TiItem_id"]),
                    "timeline_name": timeline_name,
                    "timeline_sequence": sequence,
                },
                recoverability="manual",
            )
        new_blob, previous_channels, changed = _replace_verified_channel_map_marker(
            previous_blob,
            target_channels=target_channels,
        )
        if changed:
            cursor.execute(
                "UPDATE Sm2TiItem SET VirtualAudioTrackBA = ? WHERE Sm2TiItem_id = ?",
                (new_blob, str(row["Sm2TiItem_id"])),
            )
        return {
            "action": "fairlight.channel_map.set",
            "changed": changed,
            "timeline_name": timeline_name,
            "timeline_sequence": sequence,
            "target": {
                "kind": "timeline_item",
                "clip": str(row["Name"] or clip),
                "item_id": str(row["Sm2TiItem_id"]),
                "track_index": int(row["track_index"]),
            },
            "previous_mapping": {
                "track_mapping": {"1": {"channel_idx": list(previous_channels), "mute": False, "type": "stereo"}},
                "embedded_audio_channels": 2,
                "linked_audio": {},
            },
            "mapping": normalized_mapping,
            "route": "db_native",
            "db_table": "Sm2TiItem",
            "db_column": "VirtualAudioTrackBA",
            "storage": "verified_stereo_virtual_audio_track_marker",
            "verified_set_scope": "single_timeline_item_stereo_channel_idx_1_2_or_single_source_duplicate",
        }

    return _writer


def _verify_timeline_channel_mapping_set(*, expected_mapping: dict[str, Any]):
    expected_channels = list(expected_mapping["track_mapping"]["1"]["channel_idx"])

    def _verifier(conn, mutation_result: dict[str, Any], session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        from . import clip_ops

        target = mutation_result.get("target") or {}
        native_id = str(target.get("item_id") or "")
        if not native_id:
            raise APICallFailed(
                "Fairlight channel mapping verification lost the native item identity.",
                details={"target": target},
                recoverability="manual",
            )
        native_readback = clip_ops.get_source_audio_mapping(conn, native_id)
        raw_mapping = native_readback.get("mapping")
        parsed_mapping = raw_mapping
        parse_error = None
        if isinstance(raw_mapping, str):
            try:
                parsed_mapping = json.loads(raw_mapping)
            except json.JSONDecodeError as exc:
                parse_error = {"line": exc.lineno, "column": exc.colno, "message": exc.msg}
        actual_channels = (
            (((parsed_mapping or {}).get("track_mapping") or {}).get("1") or {}).get("channel_idx")
            if isinstance(parsed_mapping, dict)
            else None
        )
        ok = actual_channels == expected_channels
        verification = {
            "status": "verified" if ok else "failed",
            "native_api": "TimelineItem.GetSourceAudioChannelMapping()",
            "expected_channel_idx": expected_channels,
            "actual_channel_idx": actual_channels,
            "native_readback": parsed_mapping,
            "raw_mapping": raw_mapping,
        }
        if parse_error:
            verification["parse_error"] = parse_error
        if not ok:
            raise APICallFailed(
                "Fairlight channel mapping verification failed after project reopen.",
                details={"verification": verification},
                recoverability="manual",
            )
        return verification

    return _verifier


def set_timeline_item_channel_mapping_db(
    conn,
    *,
    clip: str,
    mapping: dict[str, Any],
) -> dict[str, Any]:
    """Set a timeline-item mapping natively on 21.1, with the older Disk DB route retained."""
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed("No active timeline is available for Fairlight channel mapping set.")
    normalized_mapping = _normalize_timeline_channel_mapping_request(mapping)
    from .resolve_api_version import at_least
    if at_least(conn, 21, 1):
        from .native_channel_mapping import set_timeline_mapping
        return set_timeline_mapping(conn, clip=clip, mapping=normalized_mapping)
    return db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Fairlight channel mapping set",
        writer=_timeline_channel_mapping_set_writer(
            timeline_name=timeline_name,
            clip=clip,
            normalized_mapping=normalized_mapping,
        ),
        verifier=_verify_timeline_channel_mapping_set(expected_mapping=normalized_mapping),
        allow_project_name_inference=True,
    )


def _resolve_audio_track_selector(conn, *, track_index: int | None = None, track_name: str | None = None) -> dict[str, Any]:
    count = _audio_track_count(conn)
    if track_index is not None:
        _validate_audio_track_index(conn, int(track_index))
        name = ""
        getter = getattr(conn.timeline, "GetTrackName", None)
        if callable(getter):
            try:
                name = str(getter("audio", int(track_index)) or "")
            except Exception:
                name = ""
        return {"index": int(track_index), "name": name}
    if track_name:
        getter = getattr(conn.timeline, "GetTrackName", None)
        if callable(getter):
            for index in range(1, count + 1):
                try:
                    candidate = str(getter("audio", index) or "")
                except Exception:
                    candidate = ""
                if candidate == track_name:
                    return {"index": index, "name": candidate}
    raise ValidationError(
        "Audio track selector is required for Fairlight bus assignment.",
        details={
            "track": track_index,
            "track_name": track_name,
            "audio_track_count": count,
            "required": ["--track or --track-name"],
        },
        recoverability="not_applicable",
    )


def assign_audio_track_bus_db(
    conn,
    *,
    bus_name: str,
    track_index: int | None = None,
    track_name: str | None = None,
) -> dict[str, Any]:
    """Verify the default track-to-output-bus route through the Fairlight DB model."""
    canonical_bus = _canonical_fairlight_bus_name(bus_name)
    target_track = _resolve_audio_track_selector(conn, track_index=track_index, track_name=track_name)
    model = read_fairlight_bus_model(conn)
    available = {row["name"] for row in model["buses"]}
    if canonical_bus not in available:
        raise ValidationError(
            "Fairlight bus was not found in the verified DB model.",
            details={"requested_bus": bus_name, "canonical_bus": canonical_bus, "available_buses": sorted(available)},
            recoverability="not_applicable",
        )
    set_verification_status("verified")
    return {
        "action": "fairlight.bus.assign",
        "changed": False,
        "route": "db_workaround_verified_default_output",
        "timeline_name": model["timeline_name"],
        "timeline_sequence": model["timeline_sequence"],
        "bus": canonical_bus,
        "track": target_track,
        "available_buses": sorted(available),
        "verification": {
            "status": "verified",
            "checks": [
                {"name": "bus_exists", "expected": canonical_bus, "actual": sorted(available), "ok": True},
                {"name": "track_exists", "expected": target_track["index"], "actual": target_track, "ok": True},
            ],
        },
        "note": "DaVinci Resolve's default timeline output route is represented as Bus 1 in the Fairlight DB model.",
    }


_DIALOGUE_PROCESSOR_PARAM_ALIASES = {
    "threshold": "comp_threshold",
    "comp_threshold": "comp_threshold",
    "ratio": "comp_ratio",
    "comp_ratio": "comp_ratio",
    "knee": "comp_knee",
    "mix": "comp_mix",
    "gate_threshold": "gate_threshold",
    "limiter_threshold": "limiter_threshold",
}


def _dynamics_readback_initialized(readback: dict[str, Any]) -> bool:
    if readback.get("status") != "ok":
        return False
    bounded = {
        "comp_threshold": (-120.0, 60.0),
        "gate_threshold": (-120.0, 60.0),
        "limiter_threshold": (-120.0, 60.0),
        "comp_knee": (0.0, 100.0),
        "comp_mix": (0.0, 100.0),
        "comp_ratio": (0.0, 100.0),
    }
    for name, (low, high) in bounded.items():
        value = readback.get(name)
        if value is None:
            continue
        try:
            numeric = float(value)
        except Exception:
            return False
        if not low <= numeric <= high:
            return False
    return True


def _canonical_fairlight_effect_name(effect_name: str | None) -> str:
    folded = str(effect_name or "").strip().casefold().replace("_", " ").replace("-", " ")
    folded = " ".join(folded.split())
    if folded in {"dialogue processor", "dynamics"}:
        return "dialogue_processor"
    if folded in {"eq", "equalizer"}:
        return "eq"
    raise ValidationError(
        "Fairlight effect is not supported by the verified DB route.",
        details={
            "effect": effect_name,
            "supported": ["Dialogue Processor", "Dynamics", "EQ"],
            "hint": "Use the dedicated DB-backed Fairlight commands for arbitrary EQ, Dynamics, and AI audio features.",
        },
        recoverability="not_applicable",
    )


_DIALOGUE_PROCESSOR_DEFAULT_PARAMS = {
    "make_up": 10.3,
    "comp_threshold": -23.2,
    "comp_ratio": 49,
    "comp_knee": 46,
    "comp_mix": 41,
    "gate_threshold": -24.4,
    "gate_range": 45,
    "limiter_threshold": -21.8,
}


def _dialogue_processor_param_write(enabled: bool) -> dict[str, Any]:
    return {
        **_DIALOGUE_PROCESSOR_DEFAULT_PARAMS,
        "comp_enable": bool(enabled),
        "gate_enable": bool(enabled),
        "limiter_enable": bool(enabled),
    }


def set_fairlight_effect_state_db(conn, *, effect_name: str, enabled: bool) -> dict[str, Any]:
    """Enable/disable the verified Dialogue Processor/Dynamics DB parameter route."""
    canonical = _canonical_fairlight_effect_name(effect_name)
    target_timeline_name = _timeline_name(conn)
    if not target_timeline_name:
        raise APICallFailed("No active timeline is available for Fairlight effect DB route.")
    if canonical == "eq":
        if not enabled:
            raise ValidationError(
                "Fairlight EQ is a built-in processing module and cannot be removed with fairlight effect remove.",
                details={
                    "effect": effect_name,
                    "supported_action": "Use fairlight eq set/read for EQ parameter changes.",
                },
                recoverability="not_applicable",
            )
        set_verification_status("verified")
        return {
            "action": "fairlight.effect.add" if enabled else "fairlight.effect.remove",
            "changed": False,
            "route": "db_workaround_existing_eq",
            "effect": "EQ",
            "enabled": True,
            "verification": {
                "status": "verified",
                "checks": [{"name": "eq_route_exists", "expected": True, "actual": True, "ok": True}],
            },
            "note": "DaVinci Resolve timelines expose EQ as a built-in Fairlight processing module; use fairlight eq set/read for parameter writes.",
        }
    from .dynamics_db import read_dynamics_from_cursor, write_dynamics_params_with_cursor

    def _writer(_connection: sqlite3.Connection, cursor: sqlite3.Cursor, _session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        sequence = _fetch_timeline_sequence(cursor, target_timeline_name)
        params = _dialogue_processor_param_write(enabled)
        result = write_dynamics_params_with_cursor(cursor, params, sequence_id=sequence)
        return {
            "action": "fairlight.effect.add" if enabled else "fairlight.effect.remove",
            "changed": True,
            "route": "db_workaround_dynamics_params",
            "effect": "Dialogue Processor",
            "canonical_effect": canonical,
            "timeline_name": target_timeline_name,
            "timeline_sequence": sequence,
            "requested_params": params,
            **result,
        }

    def _verifier(_fresh_conn, _mutation_result: dict[str, Any], session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        connection = sqlite3.connect(session.project_db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            cursor = connection.cursor()
            readback = read_dynamics_from_cursor(cursor, sequence_id=_mutation_result.get("timeline_sequence"))
        finally:
            connection.close()
        expected = bool(enabled)
        checks = [
            {"name": name, "expected": expected, "actual": readback.get(name), "ok": readback.get(name) is expected}
            for name in ("comp_enable", "gate_enable", "limiter_enable")
        ]
        for name, expected_value in _DIALOGUE_PROCESSOR_DEFAULT_PARAMS.items():
            actual = readback.get(name)
            try:
                ok = actual is not None and abs(float(actual) - float(expected_value)) <= 0.0001
            except Exception:
                ok = False
            checks.append({"name": name, "expected": expected_value, "actual": actual, "ok": ok})
        if not all(check["ok"] for check in checks):
            raise APICallFailed(
                "Fairlight effect DB verification failed after project reopen.",
                details={"checks": checks, "readback": readback},
                recoverability="manual",
            )
        return {"status": "verified", "checks": checks, "readback": readback}

    result = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Fairlight effect DB parameter write",
        writer=_writer,
        verifier=_verifier,
        allow_project_name_inference=True,
    )
    result["db_session_route"] = result.get("route")
    result["route"] = "db_workaround_dynamics_params"
    return result


def read_fairlight_effect_params_db(conn, *, effect_name: str, param: str | None = None) -> dict[str, Any]:
    """Read verified DB-backed Fairlight effect parameters."""
    canonical = _canonical_fairlight_effect_name(effect_name)
    target_timeline_name = _timeline_name(conn)
    if not target_timeline_name:
        raise APICallFailed("No active timeline is available for Fairlight effect parameter DB route.")
    current_database = db_session.resolve_current_disk_project_db(conn, allow_project_name_inference=True)
    db_path = str(current_database["project_db_path"])
    if canonical == "eq":
        from .audio_eq_db import read_eq_state

        connection = sqlite3.connect(db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            state = read_eq_state(connection.cursor())
        finally:
            connection.close()
        set_verification_status("verified")
        return {
            "action": "fairlight.effect.params",
            "route": "db_workaround_eq_read",
            "effect": "EQ",
            "param": param,
            "params": state,
            "verification": {"status": "verified", "checks": []},
        }
    from .dynamics_db import read_dynamics_from_cursor

    connection = sqlite3.connect(db_path, timeout=5.0)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        sequence = _fetch_timeline_sequence(cursor, target_timeline_name)
        readback = read_dynamics_from_cursor(cursor, sequence_id=sequence)
    finally:
        connection.close()
    if not _dynamics_readback_initialized(readback):
        raise ReadinessFailed(
            "Dialogue Processor parameters are not initialized in the verified DB payload.",
            details={
                "effect": effect_name,
                "readback_status": readback.get("status"),
                "required_action": "Run `cutagent fairlight effect add \"Dialogue Processor\" --json` or enable Dynamics in DaVinci Resolve before reading parameters.",
                "readback": readback,
            },
            recoverability="manual",
        )
    params = {alias: readback.get(target) for alias, target in _DIALOGUE_PROCESSOR_PARAM_ALIASES.items()}
    if param:
        folded = str(param).strip().casefold().replace("-", "_")
        target = _DIALOGUE_PROCESSOR_PARAM_ALIASES.get(folded)
        if not target:
            raise ValidationError(
                "Fairlight effect parameter is not supported by the verified DB route.",
                details={"param": param, "supported": sorted(_DIALOGUE_PROCESSOR_PARAM_ALIASES)},
                recoverability="not_applicable",
            )
        params = {param: readback.get(target)}
    set_verification_status("verified")
    return {
        "action": "fairlight.effect.params",
        "route": "db_workaround_dynamics_read",
        "effect": "Dialogue Processor",
        "canonical_effect": canonical,
        "param": param,
        "params": params,
        "raw_dynamics": readback,
        "verification": {
            "status": "verified",
            "checks": [{"name": "dynamics_readback", "expected": "ok", "actual": readback.get("status"), "ok": readback.get("status") == "ok"}],
        },
    }


def rename_audio_track(conn, index: int, name: str) -> bool:
    """
    Rename an audio track.
    
    Args:
        conn: ResolveConnection instance
        index: Track index
        name: New name
    
    Returns:
        True if successful
    
    Raises:
        APICallFailed: If rename fails
    """
    result = conn.timeline.SetTrackName("audio", index, name)
    if result:
        return True
    else:
        raise APICallFailed("Failed to rename track.")


def delete_audio_track(conn, index: int) -> Dict[str, Any]:
    """Delete an audio track through the native DaVinci Resolve Timeline.DeleteTrack API."""
    before_count = _validate_audio_track_index(conn, index)
    deleter = getattr(conn.timeline, "DeleteTrack", None)
    if not callable(deleter):
        raise APICallFailed(
            "DeleteTrack not available.",
            details={
                "track_type": "audio",
                "index": index,
                "required_api": "Timeline.DeleteTrack",
            },
        )
    result = deleter("audio", int(index))
    if result is False:
        raise APICallFailed(
            "Failed to delete audio track.",
            details={"track_type": "audio", "index": index, "api_result": result},
        )
    after_count = _audio_track_count(conn)
    verified = after_count == before_count - 1
    if not verified:
        raise APICallFailed(
            "Audio track delete did not appear in timeline readback.",
            details={
                "track_type": "audio",
                "index": index,
                "audio_tracks_before": before_count,
                "audio_tracks_after": after_count,
                "api_result": result,
            },
        )
    set_verification_status("verified")
    return {
        "action": "fairlight.delete",
        "track_type": "audio",
        "index": int(index),
        "audio_tracks_before": before_count,
        "audio_tracks_after": after_count,
        "deleted": True,
        "verified": True,
    }


def _fairlight_duplicate_item_summary(item) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, method in (
        ("name", "GetName"),
        ("start", "GetStart"),
        ("end", "GetEnd"),
        ("duration", "GetDuration"),
        ("source_start", "GetLeftOffset"),
        ("source_right_offset", "GetRightOffset"),
    ):
        getter = getattr(item, method, None)
        if not callable(getter):
            continue
        try:
            value = getter()
        except Exception:
            continue
        if key in {"start", "end", "duration", "source_start", "source_right_offset"}:
            try:
                value = int(value)
            except Exception:
                pass
        summary[key] = value
    getter = getattr(item, "GetMediaPoolItem", None)
    media_pool_item = None
    if callable(getter):
        try:
            media_pool_item = getter()
        except Exception:
            media_pool_item = None
    name_getter = getattr(media_pool_item, "GetName", None)
    if callable(name_getter):
        try:
            summary["media_pool_item_name"] = name_getter()
        except Exception:
            pass
    return summary


def _safe_clip_info_for_output(clip_info: dict[str, Any]) -> dict[str, Any]:
    safe = {key: value for key, value in clip_info.items() if key != "mediaPoolItem"}
    media_pool_item = clip_info.get("mediaPoolItem")
    name_getter = getattr(media_pool_item, "GetName", None)
    if callable(name_getter):
        try:
            safe["mediaPoolItem"] = name_getter()
        except Exception:
            safe["mediaPoolItem"] = "<media_pool_item>"
    elif media_pool_item is not None:
        safe["mediaPoolItem"] = "<media_pool_item>"
    return safe


def _plan_audio_clip_duplicate_infos(source_items: list[Any], target_index: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    clip_infos: list[dict[str, Any]] = []
    source_summaries: list[dict[str, Any]] = []
    for ordinal, item in enumerate(source_items, start=1):
        summary = _fairlight_duplicate_item_summary(item)
        source_summaries.append(summary)
        required_missing: list[str] = []
        media_pool_item = None
        getter = getattr(item, "GetMediaPoolItem", None)
        if callable(getter):
            try:
                media_pool_item = getter()
            except Exception:
                media_pool_item = None
        if media_pool_item is None:
            required_missing.append("TimelineItem.GetMediaPoolItem()")
        start = summary.get("start")
        end = summary.get("end")
        source_start = summary.get("source_start")
        if not isinstance(start, int):
            required_missing.append("TimelineItem.GetStart()")
        if not isinstance(end, int):
            required_missing.append("TimelineItem.GetEnd()")
        if not isinstance(source_start, int):
            required_missing.append("TimelineItem.GetLeftOffset()")
        if required_missing:
            raise CapabilityNegotiationFailed(
                "Fairlight track duplicate with clips requires media-pool backed timeline items with source offsets.",
                details={
                    "capability_id": "fairlight.track_duplicate",
                    "clip_ordinal": ordinal,
                    "clip_summary": summary,
                    "missing_required_native_api": required_missing,
                    "supported_subset_command": "cutagent fairlight track duplicate <index> --empty --no-processing --json",
                    "workaround": "Use the empty duplicate subset, then place or move supported media-pool backed clips explicitly.",
                },
                recoverability="manual",
            )
        duration = int(end) - int(start)
        if duration <= 0:
            raise ValidationError(
                "Fairlight track duplicate with clips requires source clips with positive timeline duration.",
                details={"clip_ordinal": ordinal, "clip_summary": summary, "duration": duration},
                recoverability="manual",
            )
        clip_infos.append(
            {
                "mediaPoolItem": media_pool_item,
                "trackIndex": int(target_index),
                "trackType": "audio",
                "mediaType": 2,
                "recordFrame": int(start),
                "startFrame": int(source_start),
                "endFrame": int(source_start) + duration,
            }
        )
    return clip_infos, source_summaries


def _track_duplicate_supported_subset(
    *,
    include_clips: bool,
    copy_volume: bool = False,
    copy_pan: bool = False,
    copy_clip_eq: bool = False,
    copy_clip_fx: bool = False,
    copy_color: bool = False,
) -> str:
    copied_parts: list[str] = []
    if copy_volume:
        copied_parts.append("volume")
    if copy_pan:
        copied_parts.append("pan")
    if copy_clip_eq and include_clips:
        copied_parts.append("clip_eq")
    if copy_clip_fx and include_clips:
        copied_parts.append("clip_fx")
    if copy_color:
        copied_parts.append("color")
    if copied_parts:
        prefix = "clips" if include_clips else "empty"
        return f"{prefix}_with_{'_'.join(copied_parts)}_no_other_processing"
    return "clips_no_processing" if include_clips else "empty_no_processing"


def duplicate_empty_audio_track(
    conn,
    index: int,
    *,
    include_clips: bool = False,
    copy_volume: bool = False,
    copy_pan: bool = False,
    copy_clip_eq: bool = False,
    copy_clip_fx: bool = False,
    copy_color: bool = False,
) -> Dict[str, Any]:
    """Duplicate Fairlight audio track metadata, optionally copying media-pool backed clips."""
    active_timeline_name = _timeline_name(conn)
    if copy_clip_eq and not include_clips:
        raise ValidationError(
            "Fairlight track duplicate Clip EQ copy requires --include-clips.",
            details={
                "capability_id": "fairlight.track_duplicate",
                "copy_clip_eq": True,
                "include_clips": False,
                "supported_subset_command": (
                    f"cutagent fairlight track duplicate {int(index)} "
                    "--include-clips --no-processing --copy-clip-eq --json"
                ),
            },
            recoverability="not_applicable",
        )
    if copy_clip_fx and not include_clips:
        raise ValidationError(
            "Fairlight track duplicate Clip FX copy requires --include-clips.",
            details={
                "capability_id": "fairlight.track_duplicate",
                "copy_clip_fx": True,
                "include_clips": False,
                "supported_subset_command": (
                    f"cutagent fairlight track duplicate {int(index)} "
                    "--include-clips --no-processing --copy-clip-fx --json"
                ),
            },
            recoverability="not_applicable",
        )
    before_count = _validate_audio_track_index(conn, index)
    source_name = conn.timeline.GetTrackName("audio", index) or ""
    source_format = _read_audio_track_subtype(conn, index)
    normalized_format = str(source_format or "").strip().lower()
    if normalized_format not in FAIRLIGHT_AUDIO_SUBTYPE_BY_TRACK_TYPE:
        raise CapabilityNegotiationFailed(
            "Fairlight empty track duplicate requires audio track format readback.",
            details={
                "capability_id": "fairlight.track_duplicate",
                "index": int(index),
                "readback_track_type": source_format,
                "required_native_api": "Timeline.GetTrackSubType('audio', index)",
                "workaround": (
                    "Use `fairlight add --track-type <format>` when the source track format is known, "
                    "or duplicate the track in DaVinci Resolve."
                ),
            },
        )

    source_items = conn.timeline.GetItemListInTrack("audio", int(index)) or []
    clip_infos: list[dict[str, Any]] = []
    source_item_summaries: list[dict[str, Any]] = []
    if include_clips:
        clip_infos, source_item_summaries = _plan_audio_clip_duplicate_infos(source_items, int(index) + 1)

    volume_source_readback: dict[str, Any] | None = None
    if copy_volume:
        volume_source_readback = read_audio_track_fader_db(conn, index=int(index))
        source_level_db = volume_source_readback.get("level_db")
        if source_level_db is None:
            raise CapabilityNegotiationFailed(
                "Fairlight track duplicate Volume copy requires a common source fader level across every mapped channel lane.",
                details={
                    "capability_id": "fairlight.track_duplicate",
                    "index": int(index),
                    "copy_volume": True,
                    "source_fader_readback": {
                        key: volume_source_readback.get(key)
                        for key in (
                            "track",
                            "channel_count",
                            "channel_levels_db",
                            "level_db",
                            "storage",
                            "offset_source",
                            "db_blob",
                            "set_scope",
                            "verified_set_scope",
                        )
                    },
                    "supported_subset_command": (
                        f"cutagent fairlight track duplicate {int(index)} "
                        f"{'--include-clips' if include_clips else '--empty'} --no-processing "
                        "--copy-volume --json"
                    ),
                    "workaround": "Set target fader lanes explicitly with `fairlight mixer fader --track <index> --level <db>` after duplication.",
                },
                recoverability="manual",
            )

    pan_source_readback: dict[str, Any] | None = None
    if copy_pan:
        pan_source_readback = read_audio_track_pan_db(conn, index=int(index))
        source_pan = pan_source_readback.get("pan")
        if source_pan is None or not pan_source_readback.get("set_supported"):
            raise CapabilityNegotiationFailed(
                "Fairlight track duplicate Pan copy requires a verified mono source pan value.",
                details={
                    "capability_id": "fairlight.track_duplicate",
                    "index": int(index),
                    "copy_pan": True,
                    "source_pan_readback": {
                        key: pan_source_readback.get(key)
                        for key in (
                            "track",
                            "channel_count",
                            "channel_pan_values",
                            "pan",
                            "set_supported",
                            "storage",
                            "offset_source",
                            "db_blob",
                            "verified_set_scope",
                        )
                    },
                    "supported_subset_command": (
                        f"cutagent fairlight track duplicate {int(index)} "
                        f"{'--include-clips' if include_clips else '--empty'} --no-processing "
                        "--copy-pan --json"
                    ),
                    "workaround": "Set mono target pan explicitly with `fairlight mixer pan --track <index> --pan <value>` after duplication.",
                },
                recoverability="manual",
            )

    color_source_readback: dict[str, Any] | None = None
    if copy_color:
        color_source_readback = read_audio_track_color_db(conn, index=int(index))

    target_index = int(index) + 1
    insertion_index = target_index if target_index <= before_count else None
    add_audio_track(conn, normalized_format, index=insertion_index)
    after_count = _wait_for_audio_track_count(conn, previous_count=before_count)
    if after_count <= before_count:
        raise APICallFailed(
            "Audio track duplicate did not appear in timeline readback.",
            details={
                "track_type": "audio",
                "source_index": int(index),
                "target_index": target_index,
                "audio_tracks_before": before_count,
                "audio_tracks_after": after_count,
            },
        )
    created_index = target_index if insertion_index is not None else int(after_count)

    rename_result = True
    if source_name:
        rename_result = bool(conn.timeline.SetTrackName("audio", created_index, source_name))
        if not rename_result:
            raise APICallFailed(
                "Failed to copy Fairlight audio track name to duplicate.",
                details={"source_index": int(index), "created_index": created_index, "source_name": source_name},
            )

    copied_enabled: bool | None = None
    try:
        copied_enabled = bool(conn.timeline.GetIsTrackEnabled("audio", int(index)))
    except Exception:
        copied_enabled = None
    if copied_enabled is not None:
        _set_audio_track_enabled(conn, created_index, copied_enabled)

    copied_locked: bool | None = None
    try:
        copied_locked = bool(conn.timeline.GetIsTrackLocked("audio", int(index)))
    except Exception:
        copied_locked = None

    append_result_items: list[Any] = []
    if include_clips and clip_infos:
        for clip_info in clip_infos:
            clip_info["trackIndex"] = int(created_index)
        appender = getattr(getattr(conn, "media_pool", None), "AppendToTimeline", None)
        if not callable(appender):
            try:
                delete_audio_track(conn, created_index)
            except Exception:
                pass
            raise APICallFailed(
                "MediaPool.AppendToTimeline is not available for Fairlight track duplicate clip copy.",
                details={
                    "required_native_api": "MediaPool.AppendToTimeline",
                    "source_index": int(index),
                    "created_index": int(created_index),
                    "clip_count": len(clip_infos),
                },
                recoverability="manual",
            )
        append_result = appender(clip_infos)
        if not append_result:
            try:
                delete_audio_track(conn, created_index)
            except Exception:
                pass
            raise APICallFailed(
                "MediaPool.AppendToTimeline failed while copying Fairlight track clips.",
                details={
                    "source_index": int(index),
                    "created_index": int(created_index),
                    "clip_infos": [_safe_clip_info_for_output(info) for info in clip_infos],
                    "api_result": append_result,
                },
                recoverability="manual",
            )
        append_result_items = append_result if isinstance(append_result, list) else [append_result]

    if copied_locked is not None:
        _set_audio_track_locked(conn, created_index, copied_locked)

    readback_name = conn.timeline.GetTrackName("audio", created_index) or ""
    readback_format = _read_audio_track_subtype(conn, created_index)
    readback_items = conn.timeline.GetItemListInTrack("audio", created_index) or []
    readback_enabled: bool | None = None
    readback_locked: bool | None = None
    try:
        readback_enabled = bool(conn.timeline.GetIsTrackEnabled("audio", created_index))
    except Exception:
        pass
    try:
        readback_locked = bool(conn.timeline.GetIsTrackLocked("audio", created_index))
    except Exception:
        pass

    appended_summaries = [_fairlight_duplicate_item_summary(item) for item in append_result_items]
    readback_summaries = [_fairlight_duplicate_item_summary(item) for item in readback_items]
    checks = [
        {"name": "track_count_incremented", "ok": int(after_count) == int(before_count) + 1},
        {
            "name": "target_track_empty" if not include_clips else "target_clip_count_matches_source",
            "ok": len(readback_items) == (0 if not include_clips else len(source_items)),
            "source_count": len(source_items),
            "target_count": len(readback_items),
        },
        {"name": "name_copied", "ok": readback_name == source_name},
        {
            "name": "format_copied",
            "ok": readback_format is None or str(readback_format).strip().lower() == normalized_format,
            "skipped": readback_format is None,
        },
        {
            "name": "enabled_copied",
            "ok": readback_enabled is None or copied_enabled is None or readback_enabled == copied_enabled,
            "skipped": readback_enabled is None or copied_enabled is None,
        },
        {
            "name": "locked_copied",
            "ok": readback_locked is None or copied_locked is None or readback_locked == copied_locked,
            "skipped": readback_locked is None or copied_locked is None,
        },
    ]
    if include_clips and source_items:
        source_positions = [(row.get("name"), row.get("start"), row.get("end")) for row in source_item_summaries]
        target_positions = [(row.get("name"), row.get("start"), row.get("end")) for row in readback_summaries]
        checks.extend(
            [
                {
                    "name": "append_result_count_matches_source",
                    "ok": len(append_result_items) == len(source_items),
                    "append_result_count": len(append_result_items),
                    "source_count": len(source_items),
                },
                {
                    "name": "target_clip_positions_match_source",
                    "ok": target_positions == source_positions,
                    "source_items": source_item_summaries,
                    "target_items": readback_summaries,
                },
            ]
        )

    clip_eq_copy: dict[str, Any] | None = None
    if copy_clip_eq:
        saved_before_clip_eq_copy = _save_project_if_available(conn)
        clip_eq_set_result = _copy_track_duplicate_clip_eq_db(
            conn,
            timeline_name=active_timeline_name,
            source_index=int(index),
            target_index=int(created_index),
        )
        clip_eq_verification = clip_eq_set_result.get("verification")
        clip_eq_copy = {
            "requested": True,
            "route": "db_workaround",
            "source_track": int(index),
            "target_track": int(created_index),
            "source_clip_count": clip_eq_set_result.get("source_clip_count"),
            "target_clip_count": clip_eq_set_result.get("target_clip_count"),
            "copied_payload_count": clip_eq_set_result.get("copied_payload_count"),
            "copied_items": clip_eq_set_result.get("copied_items"),
            "verification": clip_eq_verification,
            "saved_before_db_clip_eq_copy": saved_before_clip_eq_copy,
            "project_db_path": clip_eq_set_result.get("project_db_path"),
            "backup_path": clip_eq_set_result.get("backup_path"),
            "steps": clip_eq_set_result.get("steps"),
        }
        checks.append(
            {
                "name": "clip_eq_copied",
                "ok": (clip_eq_verification or {}).get("status") == "verified",
                "source_clip_count": clip_eq_set_result.get("source_clip_count"),
                "target_clip_count": clip_eq_set_result.get("target_clip_count"),
                "copied_payload_count": clip_eq_set_result.get("copied_payload_count"),
            }
        )

    clip_fx_copy: dict[str, Any] | None = None
    if copy_clip_fx:
        saved_before_clip_fx_copy = _save_project_if_available(conn)
        clip_fx_set_result = _copy_track_duplicate_clip_fx_db(
            conn,
            timeline_name=active_timeline_name,
            source_index=int(index),
            target_index=int(created_index),
        )
        clip_fx_verification = clip_fx_set_result.get("verification")
        clip_fx_copy = {
            "requested": True,
            "route": "db_workaround",
            "source_track": int(index),
            "target_track": int(created_index),
            "source_clip_count": clip_fx_set_result.get("source_clip_count"),
            "target_clip_count": clip_fx_set_result.get("target_clip_count"),
            "copied_payload_count": clip_fx_set_result.get("copied_payload_count"),
            "copied_items": clip_fx_set_result.get("copied_items"),
            "verification": clip_fx_verification,
            "saved_before_db_clip_fx_copy": saved_before_clip_fx_copy,
            "project_db_path": clip_fx_set_result.get("project_db_path"),
            "backup_path": clip_fx_set_result.get("backup_path"),
            "steps": clip_fx_set_result.get("steps"),
        }
        checks.append(
            {
                "name": "clip_fx_copied",
                "ok": (clip_fx_verification or {}).get("status") == "verified",
                "source_clip_count": clip_fx_set_result.get("source_clip_count"),
                "target_clip_count": clip_fx_set_result.get("target_clip_count"),
                "copied_payload_count": clip_fx_set_result.get("copied_payload_count"),
            }
        )

    volume_copy: dict[str, Any] | None = None
    if copy_volume and volume_source_readback is not None:
        saved_before_volume_copy = _save_project_if_available(conn)
        source_level_db = float(volume_source_readback["level_db"])
        volume_set_result = set_audio_track_fader_db(conn, index=int(created_index), level_db=source_level_db)
        volume_verification = volume_set_result.get("verification")
        volume_copy = {
            "requested": True,
            "route": "db_workaround",
            "source_track": int(index),
            "target_track": int(created_index),
            "source_level_db": source_level_db,
            "target_level_db": volume_set_result.get("level_db"),
            "source_readback": {
                key: volume_source_readback.get(key)
                for key in (
                    "track",
                    "channel_count",
                    "channel_levels_db",
                    "level_db",
                    "storage",
                    "offset_source",
                    "db_blob",
                    "verified_set_scope",
                    "project_db_path",
                )
            },
            "target_set_result": {
                key: volume_set_result.get(key)
                for key in (
                    "track",
                    "level_db",
                    "raw_value",
                    "previous_channel_levels_db",
                    "channel_count",
                    "channel_offsets",
                    "route",
                    "db_blob",
                    "storage",
                    "offset_source",
                    "project_db_path",
                    "backup_path",
                    "steps",
                )
            },
            "verification": volume_verification,
            "saved_before_db_volume_copy": saved_before_volume_copy,
        }
        checks.append(
            {
                "name": "volume_copied",
                "ok": (volume_verification or {}).get("status") == "verified",
                "source_level_db": source_level_db,
                "target_level_db": volume_set_result.get("level_db"),
            }
        )

    pan_copy: dict[str, Any] | None = None
    if copy_pan and pan_source_readback is not None:
        timeline_restore_before_pan_copy = None
        if copy_volume and active_timeline_name and getattr(conn, "project", None) is not None:
            timeline_restore_before_pan_copy = _switch_timeline_by_name(conn, active_timeline_name)
        saved_before_pan_copy = _save_project_if_available(conn)
        source_pan = float(pan_source_readback["pan"])
        pan_set_result = set_audio_track_pan_db(conn, index=int(created_index), pan=source_pan)
        pan_verification = pan_set_result.get("verification")
        pan_copy = {
            "requested": True,
            "route": "db_workaround",
            "source_track": int(index),
            "target_track": int(created_index),
            "source_pan": source_pan,
            "target_pan": pan_set_result.get("pan"),
            "source_readback": {
                key: pan_source_readback.get(key)
                for key in (
                    "track",
                    "channel_count",
                    "channel_pan_values",
                    "pan",
                    "storage",
                    "offset_source",
                    "db_blob",
                    "verified_set_scope",
                    "project_db_path",
                )
            },
            "target_set_result": {
                key: pan_set_result.get(key)
                for key in (
                    "track",
                    "pan",
                    "raw_value",
                    "previous_channel_pan_values",
                    "channel_count",
                    "channel_offsets",
                    "route",
                    "db_blob",
                    "storage",
                    "offset_source",
                    "project_db_path",
                    "backup_path",
                    "steps",
                )
            },
            "verification": pan_verification,
            "timeline_restore_before_db_pan_copy": timeline_restore_before_pan_copy,
            "saved_before_db_pan_copy": saved_before_pan_copy,
        }
        checks.append(
            {
                "name": "pan_copied",
                "ok": (pan_verification or {}).get("status") == "verified",
                "source_pan": source_pan,
                "target_pan": pan_set_result.get("pan"),
            }
        )

    color_copy: dict[str, Any] | None = None
    if copy_color and color_source_readback is not None:
        timeline_restore_before_color_copy = None
        if (copy_clip_eq or copy_clip_fx or copy_volume or copy_pan) and active_timeline_name and getattr(conn, "project", None) is not None:
            timeline_restore_before_color_copy = _switch_timeline_by_name(conn, active_timeline_name)
        saved_before_color_copy = _save_project_if_available(conn)
        source_color = color_source_readback.get("color") or "Clear"
        color_set_result = set_audio_track_color(conn, int(created_index), str(source_color))
        color_verification = color_set_result.get("verification")
        target_color = color_set_result.get("color") or color_set_result.get("actual_color")
        if color_verification:
            target_color = color_verification.get("actual_color")
        color_copy = {
            "requested": True,
            "route": "db_workaround",
            "source_track": int(index),
            "target_track": int(created_index),
            "source_color": source_color,
            "source_color_value": color_source_readback.get("color_value"),
            "target_color": target_color,
            "target_color_value": (color_verification or {}).get("actual_color_value"),
            "source_readback": {
                key: color_source_readback.get(key)
                for key in (
                    "track_type",
                    "index",
                    "track_id",
                    "track_name",
                    "timeline_name",
                    "color",
                    "color_value",
                    "route",
                    "db_table",
                    "db_field",
                    "readback_route",
                    "project_db_path",
                )
            },
            "target_set_result": {
                key: color_set_result.get(key)
                for key in (
                    "track_type",
                    "index",
                    "track_id",
                    "track_name",
                    "timeline_name",
                    "color",
                    "requested_color",
                    "color_value",
                    "previous_color",
                    "previous_color_value",
                    "route",
                    "db_table",
                    "db_field",
                    "db_storage",
                    "project_db_path",
                    "backup_path",
                    "steps",
                )
            },
            "verification": color_verification,
            "timeline_restore_before_db_color_copy": timeline_restore_before_color_copy,
            "saved_before_db_color_copy": saved_before_color_copy,
        }
        checks.append(
            {
                "name": "color_copied",
                "ok": (color_verification or {}).get("status") == "verified",
                "source_color": source_color,
                "target_color": target_color,
            }
        )

    verified = all(bool(check["ok"]) for check in checks)
    set_verification_status("verified" if verified else "failed")
    if not verified:
        raise APICallFailed(
            "Fairlight track duplicate readback did not match the requested duplicate.",
            details={
                "source_index": int(index),
                "created_index": created_index,
                "source_name": source_name,
                "source_format": normalized_format,
                "readback_name": readback_name,
                "readback_format": readback_format,
                "checks": checks,
            },
        )

    return {
        "action": "fairlight.track.duplicate",
        "track_type": "audio",
        "route": "api_native",
        "supported_subset": (
            _track_duplicate_supported_subset(
                include_clips=include_clips,
                copy_volume=copy_volume,
                copy_pan=copy_pan,
                copy_clip_eq=copy_clip_eq,
                copy_clip_fx=copy_clip_fx,
                copy_color=copy_color,
            )
        ),
        "include_clips": bool(include_clips),
        "include_processing": False,
        "copy_volume": bool(copy_volume),
        "copy_pan": bool(copy_pan),
        "copy_clip_eq": bool(copy_clip_eq),
        "copy_clip_fx": bool(copy_clip_fx),
        "copy_color": bool(copy_color),
        "source_track": {
            "index": int(index),
            "name": source_name,
            "format": normalized_format,
            "enabled": copied_enabled,
            "locked": copied_locked,
        },
        "duplicated_track": {
            "index": created_index,
            "name": readback_name,
            "format": readback_format,
            "enabled": readback_enabled,
            "locked": readback_locked,
            "clip_count": len(readback_items),
            "clips": readback_summaries,
        },
        "native_api": [
            "Timeline.GetTrackSubType('audio', index)",
            'Timeline.AddTrack("audio", {"audioType": track_type, "index": index})'
            if insertion_index is not None
            else 'Timeline.AddTrack("audio", track_type)',
            "Timeline.SetTrackName('audio', index, name)",
            "Timeline.SetTrackEnable('audio', index, enabled)",
            "Timeline.SetTrackLock('audio', index, locked)",
            "Timeline.GetItemListInTrack('audio', index)",
            *(
                [
                    "TimelineItem.GetMediaPoolItem()",
                    "TimelineItem.GetLeftOffset()",
                    "MediaPool.AppendToTimeline([{mediaPoolItem, trackIndex, trackType, mediaType, recordFrame, startFrame, endFrame}])",
                ]
                if include_clips
                else []
            ),
            *(
                [
                    "Disk Project.db readback of source Sm2TiItem.EffectFiltersBA clip EQ payloads",
                    "Disk Project.db mutation of target Sm2TiItem.EffectFiltersBA clip EQ payloads",
                ]
                if copy_clip_eq
                else []
            ),
            *(
                [
                    "Disk Project.db readback of source Sm2TiItem.FieldsBlob FL::ClipFX payloads",
                    "Disk Project.db mutation of target Sm2TiItem.FieldsBlob FL::ClipFX payloads",
                ]
                if copy_clip_fx
                else []
            ),
            *(
                [
                    "Disk Project.db readback of source FLStudioModelBA fader lanes",
                    "Disk Project.db mutation of target FLStudioModelBA fader lanes",
                ]
                if copy_volume
                else []
            ),
            *(
                [
                    "Disk Project.db readback of source FLStudioModelBA mono pan lane",
                    "Disk Project.db mutation of target FLStudioModelBA mono pan lane",
                ]
                if copy_pan
                else []
            ),
            *(
                [
                    "Disk Project.db readback of source Sm2TiTrack.FieldsBlob.Color",
                    "Disk Project.db mutation of target Sm2TiTrack.FieldsBlob.Color through verified track color route",
                ]
                if copy_color
                else []
            ),
        ],
        "clip_copy": {
            "source_clip_count": len(source_items),
            "appended_clip_count": len(append_result_items),
            "source_items": source_item_summaries,
            "append_clip_infos": [_safe_clip_info_for_output(info) for info in clip_infos],
            "appended_items": appended_summaries,
            "target_items": readback_summaries,
        }
        if include_clips
        else None,
        "clip_eq_copy": clip_eq_copy,
        "clip_fx_copy": clip_fx_copy,
        "volume_copy": volume_copy,
        "pan_copy": pan_copy,
        "color_copy": color_copy,
        "audio_tracks_before": before_count,
        "audio_tracks_after": int(after_count),
        "inserted_after_source": created_index == int(index) + 1,
        "verification": {
            "status": "verified",
            "checks": checks,
        },
        "changed": True,
    }


def _effect_filters_digest(payload: bytes | None) -> dict[str, Any]:
    data = bytes(payload or b"")
    return {
        "length": len(data),
        "sha256": hashlib.sha256(data).hexdigest() if data else None,
        "present": bool(data),
    }


def _optional_db_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clip_eq_copy_item_payload(*, source_row: dict[str, Any], target_row: dict[str, Any]) -> dict[str, Any]:
    source_payload = bytes(source_row.get("EffectFiltersBA") or b"")
    target_payload = bytes(target_row.get("EffectFiltersBA") or b"")
    return {
        "source_audio_item_id": str(source_row.get("Sm2TiItem_id") or ""),
        "target_audio_item_id": str(target_row.get("Sm2TiItem_id") or ""),
        "source_name": source_row.get("Name"),
        "target_name": target_row.get("Name"),
        "source_start": _optional_db_int(source_row.get("Start")),
        "target_start": _optional_db_int(target_row.get("Start")),
        "source_duration": _optional_db_int(source_row.get("Duration")),
        "target_duration": _optional_db_int(target_row.get("Duration")),
        "source_effect_filters": _effect_filters_digest(source_payload),
        "target_effect_filters_before": _effect_filters_digest(target_payload),
    }


def _clip_fx_digest(payload: bytes | None) -> dict[str, Any]:
    data = bytes(payload or b"")
    return {
        "length": len(data),
        "sha256": hashlib.sha256(data).hexdigest() if data else None,
        "present": bool(data),
    }


def _clip_fx_state_summary(state: Any | None) -> dict[str, Any]:
    plugins = list(getattr(state, "plugins", []) or []) if state is not None else []
    return {
        "plugin_count": len(plugins),
        "plugins": [
            {
                "plugin_id": getattr(plugin, "plugin_id", None),
                "name": getattr(plugin, "name", None),
                "param_count": len(getattr(plugin, "params", []) or []),
            }
            for plugin in plugins
        ],
        "payload": _clip_fx_digest(getattr(state, "raw_payload", b"") if state is not None else b""),
    }


def _clip_fx_state_matches(source_state: Any | None, target_state: Any | None) -> bool:
    if source_state is None or target_state is None:
        return source_state is None and target_state is None
    source_payload = bytes(getattr(source_state, "raw_payload", b"") or b"")
    target_payload = bytes(getattr(target_state, "raw_payload", b"") or b"")
    if source_payload and target_payload:
        return source_payload == target_payload
    return source_state.to_dict() == target_state.to_dict()


def _clip_fx_copy_item_payload(*, source_row: dict[str, Any], target_row: dict[str, Any], source_state: Any, target_before: Any | None) -> dict[str, Any]:
    return {
        "source_audio_item_id": str(source_row.get("Sm2TiItem_id") or ""),
        "target_audio_item_id": str(target_row.get("Sm2TiItem_id") or ""),
        "source_name": source_row.get("Name"),
        "target_name": target_row.get("Name"),
        "source_start": _optional_db_int(source_row.get("Start")),
        "target_start": _optional_db_int(target_row.get("Start")),
        "source_duration": _optional_db_int(source_row.get("Duration")),
        "target_duration": _optional_db_int(target_row.get("Duration")),
        "source_clip_fx": _clip_fx_state_summary(source_state),
        "target_clip_fx_before": _clip_fx_state_summary(target_before),
    }


def _copy_track_duplicate_clip_eq_db(
    conn,
    *,
    timeline_name: str | None,
    source_index: int,
    target_index: int,
) -> dict[str, Any]:
    if not timeline_name:
        raise APICallFailed("No active timeline is available for Fairlight clip EQ copy.")

    def _writer(connection: sqlite3.Connection, cursor: sqlite3.Cursor, session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        columns = _table_columns(cursor, "Sm2TiItem")
        if "EffectFiltersBA" not in columns:
            raise CapabilityNegotiationFailed(
                "Fairlight clip EQ copy requires Sm2TiItem.EffectFiltersBA in the Disk Project.db.",
                details={"table": "Sm2TiItem", "column": "EffectFiltersBA"},
                recoverability="manual",
            )
        sequence = _fetch_timeline_sequence(cursor, timeline_name)
        tracks = _fetch_audio_track_rows(cursor, sequence=sequence)
        _validate_audio_track_db_index(tracks, int(source_index))
        _validate_audio_track_db_index(tracks, int(target_index))
        source_track_id = str(tracks[int(source_index) - 1].get("Sm2TiTrack_id") or "")
        target_track_id = str(tracks[int(target_index) - 1].get("Sm2TiTrack_id") or "")
        source_rows = _fetch_audio_items_for_track(cursor, track_id=source_track_id)
        target_rows = _fetch_audio_items_for_track(cursor, track_id=target_track_id)
        if len(source_rows) != len(target_rows):
            raise APICallFailed(
                "Fairlight clip EQ copy could not match source and target clip counts.",
                details={
                    "timeline_name": timeline_name,
                    "source_index": int(source_index),
                    "target_index": int(target_index),
                    "source_clip_count": len(source_rows),
                    "target_clip_count": len(target_rows),
                },
                recoverability="manual",
            )
        copied_items: list[dict[str, Any]] = []
        changed_count = 0
        for source_row, target_row in zip(source_rows, target_rows):
            source_payload = bytes(source_row.get("EffectFiltersBA") or b"")
            target_payload = bytes(target_row.get("EffectFiltersBA") or b"")
            if source_payload and not audio_eq_db.is_supported_audio_eq_effect_filters(source_payload):
                raise CapabilityNegotiationFailed(
                    "Fairlight track duplicate Clip EQ copy found an unrecognized source EffectFiltersBA payload.",
                    details={
                        "capability_id": "fairlight.track_duplicate",
                        "source_audio_item_id": str(source_row.get("Sm2TiItem_id") or ""),
                        "source_name": source_row.get("Name"),
                        "source_effect_filters": _effect_filters_digest(source_payload),
                        "supported_scope": "verified archived clip EQ EffectFiltersBA payloads only",
                        "workaround": "Duplicate the track without --copy-clip-eq, then apply supported clip audio-eq settings explicitly to the target clip.",
                    },
                    recoverability="manual",
                )
            item_payload = _clip_eq_copy_item_payload(source_row=source_row, target_row=target_row)
            cursor.execute(
                "UPDATE Sm2TiItem SET EffectFiltersBA = ? WHERE Sm2TiItem_id = ?",
                (source_payload, str(target_row.get("Sm2TiItem_id") or "")),
            )
            if source_payload != target_payload:
                changed_count += 1
            copied_items.append(item_payload)
        return {
            "action": "fairlight.track.duplicate.copy_clip_eq",
            "timeline_name": timeline_name,
            "source_index": int(source_index),
            "target_index": int(target_index),
            "source_track_id": source_track_id,
            "target_track_id": target_track_id,
            "source_clip_count": len(source_rows),
            "target_clip_count": len(target_rows),
            "copied_payload_count": len(copied_items),
            "changed_payload_count": changed_count,
            "copied_items": copied_items,
        }

    def _verifier(fresh_conn, mutation_result: dict[str, Any], session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        api_timeline_switch: dict[str, Any] | None = None
        try:
            api_timeline_switch = _switch_timeline_by_name(fresh_conn, timeline_name)
        except Exception:
            api_timeline_switch = None
        connection = sqlite3.connect(session.project_db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            cursor = connection.cursor()
            sequence = _fetch_timeline_sequence(cursor, timeline_name)
            tracks = _fetch_audio_track_rows(cursor, sequence=sequence)
            _validate_audio_track_db_index(tracks, int(source_index))
            _validate_audio_track_db_index(tracks, int(target_index))
            source_track_id = str(tracks[int(source_index) - 1].get("Sm2TiTrack_id") or "")
            target_track_id = str(tracks[int(target_index) - 1].get("Sm2TiTrack_id") or "")
            source_rows = _fetch_audio_items_for_track(cursor, track_id=source_track_id)
            target_rows = _fetch_audio_items_for_track(cursor, track_id=target_track_id)
        finally:
            connection.close()
        count_ok = len(source_rows) == len(target_rows) == int(mutation_result.get("copied_payload_count") or 0)
        item_checks: list[dict[str, Any]] = []
        for source_row, target_row in zip(source_rows, target_rows):
            source_digest = _effect_filters_digest(bytes(source_row.get("EffectFiltersBA") or b""))
            target_digest = _effect_filters_digest(bytes(target_row.get("EffectFiltersBA") or b""))
            item_checks.append(
                {
                    "name": "clip_eq_payload_match",
                    "source_audio_item_id": str(source_row.get("Sm2TiItem_id") or ""),
                    "target_audio_item_id": str(target_row.get("Sm2TiItem_id") or ""),
                    "source_start": _optional_db_int(source_row.get("Start")),
                    "target_start": _optional_db_int(target_row.get("Start")),
                    "source_effect_filters": source_digest,
                    "target_effect_filters": target_digest,
                    "ok": source_digest == target_digest,
                }
            )
        ok = bool(count_ok and all(check["ok"] for check in item_checks))
        verification = {
            "status": "verified" if ok else "failed",
            "timeline_name": timeline_name,
            "source_index": int(source_index),
            "target_index": int(target_index),
            "api_timeline_switch": api_timeline_switch,
            "checks": [
                {
                    "name": "source_target_clip_counts_match",
                    "ok": count_ok,
                    "source_clip_count": len(source_rows),
                    "target_clip_count": len(target_rows),
                    "expected_count": int(mutation_result.get("copied_payload_count") or 0),
                },
                *item_checks,
            ],
        }
        if not ok:
            raise APICallFailed(
                "Fairlight clip EQ copy verification failed after project reopen.",
                details={"verification": verification},
                recoverability="manual",
            )
        return verification

    return db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Fairlight track duplicate clip EQ copy",
        writer=_writer,
        verifier=_verifier,
        allow_project_name_inference=True,
    )


def _copy_track_duplicate_clip_fx_db(
    conn,
    *,
    timeline_name: str | None,
    source_index: int,
    target_index: int,
) -> dict[str, Any]:
    if not timeline_name:
        raise APICallFailed("No active timeline is available for Fairlight clip FX copy.")

    def _writer(connection: sqlite3.Connection, cursor: sqlite3.Cursor, session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        columns = _table_columns(cursor, "Sm2TiItem")
        if "FieldsBlob" not in columns:
            raise CapabilityNegotiationFailed(
                "Fairlight clip FX copy requires Sm2TiItem.FieldsBlob in the Disk Project.db.",
                details={"table": "Sm2TiItem", "column": "FieldsBlob"},
                recoverability="manual",
            )
        sequence = _fetch_timeline_sequence(cursor, timeline_name)
        tracks = _fetch_audio_track_rows(cursor, sequence=sequence)
        _validate_audio_track_db_index(tracks, int(source_index))
        _validate_audio_track_db_index(tracks, int(target_index))
        source_track_id = str(tracks[int(source_index) - 1].get("Sm2TiTrack_id") or "")
        target_track_id = str(tracks[int(target_index) - 1].get("Sm2TiTrack_id") or "")
        source_rows = _fetch_audio_items_for_track(cursor, track_id=source_track_id)
        target_rows = _fetch_audio_items_for_track(cursor, track_id=target_track_id)
        if len(source_rows) != len(target_rows):
            raise APICallFailed(
                "Fairlight clip FX copy could not match source and target clip counts.",
                details={
                    "timeline_name": timeline_name,
                    "source_index": int(source_index),
                    "target_index": int(target_index),
                    "source_clip_count": len(source_rows),
                    "target_clip_count": len(target_rows),
                },
                recoverability="manual",
            )
        copied_items: list[dict[str, Any]] = []
        changed_count = 0
        empty_source_count = 0
        for source_row, target_row in zip(source_rows, target_rows):
            source_clip_id = str(source_row.get("Sm2TiItem_id") or "")
            target_clip_id = str(target_row.get("Sm2TiItem_id") or "")
            source_state = audio_clip_fx.read_clip_fx_from_db(cursor, source_clip_id)
            target_state_before = audio_clip_fx.read_clip_fx_from_db(cursor, target_clip_id)
            if source_state is None or not bytes(getattr(source_state, "raw_payload", b"") or b""):
                empty_source_count += 1
                continue
            if target_state_before is not None:
                raise CapabilityNegotiationFailed(
                    "Fairlight track duplicate Clip FX copy found an existing target FL::ClipFX payload.",
                    details={
                        "capability_id": "fairlight.track_duplicate",
                        "source_audio_item_id": source_clip_id,
                        "target_audio_item_id": target_clip_id,
                        "source_clip_fx": _clip_fx_state_summary(source_state),
                        "target_clip_fx_before": _clip_fx_state_summary(target_state_before),
                        "supported_scope": "copy source FL::ClipFX payloads only onto duplicate clips that do not already contain FL::ClipFX",
                        "workaround": "Remove target clip FX first or duplicate without --copy-clip-fx and apply supported clip FX explicitly.",
                    },
                    recoverability="manual",
                )
            target_fieldsblob = bytes(target_row.get("FieldsBlob") or b"")
            try:
                new_fieldsblob = audio_clip_fx.insert_clip_fx_into_fieldsblob(
                    target_fieldsblob,
                    bytes(getattr(source_state, "raw_payload", b"") or b""),
                )
            except Exception as exc:
                raise CapabilityNegotiationFailed(
                    "Fairlight track duplicate Clip FX copy could not insert FL::ClipFX while preserving the target FieldsBlob.",
                    details={
                        "capability_id": "fairlight.track_duplicate",
                        "source_audio_item_id": source_clip_id,
                        "target_audio_item_id": target_clip_id,
                        "source_clip_fx": _clip_fx_state_summary(source_state),
                        "target_clip_fx_before": _clip_fx_state_summary(target_state_before),
                        "error": str(exc),
                    },
                    recoverability="manual",
                ) from exc
            cursor.execute(
                "UPDATE Sm2TiItem SET FieldsBlob = ? WHERE Sm2TiItem_id = ?",
                (new_fieldsblob, target_clip_id),
            )
            changed_count += 1
            copied_items.append(
                _clip_fx_copy_item_payload(
                    source_row=source_row,
                    target_row=target_row,
                    source_state=source_state,
                    target_before=target_state_before,
                )
            )
        return {
            "action": "fairlight.track.duplicate.copy_clip_fx",
            "timeline_name": timeline_name,
            "source_index": int(source_index),
            "target_index": int(target_index),
            "source_track_id": source_track_id,
            "target_track_id": target_track_id,
            "source_clip_count": len(source_rows),
            "target_clip_count": len(target_rows),
            "copied_payload_count": len(copied_items),
            "changed_payload_count": changed_count,
            "empty_source_count": empty_source_count,
            "copied_items": copied_items,
        }

    def _verifier(fresh_conn, mutation_result: dict[str, Any], session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        api_timeline_switch: dict[str, Any] | None = None
        try:
            api_timeline_switch = _switch_timeline_by_name(fresh_conn, timeline_name)
        except Exception:
            api_timeline_switch = None
        connection = sqlite3.connect(session.project_db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            cursor = connection.cursor()
            sequence = _fetch_timeline_sequence(cursor, timeline_name)
            tracks = _fetch_audio_track_rows(cursor, sequence=sequence)
            _validate_audio_track_db_index(tracks, int(source_index))
            _validate_audio_track_db_index(tracks, int(target_index))
            source_track_id = str(tracks[int(source_index) - 1].get("Sm2TiTrack_id") or "")
            target_track_id = str(tracks[int(target_index) - 1].get("Sm2TiTrack_id") or "")
            source_rows = _fetch_audio_items_for_track(cursor, track_id=source_track_id)
            target_rows = _fetch_audio_items_for_track(cursor, track_id=target_track_id)
            item_checks: list[dict[str, Any]] = []
            copied_count = 0
            for source_row, target_row in zip(source_rows, target_rows):
                source_state = audio_clip_fx.read_clip_fx_from_db(cursor, str(source_row.get("Sm2TiItem_id") or ""))
                target_state = audio_clip_fx.read_clip_fx_from_db(cursor, str(target_row.get("Sm2TiItem_id") or ""))
                has_source_fx = source_state is not None and bool(bytes(getattr(source_state, "raw_payload", b"") or b""))
                if not has_source_fx:
                    continue
                copied_count += 1
                item_checks.append(
                    {
                        "name": "clip_fx_payload_match",
                        "ok": _clip_fx_state_matches(source_state, target_state),
                        "source_audio_item_id": str(source_row.get("Sm2TiItem_id") or ""),
                        "target_audio_item_id": str(target_row.get("Sm2TiItem_id") or ""),
                        "source_clip_fx": _clip_fx_state_summary(source_state),
                        "target_clip_fx": _clip_fx_state_summary(target_state),
                    }
                )
        finally:
            connection.close()
        count_ok = int(copied_count) == int(mutation_result.get("copied_payload_count") or 0)
        checks = [
            {
                "name": "source_target_clip_counts_match",
                "ok": len(source_rows) == len(target_rows),
                "source_clip_count": len(source_rows),
                "target_clip_count": len(target_rows),
            },
            {
                "name": "copied_payload_count_matches_source_fx_count",
                "ok": count_ok,
                "copied_payload_count": mutation_result.get("copied_payload_count"),
                "source_fx_count": copied_count,
            },
            *item_checks,
        ]
        ok = all(bool(check["ok"]) for check in checks)
        verification = {
            "status": "verified" if ok else "failed",
            "timeline_name": timeline_name,
            "source_index": int(source_index),
            "target_index": int(target_index),
            "api_timeline_switch": api_timeline_switch,
            "checks": checks,
        }
        if not ok:
            raise APICallFailed(
                "Fairlight clip FX copy verification failed after project reopen.",
                details={"verification": verification},
                recoverability="manual",
            )
        return verification

    return db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Fairlight track duplicate clip FX copy",
        writer=_writer,
        verifier=_verifier,
        allow_project_name_inference=True,
    )


def mute_audio_track(conn, index: int) -> None:
    """
    Mute an audio track.
    
    Args:
        conn: ResolveConnection instance
        index: Track index
    """
    _set_audio_track_enabled(conn, index, False)


def unmute_audio_track(conn, index: int) -> None:
    """
    Unmute an audio track.
    
    Args:
        conn: ResolveConnection instance
        index: Track index
    """
    _set_audio_track_enabled(conn, index, True)


def lock_audio_track(conn, index: int) -> None:
    """
    Lock an audio track.
    
    Args:
        conn: ResolveConnection instance
        index: Track index
    """
    _set_audio_track_locked(conn, index, True)


def unlock_audio_track(conn, index: int) -> None:
    """
    Unlock an audio track.
    
    Args:
        conn: ResolveConnection instance
        index: Track index
    """
    _set_audio_track_locked(conn, index, False)


def list_audio_track_items(conn, index: int) -> List[Dict[str, Any]]:
    """
    List audio clips on a track.
    
    Args:
        conn: ResolveConnection instance
        index: Track index
    
    Returns:
        List of clip info dicts
    """
    _validate_audio_track_index(conn, index)
    clip_items = conn.timeline.GetItemListInTrack("audio", index) or []

    rows = []
    for item in clip_items:
        name = item.GetName() if hasattr(item, "GetName") else "?"
        start = item.GetStart() if hasattr(item, "GetStart") else ""
        end = item.GetEnd() if hasattr(item, "GetEnd") else ""
        rows.append({"name": name, "start": start, "end": end})

    return rows


def _optional_track_mixer_readbacks(conn, index: int) -> tuple[dict[str, Any], dict[str, Any]]:
    mixer: dict[str, Any] = {}
    field_metadata: dict[str, Any] = {}

    try:
        fader = read_audio_track_fader_db(conn, index=index)
    except (APICallFailed, CapabilityNegotiationFailed, ValidationError, sqlite3.Error, OSError, zlib.error, AttributeError) as exc:
        field_metadata["fader_db"] = _optional_db_readback_error(exc)
    else:
        mixer["fader"] = {
            "level_db": fader.get("level_db"),
            "channel_levels_db": fader.get("channel_levels_db"),
            "raw_values": fader.get("raw_values"),
            "channel_offsets": fader.get("channel_offsets"),
            "channel_count": fader.get("channel_count"),
            "route": fader.get("route"),
            "storage": fader.get("storage"),
            "set_supported": fader.get("set_supported"),
            "set_scope": fader.get("set_scope"),
            "verified_set_scope": fader.get("verified_set_scope"),
            "set_precondition": fader.get("set_precondition"),
        }
        field_metadata["fader_db"] = _optional_db_readback_success(fader)

    try:
        pan = read_audio_track_pan_db(conn, index=index)
    except (APICallFailed, CapabilityNegotiationFailed, ValidationError, sqlite3.Error, OSError, zlib.error, AttributeError) as exc:
        field_metadata["pan"] = _optional_db_readback_error(exc)
    else:
        mixer["pan"] = {
            "pan": pan.get("pan"),
            "channel_pan_values": pan.get("channel_pan_values"),
            "raw_values": pan.get("raw_values"),
            "channel_offsets": pan.get("channel_offsets"),
            "channel_count": pan.get("channel_count"),
            "route": pan.get("route"),
            "storage": pan.get("storage"),
            "set_supported": pan.get("set_supported"),
            "verified_set_scope": pan.get("verified_set_scope"),
            "set_blocker": pan.get("set_blocker"),
        }
        field_metadata["pan"] = _optional_db_readback_success(pan)

    if mixer:
        mixer["source"] = "Sm2Sequence.FieldsBlob.FLStudioModelBA"
        mixer["read_consistency"] = next(
            (
                info.get("read_consistency")
                for info in field_metadata.values()
                if isinstance(info, dict) and info.get("available")
            ),
            None,
        )
    return mixer, field_metadata


def _optional_db_readback_success(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "available": True,
        "route": state.get("route"),
        "db_blob": state.get("db_blob"),
        "storage": state.get("storage"),
        "read_consistency": state.get("read_consistency"),
        "project_db_path": state.get("project_db_path"),
        "set_supported": state.get("set_supported"),
        "set_scope": state.get("set_scope"),
        "verified_set_scope": state.get("verified_set_scope"),
        "set_blocker": state.get("set_blocker"),
    }


def _optional_db_readback_error(exc: Exception) -> dict[str, Any]:
    return {
        "available": False,
        "code": getattr(exc, "code", exc.__class__.__name__),
        "message": str(exc),
        "recoverability": getattr(exc, "recoverability", None),
        "details": getattr(exc, "details", {}),
    }


def get_audio_track_info(conn, index: int) -> Dict[str, Any]:
    """
    Get audio track details.
    
    Args:
        conn: ResolveConnection instance
        index: Track index
    
    Returns:
        Dictionary of track info
    """
    try:
        _validate_audio_track_index(conn, index)
    except ValidationError as exc:
        fallback_rows = _list_audio_tracks_from_disk_db(conn, api_audio_track_count=0)
        if 1 <= index <= len(fallback_rows):
            row = dict(fallback_rows[index - 1])
            row["native_readback"] = {
                "available": False,
                "reason": "runtime_reported_zero_audio_tracks",
                "readback_command": "cutagent fairlight tracks --json",
            }
            set_verification_status("verified")
            return row
        raise exc
    data = {
        "index": index,
        "name": conn.timeline.GetTrackName("audio", index) or "",
    }
    subtype = _read_audio_track_subtype(conn, index)
    if subtype:
        data["format"] = subtype

    try:
        data["enabled"] = conn.timeline.GetIsTrackEnabled("audio", index)
    except Exception:
        pass

    try:
        data["locked"] = conn.timeline.GetIsTrackLocked("audio", index)
    except Exception:
        pass

    items = conn.timeline.GetItemListInTrack("audio", index) or []
    data["clip_count"] = len(items)
    data["native_readback"] = {
        "name": "Timeline.GetTrackName('audio', index)",
        "format": "Timeline.GetTrackSubType('audio', index)" if subtype else None,
        "enabled": "Timeline.GetIsTrackEnabled('audio', index)" if "enabled" in data else None,
        "locked": "Timeline.GetIsTrackLocked('audio', index)" if "locked" in data else None,
        "items": "Timeline.GetItemListInTrack('audio', index)",
    }
    mixer, db_readbacks = _optional_track_mixer_readbacks(conn, index)
    if mixer:
        data["mixer"] = mixer
    display = _optional_track_display_readback(conn, index)
    if display:
        data["display"] = {"height": display}
    try:
        bus_readback = read_fairlight_bus_list_db(conn)
    except Exception as exc:  # best-effort metadata; track info should not fail when bus labels are unmapped.
        bus_db_readback = _optional_db_readback_error(exc)
    else:
        data["bus_readback"] = bus_readback
        bus_db_readback = _optional_db_readback_success(bus_readback)
    data["unsupported_native_fields"] = [
        {
            "field": "fader_db",
            "capability_id": "fairlight.fader",
            "reason": "Fairlight mixer fader readback is not exposed by the DaVinci Resolve scripting API.",
            "db_readback": db_readbacks.get("fader_db"),
        },
        {
            "field": "pan",
            "capability_id": "fairlight.pan",
            "reason": "Fairlight track pan readback is not exposed by the DaVinci Resolve scripting API.",
            "db_readback": db_readbacks.get("pan"),
        },
        {
            "field": "automation",
            "capability_id": "fairlight.automation",
            "reason": "Fairlight automation lanes and keyframes are not exposed by the DaVinci Resolve scripting API.",
        },
        {
            "field": "inserts",
            "capability_id": "fairlight.plugin_routing",
            "reason": "Fairlight plugin insert slots are not exposed by the DaVinci Resolve scripting API.",
        },
        {
            "field": "sends",
            "capability_id": "fairlight.sends",
            "reason": "Fairlight send slots are not exposed by the DaVinci Resolve scripting API.",
        },
        {
            "field": "routing",
            "capability_id": "fairlight.bus_routing",
            "reason": "Fairlight bus/FlexBus routing readback is not exposed by the DaVinci Resolve scripting API.",
            "db_readback": bus_db_readback,
        },
        {
            "field": "record_arm",
            "capability_id": "fairlight.recording",
            "reason": "Fairlight record-arm readback is not exposed by the DaVinci Resolve scripting API.",
        },
        {
            "field": "input_monitor",
            "capability_id": "fairlight.input_monitoring",
            "reason": "Fairlight input monitoring readback is not exposed by the DaVinci Resolve scripting API.",
        },
    ]

    return data


def get_fairlight_limitations() -> Dict[str, Any]:
    """
    Get information about Fairlight API limitations.
    
    Returns:
        Dictionary describing what is and isn't available
    """
    return {
        "available": [
            "List/add/rename audio tracks",
            "Mute/unmute/lock/unlock tracks",
            "Solo an audio track by enabling it and disabling other audio tracks",
            "List audio clips on tracks",
            "Basic clip properties",
        ],
        "db_backed_available": [
            "Audio track format/order, display height, mixer fader, and mono pan read/write with Disk DB verification",
            "Main/Main 1 sequence output gain context read/write via Sm2Sequence.OutputAudioGain",
            "Audio clip gain, pan, fades, crossfades, timing, source range, and selected clip FX parameter writes",
            "Stored Fairlight bus labels, send tokens, automation tokens, groups, VCAs, record/ADR/I/O/meter/loudness/elastic/waveform context, plugin catalog, and plugin slot probes",
            "Sound Library read/index/source-list/source-remove/source-rebuild/delete routes plus DB-indexed native insert verification",
            "Bounce mix/track routes that render through DaVinci Resolve and verify imported/appended audio",
        ],
        "not_available": [
            "Track color unless the runtime exposes Timeline.SetTrackColor",
            "Non-main bus/FlexBus fader and routing graph mutations",
            "Real automation curve/keyframe write parity",
            "Live audio meter value readback",
            "Fairlight FX/plugin insert slot add/remove/move/replace parity",
        ],
        "note": "DaVinci Resolve Scripting API has limited Fairlight support. "
                "Some advanced audio workflows still require DB-backed commands or remain unsupported.",
    }


def list_fairlight_presets(conn) -> List[Dict[str, Any]]:
    """List Fairlight presets available in DaVinci Resolve."""
    getter = getattr(conn.resolve, "GetFairlightPresets", None)
    if not getter:
        raise APICallFailed("GetFairlightPresets not available.")

    presets = getter() or []
    rows = []
    for index, preset in enumerate(presets, start=1):
        rows.append({"index": index, "name": str(preset)})
    return rows


def apply_fairlight_preset(conn, name: str) -> Dict[str, Any]:
    """Apply a Fairlight preset to the current timeline."""
    candidates = [
        ("Project.ApplyFairlightPresetToCurrentTimeline", getattr(conn.project, "ApplyFairlightPresetToCurrentTimeline", None)),
        ("Timeline.ApplyFairlightPreset", getattr(conn.timeline, "ApplyFairlightPreset", None)),
    ]
    attempted: list[dict[str, Any]] = []
    for method_name, applier in candidates:
        if not callable(applier):
            attempted.append({"method": method_name, "available": False})
            continue
        try:
            result = applier(name)
        except APICallFailed as exc:
            attempted.append(
                {
                    "method": method_name,
                    "available": True,
                    "error_code": exc.code,
                    "message": str(exc),
                    "details": exc.details,
                }
            )
            continue
        attempted.append({"method": method_name, "available": True, "result": result})
        if result is not False:
            return {
                "name": name,
                "applied": bool(result),
                "method": method_name,
                "attempted_methods": attempted,
            }
    if not any(row.get("available") for row in attempted):
        raise APICallFailed(
            "Fairlight preset apply API not available.",
            details={
                "name": name,
                "required_method": [
                    "Project.ApplyFairlightPresetToCurrentTimeline",
                    "Timeline.ApplyFairlightPreset",
                ],
                "attempted_methods": attempted,
            },
        )
    raise APICallFailed(
        "Failed to apply Fairlight preset.",
        details={"name": name, "attempted_methods": attempted},
    )


def insert_audio_to_current_track(
    conn,
    media_path: str,
    start_offset_in_samples: int = 0,
    duration_in_samples: int = 0,
) -> Dict[str, Any]:
    """Insert audio to the current Fairlight track at the playhead."""
    inserter = getattr(conn.project, "InsertAudioToCurrentTrackAtPlayhead", None)
    if not inserter:
        raise APICallFailed("InsertAudioToCurrentTrackAtPlayhead not available.")
    before_snapshot = _snapshot_audio_items_for_current_track_insert(conn)
    result = inserter(media_path, int(start_offset_in_samples), int(duration_in_samples))
    if result is False:
        raise APICallFailed(
            "Failed to insert audio on current Fairlight track.",
            details={
                "media_path": media_path,
                "start_offset_in_samples": start_offset_in_samples,
                "duration_in_samples": duration_in_samples,
            },
        )
    after_snapshot = _snapshot_audio_items_for_current_track_insert(conn)
    verification = _verify_current_track_insert_snapshot(
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        expected_media_name=Path(str(media_path)).name,
    )
    set_verification_status(str(verification["status"]))
    return {
        "media_path": media_path,
        "start_offset_in_samples": int(start_offset_in_samples),
        "duration_in_samples": int(duration_in_samples),
        "inserted": bool(result),
        "verification": verification,
    }


def _coerce_insert_snapshot_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _audio_insert_item_signature(item: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(item.get("track_index") or ""),
        str(item.get("name") or ""),
        str(item.get("start") if item.get("start") is not None else ""),
        str(item.get("end") if item.get("end") is not None else ""),
    )


def _snapshot_audio_items_for_current_track_insert(conn) -> dict[str, Any]:
    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        return {
            "available": False,
            "reason": "timeline_handle_unavailable",
        }
    try:
        track_count = _audio_track_count(conn)
    except Exception as exc:
        return {
            "available": False,
            "reason": "audio_track_count_unavailable",
            "error": str(exc),
        }

    tracks: list[dict[str, Any]] = []
    total_item_count = 0
    for track_index in range(1, int(track_count) + 1):
        try:
            raw_items = list_audio_track_items(conn, track_index)
        except Exception as exc:
            return {
                "available": False,
                "reason": "audio_track_items_unavailable",
                "track_index": track_index,
                "error": str(exc),
            }
        items: list[dict[str, Any]] = []
        for position, item in enumerate(raw_items, start=1):
            normalized = {
                "track_index": track_index,
                "track_item_index": position,
                "name": item.get("name"),
                "start": _coerce_insert_snapshot_int(item.get("start")),
                "end": _coerce_insert_snapshot_int(item.get("end")),
            }
            if normalized["start"] is not None and normalized["end"] is not None:
                normalized["duration"] = int(normalized["end"]) - int(normalized["start"])
            items.append(normalized)
        total_item_count += len(items)
        tracks.append(
            {
                "index": track_index,
                "item_count": len(items),
                "items": items,
            }
        )

    return {
        "available": True,
        "track_count": int(track_count),
        "total_item_count": total_item_count,
        "tracks": tracks,
    }


def _flatten_audio_insert_snapshot(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for track in snapshot.get("tracks") or []:
        if not isinstance(track, dict):
            continue
        for item in track.get("items") or []:
            if isinstance(item, dict):
                items.append(item)
    return items


def _verify_current_track_insert_snapshot(
    *,
    before_snapshot: dict[str, Any],
    after_snapshot: dict[str, Any],
    expected_media_name: str | None = None,
) -> dict[str, Any]:
    if not before_snapshot.get("available") or not after_snapshot.get("available"):
        return {
            "status": "pending_manual",
            "method": "audio_timeline_snapshot",
            "reason": "timeline_item_readback_unavailable",
            "before_snapshot": before_snapshot,
            "after_snapshot": after_snapshot,
            "checks": [
                {
                    "name": "timeline_item_readback_available",
                    "ok": False,
                    "before_available": bool(before_snapshot.get("available")),
                    "after_available": bool(after_snapshot.get("available")),
                }
            ],
        }

    before_items = _flatten_audio_insert_snapshot(before_snapshot)
    after_items = _flatten_audio_insert_snapshot(after_snapshot)
    before_counts = Counter(_audio_insert_item_signature(item) for item in before_items)
    new_or_changed_items: list[dict[str, Any]] = []
    for item in after_items:
        signature = _audio_insert_item_signature(item)
        if before_counts[signature] > 0:
            before_counts[signature] -= 1
            continue
        new_or_changed_items.append(item)

    count_delta = int(after_snapshot.get("total_item_count") or 0) - int(before_snapshot.get("total_item_count") or 0)
    matched_inserted_items = [
        item
        for item in new_or_changed_items
        if expected_media_name and str(item.get("name") or "") == str(expected_media_name)
    ]
    checks = [
        {
            "name": "audio_item_count_increased",
            "ok": count_delta > 0,
            "before": int(before_snapshot.get("total_item_count") or 0),
            "after": int(after_snapshot.get("total_item_count") or 0),
            "delta": count_delta,
        },
        {
            "name": "new_audio_item_candidate_identified",
            "ok": bool(new_or_changed_items),
            "candidate_count": len(new_or_changed_items),
        },
    ]
    if expected_media_name:
        checks.append(
            {
                "name": "expected_media_name_candidate_found",
                "ok": bool(matched_inserted_items),
                "expected_media_name": expected_media_name,
                "match_count": len(matched_inserted_items),
            }
        )
    if expected_media_name:
        verified = bool(new_or_changed_items) and bool(matched_inserted_items)
        verification_rule = "expected_media_name_changed_candidate"
    else:
        verified = count_delta > 0 and bool(new_or_changed_items)
        verification_rule = "count_increase_for_unknown_media"
    return {
        "status": "verified" if verified else "pending_manual",
        "method": "audio_timeline_snapshot",
        "verification_rule": verification_rule,
        "checks": checks,
        "expected_media_name": expected_media_name,
        "inserted_items": matched_inserted_items if matched_inserted_items else new_or_changed_items,
        "new_or_changed_items": new_or_changed_items,
        "before": {
            "track_count": before_snapshot.get("track_count"),
            "total_item_count": before_snapshot.get("total_item_count"),
        },
        "after": {
            "track_count": after_snapshot.get("track_count"),
            "total_item_count": after_snapshot.get("total_item_count"),
        },
    }


def _slug_for_bounce(value: str | None, *, fallback: str) -> str:
    raw = str(value or fallback).strip() or fallback
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-._")
    return slug or fallback


def _default_bounce_extension(format_name: str) -> str:
    normalized = str(format_name or "").strip().lower()
    if normalized in {"mp4", "mpeg-4", "mpeg4"}:
        return "mp4"
    if normalized in {"quicktime", "mov"}:
        return "mov"
    if normalized in {"wave", "wav"}:
        return "wav"
    if normalized in {"aiff", "aif"}:
        return "aif"
    return normalized.replace(" ", "-") or "audio"


def default_fairlight_bounce_output_path(conn, *, source_label: str, format_name: str = "MP4") -> str:
    export_root = os.environ.get("CUTAGENT_USER_EXPORTS_DIR")
    base_dir = Path(export_root).expanduser() if export_root else Path.home() / "Movies" / "CutAgent Exports"
    timeline_label = _slug_for_bounce(_timeline_name(conn), fallback="timeline")
    source = _slug_for_bounce(source_label, fallback="mix")
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    extension = _default_bounce_extension(format_name)
    return str(base_dir / "fairlight-bounces" / f"{timeline_label}-{source}-{timestamp}.{extension}")


def _resolve_bounce_output_path(conn, output_path: str | None, *, source_label: str, format_name: str) -> str:
    if output_path:
        return str(Path(output_path).expanduser())
    return default_fairlight_bounce_output_path(conn, source_label=source_label, format_name=format_name)


def _normalize_supported_bounce_bus(bus: str | None) -> str:
    if bus is None or not str(bus).strip():
        return "Main"
    normalized = re.sub(r"\s+", " ", str(bus).strip()).lower()
    if normalized in {"main", "main 1", "main out", "main output", "timeline main"}:
        return str(bus).strip()
    raise CapabilityNegotiationFailed(
        "Fairlight bounce mix-to-track currently supports only the main timeline mix.",
        details={
            "capability_id": "fairlight.bounce",
            "requested_bus": bus,
            "supported_bus_selectors": ["Main", "Main 1"],
            "blocker_capability_id": "fairlight.bus_routing",
            "reason": "DaVinci Resolve's scripting API does not expose Fairlight bus/FlexBus render source selection, and no verified DB route exists for non-main bus bounce selection.",
        },
        recoverability="not_applicable",
    )


def _timeline_item_summary_for_bounce(item) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, method in (("name", "GetName"), ("start", "GetStart"), ("end", "GetEnd"), ("duration", "GetDuration")):
        getter = getattr(item, method, None)
        if callable(getter):
            try:
                value = getter()
            except Exception:
                continue
            if key in {"start", "end", "duration"}:
                try:
                    value = int(value)
                except Exception:
                    pass
            summary[key] = value
    return summary


def _import_rendered_audio_to_media_pool(conn, rendered_path: str):
    importer = getattr(getattr(conn, "media_pool", None), "ImportMedia", None)
    if not callable(importer):
        raise APICallFailed(
            "MediaPool.ImportMedia is not available for Fairlight bounce placement.",
            details={"required_native_api": "MediaPool.ImportMedia", "rendered_path": rendered_path},
        )
    imported = importer([str(rendered_path)])
    if not imported:
        raise APICallFailed(
            "MediaPool.ImportMedia did not return imported media for Fairlight bounce placement.",
            details={"rendered_path": rendered_path, "api_result": imported},
        )
    imported_items = imported if isinstance(imported, list) else [imported]
    media_item = imported_items[0]
    return media_item, {
        "native_api": "MediaPool.ImportMedia",
        "path": str(rendered_path),
        "result_count": len(imported_items),
        "media_name": media_item.GetName() if hasattr(media_item, "GetName") else None,
    }


def _append_rendered_audio_to_track(
    conn,
    media_item,
    *,
    destination_track: int,
    record_frame: str | None,
    name_after_append: str | None,
) -> dict[str, Any]:
    _validate_audio_track_index(conn, int(destination_track))
    timeline_start = _timeline_start_frame(conn)
    fps = float(getattr(conn, "fps", 24.0) or 24.0)
    resolved_record_frame = (
        timeline_start
        if record_frame is None
        else parse_record_frame(str(record_frame), fps, timeline_start)
    )
    before_items = list_audio_track_items(conn, int(destination_track))
    clip_info: dict[str, Any] = {
        "mediaPoolItem": media_item,
        "trackIndex": int(destination_track),
        "trackType": "audio",
        "mediaType": 2,
        "recordFrame": int(resolved_record_frame),
    }
    appender = getattr(getattr(conn, "media_pool", None), "AppendToTimeline", None)
    if not callable(appender):
        raise APICallFailed(
            "MediaPool.AppendToTimeline is not available for Fairlight bounce placement.",
            details={"required_native_api": "MediaPool.AppendToTimeline", "clip_info": {k: v for k, v in clip_info.items() if k != "mediaPoolItem"}},
        )
    append_result = appender([clip_info])
    if not append_result:
        raise APICallFailed(
            "MediaPool.AppendToTimeline failed for Fairlight bounce placement.",
            details={"clip_info": {k: v for k, v in clip_info.items() if k != "mediaPoolItem"}, "api_result": append_result},
        )
    appended_items = append_result if isinstance(append_result, list) else [append_result]
    if name_after_append:
        for item in appended_items:
            setter = getattr(item, "SetName", None)
            if callable(setter):
                try:
                    setter(str(name_after_append))
                except Exception:
                    pass
    appended_summaries = [_timeline_item_summary_for_bounce(item) for item in appended_items]
    after_items = list_audio_track_items(conn, int(destination_track))
    count_delta = len(after_items) - len(before_items)
    matching_start = any(
        summary.get("start") == int(resolved_record_frame)
        for summary in appended_summaries
        if "start" in summary
    )
    checks = [
        {
            "name": "append_result_returned",
            "ok": bool(appended_items),
            "append_result_count": len(appended_items),
        },
        {
            "name": "destination_track_item_count_increased",
            "ok": count_delta > 0,
            "before": len(before_items),
            "after": len(after_items),
            "delta": count_delta,
        },
    ]
    if appended_summaries:
        checks.append(
            {
                "name": "appended_item_start_matches_record_frame",
                "ok": matching_start or not any("start" in summary for summary in appended_summaries),
                "record_frame": int(resolved_record_frame),
                "appended_items": appended_summaries,
            }
        )
    verified = all(bool(check["ok"]) for check in checks)
    return {
        "native_api": "MediaPool.AppendToTimeline",
        "destination_track": int(destination_track),
        "record_frame": int(resolved_record_frame),
        "record_frame_ref": record_frame,
        "clip_info": {
            "trackIndex": int(destination_track),
            "trackType": "audio",
            "mediaType": 2,
            "recordFrame": int(resolved_record_frame),
            "mediaPoolItem": media_item.GetName() if hasattr(media_item, "GetName") else None,
        },
        "append_result_count": len(appended_items),
        "appended_items": appended_summaries,
        "item_count_before": len(before_items),
        "item_count_after": len(after_items),
        "verification": {
            "status": "verified" if verified else "pending_manual",
            "checks": checks,
        },
    }


def _resolve_bounce_destination_track(conn, destination_track: int | None, *, create_track_type: str = "stereo") -> tuple[int, dict[str, Any] | None]:
    if destination_track is not None:
        _validate_audio_track_index(conn, int(destination_track))
        return int(destination_track), None

    before_count = _audio_track_count(conn)
    add_audio_track(conn, create_track_type)
    after_count = _wait_for_audio_track_count(conn, previous_count=before_count)
    if after_count <= before_count:
        raise APICallFailed(
            "Fairlight bounce could not create a destination audio track.",
            details={
                "audio_tracks_before": before_count,
                "audio_tracks_after": after_count,
                "requested_track_type": create_track_type,
            },
        )
    return int(after_count), {
        "native_api": 'Timeline.AddTrack("audio", track_type)',
        "requested_track_type": create_track_type,
        "audio_tracks_before": before_count,
        "audio_tracks_after": after_count,
        "created_track_index": int(after_count),
    }


def _place_rendered_bounce_on_track(
    conn,
    *,
    rendered_path: str,
    destination_track: int | None,
    record_frame: str | None,
    clip_name: str | None,
    create_track_type: str,
) -> dict[str, Any]:
    resolved_destination_track, created_track = _resolve_bounce_destination_track(
        conn,
        destination_track,
        create_track_type=create_track_type,
    )
    media_item, import_result = _import_rendered_audio_to_media_pool(conn, rendered_path)
    append_result = _append_rendered_audio_to_track(
        conn,
        media_item,
        destination_track=resolved_destination_track,
        record_frame=record_frame,
        name_after_append=clip_name,
    )
    return {
        "created_destination_track": created_track,
        "import": import_result,
        "append": append_result,
        "destination_track": resolved_destination_track,
        "verification": append_result["verification"],
    }


def bounce_mix_to_track(
    conn,
    *,
    bus: str | None = None,
    destination_track: int | None = None,
    record_frame: str | None = None,
    output_path: str | None = None,
    format: str = "MP4",
    codec: str = "H.264",
    bitdepth: int = 16,
    samplerate: int = 48000,
    clip_name: str | None = None,
    create_track_type: str = "stereo",
) -> dict[str, Any]:
    """Render the main Fairlight mix and place it as an audio-only timeline item."""
    selected_bus = _normalize_supported_bounce_bus(bus)
    resolved_output_path = _resolve_bounce_output_path(
        conn,
        output_path,
        source_label="main-mix",
        format_name=format,
    )
    try:
        rendered_path = render_engine.render_audio(
            conn,
            resolved_output_path,
            format,
            codec,
            bitdepth,
            samplerate,
            None,
        )
    except Exception as exc:
        set_verification_status("failed")
        set_recoverability(getattr(exc, "recoverability", "manual"))
        raise
    placement = _place_rendered_bounce_on_track(
        conn,
        rendered_path=rendered_path,
        destination_track=destination_track,
        record_frame=record_frame,
        clip_name=clip_name or "Fairlight Main Bounce",
        create_track_type=create_track_type,
    )
    verification_status = placement["verification"]["status"]
    set_verification_status("verified" if verification_status == "verified" else "pending_manual")
    set_recoverability("retryable" if verification_status == "verified" else "manual")
    return {
        "action": "fairlight.bounce.mix_to_track",
        "changed": True,
        "route": "render_audio_import_append",
        "source": {"kind": "main_mix", "bus": selected_bus},
        "render": {
            "native_api": [
                "Project.SetCurrentRenderFormatAndCodec",
                "Project.SetRenderSettings",
                "Project.AddRenderJob",
                "Project.StartRendering",
            ],
            "output_path": rendered_path,
            "format": format,
            "codec": codec,
            "bitdepth": int(bitdepth),
            "samplerate": int(samplerate),
        },
        "placement": placement,
    }


def bounce_track_to_track(
    conn,
    *,
    track: int,
    destination_track: int | None = None,
    record_frame: str | None = None,
    output_path: str | None = None,
    format: str = "MP4",
    codec: str = "H.264",
    bitdepth: int = 16,
    samplerate: int = 48000,
    clip_name: str | None = None,
    create_track_type: str = "stereo",
) -> dict[str, Any]:
    """Render one Fairlight track by temporarily soloing it, then place the render on a timeline audio track."""
    _validate_audio_track_index(conn, int(track))
    resolved_output_path = _resolve_bounce_output_path(
        conn,
        output_path,
        source_label=f"track-{int(track)}",
        format_name=format,
    )
    solo_result: dict[str, Any] | None = None
    restore_result: dict[str, Any] | None = None
    rendered_path: str | None = None
    bounce_error: Exception | None = None

    try:
        solo_result = solo_audio_track(conn, int(track))
        rendered_path = render_engine.render_audio(
            conn,
            resolved_output_path,
            format,
            codec,
            bitdepth,
            samplerate,
            None,
        )
    except Exception as exc:
        bounce_error = exc
    finally:
        if solo_result and solo_result.get("previous_states"):
            restore_result = restore_audio_track_states(conn, list(solo_result["previous_states"]))

    if bounce_error is not None:
        set_verification_status("failed")
        set_recoverability(getattr(bounce_error, "recoverability", "manual"))
        raise bounce_error
    if rendered_path is None:
        raise APICallFailed(
            "Fairlight track bounce did not produce a rendered audio path.",
            details={"track": int(track), "output_path": resolved_output_path},
        )

    placement = _place_rendered_bounce_on_track(
        conn,
        rendered_path=rendered_path,
        destination_track=destination_track,
        record_frame=record_frame,
        clip_name=clip_name or f"Fairlight Track {int(track)} Bounce",
        create_track_type=create_track_type,
    )
    verification_status = placement["verification"]["status"]
    set_verification_status("verified" if verification_status == "verified" else "pending_manual")
    set_recoverability("retryable" if verification_status == "verified" else "manual")
    return {
        "action": "fairlight.bounce.track",
        "changed": True,
        "route": "solo_render_audio_import_append",
        "source": {"kind": "track", "track": int(track)},
        "render": {
            "native_api": [
                "Timeline.SetTrackEnable",
                "Project.SetCurrentRenderFormatAndCodec",
                "Project.SetRenderSettings",
                "Project.AddRenderJob",
                "Project.StartRendering",
            ],
            "output_path": rendered_path,
            "format": format,
            "codec": codec,
            "bitdepth": int(bitdepth),
            "samplerate": int(samplerate),
        },
        "solo": solo_result,
        "restore": restore_result,
        "placement": placement,
    }
