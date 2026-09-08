"""Mutations Color helpers for Color Page DB operations."""

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

PARAM_COLOR_WARPER_MODE = 0x86000136
PARAM_COLOR_WARPER_TOOL = 0x86000137
PARAM_COLOR_WARPER_PIN = 0x86000139
COLOR_WARPER_CHROMA_WARP_MODE = 2
COLOR_WARPER_PIN_TOOL = 4
COLOR_WARPER_DEFAULT_RADIUS = 0.04
QUALIFIER_HSL_TOOL_VALUE = 4
QUALIFIER_MODE_HSL_VALUE = 0
QUALIFIER_UI_SCALE = 100.0
QUALIFIER_DEFAULT_HSL_VALUES = {
    PARAM_QUAL_HUE_CENTER: 0.5,
    PARAM_QUAL_HUE_WIDTH: 1.0,
    PARAM_QUAL_HUE_SOFT: 0.0,
    PARAM_QUAL_HUE_SYMMETRY: 0.5,
    PARAM_QUAL_SAT_LOW_CLIP: 0.0,
    PARAM_QUAL_SAT_HIGH_CLIP: 1.0,
    PARAM_QUAL_SAT_LOW_SOFT: 0.0,
    PARAM_QUAL_SAT_HIGH_SOFT: 0.0,
    PARAM_QUAL_LUM_LOW_CLIP: 0.0,
    PARAM_QUAL_LUM_HIGH_CLIP: 1.0,
    PARAM_QUAL_LUM_LOW_SOFT: 0.0,
    PARAM_QUAL_LUM_HIGH_SOFT: 0.0,
}
QUALIFIER_HSL_COMPANION_MAP = {
    PARAM_QUAL_HUE_WIDTH: PARAM_QUAL_HUE_WIDTH_COMPANION,
    PARAM_QUAL_HUE_SOFT: PARAM_QUAL_HUE_SOFT_COMPANION,
}
QUALIFIER_NODE2_TOOL_PAYLOAD = bytes.fromhex(
    "522d0d0000103f15000000001d0000000025000000002d0000803f"
    "35000000003d0000000045000000004d0000803f"
)


def _validate_warper_coord_pair(value: tuple[float, float], *, label: str) -> tuple[float, float]:
    x, y = float(value[0]), float(value[1])
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValidationError(
            f"Color Warper {label} coordinates must be finite numbers.",
            details={label: [x, y]},
            recoverability="not_applicable",
        )
    if x < 0.0 or x > 1.0 or y < 0.0 or y > 1.0:
        raise ValidationError(
            f"Color Warper {label} coordinates must be normalized between 0.0 and 1.0.",
            details={label: [x, y], "minimum": 0.0, "maximum": 1.0},
            recoverability="not_applicable",
        )
    return x, y


def _build_color_warper_triplet(x: float, y: float, radius: float = COLOR_WARPER_DEFAULT_RADIUS) -> bytes:
    return _encode_length_delimited(
        1,
        _encode_fixed32_field(1, struct.pack("<f", x))
        + _encode_fixed32_field(2, struct.pack("<f", y))
        + _encode_fixed32_field(3, struct.pack("<f", radius)),
    )


def _build_color_warper_pin_value(
    *,
    point: tuple[float, float],
    target: tuple[float, float],
    radius: float = COLOR_WARPER_DEFAULT_RADIUS,
) -> bytes:
    point_x, point_y = _validate_warper_coord_pair(point, label="point")
    target_x, target_y = _validate_warper_coord_pair(target, label="target")
    if not math.isfinite(radius) or radius <= 0.0 or radius > 1.0:
        raise ValidationError(
            "Color Warper pin radius must be a finite number between 0.0 and 1.0.",
            details={"radius": radius, "minimum": 0.0, "maximum": 1.0},
            recoverability="not_applicable",
        )
    return (
        _build_color_warper_triplet(point_x, point_y, radius)
        + _build_color_warper_triplet(target_x, target_y, radius)
    )


def _raw_color_warper_entries(
    *,
    point: tuple[float, float],
    target: tuple[float, float],
) -> dict[int, bytes]:
    pin_value = _build_color_warper_pin_value(point=point, target=target)
    return {
        PARAM_COLOR_WARPER_MODE: _build_varint_param_field(
            PARAM_COLOR_WARPER_MODE,
            COLOR_WARPER_CHROMA_WARP_MODE,
        ),
        PARAM_COLOR_WARPER_TOOL: _build_varint_param_field(
            PARAM_COLOR_WARPER_TOOL,
            COLOR_WARPER_PIN_TOOL,
        ),
        PARAM_COLOR_WARPER_PIN: _build_bytes_param_field(
            PARAM_COLOR_WARPER_PIN,
            pin_value,
            inner_field=28,
        ),
    }


def _inject_color_warper_pin_into_proto(
    base_proto: bytes,
    *,
    point: tuple[float, float],
    target: tuple[float, float],
) -> bytes:
    field7 = _extract_submessage(base_proto, [1, 7])
    if field7 is None:
        base_proto = _build_graded_proto_from_baseline(base_proto, {})

    existing_f2 = _extract_submessage(base_proto, [1, 7, 9, 1, 6, 2])
    if existing_f2 is None:
        raise APICallFailed(
            "Color Warper DB route could not find the Color Page param section.",
            recoverability="manual",
        )
    new_f2 = _rebuild_param_section_encoded(
        existing_f2,
        _raw_color_warper_entries(point=point, target=target),
    )
    return _replace_submessage_at_path(base_proto, [1, 7, 9, 1, 6, 2], new_f2)


def _color_warper_readback(state: ColorGradeState) -> dict[str, Any]:
    actual_by_key = {param.key: param for param in state.params}
    pin = actual_by_key.get(PARAM_COLOR_WARPER_PIN)
    return {
        "mode": actual_by_key.get(PARAM_COLOR_WARPER_MODE).value if actual_by_key.get(PARAM_COLOR_WARPER_MODE) else None,
        "tool": actual_by_key.get(PARAM_COLOR_WARPER_TOOL).value if actual_by_key.get(PARAM_COLOR_WARPER_TOOL) else None,
        "pin_payload_b64": (
            base64.b64encode(pin.value).decode("ascii")
            if pin is not None and isinstance(pin.value, bytes)
            else None
        ),
    }


def _validate_qualifier_ui_value(value: float, *, label: str) -> float:
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValidationError(
            f"Color Page Qualifier {label} must be a finite number.",
            details={label: value},
            recoverability="not_applicable",
        )
    if numeric < 0.0 or numeric > 100.0:
        raise ValidationError(
            f"Color Page Qualifier {label} must be between 0.0 and 100.0.",
            details={label: numeric, "minimum": 0.0, "maximum": 100.0},
            recoverability="not_applicable",
        )
    return numeric / QUALIFIER_UI_SCALE


def _qualifier_hsl_updates(
    *,
    hue: tuple[float, float, float, float] | None = None,
    saturation: tuple[float, float, float, float] | None = None,
    luma: tuple[float, float, float, float] | None = None,
    blur_radius: float | None = None,
) -> tuple[dict[int, float], dict[int, float], dict[str, Any]]:
    node1_updates: dict[int, float] = {}
    node2_updates: dict[int, float] = dict(QUALIFIER_DEFAULT_HSL_VALUES)
    requested: dict[str, Any] = {}

    if hue is not None:
        center, width, soft, symmetry = hue
        node2_updates.update(
            {
                PARAM_QUAL_HUE_CENTER: _validate_qualifier_ui_value(center, label="hue_center"),
                PARAM_QUAL_HUE_WIDTH: _validate_qualifier_ui_value(width, label="hue_width"),
                PARAM_QUAL_HUE_SOFT: _validate_qualifier_ui_value(soft, label="hue_soft"),
                PARAM_QUAL_HUE_SYMMETRY: _validate_qualifier_ui_value(symmetry, label="hue_symmetry"),
            }
        )
        requested["hue"] = {"center": center, "width": width, "soft": soft, "symmetry": symmetry}
    if saturation is not None:
        low, high, low_soft, high_soft = saturation
        node2_updates.update(
            {
                PARAM_QUAL_SAT_LOW_CLIP: _validate_qualifier_ui_value(low, label="saturation_low"),
                PARAM_QUAL_SAT_HIGH_CLIP: _validate_qualifier_ui_value(high, label="saturation_high"),
                PARAM_QUAL_SAT_LOW_SOFT: _validate_qualifier_ui_value(low_soft, label="saturation_low_soft"),
                PARAM_QUAL_SAT_HIGH_SOFT: _validate_qualifier_ui_value(high_soft, label="saturation_high_soft"),
            }
        )
        requested["saturation"] = {"low": low, "high": high, "low_soft": low_soft, "high_soft": high_soft}
    if luma is not None:
        low, high, low_soft, high_soft = luma
        node2_updates.update(
            {
                PARAM_QUAL_LUM_LOW_CLIP: _validate_qualifier_ui_value(low, label="luma_low"),
                PARAM_QUAL_LUM_HIGH_CLIP: _validate_qualifier_ui_value(high, label="luma_high"),
                PARAM_QUAL_LUM_LOW_SOFT: _validate_qualifier_ui_value(low_soft, label="luma_low_soft"),
                PARAM_QUAL_LUM_HIGH_SOFT: _validate_qualifier_ui_value(high_soft, label="luma_high_soft"),
            }
        )
        requested["luma"] = {"low": low, "high": high, "low_soft": low_soft, "high_soft": high_soft}
    if blur_radius is not None:
        node1_updates[PARAM_QUAL_MATTE_BLUR_RADIUS] = _validate_qualifier_ui_value(
            blur_radius,
            label="blur_radius",
        )
        requested["blur_radius"] = blur_radius

    for source_key, companion_key in QUALIFIER_HSL_COMPANION_MAP.items():
        node2_updates[companion_key] = node2_updates[source_key]

    return node1_updates, node2_updates, requested


def _build_qualifier_float_entries(updates: dict[int, float]) -> dict[int, bytes]:
    return {
        key: _encode_length_delimited(3, _build_param_entry(key, value))
        for key, value in updates.items()
    }


def _build_qualifier_node2_entries(updates: dict[int, float]) -> dict[int, bytes]:
    entries = _build_qualifier_float_entries(updates)
    entries[PARAM_QUAL_HSL_TOOL] = _build_varint_param_field(PARAM_QUAL_HSL_TOOL, QUALIFIER_HSL_TOOL_VALUE)
    entries[PARAM_QUAL_MODE] = _build_varint_param_field(PARAM_QUAL_MODE, QUALIFIER_MODE_HSL_VALUE)
    entries[0x88300031] = _build_bytes_param_field(
        0x88300031,
        QUALIFIER_NODE2_TOOL_PAYLOAD,
        inner_field=10,
    )
    return entries


def _build_qualifier_node(node_index: int, entries: dict[int, bytes]) -> bytes:
    param_section = _encode_varint_field(1, 1) + b"".join(entries[key] for key in entries)
    return (
        _encode_varint_field(1, node_index)
        + _encode_varint_field(3, 1)
        + _encode_length_delimited(6, _encode_length_delimited(2, param_section))
    )


def _set_qualifier_params_in_proto(
    base_proto: bytes,
    *,
    node1_updates: dict[int, float],
    node2_updates: dict[int, float],
) -> bytes:
    if _extract_submessage(base_proto, [1, 7]) is None:
        base_proto = _build_graded_proto_from_baseline(base_proto, {})

    field9 = _extract_submessage(base_proto, [1, 7, 9])
    if field9 is None:
        raise APICallFailed(
            "Color Page Qualifier DB route could not find the Color Page node section.",
            recoverability="manual",
        )
    _fields, nodes, node_order = _split_grade_node_section(field9)
    if not nodes:
        raise APICallFailed(
            "Color Page Qualifier DB route could not find a primary Color Page node.",
            recoverability="manual",
        )

    if node1_updates:
        node1 = nodes[0]
        f6 = _get_submessage(node1, 6)
        f2 = _get_submessage(f6, 2) if f6 is not None else None
        if f2 is None:
            raise APICallFailed(
                "Color Page Qualifier DB route could not find the primary Color Page param section.",
                recoverability="manual",
            )
        node1 = _replace_submessage_at_path(
            node1,
            [6, 2],
            _rebuild_param_section_encoded(f2, _build_qualifier_float_entries(node1_updates)),
        )
        field9 = _replace_grade_node(field9, 1, node1)

    node2_entries = _build_qualifier_node2_entries(node2_updates)
    if len(nodes) >= 2:
        node2 = nodes[1]
        f6 = _get_submessage(node2, 6)
        f2 = _get_submessage(f6, 2) if f6 is not None else None
        if f2 is None:
            node2 = _build_qualifier_node(2, node2_entries)
        else:
            node2 = _replace_submessage_at_path(
                node2,
                [6, 2],
                _rebuild_param_section_encoded(f2, node2_entries),
            )
        field9 = _replace_grade_node(field9, 2, node2)
    else:
        field9 = _insert_grade_node_after_index(
            field9,
            _build_qualifier_node(2, node2_entries),
            1,
        )

    return _replace_submessage_at_path(base_proto, [1, 7, 9], field9)


def _qualifier_readback(state: ColorGradeState) -> dict[str, Any]:
    params = {param.key: param for param in state.params}

    def _float_value(key: int) -> float | None:
        value = params.get(key).value if params.get(key) else None
        return float(value) if isinstance(value, float) else None

    def _ui_value(key: int) -> float | None:
        value = _float_value(key)
        return None if value is None else round(value * QUALIFIER_UI_SCALE, 3)

    return {
        "hue": {
            "center": _ui_value(PARAM_QUAL_HUE_CENTER),
            "width": _ui_value(PARAM_QUAL_HUE_WIDTH),
            "soft": _ui_value(PARAM_QUAL_HUE_SOFT),
            "symmetry": _ui_value(PARAM_QUAL_HUE_SYMMETRY),
        },
        "saturation": {
            "low": _ui_value(PARAM_QUAL_SAT_LOW_CLIP),
            "high": _ui_value(PARAM_QUAL_SAT_HIGH_CLIP),
            "low_soft": _ui_value(PARAM_QUAL_SAT_LOW_SOFT),
            "high_soft": _ui_value(PARAM_QUAL_SAT_HIGH_SOFT),
        },
        "luma": {
            "low": _ui_value(PARAM_QUAL_LUM_LOW_CLIP),
            "high": _ui_value(PARAM_QUAL_LUM_HIGH_CLIP),
            "low_soft": _ui_value(PARAM_QUAL_LUM_LOW_SOFT),
            "high_soft": _ui_value(PARAM_QUAL_LUM_HIGH_SOFT),
        },
        "blur_radius": _ui_value(PARAM_QUAL_MATTE_BLUR_RADIUS),
        "tool": params.get(PARAM_QUAL_HSL_TOOL).value if params.get(PARAM_QUAL_HSL_TOOL) else None,
        "mode": params.get(PARAM_QUAL_MODE).value if params.get(PARAM_QUAL_MODE) else None,
    }


def _qualifier_hsl_param_name(key: int) -> str:
    return QUALIFIER_HSL_PARAM_NAMES.get(key, PARAM_NAMES.get(key, f"0x{key:08X}"))


def _write_hsl_qualifier_matte_refinement(
    conn: Any,
    *,
    clip_name: str | None = None,
    hue: tuple[float, float, float, float] | None = None,
    saturation: tuple[float, float, float, float] | None = None,
    luma: tuple[float, float, float, float] | None = None,
    blur_radius: float | None = None,
) -> dict[str, Any]:
    """Write verified native Color Page HSL Qualifier matte refinement params."""
    if hue is None and saturation is None and luma is None and blur_radius is None:
        raise ValidationError(
            "Color Page qualifier-matte-refine requires --hue, --saturation, --luma, or --blur-radius.",
            details={"required_any": ["--hue", "--saturation", "--luma", "--blur-radius"]},
            recoverability="not_applicable",
        )
    node1_updates, node2_updates, requested = _qualifier_hsl_updates(
        hue=hue,
        saturation=saturation,
        luma=luma,
        blur_radius=blur_radius,
    )

    from ..db_timeline_selection import resolve_video_group

    item_ref = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None

    def writer(connection: Any, cursor: sqlite3.Cursor, session: DiskDbMutationSession) -> dict[str, Any]:
        row = find_ti_item_row(cursor, item=item_ref, db_type="Sm2TiVideoClip", timeline_name=timeline_name)
        clip_id = row["Sm2TiItem_id"]
        ver_table_id = row["pLmVerTable"]
        ver = None
        if ver_table_id:
            ver = cursor.execute(
                '''SELECT v."ListMgt::LmVersion_id", v.Body
                   FROM "ListMgt::LmVersion" v
                   JOIN "ListMgt::LmVersion_ListMgt::LmVersionTable" rel
                     ON rel.DbAssociate = v."ListMgt::LmVersion_id"
                   WHERE rel.DbOwner = ? AND v.HasCorrection = 1
                   ORDER BY v.rowid DESC LIMIT 1''',
                (ver_table_id,),
            ).fetchone()

        created_version_table = False
        created_version = False
        if ver and ver["Body"]:
            base_proto = decompress_version_body(ver["Body"])
            version_id = ver["ListMgt::LmVersion_id"]
        else:
            base_proto = decompress_version_body(bytes.fromhex(_BASELINE_VERSION_BODY_HEX))
            if not ver_table_id:
                ver_table_id = _create_lm_version_table_for_item(
                    cursor,
                    item_id=str(clip_id),
                    fields_blob=bytes.fromhex(_VERSION_TABLE_FIELDS_BLOB_HEX),
                )
                created_version_table = True
            version_id = str(uuid.uuid4())
            created_version = True

        new_proto = _set_qualifier_params_in_proto(
            base_proto,
            node1_updates=node1_updates,
            node2_updates=node2_updates,
        )
        new_body = compress_version_body(new_proto)
        if created_version:
            _insert_lm_version_from_body(cursor, body=new_body, version_id=version_id, version_table_id=str(ver_table_id))
            session.steps.append("create_qualifier_grade_version")
            if created_version_table:
                session.steps.append("create_qualifier_grade_version_table")
        else:
            cursor.execute(
                '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
                   WHERE "ListMgt::LmVersion_id" = ?''',
                (new_body, version_id),
            )
            session.steps.append("update_qualifier_grade_version")

        state = read_color_grade(cursor, clip_id=clip_id, clip_name=item_ref.name)
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "created_version_table": created_version_table,
            "created_version": created_version,
            "requested": requested,
            "readback": state.to_dict(),
            "qualifier_readback": _qualifier_readback(state),
        }

    def verifier(_fresh_conn: Any, mutation_result: Any, session: DiskDbMutationSession) -> dict[str, Any]:
        clip_id = mutation_result.get("clip_id") if isinstance(mutation_result, dict) else None
        clip_label = str((mutation_result or {}).get("clip") or clip_name or "")
        connection = sqlite3.connect(session.project_db_path)
        connection.row_factory = sqlite3.Row
        try:
            state = read_color_grade(connection.cursor(), clip_id=str(clip_id), clip_name=clip_label)
        finally:
            connection.close()
        params = {param.key: param for param in state.params}
        expected = {**node1_updates, **node2_updates}
        mismatches: list[dict[str, Any]] = []
        for key, value in expected.items():
            actual = params.get(key).value if params.get(key) else None
            if actual is None or not isinstance(actual, float) or abs(float(actual) - float(value)) > 0.001:
                mismatches.append(
                    {
                        "key": f"0x{key:08X}",
                        "name": _qualifier_hsl_param_name(key),
                        "expected": value,
                        "actual": actual,
                    }
                )
        if params.get(PARAM_QUAL_HSL_TOOL) is None or params.get(PARAM_QUAL_HSL_TOOL).value != QUALIFIER_HSL_TOOL_VALUE:
            mismatches.append(
                {
                    "key": f"0x{PARAM_QUAL_HSL_TOOL:08X}",
                    "name": _qualifier_hsl_param_name(PARAM_QUAL_HSL_TOOL),
                    "expected": QUALIFIER_HSL_TOOL_VALUE,
                    "actual": None,
                }
            )
        if params.get(PARAM_QUAL_MODE) is None or params.get(PARAM_QUAL_MODE).value != QUALIFIER_MODE_HSL_VALUE:
            mismatches.append(
                {
                    "key": f"0x{PARAM_QUAL_MODE:08X}",
                    "name": _qualifier_hsl_param_name(PARAM_QUAL_MODE),
                    "expected": QUALIFIER_MODE_HSL_VALUE,
                    "actual": None,
                }
            )
        if mismatches:
            raise APICallFailed(
                "Color Page Qualifier matte refinement DB mutation did not verify after project reload.",
                details={
                    "clip": clip_label,
                    "mismatches": mismatches,
                    "project_db_path": session.project_db_path,
                    "readback": state.to_dict(),
                },
                recoverability="manual",
            )
        return {
            "status": "db_readback_verified",
            "clip": clip_label,
            "qualifier": _qualifier_readback(state),
            "render_proof_status": "not_performed",
            "render_proof_required": True,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page qualifier matte refinement db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    result["db_session_route"] = result.get("route")
    result["route"] = "db_workaround_color_page_qualifier_matte_refine"
    result["verified_route"] = "native_color_page_hsl_qualifier_db_readback"
    return result


def write_qualifier_matte_refinement(
    conn: Any,
    *,
    clip_name: str | None = None,
    hue: tuple[float, float, float, float] | str | None = None,
    saturation: tuple[float, float, float, float] | str | None = None,
    luma: tuple[float, float, float, float] | str | None = None,
    blur_radius: float | None = None,
    node_index: int | None = None,
    softness: float | None = None,
    hue_softness: float | None = None,
    saturation_softness: float | None = None,
    luma_softness: float | None = None,
    blur: float | None = None,
    clean_black: float | None = None,
    clean_white: float | None = None,
) -> dict[str, Any]:
    legacy_request = (
        node_index is not None
        or softness is not None
        or hue_softness is not None
        or saturation_softness is not None
        or luma_softness is not None
        or blur is not None
        or clean_black is not None
        or clean_white is not None
        or isinstance(hue, str)
        or isinstance(saturation, str)
        or isinstance(luma, str)
    )
    if legacy_request:
        from .mutations_hsv_key import write_legacy_qualifier_matte_refinement

        def legacy_range(value: tuple[float, float, float, float] | str | None) -> str | None:
            if value is None or isinstance(value, str):
                return value
            return ",".join(str(part) for part in value)

        return write_legacy_qualifier_matte_refinement(
            conn,
            clip_name=clip_name,
            node_index=1 if node_index is None else int(node_index),
            hue=legacy_range(hue),
            saturation=legacy_range(saturation),
            luma=legacy_range(luma),
            softness=softness,
            hue_softness=hue_softness,
            saturation_softness=saturation_softness,
            luma_softness=luma_softness,
            blur=blur if blur is not None else blur_radius,
            clean_black=clean_black,
            clean_white=clean_white,
        )

    return _write_hsl_qualifier_matte_refinement(
        conn,
        clip_name=clip_name,
        hue=hue,
        saturation=saturation,
        luma=luma,
        blur_radius=blur_radius,
    )


def write_color_warper_pin(
    conn: Any,
    *,
    clip_name: str | None = None,
    point: tuple[float, float],
    target: tuple[float, float],
) -> dict[str, Any]:
    """Write the verified single-pin Color Warper Chroma Warp payload."""
    point = _validate_warper_coord_pair(point, label="point")
    target = _validate_warper_coord_pair(target, label="target")
    expected_pin = _build_color_warper_pin_value(point=point, target=target)

    from ..db_timeline_selection import resolve_video_group

    item_ref = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None

    def writer(connection: Any, cursor: sqlite3.Cursor, session: DiskDbMutationSession) -> dict[str, Any]:
        row = find_ti_item_row(cursor, item=item_ref, db_type="Sm2TiVideoClip", timeline_name=timeline_name)
        clip_id = row["Sm2TiItem_id"]
        ver_table_id = row["pLmVerTable"]
        ver = None
        if ver_table_id:
            ver = cursor.execute(
                '''SELECT v."ListMgt::LmVersion_id", v.Body
                   FROM "ListMgt::LmVersion" v
                   JOIN "ListMgt::LmVersion_ListMgt::LmVersionTable" rel
                     ON rel.DbAssociate = v."ListMgt::LmVersion_id"
                   WHERE rel.DbOwner = ? AND v.HasCorrection = 1
                   ORDER BY v.rowid DESC LIMIT 1''',
                (ver_table_id,),
            ).fetchone()

        created_version_table = False
        created_version = False
        if ver and ver["Body"]:
            base_proto = decompress_version_body(ver["Body"])
            version_id = ver["ListMgt::LmVersion_id"]
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
            if not ver_table_id:
                ver_table_id = _create_lm_version_table_for_item(
                    cursor,
                    item_id=str(clip_id),
                    fields_blob=bytes.fromhex(_VERSION_TABLE_FIELDS_BLOB_HEX),
                )
                created_version_table = True
            version_id = str(uuid.uuid4())
            created_version = True

        new_proto = _inject_color_warper_pin_into_proto(base_proto, point=point, target=target)
        new_body = compress_version_body(new_proto)
        if created_version:
            _insert_lm_version_from_body(cursor, body=new_body, version_id=version_id, version_table_id=str(ver_table_id))
            session.steps.append("create_warper_grade_version")
            if created_version_table:
                session.steps.append("create_warper_grade_version_table")
        else:
            cursor.execute(
                '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
                   WHERE "ListMgt::LmVersion_id" = ?''',
                (new_body, version_id),
            )
            session.steps.append("update_warper_grade_version")

        state = read_color_grade(cursor, clip_id=clip_id, clip_name=item_ref.name)
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "created_version_table": created_version_table,
            "created_version": created_version,
            "point": {"x": point[0], "y": point[1]},
            "target": {"x": target[0], "y": target[1]},
            "readback": state.to_dict(),
            "warper_readback": _color_warper_readback(state),
        }

    def verifier(_fresh_conn: Any, mutation_result: Any, session: DiskDbMutationSession) -> dict[str, Any]:
        clip_id = mutation_result.get("clip_id") if isinstance(mutation_result, dict) else None
        clip_label = str((mutation_result or {}).get("clip") or clip_name or "")
        connection = sqlite3.connect(session.project_db_path)
        connection.row_factory = sqlite3.Row
        try:
            state = read_color_grade(connection.cursor(), clip_id=str(clip_id), clip_name=clip_label)
        finally:
            connection.close()
        readback = _color_warper_readback(state)
        expected_b64 = base64.b64encode(expected_pin).decode("ascii")
        if (
            readback["mode"] != COLOR_WARPER_CHROMA_WARP_MODE
            or readback["tool"] != COLOR_WARPER_PIN_TOOL
            or readback["pin_payload_b64"] != expected_b64
        ):
            raise APICallFailed(
                "Color Warper DB mutation did not verify after project reload.",
                details={
                    "clip": clip_label,
                    "expected_pin_payload_b64": expected_b64,
                    "readback": readback,
                },
                recoverability="manual",
            )
        return {
            "status": "db_readback_verified",
            "clip": clip_label,
            "warper": readback,
            "render_proof_status": "not_performed",
            "render_proof_required": True,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page warper db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    result["db_session_route"] = result.get("route")
    result["route"] = "db_workaround_color_page_warper_single_pin"
    result["verified_route"] = "native_color_page_warper_single_pin_db_readback"
    return result


def _validate_hdr_zone_value(axis: str, value: float) -> None:
    if value != value or value in (float("inf"), float("-inf")):
        raise ValidationError(
            "Color Page HDR zone value must be a finite number.",
            details={"axis": axis, "value": value},
            recoverability="not_applicable",
        )
    if value < -4.0 or value > 4.0:
        raise ValidationError(
            "Color Page HDR zone value must be between -4.0 and 4.0.",
            details={"axis": axis, "value": value, "minimum": -4.0, "maximum": 4.0},
            recoverability="not_applicable",
        )


def write_hdr_zone(
    conn: Any,
    *,
    clip_name: str | None = None,
    zone: str,
    x: float | None = None,
    y: float | None = None,
    z: float | None = None,
    sat: float | None = None,
    range_value: float | None = None,
    falloff: float | None = None,
) -> dict[str, Any]:
    """Set native Color Page HDR zone values through verified DB payloads."""
    normalized_zone = str(zone or "").strip().lower()
    if normalized_zone in HDR_ZONE_PARAM_KEYS:
        if sat is not None or range_value is not None or falloff is not None:
            raise ValidationError(
                "Dark/Shadow/Light HDR zone fixtures expose X/Y/Z only.",
                details={"zone": normalized_zone, "unsupported": ["sat", "range", "falloff"]},
                recoverability="not_applicable",
            )
        values = {"x": x, "y": y, "z": z}
        specified = {axis: float(value) for axis, value in values.items() if value is not None}
        if not specified:
            raise ValidationError(
                "No HDR zone vector values specified.",
                details={"zone": normalized_zone, "required": ["x", "y", "z"]},
                recoverability="not_applicable",
            )
        for axis, value in specified.items():
            _validate_hdr_zone_value(axis, value)

        kwargs: dict[str, float] = {}
        for axis, value in specified.items():
            kwargs[f"hdr_{normalized_zone}_{axis}"] = value
        result = write_color_grade(conn, clip_name=clip_name, **kwargs)
        if isinstance(result, dict):
            result["db_session_route"] = result.get("route")
            result["route"] = "db_workaround_color_page_hdr_zone"
            zone_payload = {
                "zone": normalized_zone,
                "values": specified,
            }
            result["hdr_zone_written"] = zone_payload
            if isinstance(result.get("mutation_result"), dict):
                result["mutation_result"]["hdr_zone_written"] = zone_payload
            if isinstance(result.get("verification"), dict):
                result["verification"]["hdr_zone"] = zone_payload
        return result

    if normalized_zone not in HDR_DETAIL_ZONE_NAMES:
        raise ValidationError(
            "Color Page HDR zone must be one of: dark, shadow, light, highlight, specular.",
            details={"zone": zone, "supported_zones": sorted([*HDR_ZONE_PARAM_KEYS, *HDR_DETAIL_ZONE_NAMES])},
            recoverability="not_applicable",
        )
    if z is not None:
        raise ValidationError(
            "Highlight/Specular HDR detail controls expose X/Y vector and Sat controls, not Z.",
            details={"zone": normalized_zone, "unsupported_axis": "z"},
            recoverability="not_applicable",
        )
    if range_value is not None or falloff is not None:
        raise ValidationError(
            "Highlight/Specular --range/--falloff are not render-verified. Live frame-export "
            "probes showed range/falloff DB writes read back without changing rendered output; "
            "the verified controls are --x/--y/--sat through the main-section HDR palette payload.",
            details={"zone": normalized_zone, "unsupported": ["range", "falloff"], "supported": ["x", "y", "sat"]},
            recoverability="not_applicable",
        )
    specified = {
        axis: float(value)
        for axis, value in {"x": x, "y": y, "sat": sat}.items()
        if value is not None
    }
    if not specified:
        raise ValidationError(
            "Highlight/Specular hdr-zone-set requires at least one supported HDR detail value.",
            details={"zone": normalized_zone, "required": ["x", "y", "sat"]},
            recoverability="not_applicable",
        )
    for axis, value in specified.items():
        _validate_hdr_zone_value(axis, value)

    zone_label = HDR_PALETTE_ZONE_LABELS[normalized_zone]

    from ..db_timeline_selection import resolve_video_group

    item_ref = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None

    def _active_version(cursor: sqlite3.Cursor, ver_table_id: str | None) -> sqlite3.Row | None:
        if not ver_table_id:
            return None
        return _select_active_grade_version(cursor, str(ver_table_id))

    def writer(connection: Any, cursor: sqlite3.Cursor, session: DiskDbMutationSession) -> dict[str, Any]:
        row = find_ti_item_row(
            cursor,
            item=item_ref,
            db_type="Sm2TiVideoClip",
            timeline_name=timeline_name,
        )
        clip_id = row["Sm2TiItem_id"]
        ver = _active_version(cursor, row["pLmVerTable"])
        if not ver or not ver["Body"]:
            raise APICallFailed(
                "Color Page HDR Highlight/Specular route requires an existing grade version.",
                details={"clip": item_ref.name, "zone": normalized_zone},
                recoverability="manual",
            )

        base_proto = decompress_version_body(ver["Body"])
        new_proto, _seeded, _global_expected = _inject_hdr_global_into_proto(
            base_proto,
            exposure=None,
            saturation=None,
            zone_updates={zone_label: specified},
        )
        cursor.execute(
            '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
               WHERE "ListMgt::LmVersion_id" = ?''',
            (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
        )
        session.steps.append("set_color_page_hdr_palette_zone")
        state = read_color_grade(cursor, clip_id=clip_id, clip_name=item_ref.name)
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "version_id": ver["ListMgt::LmVersion_id"],
            "hdr_zone_written": {"zone": normalized_zone, "values": specified},
            "readback": {"hdr_palette": _hdr_palette_zones_readback_from_params(state.params)},
        }

    def verifier(_fresh_conn: Any, mutation_result: Any, session: DiskDbMutationSession) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Page HDR Highlight/Specular mutation did not return a mutation payload for verification.",
                details={"mutation_result": mutation_result},
            )
        clip_id = mutation_result.get("clip_id")
        version_id = mutation_result.get("version_id")
        connection = sqlite3.connect(session.project_db_path)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                'SELECT Body FROM "ListMgt::LmVersion" WHERE "ListMgt::LmVersion_id" = ?',
                (version_id,),
            ).fetchone()
            if not row or not row["Body"]:
                raise APICallFailed(
                    "Color Page HDR Highlight/Specular verification could not read the active grade body.",
                    details={"clip_id": clip_id, "version_id": version_id},
                )
            params = _parse_params_from_proto(decompress_version_body(row["Body"]))
        finally:
            connection.close()

        zones = _hdr_palette_zones_readback_from_params(params)
        zone_values = zones.get(zone_label)
        mismatches: list[dict[str, Any]] = []
        for axis, expected in specified.items():
            actual = None if not isinstance(zone_values, dict) else zone_values.get(axis)
            if actual is None or abs(float(actual) - expected) > 0.001:
                mismatches.append({"axis": axis, "expected": expected, "actual": actual})
        if mismatches:
            raise APICallFailed(
                "Color Page HDR Highlight/Specular DB write did not verify after project reload.",
                details={
                    "clip_id": clip_id,
                    "zone": normalized_zone,
                    "mismatches": mismatches,
                    "readback": zones,
                    "project_db_path": session.project_db_path,
                },
                recoverability="manual",
            )
        return {
            "status": "verified",
            "zone": normalized_zone,
            "zone_label": zone_label,
            "values": specified,
            "readback": zones,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page HDR Highlight/Specular db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    if isinstance(result, dict):
        result["db_session_route"] = result.get("route")
        result["route"] = "db_workaround_color_page_hdr_detail_zone"
        result["hdr_zone_written"] = {"zone": normalized_zone, "values": specified}
    return result


def write_hdr_detail(
    conn: Any,
    *,
    clip_name: str | None = None,
    zone: str,
    x: float | None = None,
    y: float | None = None,
    sat: float | None = None,
    range_value: float | None = None,
    falloff: float | None = None,
) -> dict[str, Any]:
    """Write verified native HDR Highlight/Specular detail controls."""
    normalized_zone = str(zone or "").strip().lower()
    if normalized_zone not in HDR_DETAIL_ZONE_NAMES:
        raise ValidationError(
            "Color Page HDR detail zone must be one of: highlight, specular.",
            details={"zone": zone, "supported_zones": sorted(HDR_DETAIL_ZONE_NAMES)},
            recoverability="not_applicable",
        )
    specified_values = {
        axis: float(value)
        for axis, value in {"x": x, "y": y, "sat": sat}.items()
        if value is not None
    }
    specified_ranges = {
        axis: float(value)
        for axis, value in {"range": range_value, "falloff": falloff}.items()
        if value is not None
    }
    if not specified_values and not specified_ranges:
        raise ValidationError(
            "Color Page HDR detail controls require at least one value.",
            details={"zone": normalized_zone, "required": ["x", "y", "sat", "range", "falloff"]},
            recoverability="not_applicable",
        )
    for axis, value in {**specified_values, **specified_ranges}.items():
        _validate_hdr_zone_value(axis, value)
    if not specified_ranges:
        result = write_hdr_zone(
            conn,
            clip_name=clip_name,
            zone=normalized_zone,
            x=x,
            y=y,
            z=None,
            sat=sat,
            range_value=None,
            falloff=None,
        )
        if isinstance(result, dict):
            result["base_route"] = result.get("route")
            result["route"] = "db_workaround_color_page_hdr_detail_set"
            if "hdr_zone_written" in result:
                result["hdr_detail_written"] = result["hdr_zone_written"]
            if "hdr_zone_readback" in result:
                result["hdr_detail_readback"] = result["hdr_zone_readback"]
        return result

    from ..db_timeline_selection import resolve_video_group

    item_ref = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None

    def _active_version(cursor: sqlite3.Cursor, ver_table_id: str | None) -> sqlite3.Row | None:
        if not ver_table_id:
            return None
        return cursor.execute(
            '''SELECT v."ListMgt::LmVersion_id", v.Body
               FROM "ListMgt::LmVersion" v
               JOIN "ListMgt::LmVersion_ListMgt::LmVersionTable" rel
                 ON rel.DbAssociate = v."ListMgt::LmVersion_id"
               WHERE rel.DbOwner = ? AND v.HasCorrection = 1
               ORDER BY v.rowid DESC LIMIT 1''',
            (ver_table_id,),
        ).fetchone()

    def writer(connection: Any, cursor: sqlite3.Cursor, session: DiskDbMutationSession) -> dict[str, Any]:
        row = find_ti_item_row(
            cursor,
            item=item_ref,
            db_type="Sm2TiVideoClip",
            timeline_name=timeline_name,
        )
        clip_id = row["Sm2TiItem_id"]
        ver = _active_version(cursor, row["pLmVerTable"])
        if not ver or not ver["Body"]:
            raise APICallFailed(
                "Color Page HDR detail route requires an existing grade version.",
                details={"clip": item_ref.name, "zone": normalized_zone},
                recoverability="manual",
            )

        base_proto = decompress_version_body(ver["Body"])
        new_proto, write_payload = _inject_hdr_detail_vector_into_proto(
            base_proto,
            zone=normalized_zone,
            x=x,
            y=y,
            sat=sat,
            range_value=range_value,
            falloff=falloff,
        )
        cursor.execute(
            '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
               WHERE "ListMgt::LmVersion_id" = ?''',
            (compress_version_body(new_proto), ver["ListMgt::LmVersion_id"]),
        )
        session.steps.append("set_color_page_hdr_detail_payload")
        readback = _parse_hdr_detail_readback(new_proto)
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "version_id": ver["ListMgt::LmVersion_id"],
            "hdr_detail_written": write_payload,
            "readback": {"hdr_detail": readback},
        }

    def verifier(_fresh_conn: Any, mutation_result: Any, session: DiskDbMutationSession) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Page HDR detail mutation did not return a mutation payload for verification.",
                details={"mutation_result": mutation_result},
            )
        clip_id = mutation_result.get("clip_id")
        version_id = mutation_result.get("version_id")
        connection = sqlite3.connect(session.project_db_path)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                'SELECT Body FROM "ListMgt::LmVersion" WHERE "ListMgt::LmVersion_id" = ?',
                (version_id,),
            ).fetchone()
            if not row or not row["Body"]:
                raise APICallFailed(
                    "Color Page HDR detail verification could not read the active grade body.",
                    details={"clip_id": clip_id, "version_id": version_id},
                )
            readback = _parse_hdr_detail_readback(decompress_version_body(row["Body"]))
        finally:
            connection.close()

        zone_values = readback.get("zones", {}).get(normalized_zone, {})
        range_values = readback.get("ranges", {}).get(normalized_zone, {})
        mismatches: list[dict[str, Any]] = []
        for axis, expected in specified_values.items():
            actual = zone_values.get(axis)
            if actual is None or abs(float(actual) - expected) > 0.001:
                mismatches.append({"axis": axis, "expected": expected, "actual": actual})
        for axis, expected in specified_ranges.items():
            actual = range_values.get(axis)
            if actual is None or abs(float(actual) - expected) > 0.001:
                mismatches.append({"axis": axis, "expected": expected, "actual": actual})
        if mismatches:
            raise APICallFailed(
                "Color Page HDR detail DB write did not verify after project reload.",
                details={
                    "clip_id": clip_id,
                    "zone": normalized_zone,
                    "mismatches": mismatches,
                    "readback": readback,
                    "project_db_path": session.project_db_path,
                },
                recoverability="manual",
            )
        return {
            "status": "verified",
            "zone": normalized_zone,
            "values": specified_values,
            "range_values": specified_ranges,
            "readback": readback,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page HDR detail db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    if isinstance(result, dict):
        result["db_session_route"] = result.get("route")
        result["route"] = "db_workaround_color_page_hdr_detail_set"
        result["hdr_detail_written"] = {
            "zone": normalized_zone,
            "values": specified_values,
            "range_values": specified_ranges,
        }
        if isinstance(result.get("verification"), dict):
            result["hdr_detail_readback"] = result["verification"].get("readback")
    return result


def write_color_grade(
    conn: Any,
    *,
    clip_name: str | None = None,
    track: int | None = None,
    at: str | None = None,
    node_index: int = 1,
    lift_r: float | None = None,
    lift_g: float | None = None,
    lift_b: float | None = None,
    gamma_r: float | None = None,
    gamma_g: float | None = None,
    gamma_b: float | None = None,
    gain_r: float | None = None,
    gain_g: float | None = None,
    gain_b: float | None = None,
    saturation: float | None = None,
    offset_r: float | None = None,
    offset_g: float | None = None,
    offset_b: float | None = None,
    hue: float | None = None,
    contrast: float | None = None,
    pivot: float | None = None,
    temperature: float | None = None,
    tint: float | None = None,
    lum_mix: float | None = None,
    highlights: float | None = None,
    shadows: float | None = None,
    color_boost: float | None = None,
    mid_detail: float | None = None,
    curve_high_y: float | None = None,
    curve_high_r: float | None = None,
    curve_high_g: float | None = None,
    curve_high_b: float | None = None,
    hdr_dark_x: float | None = None,
    hdr_dark_y: float | None = None,
    hdr_dark_z: float | None = None,
    hdr_shadow_x: float | None = None,
    hdr_shadow_y: float | None = None,
    hdr_shadow_z: float | None = None,
    hdr_light_x: float | None = None,
    hdr_light_y: float | None = None,
    hdr_light_z: float | None = None,
    delete_param_keys: set[int] | None = None,
) -> dict[str, Any]:
    """Write color grade parameters to the DB via the disk DB mutation session."""
    target_node_index = int(node_index)
    if target_node_index < 1:
        raise ValidationError(
            "Color Page node index must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )

    # Build the params dict from provided values
    params: dict[int, float] = {}
    for param_id, value in (
        (PARAM_LIFT_R, lift_r),
        (PARAM_LIFT_G, lift_g),
        (PARAM_LIFT_B, lift_b),
        (PARAM_GAMMA_R, gamma_r),
        (PARAM_GAMMA_G, gamma_g),
        (PARAM_GAMMA_B, gamma_b),
        (PARAM_GAIN_R, gain_r),
        (PARAM_GAIN_G, gain_g),
        (PARAM_GAIN_B, gain_b),
        (PARAM_SATURATION, saturation),
        (PARAM_OFFSET_R, offset_r),
        (PARAM_OFFSET_G, offset_g),
        (PARAM_OFFSET_B, offset_b),
        (PARAM_HUE, hue),
        (PARAM_CONTRAST, contrast),
        (PARAM_PIVOT, pivot),
        (PARAM_TEMPERATURE, temperature),
        (PARAM_TINT, tint),
        (PARAM_LUM_MIX, lum_mix),
        (PARAM_HIGHLIGHTS, highlights),
        (PARAM_SHADOWS, shadows),
        (PARAM_COLOR_BOOST, color_boost),
        (PARAM_MID_DETAIL, mid_detail),
        (PARAM_CURVE_HIGH_Y, curve_high_y),
        (PARAM_CURVE_HIGH_R, curve_high_r),
        (PARAM_CURVE_HIGH_G, curve_high_g),
        (PARAM_CURVE_HIGH_B, curve_high_b),
        (PARAM_HDR_DARK_1, hdr_dark_x),
        (PARAM_HDR_DARK_2, hdr_dark_y),
        (PARAM_HDR_DARK_3, hdr_dark_z),
        (PARAM_HDR_SHADOW_1, hdr_shadow_x),
        (PARAM_HDR_SHADOW_2, hdr_shadow_y),
        (PARAM_HDR_SHADOW_3, hdr_shadow_z),
        (PARAM_HDR_LIGHT_1, hdr_light_x),
        (PARAM_HDR_LIGHT_2, hdr_light_y),
        (PARAM_HDR_LIGHT_3, hdr_light_z),
    ):
        if value is not None:
            params[param_id] = value

    delete_keys = set(delete_param_keys or set())

    if not params and not delete_keys:
        raise ValidationError("No color grade parameters specified.")

    from ..db_timeline_selection import resolve_video_group

    selector_kwargs: dict[str, Any] = {"clip_name": clip_name}
    if track is not None:
        selector_kwargs["track"] = track
    if at is not None:
        selector_kwargs["at"] = at
    item_ref = resolve_video_group(conn, **selector_kwargs)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None
    if (track is not None or at is not None) and not str(timeline_name or "").strip():
        raise ValidationError(
            "Color Page primary-set with an exact track/time selector requires an exact active timeline name before Project.db mutation.",
            details={
                "clip_name": clip_name,
                "track": item_ref.track_index,
                "at": at,
            },
        )

    def _expected_param_payload() -> dict[str, float]:
        return {PARAM_NAMES.get(key, f"0x{key:08X}"): value for key, value in params.items()}

    def _deleted_param_payload() -> list[str]:
        return [PARAM_NAMES.get(key, f"0x{key:08X}") for key in sorted(delete_keys)]

    def _verify_params_readback(
        *,
        state: ColorGradeState,
        expected: dict[int, float],
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
        for key, expected_value in expected.items():
            actual_value = actual_by_key.get(key)
            if actual_value is None or abs(actual_value - expected_value) > tolerance:
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
        # Find the Sm2TiItem row
        row = find_ti_item_row(
            cursor,
            item=item_ref,
            db_type="Sm2TiVideoClip",
            timeline_name=timeline_name,
            require_timeline_name=track is not None or at is not None,
        )

        clip_id = row["Sm2TiItem_id"]
        ver_table_id = row["pLmVerTable"]

        # Get or create the graded version
        ver = _select_active_grade_version(cursor, str(ver_table_id)) if ver_table_id else None

        readback_node_index = target_node_index
        if ver and ver["Body"]:
            # Update existing graded version
            base_proto = decompress_version_body(ver["Body"])
            new_proto = _inject_params_into_proto(
                base_proto,
                params,
                node_index=target_node_index,
                delete_keys=delete_keys,
            )
            readback_node_index = _param_readback_node_index_for_color_node_index(
                new_proto,
                target_node_index,
            )
            new_body = compress_version_body(new_proto)

            cursor.execute(
                '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
                   WHERE "ListMgt::LmVersion_id" = ?''',
                (new_body, ver["ListMgt::LmVersion_id"]),
            )
            session.steps.append("update_grade_version")
        else:
            if delete_keys and not params:
                session.steps.append("delete_params_noop_no_grade")
                state = read_color_grade(cursor, clip_id=clip_id, clip_name=item_ref.name)
                return {
                    "clip": item_ref.name,
                    "clip_id": clip_id,
                    "created_version_table": False,
                    "created_version": False,
                    "changed": False,
                    "params_written": _expected_param_payload(),
                    "params_deleted": _deleted_param_payload(),
                    "readback": state.to_dict(),
                }

            # Need to create new version – get baseline body first
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
                # DaVinci Resolve-authored baseline version body (GUI fixture) so first
                # grades match native clip-version shape.
                base_proto = decompress_version_body(bytes.fromhex(_BASELINE_VERSION_BODY_HEX))

            new_proto = _inject_params_into_proto(
                base_proto,
                params,
                node_index=target_node_index,
                delete_keys=delete_keys,
            )
            readback_node_index = _param_readback_node_index_for_color_node_index(
                new_proto,
                target_node_index,
            )
            new_body = compress_version_body(new_proto)

            created_version_table = False
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
                body=new_body,
                version_id=version_id,
                version_table_id=str(ver_table_id),
            )
            session.steps.append("create_grade_version")
            if created_version_table:
                session.steps.append("create_grade_version_table")

        # Read back the grade to verify
        state = read_color_grade(cursor, clip_id=clip_id, clip_name=item_ref.name)

        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "created_version_table": not bool(row["pLmVerTable"]),
            "created_version": not bool(ver and ver["Body"]),
            "node_index": target_node_index,
            "readback_node_index": readback_node_index,
            "params_written": _expected_param_payload(),
            "params_deleted": _deleted_param_payload(),
            "readback": state.to_dict(),
        }

    def verifier(
        _fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color page DB mutation did not return a mutation payload for verification.",
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
                    "Could not resolve the written clip during Color page DB verification.",
                    details={"clip": clip_label},
                )

            state = read_color_grade(cursor, clip_id=str(clip_id), clip_name=clip_label)
        finally:
            connection.close()

        readback_node_index = int(mutation_result.get("readback_node_index") or target_node_index)
        mismatches = _verify_params_readback(
            state=state,
            expected=params,
            readback_node_index=readback_node_index,
        )
        actual_by_key = {
            param.key: param.value
            for param in state.params
            if int(param.node_index) == readback_node_index
        }
        delete_mismatches = [
            {
                "key": f"0x{key:08X}",
                "name": PARAM_NAMES.get(key, f"0x{key:08X}"),
                "actual": actual_by_key.get(key),
            }
            for key in sorted(delete_keys)
            if key in actual_by_key
        ]
        if mismatches or delete_mismatches:
            raise APICallFailed(
                "Color page DB mutation did not verify after project reload.",
                details={
                    "clip": clip_label,
                    "project_db_path": session.project_db_path,
                    "params_written": _expected_param_payload(),
                    "params_deleted": _deleted_param_payload(),
                    "mismatches": mismatches,
                    "delete_mismatches": delete_mismatches,
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
            "params_deleted": _deleted_param_payload(),
            "render_proof_status": "not_performed",
            "render_proof_required": True,
            "note": (
                "Project.db readback matched after project reload. This does not prove that "
                "DaVinci Resolve applied the grade in rendered pixels."
            ),
        }

    return execute_sqlite_disk_db_mutation(
        conn,
        context="color page db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )


def write_hsv_node_saturation(
    conn: Any,
    *,
    clip_name: str | None = None,
    gamma_r: float | None = None,
    gamma_g: float | None = None,
    gamma_b: float | None = None,
    gamma_master: float | None = None,
    gain_r: float | None = None,
    gain_g: float | None = None,
    gain_b: float | None = None,
    gain_master: float | None = None,
) -> dict[str, Any]:
    """Apply the verified tutorial HSV-node saturation workflow via Project.db."""

    params = _hsv_node_expected_params(
        gamma_r=gamma_r,
        gamma_g=gamma_g,
        gamma_b=gamma_b,
        gamma_master=gamma_master,
        gain_r=gain_r,
        gain_g=gain_g,
        gain_b=gain_b,
        gain_master=gain_master,
    )

    from ..db_timeline_selection import resolve_video_group

    item_ref = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None

    def _expected_param_payload() -> dict[str, float]:
        return {PARAM_NAMES.get(key, f"0x{key:08X}"): value for key, value in params.items()}

    def _verify_params_readback(state: ColorGradeState, tolerance: float = 0.001) -> list[dict[str, Any]]:
        actual_by_key = {param.key: param.value for param in state.params}
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
        if ver and ver["Body"]:
            base_proto = decompress_version_body(ver["Body"])
            new_proto = _inject_hsv_node_into_proto(base_proto, params)
            new_body = compress_version_body(new_proto)
            cursor.execute(
                '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
                   WHERE "ListMgt::LmVersion_id" = ?''',
                (new_body, ver["ListMgt::LmVersion_id"]),
            )
            session.steps.append("update_hsv_node_grade_version")
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
                base_proto = bytes.fromhex(
                    "0a2a10011a2208800f10b8081d0000803f"
                    "20800f28b808350000803f38800f40b808"
                    "48ffffffff0f60b2a67e100120b2a67e"
                )
            new_proto = _inject_hsv_node_into_proto(base_proto, params)
            new_body = compress_version_body(new_proto)
            if not ver_table_id:
                ver_table_id = _create_lm_version_table_for_item(
                    cursor,
                    item_id=str(clip_id),
                    fields_blob=None,
                )
                created_version_table = True
            version_id = str(uuid.uuid4())
            _insert_lm_version_from_body(
                cursor,
                body=new_body,
                version_id=version_id,
                version_table_id=str(ver_table_id),
            )
            created_version = True
            session.steps.append("create_hsv_node_grade_version")
            if created_version_table:
                session.steps.append("create_grade_version_table")

        state = read_color_grade(cursor, clip_id=clip_id, clip_name=item_ref.name)
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "created_version_table": created_version_table,
            "created_version": created_version,
            "params_written": _expected_param_payload(),
            "hsv_node": _hsv_node_graft_readback(new_proto),
            "readback": state.to_dict(),
        }

    def verifier(
        _fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Page HSV node DB mutation did not return a mutation payload for verification.",
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
                    "Could not resolve the written clip during Color Page HSV node verification.",
                    details={"clip": clip_label},
                )
            state = read_color_grade(cursor, clip_id=str(clip_id), clip_name=clip_label)
            body_row = _select_active_grade_version_for_clip(cursor, str(clip_id))
            proto = decompress_version_body(body_row["Body"]) if body_row and body_row["Body"] else b""
            hsv_readback = _hsv_node_graft_readback(proto)
        finally:
            connection.close()

        mismatches = _verify_params_readback(state)
        if mismatches or not hsv_readback["root_field3_matches_fixture"] or not hsv_readback["field10_matches_fixture"]:
            raise APICallFailed(
                "Color Page HSV node DB mutation did not verify after project reload.",
                details={
                    "clip": clip_label,
                    "project_db_path": session.project_db_path,
                    "params_written": _expected_param_payload(),
                    "mismatches": mismatches,
                    "hsv_node": hsv_readback,
                    "readback": state.to_dict(),
                },
                recoverability="manual",
            )

        return {
            "status": "verified",
            "clip": clip_label,
            "params_verified": _expected_param_payload(),
            "hsv_node": hsv_readback,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page hsv node db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    result["db_session_route"] = result.get("route")
    result["route"] = "db_workaround_color_page_hsv_node_set"
    return result


__all__ = (
    'PARAM_COLOR_WARPER_MODE',
    'PARAM_COLOR_WARPER_TOOL',
    'PARAM_COLOR_WARPER_PIN',
    'COLOR_WARPER_CHROMA_WARP_MODE',
    'COLOR_WARPER_PIN_TOOL',
    '_validate_hdr_zone_value',
    '_validate_warper_coord_pair',
    '_validate_qualifier_ui_value',
    '_build_color_warper_pin_value',
    'write_qualifier_matte_refinement',
    'write_color_warper_pin',
    'write_hdr_zone',
    'write_hdr_detail',
    'write_color_grade',
    'write_hsv_node_saturation',
)
