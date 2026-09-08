"""Offline interchange preparation for independent native retime references."""

from __future__ import annotations

from fractions import Fraction
import math
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from ..errors import ValidationError
from .retime_db import TimeMapPoint
from .retime_render_proof import _source_at


def _rational(value: float) -> Fraction:
    if not math.isfinite(value):
        raise ValidationError("Reference time coordinates must be finite.")
    return Fraction(value).limit_denominator(1_000_000_000)


def _time(value: Fraction) -> str:
    if abs(value.numerator) >= 2**63 or value.denominator >= 2**63:
        raise ValidationError("Reference time coordinate exceeds the interchange range.")
    return f"{value.numerator}/{value.denominator}s"


def requested_sources(points: tuple[TimeMapPoint, ...], *, record_in: float,
                      record_fps: float, source_fps: float, duration: int) -> list[float]:
    """Evaluate pre-encoding authoring geometry, never the candidate DB payload."""
    if duration <= 0 or not points or not all(math.isfinite(v) and v > 0 for v in (record_fps, source_fps)):
        raise ValidationError("Reference preparation requires a nonempty curve and valid frame rates.")
    state = {"points": [
        {"record_frame": p.x * record_fps, "record_position": p.x * record_fps,
         "source_frame": p.y * source_fps,
         "record_frame_in": (p.x + p.x_in) * record_fps,
         "record_frame_out": (p.x + p.x_out) * record_fps,
         "source_frame_in": (p.y + p.y_in) * source_fps,
         "source_frame_out": (p.y + p.y_out) * source_fps}
        for p in points
    ]}
    if any(p.interp != 0 for p in points):
        raise ValidationError("Reference preparation cannot infer undocumented interpolation codes.")
    result = [_source_at(state, record_in + frame) for frame in range(duration)]
    if not all(math.isfinite(v) and v >= 0 for v in result):
        raise ValidationError("Reference curve must remain within finite nonnegative source coordinates.")
    return result


def reference_document(clips: list[dict[str, Any]], *, name: str, record_fps: float,
                       timeline_start: int, width: int, height: int) -> bytes:
    """Build the calibrated trim-aware FCPXML donor timeline.

    Clips contain source_path, source_fps, source_frames, record_in, start,
    duration and expected_sources. Native import/readback remains mandatory.
    """
    rate = _rational(record_fps)
    if not clips or rate <= 0 or width <= 0 or height <= 0:
        raise ValidationError("Reference timeline requires clips, positive dimensions, and a valid rate.")
    root = ET.Element("fcpxml", version="1.8")
    resources = ET.SubElement(root, "resources")
    ET.SubElement(resources, "format", id="timelineFormat", frameDuration=_time(1 / rate), width=str(width), height=str(height))
    event = ET.SubElement(ET.SubElement(root, "library"), "event", name=name)
    duration = max(int(clip["start"]) + int(clip["duration"]) for clip in clips) - timeline_start
    sequence = ET.SubElement(ET.SubElement(event, "project", name=name), "sequence", format="timelineFormat", duration=_time(duration / rate), tcStart=_time(timeline_start / rate), tcFormat="NDF")
    spine = ET.SubElement(sequence, "spine")
    previous_end = timeline_start
    for index, clip in enumerate(sorted(clips, key=lambda row: row["start"])):
        source_rate = _rational(float(clip["source_fps"]))
        source_frames = int(clip["source_frames"])
        start, duration = int(clip["start"]), int(clip["duration"])
        origin = _rational(float(clip["record_in"])) / rate
        expected = list(clip["expected_sources"])
        if source_rate <= 0 or source_frames <= 0 or origin < 0 or duration <= 0 or len(expected) != duration or start < previous_end:
            raise ValidationError("Reference clip has invalid source bounds, trim, duration, or ordering.")
        if not all(math.isfinite(value) and 0 <= value < source_frames for value in expected):
            raise ValidationError("Reference curve exceeds the source media range.")
        if origin == 0 and expected[0] != 0:
            raise ValidationError("This curve's starting source position cannot yet be verified.")
        if start > previous_end:
            ET.SubElement(spine, "gap", name="Gap", offset=_time(previous_end/rate), duration=_time((start-previous_end)/rate), start="0s")
        previous_end = start + duration
        source_format, asset = f"sourceFormat{index}", f"source{index}"
        ET.SubElement(resources, "format", id=source_format, frameDuration=_time(1/source_rate), width=str(width), height=str(height))
        ET.SubElement(resources, "asset", id=asset, name=f"reference-source-{index}", src=Path(clip["source_path"]).resolve().as_uri(), start="0s", duration=_time(source_frames/source_rate), hasVideo="1", format=source_format)
        element = ET.SubElement(spine, "asset-clip", name=f"reference-{index}", ref=asset, offset=_time(start/rate), start=_time(origin), duration=_time(duration/rate), format=source_format)
        mapping = ET.SubElement(element, "timeMap", frameSampling="floor", preservesPitch="1")
        if origin > 0:
            ET.SubElement(mapping, "timept", time="0s", value="0s", interp="linear")
        for frame, source in enumerate([*expected, expected[-1]]):
            ET.SubElement(mapping, "timept", time=_time(origin+frame/rate), value=_time(_rational(float(source))/source_rate), interp="linear")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n'+ET.tostring(root, encoding="utf-8")
