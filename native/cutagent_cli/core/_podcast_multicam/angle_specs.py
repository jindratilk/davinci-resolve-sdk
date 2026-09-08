from __future__ import annotations

from ...errors import ValidationError


def parse_angle_spec(angles: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_entry in str(angles).split(","):
        entry = raw_entry.strip()
        if not entry:
            continue
        if "=" not in entry:
            raise ValidationError(
                "Angle spec must use angle=clip pairs.",
                details={"entry": entry, "angles": angles},
            )
        angle, clip_name = [part.strip() for part in entry.split("=", 1)]
        if not angle or not clip_name:
            raise ValidationError(
                "Angle spec must use non-empty angle=clip pairs.",
                details={"entry": entry, "angles": angles},
            )
        parsed[angle] = clip_name
    if not parsed:
        raise ValidationError("At least one multicam angle is required.", details={"angles": angles})
    return parsed
