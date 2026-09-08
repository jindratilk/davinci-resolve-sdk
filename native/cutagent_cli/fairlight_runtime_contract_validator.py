"""Runtime validator for exact Fairlight input and result contracts."""

from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from .fairlight_runtime_projection_support import FairlightDescriptorError


@lru_cache(maxsize=1)
def _definitions() -> Mapping[str, Any]:
    path = (
        Path(__file__).resolve().parent
        / "public_contract"
        / "action-contracts.schema.json"
    )
    definitions = json.loads(path.read_text(encoding="utf-8")).get("$defs")
    if not isinstance(definitions, Mapping):
        raise RuntimeError("Fairlight action contract registry is unavailable")
    return definitions


def fairlight_contract_schema(action_id: str, kind: str) -> Mapping[str, Any]:
    schema = _definitions().get(f"{action_id}.{kind}")
    if not isinstance(schema, Mapping):
        raise FairlightDescriptorError(
            "VALIDATION_ERROR", f"Fairlight {kind} contract is unavailable"
        )
    return schema


def validate_fairlight_contract(
    value: Any, schema: Mapping[str, Any] | bool, path: str = "input"
) -> None:
    if schema is True:
        return
    if schema is False:
        raise FairlightDescriptorError(
            "VALIDATION_ERROR", f"{path} contract is unavailable"
        )
    if "$ref" in schema:
        prefix = "#/$defs/"
        reference = schema["$ref"]
        if not isinstance(reference, str) or not reference.startswith(prefix):
            raise RuntimeError(
                "Only local Fairlight action-contract references are supported"
            )
        validate_fairlight_contract(
            value, _definitions()[reference[len(prefix) :]], path
        )
        return
    for part in schema.get("allOf", ()):
        validate_fairlight_contract(value, part, path)
    if "if" in schema:
        try:
            validate_fairlight_contract(value, schema["if"], path)
        except FairlightDescriptorError:
            branch = schema.get("else")
        else:
            branch = schema.get("then")
        if branch is not None:
            validate_fairlight_contract(value, branch, path)
    if "oneOf" in schema:
        matches = 0
        for part in schema["oneOf"]:
            try:
                validate_fairlight_contract(value, part, path)
            except FairlightDescriptorError:
                continue
            matches += 1
        if matches != 1:
            raise FairlightDescriptorError(
                "VALIDATION_ERROR", f"{path} must match exactly one contract branch"
            )
        return
    if "anyOf" in schema:
        for part in schema["anyOf"]:
            try:
                validate_fairlight_contract(value, part, path)
                break
            except FairlightDescriptorError:
                continue
        else:
            raise FairlightDescriptorError(
                "VALIDATION_ERROR", f"{path} does not match any contract branch"
            )
        return
    if "const" in schema and value != schema["const"]:
        raise FairlightDescriptorError(
            "VALIDATION_ERROR", f"{path} violates the constant contract"
        )
    expected = schema.get("type")
    expected_types = expected if isinstance(expected, list) else [expected]
    valid = expected is None or any(
        (candidate == "null" and value is None)
        or (candidate == "object" and isinstance(value, Mapping))
        or (candidate == "array" and isinstance(value, list))
        or (candidate == "string" and isinstance(value, str))
        or (candidate == "boolean" and isinstance(value, bool))
        or (
            candidate == "integer"
            and isinstance(value, int)
            and not isinstance(value, bool)
        )
        or (
            candidate == "number"
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
        )
        for candidate in expected_types
    )
    if not valid:
        raise FairlightDescriptorError("VALIDATION_ERROR", f"{path} has the wrong type")
    if "enum" in schema and value not in schema["enum"]:
        raise FairlightDescriptorError(
            "VALIDATION_ERROR", f"{path} is outside the allowed values"
        )
    if isinstance(value, Mapping):
        properties = schema.get("properties", {})
        required = set(schema.get("required", ()))
        if not required <= set(value) or (
            schema.get("additionalProperties") is False and set(value) - set(properties)
        ):
            raise FairlightDescriptorError(
                "VALIDATION_ERROR", f"{path} does not match the closed contract"
            )
        for key, item in value.items():
            if key in properties:
                validate_fairlight_contract(item, properties[key], f"{path}.{key}")
    if isinstance(value, list):
        if len(value) < int(schema.get("minItems", 0)) or len(value) > int(
            schema.get("maxItems", 2**31)
        ):
            raise FairlightDescriptorError(
                "VALIDATION_ERROR", f"{path} has invalid cardinality"
            )
        for index, item in enumerate(value):
            validate_fairlight_contract(
                item, schema.get("items", {}), f"{path}[{index}]"
            )
        if "contains" in schema:
            matches = 0
            for item in value:
                try:
                    validate_fairlight_contract(item, schema["contains"], path)
                except FairlightDescriptorError:
                    continue
                matches += 1
            if matches < int(schema.get("minContains", 1)):
                raise FairlightDescriptorError(
                    "VALIDATION_ERROR", f"{path} lacks required matching items"
                )
    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)) or len(value) > int(
            schema.get("maxLength", 2**31)
        ):
            raise FairlightDescriptorError(
                "VALIDATION_ERROR", f"{path} has invalid length"
            )
        if (
            schema.get("pattern")
            and re.fullmatch(str(schema["pattern"]), value) is None
        ):
            raise FairlightDescriptorError(
                "VALIDATION_ERROR", f"{path} has invalid format"
            )
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            raise FairlightDescriptorError("VALIDATION_ERROR", f"{path} must be finite")
        if "minimum" in schema and value < schema["minimum"]:
            raise FairlightDescriptorError(
                "VALIDATION_ERROR", f"{path} is below the minimum"
            )
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise FairlightDescriptorError(
                "VALIDATION_ERROR", f"{path} is below the exclusive minimum"
            )
        if "maximum" in schema and value > schema["maximum"]:
            raise FairlightDescriptorError(
                "VALIDATION_ERROR", f"{path} exceeds the maximum"
            )
