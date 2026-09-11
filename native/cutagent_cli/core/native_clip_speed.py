"""Documented native scalar-speed readback. SetSpeed writes remain unqualified."""
import math
from ..errors import APICallFailed


def read(item):
    getter = getattr(item, "GetSpeed", None)
    value = getter() if callable(getter) else None
    if not isinstance(value, dict) or isinstance(value.get("Percentage"), bool) \
            or not isinstance(value.get("Percentage"), (int, float)) or not math.isfinite(value["Percentage"]):
        raise APICallFailed("DaVinci Resolve GetSpeed did not return a finite Percentage.")
    for key in ("PitchCorrection", "StretchKeyframesToFit", "RippleTimeline"):
        if key in value and not isinstance(value[key], bool):
            raise APICallFailed("DaVinci Resolve GetSpeed returned an invalid option.")
    return value
