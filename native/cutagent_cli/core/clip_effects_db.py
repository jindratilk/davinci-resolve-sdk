"""Archive-backed EffectFiltersBA writers for clip-level DB mutations."""

from __future__ import annotations

from dataclasses import dataclass
import math
import struct
from typing import Sequence

import zstandard as zstd

from ..errors import ValidationError
from ..fixtures import db_workaround_payloads as fixture_payloads
from .db_timeline_rows import find_ti_item_row, update_row
from .db_timeline_selection import LiveItemRef


@dataclass(frozen=True)
class EffectWrite:
    effect_filters: bytes | None
    fields_blob: bytes | None = None


_AUDIO_GAIN_PREFIX = bytes.fromhex("000000020000001e800a1b087c4a0f085f1a0b0a0911")
_AUDIO_GAIN_SUFFIX = bytes.fromhex("4a004a004a004a00")
_PACKED_HEADER_SIZE = 8
_AUDIO_MIX_FIELDS_ENTRY = bytes.fromhex("0000000200000007800a0220017804")
_AUDIO_MIX_CURVE_FIELD = bytes.fromhex(
    "4a1808631a140a123a1040415e50d79435e5c049000000000000"
)
_FADE_AUDIO_FIELDS_ENTRY = bytes.fromhex(fixture_payloads.FADE_AUDIO_FIELDS_HEX)
_AUDIO_GAIN_FIELDS_ENTRY = bytes.fromhex(fixture_payloads.AUDIO_EFFECT_GAIN_FIELDS_HEX)
_AUDIO_PAN_FIELDS_ENTRY = bytes.fromhex(fixture_payloads.AUDIO_EFFECT_PAN_FIELDS_HEX)
_MANUAL_FADE_AUDIO_EFFECT_START_ENTRY = bytes.fromhex(
    "0000000200000036800a33087c4a004a0f08611a0b0a0911f79cb12d235809404a004a1808631a140a123a1040415e50d79435e5c0490000000000004a00"
)
_MANUAL_GAIN_AND_FADE_AUDIO_ENTRY = bytes.fromhex(
    "00000002000000508128b52ffd20463102000a44087c38004a0f085f1a0b0a091100000000000010404a0f08611a0b0a0911f79cb12d235809404a004a1808631a140a123a1040415e50d79435e5c0490000000000004a00"
)
_BLADE_RIGHT_AUDIO_GAIN_ENTRY = bytes.fromhex(
    "0000000200000038800a35087c38004a0f085f1a0b0a091100000000000000004a004a004a1808631a140a123a1040415e50d79435e5c0490000000000004a00"
)
_MANUAL_FADE_AUDIO_PARAMETER_PER_FRAME = struct.unpack(
    "<d",
    _MANUAL_FADE_AUDIO_EFFECT_START_ENTRY[
        _MANUAL_FADE_AUDIO_EFFECT_START_ENTRY.find(b"\x11", _PACKED_HEADER_SIZE) + 1:
        _MANUAL_FADE_AUDIO_EFFECT_START_ENTRY.find(b"\x11", _PACKED_HEADER_SIZE) + 9
    ],
)[0] / 5.0
MIN_AUDIO_GAIN_DB = -100.0
MAX_AUDIO_GAIN_DB = 60.0
MIN_AUDIO_PAN = -100.0
MAX_AUDIO_PAN = 100.0
MIN_AUDIO_PITCH_SEMITONES = -24
MAX_AUDIO_PITCH_SEMITONES = 24
MIN_AUDIO_PITCH_CENTS = -100
MAX_AUDIO_PITCH_CENTS = 100


def _pack_effect_blob(payload: bytes) -> bytes:
    return struct.pack(">II", 2, len(payload)) + payload


def _pack_compressed_effect_proto(proto: bytes) -> bytes:
    body = b"\x81" + zstd.ZstdCompressor(level=1).compress(bytes(proto))
    return _pack_effect_blob(body)


def _encode_varint(value: int) -> bytes:
    remaining = int(value)
    out = bytearray()
    while True:
        byte = remaining & 0x7F
        remaining >>= 7
        if remaining:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _encode_zigzag(value: int) -> int:
    integer = int(value)
    return (integer << 1) ^ (integer >> 31)


def _encode_int_param(field_id: int, value: int) -> bytes:
    inner = b"\x0A" + _encode_varint(2) + b"\x08" + _encode_varint(_encode_zigzag(int(value)))
    return b"\x4A" + _encode_varint(len(b"\x08" + _encode_varint(field_id) + b"\x1A" + _encode_varint(len(inner)) + inner)) + b"\x08" + _encode_varint(field_id) + b"\x1A" + _encode_varint(len(inner)) + inner


def _encode_double_param(field_id: int, value: float) -> bytes:
    nested = b"\x0A\x09\x11" + struct.pack("<d", float(value))
    message = (
        b"\x08"
        + _encode_varint(int(field_id))
        + b"\x1A"
        + _encode_varint(len(nested))
        + nested
    )
    return b"\x4A" + _encode_varint(len(message)) + message


def _empty_param() -> bytes:
    return b"\x4A\x00"


def validate_audio_gain_db(db_value: float) -> float:
    value = float(db_value)
    if not math.isfinite(value):
        raise ValidationError(
            "Clip audio gain must be a finite dB value.",
            details={"db": str(db_value), "min_db": MIN_AUDIO_GAIN_DB, "max_db": MAX_AUDIO_GAIN_DB},
            recoverability="not_applicable",
        )
    if value < MIN_AUDIO_GAIN_DB or value > MAX_AUDIO_GAIN_DB:
        raise ValidationError(
            f"Clip audio gain must be between {MIN_AUDIO_GAIN_DB:g} and {MAX_AUDIO_GAIN_DB:g} dB.",
            details={"db": value, "min_db": MIN_AUDIO_GAIN_DB, "max_db": MAX_AUDIO_GAIN_DB},
            recoverability="not_applicable",
        )
    return value


def build_audio_gain_payload(db_value: float) -> EffectWrite:
    validated_db = validate_audio_gain_db(db_value)
    payload = bytes.fromhex("800A1B087C4A0F085F1A0B0A09") + b"\x11" + struct.pack("<d", validated_db) + bytes.fromhex("4A004A004A004A00")
    return EffectWrite(
        effect_filters=_pack_effect_blob(payload),
        fields_blob=bytes.fromhex(fixture_payloads.AUDIO_EFFECT_GAIN_FIELDS_HEX),
    )


def parse_audio_gain_payload(effect_filters: bytes | None) -> float | None:
    if effect_filters is None:
        return None
    payload = bytes(effect_filters)
    if len(payload) != len(_AUDIO_GAIN_PREFIX) + 8 + len(_AUDIO_GAIN_SUFFIX):
        return None
    if not payload.startswith(_AUDIO_GAIN_PREFIX) or not payload.endswith(_AUDIO_GAIN_SUFFIX):
        return None
    return float(struct.unpack("<d", payload[len(_AUDIO_GAIN_PREFIX) : len(_AUDIO_GAIN_PREFIX) + 8])[0])


def _parse_varint(payload: bytes, offset: int) -> tuple[int, int] | None:
    value = 0
    shift = 0
    position = int(offset)
    while position < len(payload) and shift <= 63:
        byte = payload[position]
        value |= (byte & 0x7F) << shift
        position += 1
        if not byte & 0x80:
            return value, position
        shift += 7
    return None


def _packed_entry_body(entry: bytes | None) -> bytes:
    payload = bytes(entry or b"")
    if len(payload) >= _PACKED_HEADER_SIZE:
        try:
            version, body_size = struct.unpack(">II", payload[:_PACKED_HEADER_SIZE])
        except struct.error:
            return payload
        if version == 2 and body_size == len(payload) - _PACKED_HEADER_SIZE:
            return payload[_PACKED_HEADER_SIZE:]
    return payload


def _effect_proto(entry: bytes | None) -> bytes:
    body = _packed_entry_body(entry)
    if body[:1] == b"\x80":
        return body[1:]
    if body[:5] == b"\x81\x28\xb5\x2f\xfd":
        try:
            return zstd.ZstdDecompressor().decompress(
                body[1:], max_output_size=16 * 1024 * 1024
            )
        except zstd.ZstdError:
            return body
    return body


@dataclass(frozen=True)
class _WireField:
    number: int
    wire_type: int
    raw: bytes
    value: int | bytes


def _parse_wire_fields(payload: bytes) -> list[_WireField] | None:
    fields: list[_WireField] = []
    offset = 0
    while offset < len(payload):
        start = offset
        key_parsed = _parse_varint(payload, offset)
        if key_parsed is None:
            return None
        key, offset = key_parsed
        number = int(key >> 3)
        wire_type = int(key & 0x07)
        if number <= 0:
            return None
        if wire_type == 0:
            parsed = _parse_varint(payload, offset)
            if parsed is None:
                return None
            value, offset = parsed
        elif wire_type == 1:
            if offset + 8 > len(payload):
                return None
            value = payload[offset : offset + 8]
            offset += 8
        elif wire_type == 2:
            parsed = _parse_varint(payload, offset)
            if parsed is None:
                return None
            length, value_start = parsed
            offset = value_start + length
            if offset > len(payload):
                return None
            value = payload[value_start:offset]
        elif wire_type == 5:
            if offset + 4 > len(payload):
                return None
            value = payload[offset : offset + 4]
            offset += 4
        else:
            return None
        fields.append(
            _WireField(
                number=number,
                wire_type=wire_type,
                raw=payload[start:offset],
                value=value,
            )
        )
    return fields


def _encode_length_delimited_field(field_number: int, value: bytes) -> bytes:
    return (
        _encode_varint((int(field_number) << 3) | 2)
        + _encode_varint(len(value))
        + bytes(value)
    )


def _effect_message_id(message: bytes) -> int | None:
    fields = _parse_wire_fields(message)
    if fields is None:
        return None
    ids = [
        int(field.value)
        for field in fields
        if field.number == 1 and field.wire_type == 0
    ]
    return ids[0] if len(ids) == 1 else None


def _audio_param_id(message: bytes) -> int | None:
    fields = _parse_wire_fields(message)
    if fields is None:
        return None
    ids = [
        int(field.value)
        for field in fields
        if field.number == 1 and field.wire_type == 0
    ]
    return ids[0] if len(ids) == 1 else None


def _effect_message_has_audio_mix_payload(message: bytes) -> bool:
    fields = _parse_wire_fields(message)
    if fields is None:
        return False
    return any(
        field.number == 9
        and field.wire_type == 2
        and isinstance(field.value, bytes)
        and _audio_param_id(field.value) in {95, 97, 98, 99}
        for field in fields
    )


def _repack_effect_proto(entry: bytes, proto: bytes) -> bytes:
    body = _packed_entry_body(entry)
    if body[:1] == b"\x80":
        return _pack_effect_blob(b"\x80" + bytes(proto))
    if body[:5] == b"\x81\x28\xb5\x2f\xfd":
        return _pack_compressed_effect_proto(proto)
    raise ValidationError(
        "The clip audio-mix payload encoding is unsupported.",
        details={"reason": "unsupported_audio_mix_encoding"},
        recoverability="not_applicable",
    )


def _patch_audio_mix_fade_out_entry(
    entry: bytes,
    *,
    fade_out_frames: int | None,
) -> tuple[bytes, bool]:
    proto = _effect_proto(entry)
    top_fields = _parse_wire_fields(proto)
    if top_fields is None:
        raise ValidationError(
            "The clip audio-mix payload is malformed.",
            details={"reason": "malformed_audio_mix_payload"},
            recoverability="not_applicable",
        )

    mix_indices = [
        index
        for index, field in enumerate(top_fields)
        if field.number == 1
        and field.wire_type == 2
        and isinstance(field.value, bytes)
        and _effect_message_id(field.value) == 124
        and _effect_message_has_audio_mix_payload(field.value)
    ]
    if not mix_indices:
        return entry, False
    if len(mix_indices) != 1:
        raise ValidationError(
            "The clip contains more than one audio-mix effect.",
            details={"reason": "ambiguous_audio_mix_effect"},
            recoverability="not_applicable",
        )

    mix_index = mix_indices[0]
    mix_field = top_fields[mix_index]
    assert isinstance(mix_field.value, bytes)
    mix_fields = _parse_wire_fields(mix_field.value)
    if mix_fields is None:
        raise ValidationError(
            "The clip audio-mix effect is malformed.",
            details={"reason": "malformed_audio_mix_effect"},
            recoverability="not_applicable",
        )
    fade_indices = [
        index
        for index, field in enumerate(mix_fields)
        if field.number == 9
        and field.wire_type == 2
        and isinstance(field.value, bytes)
        and _audio_param_id(field.value) == 98
    ]
    if len(fade_indices) > 1:
        raise ValidationError(
            "The clip contains duplicate audio fade-out parameters.",
            details={"reason": "ambiguous_audio_fade_out_parameter"},
            recoverability="not_applicable",
        )

    replacement = (
        None
        if fade_out_frames is None
        else _encode_double_param(98, float(fade_out_frames))
    )
    rebuilt_mix: list[bytes] = []
    inserted = False
    for index, field in enumerate(mix_fields):
        if fade_indices and index == fade_indices[0]:
            if replacement is not None:
                rebuilt_mix.append(replacement)
            inserted = True
            continue
        if (
            not inserted
            and replacement is not None
            and field.number == 9
            and field.wire_type == 2
            and isinstance(field.value, bytes)
            and _audio_param_id(field.value) == 99
        ):
            rebuilt_mix.append(replacement)
            inserted = True
        rebuilt_mix.append(field.raw)
    if replacement is not None and not inserted:
        rebuilt_mix.append(replacement)
        rebuilt_mix.append(_AUDIO_MIX_CURVE_FIELD)

    new_mix = b"".join(rebuilt_mix)
    rebuilt_top = [field.raw for field in top_fields]
    rebuilt_top[mix_index] = _encode_length_delimited_field(1, new_mix)
    return _repack_effect_proto(entry, b"".join(rebuilt_top)), True


_AUDIO_PAN_EFFECT_ID = 144


def _patch_audio_double_param_field(
    field: _WireField,
    *,
    param_id: int,
    value: float,
) -> bytes:
    if (
        field.number != 9
        or field.wire_type != 2
        or not isinstance(field.value, bytes)
        or _audio_param_id(field.value) != int(param_id)
    ):
        raise ValidationError(
            "The clip audio parameter does not match the requested scalar field.",
            details={"reason": "unsupported_audio_parameter_shape"},
            recoverability="not_applicable",
        )

    param_fields = _parse_wire_fields(field.value)
    value_container_indices = [
        index
        for index, param_field in enumerate(param_fields or [])
        if param_field.number == 3
        and param_field.wire_type == 2
        and isinstance(param_field.value, bytes)
    ]
    if param_fields is None or len(value_container_indices) != 1:
        raise ValidationError(
            "The clip audio parameter has an unsupported value structure.",
            details={"reason": "unsupported_audio_parameter_value_structure"},
            recoverability="not_applicable",
        )

    container_index = value_container_indices[0]
    container_field = param_fields[container_index]
    assert isinstance(container_field.value, bytes)
    container_fields = _parse_wire_fields(container_field.value)
    scalar_indices = [
        index
        for index, container_value in enumerate(container_fields or [])
        if container_value.number == 1
        and container_value.wire_type == 2
        and isinstance(container_value.value, bytes)
    ]
    if container_fields is None or len(scalar_indices) != 1:
        raise ValidationError(
            "The clip audio parameter is not a single scalar value.",
            details={"reason": "unsupported_audio_parameter_scalar_structure"},
            recoverability="not_applicable",
        )

    scalar_index = scalar_indices[0]
    scalar_field = container_fields[scalar_index]
    assert isinstance(scalar_field.value, bytes)
    scalar_fields = _parse_wire_fields(scalar_field.value)
    double_indices = [
        index
        for index, scalar_value in enumerate(scalar_fields or [])
        if scalar_value.number == 2 and scalar_value.wire_type == 1
    ]
    if scalar_fields is None or len(double_indices) != 1:
        raise ValidationError(
            "The clip audio parameter scalar is not an unambiguous double value.",
            details={"reason": "unsupported_audio_parameter_double_structure"},
            recoverability="not_applicable",
        )

    rebuilt_scalar = [scalar_value.raw for scalar_value in scalar_fields]
    rebuilt_scalar[double_indices[0]] = b"\x11" + struct.pack("<d", float(value))
    rebuilt_container = [container_value.raw for container_value in container_fields]
    rebuilt_container[scalar_index] = _encode_length_delimited_field(
        1, b"".join(rebuilt_scalar)
    )
    rebuilt_param = [param_field.raw for param_field in param_fields]
    rebuilt_param[container_index] = _encode_length_delimited_field(
        3, b"".join(rebuilt_container)
    )
    return _encode_length_delimited_field(9, b"".join(rebuilt_param))


def _patch_audio_pan_entry(
    entry: bytes,
    *,
    pan_value: float,
) -> tuple[bytes, bool]:
    """Patch one native clip-pan parameter without rebuilding sibling fields."""
    proto = _effect_proto(entry)
    top_fields = _parse_wire_fields(proto)
    if top_fields is None:
        if _is_audio_pan_entry(entry):
            raise ValidationError(
                "The clip audio-pan payload is malformed.",
                details={"reason": "malformed_audio_pan_payload"},
                recoverability="not_applicable",
            )
        return entry, False

    matches: list[tuple[int, list[_WireField], int]] = []
    for top_index, top_field in enumerate(top_fields):
        if (
            top_field.number != 1
            or top_field.wire_type != 2
            or not isinstance(top_field.value, bytes)
            or _effect_message_id(top_field.value) != _AUDIO_PAN_EFFECT_ID
        ):
            continue
        effect_fields = _parse_wire_fields(top_field.value)
        if effect_fields is None:
            raise ValidationError(
                "The clip audio-pan effect is malformed.",
                details={"reason": "malformed_audio_pan_effect"},
                recoverability="not_applicable",
            )
        pan_indices = [
            index
            for index, field in enumerate(effect_fields)
            if field.number == 9
            and field.wire_type == 2
            and isinstance(field.value, bytes)
            and _audio_param_id(field.value) == 96
        ]
        matches.extend((top_index, effect_fields, index) for index in pan_indices)

    if not matches:
        return entry, False
    if len(matches) != 1:
        raise ValidationError(
            "The clip contains more than one audio-pan parameter.",
            details={"reason": "ambiguous_audio_pan_parameter"},
            recoverability="not_applicable",
        )

    top_index, effect_fields, pan_index = matches[0]
    rebuilt_effect = [field.raw for field in effect_fields]
    rebuilt_effect[pan_index] = _patch_audio_double_param_field(
        effect_fields[pan_index],
        param_id=96,
        value=validate_audio_pan_value(pan_value),
    )
    rebuilt_top = [field.raw for field in top_fields]
    rebuilt_top[top_index] = _encode_length_delimited_field(1, b"".join(rebuilt_effect))
    return _repack_effect_proto(entry, b"".join(rebuilt_top)), True


def _merge_audio_pan_preserving_existing_mix(
    *,
    existing_effect_filters: bytes | None,
    existing_fields_blob: bytes | None,
    pan_value: float,
) -> EffectWrite | None:
    entries = split_packed_blob_chain(existing_effect_filters)
    patched_entries: list[bytes] = []
    patched_count = 0
    for entry in entries:
        patched, found = _patch_audio_pan_entry(entry, pan_value=pan_value)
        patched_entries.append(patched)
        patched_count += int(found)
    if patched_count > 1:
        raise ValidationError(
            "The clip contains more than one audio-pan effect.",
            details={"reason": "ambiguous_audio_pan_effect"},
            recoverability="not_applicable",
        )
    if patched_count == 0:
        return None
    return EffectWrite(
        effect_filters=join_packed_blob_chain(patched_entries),
        fields_blob=existing_fields_blob,
    )


def _effect_entry_has_id(entry: bytes | None, effect_id: int) -> bool:
    body = _effect_proto(entry)
    marker = b"\x08" + _encode_varint(int(effect_id))
    return marker in body


def _iter_effect_parameter_payloads(entry: bytes | None) -> list[tuple[int, bytes]]:
    body = _effect_proto(entry)
    params: list[tuple[int, bytes]] = []
    offset = 0
    while offset < len(body):
        marker = body.find(b"\x4A", offset)
        if marker < 0:
            break
        length_parsed = _parse_varint(body, marker + 1)
        if length_parsed is None:
            offset = marker + 1
            continue
        message_length, message_start = length_parsed
        message_end = message_start + message_length
        if message_end > len(body):
            offset = marker + 1
            continue
        message = body[message_start:message_end]
        offset = message_end
        if not message:
            continue
        if message[0] != 0x08:
            continue
        field_parsed = _parse_varint(message, 1)
        if field_parsed is None:
            continue
        field_id, cursor = field_parsed
        if cursor >= len(message) or message[cursor] != 0x1A:
            continue
        payload_length = _parse_varint(message, cursor + 1)
        if payload_length is None:
            continue
        nested_length, nested_start = payload_length
        nested_end = nested_start + nested_length
        if nested_end > len(message):
            continue
        params.append((int(field_id), message[nested_start:nested_end]))
    return params


def _double_from_parameter_payload(payload: bytes) -> float | None:
    marker = payload.find(b"\x11")
    if marker < 0 or marker + 9 > len(payload):
        return None
    return float(struct.unpack("<d", payload[marker + 1: marker + 9])[0])


def find_audio_effect_double_param(entry: bytes | None, *, param_id: int) -> float | None:
    if not _effect_entry_has_id(entry, 124):
        return None
    for field_id, payload in _iter_effect_parameter_payloads(entry):
        if field_id == int(param_id):
            return _double_from_parameter_payload(payload)
    return None


def _find_double_markers(entry: bytes | None) -> list[int]:
    payload = bytes(entry or b"")
    indices: list[int] = []
    offset = _PACKED_HEADER_SIZE
    while offset < len(payload):
        idx = payload.find(b"\x11", offset)
        if idx < 0 or idx + 9 > len(payload):
            break
        indices.append(idx)
        offset = idx + 9
    return indices


def _replace_double(entry: bytes | None, marker_index: int, value: float) -> bytes:
    payload = bytearray(entry or b"")
    markers = _find_double_markers(payload)
    if marker_index < 0 or marker_index >= len(markers):
        return bytes(payload)
    idx = markers[marker_index]
    payload[idx + 1: idx + 9] = struct.pack("<d", float(value))
    return bytes(payload)


def _zero_double(entry: bytes | None, marker_index: int) -> bytes:
    return _replace_double(entry, marker_index, 0.0)


_FIXTURE_FADE_START_TEMPLATE = _zero_double(bytes.fromhex(fixture_payloads.FADE_AUDIO_EFFECT_START_HEX), 0)
_LEGACY_FALSE_FADE_END_TEMPLATE = _zero_double(
    bytes.fromhex(fixture_payloads.FADE_AUDIO_EFFECT_END_HEX), 0
)
_MANUAL_FADE_TEMPLATE = _zero_double(_MANUAL_FADE_AUDIO_EFFECT_START_ENTRY, 0)
_MANUAL_GAIN_AND_FADE_TEMPLATE = _zero_double(_zero_double(_MANUAL_GAIN_AND_FADE_AUDIO_ENTRY, 0), 1)


def split_packed_blob_chain(blob: bytes | None) -> list[bytes]:
    if not blob:
        return []
    payload = bytes(blob)
    entries: list[bytes] = []
    offset = 0
    while offset < len(payload):
        if offset + _PACKED_HEADER_SIZE > len(payload):
            return [payload]
        version, body_size = struct.unpack(">II", payload[offset: offset + _PACKED_HEADER_SIZE])
        if version != 2 or body_size < 0:
            return [payload]
        entry_end = offset + _PACKED_HEADER_SIZE + body_size
        if entry_end > len(payload):
            return [payload]
        entries.append(payload[offset:entry_end])
        offset = entry_end
    return entries


def join_packed_blob_chain(entries: Sequence[bytes]) -> bytes | None:
    packed = [bytes(entry) for entry in entries if entry]
    if not packed:
        return None
    return b"".join(packed)


def _is_audio_gain_entry(entry: bytes | None) -> bool:
    if not entry:
        return False
    payload = bytes(entry)
    if parse_audio_gain_payload(payload) is not None:
        return True
    if find_audio_effect_double_param(payload, param_id=95) is not None:
        return True
    return _zero_double(_zero_double(payload, 0), 1) == _MANUAL_GAIN_AND_FADE_TEMPLATE


def _audio_fade_entry_edge(entry: bytes | None) -> str | None:
    if not entry:
        return None
    payload = bytes(entry)
    masked_first = _zero_double(payload, 0)
    if masked_first in {_FIXTURE_FADE_START_TEMPLATE, _MANUAL_FADE_TEMPLATE}:
        return "start"
    if _zero_double(masked_first, 1) == _MANUAL_GAIN_AND_FADE_TEMPLATE:
        return "start"
    if find_audio_effect_double_param(payload, param_id=98) is not None:
        return "end"
    if find_audio_effect_double_param(payload, param_id=97) is not None:
        return "start"
    return None


def _is_audio_fade_entry(entry: bytes | None) -> bool:
    if not entry:
        return False
    payload = bytes(entry)
    return (
        _audio_fade_entry_edge(payload) is not None
        or find_audio_effect_double_param(payload, param_id=98) is not None
    )


def _canonical_audio_mix_entry_is_rebuildable(entry: bytes | None) -> bool:
    proto = _effect_proto(entry)
    if not proto.startswith(b"\x0A"):
        return False
    outer_length = _parse_varint(proto, 1)
    if outer_length is None:
        return False
    effect_length, effect_start = outer_length
    effect_end = effect_start + effect_length
    if effect_end != len(proto):
        return False
    effect = proto[effect_start:effect_end]
    if not effect.startswith(b"\x08\x7c"):
        return False
    # DaVinci Resolve may omit the default zero-valued field 7 when it saves
    # an otherwise canonical mix. Nonzero/unknown fields still fail below.
    cursor = 4 if effect[2:4] == b"\x38\x00" else 2
    while cursor < len(effect):
        if effect[cursor] != 0x4A:
            return False
        length_parsed = _parse_varint(effect, cursor + 1)
        if length_parsed is None:
            return False
        message_length, message_start = length_parsed
        message_end = message_start + message_length
        if message_end > len(effect):
            return False
        message = effect[message_start:message_end]
        field = effect[cursor:message_end]
        cursor = message_end
        if not message:
            continue
        if message[:1] != b"\x08":
            return False
        field_id_parsed = _parse_varint(message, 1)
        if field_id_parsed is None:
            return False
        field_id, payload_marker = field_id_parsed
        if payload_marker >= len(message) or message[payload_marker] != 0x1A:
            return False
        payload_length_parsed = _parse_varint(message, payload_marker + 1)
        if payload_length_parsed is None:
            return False
        payload_length, payload_start = payload_length_parsed
        if payload_start + payload_length != len(message):
            return False
        if field_id in {95, 96, 97, 98}:
            if _double_from_parameter_payload(message[payload_start:]) is None:
                return False
            continue
        if field_id == 99 and field == _AUDIO_MIX_CURVE_FIELD:
            continue
        return False
    return True


def _audio_mix_entry_is_safe_to_rebuild(entry: bytes | None) -> bool:
    payload = bytes(entry or b"")
    if _canonical_audio_mix_entry_is_rebuildable(payload):
        return True
    if parse_audio_gain_payload(payload) is not None:
        return True
    if _zero_double(payload, 0) == build_audio_pan_payload(0.0).effect_filters:
        return True
    masked_first = _zero_double(payload, 0)
    if masked_first in {
        _FIXTURE_FADE_START_TEMPLATE,
        _LEGACY_FALSE_FADE_END_TEMPLATE,
        _MANUAL_FADE_TEMPLATE,
    }:
        return True
    return _zero_double(masked_first, 1) == _MANUAL_GAIN_AND_FADE_TEMPLATE


def _decode_fade_frames_from_entry(entry: bytes | None, *, edge: str | None = None) -> int | None:
    if not entry:
        return None
    payload = bytes(entry)
    entry_edge = _audio_fade_entry_edge(payload)
    if edge == "end":
        native_end = find_audio_effect_double_param(payload, param_id=98)
        if native_end is not None:
            return max(1, int(round(native_end)))
        return None
    if edge == "start":
        native_start = find_audio_effect_double_param(payload, param_id=97)
        if native_start is not None:
            return max(
                1,
                int(round(native_start / _MANUAL_FADE_AUDIO_PARAMETER_PER_FRAME)),
            )
    if edge is not None and entry_edge != edge:
        return None
    markers = _find_double_markers(payload)
    if not markers:
        return None
    masked_first = _zero_double(payload, 0)
    if masked_first == _FIXTURE_FADE_START_TEMPLATE:
        idx = markers[0]
        return max(1, int(round(struct.unpack("<d", payload[idx + 1: idx + 9])[0])))
    if masked_first == _MANUAL_FADE_TEMPLATE:
        idx = markers[0]
        value = struct.unpack("<d", payload[idx + 1: idx + 9])[0]
        return max(1, int(round(value / _MANUAL_FADE_AUDIO_PARAMETER_PER_FRAME)))
    if _zero_double(masked_first, 1) == _MANUAL_GAIN_AND_FADE_TEMPLATE and len(markers) >= 2:
        idx = markers[1]
        value = struct.unpack("<d", payload[idx + 1: idx + 9])[0]
        return max(1, int(round(value / _MANUAL_FADE_AUDIO_PARAMETER_PER_FRAME)))
    generic_fade = find_audio_effect_double_param(payload, param_id=97)
    if generic_fade is not None and edge is None:
        return max(1, int(round(generic_fade / _MANUAL_FADE_AUDIO_PARAMETER_PER_FRAME)))
    return None


def find_audio_gain_db(effect_filters: bytes | None) -> float | None:
    for entry in split_packed_blob_chain(effect_filters):
        parsed = parse_audio_gain_payload(entry)
        if parsed is not None:
            return float(parsed)
        generic = find_audio_effect_double_param(entry, param_id=95)
        if generic is not None:
            return float(generic)
        payload = bytes(entry)
        if _zero_double(_zero_double(payload, 0), 1) == _MANUAL_GAIN_AND_FADE_TEMPLATE:
            markers = _find_double_markers(payload)
            if markers:
                idx = markers[0]
                return float(struct.unpack("<d", payload[idx + 1: idx + 9])[0])
    return None


def _is_audio_pan_entry(entry: bytes | None) -> bool:
    return find_audio_effect_double_param(entry, param_id=96) is not None


def find_audio_pan_value(effect_filters: bytes | None) -> float | None:
    return next(
        (
            float(value)
            for value in (
                find_audio_effect_double_param(entry, param_id=96)
                for entry in split_packed_blob_chain(effect_filters)
            )
            if value is not None
        ),
        None,
    )


def _find_audio_fade_frames(effect_filters: bytes | None, *, edge: str) -> int | None:
    return next(
        (
            frames
            for frames in (
                _decode_fade_frames_from_entry(entry, edge=edge)
                for entry in split_packed_blob_chain(effect_filters)
            )
            if frames is not None
        ),
        None,
    )


def find_audio_fade_in_frames(effect_filters: bytes | None) -> int | None:
    return _find_audio_fade_frames(effect_filters, edge="start")


def find_audio_fade_out_frames(effect_filters: bytes | None) -> int | None:
    return _find_audio_fade_frames(effect_filters, edge="end")


def has_audio_fade_entry(effect_filters: bytes | None) -> bool:
    return any(_is_audio_fade_entry(entry) for entry in split_packed_blob_chain(effect_filters))


def blade_right_audio_effect_filters(effect_filters: bytes | None) -> tuple[bytes | None, str]:
    """Return a native-blade-like right-side audio effect chain."""
    entries = split_packed_blob_chain(effect_filters)
    if not entries:
        return effect_filters, "none"

    changed = False
    transformed: list[bytes] = []
    preserved_unknown = False
    for entry in entries:
        payload = bytes(entry)
        if _zero_double(_zero_double(payload, 0), 1) == _MANUAL_GAIN_AND_FADE_TEMPLATE:
            gain_db = find_audio_effect_double_param(payload, param_id=95)
            if gain_db is None:
                gain_db = find_audio_gain_db(payload)
            if gain_db is not None:
                transformed.append(_replace_double(_BLADE_RIGHT_AUDIO_GAIN_ENTRY, 0, float(gain_db)))
                changed = True
                continue
        if find_audio_effect_double_param(payload, param_id=97) is not None:
            preserved_unknown = True
        transformed.append(payload)

    return (
        join_packed_blob_chain(transformed),
        "removed_start_fade" if changed else ("preserved_unknown" if preserved_unknown else "preserved"),
    )


def build_audio_fade_in_payload(*, fade_in_frames: int) -> EffectWrite:
    frames = max(1, int(fade_in_frames))
    encoded_value = float(frames) * float(_MANUAL_FADE_AUDIO_PARAMETER_PER_FRAME)
    return EffectWrite(
        effect_filters=_replace_double(_MANUAL_FADE_AUDIO_EFFECT_START_ENTRY, 0, encoded_value),
        fields_blob=bytes(_FADE_AUDIO_FIELDS_ENTRY),
    )


def build_audio_fade_out_payload(*, fade_out_frames: int) -> EffectWrite:
    frames = max(1, int(fade_out_frames))
    effect = b"\x08\x7c\x38\x00" + _encode_double_param(98, float(frames))
    effect += _AUDIO_MIX_CURVE_FIELD + b"\x4a\x00"
    proto = b"\x0a" + _encode_varint(len(effect)) + effect
    return EffectWrite(
        effect_filters=_pack_compressed_effect_proto(proto),
        fields_blob=bytes(_AUDIO_MIX_FIELDS_ENTRY),
    )


def build_audio_gain_and_fade_payload(
    *,
    gain_db: float,
    fade_in_frames: int,
    fade_out_frames: int | None = None,
) -> EffectWrite:
    validated_db = validate_audio_gain_db(gain_db)
    encoded_fade_value = float(max(1, int(fade_in_frames))) * float(_MANUAL_FADE_AUDIO_PARAMETER_PER_FRAME)
    effect = b"\x08\x7c\x38\x00"
    effect += _encode_double_param(95, validated_db)
    effect += _encode_double_param(97, encoded_fade_value)
    if fade_out_frames is not None and int(fade_out_frames) > 0:
        effect += _encode_double_param(98, float(int(fade_out_frames)))
    effect += _AUDIO_MIX_CURVE_FIELD + b"\x4a\x00"
    proto = b"\x0a" + _encode_varint(len(effect)) + effect
    return EffectWrite(
        effect_filters=_pack_compressed_effect_proto(proto),
        fields_blob=bytes(_AUDIO_MIX_FIELDS_ENTRY),
    )


def _merge_audio_fade_out_preserving_existing_mix(
    *,
    existing_effect_filters: bytes | None,
    existing_fields_blob: bytes | None,
    fade_out_frames: int | None,
) -> EffectWrite:
    entries = split_packed_blob_chain(existing_effect_filters)
    retained_entries = [
        entry
        for entry in entries
        if _zero_double(entry, 0) != _LEGACY_FALSE_FADE_END_TEMPLATE
    ]
    patched_entries: list[bytes] = []
    patched_count = 0
    for entry in retained_entries:
        patched, found = _patch_audio_mix_fade_out_entry(
            entry,
            fade_out_frames=fade_out_frames,
        )
        patched_entries.append(patched)
        patched_count += int(found)
    if patched_count > 1:
        raise ValidationError(
            "The clip contains more than one audio-mix effect.",
            details={"reason": "ambiguous_audio_mix_effect"},
            recoverability="not_applicable",
        )
    if patched_count == 0 and fade_out_frames is not None:
        created = build_audio_fade_out_payload(fade_out_frames=fade_out_frames)
        if created.effect_filters is not None:
            patched_entries.append(created.effect_filters)
    fields_blob = existing_fields_blob
    if fields_blob is None and fade_out_frames is not None:
        fields_blob = bytes(_AUDIO_MIX_FIELDS_ENTRY)
    return EffectWrite(
        effect_filters=join_packed_blob_chain(patched_entries),
        fields_blob=fields_blob,
    )


def merge_audio_effect_chains(
    *,
    existing_effect_filters: bytes | None,
    existing_fields_blob: bytes | None,
    gain_db: float | None = None,
    pan_value: float | None = None,
    fade_in_frames: int | None = None,
    fade_out_frames: int | None = None,
) -> EffectWrite:
    rebuild_known = gain_db is not None or pan_value is not None or fade_in_frames is not None or fade_out_frames is not None
    if not rebuild_known:
        return EffectWrite(effect_filters=existing_effect_filters, fields_blob=existing_fields_blob)
    if (
        fade_out_frames is not None
        and gain_db is None
        and pan_value is None
        and fade_in_frames is None
    ):
        requested_fade_out = (
            int(fade_out_frames) if int(fade_out_frames) > 0 else None
        )
        return _merge_audio_fade_out_preserving_existing_mix(
            existing_effect_filters=existing_effect_filters,
            existing_fields_blob=existing_fields_blob,
            fade_out_frames=requested_fade_out,
        )
    if (
        pan_value is not None
        and gain_db is None
        and fade_in_frames is None
        and fade_out_frames is None
    ):
        patched_pan = _merge_audio_pan_preserving_existing_mix(
            existing_effect_filters=existing_effect_filters,
            existing_fields_blob=existing_fields_blob,
            pan_value=validate_audio_pan_value(float(pan_value)),
        )
        if patched_pan is not None:
            return patched_pan

    existing_gain_db = find_audio_gain_db(existing_effect_filters)
    existing_pan_value = find_audio_pan_value(existing_effect_filters)
    existing_fade_in_frames = find_audio_fade_in_frames(existing_effect_filters)
    existing_fade_out_frames = find_audio_fade_out_frames(existing_effect_filters)
    target_gain_db = existing_gain_db if gain_db is None else validate_audio_gain_db(float(gain_db))
    target_pan_value = existing_pan_value if pan_value is None else validate_audio_pan_value(float(pan_value))
    target_fade_in_frames = (
        existing_fade_in_frames
        if fade_in_frames is None
        else (int(fade_in_frames) if int(fade_in_frames) > 0 else None)
    )
    target_fade_out_frames = (
        existing_fade_out_frames
        if fade_out_frames is None
        else (int(fade_out_frames) if int(fade_out_frames) > 0 else None)
    )
    want_combined = (
        target_gain_db is not None
        and target_fade_in_frames is not None
        and int(target_fade_in_frames) > 0
    )

    existing_effect_entries = split_packed_blob_chain(existing_effect_filters)
    for entry in existing_effect_entries:
        is_rebuilt = (
            _is_audio_gain_entry(entry)
            or _is_audio_pan_entry(entry)
            or _is_audio_fade_entry(entry)
        )
        if is_rebuilt and not _audio_mix_entry_is_safe_to_rebuild(entry):
            raise ValidationError(
                "The clip audio-mix payload contains unsupported fields and cannot be safely rebuilt.",
                details={"reason": "unsupported_compound_audio_mix_payload"},
                recoverability="not_applicable",
            )
    effect_entries = [
        entry
        for entry in existing_effect_entries
        if not (
            _is_audio_gain_entry(entry)
            or _is_audio_pan_entry(entry)
            or _is_audio_fade_entry(entry)
        )
    ]
    fields_entries = [
        entry
        for entry in split_packed_blob_chain(existing_fields_blob)
        if entry not in {_AUDIO_GAIN_FIELDS_ENTRY, _AUDIO_PAN_FIELDS_ENTRY, _FADE_AUDIO_FIELDS_ENTRY}
    ]

    if want_combined:
        combined = build_audio_gain_and_fade_payload(
            gain_db=float(target_gain_db),
            fade_in_frames=int(target_fade_in_frames),
            fade_out_frames=target_fade_out_frames,
        )
        if combined.effect_filters:
            effect_entries.append(combined.effect_filters)
        if combined.fields_blob and combined.fields_blob not in fields_entries:
            fields_entries.append(combined.fields_blob)
    elif target_gain_db is not None:
        gain_write = build_audio_gain_payload(float(target_gain_db))
        if gain_write.effect_filters:
            effect_entries.append(gain_write.effect_filters)
        if gain_write.fields_blob and gain_write.fields_blob not in fields_entries:
            fields_entries.append(gain_write.fields_blob)
    elif target_fade_in_frames is not None and int(target_fade_in_frames) > 0:
        fade_write = build_audio_fade_in_payload(fade_in_frames=int(target_fade_in_frames))
        if fade_write.effect_filters:
            effect_entries.append(fade_write.effect_filters)
        if fade_write.fields_blob and fade_write.fields_blob not in fields_entries:
            fields_entries.append(fade_write.fields_blob)
    if (
        not want_combined
        and target_fade_out_frames is not None
        and int(target_fade_out_frames) > 0
    ):
        fade_write = build_audio_fade_out_payload(fade_out_frames=int(target_fade_out_frames))
        if fade_write.effect_filters:
            effect_entries.append(fade_write.effect_filters)
        if fade_write.fields_blob and fade_write.fields_blob not in fields_entries:
            fields_entries.append(fade_write.fields_blob)
    if target_pan_value is not None:
        pan_write = build_audio_pan_payload(float(target_pan_value))
        if pan_write.effect_filters:
            effect_entries.append(pan_write.effect_filters)
        if pan_write.fields_blob and pan_write.fields_blob not in fields_entries:
            fields_entries.append(pan_write.fields_blob)

    deduped_fields: list[bytes] = []
    seen_fields: set[bytes] = set()
    for entry in fields_entries:
        key = bytes(entry)
        if key in seen_fields:
            continue
        deduped_fields.append(key)
        seen_fields.add(key)

    return EffectWrite(
        effect_filters=join_packed_blob_chain(effect_entries),
        fields_blob=join_packed_blob_chain(deduped_fields),
    )


def read_current_audio_gain(
    cursor,
    *,
    audio_item: LiveItemRef,
    timeline_name: str | None = None,
) -> float:
    audio_row = find_ti_item_row(cursor, item=audio_item, db_type="Sm2TiAudioClip", timeline_name=timeline_name)
    parsed = find_audio_gain_db(audio_row.get("EffectFiltersBA"))
    return 0.0 if parsed is None else parsed


def build_audio_pan_payload(value: float) -> EffectWrite:
    validated_value = validate_audio_pan_value(value)
    payload = bytes.fromhex("800A0C087C4A004A004A004A004A000A140890014A0F08601A0B0A09") + b"\x11" + struct.pack("<d", validated_value)
    return EffectWrite(
        effect_filters=_pack_effect_blob(payload),
        fields_blob=bytes.fromhex(fixture_payloads.AUDIO_EFFECT_PAN_FIELDS_HEX),
    )


def validate_audio_pan_value(value: float) -> float:
    pan_value = float(value)
    if not math.isfinite(pan_value):
        raise ValidationError(
            "Clip audio pan must be a finite value.",
            details={"value": str(value), "min_value": MIN_AUDIO_PAN, "max_value": MAX_AUDIO_PAN},
            recoverability="not_applicable",
        )
    if pan_value < MIN_AUDIO_PAN or pan_value > MAX_AUDIO_PAN:
        raise ValidationError(
            f"Clip audio pan must be between {MIN_AUDIO_PAN:g} and {MAX_AUDIO_PAN:g}.",
            details={"value": pan_value, "min_value": MIN_AUDIO_PAN, "max_value": MAX_AUDIO_PAN},
            recoverability="not_applicable",
        )
    return pan_value


_PITCH_EFFECT_ID = 134
_PITCH_SEMITONES_FIELD_ID = 140
_PITCH_CENTS_FIELD_ID = 141


def validate_audio_pitch_values(semitones: int, cents: int = 0) -> tuple[int, int]:
    semitone_value = int(semitones)
    cents_value = int(cents)
    if semitone_value < MIN_AUDIO_PITCH_SEMITONES or semitone_value > MAX_AUDIO_PITCH_SEMITONES:
        raise ValidationError(
            f"Clip audio pitch semitones must be between {MIN_AUDIO_PITCH_SEMITONES} and {MAX_AUDIO_PITCH_SEMITONES}.",
            details={
                "semitones": semitone_value,
                "min_semitones": MIN_AUDIO_PITCH_SEMITONES,
                "max_semitones": MAX_AUDIO_PITCH_SEMITONES,
            },
            recoverability="not_applicable",
        )
    if cents_value < MIN_AUDIO_PITCH_CENTS or cents_value > MAX_AUDIO_PITCH_CENTS:
        raise ValidationError(
            f"Clip audio pitch cents must be between {MIN_AUDIO_PITCH_CENTS} and {MAX_AUDIO_PITCH_CENTS}.",
            details={
                "cents": cents_value,
                "min_cents": MIN_AUDIO_PITCH_CENTS,
                "max_cents": MAX_AUDIO_PITCH_CENTS,
            },
            recoverability="not_applicable",
        )
    return semitone_value, cents_value


def build_audio_pitch_payload(semitones: int, cents: int = 0) -> EffectWrite:
    semitone_value, cents_value = validate_audio_pitch_values(semitones, cents)
    params = _encode_int_param(_PITCH_SEMITONES_FIELD_ID, semitone_value)
    params += _encode_int_param(_PITCH_CENTS_FIELD_ID, cents_value) if cents_value != 0 else _empty_param()
    body_rest = b"\x08" + _encode_varint(_PITCH_EFFECT_ID) + params
    payload = b"\x80\x0A" + _encode_varint(len(body_rest)) + body_rest
    return EffectWrite(
        effect_filters=_pack_effect_blob(payload),
        fields_blob=bytes.fromhex(fixture_payloads.AUDIO_EFFECT_PITCH_FIELDS_HEX),
    )


def _replace_duration(effect_hex: str, duration_frames: int) -> bytes:
    packed = bytes.fromhex(effect_hex)
    marker = b"\x11"
    idx = packed.rfind(marker)
    if idx < 0 or idx + 9 > len(packed):
        raise ValidationError("Archive fade payload is invalid.")
    return packed[: idx + 1] + struct.pack("<d", float(duration_frames)) + packed[idx + 9 :]


def build_fade_in_payloads(
    *,
    edge: str = "start",
    video_duration_frames: int = 44,
    audio_duration_frames: int = 18,
) -> tuple[EffectWrite, EffectWrite]:
    edge = normalize_fade_edge(edge)

    if edge == "both":
        video_payload = _replace_duration(fixture_payloads.FADE_VIDEO_EFFECT_START_HEX, video_duration_frames) + _replace_duration(
            fixture_payloads.FADE_VIDEO_EFFECT_END_HEX, video_duration_frames
        )
        audio_payload = _replace_duration(fixture_payloads.FADE_AUDIO_EFFECT_START_HEX, audio_duration_frames) + _replace_duration(
            fixture_payloads.FADE_AUDIO_EFFECT_END_HEX, audio_duration_frames
        )
    elif edge == "end":
        video_payload = _replace_duration(fixture_payloads.FADE_VIDEO_EFFECT_END_HEX, video_duration_frames)
        audio_payload = _replace_duration(fixture_payloads.FADE_AUDIO_EFFECT_END_HEX, audio_duration_frames)
    else:
        video_payload = _replace_duration(fixture_payloads.FADE_VIDEO_EFFECT_START_HEX, video_duration_frames)
        audio_payload = _replace_duration(fixture_payloads.FADE_AUDIO_EFFECT_START_HEX, audio_duration_frames)

    return (
        EffectWrite(effect_filters=video_payload, fields_blob=bytes.fromhex(fixture_payloads.FADE_VIDEO_FIELDS_HEX)),
        EffectWrite(effect_filters=audio_payload, fields_blob=bytes.fromhex(fixture_payloads.FADE_AUDIO_FIELDS_HEX)),
    )


def normalize_fade_scope(scope: str) -> str:
    normalized = str(scope).strip().lower()
    if normalized not in {"linked", "video", "audio"}:
        raise ValidationError(
            "Fade scope must be linked, video, or audio.",
            details={"scope": scope},
            recoverability="not_applicable",
        )
    return normalized


def normalize_fade_edge(edge: str) -> str:
    normalized = str(edge).strip().lower()
    if normalized not in {"start", "end", "both"}:
        raise ValidationError(
            "Fade edge must be start, end, or both.",
            details={"edge": edge},
            recoverability="not_applicable",
        )
    return normalized


def apply_audio_effect(
    cursor,
    *,
    audio_item: LiveItemRef,
    write: EffectWrite,
    effect_name: str,
    timeline_name: str | None = None,
) -> dict[str, object]:
    audio_row = find_ti_item_row(cursor, item=audio_item, db_type="Sm2TiAudioClip", timeline_name=timeline_name)
    updates: dict[str, object] = {"EffectFiltersBA": write.effect_filters}
    if write.fields_blob is not None:
        updates["FieldsBlob"] = write.fields_blob
    update_row(cursor, "Sm2TiItem", "Sm2TiItem_id", audio_row["Sm2TiItem_id"], updates)
    return {"effect": effect_name, "audio_item_id": audio_row["Sm2TiItem_id"]}


def apply_fade_in(
    cursor,
    *,
    video_item: LiveItemRef | None,
    audio_item: LiveItemRef | None,
    scope: str,
    edge: str,
    video_duration_frames: int | None,
    audio_duration_frames: int | None,
    timeline_name: str | None = None,
) -> dict[str, object]:
    scope = normalize_fade_scope(scope)
    edge = normalize_fade_edge(edge)
    if scope in {"linked", "video"} and video_item is None:
        raise ValidationError("Fade-in requires a video item for the requested scope.", details={"scope": scope})
    if scope in {"linked", "audio"} and audio_item is None:
        raise ValidationError("Fade-in requires an audio item for the requested scope.", details={"scope": scope})

    video_write, audio_write = build_fade_in_payloads(
        edge=edge,
        video_duration_frames=int(video_duration_frames or 44),
        audio_duration_frames=int(audio_duration_frames or 18),
    )

    video_row = None
    audio_row = None
    if scope in {"linked", "video"} and video_item is not None:
        video_row = find_ti_item_row(cursor, item=video_item, db_type="Sm2TiVideoClip", timeline_name=timeline_name)
        update_row(
            cursor,
            "Sm2TiItem",
            "Sm2TiItem_id",
            video_row["Sm2TiItem_id"],
            {"EffectFiltersBA": video_write.effect_filters, "FieldsBlob": video_write.fields_blob},
        )
    if scope in {"linked", "audio"} and audio_item is not None:
        audio_row = find_ti_item_row(cursor, item=audio_item, db_type="Sm2TiAudioClip", timeline_name=timeline_name)
        update_row(
            cursor,
            "Sm2TiItem",
            "Sm2TiItem_id",
            audio_row["Sm2TiItem_id"],
            {"EffectFiltersBA": audio_write.effect_filters, "FieldsBlob": audio_write.fields_blob},
        )
    return {
        "effect": "fade-in",
        "video_item_id": video_row["Sm2TiItem_id"] if video_row else None,
        "audio_item_id": audio_row["Sm2TiItem_id"] if audio_row else None,
        "scope": scope,
        "edge": edge,
        "video_duration_frames": video_duration_frames,
        "audio_duration_frames": audio_duration_frames,
    }
