"""Api helpers for podcast audio activity planning."""

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
from .common import *
from .parsing import *
from .levels import *
from .normalization import *
from .windows import *
from .plan_v1 import *
from .plan_v2 import *


def build_audio_activity_plan(
    *,
    audio_sources: list[dict[str, Any]],
    audio_angle_map: dict[str, str],
    audio_targets: dict[str, dict[str, Any]] | None,
    audio_sync: dict[str, Any] | None,
    switching: dict[str, Any],
    overlap: dict[str, Any] | None,
    angle_map: dict[str, str],
    reference_audio_by_angle: dict[str, str] | None = None,
    max_timeline_ms: int | None = None,
    fps: float,
) -> dict[str, Any]:
    normalized_sources = _normalize_audio_sources(audio_sources)
    normalized_angle_map = _normalize_audio_angle_map(audio_angle_map)
    normalized_targets = _normalize_audio_targets(audio_targets)
    _validate_known_angles(audio_angle_map=normalized_angle_map, audio_targets=normalized_targets, angle_map=angle_map)
    settings = normalize_switching_settings(switching)
    normalized_sources, per_source = _prepare_audio_activity_sources(
        audio_sources=normalized_sources,
        audio_sync=audio_sync,
        reference_audio_by_angle=reference_audio_by_angle or angle_map,
        fps=fps,
        window_ms=int(settings["analysis_window_ms"]),
    )
    all_sources_have_direct_angles = all(str(source["id"]) in normalized_angle_map for source in normalized_sources)
    if int(settings["switch_delay_ms"]) > 0 and not normalized_targets and normalized_angle_map and all_sources_have_direct_angles:
        return _build_audio_activity_plan_v2_from_precomputed(
            normalized_sources=normalized_sources,
            normalized_angle_map=normalized_angle_map,
            per_source=per_source,
            switching=settings,
            overlap=overlap,
            angle_map=angle_map,
            max_timeline_ms=max_timeline_ms,
            fps=fps,
        )
    return _build_audio_activity_plan_from_precomputed(
        normalized_sources=normalized_sources,
        normalized_angle_map=normalized_angle_map,
        normalized_targets=normalized_targets,
        per_source=per_source,
        switching=settings,
        overlap=overlap,
        angle_map=angle_map,
        max_timeline_ms=max_timeline_ms,
        fps=fps,
    )


__all__ = (
    'build_audio_activity_plan',
)
