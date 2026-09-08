"""Runtime probe: does this DaVinci Resolve build honor fractional (sub-frame) audio placement?

The DaVinci Resolve 19.0.2+ scripting API documents `AppendToTimeline` clipInfo
`recordFrame` as float/int and `GetStart(True)` returning fractional frames.
Documentation is not proof that audio *renders* at the fractional position, so
the probe verifies both levels:

1. metadata: append an audio-only clip at `recordFrame = N + 0.25` and read
   back `GetStart(True)`;
2. render: place two clicks — one integer-aligned, one fractionally offset —
   render the section to WAV and measure the click spacing in samples.

The verdict is cached per DaVinci Resolve version so production syncs pay zero probe
cost. All probe artifacts (media pool clips, scratch timeline, temp WAV) are
removed afterwards.
"""

from __future__ import annotations

import json
import os
import struct
import tempfile
import time
import wave
from pathlib import Path
from typing import Any, Dict, Optional

from ..errors import APICallFailed
from . import render_engine

_PROBE_SAMPLE_RATE = 48000
_FRACTION = 0.25
_RENDER_TOLERANCE_MS = 1.0
_METADATA_TOLERANCE_FRAMES = 0.01
_TIMELINE_NAME = "cutagent-subframe-probe"


def _cache_path() -> Path:
    override = os.environ.get("CUTAGENT_SUBFRAME_PROBE_PATH")
    if override:
        return Path(override)
    return Path.home() / "Library" / "Application Support" / "CutAgent" / "subframe-probe.json"


def _resolve_version(conn) -> str:
    for method in ("GetVersionString", "GetVersion"):
        getter = getattr(conn.resolve, method, None)
        if callable(getter):
            try:
                value = getter()
            except Exception:
                continue
            if value:
                return str(value)
    return "unknown"


def load_cached_probe(version: str) -> Optional[Dict[str, Any]]:
    path = _cache_path()
    try:
        payload = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("resolve_version") != version:
        return None
    return payload


def store_probe(result: Dict[str, Any]) -> None:
    path = _cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2), "utf-8")
    except OSError:
        pass


def get_subframe_support(conn, *, force: bool = False, rendered_check: bool = True) -> Dict[str, Any]:
    """Return the cached or freshly probed sub-frame capability verdict."""
    version = _resolve_version(conn)
    if not force:
        cached = load_cached_probe(version)
        if cached is not None and (cached.get("verified_render") or not rendered_check):
            return cached
    result = probe_subframe_support(conn, rendered_check=rendered_check)
    store_probe(result)
    return result


def _write_click_wav(path: Path, *, duration_seconds: float = 1.0, click_at_seconds: float = 0.5) -> None:
    total = int(duration_seconds * _PROBE_SAMPLE_RATE)
    click = int(click_at_seconds * _PROBE_SAMPLE_RATE)
    frames = bytearray(total * 2)
    # Single-sample full-scale impulse plus a short decay so codecs keep it.
    for index, amplitude in enumerate((32000, 16000, -16000, 8000, -8000)):
        position = click + index
        if 0 <= position < total:
            struct.pack_into("<h", frames, position * 2, amplitude)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(_PROBE_SAMPLE_RATE)
        handle.writeframes(bytes(frames))


def _find_click_sample(samples, *, sample_rate: int) -> Optional[int]:
    import numpy as np

    if len(samples) == 0:
        return None
    arr = np.abs(np.asarray(samples, dtype=np.float64))
    peak = float(arr.max())
    if peak <= 0:
        return None
    return int(np.argmax(arr))


def _read_rendered_mono(path: str):
    if not str(path).lower().endswith(".wav"):
        return _read_rendered_mono_ffmpeg(path)
    import numpy as np

    with wave.open(path, "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        raw = handle.readframes(handle.getnframes())
    if width == 2:
        arr = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
    elif width == 4:
        arr = np.frombuffer(raw, dtype=np.int32).astype(np.float64)
    elif width == 3:
        as_bytes = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        arr = (
            as_bytes[:, 0].astype(np.int32)
            | (as_bytes[:, 1].astype(np.int32) << 8)
            | (as_bytes[:, 2].astype(np.int32) << 16)
        )
        arr = np.where(arr >= 1 << 23, arr - (1 << 24), arr).astype(np.float64)
    else:
        return None, rate
    if channels > 1:
        arr = arr.reshape(-1, channels).mean(axis=1)
    return arr, rate


def _read_rendered_mono_ffmpeg(path: str):
    """Decode a rendered container (e.g. .mov) to mono PCM via ffmpeg."""
    import subprocess

    import numpy as np

    from ..external_tools import resolve_tool

    cmd = [
        resolve_tool("ffmpeg"),
        "-hide_banner", "-loglevel", "error",
        "-i", str(path),
        "-vn", "-ac", "1", "-ar", str(_PROBE_SAMPLE_RATE),
        "-f", "s16le", "-acodec", "pcm_s16le", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0 or len(proc.stdout) < 4:
        return None, _PROBE_SAMPLE_RATE
    return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float64), _PROBE_SAMPLE_RATE


def probe_subframe_support(conn, *, rendered_check: bool = True) -> Dict[str, Any]:
    """Run the live probe against the connected DaVinci Resolve. Leaves no artifacts behind."""
    version = _resolve_version(conn)
    result: Dict[str, Any] = {
        "resolve_version": version,
        "supports_audio_subframe_append": False,
        "verified_render": False,
        "metadata_start_frames": None,
        "render_error_ms": None,
        "warnings": [],
        "probed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    previous_timeline = conn.timeline
    fps = float(getattr(conn, "fps", 0) or 0) or 24.0

    scratch_dir = tempfile.mkdtemp(prefix="cutagent-subframe-probe-")
    click_path = Path(scratch_dir) / "cutagent-probe-click.wav"
    _write_click_wav(click_path)

    timeline = None
    imported_items = []
    try:
        imported = conn.media_pool.ImportMedia([str(click_path)])
        if not imported:
            raise APICallFailed(
                "Probe click import failed.",
                details={"path": str(click_path)},
            )
        imported_items = list(imported)
        clip_item = imported_items[0]

        timeline_name = f"{_TIMELINE_NAME}-{int(time.time())}"
        timeline = conn.media_pool.CreateEmptyTimeline(timeline_name)
        if timeline is None:
            raise APICallFailed("Probe timeline creation failed.", details={"name": timeline_name})
        conn.project.SetCurrentTimeline(timeline)
        conn.refresh()
        fps = float(getattr(conn, "fps", 0) or 0) or fps
        start_frame = int(timeline.GetStartFrame() or 0)

        anchor = start_frame + int(round(fps)) * 2
        spacing = int(round(fps)) * 2
        integer_record = float(anchor)
        fractional_record = float(anchor + spacing) + _FRACTION
        appended = conn.media_pool.AppendToTimeline(
            [
                {"mediaPoolItem": clip_item, "mediaType": 2, "trackIndex": 1, "recordFrame": integer_record},
                {"mediaPoolItem": clip_item, "mediaType": 2, "trackIndex": 1, "recordFrame": fractional_record},
            ]
        )
        if not appended or len(appended) < 2:
            result["warnings"].append("fractional_append_rejected")
            return result

        fractional_item = appended[1]
        metadata_start = None
        try:
            metadata_start = float(fractional_item.GetStart(True))
        except (TypeError, ValueError):
            try:
                metadata_start = float(fractional_item.GetStart())
            except (TypeError, ValueError):
                metadata_start = None
        result["metadata_start_frames"] = metadata_start
        if metadata_start is None:
            result["warnings"].append("fractional_readback_unavailable")
            return result
        metadata_error = abs(metadata_start - fractional_record)
        if metadata_error > _METADATA_TOLERANCE_FRAMES:
            result["warnings"].append("fractional_position_quantized")
            return result
        result["supports_audio_subframe_append"] = True

        if not rendered_check:
            return result

        render_path = Path(scratch_dir) / "probe-render.wav"
        mark_in = anchor - int(round(fps))
        mark_out = anchor + spacing + int(round(fps)) * 2
        # DaVinci Resolve 21 refuses audio-only Wave renders through the scripting API
        # (empty codec list, SetCurrentRenderFormatAndCodec returns False), so
        # try Wave first and fall back to a QuickTime container whose video
        # export is disabled — the .mov then carries only the PCM audio track.
        rendered = None
        last_render_error: Exception | None = None
        for render_format, render_codec in (("Wave", "Linear PCM"), ("QuickTime", "Apple ProRes 422 Proxy")):
            try:
                rendered = render_engine.render_audio_range(
                    conn,
                    str(render_path),
                    mark_in_frame=int(mark_in),
                    mark_out_frame=int(mark_out),
                    format=render_format,
                    codec=render_codec,
                    bitdepth=16,
                    samplerate=_PROBE_SAMPLE_RATE,
                )
                break
            except Exception as exc:
                last_render_error = exc
                rendered = None
        if rendered is None:
            result["warnings"].append(f"render_unavailable:{last_render_error}")
            return result
        rendered_file = str(rendered)
        samples, rate = _read_rendered_mono(rendered_file)
        if samples is None:
            result["warnings"].append("render_readback_unsupported_bit_depth")
            return result


        half = len(samples) // 2
        first_click = _find_click_sample(samples[:half], sample_rate=rate)
        second_click = _find_click_sample(samples[half:], sample_rate=rate)
        if first_click is None or second_click is None:
            result["warnings"].append("render_clicks_not_found")
            return result
        second_click += half
        measured_spacing = (second_click - first_click) / float(rate)
        expected_spacing = (spacing + _FRACTION) / fps
        error_ms = abs(measured_spacing - expected_spacing) * 1000.0
        result["render_error_ms"] = error_ms
        integer_spacing_error_ms = abs(measured_spacing - spacing / fps) * 1000.0
        if error_ms <= _RENDER_TOLERANCE_MS:
            result["verified_render"] = True
        elif integer_spacing_error_ms < error_ms:
            result["warnings"].append("render_quantized_to_frame")
        else:
            result["warnings"].append("render_position_unexpected")
        return result
    finally:
        try:
            if timeline is not None:
                if previous_timeline is not None:
                    try:
                        conn.project.SetCurrentTimeline(previous_timeline)
                    except Exception:
                        pass
                delete = getattr(conn.media_pool, "DeleteTimelines", None)
                if callable(delete):
                    delete([timeline])
            if imported_items:
                delete_clips = getattr(conn.media_pool, "DeleteClips", None)
                if callable(delete_clips):
                    delete_clips(imported_items)
        except Exception:
            pass
        try:
            click_path.unlink(missing_ok=True)
            for leftover in Path(scratch_dir).glob("*"):
                leftover.unlink(missing_ok=True)
            os.rmdir(scratch_dir)
        except OSError:
            pass
        try:
            conn.refresh()
        except Exception:
            pass
