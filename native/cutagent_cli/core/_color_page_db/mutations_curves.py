"""Mutations Curves helpers for Color Page DB operations."""

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
from .mutations_nodes import *


def write_custom_curve_points(
    conn: Any,
    *,
    clip_name: str | None = None,
    y: list[CurvePoint] | None = None,
    red: list[CurvePoint] | None = None,
    green: list[CurvePoint] | None = None,
    blue: list[CurvePoint] | None = None,
) -> dict[str, Any]:
    channel_points = {
        channel: points
        for channel, points in {
            "y": y,
            "red": red,
            "green": green,
            "blue": blue,
        }.items()
        if points is not None
    }
    if not channel_points:
        raise ValidationError(
            "No Color Page Custom Curves control points specified.",
            recoverability="not_applicable",
        )

    from ..db_timeline_selection import resolve_video_group

    item_ref = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None
    expected_readback = {
        channel: _curve_points_for_readback(points)
        for channel, points in channel_points.items()
    }

    def writer(connection: Any, cursor: sqlite3.Cursor, session: DiskDbMutationSession) -> dict[str, Any]:
        row = find_ti_item_row(
            cursor,
            item=item_ref,
            db_type="Sm2TiVideoClip",
            timeline_name=timeline_name,
        )
        clip_id = row["Sm2TiItem_id"]
        ver_table_id = row["pLmVerTable"]
        ver = None
        if ver_table_id:
            ver = _select_active_grade_version(cursor, str(ver_table_id))

        if not ver or not ver["Body"]:
            raise APICallFailed(
                "Color Page Custom Curves control-point route requires an existing grade version.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        base_proto = decompress_version_body(ver["Body"])
        new_proto = _inject_curve_points_into_proto(base_proto, channel_points)
        cursor.execute(
            '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
               WHERE "ListMgt::LmVersion_id" = ?''',
            (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
        )
        session.steps.append("update_custom_curve_points")
        state = read_color_grade(cursor, clip_id=clip_id, clip_name=item_ref.name)
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "curve_points_written": expected_readback,
            "readback": state.to_dict(),
        }

    def verifier(
        _fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Page Custom Curves DB mutation did not return a mutation payload for verification.",
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
                    "Could not resolve the written clip during Custom Curves DB verification.",
                    details={"clip": clip_label},
                )
            state = read_color_grade(cursor, clip_id=str(clip_id), clip_name=clip_label)
        finally:
            connection.close()

        actual = state.curves.get("control_points", {})
        mismatches = [
            {
                "channel": channel,
                "expected": expected,
                "actual": actual.get(channel),
            }
            for channel, expected in expected_readback.items()
            if not _curve_points_match(actual.get(channel), expected)
        ]
        if mismatches:
            raise APICallFailed(
                "Color Page Custom Curves DB mutation did not verify after project reload.",
                details={
                    "clip": clip_label,
                    "project_db_path": session.project_db_path,
                    "mismatches": mismatches,
                    "readback": state.to_dict(),
                },
                recoverability="manual",
            )

        return {
            "status": "db_readback_verified",
            "clip": clip_label,
            "curve_points_verified": expected_readback,
            "render_proof_status": "not_performed",
            "render_proof_required": True,
            "note": (
                "Project.db readback matched after project reload. This does not prove that "
                "DaVinci Resolve applied the curve in rendered pixels."
            ),
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page custom curves db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    result["db_session_route"] = result.get("route")
    result["route"] = "db_workaround_color_page_custom_curves_points"
    result["curve_points"] = expected_readback
    return result


def write_split_tone_curves(
    conn: Any,
    *,
    clip_name: str | None = None,
    strength: float = 1.0,
    shadow_cool: float = 0.06,
    highlight_warm: float = 0.06,
    shadow_lift: float = 0.0,
    highlight_lift: float = 0.0,
    pivot: float = 0.5,
    rolloff: float = 1.0,
    shadow_r: float | None = None,
    shadow_g: float | None = None,
    shadow_b: float | None = None,
    highlight_r: float | None = None,
    highlight_g: float | None = None,
    highlight_b: float | None = None,
    y_mood: float = 0.0,
) -> dict[str, Any]:
    curves = build_split_tone_curve_points(
        strength=strength,
        shadow_cool=shadow_cool,
        highlight_warm=highlight_warm,
        shadow_lift=shadow_lift,
        highlight_lift=highlight_lift,
        pivot=pivot,
        rolloff=rolloff,
        shadow_r=shadow_r,
        shadow_g=shadow_g,
        shadow_b=shadow_b,
        highlight_r=highlight_r,
        highlight_g=highlight_g,
        highlight_b=highlight_b,
        y_mood=y_mood,
    )
    result = write_custom_curve_points(
        conn,
        clip_name=clip_name,
        y=curves.get("y"),
        red=curves["red"],
        green=curves["green"],
        blue=curves["blue"],
    )
    result["base_route"] = result.get("route")
    result["route"] = "db_workaround_color_page_split_tone"
    result["split_tone"] = {
        "strength": float(strength),
        "shadow_cool": float(shadow_cool),
        "highlight_warm": float(highlight_warm),
        "shadow_lift": float(shadow_lift),
        "highlight_lift": float(highlight_lift),
        "pivot": float(pivot),
        "rolloff": float(rolloff),
        "shadow_rgb": {
            "red": None if shadow_r is None else float(shadow_r),
            "green": None if shadow_g is None else float(shadow_g),
            "blue": None if shadow_b is None else float(shadow_b),
        },
        "highlight_rgb": {
            "red": None if highlight_r is None else float(highlight_r),
            "green": None if highlight_g is None else float(highlight_g),
            "blue": None if highlight_b is None else float(highlight_b),
        },
        "y_mood": float(y_mood),
        "channels": {
            channel: [point.to_dict() for point in points]
            for channel, points in curves.items()
        },
    }
    return result


def write_split_tone_curves_with_key_output(
    conn: Any,
    *,
    clip_name: str | None = None,
    key_output_gain: float,
    connection_factory: Callable[[], Any] | None = None,
    **split_tone_kwargs: Any,
) -> dict[str, Any]:
    gain_value = float(key_output_gain)
    validate_key_output_gain(gain_value)

    split_tone_result = write_split_tone_curves(conn, clip_name=clip_name, **split_tone_kwargs)
    key_conn = connection_factory() if connection_factory is not None else conn
    key_output_result = write_key_output(key_conn, clip_name=clip_name, gain=gain_value)
    split_verification = split_tone_result.get("verification") if isinstance(split_tone_result, dict) else None
    key_verification = key_output_result.get("verification") if isinstance(key_output_result, dict) else None
    clip_label = None
    if isinstance(key_output_result, dict):
        clip_label = key_output_result.get("clip")
    if clip_label is None and isinstance(split_tone_result, dict):
        clip_label = split_tone_result.get("clip")
    return {
        "clip": clip_label,
        "route": "db_workaround_color_page_split_tone_key_output",
        "db_session_route": {
            "split_tone": split_tone_result.get("db_session_route") if isinstance(split_tone_result, dict) else None,
            "key_output": key_output_result.get("db_session_route") if isinstance(key_output_result, dict) else None,
        },
        "key_output_gain": gain_value,
        "split_tone": split_tone_result,
        "key_output": key_output_result,
        "verification": {
            "status": (
                "verified"
                if isinstance(split_verification, dict)
                and split_verification.get("status") == "verified"
                and isinstance(key_verification, dict)
                and key_verification.get("status") == "verified"
                else "pending_manual"
            ),
            "split_tone": split_verification,
            "key_output": key_verification,
        },
        "readback": {
            "split_tone": split_tone_result.get("split_tone") if isinstance(split_tone_result, dict) else None,
            "key_output": key_output_result.get("key_output") if isinstance(key_output_result, dict) else None,
        },
    }


def write_hue_vs_hue_curve(
    conn: Any,
    *,
    clip_name: str | None = None,
    input_hue: float,
    hue_rotate: float,
) -> dict[str, Any]:
    input_hue_value = float(input_hue)
    hue_rotate_value = float(hue_rotate)
    hue_curve_input_hue_to_internal(input_hue_value)
    hue_curve_rotate_to_internal(hue_rotate_value)
    expected = {
        "input_hue": round(input_hue_value, 6),
        "hue_rotate": round(hue_rotate_value, 6),
    }

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
        ver = None
        if ver_table_id:
            ver = _select_active_grade_version(cursor, str(ver_table_id))

        if not ver or not ver["Body"]:
            raise APICallFailed(
                "Color Page Hue vs Hue route requires an existing grade version.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        base_proto = decompress_version_body(ver["Body"])
        new_proto = _inject_hue_vs_hue_curve_into_proto(
            base_proto,
            input_hue=input_hue_value,
            hue_rotate=hue_rotate_value,
        )
        cursor.execute(
            '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
               WHERE "ListMgt::LmVersion_id" = ?''',
            (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
        )
        session.steps.append("update_hue_vs_hue_curve")
        state = read_color_grade(cursor, clip_id=clip_id, clip_name=item_ref.name)
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "hue_vs_hue_written": expected,
            "readback": state.to_dict(),
        }

    def verifier(
        _fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Page Hue vs Hue DB mutation did not return a mutation payload for verification.",
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
                    "Could not resolve the written clip during Hue vs Hue DB verification.",
                    details={"clip": clip_label},
                )
            state = read_color_grade(cursor, clip_id=str(clip_id), clip_name=clip_label)
        finally:
            connection.close()

        actual = (state.curves.get("hue_vs_hue") or {}) if state.curves else {}
        mismatches: dict[str, Any] = {}
        for key, expected_value in expected.items():
            actual_value = actual.get(key)
            if actual_value is None or abs(float(actual_value) - expected_value) > 0.01:
                mismatches[key] = {"expected": expected_value, "actual": actual_value}
        if mismatches:
            raise APICallFailed(
                "Color Page Hue vs Hue DB mutation did not verify after project reload.",
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
            "hue_vs_hue": actual,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page hue vs hue db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    result["db_session_route"] = result.get("route")
    result["route"] = "db_workaround_color_page_hue_vs_hue"
    result["hue_vs_hue"] = expected
    return result


def write_hue_curve_points(
    conn: Any,
    *,
    clip_name: str | None = None,
    mode: str,
    points: list[dict[str, float]],
) -> dict[str, Any]:
    config = _hue_curve_points_mode_config(mode)
    value_key = str(config["value_key"])
    readback_key = str(config["readback_key"])
    label = str(config["label"])
    expected_points = _hue_curve_points_readback(points, value_key=value_key)
    expected = {
        "points": expected_points,
        "point_count": len(expected_points),
    }

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
        ver = None
        if ver_table_id:
            ver = _select_active_grade_version(cursor, str(ver_table_id))

        if not ver or not ver["Body"]:
            raise APICallFailed(
                f"Color Page {label} points route requires an existing grade version.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        base_proto = decompress_version_body(ver["Body"])
        new_proto = _inject_hue_curve_points_into_proto(base_proto, mode=mode, points=points)
        cursor.execute(
            '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
               WHERE "ListMgt::LmVersion_id" = ?''',
            (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
        )
        session.steps.append(str(config["step"]))
        state = read_color_grade(cursor, clip_id=clip_id, clip_name=item_ref.name)
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            f"{readback_key}_points_written": expected,
            "readback": state.to_dict(),
        }

    def verifier(
        _fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                f"Color Page {label} points DB mutation did not return a mutation payload for verification.",
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
                    f"Could not resolve the written clip during {label} points DB verification.",
                    details={"clip": clip_label},
                )
            state = read_color_grade(cursor, clip_id=str(clip_id), clip_name=clip_label)
        finally:
            connection.close()

        actual = (state.curves.get(readback_key) or {}) if state.curves else {}
        actual_points = actual.get("points") or []
        mismatches: list[dict[str, Any]] = []
        if len(actual_points) != len(expected_points):
            mismatches.append({"expected_point_count": len(expected_points), "actual_point_count": len(actual_points)})
        for index, expected_point in enumerate(expected_points):
            actual_point = actual_points[index] if index < len(actual_points) else {}
            for key, expected_value in expected_point.items():
                actual_value = actual_point.get(key)
                if actual_value is None or abs(float(actual_value) - float(expected_value)) > 0.01:
                    mismatches.append(
                        {
                            "index": index,
                            "key": key,
                            "expected": expected_value,
                            "actual": actual_value,
                        }
                    )
        if mismatches:
            raise APICallFailed(
                f"Color Page {label} points DB mutation did not verify after project reload.",
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
            readback_key: actual,
            "points_verified": expected_points,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context=str(config["context"]),
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    result["db_session_route"] = result.get("route")
    result["route"] = str(config["route"])
    result[readback_key] = expected
    return result


def write_hue_vs_hue_curve_points(
    conn: Any,
    *,
    clip_name: str | None = None,
    points: list[dict[str, float]],
) -> dict[str, Any]:
    return write_hue_curve_points(conn, clip_name=clip_name, mode="hue-vs-hue", points=points)


def write_hue_vs_sat_curve(
    conn: Any,
    *,
    clip_name: str | None = None,
    input_hue: float,
    saturation: float,
) -> dict[str, Any]:
    input_hue_value = float(input_hue)
    saturation_value = float(saturation)
    hue_curve_input_hue_to_internal(input_hue_value)
    hue_curve_saturation_to_internal(saturation_value)
    expected = {
        "input_hue": round(input_hue_value, 6),
        "saturation": round(saturation_value, 6),
    }

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
        ver = None
        if ver_table_id:
            ver = _select_active_grade_version(cursor, str(ver_table_id))

        if not ver or not ver["Body"]:
            raise APICallFailed(
                "Color Page Hue vs Sat route requires an existing grade version.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        base_proto = decompress_version_body(ver["Body"])
        new_proto = _inject_hue_vs_sat_curve_into_proto(
            base_proto,
            input_hue=input_hue_value,
            saturation=saturation_value,
        )
        cursor.execute(
            '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
               WHERE "ListMgt::LmVersion_id" = ?''',
            (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
        )
        session.steps.append("update_hue_vs_sat_curve")
        state = read_color_grade(cursor, clip_id=clip_id, clip_name=item_ref.name)
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "hue_vs_sat_written": expected,
            "readback": state.to_dict(),
        }

    def verifier(
        _fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Page Hue vs Sat DB mutation did not return a mutation payload for verification.",
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
                    "Could not resolve the written clip during Hue vs Sat DB verification.",
                    details={"clip": clip_label},
                )
            state = read_color_grade(cursor, clip_id=str(clip_id), clip_name=clip_label)
        finally:
            connection.close()

        actual = (state.curves.get("hue_vs_sat") or {}) if state.curves else {}
        mismatches: dict[str, Any] = {}
        for key, expected_value in expected.items():
            actual_value = actual.get(key)
            if actual_value is None or abs(float(actual_value) - expected_value) > 0.01:
                mismatches[key] = {"expected": expected_value, "actual": actual_value}
        if mismatches:
            raise APICallFailed(
                "Color Page Hue vs Sat DB mutation did not verify after project reload.",
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
            "hue_vs_sat": actual,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page hue vs sat db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    result["db_session_route"] = result.get("route")
    result["route"] = "db_workaround_color_page_hue_vs_sat"
    result["hue_vs_sat"] = expected
    return result


def write_hue_vs_lum_curve(
    conn: Any,
    *,
    clip_name: str | None = None,
    input_hue: float,
    lum_gain: float,
) -> dict[str, Any]:
    input_hue_value = float(input_hue)
    lum_gain_value = float(lum_gain)
    hue_curve_input_hue_to_internal(input_hue_value)
    hue_curve_lum_gain_to_internal(lum_gain_value)
    expected = {
        "input_hue": round(input_hue_value, 6),
        "lum_gain": round(lum_gain_value, 6),
    }

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
        ver = None
        if ver_table_id:
            ver = _select_active_grade_version(cursor, str(ver_table_id))

        if not ver or not ver["Body"]:
            raise APICallFailed(
                "Color Page Hue vs Lum route requires an existing grade version.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        base_proto = decompress_version_body(ver["Body"])
        new_proto = _inject_hue_vs_lum_curve_into_proto(
            base_proto,
            input_hue=input_hue_value,
            lum_gain=lum_gain_value,
        )
        cursor.execute(
            '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
               WHERE "ListMgt::LmVersion_id" = ?''',
            (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
        )
        session.steps.append("update_hue_vs_lum_curve")
        state = read_color_grade(cursor, clip_id=clip_id, clip_name=item_ref.name)
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "hue_vs_lum_written": expected,
            "readback": state.to_dict(),
        }

    def verifier(
        _fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Page Hue vs Lum DB mutation did not return a mutation payload for verification.",
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
                    "Could not resolve the written clip during Hue vs Lum DB verification.",
                    details={"clip": clip_label},
                )
            state = read_color_grade(cursor, clip_id=str(clip_id), clip_name=clip_label)
        finally:
            connection.close()

        actual = (state.curves.get("hue_vs_lum") or {}) if state.curves else {}
        mismatches: dict[str, Any] = {}
        for key, expected_value in expected.items():
            actual_value = actual.get(key)
            if actual_value is None or abs(float(actual_value) - expected_value) > 0.01:
                mismatches[key] = {"expected": expected_value, "actual": actual_value}
        if mismatches:
            raise APICallFailed(
                "Color Page Hue vs Lum DB mutation did not verify after project reload.",
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
            "hue_vs_lum": actual,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page hue vs lum db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    result["db_session_route"] = result.get("route")
    result["route"] = "db_workaround_color_page_hue_vs_lum"
    result["hue_vs_lum"] = expected
    return result


def write_sat_vs_sat_curve(
    conn: Any,
    *,
    clip_name: str | None = None,
    input_sat: float,
    output_sat: float,
) -> dict[str, Any]:
    input_sat_value = float(input_sat)
    output_sat_value = float(output_sat)
    sat_curve_input_sat_to_internal(input_sat_value)
    sat_curve_output_sat_to_internal(output_sat_value)
    expected = {
        "input_sat": round(input_sat_value, 6),
        "output_sat": round(output_sat_value, 6),
    }

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
        ver = None
        if ver_table_id:
            ver = _select_active_grade_version(cursor, str(ver_table_id))

        if not ver or not ver["Body"]:
            raise APICallFailed(
                "Color Page Sat vs Sat route requires an existing grade version.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        base_proto = decompress_version_body(ver["Body"])
        new_proto = _inject_sat_vs_sat_curve_into_proto(
            base_proto,
            input_sat=input_sat_value,
            output_sat=output_sat_value,
        )
        cursor.execute(
            '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
               WHERE "ListMgt::LmVersion_id" = ?''',
            (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
        )
        session.steps.append("update_sat_vs_sat_curve")
        state = read_color_grade(cursor, clip_id=clip_id, clip_name=item_ref.name)
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "sat_vs_sat_written": expected,
            "readback": state.to_dict(),
        }

    def verifier(
        _fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Page Sat vs Sat DB mutation did not return a mutation payload for verification.",
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
                    "Could not resolve the written clip during Sat vs Sat DB verification.",
                    details={"clip": clip_label},
                )
            state = read_color_grade(cursor, clip_id=str(clip_id), clip_name=clip_label)
        finally:
            connection.close()

        actual = (state.curves.get("sat_vs_sat") or {}) if state.curves else {}
        mismatches: dict[str, Any] = {}
        for key, expected_value in expected.items():
            actual_value = actual.get(key)
            if actual_value is None or abs(float(actual_value) - expected_value) > 0.01:
                mismatches[key] = {"expected": expected_value, "actual": actual_value}
        if mismatches:
            raise APICallFailed(
                "Color Page Sat vs Sat DB mutation did not verify after project reload.",
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
            "sat_vs_sat": actual,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page sat vs sat db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    result["db_session_route"] = result.get("route")
    result["route"] = "db_workaround_color_page_sat_vs_sat"
    result["sat_vs_sat"] = expected
    return result


def write_sat_curve_points(
    conn: Any,
    *,
    clip_name: str | None = None,
    mode: str,
    points: list[dict[str, float]],
) -> dict[str, Any]:
    config = _sat_curve_points_mode_config(mode)
    x_key = str(config["x_key"])
    value_key = str(config["value_key"])
    readback_key = str(config["readback_key"])
    label = str(config["label"])
    expected_points = _sat_curve_points_readback(points, x_key=x_key, value_key=value_key)
    expected = {
        "points": expected_points,
        "point_count": len(expected_points),
    }

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
        ver = None
        if ver_table_id:
            ver = _select_active_grade_version(cursor, str(ver_table_id))

        if not ver or not ver["Body"]:
            raise APICallFailed(
                f"Color Page {label} points route requires an existing grade version.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        base_proto = decompress_version_body(ver["Body"])
        new_proto = _inject_sat_curve_points_into_proto(base_proto, mode=mode, points=points)
        cursor.execute(
            '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
               WHERE "ListMgt::LmVersion_id" = ?''',
            (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
        )
        session.steps.append(str(config["step"]))
        state = read_color_grade(cursor, clip_id=clip_id, clip_name=item_ref.name)
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            f"{readback_key}_points_written": expected,
            "readback": state.to_dict(),
        }

    def verifier(
        _fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                f"Color Page {label} points DB mutation did not return a mutation payload for verification.",
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
                    f"Could not resolve the written clip during {label} points DB verification.",
                    details={"clip": clip_label},
                )
            state = read_color_grade(cursor, clip_id=str(clip_id), clip_name=clip_label)
        finally:
            connection.close()

        actual = (state.curves.get(readback_key) or {}) if state.curves else {}
        raw_actual_points = [
            point for point in (actual.get("points") or [])
            if point.get("x_internal") is not None and point.get("y_internal") is not None
        ]
        actual_points = _sat_curve_points_readback(raw_actual_points, x_key=x_key, value_key=value_key)
        mismatches: list[dict[str, Any]] = []
        if len(actual_points) != len(expected_points):
            mismatches.append({"field": "point_count", "expected": len(expected_points), "actual": len(actual_points)})
        for index, expected_point in enumerate(expected_points):
            if index >= len(actual_points):
                break
            actual_point = actual_points[index]
            for key, expected_value in expected_point.items():
                actual_value = actual_point.get(key)
                if actual_value is None or abs(float(actual_value) - float(expected_value)) > 0.01:
                    mismatches.append(
                        {
                            "point_index": index,
                            "field": key,
                            "expected": expected_value,
                            "actual": actual_value,
                        }
                    )
        if mismatches:
            raise APICallFailed(
                f"Color Page {label} points DB mutation did not verify after project reload.",
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
            readback_key: actual,
            "points_verified": expected_points,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context=str(config["context"]),
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    result["db_session_route"] = result.get("route")
    result["route"] = str(config["route"])
    result[readback_key] = expected
    return result


def write_sat_vs_lum_curve(
    conn: Any,
    *,
    clip_name: str | None = None,
    input_sat: float,
    lum: float,
) -> dict[str, Any]:
    input_sat_value = float(input_sat)
    lum_value = float(lum)
    sat_curve_input_sat_to_internal(input_sat_value)
    sat_curve_lum_to_internal(lum_value)
    expected = {
        "input_sat": round(input_sat_value, 6),
        "lum": round(lum_value, 6),
    }

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
        ver = None
        if ver_table_id:
            ver = _select_active_grade_version(cursor, str(ver_table_id))

        if not ver or not ver["Body"]:
            raise APICallFailed(
                "Color Page Sat vs Lum route requires an existing grade version.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        base_proto = decompress_version_body(ver["Body"])
        new_proto = _inject_sat_vs_lum_curve_into_proto(
            base_proto,
            input_sat=input_sat_value,
            lum=lum_value,
        )
        cursor.execute(
            '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
               WHERE "ListMgt::LmVersion_id" = ?''',
            (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
        )
        session.steps.append("update_sat_vs_lum_curve")
        state = read_color_grade(cursor, clip_id=clip_id, clip_name=item_ref.name)
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "sat_vs_lum_written": expected,
            "readback": state.to_dict(),
        }

    def verifier(
        _fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Page Sat vs Lum DB mutation did not return a mutation payload for verification.",
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
                    "Could not resolve the written clip during Sat vs Lum DB verification.",
                    details={"clip": clip_label},
                )
            state = read_color_grade(cursor, clip_id=str(clip_id), clip_name=clip_label)
        finally:
            connection.close()

        actual = (state.curves.get("sat_vs_lum") or {}) if state.curves else {}
        mismatches: dict[str, Any] = {}
        for key, expected_value in expected.items():
            actual_value = actual.get(key)
            if actual_value is None or abs(float(actual_value) - expected_value) > 0.01:
                mismatches[key] = {"expected": expected_value, "actual": actual_value}
        if mismatches:
            raise APICallFailed(
                "Color Page Sat vs Lum DB mutation did not verify after project reload.",
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
            "sat_vs_lum": actual,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page sat vs lum db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    result["db_session_route"] = result.get("route")
    result["route"] = "db_workaround_color_page_sat_vs_lum"
    result["sat_vs_lum"] = expected
    return result


def write_lum_vs_sat_curve(
    conn: Any,
    *,
    clip_name: str | None = None,
    input_lum: float,
    saturation: float,
) -> dict[str, Any]:
    input_lum_value = float(input_lum)
    saturation_value = float(saturation)
    lum_curve_input_lum_to_internal(input_lum_value)
    sat_curve_output_sat_to_internal(saturation_value)
    expected = {
        "input_lum": round(input_lum_value, 6),
        "saturation": round(saturation_value, 6),
    }

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
        ver = None
        if ver_table_id:
            ver = _select_active_grade_version(cursor, str(ver_table_id))

        if not ver or not ver["Body"]:
            raise APICallFailed(
                "Color Page Lum vs Sat route requires an existing grade version.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        base_proto = decompress_version_body(ver["Body"])
        new_proto = _inject_lum_vs_sat_curve_into_proto(
            base_proto,
            input_lum=input_lum_value,
            saturation=saturation_value,
        )
        cursor.execute(
            '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
               WHERE "ListMgt::LmVersion_id" = ?''',
            (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
        )
        session.steps.append("update_lum_vs_sat_curve")
        state = read_color_grade(cursor, clip_id=clip_id, clip_name=item_ref.name)
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "lum_vs_sat_written": expected,
            "readback": state.to_dict(),
        }

    def verifier(
        _fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Page Lum vs Sat DB mutation did not return a mutation payload for verification.",
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
                    "Could not resolve the written clip during Lum vs Sat DB verification.",
                    details={"clip": clip_label},
                )
            state = read_color_grade(cursor, clip_id=str(clip_id), clip_name=clip_label)
        finally:
            connection.close()

        actual = (state.curves.get("lum_vs_sat") or {}) if state.curves else {}
        mismatches: dict[str, Any] = {}
        for key, expected_value in expected.items():
            actual_value = actual.get(key)
            if actual_value is None or abs(float(actual_value) - expected_value) > 0.01:
                mismatches[key] = {"expected": expected_value, "actual": actual_value}
        if mismatches:
            raise APICallFailed(
                "Color Page Lum vs Sat DB mutation did not verify after project reload.",
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
            "lum_vs_sat": actual,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page lum vs sat db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    result["db_session_route"] = result.get("route")
    result["route"] = "db_workaround_color_page_lum_vs_sat"
    result["lum_vs_sat"] = expected
    return result


__all__ = (
    'write_custom_curve_points',
    'write_split_tone_curves',
    'write_split_tone_curves_with_key_output',
    'write_hue_vs_hue_curve',
    'write_hue_curve_points',
    'write_hue_vs_hue_curve_points',
    'write_hue_vs_sat_curve',
    'write_hue_vs_lum_curve',
    'write_sat_vs_sat_curve',
    'write_sat_curve_points',
    'write_sat_vs_lum_curve',
    'write_lum_vs_sat_curve',
)
