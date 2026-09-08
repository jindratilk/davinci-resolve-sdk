"""Native time-map axes, including fractional DB positions and NTSC labels."""
from __future__ import annotations

import math
import re
import struct
from typing import Any

from ..errors import ValidationError


def native_frame_position(value: Any) -> float:
    """Decode the integer prefix plus little-endian binary64 fractional part.

    Native Studio 21 captures include ``24|a09999999999e93f`` for a 24.8
    record-frame trim (source frame 31 at the 24/30 rate ratio). The suffix
    must not be discarded, including for near-integer native positions.
    """
    try:
        if isinstance(value, bool) or value is None:
            raise ValueError("missing frame position")
        if isinstance(value, str) and "|" in value:
            match = re.fullmatch(r"([+-]?\d+)\|([0-9a-fA-F]{16})", value.strip())
            if match is None:
                raise ValueError("malformed compound frame position")
            fraction = struct.unpack("<d", bytes.fromhex(match[2]))[0]
            if not math.isfinite(fraction) or not -1 < fraction < 1:
                raise ValueError("invalid fractional frame component")
            number = int(match[1]) + fraction
        else:
            number = float(value)
        if not math.isfinite(number) or number < 0:
            raise ValueError("invalid frame position")
        return number
    except (ValueError, TypeError, OverflowError, struct.error) as exc:
        raise ValidationError("Native time-map readback contains an invalid record origin.") from exc


def exact_native_rate(rate: float) -> float:
    """Expand only the known rounded DaVinci Resolve NTSC setting labels."""
    number = float(rate)
    if not math.isfinite(number) or number <= 0:
        raise ValidationError("Native time-map coordinates require a finite positive frame rate.")
    for label, numerator in ((23.976, 24000), (29.97, 30000), (47.952, 48000),
                             (59.94, 60000), (95.904, 96000), (119.88, 120000)):
        if abs(number - label) <= 1e-9:
            return numerator / 1001
    return number
