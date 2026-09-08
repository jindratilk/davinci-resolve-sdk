"""ffmpeg-based audio processing operations."""

from __future__ import annotations

import subprocess
import json
import math
from pathlib import Path
from typing import Optional

from ..external_tools import resolve_tool
from ..errors import APICallFailed, ValidationError


def _ffmpeg_bin() -> str:
    return resolve_tool("ffmpeg")


def _ffprobe_bin() -> str:
    return resolve_tool("ffprobe")


def _default_output(input_path: str, suffix: str = "_processed") -> str:
    p = Path(input_path)
    return str(p.with_stem(p.stem + suffix))


def default_output(input_path: str, suffix: str = "_processed") -> str:
    return _default_output(input_path, suffix)


def validate_output_file_path(output_path: str) -> None:
    """Validate that an output path can be used as a file target."""
    path = Path(output_path)
    if path.exists() and path.is_dir():
        raise ValidationError(
            "Output path is a directory, not a file.",
            details={"path": output_path, "path_type": "directory"},
        )
    parent = path.parent
    if parent and not parent.exists():
        raise ValidationError(
            "Output directory does not exist.",
            details={"path": output_path, "parent": str(parent)},
        )
    if parent and not parent.is_dir():
        raise ValidationError(
            "Output parent path is not a directory.",
            details={"path": output_path, "parent": str(parent)},
        )


def _run_ffmpeg(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    """Run ffmpeg with given args."""
    cmd = [_ffmpeg_bin()] + args
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _run_ffprobe(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    """Run ffprobe with given args."""
    cmd = [_ffprobe_bin()] + args
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _probe_audio_streams(input_path: str) -> list[dict]:
    """Return ffprobe audio stream records with stable CLI errors."""
    try:
        result = _run_ffprobe(
            [
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                "-select_streams",
                "a",
                input_path,
            ]
        )
    except subprocess.CalledProcessError as exc:
        raise APICallFailed(
            "ffprobe audio stream inspection failed.",
            details={
                "input": input_path,
                "stderr_tail": (exc.stderr or "")[-500:],
                "stdout_tail": (exc.stdout or "")[-300:],
            },
        ) from exc

    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise APICallFailed(
            "ffprobe returned invalid JSON.",
            details={
                "input": input_path,
                "stdout_tail": (result.stdout or "")[-500:],
                "stderr_tail": (result.stderr or "")[-300:],
            },
        ) from exc
    return list(data.get("streams") or [])


def _audio_stream_summary(stream: dict) -> dict:
    return {
        "index": stream.get("index"),
        "codec": stream.get("codec_name"),
        "sample_rate": stream.get("sample_rate"),
        "channels": stream.get("channels"),
        "channel_layout": stream.get("channel_layout"),
        "bitrate": stream.get("bit_rate"),
        "duration": stream.get("duration"),
    }


def audio_stream_count(input_path: str) -> int:
    """Return the number of audio streams in a media file."""
    return len(_probe_audio_streams(input_path))


def validate_duck_parameters(
    *,
    speech_track: int,
    music_track: int,
    threshold_db: float,
    ratio: float,
    attack_ms: float,
    release_ms: float,
) -> None:
    """Validate ducking parameters before building an ffmpeg filter graph."""
    numeric_values = {
        "threshold_db": threshold_db,
        "ratio": ratio,
        "attack_ms": attack_ms,
        "release_ms": release_ms,
    }
    non_finite = [name for name, value in numeric_values.items() if not math.isfinite(float(value))]
    if non_finite:
        raise ValidationError(
            "Ducking numeric parameters must be finite.",
            details={"parameters": non_finite},
        )
    if ratio < 1.0 or ratio > 20.0:
        raise ValidationError(
            "Compression ratio must be between 1 and 20.",
            details={"ratio": ratio, "min": 1.0, "max": 20.0},
        )
    if attack_ms < 0.0:
        raise ValidationError(
            "Attack time must be non-negative.",
            details={"attack_ms": attack_ms, "min": 0.0},
        )
    if release_ms < 0.0:
        raise ValidationError(
            "Release time must be non-negative.",
            details={"release_ms": release_ms, "min": 0.0},
        )


def validate_duck_streams(input_path: str, *, speech_track: int, music_track: int) -> int:
    """Validate requested 1-based audio stream indexes and return stream count."""
    stream_count = audio_stream_count(input_path)
    requested = {"speech_track": speech_track, "music_track": music_track}
    out_of_range = {name: index for name, index in requested.items() if index > stream_count}
    if out_of_range:
        raise ValidationError(
            "Requested audio track index is outside the input media audio stream count.",
            details={
                "audio_stream_count": stream_count,
                "requested": requested,
                "out_of_range": out_of_range,
            },
        )
    return stream_count


def reverb(input_path: str, output: Optional[str] = None, *, validate_audio_streams: bool = True) -> str:
    if validate_audio_streams:
        stream_count = audio_stream_count(input_path)
        if stream_count < 1:
            raise ValidationError(
                "No audio streams found",
                details={"audio_stream_count": 0, "streams": []},
            )
    out = output or _default_output(input_path)
    validate_output_file_path(out)
    af = "aecho=0.8:0.88:60:0.4"
    try:
        _run_ffmpeg(["-y", "-i", input_path, "-filter:a", af, "-c:v", "copy", out])
    except subprocess.CalledProcessError as exc:
        raise APICallFailed(
            "ffmpeg reverb pipeline failed.",
            details={
                "input": input_path,
                "output": out,
                "stderr_tail": (exc.stderr or "")[-500:],
                "stdout_tail": (exc.stdout or "")[-300:],
            },
        ) from exc
    return out


def build_duck_filter_complex(
    *,
    speech_track: int,
    music_track: int,
    threshold_db: float,
    ratio: float,
    attack_ms: float,
    release_ms: float,
) -> str:
    """Build deterministic sidechain ducking ffmpeg filter graph."""
    if speech_track < 1 or music_track < 1:
        raise ValidationError(
            "speech_track and music_track must be >= 1",
            details={"speech_track": speech_track, "music_track": music_track},
        )
    validate_duck_parameters(
        speech_track=speech_track,
        music_track=music_track,
        threshold_db=threshold_db,
        ratio=ratio,
        attack_ms=attack_ms,
        release_ms=release_ms,
    )
    speech_idx = speech_track - 1
    music_idx = music_track - 1
    return (
        f"[0:a:{music_idx}]aresample=48000[music];"
        f"[0:a:{speech_idx}]aresample=48000[speech];"
        f"[music][speech]sidechaincompress=threshold={threshold_db}dB:ratio={ratio}"
        f":attack={attack_ms}:release={release_ms}[ducked];"
        f"[ducked][speech]amix=inputs=2:weights='1 1':normalize=0[out]"
    )


def duck(
    input_path: str,
    *,
    speech_track: int,
    music_track: int,
    threshold_db: float = -20.0,
    ratio: float = 8.0,
    attack_ms: float = 20.0,
    release_ms: float = 300.0,
    output: Optional[str] = None,
    validate_stream_indexes: bool = True,
) -> str:
    """Apply sidechain ducking with ffmpeg sidechaincompress + speech mixback."""
    validate_duck_parameters(
        speech_track=speech_track,
        music_track=music_track,
        threshold_db=threshold_db,
        ratio=ratio,
        attack_ms=attack_ms,
        release_ms=release_ms,
    )
    if validate_stream_indexes:
        validate_duck_streams(input_path, speech_track=speech_track, music_track=music_track)
    out = output or _default_output(input_path, "_ducked")
    filter_complex = build_duck_filter_complex(
        speech_track=speech_track,
        music_track=music_track,
        threshold_db=threshold_db,
        ratio=ratio,
        attack_ms=attack_ms,
        release_ms=release_ms,
    )
    try:
        _run_ffmpeg(
            [
                "-y",
                "-i",
                input_path,
                "-filter_complex",
                filter_complex,
                "-map",
                "0:v?",
                "-map",
                "[out]",
                "-c:v",
                "copy",
                out,
            ]
        )
    except subprocess.CalledProcessError as exc:
        raise APICallFailed(
            "ffmpeg ducking pipeline failed.",
            details={
                "input": input_path,
                "stderr_tail": (exc.stderr or "")[-500:],
                "stdout_tail": (exc.stdout or "")[-300:],
            },
        ) from exc
    return out


def info(input_path: str) -> dict:
    """Get audio stream info via ffprobe."""
    streams = _probe_audio_streams(input_path)
    if not streams:
        return {"error": "No audio streams found", "audio_stream_count": 0, "streams": []}
    stream_summaries = [_audio_stream_summary(stream) for stream in streams]
    s = stream_summaries[0]
    return {
        "audio_stream_count": len(stream_summaries),
        "streams": stream_summaries,
        "codec": s.get("codec"),
        "sample_rate": s.get("sample_rate"),
        "channels": s.get("channels"),
        "channel_layout": s.get("channel_layout"),
        "bitrate": s.get("bitrate"),
        "duration": s.get("duration"),
    }
