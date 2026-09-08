"""Native multicam timing recovery helpers."""

from __future__ import annotations

import os
import re
import sqlite3
import struct
from typing import Any

from ...errors import ValidationError
from ...runtime_health import resolve_current_disk_project_db
from ...utils.timecode import seconds_to_frames, timecode_to_seconds
from .. import db_session, media_pool
from . import source_rows as _source_rows
from .blob_codec import _decode_rate_blob

_SOURCE_START_TC_KEYS = (
    "Start TC",
    "Start Timecode",
    "Source Start TC",
    "Source Timecode",
    "TC",
)


def _normalize_source_path_for_match(value: str | None) -> str:
    expanded = os.path.expanduser(str(value or "").strip())
    if not expanded:
        return ""
    return os.path.normcase(os.path.normpath(expanded))


def _normalize_folder_path_for_match(value: str | None) -> str:
    return re.sub(r"/+", "/", str(value or "").strip().replace("\\", "/")).strip("/")


def _folder_leaf(value: str | None) -> str:
    normalized = _normalize_folder_path_for_match(value)
    if not normalized:
        return ""
    return normalized.rsplit("/", 1)[-1]


def _coerce_positive_int(value: Any, *, field: str, allow_zero: bool = False) -> int:
    if value in (None, ""):
        raise ValidationError(
            f"Missing required field '{field}'.",
            details={"field": field},
            recoverability="not_applicable",
        )
    try:
        normalized = int(str(value).strip().removesuffix("f"))
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"Field '{field}' must be an integer frame count.",
            details={"field": field, "value": value},
            recoverability="not_applicable",
        ) from exc
    minimum = 0 if allow_zero else 1
    if normalized < minimum:
        comparison = "greater than or equal to 0" if allow_zero else "greater than 0"
        raise ValidationError(
            f"Field '{field}' must be {comparison}.",
            details={"field": field, "value": normalized},
            recoverability="not_applicable",
        )
    return normalized


def _coerce_positive_float(value: Any, *, field: str) -> float:
    if value in (None, ""):
        raise ValidationError(
            f"Missing required field '{field}'.",
            details={"field": field},
            recoverability="not_applicable",
        )
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"Field '{field}' must be numeric.",
            details={"field": field, "value": value},
            recoverability="not_applicable",
        ) from exc
    if normalized <= 0:
        raise ValidationError(
            f"Field '{field}' must be greater than 0.",
            details={"field": field, "value": normalized},
            recoverability="not_applicable",
        )
    return normalized


def _timecode_to_frames(value: str, fps: float) -> int:
    text = str(value or "").strip()
    if not text:
        raise ValidationError(
            "source_start_tc must not be empty.",
            details={"value": value},
            recoverability="not_applicable",
        )
    try:
        return int(seconds_to_frames(timecode_to_seconds(text, fps), fps))
    except Exception as exc:
        raise ValidationError(
            "source_start_tc must be HH:MM:SS:FF or HH:MM:SS;FF.",
            details={"value": value, "fps": fps},
            recoverability="not_applicable",
        ) from exc


def _encode_recovery_media_timemap_ba(duration_frames: int, fps: float) -> bytes:
    safe_fps = fps if fps > 0 else 24.0
    duration_seconds = max(1, int(duration_frames)) / safe_fps
    return b"\x02" + struct.pack(">d", duration_seconds)


def _encode_recovery_sequence_media_extents(start_frame: int, duration_frames: int, fps: float) -> bytes:
    safe_fps = fps if fps > 0 else 24.0
    return struct.pack(
        "<dd",
        int(start_frame) / safe_fps,
        max(1, int(duration_frames)) / safe_fps,
    )


def _decode_sequence_media_extents(blob: bytes | None, fps: float) -> dict[str, Any] | None:
    if not blob or len(blob) < 16:
        return None
    try:
        start_seconds, duration_seconds = struct.unpack("<dd", blob[:16])
    except struct.error:
        return None
    return {
        "start_seconds": float(start_seconds),
        "duration_seconds": float(duration_seconds),
        "start_frame": int(round(float(start_seconds) * fps)),
        "duration_frames": int(round(float(duration_seconds) * fps)),
        "hex": bytes(blob).hex().upper(),
    }


def _sqlite_project_db_health_from_connection(connection: sqlite3.Connection) -> dict[str, Any]:
    integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()
    foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
    integrity_messages = [
        str(row[0])
        for row in integrity_rows
        if row and str(row[0]).strip().lower() != "ok"
    ]
    foreign_key_failures = [tuple(row) for row in foreign_key_rows]
    ok = not integrity_messages
    return {
        "ok": ok,
        "status": "ok" if ok and not foreign_key_failures else ("ok_with_fk_warnings" if ok else "failed"),
        "integrity": integrity_messages or ["ok"],
        "foreign_key_failure_count": len(foreign_key_failures),
        "foreign_key_failures": foreign_key_failures[:20],
    }


def _sqlite_project_db_health_from_path(project_db_path: str) -> dict[str, Any]:
    try:
        connection = sqlite3.connect(f"file:{project_db_path}?mode=ro", uri=True, timeout=5.0)
    except Exception as exc:
        return {
            "ok": False,
            "status": "sqlite_open_failed",
            "project_db_path": project_db_path,
            "error": str(exc),
        }
    try:
        health = _sqlite_project_db_health_from_connection(connection)
    finally:
        connection.close()
    health["project_db_path"] = project_db_path
    return health


def _stable_clip_matches(conn, clip_name: str, *, temp_bin_prefix: str) -> list[dict[str, Any]]:
    root = conn.media_pool.GetRootFolder() if getattr(conn, "media_pool", None) is not None else None
    if not root:
        return []
    matches: list[dict[str, Any]] = []
    media_pool._collect_clip_matches(root, clip_name, "", matches)
    return [
        match
        for match in matches
        if not _source_rows._is_temp_bin_folder_path(
            str(match.get("folder") or ""),
            temp_bin_prefix=temp_bin_prefix,
        )
    ]


def _resolve_live_clip_match(conn, spec: dict[str, Any], *, temp_bin_prefix: str) -> dict[str, Any] | None:
    stable_matches = _stable_clip_matches(conn, str(spec["clip_name"]), temp_bin_prefix=temp_bin_prefix)
    if not stable_matches:
        return None

    requested_source_path = _normalize_source_path_for_match(spec.get("source_path"))
    requested_folder = _normalize_folder_path_for_match(spec.get("folder"))
    chosen_pool = list(stable_matches)

    if requested_source_path:
        source_path_matches: list[dict[str, Any]] = []
        for match in chosen_pool:
            clip = match.get("clip")
            props = media_pool._clip_properties(clip)
            resolved_source_path = media_pool._canonical_source_path(props, clip)
            if _normalize_source_path_for_match(resolved_source_path) == requested_source_path:
                source_path_matches.append({**match, "_props": props, "_resolved_source_path": resolved_source_path})
        if len(source_path_matches) == 1:
            return source_path_matches[0]
        if source_path_matches:
            chosen_pool = source_path_matches

    if requested_folder:
        exact_folder_matches = [
            match
            for match in chosen_pool
            if _normalize_folder_path_for_match(match.get("folder")) == requested_folder
        ]
        if len(exact_folder_matches) == 1:
            return exact_folder_matches[0]
        if exact_folder_matches:
            chosen_pool = exact_folder_matches

    if requested_folder:
        suffix_folder_matches = [
            match
            for match in chosen_pool
            if _normalize_folder_path_for_match(match.get("folder")) == requested_folder
            or _normalize_folder_path_for_match(match.get("folder")).endswith(f"/{requested_folder}")
        ]
        if len(suffix_folder_matches) == 1:
            return suffix_folder_matches[0]
        if suffix_folder_matches:
            chosen_pool = suffix_folder_matches

    if requested_folder:
        requested_leaf = _folder_leaf(requested_folder)
        leaf_matches = [
            match
            for match in chosen_pool
            if _folder_leaf(match.get("folder")).lower() == requested_leaf.lower()
        ]
        if len(leaf_matches) == 1:
            return leaf_matches[0]

    if len(chosen_pool) == 1:
        return chosen_pool[0]
    return None


def _infer_source_spec_from_resolve(conn, spec: dict[str, Any], *, temp_bin_prefix: str) -> dict[str, Any]:
    if conn is None:
        return spec
    needs_inference = any(
        spec.get(key) in (None, "")
        for key in ("fps", "duration_frames", "source_start_frame", "source_start_tc", "source_path", "folder")
    )
    if not needs_inference:
        return spec
    match = _resolve_live_clip_match(conn, spec, temp_bin_prefix=temp_bin_prefix)
    if not match:
        return spec
    clip = match.get("clip")
    props = match.get("_props") or media_pool._clip_properties(clip)
    inferred = dict(spec)

    resolved_source_path = match.get("_resolved_source_path") or media_pool._canonical_source_path(props, clip)
    if not inferred.get("source_path") and resolved_source_path:
        inferred["source_path"] = resolved_source_path
        inferred["source_path_inferred"] = True
    if not inferred.get("folder") and match.get("folder"):
        inferred["folder"] = str(match.get("folder"))
        inferred["folder_inferred"] = True

    clip_fps = inferred.get("fps")
    if clip_fps in (None, ""):
        for key in ("FPS", "Camera FPS", "Frame Rate"):
            raw_value = props.get(key)
            if raw_value in (None, ""):
                continue
            try:
                clip_fps = float(str(raw_value).strip())
                break
            except (TypeError, ValueError):
                continue
        if clip_fps not in (None, ""):
            inferred["fps"] = clip_fps
            inferred["fps_inferred"] = True

    fps = float(inferred["fps"]) if inferred.get("fps") not in (None, "") else None
    if inferred.get("duration_frames") in (None, "") and fps:
        duration_raw = str(props.get("Duration") or "").strip()
        if duration_raw:
            try:
                inferred["duration_frames"] = int(seconds_to_frames(timecode_to_seconds(duration_raw, fps), fps))
                inferred["duration_frames_inferred"] = True
            except Exception:
                pass

    if inferred.get("source_start_frame") in (None, "") and inferred.get("source_start_tc") in (None, "") and fps:
        for key in _SOURCE_START_TC_KEYS:
            raw_value = props.get(key)
            if raw_value in (None, ""):
                continue
            try:
                inferred["source_start_tc"] = str(raw_value).strip()
                inferred["source_start_frame"] = _timecode_to_frames(str(raw_value).strip(), fps)
                inferred["source_start_frame_inferred"] = True
                break
            except Exception:
                continue

    return inferred


def _normalize_source_spec(
    raw: dict[str, Any],
    *,
    index: int,
    conn,
    temp_bin_prefix: str,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValidationError(
            "Each multicam recovery source spec must be a JSON object.",
            details={"index": index, "entry": raw},
            recoverability="not_applicable",
        )
    normalized = {
        "clip_name": str(raw.get("clip_name") or raw.get("clip") or raw.get("name") or "").strip(),
        "source_path": str(raw.get("source_path") or raw.get("path") or raw.get("media_path") or "").strip() or None,
        "folder": str(raw.get("folder") or raw.get("folder_path") or raw.get("bin") or "").strip() or None,
        "duration_frames": raw.get("duration_frames", raw.get("duration")),
        "fps": raw.get("fps"),
        "source_start_frame": raw.get("source_start_frame", raw.get("source_start")),
        "source_start_tc": raw.get("source_start_tc"),
        "source_start_offset_frames": raw.get("source_start_offset_frames", raw.get("source_start_offset")),
        "index": index,
    }
    if not normalized["clip_name"]:
        raise ValidationError(
            "Each multicam recovery source spec requires clip_name.",
            details={"index": index, "entry": raw},
            recoverability="not_applicable",
        )

    normalized = _infer_source_spec_from_resolve(
        conn,
        normalized,
        temp_bin_prefix=temp_bin_prefix,
    )

    if normalized.get("fps") not in (None, ""):
        normalized["fps"] = _coerce_positive_float(normalized["fps"], field="fps")
    if normalized.get("duration_frames") not in (None, ""):
        normalized["duration_frames"] = _coerce_positive_int(
            normalized["duration_frames"],
            field="duration_frames",
        )
    if normalized.get("source_start_offset_frames") not in (None, ""):
        normalized["source_start_offset_frames"] = _coerce_positive_int(
            normalized["source_start_offset_frames"],
            field="source_start_offset_frames",
            allow_zero=True,
        )
    else:
        normalized["source_start_offset_frames"] = 0

    source_start_frame = normalized.get("source_start_frame")
    source_start_tc = normalized.get("source_start_tc")
    if source_start_frame not in (None, ""):
        normalized["source_start_frame"] = _coerce_positive_int(
            source_start_frame,
            field="source_start_frame",
            allow_zero=True,
        )
    if source_start_tc not in (None, ""):
        if normalized.get("fps") in (None, ""):
            raise ValidationError(
                "source_start_tc requires fps.",
                details={"index": index, "clip_name": normalized["clip_name"]},
                recoverability="not_applicable",
            )
        parsed_source_start_frame = _timecode_to_frames(str(source_start_tc), float(normalized["fps"]))
        if normalized.get("source_start_frame") not in (None, parsed_source_start_frame):
            raise ValidationError(
                "source_start_frame and source_start_tc refer to different frame counts.",
                details={
                    "index": index,
                    "clip_name": normalized["clip_name"],
                    "source_start_frame": normalized.get("source_start_frame"),
                    "source_start_tc": source_start_tc,
                    "source_start_tc_frames": parsed_source_start_frame,
                },
                recoverability="not_applicable",
            )
        normalized["source_start_frame"] = parsed_source_start_frame
    return normalized


def _normalize_source_specs(
    source_specs: list[dict[str, Any]] | None,
    *,
    conn,
    temp_bin_prefix: str,
) -> list[dict[str, Any]]:
    if not source_specs:
        raise ValidationError(
            "multicam recover-timing requires source specs.",
            details={"reason": "missing_source_specs"},
            recoverability="not_applicable",
        )
    return [
        _normalize_source_spec(
            dict(spec),
            index=index,
            conn=conn,
            temp_bin_prefix=temp_bin_prefix,
        )
        for index, spec in enumerate(source_specs)
    ]


def _resolve_multicam_target(
    cursor: sqlite3.Cursor,
    *,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
) -> dict[str, Any]:
    normalized_name = str(multicam_name or "").strip()
    normalized_media_id = str(media_id or "").strip()
    normalized_sequence_id = str(sequence_id or "").strip()
    if not normalized_name and not normalized_media_id and not normalized_sequence_id:
        raise ValidationError(
            "multicam recover-timing requires --multicam-name, --media-id, or --sequence-id.",
            details={"reason": "missing_multicam_identifier"},
            recoverability="not_applicable",
        )

    clauses = ["media.DbType = 'Sm2MpMulticamClip'"]
    params: list[Any] = []
    if normalized_name:
        clauses.append("media.Name = ?")
        params.append(normalized_name)
    if normalized_media_id:
        clauses.append("media.Sm2MpMedia_id = ?")
        params.append(normalized_media_id)
    if normalized_sequence_id:
        clauses.append("seq.Sm2Sequence_id = ?")
        params.append(normalized_sequence_id)

    rows = cursor.execute(
        f"""
        SELECT
            media.Sm2MpMedia_id,
            media.Name,
            media.DbType,
            seq.Sm2Sequence_id,
            container.Sm2SequenceContainer_id,
            media.Sequence,
            seq.FrameRate,
            seq.MediaExtents
        FROM Sm2MpMedia media
        JOIN Sm2Sequence seq ON seq.Sm2MpMedia_id = media.Sm2MpMedia_id
        JOIN Sm2SequenceContainer container ON container.Sm2Sequence_id = seq.Sm2Sequence_id
        WHERE {" AND ".join(clauses)}
        ORDER BY LOWER(media.Name), media.Sm2MpMedia_id, seq.Sm2Sequence_id
        """,
        tuple(params),
    ).fetchall()
    candidates = [
        {
            "multicam_media_id": str(row[0] or ""),
            "multicam_name": str(row[1] or ""),
            "db_type": str(row[2] or ""),
            "multicam_sequence_id": str(row[3] or ""),
            "multicam_sequence_container_id": str(row[4] or ""),
        }
        for row in rows
    ]
    if not rows:
        raise ValidationError(
            "Could not find a native multicam clip matching the requested selector.",
            details={
                "reason": "multicam_not_found",
                "multicam_name": normalized_name or None,
                "multicam_media_id": normalized_media_id or None,
                "multicam_sequence_id": normalized_sequence_id or None,
                "candidates": [],
            },
            recoverability="not_applicable",
        )
    if len(rows) > 1:
        raise ValidationError(
            "Multicam selector is ambiguous; provide --media-id or --sequence-id.",
            details={
                "reason": "ambiguous_multicam_name",
                "multicam_name": normalized_name or None,
                "candidates": candidates,
            },
            recoverability="not_applicable",
        )
    row = rows[0]
    if str(row[2] or "") != "Sm2MpMulticamClip":
        raise ValidationError(
            "Requested selector does not refer to a native multicam clip.",
            details={
                "reason": "not_native_multicam",
                "multicam_name": normalized_name or None,
                "multicam_media_id": normalized_media_id or None,
                "multicam_sequence_id": normalized_sequence_id or None,
                "db_type": str(row[2] or ""),
            },
            recoverability="not_applicable",
        )
    sequence_fps = _decode_rate_blob(row[6]) if row[6] not in (None, b"") else None
    return {
        "multicam_media_id": str(row[0] or ""),
        "multicam_name": str(row[1] or ""),
        "db_type": str(row[2] or ""),
        "multicam_sequence_id": str(row[3] or ""),
        "multicam_sequence_container_id": str(row[4] or ""),
        "media_sequence": str(row[5] or "") or None,
        "sequence_fps": float(sequence_fps) if sequence_fps else None,
        "sequence_media_extents_blob": bytes(row[7]) if row[7] is not None else None,
        "sequence_media_extents_hex": bytes(row[7]).hex().upper() if row[7] is not None else None,
    }


def _load_sequence_item_rows(cursor: sqlite3.Cursor, *, sequence_container_id: str) -> list[dict[str, Any]]:
    rows = cursor.execute(
        """
        SELECT
            rel.DbPropertyName,
            rel.DbIndex,
            track.Type AS TrackType,
            track.Sm2TiTrack_id,
            item.Sm2TiItem_id,
            item.DbType,
            item.Name,
            item.Start,
            item.Duration,
            item."In" AS InValue,
            item.MediaRef,
            item.MediaStartTime,
            item.MediaTimemapBA
        FROM Sm2SequenceContainer_Sm2TiTrack rel
        JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = rel.DbAssociate
        JOIN Sm2TiItem item ON item.Sm2TiTrack_id = track.Sm2TiTrack_id
        WHERE rel.DbOwner = ?
          AND rel.DbPropertyName IN ('VideoTrackVec', 'AudioTrackVec')
        ORDER BY rel.DbPropertyName, rel.DbIndex, item.DbType, item.Sm2TiItem_id
        """,
        (sequence_container_id,),
    ).fetchall()
    return [
        {
            "track_property": str(row[0] or ""),
            "angle_index": int(row[1] or 0),
            "track_type": int(row[2] or 0),
            "track_id": str(row[3] or ""),
            "item_id": str(row[4] or ""),
            "db_type": str(row[5] or ""),
            "name": str(row[6] or ""),
            "start": str(row[7] or "0"),
            "duration": str(row[8] or "0"),
            "in_value": str(row[9] or "") or None,
            "media_ref": str(row[10] or ""),
            "media_start_time": float(row[11]) if row[11] not in (None, "") else None,
            "media_timemap_ba": bytes(row[12]) if row[12] is not None else None,
        }
        for row in rows
    ]


def _build_item_counts(item_rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "video_tracks": len({row["track_id"] for row in item_rows if row["track_type"] == 0}),
        "audio_tracks": len({row["track_id"] for row in item_rows if row["track_type"] == 1}),
        "video_items": sum(1 for row in item_rows if row["track_type"] == 0),
        "audio_items": sum(1 for row in item_rows if row["track_type"] == 1),
    }


def _require_recovery_flags(
    *,
    apply_timemap: bool,
    apply_source_start_tc: bool,
    apply_media_extents: bool,
) -> None:
    if apply_timemap or apply_source_start_tc or apply_media_extents:
        return
    raise ValidationError(
        "multicam recover-timing requires at least one apply flag.",
        details={
            "apply_timemap": apply_timemap,
            "apply_source_start_tc": apply_source_start_tc,
            "apply_media_extents": apply_media_extents,
        },
        recoverability="not_applicable",
    )


def _build_recovery_plan(
    cursor: sqlite3.Cursor,
    *,
    project_db_path: str,
    source_specs: list[dict[str, Any]],
    multicam_name: str | None,
    media_id: str | None,
    sequence_id: str | None,
    apply_timemap: bool,
    apply_source_start_tc: bool,
    apply_media_extents: bool,
    verify_reopen: bool,
    ops_module,
) -> dict[str, Any]:
    _require_recovery_flags(
        apply_timemap=apply_timemap,
        apply_source_start_tc=apply_source_start_tc,
        apply_media_extents=apply_media_extents,
    )
    target = _resolve_multicam_target(
        cursor,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
    )
    resolved_sources = _source_rows.resolve_source_media_rows(
        project_db_path,
        resolved_angles=source_specs,
        resolved_db_media_row_cls=ops_module.ResolvedDbMediaRow,
        row_to_dict_fn=ops_module._row_to_dict,
        temp_bin_prefix=ops_module._TEMP_BIN_PREFIX,
        return_diagnostics=True,
    )

    items_before = _load_sequence_item_rows(
        cursor,
        sequence_container_id=target["multicam_sequence_container_id"],
    )
    if not items_before:
        raise ValidationError(
            "Native multicam sequence has no internal items to recover.",
            details={
                "reason": "multicam_items_missing",
                **target,
            },
            recoverability="not_applicable",
        )
    counts_before = _build_item_counts(items_before)

    source_infos: list[dict[str, Any]] = []
    source_info_by_media_id: dict[str, dict[str, Any]] = {}
    if len(resolved_sources) != len(source_specs):
        raise ValidationError(
            "Resolved source rows do not match source spec count.",
            details={
                "requested_count": len(source_specs),
                "resolved_count": len(resolved_sources),
            },
            recoverability="not_applicable",
        )

    for spec, resolved in zip(source_specs, resolved_sources):
        row = resolved["row"]
        resolution = dict(resolved["resolution"])
        fps = spec.get("fps")
        duration_frames = spec.get("duration_frames")
        source_start_frame = spec.get("source_start_frame")
        if fps in (None, ""):
            raise ValidationError(
                "Source spec is missing fps and DaVinci Resolve could not infer it.",
                details={"clip_name": spec["clip_name"], "index": spec["index"]},
                recoverability="not_applicable",
            )
        if (apply_source_start_tc or apply_media_extents) and duration_frames in (None, ""):
            raise ValidationError(
                "duration_frames is required for source start/media extents recovery.",
                details={"clip_name": spec["clip_name"], "index": spec["index"]},
                recoverability="not_applicable",
            )
        if apply_source_start_tc and source_start_frame in (None, ""):
            raise ValidationError(
                "source_start_frame or source_start_tc is required when --apply-source-start-tc is set.",
                details={"clip_name": spec["clip_name"], "index": spec["index"]},
                recoverability="not_applicable",
            )
        source_info = {
            "index": int(spec["index"]),
            "angle_index": int(spec["index"]),
            "clip_name": spec["clip_name"],
            "folder": spec.get("folder"),
            "source_path": spec.get("source_path"),
            "fps": float(fps),
            "duration_frames": int(duration_frames) if duration_frames not in (None, "") else None,
            "source_start_frame": int(source_start_frame) if source_start_frame not in (None, "") else None,
            "source_start_tc": spec.get("source_start_tc"),
            "source_start_offset_frames": int(spec.get("source_start_offset_frames") or 0),
            "media_id": row.media_id,
            "resolved_name": row.name,
            "resolved_folder_path": row.folder_path,
            "resolved_source_path": row.source_path,
            "resolution": resolution,
        }
        source_infos.append(source_info)
        source_info_by_media_id[row.media_id] = source_info

    sequence_fps = next(
        (
            float(source["fps"])
            for source in source_infos
            if float(source["fps"]) > 0
        ),
        float(target.get("sequence_fps") or 24.0),
    )
    sequence_extents_before = _decode_sequence_media_extents(
        target.get("sequence_media_extents_blob"),
        sequence_fps,
    )

    updated_items: list[dict[str, Any]] = []
    expected_items: list[dict[str, Any]] = []
    patched_item_ids: list[str] = []
    items_after: list[dict[str, Any]] = []
    for item in items_before:
        source_info = source_info_by_media_id.get(item["media_ref"])
        if source_info is None:
            items_after.append(dict(item))
            continue
        current_duration_frames = max(1, int(item["duration"] or 0))
        expected_duration_frames = (
            int(source_info["duration_frames"])
            if apply_source_start_tc and source_info["duration_frames"] is not None
            else current_duration_frames
        )
        expected_start_frame = (
            int(source_info["source_start_frame"]) + int(source_info["source_start_offset_frames"])
            if apply_source_start_tc and source_info["source_start_frame"] is not None
            else int(item["start"] or 0)
        )
        expected_media_start_time = (
            float(expected_start_frame) / float(source_info["fps"])
            if apply_source_start_tc and source_info["source_start_frame"] is not None
            else item["media_start_time"]
        )
        expected_timemap_ba = (
            _encode_recovery_media_timemap_ba(expected_duration_frames, float(source_info["fps"]))
            if (apply_timemap or apply_source_start_tc)
            else item["media_timemap_ba"]
        )
        expected_item = {
            "item_id": item["item_id"],
            "db_type": item["db_type"],
            "track_type": item["track_type"],
            "track_property": item["track_property"],
            "angle_index": item["angle_index"],
            "media_ref": item["media_ref"],
            "start": str(expected_start_frame),
            "duration": str(expected_duration_frames),
            "media_start_time": expected_media_start_time,
            "media_timemap_hex": expected_timemap_ba.hex().upper() if expected_timemap_ba is not None else None,
            "source_media_id": source_info["media_id"],
            "clip_name": source_info["clip_name"],
            "duration_frames": expected_duration_frames,
        }
        expected_items.append(expected_item)
        items_after.append(
            {
                **item,
                "start": expected_item["start"],
                "duration": expected_item["duration"],
                "media_start_time": expected_item["media_start_time"],
                "media_timemap_ba": expected_timemap_ba,
            }
        )
        changed = False
        if (apply_timemap or apply_source_start_tc) and expected_item["media_timemap_hex"] != (
            item["media_timemap_ba"].hex().upper() if item["media_timemap_ba"] is not None else None
        ):
            changed = True
        if apply_source_start_tc:
            if expected_item["start"] != str(item["start"] or "0"):
                changed = True
            if expected_item["duration"] != str(item["duration"] or "0"):
                changed = True
            if expected_item["media_start_time"] != item["media_start_time"]:
                changed = True
        if changed:
            patched_item_ids.append(item["item_id"])
            updated_items.append(expected_item)

    if apply_media_extents:
        sequence_start_frame = min(
            int(source["source_start_frame"] or 0) + int(source["source_start_offset_frames"] or 0)
            for source in source_infos
        )
        max_end_frame = max(
            (int(source["source_start_frame"] or 0) + int(source["source_start_offset_frames"] or 0))
            + int(source["duration_frames"] or 0)
            for source in source_infos
        )
        sequence_duration_frames = max(1, max_end_frame - sequence_start_frame)
        sequence_extents_after_blob = _encode_recovery_sequence_media_extents(
            sequence_start_frame,
            sequence_duration_frames,
            sequence_fps,
        )
        sequence_extents_after = {
            "start_frame": int(sequence_start_frame),
            "duration_frames": int(sequence_duration_frames),
            "start_seconds": float(sequence_start_frame) / float(sequence_fps),
            "duration_seconds": float(sequence_duration_frames) / float(sequence_fps),
            "hex": sequence_extents_after_blob.hex().upper(),
        }
    else:
        sequence_extents_after = sequence_extents_before
        sequence_extents_after_blob = target.get("sequence_media_extents_blob")

    would_change = bool(updated_items)
    if apply_media_extents:
        before_hex = sequence_extents_before["hex"] if sequence_extents_before else None
        after_hex = sequence_extents_after["hex"] if sequence_extents_after else None
        would_change = would_change or before_hex != after_hex

    return {
        "action": "multicam.recover_timing",
        "changed": would_change,
        "selector": {
            "multicam_name": multicam_name,
            "multicam_media_id": media_id,
            "multicam_sequence_id": sequence_id,
        },
        "resolved_target": {
            key: value
            for key, value in target.items()
            if key != "sequence_media_extents_blob"
        },
        "flags": {
            "apply_timemap": bool(apply_timemap),
            "apply_source_start_tc": bool(apply_source_start_tc),
            "apply_media_extents": bool(apply_media_extents),
            "verify_reopen": bool(verify_reopen),
        },
        "source_resolution": source_infos,
        "source_start_offsets_frames": [int(source["source_start_offset_frames"]) for source in source_infos],
        "before_summary": {
            "counts": counts_before,
            "sequence_extents": sequence_extents_before,
        },
        "after_summary": {
            "counts": counts_before,
            "sequence_extents": sequence_extents_after,
        },
        "updated_items": updated_items,
        "expected_items": expected_items,
        "patched_item_ids": patched_item_ids,
        "sequence_extents": {
            "before": sequence_extents_before,
            "after": sequence_extents_after,
        },
        "sequence_fps": float(sequence_fps),
        "expected_video_track_count": counts_before["video_tracks"],
        "expected_audio_track_count": counts_before["audio_tracks"],
        "expected_video_item_count": counts_before["video_items"],
        "expected_audio_item_count": counts_before["audio_items"],
    }


def plan_multicam_timing_recovery(
    project_db_path: str,
    *,
    source_specs: list[dict[str, Any]] | None,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    apply_timemap: bool = False,
    apply_source_start_tc: bool = False,
    apply_media_extents: bool = False,
    verify_reopen: bool = False,
    conn=None,
    ops_module,
) -> dict[str, Any]:
    normalized_source_specs = _normalize_source_specs(
        source_specs,
        conn=conn,
        temp_bin_prefix=ops_module._TEMP_BIN_PREFIX,
    )
    connection = sqlite3.connect(project_db_path)
    try:
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        plan = _build_recovery_plan(
            cursor,
            project_db_path=project_db_path,
            source_specs=normalized_source_specs,
            multicam_name=multicam_name,
            media_id=media_id,
            sequence_id=sequence_id,
            apply_timemap=apply_timemap,
            apply_source_start_tc=apply_source_start_tc,
            apply_media_extents=apply_media_extents,
            verify_reopen=verify_reopen,
            ops_module=ops_module,
        )
    finally:
        connection.close()
    return plan


def _write_multicam_timing_recovery(
    cursor: sqlite3.Cursor,
    *,
    plan: dict[str, Any],
) -> dict[str, Any]:
    current_items = _load_sequence_item_rows(
        cursor,
        sequence_container_id=str(plan["resolved_target"]["multicam_sequence_container_id"]),
    )
    current_item_ids = {row["item_id"] for row in current_items}
    missing_item_ids = [
        entry["item_id"]
        for entry in plan.get("expected_items") or []
        if entry["item_id"] not in current_item_ids
    ]
    if missing_item_ids:
        raise ValidationError(
            "Native multicam sequence changed before recover-timing could write it.",
            details={
                "reason": "multicam_items_changed",
                "missing_item_ids": missing_item_ids,
                "resolved_target": plan["resolved_target"],
            },
        )

    expected_by_item_id = {
        entry["item_id"]: entry
        for entry in plan.get("expected_items") or []
    }
    for item_id in plan.get("patched_item_ids") or []:
        expected = expected_by_item_id[item_id]
        cursor.execute(
            """
            UPDATE Sm2TiItem
            SET Start = ?,
                Duration = ?,
                MediaStartTime = ?,
                MediaTimemapBA = ?
            WHERE Sm2TiItem_id = ?
            """,
            (
                expected["start"],
                expected["duration"],
                expected["media_start_time"],
                sqlite3.Binary(bytes.fromhex(expected["media_timemap_hex"])) if expected.get("media_timemap_hex") else None,
                item_id,
            ),
        )

    sequence_extents_after = plan.get("sequence_extents", {}).get("after")
    sequence_extents_before = plan.get("sequence_extents", {}).get("before")
    if sequence_extents_after and sequence_extents_after != sequence_extents_before:
        cursor.execute(
            "UPDATE Sm2Sequence SET MediaExtents = ? WHERE Sm2Sequence_id = ?",
            (
                sqlite3.Binary(bytes.fromhex(sequence_extents_after["hex"])),
                str(plan["resolved_target"]["multicam_sequence_id"]),
            ),
        )

    sqlite_health = _sqlite_project_db_health_from_connection(cursor.connection)
    if not sqlite_health["ok"]:
        raise ValidationError(
            "Native multicam timing recovery produced an invalid Project.db state.",
            details={
                "reason": "sqlite_integrity_failed",
                "sqlite_health": sqlite_health,
                "resolved_target": plan["resolved_target"],
            },
        )

    payload = {
        key: value
        for key, value in plan.items()
        if key not in {"expected_items", "patched_item_ids"}
    }
    payload["sqlite_health"] = sqlite_health
    return payload


def _verify_multicam_recovery(
    fresh_conn,
    mutation_result: dict[str, Any],
    session: db_session.DiskDbMutationSession,
) -> dict[str, Any]:
    project_db_path = str(session.project_db_path)
    resolved_target = mutation_result["resolved_target"]
    health = _sqlite_project_db_health_from_path(project_db_path)
    checks: list[dict[str, Any]] = [
        {
            "name": "sqlite_integrity_check",
            "ok": bool(health.get("ok")),
            "status": health.get("status"),
            "foreign_key_failure_count": health.get("foreign_key_failure_count"),
        }
    ]

    connection = sqlite3.connect(project_db_path)
    try:
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        target = _resolve_multicam_target(
            cursor,
            media_id=str(resolved_target["multicam_media_id"]),
        )
        checks.append(
            {
                "name": "multicam_target_exists",
                "ok": True,
                "multicam_media_id": target["multicam_media_id"],
                "multicam_sequence_id": target["multicam_sequence_id"],
            }
        )
        item_rows = _load_sequence_item_rows(
            cursor,
            sequence_container_id=target["multicam_sequence_container_id"],
        )
        counts = _build_item_counts(item_rows)
        checks.extend(
            [
                {
                    "name": "video_track_count_preserved",
                    "ok": counts["video_tracks"] == mutation_result["expected_video_track_count"],
                    "expected": mutation_result["expected_video_track_count"],
                    "actual": counts["video_tracks"],
                },
                {
                    "name": "audio_track_count_preserved",
                    "ok": counts["audio_tracks"] == mutation_result["expected_audio_track_count"],
                    "expected": mutation_result["expected_audio_track_count"],
                    "actual": counts["audio_tracks"],
                },
                {
                    "name": "video_item_count_preserved",
                    "ok": counts["video_items"] == mutation_result["expected_video_item_count"],
                    "expected": mutation_result["expected_video_item_count"],
                    "actual": counts["video_items"],
                },
                {
                    "name": "audio_item_count_preserved",
                    "ok": counts["audio_items"] == mutation_result["expected_audio_item_count"],
                    "expected": mutation_result["expected_audio_item_count"],
                    "actual": counts["audio_items"],
                },
            ]
        )
        actual_by_item_id = {row["item_id"]: row for row in item_rows}
        for expected in mutation_result.get("updated_items") or []:
            actual = actual_by_item_id.get(expected["item_id"])
            checks.append(
                {
                    "name": f"item_exists:{expected['item_id']}",
                    "ok": actual is not None,
                }
            )
            if actual is None:
                continue
            checks.extend(
                [
                    {
                        "name": f"item_start:{expected['item_id']}",
                        "ok": str(actual["start"] or "0") == str(expected["start"]),
                        "expected": str(expected["start"]),
                        "actual": str(actual["start"] or "0"),
                    },
                    {
                        "name": f"item_duration:{expected['item_id']}",
                        "ok": str(actual["duration"] or "0") == str(expected["duration"]),
                        "expected": str(expected["duration"]),
                        "actual": str(actual["duration"] or "0"),
                    },
                    {
                        "name": f"item_media_start_time:{expected['item_id']}",
                        "ok": actual["media_start_time"] == expected["media_start_time"],
                        "expected": expected["media_start_time"],
                        "actual": actual["media_start_time"],
                    },
                    {
                        "name": f"item_media_timemap:{expected['item_id']}",
                        "ok": (actual["media_timemap_ba"].hex().upper() if actual["media_timemap_ba"] is not None else None)
                        == expected["media_timemap_hex"],
                        "expected": expected["media_timemap_hex"],
                        "actual": actual["media_timemap_ba"].hex().upper() if actual["media_timemap_ba"] is not None else None,
                    },
                ]
            )

        expected_sequence_extents = mutation_result.get("sequence_extents", {}).get("after")
        if expected_sequence_extents:
            actual_extents_blob = cursor.execute(
                "SELECT MediaExtents FROM Sm2Sequence WHERE Sm2Sequence_id = ?",
                (target["multicam_sequence_id"],),
            ).fetchone()
            actual_extents_hex = (
                bytes(actual_extents_blob[0]).hex().upper()
                if actual_extents_blob and actual_extents_blob[0] is not None
                else None
            )
            checks.append(
                {
                    "name": "sequence_media_extents",
                    "ok": actual_extents_hex == expected_sequence_extents["hex"],
                    "expected": expected_sequence_extents["hex"],
                    "actual": actual_extents_hex,
                }
            )
    finally:
        connection.close()

    if mutation_result.get("flags", {}).get("verify_reopen"):
        match_count = 0
        root = fresh_conn.media_pool.GetRootFolder() if getattr(fresh_conn, "media_pool", None) is not None else None
        if root is not None:
            matches: list[dict[str, Any]] = []
            media_pool._collect_clip_matches(root, str(resolved_target["multicam_name"]), "", matches)
            match_count = len(matches)
        checks.append(
            {
                "name": "reopen_multicam_exists_in_media_pool",
                "ok": match_count >= 1,
                "multicam_name": resolved_target["multicam_name"],
                "match_count": match_count,
            }
        )

    status = "verified" if all(bool(check.get("ok")) for check in checks) else "failed"
    verification = {
        "status": status,
        "checks": checks,
        "sqlite_health": health,
    }
    if status != "verified":
        raise ValidationError(
            "Native multicam timing recovery verification failed.",
            details={"verification": verification, "resolved_target": resolved_target},
        )
    return verification


def recover_multicam_timing(
    conn,
    *,
    source_specs: list[dict[str, Any]] | None,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    apply_timemap: bool = False,
    apply_source_start_tc: bool = False,
    apply_media_extents: bool = False,
    verify_reopen: bool = False,
    ops_module,
) -> dict[str, Any]:
    current_database = resolve_current_disk_project_db(conn)
    project_db_path = str(current_database["project_db_path"])
    plan = plan_multicam_timing_recovery(
        project_db_path,
        source_specs=source_specs,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        apply_timemap=apply_timemap,
        apply_source_start_tc=apply_source_start_tc,
        apply_media_extents=apply_media_extents,
        verify_reopen=verify_reopen,
        conn=conn,
        ops_module=ops_module,
    )
    return db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Native multicam recover timing",
        writer=lambda _connection, cursor, _session: _write_multicam_timing_recovery(cursor, plan=plan),
        verifier=_verify_multicam_recovery,
    )
