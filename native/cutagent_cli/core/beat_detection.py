"""Deterministic music beat and phrase analysis for local media files."""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

import numpy as np
from scipy.signal import find_peaks

from ..errors import APICallFailed, ValidationError
from ..external_tools import resolve_tool


def _decode_mono_pcm(path: str, *, sample_rate: int) -> np.ndarray:
    command = [
        resolve_tool("ffmpeg"),
        "-v",
        "error",
        "-i",
        path,
        "-map",
        "0:a:0",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "f32le",
        "pipe:1",
    ]
    try:
        result = subprocess.run(command, capture_output=True, check=True)
    except subprocess.CalledProcessError as exc:
        raise APICallFailed(
            "ffmpeg beat-analysis decode failed.",
            details={"input": path, "stderr_tail": exc.stderr.decode("utf-8", errors="replace")[-500:]},
        ) from exc
    samples = np.frombuffer(result.stdout, dtype="<f4")
    if samples.size < sample_rate:
        raise ValidationError(
            "Beat analysis requires at least one second of audio.",
            details={"input": path, "duration_seconds": samples.size / sample_rate},
        )
    return samples


def _onset_envelope(samples: np.ndarray, *, sample_rate: int, hop_length: int) -> np.ndarray:
    frame_length = 2048
    if samples.size < frame_length:
        return np.empty(0, dtype=np.float64)
    frame_count = 1 + (samples.size - frame_length) // hop_length
    flux = np.empty(frame_count, dtype=np.float64)
    window = np.hanning(frame_length).astype(samples.dtype, copy=False)
    previous_spectrum: np.ndarray | None = None
    batch_frames = 256
    for frame_start in range(0, frame_count, batch_frames):
        batch_count = min(batch_frames, frame_count - frame_start)
        sample_start = frame_start * hop_length
        frames = np.lib.stride_tricks.as_strided(
            samples[sample_start:],
            shape=(batch_count, frame_length),
            strides=(samples.strides[0] * hop_length, samples.strides[0]),
            writeable=False,
        )
        spectra = np.abs(np.fft.rfft(frames * window, axis=1))
        if previous_spectrum is None:
            flux[frame_start] = 0.0
            first_delta_index = 1
        else:
            flux[frame_start] = np.maximum(spectra[0] - previous_spectrum, 0.0).sum()
            first_delta_index = 1
        if batch_count > first_delta_index:
            deltas = np.maximum(np.diff(spectra, axis=0), 0.0)
            flux[frame_start + first_delta_index : frame_start + batch_count] = deltas.sum(axis=1)
        previous_spectrum = spectra[-1]
    if not np.any(flux > 0):
        return np.zeros_like(flux)
    window = max(3, round(0.15 * sample_rate / hop_length))
    baseline = np.convolve(flux, np.ones(window) / window, mode="same")
    envelope = np.maximum(flux - baseline, 0.0)
    scale = float(np.percentile(envelope, 95))
    return envelope / scale if scale > 0 else envelope


def _tempo_period(envelope: np.ndarray, *, sample_rate: int, hop_length: int, min_bpm: float, max_bpm: float) -> tuple[float, float]:
    centered = envelope - float(np.mean(envelope))
    fft_length = 1 << (2 * len(centered) - 1).bit_length()
    spectrum = np.fft.rfft(centered, fft_length)
    correlation = np.fft.irfft(spectrum * np.conj(spectrum), fft_length)[: len(centered)]
    min_lag = max(1, math.floor(60.0 * sample_rate / (max_bpm * hop_length)))
    max_lag = min(len(correlation) - 1, math.ceil(60.0 * sample_rate / (min_bpm * hop_length)))
    if max_lag <= min_lag:
        raise ValidationError("Audio is too short for the requested tempo range.")
    candidates = correlation[min_lag : max_lag + 1]
    lag = min_lag + int(np.argmax(candidates))
    onset_peaks, _ = find_peaks(envelope, distance=max(1, min_lag // 2), prominence=0.08)
    if onset_peaks.size >= 4:
        intervals = np.diff(onset_peaks)
        intervals = intervals[(intervals >= min_lag) & (intervals <= max_lag)]
        if intervals.size:
            onset_lag = float(np.median(intervals))
            if correlation[round(onset_lag)] >= correlation[lag] * 0.75:
                lag = onset_lag
    lag_index = round(lag)
    if 0 < lag_index < len(correlation) - 1:
        left_value = float(correlation[lag_index - 1])
        center_value = float(correlation[lag_index])
        right_value = float(correlation[lag_index + 1])
        denominator = left_value - 2.0 * center_value + right_value
        if abs(denominator) > 1e-12:
            lag = lag_index + 0.5 * (left_value - right_value) / denominator
    peak = float(correlation[lag_index])
    confidence = max(0.0, min(1.0, peak / max(float(correlation[0]), 1e-12)))
    return lag, confidence


def analyze(
    path: str,
    *,
    fps: float,
    min_bpm: float = 60.0,
    max_bpm: float = 200.0,
    beats_per_bar: int = 4,
    bars_per_phrase: int = 8,
    beat_offset: int = 0,
    sample_rate: int = 22050,
) -> dict:
    """Return frame-snapped beats, inferred downbeats, bars, and phrases."""
    if not Path(path).is_file():
        raise ValidationError("Beat-analysis input file does not exist.", details={"input": path})
    if not math.isfinite(fps) or fps <= 0:
        raise ValidationError("fps must be a positive finite number.", details={"fps": fps})
    if not (20.0 <= min_bpm < max_bpm <= 400.0):
        raise ValidationError(
            "Tempo range must satisfy 20 <= min_bpm < max_bpm <= 400.",
            details={"min_bpm": min_bpm, "max_bpm": max_bpm},
        )
    if beats_per_bar < 1 or bars_per_phrase < 1:
        raise ValidationError("beats_per_bar and bars_per_phrase must be positive integers.")

    samples = _decode_mono_pcm(path, sample_rate=sample_rate)
    hop_length = 512
    envelope = _onset_envelope(samples, sample_rate=sample_rate, hop_length=hop_length)
    if envelope.size < 4 or float(np.max(envelope)) <= 0:
        raise ValidationError("No reliable musical onsets were detected.", details={"input": path})
    period, periodicity = _tempo_period(
        envelope,
        sample_rate=sample_rate,
        hop_length=hop_length,
        min_bpm=min_bpm,
        max_bpm=max_bpm,
    )
    peaks, _ = find_peaks(envelope, distance=max(1, round(period * 0.55)), prominence=0.08)
    if peaks.size < 2:
        raise ValidationError("Too few reliable musical onsets were detected.", details={"onset_count": int(peaks.size)})

    seed = float(peaks[0])
    grid = []
    cursor = seed
    while cursor - period >= 0:
        cursor -= period
    tolerance = max(1, round(period * 0.25))
    while cursor < len(envelope):
        expected = int(round(cursor))
        left, right = max(0, expected - tolerance), min(len(envelope), expected + tolerance + 1)
        local = left + int(np.argmax(envelope[left:right]))
        candidate = local if envelope[local] >= 0.05 else expected
        if not grid or candidate > grid[-1]:
            grid.append(candidate)
        cursor += period

    beat_seconds = [round(index * hop_length / sample_rate, 6) for index in grid]
    beat_frames = [round(value * fps) for value in beat_seconds]
    tempo_bpm = 60.0 * sample_rate / (period * hop_length)
    onset_support = float(np.mean([envelope[index] for index in grid]))
    confidence_score = max(0.0, min(1.0, 0.65 * periodicity + 0.35 * min(1.0, onset_support)))
    confidence = "high" if confidence_score >= 0.65 else "medium" if confidence_score >= 0.35 else "low"

    bar_stride = beats_per_bar
    phrase_stride = beats_per_bar * bars_per_phrase
    downbeat_indexes = [index for index in range(len(grid)) if (index - beat_offset) % bar_stride == 0]
    phrase_indexes = [index for index in range(len(grid)) if (index - beat_offset) % phrase_stride == 0]
    return {
        "operation": "beat_detect",
        "input": str(Path(path).resolve()),
        "duration_seconds": round(samples.size / sample_rate, 6),
        "fps": fps,
        "tempo_bpm": round(tempo_bpm, 3),
        "tempo_range_bpm": {"min": min_bpm, "max": max_bpm},
        "confidence": {"band": confidence, "score": round(confidence_score, 4), "periodicity": round(periodicity, 4)},
        "beats_per_bar": beats_per_bar,
        "bars_per_phrase": bars_per_phrase,
        "beat_offset": beat_offset,
        "downbeat_inference": "The first grid beat plus beat_offset is treated as the first downbeat; meter is not independently classified.",
        "beats": [
            {
                "index": index,
                "seconds": beat_seconds[index],
                "frame": beat_frames[index],
                "is_downbeat": index in downbeat_indexes,
                "is_phrase_start": index in phrase_indexes,
            }
            for index in range(len(grid))
        ],
        "downbeats": [beat_frames[index] for index in downbeat_indexes],
        "phrase_starts": [beat_frames[index] for index in phrase_indexes],
        "warnings": (["low_confidence_tempo"] if confidence == "low" else []),
    }
