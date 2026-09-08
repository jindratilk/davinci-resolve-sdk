"""Mutations Nodes helpers for Color Page DB operations."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import sqlite3
import struct
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from ...errors import APICallFailed, ValidationError
from ..db_session import DiskDbMutationSession, execute_sqlite_disk_db_mutation
from ..db_timeline_rows import find_ti_item_row
from .constants import *
from .proto_codec import *
from .version_body import *
from .transforms import *
from .params import *
from .proto_sections import *
from .curves import *
from .hdr import *
from .node_graph import *
from .power_windows import *
from .cst_hsv import *
from .grade_state import *
from .mutations_color import *


def write_hsv_node_saturation_with_key_output(
    conn: Any,
    *,
    clip_name: str | None = None,
    key_output_gain: float,
    connection_factory: Callable[[], Any] | None = None,
    **hsv_kwargs: Any,
) -> dict[str, Any]:
    gain_value = float(key_output_gain)
    validate_key_output_gain(gain_value)

    hsv_result = write_hsv_node_saturation(conn, clip_name=clip_name, **hsv_kwargs)
    key_conn = connection_factory() if connection_factory is not None else conn
    key_output_result = write_key_output(key_conn, clip_name=clip_name, gain=gain_value)
    hsv_verification = hsv_result.get("verification") if isinstance(hsv_result, dict) else None
    key_verification = key_output_result.get("verification") if isinstance(key_output_result, dict) else None
    clip_label = None
    if isinstance(key_output_result, dict):
        clip_label = key_output_result.get("clip")
    if clip_label is None and isinstance(hsv_result, dict):
        clip_label = hsv_result.get("clip")
    return {
        "clip": clip_label,
        "route": "db_workaround_color_page_hsv_node_key_output",
        "db_session_route": {
            "hsv_node": hsv_result.get("db_session_route") if isinstance(hsv_result, dict) else None,
            "key_output": key_output_result.get("db_session_route") if isinstance(key_output_result, dict) else None,
        },
        "key_output_gain": gain_value,
        "hsv_node": hsv_result,
        "key_output": key_output_result,
        "verification": {
            "status": (
                "verified"
                if isinstance(hsv_verification, dict)
                and hsv_verification.get("status") == "verified"
                and isinstance(key_verification, dict)
                and key_verification.get("status") == "verified"
                else "pending_manual"
            ),
            "hsv_node": hsv_verification,
            "key_output": key_verification,
        },
        "readback": {
            "hsv_node": hsv_result.get("hsv_node") if isinstance(hsv_result, dict) else None,
            "key_output": key_output_result.get("key_output") if isinstance(key_output_result, dict) else None,
        },
    }


def _normalize_qualifier_scalar(value: float, *, option_name: str, percent_ok: bool = True) -> float:
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValidationError(
            f"Color Page Qualifier {option_name} must be a finite number.",
            details={option_name: value},
            recoverability="not_applicable",
        )
    if percent_ok and numeric > 1.0:
        numeric = numeric / 100.0
    if numeric < 0.0 or numeric > 1.0:
        raise ValidationError(
            f"Color Page Qualifier {option_name} must be between 0 and 1, or 0 and 100 percent.",
            details={option_name: value, "normalized": numeric},
            recoverability="not_applicable",
        )
    return numeric


def _parse_qualifier_range(value: str, *, option_name: str, hue: bool = False) -> tuple[float, float, float]:
    raw = str(value or "").strip()
    if not raw:
        raise ValidationError(
            f"Color Page Qualifier {option_name} range must not be empty.",
            details={option_name: value},
            recoverability="not_applicable",
        )
    normalized = raw.replace("..", ",").replace(":", ",")
    parts = [part.strip() for part in normalized.split(",") if part.strip()]
    if len(parts) != 2:
        raise ValidationError(
            f"Color Page Qualifier {option_name} range must be two values, e.g. 180,230.",
            details={option_name: value},
            recoverability="not_applicable",
        )
    try:
        low = float(parts[0])
        high = float(parts[1])
    except ValueError as exc:
        raise ValidationError(
            f"Color Page Qualifier {option_name} range values must be numeric.",
            details={option_name: value},
            recoverability="not_applicable",
        ) from exc
    if not math.isfinite(low) or not math.isfinite(high):
        raise ValidationError(
            f"Color Page Qualifier {option_name} range values must be finite.",
            details={option_name: value},
            recoverability="not_applicable",
        )

    if hue:
        if abs(low) > 1.0 or abs(high) > 1.0:
            if low < 0.0 or low > 360.0 or high < 0.0 or high > 360.0:
                raise ValidationError(
                    "Color Page Qualifier hue range must be 0-1 turns or 0-360 degrees.",
                    details={"hue": value},
                    recoverability="not_applicable",
                )
            low = (low % 360.0) / 360.0
            high = (high % 360.0) / 360.0
        else:
            if low < 0.0 or low > 1.0 or high < 0.0 or high > 1.0:
                raise ValidationError(
                    "Color Page Qualifier hue range must be 0-1 turns or 0-360 degrees.",
                    details={"hue": value},
                    recoverability="not_applicable",
                )
        span = high - low if high >= low else (high + 1.0) - low
        if span <= 0.0 or span > 1.0:
            raise ValidationError(
                "Color Page Qualifier hue range must cover a non-zero span.",
                details={"hue": value, "normalized_low": low, "normalized_high": high},
                recoverability="not_applicable",
            )
        center = (low + span / 2.0) % 1.0
        width = min(0.5, span / 2.0)
        return center, width, span

    if abs(low) > 1.0 or abs(high) > 1.0:
        low = low / 100.0
        high = high / 100.0
    if low < 0.0 or low > 1.0 or high < 0.0 or high > 1.0 or high <= low:
        raise ValidationError(
            f"Color Page Qualifier {option_name} range must be ascending within 0-1 or 0-100 percent.",
            details={option_name: value, "normalized_low": low, "normalized_high": high},
            recoverability="not_applicable",
        )
    span = high - low
    return low + span / 2.0, span / 2.0, span


def _qualifier_expected_params(
    *,
    hue: str | None = None,
    saturation: str | None = None,
    luma: str | None = None,
    softness: float | None = None,
    hue_softness: float | None = None,
    saturation_softness: float | None = None,
    luma_softness: float | None = None,
    blur: float | None = None,
    clean_black: float | None = None,
    clean_white: float | None = None,
) -> tuple[dict[int, float], dict[int, int], dict[str, Any]]:
    params: dict[int, float] = {}
    raw_mode_params: dict[int, int] = {
        PARAM_QUAL_MODE: 0,
    }
    summary: dict[str, Any] = {}

    global_softness = None
    if softness is not None:
        global_softness = _normalize_qualifier_scalar(float(softness), option_name="softness")
    hue_soft = global_softness if hue_softness is None else _normalize_qualifier_scalar(
        float(hue_softness),
        option_name="hue_softness",
    )
    sat_soft = global_softness if saturation_softness is None else _normalize_qualifier_scalar(
        float(saturation_softness),
        option_name="saturation_softness",
    )
    lum_soft = global_softness if luma_softness is None else _normalize_qualifier_scalar(
        float(luma_softness),
        option_name="luma_softness",
    )

    if hue is not None:
        center, width, span = _parse_qualifier_range(hue, option_name="hue", hue=True)
        params[PARAM_QUAL_HUE_CENTER] = center
        params[PARAM_QUAL_HUE_WIDTH] = span
        params[PARAM_QUAL_HUE_LOW_SOFT] = hue_soft if hue_soft is not None else span
        if hue_soft is not None:
            params[PARAM_QUAL_HUE_HIGH_SOFT] = hue_soft
        summary["hue"] = {"center": center, "width": span, "half_width": width, "span": span}
    if saturation is not None:
        center, width, span = _parse_qualifier_range(saturation, option_name="saturation")
        low = max(0.0, center - width)
        high = min(1.0, center + width)
        params[PARAM_QUAL_SAT_WIDTH] = 0.0
        if high < 0.999999:
            params[PARAM_QUAL_SAT_HIGH_BOUND] = high
        params[PARAM_QUAL_SAT_LOW_BOUND] = low
        if sat_soft is not None:
            params[PARAM_QUAL_SAT_LOW_CLEAN] = sat_soft
            params[PARAM_QUAL_SAT_HIGH_CLEAN] = sat_soft
        summary["saturation"] = {"low": low, "high": high, "span": span}
    if luma is not None:
        center, width, span = _parse_qualifier_range(luma, option_name="luma")
        low = max(0.0, center - width)
        high = min(1.0, center + width)
        if high < 0.999999:
            params[PARAM_QUAL_LUMA_CENTER] = high
        params[PARAM_QUAL_LUMA_WIDTH] = low
        if lum_soft is not None:
            params[PARAM_QUAL_LUMA_LOW_SOFT] = lum_soft
            params[PARAM_QUAL_LUMA_HIGH_SOFT] = lum_soft
        summary["luma"] = {"low": low, "high": high, "span": span}
    if blur is not None:
        params[PARAM_QUAL_MATTE_BLUR] = _normalize_qualifier_scalar(float(blur), option_name="blur")
    if clean_black is not None:
        params[PARAM_QUAL_MATTE_CLEAN_BLACK] = _normalize_qualifier_scalar(
            float(clean_black),
            option_name="clean_black",
        )
    if clean_white is not None:
        params[PARAM_QUAL_MATTE_CLEAN_WHITE] = _normalize_qualifier_scalar(
            float(clean_white),
            option_name="clean_white",
        )
    if not params:
        raise ValidationError(
            "Color Page Qualifier Matte refinement requires at least one range or matte control.",
            details={
                "required_any": [
                    "hue",
                    "saturation",
                    "luma",
                    "softness with a range",
                    "blur",
                    "clean_black",
                    "clean_white",
                ]
            },
            recoverability="not_applicable",
        )
    return params, raw_mode_params, summary


def _qualifier_stale_param_keys_for_request(
    *,
    hue: str | None = None,
    saturation: str | None = None,
    luma: str | None = None,
    softness: float | None = None,
    hue_softness: float | None = None,
    saturation_softness: float | None = None,
    luma_softness: float | None = None,
) -> set[int]:
    delete_keys: set[int] = {PARAM_QUAL_MATTE_MODE}
    if hue is not None and softness is None and hue_softness is None:
        delete_keys.add(PARAM_QUAL_HUE_HIGH_SOFT)
    if saturation is not None:
        center, width, _span = _parse_qualifier_range(saturation, option_name="saturation")
        high = min(1.0, center + width)
        delete_keys.add(PARAM_QUAL_SAT_CENTER)
        if high >= 0.999999:
            delete_keys.add(PARAM_QUAL_SAT_HIGH_BOUND)
        if softness is None and saturation_softness is None:
            delete_keys.update({PARAM_QUAL_SAT_LOW_CLEAN, PARAM_QUAL_SAT_HIGH_CLEAN})
    if luma is not None:
        center, width, _span = _parse_qualifier_range(luma, option_name="luma")
        high = min(1.0, center + width)
        if high >= 0.999999:
            delete_keys.add(PARAM_QUAL_LUMA_CENTER)
        if softness is None and luma_softness is None:
            delete_keys.update({PARAM_QUAL_LUMA_LOW_SOFT, PARAM_QUAL_LUMA_HIGH_SOFT})
    return delete_keys


def write_legacy_qualifier_matte_refinement(
    conn: Any,
    *,
    clip_name: str | None = None,
    node_index: int = 1,
    hue: str | None = None,
    saturation: str | None = None,
    luma: str | None = None,
    softness: float | None = None,
    hue_softness: float | None = None,
    saturation_softness: float | None = None,
    luma_softness: float | None = None,
    blur: float | None = None,
    clean_black: float | None = None,
    clean_white: float | None = None,
) -> dict[str, Any]:
    """Write native Color Page HSL qualifier matte controls via Project.db."""
    target_node_index = int(node_index)
    if target_node_index < 1:
        raise ValidationError(
            "Color Page Qualifier node index must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    params, mode_params, range_summary = _qualifier_expected_params(
        hue=hue,
        saturation=saturation,
        luma=luma,
        softness=softness,
        hue_softness=hue_softness,
        saturation_softness=saturation_softness,
        luma_softness=luma_softness,
        blur=blur,
        clean_black=clean_black,
        clean_white=clean_white,
    )
    delete_keys = _qualifier_stale_param_keys_for_request(
        hue=hue,
        saturation=saturation,
        luma=luma,
        softness=softness,
        hue_softness=hue_softness,
        saturation_softness=saturation_softness,
        luma_softness=luma_softness,
    )
    raw_entries = {
        key: _build_varint_param_entry_content(key, value)
        for key, value in mode_params.items()
    }

    from ..db_timeline_selection import resolve_video_group

    item_ref = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None

    def _expected_param_payload() -> dict[str, float | int]:
        result: dict[str, float | int] = {
            PARAM_NAMES.get(key, f"0x{key:08X}"): value
            for key, value in params.items()
        }
        result.update({
            PARAM_NAMES.get(key, f"0x{key:08X}"): value
            for key, value in mode_params.items()
        })
        return result

    def _verify_params_readback(
        state: ColorGradeState,
        *,
        readback_node_index: int | None = None,
        tolerance: float = 0.001,
    ) -> list[dict[str, Any]]:
        expected_node_index = int(readback_node_index or target_node_index)
        actual_by_key = {
            param.key: param.value
            for param in state.params
            if int(param.node_index) == expected_node_index
        }
        mismatches: list[dict[str, Any]] = []
        for key, expected_value in params.items():
            actual_value = actual_by_key.get(key)
            if actual_value is None or abs(float(actual_value) - expected_value) > tolerance:
                mismatches.append(
                    {
                        "key": f"0x{key:08X}",
                        "name": PARAM_NAMES.get(key, f"0x{key:08X}"),
                        "expected": expected_value,
                        "actual": actual_value,
                    }
                )
        for key, expected_value in mode_params.items():
            actual_value = actual_by_key.get(key)
            if actual_value is None or int(actual_value) != int(expected_value):
                mismatches.append(
                    {
                        "key": f"0x{key:08X}",
                        "name": PARAM_NAMES.get(key, f"0x{key:08X}"),
                        "expected": expected_value,
                        "actual": actual_value,
                    }
                )
        return mismatches

    def writer(connection: Any, cursor: sqlite3.Cursor, session: DiskDbMutationSession) -> dict[str, Any]:
        row = find_ti_item_row(
            cursor,
            item=item_ref,
            db_type="Sm2TiVideoClip",
            timeline_name=timeline_name,
        )
        clip_id = row["Sm2TiItem_id"]
        ver_table_id = row["pLmVerTable"]
        ver = _select_active_grade_version(cursor, str(ver_table_id)) if ver_table_id else None

        created_version_table = False
        created_version = False
        readback_node_index = target_node_index
        if ver and ver["Body"]:
            base_proto = decompress_version_body(ver["Body"])
            new_proto = _inject_params_into_proto(
                base_proto,
                params,
                node_index=target_node_index,
                delete_keys=delete_keys,
            )
            new_proto = _inject_raw_param_entries_into_proto(
                new_proto,
                raw_entries,
                node_index=target_node_index,
            )
            readback_node_index = _param_readback_node_index_for_color_node_index(
                new_proto,
                target_node_index,
            )
            cursor.execute(
                '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
                   WHERE "ListMgt::LmVersion_id" = ?''',
                (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
            )
            session.steps.append("update_qualifier_matte_refinement")
        else:
            base_body = None
            if ver_table_id:
                base_ver = cursor.execute(
                    '''SELECT v.Body FROM "ListMgt::LmVersion" v
                       JOIN "ListMgt::LmVersion_ListMgt::LmVersionTable" rel
                         ON rel.DbAssociate = v."ListMgt::LmVersion_id"
                       WHERE rel.DbOwner = ?
                       ORDER BY v.rowid LIMIT 1''',
                    (ver_table_id,),
                ).fetchone()
                if base_ver:
                    base_body = base_ver["Body"]
            if base_body:
                base_proto = decompress_version_body(base_body)
            else:
                base_proto = decompress_version_body(bytes.fromhex(_BASELINE_VERSION_BODY_HEX))
            new_proto = _inject_params_into_proto(
                base_proto,
                params,
                node_index=target_node_index,
                delete_keys=delete_keys,
            )
            new_proto = _inject_raw_param_entries_into_proto(
                new_proto,
                raw_entries,
                node_index=target_node_index,
            )
            readback_node_index = _param_readback_node_index_for_color_node_index(
                new_proto,
                target_node_index,
            )
            if not ver_table_id:
                ver_table_id = _create_lm_version_table_for_item(
                    cursor,
                    item_id=str(clip_id),
                    fields_blob=bytes.fromhex(_VERSION_TABLE_FIELDS_BLOB_HEX),
                )
                created_version_table = True
            version_id = str(uuid.uuid4())
            _insert_lm_version_from_body(
                cursor,
                body=compress_version_body(new_proto),
                version_id=version_id,
                version_table_id=str(ver_table_id),
            )
            created_version = True
            session.steps.append("create_qualifier_matte_refinement")
            if created_version_table:
                session.steps.append("create_grade_version_table")

        state = read_color_grade(cursor, clip_id=clip_id, clip_name=item_ref.name)
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "created_version_table": created_version_table,
            "created_version": created_version,
            "node_index": target_node_index,
            "readback_node_index": readback_node_index,
            "qualifier": range_summary,
            "params_written": _expected_param_payload(),
            "readback": state.to_dict(),
        }

    def verifier(
        _fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Page Qualifier Matte DB mutation did not return a mutation payload for verification.",
                details={"mutation_result": mutation_result},
            )
        clip_id = mutation_result.get("clip_id")
        clip_label = str(mutation_result.get("clip") or clip_name or "")
        connection = sqlite3.connect(session.project_db_path)
        connection.row_factory = sqlite3.Row
        try:
            cursor = connection.cursor()
            if not clip_id:
                row = cursor.execute(
                    "SELECT Sm2TiItem_id FROM Sm2TiItem WHERE DbType = 'Sm2TiVideoClip' AND Name = ?",
                    (clip_label,),
                ).fetchone()
                if row:
                    clip_id = row["Sm2TiItem_id"]
            if not clip_id:
                raise ValidationError(
                    "Could not resolve the written clip during Color Page Qualifier Matte verification.",
                    details={"clip": clip_label},
                )
            state = read_color_grade(cursor, clip_id=str(clip_id), clip_name=clip_label)
        finally:
            connection.close()

        readback_node_index = int(mutation_result.get("readback_node_index") or target_node_index)
        mismatches = _verify_params_readback(state, readback_node_index=readback_node_index)
        if mismatches:
            raise APICallFailed(
                "Color Page Qualifier Matte DB mutation did not verify after project reload.",
                details={
                    "clip": clip_label,
                    "project_db_path": session.project_db_path,
                    "node_index": target_node_index,
                    "readback_node_index": readback_node_index,
                    "params_written": _expected_param_payload(),
                    "mismatches": mismatches,
                    "readback": state.to_dict(),
                },
                recoverability="manual",
            )
        return {
            "status": "db_readback_verified",
            "clip": clip_label,
            "node_index": target_node_index,
            "readback_node_index": readback_node_index,
            "params_verified": _expected_param_payload(),
            "render_proof_status": "not_performed",
            "render_proof_required": True,
            "note": (
                "Project.db readback matched after project reload for native HSL qualifier/matte keys. "
                "Use a render proof before declaring a visual grade successful."
            ),
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page qualifier matte db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    if isinstance(result, dict):
        result["db_session_route"] = result.get("route")
        result["route"] = "db_workaround_color_page_qualifier_matte_refinement"
        verification = result.get("verification")
        if isinstance(verification, dict):
            result["qualifier_readback"] = {
                "node_index": verification.get("node_index"),
                "readback_node_index": verification.get("readback_node_index"),
                "params": verification.get("params_verified"),
            }
    return result


def write_hdr_global(
    conn: Any,
    *,
    clip_name: str | None = None,
    exposure: float | None = None,
    saturation: float | None = None,
) -> dict[str, Any]:
    if exposure is None and saturation is None:
        raise ValidationError(
            "No HDR Global parameters specified.",
            recoverability="not_applicable",
        )
    exposure_value = None if exposure is None else float(exposure)
    saturation_value = None if saturation is None else float(saturation)
    if exposure_value is not None:
        _validate_hdr_global_value("exposure", exposure_value, minimum=-4.0, maximum=4.0)
    if saturation_value is not None:
        _validate_hdr_global_value("saturation", saturation_value, minimum=0.0, maximum=4.0)

    from ..db_timeline_selection import resolve_video_group

    item_ref = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None

    def writer(connection: Any, cursor: sqlite3.Cursor, session: DiskDbMutationSession) -> dict[str, Any]:
        row = find_ti_item_row(
            cursor,
            item=item_ref,
            db_type="Sm2TiVideoClip",
            timeline_name=timeline_name,
        )
        clip_id = row["Sm2TiItem_id"]
        ver_table_id = row["pLmVerTable"]
        ver = _select_active_grade_version(cursor, str(ver_table_id)) if ver_table_id else None

        if not ver or not ver["Body"]:
            raise APICallFailed(
                "Color Page HDR Global route requires an existing grade version.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        base_proto = decompress_version_body(ver["Body"])
        new_proto, seeded, expected = _inject_hdr_global_into_proto(
            base_proto,
            exposure=exposure_value,
            saturation=saturation_value,
        )
        cursor.execute(
            '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
               WHERE "ListMgt::LmVersion_id" = ?''',
            (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
        )
        session.steps.append("update_hdr_global")
        state = read_color_grade(cursor, clip_id=clip_id, clip_name=item_ref.name)
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "hdr_global_written": expected,
            "seeded_hdr_global_state": seeded,
            "readback": state.to_dict(),
            "route": "db_workaround_color_page_hdr_global",
        }

    def verifier(
        _fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Page HDR Global DB mutation did not return a mutation payload for verification.",
                details={"mutation_result": mutation_result},
            )
        clip_id = mutation_result.get("clip_id")
        clip_label = str(mutation_result.get("clip") or clip_name or "")
        expected = mutation_result.get("hdr_global_written")
        if not isinstance(expected, dict):
            raise APICallFailed(
                "Color Page HDR Global DB mutation did not return expected values for verification.",
                details={"mutation_result": mutation_result},
            )
        connection = sqlite3.connect(session.project_db_path)
        connection.row_factory = sqlite3.Row
        try:
            cursor = connection.cursor()
            if not clip_id:
                row = cursor.execute(
                    "SELECT Sm2TiItem_id FROM Sm2TiItem WHERE DbType = 'Sm2TiVideoClip' AND Name = ?",
                    (clip_label,),
                ).fetchone()
                if row:
                    clip_id = row["Sm2TiItem_id"]
            if not clip_id:
                raise ValidationError(
                    "Could not resolve the written clip during HDR Global DB verification.",
                    details={"clip": clip_label},
                )
            state = read_color_grade(cursor, clip_id=str(clip_id), clip_name=clip_label)
        finally:
            connection.close()

        actual = _hdr_global_readback_from_params(state.params)
        mismatches: dict[str, Any] = {}
        if not actual:
            mismatches["global"] = {"expected": expected, "actual": None}
        if not _has_hdr_global_companion_state(state.params):
            mismatches["companion_state"] = {
                "expected": "gui_fixture_backed_hdr_global_state",
                "actual": "missing_or_incomplete",
            }
        if actual:
            for key, expected_value in expected.items():
                actual_value = float(actual.get(key, float("nan")))
                if not math.isfinite(actual_value) or abs(actual_value - expected_value) > 0.001:
                    mismatches[key] = {"expected": expected_value, "actual": actual.get(key)}
        if mismatches:
            raise APICallFailed(
                "Color Page HDR Global DB mutation did not verify after project reload.",
                details={
                    "clip": clip_label,
                    "project_db_path": session.project_db_path,
                    "expected": expected,
                    "mismatches": mismatches,
                    "readback": state.to_dict(),
                },
                recoverability="manual",
            )
        return {
            "status": "verified",
            "clip": clip_label,
            "hdr_global": actual,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page hdr global db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    if isinstance(result, dict):
        result["db_session_route"] = result.get("route")
        result["route"] = "db_workaround_color_page_hdr_global"
    return result


def validate_key_output_gain(value: float) -> None:
    if not math.isfinite(value):
        raise ValidationError(
            "Color Page Key Output Gain must be a finite number.",
            details={"value": value},
            recoverability="not_applicable",
        )
    if value < 0.0 or value > 1.0:
        raise ValidationError(
            "Color Page Key Output Gain must be between 0 and 1.",
            details={"value": value, "minimum": 0, "maximum": 1},
            recoverability="not_applicable",
        )


def write_key_output(
    conn: Any,
    *,
    clip_name: str | None = None,
    gain: float,
) -> dict[str, Any]:
    gain_value = float(gain)
    validate_key_output_gain(gain_value)

    from ..db_timeline_selection import resolve_video_group

    item_ref = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None

    def writer(connection: Any, cursor: sqlite3.Cursor, session: DiskDbMutationSession) -> dict[str, Any]:
        row = find_ti_item_row(
            cursor,
            item=item_ref,
            db_type="Sm2TiVideoClip",
            timeline_name=timeline_name,
        )
        clip_id = row["Sm2TiItem_id"]
        ver_table_id = row["pLmVerTable"]
        ver = _select_active_grade_version(cursor, str(ver_table_id)) if ver_table_id else None

        if not ver or not ver["Body"]:
            raise APICallFailed(
                "Color Page Key Output route requires an existing grade version.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        base_proto = decompress_version_body(ver["Body"])
        new_proto = _inject_key_output_gain_into_proto(base_proto, gain_value)
        cursor.execute(
            '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
               WHERE "ListMgt::LmVersion_id" = ?''',
            (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
        )
        session.steps.append("update_key_output_gain")
        state = read_color_grade(cursor, clip_id=clip_id, clip_name=item_ref.name)
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "key_output_written": {"gain": gain_value},
            "readback": state.to_dict(),
            "route": "db_workaround_color_page_key_output",
        }

    def verifier(
        _fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Page Key Output DB mutation did not return a mutation payload for verification.",
                details={"mutation_result": mutation_result},
            )
        clip_id = mutation_result.get("clip_id")
        clip_label = str(mutation_result.get("clip") or clip_name or "")
        connection = sqlite3.connect(session.project_db_path)
        connection.row_factory = sqlite3.Row
        try:
            cursor = connection.cursor()
            if not clip_id:
                row = cursor.execute(
                    "SELECT Sm2TiItem_id FROM Sm2TiItem WHERE DbType = 'Sm2TiVideoClip' AND Name = ?",
                    (clip_label,),
                ).fetchone()
                if row:
                    clip_id = row["Sm2TiItem_id"]
            if not clip_id:
                raise ValidationError(
                    "Could not resolve the written clip during Key Output DB verification.",
                    details={"clip": clip_label},
                )
            state = read_color_grade(cursor, clip_id=str(clip_id), clip_name=clip_label)
        finally:
            connection.close()

        actual = state.key_output
        actual_gain = None if actual is None else actual.get("gain")
        if actual_gain is None or abs(float(actual_gain) - gain_value) > 0.001:
            raise APICallFailed(
                "Color Page Key Output DB mutation did not verify after project reload.",
                details={
                    "clip": clip_label,
                    "project_db_path": session.project_db_path,
                    "expected": {"gain": gain_value},
                    "actual": actual,
                    "readback": state.to_dict(),
                },
                recoverability="manual",
            )
        return {
            "status": "verified",
            "clip": clip_label,
            "key_output": {"gain": float(actual_gain)},
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page key output db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    if isinstance(result, dict):
        result["db_session_route"] = result.get("route")
        result["route"] = "db_workaround_color_page_key_output"
        readback = result.get("readback")
        if isinstance(readback, dict):
            result["key_output"] = readback.get("key_output", {"gain": gain_value})
        else:
            result["key_output"] = {"gain": gain_value}
        verification = result.get("verification")
        if isinstance(verification, dict):
            result["key_output"] = verification.get("key_output", result["key_output"])
    return result


def write_node_label(
    conn: Any,
    *,
    clip_name: str | None = None,
    node_index: int,
    label: str,
) -> dict[str, Any]:
    """Set a native Color Page node label via Project.db when SetNodeLabel is unavailable."""
    from ..db_timeline_selection import resolve_video_group

    item_ref = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None
    target_node_index = int(node_index)
    normalized_label = str(label)

    def writer(connection: Any, cursor: sqlite3.Cursor, session: DiskDbMutationSession) -> dict[str, Any]:
        row = find_ti_item_row(
            cursor,
            item=item_ref,
            db_type="Sm2TiVideoClip",
            timeline_name=timeline_name,
        )
        clip_id = row["Sm2TiItem_id"]
        ver_table_id = row["pLmVerTable"]
        ver = _select_active_grade_version(cursor, str(ver_table_id)) if ver_table_id else None

        if not ver or not ver["Body"]:
            raise APICallFailed(
                "Color Page node label route requires an existing grade version.",
                details={"clip": item_ref.name, "node_index": target_node_index},
                recoverability="manual",
            )

        base_proto = decompress_version_body(ver["Body"])
        new_proto, label_result = _set_node_label_in_proto(
            base_proto,
            node_index=target_node_index,
            label=normalized_label,
        )
        cursor.execute(
            '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
               WHERE "ListMgt::LmVersion_id" = ?''',
            (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
        )
        session.steps.append("set_color_page_node_label")
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "route": "db_workaround_color_page_node_label_set",
            **label_result,
        }

    def verifier(
        fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Page node label DB mutation did not return a mutation payload for verification.",
                details={"mutation_result": mutation_result},
            )
        clip_id = mutation_result.get("clip_id")
        clip_label = str(mutation_result.get("clip") or clip_name or "")
        expected_label = str(mutation_result.get("label") or "")
        db_label = None
        db_node_count = None
        connection = sqlite3.connect(session.project_db_path)
        connection.row_factory = sqlite3.Row
        try:
            cursor = connection.cursor()
            if not clip_id:
                row = cursor.execute(
                    "SELECT Sm2TiItem_id FROM Sm2TiItem WHERE DbType = 'Sm2TiVideoClip' AND Name = ?",
                    (clip_label,),
                ).fetchone()
                if row:
                    clip_id = row["Sm2TiItem_id"]
            if not clip_id:
                raise ValidationError(
                    "Could not resolve the written clip during Color Page node label verification.",
                    details={"clip": clip_label},
                )
            version_row = _select_active_grade_version_for_clip(cursor, str(clip_id))
            if not version_row or not version_row["Body"]:
                raise APICallFailed(
                    "Color Page node label DB verification could not read the active grade version.",
                    details={"clip": clip_label, "clip_id": clip_id},
                )
            containers = _root_color_node_containers(decompress_version_body(version_row["Body"]))
            db_node_count = len(containers)
            for container in containers:
                if _get_first_varint_field(container, 2) == target_node_index:
                    db_label = _decode_node_label(container)
                    break
        finally:
            connection.close()

        if db_label != expected_label:
            raise APICallFailed(
                "Color Page node label DB mutation did not verify by DB readback.",
                details={
                    "clip": clip_label,
                    "node_index": target_node_index,
                    "expected_label": expected_label,
                    "db_label": db_label,
                    "project_db_path": session.project_db_path,
                },
                recoverability="manual",
            )

        api_label = None
        if fresh_conn is not None:
            try:
                from .. import color_ops

                api_label = color_ops.get_node_label(fresh_conn, clip_label or None, target_node_index)
            except Exception:
                api_label = None
        if api_label is not None and api_label != expected_label:
            raise APICallFailed(
                "Color Page node label DB mutation did not verify through DaVinci Resolve node label readback.",
                details={
                    "clip": clip_label,
                    "node_index": target_node_index,
                    "expected_label": expected_label,
                    "api_label": api_label,
                    "db_label": db_label,
                },
                recoverability="manual",
            )
        return {
            "status": "verified",
            "clip": clip_label,
            "node_index": target_node_index,
            "label": expected_label,
            "db_label": db_label,
            "api_label": api_label,
            "db_node_count": db_node_count,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page node label db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    if isinstance(result, dict):
        result["db_session_route"] = result.get("route")
        result["route"] = "db_workaround_color_page_node_label_set"
        verification = result.get("verification")
        if isinstance(verification, dict):
            result["label"] = verification.get("label", result.get("label"))
            result["readback"] = {
                "db_label": verification.get("db_label"),
                "api_label": verification.get("api_label"),
            }
    return result


def write_rgb_mixer_monochrome(
    conn: Any,
    *,
    clip_name: str | None = None,
    node_index: int = 1,
    monochrome: bool = True,
    preserve_luminance: bool = True,
) -> dict[str, Any]:
    """Set the verified native RGB Mixer Monochrome + Preserve Luminance mode via Project.db."""
    if int(node_index) < 1:
        raise ValidationError(
            "Node index must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    if monochrome and not preserve_luminance:
        raise ValidationError(
            "RGB Mixer Monochrome without Preserve Luminance is not yet fixture-backed.",
            details={"monochrome": monochrome, "preserve_luminance": preserve_luminance},
            recoverability="not_applicable",
        )

    from ..db_timeline_selection import resolve_video_group

    item_ref = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None
    target_node_index = int(node_index)

    def writer(connection: Any, cursor: sqlite3.Cursor, session: DiskDbMutationSession) -> dict[str, Any]:
        row = find_ti_item_row(
            cursor,
            item=item_ref,
            db_type="Sm2TiVideoClip",
            timeline_name=timeline_name,
        )
        clip_id = row["Sm2TiItem_id"]
        ver_table_id = row["pLmVerTable"]
        ver = _select_active_grade_version(cursor, str(ver_table_id)) if ver_table_id else None

        if not ver or not ver["Body"]:
            raise APICallFailed(
                "RGB Mixer Monochrome route requires an existing grade version.",
                details={"clip": item_ref.name, "node_index": target_node_index},
                recoverability="manual",
            )

        base_proto = decompress_version_body(ver["Body"])
        new_proto, mono_result = _set_rgb_mixer_monochrome_in_proto(
            base_proto,
            node_index=target_node_index,
            enabled=bool(monochrome),
        )
        cursor.execute(
            '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
               WHERE "ListMgt::LmVersion_id" = ?''',
            (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
        )
        session.steps.append("set_rgb_mixer_monochrome")
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "route": "db_workaround_color_page_rgb_mixer_monochrome",
            **mono_result,
        }

    def verifier(
        fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "RGB Mixer Monochrome DB mutation did not return a mutation payload for verification.",
                details={"mutation_result": mutation_result},
            )
        clip_id = mutation_result.get("clip_id")
        clip_label = str(mutation_result.get("clip") or clip_name or "")
        expected_enabled = bool(monochrome)
        db_mode = None
        db_node_count = None
        connection = sqlite3.connect(session.project_db_path)
        connection.row_factory = sqlite3.Row
        try:
            cursor = connection.cursor()
            if not clip_id:
                row = cursor.execute(
                    "SELECT Sm2TiItem_id FROM Sm2TiItem WHERE DbType = 'Sm2TiVideoClip' AND Name = ?",
                    (clip_label,),
                ).fetchone()
                if row:
                    clip_id = row["Sm2TiItem_id"]
            if not clip_id:
                raise ValidationError(
                    "Could not resolve the written clip during RGB Mixer Monochrome verification.",
                    details={"clip": clip_label},
                )
            version_row = _select_active_grade_version_for_clip(cursor, str(clip_id))
            if not version_row or not version_row["Body"]:
                raise APICallFailed(
                    "RGB Mixer Monochrome DB verification could not read the active grade version.",
                    details={"clip": clip_label, "clip_id": clip_id},
                )
            containers = _root_color_node_containers(decompress_version_body(version_row["Body"]))
            db_node_count = len(containers)
            for container in containers:
                if _get_first_varint_field(container, 2) == target_node_index:
                    db_mode = _rgb_mixer_monochrome_mode_from_container(container)
                    break
        finally:
            connection.close()

        actual_enabled = db_mode == 4
        if actual_enabled != expected_enabled:
            raise APICallFailed(
                "RGB Mixer Monochrome DB mutation did not verify by DB readback.",
                details={
                    "clip": clip_label,
                    "node_index": target_node_index,
                    "expected_monochrome": expected_enabled,
                    "db_mode": db_mode,
                    "project_db_path": session.project_db_path,
                },
                recoverability="manual",
            )

        api_node_count = None
        if fresh_conn is not None:
            try:
                from .. import color_ops

                graph = color_ops._get_node_graph(fresh_conn, clip_label or None)
                api_node_count = graph.get("node_count") if isinstance(graph, dict) else None
            except Exception:
                api_node_count = None
        return {
            "status": "verified",
            "clip": clip_label,
            "node_index": target_node_index,
            "monochrome": actual_enabled,
            "preserve_luminance": actual_enabled,
            "db_mode": db_mode,
            "db_node_count": db_node_count,
            "api_node_count": api_node_count,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page rgb mixer monochrome db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    if isinstance(result, dict):
        result["db_session_route"] = result.get("route")
        result["route"] = "db_workaround_color_page_rgb_mixer_monochrome"
        verification = result.get("verification")
        if isinstance(verification, dict):
            result["monochrome"] = verification.get("monochrome", result.get("monochrome"))
            result["preserve_luminance"] = verification.get("preserve_luminance", result.get("preserve_luminance"))
            result["readback"] = {
                "db_mode": verification.get("db_mode"),
                "monochrome": verification.get("monochrome"),
                "preserve_luminance": verification.get("preserve_luminance"),
                "api_node_count": verification.get("api_node_count"),
            }
    return result


__all__ = (
    'write_hsv_node_saturation_with_key_output',
    '_parse_qualifier_range',
    '_qualifier_expected_params',
    'write_legacy_qualifier_matte_refinement',
    'write_hdr_global',
    'validate_key_output_gain',
    'write_key_output',
    'write_node_label',
    'write_rgb_mixer_monochrome',
)
