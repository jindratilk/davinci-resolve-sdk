"""Common helpers for podcast audio activity planning."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import statistics
import struct
import subprocess
import tempfile
from typing import Any, Iterable
import wave

from ...errors import APICallFailed, ValidationError
from ...external_tools import resolve_tool
from .. import waveform_sync
from .._podcast_multicam.audio_activity_v2 import io as audio_activity_v2_io
from .._podcast_multicam.audio_activity_v2 import plan as audio_activity_v2_plan
from .._podcast_multicam.transcript import normalize_scribe_v2_transcript


@dataclass(frozen=True)
class AudioWindowSample:
    start_ms: int
    end_ms: int
    rms_db: float


REQUIRED_SWITCHING_KEYS = (
    "analysis_window_ms",
    "activity_floor_db",
    "activity_margin_db",
    "dominance_margin_db",
    "min_switch_ms",
    "switch_delay_ms",
)


__all__ = (
    'AudioWindowSample',
    'REQUIRED_SWITCHING_KEYS',
)
