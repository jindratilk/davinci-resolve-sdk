"""Small protobuf helpers used by Color Page DB bodies."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Protobuf micro-codec (read/write the VersionBody proto)
# ---------------------------------------------------------------------------

def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    """Read a protobuf varint, return (value, new_offset)."""
    result = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        shift += 7
        if not (byte & 0x80):
            return result, offset
    raise ValueError("Truncated varint")


def _write_varint(value: int) -> bytes:
    """Encode an integer as a protobuf varint."""
    parts = bytearray()
    v = value & 0xFFFFFFFFFFFFFFFF  # treat as unsigned
    while True:
        byte = v & 0x7F
        v >>= 7
        if v:
            parts.append(byte | 0x80)
        else:
            parts.append(byte)
            return bytes(parts)


def _encode_field_tag(field_number: int, wire_type: int) -> bytes:
    return _write_varint((field_number << 3) | wire_type)


def _encode_length_delimited(field_number: int, data: bytes) -> bytes:
    return _encode_field_tag(field_number, 2) + _write_varint(len(data)) + data


def _encode_varint_field(field_number: int, value: int) -> bytes:
    return _encode_field_tag(field_number, 0) + _write_varint(value)


def _encode_fixed32_field(field_number: int, value: bytes) -> bytes:
    return _encode_field_tag(field_number, 5) + value


def _decode_ascii(value: bytes) -> str | None:
    try:
        text = value.decode("ascii")
    except UnicodeDecodeError:
        return None
    if not text:
        return None
    if any(ord(ch) < 32 or ord(ch) > 126 for ch in text):
        return None
    return text



__all__ = (
    "_read_varint",
    "_write_varint",
    "_encode_field_tag",
    "_encode_length_delimited",
    "_encode_varint_field",
    "_encode_fixed32_field",
    "_decode_ascii",
)
