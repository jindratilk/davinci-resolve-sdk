"""Packaged Color contract reader for the private prepared-action runtime.

The wheel deliberately excludes the maintainer-only ``sdk_inventory`` Python
package.  Runtime admission and result validation therefore read the generated,
reviewed public contract documents that are already mandatory wheel data.
"""

from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from functools import lru_cache
from importlib.resources import files
from typing import Any

try:
    from ..sdk_inventory.shared import InventoryValidationError
except ModuleNotFoundError:  # The maintained wheel excludes sdk_inventory source.
    class InventoryValidationError(ValueError):
        """Raised when packaged Color contract truth is inconsistent."""


_ACTION_ID_OVERRIDES = {
    "color.page.power_window_gui_set": "color.page.power_window_set",
    "color.page.primary_gui_set": "color.page.primary_extended_set",
    "color.page.qualifier_gui_hsl_set": "color.page.qualifier_hsl_set",
    "color.page.qualifier_gui_matte_set": "color.page.qualifier_matte_set",
}


@lru_cache(maxsize=1)
def _contracts() -> dict[str, Any]:
    return json.loads(
        files("cutagent_cli")
        .joinpath("public_contract", "action-contracts.schema.json")
        .read_text(encoding="utf-8")
    )["$defs"]


@lru_cache(maxsize=1)
def _actions() -> dict[str, dict[str, Any]]:
    payload = json.loads(
        files("cutagent_cli")
        .joinpath("public_contract", "sdk-inventory.json")
        .read_text(encoding="utf-8")
    )
    return {row["id"]: row for row in payload["actions"]}


def _action_command_id(command_id: str) -> str:
    return _ACTION_ID_OVERRIDES.get(command_id, command_id)


def _schema(action_id: str, suffix: str) -> dict[str, Any] | None:
    value = _contracts().get(f"{action_id}.{suffix}")
    return deepcopy(value) if isinstance(value, dict) else None


def color_action_input_schema(command_id: str) -> dict[str, Any]:
    action_id = f"cutagent.action.{_action_command_id(command_id)}"
    schema = _schema(action_id, "input")
    if schema is None:
        raise InventoryValidationError(f"Color action input schema is unavailable: {action_id}")
    return schema


def reviewed_page_input_schema(command_id: str) -> dict[str, Any] | None:
    return _schema(f"cutagent.action.{command_id}", "input")


def _metadata(*, exact: bool) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for action_id, action in _actions().items():
        if not action_id.startswith("cutagent.action.color."):
            continue
        result = _schema(action_id, "result")
        is_exact = isinstance(result, dict) and "payload" not in result.get("properties", {})
        if is_exact != exact:
            continue
        idempotency = {
            "safe_repeat": "safe_repeat",
            "replace_destination": "replace_destination",
            "requires_idempotency_key": "not_idempotent",
        }.get(action.get("idempotency_category"), "not_idempotent")
        records[action_id] = {
            "sideEffect": (
                "read"
                if action.get("operation_class") == "read"
                else "project_mutation"
            ),
            "idempotency": idempotency,
            "protectedState": action.get("protected_state_category") or "active_project_and_timeline",
        }
    return records


def color_action_metadata() -> dict[str, dict[str, Any]]:
    return _metadata(exact=True)


def normalized_color_action_metadata() -> dict[str, dict[str, Any]]:
    return _metadata(exact=False)


def all_active_color_action_ids() -> frozenset[str]:
    return frozenset(
        action_id
        for action_id in _actions()
        if action_id.startswith("cutagent.action.color.")
    )


def color_action_result_schema(action_id: str, command_id: str) -> dict[str, Any] | None:
    expected = f"cutagent.action.{_action_command_id(command_id)}"
    if action_id != expected:
        raise InventoryValidationError("Color action result identity mismatch")
    schema = _schema(action_id, "result")
    if schema is None or "payload" in schema.get("properties", {}):
        return None
    return schema


def normalized_color_action_result_schema(
    action_id: str, command_id: str
) -> dict[str, Any] | None:
    expected = f"cutagent.action.{_action_command_id(command_id)}"
    schema = _schema(action_id, "result")
    if action_id != expected or schema is None:
        return None
    return schema if "payload" in schema.get("properties", {}) else None


def reviewed_page_result_schema(
    action_id: str, command_id: str
) -> dict[str, Any] | None:
    if command_id != "page.switch" or action_id != "cutagent.action.page.switch":
        return None
    return _schema(action_id, "result")


def color_result_shared_definitions() -> dict[str, dict[str, Any]]:
    return {
        key: deepcopy(value)
        for key, value in _contracts().items()
        if key.startswith("colorResult.") and isinstance(value, dict)
    }


def _schema_error(path: str, reason: str) -> InventoryValidationError:
    return InventoryValidationError(f"Color public result {reason} at {path}")


def _validate_schema(value: Any, schema: Any, path: str) -> None:
    """Validate every assertion keyword emitted by packaged Color contracts."""
    if schema is True:
        return
    if schema is False or not isinstance(schema, dict):
        raise _schema_error(path, "is rejected by its schema")
    reference = schema.get("$ref")
    if reference is not None:
        prefix = "#/$defs/"
        if not isinstance(reference, str) or not reference.startswith(prefix):
            raise _schema_error(path, "has an unsupported schema reference")
        target = _contracts().get(reference.removeprefix(prefix))
        if target is None:
            raise _schema_error(path, "has a missing schema reference")
        _validate_schema(value, target, path)
    for branch in schema.get("allOf", ()):
        _validate_schema(value, branch, path)
    if "anyOf" in schema and not any(_schema_matches(value, branch, path) for branch in schema["anyOf"]):
        raise _schema_error(path, "does not match any allowed schema")
    if "oneOf" in schema and sum(_schema_matches(value, branch, path) for branch in schema["oneOf"]) != 1:
        raise _schema_error(path, "does not match exactly one allowed schema")
    if "not" in schema and _schema_matches(value, schema["not"], path):
        raise _schema_error(path, "matches a forbidden schema")
    if "if" in schema:
        selected = schema.get("then") if _schema_matches(value, schema["if"], path) else schema.get("else")
        if selected is not None:
            _validate_schema(value, selected, path)
    if "const" in schema and value != schema["const"]:
        raise _schema_error(path, "violates const")
    if "enum" in schema and value not in schema["enum"]:
        raise _schema_error(path, "violates enum")
    expected = schema.get("type")
    types = set(expected if isinstance(expected, list) else [expected]) if expected else set()
    valid_type = (
        not types
        or ("null" in types and value is None)
        or ("boolean" in types and isinstance(value, bool))
        or ("integer" in types and isinstance(value, int) and not isinstance(value, bool))
        or ("number" in types and isinstance(value, (int, float)) and not isinstance(value, bool))
        or ("string" in types and isinstance(value, str))
        or ("array" in types and isinstance(value, list))
        or ("object" in types and isinstance(value, dict))
    )
    if not valid_type:
        raise _schema_error(path, "has an invalid type")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 2**31):
            raise _schema_error(path, "has an invalid length")
        if "pattern" in schema and re.search(str(schema["pattern"]), value) is None:
            raise _schema_error(path, "does not match its pattern")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            raise _schema_error(path, "is not finite")
        if "minimum" in schema and value < schema["minimum"]:
            raise _schema_error(path, "is below its minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise _schema_error(path, "exceeds its maximum")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise _schema_error(path, "is below its exclusive minimum")
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            raise _schema_error(path, "exceeds its exclusive maximum")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 2**31):
            raise _schema_error(path, "has an invalid item count")
        if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True, separators=(",", ":")) for item in value}) != len(value):
            raise _schema_error(path, "has duplicate items")
        if "items" in schema:
            for index, item in enumerate(value):
                _validate_schema(item, schema["items"], f"{path}[{index}]")
        if "contains" in schema:
            count = sum(_schema_matches(item, schema["contains"], f"{path}[{index}]") for index, item in enumerate(value))
            if count < schema.get("minContains", 1) or count > schema.get("maxContains", 2**31):
                raise _schema_error(path, "has an invalid contains match count")
    if isinstance(value, dict):
        if not set(schema.get("required", ())) <= set(value):
            raise _schema_error(path, "is missing required properties")
        properties = schema.get("properties", {})
        for key, child in value.items():
            if key in properties:
                _validate_schema(child, properties[key], f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                raise _schema_error(path, "has unreviewed properties")
            elif isinstance(schema.get("additionalProperties"), dict):
                _validate_schema(child, schema["additionalProperties"], f"{path}.{key}")
        for key, dependencies in schema.get("dependentRequired", {}).items():
            if key in value and not set(dependencies) <= set(value):
                raise _schema_error(path, "is missing dependent properties")


def _schema_matches(value: Any, schema: Any, path: str) -> bool:
    try:
        _validate_schema(value, schema, path)
    except InventoryValidationError:
        return False
    return True


def validate_color_public_result(value: Any, schema: dict[str, Any]) -> None:
    _validate_schema(value, schema, "result")


def is_color_public_named_value(value: Any) -> bool:
    """Return whether a scalar is safe for normalized Color result values."""

    schema = (
        _contracts()
        .get("colorResult.read.inspection", {})
        .get("properties", {})
        .get("data", {})
        .get("properties", {})
        .get("values", {})
        .get("items", {})
        .get("properties", {})
        .get("value")
    )
    return isinstance(schema, dict) and _schema_matches(
        value, schema, "result.payload.data.values[].value"
    )


def color_result_kind(command_id: str) -> str:
    action_id = f"cutagent.action.{_action_command_id(command_id)}"
    schema = normalized_color_action_result_schema(action_id, command_id)
    ref = schema.get("properties", {}).get("payload", {}).get("$ref") if schema else None
    if not isinstance(ref, str) or not ref.startswith("#/$defs/colorResult."):
        raise InventoryValidationError("Color normalized result family is unavailable")
    return ref.rsplit(".", 1)[1]
