"""Workflow-owned GUI-assisted Color Page local-control routes.

This module is intentionally narrow. It reuses the same guarded macOS
Accessibility pattern as the Magic Mask route, but only for concrete Color
Page workflows that have their own readiness checks and proof artifacts.
"""

from __future__ import annotations

import ctypes
import math
import time
import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from ..errors import (
    CapabilityNegotiationFailed,
    ColorPageGuiProofFailed,
    ColorPagePanelNotReady,
    ColorPageTrackFailed,
    ValidationError,
)
from ..output import set_recoverability, set_verification_status
from ..utils.timecode import frames_to_timecode
from . import clip_ops
from .macos_project_library_accessibility import _AX as _ExactPidAccessibility
from .magic_mask_gui_route import (
    DEFAULT_PROOF_DIR as MAGIC_MASK_DEFAULT_PROOF_DIR,
    MacOSMagicMaskGuiDriver,
    Rect,
    _ensure_color_page,
    _post_mouse_drag,
    _run_osascript,
)

ROUTE_POWER_WINDOW_TRACK = "color.page_power_window_track_gui"
ROUTE_POWER_WINDOW_GUI_SET = "color.page_power_window_gui_set"
ROUTE_SKY_ISOLATION_GUI = "color.page_sky_isolation_gui"
ROUTE_QUALIFIER_PANEL_PROBE = "color.page_qualifier_panel_probe_gui"
ROUTE_QUALIFIER_GUI_HSL_SET = "color.page_qualifier_gui_hsl_set"
ROUTE_QUALIFIER_GUI_MATTE_SET = "color.page_qualifier_gui_matte_set"
ROUTE_PRIMARY_GUI_SET = "color.page_primary_gui_set"
ENGINE = "resolve_gui"
DEFAULT_PROOF_DIR = MAGIC_MASK_DEFAULT_PROOF_DIR.parent / "color-page-gui"


def _post_focus_free_keyboard_value(*, target_pid: int, target_window_id: int, text_value: str) -> None:
    """Replace the active target field without posting keyboard events globally."""

    app_services = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
    )
    core_foundation = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
    )
    app_services.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
    app_services.CGEventCreateKeyboardEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_bool]
    app_services.CGEventSetFlags.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    app_services.CGEventKeyboardSetUnicodeString.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_uint16),
    ]
    app_services.CGEventSetIntegerValueField.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int64]
    app_services.CGEventPostToPid.argtypes = [ctypes.c_int32, ctypes.c_void_p]
    core_foundation.CFRelease.argtypes = [ctypes.c_void_p]

    if int(target_pid) <= 0 or int(target_window_id) <= 0:
        raise ColorPagePanelNotReady(
            "Focus-free keyboard input requires a verified DaVinci Resolve PID and window ID."
        )

    def post(key_code: int, key_down: bool, *, flags: int = 0, text: str | None = None) -> None:
        event = app_services.CGEventCreateKeyboardEvent(None, int(key_code), bool(key_down))
        if not event:
            raise ColorPagePanelNotReady("macOS failed to create focus-free DaVinci Resolve keyboard input.")
        try:
            app_services.CGEventSetFlags(event, int(flags))
            for field in (91, 92):
                app_services.CGEventSetIntegerValueField(event, field, int(target_window_id))
            if text is not None:
                encoded = text.encode("utf-16-le")
                units = (ctypes.c_uint16 * (len(encoded) // 2)).from_buffer_copy(encoded)
                app_services.CGEventKeyboardSetUnicodeString(event, len(units), units)
            app_services.CGEventPostToPid(int(target_pid), event)
        finally:
            core_foundation.CFRelease(event)
        time.sleep(0.06)

    command_flag = 1 << 20
    post(0, True, flags=command_flag)
    post(0, False, flags=command_flag)
    post(0, True, text=text_value)
    post(0, False, text=text_value)
    post(36, True)
    post(36, False)

POWER_WINDOW_SHAPES = {"circle", "gradient", "linear", "rectangle", "polygon", "curve"}
TRACK_DIRECTIONS = {"forward", "backward", "both"}
SETTABLE_CONTROL_ROLES = {"AXSlider", "AXTextField", "AXValueIndicator", "AXIncrementor"}
PRESSABLE_CONTROL_ROLES = {"AXButton", "AXCheckBox", "AXRadioButton", "AXMenuButton"}
PRIMARY_GUI_CONTROL_RANGES = {
    "temperature": (-100.0, 100.0),
    "tint": (-100.0, 100.0),
    "contrast": (0.0, 2.0),
    "pivot": (0.0, 1.0),
    "mid_detail": (-100.0, 100.0),
    "color_boost": (-100.0, 100.0),
    "shadows": (-100.0, 100.0),
    "highlights": (-100.0, 100.0),
    "saturation": (0.0, 100.0),
    "hue": (0.0, 100.0),
    "lum_mix": (0.0, 100.0),
}
PRIMARY_GUI_LABELS = {
    "temperature": "Temp",
    "tint": "Tint",
    "contrast": "Contrast",
    "pivot": "Pivot",
    "mid_detail": "Mid/Detail",
    "color_boost": "Color Boost",
    "shadows": "Shadows",
    "highlights": "Highlights",
    "saturation": "Saturation",
    "hue": "Hue",
    "lum_mix": "Lum Mix",
}
POWER_WINDOW_GUI_SHAPE_LABELS = {
    "linear": "Linear",
    "rectangle": "Linear",
    "circle": "Circle",
    "polygon": "Polygon",
    "curve": "Curve",
    "gradient": "Gradient",
}
POWER_WINDOW_GUI_CONTROL_RANGES = {
    "size": (0.0, 100.0),
    "aspect": (0.0, 100.0),
    "pan": (0.0, 100.0),
    "tilt": (0.0, 100.0),
    "rotate": (-180.0, 180.0),
    "opacity": (0.0, 100.0),
    "soft_1": (0.0, 100.0),
    "soft_2": (0.0, 100.0),
    "soft_3": (0.0, 100.0),
    "soft_4": (0.0, 100.0),
    "inside": (0.0, 100.0),
    "outside": (0.0, 100.0),
}
POWER_WINDOW_GUI_LABELS = {
    "size": "Size",
    "aspect": "Aspect",
    "pan": "Pan",
    "tilt": "Tilt",
    "rotate": "Rotate",
    "opacity": "Opacity",
    "soft_1": "Soft 1",
    "soft_2": "Soft 2",
    "soft_3": "Soft 3",
    "soft_4": "Soft 4",
    "inside": "Inside",
    "outside": "Outside",
}


@dataclass(frozen=True)
class ColorPageProofPaths:
    screenshot_path: Path
    export_path: Path

    def as_payload(self) -> dict[str, str]:
        return {key: str(value) for key, value in asdict(self).items()}


ProofExporter = Callable[[Path], dict[str, Any]]


def normalize_power_window_shape(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("_", "-")
    aliases = {
        "ellipse": "circle",
        "circular": "circle",
        "grad": "gradient",
        "line": "linear",
        "rect": "rectangle",
        "poly": "polygon",
        "power-curve": "curve",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in POWER_WINDOW_SHAPES:
        raise ValidationError(
            "Color Page Power Window shape must be one of circle, gradient, linear, rectangle, polygon, or curve.",
            details={"shape": value, "allowed": sorted(POWER_WINDOW_SHAPES)},
            recoverability="not_applicable",
        )
    return normalized


def normalize_track_direction(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("_", "-")
    aliases = {
        "f": "forward",
        "forwards": "forward",
        "track-forward": "forward",
        "b": "backward",
        "back": "backward",
        "reverse": "backward",
        "track-backward": "backward",
        "bi": "both",
        "bidirectional": "both",
        "forward-backward": "both",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in TRACK_DIRECTIONS:
        raise ValidationError(
            "Color Page Power Window tracking direction must be one of forward, backward, or both.",
            details={"direction": value, "allowed": sorted(TRACK_DIRECTIONS)},
            recoverability="not_applicable",
        )
    return normalized


def normalize_power_window_gui_controls(
    *,
    shape: str,
    size: float | None = None,
    aspect: float | None = None,
    pan: float | None = None,
    tilt: float | None = None,
    rotate: float | None = None,
    opacity: float | None = None,
    soft_1: float | None = None,
    soft_2: float | None = None,
    soft_3: float | None = None,
    soft_4: float | None = None,
    inside: float | None = None,
    outside: float | None = None,
) -> dict[str, Any]:
    normalized_shape = normalize_power_window_shape(shape)
    controls: list[dict[str, Any]] = []
    values: dict[str, float] = {}
    requested = {
        "size": size,
        "aspect": aspect,
        "pan": pan,
        "tilt": tilt,
        "rotate": rotate,
        "opacity": opacity,
        "soft_1": soft_1,
        "soft_2": soft_2,
        "soft_3": soft_3,
        "soft_4": soft_4,
        "inside": inside,
        "outside": outside,
    }
    for control, raw_value in requested.items():
        if raw_value is None:
            continue
        try:
            numeric = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                f"Color Page Power Window GUI {control} must be numeric.",
                details={control: raw_value},
                recoverability="not_applicable",
            ) from exc
        minimum, maximum = POWER_WINDOW_GUI_CONTROL_RANGES[control]
        if not math.isfinite(numeric) or numeric < minimum or numeric > maximum:
            raise ValidationError(
                f"Color Page Power Window GUI {control} must be between {minimum:g} and {maximum:g}.",
                details={control: raw_value, "minimum": minimum, "maximum": maximum},
                recoverability="not_applicable",
            )
        values[control] = numeric
        controls.append({"control": control, "label": POWER_WINDOW_GUI_LABELS[control], "value": numeric})
    return {"shape": normalized_shape, "values": values, "controls": controls}


def _parse_gui_range(value: str, *, option_name: str, hue: bool = False) -> tuple[float, float]:
    raw = str(value or "").strip()
    if not raw:
        raise ValidationError(
            f"Color Page Qualifier GUI {option_name} range must not be empty.",
            details={option_name: value},
            recoverability="not_applicable",
        )
    pieces = [piece.strip() for piece in raw.replace("..", ",").replace(":", ",").split(",") if piece.strip()]
    if len(pieces) != 2:
        raise ValidationError(
            f"Color Page Qualifier GUI {option_name} range must be two values, e.g. 180,230.",
            details={option_name: value},
            recoverability="not_applicable",
        )
    try:
        low, high = (float(piece) for piece in pieces)
    except ValueError as exc:
        raise ValidationError(
            f"Color Page Qualifier GUI {option_name} range values must be numeric.",
            details={option_name: value},
            recoverability="not_applicable",
        ) from exc
    if hue:
        if abs(low) > 1.0 or abs(high) > 1.0:
            if low < 0.0 or low > 360.0 or high < 0.0 or high > 360.0:
                raise ValidationError(
                    "Color Page Qualifier GUI hue range must be 0-1 turns or 0-360 degrees.",
                    details={"hue": value},
                    recoverability="not_applicable",
                )
            low = (low % 360.0) / 360.0
            high = (high % 360.0) / 360.0
        if low == high:
            raise ValidationError(
                "Color Page Qualifier GUI hue range must cover a non-zero span.",
                details={"hue": value, "normalized_low": low, "normalized_high": high},
                recoverability="not_applicable",
            )
        return low, high
    if abs(low) > 1.0 or abs(high) > 1.0:
        low = low / 100.0
        high = high / 100.0
    if low < 0.0 or low > 1.0 or high < 0.0 or high > 1.0 or high <= low:
        raise ValidationError(
            f"Color Page Qualifier GUI {option_name} range must be ascending within 0-1 or 0-100 percent.",
            details={option_name: value, "normalized_low": low, "normalized_high": high},
            recoverability="not_applicable",
        )
    return low, high


def normalize_qualifier_gui_hsl_controls(
    *,
    hue: str | None = None,
    saturation: str | None = None,
    luma: str | None = None,
    softness: float | None = None,
    hue_softness: float | None = None,
    saturation_softness: float | None = None,
    luma_softness: float | None = None,
) -> dict[str, Any]:
    controls: list[dict[str, Any]] = []
    ranges: dict[str, dict[str, float]] = {}
    global_softness = None if softness is None else _normalize_gui_scalar(float(softness), option_name="softness")
    if hue is not None:
        low, high = _parse_gui_range(hue, option_name="hue", hue=True)
        ranges["hue"] = {"low": low, "high": high}
        controls.extend(
            [
                {"control": "hue_low", "terms": ["hue", "low"], "value": low},
                {"control": "hue_high", "terms": ["hue", "high"], "value": high},
            ]
        )
        hue_soft = (
            _normalize_gui_scalar(float(hue_softness), option_name="hue_softness")
            if hue_softness is not None
            else (global_softness if abs(high - low) < 0.98 else None)
        )
        if hue_soft is not None:
            controls.append({"control": "hue_softness", "terms": ["hue", "soft"], "value": hue_soft})
    if saturation is not None:
        low, high = _parse_gui_range(saturation, option_name="saturation")
        ranges["saturation"] = {"low": low, "high": high}
        controls.extend(
            [
                {"control": "saturation_low", "terms": ["sat", "low"], "value": low},
                {"control": "saturation_high", "terms": ["sat", "high"], "value": high},
            ]
        )
        sat_soft = (
            _normalize_gui_scalar(float(saturation_softness), option_name="saturation_softness")
            if saturation_softness is not None
            else (global_softness if abs(high - low) < 0.98 else None)
        )
        if sat_soft is not None:
            controls.append({"control": "saturation_softness", "terms": ["sat", "soft"], "value": sat_soft})
    if luma is not None:
        low, high = _parse_gui_range(luma, option_name="luma")
        ranges["luma"] = {"low": low, "high": high}
        controls.extend(
            [
                {"control": "luma_low", "terms": ["lum", "low"], "value": low},
                {"control": "luma_high", "terms": ["lum", "high"], "value": high},
            ]
        )
        lum_soft = (
            _normalize_gui_scalar(float(luma_softness), option_name="luma_softness")
            if luma_softness is not None
            else (global_softness if abs(high - low) < 0.98 else None)
        )
        if lum_soft is not None:
            controls.append({"control": "luma_softness", "terms": ["lum", "soft"], "value": lum_soft})
    if not controls:
        raise ValidationError(
            "Color Page Qualifier GUI HSL set requires at least one of --hue, --saturation, or --luma.",
            details={"hue": hue, "saturation": saturation, "luma": luma},
            recoverability="not_applicable",
        )
    return {"ranges": ranges, "controls": controls}


def _normalize_gui_scalar(value: float, *, option_name: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"Color Page Qualifier GUI {option_name} must be numeric.",
            details={option_name: value},
            recoverability="not_applicable",
        ) from exc
    if numeric > 1.0:
        numeric = numeric / 100.0
    if numeric < 0.0 or numeric > 1.0:
        raise ValidationError(
            f"Color Page Qualifier GUI {option_name} must be between 0 and 1, or 0 and 100 percent.",
            details={option_name: value, "normalized": numeric},
            recoverability="not_applicable",
        )
    return numeric


def normalize_qualifier_gui_matte_controls(
    *,
    softness: float | None = None,
    blur: float | None = None,
    clean_black: float | None = None,
    clean_white: float | None = None,
    denoise: float | None = None,
    grow_shrink: float | None = None,
) -> dict[str, Any]:
    controls: list[dict[str, Any]] = []
    values: dict[str, float] = {}
    if softness is not None:
        numeric = _normalize_gui_scalar(softness, option_name="softness")
        values["softness"] = numeric
        controls.append({"control": "softness", "terms": ["soft"], "value": numeric})
    if blur is not None:
        numeric = _normalize_gui_scalar(blur, option_name="blur")
        values["blur"] = numeric
        controls.append({"control": "blur", "terms": ["blur"], "value": numeric})
    if clean_black is not None:
        numeric = _normalize_gui_scalar(clean_black, option_name="clean_black")
        values["clean_black"] = numeric
        controls.append({"control": "clean_black", "terms": ["clean", "black"], "value": numeric})
    if clean_white is not None:
        numeric = _normalize_gui_scalar(clean_white, option_name="clean_white")
        values["clean_white"] = numeric
        controls.append({"control": "clean_white", "terms": ["clean", "white"], "value": numeric})
    if denoise is not None:
        numeric = _normalize_gui_scalar(denoise, option_name="denoise")
        values["denoise"] = numeric
        controls.append({"control": "denoise", "terms": ["denoise"], "value": numeric})
    if grow_shrink is not None:
        numeric = _normalize_gui_scalar(grow_shrink, option_name="grow_shrink")
        values["grow_shrink"] = numeric
        controls.append({"control": "grow_shrink", "terms": ["grow", "shrink"], "value": numeric})
    if not controls:
        raise ValidationError(
            "Color Page Qualifier GUI matte set requires at least one matte/refinement option.",
            details={
                "softness": softness,
                "blur": blur,
                "clean_black": clean_black,
                "clean_white": clean_white,
                "denoise": denoise,
                "grow_shrink": grow_shrink,
            },
            recoverability="not_applicable",
        )
    return {"values": values, "controls": controls}


def normalize_primary_gui_controls(**kwargs: float | None) -> dict[str, Any]:
    controls: list[dict[str, Any]] = []
    values: dict[str, float] = {}
    for control, raw_value in kwargs.items():
        if raw_value is None:
            continue
        if control not in PRIMARY_GUI_CONTROL_RANGES:
            raise ValidationError(
                "Unsupported Color Page Primaries GUI control.",
                details={"control": control, "allowed": sorted(PRIMARY_GUI_CONTROL_RANGES)},
                recoverability="not_applicable",
            )
        try:
            numeric = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                f"Color Page Primaries GUI {control} must be numeric.",
                details={control: raw_value},
                recoverability="not_applicable",
            ) from exc
        minimum, maximum = PRIMARY_GUI_CONTROL_RANGES[control]
        if not math.isfinite(numeric) or numeric < minimum or numeric > maximum:
            raise ValidationError(
                f"Color Page Primaries GUI {control} must be between {minimum:g} and {maximum:g}.",
                details={control: raw_value, "minimum": minimum, "maximum": maximum},
                recoverability="not_applicable",
            )
        values[control] = numeric
        controls.append({"control": control, "label": PRIMARY_GUI_LABELS[control], "value": numeric})
    if not controls:
        raise ValidationError(
            "Color Page Primaries GUI set requires at least one control value.",
            details={"allowed": sorted(PRIMARY_GUI_CONTROL_RANGES)},
            recoverability="not_applicable",
        )
    return {"values": values, "controls": controls}


def normalize_optional_clip(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        raise ValidationError(
            "Color Page Power Window tracking clip name must not be empty.",
            details={"clip": value},
            recoverability="not_applicable",
        )
    return normalized


def _save_project_for_color_page_payload_readback(conn: Any) -> dict[str, Any]:
    project_manager = getattr(conn.resolve, "GetProjectManager", lambda: None)()
    save_fn = getattr(project_manager, "SaveProject", None) if project_manager is not None else None
    if not callable(save_fn):
        return {"saved": False, "available": False, "reason": "SaveProject_unavailable"}
    try:
        result = bool(save_fn())
    except Exception as exc:
        return {"saved": False, "available": True, "error": str(exc)}
    time.sleep(0.25)
    return {"saved": result, "available": True}


def _first_varint(data: bytes, field_number: int) -> int | None:
    from ._color_page_db.proto_sections import _iter_proto_fields

    for fn, wt, value, _raw in _iter_proto_fields(data):
        if fn == field_number and wt == 0:
            return int(value)
    return None


def _length_delimited_fields(data: bytes, field_number: int) -> list[bytes]:
    from ._color_page_db.proto_sections import _iter_proto_fields

    return [
        bytes(value)
        for fn, wt, value, _raw in _iter_proto_fields(data)
        if fn == field_number and wt == 2 and isinstance(value, (bytes, bytearray))
    ]


def _node_internal_payload_summary(container: bytes) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    field9_values = _length_delimited_fields(container, 9)
    if not field9_values:
        return entries
    for entry in _length_delimited_fields(field9_values[0], 1):
        field6_values = _length_delimited_fields(entry, 6)
        entries.append(
            {
                "id": _first_varint(entry, 1),
                "field6_count": len(field6_values),
                "field6_keys": [_first_varint(field6, 1) for field6 in field6_values],
                "field6_sha256": [hashlib.sha256(field6).hexdigest() for field6 in field6_values],
            }
        )
    return entries


def _timeline_item_identity_for_db(item: Any) -> dict[str, Any]:
    name = None
    try:
        name = str(item.GetName() or "").strip() if hasattr(item, "GetName") else None
    except Exception:
        name = None
    unique_ids: list[str] = []
    for method_name in ("GetUniqueId", "GetUniqueID", "GetId", "GetID"):
        getter = getattr(item, method_name, None)
        if not callable(getter):
            continue
        try:
            value = getter()
        except Exception:
            continue
        if value is not None and str(value).strip():
            unique_ids.append(str(value).strip())
    start = None
    duration = None
    end = None
    for attr_name, target in (("GetStart", "start"), ("GetDuration", "duration"), ("GetEnd", "end")):
        getter = getattr(item, attr_name, None)
        if not callable(getter):
            continue
        try:
            value = int(getter())
        except Exception:
            continue
        if target == "start":
            start = value
        elif target == "duration":
            duration = value
        else:
            end = value
    if duration is None and start is not None and end is not None:
        duration = max(0, int(end) - int(start))
    track_type = None
    track_index = None
    getter = getattr(item, "GetTrackTypeAndIndex", None)
    if callable(getter):
        try:
            track_type, track_index = getter()
        except Exception:
            track_type = None
            track_index = None
    return {
        "name": name or None,
        "unique_ids": unique_ids,
        "start": start,
        "duration": duration,
        "end": end,
        "track_type": track_type,
        "track_index": track_index,
    }


def _tracking_payload_rows_for_item(
    connection: sqlite3.Connection,
    *,
    identity: dict[str, Any],
    fallback_clip: str | None,
) -> list[sqlite3.Row]:
    unique_ids = [value for value in identity.get("unique_ids") or [] if value]
    if unique_ids:
        placeholders = ", ".join("?" for _ in unique_ids)
        rows = connection.execute(
            f"""
            SELECT item.Sm2TiItem_id, item.Name, item.Start, item.Duration, v.Body
              FROM Sm2TiItem item
              JOIN "ListMgt::LmVersionTable" table_row
                ON table_row."ListMgt::LmVersionTable_id" = item.pLmVerTable
              JOIN "ListMgt::LmVersion" v
                ON v."ListMgt::LmVersion_id" = table_row.pActive
             WHERE item.DbType = 'Sm2TiVideoClip'
               AND item.Sm2TiItem_id IN ({placeholders})
            """,
            unique_ids,
        ).fetchall()
        if rows:
            return rows

    name = identity.get("name") or fallback_clip
    start = identity.get("start")
    duration = identity.get("duration")
    if name and start is not None and duration is not None:
        rows = connection.execute(
            """
            SELECT item.Sm2TiItem_id, item.Name, item.Start, item.Duration, v.Body
              FROM Sm2TiItem item
              JOIN "ListMgt::LmVersionTable" table_row
                ON table_row."ListMgt::LmVersionTable_id" = item.pLmVerTable
              JOIN "ListMgt::LmVersion" v
                ON v."ListMgt::LmVersion_id" = table_row.pActive
             WHERE item.DbType = 'Sm2TiVideoClip'
               AND item.Name = ?
               AND CAST(COALESCE(item.Start, '0') AS INTEGER) = ?
               AND CAST(COALESCE(item.Duration, '0') AS INTEGER) = ?
            """,
            (name, int(start), int(duration)),
        ).fetchall()
        if rows:
            return rows

    if name:
        rows = connection.execute(
            """
            SELECT item.Sm2TiItem_id, item.Name, item.Start, item.Duration, v.Body
              FROM Sm2TiItem item
              JOIN "ListMgt::LmVersionTable" table_row
                ON table_row."ListMgt::LmVersionTable_id" = item.pLmVerTable
              JOIN "ListMgt::LmVersion" v
                ON v."ListMgt::LmVersion_id" = table_row.pActive
             WHERE item.DbType = 'Sm2TiVideoClip'
               AND item.Name = ?
            """,
            (name,),
        ).fetchall()
        if len(rows) <= 1:
            return rows

    return []


def _fallback_tracking_payload_rows_by_name(
    connection: sqlite3.Connection,
    *,
    identity: dict[str, Any],
    fallback_clip: str | None,
) -> list[sqlite3.Row]:
    name = identity.get("name") or fallback_clip
    start = identity.get("start")
    duration = identity.get("duration")
    if not name:
        return []
    params: list[Any] = [name]
    timing_filter = ""
    if start is not None and duration is not None:
        timing_filter = """
                   AND CAST(COALESCE(item.Start, '0') AS INTEGER) = ?
                   AND CAST(COALESCE(item.Duration, '0') AS INTEGER) = ?
        """
        params.extend([int(start), int(duration)])
    rows = connection.execute(
        f"""
                SELECT item.Sm2TiItem_id, item.Name, item.Start, item.Duration, v.Body
                  FROM Sm2TiItem item
                  JOIN "ListMgt::LmVersion_ListMgt::LmVersionTable" rel
                    ON rel.DbOwner = item.pLmVerTable
                  JOIN "ListMgt::LmVersion" v
                    ON v."ListMgt::LmVersion_id" = rel.DbAssociate
                 WHERE item.DbType = 'Sm2TiVideoClip'
                   AND item.Name = ?
                   {timing_filter}
                   AND v.HasCorrection = 1
                   AND v.Body IS NOT NULL
                 ORDER BY LENGTH(v.Body) DESC
        """,
        params,
    ).fetchall()
    selected_by_item: dict[str, sqlite3.Row] = {}
    for row in rows:
        item_id = str(row["Sm2TiItem_id"])
        if item_id not in selected_by_item:
            selected_by_item[item_id] = row
    return list(selected_by_item.values())


def _active_color_page_tracking_payload_signature(conn: Any, *, clip_name: str | None, item: Any | None = None) -> dict[str, Any]:
    from ..runtime_health import resolve_current_disk_project_db
    from ._color_page_db.params import _parse_params_from_proto
    from ._color_page_db.proto_sections import _root_color_node_containers
    from ._color_page_db.version_body import decompress_version_body

    normalized_clip = normalize_optional_clip(clip_name)
    resolved_item = item
    if resolved_item is None and normalized_clip:
        resolved_item = clip_ops.cutagent_clip(conn, normalized_clip)
    identity = _timeline_item_identity_for_db(resolved_item) if resolved_item is not None else {}
    identity_clip = identity.get("name") or normalized_clip
    if not identity_clip:
        raise ColorPageGuiProofFailed(
            "Color Page tracking payload readback requires a resolved timeline item.",
            details={"clip": clip_name, "reason": "tracking_payload_clip_unresolved"},
        )
    current_db = resolve_current_disk_project_db(conn, allow_project_name_inference=True)
    db_path = str(current_db["project_db_path"])
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = [row for row in _tracking_payload_rows_for_item(connection, identity=identity, fallback_clip=identity_clip) if row["Body"] is not None]
        if not rows:
            rows = [row for row in _fallback_tracking_payload_rows_by_name(connection, identity=identity, fallback_clip=identity_clip) if row["Body"] is not None]
        if len(rows) > 1:
            raise ColorPageGuiProofFailed(
                "Color Page tracking payload readback matched multiple timeline items; refusing name-only proof.",
                details={
                    "clip": identity_clip,
                    "identity": identity,
                    "db_path": db_path,
                    "reason": "tracking_payload_item_ambiguous",
                    "matches": [
                        {
                            "item_id": row["Sm2TiItem_id"],
                            "name": row["Name"],
                            "start": row["Start"],
                            "duration": row["Duration"],
                        }
                        for row in rows
                    ],
                },
            )
        row = rows[0] if rows else None
        if row is None or row["Body"] is None:
            raise ColorPageGuiProofFailed(
                "Color Page tracking payload readback could not find an active grade body.",
                details={"clip": identity_clip, "identity": identity, "db_path": db_path, "reason": "tracking_payload_body_missing"},
            )
        proto = decompress_version_body(row["Body"])
        params = [param.to_dict() for param in _parse_params_from_proto(proto)]
        params_by_node: dict[int, list[dict[str, Any]]] = {}
        for param in params:
            node = int(param.get("node") or 0)
            params_by_node.setdefault(node, []).append(param)
        containers = _root_color_node_containers(proto)
        nodes: list[dict[str, Any]] = []
        for index, container in enumerate(containers, start=1):
            node_params = params_by_node.get(index) or []
            stable_params = json.dumps(node_params, sort_keys=True, separators=(",", ":")).encode("utf-8")
            nodes.append(
                {
                    "index": index,
                    "container_len": len(container),
                    "container_sha256": hashlib.sha256(container).hexdigest(),
                    "known_param_count": len(node_params),
                    "known_param_sha256": hashlib.sha256(stable_params).hexdigest(),
                    "internal_payload": _node_internal_payload_summary(container),
                }
            )
        return {
            "status": "captured",
            "clip": identity_clip,
            "item_id": row["Sm2TiItem_id"],
            "item_identity": identity,
            "db_path": db_path,
            "node_count": len(nodes),
            "nodes": nodes,
        }
    finally:
        connection.close()


def _compare_tracking_payload_signatures(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    expected_node_index: int | None = None,
) -> dict[str, Any]:
    before_nodes = {int(node["index"]): node for node in before.get("nodes", []) if isinstance(node, dict)}
    after_nodes = {int(node["index"]): node for node in after.get("nodes", []) if isinstance(node, dict)}
    changed_nodes: list[dict[str, Any]] = []
    hidden_payload_changed = False
    for index in sorted(set(before_nodes) | set(after_nodes)):
        before_node = before_nodes.get(index)
        after_node = after_nodes.get(index)
        if before_node == after_node:
            continue
        known_params_changed = (
            before_node is None
            or after_node is None
            or before_node.get("known_param_sha256") != after_node.get("known_param_sha256")
        )
        container_changed = (
            before_node is None
            or after_node is None
            or before_node.get("container_sha256") != after_node.get("container_sha256")
        )
        internal_payload_changed = (
            before_node is None
            or after_node is None
            or before_node.get("internal_payload") != after_node.get("internal_payload")
        )
        if container_changed and (internal_payload_changed or not known_params_changed):
            hidden_payload_changed = True
        changed_nodes.append(
            {
                "index": index,
                "container_changed": container_changed,
                "known_params_changed": known_params_changed,
                "internal_payload_changed": internal_payload_changed,
                "before": before_node,
                "after": after_node,
            }
        )
    status = "verified" if hidden_payload_changed else "failed"
    expected_node_changed = None
    if expected_node_index is not None:
        expected = int(expected_node_index)
        expected_node_changed = any(
            int(node.get("index") or 0) == expected
            and bool(node.get("container_changed"))
            and bool(node.get("internal_payload_changed"))
            for node in changed_nodes
        )
        if not expected_node_changed:
            status = "failed"
    return {
        "status": status,
        "hidden_payload_changed": hidden_payload_changed,
        "expected_node_index": expected_node_index,
        "expected_node_changed": expected_node_changed,
        "changed_node_count": len(changed_nodes),
        "changed_nodes": changed_nodes,
        "before_node_count": before.get("node_count"),
        "after_node_count": after.get("node_count"),
        "clip": after.get("clip") or before.get("clip"),
        "db_path": after.get("db_path") or before.get("db_path"),
    }


class MacOSColorPageGuiDriver(MacOSMagicMaskGuiDriver):
    """Internal macOS driver scoped to Color Page panel operations."""

    def _focus_free_ax_window_target(self) -> dict[str, Any]:
        rect = self._focus_free_target_window_rect()
        return {
            "pid": self._focus_free_target_pid(),
            "name": self._focus_free_target_window_name(),
            "x": rect.x,
            "y": rect.y,
            "width": rect.width,
            "height": rect.height,
        }

    def _post_focus_free_mouse_drag(
        self,
        points: list[tuple[int, int]],
        *,
        delay_seconds: float = 0.025,
    ) -> None:
        _post_mouse_drag(
            points,
            target_pid=self._focus_free_target_pid(),
            target_window_id=self._focus_free_target_window_id(),
            target_window_rect=self._focus_free_target_window_rect(),
            delay_seconds=delay_seconds,
        )

    @contextmanager
    def _exact_pid_accessibility_items(self):
        target_pid = self._focus_free_target_pid()
        target_window_id = self._focus_free_target_window_id()
        target_rect = self._focus_free_target_window_rect()
        client = _ExactPidAccessibility()
        if not client.ax.AXIsProcessTrusted():
            raise ColorPagePanelNotReady("macOS Accessibility is not authorized for exact-PID Color Page input.")
        windows = client.windows(target_pid)
        matches = [
            window
            for window in windows
            if client.pid(window) == target_pid and client.window_id(window) == target_window_id
        ]
        if len(matches) != 1:
            client.release_all(windows)
            raise ColorPagePanelNotReady(
                "The exact DaVinci Resolve PID/window Accessibility target is unavailable or ambiguous.",
                details={"target_pid": target_pid, "target_window_id": target_window_id, "match_count": len(matches)},
            )
        selected = matches[0]
        position = client.point(selected)
        size = client.size(selected)
        if (
            position is None
            or size is None
            or abs(position[0] - target_rect.x) > 3
            or abs(position[1] - target_rect.y) > 3
            or abs(size[0] - target_rect.width) > 3
            or abs(size[1] - target_rect.height) > 3
        ):
            client.release_all(windows)
            raise ColorPagePanelNotReady(
                "The exact DaVinci Resolve Accessibility window geometry no longer matches the verified target.",
                details={
                    "target_pid": target_pid,
                    "target_window_id": target_window_id,
                    "expected_rect": target_rect.as_payload(),
                    "position": position,
                    "size": size,
                },
            )
        for window in windows:
            if window != selected:
                client.release(window)
        try:
            items = client.flatten(selected, label="Color Page exact window", max_elements=4000)
        except Exception:
            client.release(selected)
            raise
        try:
            yield client, items
        finally:
            client.release_all(items)

    @staticmethod
    def _accessibility_candidates_at_point(
        client: Any,
        items: list[int],
        point: tuple[int, int],
        *,
        roles: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for item in items:
            role = client.string(item, "AXRole")
            if roles is not None and role not in roles:
                continue
            position = client.point(item)
            size = client.size(item)
            if position is None or size is None:
                continue
            x, y = position
            width, height = size
            if (
                point[0] >= x - 2
                and point[0] <= x + width + 2
                and point[1] >= y - 2
                and point[1] <= y + height + 2
            ):
                candidates.append(
                    {
                        "item": item,
                        "role": role,
                        "position": [x, y],
                        "size": [width, height],
                        "area": max(1.0, width * height),
                        "distance": abs(x + width / 2.0 - point[0]) + abs(y + height / 2.0 - point[1]),
                    }
                )
        candidates.sort(key=lambda row: (row["distance"], row["area"]))
        return candidates

    def _attempt_accessibility_values_at_points(
        self,
        writes: list[dict[str, Any]],
        *,
        settle_seconds: float,
    ) -> list[dict[str, Any]]:
        """Try multiple Qt numeric fields through one exact-window AX traversal."""

        target_pid = self._focus_free_target_pid()
        target_window_id = self._focus_free_target_window_id()
        target_window_rect = self._focus_free_target_window_rect()
        results: list[dict[str, Any]] = []
        try:
            with self._exact_pid_accessibility_items() as (client, items):
                for row in writes:
                    point = (int(row["point"][0]), int(row["point"][1]))
                    text_value = str(row["text_value"])
                    result: dict[str, Any] = {
                        "matched": False,
                        "set": False,
                        "target_pid": target_pid,
                        "target_window_id": target_window_id,
                        "point": list(point),
                        "text_value": text_value,
                    }
                    candidates = self._accessibility_candidates_at_point(
                        client, items, point, roles=SETTABLE_CONTROL_ROLES
                    )
                    for candidate in candidates:
                        result.update(
                            matched=True,
                            role=candidate["role"],
                            position=candidate["position"],
                            size=candidate["size"],
                            errors=[],
                        )
                        try:
                            client.set_number(candidate["item"], float(text_value))
                            result.update(set=True, value_type="number")
                        except (TypeError, ValueError, RuntimeError) as exc:
                            result["errors"].append(str(exc))
                        if not result["set"]:
                            try:
                                client.set_string(candidate["item"], text_value)
                                result.update(set=True, value_type="string")
                            except RuntimeError as exc:
                                result["errors"].append(str(exc))
                        if result["set"]:
                            result["readback"] = client.scalar_text(candidate["item"])
                            break

                    try:
                        direct_matches = math.isclose(
                            float(result["readback"]), float(text_value), abs_tol=0.011
                        )
                    except (KeyError, TypeError, ValueError):
                        direct_matches = False
                    if direct_matches:
                        result.pop("errors", None)
                        result["method"] = "focus_free_accessibility_value"
                        result["readback_matches_requested"] = True
                    else:
                        _post_mouse_drag(
                            [point],
                            target_pid=target_pid,
                            target_window_id=target_window_id,
                            target_window_rect=target_window_rect,
                            delay_seconds=0.05,
                            deactivate_after=False,
                        )
                        try:
                            _post_focus_free_keyboard_value(
                                target_pid=target_pid,
                                target_window_id=target_window_id,
                                text_value=text_value,
                            )
                        finally:
                            # Remove the synthetic app/key-window state after
                            # committing the exact PID/window keyboard write.
                            _post_mouse_drag(
                                [point],
                                target_pid=target_pid,
                                target_window_id=target_window_id,
                                target_window_rect=target_window_rect,
                                delay_seconds=0.04,
                                deactivate_after=True,
                            )
                        time.sleep(0.15)
                        result.update(
                            matched=True,
                            set=True,
                            method="focus_free_pid_targeted_keyboard",
                            readback=self._accessibility_numeric_readback_at_point(client, items, point),
                            keyboard_fallback_attempted=True,
                        )
                    results.append(result)
                    if settle_seconds > 0:
                        time.sleep(settle_seconds)

                    if result.get("method") == "focus_free_pid_targeted_keyboard":
                        try:
                            fallback_matches = math.isclose(
                                float(result["readback"]["value"]), float(text_value), abs_tol=0.011
                            )
                        except (KeyError, TypeError, ValueError):
                            fallback_matches = False
                        if not fallback_matches:
                            break
        except (PermissionError, RuntimeError) as exc:
            raise ColorPagePanelNotReady(
                "Failed to set DaVinci Resolve numeric fields through exact-PID Accessibility input.",
                details={"target_pid": target_pid, "target_window_id": target_window_id, "error": str(exc)},
            ) from exc
        return results

    def _finish_accessibility_value_at_point(
        self,
        point: tuple[int, int],
        text_value: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if isinstance(payload, dict) and payload.get("matched") and payload.get("set"):
            readback = payload.get("readback")
            readback_value = readback.get("value") if isinstance(readback, dict) else readback
            try:
                accessibility_matches = math.isclose(float(readback_value), float(text_value), abs_tol=0.011)
            except (TypeError, ValueError):
                accessibility_matches = False
            if accessibility_matches:
                payload.pop("errors", None)
                payload.setdefault("method", "focus_free_accessibility_value")
                payload["readback_matches_requested"] = True
                return payload
        raise ColorPagePanelNotReady(
            "DaVinci Resolve numeric field did not match the exact-PID input write.",
            details={
                "point": list(point),
                "text_value": text_value,
                "accessibility_attempt": payload,
                "readback": payload.get("readback") if isinstance(payload, dict) else None,
            },
        )

    def _set_accessibility_values_at_points(
        self,
        writes: list[dict[str, Any]],
        *,
        settle_seconds: float,
    ) -> list[dict[str, Any]]:
        if not writes:
            return []
        attempts = self._attempt_accessibility_values_at_points(writes, settle_seconds=settle_seconds)
        results: list[dict[str, Any]] = []
        for index, (row, attempt) in enumerate(zip(writes, attempts)):
            point = (int(row["point"][0]), int(row["point"][1]))
            text_value = str(row["text_value"])
            try:
                result = self._finish_accessibility_value_at_point(point, text_value, attempt)
            except ColorPagePanelNotReady as exc:
                exc.details = {
                    **exc.details,
                    "failed_index": index,
                    "completed_results": results,
                    "accessibility_attempts": attempts,
                }
                raise
            results.append(result)
        if len(results) != len(writes):
            raise ColorPagePanelNotReady(
                "Exact-PID numeric input stopped before completing the requested batch.",
                details={
                    "failed_index": len(results),
                    "completed_results": results,
                    "accessibility_attempts": attempts,
                },
            )
        return results

    def _accessibility_numeric_readback_at_point(
        self,
        client: Any,
        items: list[int],
        point: tuple[int, int],
    ) -> dict[str, Any]:
        candidates = self._accessibility_candidates_at_point(client, items, point)
        numeric = []
        for row in candidates:
            try:
                float(client.scalar_text(row["item"]))
            except (TypeError, ValueError):
                continue
            numeric.append(row)
        numeric.sort(key=lambda row: row["area"])
        if not numeric:
            return {}
        selected = numeric[0]
        return {
            "role": selected["role"],
            "value": client.scalar_text(selected["item"]),
            "position": selected["position"],
            "size": selected["size"],
        }

    def _read_accessibility_value_at_point(self, point: tuple[int, int]) -> dict[str, Any]:
        try:
            with self._exact_pid_accessibility_items() as (client, items):
                return self._accessibility_numeric_readback_at_point(client, items, point)
        except (PermissionError, RuntimeError, ColorPagePanelNotReady) as exc:
            return {"ok": False, "error": str(exc)}

    def _panel_control_bounds(self, panel: str) -> dict[str, float] | None:
        try:
            window_rect = self.find_resolve_window()
        except Exception:
            return None
        relative_ranges = {
            "qualifier": (0.61, 0.98),
            "power_window": (0.53, 0.92),
            "primary": (0.53, 0.98),
        }
        rel_min, rel_max = relative_ranges.get(panel, (0.0, 1.0))
        return {
            "xMin": float(window_rect.x - 8),
            "xMax": float(window_rect.x + window_rect.width + 8),
            "yMin": float(window_rect.y + window_rect.height * rel_min),
            "yMax": float(window_rect.y + window_rect.height * rel_max),
        }

    def detect_blocking_permission_prompt(self) -> dict[str, Any]:
        """Detect macOS privacy prompts that can sit above DaVinci Resolve.

        These prompts belong to the automation host process, not DaVinci Resolve,
        so normal DaVinci Resolve window checks can still pass while all
        subsequent clicks and proof screenshots are blocked.
        """
        script = r"""
const se = Application("System Events");
const candidateNames = ["Codex", "Python", "Terminal", "iTerm2", "osascript"];
let processes = [];
for (const name of candidateNames) {
  try {
    const matches = se.applicationProcesses.whose({ name })();
    for (let i = 0; i < matches.length; i++) processes.push(matches[i]);
  } catch (e) {}
}
const prompts = [];
for (let p = 0; p < processes.length; p++) {
  const proc = processes[p];
  let processName = "";
  try { processName = String(proc.name() || ""); } catch (e) {}
  let windows = [];
  try { windows = proc.windows(); } catch (e) { windows = []; }
  for (let w = 0; w < windows.length; w++) {
    const root = windows[w];
    const queue = [root];
    let scanned = 0;
    const texts = [];
    let allowButton = false;
    let denyButton = false;
    while (queue.length && scanned < 260) {
      const item = queue.shift();
      scanned += 1;
      let role = "";
      try { role = String(item.role() || ""); } catch (e) {}
      for (const getter of ["name", "description", "value", "title"]) {
        try {
          const value = item[getter]();
          if (value !== undefined && value !== null && String(value) !== "") {
            const text = String(value);
            texts.push(text);
            const lower = text.toLowerCase();
            if (role === "AXButton" && lower === "allow") allowButton = true;
            if (role === "AXButton" && (lower === "don't allow" || lower === "dont allow")) denyButton = true;
          }
        } catch (e) {}
      }
      try {
        const children = item.uiElements();
        for (let i = 0; i < children.length; i++) queue.push(children[i]);
      } catch (e) {}
    }
    const joined = texts.join(" ").toLowerCase();
    if (
      joined.includes("would like to access data from other apps") ||
      (allowButton && denyButton && joined.includes("privacy"))
    ) {
      let position = null;
      let size = null;
      try { position = root.position(); } catch (e) {}
      try { size = root.size(); } catch (e) {}
      prompts.push({
        process_name: processName,
        position,
        size,
        allow_button: allowButton,
        deny_button: denyButton,
        text: texts.slice(0, 20),
      });
    }
  }
}
JSON.stringify({ blocked: prompts.length > 0, prompts });
"""
        proc = _run_osascript(script, language="JavaScript", timeout=3.0)
        if proc.returncode != 0:
            return {
                "blocked": False,
                "probe_error": proc.stderr[-500:],
            }
        try:
            payload = json.loads(proc.stdout.strip() or "{}")
        except json.JSONDecodeError:
            return {
                "blocked": False,
                "probe_error": "invalid_json",
                "stdout": proc.stdout[-500:],
            }
        return payload if isinstance(payload, dict) else {"blocked": False}

    def assert_no_blocking_permission_prompt(self, *, stage: str) -> None:
        prompt = self.detect_blocking_permission_prompt()
        if not bool(prompt.get("blocked")):
            return
        raise ColorPagePanelNotReady(
            "A macOS privacy permission prompt is blocking the DaVinci Resolve Color Page GUI route.",
            details={
                "reason": "macos_privacy_prompt_blocking_resolve_gui",
                "stage": stage,
                "prompt": prompt,
                "required_user_action": (
                    "Approve or dismiss the visible macOS prompt manually, then rerun the command. "
                    "The route must not click Allow automatically without explicit user approval."
                ),
            },
        )

    def ensure_qualifier_panel(self) -> dict[str, Any]:
        self.assert_no_blocking_permission_prompt(stage="before_qualifier_panel")
        clicked = self._click_accessibility_exact_description("Qualifier")
        toolbar_clicked = False
        time.sleep(0.25)
        rows = self.collect_qualifier_panel_controls()
        summary = _summarize_qualifier_probe_controls(_annotate_qualifier_control_rows(rows))
        panel_state = self._qualifier_panel_state(rows, summary)
        if (not panel_state["qualifier_active"] or panel_state["looks_like_other_panel"]) and not toolbar_clicked:
            toolbar_clicked = self._click_qualifier_toolbar_fallback()
            if toolbar_clicked:
                rows = self.collect_qualifier_panel_controls()
                summary = _summarize_qualifier_probe_controls(_annotate_qualifier_control_rows(rows))
                panel_state = self._qualifier_panel_state(rows, summary)
        labels = [str(row.get("description") or row.get("name") or row.get("title") or "") for row in rows]
        found = {
            "Qualifier": self._accessibility_text_exists("Qualifier"),
            "Hue": any(str(row.get("name") or row.get("description") or "").lower() == "hue" for row in rows),
            "Sat": any(str(row.get("name") or row.get("description") or "").lower() in {"sat", "saturation"} for row in rows),
        }
        if not panel_state["qualifier_active"] or panel_state["looks_like_other_panel"]:
            raise ColorPagePanelNotReady(
                "Open the DaVinci Resolve Color page Qualifier palette before running qualifier GUI probing.",
                details={
                    "searched": ["Qualifier"],
                    "found": found,
                    "clicked": clicked,
                    "toolbar_clicked": toolbar_clicked,
                    **panel_state,
                    "labels": labels[:80],
                    "summary": summary,
                },
            )
        self.assert_no_blocking_permission_prompt(stage="after_qualifier_panel")
        return {"panel": "Qualifier", "clicked": clicked, "toolbar_clicked": toolbar_clicked, "found": found}

    def ensure_power_window_tracker_panel(self, shape: str) -> dict[str, Any]:
        self.assert_no_blocking_permission_prompt(stage="before_power_window_tracker_panel")
        labels = ["Window", "Tracker"]
        clicked = {
            "window": self._click_color_palette_toolbar_checkbox("Window"),
            "tracker": self._click_color_palette_toolbar_checkbox("Tracker"),
        }
        time.sleep(0.35)
        found = {label: self._accessibility_text_exists(label) for label in labels}
        if not (found.get("Window") and found.get("Tracker")):
            raise ColorPagePanelNotReady(
                "Open the DaVinci Resolve Color page Window palette and Tracker controls before running Power Window tracking.",
                details={"searched": labels, "found": found, "clicked": clicked, "shape": shape},
            )
        self.assert_no_blocking_permission_prompt(stage="after_power_window_tracker_panel")
        return {"panel": "Window/Tracker", "shape": shape, "found": found, "clicked": clicked}

    def ensure_power_window_panel(self, shape: str) -> dict[str, Any]:
        self.assert_no_blocking_permission_prompt(stage="before_power_window_panel")
        clicked = self._click_color_palette_toolbar_checkbox("Window")
        time.sleep(0.35)
        rows = self.collect_power_window_panel_controls()
        summary = _summarize_power_window_panel_controls(rows)
        shape_label = POWER_WINDOW_GUI_SHAPE_LABELS.get(shape, shape.title())
        if not summary.get("panel_active") or shape_label not in summary.get("shape_buttons", []):
            raise ColorPagePanelNotReady(
                "Open the DaVinci Resolve Color page Window palette before running Power Window GUI set.",
                details={
                    "shape": shape,
                    "shape_label": shape_label,
                    "clicked": clicked,
                    "summary": summary,
                    "labels": summary.get("labels", [])[:80],
                },
            )
        self.assert_no_blocking_permission_prompt(stage="after_power_window_panel")
        return {"panel": "Window", "shape": shape, "shape_label": shape_label, "clicked": clicked, "summary": summary}

    def ensure_primary_wheels_panel(self) -> dict[str, Any]:
        self.assert_no_blocking_permission_prompt(stage="before_primary_wheels_panel")
        toolbar_clicked = self._click_color_palette_toolbar_checkbox("Color Wheels")
        subpanel_clicked = self._click_primary_wheels_subpanel_checkbox()
        time.sleep(0.35)
        rows = self.collect_primary_panel_controls()
        summary = _summarize_primary_panel_controls(rows)
        if not summary.get("panel_active"):
            raise ColorPagePanelNotReady(
                "Open the DaVinci Resolve Color page Primaries - Color Wheels palette before running Primaries GUI set.",
                details={
                    "searched": ["Color Wheels", "Primaries - Color Wheels", *PRIMARY_GUI_LABELS.values()],
                    "clicked": toolbar_clicked or subpanel_clicked,
                    "toolbar_clicked": toolbar_clicked,
                    "subpanel_clicked": subpanel_clicked,
                    "summary": summary,
                    "labels": summary.get("labels", [])[:80],
                },
            )
        self.assert_no_blocking_permission_prompt(stage="after_primary_wheels_panel")
        return {
            "panel": "Primaries - Color Wheels",
            "clicked": toolbar_clicked or subpanel_clicked,
            "toolbar_clicked": toolbar_clicked,
            "subpanel_clicked": subpanel_clicked,
            "summary": summary,
        }

    def track_power_window(self, direction: str) -> dict[str, Any]:
        self.assert_no_blocking_permission_prompt(stage="before_power_window_track")
        clicked: list[str] = []
        if direction in {"backward", "both"}:
            if self._click_first_exact_description(["Track Reverse", "Track Backward"]) or self._click_first_label(
                ["Track Backward", "Track Reverse", "Reverse Track"]
            ) or self._click_first_exact_description(["Play Reverse"]):
                clicked.append("backward")
            else:
                raise ColorPageTrackFailed(
                    "Color Page Power Window backward tracking button was not found.",
                    details={
                        "direction": direction,
                        "searched": ["Track Backward", "Track Reverse", "Reverse Track", "Play Reverse"],
                    },
                )
        if direction in {"forward", "both"}:
            if self._click_first_exact_description(["Track Forward"]) or self._click_first_label(
                ["Track Forward", "Play Forward"]
            ) or self._click_first_exact_description(["Play"]):
                clicked.append("forward")
            else:
                raise ColorPageTrackFailed(
                    "Color Page Power Window forward tracking button was not found.",
                    details={"direction": direction, "searched": ["Track Forward", "Play Forward", "Play"]},
                )
        self.assert_no_blocking_permission_prompt(stage="after_power_window_track")
        return {"track_clicked": True, "direction": direction, "clicked": clicked}

    def _qualifier_panel_state(self, rows: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
        panel_text = json.dumps(rows).lower()
        labels = [str(label or "").strip().lower() for label in summary.get("labels") or []]
        label_set = {label for label in labels if label}
        has_hsl_panel_title = any(label.startswith("qualifier") and "hsl" in label for label in label_set) or "hsl" in label_set
        has_hsl_panel_rows = bool(summary.get("has_hsl_labels")) and bool(
            {"luminance", "lum", "luma", "matte finesse", "clean black", "clean white", "blur radius"}.intersection(label_set)
        )
        write_supported_in_qualifier_context = (
            (summary.get("hsl_gui_write_supported") is True or summary.get("matte_refinement_gui_write_supported") is True)
            and (has_hsl_panel_title or has_hsl_panel_rows or summary.get("has_qualifier_structure") is True)
        )
        has_qualifier_specific_structure = (
            has_hsl_panel_title
            or has_hsl_panel_rows
            or write_supported_in_qualifier_context
        )
        looks_like_other_panel = (not has_qualifier_specific_structure) and any(
            marker in panel_text
            for marker in (
                "high dynamic range",
                "color wheels",
                "hdr",
                "keyframes",
                "zones graph",
                "tracker - window",
                "track forward",
                "track reverse",
            )
        )
        qualifier_active = has_qualifier_specific_structure or ("keyer" in panel_text and not looks_like_other_panel)
        return {
            "qualifier_active": qualifier_active,
            "looks_like_other_panel": looks_like_other_panel,
            "has_hsl_panel_title": has_hsl_panel_title,
            "has_hsl_panel_rows": has_hsl_panel_rows,
        }

    def _click_qualifier_toolbar_fallback(self) -> bool:
        return self._click_color_palette_toolbar_checkbox("Qualifier")

    def _click_color_palette_toolbar_checkbox(self, label: str) -> bool:
        rect = self._find_color_palette_toolbar_checkbox(label)
        if rect is None:
            return False
        point = (int(round(rect.x + rect.width / 2.0)), int(round(rect.y + rect.height / 2.0)))
        try:
            self._post_focus_free_mouse_drag([point], delay_seconds=0.08)
        except Exception:
            return False
        time.sleep(0.4)
        return True

    def _click_primary_wheels_subpanel_checkbox(self) -> bool:
        rect = self._find_primary_wheels_subpanel_checkbox()
        if rect is None:
            return False
        point = (int(round(rect.x + rect.width / 2.0)), int(round(rect.y + rect.height / 2.0)))
        try:
            self._post_focus_free_mouse_drag([point], delay_seconds=0.08)
        except Exception:
            return False
        time.sleep(0.3)
        return True

    def _find_primary_wheels_subpanel_checkbox(self) -> Rect | None:
        try:
            window_rect = self.find_resolve_window()
        except Exception:
            window_rect = None
        script = f"""
const se = Application("System Events");
const processNames = {json.dumps(self._process_names_payload())};
let matches = [];
for (const name of processNames) {{
  matches = se.processes.whose({{ name }})();
  if (matches.length > 0) break;
}}
let candidates = [];
if (matches.length > 0) {{
  const queue = matches[0].windows();
  let scanned = 0;
  while (queue.length && scanned < 3000) {{
    const item = queue.shift();
    scanned += 1;
    let role = "";
    let description = "";
    let position = null;
    let size = null;
    try {{ role = String(item.role() || ""); }} catch (e) {{}}
    try {{ description = String(item.description() || ""); }} catch (e) {{}}
    try {{ position = item.position(); }} catch (e) {{}}
    try {{ size = item.size(); }} catch (e) {{}}
    if (role === "AXCheckBox" && description === "Color Wheels" && position && size) {{
      const x = Number(position[0]);
      const y = Number(position[1]);
      const width = Number(size[0]);
      const height = Number(size[1]);
      if (Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(width) && Number.isFinite(height)) {{
        candidates.push({{ x, y, width, height, scanned }});
      }}
    }}
    try {{
      const children = item.uiElements();
      for (let i = 0; i < children.length; i++) queue.push(children[i]);
    }} catch (e) {{}}
  }}
}}
JSON.stringify(candidates);
"""
        proc = _run_osascript(script, language="JavaScript", timeout=10.0)
        if proc.returncode != 0:
            return None
        try:
            payload = json.loads(proc.stdout.strip() or "[]")
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, list):
            return None
        candidates: list[Rect] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            try:
                rect = Rect(
                    x=int(round(float(item["x"]))),
                    y=int(round(float(item["y"]))),
                    width=int(round(float(item["width"]))),
                    height=int(round(float(item["height"]))),
                )
            except (KeyError, TypeError, ValueError):
                continue
            if rect.width <= 0 or rect.height <= 0:
                continue
            if rect.width > 34 or rect.height > 34:
                continue
            if window_rect is not None:
                center_y = rect.y + rect.height / 2.0
                min_y = window_rect.y + window_rect.height * 0.60
                max_y = window_rect.y + window_rect.height * 0.74
                if center_y < min_y or center_y > max_y:
                    continue
            candidates.append(rect)
        if not candidates:
            return None
        return min(candidates, key=lambda rect: (rect.y, rect.x))

    def _find_color_palette_toolbar_checkbox(self, label: str) -> Rect | None:
        target = str(label or "").strip()
        if not target:
            return None
        try:
            window_rect = self.find_resolve_window()
        except Exception:
            window_rect = None
        script = f"""
const target = {json.dumps(target)};
const se = Application("System Events");
const processNames = {json.dumps(self._process_names_payload())};
let matches = [];
for (const name of processNames) {{
  matches = se.processes.whose({{ name }})();
  if (matches.length > 0) break;
}}
let result = null;
if (matches.length > 0) {{
  const queue = matches[0].windows();
  let scanned = 0;
  while (queue.length && scanned < 2200 && result === null) {{
    const item = queue.shift();
    scanned += 1;
    let role = "";
    let description = "";
    let position = null;
    let size = null;
    try {{ role = String(item.role() || ""); }} catch (e) {{}}
    try {{ description = String(item.description() || ""); }} catch (e) {{}}
    try {{ position = item.position(); }} catch (e) {{}}
    try {{ size = item.size(); }} catch (e) {{}}
    if (role === "AXCheckBox" && description === target && position && size) {{
      const x = Number(position[0]);
      const y = Number(position[1]);
      const width = Number(size[0]);
      const height = Number(size[1]);
      if (Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(width) && Number.isFinite(height)) {{
        result = {{ x, y, width, height, scanned }};
        break;
      }}
    }}
    try {{
      const children = item.uiElements();
      for (let i = 0; i < children.length; i++) queue.push(children[i]);
    }} catch (e) {{}}
  }}
}}
JSON.stringify(result);
"""
        proc = _run_osascript(script, language="JavaScript", timeout=10.0)
        if proc.returncode != 0:
            return None
        try:
            payload = json.loads(proc.stdout.strip() or "null")
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        try:
            rect = Rect(
                x=int(round(float(payload["x"]))),
                y=int(round(float(payload["y"]))),
                width=int(round(float(payload["width"]))),
                height=int(round(float(payload["height"]))),
            )
        except (KeyError, TypeError, ValueError):
            return None
        if window_rect is not None:
            if rect.width <= 0 or rect.height <= 0:
                return None
            if rect.x < window_rect.x - 4 or rect.x > window_rect.x + window_rect.width + 4:
                return None
            lower_toolbar_min_y = window_rect.y + window_rect.height * 0.55
            lower_toolbar_max_y = window_rect.y + window_rect.height * 0.72
            center_y = rect.y + rect.height / 2.0
            if center_y < lower_toolbar_min_y or center_y > lower_toolbar_max_y:
                return None
        return rect

    def collect_qualifier_panel_controls(self) -> list[dict[str, Any]]:
        panel_bounds = self._panel_control_bounds("qualifier")
        target_window = self._focus_free_ax_window_target()
        script = f"""
	const se = Application("System Events");
	const targetWindow = {json.dumps(target_window)};
	const panelBounds = {json.dumps(panel_bounds)};
	function intersectsPanelBounds(position, size) {{
	  if (!position || !size || !panelBounds) return true;
	  const x = Number(position[0]);
	  const y = Number(position[1]);
	  const width = Number(size[0]);
	  const height = Number(size[1]);
	  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(width) || !Number.isFinite(height)) return true;
	  if (width <= 0 || height <= 0) return false;
	  return (x + width) >= panelBounds.xMin &&
	    x <= panelBounds.xMax &&
	    (y + height) >= panelBounds.yMin &&
	    y <= panelBounds.yMax;
	}}
	function withinPanelBounds(position, size) {{
	  if (!position || !size) return false;
	  if (!panelBounds) return true;
	  const x = Number(position[0]);
	  const y = Number(position[1]);
	  const width = Number(size[0]);
	  const height = Number(size[1]);
	  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(width) || !Number.isFinite(height)) return false;
	  const centerX = x + width / 2.0;
	  const centerY = y + height / 2.0;
	  return centerX >= panelBounds.xMin && centerX <= panelBounds.xMax && centerY >= panelBounds.yMin && centerY <= panelBounds.yMax;
	}}
	const matches = se.applicationProcesses.whose({{ unixId: targetWindow.pid }})();
const rows = [];
const settableRoles = new Set({json.dumps(sorted(SETTABLE_CONTROL_ROLES))});
const pressableRoles = new Set({json.dumps(sorted(PRESSABLE_CONTROL_ROLES))});
if (matches.length > 0) {{
  const roots = matches[0].windows().filter(win => {{
    try {{
      const name = String(win.name() || "");
      const position = win.position();
      const size = win.size();
      return name === targetWindow.name &&
        Math.abs(Number(position[0]) - targetWindow.x) <= 3 &&
        Math.abs(Number(position[1]) - targetWindow.y) <= 3 &&
        Math.abs(Number(size[0]) - targetWindow.width) <= 3 &&
        Math.abs(Number(size[1]) - targetWindow.height) <= 3;
    }} catch (e) {{ return false; }}
  }});
  let elements = [];
  if (roots.length === 1) {{
    try {{ elements = [roots[0], ...roots[0].entireContents.get()]; }} catch (e) {{ elements = []; }}
  }}
  for (let index = 0; index < elements.length; index += 1) {{
    const item = elements[index];
    const scanned = index + 1;
    let position = null;
	    let size = null;
	    let properties = {{}};
	    try {{ properties = item.properties(); }} catch (e) {{}}
	    position = properties.position || null;
	    size = properties.size || null;
	    if (withinPanelBounds(position, size)) {{
	      let row = {{ scanned, position, size }};
      for (const key of ["role", "subrole", "name", "description", "value", "title", "help", "enabled"]) {{
        const value = properties[key];
        if (value !== undefined && value !== null && String(value) !== "") row[key] = String(value);
      }}
      row.actions = [];
      const text = JSON.stringify(row).toLowerCase();
      const role = String(row.role || "");
      if (
        settableRoles.has(role) ||
        pressableRoles.has(role) ||
        row.actions.includes("AXPress") ||
        text.includes("qual") ||
        text.includes("hue") ||
        text.includes("sat") ||
        text.includes("lum") ||
        text.includes("blur") ||
        text.includes("clean") ||
        text.includes("denoise") ||
        text.includes("matte") ||
        text.includes("soft") ||
        text.includes("width") ||
        text.includes("falloff") ||
        text.includes("high dynamic") ||
        text.includes("color wheels") ||
        text.includes("keyer") ||
        text.includes("picker")
      ) {{
        rows.push(row);
      }}
    }}
	  }}
	}}
	JSON.stringify(rows.slice(0, 240));
"""
        proc = _run_osascript(script, language="JavaScript", timeout=30.0)
        if proc.returncode != 0:
            raise ColorPagePanelNotReady(
                "Failed to inspect DaVinci Resolve Qualifier panel controls through macOS Accessibility.",
                details={"stderr": proc.stderr[-500:]},
            )
        try:
            payload = json.loads(proc.stdout.strip() or "[]")
        except json.JSONDecodeError as exc:
            raise ColorPagePanelNotReady(
                "DaVinci Resolve Qualifier panel probe returned invalid JSON.",
                details={"stdout": proc.stdout[-500:]},
            ) from exc
        return payload if isinstance(payload, list) else []

    def collect_power_window_panel_controls(self) -> list[dict[str, Any]]:
        panel_bounds = self._panel_control_bounds("power_window")
        target_window = self._focus_free_ax_window_target()
        script = f"""
	const se = Application("System Events");
	const targetWindow = {json.dumps(target_window)};
	const panelBounds = {json.dumps(panel_bounds)};
	function intersectsPanelBounds(position, size) {{
	  if (!position || !size || !panelBounds) return true;
	  const x = Number(position[0]);
	  const y = Number(position[1]);
	  const width = Number(size[0]);
	  const height = Number(size[1]);
	  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(width) || !Number.isFinite(height)) return true;
	  if (width <= 0 || height <= 0) return false;
	  return (x + width) >= panelBounds.xMin && x <= panelBounds.xMax &&
	    (y + height) >= panelBounds.yMin && y <= panelBounds.yMax;
	}}
	function withinPanelBounds(position, size) {{
	  if (!position || !size) return false;
	  if (!panelBounds) return true;
	  const x = Number(position[0]);
	  const y = Number(position[1]);
	  const width = Number(size[0]);
	  const height = Number(size[1]);
	  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(width) || !Number.isFinite(height)) return false;
	  const centerX = x + width / 2.0;
	  const centerY = y + height / 2.0;
	  return centerX >= panelBounds.xMin && centerX <= panelBounds.xMax && centerY >= panelBounds.yMin && centerY <= panelBounds.yMax;
	}}
	const matches = se.applicationProcesses.whose({{ unixId: targetWindow.pid }})();
const rows = [];
if (matches.length > 0) {{
  const roots = matches[0].windows().filter(win => {{
    try {{
      const name = String(win.name() || "");
      const position = win.position();
      const size = win.size();
      return name === targetWindow.name &&
        Math.abs(Number(position[0]) - targetWindow.x) <= 3 &&
        Math.abs(Number(position[1]) - targetWindow.y) <= 3 &&
        Math.abs(Number(size[0]) - targetWindow.width) <= 3 &&
        Math.abs(Number(size[1]) - targetWindow.height) <= 3;
    }} catch (e) {{ return false; }}
  }});
  let elements = [];
  if (roots.length === 1) {{
    try {{ elements = [roots[0], ...roots[0].entireContents.get()]; }} catch (e) {{ elements = []; }}
  }}
  for (let index = 0; index < elements.length; index += 1) {{
    const item = elements[index];
    const scanned = index + 1;
    let position = null;
	    let size = null;
	    let properties = {{}};
	    try {{ properties = item.properties(); }} catch (e) {{}}
	    position = properties.position || null;
	    size = properties.size || null;
	    if (withinPanelBounds(position, size)) {{
	      let row = {{ scanned, position, size }};
      for (const key of ["role", "subrole", "name", "description", "value", "title", "help", "enabled"]) {{
        const value = properties[key];
        if (value !== undefined && value !== null && String(value) !== "") row[key] = String(value);
      }}
      row.actions = [];
      const text = JSON.stringify(row).toLowerCase();
      if (
        text.includes("window") ||
        text.includes("linear") ||
        text.includes("circle") ||
        text.includes("polygon") ||
        text.includes("curve") ||
        text.includes("gradient") ||
        text.includes("transform") ||
        text.includes("size") ||
        text.includes("aspect") ||
        text.includes("pan") ||
        text.includes("tilt") ||
        text.includes("rotate") ||
        text.includes("opacity") ||
        text.includes("soft") ||
        text.includes("inside") ||
        text.includes("outside") ||
        text.includes("delete") ||
        text.includes("reset")
      ) {{
        rows.push(row);
      }}
    }}
  }}
}}
JSON.stringify(rows.slice(0, 320));
"""
        proc = _run_osascript(script, language="JavaScript", timeout=20.0)
        if proc.returncode != 0:
            raise ColorPagePanelNotReady(
                "Failed to inspect DaVinci Resolve Window panel controls through macOS Accessibility.",
                details={"stderr": proc.stderr[-500:]},
            )
        try:
            payload = json.loads(proc.stdout.strip() or "[]")
        except json.JSONDecodeError as exc:
            raise ColorPagePanelNotReady(
                "DaVinci Resolve Window panel probe returned invalid JSON.",
                details={"stdout": proc.stdout[-500:]},
            ) from exc
        return payload if isinstance(payload, list) else []

    def collect_primary_panel_controls(self) -> list[dict[str, Any]]:
        panel_bounds = self._panel_control_bounds("primary")
        target_window = self._focus_free_ax_window_target()
        script = f"""
	const se = Application("System Events");
	const targetWindow = {json.dumps(target_window)};
	const panelBounds = {json.dumps(panel_bounds)};
	function intersectsPanelBounds(position, size) {{
	  if (!position || !size || !panelBounds) return true;
	  const x = Number(position[0]);
	  const y = Number(position[1]);
	  const width = Number(size[0]);
	  const height = Number(size[1]);
	  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(width) || !Number.isFinite(height)) return true;
	  if (width <= 0 || height <= 0) return false;
	  return (x + width) >= panelBounds.xMin && x <= panelBounds.xMax &&
	    (y + height) >= panelBounds.yMin && y <= panelBounds.yMax;
	}}
	function withinPanelBounds(position, size) {{
	  if (!position || !size) return false;
	  if (!panelBounds) return true;
	  const x = Number(position[0]);
	  const y = Number(position[1]);
	  const width = Number(size[0]);
	  const height = Number(size[1]);
	  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(width) || !Number.isFinite(height)) return false;
	  const centerX = x + width / 2.0;
	  const centerY = y + height / 2.0;
	  return centerX >= panelBounds.xMin && centerX <= panelBounds.xMax && centerY >= panelBounds.yMin && centerY <= panelBounds.yMax;
	}}
	const matches = se.applicationProcesses.whose({{ unixId: targetWindow.pid }})();
const rows = [];
if (matches.length > 0) {{
  const roots = matches[0].windows().filter(win => {{
    try {{
      const name = String(win.name() || "");
      const position = win.position();
      const size = win.size();
      return name === targetWindow.name &&
        Math.abs(Number(position[0]) - targetWindow.x) <= 3 &&
        Math.abs(Number(position[1]) - targetWindow.y) <= 3 &&
        Math.abs(Number(size[0]) - targetWindow.width) <= 3 &&
        Math.abs(Number(size[1]) - targetWindow.height) <= 3;
    }} catch (e) {{ return false; }}
  }});
  let elements = [];
  if (roots.length === 1) {{
    try {{ elements = [roots[0], ...roots[0].entireContents.get()]; }} catch (e) {{ elements = []; }}
  }}
  for (let index = 0; index < elements.length; index += 1) {{
    const item = elements[index];
    const scanned = index + 1;
    let position = null;
	    let size = null;
	    let properties = {{}};
	    try {{ properties = item.properties(); }} catch (e) {{}}
	    position = properties.position || null;
	    size = properties.size || null;
	    if (withinPanelBounds(position, size)) {{
	      let row = {{ scanned, position, size }};
      for (const key of ["role", "subrole", "name", "description", "value", "title", "help", "enabled"]) {{
        const value = properties[key];
        if (value !== undefined && value !== null && String(value) !== "") row[key] = String(value);
      }}
      const text = JSON.stringify(row).toLowerCase();
      if (
        text.includes("primaries") ||
        text.includes("color wheels") ||
        text.includes("temp") ||
        text.includes("tint") ||
        text.includes("contrast") ||
        text.includes("pivot") ||
        text.includes("mid/detail") ||
        text.includes("color boost") ||
        text.includes("shadows") ||
        text.includes("highlights") ||
        text.includes("saturation") ||
        text.includes("lum mix") ||
        text.includes("lift") ||
        text.includes("gamma") ||
        text.includes("gain") ||
        text.includes("offset")
      ) {{
        rows.push(row);
      }}
    }}
  }}
}}
JSON.stringify(rows.slice(0, 260));
"""
        proc = _run_osascript(script, language="JavaScript", timeout=20.0)
        if proc.returncode != 0:
            raise ColorPagePanelNotReady(
                "Failed to inspect DaVinci Resolve Primaries panel controls through macOS Accessibility.",
                details={"stderr": proc.stderr[-500:]},
            )
        try:
            payload = json.loads(proc.stdout.strip() or "[]")
        except json.JSONDecodeError as exc:
            raise ColorPagePanelNotReady(
                "DaVinci Resolve Primaries panel probe returned invalid JSON.",
                details={"stdout": proc.stdout[-500:]},
            ) from exc
        return payload if isinstance(payload, list) else []

    def set_primary_controls(self, controls: list[dict[str, Any]]) -> dict[str, Any]:
        self.assert_no_blocking_permission_prompt(stage="before_set_primary_controls")
        rows = self.collect_primary_panel_controls()
        numeric_controls = _infer_primary_numeric_controls(rows)
        missing = [row for row in controls if str(row.get("control") or "") not in numeric_controls]
        if missing:
            raise ColorPagePanelNotReady(
                "DaVinci Resolve Primaries numeric fields are not exposed for GUI writing.",
                details={
                    "requested_controls": controls,
                    "missing": missing,
                    "available_numeric_controls": sorted(numeric_controls),
                    "summary": _summarize_primary_panel_controls(rows),
                },
            )
        write_plan: list[dict[str, Any]] = []
        for control in controls:
            control_name = str(control.get("control") or "")
            field = numeric_controls[control_name]
            point = field["point"]
            text_value = _format_primary_gui_value(control_name, float(control["value"]))
            write_plan.append(
                {
                    "control": control,
                    "field": field,
                    "point": (int(point["x"]), int(point["y"])),
                    "text_value": text_value,
                }
            )
        input_results = self._set_accessibility_values_at_points(write_plan, settle_seconds=0.18)
        results: list[dict[str, Any]] = []
        for row, input_result in zip(write_plan, input_results, strict=True):
            control = row["control"]
            field = row["field"]
            control_name = str(control.get("control") or "")
            results.append(
                {
                    "control": control_name,
                    "label": field.get("label"),
                    "point": field["point"],
                    "value": control["value"],
                    "text_value": row["text_value"],
                    "matched": True,
                    "set": True,
                    "method": input_result.get("method", "focus_free_pid_window_targeted_input"),
                    "input": input_result,
                }
            )
        self.assert_no_blocking_permission_prompt(stage="after_set_primary_controls")
        return {"requested_controls": controls, "results": results, "method": "focus_free_pid_window_targeted_input"}

    def set_power_window_shape_and_controls(self, shape: str, controls: list[dict[str, Any]]) -> dict[str, Any]:
        self.assert_no_blocking_permission_prompt(stage="before_set_power_window_shape_and_controls")
        shape_label = POWER_WINDOW_GUI_SHAPE_LABELS.get(shape)
        if not shape_label:
            raise ColorPagePanelNotReady(
                "Unsupported DaVinci Resolve Power Window GUI shape.",
                details={"shape": shape, "supported_shapes": sorted(POWER_WINDOW_GUI_SHAPE_LABELS)},
            )
        shape_clicked = self._click_accessibility_exact_description(shape_label)
        if not shape_clicked:
            raise ColorPagePanelNotReady(
                "DaVinci Resolve Power Window shape button was not found.",
                details={"shape": shape, "shape_label": shape_label},
            )
        time.sleep(0.45)
        rows = self.collect_power_window_panel_controls()
        numeric_controls = _infer_power_window_numeric_controls(rows)
        missing = [row for row in controls if str(row.get("control") or "") not in numeric_controls]
        if missing:
            raise ColorPagePanelNotReady(
                "DaVinci Resolve Power Window numeric fields are not exposed for GUI writing.",
                details={
                    "shape": shape,
                    "shape_label": shape_label,
                    "requested_controls": controls,
                    "missing": missing,
                    "available_numeric_controls": sorted(numeric_controls),
                    "summary": _summarize_power_window_panel_controls(rows),
                },
            )
        write_plan: list[dict[str, Any]] = []
        for control in controls:
            control_name = str(control.get("control") or "")
            field = numeric_controls[control_name]
            point = field["point"]
            text_value = _format_power_window_gui_value(control_name, float(control["value"]))
            write_plan.append(
                {
                    "control": control,
                    "field": field,
                    "point": (int(point["x"]), int(point["y"])),
                    "text_value": text_value,
                }
            )
        input_results = self._set_accessibility_values_at_points(write_plan, settle_seconds=0.14)
        results: list[dict[str, Any]] = []
        for row, input_result in zip(write_plan, input_results, strict=True):
            control = row["control"]
            field = row["field"]
            control_name = str(control.get("control") or "")
            results.append(
                {
                    "control": control_name,
                    "label": field.get("label"),
                    "point": field["point"],
                    "value": control["value"],
                    "text_value": row["text_value"],
                    "matched": True,
                    "set": True,
                    "method": input_result.get("method", "focus_free_pid_window_targeted_input"),
                    "input": input_result,
                }
            )
        self.assert_no_blocking_permission_prompt(stage="after_set_power_window_shape_and_controls")
        return {
            "shape": shape,
            "shape_label": shape_label,
            "shape_clicked": shape_clicked,
            "requested_controls": controls,
            "results": results,
            "method": "focus_free_pid_window_targeted_input",
        }

    def set_qualifier_controls(self, controls: list[dict[str, Any]]) -> dict[str, Any]:
        self.assert_no_blocking_permission_prompt(stage="before_set_qualifier_controls")
        rows = _annotate_qualifier_control_rows(self.collect_qualifier_panel_controls())
        numeric_controls = _infer_qualifier_numeric_controls(rows)
        numeric_plan = _build_qualifier_numeric_write_plan(controls, numeric_controls)
        if numeric_plan:
            result = self._set_qualifier_numeric_controls(numeric_plan)
            self.assert_no_blocking_permission_prompt(stage="after_set_qualifier_controls")
            return result

        panel_bounds = self._panel_control_bounds("qualifier")
        script = f"""
	const se = Application("System Events");
	const processNames = {json.dumps(self._process_names_payload())};
	const controls = {json.dumps(controls)};
	const panelBounds = {json.dumps(panel_bounds)};
	function withinPanelBounds(position, size) {{
	  if (!position || !size) return false;
	  if (!panelBounds) return true;
	  const x = Number(position[0]);
	  const y = Number(position[1]);
	  const width = Number(size[0]);
	  const height = Number(size[1]);
	  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(width) || !Number.isFinite(height)) return false;
	  const centerX = x + width / 2.0;
	  const centerY = y + height / 2.0;
	  return centerX >= panelBounds.xMin && centerX <= panelBounds.xMax && centerY >= panelBounds.yMin && centerY <= panelBounds.yMax;
	}}
	let matches = [];
	for (const name of processNames) {{
	  matches = se.processes.whose({{ name }})();
	  if (matches.length > 0) break;
}}
const settableRoles = new Set({json.dumps(sorted(SETTABLE_CONTROL_ROLES))});
function asNumber(value, fallback) {{
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}}
function center(row) {{
  const position = row.position || [0, 0];
  const size = row.size || [0, 0];
  return {{
    x: asNumber(position[0], 0) + asNumber(size[0], 0) / 2,
    y: asNumber(position[1], 0) + asNumber(size[1], 0) / 2,
  }};
}}
function rowText(row) {{
  return [
    row.description,
    row.name,
    row.title,
    row.help,
    row.value,
    row.nearby_labels,
    row.semantic_text,
    row.semantic_control,
  ].filter(value => value !== undefined && value !== null).join(" ").toLowerCase();
}}
function ownRowText(row) {{
  return [
    row.description,
    row.name,
    row.title,
    row.help,
    row.value,
  ].filter(value => value !== undefined && value !== null).join(" ").toLowerCase();
}}
function semanticFamily(text) {{
  const lower = String(text || "").toLowerCase();
  if (/(clean[^a-z]+black|black[^a-z]+clean)/.test(lower)) return "clean_black";
  if (/(clean[^a-z]+white|white[^a-z]+clean)/.test(lower)) return "clean_white";
  if (/(^|[^a-z])blur([^a-z]|$)/.test(lower)) return "blur";
  if (/(^|[^a-z])(soft|softness)([^a-z]|$)/.test(lower)) return "softness";
  if (/(^|[^a-z])denoise([^a-z]|$)/.test(lower)) return "denoise";
  if (/(^|[^a-z])(grow|shrink)([^a-z]|$)/.test(lower)) return "grow_shrink";
  if (/(^|[^a-z])hue([^a-z]|$)/.test(lower)) return "hue";
  if (/(^|[^a-z])(sat|saturation)([^a-z]|$)/.test(lower)) return "saturation";
  if (/(^|[^a-z])(lum|luma|luminance)([^a-z]|$)/.test(lower)) return "luma";
  return null;
}}
function annotate(entries) {{
  const labels = entries.filter(entry => !settableRoles.has(String(entry.row.role || "")) && rowText(entry.row));
  for (const entry of entries) {{
    const row = entry.row;
    if (!settableRoles.has(String(row.role || ""))) continue;
    const c = center(row);
    const nearby = [];
    for (const label of labels) {{
      const lc = center(label.row);
      const text = rowText(label.row).trim();
      if (!text) continue;
      const vertical = Math.abs(lc.y - c.y);
      const horizontal = Math.abs(lc.x - c.x);
      const rowSize = row.size || [0, 0];
      const leftish = lc.x <= c.x + Math.max(24, asNumber(rowSize[0], 0) * 0.35);
      if ((vertical <= 28 && horizontal <= 420) || (vertical <= 70 && leftish && horizontal <= 360)) {{
        nearby.push({{ text, distance: vertical * 4 + horizontal }});
      }}
    }}
    nearby.sort((a, b) => a.distance - b.distance);
    row.nearby_labels = nearby.slice(0, 6).map(item => item.text);
    row.primary_label = row.nearby_labels[0] || "";
    row.semantic_text = [ownRowText(row), row.primary_label].filter(Boolean).join(" ").toLowerCase();
  }}
  const groups = {{}};
  for (const entry of entries) {{
    const row = entry.row;
    if (!settableRoles.has(String(row.role || ""))) continue;
    const family = semanticFamily(row.semantic_text || rowText(row));
    if (!family) continue;
    if (!groups[family]) groups[family] = [];
    groups[family].push(entry);
  }}
  for (const family of ["hue", "saturation", "luma"]) {{
    const group = groups[family] || [];
    group.sort((a, b) => center(a.row).x - center(b.row).x || center(a.row).y - center(b.row).y);
    for (let index = 0; index < group.length; index += 1) {{
      const row = group[index].row;
      const text = rowText(row);
      if (/(^|[^a-z])low([^a-z]|$)/.test(text)) row.semantic_control = family + "_low";
      else if (/(^|[^a-z])high([^a-z]|$)/.test(text)) row.semantic_control = family + "_high";
      else if (index === 0) row.semantic_control = family + "_low";
      else if (index === 1) row.semantic_control = family + "_high";
      else if (!row.semantic_control) row.semantic_control = family + "_" + String(index + 1);
      row.semantic_text = [ownRowText(row), row.primary_label, row.semantic_control].filter(Boolean).join(" ").toLowerCase();
    }}
  }}
  for (const family of ["softness", "blur", "clean_black", "clean_white", "denoise", "grow_shrink"]) {{
    const group = groups[family] || [];
    group.sort((a, b) => center(a.row).x - center(b.row).x || center(a.row).y - center(b.row).y);
    for (const entry of group) {{
      if (!entry.row.semantic_control) entry.row.semantic_control = family;
      entry.row.semantic_text = [ownRowText(entry.row), entry.row.primary_label, entry.row.semantic_control].filter(Boolean).join(" ").toLowerCase();
    }}
  }}
  return entries;
}}
function collectEntries(process) {{
  const entries = [];
  const queue = process.windows();
  let scanned = 0;
  while (queue.length && scanned < 3500) {{
    const item = queue.shift();
    scanned += 1;
    let position = null;
    let size = null;
    try {{ position = item.position(); }} catch (e) {{}}
    try {{ size = item.size(); }} catch (e) {{}}
    let row = {{ scanned, position, size }};
	    for (const getter of ["role", "subrole", "name", "description", "value", "title", "help", "enabled"]) {{
	      try {{
	        const value = item[getter]();
	        if (value !== undefined && value !== null && String(value) !== "") row[getter] = String(value);
	      }} catch (e) {{}}
	    }}
	    if (withinPanelBounds(position, size)) {{
	      entries.push({{ item, row }});
	    }}
    try {{
      const children = item.uiElements();
      for (let i = 0; i < children.length; i++) queue.push(children[i]);
    }} catch (e) {{}}
  }}
  return annotate(entries);
}}
const results = [];
if (matches.length > 0) {{
  const entries = collectEntries(matches[0]);
  for (const control of controls) {{
    const wanted = (control.terms || []).map(term => String(term).toLowerCase());
    let result = {{ control: control.control, terms: wanted, value: control.value, matched: false, set: false }};
    for (const entry of entries) {{
      const item = entry.item;
      const row = entry.row;
      const role = String(row.role || "");
      const lower = rowText(row);
      if (settableRoles.has(role) && (row.semantic_control === control.control || wanted.every(term => lower.includes(term)))) {{
        result.matched = true;
        result.role = role;
        result.label = lower.trim();
        result.semantic_control = row.semantic_control || null;
        result.position = row.position;
        result.size = row.size;
        const targetValue = Number(control.value);
        const errors = [];
        try {{
          item.value = targetValue;
          result.set = true;
        }} catch (e) {{
          errors.push(String(e));
        }}
        if (!result.set) {{
          try {{
            item.value = String(control.value);
            result.set = true;
          }} catch (e) {{
            errors.push(String(e));
          }}
        }}
        if (!result.set) result.errors = errors.slice(-3);
        break;
      }}
    }}
    results.push(result);
  }}
}}
JSON.stringify({{ results }});
"""
        proc = _run_osascript(script, language="JavaScript", timeout=20.0)
        if proc.returncode != 0:
            raise ColorPagePanelNotReady(
                "Failed to set DaVinci Resolve Qualifier HSL controls through macOS Accessibility.",
                details={"stderr": proc.stderr[-500:]},
            )
        try:
            payload = json.loads(proc.stdout.strip() or "{}")
        except json.JSONDecodeError as exc:
            raise ColorPagePanelNotReady(
                "DaVinci Resolve Qualifier HSL set returned invalid JSON.",
                details={"stdout": proc.stdout[-500:]},
            ) from exc
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            results = []
        missing = [row for row in results if not row.get("matched")]
        failed = [row for row in results if row.get("matched") and not row.get("set")]
        if len(results) != len(controls) or missing or failed:
            raise ColorPagePanelNotReady(
                "DaVinci Resolve Qualifier controls were not safely set through macOS Accessibility.",
                details={"requested_controls": controls, "results": results, "missing": missing, "failed": failed},
            )
        self.assert_no_blocking_permission_prompt(stage="after_set_qualifier_controls")
        return {"requested_controls": controls, "results": results}

    def set_qualifier_hsl_controls(self, controls: list[dict[str, Any]]) -> dict[str, Any]:
        return self.set_qualifier_controls(controls)

    def _set_qualifier_numeric_controls(self, write_plan: list[dict[str, Any]]) -> dict[str, Any]:
        batch_writes: list[dict[str, Any]] = []
        for row in write_plan:
            point = row.get("point") if isinstance(row.get("point"), dict) else {}
            try:
                x = int(point["x"])
                y = int(point["y"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ColorPagePanelNotReady(
                    "DaVinci Resolve Qualifier numeric field did not have a safe click point.",
                    details={"row": row},
                ) from exc
            text_value = str(row.get("text_value") or row.get("value") or "")
            batch_writes.append({"point": (x, y), "text_value": text_value})
        input_results = self._set_accessibility_values_at_points(batch_writes, settle_seconds=0.18)
        results: list[dict[str, Any]] = []
        for row, input_result in zip(write_plan, input_results, strict=True):
            point = row.get("point") if isinstance(row.get("point"), dict) else {}
            text_value = str(row.get("text_value") or row.get("value") or "")
            results.append(
                {
                    "control": row.get("control"),
                    "label": row.get("label"),
                    "point": point,
                    "value": row.get("value"),
                    "text_value": text_value,
                    "matched": True,
                    "set": True,
                    "method": input_result.get("method", "focus_free_pid_window_targeted_input"),
                    "input": input_result,
                }
            )
        return {"requested_controls": write_plan, "results": results, "method": "focus_free_pid_window_targeted_input"}

    def _click_first_label(self, labels: list[str]) -> bool:
        for label in labels:
            if self._click_accessibility_label(label):
                return True
        return False

    def _click_first_exact_description(self, labels: list[str]) -> bool:
        for label in labels:
            if self._click_accessibility_exact_description(label):
                return True
        return False

    def _click_accessibility_exact_description(self, label: str) -> bool:
        target_window = self._focus_free_ax_window_target()
        script = f"""
const target = {json.dumps(str(label))};
const se = Application("System Events");
const targetWindow = {json.dumps(target_window)};
const matches = se.applicationProcesses.whose({{ unixId: targetWindow.pid }})();
let clicked = false;
if (matches.length > 0) {{
  const roots = matches[0].windows().filter(win => {{
    try {{
      const position = win.position(); const size = win.size();
      return String(win.name() || "") === targetWindow.name &&
        Math.abs(Number(position[0]) - targetWindow.x) <= 3 && Math.abs(Number(position[1]) - targetWindow.y) <= 3 &&
        Math.abs(Number(size[0]) - targetWindow.width) <= 3 && Math.abs(Number(size[1]) - targetWindow.height) <= 3;
    }} catch (e) {{ return false; }}
  }});
  const queue = roots.length === 1 ? [roots[0]] : [];
  let scanned = 0;
  while (queue.length && scanned < 1500 && !clicked) {{
    const item = queue.shift();
    scanned += 1;
    let role = "";
    let description = "";
    try {{ role = String(item.role() || ""); }} catch (e) {{}}
    try {{ description = String(item.description() || ""); }} catch (e) {{}}
    if ((role === "AXCheckBox" || role === "AXButton") && description === target) {{
      try {{
        item.click();
        clicked = true;
        break;
      }} catch (e) {{}}
    }}
    try {{
      const children = item.uiElements();
      for (let i = 0; i < children.length; i++) queue.push(children[i]);
    }} catch (e) {{}}
  }}
}}
clicked;
"""
        proc = _run_osascript(script, language="JavaScript", timeout=8.0)
        return proc.returncode == 0 and proc.stdout.strip().lower() == "true"


def _clip_readback(conn: Any, clip_name: str | None) -> dict[str, Any]:
    item = clip_ops.cutagent_clip(conn, clip_name)
    readback_name = clip_name
    try:
        readback_name = str(item.GetName() or clip_name or "")
    except Exception:
        pass
    return {"clip": clip_name, "clip_readback": readback_name or None, "_item": item}


def _timeline_item_name(item: Any) -> str | None:
    try:
        value = item.GetName()
    except Exception:
        return None
    text = str(value or "").strip()
    return text or None


def _timeline_item_frame(item: Any, getter_name: str) -> int | None:
    getter = getattr(item, getter_name, None)
    if not callable(getter):
        return None
    try:
        return int(getter())
    except Exception:
        return None


def _timeline_item_unique_id(item: Any) -> str | None:
    for getter_name in ("GetUniqueId", "GetUniqueID"):
        getter = getattr(item, getter_name, None)
        if not callable(getter):
            continue
        try:
            value = str(getter() or "").strip()
        except Exception:
            continue
        if value:
            return value
    return None


def _timeline_item_media_id(item: Any) -> str | None:
    getter = getattr(item, "GetMediaPoolItem", None)
    try:
        media_pool_item = getter() if callable(getter) else None
    except Exception:
        media_pool_item = None
    media_id_getter = getattr(media_pool_item, "GetMediaId", None)
    if not callable(media_id_getter):
        return None
    try:
        value = str(media_id_getter() or "").strip()
    except Exception:
        return None
    return value or None


def _timeline_item_proxy_matches(left: Any, right: Any) -> bool:
    if left is right:
        return True
    left_unique_id = _timeline_item_unique_id(left)
    right_unique_id = _timeline_item_unique_id(right)
    if left_unique_id and right_unique_id:
        return left_unique_id == right_unique_id
    left_media_id = _timeline_item_media_id(left)
    right_media_id = _timeline_item_media_id(right)
    return bool(
        left_media_id
        and right_media_id
        and left_media_id == right_media_id
        and _timeline_item_name(left) == _timeline_item_name(right)
        and _timeline_item_frame(left, "GetStart") == _timeline_item_frame(right, "GetStart")
        and _timeline_item_frame(left, "GetEnd") == _timeline_item_frame(right, "GetEnd")
    )


def _timeline_item_track_index(conn: Any, item: Any) -> int | None:
    getter = getattr(item, "GetTrackTypeAndIndex", None)
    if callable(getter):
        try:
            track_type, track_index = getter()
            if str(track_type or "").lower() == "video" and int(track_index) > 0:
                return int(track_index)
        except Exception:
            pass

    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        return None
    try:
        track_count = int(timeline.GetTrackCount("video") or 0)
    except Exception:
        return None
    matches: list[int] = []
    for track_index in range(1, track_count + 1):
        try:
            candidates = timeline.GetItemListInTrack("video", track_index) or []
        except Exception:
            continue
        if any(_timeline_item_proxy_matches(candidate, item) for candidate in candidates):
            matches.append(track_index)
    return matches[0] if len(matches) == 1 else None


def _same_timeline_item(conn: Any, left: Any, right: Any) -> bool:
    if left is None or right is None:
        return False
    if left is right:
        return True
    left_unique_id = _timeline_item_unique_id(left)
    right_unique_id = _timeline_item_unique_id(right)
    if left_unique_id and right_unique_id and left_unique_id != right_unique_id:
        return False
    left_track = _timeline_item_track_index(conn, left)
    right_track = _timeline_item_track_index(conn, right)
    if left_track is None or right_track is None or left_track != right_track:
        return False
    left_media_id = _timeline_item_media_id(left)
    right_media_id = _timeline_item_media_id(right)
    if left_media_id and right_media_id and left_media_id != right_media_id:
        return False
    left_name = _timeline_item_name(left)
    right_name = _timeline_item_name(right)
    if left_name and right_name and left_name != right_name:
        return False
    left_start = _timeline_item_frame(left, "GetStart")
    right_start = _timeline_item_frame(right, "GetStart")
    left_end = _timeline_item_frame(left, "GetEnd")
    right_end = _timeline_item_frame(right, "GetEnd")
    comparable = [
        (left_name, right_name),
        (left_start, right_start),
        (left_end, right_end),
    ]
    populated = [(left_value, right_value) for left_value, right_value in comparable if left_value is not None and right_value is not None]
    return bool(populated) and all(left_value == right_value for left_value, right_value in populated)


def _current_video_item(conn: Any) -> Any | None:
    timeline = getattr(conn, "timeline", None)
    getter = getattr(timeline, "GetCurrentVideoItem", None)
    if callable(getter):
        try:
            item = getter()
            if item:
                return item
        except Exception:
            return None
    fake_item = getattr(conn, "item", None)
    if fake_item is not None:
        return fake_item
    try:
        return clip_ops.get_current_item(conn)
    except Exception:
        return None


def _timeline_start_frame(conn: Any) -> int:
    timeline = getattr(conn, "timeline", None)
    getter = getattr(timeline, "GetStartFrame", None)
    if callable(getter):
        try:
            return int(getter() or 0)
        except Exception:
            pass
    return int(getattr(conn, "start_frame", 0) or 0)


def _resolve_exact_gui_target(
    conn: Any,
    *,
    clip_name: str | None,
    track: int | None,
    at: str | None,
) -> tuple[Any, Any]:
    from .db_timeline_selection import resolve_video_group

    item_ref = resolve_video_group(conn, clip_name=clip_name, track=track, at=at)["video"]
    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        raise ColorPageGuiProofFailed(
            "Color Page GUI clip targeting requires an active timeline.",
            details={"clip": clip_name, "track": track, "at": at, "reason": "timeline_unavailable"},
        )
    try:
        candidates = timeline.GetItemListInTrack("video", int(item_ref.track_index)) or []
    except Exception as exc:
        raise ColorPageGuiProofFailed(
            "Color Page GUI route could not enumerate the selected video track.",
            details={"clip": clip_name, "track": item_ref.track_index, "at": at, "error": str(exc)},
        ) from exc

    expected_names = {str(item_ref.name).strip().lower(), *(str(value).strip().lower() for value in item_ref.aliases)}
    exact_items: list[Any] = []
    for candidate in candidates:
        candidate_names = {str(value).strip().lower() for value in clip_ops._item_name_candidates(candidate)}
        start = _timeline_item_frame(candidate, "GetStart")
        end = _timeline_item_frame(candidate, "GetEnd")
        if (
            expected_names.intersection(candidate_names)
            and start == int(item_ref.start)
            and end == int(item_ref.end)
        ):
            exact_items.append(candidate)
    if len(exact_items) != 1:
        raise ColorPageGuiProofFailed(
            "Color Page GUI route could not prove one exact target timeline item.",
            details={
                "clip": clip_name,
                "track": item_ref.track_index,
                "at": at,
                "start": item_ref.start,
                "end": item_ref.end,
                "match_count": len(exact_items),
                "reason": "exact_timeline_item_unverified",
            },
        )
    return item_ref, exact_items[0]


def _activate_clip_for_gui_mutation(
    conn: Any,
    clip_name: str | None,
    *,
    track: int | None = None,
    at: str | None = None,
) -> dict[str, Any]:
    if not clip_name and track is None and at is None:
        context = _clip_readback(conn, None)
        context["target_activation"] = {
            "status": "current_clip",
            "verified": True,
            "reason": "no_explicit_clip_target",
        }
        return context

    item_ref, item = _resolve_exact_gui_target(conn, clip_name=clip_name, track=track, at=at)
    context = {
        "clip": clip_name,
        "clip_readback": item_ref.name,
        "target_selector": {
            "clip_name": clip_name,
            "track": item_ref.track_index,
            "at": at,
            "start": item_ref.start,
            "end": item_ref.end,
        },
        "_item": item,
        "_item_ref": item_ref,
    }
    current = _current_video_item(conn)
    if _same_timeline_item(conn, current, item) and at is None:
        context["target_activation"] = {
            "status": "already_active",
            "verified": True,
            "clip_readback": context.get("clip_readback"),
        }
        return context

    timeline = getattr(conn, "timeline", None)
    setter = getattr(timeline, "SetCurrentTimecode", None)
    if timeline is None or not callable(setter):
        raise ColorPageGuiProofFailed(
            "Named Color Page GUI clip targets require Timeline.SetCurrentTimecode so DaVinci Resolve mutates the requested clip.",
            details={
                "clip": clip_name,
                "clip_readback": context.get("clip_readback"),
                "reason": "missing_timeline_playhead_setter",
            },
        )

    start = _timeline_item_frame(item, "GetStart")
    end = _timeline_item_frame(item, "GetEnd")
    if start is None or end is None or end <= start:
        raise ColorPageGuiProofFailed(
            "Named Color Page GUI clip targets require readable timeline item bounds.",
            details={
                "clip": clip_name,
                "clip_readback": context.get("clip_readback"),
                "start": start,
                "end": end,
                "reason": "missing_timeline_item_bounds",
            },
        )

    fps = float(getattr(conn, "fps", 24.0) or 24.0)
    timeline_start = _timeline_start_frame(conn)
    midpoint = start + max(0, (end - start - 1) // 2)
    if at is not None:
        from ..utils.time_ref import parse_record_frame

        candidates = [parse_record_frame(str(at), fps, timeline_start)]
    else:
        candidates = [midpoint]
    if at is None and timeline_start and midpoint < timeline_start:
        candidates.append(midpoint + timeline_start)

    attempts: list[dict[str, Any]] = []
    for frame in dict.fromkeys(candidates):
        tc = frames_to_timecode(int(frame), fps)
        try:
            api_result = setter(tc)
        except Exception as exc:
            attempts.append({"frame": frame, "timecode": tc, "error": str(exc)})
            continue
        deadline = time.monotonic() + 1.5
        active = _current_video_item(conn)
        while not _same_timeline_item(conn, active, item) and time.monotonic() < deadline:
            time.sleep(0.05)
            active = _current_video_item(conn)
        verified = _same_timeline_item(conn, active, item)
        attempts.append(
            {
                "frame": frame,
                "timecode": tc,
                "api_result": api_result,
                "verified": verified,
                "current_clip": _timeline_item_name(active),
            }
        )
        if verified:
            context["target_activation"] = {
                "status": "activated",
                "verified": True,
                "clip_readback": context.get("clip_readback"),
                "attempts": attempts,
            }
            return context

    raise ColorPageGuiProofFailed(
        "Color Page GUI route could not activate the requested clip before issuing GUI mutations.",
        details={
            "clip": clip_name,
            "clip_readback": context.get("clip_readback"),
            "timeline_start_frame": timeline_start,
            "item_start": start,
            "item_end": end,
            "attempts": attempts,
        },
    )


def _read_video_track_enabled(timeline: Any, track_index: int) -> bool:
    getter = getattr(timeline, "GetIsTrackEnabled", None)
    if not callable(getter):
        raise ColorPageGuiProofFailed(
            "Color Page lower-track targeting requires readable video track enabled state.",
            details={"track": track_index, "reason": "missing_track_enabled_readback"},
        )
    try:
        value = getter("video", int(track_index))
    except Exception as exc:
        raise ColorPageGuiProofFailed(
            "Color Page lower-track targeting could not read video track enabled state.",
            details={"track": track_index, "reason": "track_enabled_readback_failed", "error": str(exc)},
        ) from exc
    if not isinstance(value, bool):
        raise ColorPageGuiProofFailed(
            "Color Page lower-track targeting received an invalid video track enabled state.",
            details={"track": track_index, "reason": "invalid_track_enabled_readback", "actual": value},
        )
    return value


def _set_video_track_enabled_verified(timeline: Any, track_index: int, enabled: bool) -> dict[str, Any]:
    setter = getattr(timeline, "SetTrackEnable", None)
    if not callable(setter):
        raise ColorPageGuiProofFailed(
            "Color Page lower-track targeting requires Timeline.SetTrackEnable.",
            details={"track": track_index, "enabled": enabled, "reason": "missing_track_enable_setter"},
        )
    try:
        api_result = setter("video", int(track_index), bool(enabled))
    except Exception as exc:
        raise ColorPageGuiProofFailed(
            "Color Page lower-track targeting could not change video track enabled state.",
            details={"track": track_index, "enabled": enabled, "reason": "track_enable_write_failed", "error": str(exc)},
        ) from exc
    if api_result is False:
        raise ColorPageGuiProofFailed(
            "DaVinci Resolve refused the temporary video track enabled-state change.",
            details={"track": track_index, "enabled": enabled, "api_result": api_result},
        )
    deadline = time.monotonic() + 1.5
    actual = _read_video_track_enabled(timeline, track_index)
    while actual is not bool(enabled) and time.monotonic() < deadline:
        time.sleep(0.05)
        actual = _read_video_track_enabled(timeline, track_index)
    if actual is not bool(enabled):
        raise ColorPageGuiProofFailed(
            "DaVinci Resolve did not confirm the requested temporary video track state.",
            details={"track": track_index, "expected": bool(enabled), "actual": actual},
        )
    return {"track": int(track_index), "enabled": bool(enabled), "api_result": api_result, "verified": True}


def _timeline_name_for_track_restore(timeline: Any) -> str:
    getter = getattr(timeline, "GetName", None)
    if not callable(getter):
        raise ColorPageGuiProofFailed(
            "Color Page lower-track targeting requires an exact timeline identity before changing track state.",
            details={"reason": "timeline_name_readback_unavailable"},
        )
    try:
        name = str(getter() or "").strip()
    except Exception as exc:
        raise ColorPageGuiProofFailed(
            "Color Page lower-track targeting could not read the active timeline identity.",
            details={"reason": "timeline_name_readback_failed", "error": str(exc)},
        ) from exc
    if not name:
        raise ColorPageGuiProofFailed(
            "Color Page lower-track targeting requires an exact timeline identity before changing track state.",
            details={"reason": "timeline_name_empty"},
        )
    return name


def _fresh_timeline_for_track_restore(conn: Any, *, expected_name: str) -> Any:
    refresher = getattr(conn, "refresh", None)
    if not callable(refresher):
        raise ColorPageGuiProofFailed(
            "Color Page lower-track targeting could not refresh the timeline before restoring track state.",
            details={"reason": "connection_refresh_unavailable", "expected_timeline": expected_name},
        )
    try:
        refresher()
    except Exception as exc:
        raise ColorPageGuiProofFailed(
            "Color Page lower-track targeting could not refresh the timeline before restoring track state.",
            details={
                "reason": "connection_refresh_failed",
                "expected_timeline": expected_name,
                "error": str(exc),
            },
        ) from exc
    timeline = getattr(conn, "timeline", None)
    actual_name = _timeline_name_for_track_restore(timeline)
    if actual_name != expected_name:
        raise ColorPageGuiProofFailed(
            "Color Page lower-track targeting refused to restore track state on a different timeline.",
            details={
                "reason": "timeline_changed_before_track_restore",
                "expected_timeline": expected_name,
                "actual_timeline": actual_name,
            },
        )
    return timeline


def _overlapping_higher_video_tracks(conn: Any, item_ref: Any, *, at: str | None) -> list[int]:
    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        return []
    if at is not None:
        from ..utils.time_ref import parse_record_frame

        parsed_frame = parse_record_frame(
            str(at),
            float(getattr(conn, "fps", 24.0) or 24.0),
            _timeline_start_frame(conn),
        )
        probe_frames = {parsed_frame}
        timeline_start = _timeline_start_frame(conn)
        if timeline_start:
            probe_frames.add(parsed_frame - timeline_start)
    else:
        probe_frames = {int(item_ref.start) + max(0, (int(item_ref.duration) - 1) // 2)}
    try:
        track_count = int(timeline.GetTrackCount("video") or 0)
    except Exception as exc:
        raise ColorPageGuiProofFailed(
            "Color Page lower-track targeting could not enumerate higher video tracks.",
            details={"reason": "video_track_count_unreadable", "error": str(exc)},
        ) from exc
    overlaps: list[int] = []
    for track_index in range(int(item_ref.track_index) + 1, track_count + 1):
        try:
            items = timeline.GetItemListInTrack("video", track_index) or []
        except Exception as exc:
            raise ColorPageGuiProofFailed(
                "Color Page lower-track targeting could not enumerate a higher video track.",
                details={"track": track_index, "reason": "higher_track_items_unreadable", "error": str(exc)},
            ) from exc
        for item in items:
            start = _timeline_item_frame(item, "GetStart")
            end = _timeline_item_frame(item, "GetEnd")
            if start is None or end is None:
                raise ColorPageGuiProofFailed(
                    "Color Page lower-track targeting requires readable bounds for overlapping higher-track items.",
                    details={"track": track_index, "reason": "higher_track_item_bounds_unreadable"},
                )
            if any(start <= probe_frame < end for probe_frame in probe_frames):
                overlaps.append(track_index)
                break
    return overlaps


def _verify_active_primary_gui_target(
    conn: Any,
    context: dict[str, Any],
    *,
    phase: str,
) -> dict[str, Any]:
    selector = context.get("target_selector") if isinstance(context.get("target_selector"), dict) else {}
    item_ref, enumerated_item = _resolve_exact_gui_target(
        conn,
        clip_name=selector.get("clip_name"),
        track=selector.get("track"),
        at=selector.get("at"),
    )
    expected_item = context.get("_item")
    current_item = _current_video_item(conn)
    enumerated_matches = _same_timeline_item(conn, expected_item, enumerated_item)
    current_matches = _same_timeline_item(conn, current_item, enumerated_item)
    if not enumerated_matches or not current_matches:
        raise ColorPageGuiProofFailed(
            "Color Page GUI target changed during the primary-control operation.",
            details={
                "phase": phase,
                "selector": selector,
                "enumerated_matches": enumerated_matches,
                "current_matches": current_matches,
                "current_track": _timeline_item_track_index(conn, current_item),
                "expected_track": item_ref.track_index,
            },
        )
    return {
        "phase": phase,
        "verified": True,
        "track": item_ref.track_index,
        "start": item_ref.start,
        "end": item_ref.end,
    }


@contextmanager
def _isolated_primary_gui_target(
    conn: Any,
    *,
    clip_name: str | None,
    track: int | None,
    at: str | None,
):
    _ensure_color_page(conn)
    item_ref, _item = _resolve_exact_gui_target(conn, clip_name=clip_name, track=track, at=at)
    timeline = getattr(conn, "timeline", None)
    higher_tracks = _overlapping_higher_video_tracks(conn, item_ref, at=at)
    timeline_name = _timeline_name_for_track_restore(timeline) if higher_tracks else None
    original_states: dict[int, bool] = {}
    changed_tracks: list[int] = []
    context: dict[str, Any] | None = None
    primary_error: BaseException | None = None
    try:
        for track_index in higher_tracks:
            original = _read_video_track_enabled(timeline, track_index)
            original_states[track_index] = original
            if original:
                _set_video_track_enabled_verified(timeline, track_index, False)
                changed_tracks.append(track_index)
        context = _activate_clip_for_gui_mutation(conn, clip_name, track=track, at=at)
        context["track_isolation"] = {
            "status": "active" if changed_tracks else "not_required",
            "target_track": int(item_ref.track_index),
            "overlapping_higher_tracks": higher_tracks,
            "disabled_tracks": list(changed_tracks),
            "original_states": dict(original_states),
        }
        yield context
    except BaseException as exc:
        primary_error = exc

    restore_failures: list[dict[str, Any]] = []
    restored: list[dict[str, Any]] = []
    for track_index in reversed(higher_tracks):
        if track_index not in original_states:
            continue
        try:
            restored.append(_set_video_track_enabled_verified(timeline, track_index, original_states[track_index]))
        except Exception as exc:
            try:
                timeline = _fresh_timeline_for_track_restore(conn, expected_name=str(timeline_name))
                retry = _set_video_track_enabled_verified(timeline, track_index, original_states[track_index])
                retry["connection_refreshed"] = True
                retry["initial_error"] = str(exc)
                restored.append(retry)
            except Exception as retry_exc:
                restore_failures.append(
                    {
                        "track": track_index,
                        "expected": original_states[track_index],
                        "error": str(exc),
                        "refresh_retry_error": str(retry_exc),
                    }
                )
    restore_payload = {
        "status": "verified" if not restore_failures else "failed",
        "restored_tracks": restored,
        "failures": restore_failures,
    }
    if context is not None:
        context.setdefault("track_isolation", {})["restore"] = restore_payload
    if restore_failures:
        raise ColorPageGuiProofFailed(
            "Color Page lower-track targeting could not restore every temporary video track state.",
            details={
                "restore": restore_payload,
                "original_error": str(primary_error) if primary_error is not None else None,
            },
        ) from primary_error
    if primary_error is not None:
        raise primary_error


def _proof_paths(proof_dir: Path, clip_name: str | None, route_slug: str) -> ColorPageProofPaths:
    label = clip_name or "current-clip"
    safe_clip = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in label).strip("_") or "clip"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return ColorPageProofPaths(
        screenshot_path=proof_dir / f"{safe_clip}-{route_slug}-{stamp}-viewer.png",
        export_path=proof_dir / f"{safe_clip}-{route_slug}-{stamp}-export.png",
    )


def _qualifier_probe_screenshot_path(proof_dir: Path, clip_name: str | None) -> Path:
    label = clip_name or "current-clip"
    safe_clip = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in label).strip("_") or "clip"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return proof_dir / f"{safe_clip}-qualifier-panel-probe-{stamp}.png"


def _color_node_graph_snapshot(conn: Any, clip_name: str | None) -> dict[str, Any]:
    item = clip_ops.cutagent_clip(conn, clip_name)
    clip_readback = clip_name
    try:
        clip_readback = str(item.GetName() or clip_name or "")
    except Exception:
        pass
    getter = getattr(item, "GetNodeGraph", None)
    if not callable(getter):
        raise ColorPageGuiProofFailed(
            "DaVinci Resolve timeline item does not expose a Color Page node graph for GUI route verification.",
            details={"clip": clip_name, "clip_readback": clip_readback},
        )
    graph = getter()
    if not graph:
        raise ColorPageGuiProofFailed(
            "DaVinci Resolve returned no Color Page node graph for GUI route verification.",
            details={"clip": clip_name, "clip_readback": clip_readback},
        )
    try:
        node_count = int(graph.GetNumNodes()) if hasattr(graph, "GetNumNodes") else 0
    except Exception:
        node_count = 0
    nodes: list[dict[str, Any]] = []
    for index in range(1, max(0, node_count) + 1):
        label = ""
        tools: list[str] = []
        try:
            label = str(graph.GetNodeLabel(index) or "")
        except Exception:
            label = ""
        try:
            raw_tools = graph.GetToolsInNode(index)
            if isinstance(raw_tools, dict):
                tools = [str(value) for value in raw_tools.values()]
            elif isinstance(raw_tools, (list, tuple)):
                tools = [str(value) for value in raw_tools]
        except Exception:
            tools = []
        nodes.append({"index": index, "label": label, "tools": tools})
    return {"clip": clip_name, "clip_readback": clip_readback or None, "node_count": node_count, "nodes": nodes}


def _infer_qualifier_panel_rect(window_rect: Rect) -> Rect:
    return Rect(
        x=window_rect.x,
        y=int(round(window_rect.y + window_rect.height * 0.61)),
        width=window_rect.width,
        height=max(120, int(round(window_rect.height * 0.28))),
    )


def _row_text(row: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("description", "name", "title", "help", "value", "semantic_text", "semantic_control"):
        value = row.get(key)
        if value:
            parts.append(str(value))
    nearby = row.get("nearby_labels")
    if isinstance(nearby, list):
        parts.extend(str(value) for value in nearby if value)
    return " ".join(parts).lower()


def _row_own_text(row: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("description", "name", "title", "help", "value"):
        value = row.get(key)
        if value:
            parts.append(str(value))
    return " ".join(parts).lower()


def _row_label(row: dict[str, Any]) -> str:
    return str(row.get("description") or row.get("name") or row.get("title") or row.get("value") or "").strip()


def _row_center(row: dict[str, Any]) -> tuple[float, float] | None:
    position = row.get("position")
    size = row.get("size")
    if not isinstance(position, list) or len(position) < 2 or not isinstance(size, list) or len(size) < 2:
        return None
    try:
        return (float(position[0]) + float(size[0]) / 2.0, float(position[1]) + float(size[1]) / 2.0)
    except (TypeError, ValueError):
        return None


def _semantic_qualifier_family(text: str) -> str | None:
    lowered = str(text or "").lower()
    if re.search(r"(clean[^a-z]+black|black[^a-z]+clean)", lowered):
        return "clean_black"
    if re.search(r"(clean[^a-z]+white|white[^a-z]+clean)", lowered):
        return "clean_white"
    if re.search(r"(^|[^a-z])blur([^a-z]|$)", lowered):
        return "blur"
    if re.search(r"(^|[^a-z])(soft|softness)([^a-z]|$)", lowered):
        return "softness"
    if re.search(r"(^|[^a-z])denoise([^a-z]|$)", lowered):
        return "denoise"
    if re.search(r"(^|[^a-z])(grow|shrink)([^a-z]|$)", lowered):
        return "grow_shrink"
    if re.search(r"(^|[^a-z])hue([^a-z]|$)", lowered):
        return "hue"
    if re.search(r"(^|[^a-z])(sat|saturation)([^a-z]|$)", lowered):
        return "saturation"
    if re.search(r"(^|[^a-z])(lum|luma|luminance)([^a-z]|$)", lowered):
        return "luma"
    return None


def _annotate_qualifier_control_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    annotated = [dict(row) for row in rows]
    labels = [row for row in annotated if str(row.get("role") or "") not in SETTABLE_CONTROL_ROLES and _row_text(row)]

    for row in annotated:
        if str(row.get("role") or "") not in SETTABLE_CONTROL_ROLES:
            continue
        center = _row_center(row)
        if center is None:
            row["semantic_text"] = _row_text(row)
            continue
        cx, cy = center
        nearby: list[tuple[float, str]] = []
        for label in labels:
            label_center = _row_center(label)
            label_text = _row_text(label).strip()
            if label_center is None or not label_text:
                continue
            lx, ly = label_center
            vertical = abs(ly - cy)
            horizontal = abs(lx - cx)
            row_size = row.get("size") if isinstance(row.get("size"), list) else [0, 0]
            try:
                row_width = float(row_size[0])
            except (TypeError, ValueError):
                row_width = 0.0
            leftish = lx <= cx + max(24.0, row_width * 0.35)
            if (vertical <= 28.0 and horizontal <= 420.0) or (vertical <= 70.0 and leftish and horizontal <= 360.0):
                nearby.append((vertical * 4.0 + horizontal, label_text))
        nearby.sort(key=lambda item: item[0])
        row["nearby_labels"] = [label for _, label in nearby[:6]]
        row["primary_label"] = row["nearby_labels"][0] if row["nearby_labels"] else ""
        row["semantic_text"] = " ".join(
            value for value in (_row_own_text(row), str(row.get("primary_label") or "").lower()) if value
        )

    groups: dict[str, list[dict[str, Any]]] = {}
    for row in annotated:
        if str(row.get("role") or "") not in SETTABLE_CONTROL_ROLES:
            continue
        family = _semantic_qualifier_family(str(row.get("semantic_text") or _row_text(row)))
        if family:
            groups.setdefault(family, []).append(row)

    for family in ("hue", "saturation", "luma"):
        group = groups.get(family, [])
        group.sort(key=lambda row: _row_center(row) or (0.0, 0.0))
        for index, row in enumerate(group):
            text = _row_text(row)
            if re.search(r"(^|[^a-z])low([^a-z]|$)", text):
                row["semantic_control"] = f"{family}_low"
            elif re.search(r"(^|[^a-z])high([^a-z]|$)", text):
                row["semantic_control"] = f"{family}_high"
            elif index == 0:
                row["semantic_control"] = f"{family}_low"
            elif index == 1:
                row["semantic_control"] = f"{family}_high"
            else:
                row.setdefault("semantic_control", f"{family}_{index + 1}")
            row["semantic_text"] = " ".join(
                value
                for value in (
                    _row_own_text(row),
                    str(row.get("primary_label") or "").lower(),
                    str(row.get("semantic_control") or "").lower(),
                )
                if value
            )

    for family in ("softness", "blur", "clean_black", "clean_white", "denoise", "grow_shrink"):
        for row in groups.get(family, []):
            row.setdefault("semantic_control", family)
            row["semantic_text"] = " ".join(
                value
                for value in (
                    _row_own_text(row),
                    str(row.get("primary_label") or "").lower(),
                    str(row.get("semantic_control") or "").lower(),
                )
                if value
            )

    return annotated


def _field_point_from_label(row: dict[str, Any], *, x_offset: float = 82.0, y_offset: float | None = None) -> dict[str, int] | None:
    position = row.get("position")
    size = row.get("size")
    if not isinstance(position, list) or len(position) < 2:
        return None
    try:
        x = float(position[0]) + x_offset
        if y_offset is None:
            height = float(size[1]) if isinstance(size, list) and len(size) >= 2 else 20.0
            y = float(position[1]) + height / 2.0
        else:
            y = float(position[1]) + y_offset
    except (TypeError, ValueError):
        return None
    return {"x": int(round(x)), "y": int(round(y))}


def _format_primary_gui_value(control: str, value: float) -> str:
    if control in {"contrast", "pivot"}:
        return f"{float(value):.3f}"
    return f"{float(value):.2f}"


def _format_power_window_gui_value(control: str, value: float) -> str:
    if control == "rotate":
        return f"{float(value):.2f}"
    return f"{float(value):.2f}"


def _infer_power_window_numeric_controls(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    controls: dict[str, dict[str, Any]] = {}
    label_to_control = {label.lower(): control for control, label in POWER_WINDOW_GUI_LABELS.items()}
    for row in rows:
        label = _row_label(row)
        control_name = label_to_control.get(label.lower())
        if control_name is None:
            continue
        size = row.get("size") if isinstance(row.get("size"), list) else []
        try:
            label_width = float(size[0]) if size else 0.0
        except (TypeError, ValueError):
            label_width = 0.0
        point = _field_point_from_label(row, x_offset=label_width + 36.0)
        if point is None:
            continue
        controls[control_name] = {
            "control": control_name,
            "label": label,
            "point": point,
            "method": "quartz_click_type",
        }
    return controls


def _summarize_power_window_panel_controls(rows: list[dict[str, Any]]) -> dict[str, Any]:
    labels = [_row_label(row) for row in rows if _row_label(row)]
    shape_buttons = [
        label
        for label in labels
        if label in {"Linear", "Circle", "Polygon", "Curve", "Gradient"}
    ]
    numeric_controls = _infer_power_window_numeric_controls(rows)
    panel_active = "Window" in labels and bool(shape_buttons)
    return {
        "row_count": len(rows),
        "labels": labels[:120],
        "shape_buttons": shape_buttons,
        "panel_active": panel_active,
        "numeric_gui_controls": numeric_controls,
        "write_supported": panel_active and bool(numeric_controls),
        "note": (
            "Power Window GUI writes target the currently selected Color Page node. "
            "Use this only inside a workflow that controls node selection; setup-only window creation must be followed "
            "by a visible node-local correction and rendered-frame proof."
        ),
    }


def _infer_primary_numeric_controls(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    controls: dict[str, dict[str, Any]] = {}
    label_to_control = {label.lower(): control for control, label in PRIMARY_GUI_LABELS.items()}
    for row in rows:
        label = _row_label(row)
        control_name = label_to_control.get(label.lower())
        if control_name is None:
            continue
        size = row.get("size") if isinstance(row.get("size"), list) else []
        label_width = float(size[0]) if size else 0.0
        point = _field_point_from_label(row, x_offset=label_width + 23.0)
        if point is None:
            continue
        controls[control_name] = {
            "control": control_name,
            "label": label,
            "point": point,
            "method": "quartz_click_type",
        }
    return controls


def _summarize_primary_panel_controls(rows: list[dict[str, Any]]) -> dict[str, Any]:
    labels = [_row_label(row) for row in rows if _row_label(row)]
    numeric_controls = _infer_primary_numeric_controls(rows)
    normalized_labels = {label.lower() for label in labels}
    panel_active = (
        "primaries - color wheels" in normalized_labels
        or ("color wheels" in normalized_labels and bool(numeric_controls))
        or {"contrast", "pivot", "highlights", "saturation"}.issubset(numeric_controls)
    )
    return {
        "row_count": len(rows),
        "labels": labels[:100],
        "panel_active": panel_active,
        "numeric_gui_controls": numeric_controls,
        "write_supported": panel_active and bool(numeric_controls),
        "note": (
            "Primaries GUI writes target the currently selected Color Page node. Use this only inside a workflow "
            "that controls node selection, then require rendered-frame proof for visible corrections."
        ),
    }


def _infer_qualifier_numeric_controls(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    labels = {_row_label(row).lower() for row in rows if _row_label(row)}
    has_hsl_section_rows = {"hue", "saturation", "luminance"}.issubset(labels)
    has_matte_rows = bool({"clean black", "clean white", "blur radius"}.intersection(labels))
    if not (has_hsl_section_rows or has_matte_rows):
        return {}

    controls: dict[str, dict[str, Any]] = {}
    section_rows: dict[str, dict[str, Any]] = {}
    for row in rows:
        label = _row_label(row).lower()
        role = str(row.get("role") or "")
        if role == "AXCheckBox" and label in {"hue", "saturation", "luminance"}:
            section_rows[label] = row

    def add_hsl(section: str, field: str, name: str, x_offset: float) -> None:
        section_row = section_rows.get(section)
        if section_row is None:
            return
        point = _field_point_from_label(section_row, x_offset=x_offset, y_offset=55.0)
        if point is not None:
            controls[name] = {"control": name, "label": f"{section.title()} {field}", "point": point, "method": "quartz_click_type"}

    add_hsl("hue", "Center", "hue_center", 168.0)
    add_hsl("hue", "Width", "hue_width", 279.0)
    add_hsl("hue", "Soft", "hue_soft", 390.0)
    add_hsl("saturation", "Low", "saturation_low", 168.0)
    add_hsl("saturation", "High", "saturation_high", 279.0)
    add_hsl("saturation", "Low Soft", "saturation_low_soft", 390.0)
    add_hsl("saturation", "High Soft", "saturation_high_soft", 501.0)
    add_hsl("luminance", "Low", "luma_low", 168.0)
    add_hsl("luminance", "High", "luma_high", 279.0)
    add_hsl("luminance", "Low Soft", "luma_low_soft", 390.0)
    add_hsl("luminance", "High Soft", "luma_high_soft", 501.0)

    matte_names = {
        "pre-filter": "pre_filter",
        "clean black": "clean_black",
        "clean white": "clean_white",
        "black clip": "black_clip",
        "white clip": "white_clip",
        "blur radius": "blur",
        "denoise": "denoise",
        "grow/shrink": "grow_shrink",
        "grow shrink": "grow_shrink",
        "in/out ratio": "in_out_ratio",
    }
    for row in rows:
        label = _row_label(row).lower()
        control_name = matte_names.get(label)
        if control_name is None:
            continue
        point = _field_point_from_label(row, x_offset=162.0)
        if point is not None:
            controls[control_name] = {
                "control": control_name,
                "label": _row_label(row),
                "point": point,
                "method": "quartz_click_type",
            }

    return controls


def _format_gui_percent(value: float) -> str:
    numeric = max(0.0, min(100.0, float(value)))
    return f"{numeric:.1f}"


def _hue_range_to_center_width(low: float, high: float) -> tuple[float, float]:
    low = float(low) % 1.0
    high = float(high) % 1.0
    if high >= low:
        width = high - low
        center = low + width / 2.0
    else:
        width = (1.0 - low) + high
        center = (low + width / 2.0) % 1.0
    return center * 100.0, width * 100.0


def _build_qualifier_numeric_write_plan(
    controls: list[dict[str, Any]],
    numeric_controls: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    requested = {str(row.get("control") or ""): row for row in controls if row.get("control")}
    plan: list[dict[str, Any]] = []

    def add(control_name: str, value: float, source_controls: list[str]) -> None:
        field = numeric_controls.get(control_name)
        if field is None:
            raise ColorPagePanelNotReady(
                "DaVinci Resolve Qualifier numeric field is not exposed for GUI writing.",
                details={
                    "control": control_name,
                    "source_controls": source_controls,
                    "available_numeric_controls": sorted(numeric_controls),
                },
            )
        plan.append(
            {
                **field,
                "value": float(value),
                "text_value": _format_gui_percent(float(value)),
                "source_controls": source_controls,
            }
        )

    if "hue_low" in requested and "hue_high" in requested:
        center, width = _hue_range_to_center_width(float(requested["hue_low"]["value"]), float(requested["hue_high"]["value"]))
        add("hue_center", center, ["hue_low", "hue_high"])
        add("hue_width", width, ["hue_low", "hue_high"])
        if "hue_softness" in requested:
            add("hue_soft", float(requested["hue_softness"]["value"]) * 100.0, ["hue_softness"])
    elif "hue_low" in requested or "hue_high" in requested:
        raise ColorPagePanelNotReady(
            "DaVinci Resolve Qualifier hue GUI writing requires both hue_low and hue_high.",
            details={"requested_controls": sorted(requested)},
        )

    for family, low_name, high_name in (
        ("saturation", "saturation_low", "saturation_high"),
        ("luma", "luma_low", "luma_high"),
    ):
        if low_name in requested:
            add(low_name, float(requested[low_name]["value"]) * 100.0, [low_name])
        if high_name in requested:
            add(high_name, float(requested[high_name]["value"]) * 100.0, [high_name])
        if (low_name in requested) ^ (high_name in requested):
            raise ColorPagePanelNotReady(
                f"DaVinci Resolve Qualifier {family} GUI writing requires both low and high bounds.",
                details={"requested_controls": sorted(requested), "family": family},
            )
        softness_name = f"{family}_softness"
        if softness_name in requested:
            add(f"{family}_low_soft", float(requested[softness_name]["value"]) * 100.0, [softness_name])
            add(f"{family}_high_soft", float(requested[softness_name]["value"]) * 100.0, [softness_name])

    matte_aliases = {
        "clean_black": "clean_black",
        "clean_white": "clean_white",
        "blur": "blur",
        "softness": "softness",
        "denoise": "denoise",
        "grow_shrink": "grow_shrink",
    }
    used_matte_targets: set[str] = set()
    for source, target in matte_aliases.items():
        if source not in requested:
            continue
        if target in used_matte_targets:
            continue
        used_matte_targets.add(target)
        add(target, float(requested[source]["value"]) * 100.0, [source])

    return plan


def _summarize_qualifier_probe_controls(rows: list[dict[str, Any]]) -> dict[str, Any]:
    hsl_terms = {"hue", "sat", "saturation", "lum", "luma", "luminance"}
    matte_refinement_terms = {
        "blur",
        "clean",
        "denoise",
        "matte",
        "soft",
        "softness",
        "width",
        "falloff",
        "grow",
        "shrink",
        "black",
        "white",
    }
    settable = []
    hsl_settable = []
    matte_refinement_settable = []
    pressable = []
    static = []
    labels = []
    for row in rows:
        role = str(row.get("role") or "")
        label = str(row.get("description") or row.get("name") or row.get("title") or "")
        if label:
            labels.append(label)
        semantic_text = str(row.get("semantic_text") or _row_text(row))
        semantic_control = str(row.get("semantic_control") or "")
        if role in SETTABLE_CONTROL_ROLES:
            settable.append(row)
            label_terms = {piece.strip().lower() for piece in re.split(r"[^A-Za-z]+", semantic_text) if piece.strip()}
            if hsl_terms.intersection(label_terms):
                hsl_settable.append(row)
            if semantic_control in {"softness", "blur", "clean_black", "clean_white", "denoise", "grow_shrink"} or matte_refinement_terms.intersection(label_terms):
                matte_refinement_settable.append(row)
        elif role in PRESSABLE_CONTROL_ROLES or "AXPress" in (row.get("actions") or []):
            pressable.append(row)
        else:
            static.append(row)
    numeric_controls = _infer_qualifier_numeric_controls(rows)
    required_hsl_numeric = {"hue_center", "hue_width", "saturation_low", "saturation_high", "luma_low", "luma_high"}
    hsl_numeric_supported = required_hsl_numeric.issubset(numeric_controls)
    matte_numeric_controls = {"clean_black", "clean_white", "blur"}.intersection(numeric_controls)
    hsl_write_supported = len(hsl_settable) > 0 or hsl_numeric_supported
    matte_write_supported = len(matte_refinement_settable) > 0 or len(matte_numeric_controls) > 0
    has_qualifier_structure = any(
        label.lower() in {"luminance", "matte finesse", "clean black", "clean white", "blur radius", "hsl", "rgb", "lum", "3d"}
        for label in labels
    )
    hsl_write_decision = {
        "status": "ready_for_proof_gated_write" if hsl_write_supported else "blocked_no_hsl_settable_controls",
        "reason": (
            "HSL-specific controls are exposed through macOS Accessibility or verified numeric GUI fields."
            if hsl_write_supported
            else "The visible Qualifier panel exposed no HSL-specific settable controls or numeric GUI fields through macOS Accessibility."
        ),
        "required_next_proof": (
            "A mutation route must still set the specific controls, export before/after rendered frames, and fail "
            "unless the rendered pixels change in the intended region."
        ),
    }
    return {
        "row_count": len(rows),
        "labels": labels[:80],
        "settable_control_count": len(settable),
        "hsl_settable_control_count": len(hsl_settable),
        "matte_refinement_settable_control_count": len(matte_refinement_settable),
        "pressable_control_count": len(pressable),
        "static_control_count": len(static),
        "settable_roles": sorted({str(row.get("role") or "") for row in settable if row.get("role")}),
        "hsl_settable_labels": [
            str(row.get("semantic_control") or row.get("description") or row.get("name") or row.get("title") or "")
            for row in hsl_settable[:40]
        ]
        + sorted(name for name in numeric_controls if name.startswith(("hue_", "saturation_", "luma_"))),
        "matte_refinement_settable_labels": [
            str(row.get("semantic_control") or row.get("description") or row.get("name") or row.get("title") or "")
            for row in matte_refinement_settable[:40]
        ]
        + sorted(matte_numeric_controls),
        "numeric_gui_controls": numeric_controls,
        "pressable_roles": sorted({str(row.get("role") or "") for row in pressable if row.get("role")}),
        "has_hsl_labels": any(label.lower() == "hue" for label in labels)
        and any(label.lower() in {"sat", "saturation"} for label in labels),
        "has_qualifier_structure": has_qualifier_structure,
        "hsl_gui_write_supported": hsl_write_supported,
        "matte_refinement_gui_write_supported": matte_write_supported,
        "hsl_write_decision": hsl_write_decision,
        "note": (
            "This probe only reports macOS Accessibility controls visible in the Qualifier panel. "
            "A write route is safe only if HSL-specific settable controls are exposed and proof artifacts capture "
            "the actual DaVinci Resolve window."
        ),
    }


def run_qualifier_panel_probe(
    conn: Any,
    *,
    clip_name: str | None,
    proof_dir: Path | None = None,
    driver: MacOSColorPageGuiDriver | None = None,
) -> dict[str, Any]:
    normalized_clip = normalize_optional_clip(clip_name)
    active_driver = driver or MacOSColorPageGuiDriver()
    proof_root = (proof_dir or DEFAULT_PROOF_DIR).expanduser()
    if not proof_root.is_absolute():
        proof_root = Path.cwd() / proof_root
    proof_root = proof_root.resolve(strict=False)
    proof_root.mkdir(parents=True, exist_ok=True)

    permission_state = active_driver.preflight_permissions()
    window_rect = active_driver.find_resolve_window()
    context = _activate_clip_for_gui_mutation(conn, normalized_clip)
    page_state = _ensure_color_page(conn)
    panel_state = active_driver.ensure_qualifier_panel()
    rows = _annotate_qualifier_control_rows(active_driver.collect_qualifier_panel_controls())
    summary = _summarize_qualifier_probe_controls(rows)
    panel_rect = _infer_qualifier_panel_rect(window_rect)
    screenshot_path = _qualifier_probe_screenshot_path(proof_root, context.get("clip_readback") or normalized_clip)
    screenshot_state = active_driver.capture_screenshot(panel_rect, screenshot_path)
    if not screenshot_path.is_file():
        raise ColorPageGuiProofFailed(
            "Color Page Qualifier panel probe did not create the required proof screenshot.",
            details={"screenshot_path": str(screenshot_path), "screenshot_exists": screenshot_path.is_file()},
        )

    set_verification_status("verified")
    set_recoverability("manual")
    return {
        "route": ROUTE_QUALIFIER_PANEL_PROBE,
        "clip": normalized_clip,
        "clip_readback": context.get("clip_readback"),
        "target_activation": context.get("target_activation"),
        "proof": {
            "screenshot_path": str(screenshot_path),
            "panel_rect": panel_rect.as_payload(),
            "onscreen_window_rect": window_rect.as_payload(),
            "screenshot": screenshot_state,
        },
        "preflight": {
            "permissions": permission_state,
            "window_rect": window_rect.as_payload(),
            "page": page_state,
            "panel": panel_state,
        },
        "controls": rows,
        "summary": summary,
    }


def run_qualifier_gui_hsl_set(
    conn: Any,
    *,
    clip_name: str | None,
    controls: list[dict[str, Any]],
    proof_dir: Path | None = None,
    driver: MacOSColorPageGuiDriver | None = None,
    probe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_clip = normalize_optional_clip(clip_name)
    active_driver = driver or MacOSColorPageGuiDriver()
    if probe is None:
        probe = run_qualifier_panel_probe(
            conn,
            clip_name=normalized_clip,
            proof_dir=proof_dir,
            driver=active_driver,
        )
    summary = probe.get("summary") if isinstance(probe.get("summary"), dict) else {}
    decision = summary.get("hsl_write_decision") if isinstance(summary.get("hsl_write_decision"), dict) else {}
    if decision.get("status") != "ready_for_proof_gated_write":
        raise CapabilityNegotiationFailed(
            "Native Color Page Qualifier GUI HSL controls are not exposed safely enough to mutate.",
            details={
                "route": ROUTE_QUALIFIER_GUI_HSL_SET,
                "clip": normalized_clip,
                "probe_summary": summary,
                "required_decision": "ready_for_proof_gated_write",
                "actual_decision": decision.get("status"),
            },
            recoverability="manual",
        )
    context = _activate_clip_for_gui_mutation(conn, normalized_clip)
    apply_result = active_driver.set_qualifier_hsl_controls(controls)
    set_recoverability("manual")
    return {
        "route": ROUTE_QUALIFIER_GUI_HSL_SET,
        "clip": normalized_clip,
        "clip_readback": context.get("clip_readback") or probe.get("clip_readback"),
        "target_activation": context.get("target_activation"),
        "probe": probe,
        "requested_controls": controls,
        "apply_result": apply_result,
        "verification": {
            "status": "pending_render_proof",
            "render_proof_required": True,
            "source": "workflow_owned_resolve_gui_qualifier_hsl",
        },
    }


def run_qualifier_gui_matte_set(
    conn: Any,
    *,
    clip_name: str | None,
    controls: list[dict[str, Any]],
    proof_dir: Path | None = None,
    driver: MacOSColorPageGuiDriver | None = None,
    probe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_clip = normalize_optional_clip(clip_name)
    active_driver = driver or MacOSColorPageGuiDriver()
    if probe is None:
        probe = run_qualifier_panel_probe(
            conn,
            clip_name=normalized_clip,
            proof_dir=proof_dir,
            driver=active_driver,
        )
    summary = probe.get("summary") if isinstance(probe.get("summary"), dict) else {}
    if not summary.get("matte_refinement_gui_write_supported"):
        raise CapabilityNegotiationFailed(
            "Native Color Page Qualifier GUI matte controls are not exposed safely enough to mutate.",
            details={
                "route": ROUTE_QUALIFIER_GUI_MATTE_SET,
                "clip": normalized_clip,
                "probe_summary": summary,
                "required_summary_flag": "matte_refinement_gui_write_supported",
                "actual_summary_flag": summary.get("matte_refinement_gui_write_supported"),
            },
            recoverability="manual",
        )
    context = _activate_clip_for_gui_mutation(conn, normalized_clip)
    apply_result = active_driver.set_qualifier_controls(controls)
    set_recoverability("manual")
    return {
        "route": ROUTE_QUALIFIER_GUI_MATTE_SET,
        "clip": normalized_clip,
        "clip_readback": context.get("clip_readback") or probe.get("clip_readback"),
        "target_activation": context.get("target_activation"),
        "probe": probe,
        "requested_controls": controls,
        "apply_result": apply_result,
        "verification": {
            "status": "pending_render_proof",
            "render_proof_required": True,
            "source": "workflow_owned_resolve_gui_qualifier_matte",
        },
    }


def _node_has_tool(snapshot: dict[str, Any], *, node_index: int | None, tool_name: str) -> bool:
    tool_name_lower = str(tool_name or "").lower()
    for node in snapshot.get("nodes") or []:
        if node_index is not None and int(node.get("index") or 0) != int(node_index):
            continue
        tools = [str(value).lower() for value in node.get("tools") or []]
        if any(tool_name_lower in value for value in tools):
            return True
    return False


def _node_indexes_with_tool(snapshot: dict[str, Any], *, tool_name: str) -> set[int]:
    tool_name_lower = str(tool_name or "").lower()
    indexes: set[int] = set()
    for node in snapshot.get("nodes") or []:
        try:
            index = int(node.get("index") or 0)
        except (TypeError, ValueError):
            continue
        tools = [str(value).lower() for value in node.get("tools") or []]
        if any(tool_name_lower in value for value in tools):
            indexes.add(index)
    return indexes


def _verify_tool_setup_on_target_or_new_node(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    expected_node_index: int | None,
    tool_name: str,
    allow_existing_expected_node: bool = False,
    allow_existing_any_node: bool = False,
) -> dict[str, Any]:
    if expected_node_index is not None:
        expected = int(expected_node_index)
        before_has_tool = _node_has_tool(before, node_index=expected, tool_name=tool_name)
        after_has_tool = _node_has_tool(after, node_index=expected, tool_name=tool_name)
        before_node = next((node for node in before.get("nodes") or [] if int(node.get("index") or 0) == expected), None)
        after_node = next((node for node in after.get("nodes") or [] if int(node.get("index") or 0) == expected), None)
        expected_node_changed = before_node != after_node
        verified = after_has_tool and (not before_has_tool or expected_node_changed or allow_existing_expected_node)
        return {
            "verified": verified,
            "mode": "expected_node_index",
            "expected_node_index": expected,
            "before_had_tool": before_has_tool,
            "after_has_tool": after_has_tool,
            "expected_node_changed": expected_node_changed,
            "allow_existing_expected_node": allow_existing_expected_node,
            "target_scope_verified": True,
            "verified_node_indexes": [expected] if verified else [],
        }

    before_nodes = _node_indexes_with_tool(before, tool_name=tool_name)
    after_nodes = _node_indexes_with_tool(after, tool_name=tool_name)
    added_nodes = sorted(after_nodes - before_nodes)
    if allow_existing_any_node and after_nodes:
        return {
            "verified": True,
            "mode": "existing_tool_update_unscoped",
            "expected_node_index": None,
            "target_scope_verified": False,
            "before_node_indexes": sorted(before_nodes),
            "after_node_indexes": sorted(after_nodes),
            "verified_node_indexes": sorted(after_nodes),
        }
    return {
        "verified": bool(added_nodes),
        "mode": "new_tool_node_diff",
        "expected_node_index": None,
        "target_scope_verified": True,
        "before_node_indexes": sorted(before_nodes),
        "after_node_indexes": sorted(after_nodes),
        "verified_node_indexes": added_nodes,
    }


def run_power_window_gui_set(
    conn: Any,
    *,
    clip_name: str | None,
    shape: str,
    controls: list[dict[str, Any]],
    expected_node_index: int | None = None,
    proof_dir: Path | None = None,
    driver: MacOSColorPageGuiDriver | None = None,
) -> dict[str, Any]:
    normalized_clip = normalize_optional_clip(clip_name)
    normalized_shape = normalize_power_window_shape(shape)
    active_driver = driver or MacOSColorPageGuiDriver()
    proof_root = (proof_dir or DEFAULT_PROOF_DIR).expanduser()
    if not proof_root.is_absolute():
        proof_root = Path.cwd() / proof_root
    proof_root = proof_root.resolve(strict=False)
    proof_root.mkdir(parents=True, exist_ok=True)

    permission_state = active_driver.preflight_permissions()
    window_rect = active_driver.find_resolve_window()
    context = _activate_clip_for_gui_mutation(conn, normalized_clip)
    page_state = _ensure_color_page(conn)
    before = _color_node_graph_snapshot(conn, normalized_clip)
    panel_state = active_driver.ensure_power_window_panel(normalized_shape)
    apply_result = active_driver.set_power_window_shape_and_controls(normalized_shape, controls)
    after = _color_node_graph_snapshot(conn, normalized_clip)
    deadline = time.monotonic() + 2.0
    setup_readback = _verify_tool_setup_on_target_or_new_node(
        before,
        after,
        expected_node_index=expected_node_index,
        tool_name="Power Windows",
        allow_existing_expected_node=bool(controls),
        allow_existing_any_node=bool(controls),
    )
    while not setup_readback["verified"] and time.monotonic() < deadline:
        time.sleep(0.2)
        after = _color_node_graph_snapshot(conn, normalized_clip)
        setup_readback = _verify_tool_setup_on_target_or_new_node(
            before,
            after,
            expected_node_index=expected_node_index,
            tool_name="Power Windows",
            allow_existing_expected_node=bool(controls),
            allow_existing_any_node=bool(controls),
        )

    if not setup_readback["verified"]:
        raise ColorPageGuiProofFailed(
            "DaVinci Resolve Power Window GUI set did not verify through the Color Page node graph.",
            details={
                "route": ROUTE_POWER_WINDOW_GUI_SET,
                "clip": normalized_clip,
                "shape": normalized_shape,
                "expected_node_index": expected_node_index,
                "before": before,
                "after": after,
                "setup_readback": setup_readback,
                "apply_result": apply_result,
            },
        )

    label = str(context.get("clip_readback") or normalized_clip or "clip")
    safe_clip = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in label).strip("_") or "clip"
    screenshot_path = proof_root / f"{safe_clip}-power-window-gui-set-{time.strftime('%Y%m%d-%H%M%S')}.png"
    screenshot_state = active_driver.capture_screenshot(window_rect, screenshot_path)
    if not screenshot_path.is_file():
        raise ColorPageGuiProofFailed(
            "Color Page Power Window GUI set route did not create the required proof screenshot.",
            details={"screenshot_path": str(screenshot_path), "screenshot_exists": screenshot_path.is_file()},
        )

    set_recoverability("manual")
    return {
        "route": ROUTE_POWER_WINDOW_GUI_SET,
        "clip": normalized_clip,
        "clip_readback": context.get("clip_readback"),
        "shape": normalized_shape,
        "requested_controls": controls,
        "apply_result": apply_result,
        "before": before,
        "after": after,
        "proof": {
            "screenshot_path": str(screenshot_path),
            "onscreen_window_rect": window_rect.as_payload(),
            "screenshot": screenshot_state,
        },
        "preflight": {
            "permissions": permission_state,
            "window_rect": window_rect.as_payload(),
            "page": page_state,
            "panel": panel_state,
        },
        "verification": {
            "status": "setup_only",
            "source": "workflow_owned_resolve_gui_power_window",
            "expected_node_index": expected_node_index,
            "setup_readback": setup_readback,
            "node_graph_has_power_window": True,
            "render_proof_required": False,
            "final_grade_success": False,
            "required_next_proof": "Apply a visible correction on the same selected node and verify rendered-frame pixel diff plus locality.",
        },
    }


def run_primary_gui_set(
    conn: Any,
    *,
    clip_name: str | None,
    track: int | None = None,
    at: str | None = None,
    controls: list[dict[str, Any]],
    proof_dir: Path | None = None,
    driver: MacOSColorPageGuiDriver | None = None,
) -> dict[str, Any]:
    normalized_clip = normalize_optional_clip(clip_name)
    active_driver = driver or MacOSColorPageGuiDriver()
    proof_root = (proof_dir or DEFAULT_PROOF_DIR).expanduser()
    if not proof_root.is_absolute():
        proof_root = Path.cwd() / proof_root
    proof_root = proof_root.resolve(strict=False)
    proof_root.mkdir(parents=True, exist_ok=True)

    permission_state = active_driver.preflight_permissions()
    window_rect = active_driver.find_resolve_window()
    with _isolated_primary_gui_target(
        conn,
        clip_name=normalized_clip,
        track=track,
        at=at,
    ) as context:
        page_state = _ensure_color_page(conn)
        panel_state = active_driver.ensure_primary_wheels_panel()
        target_checks = [
            _verify_active_primary_gui_target(conn, context, phase="before_gui_input")
        ]
        apply_result = active_driver.set_primary_controls(controls)
        target_checks.append(
            _verify_active_primary_gui_target(conn, context, phase="after_gui_input")
        )
        label = str(context.get("clip_readback") or normalized_clip or "clip")
        safe_clip = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in label).strip("_") or "clip"
        screenshot_path = proof_root / f"{safe_clip}-primary-gui-set-{time.strftime('%Y%m%d-%H%M%S')}.png"
        target_checks.append(
            _verify_active_primary_gui_target(conn, context, phase="before_screenshot")
        )
        screenshot_state = active_driver.capture_screenshot(window_rect, screenshot_path)
        if not screenshot_path.is_file():
            raise ColorPageGuiProofFailed(
                "Color Page Primaries GUI set route did not create the required proof screenshot.",
                details={"screenshot_path": str(screenshot_path), "screenshot_exists": screenshot_path.is_file()},
            )
    set_recoverability("manual")
    return {
        "route": ROUTE_PRIMARY_GUI_SET,
        "clip": normalized_clip,
        "clip_readback": context.get("clip_readback"),
        "target_selector": context.get("target_selector"),
        "track_isolation": context.get("track_isolation"),
        "requested_controls": controls,
        "apply_result": apply_result,
        "target_checks": target_checks,
        "proof": {
            "screenshot_path": str(screenshot_path),
            "onscreen_window_rect": window_rect.as_payload(),
            "screenshot": screenshot_state,
        },
        "preflight": {
            "permissions": permission_state,
            "window_rect": window_rect.as_payload(),
            "page": page_state,
            "panel": panel_state,
        },
        "verification": {
            "status": "pending_render_proof",
            "render_proof_required": True,
            "source": "workflow_owned_resolve_gui_primary_controls",
            "node_targeting": "current_selected_color_page_node",
        },
    }


def run_power_window_track(
    conn: Any,
    *,
    clip_name: str | None,
    shape: str,
    direction: str,
    proof_exporter: ProofExporter,
    expected_node_index: int | None = None,
    proof_dir: Path | None = None,
    driver: MacOSColorPageGuiDriver | None = None,
) -> dict[str, Any]:
    normalized_clip = normalize_optional_clip(clip_name)
    normalized_shape = normalize_power_window_shape(shape)
    normalized_direction = normalize_track_direction(direction)

    active_driver = driver or MacOSColorPageGuiDriver()
    proof_root = (proof_dir or DEFAULT_PROOF_DIR).expanduser()
    if not proof_root.is_absolute():
        proof_root = Path.cwd() / proof_root
    proof_root = proof_root.resolve(strict=False)
    proof_root.mkdir(parents=True, exist_ok=True)

    permission_state = active_driver.preflight_permissions()
    window_rect = active_driver.find_resolve_window()
    context = _activate_clip_for_gui_mutation(conn, normalized_clip)
    resolved_clip = context.get("clip_readback") or normalized_clip
    resolved_item = context.get("_item")
    page_state = _ensure_color_page(conn)

    window_panel_state = active_driver.ensure_power_window_panel(normalized_shape)
    before_window_setup = _color_node_graph_snapshot(conn, normalized_clip)
    window_setup = active_driver.set_power_window_shape_and_controls(normalized_shape, [])
    after_window_setup = _color_node_graph_snapshot(conn, normalized_clip)
    deadline = time.monotonic() + 3.0
    window_setup_readback = _verify_tool_setup_on_target_or_new_node(
        before_window_setup,
        after_window_setup,
        expected_node_index=expected_node_index,
        tool_name="Power Windows",
        allow_existing_expected_node=True,
        allow_existing_any_node=expected_node_index is None,
    )
    while not window_setup_readback["verified"] and time.monotonic() < deadline:
        time.sleep(0.2)
        after_window_setup = _color_node_graph_snapshot(conn, normalized_clip)
        window_setup_readback = _verify_tool_setup_on_target_or_new_node(
            before_window_setup,
            after_window_setup,
            expected_node_index=expected_node_index,
            tool_name="Power Windows",
            allow_existing_expected_node=True,
            allow_existing_any_node=expected_node_index is None,
        )
    if not window_setup_readback["verified"]:
        raise ColorPageGuiProofFailed(
            "Color Page Power Window tracking requires a verified Power Window on the selected node before tracking.",
            details={
                "reason": "power_window_setup_readback_failed",
                "route": ROUTE_POWER_WINDOW_TRACK,
                "clip": resolved_clip,
                "shape": normalized_shape,
                "expected_node_index": expected_node_index,
                "window_panel": window_panel_state,
                "window_setup": window_setup,
                "before": before_window_setup,
                "after": after_window_setup,
                "window_setup_readback": window_setup_readback,
            },
        )

    panel_state = active_driver.ensure_power_window_tracker_panel(normalized_shape)
    viewer_rect = active_driver.capture_viewer_geometry(window_rect)
    before_save = _save_project_for_color_page_payload_readback(conn)
    before_payload = _active_color_page_tracking_payload_signature(conn, clip_name=resolved_clip, item=resolved_item)
    track_state = active_driver.track_power_window(normalized_direction)
    after_save = _save_project_for_color_page_payload_readback(conn)
    after_payload = _active_color_page_tracking_payload_signature(conn, clip_name=resolved_clip, item=resolved_item)
    payload_readback = _compare_tracking_payload_signatures(
        before_payload,
        after_payload,
        expected_node_index=expected_node_index,
    )
    payload_readback["save_project"] = {"before": before_save, "after": after_save}
    if payload_readback["status"] != "verified":
        raise ColorPageGuiProofFailed(
            "Color Page Power Window tracking did not produce a persisted hidden tracking payload change.",
            details={
                "reason": "tracking_payload_readback_unchanged",
                "route": ROUTE_POWER_WINDOW_TRACK,
                "clip": resolved_clip,
                "shape": normalized_shape,
                "direction": normalized_direction,
                "track_result": track_state,
                "tracking_payload_readback": payload_readback,
            },
        )

    paths = _proof_paths(proof_root, resolved_clip, "power-window-track")
    screenshot_state = active_driver.capture_screenshot(viewer_rect, paths.screenshot_path)
    export_state = proof_exporter(paths.export_path)
    if not paths.screenshot_path.is_file() or not paths.export_path.is_file():
        raise ColorPageGuiProofFailed(
            "Color Page Power Window tracking route did not create required proof artifacts.",
            details={
                **paths.as_payload(),
                "screenshot_exists": paths.screenshot_path.is_file(),
                "export_exists": paths.export_path.is_file(),
            },
        )

    set_verification_status("verified")
    set_recoverability("manual")
    return {
        "route": ROUTE_POWER_WINDOW_TRACK,
        "clip": normalized_clip,
        "clip_readback": context.get("clip_readback"),
        "shape": normalized_shape,
        "direction": normalized_direction,
        "proof": {
            "screenshot_path": str(paths.screenshot_path),
            "export_path": str(paths.export_path),
            "viewer_rect": viewer_rect.as_payload(),
            "screenshot": screenshot_state,
            "export": export_state,
        },
        "preflight": {
            "permissions": permission_state,
            "window_rect": window_rect.as_payload(),
            "page": page_state,
            "window_panel": window_panel_state,
            "panel": panel_state,
        },
        "window_setup": window_setup,
        "window_setup_readback": {
            "before": before_window_setup,
            "after": after_window_setup,
            **window_setup_readback,
            "node_graph_has_power_window": True,
        },
        "track_result": track_state,
        "tracking_payload_readback": payload_readback,
    }
