from __future__ import annotations

import os
import re
import tempfile
from typing import Any, Dict, Optional

from ...errors import APICallFailed, ValidationError
from .. import color_page_db


def _format_cdl_float(value: float) -> str:
    return f"{float(value):.6g}"


def _format_cdl_triplet(values: tuple[float, float, float]) -> str:
    return " ".join(_format_cdl_float(value) for value in values)


def _cdl_map(
    *,
    node_index: int,
    slope: tuple[float, float, float],
    offset: tuple[float, float, float],
    power: tuple[float, float, float],
    saturation: Optional[float],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "NodeIndex": str(node_index),
        "Slope": _format_cdl_triplet(slope),
        "Offset": _format_cdl_triplet(offset),
        "Power": _format_cdl_triplet(power),
    }
    if saturation is not None:
        payload["Saturation"] = _format_cdl_float(saturation)
    return payload


def _readback_cdl_from_color_state(readback: Dict[str, Any], *, node_index: int = 1) -> Dict[str, Any]:
    lift = readback.get("lift") if isinstance(readback.get("lift"), dict) else {}
    gamma = readback.get("gamma") if isinstance(readback.get("gamma"), dict) else {}
    gain = readback.get("gain") if isinstance(readback.get("gain"), dict) else {}

    offsets: list[float] = []
    slopes: list[float] = []
    powers: list[float] = []
    for channel in ("r", "g", "b"):
        gain_value = float(gain.get(channel, 1.0))
        offset_value = color_page_db.lift_to_cdl_offset(float(lift.get(channel, 0.0)), gain_value)
        offsets.append(offset_value)
        slopes.append(color_page_db.gain_to_cdl_slope(gain_value, offset_value))
        powers.append(color_page_db.gamma_to_cdl_power(float(gamma.get(channel, 0.0))))

    saturation = readback.get("saturation")
    return _cdl_map(
        node_index=node_index,
        slope=(slopes[0], slopes[1], slopes[2]),
        offset=(offsets[0], offsets[1], offsets[2]),
        power=(powers[0], powers[1], powers[2]),
        saturation=float(saturation) if saturation is not None else None,
    )


def _project_db_read_cdl(conn, clip_name: Optional[str], *, node_index: int = 1) -> Dict[str, Any]:
    if node_index != 1:
        return {
            "available": False,
            "cdl": None,
            "source": "project_db",
            "note": "Project.db CDL readback is only available for node 1 primary wheel values.",
        }

    data = color_page_db.read_color_grade_for_clip(conn, clip_name=clip_name)
    readback = data.get("readback") if isinstance(data.get("readback"), dict) else {}
    if not readback.get("has_grade"):
        return {
            "available": False,
            "cdl": None,
            "source": "project_db",
            "project_db_path": data.get("project_db_path"),
            "clip": data.get("clip"),
            "note": "No Project.db color grade readback is available for this clip.",
        }

    return {
        "available": True,
        "source": "project_db",
        "clip": data.get("clip"),
        "clip_id": data.get("clip_id"),
        "project_db_path": data.get("project_db_path"),
        "cdl": _readback_cdl_from_color_state(readback, node_index=node_index),
        "db_readback": readback,
        "note": "DaVinci Resolve's scripting API does not expose GetCDL readback; CDL values were reconstructed from verified Project.db primary color parameters.",
    }


def _project_db_params_from_wheels(
    lift: tuple[float, float, float],
    gamma: tuple[float, float, float],
    gain: tuple[float, float, float],
    saturation: Optional[float],
) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    for suffix, lift_value, gamma_value, gain_value in zip(("r", "g", "b"), lift, gamma, gain):
        params[f"lift_{suffix}"] = color_page_db.cdl_offset_to_lift(lift_value, gain_value)
        params[f"gamma_{suffix}"] = color_page_db.cdl_power_to_gamma(gamma_value)
        params[f"gain_{suffix}"] = color_page_db.cdl_slope_to_gain(gain_value, lift_value)
    if saturation is not None:
        params["saturation"] = saturation
    return params


def _verify_wheels_with_project_db(
    conn,
    clip_name: Optional[str],
    *,
    node_index: int,
    lift: tuple[float, float, float],
    gamma: tuple[float, float, float],
    gain: tuple[float, float, float],
    saturation: Optional[float],
) -> Dict[str, Any]:
    if node_index != 1:
        return {
            "available": False,
            "source": "project_db",
            "skipped": True,
            "reason": "node_not_supported",
            "note": "Project.db verification is limited to node 1 primary wheel/CDL values.",
        }

    params = _project_db_params_from_wheels(lift, gamma, gain, saturation)
    db_result = color_page_db.write_color_grade(conn, clip_name=clip_name, **params)
    readback = db_result.get("readback") if isinstance(db_result.get("readback"), dict) else {}
    return {
        "available": True,
        "source": "project_db_verified",
        "route": "db_workaround_color_wheels_primary",
        "db_session_route": db_result.get("route"),
        "clip": db_result.get("clip"),
        "clip_id": db_result.get("clip_id"),
        "project_db_path": db_result.get("project_db_path"),
        "cdl": _readback_cdl_from_color_state(readback, node_index=node_index),
        "db_params_written": db_result.get("params_written"),
        "db_readback": readback,
        "verification": db_result.get("verification"),
        "steps": db_result.get("steps"),
        "note": "CDL-equivalent primary color parameters were written and verified through Project.db because DaVinci Resolve does not expose CDL readback in the scripting API.",
    }


def get_cdl(conn, clip_name: Optional[str], *, ops_module, node_index: int = 1) -> Dict[str, Any]:
    with ops_module._with_required_page(conn, "color"):
        item = ops_module.resolve_item(conn, clip_name)
        getter = getattr(item, "GetCDL", None)
        if callable(getter):
            try:
                cdl_data = getter()
                if int(node_index) != 1:
                    return {
                        "available": True,
                        "source": "api_native_get_cdl_not_node_scoped",
                        "requested_node": int(node_index),
                        "node_scoped": False,
                        "reported_node": cdl_data.get("NodeIndex") if isinstance(cdl_data, dict) else None,
                        "cdl": cdl_data if isinstance(cdl_data, dict) else {"cdl": str(cdl_data)},
                        "note": (
                            "DaVinci Resolve TimelineItem.GetCDL() is not a reliable node-scoped readback for "
                            "NodeIndex values above 1. Treat the rendered-frame proof from the preceding mutation "
                            "as the node-targeting proof."
                        ),
                    }
                return cdl_data if isinstance(cdl_data, dict) else {"cdl": str(cdl_data)}
            except Exception:
                pass
        try:
            return _project_db_read_cdl(conn, clip_name, node_index=int(node_index))
        except Exception as exc:
            return {
                "available": False,
                "cdl": None,
                "source": "api_native",
                "note": "CDL read may not be available in this DaVinci Resolve version.",
                "fallback_error": str(exc),
            }


def _parse_cdl_triplet(name: str, value: str) -> str:
    parts = [part for part in re.split(r"[\s,]+", str(value).strip()) if part]
    if len(parts) != 3:
        raise ValidationError(
            f"{name} must contain exactly 3 numeric values (R G B).",
            details={"field": name, "value": value},
        )
    try:
        f0, f1, f2 = (float(x) for x in parts)
    except ValueError as exc:
        raise ValidationError(
            f"{name} must contain numeric values.",
            details={"field": name, "value": value},
        ) from exc
    return f"{f0} {f1} {f2}"


def _cdl_payload_variants(cdl_dict: Dict[str, Any], node_index: int) -> list[Dict[str, Any]]:
    variants = [dict(cdl_dict)]
    int_node_payload = dict(cdl_dict)
    int_node_payload["NodeIndex"] = node_index
    if int_node_payload not in variants:
        variants.append(int_node_payload)
    return variants


def validate_cdl_payload(
    node: int,
    slope: Optional[str] = None,
    offset: Optional[str] = None,
    power: Optional[str] = None,
    saturation: Optional[float] = None,
) -> tuple[int, Dict[str, Any]]:
    try:
        node_index = int(node)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Node index must be a positive integer.", details={"node": node}) from exc
    if node_index < 1:
        raise ValidationError("Node index must be a positive integer.", details={"node": node})

    cdl_dict = {"NodeIndex": str(node_index)}
    if slope:
        cdl_dict["Slope"] = _parse_cdl_triplet("Slope", slope)
    if offset:
        cdl_dict["Offset"] = _parse_cdl_triplet("Offset", offset)
    if power:
        cdl_dict["Power"] = _parse_cdl_triplet("Power", power)
    if saturation is not None:
        cdl_dict["Saturation"] = str(saturation)
    return node_index, cdl_dict


def set_cdl(
    conn,
    clip_name: Optional[str],
    node: int,
    slope: Optional[str] = None,
    offset: Optional[str] = None,
    power: Optional[str] = None,
    saturation: Optional[float] = None,
    *,
    ops_module,
) -> bool:
    with ops_module._with_required_page(conn, "color"):
        item = ops_module.resolve_item(conn, clip_name)
        node_index, cdl_dict = validate_cdl_payload(node, slope, offset, power, saturation)

        attempted_payloads: list[Dict[str, Any]] = []
        last_exception: Optional[Exception] = None
        try:
            for payload in _cdl_payload_variants(cdl_dict, node_index):
                attempted_payloads.append(dict(payload))
                try:
                    result = item.SetCDL(payload)
                except Exception as exc:
                    last_exception = exc
                    continue
                if result is not False:
                    return True
            if last_exception is not None:
                raise APICallFailed(
                    f"CDL operation failed: {last_exception}",
                    details={
                        "clip": clip_name,
                        "node": node_index,
                        "cdl": cdl_dict,
                        "attempted_payloads": attempted_payloads,
                    },
                ) from last_exception
            raise APICallFailed(
                "SetCDL returned failure.",
                details={
                    "clip": clip_name,
                    "node": node_index,
                    "cdl": cdl_dict,
                    "attempted_payloads": attempted_payloads,
                },
            )
        except APICallFailed:
            raise
        except Exception as exc:
            raise APICallFailed(
                f"CDL operation failed: {exc}",
                details={
                    "clip": clip_name,
                    "node": node_index,
                    "cdl": cdl_dict,
                    "attempted_payloads": attempted_payloads,
                },
            ) from exc


def set_cdl_db(
    conn,
    clip_name: Optional[str],
    node: int,
    slope: Optional[str] = None,
    offset: Optional[str] = None,
    power: Optional[str] = None,
    saturation: Optional[float] = None,
) -> Dict[str, Any]:
    node_index, cdl_dict = validate_cdl_payload(node, slope, offset, power, saturation)
    if node_index != 1:
        raise ValidationError(
            "DB-backed CDL support is limited to node 1.",
            details={"node": node_index},
            recoverability="not_applicable",
        )
    if len(cdl_dict) == 1:
        raise ValidationError("CDL set requires at least one option: --slope/--offset/--power/--sat")

    slope_v = _parse_wheels_triplet("Slope", cdl_dict.get("Slope"))
    offset_v = _parse_wheels_triplet("Offset", cdl_dict.get("Offset"))
    power_v = _parse_wheels_triplet("Power", cdl_dict.get("Power"))
    params: Dict[str, float] = {}

    if slope_v is not None or offset_v is not None:
        slope_triplet = slope_v or (1.0, 1.0, 1.0)
        offset_triplet = offset_v or (0.0, 0.0, 0.0)
        for suffix, slope_value, offset_value in zip(("r", "g", "b"), slope_triplet, offset_triplet):
            params[f"lift_{suffix}"] = color_page_db.cdl_offset_to_lift(offset_value, slope_value)
            params[f"gain_{suffix}"] = color_page_db.cdl_slope_to_gain(slope_value, offset_value)

    if power_v is not None:
        for suffix, power_value in zip(("r", "g", "b"), power_v):
            params[f"gamma_{suffix}"] = color_page_db.cdl_power_to_gamma(power_value)

    if saturation is not None:
        params["saturation"] = float(saturation)

    db_result = color_page_db.write_color_grade(conn, clip_name=clip_name, **params)
    readback = db_result.get("readback") if isinstance(db_result.get("readback"), dict) else {}
    return {
        "clip": db_result.get("clip", clip_name),
        "node": node_index,
        "cdl_requested": cdl_dict,
        "route": "db_workaround_color_cdl_primary",
        "db_session_route": db_result.get("route"),
        "project_db_path": db_result.get("project_db_path"),
        "clip_id": db_result.get("clip_id"),
        "params_written": db_result.get("params_written"),
        "readback": readback,
        "cdl_readback": {
            "available": True,
            "source": "project_db_verified",
            "cdl": _readback_cdl_from_color_state(readback, node_index=node_index),
        },
        "verification": db_result.get("verification"),
        "steps": db_result.get("steps"),
    }


def _parse_wheels_triplet(name: str, value: Optional[str]) -> Optional[tuple[float, float, float]]:
    if value is None:
        return None
    parts = [p for p in re.split(r"[\s,]+", str(value).strip()) if p]
    if len(parts) != 3:
        raise ValidationError(
            f"{name} must contain 3 numeric values (R G B).",
            details={"field": name, "value": value},
        )
    try:
        return float(parts[0]), float(parts[1]), float(parts[2])
    except ValueError as exc:
        raise ValidationError(
            f"{name} must contain numeric values.",
            details={"field": name, "value": value},
        ) from exc


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _curves_from_wheels(
    lift: tuple[float, float, float],
    gamma: tuple[float, float, float],
    gain: tuple[float, float, float],
) -> dict[str, str]:
    def channel_points(lift_value: float, gamma_value: float, gain_value: float) -> str:
        g_safe = gamma_value if gamma_value > 0 else 0.01
        p0 = _clamp01(lift_value)
        p1 = _clamp01((0.5 ** (1.0 / g_safe)) * gain_value + lift_value)
        p2 = _clamp01(gain_value + lift_value)
        return f"0,{p0:.4f};0.5,{p1:.4f};1,{p2:.4f}"

    return {
        "red": channel_points(lift[0], gamma[0], gain[0]),
        "green": channel_points(lift[1], gamma[1], gain[1]),
        "blue": channel_points(lift[2], gamma[2], gain[2]),
    }


def validate_wheels_request(
    *,
    node: int = 1,
    lift: Optional[str] = None,
    gamma: Optional[str] = None,
    gain: Optional[str] = None,
    sat: Optional[float] = None,
    mode: str = "cdl",
    lut_output: Optional[str] = None,
    ops_module,
) -> Dict[str, Any]:
    try:
        node_index = int(node)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Node index must be a positive integer.", details={"node": node}) from exc
    if node_index < 1:
        raise ValidationError("Node index must be a positive integer.", details={"node": node})

    mode_norm = str(mode).strip().lower()
    if mode_norm not in {"cdl", "lut", "both"}:
        raise ValidationError("Mode must be one of: cdl, lut, both.", details={"mode": mode})

    lift_v = _parse_wheels_triplet("lift", lift) or (0.0, 0.0, 0.0)
    gamma_v = _parse_wheels_triplet("gamma", gamma) or (1.0, 1.0, 1.0)
    gain_v = _parse_wheels_triplet("gain", gain) or (1.0, 1.0, 1.0)

    if not any([lift, gamma, gain, sat is not None]):
        raise ValidationError("Specify at least one wheel option: lift/gamma/gain/sat.")

    normalized_lut_output: Optional[str] = None
    if mode_norm in {"lut", "both"}:
        normalized_lut_output = ops_module.lut_generator.validate_cube_output_path(
            lut_output or os.path.join(tempfile.gettempdir(), "wheels_emulation.cube")
        )

    return {
        "node": node_index,
        "mode": mode_norm,
        "lift": lift_v,
        "gamma": gamma_v,
        "gain": gain_v,
        "sat": sat,
        "lut_output": normalized_lut_output,
    }


def emulate_wheels(
    conn,
    clip_name: Optional[str],
    *,
    node: int = 1,
    lift: Optional[str] = None,
    gamma: Optional[str] = None,
    gain: Optional[str] = None,
    sat: Optional[float] = None,
    mode: str = "cdl",
    lut_output: Optional[str] = None,
    verify_project_db: bool = True,
    ops_module,
) -> Dict[str, Any]:
    request = validate_wheels_request(
        node=node,
        lift=lift,
        gamma=gamma,
        gain=gain,
        sat=sat,
        mode=mode,
        lut_output=lut_output,
        ops_module=ops_module,
    )
    node_index = request["node"]
    mode_norm = request["mode"]
    lift_v = request["lift"]
    gamma_v = request["gamma"]
    gain_v = request["gain"]

    data: Dict[str, Any] = {
        "clip": clip_name,
        "node": node_index,
        "mode": mode_norm,
        "lift": lift_v,
        "gamma": gamma_v,
        "gain": gain_v,
        "sat": sat,
    }

    if mode_norm in {"cdl", "both"}:
        data["cdl_requested"] = _cdl_map(
            node_index=node_index,
            slope=gain_v,
            offset=lift_v,
            power=gamma_v,
            saturation=sat,
        )
        if node_index == 1 and verify_project_db:
            data["cdl_readback"] = _verify_wheels_with_project_db(
                conn,
                clip_name,
                node_index=node_index,
                lift=lift_v,
                gamma=gamma_v,
                gain=gain_v,
                saturation=sat,
            )
            data["cdl_applied"] = True
            data["cdl_apply_route"] = "project_db_color_page_params"
            data["route"] = data["cdl_readback"].get("route")
            data["db_session_route"] = data["cdl_readback"].get("db_session_route")
            data["verification"] = data["cdl_readback"].get("verification")
            data["readback"] = data["cdl_readback"].get("db_readback")
            data["params_written"] = data["cdl_readback"].get("db_params_written")
            data["cdl_readback_available"] = bool(data["cdl_readback"].get("available", True) is not False)
        else:
            ops_module.set_cdl(
                conn,
                clip_name=clip_name,
                node=node_index,
                slope=f"{gain_v[0]} {gain_v[1]} {gain_v[2]}",
                offset=f"{lift_v[0]} {lift_v[1]} {lift_v[2]}",
                power=f"{gamma_v[0]} {gamma_v[1]} {gamma_v[2]}",
                saturation=sat,
            )
            data["cdl_applied"] = True
            data["cdl_apply_route"] = "api_native_set_cdl_compat"

    if mode_norm in {"lut", "both"}:
        output_path = request["lut_output"]
        curves = _curves_from_wheels(lift_v, gamma_v, gain_v)
        ops_module.lut_generator.generate_curves_lut(
            output_path=output_path,
            red=curves["red"],
            green=curves["green"],
            blue=curves["blue"],
        )
        data["lut_generated"] = output_path
        try:
            ops_module.set_lut(conn, clip_name, node_index, output_path)
        except APICallFailed as exc:
            raise APICallFailed(
                "Generated LUT file, but DaVinci Resolve did not accept it for the target node.",
                details={
                    "clip": clip_name,
                    "node": node_index,
                    "mode": mode_norm,
                    "generated_lut_path": output_path,
                    "curves": curves,
                    "resolve_error": exc.message,
                    **exc.details,
                },
            ) from exc
        data["lut_applied"] = True
        if sat is not None and sat != 1.0:
            data["lut_note"] = "Saturation component is represented in CDL; LUT emulation is RGB curves only."

    if data.get("cdl_applied") and verify_project_db and "cdl_readback" not in data:
        try:
            data["cdl_readback"] = _verify_wheels_with_project_db(
                conn,
                clip_name,
                node_index=node_index,
                lift=lift_v,
                gamma=gamma_v,
                gain=gain_v,
                saturation=sat,
            )
            if data["cdl_readback"].get("available"):
                data["cdl_apply_route"] = "api_native_seed_then_project_db_verified"
        except Exception as exc:
            fallback_error = str(exc)
            try:
                data["cdl_readback"] = ops_module.get_cdl(conn, clip_name)
            except Exception as read_exc:
                data["cdl_readback"] = {
                    "available": False,
                    "cdl": None,
                    "source": "api_native",
                    "note": "CDL readback failed after SetCDL.",
                    "error": str(read_exc),
                }
            if isinstance(data.get("cdl_readback"), dict):
                data["cdl_readback"]["project_db_verification_error"] = fallback_error
        data["cdl_readback_available"] = bool(
            isinstance(data.get("cdl_readback"), dict)
            and data["cdl_readback"].get("available", True) is not False
        )
    elif data.get("cdl_applied") and "cdl_readback" not in data:
        data["cdl_readback"] = {
            "available": False,
            "source": "api_native_set_cdl",
            "note": "Project.db verification was skipped because fresh Color Page grade creation is not implemented.",
        }
        data["cdl_readback_available"] = False

    return data
