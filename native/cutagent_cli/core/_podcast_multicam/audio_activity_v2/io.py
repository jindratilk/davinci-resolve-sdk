from __future__ import annotations

import math
import shutil
import statistics
import struct
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple


@dataclass
class AudioWindowSample:
    start: float
    end: float
    rms_db: float
    active: bool


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
    elif sample_width == 4:
        count = len(frames) // 4
        samples = list(struct.unpack("<" + "i" * count, frames[: count * 4]))
    elif sample_width == 3:
        samples = []
        for offset in range(0, len(frames) - (len(frames) % 3), 3):
            chunk = frames[offset : offset + 3]
            value = int.from_bytes(chunk + (b"\x00" if chunk[-1] < 0x80 else b"\xff"), byteorder="little", signed=True)
            samples.append(value)
    else:
        return 0.0

    if not samples:
        return 0.0
    mean_square = sum(sample * sample for sample in samples) / float(len(samples))
    return math.sqrt(mean_square)


def _read_wave_window_levels(path: Path, window_seconds: float = 0.25) -> Tuple[float, int, List[AudioWindowSample]]:
    with wave.open(str(path), "rb") as handle:
        frame_rate = int(handle.getframerate() or 48000)
        sample_width = int(handle.getsampwidth() or 2)
        total_frames = int(handle.getnframes() or 0)
        window_frames = max(1, int(frame_rate * max(window_seconds, 0.05)))

        samples: List[AudioWindowSample] = []
        cursor = 0
        while cursor < total_frames:
            handle.setpos(cursor)
            frames = handle.readframes(window_frames)
            if not frames:
                break
            rms = _pcm_rms(frames, sample_width)
            start = cursor / frame_rate
            end = min(total_frames, cursor + window_frames) / frame_rate
            samples.append(
                AudioWindowSample(
                    start=start,
                    end=end,
                    rms_db=_safe_dbfs(rms, sample_width),
                    active=False,
                )
            )
            cursor += window_frames

        duration = total_frames / frame_rate if frame_rate else 0.0
        return duration, frame_rate, samples


def _ffmpeg_binary() -> str:
    candidate = shutil.which("ffmpeg")
    if candidate:
        return candidate
    raise RuntimeError("ffmpeg not available")


def _read_audio_window_levels(path: Path, window_seconds: float = 0.25) -> Tuple[float, int, List[AudioWindowSample]]:
    try:
        return _read_wave_window_levels(path, window_seconds=window_seconds)
    except wave.Error as exc:
        if "unknown format" not in str(exc).lower():
            raise

    with tempfile.TemporaryDirectory(prefix="podcast-audio-proxy-") as tmpdir:
        proxy_path = Path(tmpdir) / f"{path.stem}__proxy.wav"
        command = [
            _ffmpeg_binary(),
            "-y",
            "-i",
            str(path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "48000",
            "-c:a",
            "pcm_s16le",
            str(proxy_path),
        ]
        process = subprocess.run(command, capture_output=True, text=False)
        if process.returncode != 0 or not proxy_path.exists():
            stderr = (process.stderr or b"").decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"ffmpeg audio proxy failed for {path.name}: {stderr or 'unknown error'}")
        return _read_wave_window_levels(proxy_path, window_seconds=window_seconds)


def _merge_activity_ranges(samples: Sequence[AudioWindowSample], *, gap_tolerance: float) -> List[Tuple[float, float]]:
    ranges: List[Tuple[float, float]] = []
    for sample in samples:
        if not sample.active:
            continue
        start = float(sample.start)
        end = float(sample.end)
        if not ranges:
            ranges.append((start, end))
            continue
        prev_start, prev_end = ranges[-1]
        if start <= prev_end + gap_tolerance:
            ranges[-1] = (prev_start, max(prev_end, end))
            continue
        ranges.append((start, end))
    return ranges


def _speaker_activity_ranges(
    speaker_map: Sequence[Dict[str, Any]],
    *,
    activity_margin_db: float,
    absolute_activity_floor_db: float,
    window_seconds: float,
) -> Dict[str, List[Tuple[float, float]]]:
    speaker_ranges: Dict[str, List[Tuple[float, float]]] = {}
    for speaker in speaker_map or []:
        speaker_id = str(speaker.get("speaker_id") or "").strip()
        audio_file = str(speaker.get("mic_file") or speaker.get("audio_file") or "").strip()
        if not speaker_id or not audio_file:
            continue
        path = Path(audio_file).expanduser()
        if not path.exists():
            continue
        try:
            _duration, _rate, samples = _read_audio_window_levels(path, window_seconds=window_seconds)
        except Exception:
            continue
        levels = [sample.rms_db for sample in samples]
        if levels:
            noise_floor = statistics.median(sorted(levels)[: max(1, len(levels) // 4)])
        else:
            noise_floor = -120.0
        active_samples = [
            AudioWindowSample(
                start=sample.start,
                end=sample.end,
                rms_db=sample.rms_db,
                active=(sample.rms_db - noise_floor >= activity_margin_db and sample.rms_db > absolute_activity_floor_db),
            )
            for sample in samples
        ]
        speaker_ranges[speaker_id] = _merge_activity_ranges(
            active_samples,
            gap_tolerance=max(window_seconds * 0.5, 0.01),
        )
    return speaker_ranges
