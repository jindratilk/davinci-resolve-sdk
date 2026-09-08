"""Archive-backed DaVinci Resolve native clip EQ preset writers."""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import ValidationError
from ..fixtures import db_workaround_payloads as fixture_payloads
from . import db_timeline_rows
from .audio_eq_composer import EqBand, SHAPE_BY_NAME, compose_eq_payload


@dataclass(frozen=True)
class AudioEqPreset:
    key: str
    effect_filters_hex: str
    family: str
    summary: str


@dataclass(frozen=True)
class AudioEqSpec:
    mode: str
    preset: str | None
    filter_type: str
    band: int | None
    freq_hz: int | None
    gain_db: float | None
    q: float | None
    effect_filters: bytes
    family: str
    summary: str
    ui_band: int | None = None


_PRESETS: dict[str, AudioEqPreset] = {
    "voice-presence-1k-6db": AudioEqPreset(
        key="voice-presence-1k-6db",
        effect_filters_hex=fixture_payloads.AUDIO_EQ_PRESET_VOICE_PRESENCE_1K_6DB_EFFECT_HEX,
        family="resolve20_clip_eq_archive_v2",
        summary="Bell band at 1 kHz boosted by +6 dB (Q=1.0).",
    ),
    "voice-dip-1k-6db": AudioEqPreset(
        key="voice-dip-1k-6db",
        effect_filters_hex=fixture_payloads.AUDIO_EQ_PRESET_VOICE_DIP_1K_MINUS_6DB_EFFECT_HEX,
        family="resolve20_clip_eq_archive_v2",
        summary="Bell band at 1 kHz cut by -6 dB (Q=1.0).",
    ),
    "presence-2k-6db": AudioEqPreset(
        key="presence-2k-6db",
        effect_filters_hex=fixture_payloads.AUDIO_EQ_PRESET_PRESENCE_2K_6DB_EFFECT_HEX,
        family="resolve20_clip_eq_archive_v2",
        summary="Bell band at 2 kHz boosted by +6 dB (Q=1.0).",
    ),
    "high-pass-80hz": AudioEqPreset(
        key="high-pass-80hz",
        effect_filters_hex=fixture_payloads.AUDIO_EQ_PRESET_HIGH_PASS_80HZ_EFFECT_HEX,
        family="resolve20_clip_eq_archive_v2",
        summary="High-pass filter at 80 Hz.",
    ),
    "low-pass-12000hz": AudioEqPreset(
        key="low-pass-12000hz",
        effect_filters_hex=fixture_payloads.AUDIO_EQ_PRESET_LOW_PASS_12000HZ_EFFECT_HEX,
        family="resolve20_clip_eq_archive_v2",
        summary="Low-pass filter at 12 kHz.",
    ),
}

_PRESET_ALIASES = {
    "voice-presence-1k-6db": "voice-presence-1k-6db",
    "voice_presence_1k_6db": "voice-presence-1k-6db",
    "presence": "voice-presence-1k-6db",
    "voice": "voice-presence-1k-6db",
    "voice-presence": "voice-presence-1k-6db",
    "1k-6db": "voice-presence-1k-6db",
    "voice-dip-1k-6db": "voice-dip-1k-6db",
    "voice_dip_1k_6db": "voice-dip-1k-6db",
    "1k-minus-6db": "voice-dip-1k-6db",
    "1k-cut": "voice-dip-1k-6db",
    "presence-2k-6db": "presence-2k-6db",
    "presence_2k_6db": "presence-2k-6db",
    "2k-6db": "presence-2k-6db",
    "2k-boost": "presence-2k-6db",
    "high-pass-80hz": "high-pass-80hz",
    "high_pass_80hz": "high-pass-80hz",
    "hpf-80": "high-pass-80hz",
    "hpf80": "high-pass-80hz",
    "low-pass-12000hz": "low-pass-12000hz",
    "low_pass_12000hz": "low-pass-12000hz",
    "lpf-12000": "low-pass-12000hz",
    "lpf12000": "low-pass-12000hz",
}

_BELL_1K_PLUS6_GAIN_CHUNK = bytes.fromhex("08681A040A020878")
_BELL_2K_PLUS6_GAIN_CHUNK = bytes.fromhex("08681A040A020878")
_BELL_BAND3_5_PLUS6_GAIN_CHUNK = bytes.fromhex("086878")
_BAND1_1K_Q07_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_ARCHIVE_BELL_BAND1_1K_Q07_6DB_EFFECT_HEX
_BAND1_1K_Q14_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_ARCHIVE_BELL_BAND1_1K_Q14_6DB_EFFECT_HEX
_BAND1_1K_Q20_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_ARCHIVE_BELL_BAND1_1K_Q20_6DB_EFFECT_HEX
_BAND2_DEFAULT_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_ARCHIVE_BELL_BAND2_DEFAULT_6DB_EFFECT_HEX
_BAND3_DEFAULT_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_ARCHIVE_BELL_BAND3_DEFAULT_6DB_EFFECT_HEX
_BAND3_1K_Q10_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_ARCHIVE_BELL_BAND3_1K_Q10_6DB_EFFECT_HEX
_BAND3_2K_Q10_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_ARCHIVE_BELL_BAND3_2K_Q10_6DB_EFFECT_HEX
_BAND3_DEFAULT_Q07_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_ARCHIVE_BELL_BAND3_DEFAULT_Q07_6DB_EFFECT_HEX
_BAND3_DEFAULT_Q20_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_ARCHIVE_BELL_BAND3_DEFAULT_Q20_6DB_EFFECT_HEX
_BAND4_DEFAULT_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_ARCHIVE_BELL_BAND4_DEFAULT_6DB_EFFECT_HEX
_BAND4_1K_Q10_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_ARCHIVE_BELL_BAND4_1K_Q10_6DB_EFFECT_HEX
_BAND4_DEFAULT_Q07_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_ARCHIVE_BELL_BAND4_DEFAULT_Q07_6DB_EFFECT_HEX
_BAND4_DEFAULT_Q20_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_ARCHIVE_BELL_BAND4_DEFAULT_Q20_6DB_EFFECT_HEX
_BAND5_DEFAULT_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_ARCHIVE_BELL_BAND5_DEFAULT_6DB_EFFECT_HEX
_BAND2_LOW_SHELF_1K_Q10_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_ARCHIVE_LOW_SHELF_BAND2_1K_Q10_6DB_EFFECT_HEX
_BAND2_LOW_SHELF_DEFAULT_Q07_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_ARCHIVE_LOW_SHELF_BAND2_DEFAULT_Q07_6DB_EFFECT_HEX
_BAND2_LOW_SHELF_DEFAULT_Q20_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_ARCHIVE_LOW_SHELF_BAND2_DEFAULT_Q20_6DB_EFFECT_HEX
_BAND5_HIGH_SHELF_1K_Q10_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_ARCHIVE_HIGH_SHELF_BAND5_1K_Q10_6DB_EFFECT_HEX
_BAND5_HIGH_SHELF_DEFAULT_Q07_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_ARCHIVE_HIGH_SHELF_BAND5_DEFAULT_Q07_6DB_EFFECT_HEX
_UI_B2_BELL_DEFAULT_Q10_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B2_BELL_DEFAULT_Q10_6DB_EFFECT_HEX
_UI_B2_BELL_1K_Q10_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B2_BELL_1000_Q10_6DB_EFFECT_HEX
_UI_B2_BELL_2K_Q10_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B2_BELL_2000_Q10_6DB_EFFECT_HEX
_UI_B2_BELL_DEFAULT_Q07_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B2_BELL_DEFAULT_Q07_6DB_EFFECT_HEX
_UI_B2_BELL_DEFAULT_Q20_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B2_BELL_DEFAULT_Q20_6DB_EFFECT_HEX
_UI_B2_NOTCH_DEFAULT_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B2_NOTCH_DEFAULT_EFFECT_HEX
_UI_B2_HIGH_SHELF_DEFAULT_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B2_HIGH_SHELF_DEFAULT_6DB_EFFECT_HEX
_UI_B2_LOW_SHELF_DEFAULT_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B2_LOW_SHELF_DEFAULT_6DB_EFFECT_HEX
_UI_B5_BELL_DEFAULT_Q10_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B5_BELL_DEFAULT_Q10_6DB_EFFECT_HEX
_UI_B5_BELL_1K_Q10_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B5_BELL_1000_Q10_6DB_EFFECT_HEX
_UI_B5_BELL_2K_Q10_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B5_BELL_2000_Q10_6DB_EFFECT_HEX
_UI_B5_BELL_DEFAULT_Q07_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B5_BELL_DEFAULT_Q07_6DB_EFFECT_HEX
_UI_B5_BELL_DEFAULT_Q20_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B5_BELL_DEFAULT_Q20_6DB_EFFECT_HEX
_UI_B5_NOTCH_DEFAULT_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B5_NOTCH_DEFAULT_EFFECT_HEX
_UI_B5_HIGH_SHELF_DEFAULT_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B5_HIGH_SHELF_DEFAULT_6DB_EFFECT_HEX
_UI_B5_LOW_SHELF_DEFAULT_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B5_LOW_SHELF_DEFAULT_6DB_EFFECT_HEX
_UI_B1_HIGH_PASS_80HZ_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B1_HIGH_PASS_80HZ_EFFECT_HEX
_UI_B1_HIGH_PASS_160HZ_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B1_HIGH_PASS_160HZ_EFFECT_HEX
_UI_B1_HIGH_PASS_DEFAULT_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B1_HIGH_PASS_DEFAULT_EFFECT_HEX
_UI_B1_BELL_DEFAULT_Q10_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B1_BELL_DEFAULT_Q10_6DB_EFFECT_HEX
_UI_B1_NOTCH_DEFAULT_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B1_NOTCH_DEFAULT_EFFECT_HEX
_UI_B1_LOW_SHELF_DEFAULT_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B1_LOW_SHELF_DEFAULT_6DB_EFFECT_HEX
_UI_B1_HIGH_SHELF_DEFAULT_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B1_HIGH_SHELF_DEFAULT_6DB_EFFECT_HEX
_UI_B3_HIGH_SHELF_DEFAULT_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B3_HIGH_SHELF_DEFAULT_6DB_EFFECT_HEX
_UI_B3_NOTCH_DEFAULT_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B3_NOTCH_DEFAULT_EFFECT_HEX
_UI_B3_LOW_SHELF_DEFAULT_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B3_LOW_SHELF_DEFAULT_6DB_EFFECT_HEX
_UI_B4_HIGH_SHELF_DEFAULT_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B4_HIGH_SHELF_DEFAULT_6DB_EFFECT_HEX
_UI_B4_NOTCH_DEFAULT_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B4_NOTCH_DEFAULT_EFFECT_HEX
_UI_B4_LOW_SHELF_DEFAULT_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B4_LOW_SHELF_DEFAULT_6DB_EFFECT_HEX
_UI_B6_LOW_PASS_12000HZ_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B6_LOW_PASS_12000HZ_EFFECT_HEX
_UI_B6_LOW_PASS_6000HZ_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B6_LOW_PASS_6000HZ_EFFECT_HEX
_UI_B6_LOW_PASS_DEFAULT_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B6_LOW_PASS_DEFAULT_EFFECT_HEX
_UI_B6_BELL_DEFAULT_Q10_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B6_BELL_DEFAULT_Q10_6DB_EFFECT_HEX
_UI_B6_HIGH_SHELF_DEFAULT_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B6_HIGH_SHELF_DEFAULT_6DB_EFFECT_HEX
_UI_B6_NOTCH_DEFAULT_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B6_NOTCH_DEFAULT_EFFECT_HEX
_UI_B6_LOW_SHELF_DEFAULT_PLUS6_EFFECT_HEX = fixture_payloads.AUDIO_EQ_UI_B6_LOW_SHELF_DEFAULT_6DB_EFFECT_HEX


def _normalize_supported_q(value: float | None, *, default: float) -> float:
    if value is None:
        return float(default)
    return round(float(value), 3)


def supported_audio_eq_presets() -> tuple[str, ...]:
    return tuple(_PRESETS.keys())


def _known_audio_eq_effect_filter_hexes() -> set[str]:
    values = {preset.effect_filters_hex.lower() for preset in _PRESETS.values()}
    for name, value in globals().items():
        if name.startswith(("_BAND", "_UI_")) and name.endswith("_EFFECT_HEX") and isinstance(value, str):
            values.add(value.lower())
    return values


def is_supported_audio_eq_effect_filters(payload: bytes | None) -> bool:
    """Return True when *payload* is one of the verified archived clip EQ payloads."""
    data = bytes(payload or b"")
    return bool(data) and data.hex().lower() in _known_audio_eq_effect_filter_hexes()


def read_eq_state(
    cursor, *, audio_item_id: str | None = None
) -> dict[str, object]:
    """Read one exact clip EQ payload, or the legacy first clip when unscoped."""
    if audio_item_id is None:
        row = cursor.execute(
            """
            SELECT Sm2TiItem_id, Name, EffectFiltersBA
            FROM Sm2TiItem
            WHERE DbType = 'Sm2TiAudioClip'
            ORDER BY rowid ASC
            LIMIT 1
            """
        ).fetchone()
    else:
        row = cursor.execute(
            """
            SELECT Sm2TiItem_id, Name, EffectFiltersBA
            FROM Sm2TiItem
            WHERE DbType = 'Sm2TiAudioClip' AND Sm2TiItem_id = ?
            """,
            (str(audio_item_id),),
        ).fetchone()
    if not row:
        raise ValidationError(
            "No audio clip found in Project.db.",
            details={
                "db_type": "Sm2TiAudioClip",
                "audio_item_id": audio_item_id,
            },
        )

    audio_item_id = row[0] if isinstance(row, tuple) else row["Sm2TiItem_id"]
    clip_name = row[1] if isinstance(row, tuple) else row["Name"]
    effect_filters = row[2] if isinstance(row, tuple) else row["EffectFiltersBA"]
    payload = bytes(effect_filters or b"")

    matched_preset: AudioEqPreset | None = None
    if payload:
        payload_hex = payload.hex()
        for preset in _PRESETS.values():
            if payload_hex == preset.effect_filters_hex.lower():
                matched_preset = preset
                break

    return {
        "audio_item_id": audio_item_id,
        "clip_name": clip_name,
        "has_eq_payload": bool(payload),
        "recognized": matched_preset is not None,
        "preset": matched_preset.key if matched_preset else None,
        "summary": matched_preset.summary if matched_preset else None,
        "effect_filters_family": matched_preset.family if matched_preset else None,
        "effect_filters_hex": payload.hex() if payload else None,
        "effect_filters_length": len(payload),
    }


def normalize_audio_eq_preset_name(name: str | None) -> str:
    normalized = str(name or "voice-presence-1k-6db").strip().lower().replace("_", "-")
    preset = _PRESET_ALIASES.get(normalized)
    if preset:
        return preset
    raise ValidationError(
        "Unsupported DaVinci Resolve native audio EQ preset.",
        details={"preset": name, "supported_presets": list(supported_audio_eq_presets())},
    )


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


def _replace_once(payload: bytes, old: bytes, new: bytes, *, label: str) -> bytes:
    occurrences = payload.count(old)
    if occurrences != 1:
        raise ValidationError(
            "Could not resolve a unique archived EQ parameter chunk.",
            details={"label": label, "match_count": occurrences},
        )
    return payload.replace(old, new, 1)


def build_audio_eq_effect_filters(*, preset_name: str) -> bytes:
    canonical_preset = normalize_audio_eq_preset_name(preset_name)
    return bytes.fromhex(_PRESETS[canonical_preset].effect_filters_hex)


def _build_ui_exact_effect_filters(
    *,
    ui_band: int,
    filter_type: str,
    freq_hz: int | None,
    gain_db: float | None,
    q: float | None,
) -> AudioEqSpec:
    normalized_filter = str(filter_type or "").strip().lower()
    normalized_q = _normalize_supported_q(q, default=1.0) if q is not None else None
    freq_value = None if freq_hz in {None, 0} else int(freq_hz)
    gain_value = None if gain_db is None else round(float(gain_db), 1)

    exact_routes: dict[tuple[int, str, int | None, float | None, float | None], tuple[str, str]] = {
        (1, "high-pass", None, None, None): (
            _UI_B1_HIGH_PASS_DEFAULT_EFFECT_HEX,
            "UI band B1 high-pass at archived default settings.",
        ),
        (1, "high-pass", 80, None, None): (
            _UI_B1_HIGH_PASS_80HZ_EFFECT_HEX,
            "UI band B1 high-pass at 80 Hz.",
        ),
        (1, "high-pass", 160, None, None): (
            _UI_B1_HIGH_PASS_160HZ_EFFECT_HEX,
            "UI band B1 high-pass at 160 Hz.",
        ),
        (1, "bell", None, None, None): (
            _UI_B1_BELL_DEFAULT_Q10_PLUS6_EFFECT_HEX,
            "UI band B1 bell at archived default settings.",
        ),
        (1, "bell", None, 6.0, 1.0): (
            _UI_B1_BELL_DEFAULT_Q10_PLUS6_EFFECT_HEX,
            "UI band B1 bell at archived default frequency, +6.0 dB, Q=1.0.",
        ),
        (1, "notch", None, None, None): (
            _UI_B1_NOTCH_DEFAULT_EFFECT_HEX,
            "UI band B1 notch at archived default frequency.",
        ),
        (1, "low-shelf", None, None, None): (
            _UI_B1_LOW_SHELF_DEFAULT_PLUS6_EFFECT_HEX,
            "UI band B1 low-shelf at archived default settings.",
        ),
        (1, "low-shelf", None, 6.0, None): (
            _UI_B1_LOW_SHELF_DEFAULT_PLUS6_EFFECT_HEX,
            "UI band B1 low-shelf at archived default frequency, +6.0 dB.",
        ),
        (1, "high-shelf", None, None, None): (
            _UI_B1_HIGH_SHELF_DEFAULT_PLUS6_EFFECT_HEX,
            "UI band B1 high-shelf at archived default settings.",
        ),
        (1, "high-shelf", None, 6.0, None): (
            _UI_B1_HIGH_SHELF_DEFAULT_PLUS6_EFFECT_HEX,
            "UI band B1 high-shelf at archived default frequency, +6.0 dB.",
        ),
        (2, "bell", None, None, None): (
            _UI_B2_BELL_DEFAULT_Q10_PLUS6_EFFECT_HEX,
            "UI band B2 bell at archived default settings.",
        ),
        (2, "bell", None, 6.0, 1.0): (
            _UI_B2_BELL_DEFAULT_Q10_PLUS6_EFFECT_HEX,
            "UI band B2 bell at archived default frequency, +6.0 dB, Q=1.0.",
        ),
        (2, "bell", 1000, 6.0, 1.0): (
            _UI_B2_BELL_1K_Q10_PLUS6_EFFECT_HEX,
            "UI band B2 bell at 1000 Hz, +6.0 dB, Q=1.0.",
        ),
        (2, "bell", 2000, 6.0, 1.0): (
            _UI_B2_BELL_2K_Q10_PLUS6_EFFECT_HEX,
            "UI band B2 bell at 2000 Hz, +6.0 dB, Q=1.0.",
        ),
        (2, "bell", None, 6.0, 0.7): (
            _UI_B2_BELL_DEFAULT_Q07_PLUS6_EFFECT_HEX,
            "UI band B2 bell at archived default frequency, +6.0 dB, Q=0.7.",
        ),
        (2, "bell", None, 6.0, 2.0): (
            _UI_B2_BELL_DEFAULT_Q20_PLUS6_EFFECT_HEX,
            "UI band B2 bell at archived default frequency, +6.0 dB, Q=2.0.",
        ),
        (2, "notch", None, None, None): (
            _UI_B2_NOTCH_DEFAULT_EFFECT_HEX,
            "UI band B2 notch at archived default frequency.",
        ),
        (2, "high-shelf", None, None, None): (
            _UI_B2_HIGH_SHELF_DEFAULT_PLUS6_EFFECT_HEX,
            "UI band B2 high-shelf at archived default settings.",
        ),
        (2, "high-shelf", None, 6.0, None): (
            _UI_B2_HIGH_SHELF_DEFAULT_PLUS6_EFFECT_HEX,
            "UI band B2 high-shelf at archived default frequency, +6.0 dB.",
        ),
        (2, "low-shelf", None, None, None): (
            _UI_B2_LOW_SHELF_DEFAULT_PLUS6_EFFECT_HEX,
            "UI band B2 low-shelf at archived default settings.",
        ),
        (2, "low-shelf", None, 6.0, None): (
            _UI_B2_LOW_SHELF_DEFAULT_PLUS6_EFFECT_HEX,
            "UI band B2 low-shelf at archived default frequency, +6.0 dB.",
        ),
        (3, "bell", None, None, None): (
            _BAND3_DEFAULT_PLUS6_EFFECT_HEX,
            "UI band B3 bell at archived default settings.",
        ),
        (3, "high-shelf", None, None, None): (
            _UI_B3_HIGH_SHELF_DEFAULT_PLUS6_EFFECT_HEX,
            "UI band B3 high-shelf at archived default settings.",
        ),
        (3, "high-shelf", None, 6.0, None): (
            _UI_B3_HIGH_SHELF_DEFAULT_PLUS6_EFFECT_HEX,
            "UI band B3 high-shelf at archived default frequency, +6.0 dB.",
        ),
        (3, "notch", None, None, None): (
            _UI_B3_NOTCH_DEFAULT_EFFECT_HEX,
            "UI band B3 notch at archived default frequency.",
        ),
        (3, "low-shelf", None, None, None): (
            _UI_B3_LOW_SHELF_DEFAULT_PLUS6_EFFECT_HEX,
            "UI band B3 low-shelf at archived default settings.",
        ),
        (3, "low-shelf", None, 6.0, None): (
            _UI_B3_LOW_SHELF_DEFAULT_PLUS6_EFFECT_HEX,
            "UI band B3 low-shelf at archived default frequency, +6.0 dB.",
        ),
        (4, "bell", None, None, None): (
            _BAND4_DEFAULT_PLUS6_EFFECT_HEX,
            "UI band B4 bell at archived default settings.",
        ),
        (4, "high-shelf", None, None, None): (
            _UI_B4_HIGH_SHELF_DEFAULT_PLUS6_EFFECT_HEX,
            "UI band B4 high-shelf at archived default settings.",
        ),
        (4, "high-shelf", None, 6.0, None): (
            _UI_B4_HIGH_SHELF_DEFAULT_PLUS6_EFFECT_HEX,
            "UI band B4 high-shelf at archived default frequency, +6.0 dB.",
        ),
        (4, "notch", None, None, None): (
            _UI_B4_NOTCH_DEFAULT_EFFECT_HEX,
            "UI band B4 notch at archived default frequency.",
        ),
        (4, "low-shelf", None, None, None): (
            _UI_B4_LOW_SHELF_DEFAULT_PLUS6_EFFECT_HEX,
            "UI band B4 low-shelf at archived default settings.",
        ),
        (4, "low-shelf", None, 6.0, None): (
            _UI_B4_LOW_SHELF_DEFAULT_PLUS6_EFFECT_HEX,
            "UI band B4 low-shelf at archived default frequency, +6.0 dB.",
        ),
        (5, "bell", None, None, None): (
            _UI_B5_BELL_DEFAULT_Q10_PLUS6_EFFECT_HEX,
            "UI band B5 bell at archived default settings.",
        ),
        (5, "bell", None, 6.0, 1.0): (
            _UI_B5_BELL_DEFAULT_Q10_PLUS6_EFFECT_HEX,
            "UI band B5 bell at archived default frequency, +6.0 dB, Q=1.0.",
        ),
        (5, "bell", 1000, 6.0, 1.0): (
            _UI_B5_BELL_1K_Q10_PLUS6_EFFECT_HEX,
            "UI band B5 bell at 1000 Hz, +6.0 dB, Q=1.0.",
        ),
        (5, "bell", 2000, 6.0, 1.0): (
            _UI_B5_BELL_2K_Q10_PLUS6_EFFECT_HEX,
            "UI band B5 bell at 2000 Hz, +6.0 dB, Q=1.0.",
        ),
        (5, "bell", None, 6.0, 0.7): (
            _UI_B5_BELL_DEFAULT_Q07_PLUS6_EFFECT_HEX,
            "UI band B5 bell at archived default frequency, +6.0 dB, Q=0.7.",
        ),
        (5, "bell", None, 6.0, 2.0): (
            _UI_B5_BELL_DEFAULT_Q20_PLUS6_EFFECT_HEX,
            "UI band B5 bell at archived default frequency, +6.0 dB, Q=2.0.",
        ),
        (5, "notch", None, None, None): (
            _UI_B5_NOTCH_DEFAULT_EFFECT_HEX,
            "UI band B5 notch at archived default frequency.",
        ),
        (5, "high-shelf", None, None, None): (
            _UI_B5_HIGH_SHELF_DEFAULT_PLUS6_EFFECT_HEX,
            "UI band B5 high-shelf at archived default settings.",
        ),
        (5, "high-shelf", None, 6.0, None): (
            _UI_B5_HIGH_SHELF_DEFAULT_PLUS6_EFFECT_HEX,
            "UI band B5 high-shelf at archived default frequency, +6.0 dB.",
        ),
        (5, "low-shelf", None, None, None): (
            _UI_B5_LOW_SHELF_DEFAULT_PLUS6_EFFECT_HEX,
            "UI band B5 low-shelf at archived default settings.",
        ),
        (5, "low-shelf", None, 6.0, None): (
            _UI_B5_LOW_SHELF_DEFAULT_PLUS6_EFFECT_HEX,
            "UI band B5 low-shelf at archived default frequency, +6.0 dB.",
        ),
        (6, "low-pass", None, None, None): (
            _UI_B6_LOW_PASS_DEFAULT_EFFECT_HEX,
            "UI band B6 low-pass at archived default settings.",
        ),
        (6, "low-pass", 12000, None, None): (
            _UI_B6_LOW_PASS_12000HZ_EFFECT_HEX,
            "UI band B6 low-pass at 12000 Hz.",
        ),
        (6, "low-pass", 6000, None, None): (
            _UI_B6_LOW_PASS_6000HZ_EFFECT_HEX,
            "UI band B6 low-pass at 6000 Hz.",
        ),
        (6, "bell", None, None, None): (
            _UI_B6_BELL_DEFAULT_Q10_PLUS6_EFFECT_HEX,
            "UI band B6 bell at archived default settings.",
        ),
        (6, "bell", None, 6.0, 1.0): (
            _UI_B6_BELL_DEFAULT_Q10_PLUS6_EFFECT_HEX,
            "UI band B6 bell at archived default frequency, +6.0 dB, Q=1.0.",
        ),
        (6, "high-shelf", None, None, None): (
            _UI_B6_HIGH_SHELF_DEFAULT_PLUS6_EFFECT_HEX,
            "UI band B6 high-shelf at archived default settings.",
        ),
        (6, "high-shelf", None, 6.0, None): (
            _UI_B6_HIGH_SHELF_DEFAULT_PLUS6_EFFECT_HEX,
            "UI band B6 high-shelf at archived default frequency, +6.0 dB.",
        ),
        (6, "notch", None, None, None): (
            _UI_B6_NOTCH_DEFAULT_EFFECT_HEX,
            "UI band B6 notch at archived default frequency.",
        ),
        (6, "low-shelf", None, None, None): (
            _UI_B6_LOW_SHELF_DEFAULT_PLUS6_EFFECT_HEX,
            "UI band B6 low-shelf at archived default settings.",
        ),
        (6, "low-shelf", None, 6.0, None): (
            _UI_B6_LOW_SHELF_DEFAULT_PLUS6_EFFECT_HEX,
            "UI band B6 low-shelf at archived default frequency, +6.0 dB.",
        ),
    }

    route = exact_routes.get((int(ui_band), normalized_filter, freq_value, gain_value, normalized_q))
    if route is None and int(ui_band) in {3, 4} and normalized_filter == "bell":
        spec = _build_bell_band_effect_filters(
            band=int(ui_band),
            freq_hz=int(freq_hz or 0),
            gain_db=float(gain_db or 0.0),
            q=q,
        )
        return AudioEqSpec(
            mode=spec.mode,
            preset=spec.preset,
            filter_type=spec.filter_type,
            band=spec.band,
            ui_band=int(ui_band),
            freq_hz=spec.freq_hz,
            gain_db=spec.gain_db,
            q=spec.q,
            effect_filters=spec.effect_filters,
            family=spec.family,
            summary=spec.summary.replace(f"band {spec.band}", f"UI band B{ui_band}"),
        )

    if route is None:
        return _build_ui_composed_effect_filters(
            ui_band=int(ui_band),
            filter_type=normalized_filter,
            freq_hz=freq_value,
            gain_db=gain_value,
            q=normalized_q,
        )

    effect_hex, summary = route
    return AudioEqSpec(
        mode="ui_exact",
        preset=None,
        filter_type=normalized_filter,
        band=None,
        ui_band=int(ui_band),
        freq_hz=freq_value,
        gain_db=gain_value,
        q=normalized_q,
        effect_filters=bytes.fromhex(effect_hex),
        family="resolve20_clip_eq_ui_archive_v1",
        summary=summary,
    )


def _build_ui_composed_effect_filters(
    *,
    ui_band: int,
    filter_type: str,
    freq_hz: int | None,
    gain_db: float | None,
    q: float | None,
) -> AudioEqSpec:
    if ui_band not in {1, 2, 3, 4, 5, 6}:
        raise ValidationError(
            "Unsupported DaVinci Resolve native UI band EQ route.",
            details={
                "ui_band": ui_band,
                "filter_type": filter_type,
                "freq_hz": freq_hz,
                "gain_db": gain_db,
                "q": q,
                "supported_ui_bands": [1, 2, 3, 4, 5, 6],
            },
        )

    supported_filters_by_ui_band = {
        1: {"high-shelf", "bell", "notch", "low-shelf", "high-pass"},
        2: {"high-shelf", "bell", "notch", "low-shelf"},
        3: {"high-shelf", "bell", "notch", "low-shelf"},
        4: {"high-shelf", "bell", "notch", "low-shelf"},
        5: {"high-shelf", "bell", "notch", "low-shelf"},
        6: {"high-shelf", "bell", "notch", "low-shelf", "low-pass"},
    }
    supported_filters = supported_filters_by_ui_band[int(ui_band)]
    if filter_type not in supported_filters:
        raise ValidationError(
            "Unsupported DaVinci Resolve native UI band EQ route.",
            details={
                "ui_band": ui_band,
                "filter_type": filter_type,
                "freq_hz": freq_hz,
                "gain_db": gain_db,
                "q": q,
                "supported_filter_types_for_ui_band": sorted(supported_filters),
            },
        )

    shape = SHAPE_BY_NAME.get(filter_type)
    if shape is None:
        raise ValidationError(
            "Unsupported DaVinci Resolve native UI band EQ route.",
            details={
                "ui_band": ui_band,
                "filter_type": filter_type,
                "freq_hz": freq_hz,
                "gain_db": gain_db,
                "q": q,
                "supported_filter_types": sorted(SHAPE_BY_NAME.keys()),
                "supported_ui_bands": [1, 2, 3, 4, 5, 6],
            },
        )

    if freq_hz is None:
        raise ValidationError(
            "Composed UI band EQ requires --freq for non-archived exact routes.",
            details={"ui_band": ui_band, "filter_type": filter_type, "freq_hz": freq_hz},
        )
    if int(freq_hz) <= 0:
        raise ValidationError(
            "Composed UI band EQ frequency must be positive.",
            details={"ui_band": ui_band, "filter_type": filter_type, "freq_hz": freq_hz},
        )
    if q is not None and float(q) <= 0:
        raise ValidationError(
            "Composed UI band EQ Q must be positive.",
            details={"ui_band": ui_band, "filter_type": filter_type, "q": q},
        )

    normalized_gain = 0.0 if gain_db is None else float(gain_db)
    normalized_q = 1.0 if q is None else float(q)
    payload = compose_eq_payload(
        [
            EqBand(
                band=int(ui_band),
                shape=shape,
                freq_hz=int(freq_hz),
                gain_db=normalized_gain,
                q=normalized_q,
            )
        ]
    )

    return AudioEqSpec(
        mode="ui_composed",
        preset=None,
        filter_type=filter_type,
        band=None,
        ui_band=int(ui_band),
        freq_hz=int(freq_hz),
        gain_db=round(normalized_gain, 1),
        q=round(normalized_q, 3),
        effect_filters=payload,
        family="resolve20_clip_eq_composed_v1",
        summary=(
            f"UI band B{int(ui_band)} {filter_type} at {int(freq_hz)} Hz, "
            f"{normalized_gain:+.1f} dB, Q={normalized_q:g}."
        ),
    )


def _build_bell_band_effect_filters(*, band: int, freq_hz: int, gain_db: float, q: float | None) -> AudioEqSpec:
    gain_tenths = int(round(float(gain_db) * 10.0))
    if abs(float(gain_db) * 10.0 - gain_tenths) > 1e-6:
        raise ValidationError(
            "Bell EQ gain must use one decimal precision at most.",
            details={"gain_db": gain_db},
        )
    if gain_tenths < -60 or gain_tenths > 60:
        raise ValidationError(
            "DaVinci Resolve native archived bell EQ currently supports gain between -6.0 dB and +6.0 dB.",
            details={"gain_db": gain_db, "min_gain_db": -6.0, "max_gain_db": 6.0},
        )

    encoded_gain = _encode_varint(_encode_zigzag(gain_tenths))
    if len(encoded_gain) != 1:
        raise ValidationError(
            "DaVinci Resolve native archived bell EQ currently supports only single-byte archived gain values.",
            details={"gain_db": gain_db, "gain_tenths": gain_tenths},
        )

    normalized_band = int(band)
    normalized_q = _normalize_supported_q(q, default=1.0)

    if normalized_band == 1:
        if int(freq_hz) == 1000 and normalized_q in {0.7, 1.4, 2.0}:
            payload = bytes.fromhex(
                {
                    0.7: _BAND1_1K_Q07_PLUS6_EFFECT_HEX,
                    1.4: _BAND1_1K_Q14_PLUS6_EFFECT_HEX,
                    2.0: _BAND1_1K_Q20_PLUS6_EFFECT_HEX,
                }[normalized_q]
            )
            payload = _replace_once(
                payload,
                _BELL_1K_PLUS6_GAIN_CHUNK,
                bytes.fromhex("08681A040A0208") + encoded_gain,
                label=f"band1_gain_1k_q{str(normalized_q).replace('.', '_')}",
            )
            return AudioEqSpec(
                mode="parametric",
                preset=None,
                filter_type="bell",
                band=1,
                freq_hz=1000,
                gain_db=gain_tenths / 10.0,
                q=normalized_q,
                effect_filters=payload,
                family="resolve20_clip_eq_archive_v3",
                summary=f"Bell band 1 at 1000 Hz, {gain_tenths / 10.0:+.1f} dB, Q={normalized_q:.1f}.",
            )

        if normalized_q != 1.0:
            raise ValidationError(
                "DaVinci Resolve native archived bell EQ currently supports band 1 Q values of 0.7, 1.0, 1.4, or 2.0.",
                details={"band": band, "q": q, "supported_q_values": [0.7, 1.0, 1.4, 2.0]},
            )
        if int(freq_hz) not in {1000, 2000}:
            raise ValidationError(
                "DaVinci Resolve native archived bell EQ currently supports only 1000 Hz or 2000 Hz for band 1.",
                details={"freq_hz": freq_hz, "supported_freq_hz": [1000, 2000]},
            )

        if int(freq_hz) == 1000:
            payload = bytes.fromhex(_PRESETS["voice-presence-1k-6db"].effect_filters_hex)
            payload = _replace_once(
                payload,
                _BELL_1K_PLUS6_GAIN_CHUNK,
                bytes.fromhex("08681A040A0208") + encoded_gain,
                label="band1_gain_1k",
            )
        else:
            payload = bytes.fromhex(_PRESETS["presence-2k-6db"].effect_filters_hex)
            payload = _replace_once(
                payload,
                _BELL_2K_PLUS6_GAIN_CHUNK,
                bytes.fromhex("08681A040A0208") + encoded_gain,
                label="band1_gain_2k",
            )

        return AudioEqSpec(
            mode="parametric",
            preset=None,
            filter_type="bell",
            band=1,
            freq_hz=int(freq_hz),
            gain_db=gain_tenths / 10.0,
            q=1.0,
            effect_filters=payload,
            family="resolve20_clip_eq_archive_v2",
            summary=f"Bell band 1 at {int(freq_hz)} Hz, {gain_tenths / 10.0:+.1f} dB, Q=1.0.",
        )

    if normalized_band in {2, 3, 4, 5}:
        if normalized_band == 3:
            if freq_hz in {1000, 2000}:
                if q is not None and normalized_q != 1.0:
                    raise ValidationError(
                        "DaVinci Resolve native archived band 3 frequency routes currently support only Q=1.0.",
                        details={"band": band, "freq_hz": freq_hz, "q": q, "supported_q_values": [1.0]},
                    )
                payload = bytes.fromhex(
                    _BAND3_1K_Q10_PLUS6_EFFECT_HEX if int(freq_hz) == 1000 else _BAND3_2K_Q10_PLUS6_EFFECT_HEX
                )
                payload = _replace_once(
                    payload,
                    _BELL_BAND3_5_PLUS6_GAIN_CHUNK,
                    bytes.fromhex("0868") + encoded_gain,
                    label=f"band3_gain_freq_{int(freq_hz)}",
                )
                return AudioEqSpec(
                    mode="parametric",
                    preset=None,
                    filter_type="bell",
                    band=3,
                    freq_hz=int(freq_hz),
                    gain_db=gain_tenths / 10.0,
                    q=1.0,
                    effect_filters=payload,
                    family="resolve20_clip_eq_archive_v4",
                    summary=f"Bell band 3 at {int(freq_hz)} Hz, {gain_tenths / 10.0:+.1f} dB, Q=1.0.",
                )

            if freq_hz in {None, 0} and normalized_q == 0.7:
                payload = bytes.fromhex(_BAND3_DEFAULT_Q07_PLUS6_EFFECT_HEX)
                payload = _replace_once(
                    payload,
                    _BELL_BAND3_5_PLUS6_GAIN_CHUNK,
                    bytes.fromhex("0868") + encoded_gain,
                    label="band3_gain_default_q07",
                )
                return AudioEqSpec(
                    mode="parametric",
                    preset=None,
                    filter_type="bell",
                    band=3,
                    freq_hz=None,
                    gain_db=gain_tenths / 10.0,
                    q=0.7,
                    effect_filters=payload,
                    family="resolve20_clip_eq_archive_v4",
                    summary=f"Bell band 3 at archived default frequency, {gain_tenths / 10.0:+.1f} dB, Q=0.7.",
                )

            if freq_hz in {None, 0} and normalized_q == 2.0:
                payload = bytes.fromhex(_BAND3_DEFAULT_Q20_PLUS6_EFFECT_HEX)
                payload = _replace_once(
                    payload,
                    bytes.fromhex("08DC0B"),
                    bytes.fromhex("08") + encoded_gain,
                    label="band3_gain_default_q20",
                )
                return AudioEqSpec(
                    mode="parametric",
                    preset=None,
                    filter_type="bell",
                    band=3,
                    freq_hz=None,
                    gain_db=gain_tenths / 10.0,
                    q=2.0,
                    effect_filters=payload,
                    family="resolve20_clip_eq_archive_v4",
                    summary=f"Bell band 3 at archived default frequency, {gain_tenths / 10.0:+.1f} dB, Q=2.0.",
                )

        if normalized_band == 4:
            if freq_hz == 1000:
                if q is not None and normalized_q != 1.0:
                    raise ValidationError(
                        "DaVinci Resolve native archived band 4 frequency routes currently support only Q=1.0.",
                        details={"band": band, "freq_hz": freq_hz, "q": q, "supported_q_values": [1.0]},
                    )
                payload = bytes.fromhex(_BAND4_1K_Q10_PLUS6_EFFECT_HEX)
                payload = _replace_once(
                    payload,
                    _BELL_BAND3_5_PLUS6_GAIN_CHUNK,
                    bytes.fromhex("0868") + encoded_gain,
                    label="band4_gain_freq_1000",
                )
                return AudioEqSpec(
                    mode="parametric",
                    preset=None,
                    filter_type="bell",
                    band=4,
                    freq_hz=1000,
                    gain_db=gain_tenths / 10.0,
                    q=1.0,
                    effect_filters=payload,
                    family="resolve20_clip_eq_archive_v4",
                    summary=f"Bell band 4 at 1000 Hz, {gain_tenths / 10.0:+.1f} dB, Q=1.0.",
                )

            if freq_hz in {None, 0} and normalized_q == 0.7:
                payload = bytes.fromhex(_BAND4_DEFAULT_Q07_PLUS6_EFFECT_HEX)
                payload = _replace_once(
                    payload,
                    _BELL_BAND3_5_PLUS6_GAIN_CHUNK,
                    bytes.fromhex("0868") + encoded_gain,
                    label="band4_gain_default_q07",
                )
                return AudioEqSpec(
                    mode="parametric",
                    preset=None,
                    filter_type="bell",
                    band=4,
                    freq_hz=None,
                    gain_db=gain_tenths / 10.0,
                    q=0.7,
                    effect_filters=payload,
                    family="resolve20_clip_eq_archive_v4",
                    summary=f"Bell band 4 at archived default frequency, {gain_tenths / 10.0:+.1f} dB, Q=0.7.",
                )

            if freq_hz in {None, 0} and normalized_q == 2.0:
                payload = bytes.fromhex(_BAND4_DEFAULT_Q20_PLUS6_EFFECT_HEX)
                payload = _replace_once(
                    payload,
                    _BELL_BAND3_5_PLUS6_GAIN_CHUNK,
                    bytes.fromhex("0868") + encoded_gain,
                    label="band4_gain_default_q20",
                )
                return AudioEqSpec(
                    mode="parametric",
                    preset=None,
                    filter_type="bell",
                    band=4,
                    freq_hz=None,
                    gain_db=gain_tenths / 10.0,
                    q=2.0,
                    effect_filters=payload,
                    family="resolve20_clip_eq_archive_v4",
                    summary=f"Bell band 4 at archived default frequency, {gain_tenths / 10.0:+.1f} dB, Q=2.0.",
                )

        if freq_hz not in {None, 0}:
            raise ValidationError(
                "DaVinci Resolve native archived bell EQ currently keeps the default archived frequency for bands 2-5.",
                details={"band": band, "freq_hz": freq_hz},
            )
        if q is not None:
            raise ValidationError(
                "DaVinci Resolve native archived bell EQ currently keeps the default archived Q for bands 2-5.",
                details={"band": band, "q": q},
            )

        payload = bytes.fromhex(
            {
                2: _BAND2_DEFAULT_PLUS6_EFFECT_HEX,
                3: _BAND3_DEFAULT_PLUS6_EFFECT_HEX,
                4: _BAND4_DEFAULT_PLUS6_EFFECT_HEX,
                5: _BAND5_DEFAULT_PLUS6_EFFECT_HEX,
            }[normalized_band]
        )
        if normalized_band == 2:
            payload = _replace_once(
                payload,
                _BELL_1K_PLUS6_GAIN_CHUNK,
                bytes.fromhex("08681A040A0208") + encoded_gain,
                label="band2_gain_default",
            )
        else:
            payload = _replace_once(
                payload,
                _BELL_BAND3_5_PLUS6_GAIN_CHUNK,
                bytes.fromhex("0868") + encoded_gain,
                label=f"band{normalized_band}_gain_default",
            )

        return AudioEqSpec(
            mode="parametric",
            preset=None,
            filter_type="bell",
            band=normalized_band,
            freq_hz=None,
            gain_db=gain_tenths / 10.0,
            q=None,
            effect_filters=payload,
            family="resolve20_clip_eq_archive_v3",
            summary=f"Bell band {normalized_band} at archived default frequency/Q, {gain_tenths / 10.0:+.1f} dB.",
        )

    raise ValidationError(
        "DaVinci Resolve native archived bell EQ currently supports bands 1-5.",
        details={"band": band, "supported_bands": [1, 2, 3, 4, 5]},
    )


def _build_filter_effect_filters(*, filter_type: str, freq_hz: int) -> AudioEqSpec:
    normalized = str(filter_type or "").strip().lower()
    if normalized == "high-pass":
        if int(freq_hz) != 80:
            raise ValidationError(
                "DaVinci Resolve native archived high-pass EQ currently supports only 80 Hz.",
                details={"filter_type": filter_type, "freq_hz": freq_hz, "supported_freq_hz": [80]},
            )
        preset = _PRESETS["high-pass-80hz"]
        return AudioEqSpec(
            mode="parametric",
            preset=None,
            filter_type="high-pass",
            band=None,
            freq_hz=80,
            gain_db=None,
            q=None,
            effect_filters=bytes.fromhex(preset.effect_filters_hex),
            family=preset.family,
            summary=preset.summary,
        )
    if normalized == "low-pass":
        if int(freq_hz) != 12000:
            raise ValidationError(
                "DaVinci Resolve native archived low-pass EQ currently supports only 12000 Hz.",
                details={"filter_type": filter_type, "freq_hz": freq_hz, "supported_freq_hz": [12000]},
            )
        preset = _PRESETS["low-pass-12000hz"]
        return AudioEqSpec(
            mode="parametric",
            preset=None,
            filter_type="low-pass",
            band=None,
            freq_hz=12000,
            gain_db=None,
            q=None,
            effect_filters=bytes.fromhex(preset.effect_filters_hex),
            family=preset.family,
            summary=preset.summary,
        )
    raise ValidationError(
        "Unsupported DaVinci Resolve native EQ filter type.",
        details={"filter_type": filter_type, "supported_filter_types": ["bell", "high-pass", "low-pass", "low-shelf", "high-shelf"]},
    )


def _build_shelf_effect_filters(
    *,
    filter_type: str,
    band: int | None,
    freq_hz: int | None,
    gain_db: float | None,
    q: float | None,
) -> AudioEqSpec:
    normalized = str(filter_type or "").strip().lower()
    if float(gain_db or 0.0) != 6.0:
        raise ValidationError(
            "DaVinci Resolve native archived shelf routes currently support only +6.0 dB.",
            details={"filter_type": filter_type, "gain_db": gain_db, "supported_gain_db": [6.0]},
        )
    normalized_q = _normalize_supported_q(q, default=1.0)

    if normalized == "low-shelf":
        if band not in {None, 2}:
            raise ValidationError(
                "DaVinci Resolve native low-shelf route maps to band 2.",
                details={"filter_type": filter_type, "band": band, "supported_bands": [2]},
            )
        if freq_hz == 1000 and normalized_q == 1.0:
            payload = bytes.fromhex(_BAND2_LOW_SHELF_1K_Q10_PLUS6_EFFECT_HEX)
            return AudioEqSpec(
                mode="parametric",
                preset=None,
                filter_type="low-shelf",
                band=2,
                freq_hz=1000,
                gain_db=6.0,
                q=1.0,
                effect_filters=payload,
                family="resolve20_clip_eq_archive_v5",
                summary="Low-shelf band 2 at 1000 Hz, +6.0 dB, Q=1.0.",
            )
        if freq_hz in {None, 0} and normalized_q == 0.7:
            payload = bytes.fromhex(_BAND2_LOW_SHELF_DEFAULT_Q07_PLUS6_EFFECT_HEX)
            return AudioEqSpec(
                mode="parametric",
                preset=None,
                filter_type="low-shelf",
                band=2,
                freq_hz=None,
                gain_db=6.0,
                q=0.7,
                effect_filters=payload,
                family="resolve20_clip_eq_archive_v5",
                summary="Low-shelf band 2 at archived default frequency, +6.0 dB, Q=0.7.",
            )
        if freq_hz in {None, 0} and normalized_q == 2.0:
            payload = bytes.fromhex(_BAND2_LOW_SHELF_DEFAULT_Q20_PLUS6_EFFECT_HEX)
            return AudioEqSpec(
                mode="parametric",
                preset=None,
                filter_type="low-shelf",
                band=2,
                freq_hz=None,
                gain_db=6.0,
                q=2.0,
                effect_filters=payload,
                family="resolve20_clip_eq_archive_v5",
                summary="Low-shelf band 2 at archived default frequency, +6.0 dB, Q=2.0.",
            )
        raise ValidationError(
            "Unsupported DaVinci Resolve native low-shelf route.",
            details={
                "filter_type": filter_type,
                "band": band,
                "freq_hz": freq_hz,
                "q": q,
                "supported_routes": [
                    {"band": 2, "freq_hz": 1000, "q": 1.0, "gain_db": 6.0},
                    {"band": 2, "freq_hz": None, "q": 0.7, "gain_db": 6.0},
                    {"band": 2, "freq_hz": None, "q": 2.0, "gain_db": 6.0},
                ],
            },
        )

    if normalized == "high-shelf":
        if band not in {None, 5}:
            raise ValidationError(
                "DaVinci Resolve native high-shelf route maps to band 5.",
                details={"filter_type": filter_type, "band": band, "supported_bands": [5]},
            )
        if freq_hz == 1000 and normalized_q == 1.0:
            payload = bytes.fromhex(_BAND5_HIGH_SHELF_1K_Q10_PLUS6_EFFECT_HEX)
            return AudioEqSpec(
                mode="parametric",
                preset=None,
                filter_type="high-shelf",
                band=5,
                freq_hz=1000,
                gain_db=6.0,
                q=1.0,
                effect_filters=payload,
                family="resolve20_clip_eq_archive_v5",
                summary="High-shelf band 5 at 1000 Hz, +6.0 dB, Q=1.0.",
            )
        if freq_hz in {None, 0} and normalized_q == 0.7:
            payload = bytes.fromhex(_BAND5_HIGH_SHELF_DEFAULT_Q07_PLUS6_EFFECT_HEX)
            return AudioEqSpec(
                mode="parametric",
                preset=None,
                filter_type="high-shelf",
                band=5,
                freq_hz=None,
                gain_db=6.0,
                q=0.7,
                effect_filters=payload,
                family="resolve20_clip_eq_archive_v5",
                summary="High-shelf band 5 at archived default frequency, +6.0 dB, Q=0.7.",
            )
        raise ValidationError(
            "Unsupported DaVinci Resolve native high-shelf route.",
            details={
                "filter_type": filter_type,
                "band": band,
                "freq_hz": freq_hz,
                "q": q,
                "supported_routes": [
                    {"band": 5, "freq_hz": 1000, "q": 1.0, "gain_db": 6.0},
                    {"band": 5, "freq_hz": None, "q": 0.7, "gain_db": 6.0},
                ],
            },
        )

    raise ValidationError(
        "Unsupported DaVinci Resolve native shelf filter type.",
        details={"filter_type": filter_type, "supported_filter_types": ["low-shelf", "high-shelf"]},
    )


def resolve_audio_eq_spec(
    *,
    preset_name: str | None,
    band: int | None = None,
    ui_band: int | None = None,
    filter_type: str | None = None,
    freq_hz: int | None = None,
    gain_db: float | None = None,
    q: float | None = None,
) -> AudioEqSpec:
    if ui_band is None and filter_type is None and band is None and freq_hz is None and gain_db is None and q is None:
        canonical_preset = normalize_audio_eq_preset_name(preset_name)
        preset = _PRESETS[canonical_preset]
        return AudioEqSpec(
            mode="preset",
            preset=canonical_preset,
            filter_type="preset",
            band=None,
            freq_hz=None,
            gain_db=None,
            q=None,
            effect_filters=bytes.fromhex(preset.effect_filters_hex),
            family=preset.family,
            summary=preset.summary,
        )

    if ui_band is not None and band is not None:
        raise ValidationError(
            "Use either archived --band or DaVinci Resolve-panel --ui-band, not both.",
            details={"band": band, "ui_band": ui_band},
        )

    normalized_filter = str(filter_type or "").strip().lower()
    if ui_band is not None:
        if not normalized_filter:
            raise ValidationError(
                "UI band EQ requires --filter-type.",
                details={"ui_band": ui_band, "filter_type": filter_type},
            )
        return _build_ui_exact_effect_filters(
            ui_band=int(ui_band),
            filter_type=normalized_filter,
            freq_hz=freq_hz,
            gain_db=gain_db,
            q=q,
        )

    if normalized_filter == "bell":
        normalized_band = int(band or 1)
        if gain_db is None:
            raise ValidationError(
                "Bell EQ requires --gain-db.",
                details={"filter_type": filter_type, "band": normalized_band, "freq_hz": freq_hz, "gain_db": gain_db},
            )
        if normalized_band == 1 and freq_hz is None:
            raise ValidationError(
                "Band 1 bell EQ requires --freq.",
                details={"filter_type": filter_type, "band": normalized_band, "freq_hz": freq_hz, "gain_db": gain_db},
            )
        return _build_bell_band_effect_filters(
            band=normalized_band,
            freq_hz=int(freq_hz or 0),
            gain_db=float(gain_db),
            q=q,
        )
    if normalized_filter in {"low-shelf", "high-shelf"}:
        return _build_shelf_effect_filters(
            filter_type=normalized_filter,
            band=band,
            freq_hz=freq_hz,
            gain_db=gain_db,
            q=q,
        )
    if normalized_filter in {"high-pass", "low-pass"}:
        if gain_db is not None:
            raise ValidationError(
                "High-pass/low-pass EQ does not accept --gain-db in the current archived route.",
                details={"filter_type": filter_type, "gain_db": gain_db},
            )
        if q is not None:
            raise ValidationError(
                "High-pass/low-pass EQ does not expose --q in the current archived route.",
                details={"filter_type": filter_type, "q": q},
            )
        if freq_hz is None:
            raise ValidationError(
                "High-pass/low-pass EQ requires --freq.",
                details={"filter_type": filter_type},
            )
        return _build_filter_effect_filters(filter_type=normalized_filter, freq_hz=int(freq_hz))

    raise ValidationError(
        "DaVinci Resolve native EQ currently needs either --preset or a supported parameter family.",
        details={
            "preset": preset_name,
            "band": band,
            "filter_type": filter_type,
            "freq_hz": freq_hz,
            "gain_db": gain_db,
            "q": q,
        },
    )


def apply_audio_eq_preset(
    cursor,
    *,
    audio_item,
    preset_name: str,
    timeline_name: str | None,
) -> dict[str, object]:
    spec = resolve_audio_eq_spec(preset_name=preset_name)
    row = db_timeline_rows.find_ti_item_row(
        cursor,
        item=audio_item,
        db_type="Sm2TiAudioClip",
        timeline_name=timeline_name,
    )
    db_timeline_rows.update_row(
        cursor,
        "Sm2TiItem",
        "Sm2TiItem_id",
        row["Sm2TiItem_id"],
        {"EffectFiltersBA": spec.effect_filters},
    )
    return {
        "effect": "audio-eq",
        "preset": spec.preset,
        "audio_item_id": row["Sm2TiItem_id"],
        "mode": spec.mode,
        "filter_type": spec.filter_type,
        "band": spec.band,
        "ui_band": spec.ui_band,
        "freq_hz": spec.freq_hz,
        "gain_db": spec.gain_db,
        "q": spec.q,
        "effect_filters_family": spec.family,
        "summary": spec.summary,
        "preserved_fields_blob": True,
    }


def apply_audio_eq_settings(
    cursor,
    *,
    audio_item,
    preset_name: str | None,
    band: int | None,
    ui_band: int | None = None,
    filter_type: str | None,
    freq_hz: int | None,
    gain_db: float | None,
    q: float | None,
    timeline_name: str | None,
) -> dict[str, object]:
    spec = resolve_audio_eq_spec(
        preset_name=preset_name,
        band=band,
        ui_band=ui_band,
        filter_type=filter_type,
        freq_hz=freq_hz,
        gain_db=gain_db,
        q=q,
    )
    row = db_timeline_rows.find_ti_item_row(
        cursor,
        item=audio_item,
        db_type="Sm2TiAudioClip",
        timeline_name=timeline_name,
    )
    db_timeline_rows.update_row(
        cursor,
        "Sm2TiItem",
        "Sm2TiItem_id",
        row["Sm2TiItem_id"],
        {"EffectFiltersBA": spec.effect_filters},
    )
    return {
        "effect": "audio-eq",
        "preset": spec.preset,
        "audio_item_id": row["Sm2TiItem_id"],
        "mode": spec.mode,
        "filter_type": spec.filter_type,
        "band": spec.band,
        "ui_band": spec.ui_band,
        "freq_hz": spec.freq_hz,
        "gain_db": spec.gain_db,
        "q": spec.q,
        "effect_filters_family": spec.family,
        "summary": spec.summary,
        "preserved_fields_blob": True,
    }
