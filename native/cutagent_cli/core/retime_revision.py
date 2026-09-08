"""Stable retime revisions across lossless native keyframe recompression."""
from __future__ import annotations

import hashlib
import struct

import zstandard as zstd

_MAX_KEYFRAME_BYTES = 16 * 1024 * 1024


def time_map_digest(blob: bytes) -> str:
    """Hash every native byte, normalizing only the known zstd container.

    DaVinci Resolve may recompress KeyframesBA on its first rendered preview.
    Preserve the complete decompressed protobuf, including unknown fields, and
    all surrounding QMap bytes. Unrecognized layouts retain their raw digest.
    """
    return hashlib.sha256(_stable_container(blob)).hexdigest()


def _stable_container(blob: bytes) -> bytes:
    try:
        version, count = struct.unpack_from(">II", blob)
        if version not in (0, 1) or not 0 < count < 10000:
            return blob
        offset = 8
        replacement = None
        seen = set()
        for _ in range(count):
            size = struct.unpack_from(">I", blob, offset)[0]
            offset += 4
            if size % 2 or size > len(blob) - offset:
                return blob
            name = blob[offset:offset + size].decode("utf-16-be")
            offset += size
            if name in seen:
                return blob
            seen.add(name)
            kind = struct.unpack_from(">I", blob, offset)[0]
            offset += 4
            if offset >= len(blob) or blob[offset] != 0:
                return blob
            offset += 1
            if kind in (2, 6):
                offset += 4 if kind == 2 else 8
            elif kind in (10, 12):
                length_at = offset
                size = struct.unpack_from(">I", blob, offset)[0]
                offset += 4
                if size > len(blob) - offset:
                    return blob
                raw = blob[offset:offset + size]
                if name == "KeyframesBA" and kind == 12:
                    if not raw.startswith(b"\x81\x28\xb5\x2f\xfd"):
                        return blob
                    frame = raw[1:]
                    declared = zstd.frame_content_size(frame)
                    if declared not in (zstd.CONTENTSIZE_UNKNOWN, zstd.CONTENTSIZE_ERROR) and declared > _MAX_KEYFRAME_BYTES:
                        return blob
                    payload = zstd.ZstdDecompressor().decompress(
                        frame, max_output_size=_MAX_KEYFRAME_BYTES, allow_extra_data=False,
                    )
                    canonical = b"\x81" + zstd.ZstdCompressor(level=3).compress(payload)
                    replacement = (length_at, offset + size, struct.pack(">I", len(canonical)) + canonical)
                offset += size
            else:
                return blob
            if offset > len(blob):
                return blob
        if replacement is None:
            return blob
        start, end, value = replacement
        return blob[:start] + value + blob[end:]
    except (ValueError, UnicodeError, struct.error, zstd.ZstdError):
        return blob
