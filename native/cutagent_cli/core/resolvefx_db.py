"""Native ResolveFX OFX tool control on Color Page nodes via Project.db.

Live DaVinci Resolve Studio 21 proof (2026-06-10, Sony S-Log3 footage):
a GUI-authored Box Blur produced node tool params 0xC0000049 (plugin id),
0xC000005E (context), 0xC0000063/0xC00000D2/0xC00000DB (enables) and
0xC0000087 (options). Re-creating those entries byte-identically through the
Disk Project.db close/write/reopen route rendered pixel-identical frames
(1,976,127 changed pixels vs baseline, 0 vs the GUI reference), and a
never-GUI-touched `com.blackmagicdesign.resolvefx.vignette` insert rendered
a default vignette (2,070,298 changed pixels). The options payload carries
only generic processing options, so arbitrary ResolveFX run at plugin
defaults through this route.
"""

from __future__ import annotations

import sqlite3
import struct
import uuid
from typing import Any

from ..errors import APICallFailed, ValidationError
from .db_session import DiskDbMutationSession, execute_sqlite_disk_db_mutation
from .db_timeline_rows import find_ti_item_row
from .color_page_db import (
    _BASELINE_VERSION_BODY_HEX,
    _VERSION_TABLE_FIELDS_BLOB_HEX,
    _build_graded_proto_from_baseline,
    _create_lm_version_table_for_item,
    _encode_length_delimited,
    _encode_varint_field,
    _first_ld_field,
    _insert_lm_version_from_body,
    _select_active_grade_version,
    _message_varints,
    _read_varint,
    _replace_first_ld_field,
    compress_version_body,
    decompress_version_body,
)

RESOLVEFX_PLUGIN_PREFIX = "com.blackmagicdesign.resolvefx."
RESOLVEFX_TOOL_PARAM_PLUGIN_ID = 0xC0000049
RESOLVEFX_TOOL_PARAM_CONTEXT = 0xC000005E
RESOLVEFX_TOOL_PARAM_ENABLE_A = 0xC0000063
RESOLVEFX_TOOL_PARAM_OPTIONS = 0xC0000087
RESOLVEFX_TOOL_PARAM_ENABLE_B = 0xC00000D2
RESOLVEFX_TOOL_PARAM_ENABLE_C = 0xC00000DB
RESOLVEFX_TOOL_PARAM_KEYS = {
    RESOLVEFX_TOOL_PARAM_PLUGIN_ID,
    RESOLVEFX_TOOL_PARAM_CONTEXT,
    RESOLVEFX_TOOL_PARAM_ENABLE_A,
    RESOLVEFX_TOOL_PARAM_OPTIONS,
    RESOLVEFX_TOOL_PARAM_ENABLE_B,
    RESOLVEFX_TOOL_PARAM_ENABLE_C,
}
# Observed constant at the head of GUI-authored ResolveFX option payloads
# (0x4F4659; stable across Box Blur fixture and CLI re-insert render proof).
RESOLVEFX_OPTIONS_MAGIC = 5195353
RESOLVEFX_OFX_CONTEXT = "OfxImageEffectContextFilter"
RESOLVEFX_PLUGIN_ALIASES = {
    "aifacerefinement": "facerefinement2",
    "aifacerefinementlegacy": "facerefinement",
    "facerefinement": "facerefinement2",
    "facerefinementlegacy": "facerefinement",
    "facerefine": "facerefinement2",
    "facerefinementv1": "facerefinement",
    "facerefinementv2": "facerefinement2",
}
RESOLVEFX_DEFAULT_OPTION_NAMES = {
    "dstProcessingAlphaMode",
    "resolvefxVersion",
    "srcProcessingAlphaMode",
}

RESOLVEFX_PARAM_ALIASES = {
    ("com.blackmagicdesign.resolvefx.boxblur", "strength"): "HStrength",
    ("com.blackmagicdesign.resolvefx.boxblur", "hstrength"): "HStrength",
    ("com.blackmagicdesign.resolvefx.boxblur", "horizontal_strength"): "HStrength",
    ("com.blackmagicdesign.resolvefx.boxblur", "horizontal-strength"): "HStrength",
}
RESOLVEFX_RENDER_VERIFIED_PARAMS = {
    ("com.blackmagicdesign.resolvefx.boxblur", "HStrength"),
}
RESOLVEFX_PARAM_VALUE_TYPES = {
    ("com.blackmagicdesign.resolvefx.boxblur", "HStrength"): ["double"],
}
RESOLVEFX_AUTO_VALUE_TYPES = {"auto", "existing", "same"}
RESOLVEFX_AUTO_DECODABLE_VALUE_TYPES = {"double", "int", "string"}


def normalize_resolvefx_plugin_id(name: str) -> str:
    """Normalize a user-facing effect name to a ResolveFX OFX plugin id."""
    text = str(name or "").strip()
    if not text:
        raise ValidationError(
            "ResolveFX effect name must not be empty.",
            recoverability="not_applicable",
        )
    lowered = text.lower()
    if lowered.startswith("ofx."):
        lowered = lowered[len("ofx."):]
    explicit_plugin_id = lowered.startswith(RESOLVEFX_PLUGIN_PREFIX)
    if lowered.startswith(RESOLVEFX_PLUGIN_PREFIX):
        suffix = lowered[len(RESOLVEFX_PLUGIN_PREFIX):]
    else:
        suffix = lowered
    suffix = "".join(ch for ch in suffix if ch.isalnum())
    if not explicit_plugin_id:
        suffix = RESOLVEFX_PLUGIN_ALIASES.get(suffix, suffix)
    if not suffix:
        raise ValidationError(
            "ResolveFX effect name did not normalize to a plugin id.",
            details={"name": name},
            recoverability="not_applicable",
        )
    return RESOLVEFX_PLUGIN_PREFIX + suffix


def list_resolvefx_registry(conn) -> list[dict[str, Any]]:
    """Enumerate installed ResolveFX from the live Fusion tool registry."""
    fusion = conn.resolve.Fusion()
    if fusion is None or not hasattr(fusion, "GetRegList"):
        raise APICallFailed(
            "Fusion registry is not reachable for ResolveFX enumeration.",
            recoverability="manual",
        )
    regs = fusion.GetRegList(2) or {}
    values = regs.values() if hasattr(regs, "values") else regs
    rows: list[dict[str, Any]] = []
    for reg in values:
        try:
            attrs = reg.GetAttrs() or {}
        except Exception:
            continue
        reg_id = str(attrs.get("REGS_ID") or "")
        if ".resolvefx." not in reg_id.lower():
            continue
        suffix = reg_id.rsplit(".", 1)[-1]
        rows.append(
            {
                "name": str(attrs.get("REGS_UIName") or attrs.get("REGS_Name") or suffix),
                "plugin_id": RESOLVEFX_PLUGIN_PREFIX + suffix.lower(),
                "category": str(attrs.get("REGS_Category") or ""),
                "fusion_reg_id": reg_id,
            }
        )
    rows.sort(key=lambda row: (row["category"], row["name"]))
    return rows


def _resolvefx_lookup_token(value: str) -> str:
    return "".join(ch for ch in str(value or "").casefold() if ch.isalnum())


def resolve_resolvefx_plugin_id(conn, name: str) -> dict[str, Any]:
    """Resolve a user-facing ResolveFX name against the live Fusion registry."""
    text = str(name or "").strip()
    if not text:
        raise ValidationError(
            "ResolveFX effect name must not be empty.",
            recoverability="not_applicable",
        )
    normalized = normalize_resolvefx_plugin_id(text)
    explicit_id = text.casefold().startswith(("ofx.", RESOLVEFX_PLUGIN_PREFIX))
    if explicit_id:
        normalized_token = _resolvefx_lookup_token(normalized)
        try:
            rows = list_resolvefx_registry(conn)
        except Exception:
            rows = []
        for row in rows:
            plugin_id = str(row.get("plugin_id") or "")
            if _resolvefx_lookup_token(plugin_id) == normalized_token:
                return {
                    "input": text,
                    "plugin_id": plugin_id,
                    "match_type": "explicit_plugin_id_live_registry",
                    "registry_match": True,
                    "name": row.get("name"),
                    "category": row.get("category"),
                    "fusion_reg_id": row.get("fusion_reg_id"),
                }
        return {
            "input": text,
            "plugin_id": normalized,
            "match_type": "explicit_plugin_id",
            "registry_match": False,
        }
    rows = list_resolvefx_registry(conn)
    tokens = {_resolvefx_lookup_token(text), _resolvefx_lookup_token(normalized)}
    matches: list[dict[str, Any]] = []
    for row in rows:
        plugin_id = str(row.get("plugin_id") or "")
        suffix = plugin_id.removeprefix(RESOLVEFX_PLUGIN_PREFIX)
        row_tokens = {
            _resolvefx_lookup_token(plugin_id),
            _resolvefx_lookup_token(suffix),
            _resolvefx_lookup_token(row.get("name") or ""),
            _resolvefx_lookup_token(row.get("fusion_reg_id") or ""),
        }
        if tokens & row_tokens:
            matches.append(row)

    if len(matches) == 1:
        match = matches[0]
        return {
            "input": text,
            "plugin_id": match["plugin_id"],
            "match_type": "live_registry",
            "name": match.get("name"),
            "category": match.get("category"),
            "fusion_reg_id": match.get("fusion_reg_id"),
        }
    if len(matches) > 1:
        raise ValidationError(
            "ResolveFX effect name matched multiple installed plugins.",
            details={
                "input": text,
                "normalized_plugin_id": normalized,
                "matches": [
                    {
                        "name": row.get("name"),
                        "plugin_id": row.get("plugin_id"),
                        "category": row.get("category"),
                    }
                    for row in matches
                ],
            },
            recoverability="not_applicable",
        )
    candidates = [
        {
            "name": row.get("name"),
            "plugin_id": row.get("plugin_id"),
            "category": row.get("category"),
        }
        for row in rows[:20]
    ]
    raise ValidationError(
        "ResolveFX effect name was not found in the live Fusion registry.",
        details={
            "input": text,
            "normalized_plugin_id": normalized,
            "candidate_count": len(rows),
            "sample_candidates": candidates,
        },
        recoverability="not_applicable",
    )


def _resolvefx_descriptor_value_type(attrs: dict[str, Any]) -> str | None:
    control = str(attrs.get("INPID_InputControl") or "")
    data_type = str(attrs.get("INPS_DataType") or "")
    if control == "CheckboxControl":
        return "bool"
    if data_type == "Number":
        return "int" if bool(attrs.get("INPB_Integer")) else "double"
    if data_type in {"Text", "FuID"}:
        return "string"
    return None


def _resolvefx_input_descriptor_row(attrs: dict[str, Any]) -> dict[str, Any] | None:
    param_id = str(attrs.get("INPS_ID") or "").strip()
    if not param_id:
        return None
    row: dict[str, Any] = {
        "id": param_id,
        "name": str(attrs.get("INPS_Name") or ""),
        "control": str(attrs.get("INPID_InputControl") or ""),
        "data_type": str(attrs.get("INPS_DataType") or ""),
        "page": str(attrs.get("INPS_ICS_ControlPage") or ""),
        "priority": int(attrs.get("INPI_Priority") or 0),
        "passive": bool(attrs.get("INPB_Passive")),
        "external": bool(attrs.get("INPB_External")),
        "visible": bool(attrs.get("INPB_IC_Visible")),
        "integer": bool(attrs.get("INPB_Integer")),
        "suggested_value_type": _resolvefx_descriptor_value_type(attrs),
    }
    for source_key, target_key in (
        ("INPN_Default", "default"),
        ("INPN_MinScale", "min_scale"),
        ("INPN_MaxScale", "max_scale"),
        ("INPN_MinAllowed", "min_allowed"),
        ("INPN_MaxAllowed", "max_allowed"),
    ):
        value = attrs.get(source_key)
        if isinstance(value, (int, float)):
            row[target_key] = float(value)
    choices = attrs.get("INPIDT_MultiButtonControl_ID") or attrs.get("INPST_MultiButtonControl_String")
    if isinstance(choices, dict) and choices:
        row["choices"] = {str(key): str(value) for key, value in sorted(choices.items())}
    row["write_candidate"] = bool(row["suggested_value_type"]) and not row["passive"]
    return row


def _resolvefx_combo_choices(attrs: dict[str, Any]) -> dict[str, str]:
    choices: dict[str, str] = {}
    for key in (
        "INPIDT_ComboControl_ID",
        "INPIDT_MultiButtonControl_ID",
        "INPST_MultiButtonControl_String",
    ):
        raw = attrs.get(key)
        if isinstance(raw, dict):
            choices.update({str(choice_key): str(value) for choice_key, value in raw.items()})
    return dict(sorted(choices.items(), key=lambda item: int(item[0]) if item[0].isdigit() else item[0]))


def discover_resolvefx_params(conn, plugin: str) -> dict[str, Any]:
    """Discover ResolveFX OFX input descriptors through a temporary Fusion comp."""
    resolution = resolve_resolvefx_plugin_id(conn, plugin)
    fusion = conn.resolve.Fusion()
    if fusion is None or not hasattr(fusion, "NewComp"):
        raise APICallFailed(
            "Fusion temporary composition API is not reachable for ResolveFX parameter discovery.",
            recoverability="manual",
        )
    comp = None
    try:
        comp = fusion.NewComp()
        if comp is None or not hasattr(comp, "AddTool"):
            raise APICallFailed(
                "Fusion did not create a temporary composition for ResolveFX parameter discovery.",
                details={"plugin_id": resolution.get("plugin_id")},
                recoverability="manual",
            )
        tool_id = str(resolution.get("fusion_reg_id") or "")
        if not tool_id:
            plugin_id = str(resolution.get("plugin_id") or normalize_resolvefx_plugin_id(plugin))
            suffix = plugin_id.removeprefix(RESOLVEFX_PLUGIN_PREFIX)
            tool_id = f"ofx.{RESOLVEFX_PLUGIN_PREFIX}{suffix}"
        tool = comp.AddTool(tool_id)
        if tool is None or not hasattr(tool, "GetInputList"):
            raise APICallFailed(
                "Fusion could not instantiate the ResolveFX tool for parameter discovery.",
                details={"tool_id": tool_id, "plugin_resolution": resolution},
                recoverability="manual",
            )
        raw_inputs = tool.GetInputList() or {}
        values = raw_inputs.values() if hasattr(raw_inputs, "values") else raw_inputs
        rows: list[dict[str, Any]] = []
        for input_obj in values:
            try:
                attrs = input_obj.GetAttrs() if hasattr(input_obj, "GetAttrs") else {}
            except Exception:
                continue
            row = _resolvefx_input_descriptor_row(attrs or {})
            if row is not None:
                rows.append(row)
        rows.sort(key=lambda row: (int(row.get("priority") or 0), str(row.get("page") or ""), str(row.get("id") or "")))
        write_candidates = [row for row in rows if row.get("write_candidate")]
        return {
            "route": "api_native_resolvefx_param_discovery",
            "plugin_resolution": resolution,
            "plugin_id": resolution.get("plugin_id"),
            "fusion_reg_id": resolution.get("fusion_reg_id"),
            "parameter_count": len(rows),
            "write_candidate_count": len(write_candidates),
            "parameters": rows,
            "write_candidate_ids": [row["id"] for row in write_candidates],
            "verification": {
                "status": "descriptor_readback_only",
                "render_proof_status": "not_requested",
                "source": "Fusion.NewComp().AddTool().GetInputList()",
                "notes": [
                    "These are live ResolveFX OFX input descriptors, not proof that a Color Page DB option write changes rendered pixels.",
                    "Use resolvefx-param-set with render proof before treating a parameter change as visually applied.",
                ],
            },
        }
    finally:
        if comp is not None and hasattr(comp, "Close"):
            try:
                comp.Close()
            except Exception:
                pass


def discover_cst_option_registry(conn) -> dict[str, Any]:
    """Read live Color Space Transform combo option tokens from ResolveFX descriptors."""
    resolution = resolve_resolvefx_plugin_id(conn, "com.blackmagicdesign.resolvefx.colorspacetransformv2")
    fusion = conn.resolve.Fusion()
    if fusion is None or not hasattr(fusion, "NewComp"):
        raise APICallFailed(
            "Fusion temporary composition API is not reachable for CST option discovery.",
            recoverability="manual",
        )
    comp = None
    wanted = {"inputColorSpace", "inputGamma", "outputColorSpace", "outputGamma"}
    try:
        comp = fusion.NewComp()
        if comp is None or not hasattr(comp, "AddTool"):
            raise APICallFailed(
                "Fusion did not create a temporary composition for CST option discovery.",
                details={"plugin_id": resolution.get("plugin_id")},
                recoverability="manual",
            )
        tool = comp.AddTool(str(resolution.get("fusion_reg_id") or ""))
        if tool is None or not hasattr(tool, "GetInputList"):
            raise APICallFailed(
                "Fusion could not instantiate the CST ResolveFX tool for option discovery.",
                details={"plugin_resolution": resolution},
                recoverability="manual",
            )
        raw_inputs = tool.GetInputList() or {}
        values = raw_inputs.values() if hasattr(raw_inputs, "values") else raw_inputs
        choices_by_param: dict[str, dict[str, str]] = {}
        for input_obj in values:
            try:
                attrs = input_obj.GetAttrs() if hasattr(input_obj, "GetAttrs") else {}
            except Exception:
                continue
            param_id = str((attrs or {}).get("INPS_ID") or "")
            if param_id not in wanted:
                continue
            choices_by_param[param_id] = _resolvefx_combo_choices(attrs or {})
        color_space_tokens = sorted(
            set(choices_by_param.get("inputColorSpace", {}).values())
            | set(choices_by_param.get("outputColorSpace", {}).values())
        )
        gamma_tokens = sorted(
            set(choices_by_param.get("inputGamma", {}).values())
            | set(choices_by_param.get("outputGamma", {}).values())
        )
        if not color_space_tokens or not gamma_tokens:
            raise APICallFailed(
                "CST ResolveFX descriptor did not expose color space and gamma option tokens.",
                details={"choices_by_param": choices_by_param},
                recoverability="manual",
            )
        return {
            "route": "api_native_cst_option_registry",
            "plugin_resolution": resolution,
            "color_space_tokens": color_space_tokens,
            "gamma_tokens": gamma_tokens,
            "choices_by_param": choices_by_param,
            "verification": {
                "status": "descriptor_readback_only",
                "source": "Fusion.NewComp().AddTool().GetInputList().GetAttrs().INPIDT_ComboControl_ID",
            },
        }
    finally:
        if comp is not None and hasattr(comp, "Close"):
            try:
                comp.Close()
            except Exception:
                pass


def _build_tool_entry(key: int, payload: bytes) -> bytes:
    return _encode_length_delimited(
        1,
        _encode_varint_field(1, key) + _encode_length_delimited(2, payload),
    )


def _build_resolvefx_options(plugin_id: str) -> bytes:
    def option(name: bytes, value: bytes) -> bytes:
        return _encode_length_delimited(
            5,
            _encode_length_delimited(1, name) + _encode_length_delimited(2, value),
        )

    return (
        _encode_varint_field(1, RESOLVEFX_OPTIONS_MAGIC)
        + _encode_length_delimited(2, plugin_id.encode("ascii"))
        + _encode_length_delimited(3, RESOLVEFX_OFX_CONTEXT.encode("ascii"))
        + _encode_varint_field(4, 1)
        + option(b"dstProcessingAlphaMode", _encode_varint_field(1, 0))
        + option(b"resolvefxVersion", _encode_length_delimited(5, b"3.1"))
        + option(b"srcProcessingAlphaMode", _encode_varint_field(1, 0))
    )


def _encode_resolvefx_option_value(value_type: str, value: Any) -> bytes:
    kind = str(value_type or "").strip().lower()
    if kind in {"double", "float", "number"}:
        return bytes([0x11]) + struct.pack("<d", float(value))
    if kind in {"int", "integer"}:
        return _encode_varint_field(1, int(value))
    if kind in {"bool", "boolean"}:
        text = str(value).strip().lower()
        enabled = text in {"1", "true", "yes", "on"} if isinstance(value, str) else bool(value)
        return _encode_varint_field(1, 1 if enabled else 0)
    if kind in {"string", "str"}:
        return _encode_length_delimited(5, str(value).encode("utf-8"))
    raise ValidationError(
        "Unsupported ResolveFX parameter value type.",
        details={"value_type": value_type, "allowed": ["double", "int", "bool", "string"]},
        recoverability="not_applicable",
    )


def _resolve_resolvefx_value_type(
    value_type: str,
    *,
    options: dict[str, dict[str, Any]],
    resolved_name: str,
    plugin_id: str | None = None,
    discovered_options: dict[str, dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Resolve an explicit or existing-option ResolveFX parameter value type."""
    requested = str(value_type or "double").strip().lower()
    if requested not in RESOLVEFX_AUTO_VALUE_TYPES:
        return requested, {
            "requested_type": requested,
            "resolved_type": requested,
            "source": "explicit",
        }

    existing = (options or {}).get(resolved_name)
    existing_type = str((existing or {}).get("type") or "").strip().lower()
    if existing_type in RESOLVEFX_AUTO_DECODABLE_VALUE_TYPES:
        return existing_type, {
            "requested_type": requested,
            "resolved_type": existing_type,
            "source": "existing_option",
            "existing_value": (existing or {}).get("value"),
        }

    descriptor = (discovered_options or {}).get(resolved_name)
    descriptor_type = str((descriptor or {}).get("suggested_value_type") or "").strip().lower()
    if descriptor_type in {"double", "int", "bool", "string"}:
        return descriptor_type, {
            "requested_type": requested,
            "resolved_type": descriptor_type,
            "source": "fusion_input_descriptor",
            "descriptor": {
                "id": resolved_name,
                "name": (descriptor or {}).get("name"),
                "control": (descriptor or {}).get("control"),
                "data_type": (descriptor or {}).get("data_type"),
            },
        }

    raise ValidationError(
        "ResolveFX --type auto requires an existing decoded option payload; it will not guess a new parameter type.",
        details={
            "plugin_id": plugin_id,
            "param": resolved_name,
            "requested_type": requested,
            "existing_type": existing_type or None,
            "known_options": sorted((options or {}).keys()),
            "known_discovered_options": sorted((discovered_options or {}).keys()),
            "allowed_existing_types": sorted(RESOLVEFX_AUTO_DECODABLE_VALUE_TYPES),
            "note": "Use resolvefx-param-discover or an explicit --type for new parameters, then require render proof before treating the write as visually applied.",
        },
        recoverability="not_applicable",
    )


def _decode_resolvefx_option_value(payload: bytes) -> dict[str, Any]:
    try:
        tag, offset = _read_varint(payload, 0)
    except ValueError:
        return {"type": "unknown", "value": None, "raw_hex": payload.hex()}
    fn = tag >> 3
    wt = tag & 7
    try:
        if fn == 1 and wt == 0:
            value, _ = _read_varint(payload, offset)
            return {"type": "int", "value": int(value)}
        if fn == 2 and wt == 1 and offset + 8 <= len(payload):
            return {"type": "double", "value": struct.unpack("<d", payload[offset:offset + 8])[0]}
        if fn == 5 and wt == 2:
            length, offset = _read_varint(payload, offset)
            raw = payload[offset:offset + length]
            return {"type": "string", "value": raw.decode("utf-8", "replace")}
    except ValueError:
        pass
    return {"type": "unknown", "value": None, "raw_hex": payload.hex()}


def _build_resolvefx_option_entry(name: str, value_payload: bytes) -> bytes:
    return _encode_length_delimited(
        5,
        _encode_length_delimited(1, name.encode("utf-8"))
        + _encode_length_delimited(2, value_payload),
    )


def build_resolvefx_tool_entries(plugin_id: str, version_id: str) -> list[bytes]:
    """Build the six node tool-param entries for one ResolveFX instance."""
    context = f"{RESOLVEFX_OFX_CONTEXT}_{version_id}_1"
    return [
        _build_tool_entry(
            RESOLVEFX_TOOL_PARAM_PLUGIN_ID,
            _encode_length_delimited(5, plugin_id.encode("ascii")),
        ),
        _build_tool_entry(
            RESOLVEFX_TOOL_PARAM_CONTEXT,
            _encode_length_delimited(5, context.encode("ascii")),
        ),
        _build_tool_entry(RESOLVEFX_TOOL_PARAM_ENABLE_A, _encode_varint_field(4, 1)),
        _build_tool_entry(
            RESOLVEFX_TOOL_PARAM_OPTIONS,
            _encode_length_delimited(21, _build_resolvefx_options(plugin_id)),
        ),
        _build_tool_entry(RESOLVEFX_TOOL_PARAM_ENABLE_B, _encode_varint_field(4, 1)),
        _build_tool_entry(RESOLVEFX_TOOL_PARAM_ENABLE_C, _encode_varint_field(4, 1)),
    ]


def _is_primary_grade_container(field7: bytes) -> bool:
    varints = _message_varints(field7)
    if varints.get(1) == 1 and varints.get(5) == 180:
        return True
    # Modern multi-node Color Page grades store the renderable grade graph on
    # the root node container at [1, 7, 9] rather than using the older primary
    # marker pair. ResolveFX/CST tool blocks still live on that [1, 7] node.
    return _first_ld_field(field7, 9) is not None


def _field7_matches_node_index(field7: bytes, *, node_index: int, position: int) -> bool:
    varints = _message_varints(field7)
    current = varints.get(2)
    target = int(node_index)
    if current == target:
        return True
    if target == 1 and current is None and (position == 1 or _is_primary_grade_container(field7)):
        return True
    return False


def _replace_field7_for_node(base_proto: bytes, *, node_index: int, replacer) -> bytes:
    root = _first_ld_field(base_proto, 1)
    if root is None:
        raise APICallFailed(
            "ResolveFX DB route requires an existing Color Page grade body.",
            details={"path": "1"},
            recoverability="manual",
        )

    out = bytearray()
    offset = 0
    position = 0
    replaced = False
    while offset < len(root):
        start = offset
        tag, offset = _read_varint(root, offset)
        fn = tag >> 3
        wt = tag & 7
        if wt == 0:
            _, offset = _read_varint(root, offset)
            out += root[start:offset]
        elif wt == 1:
            offset += 8
            out += root[start:offset]
        elif wt == 5:
            offset += 4
            out += root[start:offset]
        elif wt == 2:
            length, offset = _read_varint(root, offset)
            payload = root[offset:offset + length]
            offset += length
            if fn == 7:
                position += 1
                if _field7_matches_node_index(payload, node_index=int(node_index), position=position):
                    out += _encode_length_delimited(7, replacer(payload))
                    replaced = True
                else:
                    out += root[start:offset]
            else:
                out += root[start:offset]
        else:
            raise APICallFailed(
                "ResolveFX DB route encountered an unsupported Color Page protobuf field.",
                details={"field_number": fn, "wire_type": wt},
                recoverability="manual",
            )
    if not replaced:
        raise ValidationError(
            "ResolveFX DB route could not find the requested Color Page node.",
            details={"node_index": int(node_index), "node_count": position},
            recoverability="not_applicable",
        )
    return _replace_first_ld_field(base_proto, 1, lambda _x: True, lambda _x: bytes(out))


def _field7_for_node(base_proto: bytes, *, node_index: int) -> bytes | None:
    root = _first_ld_field(base_proto, 1)
    if root is None:
        return None
    position = 0
    for field7 in _all_ld_fields_local(root, 7):
        position += 1
        if _field7_matches_node_index(field7, node_index=int(node_index), position=position):
            return field7
    return None


def _tool_block_entries(field10: bytes) -> list[tuple[int | None, bytes]]:
    entries: list[tuple[int | None, bytes]] = []
    offset = 0
    while offset < len(field10):
        start = offset
        try:
            tag, offset = _read_varint(field10, offset)
        except ValueError:
            break
        if tag & 7 != 2:
            break
        try:
            length, offset = _read_varint(field10, offset)
        except ValueError:
            break
        entry = field10[offset:offset + length]
        offset += length
        key = None
        try:
            entry_tag, entry_offset = _read_varint(entry, 0)
            if (entry_tag >> 3) == 1 and (entry_tag & 7) == 0:
                key, _ = _read_varint(entry, entry_offset)
        except ValueError:
            key = None
        entries.append((key, field10[start:offset]))
    return entries


def _tool_entry_payload(entry: bytes) -> bytes | None:
    try:
        tag, offset = _read_varint(entry, 0)
        if (tag >> 3) != 1 or (tag & 7) != 2:
            return None
        length, offset = _read_varint(entry, offset)
        inner = entry[offset:offset + length]
        ioff = 0
        while ioff < len(inner):
            itag, ioff = _read_varint(inner, ioff)
            fn = itag >> 3
            wt = itag & 7
            if wt == 0:
                _, ioff = _read_varint(inner, ioff)
            elif wt == 2:
                ilen, ioff = _read_varint(inner, ioff)
                payload = inner[ioff:ioff + ilen]
                ioff += ilen
                if fn == 2:
                    return payload
            else:
                break
    except ValueError:
        return None
    return None


def _extract_options_payload(entry: bytes) -> bytes | None:
    payload = _tool_entry_payload(entry)
    if not payload:
        return None
    return _first_ld_field(payload, 21)


def _option_entry_name(option_msg: bytes) -> str | None:
    offset = 0
    while offset < len(option_msg):
        try:
            tag, offset = _read_varint(option_msg, offset)
        except ValueError:
            return None
        fn = tag >> 3
        wt = tag & 7
        if wt == 0:
            try:
                _, offset = _read_varint(option_msg, offset)
            except ValueError:
                return None
        elif wt == 2:
            try:
                length, offset = _read_varint(option_msg, offset)
            except ValueError:
                return None
            payload = option_msg[offset:offset + length]
            offset += length
            if fn == 1:
                return payload.decode("utf-8", "replace")
        elif wt == 1:
            offset += 8
        elif wt == 5:
            offset += 4
        else:
            return None
    return None


def _parse_resolvefx_options(options_payload: bytes) -> dict[str, dict[str, Any]]:
    options: dict[str, dict[str, Any]] = {}
    offset = 0
    while offset < len(options_payload):
        try:
            tag, offset = _read_varint(options_payload, offset)
        except ValueError:
            break
        fn = tag >> 3
        wt = tag & 7
        if wt == 0:
            try:
                _, offset = _read_varint(options_payload, offset)
            except ValueError:
                break
        elif wt == 2:
            try:
                length, offset = _read_varint(options_payload, offset)
            except ValueError:
                break
            payload = options_payload[offset:offset + length]
            offset += length
            if fn != 5:
                continue
            name = _option_entry_name(payload)
            if not name:
                continue
            value_payload = _first_ld_field(payload, 2) or b""
            decoded = _decode_resolvefx_option_value(value_payload)
            decoded["raw_hex"] = value_payload.hex()
            options[name] = decoded
        elif wt == 1:
            offset += 8
        elif wt == 5:
            offset += 4
        else:
            break
    return options


def _resolvefx_option_names(options_payload: bytes) -> list[str]:
    names: list[str] = []
    offset = 0
    while offset < len(options_payload):
        try:
            tag, offset = _read_varint(options_payload, offset)
        except ValueError:
            break
        fn = tag >> 3
        wt = tag & 7
        if wt == 0:
            try:
                _, offset = _read_varint(options_payload, offset)
            except ValueError:
                break
        elif wt == 2:
            try:
                length, offset = _read_varint(options_payload, offset)
            except ValueError:
                break
            payload = options_payload[offset:offset + length]
            offset += length
            if fn == 5:
                option_name = _option_entry_name(payload)
                if option_name:
                    names.append(option_name)
        elif wt == 1:
            offset += 8
        elif wt == 5:
            offset += 4
        else:
            break
    return names


def _set_resolvefx_option(options_payload: bytes, name: str, value_payload: bytes) -> bytes:
    replacement = _build_resolvefx_option_entry(name, value_payload)
    out = bytearray()
    offset = 0
    replaced = False
    inserted = False
    target_exists = name in _resolvefx_option_names(options_payload)
    while offset < len(options_payload):
        start = offset
        try:
            tag, offset = _read_varint(options_payload, offset)
        except ValueError:
            out += options_payload[start:]
            break
        fn = tag >> 3
        wt = tag & 7
        if wt == 0:
            try:
                _, offset = _read_varint(options_payload, offset)
            except ValueError:
                out += options_payload[start:]
                break
            out += options_payload[start:offset]
            continue
        if wt == 2:
            try:
                length, offset = _read_varint(options_payload, offset)
            except ValueError:
                out += options_payload[start:]
                break
            payload = options_payload[offset:offset + length]
            offset += length
            raw = options_payload[start:offset]
            if fn == 5:
                option_name = _option_entry_name(payload)
                if option_name == name:
                    out += replacement
                    replaced = True
                    continue
                if (
                    not replaced
                    and not inserted
                    and not target_exists
                    and option_name in RESOLVEFX_DEFAULT_OPTION_NAMES
                ):
                    out += replacement
                    inserted = True
            out += raw
            continue
        if wt == 1:
            offset += 8
        elif wt == 5:
            offset += 4
        else:
            out += options_payload[start:]
            break
        out += options_payload[start:offset]
    if not replaced and not inserted:
        out += replacement
    return bytes(out)


def read_resolvefx_state(base_proto: bytes, *, node_index: int = 1) -> dict[str, Any]:
    """Read ResolveFX tool params from one Color Page node container."""
    state: dict[str, Any] = {
        "node_index": int(node_index),
        "plugin_id": None,
        "context": None,
        "tool_param_keys": [],
        "options": {},
    }
    field7 = _field7_for_node(base_proto, node_index=int(node_index))
    if field7 is None:
        return state
    field10 = _first_ld_field(field7, 10)
    if not field10:
        return state
    for key, raw in _tool_block_entries(field10):
        if key in RESOLVEFX_TOOL_PARAM_KEYS:
            state["tool_param_keys"].append(f"0x{key:08X}")
        if key in (RESOLVEFX_TOOL_PARAM_PLUGIN_ID, RESOLVEFX_TOOL_PARAM_CONTEXT):
            value = _extract_string_payload(raw)
            if key == RESOLVEFX_TOOL_PARAM_PLUGIN_ID:
                state["plugin_id"] = value
            else:
                state["context"] = value
        if key == RESOLVEFX_TOOL_PARAM_OPTIONS:
            options_payload = _extract_options_payload(raw)
            if options_payload:
                state["options"] = _parse_resolvefx_options(options_payload)
    return state


def _select_latest_resolvefx_grade_version(
    cursor: sqlite3.Cursor,
    version_table_id: str | None,
) -> sqlite3.Row | None:
    if not version_table_id:
        return None
    return _select_active_grade_version(cursor, str(version_table_id))


def _select_seed_resolvefx_grade_body(
    cursor: sqlite3.Cursor,
    version_table_id: str | None,
) -> bytes | None:
    if not version_table_id:
        return None
    row = _select_active_grade_version(cursor, str(version_table_id))
    if row and row["Body"]:
        return row["Body"]
    return None


def _activate_resolvefx_grade_version(
    cursor: sqlite3.Cursor,
    *,
    version_table_id: str,
    version_id: str,
) -> None:
    cursor.execute(
        '''UPDATE "ListMgt::LmVersionTable" SET pActive = ?
           WHERE "ListMgt::LmVersionTable_id" = ?''',
        (version_id, version_table_id),
    )
    cursor.execute(
        '''INSERT INTO "ListMgt::LmVersion_ListMgt::LmVersionTable"
           (DbOwner, DbAssociate, DbPropertyName, DbIndex)
           SELECT ?, ?, 'Locals', 0
           WHERE NOT EXISTS (
             SELECT 1 FROM "ListMgt::LmVersion_ListMgt::LmVersionTable"
             WHERE DbOwner = ? AND DbAssociate = ?
           )''',
        (version_table_id, version_id, version_table_id, version_id),
    )


def _all_ld_fields_local(data: bytes, field_number: int) -> list[bytes]:
    out: list[bytes] = []
    offset = 0
    while offset < len(data):
        try:
            tag, offset = _read_varint(data, offset)
        except ValueError:
            break
        fn = tag >> 3
        wt = tag & 7
        if wt == 0:
            _, offset = _read_varint(data, offset)
        elif wt == 2:
            length, offset = _read_varint(data, offset)
            if fn == field_number:
                out.append(data[offset:offset + length])
            offset += length
        elif wt == 1:
            offset += 8
        elif wt == 5:
            offset += 4
        else:
            break
    return out


def _extract_string_payload(entry: bytes) -> str | None:
    # entry = f1{f1=key, f2{f5=string}}
    try:
        _, offset = _read_varint(entry, 0)  # outer f1 tag
        length, offset = _read_varint(entry, offset)
        inner = entry[offset:offset + length]
        ioff = 0
        while ioff < len(inner):
            tag, ioff = _read_varint(inner, ioff)
            fn = tag >> 3
            wt = tag & 7
            if wt == 0:
                _, ioff = _read_varint(inner, ioff)
            elif wt == 2:
                ilen, ioff = _read_varint(inner, ioff)
                payload = inner[ioff:ioff + ilen]
                ioff += ilen
                if fn == 2:
                    ptag, poff = _read_varint(payload, 0)
                    if (ptag >> 3) == 5 and (ptag & 7) == 2:
                        plen, poff = _read_varint(payload, poff)
                        return payload[poff:poff + plen].decode("ascii", "ignore")
            else:
                break
    except ValueError:
        return None
    return None


def _rebuild_tool_block(field10: bytes, new_entries: list[bytes]) -> bytes:
    out = bytearray()
    for key, raw in _tool_block_entries(field10):
        if key in RESOLVEFX_TOOL_PARAM_KEYS:
            continue
        out += raw
    for entry in new_entries:
        out += entry
    return bytes(out)


def _patch_resolvefx_into_body(
    base_proto: bytes,
    new_entries: list[bytes],
    *,
    node_index: int = 1,
) -> bytes:
    def _replace_field7(field7: bytes) -> bytes:
        field10 = _first_ld_field(field7, 10) or b""
        new_field10 = _rebuild_tool_block(field10, new_entries)
        if field10:
            return _replace_first_ld_field(field7, 10, lambda _x: True, lambda _x: new_field10)
        return field7 + _encode_length_delimited(10, new_field10)

    return _replace_field7_for_node(base_proto, node_index=int(node_index), replacer=_replace_field7)


def _replace_tool_entry(field10: bytes, target_key: int, replacement: bytes) -> bytes:
    out = bytearray()
    replaced = False
    for key, raw in _tool_block_entries(field10):
        if key == target_key:
            out += replacement
            replaced = True
        else:
            out += raw
    if not replaced:
        raise APICallFailed(
            "ResolveFX parameter route could not find the native options payload.",
            details={"target_key": f"0x{target_key:08X}"},
            recoverability="manual",
        )
    return bytes(out)


def normalize_resolvefx_param_name(plugin_id: str, name: str) -> str:
    text = str(name or "").strip()
    if not text:
        raise ValidationError(
            "ResolveFX parameter name must not be empty.",
            recoverability="not_applicable",
        )
    alias_key = (normalize_resolvefx_plugin_id(plugin_id), text.lower())
    resolved = RESOLVEFX_PARAM_ALIASES.get(alias_key, text)
    try:
        resolved.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValidationError(
            "ResolveFX parameter names must be UTF-8 encodable.",
            details={"param": name},
            recoverability="not_applicable",
        ) from exc
    return resolved


def resolve_resolvefx_param_support(plugin_id: str, requested_name: str, resolved_name: str) -> dict[str, Any]:
    """Return the support tier for a ResolveFX option payload name."""
    normalized_plugin = normalize_resolvefx_plugin_id(plugin_id)
    alias_key = (normalized_plugin, str(requested_name or "").strip().lower())
    verified = (
        (normalized_plugin, resolved_name) in RESOLVEFX_RENDER_VERIFIED_PARAMS
        or alias_key in RESOLVEFX_PARAM_ALIASES
    )
    if verified:
        return {
            "status": "render_proof_verified_param",
            "render_proof_required_for_success": True,
            "notes": [
                "This ResolveFX parameter name is backed by a GUI-derived payload fixture and live render proof.",
            ],
        }
    return {
        "status": "raw_unverified_param_name",
        "render_proof_required_for_success": True,
        "notes": [
            "This parameter name can be encoded into the native options payload, but it is not artist-safe until a render proof changes pixels.",
        ],
    }


def describe_resolvefx_param_support(plugin_id: str | None) -> dict[str, Any]:
    """Return machine-readable support metadata for one ResolveFX plugin."""
    if not plugin_id:
        return {
            "plugin_id": None,
            "route_scope": "node_scoped_color_page_node",
            "raw_param_encoding_supported": False,
            "raw_param_encoding_status": "no_resolvefx_tool",
            "render_verified_params": [],
            "aliases": [],
            "broad_parity": False,
            "verification_required": "Add a ResolveFX tool first, then rerun parameter list/set.",
        }

    normalized_plugin = normalize_resolvefx_plugin_id(plugin_id)
    alias_rows = [
        {"alias": alias, "param": param}
        for (alias_plugin, alias), param in sorted(RESOLVEFX_PARAM_ALIASES.items())
        if alias_plugin == normalized_plugin
    ]
    aliases_by_param: dict[str, list[str]] = {}
    for row in alias_rows:
        aliases_by_param.setdefault(str(row["param"]), []).append(str(row["alias"]))

    verified_rows = []
    for param_plugin, param_name in sorted(RESOLVEFX_RENDER_VERIFIED_PARAMS):
        if param_plugin != normalized_plugin:
            continue
        verified_rows.append(
            {
                "name": param_name,
                "aliases": sorted(aliases_by_param.get(param_name, [])),
                "value_types": list(RESOLVEFX_PARAM_VALUE_TYPES.get((param_plugin, param_name), ["double"])),
                "status": "render_proof_verified_param",
            }
        )

    return {
        "plugin_id": normalized_plugin,
        "route_scope": "node_scoped_color_page_node",
        "raw_param_encoding_supported": True,
        "raw_param_encoding_status": "render_proof_required",
        "auto_value_type_inference": {
            "status": "existing_decoded_options_only",
            "supported_existing_types": sorted(RESOLVEFX_AUTO_DECODABLE_VALUE_TYPES),
            "unsupported_existing_types": ["bool", "unknown"],
            "notes": [
                "resolvefx-param-set --type auto can reuse the decoded type of an option already present in the active OFX payload.",
                "It intentionally fails for missing or undecoded options so new ResolveFX parameters are not guessed.",
            ],
        },
        "render_verified_params": verified_rows,
        "aliases": alias_rows,
        "broad_parity": False,
        "verification_required": (
            "Every raw/unlisted ResolveFX parameter write must produce a fresh rendered-frame pixel diff before it can be treated as visually applied."
        ),
    }


def _describe_resolvefx_options(plugin_id: str | None, state: dict[str, Any]) -> list[dict[str, Any]]:
    """Return stable, support-annotated option rows for a decoded ResolveFX state."""
    rows: list[dict[str, Any]] = []
    for name, value in sorted((state.get("options") or {}).items()):
        decoded_type = str(value.get("type") or "").strip().lower()
        auto_supported = decoded_type in RESOLVEFX_AUTO_DECODABLE_VALUE_TYPES
        row = {
            "name": name,
            "type": value.get("type"),
            "value": value.get("value"),
            "raw_hex": value.get("raw_hex"),
            "is_default_processing_option": name in RESOLVEFX_DEFAULT_OPTION_NAMES,
            "auto_value_type_supported": auto_supported,
            "suggested_value_type": decoded_type if auto_supported else None,
        }
        if not auto_supported:
            row["auto_value_type_unavailable_reason"] = (
                "option_type_not_decoded_for_auto_write"
                if decoded_type
                else "missing_option_type"
            )
        if plugin_id:
            row["param_support"] = resolve_resolvefx_param_support(plugin_id, name, name)
        else:
            row["param_support"] = {
                "status": "no_resolvefx_tool",
                "render_proof_required_for_success": True,
                "notes": [
                    "No ResolveFX tool is present on the requested Color Page node.",
                ],
            }
        rows.append(row)
    return rows


def read_resolvefx_params(
    conn: Any,
    *,
    clip_name: str | None = None,
    node_index: int = 1,
    plugin: str | None = None,
) -> dict[str, Any]:
    """Read the active ResolveFX option payload for a timeline clip/node."""
    target_node_index = int(node_index)
    if target_node_index < 1:
        raise ValidationError(
            "Color Page node index must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    expected_plugin_id = normalize_resolvefx_plugin_id(plugin) if plugin else None

    from ..runtime_health import resolve_current_disk_project_db
    from .db_timeline_selection import resolve_video_group

    item_ref = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None
    db_details = resolve_current_disk_project_db(conn)
    project_db_path = str(db_details.get("project_db_path") or "")
    if not project_db_path:
        raise APICallFailed(
            "Could not determine Project.db path for ResolveFX parameter readback.",
            details={"current_database": db_details},
            recoverability="manual",
        )

    connection = sqlite3.connect(f"file:{project_db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        row = find_ti_item_row(
            connection.cursor(),
            item=item_ref,
            db_type="Sm2TiVideoClip",
            timeline_name=timeline_name,
        )
        clip_id = row["Sm2TiItem_id"]
        version_table_id = row["pLmVerTable"]
        version = _select_active_grade_version(connection.cursor(), str(version_table_id)) if version_table_id else None
        version_id = version["ListMgt::LmVersion_id"] if version else None
        state = read_resolvefx_state(
            decompress_version_body(version["Body"]),
            node_index=target_node_index,
        ) if version and version["Body"] else {
            "node_index": target_node_index,
            "plugin_id": None,
            "context": None,
            "tool_param_keys": [],
            "options": {},
        }
    finally:
        connection.close()

    plugin_id = state.get("plugin_id")
    if expected_plugin_id and plugin_id != expected_plugin_id:
        raise ValidationError(
            "ResolveFX parameter readback target effect does not match the current node effect.",
            details={"expected_plugin_id": expected_plugin_id, "current_plugin_id": plugin_id},
            recoverability="not_applicable",
        )
    option_rows = _describe_resolvefx_options(str(plugin_id) if plugin_id else None, state)
    support_summary = describe_resolvefx_param_support(str(plugin_id) if plugin_id else None)
    return {
        "route": "db_direct_color_page_resolvefx_param_list",
        "clip": item_ref.name,
        "clip_id": clip_id,
        "node_index": target_node_index,
        "timeline": timeline_name,
        "project_db_path": project_db_path,
        "project_name": db_details.get("project_name"),
        "version_table_id": version_table_id,
        "version_id": version_id,
        "has_resolvefx_tool": bool(plugin_id),
        "plugin_id": plugin_id,
        "context": state.get("context"),
        "tool_param_keys": list(state.get("tool_param_keys") or []),
        "options": option_rows,
        "option_count": len(option_rows),
        "param_support_summary": support_summary,
        "verified_param_names": [
            row["name"]
            for row in option_rows
            if (row.get("param_support") or {}).get("status") == "render_proof_verified_param"
        ],
        "raw_unverified_param_names": [
            row["name"]
            for row in option_rows
            if (row.get("param_support") or {}).get("status") == "raw_unverified_param_name"
        ],
        "verification": {
            "status": "readback_only",
            "render_proof_status": "not_requested",
            "source": "active_color_page_grade_version_project_db",
            "notes": [
                "This command only reports decoded native ResolveFX option payloads.",
                "Use resolvefx-param-set with render proof before claiming a parameter is visually applied.",
            ],
        },
    }


def _patch_resolvefx_option_into_body(
    base_proto: bytes,
    *,
    node_index: int = 1,
    param_name: str,
    value_payload: bytes,
) -> bytes:
    def _replace_field7(field7: bytes) -> bytes:
        field10 = _first_ld_field(field7, 10)
        if not field10:
            raise APICallFailed(
                "ResolveFX parameter route requires an existing ResolveFX tool on the requested node.",
                details={"node_index": int(node_index)},
                recoverability="manual",
            )
        options_entry = None
        for key, raw in _tool_block_entries(field10):
            if key == RESOLVEFX_TOOL_PARAM_OPTIONS:
                options_entry = raw
                break
        if options_entry is None:
            raise APICallFailed(
                "ResolveFX parameter route could not find the native options entry.",
                recoverability="manual",
            )
        options_payload = _extract_options_payload(options_entry)
        if options_payload is None:
            raise APICallFailed(
                "ResolveFX parameter route could not decode the native options payload.",
                recoverability="manual",
            )
        new_options = _set_resolvefx_option(options_payload, param_name, value_payload)
        replacement = _build_tool_entry(
            RESOLVEFX_TOOL_PARAM_OPTIONS,
            _encode_length_delimited(21, new_options),
        )
        new_field10 = _replace_tool_entry(field10, RESOLVEFX_TOOL_PARAM_OPTIONS, replacement)
        return _replace_first_ld_field(field7, 10, lambda _x: True, lambda _x: new_field10)

    return _replace_field7_for_node(base_proto, node_index=int(node_index), replacer=_replace_field7)


def write_resolvefx_tool(
    conn: Any,
    *,
    clip_name: str | None = None,
    node_index: int = 1,
    plugin: str | None = None,
    remove: bool = False,
) -> dict[str, Any]:
    """Insert (or remove) a native ResolveFX OFX tool on a Color Page node."""
    target_node_index = int(node_index)
    if target_node_index < 1:
        raise ValidationError(
            "Color Page node index must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    plugin_id = None if remove and not plugin else normalize_resolvefx_plugin_id(plugin or "")

    from .db_timeline_selection import resolve_video_group

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
        ver = _select_latest_resolvefx_grade_version(cursor, ver_table_id)
        if not ver or not ver["Body"]:
            if remove:
                raise APICallFailed(
                    "ResolveFX remove route requires an existing grade version.",
                    details={"clip": item_ref.name},
                    recoverability="manual",
                )
            seed_body = _select_seed_resolvefx_grade_body(cursor, ver_table_id)
            base_proto = decompress_version_body(
                seed_body or bytes.fromhex(_BASELINE_VERSION_BODY_HEX)
            )
            base_proto = _build_graded_proto_from_baseline(base_proto, {})
            if not ver_table_id:
                ver_table_id = _create_lm_version_table_for_item(
                    cursor,
                    item_id=str(clip_id),
                    fields_blob=bytes.fromhex(_VERSION_TABLE_FIELDS_BLOB_HEX),
                )
                session.steps.append("create_grade_version_table")
            version_id = str(uuid.uuid4())
            created_version = True
        else:
            version_id = ver["ListMgt::LmVersion_id"]
            base_proto = decompress_version_body(ver["Body"])
            created_version = False

        if not base_proto:
            raise APICallFailed(
                "ResolveFX DB route could not prepare a Color Page grade body.",
                details={"clip": item_ref.name, "plugin_id": plugin_id},
                recoverability="manual",
            )
        entries = [] if remove else build_resolvefx_tool_entries(str(plugin_id), str(version_id))
        new_proto = _patch_resolvefx_into_body(base_proto, entries, node_index=target_node_index)
        new_body = compress_version_body(new_proto)
        if created_version:
            _insert_lm_version_from_body(
                cursor,
                body=new_body,
                version_id=version_id,
                version_table_id=str(ver_table_id),
            )
            _activate_resolvefx_grade_version(
                cursor,
                version_table_id=str(ver_table_id),
                version_id=str(version_id),
            )
            session.steps.append("create_resolvefx_grade_version")
        else:
            cursor.execute(
                '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
                   WHERE "ListMgt::LmVersion_id" = ?''',
                (new_body, version_id),
            )
            session.steps.append("update_resolvefx_grade_version")
        session.steps.append("remove_resolvefx_tool" if remove else "insert_resolvefx_tool")
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "node_index": target_node_index,
            "version_id": version_id,
            "created_version": created_version,
            "created_version_table": "create_grade_version_table" in session.steps,
            "plugin_id": plugin_id,
            "removed": remove,
            "state_after_write": read_resolvefx_state(new_proto, node_index=target_node_index),
        }

    def verifier(_fresh_conn: Any, mutation_result: Any, session: DiskDbMutationSession) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "ResolveFX DB mutation did not return a mutation payload for verification.",
                details={"mutation_result": mutation_result},
            )
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
                    "ResolveFX verification could not read the active grade body.",
                    details={"version_id": version_id},
                )
            state = read_resolvefx_state(decompress_version_body(row["Body"]), node_index=target_node_index)
        finally:
            connection.close()

        if remove:
            verified = state.get("plugin_id") is None
        else:
            verified = state.get("plugin_id") == plugin_id
        if not verified:
            raise APICallFailed(
                "ResolveFX DB write did not verify after project reload.",
                details={
                    "expected_plugin_id": None if remove else plugin_id,
                    "readback": state,
                    "project_db_path": session.project_db_path,
                },
                recoverability="manual",
            )
        return {
            "status": "verified",
            "node_index": target_node_index,
            "plugin_id": state.get("plugin_id"),
            "removed": remove,
            "readback": state,
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page resolvefx db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    if isinstance(result, dict):
        result["db_session_route"] = result.get("route")
        result["route"] = (
            "db_workaround_color_page_resolvefx_remove"
            if remove
            else "db_workaround_color_page_resolvefx_add"
        )
        result["plugin_id"] = plugin_id
    return result


def write_resolvefx_param(
    conn: Any,
    *,
    clip_name: str | None = None,
    node_index: int = 1,
    param_name: str,
    value: Any,
    value_type: str = "double",
    plugin: str | None = None,
) -> dict[str, Any]:
    """Set a native ResolveFX OFX option on a Color Page node."""
    target_node_index = int(node_index)
    if target_node_index < 1:
        raise ValidationError(
            "Color Page node index must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    expected_plugin_id = normalize_resolvefx_plugin_id(plugin) if plugin else None

    from .db_timeline_selection import resolve_video_group

    item_ref = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None
    descriptor_discovery: dict[str, Any] | None = None
    discovered_options: dict[str, dict[str, Any]] = {}
    descriptor_discovery_error: str | None = None
    if str(value_type or "").strip().lower() in RESOLVEFX_AUTO_VALUE_TYPES:
        try:
            current_params = read_resolvefx_params(
                conn,
                clip_name=clip_name,
                node_index=target_node_index,
                plugin=expected_plugin_id,
            )
            current_plugin_id = str(current_params.get("plugin_id") or expected_plugin_id or "")
            if current_plugin_id:
                descriptor_discovery = discover_resolvefx_params(conn, current_plugin_id)
                discovered_options = {
                    str(row.get("id")): row
                    for row in descriptor_discovery.get("parameters", [])
                    if row.get("id")
                }
        except Exception as exc:
            descriptor_discovery_error = str(exc)

    def writer(connection: Any, cursor: sqlite3.Cursor, session: DiskDbMutationSession) -> dict[str, Any]:
        row = find_ti_item_row(
            cursor,
            item=item_ref,
            db_type="Sm2TiVideoClip",
            timeline_name=timeline_name,
        )
        clip_id = row["Sm2TiItem_id"]
        ver = _select_active_grade_version(cursor, str(row["pLmVerTable"])) if row["pLmVerTable"] else None
        if not ver or not ver["Body"]:
            raise APICallFailed(
                "ResolveFX parameter route requires an existing grade version and ResolveFX tool. "
                "Add the effect first with `color page resolvefx-add`.",
                details={"clip": item_ref.name, "param_name": param_name},
                recoverability="manual",
            )
        version_id = ver["ListMgt::LmVersion_id"]
        base_proto = decompress_version_body(ver["Body"])
        state_before = read_resolvefx_state(base_proto, node_index=target_node_index)
        plugin_id = state_before.get("plugin_id")
        if not plugin_id:
            raise APICallFailed(
                "ResolveFX parameter route requires an existing ResolveFX tool on the requested node.",
                details={"clip": item_ref.name, "node_index": target_node_index, "state": state_before},
                recoverability="manual",
            )
        if expected_plugin_id and plugin_id != expected_plugin_id:
            raise ValidationError(
                "ResolveFX parameter target effect does not match the current node effect.",
                details={"node_index": target_node_index, "expected_plugin_id": expected_plugin_id, "current_plugin_id": plugin_id},
                recoverability="not_applicable",
            )
        resolved_param_name = normalize_resolvefx_param_name(str(plugin_id), param_name)
        param_support = resolve_resolvefx_param_support(
            str(plugin_id),
            param_name,
            resolved_param_name,
        )
        effective_value_type, value_type_resolution = _resolve_resolvefx_value_type(
            value_type,
            options=state_before.get("options") or {},
            resolved_name=resolved_param_name,
            plugin_id=str(plugin_id),
            discovered_options=discovered_options,
        )
        encoded_value = _encode_resolvefx_option_value(effective_value_type, value)
        expected_decoded = _decode_resolvefx_option_value(encoded_value)
        new_proto = _patch_resolvefx_option_into_body(
            base_proto,
            node_index=target_node_index,
            param_name=resolved_param_name,
            value_payload=encoded_value,
        )
        cursor.execute(
            '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
               WHERE "ListMgt::LmVersion_id" = ?''',
            (compress_version_body(new_proto), version_id),
        )
        session.steps.append("set_resolvefx_param")
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "node_index": target_node_index,
            "version_id": version_id,
            "plugin_id": plugin_id,
            "param": param_name,
            "resolved_param": resolved_param_name,
            "param_support": param_support,
            "value_type": effective_value_type,
            "requested_value_type": value_type,
            "value_type_resolution": value_type_resolution,
            "param_discovery": (
                None
                if descriptor_discovery is None
                else {
                    "route": descriptor_discovery.get("route"),
                    "source": (descriptor_discovery.get("verification") or {}).get("source"),
                    "parameter_count": descriptor_discovery.get("parameter_count"),
                    "write_candidate_count": descriptor_discovery.get("write_candidate_count"),
                    "matched": discovered_options.get(resolved_param_name),
                }
            ),
            "param_discovery_error": descriptor_discovery_error,
            "value": expected_decoded.get("value"),
            "expected_readback": expected_decoded,
            "state_after_write": read_resolvefx_state(new_proto, node_index=target_node_index),
        }

    def verifier(_fresh_conn: Any, mutation_result: Any, session: DiskDbMutationSession) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "ResolveFX parameter mutation did not return a mutation payload for verification.",
                details={"mutation_result": mutation_result},
            )
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
                    "ResolveFX parameter verification could not read the active grade body.",
                    details={"version_id": version_id},
                )
            state = read_resolvefx_state(decompress_version_body(row["Body"]), node_index=target_node_index)
        finally:
            connection.close()

        resolved = str(mutation_result.get("resolved_param") or "")
        readback = (state.get("options") or {}).get(resolved)
        expected = mutation_result.get("expected_readback") or {}
        verified = bool(readback) and readback.get("type") == expected.get("type")
        if verified and expected.get("type") == "double":
            verified = abs(float(readback.get("value")) - float(expected.get("value"))) < 1e-9
        elif verified:
            verified = readback.get("value") == expected.get("value")
        if not verified:
            raise APICallFailed(
                "ResolveFX parameter DB write did not verify after project reload.",
                details={
                    "expected_param": resolved,
                    "expected": expected,
                    "readback": readback,
                    "state": state,
                    "project_db_path": session.project_db_path,
                },
                recoverability="manual",
            )
        return {
            "status": "db_readback_verified",
            "node_index": target_node_index,
            "plugin_id": state.get("plugin_id"),
            "param": resolved,
            "readback": readback,
            "param_support": mutation_result.get("param_support"),
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color page resolvefx parameter db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    if isinstance(result, dict):
        result["db_session_route"] = result.get("route")
        result["route"] = "db_workaround_color_page_resolvefx_param_set"
    return result
