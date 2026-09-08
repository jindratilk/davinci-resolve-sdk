"""Metadata/timecode prepass for audio sync.

Reads deterministic sync hints before any waveform analysis:

- BWF ``bext`` chunk: ``TimeReference`` (first sample since midnight) and
  originator fields, read directly from the RIFF structure.
- iXML chunk: recorder/project identity when present.
- Container start timecode (camera files) via ffprobe stream/format tags.
- Basic stream facts (sample rate, channels, duration).

A metadata prior never replaces waveform verification — recorders can carry
wrong or free-running timecode. The prior narrows the waveform search and the
recorder identity feeds conservative shared-clock grouping.
"""

from __future__ import annotations

import json
import os
import re
import struct
import subprocess
from typing import Any, Dict, Optional

from ..external_tools import resolve_tool

_RIFF_SCAN_LIMIT = 64 * 1024 * 1024  # bext/iXML live near the head; do not scan huge data chunks


def _ffprobe_bin() -> str:
    return resolve_tool("ffprobe")


def _read_riff_chunks(path: str) -> Dict[str, bytes]:
    """Return raw bytes of small metadata chunks (bext, iXML) from a RIFF/RF64 WAV."""
    chunks: Dict[str, bytes] = {}
    try:
        with open(path, "rb") as handle:
            header = handle.read(12)
            if len(header) < 12 or header[:4] not in (b"RIFF", b"RF64") or header[8:12] != b"WAVE":
                return chunks
            scanned = 12
            while scanned < _RIFF_SCAN_LIMIT:
                chunk_header = handle.read(8)
                if len(chunk_header) < 8:
                    break
                chunk_id = chunk_header[:4]
                chunk_size = struct.unpack("<I", chunk_header[4:8])[0]
                if chunk_id in (b"bext", b"iXML") and chunk_size <= 4 * 1024 * 1024:
                    chunks[chunk_id.decode("ascii")] = handle.read(chunk_size)
                else:
                    handle.seek(chunk_size, os.SEEK_CUR)
                if chunk_size % 2:
                    handle.seek(1, os.SEEK_CUR)
                scanned += 8 + chunk_size
    except OSError:
        return chunks
    return chunks


def _parse_bext(raw: bytes) -> Dict[str, Any]:
    """Decode the fixed-layout fields of a BWF bext chunk."""
    if len(raw) < 348:
        return {}

    def _text(blob: bytes) -> Optional[str]:
        value = blob.split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()
        return value or None

    time_reference = struct.unpack("<Q", raw[338:346])[0]
    return {
        "description": _text(raw[0:256]),
        "originator": _text(raw[256:288]),
        "originator_reference": _text(raw[288:320]),
        "origination_date": _text(raw[320:330]),
        "origination_time": _text(raw[330:338]),
        "time_reference_samples": int(time_reference),
    }


def _parse_ixml_recorder(raw: bytes) -> Optional[str]:
    text = raw.decode("utf-8", errors="replace")
    for tag in ("RECORDER_SERIAL_NUMBER", "RECORDER", "TAPE", "PROJECT"):
        match = re.search(rf"<{tag}>([^<]+)</{tag}>", text)
        if match:
            value = match.group(1).strip()
            if value:
                return f"{tag.lower()}:{value}"
    return None


def _timecode_to_seconds(timecode: str, fps: float) -> Optional[float]:
    match = re.match(r"^(\d{2}):(\d{2}):(\d{2})[:;](\d{2})$", timecode.strip())
    if not match or fps <= 0:
        return None
    hours, minutes, seconds, frames = (int(part) for part in match.groups())
    nominal = round(fps) if abs(fps - round(fps)) < 0.01 else fps
    return hours * 3600.0 + minutes * 60.0 + seconds + frames / float(nominal)


def _ffprobe_facts(path: str) -> Dict[str, Any]:
    cmd = [
        _ffprobe_bin(),
        "-v", "error",
        "-show_entries",
        "format=duration:format_tags:stream=codec_type,sample_rate,channels,duration:stream_tags=timecode",
        "-of", "json",
        path,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=False)
        payload = json.loads(proc.stdout or b"{}")
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def read_sync_metadata(source_path: str, *, fps: Optional[float] = None) -> Dict[str, Any]:
    """Collect sync-relevant metadata for one media file."""
    facts = _ffprobe_facts(source_path)
    streams = facts.get("streams") or []
    format_info = facts.get("format") or {}
    format_tags = {str(k).lower(): v for k, v in (format_info.get("tags") or {}).items()}

    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})
    sample_rate = None
    try:
        sample_rate = int(audio_stream.get("sample_rate") or 0) or None
    except (TypeError, ValueError):
        sample_rate = None
    duration_seconds = None
    for candidate in (audio_stream.get("duration"), format_info.get("duration")):
        try:
            duration_seconds = float(candidate)
            break
        except (TypeError, ValueError):
            continue

    timecode = format_tags.get("timecode")
    if not timecode:
        for stream in streams:
            tags = {str(k).lower(): v for k, v in (stream.get("tags") or {}).items()}
            if tags.get("timecode"):
                timecode = tags["timecode"]
                break

    metadata: Dict[str, Any] = {
        "path": source_path,
        "sample_rate": sample_rate,
        "channels": audio_stream.get("channels"),
        "duration_seconds": duration_seconds,
        "start_timecode": timecode,
        "bwf": None,
        "ixml_recorder_id": None,
        "recorder_id": None,
        "recorder_id_source": None,
        "start_seconds_since_midnight": None,
    }

    if source_path.lower().endswith((".wav", ".bwf", ".w64")):
        chunks = _read_riff_chunks(source_path)
        if "bext" in chunks:
            metadata["bwf"] = _parse_bext(chunks["bext"])
        elif format_tags.get("time_reference") is not None:
            try:
                metadata["bwf"] = {"time_reference_samples": int(format_tags["time_reference"])}
            except (TypeError, ValueError):
                pass
        if "iXML" in chunks:
            metadata["ixml_recorder_id"] = _parse_ixml_recorder(chunks["iXML"])

    if metadata["ixml_recorder_id"]:
        metadata["recorder_id"] = metadata["ixml_recorder_id"]
        metadata["recorder_id_source"] = "ixml"
    elif metadata["bwf"] and metadata["bwf"].get("originator") and metadata["bwf"].get("origination_date"):
        metadata["recorder_id"] = (
            f"bwf:{metadata['bwf']['originator']}:{metadata['bwf']['origination_date']}"
        )
        metadata["recorder_id_source"] = "bwf_originator"

    bwf = metadata["bwf"] or {}
    time_reference = bwf.get("time_reference_samples")
    if time_reference and sample_rate:
        metadata["start_seconds_since_midnight"] = float(time_reference) / float(sample_rate)
    elif timecode and fps:
        metadata["start_seconds_since_midnight"] = _timecode_to_seconds(timecode, fps)

    return metadata


def compute_metadata_prior(
    reference_metadata: Dict[str, Any],
    target_metadata: Dict[str, Any],
) -> Optional[float]:
    """Deterministic prior offset (seconds, positive = target placed later).

    Derived from wall-clock start times. With reference starting at R0 and the
    target at T0, a shared wall-clock event sits at file time (W - R0) in the
    reference and (W - T0) in the target, so the placement offset is T0 - R0.
    A BWF TimeReference of zero means "unset" and produces no prior.
    """
    ref_start = reference_metadata.get("start_seconds_since_midnight")
    tgt_start = target_metadata.get("start_seconds_since_midnight")
    if ref_start is None or tgt_start is None:
        return None
    if not ref_start and not (reference_metadata.get("start_timecode")):
        return None
    if not tgt_start and not (target_metadata.get("start_timecode")):
        return None
    return float(tgt_start) - float(ref_start)
