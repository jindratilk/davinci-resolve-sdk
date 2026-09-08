"""Exact persisted time-map coordinates in clip-relative seconds."""
from __future__ import annotations

import math
from typing import Any, Mapping

from ..errors import ValidationError


def curve_coordinates(state: Mapping[str, Any], *, record_start: int, source_start: float) -> dict[str, Any]:
    record_fps, source_fps = float(state["record_fps"]), float(state["source_fps"])
    if not all(math.isfinite(rate) and rate > 0 for rate in (record_fps, source_fps)):
        raise ValidationError("Exact curve readback requires valid record and source frame rates.")
    seconds = lambda value: {"unit": "seconds", "value": value}
    points = []
    if state.get("curve_kind") not in {"explicit_points", "identity"}:
        raise ValidationError("Exact curve readback is unavailable for this time-map representation.")
    if state["curve_kind"] == "explicit_points":
        native_points = state["curve_points"]
    else:
        native_points = [{"x": (point["record_position"] - record_start) / record_fps + state["native_record_origin_seconds"],
                          "y": point["source_frame"] / source_fps} for point in state["points"]]
    for point in native_points:
        values = [float(point["x"]) - state["native_record_origin_seconds"], float(point["y"]) - source_start / source_fps]
        handles = {}
        for side, suffix in (("incomingHandle", "in"), ("outgoingHandle", "out")):
            x, y = float(point.get(f"x_{suffix}", 0)), float(point.get(f"y_{suffix}", 0))
            values.extend((x, y))
            handles[side] = {"recordDelta": seconds(x), "sourceDelta": seconds(y)}
        if not all(math.isfinite(value) for value in values):
            raise ValidationError("Exact curve readback contains non-finite coordinates.")
        points.append({"recordTime": seconds(values[0]), "sourceTime": seconds(values[1]),
                       "interpolationCode": int(point.get("interp", 0)), **handles})
    return {"recordFrameRate": record_fps, "sourceFrameRate": source_fps,
            "recordStartFrame": record_start, "sourceStartFrame": source_start,
            "kind": state["curve_kind"], "points": points}
