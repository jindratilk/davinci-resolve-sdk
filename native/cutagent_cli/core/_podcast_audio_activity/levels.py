"""Levels helpers for podcast audio activity planning."""

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


def _safe_dbfs(rms_value: float, sample_width: int) -> float:
    if rms_value <= 0:
        return -120.0
    peak = float((1 << (sample_width * 8 - 1)) - 1)
    if peak <= 0:
        return -120.0
    return 20.0 * math.log10(max(rms_value, 1e-12) / peak)


def _pcm_rms(frames: bytes, sample_width: int) -> float:
    if not frames:
        return 0.0
    if sample_width == 1:
        samples = [sample - 128 for sample in frames]
    elif sample_width == 2:
        count = len(frames) // 2
        samples = list(struct.unpack("<" + "h" * count, frames[: count * 2]))
    elif sample_width == 3:
        samples = []
        for offset in range(0, len(frames) - (len(frames) % 3), 3):
            chunk = frames[offset : offset + 3]
            value = int.from_bytes(chunk + (b"\x00" if chunk[-1] < 0x80 else b"\xff"), byteorder="little", signed=True)
            samples.append(value)
    elif sample_width == 4:
        count = len(frames) // 4
        samples = list(struct.unpack("<" + "i" * count, frames[: count * 4]))
    else:
        return 0.0
    if not samples:
        return 0.0
    mean_square = sum(sample * sample for sample in samples) / float(len(samples))
    return math.sqrt(mean_square)


def _read_wave_window_levels(path: Path, *, window_ms: int) -> tuple[float, int, list[AudioWindowSample]]:
    with wave.open(str(path), "rb") as handle:
        frame_rate = int(handle.getframerate() or 48_000)
        sample_width = int(handle.getsampwidth() or 2)
        total_frames = int(handle.getnframes() or 0)
        window_frames = max(1, int(frame_rate * max(window_ms, 1) / 1000.0))
        samples: list[AudioWindowSample] = []
        cursor = 0
        while cursor < total_frames:
            handle.setpos(cursor)
            frames = handle.readframes(window_frames)
            if not frames:
                break
            start_ms = int(round(cursor * 1000.0 / frame_rate))
            end_ms = int(round(min(total_frames, cursor + window_frames) * 1000.0 / frame_rate))
            samples.append(
                AudioWindowSample(
                    start_ms=start_ms,
                    end_ms=end_ms,
                    rms_db=_safe_dbfs(_pcm_rms(frames, sample_width), sample_width),
                )
            )
            cursor += window_frames
        duration = total_frames / frame_rate if frame_rate else 0.0
        return duration, frame_rate, samples


def _ffmpeg_bin() -> str:
    return resolve_tool("ffmpeg")


def _read_audio_window_levels(path: str, *, window_ms: int) -> tuple[float, int, list[AudioWindowSample]]:
    expanded = Path(path).expanduser()
    if not expanded.is_file():
        raise ValidationError("Audio activity source file not found.", details={"path": str(expanded)})
    try:
        return _read_wave_window_levels(expanded, window_ms=window_ms)
    except wave.Error:
        pass
    except EOFError:
        pass

    with tempfile.TemporaryDirectory(prefix="cutagent-audio-activity-") as tmpdir:
        proxy = Path(tmpdir) / f"{expanded.stem}.wav"
        command = [
            _ffmpeg_bin(),
            "-y",
            "-i",
            str(expanded),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "48000",
            "-c:a",
            "pcm_s16le",
            str(proxy),
        ]
        try:
            process = subprocess.run(command, capture_output=True, check=False)
        except FileNotFoundError as exc:
            raise APICallFailed(
                "ffmpeg not found. Install ffmpeg or set --ffmpeg-path.",
                details={"path": str(expanded)},
            ) from exc
        if process.returncode != 0 or not proxy.exists():
            raise APICallFailed(
                "ffmpeg audio proxy generation failed.",
                details={
                    "path": str(expanded),
                    "stderr_tail": (process.stderr or b"").decode("utf-8", errors="replace")[-500:],
                },
            )
        return _read_wave_window_levels(proxy, window_ms=window_ms)


def _finite_number(value: Any, *, key: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Audio activity switching parameter must be numeric.",
            details={"parameter": key, "value": value},
        ) from exc
    if not math.isfinite(numeric):
        raise ValidationError(
            "Audio activity switching parameter must be finite.",
            details={"parameter": key, "value": value},
        )
    return numeric


__all__ = (
    '_safe_dbfs',
    '_pcm_rms',
    '_read_wave_window_levels',
    '_ffmpeg_bin',
    '_read_audio_window_levels',
    '_finite_number',
)
