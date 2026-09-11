"""Explicit native DCTL diagnostics, separate from ordinary clip mutations."""
from __future__ import annotations

from typing import Any

from ..errors import APICallFailed, CapabilityNegotiationFailed, ValidationError
from .resolve_api_version import at_least

MAX_SOURCE_BYTES = 65536


def validate_source(conn: Any, source: str) -> dict[str, Any]:
    if not isinstance(source, str) or not source.strip() or "\x00" in source:
        raise ValidationError("DCTL source must be nonempty text without null characters.")
    if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise ValidationError("DCTL source exceeds the 65536-byte validation limit.")
    product = conn.resolve.GetProductName()
    if not at_least(conn, 21, 1) or not isinstance(product, str) or "Studio" not in product:
        raise CapabilityNegotiationFailed("Native DCTL validation requires DaVinci Resolve Studio 21.1 or newer.")
    validator = getattr(conn.resolve, "ValidateDCTL", None)
    if not callable(validator):
        raise CapabilityNegotiationFailed("Native DCTL validation is unavailable in this DaVinci Resolve runtime.")
    diagnostics = validator(source)
    if diagnostics is not None and not isinstance(diagnostics, str):
        raise APICallFailed("DaVinci Resolve returned an invalid DCTL diagnostic result.")
    # The documented success sentinel is None, not a truthy/falsy conversion.
    return {"valid": diagnostics is None, "diagnostics": diagnostics, "validator": "davinci_resolve_native"}
