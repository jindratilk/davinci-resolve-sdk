from __future__ import annotations

import math
import sqlite3
from types import ModuleType
from typing import Any

from cutagent_cli.errors import APICallFailed, ValidationError
from cutagent_cli.output import set_verification_status
from cutagent_cli.utils.timecode import parse_time_input, seconds_to_frames
from cutagent_cli.core import clip_effects_db, db_session, db_timeline_rows, native_clip_audio

_facade: ModuleType


def _bind_facade(facade: ModuleType) -> None:
    global _facade, AudioGainBatchSelector
    _facade = facade
    AudioGainBatchSelector = facade.AudioGainBatchSelector


def _facade_call(name: str, *args: Any, **kwargs: Any) -> Any:
    return getattr(_facade, name)(*args, **kwargs)


def _timeline_name(*args: Any, **kwargs: Any) -> Any:
    return _facade_call("_timeline_name", *args, **kwargs)


def _timeline_start_frame(*args: Any, **kwargs: Any) -> Any:
    return _facade_call("_timeline_start_frame", *args, **kwargs)


def _fetch_timeline_sequence(*args: Any, **kwargs: Any) -> Any:
    return _facade_call("_fetch_timeline_sequence", *args, **kwargs)


def _fetch_audio_track_ids(*args: Any, **kwargs: Any) -> Any:
    return _facade_call("_fetch_audio_track_ids", *args, **kwargs)


def _fetch_audio_items_for_track(*args: Any, **kwargs: Any) -> Any:
    return _facade_call("_fetch_audio_items_for_track", *args, **kwargs)


def _fetch_audio_item_by_id(*args: Any, **kwargs: Any) -> Any:
    return _facade_call("_fetch_audio_item_by_id", *args, **kwargs)


def _item_matches_selector(*args: Any, **kwargs: Any) -> Any:
    return _facade_call("_item_matches_selector", *args, **kwargs)


def _item_payload(*args: Any, **kwargs: Any) -> Any:
    return _facade_call("_item_payload", *args, **kwargs)


def _audio_item_track_index(*args: Any, **kwargs: Any) -> Any:
    return _facade_call("_audio_item_track_index", *args, **kwargs)


def _int_cell(*args: Any, **kwargs: Any) -> Any:
    return _facade_call("_int_cell", *args, **kwargs)


def _parse_record_ref(*args: Any, **kwargs: Any) -> Any:
    return _facade_call("_parse_record_ref", *args, **kwargs)


def _parse_duration_ref(*args: Any, **kwargs: Any) -> Any:
    return _facade_call("_parse_duration_ref", *args, **kwargs)


def _coerce_int(*args: Any, **kwargs: Any) -> Any:
    return _facade_call("_coerce_int", *args, **kwargs)


def _first_present(*args: Any, **kwargs: Any) -> Any:
    return _facade_call("_first_present", *args, **kwargs)


def normalize_audio_gain_batch_selectors(*args: Any, **kwargs: Any) -> Any:
    return _facade_call("normalize_audio_gain_batch_selectors", *args, **kwargs)


def _patch_audio_track_subtypes_writer(*args: Any, **kwargs: Any) -> Any:
    return _facade_call("_patch_audio_track_subtypes_writer", *args, **kwargs)


def _verify_audio_track_subtypes(*args: Any, **kwargs: Any) -> Any:
    return _facade_call("_verify_audio_track_subtypes", *args, **kwargs)


def inspect_sdk_fairlight_plan_clip_state(conn) -> dict[str, Any]:
    """Read exact clip mutation state for private SDK verification."""
    from .. import audio_clip_fx

    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed("No active timeline is available for Fairlight plan readback.")
    current_database = db_session.resolve_current_disk_project_db(conn)
    connection = sqlite3.connect(str(current_database["project_db_path"]), timeout=5.0)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        sequence = _fetch_timeline_sequence(cursor, timeline_name)
        audio_track_ids = _fetch_audio_track_ids(cursor, sequence=sequence)
        from ..audio_fade_curve import observe_curve
        clips: list[dict[str, Any]] = []
        for track_index, track_id in enumerate(audio_track_ids, start=1):
            for row in _fetch_audio_items_for_track(cursor, track_id=track_id):
                item_id = str(row.get("Sm2TiItem_id") or "")
                if not item_id:
                    raise APICallFailed(
                        "Fairlight plan readback found an audio item without "
                        "native identity."
                    )
                effect_filters = row.get("EffectFiltersBA")
                try:
                    clip_fx = audio_clip_fx.read_clip_fx_from_db(cursor, item_id)
                    effect_plugin_ids = [
                        plugin.plugin_id for plugin in (clip_fx.plugins if clip_fx else [])
                    ]
                except Exception:
                    # Gain/pan/fade plans remain independently readable when
                    # Clip FX decoding is unavailable. Effect plans fail closed
                    # on the explicit null readback in the carrier.
                    effect_plugin_ids = None
                clips.append({
                    "item_id": item_id,
                    "track_index": track_index,
                    "gain_db": clip_effects_db.find_audio_gain_db(effect_filters),
                    "pan": clip_effects_db.find_audio_pan_value(effect_filters),
                    "fade_in_frames": clip_effects_db.find_audio_fade_in_frames(effect_filters),
                    "fade_out_frames": clip_effects_db.find_audio_fade_out_frames(effect_filters),
                    "effect_plugin_ids": effect_plugin_ids,
                    "fade_in_curve": observe_curve(effect_filters, "in"),
                    "fade_out_curve": observe_curve(effect_filters, "out"),
                })
        if native_clip_audio.available(conn):
            by_id = {row['item_id']: row for row in clips}
            for index in range(1, int(conn.timeline.GetTrackCount('audio')) + 1):
                for item in conn.timeline.GetItemListInTrack('audio', index) or []:
                    row = by_id.get(str(item.GetUniqueId()))
                    if row is None:
                        raise APICallFailed('Live audio item is missing from the persisted identity map.')
                    props = native_clip_audio._read(item, 'GetProperties', ('AudioVolume', 'AudioPan'))
                    fades = native_clip_audio._read(item, 'GetFades', ('FadeIn', 'FadeOut'), fades=True)
                    row.update(gain_db=props['AudioVolume'], pan=props['AudioPan'],
                               fade_in_frames=fades['FadeIn'], fade_out_frames=fades['FadeOut'])
        return {"status": "available", "clips": clips}
    finally:
        connection.close()

def _resolve_audio_gain_batch_targets(
    cursor: sqlite3.Cursor,
    *,
    timeline_name: str,
    selectors: list[AudioGainBatchSelector],
    allow_empty: bool,
    allow_multiple: bool,
    gain_db: float,
    timeline_start: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, list[str]]:
    sequence = _fetch_timeline_sequence(cursor, timeline_name)
    audio_track_ids = _fetch_audio_track_ids(cursor, sequence=sequence)
    if not audio_track_ids:
        raise ValidationError(
            "Target timeline has no audio tracks in the DaVinci Resolve Disk project database.",
            details={"timeline_name": timeline_name, "timeline_sequence": sequence},
            recoverability="not_applicable",
        )

    targets_by_id: dict[str, dict[str, Any]] = {}
    selector_results: list[dict[str, Any]] = []
    for selector_index, selector in enumerate(selectors):
        matches: list[dict[str, Any]] = []
        if selector.kind == "item_id":
            item = _fetch_audio_item_by_id(cursor, item_id=str(selector.item_id or ""), audio_track_ids=audio_track_ids)
            matches = [item] if item is not None else []
        else:
            track_index = int(selector.track_index or 0)
            if track_index < 1 or track_index > len(audio_track_ids):
                raise ValidationError(
                    "Audio track index is out of range for the target timeline.",
                    details={
                        "selector_index": selector_index,
                        "track_index": track_index,
                        "available_audio_tracks": len(audio_track_ids),
                    },
                    recoverability="not_applicable",
                )
            track_rows = _fetch_audio_items_for_track(cursor, track_id=audio_track_ids[track_index - 1])
            matches = [
                row
                for row in track_rows
                if _item_matches_selector(row, selector, timeline_start=timeline_start)
            ]

        if not matches and not allow_empty:
            raise ValidationError(
                "Audio-gain selector did not match any audio items.",
                details={"selector_index": selector_index, "selector": selector.raw},
                recoverability="not_applicable",
            )
        if len(matches) > 1 and not allow_multiple:
            raise ValidationError(
                "Audio-gain selector matched multiple audio items.",
                details={
                    "selector_index": selector_index,
                    "selector": selector.raw,
                    "match_count": len(matches),
                    "matches": [
                        {
                            "item_id": str(row.get("Sm2TiItem_id") or ""),
                            "clip_name": str(row.get("Name") or ""),
                            "start": _int_cell(row.get("Start")),
                            "duration": _int_cell(row.get("Duration")),
                        }
                        for row in matches
                    ],
                    "hint": "Pass --allow-multiple to update every matching audio item.",
                },
                recoverability="not_applicable",
            )

        selector_results.append(
            {
                "selector_index": selector_index,
                "selector": selector.raw,
                "match_count": len(matches),
                "item_ids": [str(row.get("Sm2TiItem_id") or "") for row in matches],
            }
        )
        for row in matches:
            item_id = str(row.get("Sm2TiItem_id") or "")
            if item_id and item_id not in targets_by_id:
                targets_by_id[item_id] = row

    targets = [
        _item_payload(cursor, row, audio_track_ids=audio_track_ids, resulting_gain_db=gain_db)
        for row in targets_by_id.values()
    ]
    return targets, selector_results, sequence, audio_track_ids


def _audio_gain_batch_writer(
    *,
    timeline_name: str,
    selectors: list[AudioGainBatchSelector],
    gain_db: float,
    allow_empty: bool,
    allow_multiple: bool,
    timeline_start: int,
):
    def _writer(connection: sqlite3.Connection, cursor: sqlite3.Cursor, session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        targets, selector_results, sequence, _audio_track_ids = _resolve_audio_gain_batch_targets(
            cursor,
            timeline_name=timeline_name,
            selectors=selectors,
            allow_empty=allow_empty,
            allow_multiple=allow_multiple,
            gain_db=gain_db,
            timeline_start=timeline_start,
        )
        for target in targets:
            row = cursor.execute(
                "SELECT EffectFiltersBA, FieldsBlob FROM Sm2TiItem WHERE Sm2TiItem_id = ?",
                (target["item_id"],),
            ).fetchone()
            write = clip_effects_db.merge_audio_effect_chains(
                existing_effect_filters=row["EffectFiltersBA"] if row else None,
                existing_fields_blob=row["FieldsBlob"] if row else None,
                gain_db=gain_db,
            )
            updates: dict[str, object] = {"EffectFiltersBA": write.effect_filters}
            if write.fields_blob is not None:
                updates["FieldsBlob"] = write.fields_blob
            db_timeline_rows.update_row(cursor, "Sm2TiItem", "Sm2TiItem_id", target["item_id"], updates)
        return {
            "action": "fairlight.audio_gain.batch",
            "changed": bool(targets),
            "timeline_name": timeline_name,
            "timeline_sequence": sequence,
            "gain_db": float(gain_db),
            "target_count": len(targets),
            "updated_count": len(targets),
            "updated_items": targets,
            "selector_results": selector_results,
        }

    return _writer


def _verify_audio_gain_batch(
    *,
    expected_gain_db: float,
):
    def _verifier(conn, mutation_result: dict[str, Any], session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        connection = sqlite3.connect(session.project_db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        checks: list[dict[str, Any]] = []
        try:
            cursor = connection.cursor()
            for item in mutation_result.get("updated_items") or []:
                item_id = str(item.get("item_id") or "")
                row = cursor.execute(
                    "SELECT EffectFiltersBA FROM Sm2TiItem WHERE Sm2TiItem_id = ?",
                    (item_id,),
                ).fetchone()
                actual = clip_effects_db.find_audio_gain_db(row["EffectFiltersBA"] if row else None)
                ok = actual is not None and math.isclose(float(actual), float(expected_gain_db), abs_tol=1e-6)
                checks.append(
                    {
                        "name": f"audio_gain_{item_id}",
                        "ok": ok,
                        "item_id": item_id,
                        "expected_gain_db": float(expected_gain_db),
                        "actual_gain_db": actual,
                    }
                )
        finally:
            connection.close()
        return {
            "status": "verified" if all(check["ok"] for check in checks) else "failed",
            "checks": checks,
        }

    return _verifier


def preview_audio_gain_batch(
    conn,
    *,
    gain_db: float,
    selectors: list[dict[str, Any]],
    allow_empty: bool = False,
    allow_multiple: bool = False,
) -> dict[str, Any]:
    """Resolve a batch audio-gain selector set without mutating the project DB."""
    validated_gain = clip_effects_db.validate_audio_gain_db(gain_db)
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed("No active timeline is available for Fairlight audio gain batch.")
    normalized = normalize_audio_gain_batch_selectors(conn, selectors)
    current_database = db_session.resolve_current_disk_project_db(conn)
    db_path = str(current_database["project_db_path"])
    connection = sqlite3.connect(db_path, timeout=5.0)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        targets, selector_results, sequence, _audio_track_ids = _resolve_audio_gain_batch_targets(
            cursor,
            timeline_name=timeline_name,
            selectors=normalized,
            allow_empty=allow_empty,
            allow_multiple=allow_multiple,
            gain_db=validated_gain,
            timeline_start=_timeline_start_frame(conn),
        )
    finally:
        connection.close()
    return {
        "action": "fairlight.audio_gain.batch",
        "changed": False,
        "dry_run": True,
        "timeline_name": timeline_name,
        "timeline_sequence": sequence,
        "gain_db": float(validated_gain),
        "target_count": len(targets),
        "updated_count": 0,
        "updated_items": targets,
        "selector_results": selector_results,
        "verification": {"status": "not_requested", "checks": []},
    }


def apply_audio_gain_batch(
    conn,
    *,
    gain_db: float,
    selectors: list[dict[str, Any]],
    allow_empty: bool = False,
    allow_multiple: bool = False,
) -> dict[str, Any]:
    """Apply a DB-backed audio gain payload to audio items selected by id or record bounds."""
    validated_gain = clip_effects_db.validate_audio_gain_db(gain_db)
    if native_clip_audio.available(conn, gain_db=validated_gain):
        preview = preview_audio_gain_batch(conn, gain_db=validated_gain, selectors=selectors,
                                           allow_empty=allow_empty, allow_multiple=allow_multiple)
        return native_clip_audio.apply_batch_preview(conn, preview, property_key='AudioVolume', value=validated_gain)
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed("No active timeline is available for Fairlight audio gain batch.")
    normalized = normalize_audio_gain_batch_selectors(conn, selectors)
    result = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Fairlight batch audio gain",
        writer=_audio_gain_batch_writer(
            timeline_name=timeline_name,
            selectors=normalized,
            gain_db=validated_gain,
            allow_empty=allow_empty,
            allow_multiple=allow_multiple,
            timeline_start=_timeline_start_frame(conn),
        ),
        verifier=_verify_audio_gain_batch(expected_gain_db=validated_gain),
        allow_project_name_inference=True,
    )
    result["db_session_route"] = result.get("route")
    result["route"] = "db_workaround_audio_gain_batch"
    return result


def apply_audio_gain_entries(
    conn,
    *,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply exact per-item gains in one native batch or one Disk DB session."""
    if not isinstance(entries, list) or not 1 <= len(entries) <= 128:
        raise ValidationError("Fairlight audio gain entries must contain 1 to 128 items.")
    normalized_entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != {"item_id", "gain_db"}:
            raise ValidationError(
                "Each Fairlight audio gain entry must contain item_id and gain_db.",
                details={"index": index},
                recoverability="not_applicable",
            )
        item_id = entry.get("item_id")
        if not isinstance(item_id, str) or not item_id or item_id in seen:
            raise ValidationError(
                "Fairlight audio gain entries require distinct non-empty item identities.",
                details={"index": index, "item_id": item_id},
                recoverability="not_applicable",
            )
        seen.add(item_id)
        normalized_entries.append({
            "item_id": item_id,
            "gain_db": clip_effects_db.validate_audio_gain_db(entry.get("gain_db")),
        })

    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed("No active timeline is available for Fairlight audio gain batch.")
    selectors = normalize_audio_gain_batch_selectors(
        conn, [{"item_id": entry["item_id"]} for entry in normalized_entries]
    )
    gain_by_item_id = {entry["item_id"]: entry["gain_db"] for entry in normalized_entries}
    timeline_start = _timeline_start_frame(conn)

    def resolve_targets(cursor: sqlite3.Cursor) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
        targets, selector_results, sequence, _audio_track_ids = _resolve_audio_gain_batch_targets(
            cursor,
            timeline_name=timeline_name,
            selectors=selectors,
            allow_empty=False,
            allow_multiple=False,
            gain_db=normalized_entries[0]["gain_db"],
            timeline_start=timeline_start,
        )
        for target in targets:
            target["resulting_gain_db"] = gain_by_item_id[target["item_id"]]
        return targets, selector_results, sequence

    def writer(connection: sqlite3.Connection, cursor: sqlite3.Cursor, session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        targets, selector_results, sequence = resolve_targets(cursor)
        for target in targets:
            row = cursor.execute(
                "SELECT EffectFiltersBA, FieldsBlob FROM Sm2TiItem WHERE Sm2TiItem_id = ?",
                (target["item_id"],),
            ).fetchone()
            write = clip_effects_db.merge_audio_effect_chains(
                existing_effect_filters=row["EffectFiltersBA"] if row else None,
                existing_fields_blob=row["FieldsBlob"] if row else None,
                gain_db=target["resulting_gain_db"],
            )
            updates: dict[str, object] = {"EffectFiltersBA": write.effect_filters}
            if write.fields_blob is not None:
                updates["FieldsBlob"] = write.fields_blob
            db_timeline_rows.update_row(cursor, "Sm2TiItem", "Sm2TiItem_id", target["item_id"], updates)
        return {
            "action": "fairlight.audio_gain.batch",
            "changed": bool(targets),
            "timeline_name": timeline_name,
            "timeline_sequence": sequence,
            "target_count": len(targets),
            "updated_count": len(targets),
            "updated_items": targets,
            "selector_results": selector_results,
        }

    def verifier(_conn, mutation_result: dict[str, Any], session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        connection = sqlite3.connect(session.project_db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        checks: list[dict[str, Any]] = []
        try:
            cursor = connection.cursor()
            for item in mutation_result.get("updated_items") or []:
                item_id = item["item_id"]
                expected = item["resulting_gain_db"]
                row = cursor.execute(
                    "SELECT EffectFiltersBA FROM Sm2TiItem WHERE Sm2TiItem_id = ?", (item_id,)
                ).fetchone()
                actual = clip_effects_db.find_audio_gain_db(row["EffectFiltersBA"] if row else None)
                checks.append({
                    "name": f"audio_gain_{item_id}",
                    "ok": actual is not None and math.isclose(float(actual), float(expected), abs_tol=1e-6),
                    "item_id": item_id,
                    "expected_gain_db": float(expected),
                    "actual_gain_db": actual,
                })
        finally:
            connection.close()
        return {"status": "verified" if all(check["ok"] for check in checks) else "failed", "checks": checks}

    if native_clip_audio.available(
        conn, gain_db=max(entry["gain_db"] for entry in normalized_entries)
    ):
        current_database = db_session.resolve_current_disk_project_db(conn)
        connection = sqlite3.connect(str(current_database["project_db_path"]), timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            targets, selector_results, sequence = resolve_targets(connection.cursor())
        finally:
            connection.close()
        preview = {
            "action": "fairlight.audio_gain.batch",
            "changed": False,
            "dry_run": True,
            "timeline_name": timeline_name,
            "timeline_sequence": sequence,
            "target_count": len(targets),
            "updated_count": 0,
            "updated_items": targets,
            "selector_results": selector_results,
            "verification": {"status": "not_requested", "checks": []},
        }
        return native_clip_audio.apply_batch_preview(
            conn, preview, property_key="AudioVolume", value=None
        )

    result = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Fairlight per-item audio gain batch",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    result["db_session_route"] = result.get("route")
    result["route"] = "db_workaround_audio_gain_batch"
    return result


def _audio_pan_item_payload(
    cursor: sqlite3.Cursor,
    row: dict[str, Any],
    *,
    audio_track_ids: list[str],
    resulting_pan: float,
) -> dict[str, Any]:
    previous_pan = clip_effects_db.find_audio_pan_value(row.get("EffectFiltersBA"))
    return {
        "item_id": str(row.get("Sm2TiItem_id") or ""),
        "track_index": _audio_item_track_index(cursor, row, audio_track_ids=audio_track_ids),
        "clip_name": str(row.get("Name") or ""),
        "start": _int_cell(row.get("Start")),
        "duration": _int_cell(row.get("Duration")),
        "previous_pan": previous_pan,
        "resulting_pan": float(resulting_pan),
    }


def _audio_pan_entries(
    conn,
    selectors: list[dict[str, Any]],
    *,
    default_pan: float | None,
) -> list[tuple[AudioGainBatchSelector, float]]:
    normalized = normalize_audio_gain_batch_selectors(
        conn, selectors, operation_label="audio-pan"
    )
    entries: list[tuple[AudioGainBatchSelector, float]] = []
    for index, selector in enumerate(normalized):
        raw = selector.raw or {}
        specified = [
            raw[key]
            for key in ("value", "pan", "pan_value")
            if raw.get(key) is not None
        ]
        if len(specified) > 1:
            raise ValidationError(
                "Audio-pan batch entry specifies the pan value more than once.",
                details={"index": index, "selector": raw},
                recoverability="not_applicable",
            )
        requested = specified[0] if specified else default_pan
        if requested is None:
            raise ValidationError(
                "Each audio-pan batch entry requires a value when no default is supplied.",
                details={"index": index, "selector": raw},
                recoverability="not_applicable",
            )
        try:
            value = clip_effects_db.validate_audio_pan_value(requested)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "Audio-pan batch values must be finite numbers.",
                details={"index": index, "value": requested},
                recoverability="not_applicable",
            ) from exc
        entries.append((selector, value))
    return entries


def _resolve_audio_pan_batch_targets(
    cursor: sqlite3.Cursor,
    *,
    timeline_name: str,
    entries: list[tuple[AudioGainBatchSelector, float]],
    allow_empty: bool,
    allow_multiple: bool,
    timeline_start: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, list[str]]:
    sequence = _fetch_timeline_sequence(cursor, timeline_name)
    audio_track_ids = _fetch_audio_track_ids(cursor, sequence=sequence)
    if not audio_track_ids:
        raise ValidationError(
            "Target timeline has no audio tracks in the DaVinci Resolve Disk project database.",
            details={"timeline_name": timeline_name, "timeline_sequence": sequence},
            recoverability="not_applicable",
        )

    targets_by_id: dict[str, dict[str, Any]] = {}
    selector_results: list[dict[str, Any]] = []
    for selector_index, (selector, pan_value) in enumerate(entries):
        matches: list[dict[str, Any]] = []
        if selector.kind == "item_id":
            item = _fetch_audio_item_by_id(cursor, item_id=str(selector.item_id or ""), audio_track_ids=audio_track_ids)
            matches = [item] if item is not None else []
        else:
            track_index = int(selector.track_index or 0)
            if track_index < 1 or track_index > len(audio_track_ids):
                raise ValidationError(
                    "Audio track index is out of range for the target timeline.",
                    details={
                        "selector_index": selector_index,
                        "track_index": track_index,
                        "available_audio_tracks": len(audio_track_ids),
                    },
                    recoverability="not_applicable",
                )
            track_rows = _fetch_audio_items_for_track(cursor, track_id=audio_track_ids[track_index - 1])
            matches = [
                row
                for row in track_rows
                if _item_matches_selector(row, selector, timeline_start=timeline_start)
            ]

        if not matches and not allow_empty:
            raise ValidationError(
                "Audio-pan selector did not match any audio items.",
                details={"selector_index": selector_index, "selector": selector.raw},
                recoverability="not_applicable",
            )
        if len(matches) > 1 and not allow_multiple:
            raise ValidationError(
                "Audio-pan selector matched multiple audio items.",
                details={
                    "selector_index": selector_index,
                    "selector": selector.raw,
                    "match_count": len(matches),
                    "matches": [
                        {
                            "item_id": str(row.get("Sm2TiItem_id") or ""),
                            "clip_name": str(row.get("Name") or ""),
                            "start": _int_cell(row.get("Start")),
                            "duration": _int_cell(row.get("Duration")),
                        }
                        for row in matches
                    ],
                    "hint": "Pass --allow-multiple to update every matching audio item.",
                },
                recoverability="not_applicable",
            )

        selector_results.append(
            {
                "selector_index": selector_index,
                "selector": selector.raw,
                "pan": float(pan_value),
                "match_count": len(matches),
                "item_ids": [str(row.get("Sm2TiItem_id") or "") for row in matches],
            }
        )
        for row in matches:
            item_id = str(row.get("Sm2TiItem_id") or "")
            if not item_id:
                continue
            existing = targets_by_id.get(item_id)
            if existing is not None and not math.isclose(
                existing["resulting_pan"], pan_value, rel_tol=0.0, abs_tol=1e-9
            ):
                raise ValidationError(
                    "Audio-pan selectors assign conflicting values to one audio item.",
                    details={"item_id": item_id},
                    recoverability="not_applicable",
                )
            if existing is None:
                targets_by_id[item_id] = _audio_pan_item_payload(
                    cursor,
                    row,
                    audio_track_ids=audio_track_ids,
                    resulting_pan=pan_value,
                )

    targets = list(targets_by_id.values())
    return targets, selector_results, sequence, audio_track_ids


def _audio_pan_batch_writer(
    *,
    timeline_name: str,
    entries: list[tuple[AudioGainBatchSelector, float]],
    allow_empty: bool,
    allow_multiple: bool,
    timeline_start: int,
):
    def _writer(connection: sqlite3.Connection, cursor: sqlite3.Cursor, session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        targets, selector_results, sequence, _audio_track_ids = _resolve_audio_pan_batch_targets(
            cursor,
            timeline_name=timeline_name,
            entries=entries,
            allow_empty=allow_empty,
            allow_multiple=allow_multiple,
            timeline_start=timeline_start,
        )
        for target in targets:
            row = cursor.execute(
                "SELECT EffectFiltersBA, FieldsBlob FROM Sm2TiItem WHERE Sm2TiItem_id = ?",
                (target["item_id"],),
            ).fetchone()
            write = clip_effects_db.merge_audio_effect_chains(
                existing_effect_filters=row["EffectFiltersBA"] if row else None,
                existing_fields_blob=row["FieldsBlob"] if row else None,
                pan_value=target["resulting_pan"],
            )
            updates: dict[str, object] = {"EffectFiltersBA": write.effect_filters}
            if write.fields_blob is not None:
                updates["FieldsBlob"] = write.fields_blob
            db_timeline_rows.update_row(cursor, "Sm2TiItem", "Sm2TiItem_id", target["item_id"], updates)
        return {
            "action": "fairlight.audio_pan.batch",
            "changed": bool(targets),
            "timeline_name": timeline_name,
            "timeline_sequence": sequence,
            "pan": float(entries[0][1]) if entries and all(
                math.isclose(value, entries[0][1], rel_tol=0.0, abs_tol=1e-9)
                for _selector, value in entries
            ) else None,
            "target_count": len(targets),
            "updated_count": len(targets),
            "updated_items": targets,
            "selector_results": selector_results,
        }

    return _writer


def _verify_audio_pan_batch():
    def _verifier(conn, mutation_result: dict[str, Any], session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        connection = sqlite3.connect(session.project_db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        checks: list[dict[str, Any]] = []
        try:
            cursor = connection.cursor()
            for item in mutation_result.get("updated_items") or []:
                item_id = str(item.get("item_id") or "")
                expected_pan = item.get("resulting_pan")
                row = cursor.execute(
                    "SELECT EffectFiltersBA FROM Sm2TiItem WHERE Sm2TiItem_id = ?",
                    (item_id,),
                ).fetchone()
                actual = clip_effects_db.find_audio_pan_value(row["EffectFiltersBA"] if row else None)
                ok = actual is not None and math.isclose(float(actual), float(expected_pan), abs_tol=1e-6)
                checks.append(
                    {
                        "name": f"audio_pan_{item_id}",
                        "ok": ok,
                        "item_id": item_id,
                        "expected_pan": float(expected_pan),
                        "actual_pan": actual,
                    }
                )
        finally:
            connection.close()
        return {
            "status": "verified" if all(check["ok"] for check in checks) else "failed",
            "checks": checks,
        }

    return _verifier


def preview_audio_pan_batch(
    conn,
    *,
    pan_value: float | None,
    selectors: list[dict[str, Any]],
    allow_empty: bool = False,
    allow_multiple: bool = False,
) -> dict[str, Any]:
    """Resolve a batch audio-pan selector set without mutating the project DB."""
    validated_pan = (
        None if pan_value is None else clip_effects_db.validate_audio_pan_value(pan_value)
    )
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed("No active timeline is available for Fairlight audio pan batch.")
    entries = _audio_pan_entries(conn, selectors, default_pan=validated_pan)
    current_database = db_session.resolve_current_disk_project_db(conn)
    db_path = str(current_database["project_db_path"])
    connection = sqlite3.connect(db_path, timeout=5.0)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        targets, selector_results, sequence, _audio_track_ids = _resolve_audio_pan_batch_targets(
            cursor,
            timeline_name=timeline_name,
            entries=entries,
            allow_empty=allow_empty,
            allow_multiple=allow_multiple,
            timeline_start=_timeline_start_frame(conn),
        )
    finally:
        connection.close()
    return {
        "action": "fairlight.audio_pan.batch",
        "changed": False,
        "dry_run": True,
        "timeline_name": timeline_name,
        "timeline_sequence": sequence,
        "pan": float(validated_pan) if validated_pan is not None else None,
        "target_count": len(targets),
        "updated_count": 0,
        "updated_items": targets,
        "selector_results": selector_results,
        "verification": {"status": "not_requested", "checks": []},
    }


def apply_audio_pan_batch(
    conn,
    *,
    pan_value: float | None,
    selectors: list[dict[str, Any]],
    allow_empty: bool = False,
    allow_multiple: bool = False,
) -> dict[str, Any]:
    """Apply a DB-backed audio pan payload to audio items selected by id or record bounds."""
    validated_pan = (
        None if pan_value is None else clip_effects_db.validate_audio_pan_value(pan_value)
    )
    if native_clip_audio.available(conn):
        preview = preview_audio_pan_batch(conn, pan_value=validated_pan, selectors=selectors,
                                          allow_empty=allow_empty, allow_multiple=allow_multiple)
        return native_clip_audio.apply_batch_preview(conn, preview, property_key='AudioPan', value=validated_pan)
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed("No active timeline is available for Fairlight audio pan batch.")
    entries = _audio_pan_entries(conn, selectors, default_pan=validated_pan)
    return db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Fairlight batch audio pan",
        writer=_audio_pan_batch_writer(
            timeline_name=timeline_name,
            entries=entries,
            allow_empty=allow_empty,
            allow_multiple=allow_multiple,
            timeline_start=_timeline_start_frame(conn),
        ),
        verifier=_verify_audio_pan_batch(),
        allow_project_name_inference=True,
    )


def _parse_fade_duration_ref(conn, value: Any, *, field_name: str = "duration") -> int:
    try:
        frames = seconds_to_frames(parse_time_input(str(value), float(getattr(conn, "fps", 24.0) or 24.0)), float(getattr(conn, "fps", 24.0) or 24.0))
    except Exception as exc:
        details = getattr(exc, "details", {"field": field_name, "value": value})
        raise ValidationError(
            f"Cannot parse fade duration {field_name}: {value}",
            details=details,
            recoverability="not_applicable",
        ) from exc
    if frames <= 0:
        raise ValidationError(
            "Fade duration must be greater than 0 frames.",
            details={"field": field_name, "value": value, "resolved_frames": frames},
            recoverability="not_applicable",
        )
    return int(frames)


def _fade_operation_label(edge: str) -> str:
    if edge == "end":
        return "fade-out"
    if edge == "crossfade":
        return "crossfade"
    return "fade-in"


def _fade_duration_frames_for_entry(conn, raw: dict[str, Any], *, default_duration: str | None, index: int, edge: str = "start") -> int:
    if edge == "end":
        frame_value = _first_present(raw, "fade_duration_frames", "fadeDurationFrames", "fade_out_frames", "fadeOutFrames")
        ref_value = _first_present(raw, "fade_duration", "fadeDuration", "fade_out_duration", "fadeOutDuration")
    elif edge == "crossfade":
        frame_value = _first_present(raw, "fade_duration_frames", "fadeDurationFrames", "crossfade_frames", "crossfadeFrames")
        ref_value = _first_present(raw, "fade_duration", "fadeDuration", "crossfade_duration", "crossfadeDuration")
    else:
        frame_value = _first_present(raw, "fade_duration_frames", "fadeDurationFrames", "fade_in_frames", "fadeInFrames")
        ref_value = _first_present(raw, "fade_duration", "fadeDuration", "fade_in_duration", "fadeInDuration")
    if frame_value is not None and ref_value is not None:
        raise ValidationError(
            "Use only one fade duration field per batch entry.",
            details={"index": index, "fade_duration_frames": frame_value, "fade_duration": ref_value},
            recoverability="not_applicable",
        )
    if frame_value is not None:
        frames = _coerce_int(frame_value, field="fade_duration_frames")
        if frames <= 0:
            raise ValidationError(
                "fade_duration_frames must be greater than 0.",
                details={"index": index, "fade_duration_frames": frames},
                recoverability="not_applicable",
            )
        return int(frames)
    if ref_value is not None:
        return _parse_fade_duration_ref(conn, ref_value, field_name="fade_duration")
    if default_duration is None:
        raise ValidationError(
            "--duration is required unless every batch entry has fade_duration/fade_duration_frames.",
            details={"index": index, "entry": raw},
            recoverability="not_applicable",
        )
    return _parse_fade_duration_ref(conn, default_duration, field_name="duration")


def normalize_audio_fade_batch_selectors(
    conn,
    entries: list[dict[str, Any]],
    *,
    default_duration: str | None,
    edge: str = "start",
) -> list[dict[str, Any]]:
    """Normalize audio fade batch entries while allowing item_id metadata from source-offset results."""
    operation_label = _fade_operation_label(edge)
    normalized: list[dict[str, Any]] = []
    explicit_pair_item_ids: set[str] = set()
    saw_explicit_pair = False
    saw_ordinary_selector = False
    for index, raw_entry in enumerate(entries):
        if not isinstance(raw_entry, dict):
            raise ValidationError(
                f"Each audio {operation_label} batch entry must be a JSON object.",
                details={"index": index, "entry": raw_entry},
                recoverability="not_applicable",
            )
        raw = dict(raw_entry)
        requested_fade_frames = _fade_duration_frames_for_entry(conn, raw, default_duration=default_duration, index=index, edge=edge)
        left_item_id = str(_first_present(raw, "left_item_id", "leftItemId") or "").strip()
        right_item_id = str(_first_present(raw, "right_item_id", "rightItemId") or "").strip()
        if left_item_id or right_item_id:
            if edge != "crossfade" or not left_item_id or not right_item_id:
                raise ValidationError(
                    "Explicit crossfade pairs require both left_item_id and right_item_id.",
                    details={"index": index, "entry": raw},
                    recoverability="not_applicable",
                )
            if left_item_id == right_item_id or {left_item_id, right_item_id} & explicit_pair_item_ids:
                raise ValidationError(
                    "Explicit crossfade pairs require distinct audio item ids.",
                    details={"index": index, "left_item_id": left_item_id, "right_item_id": right_item_id},
                    recoverability="not_applicable",
                )
            if saw_ordinary_selector:
                raise ValidationError(
                    "Do not mix explicit crossfade pairs with ordinary crossfade selectors.",
                    details={"index": index},
                    recoverability="not_applicable",
                )
            saw_explicit_pair = True
            explicit_pair_item_ids.update((left_item_id, right_item_id))
            for role, item_id in (("left", left_item_id), ("right", right_item_id)):
                selector = AudioGainBatchSelector(kind="item_id", item_id=item_id, raw=raw)
                normalized.append({
                    "selector": selector,
                    "requested_fade_frames": requested_fade_frames,
                    "raw": raw,
                    "explicit_pair_index": index,
                    "explicit_pair_role": role,
                })
            continue

        if saw_explicit_pair:
            raise ValidationError(
                "Do not mix explicit crossfade pairs with ordinary crossfade selectors.",
                details={"index": index},
                recoverability="not_applicable",
            )
        saw_ordinary_selector = True
        item_id = str(_first_present(raw, "item_id", "itemId", "Sm2TiItem_id") or "").strip()
        if item_id:
            selector = AudioGainBatchSelector(kind="item_id", item_id=item_id, raw=raw)
            normalized.append({"selector": selector, "requested_fade_frames": requested_fade_frames, "raw": raw})
            continue

        track_value = _first_present(raw, "track_index", "trackIndex")
        if track_value is None:
            raise ValidationError(
                f"Audio {operation_label} batch entries require item_id or track_index.",
                details={"index": index, "entry": raw},
                recoverability="not_applicable",
            )
        track_index = _coerce_int(track_value, field="track_index")
        if track_index < 1:
            raise ValidationError(
                "track_index must be 1 or greater.",
                details={"index": index, "track_index": track_index},
                recoverability="not_applicable",
            )

        start_value = _first_present(raw, "start_frame", "startFrame")
        end_value = _first_present(raw, "end_frame", "endFrame")
        record_value = _first_present(raw, "record_frame", "recordFrame", "output_start_frame", "outputStartFrame")
        record_duration_value = _first_present(raw, "record_duration", "recordDuration", "record_duration_frames", "duration_frames", "durationFrames")
        record_end_value = _first_present(raw, "record_end", "recordEnd", "record_end_frame", "output_end_frame", "outputEndFrame")

        if (start_value is not None or end_value is not None) and record_value is not None:
            raise ValidationError(
                "Use either start_frame/end_frame bounds or record_frame/output_start_frame, not both.",
                details={"index": index, "entry": raw},
                recoverability="not_applicable",
            )
        if start_value is not None or end_value is not None:
            if start_value is None or end_value is None:
                raise ValidationError(
                    "Bounds fade selectors require both start_frame and end_frame.",
                    details={"index": index, "entry": raw},
                    recoverability="not_applicable",
                )
            start_frame = _parse_record_ref(conn, start_value, field_name="start_frame")
            end_frame = _parse_record_ref(conn, end_value, field_name="end_frame")
            if end_frame <= start_frame:
                raise ValidationError(
                    "end_frame must be after start_frame.",
                    details={"index": index, "start_frame": start_value, "end_frame": end_value},
                    recoverability="not_applicable",
                )
            selector = AudioGainBatchSelector(
                kind="range",
                track_index=track_index,
                start_frame=start_frame,
                end_frame=end_frame,
                raw=raw,
            )
            normalized.append({"selector": selector, "requested_fade_frames": requested_fade_frames, "raw": raw})
            continue

        if record_value is None:
            raise ValidationError(
                f"Track {operation_label} selectors require start_frame/end_frame or record_frame/output_start_frame.",
                details={"index": index, "entry": raw},
                recoverability="not_applicable",
            )
        if record_duration_value is not None and record_end_value is not None:
            raise ValidationError(
                "Use only one of record_duration/duration_frames or record_end.",
                details={"index": index, "entry": raw},
                recoverability="not_applicable",
            )
        record_frame = _parse_record_ref(conn, record_value, field_name="record_frame")
        end_frame = None
        if record_duration_value is not None:
            end_frame = record_frame + _parse_duration_ref(conn, record_duration_value, field_name="record_duration")
        elif record_end_value is not None:
            end_frame = _parse_record_ref(conn, record_end_value, field_name="record_end")
            if end_frame <= record_frame:
                raise ValidationError(
                    "record_end must be after record_frame.",
                    details={"index": index, "record_frame": record_value, "record_end": record_end_value},
                    recoverability="not_applicable",
                )
        selector = AudioGainBatchSelector(
            kind="point" if end_frame is None else "range",
            track_index=track_index,
            record_frame=record_frame,
            start_frame=record_frame,
            end_frame=end_frame,
            raw=raw,
        )
        normalized.append({"selector": selector, "requested_fade_frames": requested_fade_frames, "raw": raw})
    return normalized


def _audio_fade_target_payload(
    cursor: sqlite3.Cursor,
    row: dict[str, Any],
    *,
    audio_track_ids: list[str],
    requested_fade_frames: int,
) -> dict[str, Any]:
    effect_filters = row.get("EffectFiltersBA")
    return {
        "item_id": str(row.get("Sm2TiItem_id") or ""),
        "track_index": _audio_item_track_index(cursor, row, audio_track_ids=audio_track_ids),
        "clip_name": str(row.get("Name") or ""),
        "start": _int_cell(row.get("Start")),
        "duration_frames": _int_cell(row.get("Duration")),
        "raw_duration": row.get("Duration"),
        "requested_fade_frames": int(requested_fade_frames),
        "previous_fade_in_frames": clip_effects_db.find_audio_fade_in_frames(effect_filters),
        "previous_fade_out_frames": clip_effects_db.find_audio_fade_out_frames(effect_filters),
        "db_rowid": _int_cell(row.get("_rowid_")),
        "row": row,
    }


def _resolve_audio_fade_batch_targets(
    cursor: sqlite3.Cursor,
    *,
    timeline_name: str,
    entries: list[dict[str, Any]],
    allow_empty: bool,
    timeline_start: int,
    edge: str = "start",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, list[str], list[dict[str, Any]]]:
    operation_label = _fade_operation_label(edge)
    sequence = _fetch_timeline_sequence(cursor, timeline_name)
    audio_track_ids = _fetch_audio_track_ids(cursor, sequence=sequence)
    if not audio_track_ids:
        raise ValidationError(
            "Target timeline has no audio tracks in the DaVinci Resolve Disk project database.",
            details={"timeline_name": timeline_name, "timeline_sequence": sequence},
            recoverability="not_applicable",
        )

    targets_by_id: dict[str, dict[str, Any]] = {}
    selector_results: list[dict[str, Any]] = []
    skipped_items: list[dict[str, Any]] = []
    for selector_index, entry in enumerate(entries):
        selector: AudioGainBatchSelector = entry["selector"]
        matches: list[dict[str, Any]] = []
        if selector.kind == "item_id":
            item_id = str(selector.item_id or "")
            item = _fetch_audio_item_by_id(cursor, item_id=item_id, audio_track_ids=audio_track_ids)
            matches = [item] if item is not None else []
            if item is None:
                skipped = {"item_id": item_id, "reason": "row_missing"}
                if "explicit_pair_index" in entry:
                    skipped.update({
                        "explicit_pair_index": int(entry["explicit_pair_index"]),
                        "explicit_pair_role": str(entry["explicit_pair_role"]),
                    })
                skipped_items.append(skipped)
        else:
            track_index = int(selector.track_index or 0)
            if track_index < 1 or track_index > len(audio_track_ids):
                raise ValidationError(
                    "Audio track index is out of range for the target timeline.",
                    details={
                        "selector_index": selector_index,
                        "track_index": track_index,
                        "available_audio_tracks": len(audio_track_ids),
                    },
                    recoverability="not_applicable",
                )
            track_rows = _fetch_audio_items_for_track(cursor, track_id=audio_track_ids[track_index - 1])
            matches = [
                row
                for row in track_rows
                if _item_matches_selector(row, selector, timeline_start=timeline_start)
            ]
            if not matches:
                skipped_items.append(
                    {
                        "track_index": track_index,
                        "record_frame": selector.record_frame,
                        "start_frame": selector.start_frame,
                        "end_frame": selector.end_frame,
                        "reason": "row_missing",
                    }
                )

        selector_results.append(
            {
                "selector_index": selector_index,
                "selector": selector.raw,
                "match_count": len(matches),
                "item_ids": [str(row.get("Sm2TiItem_id") or "") for row in matches],
            }
        )
        for row in matches:
            item_id = str(row.get("Sm2TiItem_id") or "")
            if not item_id or item_id in targets_by_id:
                continue
            targets_by_id[item_id] = _audio_fade_target_payload(
                cursor,
                row,
                audio_track_ids=audio_track_ids,
                requested_fade_frames=int(entry["requested_fade_frames"]),
            )
            if "explicit_pair_index" in entry:
                targets_by_id[item_id]["explicit_pair_index"] = int(entry["explicit_pair_index"])
                targets_by_id[item_id]["explicit_pair_role"] = str(entry["explicit_pair_role"])

    targets = list(targets_by_id.values())
    if not targets and not allow_empty:
        raise ValidationError(
            f"No audio timeline items matched the {operation_label} batch selectors.",
            details={"timeline_name": timeline_name, "selector_results": selector_results, "skipped_items": skipped_items},
            recoverability="not_applicable",
        )
    return targets, selector_results, sequence, audio_track_ids, skipped_items


def _adjacent_same_track_audio_item_ids(targets: list[dict[str, Any]], *, edge: str = "start") -> set[str]:
    skipped: set[str] = set()
    by_track: dict[int, list[dict[str, Any]]] = {}
    for target in targets:
        track_index = int(target.get("track_index") or 0)
        by_track.setdefault(track_index, []).append(target)
    for track_targets in by_track.values():
        ordered = sorted(track_targets, key=lambda item: (int(item["start"]), int(item["duration_frames"]), str(item["item_id"])))
        previous: dict[str, Any] | None = None
        for item in ordered:
            if previous is not None and int(previous["start"]) + int(previous["duration_frames"]) == int(item["start"]):
                skipped.add(str(previous["item_id"] if edge == "end" else item["item_id"]))
            previous = item
    return skipped


def _plan_audio_fade_batch(
    targets: list[dict[str, Any]],
    *,
    edge: str = "start",
    skip_first_segment: bool,
    skip_last_segment: bool = False,
    skip_adjacent_same_track: bool,
    clamp_half_clip: bool,
    gain_db: float | None,
    initial_skipped_items: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    updated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = list(initial_skipped_items or [])
    first_start = min((int(target["start"]) for target in targets), default=None)
    last_end = max((int(target["start"]) + int(target["duration_frames"]) for target in targets), default=None)
    adjacent_ids = _adjacent_same_track_audio_item_ids(targets, edge=edge) if skip_adjacent_same_track else set()
    fade_frame_key = "fade_out_frames" if edge == "end" else "fade_in_frames"

    for target in sorted(targets, key=lambda item: (int(item["start"]), int(item.get("track_index") or 0), str(item["item_id"]))):
        item_end = int(target["start"]) + int(target["duration_frames"])
        base = {
            "item_id": str(target["item_id"]),
            "track_index": int(target.get("track_index") or 0),
            "clip_name": str(target.get("clip_name") or ""),
            "start": int(target["start"]),
            "duration_frames": int(target["duration_frames"]),
            "raw_duration": target.get("raw_duration"),
        }
        if edge != "end" and skip_first_segment and first_start is not None and int(target["start"]) == int(first_start):
            skipped.append({**base, "reason": "skip_first_segment"})
            continue
        if edge == "end" and skip_last_segment and last_end is not None and item_end == int(last_end):
            skipped.append({**base, "reason": "skip_last_segment"})
            continue
        if str(target["item_id"]) in adjacent_ids:
            skipped.append({**base, "reason": "adjacent_same_track_audio"})
            continue
        if int(target["duration_frames"]) < 2:
            skipped.append({**base, "reason": "segment_too_short"})
            continue

        requested_fade_frames = int(target["requested_fade_frames"])
        fade_in_frames = min(requested_fade_frames, int(target["duration_frames"]) // 2) if clamp_half_clip else requested_fade_frames
        if fade_in_frames <= 0:
            skipped.append({**base, "reason": "segment_too_short"})
            continue
        updated.append(
            {
                **base,
                "requested_fade_frames": requested_fade_frames,
                fade_frame_key: int(fade_in_frames),
                "gain_db": None if gain_db is None else float(gain_db),
                "db_rowid": int(target.get("db_rowid") or 0),
            }
        )
    return updated, skipped


def _missing_audio_fade_selector_skips(skipped_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in skipped_items if item.get("reason") == "row_missing"]


def _audio_fade_batch_counts(
    *,
    requested_count: int,
    targets: list[dict[str, Any]],
    updated_items: list[dict[str, Any]],
    skipped_items: list[dict[str, Any]],
) -> dict[str, Any]:
    skipped_reasons: dict[str, int] = {}
    for item in skipped_items:
        reason = str(item.get("reason") or "unknown")
        skipped_reasons[reason] = int(skipped_reasons.get(reason, 0)) + 1
    return {
        "requested_count": int(requested_count),
        "target_count": len(targets),
        "fadeable_count": sum(1 for target in targets if int(target.get("duration_frames") or 0) >= 2),
        "updated_count": len(updated_items),
        "skipped_count": len(skipped_items),
        "skipped_reasons": skipped_reasons,
    }


def _unexpected_audio_fade_skips(skipped_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unexpected: list[dict[str, Any]] = []
    for item in skipped_items:
        if item.get("reason") != "segment_too_short":
            continue
        raw_duration = item.get("raw_duration")
        if raw_duration is None:
            continue
        if _int_cell(raw_duration) >= 2 and int(item.get("duration_frames") or 0) < 2:
            unexpected.append(item)
    return unexpected


def _raise_incomplete_audio_fade_batch(
    *,
    operation_label: str,
    timeline_name: str,
    selector_results: list[dict[str, Any]],
    skipped_items: list[dict[str, Any]],
) -> None:
    missing = _missing_audio_fade_selector_skips(skipped_items)
    if missing:
        raise ValidationError(
            f"Fairlight {operation_label} batch did not match every requested audio item.",
            details={
                "timeline_name": timeline_name,
                "missing_count": len(missing),
                "missing_items": missing,
                "selector_results": selector_results,
                "skipped_items": skipped_items,
                "hint": "Re-read Fairlight items and rebuild selectors from current timeline item ids or record ranges before applying the batch.",
            },
            recoverability="not_applicable",
        )
    unexpected = _unexpected_audio_fade_skips(skipped_items)
    if unexpected:
        raise ValidationError(
            f"Fairlight {operation_label} batch skipped audio items that appear fadeable in Project.db.",
            details={
                "timeline_name": timeline_name,
                "unexpected_skip_count": len(unexpected),
                "unexpected_skips": unexpected,
                "selector_results": selector_results,
                "skipped_items": skipped_items,
                "hint": "The raw Project.db duration is nonzero but the fade planner treated it as too short; inspect Fairlight duration parsing before accepting this batch.",
            },
            recoverability="not_applicable",
        )


def _audio_fade_batch_writer(
    *,
    timeline_name: str,
    entries: list[dict[str, Any]],
    allow_empty: bool,
    timeline_start: int,
    edge: str = "start",
    skip_first_segment: bool,
    skip_last_segment: bool = False,
    skip_adjacent_same_track: bool,
    clamp_half_clip: bool,
    gain_db: float | None,
    duration: str | None,
):
    def _writer(connection: sqlite3.Connection, cursor: sqlite3.Cursor, session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        targets, selector_results, sequence, _audio_track_ids, initial_skipped = _resolve_audio_fade_batch_targets(
            cursor,
            timeline_name=timeline_name,
            entries=entries,
            allow_empty=allow_empty,
            timeline_start=timeline_start,
            edge=edge,
        )
        updated_items, skipped_items = _plan_audio_fade_batch(
            targets,
            edge=edge,
            skip_first_segment=skip_first_segment,
            skip_last_segment=skip_last_segment,
            skip_adjacent_same_track=skip_adjacent_same_track,
            clamp_half_clip=clamp_half_clip,
            gain_db=gain_db,
            initial_skipped_items=initial_skipped,
        )
        _raise_incomplete_audio_fade_batch(
            operation_label=_fade_operation_label(edge),
            timeline_name=timeline_name,
            selector_results=selector_results,
            skipped_items=skipped_items,
        )
        counts = _audio_fade_batch_counts(
            requested_count=len(entries),
            targets=targets,
            updated_items=updated_items,
            skipped_items=skipped_items,
        )
        fade_frame_key = "fade_out_frames" if edge == "end" else "fade_in_frames"
        target_rows = {str(target["item_id"]): target["row"] for target in targets}
        for item in updated_items:
            row = target_rows[str(item["item_id"])]
            write = clip_effects_db.merge_audio_effect_chains(
                existing_effect_filters=row.get("EffectFiltersBA"),
                existing_fields_blob=row.get("FieldsBlob"),
                gain_db=gain_db,
                fade_in_frames=int(item[fade_frame_key]) if edge != "end" else None,
                fade_out_frames=int(item[fade_frame_key]) if edge == "end" else None,
            )
            updates: dict[str, object] = {"EffectFiltersBA": write.effect_filters}
            if write.fields_blob is not None:
                updates["FieldsBlob"] = write.fields_blob
            db_timeline_rows.update_row(cursor, "Sm2TiItem", "Sm2TiItem_id", item["item_id"], updates)
        return {
            "action": "fairlight.fade_out.batch" if edge == "end" else "fairlight.fade_in.batch",
            "changed": bool(updated_items),
            "timeline_name": timeline_name,
            "timeline_sequence": sequence,
            "duration": duration,
            **counts,
            "updated_items": updated_items,
            "skipped_items": skipped_items,
            "selector_results": selector_results,
            "skip_first_segment": bool(skip_first_segment),
            "skip_last_segment": bool(skip_last_segment),
            "skip_adjacent_same_track": bool(skip_adjacent_same_track),
            "clamp_half_clip": bool(clamp_half_clip),
            "gain_db": None if gain_db is None else float(gain_db),
        }

    return _writer


def _verify_audio_fade_batch(*, edge: str = "start", expected_gain_db: float | None):
    def _verifier(conn, mutation_result: dict[str, Any], session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        connection = sqlite3.connect(session.project_db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        checks: list[dict[str, Any]] = []
        fade_frame_key = "fade_out_frames" if edge == "end" else "fade_in_frames"
        find_fade_frames = clip_effects_db.find_audio_fade_out_frames if edge == "end" else clip_effects_db.find_audio_fade_in_frames
        try:
            cursor = connection.cursor()
            for item in mutation_result.get("updated_items") or []:
                item_id = str(item.get("item_id") or "")
                row = cursor.execute(
                    "SELECT EffectFiltersBA FROM Sm2TiItem WHERE Sm2TiItem_id = ?",
                    (item_id,),
                ).fetchone()
                effect_filters = row["EffectFiltersBA"] if row else None
                expected_fade_frames = int(item.get(fade_frame_key) or 0)
                actual_fade_frames = find_fade_frames(effect_filters)
                actual_gain = clip_effects_db.find_audio_gain_db(effect_filters)
                gain_ok = True if expected_gain_db is None else actual_gain is not None and math.isclose(float(actual_gain), float(expected_gain_db), abs_tol=1e-6)
                checks.append(
                    {
                        "name": f"audio_{'fade_out' if edge == 'end' else 'fade_in'}_{item_id}",
                        "ok": bool(actual_fade_frames == expected_fade_frames and gain_ok),
                        "item_id": item_id,
                        "expected_fade_frames": expected_fade_frames,
                        "actual_fade_frames": actual_fade_frames,
                        "expected_gain_db": None if expected_gain_db is None else float(expected_gain_db),
                        "actual_gain_db": actual_gain,
                    }
                )
        finally:
            connection.close()
        return {
            "status": "verified" if all(check["ok"] for check in checks) else ("not_requested" if not checks else "failed"),
            "checks": checks,
        }

    return _verifier


def _crossfade_base_payload(target: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_id": str(target["item_id"]),
        "track_index": int(target.get("track_index") or 0),
        "clip_name": str(target.get("clip_name") or ""),
        "start": int(target["start"]),
        "duration_frames": int(target["duration_frames"]),
        "db_rowid": int(target.get("db_rowid") or 0),
    }


def _crossfade_edge_frames(target: dict[str, Any], *, clamp_half_clip: bool) -> int:
    requested = int(target["requested_fade_frames"])
    if not clamp_half_clip:
        return requested
    return min(requested, int(target["duration_frames"]) // 2)


def _plan_audio_crossfade_batch(
    targets: list[dict[str, Any]],
    *,
    clamp_half_clip: bool,
    initial_skipped_items: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    missing_explicit = [
        item for item in (initial_skipped_items or [])
        if "explicit_pair_index" in item
    ]
    if missing_explicit:
        raise ValidationError(
            "An explicit crossfade pair no longer resolves both audio items.",
            details={"missing_items": missing_explicit},
            recoverability="not_applicable",
        )
    explicit_targets = [target for target in targets if "explicit_pair_index" in target]
    if explicit_targets:
        by_pair: dict[int, dict[str, dict[str, Any]]] = {}
        for target in explicit_targets:
            pair_index = int(target["explicit_pair_index"])
            role = str(target.get("explicit_pair_role") or "")
            if role not in {"left", "right"} or role in by_pair.setdefault(pair_index, {}):
                raise ValidationError(
                    "Explicit crossfade pair binding is invalid.",
                    details={"pair_index": pair_index, "role": role},
                    recoverability="not_applicable",
                )
            by_pair[pair_index][role] = target

        updates_by_id: dict[str, dict[str, Any]] = {}
        crossfade_pairs: list[dict[str, Any]] = []
        for pair_index, pair in sorted(by_pair.items()):
            if set(pair) != {"left", "right"}:
                raise ValidationError(
                    "An explicit crossfade pair no longer resolves both audio items.",
                    details={"pair_index": pair_index, "resolved_roles": sorted(pair)},
                    recoverability="not_applicable",
                )
            left, right = pair["left"], pair["right"]
            left_end = int(left["start"]) + int(left["duration_frames"])
            if int(left.get("track_index") or 0) != int(right.get("track_index") or 0) or left_end != int(right["start"]):
                raise ValidationError(
                    "Explicit crossfade pairs must remain adjacent on the same audio track.",
                    details={
                        "pair_index": pair_index,
                        "left_item_id": str(left["item_id"]),
                        "right_item_id": str(right["item_id"]),
                    },
                    recoverability="not_applicable",
                )
            if int(left["requested_fade_frames"]) != int(right["requested_fade_frames"]):
                raise ValidationError(
                    "Both sides of an explicit crossfade pair must use one duration.",
                    details={"pair_index": pair_index},
                    recoverability="not_applicable",
                )
            left_frames = _crossfade_edge_frames(left, clamp_half_clip=clamp_half_clip)
            right_frames = _crossfade_edge_frames(right, clamp_half_clip=clamp_half_clip)
            if left_frames <= 0 or right_frames <= 0:
                raise ValidationError(
                    "Explicit crossfade pair clips are too short for a fade.",
                    details={"pair_index": pair_index},
                    recoverability="not_applicable",
                )
            left_update = updates_by_id.setdefault(str(left["item_id"]), _crossfade_base_payload(left))
            right_update = updates_by_id.setdefault(str(right["item_id"]), _crossfade_base_payload(right))
            left_update["fade_out_frames"] = int(left_frames)
            right_update["fade_in_frames"] = int(right_frames)
            crossfade_pairs.append({
                "track_index": int(left.get("track_index") or 0),
                "left_item_id": str(left["item_id"]),
                "right_item_id": str(right["item_id"]),
                "left_clip_name": str(left.get("clip_name") or ""),
                "right_clip_name": str(right.get("clip_name") or ""),
                "edit_frame": int(left_end),
                "left_fade_out_frames": int(left_frames),
                "right_fade_in_frames": int(right_frames),
                "requested_left_frames": int(left["requested_fade_frames"]),
                "requested_right_frames": int(right["requested_fade_frames"]),
            })
        return (
            sorted(updates_by_id.values(), key=lambda item: (int(item["start"]), int(item.get("track_index") or 0), str(item["item_id"]))),
            list(initial_skipped_items or []),
            crossfade_pairs,
        )

    updates_by_id: dict[str, dict[str, Any]] = {}
    crossfade_pairs: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = list(initial_skipped_items or [])
    paired_ids: set[str] = set()

    by_track: dict[int, list[dict[str, Any]]] = {}
    for target in targets:
        by_track.setdefault(int(target.get("track_index") or 0), []).append(target)

    for track_index, track_targets in by_track.items():
        ordered = sorted(track_targets, key=lambda item: (int(item["start"]), int(item["duration_frames"]), str(item["item_id"])))
        for left, right in zip(ordered, ordered[1:]):
            left_end = int(left["start"]) + int(left["duration_frames"])
            right_start = int(right["start"])
            if left_end != right_start:
                continue
            left_frames = _crossfade_edge_frames(left, clamp_half_clip=clamp_half_clip)
            right_frames = _crossfade_edge_frames(right, clamp_half_clip=clamp_half_clip)
            if left_frames <= 0 or right_frames <= 0:
                skipped.append(
                    {
                        "track_index": int(track_index),
                        "left_item_id": str(left["item_id"]),
                        "right_item_id": str(right["item_id"]),
                        "edit_frame": int(left_end),
                        "reason": "segment_too_short",
                    }
                )
                paired_ids.update({str(left["item_id"]), str(right["item_id"])})
                continue

            left_update = updates_by_id.setdefault(str(left["item_id"]), _crossfade_base_payload(left))
            right_update = updates_by_id.setdefault(str(right["item_id"]), _crossfade_base_payload(right))
            left_update["fade_out_frames"] = int(left_frames)
            right_update["fade_in_frames"] = int(right_frames)
            paired_ids.update({str(left["item_id"]), str(right["item_id"])})
            crossfade_pairs.append(
                {
                    "track_index": int(track_index),
                    "left_item_id": str(left["item_id"]),
                    "right_item_id": str(right["item_id"]),
                    "left_clip_name": str(left.get("clip_name") or ""),
                    "right_clip_name": str(right.get("clip_name") or ""),
                    "edit_frame": int(left_end),
                    "left_fade_out_frames": int(left_frames),
                    "right_fade_in_frames": int(right_frames),
                    "requested_left_frames": int(left["requested_fade_frames"]),
                    "requested_right_frames": int(right["requested_fade_frames"]),
                }
            )

    for target in targets:
        item_id = str(target["item_id"])
        if item_id not in paired_ids:
            skipped.append({**_crossfade_base_payload(target), "reason": "no_adjacent_edit_point"})

    updated_items = sorted(
        updates_by_id.values(),
        key=lambda item: (int(item["start"]), int(item.get("track_index") or 0), str(item["item_id"])),
    )
    return updated_items, skipped, crossfade_pairs


def _audio_crossfade_batch_writer(
    *,
    timeline_name: str,
    entries: list[dict[str, Any]],
    allow_empty: bool,
    timeline_start: int,
    clamp_half_clip: bool,
    duration: str | None,
):
    def _writer(connection: sqlite3.Connection, cursor: sqlite3.Cursor, session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        targets, selector_results, sequence, _audio_track_ids, initial_skipped = _resolve_audio_fade_batch_targets(
            cursor,
            timeline_name=timeline_name,
            entries=entries,
            allow_empty=allow_empty,
            timeline_start=timeline_start,
            edge="crossfade",
        )
        updated_items, skipped_items, crossfade_pairs = _plan_audio_crossfade_batch(
            targets,
            clamp_half_clip=clamp_half_clip,
            initial_skipped_items=initial_skipped,
        )
        if not updated_items and not allow_empty:
            raise ValidationError(
                "No adjacent audio edit points matched the crossfade batch selectors.",
                details={
                    "timeline_name": timeline_name,
                    "selector_results": selector_results,
                    "skipped_items": skipped_items,
                },
                recoverability="not_applicable",
            )

        target_rows = {str(target["item_id"]): target["row"] for target in targets}
        for item in updated_items:
            row = target_rows[str(item["item_id"])]
            write = clip_effects_db.merge_audio_effect_chains(
                existing_effect_filters=row.get("EffectFiltersBA"),
                existing_fields_blob=row.get("FieldsBlob"),
                fade_in_frames=int(item["fade_in_frames"]) if item.get("fade_in_frames") is not None else None,
                fade_out_frames=int(item["fade_out_frames"]) if item.get("fade_out_frames") is not None else None,
            )
            updates: dict[str, object] = {"EffectFiltersBA": write.effect_filters}
            if write.fields_blob is not None:
                updates["FieldsBlob"] = write.fields_blob
            db_timeline_rows.update_row(cursor, "Sm2TiItem", "Sm2TiItem_id", item["item_id"], updates)
        return {
            "action": "fairlight.crossfade.batch",
            "changed": bool(updated_items),
            "timeline_name": timeline_name,
            "timeline_sequence": sequence,
            "duration": duration,
            "updated_count": len(updated_items),
            "crossfade_pair_count": len(crossfade_pairs),
            "crossfade_pairs": crossfade_pairs,
            "updated_items": updated_items,
            "skipped_count": len(skipped_items),
            "skipped_items": skipped_items,
            "selector_results": selector_results,
            "clamp_half_clip": bool(clamp_half_clip),
        }

    return _writer


def _verify_audio_crossfade_batch():
    def _verifier(conn, mutation_result: dict[str, Any], session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        connection = sqlite3.connect(session.project_db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        checks: list[dict[str, Any]] = []
        try:
            cursor = connection.cursor()
            for item in mutation_result.get("updated_items") or []:
                item_id = str(item.get("item_id") or "")
                row = cursor.execute(
                    "SELECT EffectFiltersBA FROM Sm2TiItem WHERE Sm2TiItem_id = ?",
                    (item_id,),
                ).fetchone()
                effect_filters = row["EffectFiltersBA"] if row else None
                actual_fade_in = clip_effects_db.find_audio_fade_in_frames(effect_filters)
                actual_fade_out = clip_effects_db.find_audio_fade_out_frames(effect_filters)
                expected_fade_in = item.get("fade_in_frames")
                expected_fade_out = item.get("fade_out_frames")
                fade_in_ok = True if expected_fade_in is None else actual_fade_in == int(expected_fade_in)
                fade_out_ok = True if expected_fade_out is None else actual_fade_out == int(expected_fade_out)
                checks.append(
                    {
                        "name": f"audio_crossfade_{item_id}",
                        "ok": bool(fade_in_ok and fade_out_ok),
                        "item_id": item_id,
                        "expected_fade_in_frames": expected_fade_in,
                        "actual_fade_in_frames": actual_fade_in,
                        "expected_fade_out_frames": expected_fade_out,
                        "actual_fade_out_frames": actual_fade_out,
                    }
                )
        finally:
            connection.close()
        return {
            "status": "verified" if all(check["ok"] for check in checks) else ("not_requested" if not checks else "failed"),
            "checks": checks,
        }

    return _verifier


def preview_audio_crossfade_batch(
    conn,
    *,
    entries: list[dict[str, Any]],
    duration: str | None = None,
    clamp_half_clip: bool = True,
    allow_empty: bool = False,
) -> dict[str, Any]:
    """Resolve adjacent audio edit points for a crossfade batch without mutating the project DB."""
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed("No active timeline is available for Fairlight crossfade batch.")
    normalized = normalize_audio_fade_batch_selectors(conn, entries, default_duration=duration, edge="crossfade")
    current_database = db_session.resolve_current_disk_project_db(conn)
    db_path = str(current_database["project_db_path"])
    connection = sqlite3.connect(db_path, timeout=5.0)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        targets, selector_results, sequence, _audio_track_ids, initial_skipped = _resolve_audio_fade_batch_targets(
            cursor,
            timeline_name=timeline_name,
            entries=normalized,
            allow_empty=allow_empty,
            timeline_start=_timeline_start_frame(conn),
            edge="crossfade",
        )
        updated_items, skipped_items, crossfade_pairs = _plan_audio_crossfade_batch(
            targets,
            clamp_half_clip=clamp_half_clip,
            initial_skipped_items=initial_skipped,
        )
    finally:
        connection.close()
    if not updated_items and not allow_empty:
        raise ValidationError(
            "No adjacent audio edit points matched the crossfade batch selectors.",
            details={"timeline_name": timeline_name, "selector_results": selector_results, "skipped_items": skipped_items},
            recoverability="not_applicable",
        )
    return {
        "action": "fairlight.crossfade.batch",
        "changed": False,
        "dry_run": True,
        "timeline_name": timeline_name,
        "timeline_sequence": sequence,
        "duration": duration,
        "updated_count": 0,
        "target_count": len(targets),
        "preview_update_count": len(updated_items),
        "crossfade_pair_count": len(crossfade_pairs),
        "crossfade_pairs": crossfade_pairs,
        "updated_items": updated_items,
        "skipped_count": len(skipped_items),
        "skipped_items": skipped_items,
        "selector_results": selector_results,
        "clamp_half_clip": bool(clamp_half_clip),
        "verification": {"status": "not_requested", "checks": []},
    }


def apply_audio_crossfade_batch(
    conn,
    *,
    entries: list[dict[str, Any]],
    duration: str | None = None,
    clamp_half_clip: bool = True,
    allow_empty: bool = False,
) -> dict[str, Any]:
    """Apply DB-backed crossfade payloads at adjacent audio edit points selected by id or record bounds."""
    if native_clip_audio.available(conn):
        preview = preview_audio_crossfade_batch(
            conn,
            entries=entries,
            duration=duration,
            clamp_half_clip=clamp_half_clip,
            allow_empty=allow_empty,
        )
        return native_clip_audio.apply_batch_preview(conn, preview, edge="crossfade")
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed("No active timeline is available for Fairlight crossfade batch.")
    normalized = normalize_audio_fade_batch_selectors(conn, entries, default_duration=duration, edge="crossfade")
    result = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Fairlight batch audio crossfade",
        writer=_audio_crossfade_batch_writer(
            timeline_name=timeline_name,
            entries=normalized,
            allow_empty=allow_empty,
            timeline_start=_timeline_start_frame(conn),
            clamp_half_clip=clamp_half_clip,
            duration=duration,
        ),
        verifier=_verify_audio_crossfade_batch(),
        allow_project_name_inference=True,
    )
    verification = result.get("verification") or {}
    if verification.get("status") == "failed":
        set_verification_status("failed")
    elif result.get("updated_count"):
        set_verification_status("verified")
    else:
        set_verification_status("not_requested")
    return result


def _preview_audio_fade_batch(
    conn,
    *,
    entries: list[dict[str, Any]],
    duration: str | None = None,
    edge: str = "start",
    skip_first_segment: bool = False,
    skip_last_segment: bool = False,
    skip_adjacent_same_track: bool = True,
    clamp_half_clip: bool = True,
    gain_db: float | None = None,
    allow_empty: bool = False,
) -> dict[str, Any]:
    """Resolve a batch audio fade selector set without mutating the project DB."""
    operation_label = "fade-out" if edge == "end" else "fade-in"
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed(f"No active timeline is available for Fairlight {operation_label} batch.")
    validated_gain = None if gain_db is None else clip_effects_db.validate_audio_gain_db(gain_db)
    normalized = normalize_audio_fade_batch_selectors(conn, entries, default_duration=duration, edge=edge)
    current_database = db_session.resolve_current_disk_project_db(conn)
    db_path = str(current_database["project_db_path"])
    connection = sqlite3.connect(db_path, timeout=5.0)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        targets, selector_results, sequence, _audio_track_ids, initial_skipped = _resolve_audio_fade_batch_targets(
            cursor,
            timeline_name=timeline_name,
            entries=normalized,
            allow_empty=allow_empty,
            timeline_start=_timeline_start_frame(conn),
            edge=edge,
        )
        updated_items, skipped_items = _plan_audio_fade_batch(
            targets,
            edge=edge,
            skip_first_segment=skip_first_segment,
            skip_last_segment=skip_last_segment,
            skip_adjacent_same_track=skip_adjacent_same_track,
            clamp_half_clip=clamp_half_clip,
            gain_db=validated_gain,
            initial_skipped_items=initial_skipped,
        )
        counts = _audio_fade_batch_counts(
            requested_count=len(normalized),
            targets=targets,
            updated_items=updated_items,
            skipped_items=skipped_items,
        )
    finally:
        connection.close()
    return {
        "action": "fairlight.fade_out.batch" if edge == "end" else "fairlight.fade_in.batch",
        "changed": False,
        "dry_run": True,
        "timeline_name": timeline_name,
        "timeline_sequence": sequence,
        "duration": duration,
        "updated_count": 0,
        "requested_count": counts["requested_count"],
        "target_count": counts["target_count"],
        "fadeable_count": counts["fadeable_count"],
        "preview_update_count": len(updated_items),
        "updated_items": updated_items,
        "skipped_count": counts["skipped_count"],
        "skipped_reasons": counts["skipped_reasons"],
        "skipped_items": skipped_items,
        "selector_results": selector_results,
        "skip_first_segment": bool(skip_first_segment),
        "skip_last_segment": bool(skip_last_segment),
        "skip_adjacent_same_track": bool(skip_adjacent_same_track),
        "clamp_half_clip": bool(clamp_half_clip),
        "gain_db": None if validated_gain is None else float(validated_gain),
        "verification": {"status": "not_requested", "checks": []},
    }


def preview_audio_fade_in_batch(
    conn,
    *,
    entries: list[dict[str, Any]],
    duration: str | None = None,
    skip_first_segment: bool = False,
    skip_adjacent_same_track: bool = True,
    clamp_half_clip: bool = True,
    gain_db: float | None = None,
    allow_empty: bool = False,
) -> dict[str, Any]:
    """Resolve a batch audio fade-in selector set without mutating the project DB."""
    return _preview_audio_fade_batch(
        conn,
        entries=entries,
        duration=duration,
        edge="start",
        skip_first_segment=skip_first_segment,
        skip_adjacent_same_track=skip_adjacent_same_track,
        clamp_half_clip=clamp_half_clip,
        gain_db=gain_db,
        allow_empty=allow_empty,
    )


def preview_audio_fade_out_batch(
    conn,
    *,
    entries: list[dict[str, Any]],
    duration: str | None = None,
    skip_last_segment: bool = False,
    skip_adjacent_same_track: bool = True,
    clamp_half_clip: bool = True,
    gain_db: float | None = None,
    allow_empty: bool = False,
) -> dict[str, Any]:
    """Resolve a batch audio fade-out selector set without mutating the project DB."""
    return _preview_audio_fade_batch(
        conn,
        entries=entries,
        duration=duration,
        edge="end",
        skip_last_segment=skip_last_segment,
        skip_adjacent_same_track=skip_adjacent_same_track,
        clamp_half_clip=clamp_half_clip,
        gain_db=gain_db,
        allow_empty=allow_empty,
    )


def _apply_audio_fade_batch(
    conn,
    *,
    entries: list[dict[str, Any]],
    duration: str | None = None,
    edge: str = "start",
    skip_first_segment: bool = False,
    skip_last_segment: bool = False,
    skip_adjacent_same_track: bool = True,
    clamp_half_clip: bool = True,
    gain_db: float | None = None,
    allow_empty: bool = False,
) -> dict[str, Any]:
    """Apply DB-backed audio fade payloads to audio items selected by id or record bounds."""
    if gain_db is None and native_clip_audio.available(conn):
        preview = _preview_audio_fade_batch(conn, entries=entries, duration=duration, edge=edge,
            skip_first_segment=skip_first_segment, skip_last_segment=skip_last_segment,
            skip_adjacent_same_track=skip_adjacent_same_track, clamp_half_clip=clamp_half_clip,
            gain_db=None, allow_empty=allow_empty)
        return native_clip_audio.apply_batch_preview(conn, preview, edge=edge)
    operation_label = "fade-out" if edge == "end" else "fade-in"
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed(f"No active timeline is available for Fairlight {operation_label} batch.")
    validated_gain = None if gain_db is None else clip_effects_db.validate_audio_gain_db(gain_db)
    normalized = normalize_audio_fade_batch_selectors(conn, entries, default_duration=duration, edge=edge)
    result = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context=f"Fairlight batch audio {operation_label}",
        writer=_audio_fade_batch_writer(
            timeline_name=timeline_name,
            entries=normalized,
            allow_empty=allow_empty,
            timeline_start=_timeline_start_frame(conn),
            edge=edge,
            skip_first_segment=skip_first_segment,
            skip_last_segment=skip_last_segment,
            skip_adjacent_same_track=skip_adjacent_same_track,
            clamp_half_clip=clamp_half_clip,
            gain_db=validated_gain,
            duration=duration,
        ),
        verifier=_verify_audio_fade_batch(edge=edge, expected_gain_db=validated_gain),
        allow_project_name_inference=True,
    )
    verification = result.get("verification") or {}
    if verification.get("status") == "failed":
        set_verification_status("failed")
    elif result.get("updated_count"):
        set_verification_status("verified")
    else:
        set_verification_status("not_requested")
    return result


def apply_audio_fade_in_batch(
    conn,
    *,
    entries: list[dict[str, Any]],
    duration: str | None = None,
    skip_first_segment: bool = False,
    skip_adjacent_same_track: bool = True,
    clamp_half_clip: bool = True,
    gain_db: float | None = None,
    allow_empty: bool = False,
) -> dict[str, Any]:
    """Apply DB-backed audio fade-in payloads to audio items selected by id or record bounds."""
    return _apply_audio_fade_batch(
        conn,
        entries=entries,
        duration=duration,
        edge="start",
        skip_first_segment=skip_first_segment,
        skip_adjacent_same_track=skip_adjacent_same_track,
        clamp_half_clip=clamp_half_clip,
        gain_db=gain_db,
        allow_empty=allow_empty,
    )


def apply_audio_fade_out_batch(
    conn,
    *,
    entries: list[dict[str, Any]],
    duration: str | None = None,
    skip_last_segment: bool = False,
    skip_adjacent_same_track: bool = True,
    clamp_half_clip: bool = True,
    gain_db: float | None = None,
    allow_empty: bool = False,
) -> dict[str, Any]:
    """Apply DB-backed audio fade-out payloads to audio items selected by id or record bounds."""
    return _apply_audio_fade_batch(
        conn,
        entries=entries,
        duration=duration,
        edge="end",
        skip_last_segment=skip_last_segment,
        skip_adjacent_same_track=skip_adjacent_same_track,
        clamp_half_clip=clamp_half_clip,
        gain_db=gain_db,
        allow_empty=allow_empty,
    )


def patch_audio_track_db_subtypes(conn, *, timeline_name: str, subtype: int, expected_count: int | None = None) -> dict[str, Any]:
    """Patch every audio track subtype for a timeline through the shared Disk DB session."""
    return db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Fairlight stereo audio track subtype patch",
        writer=_patch_audio_track_subtypes_writer(timeline_name=timeline_name, subtype=subtype, expected_count=expected_count),
        verifier=_verify_audio_track_subtypes(timeline_name=timeline_name, subtype=subtype, expected_count=expected_count),
        allow_project_name_inference=True,
    )
