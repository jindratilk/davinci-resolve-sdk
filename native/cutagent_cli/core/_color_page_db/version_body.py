"""Compression helpers for DaVinci Resolve LmVersion.Body payloads."""

from __future__ import annotations

from ...errors import APICallFailed

try:
    import zstandard
except ImportError:
    zstandard = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Version body compression helpers
# ---------------------------------------------------------------------------

VERSION_BODY_PREFIX_RAW = 0x80
VERSION_BODY_PREFIX_ZSTD = 0x81
_BASELINE_VERSION_BODY_HEX = (
    "800a2a10011a2208800f10b8081d0000803f"
    "20800f28b808350000803f38800f40b808"
    "48ffffffff0f60b2a67e100120b2a67e"
)
_VERSION_TABLE_FIELDS_BLOB_HEX = (
    "00000001000000020000001E004C006100730074004300680061006E00670065006400540069006D006500"
    "000004000000019E97D51AA50000002200410063007400690076006500560065007200730069006F006E"
    "0054007900700065000000020000000000"
)


def decompress_version_body(raw_body: bytes) -> bytes:
    """Decompress a LmVersion.Body blob → raw protobuf bytes."""
    if not raw_body:
        return b""
    prefix = raw_body[0]
    if prefix == VERSION_BODY_PREFIX_RAW:
        return raw_body[1:]
    if prefix == VERSION_BODY_PREFIX_ZSTD:
        if zstandard is None:
            raise APICallFailed(
                "zstandard library required for reading graded version bodies.",
                details={"hint": "pip install zstandard"},
            )
        dctx = zstandard.ZstdDecompressor()
        return dctx.decompress(raw_body[1:], max_output_size=16 * 1024 * 1024)
    # Unknown prefix – try raw protobuf
    return raw_body


def compress_version_body(proto_data: bytes) -> bytes:
    """Compress raw protobuf → LmVersion.Body blob with ZSTD."""
    if zstandard is None:
        raise APICallFailed(
            "zstandard library required for writing graded version bodies.",
            details={"hint": "pip install zstandard"},
        )
    cctx = zstandard.ZstdCompressor(level=3)
    compressed = cctx.compress(proto_data)
    return bytes([VERSION_BODY_PREFIX_ZSTD]) + compressed


__all__ = (
    "VERSION_BODY_PREFIX_RAW",
    "VERSION_BODY_PREFIX_ZSTD",
    "_BASELINE_VERSION_BODY_HEX",
    "_VERSION_TABLE_FIELDS_BLOB_HEX",
    "decompress_version_body",
    "compress_version_body",
    "zstandard",
)
