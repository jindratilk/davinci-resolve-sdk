"""Persisted Inspector authority stable across lossless native recompression."""
from __future__ import annotations

import hashlib
import struct
import zstandard as zstd

_MAX_BYTES = 16 * 1024 * 1024


def inspector_state_digest(blob: bytes) -> str:
    """Bind all packed effect bytes, normalizing only known compression frames."""
    if len(blob) > _MAX_BYTES:
        return hashlib.sha256(blob).hexdigest()
    canonical = bytearray()
    offset = 0
    try:
        while offset < len(blob):
            version, size = struct.unpack_from(">II", blob, offset)
            if version != 2 or size < 1 or size > len(blob) - offset - 8:
                return hashlib.sha256(blob).hexdigest()
            body = blob[offset + 8:offset + 8 + size]
            if body[0] == 0x80:
                payload = body[1:]
            elif body[0] == 0x81:
                frame = body[1:]
                declared = zstd.frame_content_size(frame)
                if declared not in (zstd.CONTENTSIZE_UNKNOWN, zstd.CONTENTSIZE_ERROR) and declared > _MAX_BYTES - len(canonical) - 9:
                    return hashlib.sha256(blob).hexdigest()
                payload = zstd.ZstdDecompressor().decompress(
                    frame, max_output_size=max(1, _MAX_BYTES - len(canonical) - 9), allow_extra_data=False,
                )
            else:
                return hashlib.sha256(blob).hexdigest()
            if len(payload) + len(canonical) + 9 > _MAX_BYTES:
                return hashlib.sha256(blob).hexdigest()
            canonical.extend(struct.pack(">II", version, len(payload) + 1))
            canonical.extend(b"\x80" + payload)
            offset += 8 + size
    except (ValueError, struct.error, zstd.ZstdError):
        return hashlib.sha256(blob).hexdigest()
    return hashlib.sha256(canonical).hexdigest()
