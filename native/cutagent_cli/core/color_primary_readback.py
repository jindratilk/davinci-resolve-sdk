"""Read-only Project.db readback for persisted Color primary controls."""

from __future__ import annotations

import math
from pathlib import Path
import sqlite3
from typing import Any, Iterable
from urllib.parse import quote

from . import db_session, db_timeline_rows, db_timeline_selection, clip_effects_db
from ._color_page_db import constants
from ._color_page_db.grade_state import read_color_grade, read_color_topology_evidence
from ._color_page_db.params import GradeParam


_PRIMARY_KEYS = frozenset({
    constants.PARAM_SATURATION,
    constants.PARAM_HUE,
    constants.PARAM_CONTRAST,
    constants.PARAM_PIVOT,
    constants.PARAM_TEMPERATURE,
    constants.PARAM_TINT,
    constants.PARAM_LIFT_R,
    constants.PARAM_LIFT_G,
    constants.PARAM_LIFT_B,
    constants.PARAM_GAIN_R,
    constants.PARAM_GAIN_G,
    constants.PARAM_GAIN_B,
    constants.PARAM_GAIN_MASTER,
    constants.PARAM_GAMMA_R,
    constants.PARAM_GAMMA_G,
    constants.PARAM_GAMMA_B,
    constants.PARAM_GAMMA_MASTER,
    constants.PARAM_OFFSET_R,
    constants.PARAM_OFFSET_G,
    constants.PARAM_OFFSET_B,
    constants.PARAM_LUM_MIX,
    constants.PARAM_HIGHLIGHTS,
    constants.PARAM_SHADOWS,
    constants.PARAM_COLOR_BOOST,
    constants.PARAM_MID_DETAIL,
})


class ColorPrimaryReadbackError(ValueError):
    """Persisted Color primary-control evidence was malformed or ambiguous."""


def decode_color_primary_controls(params: Iterable[GradeParam]) -> dict[str, dict[str, float | int]]:
    """Return only explicit, fixture-backed primary parameters grouped by node.

    Values remain in DaVinci Resolve's persisted parameter domain. Missing
    parameters stay missing; this deliberately avoids ColorGradeState's neutral
    convenience defaults.
    """

    by_node: dict[str, dict[str, float | int]] = {}
    seen: set[tuple[int, int]] = set()
    for param in params:
        if param.key not in _PRIMARY_KEYS:
            continue
        identity = (int(param.node_index), int(param.key))
        if identity in seen:
            raise ColorPrimaryReadbackError("duplicate Color primary parameter")
        seen.add(identity)
        if param.node_index < 1:
            raise ColorPrimaryReadbackError("invalid Color node index")
        value = param.value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ColorPrimaryReadbackError("Color primary parameter is not numeric")
        if isinstance(value, float) and not math.isfinite(value):
            raise ColorPrimaryReadbackError("Color primary parameter is not finite")
        by_node.setdefault(str(param.node_index), {})[param.name] = (
            round(value, 6) if isinstance(value, float) else value
        )
    return by_node


def decode_color_node_enabled(proto: bytes) -> dict[str, bool]:
    """Read native serial-node enable values from their exact control location."""
    if not proto:
        return {}

    def fields(data):
        parsed = clip_effects_db._parse_wire_fields(data)
        if parsed is None:
            raise ColorPrimaryReadbackError("malformed Color node enabled state")
        return parsed

    def one(data, number, wire):
        values = [x.value for x in fields(data) if x.number == number and x.wire_type == wire]
        if len(values) > 1:
            raise ColorPrimaryReadbackError("ambiguous Color node enabled state")
        return values[0] if values else None

    root = one(proto, 1, 2)
    if root is None:
        return {}
    result = {}
    seen_indices = set()
    for container in [x.value for x in fields(root) if x.number == 7 and x.wire_type == 2]:
        if one(container, 8, 0) != 44:
            continue  # Other node kinds have not been qualified by the native probe.
        index = one(container, 2, 0)
        controls = one(container, 10, 2)
        if index is None or index < 1 or controls is None:
            continue
        key = str(index)
        if key in seen_indices:
            raise ColorPrimaryReadbackError("duplicate Color node index")
        seen_indices.add(key)
        for param in [x.value for x in fields(controls) if x.number == 1 and x.wire_type == 2]:
            if one(param, 1, 0) != constants.PARAM_NODE_ENABLE:
                continue
            value = one(param, 2, 2)
            if value is None:
                continue
            values = fields(value)
            if len(values) != 1 or values[0].number != 2 or values[0].wire_type != 0 or values[0].value not in (0, 2):
                raise ColorPrimaryReadbackError("unsupported Color node enable encoding")
            if key in result:
                raise ColorPrimaryReadbackError("duplicate Color node enable parameter")
            result[key] = values[0].value == 2
    return result


def _read_only_connection(path: str) -> sqlite3.Connection:
    resolved = Path(path).expanduser().resolve(strict=True)
    connection = sqlite3.connect(f"file:{quote(str(resolved))}?mode=ro", uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    return connection


def list_color_primary_controls(conn: Any) -> dict[str, Any]:
    """Read persisted primary controls for every identity-bound live video item."""

    current_database = db_session.resolve_current_disk_project_db(
        conn, allow_project_name_inference=True
    )
    timeline_name = None
    try:
        timeline_name = str(conn.timeline.GetName() or "") or None
    except Exception:
        pass
    live_items = db_timeline_selection._read_live_items(conn, track_type="video")
    items: list[dict[str, Any]] = []
    connection = _read_only_connection(str(current_database["project_db_path"]))
    try:
        cursor = connection.cursor()
        for item in live_items:
            base = {
                "itemId": item.item_id,
                "trackIndex": int(item.track_index),
                "recordStartFrame": int(item.start),
                "recordEndFrame": int(item.end),
            }
            if not item.item_id:
                items.append({**base, "status": "unavailable", "reason": "native_item_identity_unavailable"})
                continue
            try:
                row = db_timeline_rows.find_ti_item_row(
                    cursor,
                    item=item,
                    db_type="Sm2TiVideoClip",
                    timeline_name=timeline_name,
                )
                if str(row.get("Sm2TiItem_id") or "") != item.item_id:
                    raise ColorPrimaryReadbackError("live and persisted item identities differ")
                state = read_color_grade(
                    cursor,
                    clip_id=item.item_id,
                    clip_name=item.name,
                )
                controls = decode_color_primary_controls(state.params)
                enabled = decode_color_node_enabled(state.proto_data or b"")
            except Exception as exc:
                items.append({
                    **base,
                    "status": "unavailable",
                    "reason": "project_db_color_primary_readback_unavailable",
                    "detail": str(exc),
                })
                continue
            try:
                topology = read_color_topology_evidence(state.proto_data or b"")
                topology_evidence = {
                    "status": "partial",
                    "layerIndex": 1,
                    "connectivityComplete": False,
                    "matchesVerifiedLayout": topology["exact"],
                    "containers": topology["containers"],
                    "encodedEdges": topology["edges"],
                    "renderGraphEvidence": topology["render"],
                    "structureSha256": topology["structure_sha256"],
                    "source": "active persisted first-layer grade",
                    "limitations": "Encoded edge fields and render hashes are evidence, not complete graph connectivity; additional layers and group graphs are not decoded here.",
                }
            except Exception:
                topology_evidence = {"status": "unavailable", "reason": "persisted_color_topology_unreadable"}
            items.append({
                **base,
                "status": "available",
                "hasGrade": bool(state.has_grade),
                "primaryControlsByNode": controls,
                "nodeEnabledByNode": enabled,
                "topologyEvidence": topology_evidence,
                "valueDomain": "Project.db persisted Color parameter value",
                "source": "active ListMgt::LmVersion Body",
            })
    finally:
        connection.close()
    return {
        "items": items,
        "count": len(items),
        "route": "project_db_read_only",
        "identitySource": "TimelineItem.GetUniqueId equals Sm2TiItem.Sm2TiItem_id",
        "nodeEnabled": {
            "status": "partial",
            "source": "exact serial-node container enable control; native 21.1 true/false/true qualification",
            "limitations": "only explicit values on node type 44 in the active persisted first-layer grade",
        },
    }
