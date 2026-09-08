"""Deterministic YAML recipe parsing and execution for batch/auto-edit."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..errors import CLIError, ValidationError
from ..external_tools import probe_tool_version

try:
    import yaml
except Exception:  # pragma: no cover - exercised via runtime error path
    yaml = None


_SUPPORTED_OPS: dict[str, set[str]] = {
    "doctor": set(),
    "edit.transition.add": {"type"},
    "edit.fx.add": {"name"},
    "color.wheels.set": set(),
    "audio.duck": {"input_media", "speech_track", "music_track"},
    "clip.speed-ramp": set(),
    "edit.multicam-create": {"timeline", "angles"},
    "edit.multicam-switch": {"switches"},
}

_OPTIONAL_FIELDS: dict[str, set[str]] = {
    "doctor": set(),
    "edit.transition.add": {"duration", "scope", "clip", "at", "placement"},
    "edit.fx.add": {"clip", "template", "params", "verify"},
    "color.wheels.set": {"clip", "node", "lift", "gamma", "gain", "sat", "mode", "lut_output"},
    "audio.duck": {"threshold_db", "ratio", "attack_ms", "release_ms", "output", "replace_media"},
    "clip.speed-ramp": {
        "cut_at",
        "out_frames",
        "in_frames",
        "peak_speed",
        "curve",
        "reverse_incoming",
        "track",
        "out_start_speed",
        "out_end_speed",
        "in_start_speed",
        "in_end_speed",
        "out_start_handle",
        "out_end_handle",
        "in_start_handle",
        "in_end_handle",
        "out_ease",
        "in_ease",
        "out_start_interp",
        "out_end_interp",
        "in_start_interp",
        "in_end_interp",
        "out_point",
        "out_points",
        "in_point",
        "in_points",
        "adjustment_blur",
        "blur_frames",
        "blur_track",
        "blur_angle",
        "blur_distance",
        "blur_peak_opacity",
        "blur_name",
    },
    "edit.multicam-create": {"sync", "base_track"},
    "edit.multicam-switch": {"program_track", "angles_track_base"},
}

_FIELD_KINDS: dict[str, dict[str, str]] = {
    "edit.transition.add": {
        "type": "string",
        "duration": "time_value",
        "scope": "string_or_null",
        "clip": "string_or_null",
        "at": "time_value_or_null",
        "placement": "string_or_null",
    },
    "edit.fx.add": {
        "name": "string",
        "clip": "string_or_null",
        "template": "string_or_null",
        "params": "mapping_or_json_string",
        "verify": "bool",
    },
    "color.wheels.set": {
        "clip": "string_or_null",
        "node": "positive_int",
        "lift": "triplet_string",
        "gamma": "triplet_string",
        "gain": "triplet_string",
        "sat": "number",
        "mode": "string",
        "lut_output": "string_or_null",
    },
    "audio.duck": {
        "input_media": "string",
        "speech_track": "positive_int",
        "music_track": "positive_int",
        "threshold_db": "number",
        "ratio": "positive_number",
        "attack_ms": "non_negative_number",
        "release_ms": "non_negative_number",
        "output": "string_or_null",
        "replace_media": "string_or_null",
    },
    "clip.speed-ramp": {
        "cut_at": "time_value_or_null",
        "out_frames": "positive_int",
        "in_frames": "positive_int",
        "peak_speed": "string",
        "curve": "string",
        "reverse_incoming": "bool",
        "track": "non_negative_int",
        "out_start_speed": "string",
        "out_end_speed": "string_or_null",
        "in_start_speed": "string_or_null",
        "in_end_speed": "string",
        "out_start_handle": "string_or_null",
        "out_end_handle": "string_or_null",
        "in_start_handle": "string_or_null",
        "in_end_handle": "string_or_null",
        "out_ease": "string",
        "in_ease": "string",
        "out_start_interp": "non_negative_int",
        "out_end_interp": "non_negative_int",
        "in_start_interp": "non_negative_int",
        "in_end_interp": "non_negative_int",
        "out_point": "string_or_list",
        "out_points": "string_or_list",
        "in_point": "string_or_list",
        "in_points": "string_or_list",
        "adjustment_blur": "bool",
        "blur_frames": "positive_int",
        "blur_track": "non_negative_int",
        "blur_angle": "number",
        "blur_distance": "positive_number",
        "blur_peak_opacity": "number",
        "blur_name": "string_or_null",
    },
    "edit.multicam-create": {
        "timeline": "string",
        "angles": "string",
        "sync": "string",
        "base_track": "positive_int",
    },
    "edit.multicam-switch": {
        "switches": "string",
        "program_track": "positive_int",
        "angles_track_base": "positive_int",
    },
}


def _schema_error(message: str, *, details: dict[str, Any] | None = None) -> ValidationError:
    return ValidationError(message, details=details, recoverability="not_applicable")


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text and (text.isdigit() or (text[0] in {"-", "+"} and text[1:].isdigit())):
            try:
                return int(text)
            except ValueError:
                return None
    return None


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    if number != number or number in {float("inf"), float("-inf")}:
        return None
    return number


def _matches_kind(value: Any, kind: str) -> bool:
    if kind.endswith("_or_null") and value is None:
        return True
    if kind == "string" or kind == "string_or_null":
        return isinstance(value, str) and bool(value.strip())
    if kind == "bool":
        return isinstance(value, bool)
    if kind == "number":
        return _coerce_float(value) is not None
    if kind == "positive_number":
        number = _coerce_float(value)
        return number is not None and number > 0
    if kind == "non_negative_number":
        number = _coerce_float(value)
        return number is not None and number >= 0
    if kind == "positive_int":
        number = _coerce_int(value)
        return number is not None and number > 0
    if kind == "non_negative_int":
        number = _coerce_int(value)
        return number is not None and number >= 0
    if kind == "time_value" or kind == "time_value_or_null":
        return isinstance(value, (str, int, float)) and not isinstance(value, bool)
    if kind == "triplet_string":
        if not isinstance(value, str):
            return False
        parts = [part for part in value.replace(",", " ").split() if part]
        if len(parts) != 3:
            return False
        return all(_coerce_float(part) is not None for part in parts)
    if kind == "mapping_or_json_string":
        return isinstance(value, (dict, str))
    if kind == "string_or_list":
        return isinstance(value, str) or (isinstance(value, list) and all(isinstance(item, str) for item in value))
    return True


def _validate_arg_types(op: str, args: dict[str, Any], index: int) -> None:
    field_kinds = _FIELD_KINDS.get(op, {})
    for field, value in args.items():
        kind = field_kinds.get(field)
        if kind and not _matches_kind(value, kind):
            raise _schema_error(
                "Recipe step field has invalid type or value.",
                details={
                    "step_index": index,
                    "op": op,
                    "field": field,
                    "expected": kind,
                    "value": value,
                },
            )


def _parse_scalar(value: str) -> Any:
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none", "~"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _minimal_yaml_load(text: str) -> dict[str, Any]:
    """Parse minimal YAML subset used by deterministic recipe schema."""
    payload: dict[str, Any] = {}
    steps: list[dict[str, Any]] = []
    current_step: dict[str, Any] | None = None

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue

        if line.startswith("  - "):
            if current_step is not None:
                steps.append(current_step)
            current_step = {}
            rem = line[4:].strip()
            if rem:
                if ":" not in rem:
                    raise _schema_error("Invalid YAML step mapping.", details={"line": raw})
                key, value = rem.split(":", 1)
                current_step[key.strip()] = _parse_scalar(value.strip())
            continue

        if line.startswith("    "):
            if current_step is None:
                raise _schema_error("Invalid YAML indentation.", details={"line": raw})
            rem = line.strip()
            if ":" not in rem:
                raise _schema_error("Invalid YAML step field.", details={"line": raw})
            key, value = rem.split(":", 1)
            current_step[key.strip()] = _parse_scalar(value.strip())
            continue

        if current_step is not None:
            steps.append(current_step)
            current_step = None

        rem = line.strip()
        if ":" not in rem:
            raise _schema_error("Invalid YAML mapping line.", details={"line": raw})
        key, value = rem.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "":
            payload[key] = [] if key == "steps" else None
        else:
            payload[key] = _parse_scalar(value)

    if current_step is not None:
        steps.append(current_step)
    if steps:
        payload["steps"] = steps
    return payload


def load_recipe(path: str) -> dict[str, Any]:
    p = Path(path).expanduser()
    if not p.is_file():
        raise _schema_error("Recipe file not found.", details={"path": str(p)})
    with p.open("r", encoding="utf-8") as f:
        text = f.read()

    if yaml is None:
        payload = _minimal_yaml_load(text)
    else:
        try:
            payload = yaml.safe_load(text)
        except Exception as exc:
            raise _schema_error("Invalid recipe YAML.", details={"path": str(p), "error": str(exc)}) from exc

    if not isinstance(payload, dict):
        raise _schema_error("Recipe root must be a YAML object.", details={"path": str(p)})
    return payload


def _validate_step(step: dict[str, Any], index: int) -> dict[str, Any]:
    if not isinstance(step, dict):
        raise _schema_error("Recipe step must be an object.", details={"step_index": index})

    op = step.get("op")
    if not isinstance(op, str) or not op.strip():
        raise _schema_error("Recipe step requires non-empty 'op'.", details={"step_index": index})
    op = op.strip()
    if op not in _SUPPORTED_OPS:
        raise _schema_error(
            "Unsupported recipe operation.",
            details={"step_index": index, "op": op, "supported": sorted(_SUPPORTED_OPS.keys())},
        )

    args = {k: v for k, v in step.items() if k != "op"}
    required = _SUPPORTED_OPS[op]
    allowed = required | _OPTIONAL_FIELDS.get(op, set())
    unknown = sorted([k for k in args if k not in allowed])
    if unknown:
        raise _schema_error(
            "Recipe step has unsupported fields.",
            details={"step_index": index, "op": op, "unsupported": unknown, "allowed": sorted(allowed)},
        )

    missing = sorted([k for k in required if k not in args])
    if missing:
        raise _schema_error(
            "Recipe step is missing required fields.",
            details={"step_index": index, "op": op, "missing": missing},
        )

    if op == "color.wheels.set":
        if not any(k in args for k in ("lift", "gamma", "gain", "sat")):
            raise _schema_error(
                "color.wheels.set requires at least one of lift/gamma/gain/sat.",
                details={"step_index": index},
            )

    _validate_arg_types(op, args, index)
    return {"op": op, "args": args}


def validate_recipe_data(payload: dict[str, Any]) -> dict[str, Any]:
    version = payload.get("version")
    if version != 1:
        raise _schema_error("Recipe version must be 1.", details={"version": version})

    steps = payload.get("steps")
    if not isinstance(steps, list) or not steps:
        raise _schema_error("Recipe requires non-empty 'steps' list.", details={"steps": steps})

    normalized_steps = [_validate_step(step, idx) for idx, step in enumerate(steps)]
    return {
        "version": 1,
        "steps": normalized_steps,
        "step_count": len(normalized_steps),
        "supported_ops": sorted(_SUPPORTED_OPS.keys()),
    }


def validate_recipe_file(path: str) -> dict[str, Any]:
    payload = load_recipe(path)
    normalized = validate_recipe_data(payload)
    normalized["path"] = str(Path(path).expanduser())
    return normalized


def doctor_snapshot() -> dict[str, Any]:
    """Minimal doctor checks for recipe preflight."""
    checks = []

    # DaVinci Resolve runtime check
    try:
        from ..connection import get_connection

        conn = get_connection(require_project=False)
        checks.append(
            {
                "check": "resolve_connection",
                "ok": True,
                "details": {
                    "project": conn.project.GetName() if conn.project else None,
                    "timeline": conn.timeline.GetName() if conn.timeline else None,
                },
            }
        )
    except Exception as exc:
        checks.append({"check": "resolve_connection", "ok": False, "details": {"error": str(exc)}})

    for tool in ("ffmpeg", "ffprobe"):
        try:
            checks.append({"check": f"{tool}_binary", "ok": True, "details": probe_tool_version(tool)})
        except Exception as exc:
            checks.append({"check": f"{tool}_binary", "ok": False, "details": {"error": str(exc)}})

    return {"ok": all(c["ok"] for c in checks), "checks": checks}


def _error_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, CLIError):
        return {
            "code": exc.code,
            "message": str(exc),
            "details": exc.details,
        }
    return {
        "code": "INTERNAL_ERROR",
        "message": str(exc),
        "details": {"type": exc.__class__.__name__},
    }


def run_recipe_data(
    normalized: dict[str, Any],
    *,
    dispatcher: Callable[[str, dict[str, Any]], Any],
    fail_fast: bool = True,
    run_doctor: bool = False,
) -> dict[str, Any]:
    results = []

    doctor_result = None
    if run_doctor:
        doctor_result = doctor_snapshot()
        if fail_fast and doctor_result and not doctor_result.get("ok", False):
            return {
                "ok": False,
                "doctor": doctor_result,
                "steps": results,
                "failed_step": None,
            }

    failed_step = None
    for idx, step in enumerate(normalized["steps"]):
        op = step["op"]
        args = dict(step.get("args", {}))
        try:
            data = dispatcher(op, args)
            results.append({"index": idx, "op": op, "ok": True, "data": data, "error": None})
        except Exception as exc:  # noqa: BLE001
            err = _error_payload(exc)
            results.append({"index": idx, "op": op, "ok": False, "data": None, "error": err})
            failed_step = idx
            if fail_fast:
                break

    return {
        "ok": failed_step is None,
        "doctor": doctor_result,
        "failed_step": failed_step,
        "step_count": len(normalized["steps"]),
        "steps": results,
    }
