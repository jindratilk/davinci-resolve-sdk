"""Exact-item read-only ResolveFX state from persisted Color grade bodies."""

from __future__ import annotations

import math
from pathlib import Path
import re
import sqlite3
from typing import Any
from urllib.parse import quote

from . import db_session, db_timeline_rows, db_timeline_selection
from .color_page_db import _root_color_node_containers
from ._color_page_db.grade_state import read_color_grade
from .resolvefx_db import read_resolvefx_state


_DECODED_SETTING_TYPES = frozenset({"double", "int", "string"})
_EFFECT_ID = re.compile(r"^com\.blackmagicdesign\.resolvefx\.[A-Za-z0-9._-]{1,160}$")
_SETTING_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_UNKNOWN_REMAINDER = (
    {
        "scope": "node_stack_layers_above_1",
        "status": "unavailable",
        "reason": "no_verified_project_db_layer_mapping",
    },
    {
        "scope": "additional_effects_per_node",
        "status": "unavailable",
        "reason": "verified_reader_exposes_one_resolvefx_tool_slot_per_node",
    },
    {
        "scope": "unrecognized_or_undecoded_effect_payloads",
        "status": "unavailable",
        "reason": "only_safe_exact_resolvefx_ids_and_decoded_settings_are_exposed",
    },
)


def _read_only_connection(path: str) -> sqlite3.Connection:
    resolved = Path(path).expanduser().resolve(strict=True)
    connection = sqlite3.connect(
        f"file:{quote(str(resolved))}?mode=ro",
        uri=True,
        timeout=5.0,
    )
    connection.row_factory = sqlite3.Row
    return connection


def _safe_string_setting(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 512:
        return False
    if any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value):
        return False
    lowered = value.strip().lower()
    return not (
        lowered.startswith(("/", "\\", "~/", "file:"))
        or re.match(r"^[a-z]:[\\/]", lowered)
        or "/../" in f"/{lowered}/"
        or "\\..\\" in f"\\{lowered}\\"
    )


def _safe_decoded_setting(value_type: str, value: object) -> bool:
    if value_type == "double":
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
        )
    if value_type == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if value_type == "string":
        return _safe_string_setting(value)
    return False


def _setting_rows(options: object) -> list[dict[str, Any]]:
    if not isinstance(options, dict):
        return []
    rows: list[dict[str, Any]] = []
    for raw_name, raw_value in sorted(options.items()):
        name = str(raw_name)
        value = raw_value if isinstance(raw_value, dict) else {}
        value_type = str(value.get("type") or "").strip().lower()
        decoded_value = value.get("value")
        identity_safe = bool(_SETTING_NAME.fullmatch(name))
        value_decoded = value_type in _DECODED_SETTING_TYPES and "value" in value
        value_safe = value_decoded and _safe_decoded_setting(value_type, decoded_value)
        if identity_safe and value_safe:
            rows.append({
                "name": name,
                "status": "available",
                "type": value_type,
                "value": value["value"],
            })
        else:
            rows.append({
                "name": name if identity_safe else None,
                "status": "unavailable",
                "reason": (
                    "setting_identity_not_safe"
                    if not identity_safe
                    else "value_encoding_not_decoded"
                    if not value_decoded
                    else "setting_value_not_safe"
                ),
            })
    return rows


def decode_color_resolvefx_effects(proto_data: bytes | None) -> list[dict[str, Any]]:
    """Decode only ResolveFX identities/settings proven by the existing DB reader."""

    if not proto_data:
        return []
    effects: list[dict[str, Any]] = []
    node_count = len(_root_color_node_containers(proto_data))
    for node_index in range(1, node_count + 1):
        state = read_resolvefx_state(proto_data, node_index=node_index)
        plugin_id = state.get("plugin_id")
        if not isinstance(plugin_id, str) or not _EFFECT_ID.fullmatch(plugin_id.strip()):
            continue
        settings = _setting_rows(state.get("options"))
        effects.append({
            "nodeStackLayerIndex": 1,
            "nodeIndex": node_index,
            "effectId": plugin_id.strip(),
            "settings": settings,
            "unknownSettingCount": sum(row["status"] != "available" for row in settings),
            "source": "active ListMgt::LmVersion ResolveFX tool payload",
        })
    return effects


def list_color_resolvefx_state(conn: Any) -> dict[str, Any]:
    """Read layer-1 ResolveFX state for every exact-identity live video item."""

    current_database = db_session.resolve_current_disk_project_db(
        conn,
        allow_project_name_inference=True,
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
                items.append({
                    **base,
                    "status": "unavailable",
                    "reason": "native_item_identity_unavailable",
                    "effects": [],
                })
                continue
            try:
                row = db_timeline_rows.find_ti_item_row(
                    cursor,
                    item=item,
                    db_type="Sm2TiVideoClip",
                    timeline_name=timeline_name,
                )
                if str(row["Sm2TiItem_id"] or "") != item.item_id:
                    raise ValueError("live and persisted item identities differ")
                grade = read_color_grade(
                    cursor,
                    clip_id=item.item_id,
                    clip_name=item.name,
                )
                effects = decode_color_resolvefx_effects(grade.proto_data)
            except Exception:
                items.append({
                    **base,
                    "status": "unavailable",
                    "reason": "project_db_resolvefx_readback_unavailable",
                    "effects": [],
                })
                continue
            items.append({
                **base,
                "status": "available",
                "effects": effects,
                "source": "active ListMgt::LmVersion Body",
            })
    finally:
        connection.close()
    return {
        "items": items,
        "count": len(items),
        "route": "project_db_read_only",
        "identitySource": "TimelineItem.GetUniqueId equals Sm2TiItem.Sm2TiItem_id",
        "knownNodeStackLayers": [1],
        "unknownRemainder": [dict(row) for row in _UNKNOWN_REMAINDER],
    }
