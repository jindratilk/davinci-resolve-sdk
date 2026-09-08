"""Packaged Timeline action-contract lookup for production descriptors."""

from __future__ import annotations

from typing import Any

from .._sdk_low_level_runtime import SDK_TIMELINE_PREPARED_ACTION_SCHEMAS


def timeline_action_input_schema(command_id: str) -> dict[str, Any] | None:
    schemas = SDK_TIMELINE_PREPARED_ACTION_SCHEMAS.get(f"cutagent.action.{command_id}")
    value = schemas.get("input") if isinstance(schemas, dict) else None
    return value if isinstance(value, dict) else None


def timeline_action_result_schema(
    action_id: str, _command_id: str
) -> dict[str, Any] | None:
    schemas = SDK_TIMELINE_PREPARED_ACTION_SCHEMAS.get(action_id)
    value = schemas.get("result") if isinstance(schemas, dict) else None
    return value if isinstance(value, dict) else None
