"""Timecode / frames / seconds conversion utilities."""

from __future__ import annotations

import re

from ..errors import ValidationError
from .frame_math import format_frame_timecode, parse_frame_quantity


def timecode_to_seconds(tc: str, fps: float = 25.0) -> float:
    """Convert HH:MM:SS:FF or HH:MM:SS;FF timecode to seconds."""
    tc = tc.strip()
    # Support ; for drop-frame
    parts = re.split(r"[:;]", tc)
    if len(parts) == 4:
        return parse_frame_quantity(tc, fps, field="timecode", allow_signed=False) / fps
    if len(parts) == 3:
        h, m, s = (int(p) for p in parts)
        return float(h * 3600 + m * 60 + s)
    raise ValidationError(f"Invalid timecode format: {tc}", details={"value": tc, "fps": fps})


def seconds_to_timecode(seconds: float, fps: float = 25.0) -> str:
    """Convert seconds to HH:MM:SS:FF timecode."""
    if seconds < 0:
        seconds = 0
    total_frames = round(seconds * fps)
    return format_frame_timecode(total_frames, fps)


def seconds_to_frames(seconds: float, fps: float = 25.0) -> int:
    """Convert seconds to frame count."""
    return round(seconds * fps)


def frames_to_seconds(frames: int, fps: float = 25.0) -> float:
    """Convert frame count to seconds."""
    return frames / fps


def frames_to_timecode(frames: int, fps: float = 25.0) -> str:
    """Convert frame count to timecode."""
    return seconds_to_timecode(frames_to_seconds(frames, fps), fps)


def parse_time_input(value: str, fps: float = 25.0) -> float:
    """
    Parse flexible time input to seconds.
    
    Formats:
    - "00:01:30:00" — timecode
    - "90.5s" or "90.5" — seconds
    - "2250f" — frames
    """
    value = value.strip()
    if value.endswith("f"):
        return frames_to_seconds(int(value[:-1]), fps)
    if value.endswith("s"):
        return float(value[:-1])
    if ":" in value:
        return timecode_to_seconds(value, fps)
    # Default: try as seconds
    try:
        return float(value)
    except ValueError:
        raise ValidationError(f"Cannot parse time value: {value}", details={"value": value, "fps": fps})


def format_duration(seconds: float) -> str:
    """Format duration as human-readable string."""
    if seconds < 0:
        return "0:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
