"""Waveform-based audio sync offset computation using ffmpeg + NumPy FFT correlation.

`estimate_offset` is the single production estimator. It proposes alignment
candidates from generic waveform evidence, refines them on quality-selected
48 kHz windows with GCC-PHAT and parabolic sub-sample interpolation, and
aggregates a robust consensus that also yields a clock-drift estimate.
Sub-frame precision is preserved in the result instead of being rounded away.

`compute_waveform_offset` / `compute_waveform_offsets` keep their historical
signatures and integer-frame return values but route through `estimate_offset`.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from ..errors import APICallFailed, ValidationError
from ..external_tools import resolve_tool

_ANALYSIS_SAMPLE_RATE = 16000
_REFINE_SAMPLE_RATE = 48000
_ENVELOPE_HZ = 250
_WINDOW_SECONDS = 30.0
_SEARCH_SECONDS = 1.0
_DEFAULT_WINDOWS = 7
_COARSE_TOP_K = 3
_SILENCE_RMS_FLOOR = 30.0  # int16 RMS below this is treated as silence
_CLIP_PEAK_LEVEL = 0.98 * 32767.0
_LANDMARK_MAX_PEAKS = 240
_LANDMARK_TOP_EACH = 120
_LANDMARK_MATCH_TOLERANCE_SECONDS = 0.08
_LANDMARK_MIN_REFINED_MATCHES = 3
_ENGINE_METHOD = "waveform_sync"
SCHEMA_VERSION = 1

_ENVELOPE_CACHE: Dict[Tuple[str, float, int, int], Dict[str, Any]] = {}
_ENVELOPE_CACHE_LIMIT = 8


def _ffmpeg_bin() -> str:
    return resolve_tool("ffmpeg")


def _load_waveform_dependencies():
    try:
        import numpy as np
    except ImportError as exc:
        raise APICallFailed(
            "Waveform sync requires numpy. Install cutagent with waveform sync dependencies.",
            details={"missing_dependency": exc.name},
            recoverability="manual",
        ) from exc
    return np


def _extract_mono_pcm(source_path: str) -> Any:
    """Extract mono 16-bit PCM audio from a media file via ffmpeg."""
    np = _load_waveform_dependencies()
    cmd = [
        _ffmpeg_bin(),
        "-i", source_path,
        "-vn",
        "-ac", "1",
        "-ar", str(_ANALYSIS_SAMPLE_RATE),
        "-f", "s16le",
        "-acodec", "pcm_s16le",
        "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=False)
    except FileNotFoundError:
        raise APICallFailed(
            "ffmpeg not found. Install ffmpeg or set --ffmpeg-path.",
            details={"source_path": source_path},
        )
    if proc.returncode != 0:
        raise APICallFailed(
            "ffmpeg audio extraction failed.",
            details={
                "source_path": source_path,
                "stderr_tail": (proc.stderr or b"").decode("utf-8", errors="replace")[-500:],
            },
        )
    raw = proc.stdout
    if len(raw) < 4:
        raise ValidationError(
            "Source clip has no usable audio for waveform sync.",
            details={"source_path": source_path, "raw_bytes": len(raw)},
        )
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    return samples


def _cross_correlation_offset_samples(reference: Any, target: Any) -> int:
    """Compute the sample offset that best aligns target to reference via cross-correlation.

    Returns the number of samples target must be delayed (positive = target starts later).
    """
    np = _load_waveform_dependencies()
    output_len = len(reference) + len(target) - 1
    fft_len = 1 << max(1, output_len - 1).bit_length()
    correlation = np.fft.irfft(
        np.fft.rfft(reference, fft_len) * np.fft.rfft(target[::-1], fft_len),
        fft_len,
    )[:output_len]
    peak_index = int(np.argmax(np.abs(correlation)))
    offset = peak_index - (len(target) - 1)
    return offset


# ---------------------------------------------------------------------------
# v2 estimator internals
# ---------------------------------------------------------------------------


def _envelope_cache_key(source_path: str, envelope_hz: int) -> Optional[Tuple[str, float, int, int]]:
    try:
        real = os.path.realpath(source_path)
        stat = os.stat(real)
    except OSError:
        return None
    return (real, stat.st_mtime, stat.st_size, int(envelope_hz))


def _extract_envelope(source_path: str, *, envelope_hz: int = _ENVELOPE_HZ) -> Dict[str, Any]:
    """Stream-decode audio at 16 kHz and accumulate per-block RMS/peak envelopes.

    Never holds the full decoded signal in memory; the envelope arrays are
    ~64x smaller than the 16 kHz stream.
    """
    np = _load_waveform_dependencies()
    key = _envelope_cache_key(source_path, envelope_hz)
    if key is not None and key in _ENVELOPE_CACHE:
        return _ENVELOPE_CACHE[key]

    block = max(1, int(round(_ANALYSIS_SAMPLE_RATE / float(envelope_hz))))
    cmd = [
        _ffmpeg_bin(),
        "-hide_banner", "-loglevel", "error",
        "-i", source_path,
        "-vn",
        "-ac", "1",
        "-ar", str(_ANALYSIS_SAMPLE_RATE),
        "-f", "s16le",
        "-acodec", "pcm_s16le",
        "-",
    ]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        raise APICallFailed(
            "ffmpeg not found. Install ffmpeg or set --ffmpeg-path.",
            details={"source_path": source_path},
        )
    rms_parts: List[Any] = []
    peak_parts: List[Any] = []
    carry = b""
    total_samples = 0
    chunk_bytes = block * 2 * 8192
    assert proc.stdout is not None
    while True:
        data = proc.stdout.read(chunk_bytes)
        if not data:
            break
        data = carry + data
        usable = (len(data) // (block * 2)) * block * 2
        carry = data[usable:]
        if usable == 0:
            continue
        arr = np.frombuffer(data[:usable], dtype=np.int16).astype(np.float32).reshape(-1, block)
        total_samples += arr.size
        rms_parts.append(np.sqrt(np.mean(arr * arr, axis=1)))
        peak_parts.append(np.max(np.abs(arr), axis=1))
    if carry:
        tail = np.frombuffer(carry[: (len(carry) // 2) * 2], dtype=np.int16).astype(np.float32)
        if tail.size:
            total_samples += int(tail.size)
            rms_parts.append(np.array([float(np.sqrt(np.mean(tail * tail)))], dtype=np.float32))
            peak_parts.append(np.array([float(np.max(np.abs(tail)))], dtype=np.float32))
    stderr_data = proc.stderr.read() if proc.stderr else b""
    return_code = proc.wait()
    if return_code != 0:
        raise APICallFailed(
            "ffmpeg audio extraction failed.",
            details={
                "source_path": source_path,
                "stderr_tail": stderr_data.decode("utf-8", errors="replace")[-500:],
            },
        )
    if total_samples < _ANALYSIS_SAMPLE_RATE // 4:
        raise ValidationError(
            "Source clip has no usable audio for waveform sync.",
            details={"source_path": source_path, "decoded_samples": int(total_samples)},
        )
    rms = np.concatenate(rms_parts)
    peak = np.concatenate(peak_parts)
    onset = np.diff(rms, prepend=rms[:1])
    onset[onset < 0.0] = 0.0
    envelope = {
        "rms": rms,
        "peak": peak,
        "onset": onset,
        "envelope_hz": float(envelope_hz),
        "duration_seconds": total_samples / float(_ANALYSIS_SAMPLE_RATE),
        "samples": int(total_samples),
    }
    if key is not None:
        if len(_ENVELOPE_CACHE) >= _ENVELOPE_CACHE_LIMIT:
            _ENVELOPE_CACHE.pop(next(iter(_ENVELOPE_CACHE)))
        _ENVELOPE_CACHE[key] = envelope
    return envelope


def _coarse_candidates(
    ref_env: Dict[str, Any],
    tgt_env: Dict[str, Any],
    *,
    top_k: int = _COARSE_TOP_K,
    min_separation_seconds: float = 5.0,
) -> List[float]:
    """Correlate onset envelopes and return up to top_k candidate offsets in seconds.

    Music is self-similar, so the single best envelope peak can sit on a repeated
    phrase; downstream refinement picks the true candidate by window consensus.
    """
    np = _load_waveform_dependencies()
    env_hz = float(ref_env["envelope_hz"])
    a = ref_env["onset"].astype(np.float64)
    b = tgt_env["onset"].astype(np.float64)
    for arr in (a, b):
        arr -= arr.mean()
        peak = float(np.max(np.abs(arr)))
        if peak > 0.0:
            arr /= peak
    output_len = len(a) + len(b) - 1
    fft_len = 1 << max(1, output_len - 1).bit_length()
    correlation = np.fft.irfft(
        np.fft.rfft(a, fft_len) * np.fft.rfft(b[::-1], fft_len),
        fft_len,
    )[:output_len]
    score = np.abs(correlation)
    min_sep = max(1, int(round(min_separation_seconds * env_hz)))
    order = np.argsort(score)[::-1]
    picked: List[int] = []
    for idx in order[: max(64, top_k * 32)]:
        idx = int(idx)
        if all(abs(idx - other) >= min_sep for other in picked):
            picked.append(idx)
            if len(picked) >= top_k:
                break
    offsets = [(idx - (len(b) - 1)) / env_hz for idx in picked]
    return offsets


def _pick_landmark_peaks(env: Dict[str, Any], *, max_peaks: int = _LANDMARK_MAX_PEAKS) -> List[Dict[str, float]]:
    """Return distributed high-confidence onset landmarks from the coarse envelope.

    This is intentionally generic: it does not know about claps or podcasts. It
    selects salient transient onsets across the file so repeated event patterns
    can propose offset candidates before the heavier windowed refine stage.
    """
    np = _load_waveform_dependencies()
    onset = np.asarray(env["onset"], dtype=np.float64)
    if onset.size < 3:
        return []
    env_hz = float(env["envelope_hz"])
    positive = onset[onset > 0.0]
    if positive.size == 0:
        return []
    threshold = float(np.percentile(positive, 90.0))
    candidates = np.where(
        (onset[1:-1] >= onset[:-2])
        & (onset[1:-1] >= onset[2:])
        & (onset[1:-1] >= threshold)
    )[0] + 1
    if candidates.size == 0:
        return []
    order = candidates[np.argsort(onset[candidates])[::-1]]
    min_sep = max(1, int(round(0.10 * env_hz)))
    picked: List[int] = []
    # Keep strong landmarks from all parts of the file, not only the loudest
    # intro sequence; drift validation needs temporal spread.
    bucket_count = min(8, max(1, int(float(env["duration_seconds"]) // 300) + 1))
    per_bucket = max(8, max_peaks // bucket_count)
    bucket_picked = [0 for _ in range(bucket_count)]
    for idx_value in order:
        idx = int(idx_value)
        bucket = min(bucket_count - 1, int(idx / max(1, onset.size) * bucket_count))
        if bucket_picked[bucket] >= per_bucket:
            continue
        if any(abs(idx - old) < min_sep for old in picked):
            continue
        picked.append(idx)
        bucket_picked[bucket] += 1
        if len(picked) >= max_peaks:
            break
    picked.sort()
    score_scale = float(np.percentile(onset[picked], 95.0)) if picked else 1.0
    score_scale = score_scale or 1.0
    return [
        {
            "time": idx / env_hz,
            "score": float(onset[idx] / score_scale),
            "index": float(idx),
        }
        for idx in picked
    ]


def _score_landmark_offset(
    ref_peaks: List[Dict[str, float]],
    tgt_peaks: List[Dict[str, float]],
    offset_seconds: float,
    *,
    tolerance_seconds: float = _LANDMARK_MATCH_TOLERANCE_SECONDS,
) -> Dict[str, Any]:
    np = _load_waveform_dependencies()
    if not ref_peaks or not tgt_peaks:
        return {"score": 0.0, "matches": []}
    target_times = np.array([p["time"] + offset_seconds for p in tgt_peaks], dtype=np.float64)
    matches: List[Dict[str, float]] = []
    used_targets: set[int] = set()
    score = 0.0
    for ref in sorted(ref_peaks, key=lambda p: p["score"], reverse=True):
        ref_time = float(ref["time"])
        insert = int(np.searchsorted(target_times, ref_time))
        best: tuple[float, int] | None = None
        for idx in (insert - 1, insert, insert + 1):
            if idx < 0 or idx >= len(tgt_peaks) or idx in used_targets:
                continue
            delta = abs(ref_time - float(target_times[idx]))
            if delta <= tolerance_seconds and (best is None or delta < best[0]):
                best = (delta, idx)
        if best is None:
            continue
        delta, idx = best
        used_targets.add(idx)
        tgt = tgt_peaks[idx]
        weight = (max(0.0, float(ref["score"])) * max(0.0, float(tgt["score"]))) ** 0.5
        contribution = weight * max(0.0, 1.0 - delta / tolerance_seconds)
        score += contribution
        matches.append(
            {
                "ref_time": ref_time,
                "target_time": float(tgt["time"]),
                "raw_offset_seconds": ref_time - float(tgt["time"]),
                "delta_seconds": float(delta),
                "score": float(contribution),
            }
        )
    return {"score": float(score), "matches": matches}


def _landmark_candidates(ref_env: Dict[str, Any], tgt_env: Dict[str, Any]) -> List[Dict[str, Any]]:
    ref_peaks = _pick_landmark_peaks(ref_env)
    tgt_peaks = _pick_landmark_peaks(tgt_env)
    if len(ref_peaks) < 3 or len(tgt_peaks) < 3:
        return []
    ref_top = sorted(ref_peaks, key=lambda p: p["score"], reverse=True)[:_LANDMARK_TOP_EACH]
    tgt_top = sorted(tgt_peaks, key=lambda p: p["score"], reverse=True)[:_LANDMARK_TOP_EACH]
    raw_offsets = [
        float(ref["time"]) - float(tgt["time"])
        for ref in ref_top
        for tgt in tgt_top
    ]
    # Cluster nearby raw offsets before expensive scoring.
    raw_offsets.sort()
    clustered: List[float] = []
    for value in raw_offsets:
        if not clustered or abs(value - clustered[-1]) >= 0.04:
            clustered.append(value)
    scored: List[Dict[str, Any]] = []
    for candidate in clustered:
        result = _score_landmark_offset(ref_peaks, tgt_peaks, candidate)
        if len(result["matches"]) >= _LANDMARK_MIN_REFINED_MATCHES:
            result["offset_seconds"] = float(candidate)
            scored.append(result)
    scored.sort(key=lambda item: (float(item["score"]), len(item["matches"])), reverse=True)
    return scored[:5]


def _alignment_candidates(
    ref_env: Dict[str, Any],
    tgt_env: Dict[str, Any],
    *,
    prior_offset_seconds: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Return ranked offset proposals for the single estimator pipeline."""
    if prior_offset_seconds is not None:
        return [{"offset_seconds": float(prior_offset_seconds), "source": "prior", "score": 1.0}]

    proposals: List[Dict[str, Any]] = []
    for candidate in _landmark_candidates(ref_env, tgt_env):
        proposals.append(
            {
                "offset_seconds": float(candidate["offset_seconds"]),
                "source": "landmark",
                "score": float(candidate.get("score") or 0.0),
                "match_count": len(candidate.get("matches") or []),
                "matches": candidate.get("matches") or [],
            }
        )
    for index, offset in enumerate(_coarse_candidates(ref_env, tgt_env)):
        proposals.append(
            {
                "offset_seconds": float(offset),
                "source": "envelope",
                "score": float(_COARSE_TOP_K - index),
                "match_count": 0,
                "matches": [],
            }
        )

    merged: List[Dict[str, Any]] = []
    for proposal in sorted(proposals, key=lambda item: float(item["score"]), reverse=True):
        offset = float(proposal["offset_seconds"])
        duplicate = next(
            (existing for existing in merged if abs(float(existing["offset_seconds"]) - offset) < 0.04),
            None,
        )
        if duplicate is None:
            merged.append(proposal)
            continue
        if float(proposal["score"]) > float(duplicate["score"]):
            duplicate.update(proposal)
    return merged[: _COARSE_TOP_K + 5]


def _window_quality(env: Dict[str, Any], start_seconds: float, duration_seconds: float) -> float:
    """Score window quality from envelope stats: transient density, penalized for clipping/silence."""
    np = _load_waveform_dependencies()
    env_hz = float(env["envelope_hz"])
    lo = max(0, int(start_seconds * env_hz))
    hi = min(len(env["rms"]), int((start_seconds + duration_seconds) * env_hz))
    if hi - lo < max(2, int(env_hz)):
        return 0.0
    rms = env["rms"][lo:hi]
    if float(np.mean(rms)) < _SILENCE_RMS_FLOOR:
        return 0.0
    onset = env["onset"][lo:hi]
    transient_energy = float(np.sum(onset))
    clip_fraction = float(np.mean(env["peak"][lo:hi] >= _CLIP_PEAK_LEVEL))
    return transient_energy * (1.0 - min(1.0, clip_fraction * 4.0))


def _select_window_centers(
    ref_env: Dict[str, Any],
    tgt_env: Dict[str, Any],
    coarse_offset_seconds: float,
    *,
    windows: int,
    window_seconds: float,
    search_seconds: float,
) -> List[float]:
    """Pick window centers (reference time) by signal quality across early/middle/late buckets."""
    ref_dur = float(ref_env["duration_seconds"])
    tgt_dur = float(tgt_env["duration_seconds"])
    ov_start = max(0.0, coarse_offset_seconds)
    ov_end = min(ref_dur, tgt_dur + coarse_offset_seconds)
    margin = search_seconds * 2.0
    lo = ov_start + margin
    hi = ov_end - window_seconds - margin
    if hi <= lo:
        return []
    step = max(window_seconds / 2.0, (hi - lo) / 200.0)
    candidates: List[Tuple[float, float]] = []
    pos = lo
    while pos <= hi:
        ref_q = _window_quality(ref_env, pos, window_seconds)
        tgt_q = _window_quality(tgt_env, pos - coarse_offset_seconds, window_seconds)
        score = min(ref_q, tgt_q)
        if score > 0.0:
            candidates.append((pos + window_seconds / 2.0, score))
        pos += step
    if not candidates:
        return []
    span = hi - lo
    buckets: List[List[Tuple[float, float]]] = [[], [], []]
    for center, score in candidates:
        bucket = min(2, int((center - lo) / span * 3.0)) if span > 0 else 0
        buckets[bucket].append((center, score))
    for bucket in buckets:
        bucket.sort(key=lambda item: item[1], reverse=True)
    selected: List[float] = []
    # Round-robin across buckets so early/middle/late are all represented
    # (the drift fit needs temporal spread, not just the loudest passages).
    round_index = 0
    while len(selected) < windows:
        progressed = False
        for bucket in buckets:
            if round_index < len(bucket) and len(selected) < windows:
                center = bucket[round_index][0]
                if all(abs(center - other) >= window_seconds for other in selected):
                    selected.append(center)
                progressed = True
        if not progressed:
            break
        round_index += 1
    selected.sort()
    return selected


def _extract_window_pcm(
    source_path: str,
    *,
    start_seconds: float,
    duration_seconds: float,
    sample_rate: int = _REFINE_SAMPLE_RATE,
) -> Any:
    """Extract a mono PCM window via ffmpeg input-seek (verified sample-accurate)."""
    np = _load_waveform_dependencies()
    cmd = [
        _ffmpeg_bin(),
        "-hide_banner", "-loglevel", "error",
        "-ss", f"{max(0.0, start_seconds):.6f}",
        "-i", source_path,
        "-t", f"{max(0.1, duration_seconds):.6f}",
        "-vn",
        "-ac", "1",
        "-ar", str(sample_rate),
        "-f", "s16le",
        "-acodec", "pcm_s16le",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        raise APICallFailed(
            "ffmpeg window extraction failed.",
            details={
                "source_path": source_path,
                "start_seconds": start_seconds,
                "stderr_tail": (proc.stderr or b"").decode("utf-8", errors="replace")[-500:],
            },
        )
    return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32)


def _parabolic_peak_interpolation(y_left: float, y_center: float, y_right: float) -> float:
    denominator = y_left - 2.0 * y_center + y_right
    if denominator == 0.0:
        return 0.0
    shift = 0.5 * (y_left - y_right) / denominator
    return float(min(0.5, max(-0.5, shift)))


def _short_file_offset_seconds(reference_path: str, target_path: str) -> Tuple[float, float]:
    """Full-file correlation for sources too short for windowed validation."""
    np = _load_waveform_dependencies()
    reference = _extract_mono_pcm(reference_path)
    target = _extract_mono_pcm(target_path)
    output_len = len(reference) + len(target) - 1
    fft_len = 1 << max(1, output_len - 1).bit_length()
    correlation = np.fft.irfft(
        np.fft.rfft(reference, fft_len) * np.fft.rfft(target[::-1], fft_len),
        fft_len,
    )[:output_len]
    abs_corr = np.abs(correlation)
    peak_index = int(np.argmax(abs_corr))
    fraction = 0.0
    if 0 < peak_index < output_len - 1:
        fraction = _parabolic_peak_interpolation(
            float(abs_corr[peak_index - 1]),
            float(abs_corr[peak_index]),
            float(abs_corr[peak_index + 1]),
        )
    median_value = float(np.median(abs_corr))
    quality = float(abs_corr[peak_index]) / median_value if median_value > 0.0 else 0.0
    offset_samples = (peak_index - (len(target) - 1)) + fraction
    return offset_samples / float(_ANALYSIS_SAMPLE_RATE), quality


def _gcc_phat_lag(
    ref_win: Any,
    tgt_win: Any,
    *,
    lag_lo: int,
    lag_hi: int,
) -> Tuple[float, float]:
    """Whitened cross-correlation; returns (fractional lag, peak quality).

    Lag semantics: ref_win[i] aligns tgt_win[i - lag].
    Quality is peak magnitude over the median magnitude in the searched range.
    """
    np = _load_waveform_dependencies()
    a = ref_win.astype(np.float64)
    b = tgt_win.astype(np.float64)
    a -= a.mean()
    b -= b.mean()
    n = len(a) + len(b) - 1
    fft_len = 1 << max(1, n - 1).bit_length()
    spec = np.fft.rfft(a, fft_len) * np.conj(np.fft.rfft(b, fft_len))
    magnitude = np.abs(spec)
    spec /= np.maximum(magnitude, 1e-12)
    correlation = np.fft.irfft(spec, fft_len)
    lags = np.concatenate([np.arange(0, len(b)), np.arange(-fft_len + len(b), 0)])
    valid = (lags >= lag_lo) & (lags <= lag_hi)
    if not bool(np.any(valid)):
        return 0.0, 0.0
    abs_corr = np.abs(correlation)
    masked = np.where(valid, abs_corr, -np.inf)
    peak_index = int(np.argmax(masked))
    peak_value = float(abs_corr[peak_index])
    median_value = float(np.median(abs_corr[valid]))
    quality = peak_value / median_value if median_value > 0.0 else 0.0
    fraction = 0.0
    if 0 < peak_index < len(correlation) - 1:
        fraction = _parabolic_peak_interpolation(
            float(abs_corr[peak_index - 1]),
            peak_value,
            float(abs_corr[peak_index + 1]),
        )
    return float(lags[peak_index]) + fraction, quality


def _refine_window_offset(
    reference_path: str,
    target_path: str,
    center_seconds: float,
    coarse_offset_seconds: float,
    ref_duration: float,
    tgt_duration: float,
    *,
    window_seconds: float,
    search_seconds: float,
    sample_rate: int = _REFINE_SAMPLE_RATE,
) -> Optional[Dict[str, float]]:
    """Measure the precise offset around one window. Returns None when the window is unusable."""
    r0 = center_seconds - window_seconds / 2.0
    r0 = min(max(0.0, r0), max(0.0, ref_duration - window_seconds))
    t0 = r0 - coarse_offset_seconds - search_seconds
    if t0 < 0.0:
        r0 = min(r0 - t0, max(0.0, ref_duration - window_seconds))
        t0 = r0 - coarse_offset_seconds - search_seconds
        if t0 < 0.0:
            return None
    tgt_needed = window_seconds + 2.0 * search_seconds
    if t0 + tgt_needed > tgt_duration:
        overshoot = (t0 + tgt_needed) - tgt_duration
        r0 -= overshoot
        t0 -= overshoot
        if r0 < 0.0 or t0 < 0.0:
            return None
    ref_win = _extract_window_pcm(
        reference_path, start_seconds=r0, duration_seconds=window_seconds, sample_rate=sample_rate
    )
    tgt_win = _extract_window_pcm(
        target_path, start_seconds=t0, duration_seconds=tgt_needed, sample_rate=sample_rate
    )
    min_samples = int(window_seconds * sample_rate * 0.5)
    if len(ref_win) < min_samples or len(tgt_win) < min_samples:
        return None
    search_samples = int(round(search_seconds * sample_rate))
    lag, quality = _gcc_phat_lag(ref_win, tgt_win, lag_lo=-2 * search_samples, lag_hi=0)
    if quality <= 0.0:
        return None
    offset_seconds = (r0 - t0) + lag / float(sample_rate)
    return {
        "center_seconds": float(r0 + window_seconds / 2.0),
        "offset_seconds": float(offset_seconds),
        "peak_quality": float(quality),
    }


def _consensus(window_results: List[Dict[str, float]]) -> Dict[str, Any]:
    """Robust aggregate of per-window offsets: midpoint offset, drift, confidence."""
    np = _load_waveform_dependencies()
    offsets = np.array([w["offset_seconds"] for w in window_results], dtype=np.float64)
    centers = np.array([w["center_seconds"] for w in window_results], dtype=np.float64)
    qualities = np.array([w["peak_quality"] for w in window_results], dtype=np.float64)
    median = float(np.median(offsets))
    deviations = np.abs(offsets - median)
    mad = float(np.median(deviations))
    tolerance = max(3.5 * mad, 0.001)
    used = deviations <= tolerance
    if int(np.sum(used)) < 2:
        used = np.ones(len(offsets), dtype=bool)
    used_offsets = offsets[used]
    used_centers = centers[used]
    used_qualities = qualities[used]
    midpoint = float(np.mean(used_centers))
    drift_ppm = 0.0
    offset_at_midpoint = float(np.median(used_offsets))
    center_span = float(used_centers.max() - used_centers.min()) if len(used_centers) > 1 else 0.0
    fitted_offsets = np.full_like(used_offsets, offset_at_midpoint)
    if len(used_offsets) >= 3 and center_span >= 300.0:
        slope, intercept = np.polyfit(used_centers, used_offsets, 1)
        drift_ppm = float(slope * 1e6)
        offset_at_midpoint = float(slope * midpoint + intercept)
        fitted_offsets = slope * used_centers + intercept
    spread_ms = float((used_offsets.max() - used_offsets.min()) * 1000.0) if len(used_offsets) else 0.0
    residuals = used_offsets - fitted_offsets
    residual_spread_ms = float((residuals.max() - residuals.min()) * 1000.0) if len(residuals) else 0.0
    return {
        "offset_seconds": offset_at_midpoint,
        "midpoint_seconds": midpoint,
        "drift_ppm": drift_ppm,
        "drift_window_span_seconds": center_span,
        "confidence": {
            "spread_ms": spread_ms,
            "residual_spread_ms": residual_spread_ms,
            "mad_ms": float(mad * 1000.0),
            "median_peak_quality": float(np.median(used_qualities)) if len(used_qualities) else 0.0,
            "windows_used": int(np.sum(used)),
            "windows_total": int(len(window_results)),
        },
        "used_mask": [bool(flag) for flag in used],
    }


def _result_frames(offset_seconds: float, fps: float) -> Dict[str, float]:
    frames_float = offset_seconds * fps
    frames_int = int(round(frames_float))
    residual_ms = (offset_seconds - frames_int / fps) * 1000.0
    return {
        "offset_frames_float": float(frames_float),
        "offset_frames_int": frames_int,
        "subframe_residual_ms": float(residual_ms),
    }


def estimate_offset(
    reference_path: str,
    target_path: str,
    fps: float,
    *,
    windows: int = _DEFAULT_WINDOWS,
    window_seconds: float = _WINDOW_SECONDS,
    search_seconds: float = _SEARCH_SECONDS,
    prior_offset_seconds: Optional[float] = None,
    envelope_hz: int = _ENVELOPE_HZ,
) -> Dict[str, Any]:
    """Estimate the precise offset of target relative to reference.

    Positive offset means the target must be placed later on the timeline,
    matching the existing sign convention. The returned offset is measured at the
    overlap midpoint; `drift_ppm` describes how it changes per second.
    """
    if fps <= 0:
        raise ValidationError(
            "Invalid frame rate for waveform sync.",
            details={"fps": fps},
        )
    warnings: List[str] = []

    ref_env = _extract_envelope(reference_path, envelope_hz=envelope_hz)
    tgt_env = _extract_envelope(target_path, envelope_hz=envelope_hz)
    ref_duration = float(ref_env["duration_seconds"])
    tgt_duration = float(tgt_env["duration_seconds"])

    min_duration = min(ref_duration, tgt_duration)
    effective_window_seconds = min(window_seconds, max(2.0, min_duration - 4.0 * search_seconds))
    if min_duration <= window_seconds + 4.0 * search_seconds:
        offset_seconds, quality = _short_file_offset_seconds(reference_path, target_path)
        result: Dict[str, Any] = {
            "offset_seconds": float(offset_seconds),
            "midpoint_seconds": float(min_duration / 2.0),
            "drift_ppm": 0.0,
            "drift_span_ms": 0.0,
            "confidence": {
                "spread_ms": 0.0,
                "residual_spread_ms": 0.0,
                "mad_ms": 0.0,
                "median_peak_quality": float(quality),
                "windows_used": 1,
                "windows_total": 1,
            },
            "per_window": [],
            "warnings": ["short_source_full_correlation"],
            "method": _ENGINE_METHOD,
            "candidate": {
                "offset_seconds": float(offset_seconds),
                "source": "short_full_correlation",
                "score": float(quality),
                "match_count": 1,
            },
            "schema_version": SCHEMA_VERSION,
        }
        result.update(_result_frames(offset_seconds, fps))
        return result
    candidates = _alignment_candidates(ref_env, tgt_env, prior_offset_seconds=prior_offset_seconds)
    if not candidates:
        raise ValidationError(
            "Waveform sync could not find an alignment candidate.",
            details={"reference_path": reference_path, "target_path": target_path},
        )

    minimum_window_count = max(1, min(3, int(windows)))
    probe_windows = minimum_window_count
    candidate_runs: List[Dict[str, Any]] = []
    for candidate in candidates:
        candidate_offset = float(candidate["offset_seconds"])
        centers = _select_window_centers(
            ref_env, tgt_env, candidate_offset,
            windows=windows, window_seconds=effective_window_seconds, search_seconds=search_seconds,
        )
        landmark_centers = [
            float(match["ref_time"])
            for match in sorted(candidate.get("matches") or [], key=lambda item: item.get("score", 0.0), reverse=True)
        ]
        for center in landmark_centers:
            if len(centers) >= windows:
                break
            half_window = effective_window_seconds / 2.0
            if center < half_window or center > ref_duration - half_window:
                continue
            if all(abs(center - existing) >= half_window for existing in centers):
                centers.append(center)
        centers.sort()
        if not centers:
            continue
        probe_centers = centers[:: max(1, len(centers) // probe_windows)][:probe_windows]
        measurements = []
        for center in probe_centers:
            measured = _refine_window_offset(
                reference_path, target_path, center, candidate_offset,
                ref_duration, tgt_duration,
                window_seconds=effective_window_seconds, search_seconds=search_seconds,
            )
            if measured is not None:
                measurements.append(measured)
        if not measurements:
            continue
        agreement = [m for m in measurements if abs(m["offset_seconds"] - candidate_offset) <= search_seconds]
        score = sum(m["peak_quality"] for m in agreement)
        candidate_runs.append(
            {
                "candidate": candidate_offset,
                "candidate_source": candidate.get("source"),
                "candidate_score": float(candidate.get("score") or 0.0),
                "candidate_match_count": int(candidate.get("match_count") or 0),
                "centers": centers,
                "measurements": measurements,
                "agreement": len(agreement),
                "score": score,
            }
        )

    if not candidate_runs:
        raise ValidationError(
            "Waveform sync could not refine any alignment candidate.",
            details={
                "reference_path": reference_path,
                "target_path": target_path,
                "candidate_count": len(candidates),
            },
        )

    candidate_runs.sort(key=lambda run: (run["agreement"], run["score"]), reverse=True)
    max_spread_ms = min(50.0, 1000.0 / max(float(fps), 1.0) * 0.75)
    selected: Optional[Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, float]]]] = None
    rejected: List[Dict[str, Any]] = []
    for run in candidate_runs:
        if run["agreement"] == 0:
            rejected.append({"candidate": run["candidate"], "reason": "no_probe_agreement"})
            continue

        measured_centers = {m["center_seconds"] for m in run["measurements"]}
        measurements: List[Dict[str, float]] = list(run["measurements"])
        for center in run["centers"]:
            if len(measurements) >= windows:
                break
            if any(abs(center - existing) < effective_window_seconds / 2.0 for existing in measured_centers):
                continue
            measured = _refine_window_offset(
                reference_path, target_path, center, run["candidate"],
                ref_duration, tgt_duration,
                window_seconds=effective_window_seconds, search_seconds=search_seconds,
            )
            if measured is not None:
                measurements.append(measured)
                measured_centers.add(measured["center_seconds"])

        consistent = [
            m for m in measurements if abs(m["offset_seconds"] - run["candidate"]) <= 2.0 * search_seconds
        ]
        if len(consistent) >= 2:
            measurements = consistent
        if len(measurements) < minimum_window_count:
            rejected.append({"candidate": run["candidate"], "reason": "low_window_count"})
            continue
        aggregate = _consensus(measurements)
        confidence = aggregate["confidence"]
        residual_spread_ms = float(confidence.get("residual_spread_ms", confidence["spread_ms"]))
        if residual_spread_ms > max_spread_ms:
            rejected.append(
                {
                    "candidate": run["candidate"],
                    "reason": "high_residual_spread",
                    "residual_spread_ms": residual_spread_ms,
                    "spread_ms": float(confidence["spread_ms"]),
                }
            )
            continue
        selected = (run, aggregate, measurements)
        break

    if selected is None:
        raise ValidationError(
            "Waveform sync could not validate any refined alignment candidate.",
            details={
                "reference_path": reference_path,
                "target_path": target_path,
                "candidate_count": len(candidates),
                "rejected": rejected[:5],
            },
        )

    winner, aggregate, measurements = selected
    offset_seconds = float(aggregate["offset_seconds"])
    overlap_seconds = min(ref_duration, tgt_duration + offset_seconds) - max(0.0, offset_seconds)
    drift_span_ms = abs(aggregate["drift_ppm"]) * 1e-6 * max(0.0, overlap_seconds) * 1000.0

    per_window = [
        {
            "center_seconds": m["center_seconds"],
            "offset_seconds": m["offset_seconds"],
            "peak_quality": m["peak_quality"],
            "used": bool(aggregate["used_mask"][index]),
        }
        for index, m in enumerate(measurements)
    ]
    result = {
        "offset_seconds": offset_seconds,
        "midpoint_seconds": float(aggregate["midpoint_seconds"]),
        "drift_ppm": float(aggregate["drift_ppm"]),
        "drift_span_ms": float(drift_span_ms),
        "confidence": aggregate["confidence"],
        "per_window": per_window,
        "warnings": warnings,
        "method": _ENGINE_METHOD,
        "candidate": {
            "offset_seconds": float(winner["candidate"]),
            "source": winner.get("candidate_source"),
            "score": float(winner.get("candidate_score") or 0.0),
            "match_count": int(winner.get("candidate_match_count") or 0),
        },
        "schema_version": SCHEMA_VERSION,
    }
    result.update(_result_frames(offset_seconds, fps))
    return result


# ---------------------------------------------------------------------------
# Shared-clock grouping
# ---------------------------------------------------------------------------


def group_offsets(
    offset_results: Dict[str, Dict[str, Any]],
    recorder_ids: Optional[Dict[str, Optional[str]]] = None,
    pairwise_results: Optional[Dict[Tuple[str, str], Dict[str, Any]]] = None,
    *,
    fps: float,
    offset_tolerance_seconds: float = 0.010,
    drift_tolerance_ppm: float = 0.5,
) -> Dict[str, Dict[str, Any]]:
    """Assign shared-clock groups and one shared offset per group.

    Sources are grouped only on hard evidence: an identical recorder identity
    from metadata, or a direct pairwise measurement showing near-zero mutual
    offset AND near-zero mutual drift. Offset similarity alone never groups —
    independent recorders can coincidentally land close together.

    Members of a group share a single offset (the quality-weighted median of
    member offsets), so their as-recorded mutual sample alignment is preserved
    exactly on the timeline.
    """
    labels = list(offset_results.keys())
    parent = {label: label for label in labels}

    def find(label: str) -> str:
        while parent[label] != label:
            parent[label] = parent[parent[label]]
            label = parent[label]
        return label

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    recorder_ids = recorder_ids or {}
    for i, a in enumerate(labels):
        for b in labels[i + 1:]:
            rid_a, rid_b = recorder_ids.get(a), recorder_ids.get(b)
            if rid_a and rid_b and rid_a == rid_b:
                union(a, b)
                continue
            if pairwise_results:
                pair = pairwise_results.get((a, b)) or pairwise_results.get((b, a))
                if pair is not None and (
                    abs(float(pair.get("offset_seconds", 1e9))) <= offset_tolerance_seconds
                    and abs(float(pair.get("drift_ppm", 1e9))) <= drift_tolerance_ppm
                ):
                    union(a, b)

    groups: Dict[str, List[str]] = {}
    for label in labels:
        groups.setdefault(find(label), []).append(label)

    output: Dict[str, Dict[str, Any]] = {}
    for root, members in groups.items():
        offsets = sorted(float(offset_results[m]["offset_seconds"]) for m in members)
        mid = len(offsets) // 2
        shared = offsets[mid] if len(offsets) % 2 else 0.5 * (offsets[mid - 1] + offsets[mid])
        shared_drift = None
        shared_midpoint = None
        shared_span = None
        if len(members) > 1:
            # One clock means one drift: average the members' measurements
            # (weighted by window count) so they receive identical treatment.
            weights = []
            drifts = []
            midpoints = []
            spans = []
            for member in members:
                entry = offset_results[member]
                if entry.get("drift_ppm") is None:
                    continue
                weight = float(((entry.get("confidence") or {}).get("windows_used")) or 1.0)
                weights.append(weight)
                drifts.append(float(entry["drift_ppm"]) * weight)
                midpoints.append(float(entry.get("midpoint_seconds") or 0.0) * weight)
                spans.append(float(entry.get("drift_span_ms") or 0.0) * weight)
            total = sum(weights)
            if total > 0:
                shared_drift = sum(drifts) / total
                shared_midpoint = sum(midpoints) / total
                shared_span = sum(spans) / total
        for member in members:
            value = shared if len(members) > 1 else float(offset_results[member]["offset_seconds"])
            output[member] = {
                "group": root,
                "group_size": len(members),
                "offset_seconds": value,
                "drift_ppm": shared_drift,
                "drift_midpoint_seconds": shared_midpoint,
                "drift_span_ms": shared_span,
                **_result_frames(value, fps),
            }
    return output


# ---------------------------------------------------------------------------
# Backward-compatible public API
# ---------------------------------------------------------------------------


def compute_waveform_offsets(source_paths: List[str], fps: float) -> List[int]:
    """Compute per-clip frame offsets for waveform-based multicam sync.

    The first clip is the reference (offset 0). Other clips get a positive
    offset if they need to start later on the timeline to align audio.

    Args:
        source_paths: Paths to source media files (at least 2).
        fps: Timeline frame rate for converting sample offsets to frames.

    Returns:
        List of integer frame offsets, one per source clip.
    """
    if len(source_paths) < 2:
        raise ValidationError(
            "Waveform sync requires at least 2 source clips.",
            details={"source_count": len(source_paths)},
        )
    if fps <= 0:
        raise ValidationError(
            "Invalid frame rate for waveform sync.",
            details={"fps": fps},
        )

    frame_offsets = [0]
    for path in source_paths[1:]:
        result = estimate_offset(source_paths[0], path, fps)
        frame_offsets.append(int(result["offset_frames_int"]))

    # Normalize so the minimum offset is 0 (no clip starts before timeline origin).
    min_offset = min(frame_offsets)
    frame_offsets = [offset - min_offset for offset in frame_offsets]

    return frame_offsets


def compute_waveform_offset(reference_path: str, target_path: str, fps: float) -> int:
    """Compute signed target offset in frames relative to a reference path.

    Positive means the target source should be placed later on the timeline to
    align with the reference. Negative means it starts earlier than the
    reference. Unlike compute_waveform_offsets(), this function does not
    normalize offsets to a non-negative origin because audio-activity planning
    needs the source-to-timeline translation for each isolated microphone.
    """
    result = estimate_offset(reference_path, target_path, fps)
    return int(result["offset_frames_int"])
