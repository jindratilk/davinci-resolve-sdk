"""Mutations Cst helpers for Color Page DB operations."""

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


def write_color_space_transform(
    conn: Any,
    *,
    clip_name: str | None = None,
    node_index: int = 1,
    input_color_space: str | None = None,
    input_gamma: str | None = None,
    output_color_space: str | None = None,
    output_gamma: str | None = None,
) -> dict[str, Any]:
    """Create or update native ResolveFX Color Space Transform options in Color Page DB."""
    target_node_index = int(node_index)
    if target_node_index < 1:
        raise ValidationError(
            "Color Page node index must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    color_space_registry_tokens: set[str] | None = None
    gamma_registry_tokens: set[str] | None = None
    registry_status: dict[str, Any] = {"status": "not_available"}
    try:
        from .. import resolvefx_db

        registry = resolvefx_db.discover_cst_option_registry(conn)
        color_space_registry_tokens = {str(token).strip().upper() for token in registry.get("color_space_tokens") or []}
        gamma_registry_tokens = {str(token).strip().upper() for token in registry.get("gamma_tokens") or []}
        registry_status = {
            "status": "loaded",
            "route": registry.get("route"),
            "color_space_token_count": len(color_space_registry_tokens),
            "gamma_token_count": len(gamma_registry_tokens),
        }
    except Exception as exc:
        registry_status = {
            "status": "unavailable",
            "error": str(exc),
        }
    color_space_mapping = _build_cst_registry_token_map(
        CST_COLOR_SPACE_TOKENS,
        color_space_registry_tokens,
        suffix="_COLORSPACE",
        curated_aliases=CST_COLOR_SPACE_REGISTRY_ALIASES,
    )
    gamma_mapping = _build_cst_registry_token_map(
        CST_GAMMA_TOKENS,
        gamma_registry_tokens,
        suffix="_GAMMA",
        curated_aliases=CST_GAMMA_REGISTRY_ALIASES,
    )
    desired: dict[str, str] = {}
    for name, value, mapping, label in (
        (CST_PARAM_INPUT_COLOR_SPACE, input_color_space, color_space_mapping, "input color space"),
        (CST_PARAM_INPUT_GAMMA, input_gamma, gamma_mapping, "input gamma"),
        (CST_PARAM_OUTPUT_COLOR_SPACE, output_color_space, color_space_mapping, "output color space"),
        (CST_PARAM_OUTPUT_GAMMA, output_gamma, gamma_mapping, "output gamma"),
    ):
        allowed = color_space_registry_tokens if name.endswith("ColorSpace") else gamma_registry_tokens
        token = _normalize_cst_token(value, mapping, label, allowed_tokens=allowed)
        if token is not None:
            desired[name] = token

    if not desired:
        raise ValidationError("No Color Space Transform options specified.")

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
        if not ver_table_id:
            raise APICallFailed(
                "Color Space Transform DB route requires an existing Color Page grade/version table.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        ver = _select_active_grade_version(cursor, str(ver_table_id))
        if not ver or not ver["Body"]:
            raise APICallFailed(
                "Color Space Transform DB route requires an existing Color Page grade body.",
                details={"clip": item_ref.name},
                recoverability="manual",
            )

        base_proto = decompress_version_body(ver["Body"])
        created_tool = False
        removed_duplicate_tool = False
        route = "db_workaround_color_page_cst_existing_ofx"
        if not _walk_cst_options_for_node(base_proto, target_node_index):
            base_proto, removed_duplicate_tool = _insert_cst_tool_entries(
                base_proto,
                str(ver["ListMgt::LmVersion_id"]),
                desired,
                node_index=target_node_index,
            )
            new_proto = base_proto
            written = set(desired)
            changed = True
            created_tool = True
            route = "db_workaround_color_page_cst_insert_ofx"
        else:
            new_proto, written, changed, _cst_tool_count = _replace_cst_options_in_existing_tool(
                base_proto,
                desired,
                node_index=target_node_index,
            )

        existing_cst = _walk_cst_options_for_node(base_proto, target_node_index)
        missing = sorted(
            name for name, token in desired.items()
            if name not in written and existing_cst.get(name) != token
        )
        if missing:
            raise APICallFailed(
                "Color Space Transform DB route could not place all requested options.",
                details={"clip": item_ref.name, "missing": missing, "requested": desired},
                recoverability="manual",
            )
        if (
            not created_tool
            and not changed
            and all(_walk_cst_options(base_proto).get(name) == token for name, token in desired.items())
        ):
            session.steps.append("cst_options_already_matched")
        else:
            cursor.execute(
                '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
                   WHERE "ListMgt::LmVersion_id" = ?''',
                (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
            )
            session.steps.append("insert_cst_ofx_tool" if created_tool else "update_cst_ofx_options")

        state = read_color_grade(cursor, clip_id=clip_id, clip_name=item_ref.name)
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "node_index": target_node_index,
            "version_id": ver["ListMgt::LmVersion_id"],
            "cst_route": route,
            "created_tool": created_tool,
            "removed_duplicate_tool": removed_duplicate_tool,
            "params_written": desired,
            "cst_registry": registry_status,
            "node_cst_readback": _walk_cst_options_for_node(new_proto, target_node_index),
            "readback": state.to_dict(),
        }

    def verifier(
        _fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Space Transform DB mutation did not return a mutation payload for verification.",
                details={"mutation_result": mutation_result},
            )

        clip_id = mutation_result.get("clip_id")
        clip_label = str(mutation_result.get("clip") or clip_name or "")
        version_id = str(mutation_result.get("version_id") or "")
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
                    "Could not resolve the written clip during Color Space Transform verification.",
                    details={"clip": clip_label},
                )
            state = read_color_grade(cursor, clip_id=str(clip_id), clip_name=clip_label)
            version_row = cursor.execute(
                'SELECT Body FROM "ListMgt::LmVersion" WHERE "ListMgt::LmVersion_id" = ?',
                (version_id,),
            ).fetchone() if version_id else None
            node_cst = (
                _walk_cst_options_for_node(decompress_version_body(version_row["Body"]), target_node_index)
                if version_row and version_row["Body"]
                else {}
            )
        finally:
            connection.close()

        readback = node_cst
        mismatches = [
            {"name": name, "expected": expected, "actual": readback.get(name)}
            for name, expected in desired.items()
            if readback.get(name) != expected
        ]
        if mismatches:
            raise APICallFailed(
                "Color Space Transform DB mutation did not verify after project reload.",
                details={
                    "clip": clip_label,
                    "project_db_path": session.project_db_path,
                    "mismatches": mismatches,
                    "readback": state.to_dict(),
                },
                recoverability="manual",
            )
        return {
            "status": "verified",
            "clip": clip_label,
            "node_index": target_node_index,
            "params_verified": desired,
            "readback": readback,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page cst db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    result["db_session_route"] = result.get("route")
    result["route"] = result.get("cst_route", "db_workaround_color_page_cst_existing_ofx")
    return result


def delete_color_params(
    conn: Any,
    *,
    clip_name: str | None = None,
    param_names: list[str],
) -> dict[str, Any]:
    """Delete explicit Color Page params so DaVinci Resolve falls back to GUI defaults."""
    delete_keys: set[int] = set()
    unknown: list[str] = []
    for raw_name in param_names:
        name = str(raw_name or "").strip().lower().replace("-", "_")
        if not name:
            continue
        key = PARAM_KEYS_BY_NAME.get(name)
        if key is None:
            unknown.append(raw_name)
        else:
            delete_keys.add(key)
    if unknown:
        raise ValidationError(
            "Unknown Color Page parameter name.",
            details={"unknown": unknown, "known": sorted(PARAM_KEYS_BY_NAME)},
            recoverability="not_applicable",
        )
    if not delete_keys:
        raise ValidationError("No Color Page parameter names specified.")
    return write_color_grade(conn, clip_name=clip_name, delete_param_keys=delete_keys)


__all__ = (
    'write_color_space_transform',
    'delete_color_params',
)
