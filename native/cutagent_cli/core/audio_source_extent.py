"""Sample-accurate extent for local WAV and FLAC media used by edit and readback."""

from __future__ import annotations

from typing import Any
import wave


_FLAC_MAGIC = b"fLaC"
_FLAC_STREAMINFO_SIZE = 34
_FLAC_TOTAL_SAMPLES_MASK = (1 << 36) - 1


def _flac_streaminfo_duration(stream: Any) -> tuple[int, int] | None:
    metadata_header = stream.read(4)
    if len(metadata_header) != 4:
        return None
    block_type = metadata_header[0] & 0x7F
    block_size = int.from_bytes(metadata_header[1:4], "big")
    if block_type != 0 or block_size != _FLAC_STREAMINFO_SIZE:
        return None
    streaminfo = stream.read(block_size)
    if len(streaminfo) != block_size:
        return None
    sample_fields = int.from_bytes(streaminfo[10:18], "big")
    sample_rate = sample_fields >> 44
    sample_count = sample_fields & _FLAC_TOTAL_SAMPLES_MASK
    if sample_rate <= 0 or sample_count == 0:
        return None
    return sample_count, sample_rate


def audio_file_duration(item: Any) -> tuple[int, int] | None:
    getter = getattr(item, "GetClipProperty", None)
    if not callable(getter):
        return None
    try:
        properties = getter()
    except Exception:
        properties = {}
    if not isinstance(properties, dict):
        properties = {}
    source_path = None
    for key in ("File Path", "Source File", "SourcePath"):
        candidate = properties.get(key)
        if not candidate:
            try:
                candidate = getter(key)
            except Exception:
                candidate = None
        if isinstance(candidate, str) and candidate.strip():
            source_path = candidate.strip()
            break
    if source_path is None:
        return None
    try:
        with open(source_path, "rb") as stream:
            if stream.read(4) == _FLAC_MAGIC:
                return _flac_streaminfo_duration(stream)
        with wave.open(source_path, "rb") as stream:
            sample_count = int(stream.getnframes())
            sample_rate = int(stream.getframerate())
    except (EOFError, OSError, wave.Error):
        return None
    if sample_count < 0 or sample_rate <= 0:
        return None
    return sample_count, sample_rate
