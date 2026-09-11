"""DaVinci Resolve native peak normalization helpers for timeline audio clips."""

from __future__ import annotations

from array import array
from dataclasses import asdict
import hashlib
import math
import os
import shutil
import subprocess
import tempfile
import wave

from ..errors import APICallFailed, ValidationError
from ..external_tools import resolve_tool
from . import render_engine
from .db_timeline_selection import LiveItemRef


_RETRYABLE_AUDIO_RENDER_MESSAGES = {
    "Failed to add audio range render job.",
    "Render complete but output file not found at expected path.",
}
_UNAVAILABLE_AUDIO_RENDER_ROUTE_MESSAGES = {
    "Render codec not available for format.",
    "Render format not available.",
}
MIN_TARGET_DBFS = -100.0
MAX_TARGET_DBFS = 0.0


def _max_ratio_for_sample_width(frames: bytes, sample_width: int) -> float:
    if not frames:
        return 0.0

    if sample_width == 1:
        return max(abs((byte - 128) / 127.0) for byte in frames)

    if sample_width == 2:
        samples = array("h")
        samples.frombytes(frames)
        return max((abs(sample) / 32767.0 for sample in samples), default=0.0)

    if sample_width == 3:
        peak = 0.0
        for index in range(0, len(frames) - 2, 3):
            chunk = frames[index : index + 3]
            sign = b"\xff" if chunk[2] & 0x80 else b"\x00"
            sample = int.from_bytes(chunk + sign, byteorder="little", signed=True)
            peak = max(peak, abs(sample) / 8388607.0)
        return peak

    if sample_width == 4:
        samples = array("i")
        samples.frombytes(frames)
        return max((abs(sample) / 2147483647.0 for sample in samples), default=0.0)

    raise ValidationError(
        "Unsupported WAV sample width for audio normalize.",
        details={"sample_width_bytes": sample_width},
    )


def analyze_wav_peak(path: str) -> dict[str, object]:
    with wave.open(path, "rb") as handle:
        if handle.getcomptype() != "NONE":
            raise ValidationError(
                "Audio normalize requires uncompressed PCM WAV analysis input.",
                details={"path": path, "compression": handle.getcomptype()},
            )

        sample_width = int(handle.getsampwidth())
        channels = int(handle.getnchannels())
        frame_count = int(handle.getnframes())
        sample_rate = int(handle.getframerate())

        peak_ratio = 0.0
        pcm_digest = hashlib.sha256()
        while True:
            frames = handle.readframes(65536)
            if not frames:
                break
            pcm_digest.update(frames)
            peak_ratio = max(peak_ratio, _max_ratio_for_sample_width(frames, sample_width))

    peak_dbfs = None if peak_ratio <= 0 else round(20.0 * math.log10(min(1.0, peak_ratio)), 3)
    return {
        "analysis_path": path,
        "sample_width_bytes": sample_width,
        "channels": channels,
        "frame_count": frame_count,
        "sample_rate": sample_rate,
        "peak_ratio": round(peak_ratio, 6),
        "peak_dbfs": peak_dbfs,
        "pcm_sha256": f"sha256:{pcm_digest.hexdigest()}",
    }


def compute_peak_normalization_gain(*, peak_dbfs: float | None, target_dbfs: float) -> float:
    if peak_dbfs is None:
        raise ValidationError("Cannot normalize a silent audio clip.", details={"target_dbfs": target_dbfs})
    return round(validate_target_dbfs(target_dbfs) - float(peak_dbfs), 3)


def validate_target_dbfs(target_dbfs: float) -> float:
    value = float(target_dbfs)
    if not math.isfinite(value):
        raise ValidationError(
            "Audio normalize target must be a finite dBFS value.",
            details={"target_dbfs": str(target_dbfs), "min_dbfs": MIN_TARGET_DBFS, "max_dbfs": MAX_TARGET_DBFS},
            recoverability="not_applicable",
        )
    if value < MIN_TARGET_DBFS or value > MAX_TARGET_DBFS:
        raise ValidationError(
            f"Audio normalize target must be between {MIN_TARGET_DBFS:g} and {MAX_TARGET_DBFS:g} dBFS.",
            details={"target_dbfs": value, "min_dbfs": MIN_TARGET_DBFS, "max_dbfs": MAX_TARGET_DBFS},
            recoverability="not_applicable",
        )
    return value


def _audio_render_route_is_unavailable(exc: Exception) -> bool:
    """Return whether a render failure permits trying another format/codec."""

    return isinstance(exc, ValidationError) and str(exc) in _UNAVAILABLE_AUDIO_RENDER_ROUTE_MESSAGES


def coerce_rendered_audio_to_wav(
    path: str,
    *,
    sample_rate: int = 48000,
    bitdepth: int = 16,
) -> str:
    normalized_path = os.path.abspath(path)
    if normalized_path.lower().endswith(".wav"):
        return normalized_path

    afconvert = shutil.which("afconvert")
    ffmpeg = None if afconvert else resolve_tool("ffmpeg")

    output_path = os.path.splitext(normalized_path)[0] + ".wav"
    if afconvert:
        args = [
            afconvert,
            "-f",
            "WAVE",
            "-d",
            f"LEI{int(bitdepth)}@{int(sample_rate)}",
            normalized_path,
            output_path,
        ]
    else:
        args = [
            str(ffmpeg),
            "-y",
            "-i",
            normalized_path,
            "-vn",
            "-acodec",
            f"pcm_s{int(bitdepth)}le",
            "-ar",
            str(int(sample_rate)),
            output_path,
        ]
    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not os.path.exists(output_path):
        raise APICallFailed(
            "Failed to convert DaVinci Resolve audio render to WAV for peak analysis.",
            details={
                "input_path": normalized_path,
                "output_path": output_path,
                "tool": "afconvert" if afconvert else "ffmpeg",
                "stderr_tail": (proc.stderr or "")[-500:],
                "stdout_tail": (proc.stdout or "")[-300:],
            },
        )
    return output_path


def _read_overlapping_audio_items(conn, *, target: LiveItemRef) -> list[LiveItemRef]:
    overlaps: list[LiveItemRef] = []
    count = int(conn.timeline.GetTrackCount("audio") or 0)
    for track_index in range(1, count + 1):
        for item in conn.timeline.GetItemListInTrack("audio", track_index) or []:
            try:
                start = int(item.GetStart())
                end = int(item.GetEnd())
                name = str(item.GetName() or "")
            except Exception:
                continue
            candidate = LiveItemRef(
                track_type="audio",
                track_index=track_index,
                name=name,
                start=start,
                duration=max(0, end - start),
            )
            same_item = (
                candidate.track_index == target.track_index
                and candidate.start == target.start
                and candidate.duration == target.duration
                and candidate.name == target.name
            )
            if same_item:
                continue
            if candidate.start < target.end and target.start < candidate.end:
                overlaps.append(candidate)
    return overlaps


def measure_peak_normalization(
    conn,
    *,
    audio_item: LiveItemRef,
    target_dbfs: float = -9.0,
    preferred_render_route: tuple[str, str] | None = None,
) -> dict[str, object]:
    validated_target_dbfs = validate_target_dbfs(target_dbfs)
    overlaps = _read_overlapping_audio_items(conn, target=audio_item)
    if overlaps:
        raise ValidationError(
            "Audio normalize requires an isolated audio clip span on the timeline.",
            details={
                "selected_audio": asdict(audio_item),
                "overlaps": [asdict(item) for item in overlaps],
            },
        )

    last_retryable_error: APICallFailed | None = None
    unavailable_routes: set[tuple[str, str]] = set()
    for attempt in range(1, 4):
        temp_dir = tempfile.mkdtemp(prefix="resolve_audio_normalize_")
        try:
            rendered_path: str | None = None
            route_errors: list[Exception] = []
            default_render_routes = (
                (os.path.join(temp_dir, "normalize.wav"), "Wave", "Linear PCM"),
                (os.path.join(temp_dir, "normalize.mov"), "QuickTime", "Apple ProRes 422 Proxy"),
            )
            render_routes = default_render_routes
            if preferred_render_route is not None:
                render_routes = tuple(
                    sorted(
                        default_render_routes,
                        key=lambda candidate: (candidate[1], candidate[2]) != preferred_render_route,
                    )
                )
            for render_path, render_format, render_codec in render_routes:
                route = (render_format, render_codec)
                if route in unavailable_routes:
                    continue
                try:
                    rendered_path = render_engine.render_audio_range(
                        conn,
                        render_path,
                        mark_in_frame=int(audio_item.start),
                        mark_out_frame=max(int(audio_item.start), int(audio_item.end) - 1),
                        format=render_format,
                        codec=render_codec,
                    )
                    break
                except (APICallFailed, ValidationError) as exc:
                    if not _audio_render_route_is_unavailable(exc):
                        raise
                    unavailable_routes.add(route)
                    route_errors.append(exc)
            if rendered_path is None:
                if not route_errors:
                    raise APICallFailed("Audio normalize render analysis failed unexpectedly.")
                raise route_errors[-1]
            analysis_path = coerce_rendered_audio_to_wav(rendered_path)
            analysis = analyze_wav_peak(analysis_path)
            gain_db = compute_peak_normalization_gain(
                peak_dbfs=analysis["peak_dbfs"],
                target_dbfs=validated_target_dbfs,
            )
            return {
                **analysis,
                "mode": "peak",
                "target_dbfs": validated_target_dbfs,
                "gain_db": gain_db,
                "clip_start": int(audio_item.start),
                "clip_duration": int(audio_item.duration),
                "render_format": render_format,
                "render_codec": render_codec,
            }
        except APICallFailed as exc:
            if str(exc) not in _RETRYABLE_AUDIO_RENDER_MESSAGES or attempt >= 3:
                raise
            last_retryable_error = exc
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    if last_retryable_error is not None:
        raise last_retryable_error
    raise APICallFailed("Audio normalize render analysis failed unexpectedly.")
