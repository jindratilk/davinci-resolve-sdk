"""Mutations Power Windows helpers for Color Page DB operations."""

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
from .mutations_curves import *
from .mutations_cst import *


def _matches_requested_power_window_node(window: dict[str, Any], node_index: int | None) -> bool:
    return node_index is None or window.get("node_index") == int(node_index)


def write_circle_power_window(
    conn: Any,
    *,
    clip_name: str | None = None,
    node_index: int | None = None,
    size: float = 288.0,
    soft_1: float | None = None,
    pan: float | None = None,
    tilt: float | None = None,
    opacity: float | None = None,
    invert: bool | None = None,
) -> dict[str, Any]:
    """Create/update a native Color Page Circle Power Window via Project.db."""
    if size <= 0 or size > 4096:
        raise ValidationError(
            "Color Page circle power-window size must be between 0 and 4096.",
            details={"size": size},
            recoverability="not_applicable",
        )
    if pan is not None and (pan < 0 or pan > 100):
        raise ValidationError(
            "Color Page circle power-window pan must be between 0 and 100.",
            details={"pan": pan},
            recoverability="not_applicable",
        )
    if soft_1 is not None and (soft_1 < 0 or soft_1 > 100):
        raise ValidationError(
            "Color Page circle power-window Soft 1 must be between 0 and 100.",
            details={"soft_1": soft_1},
            recoverability="not_applicable",
        )
    if tilt is not None and (tilt < 0 or tilt > 100):
        raise ValidationError(
            "Color Page circle power-window tilt must be between 0 and 100.",
            details={"tilt": tilt},
            recoverability="not_applicable",
        )
    if opacity is not None and (opacity < 0 or opacity > 100):
        raise ValidationError(
            "Color Page circle power-window opacity must be between 0 and 100.",
            details={"opacity": opacity},
            recoverability="not_applicable",
        )
    target_node_index = None if node_index is None else int(node_index)
    if target_node_index is not None and target_node_index < 1:
        raise ValidationError(
            "Power Window target node index must be a positive integer.",
            details={"node_index": target_node_index, "minimum": 1},
            recoverability="not_applicable",
        )

    from ..db_timeline_selection import resolve_video_group

    item_ref = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None

    def _verified_window(state: ColorGradeState) -> dict[str, Any]:
        for window in state.power_windows:
            if window.get("shape") != "circle":
                continue
            if not _matches_requested_power_window_node(window, target_node_index):
                continue
            actual_size = window.get("size")
            if not isinstance(actual_size, (int, float)) or abs(float(actual_size) - size) > 0.001:
                continue
            if pan is not None:
                actual_pan = window.get("pan")
                if not isinstance(actual_pan, (int, float)) or abs(float(actual_pan) - pan) > 0.001:
                    continue
            if soft_1 is not None:
                actual_soft_1 = window.get("soft_1")
                if not isinstance(actual_soft_1, (int, float)) or abs(float(actual_soft_1) - soft_1) > 0.001:
                    continue
            if tilt is not None:
                actual_tilt = window.get("tilt")
                if not isinstance(actual_tilt, (int, float)) or abs(float(actual_tilt) - tilt) > 0.001:
                    continue
            if opacity is not None:
                actual_opacity = window.get("opacity")
                if not isinstance(actual_opacity, (int, float)) or abs(float(actual_opacity) - opacity) > 0.01:
                    continue
            if invert is not None and window.get("invert") is not invert:
                continue
            return window
        expected = {
            "node_index": target_node_index,
            "shape": "circle",
            "size": size,
            "soft_1": soft_1,
            "pan": pan,
            "tilt": tilt,
            "opacity": opacity,
        }
        if invert is not None:
            expected["invert"] = invert
        raise APICallFailed(
            "Color Page Power Window DB mutation did not verify after project reload.",
            details={
                "clip": item_ref.name,
                "expected": expected,
                "readback": state.to_dict(),
            },
            recoverability="manual",
        )

    def writer(connection: Any, cursor: sqlite3.Cursor, session: DiskDbMutationSession) -> dict[str, Any]:
        row = find_ti_item_row(
            cursor,
            item=item_ref,
            db_type="Sm2TiVideoClip",
            timeline_name=timeline_name,
        )
        clip_id = row["Sm2TiItem_id"]
        ver_table_id = row["pLmVerTable"]
        if not ver_table_id:
            raise APICallFailed(
                "Color Page Power Window DB route requires an existing Color Page grade/version table.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        ver = _select_active_grade_version(cursor, str(ver_table_id))
        if not ver or not ver["Body"]:
            raise APICallFailed(
                "Color Page Power Window DB route requires an existing Color Page grade body.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        base_proto = decompress_version_body(ver["Body"])
        new_proto, created, window_readback = _upsert_circle_power_window_proto(
            base_proto,
            node_index=target_node_index,
            size=size,
            soft_1=soft_1,
            pan=pan,
            tilt=tilt,
            opacity=opacity,
            invert=invert,
        )
        cursor.execute(
            '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
               WHERE "ListMgt::LmVersion_id" = ?''',
            (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
        )
        session.steps.append("upsert_circle_power_window")
        state = read_color_grade(cursor, clip_id=str(clip_id), clip_name=item_ref.name)
        return {
            "route": "db_workaround_color_page_power_window_circle",
            "clip": item_ref.name,
            "clip_id": clip_id,
            "version_id": ver["ListMgt::LmVersion_id"],
            "requested_node_index": target_node_index,
            "created_window": created,
            "window": window_readback,
            "readback": state.to_dict(),
        }

    def verifier(
        _fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Page Power Window DB mutation did not return a mutation payload for verification.",
                details={"mutation_result": mutation_result},
            )

        clip_id = str(mutation_result.get("clip_id") or "")
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
                    clip_id = str(row["Sm2TiItem_id"])
            if not clip_id:
                raise ValidationError(
                    "Could not resolve the written clip during Color Page Power Window DB verification.",
                    details={"clip": clip_label},
                )
            state = read_color_grade(cursor, clip_id=clip_id, clip_name=clip_label)
        finally:
            connection.close()

        window = _verified_window(state)
        verification = {
            "status": "verified",
            "clip": clip_label,
            "window_verified": window,
            "requested_node_index": target_node_index,
            "size": size,
            "soft_1": soft_1,
            "pan": pan,
            "tilt": tilt,
            "opacity": opacity,
        }
        if invert is not None:
            verification["invert"] = invert
        return verification

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page power-window circle db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    if isinstance(result, dict):
        result["db_session_route"] = result.get("route")
        result["route"] = "db_workaround_color_page_power_window_circle"
    return result


def write_gradient_power_window(
    conn: Any,
    *,
    clip_name: str | None = None,
    node_index: int | None = None,
    size: float | None = 200.0,
    pan: float | None = None,
    tilt: float | None = None,
) -> dict[str, Any]:
    """Create/update a native Color Page Gradient Power Window via Project.db."""
    from ..db_timeline_selection import resolve_video_group

    if size is not None:
        validate_gradient_power_window_size(size)
    target_node_index = None if node_index is None else int(node_index)
    if target_node_index is not None and target_node_index < 1:
        raise ValidationError(
            "Power Window target node index must be a positive integer.",
            details={"node_index": target_node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    item_ref = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None

    def _verified_window(state: ColorGradeState) -> dict[str, Any]:
        for window in state.power_windows:
            if window.get("shape") != "gradient":
                continue
            if not _matches_requested_power_window_node(window, target_node_index):
                continue
            actual_size = window.get("gradient_size")
            if size is not None:
                if not isinstance(actual_size, (int, float)) or abs(float(actual_size) - size) > 0.001:
                    continue
            if pan is not None and abs(float(window.get("pan") or 0.0) - pan) > 0.001:
                continue
            if tilt is not None and abs(float(window.get("tilt") or 0.0) - tilt) > 0.001:
                continue
            return window
        raise APICallFailed(
            "Color Page Gradient Power Window DB mutation did not verify after project reload.",
            details={
                "clip": item_ref.name,
                "expected": {
                    "node_index": target_node_index,
                    "shape": "gradient",
                    "gradient_size": size,
                    "pan": pan,
                    "tilt": tilt,
                },
                "readback": state.to_dict(),
            },
            recoverability="manual",
        )

    def writer(connection: Any, cursor: sqlite3.Cursor, session: DiskDbMutationSession) -> dict[str, Any]:
        row = find_ti_item_row(
            cursor,
            item=item_ref,
            db_type="Sm2TiVideoClip",
            timeline_name=timeline_name,
        )
        clip_id = row["Sm2TiItem_id"]
        ver_table_id = row["pLmVerTable"]
        if not ver_table_id:
            raise APICallFailed(
                "Color Page Gradient Power Window DB route requires an existing Color Page grade/version table.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        ver = _select_active_grade_version(cursor, str(ver_table_id))
        if not ver or not ver["Body"]:
            raise APICallFailed(
                "Color Page Gradient Power Window DB route requires an existing Color Page grade body.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        base_proto = decompress_version_body(ver["Body"])
        new_proto, created, window_readback = _upsert_gradient_power_window_proto(
            base_proto,
            node_index=target_node_index,
            size=size,
            pan=pan,
            tilt=tilt,
        )
        cursor.execute(
            '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
               WHERE "ListMgt::LmVersion_id" = ?''',
            (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
        )
        session.steps.append("upsert_gradient_power_window")
        state = read_color_grade(cursor, clip_id=str(clip_id), clip_name=item_ref.name)
        return {
            "route": "db_workaround_color_page_power_window_gradient",
            "clip": item_ref.name,
            "clip_id": clip_id,
            "version_id": ver["ListMgt::LmVersion_id"],
            "requested_node_index": target_node_index,
            "created_window": created,
            "window": window_readback,
            "readback": state.to_dict(),
        }

    def verifier(
        _fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Page Gradient Power Window DB mutation did not return a mutation payload for verification.",
                details={"mutation_result": mutation_result},
            )

        clip_id = str(mutation_result.get("clip_id") or "")
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
                    clip_id = str(row["Sm2TiItem_id"])
            if not clip_id:
                raise ValidationError(
                    "Could not resolve the written clip during Color Page Gradient Power Window DB verification.",
                    details={"clip": clip_label},
                )
            state = read_color_grade(cursor, clip_id=clip_id, clip_name=clip_label)
        finally:
            connection.close()

        window = _verified_window(state)
        return {
            "status": "verified",
            "clip": clip_label,
            "requested_node_index": target_node_index,
            "window_verified": window,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page power-window gradient db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    if isinstance(result, dict):
        result["db_session_route"] = result.get("route")
        result["route"] = "db_workaround_color_page_power_window_gradient"
    return result


def write_linear_power_window(
    conn: Any,
    *,
    clip_name: str | None = None,
    node_index: int | None = None,
    x: float | None = None,
    y: float | None = None,
    width: float | None = None,
    height: float | None = None,
    soft_1: float | None = None,
    soft_2: float | None = None,
    soft_3: float | None = None,
    soft_4: float | None = None,
    opacity: float | None = None,
) -> dict[str, Any]:
    """Create/update a native Color Page Linear Power Window via Project.db."""
    from ..db_timeline_selection import resolve_video_group

    _linear_power_window_updates(
        x=x,
        y=y,
        width=width,
        height=height,
        soft_1=soft_1,
        soft_2=soft_2,
        soft_3=soft_3,
        soft_4=soft_4,
        opacity=opacity,
    )
    target_node_index = None if node_index is None else int(node_index)
    if target_node_index is not None and target_node_index < 1:
        raise ValidationError(
            "Power Window target node index must be a positive integer.",
            details={"node_index": target_node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    item_ref = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None

    def _verified_window(state: ColorGradeState) -> dict[str, Any]:
        for window in state.power_windows:
            if window.get("shape") != "linear":
                continue
            if not _matches_requested_power_window_node(window, target_node_index):
                continue
            for field_name, expected in {
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "soft_1": soft_1,
                "soft_2": soft_2,
                "soft_3": soft_3,
                "soft_4": soft_4,
                "opacity": opacity,
            }.items():
                if expected is None:
                    continue
                actual = window.get(field_name)
                if not isinstance(actual, (int, float)) or abs(float(actual) - expected) > 0.001:
                    break
            else:
                return window
        raise APICallFailed(
            "Color Page Linear Power Window DB mutation did not verify after project reload.",
            details={
                "clip": item_ref.name,
                "expected": {
                    "node_index": target_node_index,
                    "shape": "linear",
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "soft_1": soft_1,
                    "soft_2": soft_2,
                    "soft_3": soft_3,
                    "soft_4": soft_4,
                    "opacity": opacity,
                },
                "readback": state.to_dict(),
            },
            recoverability="manual",
        )

    def writer(connection: Any, cursor: sqlite3.Cursor, session: DiskDbMutationSession) -> dict[str, Any]:
        row = find_ti_item_row(
            cursor,
            item=item_ref,
            db_type="Sm2TiVideoClip",
            timeline_name=timeline_name,
        )
        clip_id = row["Sm2TiItem_id"]
        ver_table_id = row["pLmVerTable"]
        if not ver_table_id:
            raise APICallFailed(
                "Color Page Linear Power Window DB route requires an existing Color Page grade/version table.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        ver = _select_active_grade_version(cursor, str(ver_table_id))
        if not ver or not ver["Body"]:
            raise APICallFailed(
                "Color Page Linear Power Window DB route requires an existing Color Page grade body.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        base_proto = decompress_version_body(ver["Body"])
        new_proto, created, window_readback = _upsert_linear_power_window_proto(
            base_proto,
            node_index=target_node_index,
            x=x,
            y=y,
            width=width,
            height=height,
            soft_1=soft_1,
            soft_2=soft_2,
            soft_3=soft_3,
            soft_4=soft_4,
            opacity=opacity,
        )
        cursor.execute(
            '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
               WHERE "ListMgt::LmVersion_id" = ?''',
            (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
        )
        session.steps.append("upsert_linear_power_window")
        state = read_color_grade(cursor, clip_id=str(clip_id), clip_name=item_ref.name)
        return {
            "route": "db_workaround_color_page_power_window_linear",
            "clip": item_ref.name,
            "clip_id": clip_id,
            "version_id": ver["ListMgt::LmVersion_id"],
            "requested_node_index": target_node_index,
            "created_window": created,
            "window": window_readback,
            "readback": state.to_dict(),
        }

    def verifier(
        _fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Page Linear Power Window DB mutation did not return a mutation payload for verification.",
                details={"mutation_result": mutation_result},
            )

        clip_id = str(mutation_result.get("clip_id") or "")
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
                    clip_id = str(row["Sm2TiItem_id"])
            if not clip_id:
                raise ValidationError(
                    "Could not resolve the written clip during Color Page Linear Power Window DB verification.",
                    details={"clip": clip_label},
                )
            state = read_color_grade(cursor, clip_id=clip_id, clip_name=clip_label)
        finally:
            connection.close()

        window = _verified_window(state)
        return {
            "status": "verified",
            "clip": clip_label,
            "requested_node_index": target_node_index,
            "window_verified": window,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page power-window linear db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    if isinstance(result, dict):
        result["db_session_route"] = result.get("route")
        result["route"] = "db_workaround_color_page_power_window_linear"
    return result


def write_polygon_power_window(
    conn: Any,
    *,
    clip_name: str | None = None,
    node_index: int | None = None,
    points: list[CurvePoint] | None = None,
) -> dict[str, Any]:
    """Create/update a native Color Page Polygon Power Window via Project.db."""
    from ..db_timeline_selection import resolve_video_group

    requested_points = list(points or DEFAULT_POWER_WINDOW_POLYGON_POINTS)
    if len(requested_points) < 3:
        raise ValidationError(
            "Polygon Power Window requires at least three normalized points.",
            details={"point_count": len(requested_points)},
            recoverability="not_applicable",
        )
    for point in requested_points:
        if not math.isfinite(point.x) or not math.isfinite(point.y) or point.x < 0.0 or point.x > 1.0 or point.y < 0.0 or point.y > 1.0:
            raise ValidationError(
                "Polygon Power Window points must be normalized between 0 and 1.",
                details={"point": point.to_dict()},
                recoverability="not_applicable",
            )

    target_node_index = None if node_index is None else int(node_index)
    if target_node_index is not None and target_node_index < 1:
        raise ValidationError(
            "Power Window target node index must be a positive integer.",
            details={"node_index": target_node_index, "minimum": 1},
            recoverability="not_applicable",
        )

    item_ref = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None
    width, height = _timeline_resolution(conn)
    expected_internal = _power_window_internal_points(requested_points, width=width, height=height)
    expected_readback = _power_window_points_for_readback(expected_internal)

    def _verified_window(state: ColorGradeState) -> dict[str, Any]:
        for window in state.power_windows:
            if not _matches_requested_power_window_node(window, target_node_index):
                continue
            if window.get("shape") == "polygon" and _power_window_points_match(window.get("points_internal"), expected_readback):
                return window
        raise APICallFailed(
            "Color Page Polygon Power Window DB mutation did not verify after project reload.",
            details={
                "clip": item_ref.name,
                "expected": {
                    "node_index": target_node_index,
                    "shape": "polygon",
                    "points_internal": expected_readback,
                },
                "readback": state.to_dict(),
            },
            recoverability="manual",
        )

    def writer(connection: Any, cursor: sqlite3.Cursor, session: DiskDbMutationSession) -> dict[str, Any]:
        row = find_ti_item_row(
            cursor,
            item=item_ref,
            db_type="Sm2TiVideoClip",
            timeline_name=timeline_name,
        )
        clip_id = row["Sm2TiItem_id"]
        ver_table_id = row["pLmVerTable"]
        if not ver_table_id:
            raise APICallFailed(
                "Color Page Polygon Power Window DB route requires an existing Color Page grade/version table.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        ver = _select_active_grade_version(cursor, str(ver_table_id))
        if not ver or not ver["Body"]:
            raise APICallFailed(
                "Color Page Polygon Power Window DB route requires an existing Color Page grade body.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        base_proto = decompress_version_body(ver["Body"])
        new_proto, created, window_readback = _upsert_polygon_power_window_proto(
            base_proto,
            node_index=target_node_index,
            points=requested_points,
            width=width,
            height=height,
        )
        cursor.execute(
            '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
               WHERE "ListMgt::LmVersion_id" = ?''',
            (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
        )
        session.steps.append("upsert_polygon_power_window")
        state = read_color_grade(cursor, clip_id=str(clip_id), clip_name=item_ref.name)
        return {
            "route": "db_workaround_color_page_power_window_polygon",
            "clip": item_ref.name,
            "clip_id": clip_id,
            "version_id": ver["ListMgt::LmVersion_id"],
            "requested_node_index": target_node_index,
            "created_window": created,
            "timeline_resolution": {"width": width, "height": height},
            "points": [point.to_dict() for point in requested_points],
            "points_internal": expected_readback,
            "window": window_readback,
            "readback": state.to_dict(),
        }

    def verifier(
        _fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Page Polygon Power Window DB mutation did not return a mutation payload for verification.",
                details={"mutation_result": mutation_result},
            )

        clip_id = str(mutation_result.get("clip_id") or "")
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
                    clip_id = str(row["Sm2TiItem_id"])
            if not clip_id:
                raise ValidationError(
                    "Could not resolve the written clip during Color Page Polygon Power Window DB verification.",
                    details={"clip": clip_label},
                )
            state = read_color_grade(cursor, clip_id=clip_id, clip_name=clip_label)
        finally:
            connection.close()

        window = _verified_window(state)
        return {
            "status": "verified",
            "clip": clip_label,
            "requested_node_index": target_node_index,
            "window_verified": window,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page power-window polygon db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    if isinstance(result, dict):
        result["db_session_route"] = result.get("route")
        result["route"] = "db_workaround_color_page_power_window_polygon"
    return result


def write_curve_power_window(
    conn: Any,
    *,
    clip_name: str | None = None,
    node_index: int | None = None,
    points: list[CurvePoint] | None = None,
) -> dict[str, Any]:
    """Create/update a native Color Page Curve Power Window via Project.db."""
    from ..db_timeline_selection import resolve_video_group

    requested_points = list(points or DEFAULT_POWER_WINDOW_CURVE_POINTS)
    if len(requested_points) < 3:
        raise ValidationError(
            "Curve Power Window requires at least three normalized points.",
            details={"point_count": len(requested_points)},
            recoverability="not_applicable",
        )
    for point in requested_points:
        if not math.isfinite(point.x) or not math.isfinite(point.y) or point.x < 0.0 or point.x > 1.0 or point.y < 0.0 or point.y > 1.0:
            raise ValidationError(
                "Curve Power Window points must be normalized between 0 and 1.",
                details={"point": point.to_dict()},
                recoverability="not_applicable",
            )

    target_node_index = None if node_index is None else int(node_index)
    if target_node_index is not None and target_node_index < 1:
        raise ValidationError(
            "Power Window target node index must be a positive integer.",
            details={"node_index": target_node_index, "minimum": 1},
            recoverability="not_applicable",
        )

    item_ref = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None
    width, height = _timeline_resolution(conn)
    expected_internal = _power_window_curve_internal_points(requested_points, width=width, height=height)

    def _verified_window(state: ColorGradeState) -> dict[str, Any]:
        for window in state.power_windows:
            if not _matches_requested_power_window_node(window, target_node_index):
                continue
            if window.get("shape") == "curve":
                return window
        raise APICallFailed(
            "Color Page Curve Power Window DB mutation did not verify after project reload.",
            details={
                "clip": item_ref.name,
                "expected": {"node_index": target_node_index, "shape": "curve"},
                "readback": state.to_dict(),
            },
            recoverability="manual",
        )

    def writer(connection: Any, cursor: sqlite3.Cursor, session: DiskDbMutationSession) -> dict[str, Any]:
        row = find_ti_item_row(
            cursor,
            item=item_ref,
            db_type="Sm2TiVideoClip",
            timeline_name=timeline_name,
        )
        clip_id = row["Sm2TiItem_id"]
        ver_table_id = row["pLmVerTable"]
        if not ver_table_id:
            raise APICallFailed(
                "Color Page Curve Power Window DB route requires an existing Color Page grade/version table.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        ver = _select_active_grade_version(cursor, str(ver_table_id))
        if not ver or not ver["Body"]:
            raise APICallFailed(
                "Color Page Curve Power Window DB route requires an existing Color Page grade body.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        base_proto = decompress_version_body(ver["Body"])
        new_proto, created, window_readback = _upsert_curve_power_window_proto(
            base_proto,
            node_index=target_node_index,
            points=requested_points,
            width=width,
            height=height,
        )
        cursor.execute(
            '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
               WHERE "ListMgt::LmVersion_id" = ?''',
            (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
        )
        session.steps.append("upsert_curve_power_window")
        state = read_color_grade(cursor, clip_id=str(clip_id), clip_name=item_ref.name)
        return {
            "route": "db_workaround_color_page_power_window_curve",
            "clip": item_ref.name,
            "clip_id": clip_id,
            "version_id": ver["ListMgt::LmVersion_id"],
            "requested_node_index": target_node_index,
            "created_window": created,
            "timeline_resolution": {"width": width, "height": height},
            "points": [point.to_dict() for point in requested_points],
            "points_internal": [
                {"x": round(point[0], 6), "y": round(point[1], 6)}
                for point in expected_internal
            ],
            "window": window_readback,
            "readback": state.to_dict(),
        }

    def verifier(
        _fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Page Curve Power Window DB mutation did not return a mutation payload for verification.",
                details={"mutation_result": mutation_result},
            )

        clip_id = str(mutation_result.get("clip_id") or "")
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
                    clip_id = str(row["Sm2TiItem_id"])
            if not clip_id:
                raise ValidationError(
                    "Could not resolve the written clip during Color Page Curve Power Window DB verification.",
                    details={"clip": clip_label},
                )
            state = read_color_grade(cursor, clip_id=clip_id, clip_name=clip_label)
        finally:
            connection.close()

        window = _verified_window(state)
        return {
            "status": "verified",
            "clip": clip_label,
            "requested_node_index": target_node_index,
            "window_verified": window,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page power-window curve db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    if isinstance(result, dict):
        result["db_session_route"] = result.get("route")
        result["route"] = "db_workaround_color_page_power_window_curve"
    return result


__all__ = (
    'write_circle_power_window',
    'write_gradient_power_window',
    'write_linear_power_window',
    'write_polygon_power_window',
    'write_curve_power_window',
)
