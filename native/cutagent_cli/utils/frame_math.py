"""Exact frame-quantity parsing for edit mutations.

This module intentionally avoids binary floating-point multiplication.  Edit
commands use the returned integer frames as their mutation contract, so a
half-frame input must round deterministically and an SMPTE timecode must use
the nominal timecode rate rather than drift with a fractional playback rate.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import math
import re

from ..errors import ValidationError


_FRAME_RE = re.compile(r"^(?P<sign>[+-]?)(?P<frames>\d+)f$")
_SECONDS_RE = re.compile(r"^(?P<sign>[+-]?)(?P<seconds>(?:\d+(?:\.\d*)?|\.\d+))(?:s)?$")
_TIMECODE_RE = re.compile(
    r"^(?P<sign>[+-]?)(?P<hours>\d{1,3}):(?P<minutes>\d{2}):(?P<seconds>\d{2})(?P<separator>[:;])(?P<frames>\d{2})$"
)
_DROP_FRAME_RATES = {
    Decimal("29.97"): 2,
    Decimal("30000") / Decimal("1001"): 2,
    Decimal("59.94"): 4,
    Decimal("60000") / Decimal("1001"): 4,
}


def _validated_rate(fps: float, *, field: str, raw: str) -> tuple[Decimal, int]:
    try:
        numeric = float(fps)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Timeline frame rate must be numeric.", details={field: raw, "fps": fps}) from exc
    if not math.isfinite(numeric) or numeric <= 0:
        raise ValidationError("Timeline frame rate must be finite and greater than 0.", details={field: raw, "fps": fps})
    rate = Decimal(str(fps))
    nominal = int(rate.to_integral_value(rounding=ROUND_HALF_UP))
    if nominal <= 0:
        raise ValidationError("Timeline frame rate has no valid nominal timecode rate.", details={field: raw, "fps": fps})
    return rate, nominal


def format_frame_timecode(frames: int, fps: float, *, drop_frame: bool = False) -> str:
    """Format an exact frame position using nominal NDF or standard DF labels."""
    if type(frames) is not int or frames < 0:
        raise ValidationError("Timecode requires a nonnegative integer frame position.")
    rate, nominal = _validated_rate(fps, field="frames", raw=str(frames))
    labels = frames
    if drop_frame:
        drop = next((count for supported, count in _DROP_FRAME_RATES.items()
                     if abs(rate - supported) <= Decimal("0.000001")), 0)
        if not drop:
            raise ValidationError("Drop-frame timecode is only supported for 29.97 or 59.94 timelines.")
        per_ten_minutes = nominal * 600 - drop * 9
        blocks, remainder = divmod(frames, per_ten_minutes)
        labels += drop * 9 * blocks
        if remainder >= drop:
            labels += drop * ((remainder - drop) // (nominal * 60 - drop))
    seconds, frame = divmod(labels, nominal)
    minutes, second = divmod(seconds, 60)
    hour, minute = divmod(minutes, 60)
    separator = ";" if drop_frame else ":"
    return f"{hour:02d}:{minute:02d}:{second:02d}{separator}{frame:02d}"


def parse_frame_quantity(
    raw: str,
    fps: float,
    *,
    field: str,
    allow_signed: bool,
    bare_integers_are_frames: bool = False,
) -> int:
    """Parse a frame count, seconds value, or SMPTE timecode exactly.

    Frame literals (``12f``) and source-position bare integers are exact.
    Seconds use decimal half-up rounding. Non-drop timecode uses the nominal
    integer timecode rate; ``;`` drop-frame syntax is accepted only for the
    standard 29.97/59.94 families and rejects dropped frame labels.
    """

    value = str(raw or "").strip()
    if not value:
        raise ValidationError("Time value must not be empty.", details={field: raw, "fps": fps})
    rate, nominal = _validated_rate(fps, field=field, raw=value)

    frame_match = _FRAME_RE.fullmatch(value)
    if frame_match:
        sign = -1 if frame_match.group("sign") == "-" else 1
        frames = sign * int(frame_match.group("frames"))
    else:
        timecode_match = _TIMECODE_RE.fullmatch(value)
        if timecode_match:
            sign = -1 if timecode_match.group("sign") == "-" else 1
            hours = int(timecode_match.group("hours"))
            minutes = int(timecode_match.group("minutes"))
            seconds = int(timecode_match.group("seconds"))
            frame_number = int(timecode_match.group("frames"))
            if minutes >= 60 or seconds >= 60 or frame_number >= nominal:
                raise ValidationError(
                    "Timecode component is outside the timeline rate.",
                    details={field: raw, "fps": fps, "nominal_fps": nominal},
                )
            total_minutes = hours * 60 + minutes
            frames = ((hours * 3600 + minutes * 60 + seconds) * nominal) + frame_number
            if timecode_match.group("separator") == ";":
                drop_frames = next(
                    (
                        count
                        for supported_rate, count in _DROP_FRAME_RATES.items()
                        if abs(rate - supported_rate) <= Decimal("0.000001")
                    ),
                    0,
                )
                if drop_frames == 0:
                    raise ValidationError(
                        "Drop-frame timecode is only supported for 29.97 or 59.94 timelines.",
                        details={field: raw, "fps": fps},
                    )
                if seconds == 0 and minutes % 10 != 0 and frame_number < drop_frames:
                    raise ValidationError(
                        "Timecode names a frame omitted by the drop-frame numbering scheme.",
                        details={field: raw, "fps": fps, "dropped_frame_count": drop_frames},
                    )
                frames -= drop_frames * (total_minutes - total_minutes // 10)
            frames *= sign
        else:
            seconds_match = _SECONDS_RE.fullmatch(value)
            if not seconds_match:
                raise ValidationError("Cannot parse time value.", details={field: raw, "fps": fps})
            sign = -1 if seconds_match.group("sign") == "-" else 1
            number = seconds_match.group("seconds")
            if bare_integers_are_frames and "." not in number and not value.lower().endswith("s"):
                frames = sign * int(number)
            else:
                try:
                    seconds_value = Decimal(number)
                except InvalidOperation as exc:  # pragma: no cover - guarded by regex
                    raise ValidationError("Cannot parse seconds value.", details={field: raw, "fps": fps}) from exc
                frames = sign * int((seconds_value * rate).to_integral_value(rounding=ROUND_HALF_UP))

    if not allow_signed and frames < 0:
        raise ValidationError("Negative frame value is not allowed.", details={field: raw, "fps": fps, "frames": frames})
    return int(frames)
