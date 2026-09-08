"""Render offset/drift-conformed audio media (fallback path for sample-accurate sync).

The primary sub-frame mechanisms are pure placement math (fractional DaVinci Resolve
placement, shared-clock grouping, drift-aware slices) which write no media.
Conform is the fallback: it bakes a constant sub-frame shift and/or a clock
drift correction into a derived WAV so the file placed at an integer frame is
sample-accurate.

Hard safety rules (large media must never be duplicated by surprise):
- per-file output size cap,
- free-space requirement on the destination volume,
- cumulative per-run derived-media budget,
- below-threshold residuals skip rendering entirely.

The shift is always a constant time translation of the whole file (head trim or
silence prepend) — never a per-segment retime — so integer-frame source in/out
values computed against the original remain valid against the conformed file.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from ..errors import APICallFailed, ValidationError
from ..external_tools import resolve_tool
from .audio_ops import _probe_audio_streams

DERIVED_DIR_NAME = ".cutagent-derived"
RESIDUAL_SKIP_MS = 2.0
DRIFT_SKIP_SPAN_MS = 5.0
PER_FILE_LIMIT_GB = 8.0
FREE_SPACE_FACTOR = 4.0
DEFAULT_RUN_BUDGET_GB = 20.0

_GB = 1024.0 ** 3


class ConformRunBudget:
    """Tracks cumulative derived-media bytes for one CLI invocation."""

    def __init__(self, max_gb: float = DEFAULT_RUN_BUDGET_GB):
        self.max_bytes = float(max_gb) * _GB
        self.spent_bytes = 0.0

    def can_spend(self, size_bytes: float) -> bool:
        return self.spent_bytes + size_bytes <= self.max_bytes

    def spend(self, size_bytes: float) -> None:
        self.spent_bytes += size_bytes


def _codec_for_stream(stream: Dict[str, Any]) -> str:
    codec = str(stream.get("codec_name") or "")
    if codec.startswith("pcm_"):
        return codec
    bits = 0
    try:
        bits = int(stream.get("bits_per_sample") or 0)
    except (TypeError, ValueError):
        bits = 0
    if bits >= 32:
        return "pcm_f32le"
    if bits == 24:
        return "pcm_s24le"
    return "pcm_s16le"


def build_conform_filter(
    *,
    residual_seconds: float,
    drift_ppm: float,
    sample_rate: int,
) -> Optional[str]:
    """Construct the sample-exact ffmpeg filter graph for a conform render.

    residual_seconds is the leftover shift to bake in: positive means the audio
    must start later (prepend silence), negative means it must start earlier
    (trim the head). drift_ppm stretches the clock via asetrate + aresample —
    at single-digit ppm the pitch change is far below audibility.
    """
    stages = []
    shift_samples = int(round(abs(residual_seconds) * sample_rate))
    if shift_samples > 0:
        if residual_seconds < 0:
            stages.append(f"atrim=start_sample={shift_samples}")
            stages.append("asetpts=PTS-STARTPTS")
        else:
            # adelay only has millisecond resolution; aevalsrc+concat in a
            # filter graph complicates channel layouts. apad-at-head via
            # areverse is wasteful. The sample-exact and layout-safe choice is
            # adelay with sample units, supported via the "S" suffix.
            stages.append(f"adelay={shift_samples}S:all=1")
    if abs(drift_ppm) > 1e-3:
        ratio = 1.0 + drift_ppm * 1e-6
        stages.append(f"asetrate={sample_rate}*{ratio:.9f}")
        stages.append(f"aresample={sample_rate}")
    if not stages:
        return None
    return ",".join(stages)


def conform_output_path(
    source_path: str,
    *,
    residual_seconds: float,
    drift_ppm: float,
    derived_media_dir: Optional[str] = None,
) -> Path:
    source = Path(source_path)
    try:
        stat = os.stat(os.path.realpath(source_path))
        identity = f"{os.path.realpath(source_path)}|{stat.st_mtime}|{stat.st_size}"
    except OSError:
        identity = str(source_path)
    digest_input = f"{identity}|{round(residual_seconds, 9)}|{round(drift_ppm, 4)}"
    digest = hashlib.sha1(digest_input.encode("utf-8")).hexdigest()[:12]
    directory = Path(derived_media_dir) if derived_media_dir else source.parent / DERIVED_DIR_NAME
    return directory / f"{source.stem}.cutagent-conform.{digest}.wav"


def conform_audio(
    source_path: str,
    *,
    residual_seconds: float,
    drift_ppm: float = 0.0,
    drift_span_ms: float = 0.0,
    derived_media_dir: Optional[str] = None,
    run_budget: Optional[ConformRunBudget] = None,
    per_file_limit_gb: float = PER_FILE_LIMIT_GB,
    force: bool = False,
) -> Dict[str, Any]:
    """Render (or reuse) a conformed WAV. Refusals are soft: callers fall back
    to placement-math mode and surface the reason."""
    source = Path(source_path)
    if not source.is_file():
        raise ValidationError(
            "Conform source file not found.",
            details={"source_path": source_path},
        )

    skip_shift = abs(residual_seconds) * 1000.0 < RESIDUAL_SKIP_MS
    skip_drift = abs(drift_span_ms) < DRIFT_SKIP_SPAN_MS
    if skip_drift:
        drift_ppm = 0.0
    if skip_shift:
        residual_seconds = 0.0
    if not force and skip_shift and skip_drift:
        return {
            "conformed": False,
            "path": str(source_path),
            "reason": "below_threshold",
            "cache_hit": False,
        }

    streams = _probe_audio_streams(str(source_path))
    if not streams:
        raise ValidationError(
            "Conform source has no audio stream.",
            details={"source_path": source_path},
        )
    stream = streams[0]
    try:
        sample_rate = int(stream.get("sample_rate") or 0)
    except (TypeError, ValueError):
        sample_rate = 0
    if sample_rate <= 0:
        raise ValidationError(
            "Conform source has no readable sample rate.",
            details={"source_path": source_path},
        )

    filter_graph = build_conform_filter(
        residual_seconds=residual_seconds, drift_ppm=drift_ppm, sample_rate=sample_rate
    )
    if filter_graph is None:
        return {
            "conformed": False,
            "path": str(source_path),
            "reason": "nothing_to_apply",
            "cache_hit": False,
        }

    output_path = conform_output_path(
        source_path,
        residual_seconds=residual_seconds,
        drift_ppm=drift_ppm,
        derived_media_dir=derived_media_dir,
    )
    if output_path.is_file() and output_path.stat().st_size > 0:
        return {
            "conformed": True,
            "path": str(output_path),
            "filter_graph": filter_graph,
            "residual_applied_ms": residual_seconds * 1000.0,
            "drift_applied_ppm": drift_ppm,
            "reason": "cache",
            "cache_hit": True,
        }

    estimated_bytes = float(source.stat().st_size)
    if estimated_bytes > per_file_limit_gb * _GB:
        return {
            "conformed": False,
            "path": str(source_path),
            "reason": "per_file_size_limit",
            "estimated_gb": estimated_bytes / _GB,
            "cache_hit": False,
        }
    try:
        free_bytes = shutil.disk_usage(output_path.parent if output_path.parent.exists() else source.parent).free
    except OSError:
        free_bytes = 0
    if free_bytes < estimated_bytes * FREE_SPACE_FACTOR:
        return {
            "conformed": False,
            "path": str(source_path),
            "reason": "insufficient_free_space",
            "free_gb": free_bytes / _GB,
            "needed_gb": estimated_bytes * FREE_SPACE_FACTOR / _GB,
            "cache_hit": False,
        }
    if run_budget is not None and not run_budget.can_spend(estimated_bytes):
        return {
            "conformed": False,
            "path": str(source_path),
            "reason": "run_budget_exhausted",
            "budget_spent_gb": run_budget.spent_bytes / _GB,
            "budget_max_gb": run_budget.max_bytes / _GB,
            "cache_hit": False,
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    codec = _codec_for_stream(stream)
    cmd = [
        resolve_tool("ffmpeg"),
        "-hide_banner", "-loglevel", "error",
        "-i", str(source_path),
        "-af", filter_graph,
        "-c:a", codec,
        "-y", str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0 or not output_path.is_file() or output_path.stat().st_size == 0:
        output_path.unlink(missing_ok=True)
        raise APICallFailed(
            "ffmpeg conform render failed.",
            details={
                "source_path": source_path,
                "filter_graph": filter_graph,
                "stderr_tail": (proc.stderr or b"").decode("utf-8", errors="replace")[-500:],
            },
        )
    if run_budget is not None:
        run_budget.spend(float(output_path.stat().st_size))
    return {
        "conformed": True,
        "path": str(output_path),
        "filter_graph": filter_graph,
        "residual_applied_ms": residual_seconds * 1000.0,
        "drift_applied_ppm": drift_ppm,
        "reason": "rendered",
        "cache_hit": False,
    }
