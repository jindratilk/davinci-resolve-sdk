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


def validate_page_node_add_kind(kind: str) -> str:
    normalized = str(kind or "").strip().lower().replace("_", "-")
    if normalized not in {"serial", "parallel", "layer"}:
        raise ValidationError(
            "Only serial, parallel, and layer Color Page node-add are currently verified.",
            details={"kind": kind, "allowed": ["serial", "parallel", "layer"]},
            recoverability="not_applicable",
        )
    return normalized


def write_page_node_add_serial(
    conn: Any,
    *,
    clip_name: str | None = None,
    position: str = "after",
    target_node_index: int | None = None,
) -> dict[str, Any]:
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

        created_version = False
        created_version_table = False
        if ver and ver["Body"]:
            base_proto = decompress_version_body(ver["Body"])
            version_id = str(ver["ListMgt::LmVersion_id"])
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
            base_proto = decompress_version_body(base_body or bytes.fromhex(_BASELINE_VERSION_BODY_HEX))
            base_proto = _build_graded_proto_from_baseline(base_proto, {})
            if not ver_table_id:
                ver_table_id = _create_lm_version_table_for_item(
                    cursor,
                    item_id=str(clip_id),
                    fields_blob=bytes.fromhex(_VERSION_TABLE_FIELDS_BLOB_HEX),
                )
                created_version_table = True
            version_id = str(uuid.uuid4())
            created_version = True

        new_proto, node_result = _inject_serial_color_node_into_proto(
            base_proto,
            position=position,
            target_node_index=target_node_index,
        )
        new_body = compress_version_body(new_proto)
        if created_version:
            _insert_lm_version_from_body(
                cursor,
                body=new_body,
                version_id=version_id,
                version_table_id=str(ver_table_id),
            )
            session.steps.append("create_grade_version_for_serial_node")
        else:
            cursor.execute(
                '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
                   WHERE "ListMgt::LmVersion_id" = ?''',
                (new_body, version_id),
            )
            session.steps.append("add_serial_color_page_node")
        if created_version_table:
            session.steps.append("create_grade_version_table")

        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "version_table_id": str(ver_table_id),
            "version_id": version_id,
            "created_version": created_version,
            "created_version_table": created_version_table,
            "kind": "serial",
            "route": "db_workaround_color_page_node_add_serial",
            **node_result,
        }

    def verifier(
        fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Page node-add DB mutation did not return a mutation payload for verification.",
                details={"mutation_result": mutation_result},
            )
        expected_count = int(mutation_result["after_node_count"])
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
                    "Could not resolve the written clip during Color Page node-add verification.",
                    details={"clip": clip_label},
                )
            version_row = _select_active_grade_version_for_clip(cursor, str(clip_id))
            if not version_row or not version_row["Body"]:
                raise APICallFailed(
                    "Color Page node-add DB verification could not read the active grade version.",
                    details={"clip": clip_label, "clip_id": clip_id},
                )
            db_containers = _root_color_node_containers(decompress_version_body(version_row["Body"]))
            db_node_count = len(db_containers)
        finally:
            connection.close()

        api_node_count = None
        if fresh_conn is not None:
            try:
                from .. import color_ops

                api_node_count = int(color_ops.get_num_nodes(fresh_conn, clip_label or None))
            except Exception:
                api_node_count = None
        if db_node_count != expected_count:
            raise APICallFailed(
                "Color Page node-add DB mutation did not verify by DB readback.",
                details={
                    "clip": clip_label,
                    "expected_node_count": expected_count,
                    "db_node_count": db_node_count,
                    "project_db_path": session.project_db_path,
                },
                recoverability="manual",
            )
        if api_node_count is not None and api_node_count != expected_count:
            raise APICallFailed(
                "Color Page node-add DB mutation did not verify through DaVinci Resolve node graph readback.",
                details={
                    "clip": clip_label,
                    "expected_node_count": expected_count,
                    "api_node_count": api_node_count,
                    "db_node_count": db_node_count,
                },
                recoverability="manual",
            )
        expected_preserved_hashes = mutation_result.get("preserved_existing_node_hashes")
        preserved_existing_verified = None
        if isinstance(expected_preserved_hashes, list):
            preserved_count = len(expected_preserved_hashes)
            actual_preserved_hashes = [
                hashlib.sha256(container).hexdigest()
                for container in db_containers[:preserved_count]
            ]
            preserved_existing_verified = actual_preserved_hashes == expected_preserved_hashes
            if not preserved_existing_verified:
                raise APICallFailed(
                    "Color Page node-add DB mutation did not preserve existing node containers.",
                    details={
                        "clip": clip_label,
                        "expected_hashes": expected_preserved_hashes,
                        "actual_hashes": actual_preserved_hashes,
                        "preserved_node_count": preserved_count,
                    },
                    recoverability="manual",
                )
        return {
            "status": "verified",
            "clip": clip_label,
            "kind": "serial",
            "node_index": int(mutation_result["node_index"]),
            "node_count": expected_count,
            "db_node_count": db_node_count,
            "api_node_count": api_node_count,
            "preserved_existing_node_count": mutation_result.get("preserved_existing_node_count"),
            "preserved_existing_containers_verified": preserved_existing_verified,
            "preserved_mixer_node_indices": mutation_result.get("preserved_mixer_node_indices") or [],
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page node-add serial db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    if isinstance(result, dict):
        result["db_session_route"] = result.get("route")
        result["route"] = "db_workaround_color_page_node_add_serial"
        verification = result.get("verification")
        if isinstance(verification, dict):
            result["node_count"] = verification.get("node_count", result.get("after_node_count"))
            result["node_index"] = verification.get("node_index", result.get("node_index"))
    return result


def write_page_node_add_parallel(
    conn: Any,
    *,
    clip_name: str | None = None,
) -> dict[str, Any]:
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
                "Color Page parallel node-add route requires an existing grade version.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        base_proto = decompress_version_body(ver["Body"])
        new_proto, node_result = _inject_parallel_color_node_into_proto(base_proto)
        cursor.execute(
            '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
               WHERE "ListMgt::LmVersion_id" = ?''',
            (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
        )
        session.steps.append("add_parallel_color_page_node")
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "kind": "parallel",
            "route": "db_workaround_color_page_node_add_parallel",
            **node_result,
        }

    def verifier(
        fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Page parallel node-add DB mutation did not return a mutation payload for verification.",
                details={"mutation_result": mutation_result},
            )
        expected_count = int(mutation_result["after_node_count"])
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
                    "Could not resolve the written clip during Color Page parallel node-add verification.",
                    details={"clip": clip_label},
                )
            version_row = _select_active_grade_version_for_clip(cursor, str(clip_id))
            if not version_row or not version_row["Body"]:
                raise APICallFailed(
                    "Color Page parallel node-add DB verification could not read the active grade version.",
                    details={"clip": clip_label, "clip_id": clip_id},
                )
            db_node_count = len(_root_color_node_containers(decompress_version_body(version_row["Body"])))
        finally:
            connection.close()

        api_node_count = None
        if fresh_conn is not None:
            try:
                from .. import color_ops

                api_node_count = int(color_ops.get_num_nodes(fresh_conn, clip_label or None))
            except Exception:
                api_node_count = None
        if db_node_count != expected_count:
            raise APICallFailed(
                "Color Page parallel node-add DB mutation did not verify by DB readback.",
                details={
                    "clip": clip_label,
                    "expected_node_count": expected_count,
                    "db_node_count": db_node_count,
                    "project_db_path": session.project_db_path,
                },
                recoverability="manual",
            )
        if api_node_count is not None and api_node_count != expected_count:
            raise APICallFailed(
                "Color Page parallel node-add DB mutation did not verify through DaVinci Resolve node graph readback.",
                details={
                    "clip": clip_label,
                    "expected_node_count": expected_count,
                    "api_node_count": api_node_count,
                    "db_node_count": db_node_count,
                },
                recoverability="manual",
            )
        return {
            "status": "verified",
            "clip": clip_label,
            "kind": "parallel",
            "node_index": int(mutation_result["node_index"]),
            "mixer_node_index": int(mutation_result["mixer_node_index"]),
            "node_count": expected_count,
            "db_node_count": db_node_count,
            "api_node_count": api_node_count,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page node-add parallel db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    if isinstance(result, dict):
        result["db_session_route"] = result.get("route")
        result["route"] = "db_workaround_color_page_node_add_parallel"
        verification = result.get("verification")
        if isinstance(verification, dict):
            result["node_count"] = verification.get("node_count", result.get("after_node_count"))
            result["node_index"] = verification.get("node_index", result.get("node_index"))
            result["mixer_node_index"] = verification.get("mixer_node_index", result.get("mixer_node_index"))
    return result


def write_page_node_add_layer(
    conn: Any,
    *,
    clip_name: str | None = None,
) -> dict[str, Any]:
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
                "Color Page layer node-add route requires an existing grade version.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        base_proto = decompress_version_body(ver["Body"])
        new_proto, node_result = _inject_layer_color_node_into_proto(base_proto)
        cursor.execute(
            '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
               WHERE "ListMgt::LmVersion_id" = ?''',
            (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
        )
        session.steps.append("add_layer_color_page_node")
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "kind": "layer",
            "route": "db_workaround_color_page_node_add_layer",
            **node_result,
        }

    def verifier(
        fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Page layer node-add DB mutation did not return a mutation payload for verification.",
                details={"mutation_result": mutation_result},
            )
        expected_count = int(mutation_result["after_node_count"])
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
                    "Could not resolve the written clip during Color Page layer node-add verification.",
                    details={"clip": clip_label},
                )
            version_row = _select_active_grade_version_for_clip(cursor, str(clip_id))
            if not version_row or not version_row["Body"]:
                raise APICallFailed(
                    "Color Page layer node-add DB verification could not read the active grade version.",
                    details={"clip": clip_label, "clip_id": clip_id},
                )
            db_node_count = len(_root_color_node_containers(decompress_version_body(version_row["Body"])))
        finally:
            connection.close()

        api_node_count = None
        if fresh_conn is not None:
            try:
                from .. import color_ops

                api_node_count = int(color_ops.get_num_nodes(fresh_conn, clip_label or None))
            except Exception:
                api_node_count = None
        if db_node_count != expected_count:
            raise APICallFailed(
                "Color Page layer node-add DB mutation did not verify by DB readback.",
                details={
                    "clip": clip_label,
                    "expected_node_count": expected_count,
                    "db_node_count": db_node_count,
                    "project_db_path": session.project_db_path,
                },
                recoverability="manual",
            )
        if api_node_count is not None and api_node_count != expected_count:
            raise APICallFailed(
                "Color Page layer node-add DB mutation did not verify through DaVinci Resolve node graph readback.",
                details={
                    "clip": clip_label,
                    "expected_node_count": expected_count,
                    "api_node_count": api_node_count,
                    "db_node_count": db_node_count,
                },
                recoverability="manual",
            )
        return {
            "status": "verified",
            "clip": clip_label,
            "kind": "layer",
            "node_index": int(mutation_result["node_index"]),
            "mixer_node_index": int(mutation_result["mixer_node_index"]),
            "node_count": expected_count,
            "db_node_count": db_node_count,
            "api_node_count": api_node_count,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page node-add layer db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    if isinstance(result, dict):
        result["db_session_route"] = result.get("route")
        result["route"] = "db_workaround_color_page_node_add_layer"
        verification = result.get("verification")
        if isinstance(verification, dict):
            result["node_count"] = verification.get("node_count", result.get("after_node_count"))
            result["node_index"] = verification.get("node_index", result.get("node_index"))
            result["mixer_node_index"] = verification.get("mixer_node_index", result.get("mixer_node_index"))
    return result


def write_layer_mixer_composite_mode(
    conn: Any,
    *,
    clip_name: str | None = None,
    layer_node_index: int = 2,
    mode: str = "Overlay",
    opacity: float | None = None,
) -> dict[str, Any]:
    from ..db_timeline_selection import resolve_video_group

    mode_label, mode_value = validate_layer_mixer_composite_mode(mode)
    if layer_node_index < 1:
        raise ValidationError(
            "Layer node index must be a positive integer.",
            details={"layer_node_index": layer_node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    opacity_value = None if opacity is None else float(opacity)
    if opacity_value is not None and (
        not math.isfinite(opacity_value) or opacity_value < 0.0 or opacity_value > 100.0
    ):
        raise ValidationError(
            "Layer Mixer branch opacity must be between 0 and 100.",
            details={"opacity": opacity, "minimum": 0.0, "maximum": 100.0},
            recoverability="not_applicable",
        )

    item_ref = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None

    def _read_state_from_cursor(cursor: sqlite3.Cursor, clip_id: str) -> tuple[int | None, int, float | None]:
        version_row = _select_active_grade_version_for_clip(cursor, str(clip_id))
        if not version_row or not version_row["Body"]:
            raise APICallFailed(
                "Color Page Layer Mixer DB verification could not read the active grade version.",
                details={"clip_id": clip_id},
            )
        proto = decompress_version_body(version_row["Body"])
        root = _get_submessage(proto, 1)
        if root is None:
            raise APICallFailed(
                "Color Page Layer Mixer DB verification could not read the active grade root.",
                details={"clip_id": clip_id},
            )
        containers = _root_color_node_containers(proto)
        layer_graph_id = None
        for container in containers:
            if _get_first_varint_field(container, 2) == layer_node_index:
                layer_graph_id = _get_first_varint_field(container, 1)
                break
        if layer_graph_id is None:
            raise ValidationError(
                "Color Page Layer Mixer DB verification could not find the requested layer node.",
                details={"clip_id": clip_id, "layer_node_index": layer_node_index},
                recoverability="not_applicable",
            )
        return (
            _read_layer_mixer_composite_mode_from_root(root, layer_graph_id),
            len(containers),
            _layer_mixer_branch_opacity_from_root(root, layer_graph_id),
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
        ver = None
        if ver_table_id:
            ver = _select_active_grade_version(cursor, str(ver_table_id))

        if not ver or not ver["Body"]:
            raise APICallFailed(
                "Color Page Layer Mixer route requires an existing grade version.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        base_proto = decompress_version_body(ver["Body"])
        new_proto, mutation = _set_layer_mixer_composite_mode_in_proto(
            base_proto,
            layer_node_index=layer_node_index,
            mode_value=mode_value,
            branch_opacity=opacity_value,
        )
        cursor.execute(
            '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
               WHERE "ListMgt::LmVersion_id" = ?''',
            (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
        )
        session.steps.append("set_layer_mixer_composite_mode")
        if opacity_value is not None:
            session.steps.append("set_layer_mixer_branch_opacity")
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "mode": mode_label,
            "mode_value": mode_value,
            "route": "db_workaround_color_page_layer_mixer_composite",
            "opacity": opacity_value,
            **mutation,
        }

    def verifier(
        fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Page Layer Mixer DB mutation did not return a mutation payload for verification.",
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
                    "Could not resolve the written clip during Color Page Layer Mixer verification.",
                    details={"clip": clip_label},
                )
            readback_mode, db_node_count, readback_opacity = _read_state_from_cursor(cursor, str(clip_id))
        finally:
            connection.close()

        if readback_mode != mode_value:
            raise APICallFailed(
                "Color Page Layer Mixer DB mutation did not verify by DB readback.",
                details={
                    "clip": clip_label,
                    "expected_mode": mode_label,
                    "expected_mode_value": mode_value,
                    "readback_mode_value": readback_mode,
                    "project_db_path": session.project_db_path,
                },
                recoverability="manual",
            )
        if opacity_value is not None and (
            readback_opacity is None or abs(float(readback_opacity) - opacity_value) > 0.01
        ):
            raise APICallFailed(
                "Color Page Layer Mixer branch opacity did not verify by DB readback.",
                details={
                    "clip": clip_label,
                    "expected_opacity": opacity_value,
                    "readback_opacity": readback_opacity,
                    "project_db_path": session.project_db_path,
                },
                recoverability="manual",
            )

        api_node_count = None
        if fresh_conn is not None:
            try:
                from .. import color_ops

                api_node_count = int(color_ops.get_num_nodes(fresh_conn, clip_label or None))
            except Exception:
                api_node_count = None
        if api_node_count is not None and api_node_count != db_node_count:
            raise APICallFailed(
                "Color Page Layer Mixer DB mutation did not verify through DaVinci Resolve node graph readback.",
                details={
                    "clip": clip_label,
                    "api_node_count": api_node_count,
                    "db_node_count": db_node_count,
                },
                recoverability="manual",
            )

        return {
            "status": "verified",
            "clip": clip_label,
            "layer_node_index": layer_node_index,
            "mode": mode_label,
            "mode_value": mode_value,
            "readback_mode_value": readback_mode,
            "opacity": opacity_value,
            "readback_opacity": readback_opacity,
            "db_node_count": db_node_count,
            "api_node_count": api_node_count,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page layer mixer composite db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    if isinstance(result, dict):
        result["db_session_route"] = result.get("route")
        result["route"] = "db_workaround_color_page_layer_mixer_composite"
        verification = result.get("verification")
        if isinstance(verification, dict):
            result["readback"] = {
                "mode": verification.get("mode"),
                "mode_value": verification.get("readback_mode_value"),
            }
            if verification.get("readback_opacity") is not None:
                result["readback"]["opacity"] = verification.get("readback_opacity")
    return result


def write_bleach_bypass(
    conn: Any,
    *,
    clip_name: str | None = None,
) -> dict[str, Any]:
    """Create or normalize the DB-readback bleach-bypass candidate topology.

    This helper is retained for Project.db forensics only. The public CLI keeps
    bleach bypass partial until the real GUI Layer Mixer Overlay payload has
    live DaVinci Resolve render proof.
    """
    from ..db_timeline_selection import resolve_video_group

    item_ref = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None

    def _read_state_from_cursor(cursor: sqlite3.Cursor, clip_id: str) -> dict[str, Any]:
        version_row = _select_active_grade_version_for_clip(cursor, str(clip_id))
        if not version_row or not version_row["Body"]:
            raise APICallFailed(
                "Color Page bleach bypass DB verification could not read the active grade version.",
                details={"clip_id": clip_id},
            )
        return _read_bleach_bypass_state_from_proto(decompress_version_body(version_row["Body"]))

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
                "Color Page bleach bypass route requires an existing grade version.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        base_proto = decompress_version_body(ver["Body"])
        new_proto, mutation = _set_bleach_bypass_in_proto(base_proto)
        cursor.execute(
            '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
               WHERE "ListMgt::LmVersion_id" = ?''',
            (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
        )
        session.steps.append("set_bleach_bypass_topology")
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "route": "db_workaround_color_page_bleach_bypass",
            **mutation,
        }

    def verifier(
        fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Page bleach bypass DB mutation did not return a mutation payload for verification.",
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
                    "Could not resolve the written clip during Color Page bleach bypass verification.",
                    details={"clip": clip_label},
                )
            state = _read_state_from_cursor(cursor, str(clip_id))
        finally:
            connection.close()

        expected = {
            "node_count": 3,
            "topology": "layer_mixer",
            "rgb_mixer_mode_value": 4,
            "layer_mixer_mode_value": LAYER_MIXER_COMPOSITE_MODES["overlay"],
            "render_graph_verified": True,
        }
        mismatches = {
            key: {"expected": value, "actual": state.get(key)}
            for key, value in expected.items()
            if state.get(key) != value
        }
        if mismatches:
            raise APICallFailed(
                "Color Page bleach bypass DB mutation did not verify by DB readback.",
                details={
                    "clip": clip_label,
                    "mismatches": mismatches,
                    "readback": state,
                    "project_db_path": session.project_db_path,
                },
                recoverability="manual",
            )

        api_node_count = None
        if fresh_conn is not None:
            try:
                from .. import color_ops

                api_node_count = int(color_ops.get_num_nodes(fresh_conn, clip_label or None))
            except Exception:
                api_node_count = None
        if api_node_count is not None and api_node_count != 3:
            raise APICallFailed(
                "Color Page bleach bypass DB mutation did not verify through DaVinci Resolve node graph readback.",
                details={
                    "clip": clip_label,
                    "expected_node_count": 3,
                    "api_node_count": api_node_count,
                    "readback": state,
                },
                recoverability="manual",
            )
        return {
            "status": "verified",
            "clip": clip_label,
            "db_node_count": state["node_count"],
            "api_node_count": api_node_count,
            "readback": state,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page bleach bypass db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    if isinstance(result, dict):
        result["db_session_route"] = result.get("route")
        result["route"] = "db_workaround_color_page_bleach_bypass"
        verification = result.get("verification")
        if isinstance(verification, dict):
            result["readback"] = verification.get("readback", result.get("topology_after"))
            result["node_count"] = verification.get("db_node_count")
    return result


def write_bleach_bypass_intensity(
    conn: Any,
    *,
    clip_name: str | None = None,
    gain: float,
    connection_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Apply bleach bypass topology and set its verified Key Output intensity."""
    gain_value = float(gain)
    validate_key_output_gain(gain_value)

    topology_result = write_bleach_bypass(conn, clip_name=clip_name)
    key_conn = connection_factory() if connection_factory is not None else conn
    key_output_result = write_key_output(key_conn, clip_name=clip_name, gain=gain_value)
    topology_verification = topology_result.get("verification") if isinstance(topology_result, dict) else None
    key_verification = key_output_result.get("verification") if isinstance(key_output_result, dict) else None
    clip_label = None
    if isinstance(key_output_result, dict):
        clip_label = key_output_result.get("clip")
    if clip_label is None and isinstance(topology_result, dict):
        clip_label = topology_result.get("clip")
    return {
        "clip": clip_label,
        "route": "db_workaround_color_page_bleach_bypass_intensity",
        "db_session_route": {
            "topology": topology_result.get("db_session_route") if isinstance(topology_result, dict) else None,
            "key_output": key_output_result.get("db_session_route") if isinstance(key_output_result, dict) else None,
        },
        "gain": gain_value,
        "topology": topology_result,
        "key_output": key_output_result,
        "verification": {
            "status": (
                "verified"
                if isinstance(topology_verification, dict)
                and topology_verification.get("status") == "verified"
                and isinstance(key_verification, dict)
                and key_verification.get("status") == "verified"
                else "pending_manual"
            ),
            "topology": topology_verification,
            "key_output": key_verification,
        },
        "readback": {
            "topology": topology_result.get("readback") if isinstance(topology_result, dict) else None,
            "key_output": key_output_result.get("key_output") if isinstance(key_output_result, dict) else None,
        },
    }


def write_page_node_cleanup_empty_serial(
    conn: Any,
    *,
    clip_name: str | None = None,
) -> dict[str, Any]:
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
                "Color Page node-cleanup route requires an existing grade version.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        base_proto = decompress_version_body(ver["Body"])
        new_proto, cleanup_result = _remove_empty_serial_color_nodes_from_proto(base_proto)
        changed = cleanup_result["removed_node_count"] > 0
        if changed:
            cursor.execute(
                '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
                   WHERE "ListMgt::LmVersion_id" = ?''',
                (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
            )
            session.steps.append("cleanup_empty_serial_color_page_nodes")
        else:
            session.steps.append("cleanup_empty_serial_color_page_nodes_noop")
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "route": "db_workaround_color_page_node_cleanup_empty_serial",
            "changed": changed,
            **cleanup_result,
        }

    def verifier(
        fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Page node-cleanup DB mutation did not return a mutation payload for verification.",
                details={"mutation_result": mutation_result},
            )
        expected_count = int(mutation_result["after_node_count"])
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
                    "Could not resolve the written clip during Color Page node-cleanup verification.",
                    details={"clip": clip_label},
                )
            version_row = _select_active_grade_version_for_clip(cursor, str(clip_id))
            if not version_row or not version_row["Body"]:
                raise APICallFailed(
                    "Color Page node-cleanup DB verification could not read the active grade version.",
                    details={"clip": clip_label, "clip_id": clip_id},
                )
            db_node_count = len(_root_color_node_containers(decompress_version_body(version_row["Body"])))
        finally:
            connection.close()

        api_node_count = None
        if fresh_conn is not None:
            try:
                from .. import color_ops

                api_node_count = int(color_ops.get_num_nodes(fresh_conn, clip_label or None))
            except Exception:
                api_node_count = None
        if db_node_count != expected_count:
            raise APICallFailed(
                "Color Page node-cleanup DB mutation did not verify by DB readback.",
                details={
                    "clip": clip_label,
                    "expected_node_count": expected_count,
                    "db_node_count": db_node_count,
                    "project_db_path": session.project_db_path,
                },
                recoverability="manual",
            )
        if api_node_count is not None and api_node_count != expected_count:
            raise APICallFailed(
                "Color Page node-cleanup DB mutation did not verify through DaVinci Resolve node graph readback.",
                details={
                    "clip": clip_label,
                    "expected_node_count": expected_count,
                    "api_node_count": api_node_count,
                    "db_node_count": db_node_count,
                },
                recoverability="manual",
            )
        return {
            "status": "verified",
            "clip": clip_label,
            "node_count": expected_count,
            "db_node_count": db_node_count,
            "api_node_count": api_node_count,
            "removed_node_count": int(mutation_result["removed_node_count"]),
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page node-cleanup empty serial db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    if isinstance(result, dict):
        result["db_session_route"] = result.get("route")
        result["route"] = "db_workaround_color_page_node_cleanup_empty_serial"
        verification = result.get("verification")
        if isinstance(verification, dict):
            result["node_count"] = verification.get("node_count", result.get("after_node_count"))
    return result


def write_page_alpha_output_connect(
    conn: Any,
    *,
    clip_name: str | None = None,
    track: int | None = None,
    at: str | None = None,
    node_index: int = 1,
) -> dict[str, Any]:
    """Connect one Color node's native key output to a verified Alpha Output."""
    from ..db_timeline_selection import resolve_video_group

    requested_node_index = int(node_index)
    if requested_node_index != 1:
        raise ValidationError(
            "Color Page Alpha Output DB route is verified only for node 1 in an exact single-node graph.",
            details={"node_index": requested_node_index, "verified_node_index": 1},
            recoverability="not_applicable",
        )
    item_ref = resolve_video_group(conn, clip_name=clip_name, track=track, at=at)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = str(timeline.GetName() if timeline and hasattr(timeline, "GetName") else "").strip()
    if not timeline_name:
        raise ValidationError(
            "Color Page Alpha Output DB route requires an exact active timeline name.",
            recoverability="not_applicable",
        )

    def writer(connection: Any, cursor: sqlite3.Cursor, session: DiskDbMutationSession) -> dict[str, Any]:
        row = find_ti_item_row(
            cursor,
            item=item_ref,
            db_type="Sm2TiVideoClip",
            timeline_name=timeline_name,
            require_timeline_name=True,
        )
        clip_id = str(row["Sm2TiItem_id"])
        version_row = _select_active_grade_version_for_clip(cursor, clip_id)
        if not version_row or not version_row["Body"]:
            raise APICallFailed(
                "Color Page Alpha Output DB route requires an existing Color grade on the selected clip.",
                details={
                    "clip": item_ref.name,
                    "track": item_ref.track_index,
                    "start": item_ref.start,
                    "timeline": timeline_name,
                },
                recoverability="not_applicable",
            )
        base_proto = decompress_version_body(version_row["Body"])
        before_hash = hashlib.sha256(base_proto).hexdigest()
        updated_proto, topology = _ensure_single_node_alpha_output_in_proto(
            base_proto,
            node_index=requested_node_index,
        )
        after_hash = hashlib.sha256(updated_proto).hexdigest()
        if topology["changed"]:
            cursor.execute(
                '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
                   WHERE "ListMgt::LmVersion_id" = ?''',
                (compress_version_body(updated_proto), version_row["ListMgt::LmVersion_id"]),
            )
            session.steps.append("connect_single_node_color_page_alpha_output")
        else:
            session.steps.append("connect_single_node_color_page_alpha_output_noop")
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "timeline": timeline_name,
            "track": item_ref.track_index,
            "start": item_ref.start,
            "duration": item_ref.duration,
            "node_index": requested_node_index,
            "changed": bool(topology["changed"]),
            "before_proto_sha256": before_hash,
            "after_proto_sha256": after_hash,
            "route": "db_workaround_color_page_alpha_output_connect",
            **topology,
        }

    def verifier(
        fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if fresh_conn is None or not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Page Alpha Output DB mutation did not return a live verification context.",
                details={"mutation_result": mutation_result},
                recoverability="manual",
            )
        fresh_timeline = getattr(fresh_conn, "timeline", None)
        fresh_timeline_name = str(
            fresh_timeline.GetName() if fresh_timeline and hasattr(fresh_timeline, "GetName") else ""
        ).strip()
        if fresh_timeline_name != timeline_name:
            raise APICallFailed(
                "Color Page Alpha Output DB mutation did not restore the exact target timeline.",
                details={"expected_timeline": timeline_name, "actual_timeline": fresh_timeline_name or None},
                recoverability="manual",
            )
        fresh_item = resolve_video_group(
            fresh_conn,
            clip_name=clip_name,
            track=track,
            at=at,
        )["video"]
        expected_item = {
            "track": int(mutation_result["track"]),
            "start": int(mutation_result["start"]),
            "duration": int(mutation_result["duration"]),
        }
        actual_item = {
            "track": int(fresh_item.track_index),
            "start": int(fresh_item.start),
            "duration": int(fresh_item.duration),
        }
        if actual_item != expected_item:
            raise APICallFailed(
                "Color Page Alpha Output DB verification resolved different clip timing or track placement.",
                details={"expected": expected_item, "actual": actual_item},
                recoverability="manual",
            )
        connection = sqlite3.connect(session.project_db_path)
        connection.row_factory = sqlite3.Row
        try:
            cursor = connection.cursor()
            row = find_ti_item_row(
                cursor,
                item=fresh_item,
                db_type="Sm2TiVideoClip",
                timeline_name=fresh_timeline_name,
                require_timeline_name=True,
            )
            if str(row["Sm2TiItem_id"]) != str(mutation_result["clip_id"]):
                raise APICallFailed(
                    "Color Page Alpha Output DB verification resolved a different timeline item.",
                    details={
                        "expected_clip_id": mutation_result["clip_id"],
                        "actual_clip_id": row["Sm2TiItem_id"],
                    },
                    recoverability="manual",
                )
            version_row = _select_active_grade_version_for_clip(cursor, str(row["Sm2TiItem_id"]))
            if not version_row or not version_row["Body"]:
                raise APICallFailed(
                    "Color Page Alpha Output DB verification could not read the active grade version.",
                    details={"clip": fresh_item.name, "clip_id": row["Sm2TiItem_id"]},
                    recoverability="manual",
                )
            proto = decompress_version_body(version_row["Body"])
            topology = _single_node_alpha_output_state(proto, node_index=requested_node_index)
            proto_hash = hashlib.sha256(proto).hexdigest()
        finally:
            connection.close()
        if not topology["alpha_output_connected"] or proto_hash != mutation_result["after_proto_sha256"]:
            raise APICallFailed(
                "Color Page Alpha Output DB mutation did not verify after reopening DaVinci Resolve.",
                details={
                    "clip": fresh_item.name,
                    "expected_proto_sha256": mutation_result["after_proto_sha256"],
                    "actual_proto_sha256": proto_hash,
                    "topology": topology,
                },
                recoverability="manual",
            )
        return {
            "status": "verified",
            "clip": fresh_item.name,
            "clip_id": str(row["Sm2TiItem_id"]),
            "timeline": fresh_timeline_name,
            "track": fresh_item.track_index,
            "start": fresh_item.start,
            "duration": fresh_item.duration,
            "proto_sha256": proto_hash,
            **topology,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page alpha output connect db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    if isinstance(result, dict):
        result["db_session_route"] = result.get("route")
        result["route"] = "db_workaround_color_page_alpha_output_connect"
    return result


__all__ = (
    'validate_page_node_add_kind',
    'write_page_node_add_serial',
    'write_page_node_add_parallel',
    'write_page_node_add_layer',
    'write_layer_mixer_composite_mode',
    'write_bleach_bypass',
    'write_bleach_bypass_intensity',
    'write_page_node_cleanup_empty_serial',
    'write_page_alpha_output_connect',
)
