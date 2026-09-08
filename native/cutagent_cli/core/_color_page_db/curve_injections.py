"""Curves helpers for Color Page DB operations."""

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


def _inject_curve_points_into_proto(
    base_proto: bytes,
    channel_points: dict[str, list[CurvePoint]],
) -> bytes:
    field9 = _extract_submessage(base_proto, [1, 7, 9])
    if field9 is None:
        raise APICallFailed(
            "Color Page Custom Curves DB route requires an existing Color Page grade body.",
            details={"path": "1.7.9"},
            recoverability="manual",
        )
    nodes = _split_grade_node_section(field9)[1]
    if not nodes:
        raise APICallFailed(
            "Color Page Custom Curves DB route could not find a grade node.",
            recoverability="manual",
        )
    node = nodes[0]
    f6 = _get_submessage(node, 6)
    f2 = _get_submessage(f6, 2) if f6 is not None else None
    if f2 is None:
        raise APICallFailed(
            "Color Page Custom Curves DB route could not find the grade param section.",
            details={"path": "1.7.9.1.6.2"},
            recoverability="manual",
        )

    raw_entries: dict[int, bytes] = {
        key: _build_varint_param_entry(key, value)
        for key, value in CURVE_MODE_PARAM_KEYS.items()
    }
    for channel, points in channel_points.items():
        key = CURVE_CHANNEL_PARAMS[channel]
        raw_entries[key] = _build_bytes_param_entry(
            key,
            _curve_payload_with_guards(points),
            inner_field=8,
        )
    new_f2 = _rebuild_param_section_raw(f2, raw_entries)
    new_node = _replace_submessage_at_path(node, [6, 2], new_f2)
    new_field9 = _replace_grade_node(field9, 1, new_node)
    return _replace_submessage_at_path(base_proto, [1, 7, 9], new_field9)


def _inject_hue_vs_hue_curve_into_proto(
    base_proto: bytes,
    *,
    input_hue: float,
    hue_rotate: float,
) -> bytes:
    field9 = _extract_submessage(base_proto, [1, 7, 9])
    if field9 is None:
        raise APICallFailed(
            "Color Page Hue vs Hue DB route requires an existing Color Page grade body.",
            details={"path": "1.7.9"},
            recoverability="manual",
        )
    nodes = _split_grade_node_section(field9)[1]
    if not nodes:
        raise APICallFailed(
            "Color Page Hue vs Hue DB route could not find a grade node.",
            recoverability="manual",
        )
    node = nodes[0]
    f6 = _get_submessage(node, 6)
    f2 = _get_submessage(f6, 2) if f6 is not None else None
    if f2 is None:
        raise APICallFailed(
            "Color Page Hue vs Hue DB route could not find the grade param section.",
            details={"path": "1.7.9.1.6.2"},
            recoverability="manual",
        )

    raw_entries: dict[int, bytes] = {
        PARAM_HUE_CURVE_MODE: _build_varint_param_entry(PARAM_HUE_CURVE_MODE, 0),
        PARAM_HUE_CURVE_VARIANT: _build_varint_param_entry(PARAM_HUE_CURVE_VARIANT, 2),
        PARAM_HUE_VS_HUE_CURVE: _build_bytes_param_entry(
            PARAM_HUE_VS_HUE_CURVE,
            _hue_vs_hue_payload(input_hue, hue_rotate),
            inner_field=8,
        ),
    }
    new_f2 = _rebuild_param_section_raw(f2, raw_entries)
    new_node = _replace_submessage_at_path(node, [6, 2], new_f2)
    new_field9 = _replace_grade_node(field9, 1, new_node)
    return _replace_submessage_at_path(base_proto, [1, 7, 9], new_field9)


def _hue_curve_points_mode_config(mode: str) -> dict[str, Any]:
    normalized_mode = mode.strip().lower().replace("_", "-")
    configs: dict[str, dict[str, Any]] = {
        "hue-vs-hue": {
            "value_key": "hue_rotate",
            "curve_key": PARAM_HUE_VS_HUE_CURVE,
            "readback_key": "hue_vs_hue",
            "route": "db_workaround_color_page_hue_vs_hue_points",
            "step": "update_hue_vs_hue_curve_points",
            "context": "color page hue vs hue points db mutation",
            "label": "Hue vs Hue",
            "entries": {
                PARAM_HUE_CURVE_MODE: _build_varint_param_entry(PARAM_HUE_CURVE_MODE, 0),
                PARAM_HUE_CURVE_VARIANT: _build_varint_param_entry(PARAM_HUE_CURVE_VARIANT, 2),
            },
        },
        "hue-vs-sat": {
            "value_key": "saturation",
            "curve_key": PARAM_HUE_VS_SAT_CURVE,
            "readback_key": "hue_vs_sat",
            "route": "db_workaround_color_page_hue_vs_sat_points",
            "step": "update_hue_vs_sat_curve_points",
            "context": "color page hue vs sat points db mutation",
            "label": "Hue vs Sat",
            "entries": {
                PARAM_HUE_VS_SAT_MODE: _build_varint_param_entry(PARAM_HUE_VS_SAT_MODE, 0),
                PARAM_HUE_CURVE_VARIANT: _build_varint_param_entry(PARAM_HUE_CURVE_VARIANT, 2),
            },
        },
        "hue-vs-lum": {
            "value_key": "lum_gain",
            "curve_key": PARAM_HUE_VS_LUM_CURVE,
            "readback_key": "hue_vs_lum",
            "route": "db_workaround_color_page_hue_vs_lum_points",
            "step": "update_hue_vs_lum_curve_points",
            "context": "color page hue vs lum points db mutation",
            "label": "Hue vs Lum",
            "entries": {
                PARAM_HUE_VS_LUM_MODE: _build_varint_param_entry(PARAM_HUE_VS_LUM_MODE, 0),
                PARAM_HUE_CURVE_VARIANT: _build_varint_param_entry(PARAM_HUE_CURVE_VARIANT, 2),
                PARAM_HUE_VS_LUM_SELECTOR: _build_varint_param_entry(PARAM_HUE_VS_LUM_SELECTOR, 2),
            },
        },
    }
    config = configs.get(normalized_mode)
    if config is None:
        raise ValidationError(
            "Hue curve points mode must be hue-vs-hue, hue-vs-sat, or hue-vs-lum.",
            details={"mode": mode, "supported_modes": sorted(configs)},
            recoverability="not_applicable",
        )
    return config


def _inject_hue_curve_points_into_proto(
    base_proto: bytes,
    *,
    mode: str,
    points: list[dict[str, float]],
) -> bytes:
    config = _hue_curve_points_mode_config(mode)
    label = str(config["label"])
    field9 = _extract_submessage(base_proto, [1, 7, 9])
    if field9 is None:
        raise APICallFailed(
            f"Color Page {label} points DB route requires an existing Color Page grade body.",
            details={"path": "1.7.9"},
            recoverability="manual",
        )
    nodes = _split_grade_node_section(field9)[1]
    if not nodes:
        raise APICallFailed(
            f"Color Page {label} points DB route could not find a grade node.",
            recoverability="manual",
        )
    node = nodes[0]
    f6 = _get_submessage(node, 6)
    f2 = _get_submessage(f6, 2) if f6 is not None else None
    if f2 is None:
        raise APICallFailed(
            f"Color Page {label} points DB route could not find the grade param section.",
            details={"path": "1.7.9.1.6.2"},
            recoverability="manual",
        )

    raw_entries: dict[int, bytes] = dict(config["entries"])
    curve_key = int(config["curve_key"])
    raw_entries[curve_key] = _build_bytes_param_entry(
        curve_key,
        _hue_curve_multi_point_payload(points, value_key=str(config["value_key"])),
        inner_field=8,
    )
    new_f2 = _rebuild_param_section_raw(f2, raw_entries)
    new_node = _replace_submessage_at_path(node, [6, 2], new_f2)
    new_field9 = _replace_grade_node(field9, 1, new_node)
    return _replace_submessage_at_path(base_proto, [1, 7, 9], new_field9)


def _inject_hue_vs_hue_curve_points_into_proto(
    base_proto: bytes,
    *,
    points: list[dict[str, float]],
) -> bytes:
    return _inject_hue_curve_points_into_proto(base_proto, mode="hue-vs-hue", points=points)


def _inject_hue_vs_sat_curve_into_proto(
    base_proto: bytes,
    *,
    input_hue: float,
    saturation: float,
) -> bytes:
    field9 = _extract_submessage(base_proto, [1, 7, 9])
    if field9 is None:
        raise APICallFailed(
            "Color Page Hue vs Sat DB route requires an existing Color Page grade body.",
            details={"path": "1.7.9"},
            recoverability="manual",
        )
    nodes = _split_grade_node_section(field9)[1]
    if not nodes:
        raise APICallFailed(
            "Color Page Hue vs Sat DB route could not find a grade node.",
            recoverability="manual",
        )
    node = nodes[0]
    f6 = _get_submessage(node, 6)
    f2 = _get_submessage(f6, 2) if f6 is not None else None
    if f2 is None:
        raise APICallFailed(
            "Color Page Hue vs Sat DB route could not find the grade param section.",
            details={"path": "1.7.9.1.6.2"},
            recoverability="manual",
        )

    raw_entries: dict[int, bytes] = {
        PARAM_HUE_VS_SAT_MODE: _build_varint_param_entry(PARAM_HUE_VS_SAT_MODE, 0),
        PARAM_HUE_CURVE_VARIANT: _build_varint_param_entry(PARAM_HUE_CURVE_VARIANT, 2),
        PARAM_HUE_VS_SAT_CURVE: _build_bytes_param_entry(
            PARAM_HUE_VS_SAT_CURVE,
            _hue_vs_sat_payload(input_hue, saturation),
            inner_field=8,
        ),
    }
    new_f2 = _rebuild_param_section_raw(f2, raw_entries)
    new_node = _replace_submessage_at_path(node, [6, 2], new_f2)
    new_field9 = _replace_grade_node(field9, 1, new_node)
    return _replace_submessage_at_path(base_proto, [1, 7, 9], new_field9)


def _inject_hue_vs_lum_curve_into_proto(
    base_proto: bytes,
    *,
    input_hue: float,
    lum_gain: float,
) -> bytes:
    field9 = _extract_submessage(base_proto, [1, 7, 9])
    if field9 is None:
        raise APICallFailed(
            "Color Page Hue vs Lum DB route requires an existing Color Page grade body.",
            details={"path": "1.7.9"},
            recoverability="manual",
        )
    nodes = _split_grade_node_section(field9)[1]
    if not nodes:
        raise APICallFailed(
            "Color Page Hue vs Lum DB route could not find a grade node.",
            recoverability="manual",
        )
    node = nodes[0]
    f6 = _get_submessage(node, 6)
    f2 = _get_submessage(f6, 2) if f6 is not None else None
    if f2 is None:
        raise APICallFailed(
            "Color Page Hue vs Lum DB route could not find the grade param section.",
            details={"path": "1.7.9.1.6.2"},
            recoverability="manual",
        )

    raw_entries: dict[int, bytes] = {
        PARAM_HUE_VS_LUM_MODE: _build_varint_param_entry(PARAM_HUE_VS_LUM_MODE, 0),
        PARAM_HUE_CURVE_VARIANT: _build_varint_param_entry(PARAM_HUE_CURVE_VARIANT, 2),
        PARAM_HUE_VS_LUM_SELECTOR: _build_varint_param_entry(PARAM_HUE_VS_LUM_SELECTOR, 2),
        PARAM_HUE_VS_LUM_CURVE: _build_bytes_param_entry(
            PARAM_HUE_VS_LUM_CURVE,
            _hue_vs_lum_payload(input_hue, lum_gain),
            inner_field=8,
        ),
    }
    new_f2 = _rebuild_param_section_raw(f2, raw_entries)
    new_node = _replace_submessage_at_path(node, [6, 2], new_f2)
    new_field9 = _replace_grade_node(field9, 1, new_node)
    return _replace_submessage_at_path(base_proto, [1, 7, 9], new_field9)


def _inject_sat_vs_sat_curve_into_proto(
    base_proto: bytes,
    *,
    input_sat: float,
    output_sat: float,
) -> bytes:
    field9 = _extract_submessage(base_proto, [1, 7, 9])
    if field9 is None:
        raise APICallFailed(
            "Color Page Sat vs Sat DB route requires an existing Color Page grade body.",
            details={"path": "1.7.9"},
            recoverability="manual",
        )
    nodes = _split_grade_node_section(field9)[1]
    if not nodes:
        raise APICallFailed(
            "Color Page Sat vs Sat DB route could not find a grade node.",
            recoverability="manual",
        )
    node = nodes[0]
    f6 = _get_submessage(node, 6)
    f2 = _get_submessage(f6, 2) if f6 is not None else None
    if f2 is None:
        raise APICallFailed(
            "Color Page Sat vs Sat DB route could not find the grade param section.",
            details={"path": "1.7.9.1.6.2"},
            recoverability="manual",
        )

    raw_entries: dict[int, bytes] = {
        PARAM_HUE_CURVE_VARIANT: _build_varint_param_entry(PARAM_HUE_CURVE_VARIANT, 2),
        PARAM_SAT_VS_SAT_SELECTOR: _build_varint_param_entry(PARAM_SAT_VS_SAT_SELECTOR, 2),
        PARAM_SAT_VS_SAT_CURVE: _build_bytes_param_entry(
            PARAM_SAT_VS_SAT_CURVE,
            _sat_vs_sat_payload(input_sat, output_sat),
            inner_field=8,
        ),
    }
    new_f2 = _rebuild_param_section_raw(f2, raw_entries)
    new_node = _replace_submessage_at_path(node, [6, 2], new_f2)
    new_field9 = _replace_grade_node(field9, 1, new_node)
    return _replace_submessage_at_path(base_proto, [1, 7, 9], new_field9)


def _sat_curve_points_mode_config(mode: str) -> dict[str, Any]:
    normalized_mode = mode.strip().lower().replace("_", "-")
    configs: dict[str, dict[str, Any]] = {
        "sat-vs-sat": {
            "x_key": "input_sat",
            "value_key": "output_sat",
            "curve_key": PARAM_SAT_VS_SAT_CURVE,
            "readback_key": "sat_vs_sat",
            "route": "db_workaround_color_page_sat_vs_sat_points",
            "step": "update_sat_vs_sat_curve_points",
            "context": "color page sat vs sat points db mutation",
            "label": "Sat vs Sat",
            "entries": {
                PARAM_HUE_CURVE_VARIANT: _build_varint_param_entry(PARAM_HUE_CURVE_VARIANT, 2),
                PARAM_SAT_VS_SAT_SELECTOR: _build_varint_param_entry(PARAM_SAT_VS_SAT_SELECTOR, 2),
            },
        },
        "sat-vs-lum": {
            "x_key": "input_sat",
            "value_key": "lum",
            "curve_key": PARAM_SAT_VS_LUM_CURVE,
            "readback_key": "sat_vs_lum",
            "route": "db_workaround_color_page_sat_vs_lum_points",
            "step": "update_sat_vs_lum_curve_points",
            "context": "color page sat vs lum points db mutation",
            "label": "Sat vs Lum",
            "entries": {
                PARAM_HUE_CURVE_VARIANT: _build_varint_param_entry(PARAM_HUE_CURVE_VARIANT, 2),
                PARAM_SAT_VS_LUM_SELECTOR: _build_varint_param_entry(PARAM_SAT_VS_LUM_SELECTOR, 2),
            },
        },
        "lum-vs-sat": {
            "x_key": "input_lum",
            "value_key": "saturation",
            "curve_key": PARAM_LUM_VS_SAT_CURVE,
            "readback_key": "lum_vs_sat",
            "route": "db_workaround_color_page_lum_vs_sat_points",
            "step": "update_lum_vs_sat_curve_points",
            "context": "color page lum vs sat points db mutation",
            "label": "Lum vs Sat",
            "entries": {
                PARAM_HUE_CURVE_VARIANT: _build_varint_param_entry(PARAM_HUE_CURVE_VARIANT, 2),
                PARAM_LUM_VS_SAT_SELECTOR: _build_varint_param_entry(PARAM_LUM_VS_SAT_SELECTOR, 2),
            },
        },
    }
    config = configs.get(normalized_mode)
    if config is None:
        raise ValidationError(
            "Saturation curve points mode must be sat-vs-sat, sat-vs-lum, or lum-vs-sat.",
            details={"mode": mode, "supported_modes": sorted(configs)},
            recoverability="not_applicable",
        )
    return config


def _inject_sat_curve_points_into_proto(
    base_proto: bytes,
    *,
    mode: str,
    points: list[dict[str, float]],
) -> bytes:
    config = _sat_curve_points_mode_config(mode)
    label = str(config["label"])
    field9 = _extract_submessage(base_proto, [1, 7, 9])
    if field9 is None:
        raise APICallFailed(
            f"Color Page {label} points DB route requires an existing Color Page grade body.",
            details={"path": "1.7.9"},
            recoverability="manual",
        )
    nodes = _split_grade_node_section(field9)[1]
    if not nodes:
        raise APICallFailed(
            f"Color Page {label} points DB route could not find a grade node.",
            recoverability="manual",
        )
    node = nodes[0]
    f6 = _get_submessage(node, 6)
    f2 = _get_submessage(f6, 2) if f6 is not None else None
    if f2 is None:
        raise APICallFailed(
            f"Color Page {label} points DB route could not find the grade param section.",
            details={"path": "1.7.9.1.6.2"},
            recoverability="manual",
        )

    raw_entries: dict[int, bytes] = dict(config["entries"])
    curve_key = int(config["curve_key"])
    raw_entries[curve_key] = _build_bytes_param_entry(
        curve_key,
        _sat_curve_multi_point_payload(points),
        inner_field=8,
    )
    new_f2 = _rebuild_param_section_raw(f2, raw_entries)
    new_node = _replace_submessage_at_path(node, [6, 2], new_f2)
    new_field9 = _replace_grade_node(field9, 1, new_node)
    return _replace_submessage_at_path(base_proto, [1, 7, 9], new_field9)


def _inject_sat_vs_lum_curve_into_proto(
    base_proto: bytes,
    *,
    input_sat: float,
    lum: float,
) -> bytes:
    field9 = _extract_submessage(base_proto, [1, 7, 9])
    if field9 is None:
        raise APICallFailed(
            "Color Page Sat vs Lum DB route requires an existing Color Page grade body.",
            details={"path": "1.7.9"},
            recoverability="manual",
        )
    nodes = _split_grade_node_section(field9)[1]
    if not nodes:
        raise APICallFailed(
            "Color Page Sat vs Lum DB route could not find a grade node.",
            recoverability="manual",
        )
    node = nodes[0]
    f6 = _get_submessage(node, 6)
    f2 = _get_submessage(f6, 2) if f6 is not None else None
    if f2 is None:
        raise APICallFailed(
            "Color Page Sat vs Lum DB route could not find the grade param section.",
            details={"path": "1.7.9.1.6.2"},
            recoverability="manual",
        )

    raw_entries: dict[int, bytes] = {
        PARAM_HUE_CURVE_VARIANT: _build_varint_param_entry(PARAM_HUE_CURVE_VARIANT, 2),
        PARAM_SAT_VS_LUM_SELECTOR: _build_varint_param_entry(PARAM_SAT_VS_LUM_SELECTOR, 2),
        PARAM_SAT_VS_LUM_CURVE: _build_bytes_param_entry(
            PARAM_SAT_VS_LUM_CURVE,
            _sat_vs_lum_payload(input_sat, lum),
            inner_field=8,
        ),
    }
    new_f2 = _rebuild_param_section_raw(f2, raw_entries)
    new_node = _replace_submessage_at_path(node, [6, 2], new_f2)
    new_field9 = _replace_grade_node(field9, 1, new_node)
    return _replace_submessage_at_path(base_proto, [1, 7, 9], new_field9)


def _inject_lum_vs_sat_curve_into_proto(
    base_proto: bytes,
    *,
    input_lum: float,
    saturation: float,
) -> bytes:
    field9 = _extract_submessage(base_proto, [1, 7, 9])
    if field9 is None:
        raise APICallFailed(
            "Color Page Lum vs Sat DB route requires an existing Color Page grade body.",
            details={"path": "1.7.9"},
            recoverability="manual",
        )
    nodes = _split_grade_node_section(field9)[1]
    if not nodes:
        raise APICallFailed(
            "Color Page Lum vs Sat DB route could not find a grade node.",
            recoverability="manual",
        )
    node = nodes[0]
    f6 = _get_submessage(node, 6)
    f2 = _get_submessage(f6, 2) if f6 is not None else None
    if f2 is None:
        raise APICallFailed(
            "Color Page Lum vs Sat DB route could not find the grade param section.",
            details={"path": "1.7.9.1.6.2"},
            recoverability="manual",
        )

    raw_entries: dict[int, bytes] = {
        PARAM_LUM_VS_SAT_SELECTOR: _build_varint_param_entry(PARAM_LUM_VS_SAT_SELECTOR, 2),
        PARAM_HUE_CURVE_VARIANT: _build_varint_param_entry(PARAM_HUE_CURVE_VARIANT, 2),
        PARAM_LUM_VS_SAT_CURVE: _build_bytes_param_entry(
            PARAM_LUM_VS_SAT_CURVE,
            _lum_vs_sat_payload(input_lum, saturation),
            inner_field=8,
        ),
    }
    new_f2 = _rebuild_param_section_raw(f2, raw_entries)
    new_node = _replace_submessage_at_path(node, [6, 2], new_f2)
    new_field9 = _replace_grade_node(field9, 1, new_node)
    return _replace_submessage_at_path(base_proto, [1, 7, 9], new_field9)


__all__ = (
    '_inject_curve_points_into_proto',
    '_inject_hue_vs_hue_curve_into_proto',
    '_hue_curve_points_mode_config',
    '_inject_hue_curve_points_into_proto',
    '_inject_hue_vs_hue_curve_points_into_proto',
    '_inject_hue_vs_sat_curve_into_proto',
    '_inject_hue_vs_lum_curve_into_proto',
    '_inject_sat_vs_sat_curve_into_proto',
    '_sat_curve_points_mode_config',
    '_inject_sat_curve_points_into_proto',
    '_inject_sat_vs_lum_curve_into_proto',
    '_inject_lum_vs_sat_curve_into_proto',
)
