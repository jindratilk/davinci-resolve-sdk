"""Typed time-domain parsing for record/source references."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from ..errors import InvalidTimeReference
from .timecode import parse_time_input, seconds_to_frames

TimeDomain = Literal["record", "source", "absolute"]
_INT_RE = re.compile(r"^[+-]?\d+$")


@dataclass(frozen=True)
class TimeRef:
    domain: TimeDomain
    raw: str
    fps: float
    start_frame: int = 0

    def to_frame(self) -> int:
        if self.fps <= 0:
            raise InvalidTimeReference(
                "FPS must be greater than 0.",
                details={"fps": self.fps, "domain": self.domain, "raw": self.raw},
            )
        value = self.raw.strip()
        try:
            if value.endswith("f"):
                frame = int(value[:-1].strip())
            elif _INT_RE.match(value):
                # Bare integers are interpreted as frame counts.
                frame = int(value)
            else:
                seconds = parse_time_input(value, self.fps)
                frame = seconds_to_frames(seconds, self.fps)
        except Exception as exc:
            raise InvalidTimeReference(
                f"Cannot parse time reference '{self.raw}': {exc}",
                details={"domain": self.domain, "raw": self.raw, "fps": self.fps},
            ) from exc

        if frame < 0:
            raise InvalidTimeReference(
                "Negative frame value is not allowed.",
                details={"domain": self.domain, "raw": self.raw, "frame": frame},
            )

        if self.domain == "record":
            return frame + int(self.start_frame)
        return frame


def parse_record_frame(raw: str, fps: float, start_frame: int) -> int:
    return TimeRef(domain="record", raw=raw, fps=fps, start_frame=start_frame).to_frame()


def parse_source_frame(raw: str, fps: float) -> int:
    return TimeRef(domain="source", raw=raw, fps=fps, start_frame=0).to_frame()


def parse_absolute_frame(raw: str, fps: float) -> int:
    return TimeRef(domain="absolute", raw=raw, fps=fps, start_frame=0).to_frame()
