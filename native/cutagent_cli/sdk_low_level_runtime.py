"""Private lowering for the authenticated SDK read carrier.

This module is packaged with CutAgent CLI, never with the public TypeScript SDK
or Bridge bundle.  The generated registry is the only descriptor-to-command
mapping accepted here.
"""

from __future__ import annotations

import json
from typing import Any

from ._sdk_low_level_runtime import SDK_LOW_LEVEL_RUNTIME_BINDINGS
from .errors import ValidationError


_BINDINGS = {binding["actionId"]: binding for binding in SDK_LOW_LEVEL_RUNTIME_BINDINGS}


def _validation_error(message: str, *, field: str | None = None) -> ValidationError:
    details = {"field": field} if field is not None else {}
    return ValidationError(message, details=details)


def _validate_value(value: Any, schema: dict[str, Any], field: str) -> None:
    declared_type = schema.get("type")
    if "enum" in schema:
        if value not in schema["enum"]:
            raise _validation_error("Typed low-level action input is outside the allowed values.", field=field)
        if declared_type is None:
            return
    allowed_types = declared_type if isinstance(declared_type, list) else [declared_type]
    if value is None and "null" in allowed_types:
        return
    if "boolean" in allowed_types and isinstance(value, bool):
        pass
    elif "integer" in allowed_types and isinstance(value, int) and not isinstance(value, bool):
        pass
    elif "string" in allowed_types and isinstance(value, str):
        pass
    else:
        raise _validation_error("Typed low-level action input has an invalid value type.", field=field)

    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)):
            raise _validation_error("Typed low-level action input is too short.", field=field)
        maximum_length = schema.get("maxLength")
        if maximum_length is not None and len(value) > int(maximum_length):
            raise _validation_error("Typed low-level action input is too long.", field=field)
    if isinstance(value, int) and not isinstance(value, bool):
        if schema.get("minimum") is not None and value < schema["minimum"]:
            raise _validation_error("Typed low-level action input is below its minimum.", field=field)
        if schema.get("maximum") is not None and value > schema["maximum"]:
            raise _validation_error("Typed low-level action input exceeds its maximum.", field=field)


def _validate_input(binding: dict[str, Any], value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _validation_error("Typed low-level action input must be an object.")
    schema = binding["inputSchema"]
    properties = schema.get("properties", {})
    unknown = sorted(set(value) - set(properties))
    if unknown:
        raise _validation_error("Typed low-level action input contains an unknown field.", field=unknown[0])
    missing = sorted(set(schema.get("required", [])) - set(value))
    if missing:
        raise _validation_error("Typed low-level action input is missing a required field.", field=missing[0])
    for field, field_value in value.items():
        _validate_value(field_value, properties[field], field)
    return value


def _serialize(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    return str(value)


def lower_read_action(action_id: str, input_json: str) -> list[str]:
    """Validate a public descriptor and return its private exact CLI argv."""
    binding = _BINDINGS.get(action_id)
    if binding is None or binding.get("operationClass") != "read":
        raise ValidationError(
            "The requested action has no authenticated read-only lowering.",
            details={"action_id": action_id},
        )
    try:
        raw_input = json.loads(input_json)
    except (TypeError, ValueError) as exc:
        raise _validation_error("Typed low-level action input must be valid JSON.") from exc
    action_input = _validate_input(binding, raw_input)
    argv = list(binding["path"])
    for parameter in binding["parameters"]:
        key = parameter["key"]
        if key not in action_input or action_input[key] is None:
            continue
        value = action_input[key]
        if parameter["kind"] == "argument":
            argv.append(_serialize(value))
            continue
        cli_names = parameter["cliNames"]
        if not cli_names:
            raise RuntimeError("Generated SDK read lowering omitted an option name.")
        if isinstance(value, bool):
            declaration = cli_names[0]
            if "/" in declaration:
                positive, negative = declaration.split("/", 1)
                argv.append(positive if value else negative)
            elif value:
                argv.append(declaration)
            continue
        argv.extend((cli_names[0], _serialize(value)))
    return argv


def read_action_ids() -> tuple[str, ...]:
    return tuple(sorted(_BINDINGS))
