"""Snapshot helpers for Color Page DB operations."""

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
from .mutations_power_windows import *


def snapshot_color_data(
    db_path: str,
    clip_name: str | None = None,
) -> dict[str, Any]:
    """Extract color grading data from a Project.db for analysis.

    This is a standalone function that doesn't require a live DaVinci Resolve connection.
    """
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row

    try:
        clips = connection.execute(
            "SELECT Sm2TiItem_id, Name, pLmVerTable FROM Sm2TiItem WHERE DbType = 'Sm2TiVideoClip'"
        ).fetchall()

        results: list[dict[str, Any]] = []
        for clip in clips:
            if clip_name and clip["Name"] != clip_name:
                continue

            entry: dict[str, Any] = {
                "clip": clip["Name"],
                "id": clip["Sm2TiItem_id"],
                "versions": [],
            }

            ver_table_id = clip["pLmVerTable"]
            if ver_table_id:
                versions = connection.execute(
                    '''SELECT v."ListMgt::LmVersion_id", v.Name, v.HasCorrection, v.Body
                       FROM "ListMgt::LmVersion" v
                       JOIN "ListMgt::LmVersion_ListMgt::LmVersionTable" rel
                         ON rel.DbAssociate = v."ListMgt::LmVersion_id"
                       WHERE rel.DbOwner = ?''',
                    (ver_table_id,),
                ).fetchall()

                for v in versions:
                    ver_entry: dict[str, Any] = {
                        "id": v["ListMgt::LmVersion_id"],
                        "name": v["Name"],
                        "has_correction": bool(v["HasCorrection"]),
                        "body_size": len(v["Body"]) if v["Body"] else 0,
                    }

                    if v["Body"]:
                        try:
                            proto = decompress_version_body(v["Body"])
                            ver_entry["proto_size"] = len(proto)
                            ver_entry["compression"] = "zstd" if v["Body"][0] == VERSION_BODY_PREFIX_ZSTD else "none"

                            params = _parse_params_from_proto(proto)
                            ver_entry["params"] = [param.to_dict() for param in params]
                            state = ColorGradeState(
                                clip_name=str(clip["Name"] or ""),
                                has_grade=bool(v["HasCorrection"]),
                                params=params,
                                proto_data=proto,
                            )
                            ver_entry["nodes"] = state._nodes()
                            ver_entry["curves"] = _params_to_curves_dict(params)
                            from .color_warper import _existing_color_warper_state

                            color_warper = _existing_color_warper_state(proto)
                            if color_warper:
                                ver_entry["color_warper"] = color_warper
                            hdr = _params_to_hdr_dict(params)
                            if hdr:
                                ver_entry["hdr"] = hdr
                            ver_entry["cst"] = _walk_cst_options(proto)
                        except Exception as e:
                            ver_entry["error"] = str(e)

                    entry["versions"].append(ver_entry)

            results.append(entry)

        return {"db_path": db_path, "clips": results}
    finally:
        connection.close()


__all__ = (
    'snapshot_color_data',
)
