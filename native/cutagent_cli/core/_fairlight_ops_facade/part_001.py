"""Fairlight (audio) operations — Audio tracks, volume, mute/solo."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import struct
import time
from typing import List, Dict, Any
import xml.etree.ElementTree as ET
import zlib

from ..errors import (
    APICallFailed,
    CapabilityNegotiationFailed,
    ReadinessFailed,
    ValidationError,
)
from ..output import set_recoverability, set_verification_status
from ..runtime_health import resolve_current_disk_project_db
from ..utils.time_ref import parse_record_frame, parse_source_frame
from ..utils.timecode import parse_time_input, seconds_to_frames
from . import (
    audio_clip_fx,
    audio_eq_db,
    clip_effects_db,
    db_session,
    db_timeline_rows,
    dynamics_db,
    render_engine,
    retime_db,
    timeline_ops,
)


_UI_SEQUENCE_AUDIO_CLIP_HEIGHT_KEY = "UI_SEQUENCE_AUDIO_CLIP_HEIGHT"
_UI_SEQUENCE_USER_ADJUSTED_AUDIO_TRACK_HEIGHTS_KEY = (
    "UI_SEQUENCE_USER_ADJUSTED_AUDIO_TRACK_HEIGHTS"
)
_UI_TYPE_BOOL = 0x01
_UI_TYPE_INT32 = 0x02
_UI_TYPE_ENUM_INT32 = 0x03
_UI_TYPE_BLOB = 0x0C
_UI_TYPE_DOUBLE = 0x26
_FAIRLIGHT_BUS_LABEL_RE = re.compile(rb"(Main|Bus [1-9][0-9]{0,2})")
_FAIRLIGHT_GROUP_LABEL_RE = re.compile(rb"(Group [1-9][0-9]{0,2})")
_FAIRLIGHT_VCA_LABEL_RE = re.compile(rb"(VCA [1-9][0-9]{0,2})")
_FAIRLIGHT_TRACK_FX_SETTING_RE = re.compile(
    r"^TrackFxSetting:([^:]+):([0-9]+):([0-9]+)$"
)
_FAIRLIGHT_MACRO_FX_SETTING_RE = re.compile(r"^MacroFxSetting:([^:]+):([0-9]+)$")
_FAIRLIGHT_MIX_LEVEL_RE = re.compile(r"^MixLevel:([^:]+):([0-9]+)$")
_FAIRLIGHT_BMD_EFFECT_RE = re.compile(r"^bmd:([^:]+):([0-9]+)$")
_FAIRLIGHT_AUTOMIX_RE = re.compile(r"^(AutoMix[A-Za-z]*)(?::([0-9]+))?$")
_FAIRLIGHT_BUS_PROCESSING_RE = re.compile(r"^(OptimizeBusLevel)$")
_FAIRLIGHT_SEND_TOKEN_RE = re.compile(
    r"(send|aux|auxiliary|pre[-_ ]?fader|post[-_ ]?fader|sendlevel|sendpan)",
    re.IGNORECASE,
)
_FAIRLIGHT_MAIN_OUTPUT_ALIASES = {
    "bus 1",
    "bus1",
    "main",
    "main 1",
    "main out",
    "main output",
    "timeline main",
}
_FAIRLIGHT_SEQUENCE_OUTPUT_GAIN_MIN_DB = -100.0
_FAIRLIGHT_SEQUENCE_OUTPUT_GAIN_MAX_DB = 10.0
_FAIRLIGHT_TRACK_COLOR_FIELD = "Color"
_FAIRLIGHT_TRACK_COLOR_TYPE = 0x02
_FAIRLIGHT_TRACK_COLOR_VALUE_PREFIX = b"\x00"
_FAIRLIGHT_TRACK_COLOR_VALUES = {
    "Green": 0,
    "Teal": 1,
    "Blue": 2,
    "Purple": 3,
    "Pink": 4,
    "Tan": 5,
    "Brown": 6,
    "Apricot": 7,
    "Beige": 8,
    "Chocolate": 9,
    "Lime": 10,
    "Navy": 11,
    "Olive": 12,
    "Orange": 13,
    "Violet": 14,
    "Yellow": 15,
}
_FAIRLIGHT_TRACK_COLOR_NAMES_BY_VALUE = {
    value: name for name, value in _FAIRLIGHT_TRACK_COLOR_VALUES.items()
}
_FAIRLIGHT_TRACK_COLOR_ALIASES = {
    **{name.casefold(): name for name in _FAIRLIGHT_TRACK_COLOR_VALUES},
    "clear": "Clear",
    "clear color": "Clear",
    "none": "Clear",
}
_FAIRLIGHT_GROUP_STATE_TABLES = (
    {
        "result_key": "session_group_lists",
        "table": "SM_GroupList",
        "id_column": "SM_GroupList_id",
        "columns": (
            "SM_GroupList_id",
            "DbType",
            "Parent",
            "SM_Session_id",
            "Sequence",
            "Sm2Sequence_id",
        ),
    },
    {
        "result_key": "session_groups",
        "table": "SM_Group",
        "id_column": "SM_Group_id",
        "columns": (
            "SM_Group_id",
            "DbType",
            "GrpId",
            "GrpName",
            "SsnId",
            "RippleMode",
            "Parent",
            "SM_GroupList_id",
            "Sequence",
        ),
    },
    {
        "result_key": "session_group_memberships",
        "table": "SM_Group_SM_GroupList",
        "id_column": "DbOwner",
        "columns": ("DbOwner", "DbAssociate", "DbPropertyName", "DbIndex"),
    },
    {
        "result_key": "timeline_group_lists",
        "table": "Sm2GroupList",
        "id_column": "Sm2GroupList_id",
        "columns": (
            "Sm2GroupList_id",
            "DbType",
            "SM_Project_id",
            "LockSysId",
            "DbSavedTime",
        ),
    },
    {
        "result_key": "timeline_groups",
        "table": "Sm2Group",
        "id_column": "Sm2Group_id",
        "columns": (
            "Sm2Group_id",
            "DbType",
            "Name",
            "SM_Project_id",
            "Sm2GroupList_id",
            "pLmVerTable",
            "VersionTableLockSysId",
        ),
    },
    {
        "result_key": "timeline_group_memberships",
        "table": "Sm2Group_Sm2GroupList",
        "id_column": "DbOwner",
        "columns": ("DbOwner", "DbAssociate", "DbPropertyName", "DbIndex"),
    },
    {
        "result_key": "project_group_memberships",
        "table": "SM_Project_Sm2Group",
        "id_column": "DbOwner",
        "columns": ("DbOwner", "DbAssociate", "DbPropertyName", "DbIndex"),
    },
)


@dataclass(frozen=True)
class AudioGainBatchSelector:
    kind: str
    item_id: str | None = None
    track_index: int | None = None
    start_frame: int | None = None
    end_frame: int | None = None
    record_frame: int | None = None
    raw: dict[str, Any] | None = None


def _audio_track_count(conn) -> int:
    try:
        return int(conn.timeline.GetTrackCount("audio") or 0)
    except Exception as exc:
        raise APICallFailed(
            "Cannot inspect audio track count.",
            details={"track_type": "audio"},
        ) from exc


def _validate_audio_track_index(conn, index: int) -> int:
    if index < 1:
        raise ValidationError(
            "Audio track index must be 1 or greater.",
            details={"index": index, "track_type": "audio"},
        )

    count = _audio_track_count(conn)
    if index > count:
        raise ValidationError(
            "Audio track index does not exist.",
            details={
                "index": index,
                "audio_track_count": count,
                "valid_range": f"1-{count}" if count else "none",
                "readback_command": "cutagent fairlight tracks --json",
            },
        )
    return count


def _normalize_fairlight_track_color(color: str) -> str:
    normalized = str(color or "").strip().casefold()
    canonical = _FAIRLIGHT_TRACK_COLOR_ALIASES.get(normalized)
    if canonical is None:
        raise ValidationError(
            "Fairlight track color must be a supported DaVinci Resolve track color name.",
            details={
                "color": color,
                "allowed": sorted(set(_FAIRLIGHT_TRACK_COLOR_ALIASES.values())),
            },
            recoverability="not_applicable",
        )
    return canonical


def _decode_bmd_fields_blob_entries(
    blob: bytes | None,
) -> tuple[int, list[dict[str, Any]]]:
    data = bytes(blob or b"")
    if not data:
        return 1, []
    if len(data) < 8:
        raise ValidationError(
            "Fairlight track FieldsBlob is too small to decode.",
            details={"blob_bytes": len(data), "db_field": "Sm2TiTrack.FieldsBlob"},
            recoverability="manual",
        )
    offset = 0
    version, count = struct.unpack_from(">II", data, offset)
    offset += 8
    entries: list[dict[str, Any]] = []
    for entry_index in range(count):
        if offset + 4 > len(data):
            raise ValidationError(
                "Fairlight track FieldsBlob ended while reading a field key length.",
                details={
                    "entry_index": entry_index,
                    "blob_bytes": len(data),
                    "offset": offset,
                },
                recoverability="manual",
            )
        key_bytes = struct.unpack_from(">I", data, offset)[0]
        offset += 4
        end_key = offset + key_bytes
        if end_key + 4 > len(data):
            raise ValidationError(
                "Fairlight track FieldsBlob ended while reading a field key.",
                details={
                    "entry_index": entry_index,
                    "blob_bytes": len(data),
                    "offset": offset,
                    "key_bytes": key_bytes,
                },
                recoverability="manual",
            )
        key_raw = data[offset:end_key]
        offset = end_key
        try:
            key = key_raw.decode("utf-16-be")
        except UnicodeDecodeError as exc:
            raise ValidationError(
                "Fairlight track FieldsBlob contains an undecodable field key.",
                details={"entry_index": entry_index, "key_bytes": key_bytes},
                recoverability="manual",
            ) from exc
        value_type = struct.unpack_from(">I", data, offset)[0]
        offset += 4
        value_start = offset
        if value_type == _UI_TYPE_BOOL:
            value_end = offset + 2
        elif value_type in (_UI_TYPE_INT32, _UI_TYPE_ENUM_INT32):
            value_end = offset + 5
        elif value_type == _UI_TYPE_DOUBLE:
            value_end = offset + 9
        elif value_type == _UI_TYPE_BLOB:
            if offset + 5 > len(data):
                raise ValidationError(
                    "Fairlight track FieldsBlob ended while reading a blob field length.",
                    details={"entry_index": entry_index, "field": key},
                    recoverability="manual",
                )
            payload_bytes = struct.unpack_from(">I", data, offset + 1)[0]
            value_end = offset + 5 + payload_bytes
        else:
            raise ValidationError(
                "Fairlight track FieldsBlob contains an unsupported field value type.",
                details={
                    "entry_index": entry_index,
                    "field": key,
                    "value_type": value_type,
                },
                recoverability="manual",
            )
        if value_end > len(data):
            raise ValidationError(
                "Fairlight track FieldsBlob ended while reading a field value.",
                details={
                    "entry_index": entry_index,
                    "field": key,
                    "value_type": value_type,
                },
                recoverability="manual",
            )
        value_raw = data[value_start:value_end]
        offset = value_end
        entries.append({"key": key, "value_type": value_type, "value_raw": value_raw})
    if offset != len(data):
        raise ValidationError(
            "Fairlight track FieldsBlob has trailing undecoded bytes.",
            details={"blob_bytes": len(data), "decoded_bytes": offset},
            recoverability="manual",
        )
    return version, entries


def _encode_bmd_fields_blob_entries(
    version: int, entries: list[dict[str, Any]]
) -> bytes:
    payload = bytearray(struct.pack(">II", int(version), len(entries)))
    for entry in entries:
        key_raw = str(entry["key"]).encode("utf-16-be")
        payload += struct.pack(">I", len(key_raw))
        payload += key_raw
        payload += struct.pack(">I", int(entry["value_type"]))
        payload += bytes(entry["value_raw"])
    return bytes(payload)


def _track_color_value_from_entry(entry: dict[str, Any]) -> int:
    raw = bytes(entry["value_raw"])
    if int(entry["value_type"]) != _FAIRLIGHT_TRACK_COLOR_TYPE or len(raw) != 5:
        raise ValidationError(
            "Fairlight track Color field has an unsupported payload shape.",
            details={
                "db_field": "Sm2TiTrack.FieldsBlob.Color",
                "value_type": entry["value_type"],
                "payload_bytes": len(raw),
            },
            recoverability="manual",
        )
    return struct.unpack(">i", raw[1:5])[0]


def _read_track_color_value_from_fields_blob(blob: bytes | None) -> int | None:
    _version, entries = _decode_bmd_fields_blob_entries(blob)
    for entry in entries:
        if entry["key"] == _FAIRLIGHT_TRACK_COLOR_FIELD:
            return _track_color_value_from_entry(entry)
    return None


def _set_track_color_value_in_fields_blob(
    blob: bytes | None, color_value: int | None
) -> tuple[bytes | None, int | None]:
    version, entries = _decode_bmd_fields_blob_entries(blob)
    previous_value: int | None = None
    color_index: int | None = None
    for index, entry in enumerate(entries):
        if entry["key"] != _FAIRLIGHT_TRACK_COLOR_FIELD:
            continue
        color_index = index
        previous_value = _track_color_value_from_entry(entry)
        break

    if color_value is None:
        if color_index is not None:
            del entries[color_index]
    else:
        color_entry = {
            "key": _FAIRLIGHT_TRACK_COLOR_FIELD,
            "value_type": _FAIRLIGHT_TRACK_COLOR_TYPE,
            "value_raw": _FAIRLIGHT_TRACK_COLOR_VALUE_PREFIX
            + struct.pack(">i", int(color_value)),
        }
        if color_index is None:
            entries.append(color_entry)
        else:
            entries[color_index] = color_entry
    if not entries:
        return None, previous_value
    return _encode_bmd_fields_blob_entries(version, entries), previous_value


def _fairlight_track_color_name_from_value(value: int | None) -> str | None:
    if value is None:
        return None
    return _FAIRLIGHT_TRACK_COLOR_NAMES_BY_VALUE.get(
        int(value), f"unknown:{int(value)}"
    )


def _ensure_fairlight_page_for_track_state(conn) -> dict[str, Any]:
    resolve = getattr(conn, "resolve", None)
    if resolve is None:
        return {"available": False, "reason": "resolve_handle_unavailable"}

    get_current_page = getattr(resolve, "GetCurrentPage", None)
    open_page = getattr(resolve, "OpenPage", None)
    current_page = None
    if callable(get_current_page):
        try:
            current_page = get_current_page()
        except Exception:
            current_page = None

    if str(current_page or "").lower() == "fairlight":
        return {"available": True, "changed": False, "current_page": current_page}

    if not callable(open_page):
        return {
            "available": False,
            "reason": "open_page_unavailable",
            "current_page": current_page,
        }

    opened = open_page("fairlight")
    if opened is False:
        return {
            "available": True,
            "changed": False,
            "current_page": current_page,
            "open_result": opened,
            "error": "open_page_failed",
        }
    time.sleep(0.15)
    updated_page = None
    if callable(get_current_page):
        try:
            updated_page = get_current_page()
        except Exception:
            updated_page = None
    return {
        "available": True,
        "changed": str(updated_page or current_page or "").lower() == "fairlight",
        "previous_page": current_page,
        "current_page": updated_page,
        "open_result": opened,
        "native_api": "Resolve.OpenPage('fairlight')",
    }


def _set_audio_track_enabled(conn, index: int, enabled: bool) -> None:
    _validate_audio_track_index(conn, index)
    page_switch = _ensure_fairlight_page_for_track_state(conn)
    result = conn.timeline.SetTrackEnable("audio", index, enabled)
    getter = getattr(conn.timeline, "GetIsTrackEnabled", None)
    if callable(getter):
        actual = None
        deadline = time.monotonic() + 1.0
        while True:
            try:
                actual = bool(getter("audio", index))
            except Exception:
                actual = None
            else:
                if actual == bool(enabled):
                    set_verification_status("verified")
                    return
            if time.monotonic() >= deadline:
                break
            time.sleep(0.05)
        set_verification_status("failed")
        raise APICallFailed(
            "Failed to update audio track enabled state.",
            details={
                "index": index,
                "enabled": bool(enabled),
                "actual": actual,
                "api_result": result,
                "page_switch": page_switch,
            },
        )
    if result is False:
        set_verification_status("failed")
        raise APICallFailed(
            "Failed to update audio track enabled state.",
            details={"index": index, "enabled": bool(enabled), "api_result": result},
        )


def _set_audio_track_locked(conn, index: int, locked: bool) -> None:
    _validate_audio_track_index(conn, index)
    result = conn.timeline.SetTrackLock("audio", index, locked)
    getter = getattr(conn.timeline, "GetIsTrackLocked", None)
    if callable(getter):
        try:
            actual = bool(getter("audio", index))
        except Exception:
            actual = None
        else:
            if actual == bool(locked):
                set_verification_status("verified")
                return
        raise APICallFailed(
            "Failed to update audio track locked state.",
            details={
                "index": index,
                "locked": bool(locked),
                "actual": actual,
                "api_result": result,
            },
        )
    if result is False:
        raise APICallFailed(
            "Failed to update audio track locked state.",
            details={"index": index, "locked": bool(locked), "api_result": result},
        )


def _read_audio_track_enabled(conn, index: int) -> bool:
    getter = getattr(conn.timeline, "GetIsTrackEnabled", None)
    if callable(getter):
        try:
            return bool(getter("audio", index))
        except Exception:
            pass
    return True


def _read_audio_track_enabled_strict(conn, index: int) -> bool:
    """Read one audio-track enabled state without inventing a fallback value."""
    getter = getattr(conn.timeline, "GetIsTrackEnabled", None)
    if not callable(getter):
        raise APICallFailed(
            "DaVinci Resolve cannot read the audio track enabled state.",
            details={"index": index, "getter": "GetIsTrackEnabled"},
        )
    try:
        value = getter("audio", index)
    except Exception as exc:
        raise APICallFailed(
            "Failed to read the audio track enabled state.",
            details={"index": index, "error": str(exc)},
        ) from exc
    if not isinstance(value, bool):
        raise APICallFailed(
            "DaVinci Resolve returned an invalid audio track enabled state.",
            details={"index": index, "actual": value},
        )
    return value


def _read_audio_track_color(conn, index: int) -> str | None:
    getter = getattr(conn.timeline, "GetTrackColor", None)
    if not callable(getter):
        return None
    try:
        value = getter("audio", index)
    except TypeError:
        try:
            value = getter(index)
        except Exception:
            return None
    except Exception:
        return None
    if value in (None, ""):
        return None
    return str(value)


_FAIRLIGHT_TRACK_COLOR_DB_BLOCKER_EVIDENCE = {
    "source": "local DaVinci Resolve 20/21 Free Project.db schema scan",
    "sampled_project_db_count": 7,
    "read_scope": "negative_audio_track_color_schema_probe",
    "tables_checked": [
        "Sm2TiTrack",
        "Sm2Sequence",
        "SM_Setup",
        "BtClipProcParams",
        "FontRenderItem",
    ],
    "sm2_titrack_color_column_found": False,
    "audio_track_color_table_found": False,
    "color_columns_seen_are_not_audio_track_color": [
        "BtClipProcParams.REDColorSpace",
        "BtClipProcParams.REDColorVersion",
        "BtClipProcParams.SonyF65ColorSpace",
        "BtClipProcParams.DNGColorSpace",
        "FontRenderItem.ForegroundColor",
        "FontRenderItem.BackgroundColor",
        "SM_Setup.VOColorMode",
        "SM_Setup.VOColorMatrix",
        "SM_Setup.ColorScience",
        "SM_Setup.TimelineColorSpace",
    ],
    "write_readback_route_found": False,
    "resolve_21_embedded_recheck": {
        "runtime": "DaVinci Resolve 21.0.0.48 Free",
        "transport": "embedded_lua_http_poll",
        "artifact": "/tmp/cutagent_fairlight_display_control_cm_20260619/13_direct_runtime_read_probe_after_allowlist.json",
        "candidate_methods_not_available": [
            "Timeline.GetTrackColor('audio', index)",
        ],
        "unsupported_bridge_count": 0,
        "probe_result": "audio track color getter candidate reached DaVinci Resolve and returned method_not_available",
    },
}


def solo_audio_track(conn, index: int) -> Dict[str, Any]:
    """Solo one audio track by enabling it and disabling all other audio tracks."""
    count = _validate_audio_track_index(conn, index)
    previous_states = [
        {"index": i, "enabled": _read_audio_track_enabled_strict(conn, i)}
        for i in range(1, count + 1)
    ]

    for i in range(1, count + 1):
        _set_audio_track_enabled(conn, i, i == index)

    applied_states = [
        {"index": i, "enabled": _read_audio_track_enabled_strict(conn, i)}
        for i in range(1, count + 1)
    ]
    verified = all(row["enabled"] == (row["index"] == index) for row in applied_states)
    if verified:
        set_verification_status("verified")
    else:
        set_verification_status("failed")
        raise APICallFailed(
            "Failed to apply solo state to audio tracks.",
            details={
                "solo_index": index,
                "previous_states": previous_states,
                "applied_states": applied_states,
            },
        )

    return {
        "action": "fairlight.solo",
        "track_type": "audio",
        "solo_index": index,
        "previous_states": previous_states,
        "applied_states": applied_states,
        "restore_command": "cutagent fairlight solo-restore --states-json '<previous_states_json>' --json",
    }


def restore_audio_track_states(conn, states: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Restore audio track enabled states captured by solo_audio_track()."""
    if not isinstance(states, list) or not states:
        raise ValidationError(
            "Track state restore payload must be a non-empty JSON list.",
            details={"states": states},
            recoverability="not_applicable",
        )
    count = _audio_track_count(conn)
    normalized_states: list[dict[str, Any]] = []
    for row in states:
        if not isinstance(row, dict):
            raise ValidationError(
                "Each track state must be an object with index and enabled.",
                details={"row": row},
                recoverability="not_applicable",
            )
        try:
            track_index = int(row["index"])
        except Exception as exc:
            raise ValidationError(
                "Each track state must include an integer index.",
                details={"row": row},
                recoverability="not_applicable",
            ) from exc
        if track_index < 1 or track_index > count:
            raise ValidationError(
                "Audio track index in restore payload is out of range.",
                details={"index": track_index, "audio_track_count": count},
                recoverability="not_applicable",
            )
        normalized_states.append(
            {"index": track_index, "enabled": bool(row.get("enabled"))}
        )

    failures: list[dict[str, Any]] = []
    for row in normalized_states:
        try:
            _set_audio_track_enabled(conn, int(row["index"]), bool(row["enabled"]))
        except Exception as exc:
            failures.append(
                {"index": row["index"], "stage": "restore", "error": str(exc)}
            )

    applied_states: list[dict[str, Any]] = []
    for row in normalized_states:
        try:
            applied_states.append(
                {
                    "index": int(row["index"]),
                    "enabled": _read_audio_track_enabled_strict(
                        conn, int(row["index"])
                    ),
                }
            )
        except Exception as exc:
            failures.append(
                {"index": row["index"], "stage": "readback", "error": str(exc)}
            )
    verified = all(
        bool(expected["enabled"]) == bool(actual["enabled"])
        for expected, actual in zip(normalized_states, applied_states)
    )
    set_verification_status("verified" if verified and not failures else "failed")
    if not verified or failures:
        raise APICallFailed(
            "Failed to restore audio track states.",
            details={
                "requested_states": normalized_states,
                "applied_states": applied_states,
                "failures": failures,
            },
            recoverability="manual",
        )

    return {
        "action": "fairlight.solo_restore",
        "track_type": "audio",
        "restored_states": applied_states,
    }


def set_audio_track_color(conn, index: int, color: str) -> Dict[str, Any]:
    """Set a Fairlight audio track color through native APIs or the verified Disk DB route."""
    _validate_audio_track_index(conn, index)
    normalized_color = _normalize_fairlight_track_color(color)

    def _set_track_color_db() -> dict[str, Any]:
        timeline_name = _timeline_name(conn)
        if not timeline_name:
            raise APICallFailed(
                "No active timeline is available for Fairlight track color set."
            )
        return db_session.execute_sqlite_disk_db_mutation(
            conn,
            context="Fairlight track color set",
            writer=_fairlight_track_color_set_writer(
                timeline_name=timeline_name,
                index=index,
                color=normalized_color,
            ),
            verifier=_verify_fairlight_track_color_set(
                index=index,
                color=normalized_color,
            ),
            allow_project_name_inference=True,
        )

    def _raise_track_color_unavailable(*, runtime_error: str | None = None) -> None:
        details = {
            "capability_id": "fairlight.track_color",
            "track_type": "audio",
            "index": index,
            "requested_color": normalized_color,
            "required_native_api": "Timeline.SetTrackColor('audio', index, color)",
            "available_readback_api": "Timeline.GetTrackColor('audio', index) when exposed by the runtime",
            "db_schema_evidence": _FAIRLIGHT_TRACK_COLOR_DB_BLOCKER_EVIDENCE,
            "workaround": (
                "Use the verified Project.db route on Disk projects, or set the track color in DaVinci Resolve manually. "
                "CutAgent CLI will prefer the native track-color method if Blackmagic exposes it."
            ),
        }
        if runtime_error:
            details["runtime_error"] = runtime_error
            details["native_probe_evidence"] = {
                "probe_result": "method not available",
                "runtime_method": "Timeline.SetTrackColor",
                "mutating_write_confirmed": False,
            }
        raise CapabilityNegotiationFailed(
            "Audio track color is not available through this DaVinci Resolve scripting runtime.",
            details=details,
        )

    setter = getattr(conn.timeline, "SetTrackColor", None)
    if not callable(setter):
        return _set_track_color_db()

    try:
        result = setter("audio", index, normalized_color)
    except TypeError:
        try:
            result = setter(index, normalized_color)
        except APICallFailed as exc:
            if "method not available" in str(exc).lower():
                return _set_track_color_db()
            raise
    except APICallFailed as exc:
        if "method not available" in str(exc).lower():
            return _set_track_color_db()
        raise
    if result is False:
        return _set_track_color_db()

    readback = _read_audio_track_color(conn, index)
    if readback is not None and readback != normalized_color:
        set_verification_status("failed")
        raise APICallFailed(
            "Audio track color readback did not match requested color.",
            details={
                "index": index,
                "requested_color": normalized_color,
                "actual_color": readback,
            },
        )
    set_verification_status("verified" if readback is not None else "pending_manual")
    return {
        "action": "fairlight.track_color",
        "track_type": "audio",
        "index": index,
        "color": normalized_color,
        "readback_color": readback,
        "set": True,
        "route": "api_native",
    }


def _fairlight_track_color_rows(
    cursor: sqlite3.Cursor, *, timeline_name: str
) -> list[sqlite3.Row]:
    sequence = _fetch_timeline_sequence(cursor, timeline_name)
    return cursor.execute(
        """
        SELECT
          track.Sm2TiTrack_id AS track_id,
          track.FieldsBlob AS fields_blob,
          track.UserDefinedName AS name,
          COALESCE(rel.DbIndex, track.rowid - 1) AS track_order
        FROM Sm2TiTrack track
        LEFT JOIN Sm2SequenceContainer_Sm2TiTrack rel
          ON rel.DbAssociate = track.Sm2TiTrack_id
         AND rel.DbPropertyName = 'AudioTrackVec'
        WHERE track.Sequence = ? AND track.Type = 1
        ORDER BY track_order, track.rowid
        """,
        (sequence,),
    ).fetchall()


def _fairlight_track_color_set_writer(*, timeline_name: str, index: int, color: str):
    color_value = None if color == "Clear" else _FAIRLIGHT_TRACK_COLOR_VALUES[color]

    def _writer(
        connection: sqlite3.Connection,
        cursor: sqlite3.Cursor,
        session: db_session.DiskDbMutationSession,
    ) -> dict[str, Any]:
        rows = _fairlight_track_color_rows(cursor, timeline_name=timeline_name)
        if index > len(rows):
            raise ValidationError(
                "Audio track index does not exist in the DaVinci Resolve Disk project database.",
                details={
                    "index": index,
                    "audio_track_count": len(rows),
                    "timeline_name": timeline_name,
                },
                recoverability="not_applicable",
            )
        row = rows[index - 1]
        original_blob = row["fields_blob"] if row["fields_blob"] else None
        updated_blob, previous_value = _set_track_color_value_in_fields_blob(
            original_blob, color_value
        )
        changed = bytes(original_blob or b"") != bytes(updated_blob or b"")
        cursor.execute(
            "UPDATE Sm2TiTrack SET FieldsBlob = ? WHERE Sm2TiTrack_id = ?",
            (
                sqlite3.Binary(updated_blob) if updated_blob is not None else None,
                row["track_id"],
            ),
        )
        return {
            "action": "fairlight.track_color",
            "changed": changed,
            "track_type": "audio",
            "index": index,
            "track_id": row["track_id"],
            "track_name": row["name"] or f"Audio {index}",
            "timeline_name": timeline_name,
            "color": None if color == "Clear" else color,
            "requested_color": color,
            "color_value": color_value,
            "previous_color": _fairlight_track_color_name_from_value(previous_value),
            "previous_color_value": previous_value,
            "runtime_write_called": True,
            "native_api_attempted": False,
            "route": "db_workaround",
            "db_table": "Sm2TiTrack",
            "db_field": "FieldsBlob.Color",
            "db_storage": "BMD FieldsBlob UTF-16BE keyed value",
            "fields_blob_preserved": True,
            "updated_rows": cursor.rowcount,
        }

    return _writer


def _verify_fairlight_track_color_set(*, index: int, color: str):
    expected_value = None if color == "Clear" else _FAIRLIGHT_TRACK_COLOR_VALUES[color]

    def _verifier(
        conn,
        mutation_result: dict[str, Any],
        session: db_session.DiskDbMutationSession,
    ) -> dict[str, Any]:
        current_database = resolve_current_disk_project_db(
            conn, allow_project_name_inference=True
        )
        db_path = str(current_database["project_db_path"])
        timeline_name = (
            conn.timeline.GetName()
            if getattr(conn, "timeline", None)
            else mutation_result.get("timeline_name")
        )
        connection = sqlite3.connect(db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            rows = _fairlight_track_color_rows(
                connection.cursor(), timeline_name=str(timeline_name)
            )
            if index > len(rows):
                raise APICallFailed(
                    "Fairlight track color verification could not find the target audio track after project reopen.",
                    details={
                        "index": index,
                        "audio_track_count": len(rows),
                        "timeline_name": timeline_name,
                    },
                    recoverability="manual",
                )
            actual_value = _read_track_color_value_from_fields_blob(
                rows[index - 1]["fields_blob"]
            )
        finally:
            connection.close()
        ok = actual_value == expected_value
        verification = {
            "status": "verified" if ok else "failed",
            "expected_color": None if color == "Clear" else color,
            "expected_color_value": expected_value,
            "actual_color": _fairlight_track_color_name_from_value(actual_value),
            "actual_color_value": actual_value,
            "project_name": conn.project.GetName(),
            "timeline_name": timeline_name,
            "readback_route": "Sm2TiTrack.FieldsBlob.Color after project reopen",
            "native_api_readback": None,
        }
        if not ok:
            raise APICallFailed(
                "Fairlight track color verification failed after project reopen.",
                details={
                    "verification": verification,
                    "mutation_result": mutation_result,
                },
                recoverability="manual",
            )
        return verification

    return _verifier


def read_audio_track_color_db(conn, *, index: int) -> dict[str, Any]:
    """Read a Fairlight audio track color through the verified Disk DB route."""
    _validate_audio_track_index(conn, index)
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed(
            "No active timeline is available for Fairlight track color readback."
        )
    current_database = resolve_current_disk_project_db(
        conn, allow_project_name_inference=True
    )
    db_path = str(current_database["project_db_path"])
    connection = sqlite3.connect(db_path, timeout=5.0)
    connection.row_factory = sqlite3.Row
    try:
        rows = _fairlight_track_color_rows(
            connection.cursor(), timeline_name=str(timeline_name)
        )
        if index > len(rows):
            raise ValidationError(
                "Audio track index does not exist in the DaVinci Resolve Disk project database.",
                details={
                    "index": index,
                    "audio_track_count": len(rows),
                    "timeline_name": timeline_name,
                },
                recoverability="not_applicable",
            )
        row = rows[index - 1]
        color_value = _read_track_color_value_from_fields_blob(row["fields_blob"])
    finally:
        connection.close()
    return {
        "action": "fairlight.track_color.read",
        "track_type": "audio",
        "index": int(index),
        "track_id": row["track_id"],
        "track_name": row["name"] or f"Audio {index}",
        "timeline_name": timeline_name,
        "color": _fairlight_track_color_name_from_value(color_value),
        "color_value": color_value,
        "route": "db_workaround",
        "db_table": "Sm2TiTrack",
        "db_field": "FieldsBlob.Color",
        "readback_route": "Sm2TiTrack.FieldsBlob.Color",
        "project_db_path": db_path,
    }


def _list_audio_tracks_from_disk_db(
    conn, *, api_audio_track_count: int
) -> List[Dict[str, Any]]:
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        return []
    try:
        current_database = resolve_current_disk_project_db(
            conn, allow_project_name_inference=True
        )
    except Exception:
        return []
    db_path = (current_database or {}).get("project_db_path")
    if not db_path:
        return []

    try:
        connection = sqlite3.connect(db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            cursor = connection.cursor()
            timeline_row = cursor.execute(
                "SELECT Sequence FROM Sm2Timeline WHERE Name = ? LIMIT 1",
                (timeline_name,),
            ).fetchone()
            if timeline_row is None:
                return []
            sequence = timeline_row["Sequence"]
            rows = cursor.execute(
                """
                SELECT
                  track.Sm2TiTrack_id AS track_id,
                  track.UserDefinedName AS name,
                  track.SubType AS subtype,
                  COALESCE(rel.DbIndex, track.rowid - 1) AS track_order
                FROM Sm2TiTrack track
                LEFT JOIN Sm2SequenceContainer_Sm2TiTrack rel
                  ON rel.DbAssociate = track.Sm2TiTrack_id
                 AND rel.DbPropertyName = 'AudioTrackVec'
                WHERE track.Sequence = ? AND track.Type = 1
                ORDER BY track_order, track.rowid
                """,
                (sequence,),
            ).fetchall()
        finally:
            connection.close()
    except Exception:
        return []

    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        subtype = row["subtype"]
        track_format = None
        if subtype is not None:
            track_format = FAIRLIGHT_TRACK_TYPE_BY_AUDIO_SUBTYPE.get(
                int(subtype), f"subtype:{int(subtype)}"
            )
        result_row: dict[str, Any] = {
            "index": index,
            "name": row["name"] or f"Audio {index}",
            "clips": 0,
            "clip_count": 0,
            "enabled": "?",
            "enabled_bool": None,
            "locked": "",
            "locked_bool": None,
            "source": "disk_project_db",
            "db_readback": {
                "route": "Project.db",
                "project_db_path": str(db_path),
                "timeline_name": timeline_name,
                "timeline_sequence": sequence,
                "track_id": row["track_id"],
                "api_audio_track_count": int(api_audio_track_count),
            },
        }
        if track_format:
            result_row["format"] = track_format
        result.append(result_row)
    return result


def list_audio_tracks(conn) -> List[Dict[str, Any]]:
    """
    List audio tracks.

    Args:
        conn: ResolveConnection instance

    Returns:
        List of audio track info dicts
    """
    count = conn.timeline.GetTrackCount("audio") or 0
    if count == 0:
        db_rows = _list_audio_tracks_from_disk_db(conn, api_audio_track_count=count)
        if db_rows:
            set_verification_status("verified")
            return db_rows

    rows = []
    for i in range(1, count + 1):
        name = conn.timeline.GetTrackName("audio", i) or ""
        items = conn.timeline.GetItemListInTrack("audio", i) or []
        enabled = True
        try:
            enabled = conn.timeline.GetIsTrackEnabled("audio", i)
        except Exception:
            pass
        locked = False
        try:
            locked = conn.timeline.GetIsTrackLocked("audio", i)
        except Exception:
            pass
        row = {
            "index": i,
            "name": name,
            "clips": len(items),
            "clip_count": len(items),
            "enabled": "✓" if enabled else "✗",
            "enabled_bool": bool(enabled),
            "locked": "🔒" if locked else "",
            "locked_bool": bool(locked),
        }
        subtype = _read_audio_track_subtype(conn, i)
        if subtype:
            row["format"] = subtype
        color = _read_audio_track_color(conn, i)
        if color is not None:
            row["color"] = color
        mixer, db_readbacks = _optional_track_mixer_readbacks(conn, i)
        if mixer:
            row["mixer"] = mixer
            fader = mixer.get("fader")
            if isinstance(fader, dict):
                row["fader_db"] = fader.get("level_db")
                row["fader_channel_levels_db"] = fader.get("channel_levels_db")
            pan = mixer.get("pan")
            if isinstance(pan, dict):
                row["pan"] = pan.get("pan")
                row["pan_channel_values"] = pan.get("channel_pan_values")
        if db_readbacks:
            row["mixer_db_readback"] = db_readbacks
        display = _optional_track_display_readback(conn, i)
        if display:
            row["display"] = {"height": display}
            row["display_db_readback"] = {
                "height": {
                    "available": True,
                    "route": display.get("route"),
                    "db_blob": display.get("db_blob"),
                    "storage": display.get("storage"),
                    "read_consistency": display.get("read_consistency"),
                    "project_db_path": display.get("project_db_path"),
                }
            }
        rows.append(row)

    return rows


def _decode_sequence_ui_elements_state(blob: bytes | None) -> dict[str, Any]:
    if not blob:
        raise APICallFailed(
            "Timeline UIElementsState is missing from the DaVinci Resolve Disk project database.",
            details={"db_blob": "Sm2Sequence.UIElementsState"},
            recoverability="manual",
        )
    data = bytes(blob)
    if len(data) < 8:
        raise APICallFailed(
            "Timeline UIElementsState blob is too small to decode.",
            details={
                "db_blob": "Sm2Sequence.UIElementsState",
                "actual_bytes": len(data),
            },
            recoverability="manual",
        )

    try:
        version = struct.unpack_from(">I", data, 0)[0]
        entry_count = struct.unpack_from(">I", data, 4)[0]
        offset = 8
        entries: dict[str, dict[str, Any]] = {}
        for entry_index in range(1, entry_count + 1):
            entry_start = offset
            key_len = struct.unpack_from(">I", data, offset)[0]
            offset += 4
            if key_len <= 0 or key_len > 512 or offset + key_len + 5 > len(data):
                raise ValueError(f"invalid key length {key_len} at entry {entry_index}")
            key = data[offset : offset + key_len].decode("utf-16-be")
            offset += key_len
            value_type = struct.unpack_from(">I", data, offset)[0]
            offset += 4
            prefix = data[offset]
            offset += 1
            if value_type == _UI_TYPE_DOUBLE:
                value: Any = struct.unpack_from(">d", data, offset)[0]
                offset += 8
            elif value_type in {_UI_TYPE_INT32, _UI_TYPE_ENUM_INT32}:
                value = struct.unpack_from(">i", data, offset)[0]
                offset += 4
            elif value_type == _UI_TYPE_BOOL:
                value = bool(data[offset])
                offset += 1
            elif value_type == _UI_TYPE_BLOB:
                payload_len = struct.unpack_from(">I", data, offset)[0]
                offset += 4
                payload = data[offset : offset + payload_len]
                if len(payload) != payload_len:
                    raise ValueError(f"short blob payload at entry {entry_index}")
                item_count = (
                    struct.unpack_from(">I", payload, 0)[0] if len(payload) >= 4 else 0
                )
                values: list[int] = []
                for item_index in range(item_count):
                    value_offset = 4 + item_index * 4
                    if value_offset + 4 <= len(payload):
                        values.append(
                            struct.unpack_from(">i", payload, value_offset)[0]
                        )
                value = {
                    "payload_len": payload_len,
                    "count": item_count,
                    "values": values,
                }
                offset += payload_len
            else:
                raise ValueError(f"unknown value type 0x{value_type:x} for key {key}")
            entries[key] = {
                "entry_index": entry_index,
                "entry_start": entry_start,
                "value_type": value_type,
                "prefix": prefix,
                "value": value,
            }
        if offset != len(data):
            raise ValueError(f"decoded {offset} bytes, expected {len(data)}")
        return {"version": version, "entry_count": entry_count, "entries": entries}
    except Exception as exc:
        raise APICallFailed(
            "Failed to decode timeline UIElementsState blob from the DaVinci Resolve Disk project database.",
            details={
                "db_blob": "Sm2Sequence.UIElementsState",
                "error": str(exc),
                "actual_bytes": len(data),
            },
            recoverability="manual",
        ) from exc


def _read_track_display_height_state_from_cursor(
    cursor: sqlite3.Cursor,
    *,
    timeline_name: str,
    index: int,
    project_db_path: str | None = None,
) -> dict[str, Any]:
    sequence = _fetch_timeline_sequence(cursor, timeline_name)
    rows = _fetch_audio_track_rows(cursor, sequence=sequence)
    _validate_audio_track_db_index(rows, int(index))
    track = _track_payload(rows[int(index) - 1], index=int(index))
    row = cursor.execute(
        "SELECT UIElementsState FROM Sm2Sequence WHERE Sm2Sequence_id = ?",
        (sequence,),
    ).fetchone()
    if row is None:
        raise ValidationError(
            "Timeline sequence was not found in the DaVinci Resolve Disk project database.",
            details={
                "timeline_name": timeline_name,
                "timeline_sequence": sequence,
                "table": "Sm2Sequence",
            },
            recoverability="manual",
        )
    ui_state = _decode_sequence_ui_elements_state(
        row["UIElementsState"] if isinstance(row, sqlite3.Row) else row[0]
    )
    entries = ui_state["entries"]
    audio_clip_entry = entries.get(_UI_SEQUENCE_AUDIO_CLIP_HEIGHT_KEY)
    track_heights_entry = entries.get(
        _UI_SEQUENCE_USER_ADJUSTED_AUDIO_TRACK_HEIGHTS_KEY
    )
    if not isinstance(audio_clip_entry, dict) or not isinstance(
        track_heights_entry, dict
    ):
        raise APICallFailed(
            "Timeline UIElementsState does not contain Fairlight audio track display height keys.",
            details={
                "timeline_name": timeline_name,
                "timeline_sequence": sequence,
                "required_keys": [
                    _UI_SEQUENCE_AUDIO_CLIP_HEIGHT_KEY,
                    _UI_SEQUENCE_USER_ADJUSTED_AUDIO_TRACK_HEIGHTS_KEY,
                ],
                "available_keys": sorted(entries),
            },
            recoverability="manual",
        )
    track_height_value = track_heights_entry.get("value")
    adjusted_values = (
        list(track_height_value.get("values") or [])
        if isinstance(track_height_value, dict)
        else []
    )
    track_adjusted_value = (
        adjusted_values[int(index) - 1]
        if int(index) - 1 < len(adjusted_values)
        else None
    )
    return {
        "action": "fairlight.track.height.read",
        "track_type": "audio",
        "index": int(index),
        "timeline_name": timeline_name,
        "timeline_sequence": sequence,
        "track": track,
        "height": {
            "audio_clip_height": audio_clip_entry.get("value"),
            "track_adjusted_height": track_adjusted_value,
            "all_track_adjusted_heights": adjusted_values,
            "track_height_count": len(adjusted_values),
            "audio_track_count": len(rows),
            "values_match_track_count": len(adjusted_values) == len(rows),
            "value_semantics": "DaVinci Resolve UIElementsState values; read-only DB state, not a verified GUI resize write route.",
        },
        "route": "db_workaround",
        "db_blob": "Sm2Sequence.UIElementsState",
        "storage": "UI_SEQUENCE_AUDIO_CLIP_HEIGHT + UI_SEQUENCE_USER_ADJUSTED_AUDIO_TRACK_HEIGHTS",
        "ui_state_version": ui_state.get("version"),
        "ui_state_entry_count": ui_state.get("entry_count"),
        "read_consistency": "disk_project_db",
        "project_db_path": project_db_path,
        "set_supported": False,
        "set_blocker": "DaVinci Resolve 20 Free probe persisted DB writes to these keys, but Fairlight GUI height did not change after project reload.",
    }


def read_audio_track_height_state(conn, index: int) -> dict[str, Any]:
    _validate_audio_track_index(conn, int(index))
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed(
            "No active timeline is available for Fairlight track height readback."
        )
    current_database = resolve_current_disk_project_db(
        conn, allow_project_name_inference=True
    )
    project_db_path = str(current_database["project_db_path"])
    connection = sqlite3.connect(
        f"file:{project_db_path}?mode=ro", uri=True, timeout=5.0
    )
    connection.row_factory = sqlite3.Row
    try:
        return _read_track_display_height_state_from_cursor(
            connection.cursor(),
            timeline_name=timeline_name,
            index=int(index),
            project_db_path=project_db_path,
        )
    finally:
        connection.close()


def _optional_track_display_readback(conn, index: int) -> dict[str, Any] | None:
    try:
        state = read_audio_track_height_state(conn, int(index))
    except Exception:
        return None
    return {
        **dict(state.get("height") or {}),
        "route": state.get("route"),
        "db_blob": state.get("db_blob"),
        "storage": state.get("storage"),
        "read_consistency": state.get("read_consistency"),
        "project_db_path": state.get("project_db_path"),
        "set_supported": state.get("set_supported"),
    }


def _extract_length_prefixed_ascii_bus_labels(
    model: bytes,
) -> dict[str, list[dict[str, Any]]]:
    outputs: dict[str, list[dict[str, Any]]] = {"main_outputs": [], "buses": []}
    seen: set[tuple[str, str]] = set()
    for match in _FAIRLIGHT_BUS_LABEL_RE.finditer(model):
        start = int(match.start())
        label = match.group(1).decode("ascii")
        if start < 4:
            continue
        declared_len = struct.unpack("<I", model[start - 4 : start])[0]
        if declared_len != len(label):
            continue
        after = start + len(label)
        if after < len(model) and 32 <= model[after] <= 126:
            continue
        kind = "main" if label == "Main" else "bus"
        key = (kind, label)
        if key in seen:
            continue
        seen.add(key)
        entry = {
            "name": label,
            "kind": kind,
            "model_offset": start,
            "parser": "length_prefixed_ascii_label",
        }
        if kind == "main":
            outputs["main_outputs"].append(entry)
        else:
            outputs["buses"].append(entry)
    outputs["buses"].sort(
        key=lambda item: (int(str(item["name"]).split()[1]), int(item["model_offset"]))
    )
    outputs["main_outputs"].sort(key=lambda item: int(item["model_offset"]))
    return outputs


def _extract_length_prefixed_ascii_label_entries(
    model: bytes,
    *,
    pattern: re.Pattern[bytes],
    kind: str,
) -> list[dict[str, Any]]:
    labels: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in pattern.finditer(model):
        start = int(match.start())
        label = match.group(1).decode("ascii")
        if start < 4:
            continue
        declared_len = struct.unpack("<I", model[start - 4 : start])[0]
        if declared_len != len(label):
            continue
        after = start + len(label)
        if after < len(model) and 32 <= model[after] <= 126:
            continue
        if label in seen:
            continue
        seen.add(label)
        number_match = re.search(r"([0-9]+)$", label)
        labels.append(
            {
                "name": label,
                "kind": kind,
                "index": int(number_match.group(1)) if number_match else None,
                "model_offset": start,
                "parser": "length_prefixed_ascii_label",
            }
        )
    labels.sort(
        key=lambda item: (int(item.get("index") or 0), int(item["model_offset"]))
    )
    return labels


def _normalize_fairlight_effect_catalog_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).casefold()).strip("_")


def _iter_length_prefixed_ascii_strings(model: bytes) -> list[dict[str, Any]]:
    strings: list[dict[str, Any]] = []
    for offset in range(4, len(model)):
        declared_len = struct.unpack("<I", model[offset - 4 : offset])[0]
        if declared_len < 4 or declared_len > 128:
            continue
        end = offset + declared_len
        if end > len(model):
            continue
        raw = model[offset:end]
        if any(byte < 32 or byte > 126 for byte in raw):
            continue
        try:
            text = raw.decode("ascii")
        except UnicodeDecodeError:
            continue
        strings.append(
            {"text": text, "model_offset": offset, "declared_len": declared_len}
        )
    return strings


def _printable_ascii_window(raw: bytes) -> str:
    return "".join(chr(byte) if 32 <= byte <= 126 else "." for byte in raw)


def _fairlight_model_token_context(
    model: bytes,
    *,
    offset: int,
    token_text: str,
    context_bytes: int,
) -> dict[str, Any]:
    token_raw = token_text.encode("ascii", errors="ignore")
    token_length = len(token_raw)
    window_start = max(0, int(offset) - int(context_bytes))
    window_end = min(len(model), int(offset) + token_length + int(context_bytes))
    prefix_raw = model[window_start : int(offset)]
    token_window_raw = model[int(offset) : int(offset) + token_length]
    suffix_raw = model[int(offset) + token_length : window_end]
    declared_len = None
    length_prefix_hex = None
    if int(offset) >= 4:
        prefix = model[int(offset) - 4 : int(offset)]
        declared_len = struct.unpack("<I", prefix)[0]
        length_prefix_hex = prefix.hex()
    return {
        "model_offset": int(offset),
        "window_start": window_start,
        "window_end": window_end,
        "context_bytes": int(context_bytes),
        "token_text": token_text,
        "token_length": token_length,
        "declared_len": declared_len,
        "declared_len_matches_token": declared_len == token_length
        if declared_len is not None
        else False,
        "length_prefix_hex": length_prefix_hex,
        "window_ascii": _printable_ascii_window(model[window_start:window_end]),
        "prefix_hex": prefix_raw.hex(),
        "token_hex": token_window_raw.hex(),
        "suffix_hex": suffix_raw.hex(),
    }


def _attach_fairlight_model_token_contexts(
    model: bytes,
    rows: list[dict[str, Any]],
    *,
    context_bytes: int,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        token_text = str(
            item.get("raw_token") or item.get("text") or item.get("name") or ""
        )
        offsets = item.get("model_offsets") or []
        if not offsets and item.get("model_offset") is not None:
            offsets = [item["model_offset"]]
        contexts = [
            _fairlight_model_token_context(
                model,
                offset=int(offset),
                token_text=token_text,
                context_bytes=int(context_bytes),
            )
            for offset in offsets
        ]
        item["contexts"] = contexts
        enriched.append(item)
    return enriched


def _append_fairlight_effect_catalog_entry(
    buckets: dict[tuple[Any, ...], dict[str, Any]],
    *,
    key: tuple[Any, ...],
    entry: dict[str, Any],
    model_offset: int,
) -> None:
    existing = buckets.get(key)
    if existing is None:
        buckets[key] = {**entry, "model_offsets": [model_offset], "occurrence_count": 1}
        return
    offsets = list(existing.get("model_offsets") or [])
    if model_offset not in offsets:
        offsets.append(model_offset)
    existing["model_offsets"] = offsets
    existing["occurrence_count"] = len(offsets)


def _read_length_prefixed_ascii_at(model: bytes, offset: int) -> str | None:
    if offset < 0 or offset + 4 > len(model):
        return None
    declared_len = struct.unpack("<I", model[offset : offset + 4])[0]
    if declared_len < 1 or declared_len > 128:
        return None
    start = offset + 4
    end = start + declared_len
    if end > len(model):
        return None
    raw = model[start:end]
    if any(byte < 32 or byte > 126 for byte in raw):
        return None
    try:
        return raw.decode("ascii")
    except UnicodeDecodeError:
        return None


def _append_fairlight_bmd_effect_entry(
    buckets: dict[str, dict[str, Any]],
    *,
    plugin_id: str,
    name: str,
    effect_id: int,
    model_offset: int,
    adjacent_label: str | None,
) -> None:
    entry = buckets.get(plugin_id)
    if entry is None:
        entry = {
            "plugin_id": plugin_id,
            "name": name,
            "kind": "bmd_effect_id",
            "key": _normalize_fairlight_effect_catalog_key(name),
            "effect_id": effect_id,
            "labels": [],
            "raw_token": plugin_id,
            "parser": "length_prefixed_ascii_token",
            "model_offsets": [],
            "occurrence_count": 0,
        }
        buckets[plugin_id] = entry
    offsets = list(entry.get("model_offsets") or [])
    if model_offset not in offsets:
        offsets.append(model_offset)
    labels = list(entry.get("labels") or [])
    if adjacent_label and adjacent_label not in labels:
        labels.append(adjacent_label)
    entry["model_offsets"] = offsets
    entry["labels"] = labels
    entry["occurrence_count"] = len(offsets)


def _extract_fairlight_effect_catalog(model: bytes) -> dict[str, list[dict[str, Any]]]:
    track_fx: dict[tuple[Any, ...], dict[str, Any]] = {}
    macro_fx: dict[tuple[Any, ...], dict[str, Any]] = {}
    mix_levels: dict[tuple[Any, ...], dict[str, Any]] = {}
    automix_controls: dict[tuple[Any, ...], dict[str, Any]] = {}
    bus_processing_controls: dict[tuple[Any, ...], dict[str, Any]] = {}
    bmd_effects: dict[str, dict[str, Any]] = {}

    for row in _iter_length_prefixed_ascii_strings(model):
        text = str(row["text"])
        model_offset = int(row["model_offset"])
        bmd_match = _FAIRLIGHT_BMD_EFFECT_RE.match(text)
        if bmd_match:
            name = bmd_match.group(1)
            effect_id = int(bmd_match.group(2))
            adjacent_label = _read_length_prefixed_ascii_at(
                model, model_offset + len(text)
            )
            _append_fairlight_bmd_effect_entry(
                bmd_effects,
                plugin_id=text,
                name=name,
                effect_id=effect_id,
                model_offset=model_offset,
                adjacent_label=adjacent_label,
            )
            continue

        automix_match = _FAIRLIGHT_AUTOMIX_RE.match(text)
        if automix_match:
            name = automix_match.group(1)
            profile_value = automix_match.group(2)
            profile_index = int(profile_value) if profile_value is not None else None
            key = ("automix", name, profile_index)
            _append_fairlight_effect_catalog_entry(
                automix_controls,
                key=key,
                model_offset=model_offset,
                entry={
                    "name": name,
                    "kind": "automix_control",
                    "key": _normalize_fairlight_effect_catalog_key(name),
                    "profile_index": profile_index,
                    "raw_token": text,
                    "parser": "length_prefixed_ascii_token",
                },
            )
            continue

        bus_processing_match = _FAIRLIGHT_BUS_PROCESSING_RE.match(text)
        if bus_processing_match:
            name = bus_processing_match.group(1)
            key = ("bus_processing", name)
            _append_fairlight_effect_catalog_entry(
                bus_processing_controls,
                key=key,
                model_offset=model_offset,
                entry={
                    "name": name,
                    "kind": "bus_processing_control",
                    "key": _normalize_fairlight_effect_catalog_key(name),
                    "raw_token": text,
                    "parser": "length_prefixed_ascii_token",
                },
            )
            continue

        track_match = _FAIRLIGHT_TRACK_FX_SETTING_RE.match(text)
        if track_match:
            name = track_match.group(1)
            profile_index = int(track_match.group(2))
            setting_index = int(track_match.group(3))
            key = ("track_fx", name, profile_index, setting_index)
            _append_fairlight_effect_catalog_entry(
                track_fx,
                key=key,
                model_offset=model_offset,
                entry={
                    "name": name,
                    "kind": "track_fx_setting",
                    "key": _normalize_fairlight_effect_catalog_key(name),
                    "profile_index": profile_index,
                    "setting_index": setting_index,
                    "raw_token": text,
                    "parser": "length_prefixed_ascii_token",
                },
            )
            continue

        macro_match = _FAIRLIGHT_MACRO_FX_SETTING_RE.match(text)
        if macro_match:
            name = macro_match.group(1)
            macro_index = int(macro_match.group(2))
            key = ("macro_fx", name, macro_index)
            _append_fairlight_effect_catalog_entry(
                macro_fx,
                key=key,
                model_offset=model_offset,
                entry={
                    "name": name,
                    "kind": "macro_fx_setting",
                    "key": _normalize_fairlight_effect_catalog_key(name),
                    "macro_index": macro_index,
                    "raw_token": text,
                    "parser": "length_prefixed_ascii_token",
                },
            )
            continue

        mix_match = _FAIRLIGHT_MIX_LEVEL_RE.match(text)
        if mix_match:
            name = mix_match.group(1)
            profile_index = int(mix_match.group(2))
            key = ("mix_level", name, profile_index)
            _append_fairlight_effect_catalog_entry(
                mix_levels,
                key=key,
                model_offset=model_offset,
                entry={
                    "name": name,
                    "kind": "mix_level_control",
                    "key": _normalize_fairlight_effect_catalog_key(name),
                    "profile_index": profile_index,
                    "raw_token": text,
                    "parser": "length_prefixed_ascii_token",
                },
            )

    return {
        "track_fx_settings": sorted(
            track_fx.values(),
            key=lambda item: (
                int(item.get("profile_index") or 0),
                int(item.get("setting_index") or 0),
                str(item["name"]),
            ),
        ),
        "macro_fx_settings": sorted(
            macro_fx.values(),
            key=lambda item: (int(item.get("macro_index") or 0), str(item["name"])),
        ),
        "mix_level_controls": sorted(
            mix_levels.values(),
            key=lambda item: (int(item.get("profile_index") or 0), str(item["name"])),
        ),
        "automix_controls": sorted(
            automix_controls.values(),
            key=lambda item: (
                str(item["name"]),
                -1
                if item.get("profile_index") is None
                else int(item.get("profile_index") or 0),
            ),
        ),
        "bus_processing_controls": sorted(
            bus_processing_controls.values(),
            key=lambda item: str(item["name"]),
        ),
        "bmd_effects": sorted(
            bmd_effects.values(),
            key=lambda item: (
                str(item.get("name") or ""),
                str(item.get("plugin_id") or ""),
            ),
        ),
    }


def _read_fairlight_effect_catalog_from_cursor(
    cursor: sqlite3.Cursor,
    *,
    timeline_name: str,
    project_db_path: str | None,
) -> dict[str, Any]:
    sequence = _fetch_timeline_sequence(cursor, timeline_name)
    seq_blob = _fetch_sequence_fields_blob(cursor, sequence=sequence)
    decomp, _, _, _, _ = _decode_fairlight_model(seq_blob)
    catalog = _extract_fairlight_effect_catalog(bytes(decomp))
    return {
        "action": "fairlight.effect.catalog",
        "timeline_name": timeline_name,
        "timeline_sequence": sequence,
        **catalog,
        "counts": {
            "track_fx_settings": len(catalog["track_fx_settings"]),
            "macro_fx_settings": len(catalog["macro_fx_settings"]),
            "mix_level_controls": len(catalog["mix_level_controls"]),
            "automix_controls": len(catalog["automix_controls"]),
            "bus_processing_controls": len(catalog["bus_processing_controls"]),
            "bmd_effects": len(catalog["bmd_effects"]),
        },
        "route": "db_workaround",
        "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
        "storage": "length_prefixed_ascii_effect_catalog_tokens",
        "read_scope": "track_fx_macro_automix_bus_bmd_catalog_only",
        "read_consistency": "disk_project_db",
        "project_db_path": project_db_path,
        "slot_readback_supported": False,
        "param_readback_supported": False,
        "set_supported": False,
        "set_blocker": (
            "Track/bus plugin slot assignment, insertion/removal, bypass state, and arbitrary parameter routing "
            "remain unmapped; this command only reports Fairlight Track FX/Macro FX/AutoMix/bus-processing/BMD effect catalog tokens discovered in the timeline mixer model."
        ),
        "note": (
            "These entries are catalog tokens stored in DaVinci Resolve's Fairlight timeline mixer model, "
            "not proof that a plugin slot is active on a specific track or bus."
        ),
    }


def read_fairlight_effect_catalog_db(conn) -> dict[str, Any]:
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed(
            "No active timeline is available for Fairlight effect catalog read."
        )
    current_database = db_session.resolve_current_disk_project_db(
        conn,
        allow_project_name_inference=True,
    )
    project_db_path = str(current_database["project_db_path"])
    connection = sqlite3.connect(
        f"file:{project_db_path}?mode=ro", uri=True, timeout=5.0
    )
    connection.row_factory = sqlite3.Row
    try:
        return _read_fairlight_effect_catalog_from_cursor(
            connection.cursor(),
            timeline_name=timeline_name,
            project_db_path=project_db_path,
        )
    finally:
        connection.close()


def _fairlight_slot_probe_table_exists(cursor: sqlite3.Cursor, table_name: str) -> bool:
    row = cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _fairlight_slot_probe_row_to_dict(
    cursor: sqlite3.Cursor, row: Any
) -> dict[str, Any]:
    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}
    return {cursor.description[index][0]: value for index, value in enumerate(row)}


def _fetch_fairlight_audio_clip_rows_for_slot_probe(
    cursor: sqlite3.Cursor, *, timeline_name: str
) -> list[dict[str, Any]]:
    if not _fairlight_slot_probe_table_exists(cursor, "Sm2TiItem"):
        return []
    item_columns = db_timeline_rows.table_columns(cursor, "Sm2TiItem")
    media_timemap_select = (
        "item.MediaTimemapBA" if "MediaTimemapBA" in item_columns else "NULL"
    )
    media_timemap_fallback_select = (
        "MediaTimemapBA" if "MediaTimemapBA" in item_columns else "NULL"
    )
    if (
        timeline_name
        and _fairlight_slot_probe_table_exists(cursor, "Sm2Timeline")
        and _fairlight_slot_probe_table_exists(cursor, "Sm2TiTrack")
    ):
        try:
            sequence = _fetch_timeline_sequence(cursor, timeline_name)
            rows = cursor.execute(
                """
                SELECT
                    item.rowid AS db_rowid,
                    item.Sm2TiItem_id,
                    item.Name,
                    item.Sm2TiTrack_id,
                    item.Start,
                    item.Duration,
                    {media_timemap_select} AS MediaTimemapBA,
                    COALESCE(track_rel.DbIndex, track.rowid - 1) + 1 AS track_index
                FROM Sm2TiTrack track
                JOIN Sm2TiItem item
                  ON item.Sm2TiTrack_id = track.Sm2TiTrack_id
                 AND item.DbType = 'Sm2TiAudioClip'
                LEFT JOIN Sm2SequenceContainer_Sm2TiTrack track_rel
                  ON track_rel.DbAssociate = track.Sm2TiTrack_id
                 AND track_rel.DbPropertyName = 'AudioTrackVec'
                WHERE track.Sequence = ?
                  AND track.Type = 1
                ORDER BY COALESCE(track_rel.DbIndex, track.rowid), item.Start, item.rowid
                """.format(media_timemap_select=media_timemap_select),
                (sequence,),
            ).fetchall()
            if rows:
                return [_fairlight_slot_probe_row_to_dict(cursor, row) for row in rows]
        except sqlite3.Error:
            pass

    rows = cursor.execute(
        """
        SELECT
            rowid AS db_rowid,
            Sm2TiItem_id,
            Name,
            Sm2TiTrack_id,
            Start,
            Duration,
            {media_timemap_fallback_select} AS MediaTimemapBA,
            NULL AS track_index
        FROM Sm2TiItem
        WHERE DbType = 'Sm2TiAudioClip'
        ORDER BY rowid
        """.format(media_timemap_fallback_select=media_timemap_fallback_select)
    ).fetchall()
    return [_fairlight_slot_probe_row_to_dict(cursor, row) for row in rows]


def _clip_fx_plugins_for_slot_probe(
    cursor: sqlite3.Cursor, clip_rows: list[dict[str, Any]], *, limit: int
) -> tuple[list[dict[str, Any]], bool, int]:
    from . import audio_clip_fx

    plugins: list[dict[str, Any]] = []
    for row in clip_rows:
        clip_id = str(row.get("Sm2TiItem_id") or "")
        if not clip_id:
            continue
        try:
            state = audio_clip_fx.read_clip_fx_from_db(cursor, clip_id)
        except Exception:
            continue
        for plugin in getattr(state, "plugins", []) if state else []:
            param_count = len(getattr(plugin, "params", []) or [])
            plugins.append(
                {
                    "source": "clip_fx_payload",
                    "target": {
                        "kind": "audio_clip",
                        "clip_id": clip_id,
                        "name": row.get("Name"),
                        "track_index": row.get("track_index"),
                        "track_id": row.get("Sm2TiTrack_id"),
                    },
                    "plugin_id": getattr(plugin, "plugin_id", None),
                    "name": getattr(plugin, "name", None),
                    "param_count": param_count,
                    "slot_state": "clip_level_fx_payload_present",
                    "active_slot_verified": True,
                    "parser": "Sm2TiItem.FieldsBlob.FL::ClipFX",
                    "db_blob": "Sm2TiItem.FieldsBlob",
                }
            )
    total = len(plugins)
    return plugins[: int(limit)], total > int(limit), total


def _mixer_model_bmd_tokens_for_slot_probe(
    catalog: dict[str, list[dict[str, Any]]], *, limit: int
) -> tuple[list[dict[str, Any]], bool, int]:
    raw_tokens = list(catalog.get("bmd_effects") or [])
    entries: list[dict[str, Any]] = []
    for token in raw_tokens[: int(limit)]:
        entries.append(
            {
                "source": "timeline_mixer_model_bmd_token",
                "target": {
                    "kind": "timeline_mixer_model",
                },
                "plugin_id": token.get("plugin_id"),
                "name": token.get("name"),
                "effect_id": token.get("effect_id"),
                "labels": token.get("labels") or [],
                "model_offsets": token.get("model_offsets") or [],
                "occurrence_count": token.get("occurrence_count"),
                "slot_state": "catalog_or_mixer_token_only",
                "active_slot_verified": False,
                "parser": token.get("parser") or "length_prefixed_ascii_token",
                "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
            }
        )
    return entries, len(raw_tokens) > int(limit), len(raw_tokens)


def _read_fairlight_plugin_slot_probe_from_cursor(
    cursor: sqlite3.Cursor,
    *,
    timeline_name: str,
    project_db_path: str | None,
    limit: int,
) -> dict[str, Any]:
    sequence = _fetch_timeline_sequence(cursor, timeline_name)
    seq_blob = _fetch_sequence_fields_blob(cursor, sequence=sequence)
    decomp, _, _, _, _ = _decode_fairlight_model(seq_blob)
    catalog = _extract_fairlight_effect_catalog(bytes(decomp))
    mixer_tokens, mixer_truncated, mixer_total = _mixer_model_bmd_tokens_for_slot_probe(
        catalog, limit=int(limit)
    )
    try:
        clip_rows = _fetch_fairlight_audio_clip_rows_for_slot_probe(
            cursor, timeline_name=timeline_name
        )
    except sqlite3.Error:
        clip_rows = []
    clip_fx_plugins, clip_fx_truncated, clip_fx_total = _clip_fx_plugins_for_slot_probe(
        cursor,
        clip_rows,
        limit=int(limit),
    )
    candidates = [*mixer_tokens, *clip_fx_plugins]
    return {
        "action": "fairlight.effect.slot_scan",
        "timeline_name": timeline_name,
        "timeline_sequence": sequence,
        "route": "db_workaround",
        "read_scope": "mixer_model_bmd_tokens_and_clip_fx_payloads",
        "read_consistency": "disk_project_db",
        "project_db_path": project_db_path,
        "limit": int(limit),
        "found": bool(candidates),
        "count": len(candidates),
        "total_count": mixer_total + clip_fx_total,
        "counts": {
            "mixer_model_bmd_tokens": len(mixer_tokens),
            "clip_fx_plugins": len(clip_fx_plugins),
            "audio_clips_scanned": len(clip_rows),
        },
        "total_counts": {
            "mixer_model_bmd_tokens": mixer_total,
            "clip_fx_plugins": clip_fx_total,
            "audio_clips_scanned": len(clip_rows),
        },
        "truncated": mixer_truncated or clip_fx_truncated,
        "candidates": candidates,
        "mixer_model_bmd_tokens": mixer_tokens,
        "clip_fx_plugins": clip_fx_plugins,
        "db_readback": {
            "timeline_mixer_model": {
                "table": "Sm2Sequence",
                "column": "FieldsBlob",
                "payload": "FLStudioModelBA",
                "storage": "length_prefixed_ascii_bmd_tokens",
            },
            "clip_fx": {
                "table": "Sm2TiItem",
                "column": "FieldsBlob",
                "payload": "FL::ClipFX",
            },
        },
        "candidate_probe_supported": True,
        "clip_fx_payload_read_supported": True,
        "track_bus_slot_state_supported": False,
        "slot_insert_supported": False,
        "slot_remove_supported": False,
        "slot_bypass_supported": False,
        "param_routing_supported": False,
        "set_supported": False,
        "set_blocker": (
            "This command is a read-only Project.db scanner. Clip-level FL::ClipFX payloads prove stored clip FX "
            "payload presence; timeline mixer BMD tokens are candidate/catalog signals only. Track/bus slot "
            "assignment, insertion/removal, bypass state, and arbitrary parameter routing remain unmapped."
        ),
        "note": (
            "Use this scanner to gather DB evidence before promoting any Fairlight plugin slot route. "
            "Do not treat timeline mixer BMD tokens as active track/bus slots without separate GUI/readback verification."
        ),
    }


def read_fairlight_plugin_slot_probe_db(conn, *, limit: int = 100) -> dict[str, Any]:
    if limit < 1:
        raise ValidationError(
            "--limit must be 1 or greater.",
            details={"limit": limit, "min": 1},
            recoverability="not_applicable",
        )
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed(
            "No active timeline is available for Fairlight plugin slot scan."
        )
    current_database = db_session.resolve_current_disk_project_db(
        conn,
        allow_project_name_inference=True,
    )
    project_db_path = str(current_database["project_db_path"])
    connection = sqlite3.connect(
        f"file:{project_db_path}?mode=ro", uri=True, timeout=5.0
    )
    connection.row_factory = sqlite3.Row
    try:
        return _read_fairlight_plugin_slot_probe_from_cursor(
            connection.cursor(),
            timeline_name=timeline_name,
            project_db_path=project_db_path,
            limit=int(limit),
        )
    finally:
        connection.close()


def _read_fairlight_automation_list_from_cursor(
    cursor: sqlite3.Cursor,
    *,
    timeline_name: str,
    project_db_path: str | None,
    limit: int,
    include_context: bool = False,
    context_bytes: int = 32,
) -> dict[str, Any]:
    sequence = _fetch_timeline_sequence(cursor, timeline_name)
    seq_blob = _fetch_sequence_fields_blob(cursor, sequence=sequence)
    decomp, _, _, _, _ = _decode_fairlight_model(seq_blob)
    model = bytes(decomp)
    catalog = _extract_fairlight_effect_catalog(bytes(decomp))
    automix_controls = list(catalog["automix_controls"])
    mix_level_controls = list(catalog["mix_level_controls"])
    automix_truncated = len(automix_controls) > int(limit)
    mix_level_truncated = len(mix_level_controls) > int(limit)
    automix_controls = automix_controls[: int(limit)]
    mix_level_controls = mix_level_controls[: int(limit)]
    if include_context:
        automix_controls = _attach_fairlight_model_token_contexts(
            model,
            automix_controls,
            context_bytes=int(context_bytes),
        )
        mix_level_controls = _attach_fairlight_model_token_contexts(
            model,
            mix_level_controls,
            context_bytes=int(context_bytes),
        )
    return {
        "action": "fairlight.automation.list",
        "timeline_name": timeline_name,
        "timeline_sequence": sequence,
        "automix_controls": automix_controls,
        "mix_level_controls": mix_level_controls,
        "counts": {
            "automix_controls": len(automix_controls),
            "mix_level_controls": len(mix_level_controls),
        },
        "total_counts": {
            "automix_controls": len(catalog["automix_controls"]),
            "mix_level_controls": len(catalog["mix_level_controls"]),
        },
        "limit": int(limit),
        "truncated": automix_truncated or mix_level_truncated,
        "route": "db_workaround",
        "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
        "storage": "length_prefixed_ascii_tokens",
        "read_scope": "automix_and_mix_level_tokens_only",
        "context_supported": True,
        "context_included": bool(include_context),
        "context_bytes": int(context_bytes) if include_context else 0,
        "read_consistency": "disk_project_db",
        "project_db_path": project_db_path,
        "token_probe_supported": True,
        "lane_keyframes_supported": False,
        "write_supported": False,
        "set_supported": False,
        "set_blocker": (
            "This DB route reports stored AutoMix and MixLevel control tokens only. Fairlight automation lanes, "
            "keyframes, touch/latch/write modes, snapshots, and writes remain unmapped."
        ),
        "note": (
            "AutoMix and MixLevel tokens come from DaVinci Resolve's Fairlight mixer model; they are not proof "
            "of user-authored automation curves on a track, bus, plugin, send, EQ, or dynamics lane."
        ),
    }


def read_fairlight_automation_list_db(
    conn,
    *,
    limit: int = 50,
    include_context: bool = False,
    context_bytes: int = 32,
) -> dict[str, Any]:
    if limit < 1:
        raise ValidationError(
            "--limit must be 1 or greater.",
            details={"limit": limit, "min": 1},
            recoverability="not_applicable",
        )
    if context_bytes < 0 or context_bytes > 256:
        raise ValidationError(
            "--context-bytes must be between 0 and 256.",
            details={"context_bytes": context_bytes, "min": 0, "max": 256},
            recoverability="not_applicable",
        )
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed(
            "No active timeline is available for Fairlight automation list read."
        )
    current_database = db_session.resolve_current_disk_project_db(
        conn,
        allow_project_name_inference=True,
    )
    project_db_path = str(current_database["project_db_path"])
    connection = sqlite3.connect(
        f"file:{project_db_path}?mode=ro", uri=True, timeout=5.0
    )
    connection.row_factory = sqlite3.Row
    try:
        return _read_fairlight_automation_list_from_cursor(
            connection.cursor(),
            timeline_name=timeline_name,
            project_db_path=project_db_path,
            limit=int(limit),
            include_context=bool(include_context),
            context_bytes=int(context_bytes),
        )
    finally:
        connection.close()


def _read_fairlight_group_or_vca_labels_from_cursor(
    cursor: sqlite3.Cursor,
    *,
    timeline_name: str,
    project_db_path: str | None,
    action: str,
    label_kind: str,
    result_key: str,
    pattern: re.Pattern[bytes],
    assign_blocker: str,
    stored_group_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sequence = _fetch_timeline_sequence(cursor, timeline_name)
    seq_blob = _fetch_sequence_fields_blob(cursor, sequence=sequence)
    decomp, _, _, _, _ = _decode_fairlight_model(seq_blob)
    labels = _extract_length_prefixed_ascii_label_entries(
        bytes(decomp),
        pattern=pattern,
        kind=label_kind,
    )
    payload: dict[str, Any] = {
        "action": action,
        "timeline_name": timeline_name,
        "timeline_sequence": sequence,
        result_key: labels,
        "counts": {result_key: len(labels)},
        "route": "db_workaround",
        "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
        "storage": "length_prefixed_ascii_labels",
        "read_scope": "label_pool_and_stored_state"
        if stored_group_state
        else "labels_only",
        "read_consistency": "disk_project_db",
        "project_db_path": project_db_path,
        "label_pool": {
            "count": len(labels),
            "default_label_pool_only": True,
            "assignment_state_in_labels": False,
            "note": "These labels are the Fairlight mixer model's reusable label pool, not proof of active group membership.",
        },
        "assignment_supported": False,
        "set_supported": False,
        "set_blocker": assign_blocker,
        "note": (
            "DaVinci Resolve stores Fairlight label pools in the timeline mixer model. "
            "This readback reports available labels and, for groups, stored group-table rows when present; "
            "assignment mutation and VCA fader state remain unmapped."
        ),
    }
    if stored_group_state is not None:
        payload["stored_group_state"] = stored_group_state
    return payload


def _read_fairlight_group_state_tables_from_cursor(
    cursor: sqlite3.Cursor,
    *,
    timeline_name: str,
    sequence: str,
    limit: int,
) -> dict[str, Any]:
    tables: dict[str, Any] = {}
    counts: dict[str, int] = {}
    total_counts: dict[str, int] = {}
    for spec in _FAIRLIGHT_GROUP_STATE_TABLES:
        table_payload = _read_fairlight_io_table(
            cursor,
            table_name=str(spec["table"]),
            id_column=str(spec["id_column"]),
            columns=tuple(spec["columns"]),
            limit=int(limit),
        )
        result_key = str(spec["result_key"])
        tables[result_key] = table_payload
        counts[result_key] = int(table_payload["count"])
        total_counts[result_key] = int(table_payload["total_count"])
    actual_group_count = int(total_counts.get("session_groups", 0)) + int(
        total_counts.get("timeline_groups", 0)
    )
    membership_count = (
        int(total_counts.get("session_group_memberships", 0))
        + int(total_counts.get("timeline_group_memberships", 0))
        + int(total_counts.get("project_group_memberships", 0))
    )
    return {
        "source": "Project.db stored group tables",
        "timeline_name": timeline_name,
        "timeline_sequence": str(sequence),
        "db_tables": [str(spec["table"]) for spec in _FAIRLIGHT_GROUP_STATE_TABLES],
        "limit": int(limit),
        "found": actual_group_count > 0 or membership_count > 0,
        "table_row_found": any(total > 0 for total in total_counts.values()),
        "actual_group_count": actual_group_count,
        "membership_count": membership_count,
        "count": sum(counts.values()),
        "total_count": sum(total_counts.values()),
        "counts": counts,
        "total_counts": total_counts,
        **tables,
        "membership_mutation_supported": False,
        "link_options_supported": False,
    }


def read_fairlight_group_list_db(conn, *, limit: int = 50) -> dict[str, Any]:
    if limit < 1:
        raise ValidationError(
            "--limit must be 1 or greater.",
            details={"limit": limit, "min": 1},
            recoverability="not_applicable",
        )
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed(
            "No active timeline is available for Fairlight group list read."
        )
    current_database = db_session.resolve_current_disk_project_db(
        conn,
        allow_project_name_inference=True,
    )
    project_db_path = str(current_database["project_db_path"])
    connection = sqlite3.connect(
        f"file:{project_db_path}?mode=ro", uri=True, timeout=5.0
    )
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        sequence = _fetch_timeline_sequence(cursor, timeline_name)
        return _read_fairlight_group_or_vca_labels_from_cursor(
            cursor,
            timeline_name=timeline_name,
            project_db_path=project_db_path,
            action="fairlight.group.list",
            label_kind="group",
            result_key="groups",
            pattern=_FAIRLIGHT_GROUP_LABEL_RE,
            assign_blocker="Group creation, deletion, membership assignment, and link options remain unmapped.",
            stored_group_state=_read_fairlight_group_state_tables_from_cursor(
                cursor,
                timeline_name=timeline_name,
                sequence=sequence,
                limit=int(limit),
            ),
        )
    finally:
        connection.close()


def read_fairlight_vca_list_db(conn) -> dict[str, Any]:
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed(
            "No active timeline is available for Fairlight VCA list read."
        )
    current_database = db_session.resolve_current_disk_project_db(
        conn,
        allow_project_name_inference=True,
    )
    project_db_path = str(current_database["project_db_path"])
    connection = sqlite3.connect(
        f"file:{project_db_path}?mode=ro", uri=True, timeout=5.0
    )
    connection.row_factory = sqlite3.Row
    try:
        return _read_fairlight_group_or_vca_labels_from_cursor(
            connection.cursor(),
            timeline_name=timeline_name,
            project_db_path=project_db_path,
            action="fairlight.vca.list",
            label_kind="vca",
            result_key="vcas",
            pattern=_FAIRLIGHT_VCA_LABEL_RE,
            assign_blocker="VCA creation, assignment, fader, mute, and solo state remain unmapped.",
        )
    finally:
        connection.close()


def _read_fairlight_bus_labels_from_cursor(
    cursor: sqlite3.Cursor,
    *,
    timeline_name: str,
    project_db_path: str | None = None,
    include_context: bool = False,
    context_bytes: int = 32,
) -> dict[str, Any]:
    sequence = _fetch_timeline_sequence(cursor, timeline_name)
    sequence_row = cursor.execute(
        "SELECT NumOutputAudioChannels, OutputAudioGain FROM Sm2Sequence WHERE Sm2Sequence_id = ?",
        (sequence,),
    ).fetchone()
    seq_blob = _fetch_sequence_fields_blob(cursor, sequence=sequence)
    decomp, _, _, _, _ = _decode_fairlight_model(seq_blob)
    model = bytes(decomp)
    labels = _extract_length_prefixed_ascii_bus_labels(model)
    main_outputs = labels["main_outputs"]
    buses = labels["buses"]
    if include_context:
        main_outputs = _attach_fairlight_model_token_contexts(
            model,
            main_outputs,
            context_bytes=int(context_bytes),
        )
        buses = _attach_fairlight_model_token_contexts(
            model,
            buses,
            context_bytes=int(context_bytes),
        )
    return {
        "action": "fairlight.bus.list",
        "timeline_name": timeline_name,
        "timeline_sequence": sequence,
        "main_outputs": main_outputs,
        "buses": buses,
        "counts": {
            "main_outputs": len(main_outputs),
            "buses": len(buses),
        },
        "sequence_output": {
            "num_output_audio_channels": sequence_row["NumOutputAudioChannels"]
            if sequence_row is not None
            else None,
            "output_audio_gain": sequence_row["OutputAudioGain"]
            if sequence_row is not None
            else None,
            "note": "Sequence output fields are reported as DB context only; they are not treated as verified Fairlight bus fader controls.",
        },
        "route": "db_workaround",
        "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
        "storage": "length_prefixed_ascii_bus_labels",
        "read_scope": "labels_only",
        "context_supported": True,
        "context_included": bool(include_context),
        "context_bytes": int(context_bytes) if include_context else 0,
        "read_consistency": "disk_project_db",
        "project_db_path": project_db_path,
        "set_supported": False,
        "set_blocker": "Bus routing, FlexBus graph edits, sends, and bus/main fader/pan writes remain unmapped.",
    }


def read_fairlight_bus_list_db(
    conn,
    *,
    include_context: bool = False,
    context_bytes: int = 32,
) -> dict[str, Any]:
    if context_bytes < 0 or context_bytes > 256:
        raise ValidationError(
            "--context-bytes must be between 0 and 256.",
            details={"context_bytes": context_bytes, "min": 0, "max": 256},
            recoverability="not_applicable",
        )
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed(
            "No active timeline is available for Fairlight bus list read."
        )
    current_database = db_session.resolve_current_disk_project_db(
        conn,
        allow_project_name_inference=True,
    )
    project_db_path = str(current_database["project_db_path"])
    connection = sqlite3.connect(
        f"file:{project_db_path}?mode=ro", uri=True, timeout=5.0
    )
    connection.row_factory = sqlite3.Row
    try:
        return _read_fairlight_bus_labels_from_cursor(
            connection.cursor(),
            timeline_name=timeline_name,
            project_db_path=project_db_path,
            include_context=bool(include_context),
            context_bytes=int(context_bytes),
        )
    finally:
        connection.close()


def normalize_fairlight_main_output_selector(bus: str | None) -> str | None:
    normalized = re.sub(r"\s+", " ", str(bus or "").strip()).casefold()
    if normalized in _FAIRLIGHT_MAIN_OUTPUT_ALIASES:
        return "Main"
    return None


def validate_fairlight_sequence_output_gain_level(level_db: float) -> float:
    try:
        normalized = float(level_db)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Fairlight main output gain must be a finite dB value.",
            details={"level_db": level_db},
            recoverability="not_applicable",
        ) from exc
    if not math.isfinite(normalized):
        raise ValidationError(
            "Fairlight main output gain must be a finite dB value.",
            details={"level_db": level_db},
            recoverability="not_applicable",
        )
    if (
        normalized < _FAIRLIGHT_SEQUENCE_OUTPUT_GAIN_MIN_DB
        or normalized > _FAIRLIGHT_SEQUENCE_OUTPUT_GAIN_MAX_DB
    ):
        raise ValidationError(
            "Fairlight main output gain is outside the supported DaVinci Resolve level range.",
            details={
                "level_db": normalized,
                "min_db": _FAIRLIGHT_SEQUENCE_OUTPUT_GAIN_MIN_DB,
                "max_db": _FAIRLIGHT_SEQUENCE_OUTPUT_GAIN_MAX_DB,
            },
            recoverability="not_applicable",
        )
    return round(normalized, 1)


def read_fairlight_bus_level_db(conn, *, bus: str) -> dict[str, Any]:
    resolved_bus = normalize_fairlight_main_output_selector(bus)
    if not resolved_bus:
        raise CapabilityNegotiationFailed(
            "Only main-output sequence gain context is currently mapped for Fairlight bus level readback.",
            details={
                "capability_id": "fairlight.bus_routing",
                "requested_bus": bus,
                "supported_read_bus_selectors": ["Main", "Main 1"],
                "unsupported_scope": "non_main_bus_fader_readback",
                "reason": "Non-main bus/FlexBus fader storage is not safely mapped in the DaVinci Resolve Disk DB route.",
            },
            recoverability="manual",
        )
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed(
            "No active timeline is available for Fairlight bus level read."
        )
    current_database = db_session.resolve_current_disk_project_db(
        conn,
        allow_project_name_inference=True,
    )
    project_db_path = str(current_database["project_db_path"])
    connection = sqlite3.connect(
        f"file:{project_db_path}?mode=ro", uri=True, timeout=5.0
    )
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        sequence = _fetch_timeline_sequence(cursor, timeline_name)
        sequence_row = cursor.execute(
            "SELECT NumOutputAudioChannels, OutputAudioGain FROM Sm2Sequence WHERE Sm2Sequence_id = ?",
            (sequence,),
        ).fetchone()
        bus_readback = _read_fairlight_bus_labels_from_cursor(
            cursor,
            timeline_name=timeline_name,
            project_db_path=project_db_path,
            include_context=True,
            context_bytes=16,
        )
        return {
            "action": "fairlight.bus.level",
            "timeline_name": timeline_name,
            "timeline_sequence": sequence,
            "bus": {
                "requested": bus,
                "resolved": resolved_bus,
                "kind": "main_output",
            },
            "sequence_output_gain_context": {
                "output_audio_gain": sequence_row["OutputAudioGain"]
                if sequence_row is not None
                else None,
                "num_output_audio_channels": (
                    sequence_row["NumOutputAudioChannels"]
                    if sequence_row is not None
                    else None
                ),
                "db_table": "Sm2Sequence",
                "db_field": "OutputAudioGain",
                "verified_fader_read_supported": False,
                "note": (
                    "This is sequence output gain DB context only. It is not treated as verified Fairlight "
                    "main bus fader readback until a GUI-matched storage route is proven."
                ),
            },
            "bus_readback": {
                "main_outputs": bus_readback.get("main_outputs") or [],
                "buses": bus_readback.get("buses") or [],
                "counts": bus_readback.get("counts") or {},
            },
            "route": "db_workaround",
            "db_table": "Sm2Sequence",
            "db_field": "OutputAudioGain",
            "read_scope": "sequence_output_gain_context_only",
            "read_consistency": "disk_project_db",
            "project_db_path": project_db_path,
            "sequence_output_gain_read_supported": True,
            "verified_fader_read_supported": False,
            "sequence_output_gain_set_supported": True,
            "verified_fader_set_supported": False,
            "set_supported": True,
            "set_scope": "sequence_output_gain_context_only",
            "set_blocker": (
                "Only Sm2Sequence.OutputAudioGain writes are mapped. Bus/main mixer fader writes remain "
                "unmapped until a GUI-matched Fairlight mixer strip storage route is proven."
            ),
        }
    finally:
        connection.close()


def _fairlight_bus_level_set_writer(*, timeline_name: str, bus: str, level_db: float):
    normalized_level = validate_fairlight_sequence_output_gain_level(level_db)

    def _writer(
        connection: sqlite3.Connection,
        cursor: sqlite3.Cursor,
        session: db_session.DiskDbMutationSession,
    ) -> dict[str, Any]:
        sequence = _fetch_timeline_sequence(cursor, timeline_name)
        before = cursor.execute(
            "SELECT NumOutputAudioChannels, OutputAudioGain FROM Sm2Sequence WHERE Sm2Sequence_id = ?",
            (sequence,),
        ).fetchone()
        previous = before["OutputAudioGain"] if before is not None else None
        cursor.execute(
            "UPDATE Sm2Sequence SET OutputAudioGain = ? WHERE Sm2Sequence_id = ?",
            (normalized_level, sequence),
        )
        return {
            "action": "fairlight.bus.level",
            "changed": previous != normalized_level,
            "timeline_name": timeline_name,
            "timeline_sequence": sequence,
            "bus": {
                "requested": bus,
                "resolved": "Main",
                "kind": "main_output",
            },
            "previous_output_audio_gain": previous,
            "output_audio_gain": normalized_level,
            "level_db": normalized_level,
            "num_output_audio_channels": before["NumOutputAudioChannels"]
            if before is not None
            else None,
            "updated_rows": cursor.rowcount,
            "route": "db_native",
            "db_table": "Sm2Sequence",
            "db_field": "OutputAudioGain",
            "storage": "sequence_output_gain_context_only",
            "set_scope": "sequence_output_gain_context_only",
            "sequence_output_gain_set_supported": True,
            "verified_fader_set_supported": False,
        }

    return _writer


def _verify_fairlight_bus_level_set(*, bus: str, level_db: float):
    normalized_level = validate_fairlight_sequence_output_gain_level(level_db)

    def _verifier(
        conn,
        mutation_result: dict[str, Any],
        session: db_session.DiskDbMutationSession,
    ) -> dict[str, Any]:
        readback = read_fairlight_bus_level_db(conn, bus=bus)
        actual = readback["sequence_output_gain_context"]["output_audio_gain"]
        ok = actual == normalized_level
        verification = {
            "status": "verified" if ok else "failed",
            "expected_output_audio_gain": normalized_level,
            "actual_output_audio_gain": actual,
            "read_scope": readback.get("read_scope"),
            "set_scope": "sequence_output_gain_context_only",
            "verified_fader_read_supported": readback.get(
                "verified_fader_read_supported"
            ),
            "verified_fader_set_supported": False,
            "project_name": conn.project.GetName(),
            "timeline_name": conn.timeline.GetName(),
            "native_api_readback": None,
            "native_api_note": (
                "DaVinci Resolve does not expose Fairlight main bus fader readback through the scripting API; "
                "verification reads the reopened Disk DB Sm2Sequence.OutputAudioGain value."
            ),
        }
        if not ok:
            raise APICallFailed(
                "Fairlight main output gain verification failed after project reopen.",
                details={
                    "verification": verification,
                    "mutation_result": mutation_result,
                },
                recoverability="manual",
            )
        return verification

    return _verifier


def set_fairlight_bus_level_db(
    conn,
    *,
    bus: str | None = None,
    bus_name: str | None = None,
    level_db: float,
) -> dict[str, Any]:
    bus = bus if bus is not None else bus_name
    resolved_bus = normalize_fairlight_main_output_selector(bus)
    if not resolved_bus:
        raise CapabilityNegotiationFailed(
            "Only main-output sequence gain DB writes are currently mapped for Fairlight bus level.",
            details={
                "capability_id": "fairlight.bus_routing",
                "requested_bus": bus,
                "requested_level_db": level_db,
                "supported_write_bus_selectors": ["Main", "Main 1"],
                "unsupported_scope": "non_main_bus_fader_write",
                "reason": "Non-main bus/FlexBus fader storage is not safely mapped in the DaVinci Resolve Disk DB route.",
            },
            recoverability="manual",
        )
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed(
            "No active timeline is available for Fairlight main output gain set."
        )
    normalized_level = validate_fairlight_sequence_output_gain_level(level_db)
    return db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Fairlight main output gain set",
        writer=_fairlight_bus_level_set_writer(
            timeline_name=timeline_name,
            bus=bus,
            level_db=normalized_level,
        ),
        verifier=_verify_fairlight_bus_level_set(
            bus=bus,
            level_db=normalized_level,
        ),
        allow_project_name_inference=True,
    )


def _fairlight_send_token_kind(text: str) -> str:
    normalized = str(text or "").casefold()
    if "send" in normalized:
        return "send_token"
    if "aux" in normalized:
        return "aux_token"
    if (
        "prefader" in normalized
        or "pre-fader" in normalized
        or "pre fader" in normalized
    ):
        return "pre_fader_token"
    if (
        "postfader" in normalized
        or "post-fader" in normalized
        or "post fader" in normalized
    ):
        return "post_fader_token"
    return "send_related_token"


def _extract_fairlight_send_tokens(
    model: bytes, *, limit: int
) -> tuple[list[dict[str, Any]], bool]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in _iter_length_prefixed_ascii_strings(model):
        text = str(row["text"])
        if not _FAIRLIGHT_SEND_TOKEN_RE.search(text):
            continue
        key = _normalize_fairlight_effect_catalog_key(text)
        entry = buckets.get(key)
        if entry is None:
            entry = {
                "text": text,
                "key": key,
                "kind": _fairlight_send_token_kind(text),
                "parser": "length_prefixed_ascii_token",
                "model_offsets": [],
                "occurrence_count": 0,
            }
            buckets[key] = entry
        offsets = list(entry.get("model_offsets") or [])
        model_offset = int(row["model_offset"])
        if model_offset not in offsets:
            offsets.append(model_offset)
        entry["model_offsets"] = offsets
        entry["occurrence_count"] = len(offsets)
    tokens = sorted(
        buckets.values(),
        key=lambda item: (str(item.get("kind") or ""), str(item.get("key") or "")),
    )
    truncated = len(tokens) > int(limit)
    return tokens[: int(limit)], truncated


def _read_fairlight_send_list_from_cursor(
    cursor: sqlite3.Cursor,
    *,
    timeline_name: str,
    project_db_path: str | None = None,
    limit: int = 50,
    include_context: bool = False,
    context_bytes: int = 32,
) -> dict[str, Any]:
    sequence = _fetch_timeline_sequence(cursor, timeline_name)
    seq_blob = _fetch_sequence_fields_blob(cursor, sequence=sequence)
    decomp, _, _, _, _ = _decode_fairlight_model(seq_blob)
    model = bytes(decomp)
    send_tokens, truncated = _extract_fairlight_send_tokens(model, limit=int(limit))
    bus_labels = _extract_length_prefixed_ascii_bus_labels(model)
    candidate_destinations = [*bus_labels["main_outputs"], *bus_labels["buses"]]
    if include_context:
        send_tokens = _attach_fairlight_model_token_contexts(
            model,
            send_tokens,
            context_bytes=int(context_bytes),
        )
        candidate_destinations = _attach_fairlight_model_token_contexts(
            model,
            candidate_destinations,
            context_bytes=int(context_bytes),
        )
    return {
        "action": "fairlight.send.list",
        "timeline_name": timeline_name,
        "timeline_sequence": sequence,
        "send_tokens": send_tokens,
        "candidate_destinations": candidate_destinations,
        "counts": {
            "send_tokens": len(send_tokens),
            "candidate_destinations": len(candidate_destinations),
            "main_outputs": len(bus_labels["main_outputs"]),
            "buses": len(bus_labels["buses"]),
        },
        "limit": int(limit),
        "truncated": truncated,
        "found": bool(send_tokens),
        "route": "db_workaround",
        "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
        "storage": "length_prefixed_ascii_tokens",
        "read_scope": "send_token_probe_and_bus_destinations",
        "context_supported": True,
        "context_included": bool(include_context),
        "context_bytes": int(context_bytes) if include_context else 0,
        "read_consistency": "disk_project_db",
        "project_db_path": project_db_path,
        "token_probe_supported": True,
        "slot_state_read_supported": False,
        "assignment_supported": False,
        "set_supported": False,
        "set_blocker": (
            "This DB route probes stored send/aux-related tokens and bus destination labels only. "
            "Per-track send slot assignment, send level/pan/pre-post/mute state, and send mutation remain unmapped."
        ),
        "note": (
            "An empty send_tokens list means no send-related length-prefixed tokens were found in the current "
            "timeline mixer model; candidate_destinations are bus labels, not proof of active send slots."
        ),
    }


def read_fairlight_send_list_db(
    conn,
    *,
    limit: int = 50,
    include_context: bool = False,
    context_bytes: int = 32,
) -> dict[str, Any]:
    if limit < 1:
        raise ValidationError(
            "--limit must be 1 or greater.",
            details={"limit": limit, "min": 1},
            recoverability="not_applicable",
        )
    if context_bytes < 0 or context_bytes > 256:
        raise ValidationError(
            "--context-bytes must be between 0 and 256.",
            details={"context_bytes": context_bytes, "min": 0, "max": 256},
            recoverability="not_applicable",
        )
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed(
            "No active timeline is available for Fairlight send list read."
        )
    current_database = db_session.resolve_current_disk_project_db(
        conn,
        allow_project_name_inference=True,
    )
    project_db_path = str(current_database["project_db_path"])
    connection = sqlite3.connect(
        f"file:{project_db_path}?mode=ro", uri=True, timeout=5.0
    )
    connection.row_factory = sqlite3.Row
    try:
        return _read_fairlight_send_list_from_cursor(
            connection.cursor(),
            timeline_name=timeline_name,
            project_db_path=project_db_path,
            limit=int(limit),
            include_context=bool(include_context),
            context_bytes=int(context_bytes),
        )
    finally:
        connection.close()


def _record_info_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "t", "yes", "y"}:
        return True
    if normalized in {"0", "false", "f", "no", "n"}:
        return False
    return None


def _record_info_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "record_info_id": row["SyRecordInfo_id"],
        "name": row["RecordInfoName"],
        "status": row["Status"],
        "record_mode": row["RecordMode"],
        "timeline_id": row["Timeline"],
        "timeline_name": row["TimelineName"],
        "session_id": row["Session"],
        "project_name": row["ProjectName"],
        "session_name": row["SessionName"],
        "user_name": row["UserName"],
        "creation_time": row["CreationTime"],
        "target_dir": row["RecordTargetDir"],
        "prefix": row["RecordPrefix"],
        "suffix": row["RecordSuffix"],
        "format": {
            "type": row["RecordFormatType"],
            "subtype": row["RecordFormatSubType"],
            "fps": row["RecordFPS"],
            "bit_depth": row["RecordBitDepth"],
            "quality": row["RecordQuality"],
            "width": row["FormatWidth"],
            "height": row["FormatHeight"],
            "pixel_aspect_ratio": row["FormatPixelAspectRatio"],
        },
        "audio": {
            "enabled": _record_info_bool(row["RecordAudioEnabled"]),
            "channels": row["RecordAudioNumChannels"],
            "bit_depth": row["RecordAudioBitDepth"],
        },
        "range": {
            "start_frame": row["RecordStartFrame"],
            "end_frame": row["RecordEndFrame"],
            "total_frames": row["RecordTotalFrame"],
            "old_frame": row["RecordOldFrame"],
            "new_frame": row["RecordNewFrame"],
            "clip_start_frame": row["RecordClipStartFrame"],
            "use_clip_start_frame": _record_info_bool(row["UseRecordClipStartFrame"]),
        },
        "progress": {
            "completion_percentage": row["CompletionPercentage"],
            "time_taken_ms": row["TimeTakenToRenderInMs"],
            "estimated_remaining_ms": row["EstimatedTimeRemainingInMs"],
        },
        "error": {
            "code": row["ErrorCode"],
            "message": row["ErrorStr"],
            "notified": _record_info_bool(row["ErrorNotified"]),
        },
        "flags": {
            "record_cancelled": _record_info_bool(row["RecordCancelled"]),
            "record_as_float": _record_info_bool(row["RecordAsFloat"]),
            "record_clip_unique_name": _record_info_bool(row["RecordClipUniqueName"]),
            "record_set_timeline_timecode": _record_info_bool(
                row["RecordSetTimelineTimecode"]
            ),
            "render_at_source_resolution": _record_info_bool(
                row["RenderAtSourceResolution"]
            ),
            "use_render_cached_images": _record_info_bool(
                row["UseRenderCachedImagesForRecording"]
            ),
        },
    }


def _read_fairlight_record_info_from_cursor(
    cursor: sqlite3.Cursor,
    *,
    project_db_path: str | None,
    active_timeline_name: str | None,
    limit: int,
) -> dict[str, Any]:
    total_row = cursor.execute("SELECT COUNT(*) AS count FROM SyRecordInfo").fetchone()
    total_count = int(total_row["count"] if total_row is not None else 0)
    rows = cursor.execute(
        """
        SELECT
            r.SyRecordInfo_id,
            r.RecordInfoName,
            r.Status,
            r.RecordMode,
            r.Timeline,
            t.Name AS TimelineName,
            r.Session,
            r.ProjectName,
            r.SessionName,
            r.UserName,
            r.CreationTime,
            r.RecordTargetDir,
            r.RecordPrefix,
            r.RecordSuffix,
            r.RecordFormatType,
            r.RecordFormatSubType,
            r.RecordFPS,
            r.RecordBitDepth,
            r.RecordQuality,
            r.FormatWidth,
            r.FormatHeight,
            r.FormatPixelAspectRatio,
            r.RecordAudioEnabled,
            r.RecordAudioNumChannels,
            r.RecordAudioBitDepth,
            r.RecordStartFrame,
            r.RecordEndFrame,
            r.RecordTotalFrame,
            r.RecordOldFrame,
            r.RecordNewFrame,
            r.RecordClipStartFrame,
            r.UseRecordClipStartFrame,
            r.CompletionPercentage,
            r.TimeTakenToRenderInMs,
            r.EstimatedTimeRemainingInMs,
            r.ErrorCode,
            r.ErrorStr,
            r.ErrorNotified,
            r.RecordCancelled,
            r.RecordAsFloat,
            r.RecordClipUniqueName,
            r.RecordSetTimelineTimecode,
            r.RenderAtSourceResolution,
            r.UseRenderCachedImagesForRecording
        FROM SyRecordInfo r
        LEFT JOIN Sm2Timeline t ON t.Sm2Timeline_id = r.Timeline
        ORDER BY
            COALESCE(r.DisplayOrder, 2147483647),
            COALESCE(r.CreationTime, ''),
            r.SyRecordInfo_id
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    record_infos = [_record_info_row(row) for row in rows]
    return {
        "action": "fairlight.record.info",
        "record_infos": record_infos,
        "count": len(record_infos),
        "total_count": total_count,
        "limit": int(limit),
        "found": bool(record_infos),
        "active_timeline_name": active_timeline_name,
        "route": "db_workaround",
        "db_tables": ["SyRecordInfo", "Sm2Timeline"],
        "read_scope": "stored_record_setup_only",
        "read_consistency": "disk_project_db",
        "project_db_path": project_db_path,
        "record_arm_supported": False,
        "record_transport_supported": False,
        "take_management_supported": False,
        "set_supported": False,
        "set_blocker": (
            "DaVinci Resolve stores record setup/status rows in Project.db, but Fairlight audio track arm, input patch, "
            "record start/stop, and take-management controls remain unmapped and are not exposed by the scripting API."
        ),
    }


def read_fairlight_record_info_db(conn, *, limit: int = 20) -> dict[str, Any]:
    if limit < 1:
        raise ValidationError(
            "--limit must be 1 or greater.",
            details={"limit": limit, "min": 1},
            recoverability="not_applicable",
        )
    current_database = db_session.resolve_current_disk_project_db(
        conn,
        allow_project_name_inference=True,
    )
    project_db_path = str(current_database["project_db_path"])
    connection = sqlite3.connect(
        f"file:{project_db_path}?mode=ro", uri=True, timeout=5.0
    )
    connection.row_factory = sqlite3.Row
    try:
        return _read_fairlight_record_info_from_cursor(
            connection.cursor(),
            project_db_path=project_db_path,
            active_timeline_name=_timeline_name(conn),
            limit=limit,
        )
    finally:
        connection.close()


_FAIRLIGHT_ADR_TABLE_RE = re.compile(r"(adr|cue|take)", re.IGNORECASE)
_FAIRLIGHT_ADR_COLUMN_RE = re.compile(
    r"(adr|cue|prompt|streamer|beep|autocue|pre.?roll|post.?roll)",
    re.IGNORECASE,
)
_FAIRLIGHT_ADR_ID_COLUMNS = (
    "ADRCue_id",
    "ADR_Cue_id",
    "Cue_id",
    "Take_id",
    "SM_UserSetup_id",
    "SM_Setup_id",
    "SyRecordInfo_id",
    "SmTimelineFilter_id",
)


def _fairlight_adr_table_kind(table_name: str, matching_columns: list[str]) -> str:
    normalized = table_name.lower()
    if "adr" in normalized and "cue" in normalized:
        return "adr_cue_candidate"
    if "adr" in normalized and "take" in normalized:
        return "adr_take_candidate"
    if "cue" in normalized:
        return "cue_candidate"
    if "take" in normalized:
        return "take_candidate"
    if any(column.lower().startswith("autocue") for column in matching_columns):
        return "autocue_setup_signal"
    return "adr_related_setup_signal"


def _fairlight_adr_candidate_payload(
    cursor: sqlite3.Cursor,
    *,
    table_name: str,
    table_type: str,
    columns: list[str],
    matching_columns: list[str],
    limit: int,
) -> dict[str, Any]:
    columns = list(columns)
    matching_columns = list(matching_columns)
    id_column = next(
        (column for column in _FAIRLIGHT_ADR_ID_COLUMNS if column in columns),
        columns[0] if columns else "",
    )
    selected_columns: list[str] = []
    if id_column:
        selected_columns.append(id_column)
    for column in matching_columns:
        if column not in selected_columns:
            selected_columns.append(column)
    if not selected_columns:
        selected_columns = columns[:8]
    table_payload = _read_fairlight_io_table(
        cursor,
        table_name=table_name,
        id_column=id_column,
        columns=tuple(selected_columns[:16]),
        limit=limit,
    )
    table_name_matches = bool(_FAIRLIGHT_ADR_TABLE_RE.search(table_name))
    return {
        "table": table_name,
        "type": table_type,
        "kind": _fairlight_adr_table_kind(table_name, matching_columns),
        "table_name_matches": table_name_matches,
        "matching_columns": matching_columns,
        "available_columns": columns,
        "row_count": int(table_payload["count"]),
        "total_row_count": int(table_payload["total_count"]),
        "truncated": bool(table_payload.get("truncated")),
        "selected_columns": table_payload["columns"],
        "rows": table_payload["rows"],
    }


def _read_fairlight_adr_info_from_cursor(
    cursor: sqlite3.Cursor,
    *,
    project_db_path: str | None,
    active_timeline_name: str | None,
    limit: int,
) -> dict[str, Any]:
    storage_rows = cursor.execute(
        "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view') ORDER BY name"
    ).fetchall()
    candidates: list[dict[str, Any]] = []
    for storage_row in storage_rows:
        table_name = str(
            storage_row["name"]
            if isinstance(storage_row, sqlite3.Row)
            else storage_row[0]
        )
        table_type = str(
            storage_row["type"]
            if isinstance(storage_row, sqlite3.Row)
            else storage_row[1]
        )
        columns = sorted(_table_columns(cursor, table_name))
        matching_columns = [
            column for column in columns if _FAIRLIGHT_ADR_COLUMN_RE.search(column)
        ]
        if not _FAIRLIGHT_ADR_TABLE_RE.search(table_name) and not matching_columns:
            continue
        candidates.append(
            _fairlight_adr_candidate_payload(
                cursor,
                table_name=table_name,
                table_type=table_type,
                columns=columns,
                matching_columns=matching_columns,
                limit=limit,
            )
        )
    strong_candidates = [
        candidate for candidate in candidates if candidate["table_name_matches"]
    ]
    setup_signals = [
        candidate for candidate in candidates if not candidate["table_name_matches"]
    ]
    cue_rows_found = any(
        candidate["total_row_count"] > 0 for candidate in strong_candidates
    )
    return {
        "action": "fairlight.adr.info",
        "active_timeline_name": active_timeline_name,
        "route": "db_workaround",
        "read_scope": "adr_schema_probe_and_setup_signals",
        "read_consistency": "disk_project_db",
        "project_db_path": project_db_path,
        "limit": int(limit),
        "found": bool(candidates),
        "candidate_count": len(candidates),
        "cue_schema_found": bool(strong_candidates),
        "cue_rows_found": cue_rows_found,
        "strong_candidates": strong_candidates,
        "setup_signals": setup_signals,
        "counts": {
            "strong_candidates": len(strong_candidates),
            "setup_signals": len(setup_signals),
        },
        "cue_list_supported": cue_rows_found,
        "cue_mutation_supported": False,
        "record_supported": False,
        "take_management_supported": False,
        "set_supported": False,
        "set_blocker": (
            "This DB route probes project storage for ADR cue/take tables and setup signals only. "
            "On projects without a discovered ADR cue/take table, cue listing, cue mutation, ADR recording, "
            "beeps/streamers/prompts, and take review remain unmapped."
        ),
        "note": (
            "AutoCue, pre-roll, post-roll, or beep setup columns are setup signals, not proof of stored ADR cue rows."
        ),
    }


def read_fairlight_adr_info_db(conn, *, limit: int = 20) -> dict[str, Any]:
    if limit < 1:
        raise ValidationError(
            "--limit must be 1 or greater.",
            details={"limit": limit, "min": 1},
            recoverability="not_applicable",
        )
    current_database = db_session.resolve_current_disk_project_db(
        conn,
        allow_project_name_inference=True,
    )
    project_db_path = str(current_database["project_db_path"])
    connection = sqlite3.connect(
        f"file:{project_db_path}?mode=ro", uri=True, timeout=5.0
    )
    connection.row_factory = sqlite3.Row
    try:
        return _read_fairlight_adr_info_from_cursor(
            connection.cursor(),
            project_db_path=project_db_path,
            active_timeline_name=_timeline_name(conn),
            limit=limit,
        )
    finally:
        connection.close()


_FAIRLIGHT_IO_INFO_TABLES: tuple[dict[str, Any], ...] = (
    {
        "table": "SM_AudioSettings",
        "result_key": "audio_settings",
        "id_column": "SM_AudioSettings_id",
        "columns": (
            "SM_AudioSettings_id",
            "EnableAudio",
            "NumChannel",
            "BitDepth",
            "SampleRate",
            "FileName",
            "SourceIndex",
            "Offset",
            "SM_VTRInputSettings_id",
            "SM_VTROutputSettings_id",
            "FieldsBlob",
        ),
    },
    {
        "table": "SM_VTRInputSettings",
        "result_key": "vtr_input_settings",
        "id_column": "SM_VTRInputSettings_id",
        "columns": (
            "SM_VTRInputSettings_id",
            "InputFolder",
            "TapeMarkIn",
            "TapeMarkOut",
            "ReelName",
            "UpdateTCOnCrashRecord",
            "CaptureTCFromExtInput",
            "Prefix",
            "AudioSettings",
            "SM_VTRConfiguration_id",
            "FieldsBlob",
        ),
    },
    {
        "table": "SM_VTROutputSettings",
        "result_key": "vtr_output_settings",
        "id_column": "SM_VTROutputSettings_id",
        "columns": (
            "SM_VTROutputSettings_id",
            "ClipForOutput",
            "ClipMarkIn",
            "ClipMarkOut",
            "ClipFrameStart",
            "ClipFrameEnd",
            "TapeMarkIn",
            "TapeMarkOut",
            "OutputVITC",
            "OutputLTC",
            "LTCDelay",
            "BatchOutputMode",
            "AudioSettings",
            "SM_VTRConfiguration_id",
            "FieldsBlob",
        ),
    },
    {
        "table": "SM_VTRConfiguration",
        "result_key": "vtr_configurations",
        "id_column": "SM_VTRConfiguration_id",
        "columns": (
            "SM_VTRConfiguration_id",
            "VTRStandard",
            "VTRColorMode",
            "VTRColorMatrix",
            "VTRBitDepth",
            "VTREditMode",
            "VTRTCType",
            "VTRSyncMode",
            "InputSettings",
            "OutputSettings",
            "SM_Setup_id",
            "FieldsBlob",
        ),
    },
)


def _quote_sqlite_identifier(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


def _table_columns(cursor: sqlite3.Cursor, table_name: str) -> list[str]:
    try:
        rows = cursor.execute(
            f"PRAGMA table_info({_quote_sqlite_identifier(table_name)})"
        ).fetchall()
    except sqlite3.Error:
        return []
    columns: list[str] = []
    for row in rows:
        try:
            columns.append(str(row["name"] if isinstance(row, sqlite3.Row) else row[1]))
        except Exception:
            continue
    return columns


def _fairlight_io_json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {
            "byte_count": len(value),
            "preview_hex": value[:16].hex(),
        }
    return value


def _read_fairlight_io_table(
    cursor: sqlite3.Cursor,
    *,
    table_name: str,
    id_column: str,
    columns: tuple[str, ...],
    limit: int,
) -> dict[str, Any]:
    available_columns = _table_columns(cursor, table_name)
    if not available_columns:
        return {
            "table": table_name,
            "available": False,
            "count": 0,
            "total_count": 0,
            "limit": int(limit),
            "columns": [],
            "rows": [],
        }
    selected_columns = [column for column in columns if column in available_columns]
    if not selected_columns:
        selected_columns = available_columns[:8]
    quoted_table = _quote_sqlite_identifier(table_name)
    quoted_columns = ", ".join(
        _quote_sqlite_identifier(column) for column in selected_columns
    )
    order_clause = ""
    if id_column in available_columns:
        order_clause = f" ORDER BY {_quote_sqlite_identifier(id_column)}"
    total_row = cursor.execute(
        f"SELECT COUNT(*) AS count FROM {quoted_table}"
    ).fetchone()
    total_count = int(
        total_row["count"] if isinstance(total_row, sqlite3.Row) else total_row[0]
    )
    rows = cursor.execute(
        f"SELECT {quoted_columns} FROM {quoted_table}{order_clause} LIMIT ?",
        (int(limit),),
    ).fetchall()
    payload_rows = [
        {
            key: _fairlight_io_json_value(value)
            for key, value in _row_to_dict(cursor, row).items()
        }
        for row in rows
    ]
    return {
        "table": table_name,
        "available": True,
        "count": len(payload_rows),
        "total_count": total_count,
        "limit": int(limit),
        "truncated": total_count > len(payload_rows),
        "columns": selected_columns,
        "rows": payload_rows,
    }


def _read_fairlight_io_info_from_cursor(
    cursor: sqlite3.Cursor,
    *,
    project_db_path: str | None,
    active_timeline_name: str | None,
    limit: int,
) -> dict[str, Any]:
    tables: dict[str, Any] = {}
    counts: dict[str, int] = {}
    total_counts: dict[str, int] = {}
    for spec in _FAIRLIGHT_IO_INFO_TABLES:
        table_payload = _read_fairlight_io_table(
            cursor,
            table_name=str(spec["table"]),
            id_column=str(spec["id_column"]),
            columns=tuple(spec["columns"]),
            limit=int(limit),
        )
        result_key = str(spec["result_key"])
        tables[result_key] = table_payload
        counts[result_key] = int(table_payload["count"])
        total_counts[result_key] = int(table_payload["total_count"])
    found = any(count > 0 for count in total_counts.values())
    return {
        "action": "fairlight.io.info",
        "active_timeline_name": active_timeline_name,
        "route": "db_workaround",
        "db_tables": [str(spec["table"]) for spec in _FAIRLIGHT_IO_INFO_TABLES],
        "read_scope": "stored_patch_io_setup_only",
        "read_consistency": "disk_project_db",
        "project_db_path": project_db_path,
        "limit": int(limit),
        "found": found,
        "count": sum(counts.values()),
        "total_count": sum(total_counts.values()),
        "counts": counts,
        "total_counts": total_counts,
        **tables,
        "patch_mutation_supported": False,
        "hardware_route_probe_supported": False,
        "input_monitor_supported": False,
        "set_supported": False,
        "set_blocker": (
            "DaVinci Resolve stores some project-level audio/VTR patch setup rows in Project.db, "
            "but Fairlight hardware input/output enumeration, track patch mutation, and input monitoring controls "
            "remain unmapped and are not exposed by the scripting API."
        ),
    }


def read_fairlight_io_info_db(conn, *, limit: int = 20) -> dict[str, Any]:
    if limit < 1:
        raise ValidationError(
            "--limit must be 1 or greater.",
            details={"limit": limit, "min": 1},
            recoverability="not_applicable",
        )
    current_database = db_session.resolve_current_disk_project_db(
        conn,
        allow_project_name_inference=True,
    )
    project_db_path = str(current_database["project_db_path"])
    connection = sqlite3.connect(
        f"file:{project_db_path}?mode=ro", uri=True, timeout=5.0
    )
    connection.row_factory = sqlite3.Row
    try:
        return _read_fairlight_io_info_from_cursor(
            connection.cursor(),
            project_db_path=project_db_path,
            active_timeline_name=_timeline_name(conn),
            limit=limit,
        )
    finally:
        connection.close()


_FAIRLIGHT_METER_SETTINGS_TABLES = (
    {
        "table": "SM_UserSetup",
        "result_key": "user_setup",
        "id_column": "SM_UserSetup_id",
        "columns": (
            "SM_UserSetup_id",
            "ResolveVersion",
            "CurrentPage",
            "TargetMonitor",
            "EnableAudio",
            "MuteAudio",
            "MasterAudioDisable",
            "AudioMeterDBUEnable",
            "AudioMeterAlignmentLevel",
            "ApplyWfmDuringRecord",
            "DisableCcDuringRecording",
            "DisablePtzDuringRecording",
            "AudioFile",
            "LastRecordFrameNum",
            "RecordSpeed",
            "PanelBeepEnabled",
            "FieldsBlob",
        ),
    },
    {
        "table": "SM_Setup",
        "result_key": "record_setup",
        "id_column": "SM_Setup_id",
        "columns": (
            "SM_Setup_id",
            "IsRecording",
            "IsVTRRecording",
            "RecordAudioEnabled",
            "RecordAudioNumChannels",
            "RecordAudioBitDepth",
            "RecordFormatType",
            "RecordFormatSubType",
            "RecordFPS",
            "RecordTargetDir",
            "PreRollDurationType",
            "PreRollDurationSecs",
            "PreRollDurationFrames",
            "PostRollDurationType",
            "PostRollDurationSecs",
            "PostRollDurationFrames",
            "UseTimelineKeyframes",
            "FieldsBlob",
        ),
    },
)


def _read_fairlight_meter_settings_from_cursor(
    cursor: sqlite3.Cursor,
    *,
    project_db_path: str | None,
    active_timeline_name: str | None,
    limit: int,
) -> dict[str, Any]:
    tables: dict[str, Any] = {}
    counts: dict[str, int] = {}
    total_counts: dict[str, int] = {}
    for spec in _FAIRLIGHT_METER_SETTINGS_TABLES:
        table_payload = _read_fairlight_io_table(
            cursor,
            table_name=str(spec["table"]),
            id_column=str(spec["id_column"]),
            columns=tuple(spec["columns"]),
            limit=int(limit),
        )
        result_key = str(spec["result_key"])
        tables[result_key] = table_payload
        counts[result_key] = int(table_payload["count"])
        total_counts[result_key] = int(table_payload["total_count"])
    found = any(count > 0 for count in total_counts.values())
    return {
        "action": "fairlight.mixer.meter_settings",
        "active_timeline_name": active_timeline_name,
        "route": "db_workaround",
        "db_tables": [str(spec["table"]) for spec in _FAIRLIGHT_METER_SETTINGS_TABLES],
        "read_scope": "stored_audio_meter_setup_only",
        "read_consistency": "disk_project_db",
        "project_db_path": project_db_path,
        "limit": int(limit),
        "found": found,
        "count": sum(counts.values()),
        "total_count": sum(total_counts.values()),
        "counts": counts,
        "total_counts": total_counts,
        **tables,
        "live_meter_values_supported": False,
        "peak_hold_supported": False,
        "loudness_analysis_supported": False,
        "monitor_control_supported": False,
        "set_supported": False,
        "set_blocker": (
            "DaVinci Resolve may persist project/user audio-meter preferences in SM_UserSetup and SM_Setup, "
            "but live Fairlight meter values, peak/hold state, loudness analysis, and control-room monitoring "
            "remain unmapped and are not exposed by the scripting API."
        ),
    }


def read_fairlight_meter_settings_db(conn, *, limit: int = 20) -> dict[str, Any]:
    if limit < 1:
        raise ValidationError(
            "--limit must be 1 or greater.",
            details={"limit": limit, "min": 1},
            recoverability="not_applicable",
        )
    current_database = db_session.resolve_current_disk_project_db(
        conn,
        allow_project_name_inference=True,
    )
    project_db_path = str(current_database["project_db_path"])
    connection = sqlite3.connect(
        f"file:{project_db_path}?mode=ro", uri=True, timeout=5.0
    )
    connection.row_factory = sqlite3.Row
    try:
        return _read_fairlight_meter_settings_from_cursor(
            connection.cursor(),
            project_db_path=project_db_path,
            active_timeline_name=_timeline_name(conn),
            limit=limit,
        )
    finally:
        connection.close()


_FAIRLIGHT_LOUDNESS_TABLE_RE = re.compile(
    r"(loud|lufs|true.?peak|bs.?1770|ebu|atsc|itu)", re.IGNORECASE
)
_FAIRLIGHT_LOUDNESS_COLUMN_RE = re.compile(
    r"(loud|lufs|true.?peak|bs.?1770|ebu|atsc|itu|integrated|short.?term|audio.?meter)",
    re.IGNORECASE,
)
_FAIRLIGHT_LOUDNESS_SETUP_RE = re.compile(
    r"(AudioMeterDBUEnable|AudioMeterAlignmentLevel)", re.IGNORECASE
)
_FAIRLIGHT_LOUDNESS_ID_COLUMNS = (
    "Loudness_id",
    "LoudnessAnalysis_id",
    "SM_UserSetup_id",
    "SM_Setup_id",
)


def _fairlight_loudness_candidate_kind(
    table_name: str, matching_columns: list[str]
) -> str:
    if _FAIRLIGHT_LOUDNESS_TABLE_RE.search(table_name):
        return "loudness_storage_candidate"
    if any(
        not _FAIRLIGHT_LOUDNESS_SETUP_RE.fullmatch(column)
        for column in matching_columns
    ):
        return "loudness_column_candidate"
    return "meter_setup_signal"


def _read_fairlight_loudness_info_from_cursor(
    cursor: sqlite3.Cursor,
    *,
    project_db_path: str | None,
    active_timeline_name: str | None,
    limit: int,
) -> dict[str, Any]:
    storage_rows = cursor.execute(
        "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view') ORDER BY name"
    ).fetchall()
    candidates: list[dict[str, Any]] = []
    for storage_row in storage_rows:
        table_name = str(
            storage_row["name"]
            if isinstance(storage_row, sqlite3.Row)
            else storage_row[0]
        )
        table_type = str(
            storage_row["type"]
            if isinstance(storage_row, sqlite3.Row)
            else storage_row[1]
        )
        columns = sorted(_table_columns(cursor, table_name))
        matching_columns = [
            column for column in columns if _FAIRLIGHT_LOUDNESS_COLUMN_RE.search(column)
        ]
        if not _FAIRLIGHT_LOUDNESS_TABLE_RE.search(table_name) and not matching_columns:
            continue
        id_column = next(
            (column for column in _FAIRLIGHT_LOUDNESS_ID_COLUMNS if column in columns),
            columns[0] if columns else "",
        )
        selected_columns: list[str] = []
        if id_column:
            selected_columns.append(id_column)
        for column in matching_columns:
            if column not in selected_columns:
                selected_columns.append(column)
        table_payload = _read_fairlight_io_table(
            cursor,
            table_name=table_name,
            id_column=id_column,
            columns=tuple(selected_columns[:16]),
            limit=limit,
        )
        kind = _fairlight_loudness_candidate_kind(table_name, matching_columns)
        candidates.append(
            {
                "table": table_name,
                "type": table_type,
                "kind": kind,
                "matching_columns": matching_columns,
                "available_columns": columns,
                "row_count": int(table_payload["count"]),
                "total_row_count": int(table_payload["total_count"]),
                "truncated": bool(table_payload.get("truncated")),
                "selected_columns": table_payload["columns"],
                "rows": table_payload["rows"],
            }
        )
    strong_candidates = [
        candidate
        for candidate in candidates
        if candidate["kind"] != "meter_setup_signal"
    ]
    meter_setup_signals = [
        candidate
        for candidate in candidates
        if candidate["kind"] == "meter_setup_signal"
    ]
    loudness_rows_found = any(
        candidate["total_row_count"] > 0 for candidate in strong_candidates
    )
    return {
        "action": "fairlight.loudness.info",
        "active_timeline_name": active_timeline_name,
        "route": "db_workaround",
        "read_scope": "loudness_schema_probe_and_meter_setup_signals",
        "read_consistency": "disk_project_db",
        "project_db_path": project_db_path,
        "limit": int(limit),
        "found": bool(candidates),
        "candidate_count": len(candidates),
        "loudness_schema_found": bool(strong_candidates),
        "loudness_rows_found": loudness_rows_found,
        "strong_candidates": strong_candidates,
        "meter_setup_signals": meter_setup_signals,
        "counts": {
            "strong_candidates": len(strong_candidates),
            "meter_setup_signals": len(meter_setup_signals),
        },
        "live_meter_values_supported": False,
        "offline_analysis_supported": False,
        "normalization_supported": False,
        "export_supported": False,
        "set_supported": False,
        "set_blocker": (
            "This DB route probes project storage for loudness/LUFS/true-peak schema and meter setup signals only. "
            "Live loudness values, offline loudness analysis, graph export, reset, and normalization remain unmapped."
        ),
        "note": (
            "Audio meter dBU/alignment columns are setup signals, not proof of Fairlight loudness analysis results."
        ),
    }


def read_fairlight_loudness_info_db(conn, *, limit: int = 20) -> dict[str, Any]:
    if limit < 1:
        raise ValidationError(
            "--limit must be 1 or greater.",
            details={"limit": limit, "min": 1},
            recoverability="not_applicable",
        )
    current_database = db_session.resolve_current_disk_project_db(
        conn,
        allow_project_name_inference=True,
    )
    project_db_path = str(current_database["project_db_path"])
    connection = sqlite3.connect(
        f"file:{project_db_path}?mode=ro", uri=True, timeout=5.0
    )
    connection.row_factory = sqlite3.Row
    try:
        return _read_fairlight_loudness_info_from_cursor(
            connection.cursor(),
            project_db_path=project_db_path,
            active_timeline_name=_timeline_name(conn),
            limit=limit,
        )
    finally:
        connection.close()


_FAIRLIGHT_ELASTIC_INFO_TABLES: tuple[dict[str, Any], ...] = (
    {
        "table": "SM_Clip",
        "result_key": "clip_speed_refs",
        "id_column": "SM_Clip_id",
        "columns": (
            "SM_Clip_id",
            "Name",
            "ClipName",
            "SpeedProfile",
            "IsNormalSpeed",
            "FrameRate",
            "StartFrame",
            "EndFrame",
            "FieldsBlob",
        ),
    },
    {
        "table": "SmSpeedProfile",
        "result_key": "speed_profiles",
        "id_column": "SmSpeedProfile_id",
        "columns": (
            "SmSpeedProfile_id",
            "SpeedPercent",
            "SpeedValue",
            "IsVariableSpeed",
            "SpeedCurveParameterBody",
            "FieldsBlob",
        ),
    },
    {
        "table": "SM_Setup",
        "result_key": "retime_setup",
        "id_column": "SM_Setup_id",
        "columns": (
            "SM_Setup_id",
            "ProfileStartPoint",
            "ProfileStopPoint",
            "RetimeProcess",
            "FieldsBlob",
        ),
    },
)

_FAIRLIGHT_ELASTIC_RETIME_NAME = b"FL::Retimer"
_FAIRLIGHT_ELASTIC_RETIME_TAIL = b"\x78\x04"
_FAIRLIGHT_ELASTIC_RETIME_VOICE_PAYLOAD = bytes.fromhex(
    "6688667701000000300000000200000028000000010000000100000000000000"
    "00000000000000000000000000000000000000000000000000000000"
)
_FAIRLIGHT_ELASTIC_RETIME_VOICE_COMPLEX_PAYLOAD = bytes.fromhex(
    "6688667701000000300000000200000028000000010000000100000000000000"
    "0000000000000000000000000080780F598000000088F027D07F0000"
)
_FAIRLIGHT_ELASTIC_RETIME_GENERAL_PURPOSE_PAYLOAD = bytes.fromhex(
    "6688667701000000300000000200000028000000010000000000000000000000"
    "0000000000000000000000000080780F598000000088F027D07F0000"
)
_FAIRLIGHT_ELASTIC_RETIME_VARISPEED_PAYLOAD = bytes.fromhex(
    "6688667701000000300000000200000028000000010000000400000000000000"
    "00000000000000000000000000000000000000000000000000000000"
)
_FAIRLIGHT_ELASTIC_RETIME_VOICE_ENTRY = bytes.fromhex(
    "0A340A30122E0A0B464C3A3A526574696D6572121F0000003C"
    "789C4BEB482B676460603000622620D6006246282604007A9B02292001"
)
_FAIRLIGHT_ELASTIC_RETIME_GENERAL_PURPOSE_ENTRY = bytes.fromhex(
    "8128B52FFD20463102000A420A3E123C0A0B464C3A3A526574696D6572122D0000003C"
    "789C4BEB482B676460603000622620D60062101F2B68A8E08F6C00D21D1FD42FD433300000A1CE06F62001"
)
_FAIRLIGHT_ELASTIC_RETIME_VARISPEED_ENTRY = bytes.fromhex(
    "0A360A3212300A0B464C3A3A526574696D657212210000003C"
    "789C4BEB482B676460603000622620D60062109F85813000007B07022C2001"
)
_FAIRLIGHT_ELASTIC_ALGORITHMS = {
    "general_purpose": "General Purpose",
    "varispeed": "Varispeed",
    "voice": "Voice",
}
_FAIRLIGHT_ELASTIC_RETIME_ENTRIES = {
    "general_purpose": _FAIRLIGHT_ELASTIC_RETIME_GENERAL_PURPOSE_ENTRY,
    "varispeed": _FAIRLIGHT_ELASTIC_RETIME_VARISPEED_ENTRY,
    "voice": _FAIRLIGHT_ELASTIC_RETIME_VOICE_ENTRY,
}
_FAIRLIGHT_ELASTIC_RETIME_PAYLOAD_ALGORITHMS = {
    _FAIRLIGHT_ELASTIC_RETIME_GENERAL_PURPOSE_PAYLOAD: "general_purpose",
    _FAIRLIGHT_ELASTIC_RETIME_VARISPEED_PAYLOAD: "varispeed",
    _FAIRLIGHT_ELASTIC_RETIME_VOICE_COMPLEX_PAYLOAD: "voice",
    _FAIRLIGHT_ELASTIC_RETIME_VOICE_PAYLOAD: "voice",
}


def _encode_fairlight_elastic_retime_entry(*, algorithm: str = "voice") -> bytes:
    normalized = (
        str(algorithm or "voice").strip().casefold().replace("-", "_").replace(" ", "_")
    )
    if normalized not in _FAIRLIGHT_ELASTIC_ALGORITHMS:
        raise ValidationError(
            "Unsupported Elastic Wave algorithm.",
            details={
                "algorithm": algorithm,
                "supported_algorithms": sorted(_FAIRLIGHT_ELASTIC_ALGORITHMS),
                "unsupported_reason": "Supported algorithms must be live-mapped DaVinci Resolve FL::Retimer payloads.",
            },
            recoverability="not_applicable",
        )
    return _FAIRLIGHT_ELASTIC_RETIME_ENTRIES[normalized]


def _wrap_fairlight_elastic_retime_proto(proto: bytes) -> bytes:
    body = b"\x80" + bytes(proto) + _FAIRLIGHT_ELASTIC_RETIME_TAIL
    return struct.pack(">II", 2, len(body)) + body


def _build_fairlight_elastic_retime_fieldsblob(*, algorithm: str = "voice") -> bytes:
    return _wrap_fairlight_elastic_retime_proto(
        _encode_fairlight_elastic_retime_entry(algorithm=algorithm)
    )


def _standalone_fairlight_elastic_retime_algorithm(raw: bytes) -> str | None:
    for supported_algorithm in _FAIRLIGHT_ELASTIC_ALGORITHMS:
        if raw == _build_fairlight_elastic_retime_fieldsblob(
            algorithm=supported_algorithm
        ):
            return supported_algorithm
    return None


def _decode_fairlight_elastic_retime_payload(blob: Any) -> dict[str, Any] | None:
    raw = bytes(blob or b"")
    marker_idx = raw.find(_FAIRLIGHT_ELASTIC_RETIME_NAME)
    if marker_idx < 0:
        return None
    zlib_idx = raw.find(b"\x78\x9c", marker_idx)
    if zlib_idx < 0:
        zlib_idx = raw.find(b"\x78\x9c", marker_idx)
    if zlib_idx < 0:
        return {
            "enabled": True,
            "payload": "FL::Retimer",
            "payload_decodable": False,
            "algorithm": "unknown",
            "db_blob": "Sm2TiItem.FieldsBlob",
        }
    try:
        decomp_obj = zlib.decompressobj()
        payload = decomp_obj.decompress(raw[zlib_idx:])
    except Exception:
        return {
            "enabled": True,
            "payload": "FL::Retimer",
            "payload_decodable": False,
            "algorithm": "unknown",
            "db_blob": "Sm2TiItem.FieldsBlob",
        }
    algorithm = _FAIRLIGHT_ELASTIC_RETIME_PAYLOAD_ALGORITHMS.get(payload, "unknown")
    return {
        "enabled": True,
        "payload": "FL::Retimer",
        "payload_decodable": True,
        "algorithm": algorithm,
        "algorithm_label": _FAIRLIGHT_ELASTIC_ALGORITHMS.get(algorithm),
        "payload_length": len(payload),
        "compressed_zlib_offset": zlib_idx,
        "payload_hex": payload.hex().upper(),
        "db_blob": "Sm2TiItem.FieldsBlob",
    }


def _set_fairlight_elastic_retime_fieldsblob(
    blob: Any,
    *,
    enabled: bool,
    algorithm: str = "voice",
) -> tuple[bytes | None, bool, dict[str, Any] | None, dict[str, Any] | None]:
    raw = bytes(blob or b"")
    previous = _decode_fairlight_elastic_retime_payload(raw)
    if enabled:
        new_entry = _encode_fairlight_elastic_retime_entry(algorithm=algorithm)
        new_blob = _wrap_fairlight_elastic_retime_proto(new_entry)
        if not raw:
            return (
                new_blob,
                True,
                previous,
                _decode_fairlight_elastic_retime_payload(new_blob),
            )
        if raw == new_blob:
            return raw, False, previous, previous
        if _standalone_fairlight_elastic_retime_algorithm(raw) is not None:
            return (
                new_blob,
                True,
                previous,
                _decode_fairlight_elastic_retime_payload(new_blob),
            )
        if _FAIRLIGHT_ELASTIC_RETIME_NAME in raw:
            raise CapabilityNegotiationFailed(
                "Cannot safely change Elastic Wave on a clip FieldsBlob that contains additional or unmapped payload data.",
                details={
                    "capability_id": "fairlight.elastic_wave_enable",
                    "existing_state": previous,
                    "existing_fieldsblob_length": len(raw),
                    "supported_write_scope": "standalone FL::Retimer Voice, General Purpose, and Varispeed payloads only",
                    "unsupported_reason": "The command must preserve other clip field payloads and will not overwrite unknown data.",
                },
                recoverability="manual",
            )
        if (
            len(raw) >= 11
            and raw[8] == 0x80
            and raw.endswith(_FAIRLIGHT_ELASTIC_RETIME_TAIL)
        ):
            proto = raw[9:-2]
            new_blob = _wrap_fairlight_elastic_retime_proto(proto + new_entry)
            return (
                new_blob,
                True,
                previous,
                _decode_fairlight_elastic_retime_payload(new_blob),
            )
        raise CapabilityNegotiationFailed(
            "Cannot safely add Elastic Wave to an existing unsupported clip FieldsBlob encoding.",
            details={
                "capability_id": "fairlight.elastic_wave_enable",
                "existing_fieldsblob_length": len(raw),
                "supported_existing_encodings": [
                    "empty",
                    "direct_qt_proto_0x80_without_FL::Retimer",
                ],
                "unsupported_reason": "The command must preserve other clip field payloads and will not overwrite unknown data.",
            },
            recoverability="manual",
        )

    if previous is None:
        return raw if raw else None, False, previous, None
    if _standalone_fairlight_elastic_retime_algorithm(raw) is not None:
        return None, True, previous, None
    raise CapabilityNegotiationFailed(
        "Cannot safely remove Elastic Wave from a clip FieldsBlob that contains additional or unmapped payload data.",
        details={
            "capability_id": "fairlight.elastic_wave_enable",
            "existing_state": previous,
            "existing_fieldsblob_length": len(raw),
            "supported_disable_scope": "standalone FL::Retimer Voice payload",
        },
        recoverability="manual",
    )


def _fairlight_elastic_clip_rows(
    cursor: sqlite3.Cursor, *, timeline_name: str | None
) -> list[dict[str, Any]]:
    if not timeline_name:
        rows = cursor.execute(
            """
            SELECT
                rowid AS db_rowid,
                Sm2TiItem_id,
                Name,
                Sm2TiTrack_id,
                Start,
                Duration,
                MediaTimemapBA,
                NULL AS track_index,
                FieldsBlob
            FROM Sm2TiItem
            WHERE DbType = 'Sm2TiAudioClip'
            ORDER BY rowid
            """
        ).fetchall()
        return [_fairlight_slot_probe_row_to_dict(cursor, row) for row in rows]
    rows = _fetch_fairlight_audio_clip_rows_for_slot_probe(
        cursor, timeline_name=timeline_name
    )
    if not rows:
        return []
    ids = [str(row.get("Sm2TiItem_id")) for row in rows if row.get("Sm2TiItem_id")]
    if not ids:
        return rows
    placeholders = ",".join("?" for _ in ids)
    item_columns = db_timeline_rows.table_columns(cursor, "Sm2TiItem")
    media_timemap_select = (
        ", MediaTimemapBA" if "MediaTimemapBA" in item_columns else ""
    )
    blob_rows = cursor.execute(
        f"SELECT Sm2TiItem_id, FieldsBlob{media_timemap_select} FROM Sm2TiItem WHERE Sm2TiItem_id IN ({placeholders})",
        ids,
    ).fetchall()
    fields_by_id = {str(row["Sm2TiItem_id"]): row["FieldsBlob"] for row in blob_rows}
    timemap_by_id = (
        {str(row["Sm2TiItem_id"]): row["MediaTimemapBA"] for row in blob_rows}
        if "MediaTimemapBA" in item_columns
        else {}
    )
    return [
        {
            **row,
            "FieldsBlob": fields_by_id.get(str(row.get("Sm2TiItem_id"))),
            "MediaTimemapBA": timemap_by_id.get(str(row.get("Sm2TiItem_id"))),
        }
        for row in rows
    ]


def _resolve_fairlight_elastic_clip_row(
    cursor: sqlite3.Cursor,
    *,
    timeline_name: str | None,
    clip: str | None,
) -> dict[str, Any]:
    if not clip or not str(clip).strip():
        raise ValidationError(
            "--clip is required for Fairlight Elastic Wave enable/disable.",
            details={"clip": clip},
        )
    needle = str(clip).strip()
    rows = _fairlight_elastic_clip_rows(cursor, timeline_name=timeline_name)
    id_matches = [row for row in rows if str(row.get("Sm2TiItem_id") or "") == needle]
    if id_matches:
        return id_matches[0]
    exact = [row for row in rows if str(row.get("Name") or "") == needle]
    matches = exact or [
        row
        for row in rows
        if needle.casefold() in str(row.get("Name") or "").casefold()
    ]
    if not matches:
        raise ReadinessFailed(
            "No matching Fairlight audio clip was found for Elastic Wave.",
            details={
                "clip": clip,
                "timeline_name": timeline_name,
                "audio_clip_count": len(rows),
                "available_clips": [
                    {
                        "clip_id": row.get("Sm2TiItem_id"),
                        "name": row.get("Name"),
                        "track_index": row.get("track_index"),
                        "start": row.get("Start"),
                        "duration": row.get("Duration"),
                    }
                    for row in rows[:20]
                ],
            },
            recoverability="manual",
        )
    if len(matches) > 1 and not any(
        str(row.get("Sm2TiItem_id") or "") == needle for row in matches
    ):
        raise ReadinessFailed(
            "Multiple Fairlight audio clips match --clip; use a unique Sm2TiItem_id.",
            details={
                "clip": clip,
                "timeline_name": timeline_name,
                "match_count": len(matches),
                "matches": [
                    {
                        "clip_id": row.get("Sm2TiItem_id"),
                        "name": row.get("Name"),
                        "track_index": row.get("track_index"),
                        "start": row.get("Start"),
                        "duration": row.get("Duration"),
                    }
                    for row in matches[:20]
                ],
            },
            recoverability="manual",
        )
    return matches[0]


def _read_fairlight_elastic_info_from_cursor(
    cursor: sqlite3.Cursor,
    *,
    project_db_path: str | None,
    active_timeline_name: str | None,
    limit: int,
) -> dict[str, Any]:
    tables: dict[str, Any] = {}
    counts: dict[str, int] = {}
    total_counts: dict[str, int] = {}
    for spec in _FAIRLIGHT_ELASTIC_INFO_TABLES:
        table_payload = _read_fairlight_io_table(
            cursor,
            table_name=str(spec["table"]),
            id_column=str(spec["id_column"]),
            columns=tuple(spec["columns"]),
            limit=int(limit),
        )
        result_key = str(spec["result_key"])
        tables[result_key] = table_payload
        counts[result_key] = int(table_payload["count"])
        total_counts[result_key] = int(table_payload["total_count"])
    elastic_clip_rows: list[dict[str, Any]] = []
    try:
        for row in _fairlight_elastic_clip_rows(
            cursor, timeline_name=active_timeline_name
        ):
            state = _decode_fairlight_elastic_retime_payload(row.get("FieldsBlob"))
            timemap = retime_db.decode_timemap_blob(row.get("MediaTimemapBA"))
            timemap_stretched = not bool(timemap.get("is_default_simple"))
            if state is None and not timemap_stretched:
                continue
            elastic_clip_rows.append(
                {
                    "clip_id": row.get("Sm2TiItem_id"),
                    "name": row.get("Name"),
                    "track_id": row.get("Sm2TiTrack_id"),
                    "track_index": row.get("track_index"),
                    "start": row.get("Start"),
                    "duration": row.get("Duration"),
                    "state": {
                        key: value
                        for key, value in state.items()
                        if key != "payload_hex"
                    }
                    if state
                    else None,
                    "retime": {
                        "db_blob": "Sm2TiItem.MediaTimemapBA",
                        "media_timemap_ba": timemap,
                        "stretched": timemap_stretched,
                    },
                }
            )
    except sqlite3.Error:
        elastic_clip_rows = []
    counts["elastic_audio_clips"] = min(len(elastic_clip_rows), int(limit))
    total_counts["elastic_audio_clips"] = len(elastic_clip_rows)
    return {
        "action": "fairlight.elastic.info",
        "active_timeline_name": active_timeline_name,
        "route": "db_workaround",
        "db_tables": [str(spec["table"]) for spec in _FAIRLIGHT_ELASTIC_INFO_TABLES]
        + ["Sm2TiItem"],
        "read_scope": "speed_profile_retime_candidates_clip_level_fl_retimer_and_media_timemap",
        "read_consistency": "disk_project_db",
        "project_db_path": project_db_path,
        "limit": int(limit),
        "found": any(count > 0 for count in total_counts.values()),
        "count": sum(counts.values()),
        "total_count": sum(total_counts.values()),
        "counts": counts,
        "total_counts": total_counts,
        **tables,
        "elastic_audio_clips": {
            "count": min(len(elastic_clip_rows), int(limit)),
            "total_count": len(elastic_clip_rows),
            "rows": elastic_clip_rows[: int(limit)],
            "source": "Sm2TiItem.FieldsBlob.FL::Retimer + Sm2TiItem.MediaTimemapBA",
        },
        "elastic_wave_state_supported": True,
        "elastic_keyframe_read_supported": True,
        "elastic_timemap_point_read_supported": True,
        "elastic_enable_supported": True,
        "elastic_keyframe_write_supported": True,
        "explicit_segment_timemap_supported": True,
        "explicit_timemap_handle_read_supported": True,
        "explicit_timemap_handle_write_supported": True,
        "supported_algorithms": sorted(_FAIRLIGHT_ELASTIC_ALGORITHMS),
        "set_supported": True,
        "set_blocker": (
            "This DB route now verifies clip-level FL::Retimer enable state for the live-mapped Voice, General Purpose, "
            "and Varispeed algorithms. "
            "Whole-clip and explicit segment audio stretch readback also report non-default Sm2TiItem.MediaTimemapBA state. "
            "Explicit raw timemap handle/interp values are verified, and a DaVinci Resolve GUI Cmd-click timing point uses "
            "the same MediaTimemapBA/RetimeKeyframeListProto model."
        ),
    }


def read_fairlight_elastic_info_db(conn, *, limit: int = 20) -> dict[str, Any]:
    if limit < 1:
        raise ValidationError(
            "--limit must be 1 or greater.",
            details={"limit": limit, "min": 1},
            recoverability="not_applicable",
        )
    current_database = db_session.resolve_current_disk_project_db(
        conn,
        allow_project_name_inference=True,
    )
    project_db_path = str(current_database["project_db_path"])
    connection = sqlite3.connect(
        f"file:{project_db_path}?mode=ro", uri=True, timeout=5.0
    )
    connection.row_factory = sqlite3.Row
    try:
        return _read_fairlight_elastic_info_from_cursor(
            connection.cursor(),
            project_db_path=project_db_path,
            active_timeline_name=_timeline_name(conn),
            limit=limit,
        )
    finally:
        connection.close()


def _fairlight_elastic_set_writer(
    *,
    timeline_name: str | None,
    clip: str,
    enabled: bool,
    algorithm: str,
):
    def _writer(
        _connection: sqlite3.Connection,
        cursor: sqlite3.Cursor,
        _session: db_session.DiskDbMutationSession,
    ) -> dict[str, Any]:
        row = _resolve_fairlight_elastic_clip_row(
            cursor, timeline_name=timeline_name, clip=clip
        )
        new_blob, changed, previous, new_state = (
            _set_fairlight_elastic_retime_fieldsblob(
                row.get("FieldsBlob"),
                enabled=enabled,
                algorithm=algorithm,
            )
        )
        cursor.execute(
            "UPDATE Sm2TiItem SET FieldsBlob = ? WHERE Sm2TiItem_id = ?",
            (
                sqlite3.Binary(new_blob) if new_blob is not None else None,
                row["Sm2TiItem_id"],
            ),
        )
        return {
            "action": "fairlight.elastic.enable",
            "changed": bool(changed),
            "route": "db_workaround",
            "db_table": "Sm2TiItem",
            "db_field": "FieldsBlob",
            "db_payload": "FL::Retimer",
            "read_scope": "clip_level_fl_retimer",
            "timeline_name": timeline_name,
            "target": {
                "kind": "audio_clip",
                "clip_id": row.get("Sm2TiItem_id"),
                "name": row.get("Name"),
                "track_id": row.get("Sm2TiTrack_id"),
                "track_index": row.get("track_index"),
                "start": row.get("Start"),
                "duration": row.get("Duration"),
            },
            "requested": {
                "clip": clip,
                "enable": bool(enabled),
                "algorithm": str(algorithm),
            },
            "previous_state": previous or {"enabled": False, "payload": "FL::Retimer"},
            "state": new_state or {"enabled": False, "payload": "FL::Retimer"},
            "elastic_wave_state_supported": True,
            "elastic_enable_supported": True,
            "elastic_keyframe_read_supported": True,
            "elastic_keyframe_write_supported": True,
            "explicit_segment_timemap_supported": True,
            "explicit_timemap_handle_read_supported": True,
            "explicit_timemap_handle_write_supported": True,
            "set_supported": True,
            "set_scope": "clip_level_fl_retimer_algorithm_enable",
            "residual_blockers": ["pitch-preservation storage flag readback"],
        }

    return _writer


def _verify_fairlight_elastic_set(
    *, clip_id: str | None, expected_enabled: bool, algorithm: str
):
    def _verifier(
        _conn,
        mutation_result: dict[str, Any],
        session: db_session.DiskDbMutationSession,
    ) -> dict[str, Any]:
        target_id = clip_id or mutation_result.get("target", {}).get("clip_id")
        connection = sqlite3.connect(session.project_db_path, timeout=2.0)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                "SELECT Sm2TiItem_id, Name, FieldsBlob FROM Sm2TiItem WHERE Sm2TiItem_id = ?",
                (target_id,),
            ).fetchone()
        finally:
            connection.close()
        state = _decode_fairlight_elastic_retime_payload(
            row["FieldsBlob"] if row is not None else None
        )
        actual_enabled = state is not None
        algorithm_ok = (not expected_enabled) or (state or {}).get(
            "algorithm"
        ) == algorithm
        ok = bool(
            row is not None and actual_enabled == expected_enabled and algorithm_ok
        )
        verification = {
            "status": "verified" if ok else "failed",
            "target_clip_id": target_id,
            "expected_enabled": bool(expected_enabled),
            "actual_enabled": actual_enabled,
            "expected_algorithm": algorithm if expected_enabled else None,
            "actual_state": state,
            "read_scope": "Sm2TiItem.FieldsBlob.FL::Retimer",
            "project_db_path": session.project_db_path,
        }
        if not ok:
            raise APICallFailed(
                "Fairlight Elastic Wave DB verification failed after project reopen.",
                details={
                    "verification": verification,
                    "mutation_result": mutation_result,
                },
                recoverability="manual",
            )
        return verification

    return _verifier


def set_fairlight_elastic_wave_db(
    conn,
    *,
    clip: str,
    enabled: bool,
    algorithm: str = "voice",
) -> dict[str, Any]:
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed(
            "No active timeline is available for Fairlight Elastic Wave enable/disable."
        )
    _encode_fairlight_elastic_retime_entry(algorithm=algorithm)
    target_clip_id: str | None = None

    def _writer_with_target(
        connection: sqlite3.Connection,
        cursor: sqlite3.Cursor,
        session: db_session.DiskDbMutationSession,
    ) -> dict[str, Any]:
        nonlocal target_clip_id
        result = _fairlight_elastic_set_writer(
            timeline_name=timeline_name,
            clip=clip,
            enabled=enabled,
            algorithm=algorithm,
        )(connection, cursor, session)
        target_clip_id = result.get("target", {}).get("clip_id")
        return result

    return db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Fairlight Elastic Wave clip-level FL::Retimer set",
        writer=_writer_with_target,
        verifier=lambda fresh_conn, mutation_result, session: (
            _verify_fairlight_elastic_set(
                clip_id=target_clip_id
                or mutation_result.get("target", {}).get("clip_id"),
                expected_enabled=enabled,
                algorithm=algorithm,
            )(fresh_conn, mutation_result, session)
        ),
        allow_project_name_inference=True,
    )


_FAIRLIGHT_EXTERNAL_PROCESS_CONFIG_PATH = Path(
    "~/Library/Preferences/Blackmagic Design/DaVinci Resolve/Fairlight/Effects/ExternalFXConfiguration.xml"
).expanduser()
_FAIRLIGHT_EFFECTS_CONFIG_DIR = Path(
    "~/Library/Preferences/Blackmagic Design/DaVinci Resolve/Fairlight/Effects"
).expanduser()
_FAIRLIGHT_BMD_AUDIO_PLUGINS_PATH = Path(
    "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/libBMDAudioPlugins.dylib"
)
_FAIRLIGHT_PLUGIN_CONFIG_SPECS: tuple[dict[str, str], ...] = (
    {"provider": "audio_unit", "file": "AUConfiguration.xml", "root": "Effects"},
    {"provider": "vst3", "file": "VST3Configuration.xml", "root": "Effects"},
    {"provider": "fairlight_fx", "file": "FXConfiguration.xml", "root": "Effects"},
)
_FAIRLIGHT_BMD_AUDIO_PLUGIN_DISPLAY_NAMES = {
    "BMDAmbisonicsMeter": "Ambisonics Meter",
    "BMDAudioPitchShift": "Pitch Shift",
    "BMDChainFX": "Chain FX",
    "BMDChorus": "Chorus",
    "BMDConvolutionReverb": "Convolution Reverb",
    "BMDDeesser": "De-Esser",
    "BMDDialogProcessor": "Dialogue Processor",
    "BMDDistortion": "Distortion",
    "BMDDucker": "Ducker",
    "BMDEq": "Fairlight EQ",
    "BMDFlanger": "Flanger",
    "BMDGain": "Gain",
    "BMDHumRemoval": "De-Hummer",
    "BMDKrush": "Krush",
    "BMDLFEFilter": "LFE Filter",
    "BMDLimiter": "Limiter",
    "BMDLoudnessMeter": "Loudness Meter",
    "BMDMultiBandCompressor": "Multi Band Compressor",
    "BMDNoiseReduction": "Noise Reduction",
    "BMDReverb": "Reverb",
    "BMDStereoDelay": "Stereo Delay",
    "BMDStereoEcho": "Stereo Echo",
    "BMDStereoFixer": "Stereo Fixer",
    "BMDStereoWidth": "Stereo Width",
    "BMDVoiceIsolationControl": "Voice Isolation",
}
_FAIRLIGHT_BMD_PLUGIN_CLASS_RE = re.compile(rb"\b(BMD[A-Za-z0-9]+)::([A-Z0-9_]+)\b")
_PRINTABLE_ASCII_RE = re.compile(rb"[ -~]{4,}")
_FAIRLIGHT_RELATED_RESOLVEFX_ROUTE_EVIDENCE: dict[str, Any] = {
    "color_page_resolvefx_route_available": True,
    "registry_command": "cutagent color page resolvefx-list --json",
    "write_commands": [
        "cutagent color page resolvefx-add CLIP --fx EFFECT --json",
        "cutagent color page resolvefx-remove CLIP --json",
    ],
    "registry_source": "resolve.Fusion().GetRegList(2)",
    "write_route": "db_workaround_color_page_resolvefx_add",
    "write_storage_scope": "Color Page primary grade container tool params",
    "ofx_context": "OfxImageEffectContextFilter",
    "fairlight_audio_slot_route": False,
    "fairlight_route_boundary": (
        "Color Page ResolveFX entries are image OFX filters stored in the grade body. "
        "They do not describe Fairlight track, bus, or audio clip plugin slot assignment."
    ),
}


def _external_process_config_path(config_path: str | None = None) -> Path:
    raw_path = str(config_path or "").strip()
    if raw_path:
        return Path(raw_path).expanduser()
    return _FAIRLIGHT_EXTERNAL_PROCESS_CONFIG_PATH


def _external_process_simple_fields(element: ET.Element) -> dict[str, str]:
    fields: dict[str, str] = {}
    for child in list(element):
        if list(child):
            continue
        text = str(child.text or "").strip()
        if text:
            fields[str(child.tag)] = text
    return fields


def _first_external_process_value(
    attributes: dict[str, str],
    fields: dict[str, str],
    candidates: tuple[str, ...],
) -> str | None:
    normalized_attributes = {key.casefold(): value for key, value in attributes.items()}
    normalized_fields = {key.casefold(): value for key, value in fields.items()}
    for candidate in candidates:
        key = candidate.casefold()
        value = normalized_attributes.get(key) or normalized_fields.get(key)
        if value:
            return value
    return None


def _external_process_payload_from_element(
    index: int, element: ET.Element
) -> dict[str, Any]:
    attributes = {str(key): str(value) for key, value in element.attrib.items()}
    fields = _external_process_simple_fields(element)
    name = _first_external_process_value(
        attributes, fields, ("name", "Name", "label", "Label", "title", "Title")
    )
    executable = _first_external_process_value(
        attributes,
        fields,
        (
            "path",
            "Path",
            "executable",
            "Executable",
            "application",
            "Application",
            "command",
            "Command",
        ),
    )
    arguments = _first_external_process_value(
        attributes, fields, ("args", "Args", "arguments", "Arguments")
    )
    return {
        "index": int(index),
        "tag": str(element.tag),
        "name": name,
        "executable": executable,
        "arguments": arguments,
        "attributes": attributes,
        "fields": fields,
    }


def read_fairlight_external_process_config(
    *,
    config_path: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    if limit < 1:
        raise ValidationError(
            "--limit must be 1 or greater.",
            details={"limit": limit, "min": 1},
            recoverability="not_applicable",
        )
    path = _external_process_config_path(config_path)
    if not path.exists():
        return {
            "action": "fairlight.external_process.list",
            "route": "workaround_setting",
            "config_path": str(path),
            "config_file_found": False,
            "root_tag": None,
            "read_scope": "external_process_configuration_xml",
            "count": 0,
            "total_count": 0,
            "truncated": False,
            "processes": [],
            "run_supported": False,
            "roundtrip_supported": False,
            "set_supported": False,
            "set_blocker": (
                "Fairlight external process configuration is stored outside the project database. "
                "This route can read configured process entries when the XML file exists, but it does "
                "not expose a verified native way to launch a process or round-trip processed audio."
            ),
        }
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise ValidationError(
            "Fairlight external process configuration XML could not be parsed.",
            details={"config_path": str(path), "error": str(exc)},
            recoverability="manual",
        ) from exc

    entries = [
        _external_process_payload_from_element(index, element)
        for index, element in enumerate(list(root), start=1)
    ]
    total_count = len(entries)
    processes = entries[: int(limit)]
    return {
        "action": "fairlight.external_process.list",
        "route": "workaround_setting",
        "config_path": str(path),
        "config_file_found": True,
        "root_tag": str(root.tag),
        "read_scope": "external_process_configuration_xml",
        "count": len(processes),
        "total_count": total_count,
        "truncated": total_count > len(processes),
        "processes": processes,
        "run_supported": False,
        "roundtrip_supported": False,
        "set_supported": False,
        "set_blocker": (
            "DaVinci Resolve stores external-process configuration in Fairlight/Effects/ExternalFXConfiguration.xml, "
            "but the scripting API still does not expose a verified launch or round-trip operation."
        ),
    }


def _fairlight_effects_config_dir(config_dir: str | None = None) -> Path:
    raw_path = str(config_dir or "").strip()
    if raw_path:
        return Path(raw_path).expanduser()
    return _FAIRLIGHT_EFFECTS_CONFIG_DIR


def _boolish_xml_value(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = str(value).strip().casefold()
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return None


def _effect_plugin_payload_from_element(
    index: int, element: ET.Element
) -> dict[str, Any]:
    fields = _external_process_simple_fields(element)
    attributes = {str(key): str(value) for key, value in element.attrib.items()}
    name = _first_external_process_value(
        attributes, fields, ("name", "Name", "label", "Label")
    )
    plugin_id = _first_external_process_value(
        attributes, fields, ("id", "ID", "plugin_id", "PluginID")
    )
    vendor = _first_external_process_value(
        attributes,
        fields,
        ("vendor", "Vendor", "manufacturer_name", "ManufacturerName"),
    )
    enabled = _boolish_xml_value(
        _first_external_process_value(attributes, fields, ("enabled", "Enabled"))
    )
    favourite = _boolish_xml_value(
        _first_external_process_value(
            attributes, fields, ("favourite", "favorite", "Favourite", "Favorite")
        )
    )
    return {
        "index": int(index),
        "tag": str(element.tag),
        "name": name,
        "plugin_id": plugin_id,
        "vendor": vendor,
        "enabled": enabled,
        "favourite": favourite,
        "manufacturer": _first_external_process_value(
            attributes, fields, ("manufacturer", "Manufacturer")
        ),
        "subtype": _first_external_process_value(
            attributes, fields, ("subtype", "SubType")
        ),
        "version": _first_external_process_value(
            attributes, fields, ("version", "Version")
        ),
        "category_mask": _first_external_process_value(
            attributes, fields, ("category_mask", "CategoryMask")
        ),
        "attributes": attributes,
        "fields": fields,
    }


def _read_fairlight_plugin_config_file(
    path: Path, *, provider: str, limit: int
) -> dict[str, Any]:
    if not path.exists():
        return {
            "provider": provider,
            "config_path": str(path),
            "config_file_found": False,
            "root_tag": None,
            "count": 0,
            "total_count": 0,
            "truncated": False,
            "effects": [],
        }
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise ValidationError(
            "Fairlight effect plugin configuration XML could not be parsed.",
            details={"config_path": str(path), "provider": provider, "error": str(exc)},
            recoverability="manual",
        ) from exc
    entries = [
        _effect_plugin_payload_from_element(index, element)
        for index, element in enumerate(
            [child for child in list(root) if str(child.tag) == "Effect"], start=1
        )
    ]
    total_count = len(entries)
    effects = entries[: int(limit)]
    return {
        "provider": provider,
        "config_path": str(path),
        "config_file_found": True,
        "root_tag": str(root.tag),
        "count": len(effects),
        "total_count": total_count,
        "truncated": total_count > len(effects),
        "effects": effects,
    }


def _humanize_bmd_plugin_class(class_name: str) -> str:
    mapped = _FAIRLIGHT_BMD_AUDIO_PLUGIN_DISPLAY_NAMES.get(class_name)
    if mapped:
        return mapped
    raw = class_name.removeprefix("BMD")
    return re.sub(r"(?<!^)(?=[A-Z])", " ", raw).strip() or class_name


def _read_fairlight_bmd_builtin_audio_plugins(
    *,
    library_path: str | None = None,
    limit: int,
) -> dict[str, Any]:
    path = (
        Path(str(library_path).strip()).expanduser()
        if library_path
        else _FAIRLIGHT_BMD_AUDIO_PLUGINS_PATH
    )
    if not path.exists():
        return {
            "provider": "bmd_builtin_audio_fx",
            "library_path": str(path),
            "library_found": False,
            "count": 0,
            "total_count": 0,
            "truncated": False,
            "effects": [],
            "read_scope": "libBMDAudioPlugins_symbol_catalog",
            "slot_assignment_state": False,
        }
    data = path.read_bytes()
    params_by_class: dict[str, set[str]] = {}
    for raw_value in _PRINTABLE_ASCII_RE.findall(data):
        value = raw_value.decode("ascii", errors="ignore")
        if value in _FAIRLIGHT_BMD_AUDIO_PLUGIN_DISPLAY_NAMES:
            params_by_class.setdefault(value, set())
    for match in _FAIRLIGHT_BMD_PLUGIN_CLASS_RE.finditer(data):
        class_name = match.group(1).decode("ascii", errors="ignore")
        param_name = match.group(2).decode("ascii", errors="ignore")
        if not class_name or not param_name:
            continue
        params_by_class.setdefault(class_name, set()).add(param_name)
    entries = [
        {
            "index": index,
            "class_name": class_name,
            "name": _humanize_bmd_plugin_class(class_name),
            "plugin_id": class_name,
            "vendor": "Blackmagic Design",
            "enabled": None,
            "favourite": None,
            "param_count": len(params),
            "param_tokens": sorted(params)[:50],
            "param_tokens_truncated": len(params) > 50,
            "slot_assignment_state": False,
        }
        for index, (class_name, params) in enumerate(
            sorted(params_by_class.items()), start=1
        )
    ]
    effects = entries[: int(limit)]
    return {
        "provider": "bmd_builtin_audio_fx",
        "library_path": str(path),
        "library_found": True,
        "count": len(effects),
        "total_count": len(entries),
        "truncated": len(entries) > len(effects),
        "effects": effects,
        "read_scope": "libBMDAudioPlugins_symbol_catalog",
        "slot_assignment_state": False,
    }


def _read_fairlight_plugin_scan_paths(config_dir: Path) -> dict[str, Any]:
    path = config_dir / "FXScan.xml"
    if not path.exists():
        return {
            "config_path": str(path),
            "config_file_found": False,
            "root_tag": None,
            "paths": [],
        }
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise ValidationError(
            "Fairlight effect scan-path XML could not be parsed.",
            details={"config_path": str(path), "error": str(exc)},
            recoverability="manual",
        ) from exc
    paths = [
        str(child.text or "").strip()
        for child in list(root)
        if str(child.tag) == "Path" and str(child.text or "").strip()
    ]
    return {
        "config_path": str(path),
        "config_file_found": True,
        "root_tag": str(root.tag),
        "paths": paths,
    }


def read_fairlight_effect_plugin_catalog_config(
    *,
    config_dir: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    if limit < 1:
        raise ValidationError(
            "--limit must be 1 or greater.",
            details={"limit": limit, "min": 1},
            recoverability="not_applicable",
        )
    root_dir = _fairlight_effects_config_dir(config_dir)
    provider_catalogs = [
        _read_fairlight_plugin_config_file(
            root_dir / spec["file"], provider=spec["provider"], limit=int(limit)
        )
        for spec in _FAIRLIGHT_PLUGIN_CONFIG_SPECS
    ]
    bmd_builtin_catalog = _read_fairlight_bmd_builtin_audio_plugins(limit=int(limit))
    provider_catalogs.append(bmd_builtin_catalog)
    counts = {
        catalog["provider"]: int(catalog["count"]) for catalog in provider_catalogs
    }
    total_counts = {
        catalog["provider"]: int(catalog["total_count"])
        for catalog in provider_catalogs
    }
    return {
        "action": "fairlight.effect.plugin_catalog",
        "route": "workaround_setting",
        "config_dir": str(root_dir),
        "read_scope": "fairlight_effect_plugin_configuration_xml_and_bmd_builtin_audio_symbols",
        "limit": int(limit),
        "count": sum(counts.values()),
        "total_count": sum(total_counts.values()),
        "counts": counts,
        "total_counts": total_counts,
        "truncated": any(bool(catalog["truncated"]) for catalog in provider_catalogs),
        "providers": provider_catalogs,
        "scan_paths": _read_fairlight_plugin_scan_paths(root_dir),
        "related_resolvefx_route": _FAIRLIGHT_RELATED_RESOLVEFX_ROUTE_EVIDENCE,
        "slot_readback_supported": False,
        "slot_insert_supported": False,
        "slot_remove_supported": False,
        "slot_bypass_supported": False,
        "param_routing_supported": False,
        "set_supported": False,
        "bmd_builtin_catalog_note": (
            "Built-in Blackmagic Design Fairlight FX names and parameter tokens are read from libBMDAudioPlugins.dylib. "
            "That library is an availability catalog only; it does not expose Project.db slot assignment state."
        ),
        "set_blocker": (
            "This route reads DaVinci Resolve's persisted Fairlight plugin availability catalog and built-in BMD audio symbols only. "
            "Track/bus/clip slot assignment, insertion/removal, bypass, and arbitrary parameter routing remain unmapped."
        ),
    }


_FAIRLIGHT_MONITOR_INFO_COLUMNS = (
    "SM_UserSetup_id",
    "ResolveVersion",
    "CurrentPage",
    "TargetMonitor",
    "EnableAudio",
    "MuteAudio",
    "MasterAudioDisable",
    "AudioMeterDBUEnable",
    "AudioMeterAlignmentLevel",
    "ApplyLutToWfm",
    "ApplyWfmDuringRecord",
    "DisableCcDuringRecording",
    "DisablePtzDuringRecording",
    "AudioFile",
    "LastRecordFrameNum",
    "RecordSpeed",
    "PanelBeepEnabled",
    "SM_Setup_id",
    "FieldsBlob",
)


def _read_fairlight_monitor_info_from_cursor(
    cursor: sqlite3.Cursor,
    *,
    project_db_path: str | None,
    active_timeline_name: str | None,
    limit: int,
) -> dict[str, Any]:
    user_setup = _read_fairlight_io_table(
        cursor,
        table_name="SM_UserSetup",
        id_column="SM_UserSetup_id",
        columns=_FAIRLIGHT_MONITOR_INFO_COLUMNS,
        limit=int(limit),
    )
    count = int(user_setup["count"])
    total_count = int(user_setup["total_count"])
    return {
        "action": "fairlight.monitor.info",
        "active_timeline_name": active_timeline_name,
        "route": "db_workaround",
        "db_tables": ["SM_UserSetup"],
        "read_scope": "stored_monitor_setup_only",
        "read_consistency": "disk_project_db",
        "project_db_path": project_db_path,
        "limit": int(limit),
        "found": total_count > 0,
        "count": count,
        "total_count": total_count,
        "counts": {"user_setup": count},
        "total_counts": {"user_setup": total_count},
        "user_setup": user_setup,
        "stored_fields": [
            "TargetMonitor",
            "EnableAudio",
            "MuteAudio",
            "MasterAudioDisable",
            "AudioMeterDBUEnable",
            "AudioMeterAlignmentLevel",
        ],
        "live_level_supported": False,
        "live_mute_supported": False,
        "dim_supported": False,
        "speaker_set_supported": False,
        "fold_down_supported": False,
        "set_supported": False,
        "set_blocker": (
            "DaVinci Resolve may persist monitor/audio setup fields in SM_UserSetup, but live Fairlight "
            "control-room level, mute/dim state, speaker-set selection, and fold-down controls remain "
            "unmapped and are not exposed by the scripting API."
        ),
    }


def read_fairlight_monitor_info_db(conn, *, limit: int = 20) -> dict[str, Any]:
    if limit < 1:
        raise ValidationError(
            "--limit must be 1 or greater.",
            details={"limit": limit, "min": 1},
            recoverability="not_applicable",
        )
    current_database = db_session.resolve_current_disk_project_db(
        conn,
        allow_project_name_inference=True,
    )
    project_db_path = str(current_database["project_db_path"])
    connection = sqlite3.connect(
        f"file:{project_db_path}?mode=ro", uri=True, timeout=5.0
    )
    connection.row_factory = sqlite3.Row
    try:
        return _read_fairlight_monitor_info_from_cursor(
            connection.cursor(),
            project_db_path=project_db_path,
            active_timeline_name=_timeline_name(conn),
            limit=limit,
        )
    finally:
        connection.close()


def _read_fairlight_waveform_view_state_from_cursor(
    cursor: sqlite3.Cursor,
    *,
    timeline_name: str,
    project_db_path: str | None,
) -> dict[str, Any]:
    sequence = _fetch_timeline_sequence(cursor, timeline_name)
    row = cursor.execute(
        "SELECT UIElementsState FROM Sm2Sequence WHERE Sm2Sequence_id = ?",
        (sequence,),
    ).fetchone()
    if row is None:
        raise ValidationError(
            "Timeline sequence was not found in the DaVinci Resolve Disk project database.",
            details={
                "timeline_name": timeline_name,
                "timeline_sequence": sequence,
                "table": "Sm2Sequence",
            },
            recoverability="manual",
        )
    ui_state = _decode_sequence_ui_elements_state(
        row["UIElementsState"] if isinstance(row, sqlite3.Row) else row[0]
    )
    entries = ui_state["entries"]
    tracked_keys = [
        _UI_SEQUENCE_AUDIO_CLIP_HEIGHT_KEY,
        _UI_SEQUENCE_USER_ADJUSTED_AUDIO_TRACK_HEIGHTS_KEY,
        "UI_SEQUENCE_AUDIO_MARK_IN",
        "UI_SEQUENCE_AUDIO_MARK_OUT",
        "UI_SEQUENCE_AUDIO_VIEW_Y_POS",
        "UI_SEQUENCE_AUDIO_WF_VIEW_OPTION",
    ]
    present = {key: entries[key] for key in tracked_keys if key in entries}
    missing = [key for key in tracked_keys if key not in entries]
    track_heights_value = present.get(
        _UI_SEQUENCE_USER_ADJUSTED_AUDIO_TRACK_HEIGHTS_KEY, {}
    ).get("value")
    track_heights = (
        list(track_heights_value.get("values") or [])
        if isinstance(track_heights_value, dict)
        else []
    )
    return {
        "action": "fairlight.waveform.info",
        "timeline_name": timeline_name,
        "timeline_sequence": sequence,
        "route": "db_workaround",
        "db_blob": "Sm2Sequence.UIElementsState",
        "read_scope": "audio_waveform_view_state_only",
        "read_consistency": "disk_project_db",
        "project_db_path": project_db_path,
        "ui_state_version": ui_state.get("version"),
        "ui_state_entry_count": ui_state.get("entry_count"),
        "keys_present": sorted(present),
        "missing_keys": missing,
        "audio_clip_height": present.get(_UI_SEQUENCE_AUDIO_CLIP_HEIGHT_KEY, {}).get(
            "value"
        ),
        "track_adjusted_heights": track_heights,
        "track_adjusted_height_count": len(track_heights),
        "audio_mark_in": present.get("UI_SEQUENCE_AUDIO_MARK_IN", {}).get("value"),
        "audio_mark_out": present.get("UI_SEQUENCE_AUDIO_MARK_OUT", {}).get("value"),
        "audio_view_y_pos": present.get("UI_SEQUENCE_AUDIO_VIEW_Y_POS", {}).get(
            "value"
        ),
        "waveform_view_option": {
            "raw": present.get("UI_SEQUENCE_AUDIO_WF_VIEW_OPTION", {}).get("value"),
            "semantics": "DaVinci Resolve UIElementsState value; read-only DB state, not a verified waveform redraw or sample edit route.",
        },
        "set_supported": False,
        "waveform_redraw_supported": False,
        "sample_repair_supported": False,
        "set_blocker": (
            "DaVinci Resolve stores audio waveform view state in UIElementsState, but waveform redraw, sample repair, "
            "and click/pop repair controls remain unmapped and are not exposed by the scripting API."
        ),
    }


def read_fairlight_waveform_info_db(conn) -> dict[str, Any]:
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise APICallFailed(
            "No active timeline is available for Fairlight waveform view-state read."
        )
    current_database = db_session.resolve_current_disk_project_db(
        conn,
        allow_project_name_inference=True,
    )
    project_db_path = str(current_database["project_db_path"])
    connection = sqlite3.connect(
        f"file:{project_db_path}?mode=ro", uri=True, timeout=5.0
    )
    connection.row_factory = sqlite3.Row
    try:
        return _read_fairlight_waveform_view_state_from_cursor(
            connection.cursor(),
            timeline_name=timeline_name,
            project_db_path=project_db_path,
        )
    finally:
        connection.close()


def _read_audio_track_subtype(conn, index: int) -> str | None:
    getter = getattr(conn.timeline, "GetTrackSubType", None) or getattr(
        conn.timeline, "GetTrackSubtype", None
    )
    if not callable(getter):
        return None
    try:
        subtype = getter("audio", int(index))
    except Exception:
        return None
    normalized = str(subtype or "").strip()
    return normalized or None


def add_audio_track(conn, track_type: str = "mono", index: int | None = None) -> bool:
    """
    Add an audio track.

    Args:
        conn: ResolveConnection instance
        track_type: Audio track format supported by Timeline.AddTrack.
        index: Optional 1-based insertion index for the modern AddTrack options form.

    Returns:
        True if successful

    Raises:
        APICallFailed: If addition fails
    """
    normalized_type = str(track_type).strip().lower()
    options: dict[str, Any] | None = None
    if index is not None:
        options = {"audioType": normalized_type, "index": int(index)}
        try:
            result = conn.timeline.AddTrack("audio", options)
        except TypeError as exc:
            raise CapabilityNegotiationFailed(
                "This DaVinci Resolve scripting API does not support audio track insertion options.",
                details={
                    "track_type": normalized_type,
                    "index": int(index),
                    "required_native_api": 'Timeline.AddTrack("audio", {"audioType": track_type, "index": index})',
                },
            ) from exc
        if result:
            return True
        raise APICallFailed(
            "Failed to add audio track.",
            details={
                "track_type": normalized_type,
                "index": int(index),
                "api_result": result,
            },
        )

    try:
        result = conn.timeline.AddTrack("audio", normalized_type)
    except TypeError:
        result = False
    if result:
        return True

    # Calling AddTrack("audio") creates a mono track, so only use it when it
    # preserves the requested format on older scripting runtimes.
    if normalized_type == "mono":
        result = conn.timeline.AddTrack("audio")
        if result:
            return True
    raise APICallFailed(
        "Failed to add audio track.",
        details={"track_type": normalized_type, "index": None, "api_result": result},
    )


def _timeline_name(conn) -> str | None:
    timeline = getattr(conn, "timeline", None)
    if timeline is None or not hasattr(timeline, "GetName"):
        return None
    try:
        name = timeline.GetName()
    except Exception:
        return None
    return str(name) if name else None


def _timeline_start_frame(conn) -> int:
    try:
        value = int(getattr(conn, "start_frame", 0) or 0)
    except Exception:
        value = 0
    timeline = getattr(conn, "timeline", None)
    if value == 0 and timeline is not None and hasattr(timeline, "GetStartFrame"):
        try:
            value = int(timeline.GetStartFrame())
        except Exception:
            value = 0
    return value


def _row_to_dict(
    cursor: sqlite3.Cursor, row: sqlite3.Row | tuple[Any, ...]
) -> dict[str, Any]:
    if isinstance(row, sqlite3.Row):
        return {key: row[key] for key in row.keys()}
    return {cursor.description[index][0]: value for index, value in enumerate(row)}


def _int_cell(value: Any, *, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        if "|" in value:
            value = value.split("|", 1)[0]
        value = value.strip()
        if re.fullmatch(r"[+-]?\d+\.0+", value):
            value = value.split(".", 1)[0]
    try:
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return default


def _parse_record_ref(conn, value: Any, *, field_name: str) -> int:
    try:
        return parse_record_frame(
            str(value),
            float(getattr(conn, "fps", 24.0) or 24.0),
            _timeline_start_frame(conn),
        )
    except Exception as exc:
        details = getattr(exc, "details", {"field": field_name, "value": value})
        raise ValidationError(
            f"Cannot parse record-domain {field_name}: {value}",
            details=details,
            recoverability="not_applicable",
        ) from exc


def _parse_duration_ref(conn, value: Any, *, field_name: str) -> int:
    try:
        frames = parse_source_frame(
            str(value), float(getattr(conn, "fps", 24.0) or 24.0)
        )
    except Exception as exc:
        details = getattr(exc, "details", {"field": field_name, "value": value})
        raise ValidationError(
            f"Cannot parse duration {field_name}: {value}",
            details=details,
            recoverability="not_applicable",
        ) from exc
    if frames <= 0:
        raise ValidationError(
            "Record duration must be greater than 0 frames.",
            details={"field": field_name, "value": value, "resolved_frames": frames},
            recoverability="not_applicable",
        )
    return int(frames)


def normalize_audio_gain_batch_selectors(
    conn,
    selectors: list[dict[str, Any]],
    *,
    operation_label: str = "audio-gain",
) -> list[AudioGainBatchSelector]:
    """Normalize raw batch selector dictionaries into record-frame selectors."""
    if not selectors:
        raise ValidationError(
            f"At least one {operation_label} batch selector is required.",
            details={
                "accepted": [
                    {"item_id": "Sm2TiItem_id"},
                    {"track_index": 1, "record_frame": "0f", "record_duration": "120f"},
                    {"track_index": 1, "start_frame": "0f", "end_frame": "120f"},
                ],
            },
            recoverability="not_applicable",
        )

    normalized: list[AudioGainBatchSelector] = []
    for index, raw_selector in enumerate(selectors):
        if not isinstance(raw_selector, dict):
            raise ValidationError(
                f"Each {operation_label} batch selector must be a JSON object.",
                details={"index": index, "selector": raw_selector},
                recoverability="not_applicable",
            )
        raw = dict(raw_selector)
        item_id = str(raw.get("item_id") or "").strip()
        has_item = bool(item_id)
        has_track = raw.get("track_index") is not None
        has_bounds = (
            raw.get("start_frame") is not None or raw.get("end_frame") is not None
        )
        has_point = raw.get("record_frame") is not None

        if has_item and (
            has_track
            or has_bounds
            or has_point
            or raw.get("record_duration") is not None
            or raw.get("record_end") is not None
        ):
            raise ValidationError(
                "Use item_id by itself, or use one track/time selector.",
                details={"index": index, "selector": raw},
                recoverability="not_applicable",
            )
        if has_item:
            normalized.append(
                AudioGainBatchSelector(kind="item_id", item_id=item_id, raw=raw)
            )
            continue

        if not has_track:
            raise ValidationError(
                f"Track/time {operation_label} selectors require track_index.",
                details={"index": index, "selector": raw},
                recoverability="not_applicable",
            )
        try:
            track_index = int(raw.get("track_index"))
        except Exception as exc:
            raise ValidationError(
                "track_index must be an integer.",
                details={"index": index, "track_index": raw.get("track_index")},
                recoverability="not_applicable",
            ) from exc
        if track_index < 1:
            raise ValidationError(
                "track_index must be 1 or greater.",
                details={"index": index, "track_index": track_index},
                recoverability="not_applicable",
            )

        if has_bounds and has_point:
            raise ValidationError(
                "Use either start_frame/end_frame bounds or record_frame, not both.",
                details={"index": index, "selector": raw},
                recoverability="not_applicable",
            )
        if has_bounds:
            if raw.get("start_frame") is None or raw.get("end_frame") is None:
                raise ValidationError(
                    "Bounds selectors require both start_frame and end_frame.",
                    details={"index": index, "selector": raw},
                    recoverability="not_applicable",
                )
            start_frame = _parse_record_ref(
                conn, raw.get("start_frame"), field_name="start_frame"
            )
            end_frame = _parse_record_ref(
                conn, raw.get("end_frame"), field_name="end_frame"
            )
            if end_frame <= start_frame:
                raise ValidationError(
                    "end_frame must be after start_frame.",
                    details={
                        "index": index,
                        "start_frame": raw.get("start_frame"),
                        "end_frame": raw.get("end_frame"),
                        "resolved_start_frame": start_frame,
                        "resolved_end_frame": end_frame,
                    },
                    recoverability="not_applicable",
                )
            normalized.append(
                AudioGainBatchSelector(
                    kind="range",
                    track_index=track_index,
                    start_frame=start_frame,
                    end_frame=end_frame,
                    raw=raw,
                )
            )
            continue

        if has_point:
            if (
                raw.get("record_duration") is not None
                and raw.get("record_end") is not None
            ):
                raise ValidationError(
                    "Use only one of record_duration or record_end.",
                    details={"index": index, "selector": raw},
                    recoverability="not_applicable",
                )
            record_frame = _parse_record_ref(
                conn, raw.get("record_frame"), field_name="record_frame"
            )
            end_frame = None
            if raw.get("record_duration") is not None:
                end_frame = record_frame + _parse_duration_ref(
                    conn, raw.get("record_duration"), field_name="record_duration"
                )
            elif raw.get("record_end") is not None:
                end_frame = _parse_record_ref(
                    conn, raw.get("record_end"), field_name="record_end"
                )
                if end_frame <= record_frame:
                    raise ValidationError(
                        "record_end must be after record_frame.",
                        details={
                            "index": index,
                            "record_frame": raw.get("record_frame"),
                            "record_end": raw.get("record_end"),
                            "resolved_record_frame": record_frame,
                            "resolved_record_end": end_frame,
                        },
                        recoverability="not_applicable",
                    )
            normalized.append(
                AudioGainBatchSelector(
                    kind="point" if end_frame is None else "range",
                    track_index=track_index,
                    record_frame=record_frame,
                    start_frame=record_frame,
                    end_frame=end_frame,
                    raw=raw,
                )
            )
            continue

        raise ValidationError(
            "Track selectors require start_frame/end_frame or record_frame.",
            details={"index": index, "selector": raw},
            recoverability="not_applicable",
        )

    return normalized


def _switch_timeline_by_name(conn, timeline_name: str) -> dict[str, Any]:
    details = timeline_ops.switch_timeline(
        conn, name=timeline_name, return_details=True
    )
    return {key: value for key, value in details.items() if key != "timeline"}


def _wait_for_audio_track_count(
    conn, *, previous_count: int, timeout_seconds: float = 2.0
) -> int:
    after_count = _audio_track_count(conn)
    deadline = time.monotonic() + timeout_seconds
    while after_count <= previous_count and time.monotonic() < deadline:
        time.sleep(0.1)
        after_count = _audio_track_count(conn)
    return after_count


def _add_stereo_audio_track_with_fallback(conn, *, before_count: int) -> dict[str, Any]:
    native_subtype_supported = True
    fallback_used = False
    add_result: Any = None
    error: dict[str, str] | None = None

    try:
        add_result = conn.timeline.AddTrack("audio", "stereo")
    except TypeError as exc:
        native_subtype_supported = False
        error = {"type": exc.__class__.__name__, "message": str(exc)}
        add_result = False

    if add_result is False:
        native_subtype_supported = False
        fallback_used = True
        try:
            fallback_result = conn.timeline.AddTrack("audio")
        except Exception as exc:
            raise APICallFailed(
                "Failed to add stereo audio track via native and fallback AddTrack routes.",
                details={
                    "track_type": "audio",
                    "subtype": "stereo",
                    "audio_tracks_before": before_count,
                    "native_subtype_supported": native_subtype_supported,
                    "fallback_used": fallback_used,
                    "native_error": error,
                    "fallback_error": {
                        "type": exc.__class__.__name__,
                        "message": str(exc),
                    },
                },
            ) from exc
        add_result = fallback_result

    if add_result is False:
        raise APICallFailed(
            "Failed to add stereo audio track.",
            details={
                "track_type": "audio",
                "subtype": "stereo",
                "audio_tracks_before": before_count,
                "native_subtype_supported": native_subtype_supported,
                "fallback_used": fallback_used,
                "native_error": error,
                "api_result": add_result,
            },
        )

    after_count = _wait_for_audio_track_count(conn, previous_count=before_count)
    verified = after_count > before_count
    if not verified:
        raise APICallFailed(
            "Audio track add did not appear in timeline readback.",
            details={
                "track_type": "audio",
                "subtype": "stereo",
                "audio_tracks_before": before_count,
                "audio_tracks_after": after_count,
                "native_subtype_supported": native_subtype_supported,
                "fallback_used": fallback_used,
                "api_result": add_result,
            },
        )

    return {
        "requested_subtype": "stereo",
        "api_call": 'Timeline.AddTrack("audio", "stereo")',
        "fallback_api_call": 'Timeline.AddTrack("audio")' if fallback_used else None,
        "native_subtype_supported": native_subtype_supported,
        "fallback_used": fallback_used,
        "api_result": bool(add_result),
        "audio_tracks_before": before_count,
        "audio_tracks_after": after_count,
        "verified": verified,
    }


def _fetch_timeline_sequence(cursor: sqlite3.Cursor, timeline_name: str) -> str:
    rows = cursor.execute(
        "SELECT Sequence FROM Sm2Timeline WHERE Name = ?",
        (timeline_name,),
    ).fetchall()
    if not rows:
        raise ValidationError(
            "Timeline was not found in the DaVinci Resolve Disk project database.",
            details={"timeline_name": timeline_name, "table": "Sm2Timeline"},
        )
    if len(rows) > 1:
        raise ValidationError(
            "Timeline name is ambiguous in the DaVinci Resolve Disk project database.",
            details={
                "timeline_name": timeline_name,
                "matches": len(rows),
                "table": "Sm2Timeline",
            },
        )
    return str(rows[0][0])


def _coerce_int(value: Any, *, field: str) -> int:
    try:
        return int(value)
    except Exception as exc:
        raise ValidationError(
            f"{field} must be an integer frame value.",
            details={"field": field, "value": value},
            recoverability="not_applicable",
        ) from exc


def _duration_frames(value: Any) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    try:
        head, separator, tail = text.partition("|")
        base = int(head.strip())
    except Exception:
        return 0
    if not separator:
        return base
    try:
        raw = bytes.fromhex(tail.strip())
        if len(raw) == 8:
            fraction = struct.unpack("<d", raw)[0]
            if math.isfinite(fraction):
                return int(round(base + fraction))
    except Exception:
        pass
    return base


def _timeline_start_frame(conn) -> int:
    value = int(getattr(conn, "start_frame", 0) or 0)
    timeline = getattr(conn, "timeline", None)
    if value == 0 and timeline is not None and hasattr(timeline, "GetStartFrame"):
        try:
            value = int(timeline.GetStartFrame())
        except Exception:
            value = 0
    return value


def _timeline_fps(conn) -> float:
    value = getattr(conn, "fps", None)
    if value:
        return float(value)
    return 24.0


def _first_present(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    return None


def _parse_frame_count(value: Any, *, field: str, fps: float) -> int:
    if isinstance(value, int):
        return int(value)
    text = str(value).strip()
    if not text:
        raise ValidationError(
            f"{field} is required.",
            details={"field": field},
            recoverability="not_applicable",
        )
    try:
        return parse_source_frame(text, fps)
    except Exception as exc:
        raise ValidationError(
            f"{field} must be a non-negative frame count.",
            details={"field": field, "value": value},
            recoverability="not_applicable",
        ) from exc
