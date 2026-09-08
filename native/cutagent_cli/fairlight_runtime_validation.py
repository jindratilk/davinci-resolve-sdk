"""Canonical and public-boundary checks for Fairlight prepared actions."""

from __future__ import annotations

import math
from typing import Any, Mapping

from .fairlight_runtime_projection_support import FairlightDescriptorError


_PRIVATE_KEYS = frozenset(
    {
        "argv",
        "command",
        "commandId",
        "commandPath",
        "engine",
        "lowering",
        "preState",
        "recoveryPlan",
        "verificationPlan",
    }
)


def canonical_fairlight_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if abs(value) > 9_007_199_254_740_991:
            raise FairlightDescriptorError(
                "VALIDATION_ERROR", "Fairlight integer is outside the canonical range"
            )
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise FairlightDescriptorError(
                "VALIDATION_ERROR", "Fairlight number must be finite"
            )
        return 0 if value == 0 else value
    if isinstance(value, Mapping) and all(isinstance(key, str) for key in value):
        return {key: canonical_fairlight_value(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [canonical_fairlight_value(item) for item in value]
    raise FairlightDescriptorError(
        "VALIDATION_ERROR", "Fairlight data must be canonical JSON"
    )


def assert_public_fairlight_value(value: Any) -> Any:
    result = canonical_fairlight_value(value)

    def visit(current: Any) -> None:
        if isinstance(current, Mapping):
            if _PRIVATE_KEYS.intersection(current):
                raise FairlightDescriptorError(
                    "VALIDATION_ERROR",
                    "Private Fairlight data reached the public result",
                )
            for item in current.values():
                visit(item)
        elif isinstance(current, list):
            for item in current:
                visit(item)

    visit(result)
    return result
