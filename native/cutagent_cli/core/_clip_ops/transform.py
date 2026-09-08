from __future__ import annotations

from typing import Any

from ...errors import ValidationError

_DYNAMIC_ZOOM_EASE_LABELS = {
    0: "linear",
    1: "in",
    2: "out",
    3: "inout",
}

_DYNAMIC_ZOOM_EASE_CONSTANTS = {
    "linear": "DYNAMIC_ZOOM_EASE_LINEAR",
    "in": "DYNAMIC_ZOOM_EASE_IN",
    "out": "DYNAMIC_ZOOM_EASE_OUT",
    "inout": "DYNAMIC_ZOOM_EASE_IN_AND_OUT",
}


def _get_dynamic_zoom_ease_constant(conn, ease: str) -> int:
    normalized = str(ease).strip().lower()
    if normalized not in _DYNAMIC_ZOOM_EASE_CONSTANTS:
        raise ValidationError(
            "Dynamic zoom ease must be one of: linear, in, out, inout.",
            details={"ease": ease},
        )
    constant_name = _DYNAMIC_ZOOM_EASE_CONSTANTS[normalized]
    fallback = {
        "linear": 0,
        "in": 1,
        "out": 2,
        "inout": 3,
    }[normalized]
    resolve_obj = getattr(conn, "resolve", None)
    return int(getattr(resolve_obj, constant_name, fallback))


def _serialize_dynamic_zoom_ease(raw_value: Any) -> Any:
    try:
        numeric = int(raw_value)
    except (TypeError, ValueError):
        return raw_value
    return _DYNAMIC_ZOOM_EASE_LABELS.get(numeric, numeric)


def _parse_zoom_tuple(raw: str) -> tuple[float, float, float]:
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 3:
        raise ValidationError("Zoom point must be x,y,zoom.", details={"value": raw})
    try:
        return float(parts[0]), float(parts[1]), float(parts[2])
    except ValueError as exc:
        raise ValidationError("Zoom point must contain numeric x,y,zoom values.", details={"value": raw}) from exc
