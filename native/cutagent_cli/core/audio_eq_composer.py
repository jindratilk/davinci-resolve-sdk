"""Multi-band EQ composer for DaVinci Resolve Disk DB.

Builds arbitrary multi-band EQ payloads from scratch by constructing
the protobuf structure directly. No more single-band preset limitations.

Format (confirmed 2026-04-05):
  EQ payload = [8B header: 0x00000002 + uint32 body_len] + [0x81 + ZSTD(protobuf)]

  Protobuf:
    repeated field 1 = EQ entries
      Entry[0]: HEADER  (field 1=128, field 3=6)
      Entry[1-N]: BAND   (field 1=126, field 3=6, field 9[0-4] = params)

  Band params (field 9 array, identified by param ID):
    id=101: Filter shape   → field 3.field 1.field 4 = enum (field 1 for bell=0)
    id=102: Gain           → field 3.field 1.field 1 = internal value
    id=103: Frequency      → field 3.field 1.field 1 = Hz
    id=104: Q factor       → field 3.field 1.field 1 = internal value
    id=105: Band index     → field 3.field 1.field 1 = (0,2,4,6,8,10 for B1-B6)

  Shape enum: 0=bell, 1=high-shelf, 2=high-pass, 3=low-shelf, 4=notch, 5=low-pass
  Gain internal: ~333.33 per dB (2000 = +6dB, -2000 = -6dB)
  Q internal: 120 = Q 1.0 (linear scale, 120 per Q unit)
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from ..errors import ValidationError

try:
    import zstandard
except ImportError:
    zstandard = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Shape enum
# ---------------------------------------------------------------------------

SHAPE_BELL = 0
SHAPE_HIGH_SHELF = 1
SHAPE_HIGH_PASS = 2
SHAPE_LOW_SHELF = 3
SHAPE_NOTCH = 4
SHAPE_LOW_PASS = 5

SHAPE_NAMES: dict[int, str] = {
    SHAPE_BELL: "bell",
    SHAPE_HIGH_SHELF: "high-shelf",
    SHAPE_HIGH_PASS: "high-pass",
    SHAPE_LOW_SHELF: "low-shelf",
    SHAPE_NOTCH: "notch",
    SHAPE_LOW_PASS: "low-pass",
}

SHAPE_BY_NAME: dict[str, int] = {v: k for k, v in SHAPE_NAMES.items()}

# Band index mapping
BAND_INDICES = {1: 0, 2: 2, 3: 4, 4: 6, 5: 8, 6: 10}

# Internal value scales (confirmed from preset analysis)
GAIN_SCALE = 333.33  # internal units per dB
Q_SCALE = 120.0  # internal units per Q unit


# ---------------------------------------------------------------------------
# Protobuf micro-encoder
# ---------------------------------------------------------------------------

def _write_varint(value: int) -> bytes:
    parts = bytearray()
    v = value & 0xFFFFFFFFFFFFFFFF
    while True:
        byte = v & 0x7F
        v >>= 7
        if v:
            parts.append(byte | 0x80)
        else:
            parts.append(byte)
            return bytes(parts)


def _encode_tag(field_number: int, wire_type: int) -> bytes:
    return _write_varint((field_number << 3) | wire_type)


def _encode_varint_field(field_number: int, value: int) -> bytes:
    return _encode_tag(field_number, 0) + _write_varint(value)


def _encode_length_delimited(field_number: int, data: bytes) -> bytes:
    return _encode_tag(field_number, 2) + _write_varint(len(data)) + data


# ---------------------------------------------------------------------------
# EQ band data model
# ---------------------------------------------------------------------------

@dataclass
class EqBand:
    """One EQ band configuration."""
    band: int  # 1-6
    shape: int = SHAPE_BELL  # shape enum
    freq_hz: int = 1000  # frequency in Hz
    gain_db: float = 0.0  # gain in dB
    q: float = 1.0  # Q factor

    @property
    def shape_name(self) -> str:
        return SHAPE_NAMES.get(self.shape, f"unknown({self.shape})")

    @property
    def band_index(self) -> int:
        return BAND_INDICES.get(self.band, 0)

    @property
    def gain_internal(self) -> int:
        return round(self.gain_db * GAIN_SCALE)

    @property
    def q_internal(self) -> int:
        return round(self.q * Q_SCALE)

    def to_dict(self) -> dict:
        return {
            "band": self.band,
            "shape": self.shape_name,
            "freq_hz": self.freq_hz,
            "gain_db": self.gain_db,
            "q": self.q,
        }


# ---------------------------------------------------------------------------
# Protobuf builders
# ---------------------------------------------------------------------------

def _build_param_entry(param_id: int, value: int, *, use_field4: bool = False) -> bytes:
    """Build a field 9 param entry: {f1=param_id, f3={f1={f1 or f4=value}}}."""
    if use_field4:
        inner_value = _encode_varint_field(4, value)
    else:
        inner_value = _encode_varint_field(1, value)
    inner = _encode_length_delimited(1, inner_value)
    return (
        _encode_varint_field(1, param_id) +
        _encode_length_delimited(3, inner)
    )


def _build_empty_param() -> bytes:
    """Build an empty field 9 entry."""
    return b""


def _build_shape_param(shape: int) -> bytes:
    """Build shape param (id=101)."""
    if shape == SHAPE_BELL:
        # Bell uses field 1 = 0 (or sometimes field 4 = 0)
        inner_value = _encode_varint_field(1, 0)
    else:
        # Other shapes use field 4
        inner_value = _encode_varint_field(4, shape)
    inner = _encode_length_delimited(1, inner_value)
    return (
        _encode_varint_field(1, 101) +
        _encode_length_delimited(3, inner)
    )


def _build_gain_param(gain_internal: int) -> bytes:
    """Build gain param (id=102)."""
    if gain_internal == 0:
        return b""  # empty = default (0 dB)
    return _build_param_entry(102, gain_internal)


def _build_freq_param(freq_hz: int) -> bytes:
    """Build frequency param (id=103)."""
    return _build_param_entry(103, freq_hz)


def _build_q_param(q_internal: int) -> bytes:
    """Build Q param (id=104)."""
    if q_internal == 120:  # default Q=1.0
        return b""  # empty = default
    return _build_param_entry(104, q_internal)


def _build_band_index_param(band_index: int) -> bytes:
    """Build band index param (id=105)."""
    return _build_param_entry(105, band_index)


def _build_band_entry(band: EqBand) -> bytes:
    """Build a complete band entry (field 1 submessage)."""
    # field 9 slots: [shape, gain, q, freq, band_index]
    # Empty slots are encoded as empty field 9 entries
    shape_data = _build_shape_param(band.shape)
    gain_data = _build_gain_param(band.gain_internal)
    q_data = _build_q_param(band.q_internal)
    freq_data = _build_freq_param(band.freq_hz) if band.freq_hz > 0 else b""
    index_data = _build_band_index_param(band.band_index)

    # Assemble field 9 entries
    f9_entries = b""
    f9_entries += _encode_length_delimited(9, shape_data) if shape_data else _encode_length_delimited(9, b"")
    f9_entries += _encode_length_delimited(9, gain_data) if gain_data else _encode_length_delimited(9, b"")
    f9_entries += _encode_length_delimited(9, q_data) if q_data else _encode_length_delimited(9, b"")
    f9_entries += _encode_length_delimited(9, freq_data) if freq_data else _encode_length_delimited(9, b"")
    f9_entries += _encode_length_delimited(9, index_data)

    return (
        _encode_varint_field(1, 126) +  # band marker
        _encode_varint_field(3, 6) +  # fixed value
        f9_entries
    )


def _build_header_entry() -> bytes:
    """Build the EQ header entry."""
    return (
        _encode_varint_field(1, 128) +  # header marker
        _encode_varint_field(3, 6) +  # 6 bands
        _encode_length_delimited(9, b"")  # empty
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compose_eq_payload(bands: list[EqBand]) -> bytes:
    """Compose a complete multi-band EQ payload ready for EffectFiltersBA.

    Args:
        bands: List of EqBand configurations (1-6 bands).

    Returns:
        Complete binary payload with header + ZSTD compression.
    """
    if not bands:
        raise ValidationError("At least one band is required.")
    if len(bands) > 6:
        raise ValidationError("Maximum 6 EQ bands supported.")

    # Build protobuf
    proto = _encode_length_delimited(1, _build_header_entry())
    for band in bands:
        proto += _encode_length_delimited(1, _build_band_entry(band))

    # ZSTD compress
    if zstandard is None:
        raise RuntimeError("zstandard library required. pip install zstandard")
    cctx = zstandard.ZstdCompressor(level=3)
    compressed = cctx.compress(proto)

    # Add header: 0x00000002 + body length
    body = bytes([0x81]) + compressed
    header = struct.pack(">II", 2, len(body))
    return header + body


def compose_default_eq() -> bytes:
    """Compose the default all-bell EQ (equivalent to Base-AllBell).

    6 bands, all bell shape, default freq/gain/Q.
    """
    bands = [
        EqBand(band=1, shape=SHAPE_BELL, freq_hz=0, gain_db=0.0, q=1.0),
        EqBand(band=2, shape=SHAPE_BELL, freq_hz=1500, gain_db=0.0, q=1.0),
        EqBand(band=3, shape=SHAPE_BELL, freq_hz=1500, gain_db=0.0, q=1.0),
        EqBand(band=4, shape=SHAPE_BELL, freq_hz=1500, gain_db=0.0, q=1.0),
        EqBand(band=5, shape=SHAPE_BELL, freq_hz=1500, gain_db=0.0, q=1.0),
        EqBand(band=6, shape=SHAPE_BELL, freq_hz=0, gain_db=0.0, q=1.0),
    ]
    return compose_eq_payload(bands)


def parse_eq_spec(spec_str: str) -> list[EqBand]:
    """Parse a human-friendly EQ spec string into bands.

    Format: "B1:high-pass@80 B2:bell@1k+6dB/Q2 B3:notch@500 B6:low-pass@12k"

    Each band: B<n>:<shape>@<freq>[+/-<gain>dB][/Q<value>]
    """
    import re

    if not str(spec_str or "").strip():
        raise ValidationError(
            "Fairlight EQ set requires at least one band spec.",
            details={
                "example": "cutagent fairlight eq set \"B1:high-pass@80 B2:bell@1k+6dB/Q2\" --json",
                "format": "B<n>:<shape>@<freq>[+/-<gain>dB][/Q<value>]",
                "valid_shapes": list(SHAPE_BY_NAME.keys()),
            },
        )

    bands = []
    for part in spec_str.strip().split():
        part = part.strip()
        if not part:
            continue

        # Parse band number
        if not part.upper().startswith("B"):
            raise ValidationError(f"Invalid band spec: {part} (must start with B)")
        colon_idx = part.index(":") if ":" in part else -1
        if colon_idx < 0:
            raise ValidationError(f"Invalid band spec: {part} (missing ':')")
        try:
            band_num = int(part[1:colon_idx])
        except ValueError as exc:
            raise ValidationError(
                f"Invalid band number in spec: {part}",
                details={"band": part[1:colon_idx], "valid_bands": list(BAND_INDICES.keys())},
            ) from exc
        if band_num not in BAND_INDICES:
            raise ValidationError(
                f"Invalid EQ band: B{band_num}. Valid bands are B1-B6.",
                details={"band": band_num, "valid_bands": list(BAND_INDICES.keys())},
            )
        rest = part[colon_idx + 1:]

        # Parse shape
        at_idx = rest.index("@") if "@" in rest else len(rest)
        shape_name = rest[:at_idx].lower().strip()
        shape = SHAPE_BY_NAME.get(shape_name)
        if shape is None:
            raise ValidationError(f"Unknown shape: {shape_name}. Valid: {list(SHAPE_BY_NAME.keys())}")

        # Parse freq, gain, Q
        freq_gain_q = rest[at_idx + 1:] if at_idx < len(rest) else ""
        freq_hz = 1000
        gain_db = 0.0
        q = 1.0

        if freq_gain_q:
            # Split on + or - for gain, / for Q
            m = re.fullmatch(r"(\d+(?:\.\d+)?[kK]?)(([+-]\d+(?:\.\d*)?)dB)?(/Q(\d+(?:\.\d*)?))?", freq_gain_q)
            if not m:
                raise ValidationError(
                    f"Invalid EQ band parameters: {part}",
                    details={
                        "band_spec": part,
                        "format": "B<n>:<shape>@<freq>[+/-<gain>dB][/Q<value>]",
                        "example": "B2:bell@1k+6dB/Q2",
                    },
                )
            freq_str = m.group(1)
            if freq_str.lower().endswith("k"):
                freq_hz = int(float(freq_str[:-1]) * 1000)
            else:
                freq_hz = int(float(freq_str))
            if freq_hz <= 0:
                raise ValidationError(
                    f"Invalid EQ frequency in spec: {part}",
                    details={"band_spec": part, "freq_hz": freq_hz},
                )
            if m.group(3):
                gain_db = float(m.group(3))
            if m.group(5):
                q = float(m.group(5))
                if q <= 0:
                    raise ValidationError(
                        f"Invalid EQ Q in spec: {part}",
                        details={"band_spec": part, "q": q},
                    )

        bands.append(EqBand(
            band=band_num,
            shape=shape,
            freq_hz=freq_hz,
            gain_db=gain_db,
            q=q,
        ))

    return bands


def compose_eq_from_spec(conn, spec_str: str) -> dict[str, object]:
    """Parse an EQ spec string and write the composed payload to the current audio clip."""
    bands = parse_eq_spec(spec_str)
    payload = compose_eq_payload(bands)

    cursor = conn.disk_db_cursor()
    result = write_eq_payload_with_cursor(cursor, payload=payload, bands=bands, spec_str=spec_str)
    conn.disk_db_connection().commit()
    return result


def write_eq_payload_with_cursor(
    cursor,
    *,
    payload: bytes,
    bands: list[EqBand],
    spec_str: str,
    audio_item_id: str | None = None,
) -> dict[str, object]:
    """Write a composed EQ payload using an existing mutation transaction."""
    from .audio_eq_db import read_eq_state

    state = read_eq_state(cursor, audio_item_id=audio_item_id)
    resolved_audio_item_id = state.get("audio_item_id")
    if not resolved_audio_item_id:
        raise ValidationError(
            "No audio clip found for Fairlight EQ write.",
            details={"spec": spec_str},
        )

    cursor.execute(
        "UPDATE Sm2TiItem SET EffectFiltersBA = ? WHERE Sm2TiItem_id = ?",
        (payload, resolved_audio_item_id),
    )

    return {
        "audio_item_id": resolved_audio_item_id,
        "band_count": len(bands),
        "bands": [band.to_dict() for band in bands],
    }
