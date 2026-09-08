"""Visual-truth checks for exported frames.

DaVinci Resolve renders a "Media Offline" placeholder (dark maroon background,
red warning triangle and caption) when a clip's media is unlinked. A frame or
preview export then succeeds at the API level while the pixels are garbage —
an agent that "looks" at the export would reason over the placeholder without
knowing it. This module fingerprints that placeholder so exports can report
``media_offline`` honestly.

The check decodes a tiny downscale of the exported image through the managed
ffmpeg (already a first-class external tool) and measures how much of the
frame sits in the placeholder's narrow dark-red band. Measured reference: the
placeholder averages RGB ≈ (57, 6, 6) with ~99% of pixels in-band; real
footage essentially never spends 85%+ of the frame there.
"""

from __future__ import annotations

import subprocess
from typing import Any, Optional

_SAMPLE_WIDTH = 48
_SAMPLE_HEIGHT = 27
_DARK_RED_FRACTION_THRESHOLD = 0.85
_DECODE_TIMEOUT_S = 10


def _decode_rgb_sample(image_path: str, ffmpeg_path: str) -> Optional[bytes]:
    try:
        result = subprocess.run(
            [
                ffmpeg_path,
                "-v", "error",
                "-i", image_path,
                "-vf", f"scale={_SAMPLE_WIDTH}:{_SAMPLE_HEIGHT}",
                "-frames:v", "1",
                "-f", "rawvideo",
                "-pix_fmt", "rgb24",
                "-",
            ],
            capture_output=True,
            timeout=_DECODE_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    expected = _SAMPLE_WIDTH * _SAMPLE_HEIGHT * 3
    if result.returncode != 0 or len(result.stdout) < expected:
        return None
    return result.stdout[:expected]


def detect_media_offline(image_path: str, *, ffmpeg_path: str | None = None) -> Optional[dict[str, Any]]:
    """Return a media-offline verdict for an exported frame, or None if unknown.

    The check is best-effort: any decode/tooling failure returns None rather
    than blocking the export. A returned dict always carries ``media_offline``
    and the measured ``dark_red_fraction`` so callers can surface evidence.
    """
    try:
        import numpy as np
    except Exception:
        return None

    if ffmpeg_path is None:
        try:
            from ..external_tools import resolve_tool

            ffmpeg_path = resolve_tool("ffmpeg")
        except Exception:
            return None

    raw = _decode_rgb_sample(image_path, ffmpeg_path)
    if raw is None:
        return None

    pixels = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.float64)
    red, green, blue = pixels[:, 0], pixels[:, 1], pixels[:, 2]
    in_band = (
        (red > 25)
        & (red < 140)
        & (green < 50)
        & (blue < 50)
        & (red > green * 1.7)
        & (red > blue * 1.7)
    )
    fraction = float(in_band.mean())
    return {
        "media_offline": fraction >= _DARK_RED_FRACTION_THRESHOLD,
        "dark_red_fraction": round(fraction, 3),
    }


def attach_media_offline_verdict(payload: dict[str, Any], image_path: str) -> None:
    """Annotate an export payload in place with the media-offline verdict.

    Adds ``media_offline`` (plus a warning) only when detection ran; silently
    leaves the payload untouched when the check is unavailable.
    """
    verdict = detect_media_offline(str(image_path))
    if verdict is None:
        return
    payload["media_offline"] = verdict["media_offline"]
    if verdict["media_offline"]:
        payload["media_offline_warning"] = (
            "The exported frame is the DaVinci Resolve 'Media Offline' placeholder "
            f"(dark-red coverage {verdict['dark_red_fraction']}). The source media is "
            "unlinked or unavailable — do not treat this image as the real frame. "
            "Relink the media or verify clip availability before visual judgments."
        )
