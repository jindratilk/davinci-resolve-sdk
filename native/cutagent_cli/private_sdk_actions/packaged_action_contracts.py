"""Wheel-safe access to reviewed public prepared-action contracts."""

from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from importlib.resources import files
from typing import Any


@lru_cache(maxsize=1)
def _contracts() -> dict[str, Any]:
    return json.loads(
        files("cutagent_cli")
        .joinpath("public_contract", "action-contracts.schema.json")
        .read_text(encoding="utf-8")
    )["$defs"]


def reviewed_action_input_schema(action_id: str) -> dict[str, Any] | None:
    value = _contracts().get(f"{action_id}.input")
    return deepcopy(value) if isinstance(value, dict) else None


def reviewed_action_result_schema(action_id: str) -> dict[str, Any] | None:
    value = _contracts().get(f"{action_id}.result")
    return deepcopy(value) if isinstance(value, dict) else None
