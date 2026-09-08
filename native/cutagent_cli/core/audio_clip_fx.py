"""FL::ClipFX reader/writer for DaVinci Resolve audio clip effects.

Reads and writes AI Voice Isolation, Dialogue Leveler, Music Remixer
and other clip-level audio effects stored in Sm2TiAudioClip.FieldsBlob.

Storage chain:
  FieldsBlob = [8B header] + [0x81 + ZSTD(protobuf)]
  protobuf → field 1.1.2 = {1: "FL::ClipFX", 2: zlib(fx_payload)}
  fx_payload = BMD binary format with plugin blocks + param entries

Format (confirmed 2026-04-05):
  fx_payload header:
    magic: f88f6677 (4B)
    version: 01000000 (4B LE)
    total_size: uint32 LE
    field_count: uint32 LE
    plugin_count: uint32 LE
  
  Plugin blocks (fixed-size, sequential):
    plugin_id_string: "bmd:Name:Number\\0" + padding to 256B
    param entries: name(64B null-padded) + value region(~68B)
"""

from __future__ import annotations

import base64
import hashlib
import sqlite3
import struct
import zlib
from dataclasses import dataclass, field
from typing import Any

from .audio_clip_fx_payload_data import (
    CHORUS_DEFAULT_PAYLOAD_B64,
    CHORUS_DEFAULT_PAYLOAD_SHA256,
    DEESSER_DEFAULT_PAYLOAD_SHA256,
    DELAY_DEFAULT_PAYLOAD_B64,
    DELAY_DEFAULT_PAYLOAD_SHA256,
    DEHUMMER_DEFAULT_PAYLOAD_B64,
    DEHUMMER_DEFAULT_PAYLOAD_SHA256,
    DIALOGUE_LEVELER_DEFAULT_PAYLOAD_SHA256,
    DIALOGUE_PROCESSOR_DEFAULT_PAYLOAD_SHA256,
    DISTORTION_DEFAULT_PAYLOAD_SHA256,
    ECHO_DEFAULT_PAYLOAD_B64,
    ECHO_DEFAULT_PAYLOAD_SHA256,
    FAIRLIGHT_EQ_DEFAULT_PAYLOAD_B64,
    FAIRLIGHT_EQ_DEFAULT_PAYLOAD_SHA256,
    FLANGER_DEFAULT_PAYLOAD_B64,
    FLANGER_DEFAULT_PAYLOAD_SHA256,
    GAIN_DEFAULT_PAYLOAD_B64,
    GAIN_DEFAULT_PAYLOAD_SHA256,
    LIMITER_DEFAULT_PAYLOAD_B64,
    LIMITER_DEFAULT_PAYLOAD_SHA256,
    MODULATION_DEFAULT_PAYLOAD_B64,
    MODULATION_DEFAULT_PAYLOAD_SHA256,
    MULTIBAND_COMPRESSOR_DEFAULT_PAYLOAD_SHA256,
    MUSIC_REMIXER_DEFAULT_PAYLOAD_SHA256,
    NOISE_REDUCTION_DEFAULT_PAYLOAD_SHA256,
    PITCH_DEFAULT_PAYLOAD_B64,
    PITCH_DEFAULT_PAYLOAD_SHA256,
    REVERB_DEFAULT_PAYLOAD_SHA256,
    SOFT_CLIPPER_DEFAULT_PAYLOAD_B64,
    SOFT_CLIPPER_DEFAULT_PAYLOAD_SHA256,
    STEREO_FIXER_DEFAULT_PAYLOAD_B64,
    STEREO_FIXER_DEFAULT_PAYLOAD_SHA256,
    STEREO_WIDTH_DEFAULT_PAYLOAD_B64,
    STEREO_WIDTH_DEFAULT_PAYLOAD_SHA256,
    VOCAL_CHANNEL_DEFAULT_PAYLOAD_B64,
    VOCAL_CHANNEL_DEFAULT_PAYLOAD_SHA256,
)

try:
    import zstandard
except ImportError:
    zstandard = None  # type: ignore


# ---------------------------------------------------------------------------
# Known plugin IDs
# ---------------------------------------------------------------------------

PLUGIN_VOICE_ISOLATION = "bmd:Voice Isolation:1112364617"
PLUGIN_DIALOGUE_LEVELER = "bmd:Dialogue Leveler:1112360050"
PLUGIN_DIALOGUE_PROCESSOR = "bmd:Dialogue Processor:1112360036"
PLUGIN_MUSIC_REMIXER = "bmd:Music Remixer:1112363856"
PLUGIN_CHORUS = "bmd:Chorus:1112360057"
PLUGIN_DEESSER = "bmd:De-Esser:1112360051"
PLUGIN_REVERB = "bmd:Reverb:1112363618"
PLUGIN_DISTORTION = "bmd:Distortion:1112360051"
PLUGIN_MULTIBAND_COMPRESSOR = "bmd:Multiband Compressor:1112360043"
PLUGIN_NOISE_REDUCTION = "bmd:Noise Reduction:1112362610"
PLUGIN_FLANGER = "bmd:Flanger:1112360057"
PLUGIN_ECHO = "bmd:Echo:1112360057"
PLUGIN_DELAY = "bmd:Delay:1112360057"
PLUGIN_DEHUMMER = "bmd:De-Hummer:1112360040"
PLUGIN_GAIN = "bmd:Gain:1112360814"
PLUGIN_VOCAL_CHANNEL = "bmd:Vocal Channel:1112360057"
PLUGIN_LIMITER = "bmd:Limiter:1112362098"
PLUGIN_STEREO_WIDTH = "bmd:Stereo Width:1112360051"
PLUGIN_STEREO_FIXER = "bmd:Stereo Fixer:1112363846"
PLUGIN_SOFT_CLIPPER = "bmd:Soft Clipper:1112363875"
PLUGIN_PITCH = "bmd:Pitch:1112360545"
PLUGIN_MODULATION = "bmd:Modulation:1112362348"
PLUGIN_FAIRLIGHT_EQ = "bmd:Fairlight EQ:1112360305"

# Known parameter names
PARAM_VOICE_ISO_DRY_MIX = "BMDVoiceIsolationControl::DRY_MIX"
PARAM_VOICE_ISO_VERSION = "BMDVoiceIsolationControl::PARAMETER_MAPPING_VERSION"

PARAM_DL_PRESET = "UI_BAS_PRESET"
PARAM_DL_RIDER_ON = "UI_ADV_RIDER_ON"
PARAM_DL_LIFTER_ON = "UI_BAS_LIFTER_ON"
PARAM_DL_CLEANER_ON = "UI_BAS_CLEANER_ON"
PARAM_DL_OUTPUT_GAIN = "UI_BAS_OUTPUT_GAIN"
PARAM_DL_GATE_AUTOMATION = "WRITE_GATE_AUTOMATION"

PARAM_MR_VOICE_LEVEL = "BMDMusicSeparator::VOICE_LEVEL"
PARAM_MR_DRUMS_LEVEL = "BMDMusicSeparator::DRUMS_LEVEL"
PARAM_MR_BASS_LEVEL = "BMDMusicSeparator::BASS_LEVEL"
PARAM_MR_OTHER_LEVEL = "BMDMusicSeparator::OTHER_LEVEL"
PARAM_MR_GUITAR_LEVEL = "BMDMusicSeparator::GUITAR_LEVEL"
PARAM_MR_VOICE_MUTE = "BMDMusicSeparator::VOICE_MUTE"
PARAM_MR_DRUMS_MUTE = "BMDMusicSeparator::DRUMS_MUTE"
PARAM_MR_BASS_MUTE = "BMDMusicSeparator::BASS_MUTE"
PARAM_MR_OTHER_MUTE = "BMDMusicSeparator::OTHER_MUTE"
PARAM_MR_GUITAR_MUTE = "BMDMusicSeparator::GUITAR_MUTE"


def _write_null_padded_ascii(data: bytearray, offset: int, size: int, value: str) -> None:
    encoded = value.encode("ascii")
    if len(encoded) >= size:
        raise ValueError(f"{value!r} does not fit in {size} bytes.")
    data[offset : offset + size] = encoded + (b"\0" * (size - len(encoded)))


def _distortion_default_payload_from_chorus(chorus_payload: bytes) -> bytes:
    payload = bytearray(chorus_payload)
    _write_null_padded_ascii(payload, 32, 256, PLUGIN_DISTORTION)
    _write_null_padded_ascii(payload, 404, 48, "Distortion")
    params = [
        ("BMDDistortion::HF_CUT", 1.0),
        ("BMDDistortion::LF_CUT", 0.0),
        ("BMDDistortion::MODE", 1.0),
        ("BMDDistortion::DISTORTION", 1.0),
        ("BMDDistortion::CEILING", 1.0),
        ("BMDDistortion::DRY_WET", 1.0),
        ("BMDDistortion::OUTPUT_GAIN", 0.75),
        ("BMDDistortion::AUTO_LEVEL", 0.0),
    ]
    param_offsets = (584, 652, 720, 788, 856, 924, 992, 1060, 1128, 1196, 1264)
    for index, offset in enumerate(param_offsets):
        if index < len(params):
            name, value = params[index]
            _write_null_padded_ascii(payload, offset, 64, name)
            payload[offset + 64 : offset + 68] = struct.pack("<f", value)
        else:
            payload[offset : offset + 68] = b"\0" * 68
    return bytes(payload)


def _deesser_default_payload_from_chorus(chorus_payload: bytes) -> bytes:
    payload = bytearray(chorus_payload)
    _write_null_padded_ascii(payload, 32, 256, PLUGIN_DEESSER)
    _write_null_padded_ascii(payload, 404, 48, "De-Esser")
    params = [
        ("BMDDeesser::MODE", 1.0),
        ("BMDDeesser::RANGE", 1.0),
        ("BMDDeesser::AMOUNT", 1.0),
        ("BMDDeesser::ESS_ONLY", 0.0),
    ]
    param_offsets = (584, 652, 720, 788, 856, 924, 992, 1060, 1128, 1196, 1264)
    for index, offset in enumerate(param_offsets):
        if index < len(params):
            name, value = params[index]
            _write_null_padded_ascii(payload, offset, 64, name)
            payload[offset + 64 : offset + 68] = struct.pack("<f", value)
        else:
            payload[offset : offset + 68] = b"\0" * 68
    return bytes(payload)


def _multiband_compressor_default_payload_from_chorus(chorus_payload: bytes) -> bytes:
    payload = bytearray(chorus_payload)
    _write_null_padded_ascii(payload, 32, 256, PLUGIN_MULTIBAND_COMPRESSOR)
    _write_null_padded_ascii(payload, 404, 48, "Multiband Compressor")
    params = [
        ("BMDMultiBandCompressor::B1_ON", 1.0),
        ("BMDMultiBandCompressor::B1_THRES", -60.0),
        ("BMDMultiBandCompressor::B1_RATIO", 20.0),
        ("BMDMultiBandCompressor::B1_GAIN", 12.0),
        ("BMDMultiBandCompressor::B2_ON", 1.0),
        ("BMDMultiBandCompressor::B2_THRES", -60.0),
        ("BMDMultiBandCompressor::B2_RATIO", 20.0),
        ("BMDMultiBandCompressor::B2_GAIN", -12.0),
        ("BMDMultiBandCompressor::B3_ON", 1.0),
        ("BMDMultiBandCompressor::B4_ON", 1.0),
        ("BMDMultiBandCompressor::GAIN", 1.0),
    ]
    for (name, value), offset in zip(params, (584, 652, 720, 788, 856, 924, 992, 1060, 1128, 1196, 1264), strict=True):
        _write_null_padded_ascii(payload, offset, 64, name)
        payload[offset + 64 : offset + 68] = struct.pack("<f", value)
    return bytes(payload)


def _dialogue_processor_default_payload_from_chorus(chorus_payload: bytes) -> bytes:
    payload = bytearray(chorus_payload)
    _write_null_padded_ascii(payload, 32, 256, PLUGIN_DIALOGUE_PROCESSOR)
    _write_null_padded_ascii(payload, 404, 48, "Dialogue Processor")
    params = [
        ("BMDDialogProcessor::RUMBLE_FILTER_IN", 1.0),
        ("BMDDialogProcessor::RUMBLE_FILTER_FREQ", 80.0),
        ("BMDDialogProcessor::DE_POP_IN", 1.0),
        ("BMDDialogProcessor::DE_POP_FREQ", 120.0),
        ("BMDDialogProcessor::DE_POP_AMOUNT", 1.0),
        ("BMDDialogProcessor::DE_ESS_IN", 1.0),
        ("BMDDialogProcessor::DE_ESS_FREQ", 6000.0),
        ("BMDDialogProcessor::DE_ESS_AMOUNT", 1.0),
        ("BMDDialogProcessor::COMP_IN", 1.0),
        ("BMDDialogProcessor::COMP_THRES", -30.0),
        ("BMDDialogProcessor::COMP_AMOUNT", 1.0),
    ]
    for (name, value), offset in zip(params, (584, 652, 720, 788, 856, 924, 992, 1060, 1128, 1196, 1264), strict=True):
        _write_null_padded_ascii(payload, offset, 64, name)
        payload[offset + 64 : offset + 68] = struct.pack("<f", value)
    return bytes(payload)


def _dialogue_leveler_default_payload_from_chorus(chorus_payload: bytes) -> bytes:
    payload = bytearray(chorus_payload)
    _write_null_padded_ascii(payload, 32, 256, PLUGIN_DIALOGUE_LEVELER)
    _write_null_padded_ascii(payload, 404, 48, "Dialogue Leveler")
    params = [
        (PARAM_DL_PRESET, 1.0),
        (PARAM_DL_RIDER_ON, 1.0),
        (PARAM_DL_LIFTER_ON, 1.0),
        (PARAM_DL_CLEANER_ON, 1.0),
        (PARAM_DL_OUTPUT_GAIN, 1.0),
        (PARAM_DL_GATE_AUTOMATION, 0.0),
    ]
    param_offsets = (584, 652, 720, 788, 856, 924, 992, 1060, 1128, 1196, 1264)
    for index, offset in enumerate(param_offsets):
        if index < len(params):
            name, value = params[index]
            _write_null_padded_ascii(payload, offset, 64, name)
            payload[offset + 64 : offset + 68] = struct.pack("<f", value)
        else:
            payload[offset : offset + 68] = b"\0" * 68
    return bytes(payload)


def _music_remixer_default_payload_from_chorus(chorus_payload: bytes) -> bytes:
    payload = bytearray(chorus_payload)
    _write_null_padded_ascii(payload, 32, 256, PLUGIN_MUSIC_REMIXER)
    _write_null_padded_ascii(payload, 404, 48, "Music Remixer")
    params = [
        (PARAM_MR_VOICE_LEVEL, 0.0),
        (PARAM_MR_DRUMS_LEVEL, 1.0),
        (PARAM_MR_BASS_LEVEL, 1.0),
        (PARAM_MR_OTHER_LEVEL, 1.0),
        (PARAM_MR_GUITAR_LEVEL, 1.0),
    ]
    param_offsets = (584, 652, 720, 788, 856, 924, 992, 1060, 1128, 1196, 1264)
    for index, offset in enumerate(param_offsets):
        if index < len(params):
            name, value = params[index]
            _write_null_padded_ascii(payload, offset, 64, name)
            payload[offset + 64 : offset + 68] = struct.pack("<f", value)
        else:
            payload[offset : offset + 68] = b"\0" * 68
    return bytes(payload)


def _noise_reduction_default_payload_from_chorus(chorus_payload: bytes) -> bytes:
    payload = bytearray(chorus_payload)
    _write_null_padded_ascii(payload, 32, 256, PLUGIN_NOISE_REDUCTION)
    _write_null_padded_ascii(payload, 404, 48, "Noise Reduction")
    for offset in (584, 652, 720, 788, 856, 924, 992, 1060, 1128, 1196, 1264):
        payload[offset : offset + 68] = b"\0" * 68
    return bytes(payload)


def default_clip_fx_payload(plugin_id: str) -> bytes | None:
    """Return a verified default FL::ClipFX payload for a known built-in plugin."""
    payload = base64.b64decode(CHORUS_DEFAULT_PAYLOAD_B64)
    digest = hashlib.sha256(payload).hexdigest()
    if digest != CHORUS_DEFAULT_PAYLOAD_SHA256:
        raise RuntimeError("Packaged Chorus FL::ClipFX payload failed SHA-256 verification.")
    if plugin_id == PLUGIN_CHORUS:
        return payload
    if plugin_id == PLUGIN_DEESSER:
        deesser_payload = _deesser_default_payload_from_chorus(payload)
        deesser_digest = hashlib.sha256(deesser_payload).hexdigest()
        if deesser_digest != DEESSER_DEFAULT_PAYLOAD_SHA256:
            raise RuntimeError("Packaged De-Esser FL::ClipFX payload failed SHA-256 verification.")
        return deesser_payload
    if plugin_id == PLUGIN_REVERB:
        reverb_payload = (
            payload.replace(PLUGIN_CHORUS.encode("ascii"), PLUGIN_REVERB.encode("ascii"))
            .replace(b"BMDChorus", b"BMDReverb")
            .replace(b"Chorus", b"Reverb")
        )
        reverb_digest = hashlib.sha256(reverb_payload).hexdigest()
        if reverb_digest != REVERB_DEFAULT_PAYLOAD_SHA256:
            raise RuntimeError("Packaged Reverb FL::ClipFX payload failed SHA-256 verification.")
        return reverb_payload
    if plugin_id == PLUGIN_DISTORTION:
        distortion_payload = _distortion_default_payload_from_chorus(payload)
        distortion_digest = hashlib.sha256(distortion_payload).hexdigest()
        if distortion_digest != DISTORTION_DEFAULT_PAYLOAD_SHA256:
            raise RuntimeError("Packaged Distortion FL::ClipFX payload failed SHA-256 verification.")
        return distortion_payload
    if plugin_id == PLUGIN_MULTIBAND_COMPRESSOR:
        multiband_payload = _multiband_compressor_default_payload_from_chorus(payload)
        multiband_digest = hashlib.sha256(multiband_payload).hexdigest()
        if multiband_digest != MULTIBAND_COMPRESSOR_DEFAULT_PAYLOAD_SHA256:
            raise RuntimeError("Packaged Multiband Compressor FL::ClipFX payload failed SHA-256 verification.")
        return multiband_payload
    if plugin_id == PLUGIN_DIALOGUE_LEVELER:
        dialogue_leveler_payload = _dialogue_leveler_default_payload_from_chorus(payload)
        dialogue_leveler_digest = hashlib.sha256(dialogue_leveler_payload).hexdigest()
        if dialogue_leveler_digest != DIALOGUE_LEVELER_DEFAULT_PAYLOAD_SHA256:
            raise RuntimeError("Packaged Dialogue Leveler FL::ClipFX payload failed SHA-256 verification.")
        return dialogue_leveler_payload
    if plugin_id == PLUGIN_MUSIC_REMIXER:
        music_remixer_payload = _music_remixer_default_payload_from_chorus(payload)
        music_remixer_digest = hashlib.sha256(music_remixer_payload).hexdigest()
        if music_remixer_digest != MUSIC_REMIXER_DEFAULT_PAYLOAD_SHA256:
            raise RuntimeError("Packaged Music Remixer FL::ClipFX payload failed SHA-256 verification.")
        return music_remixer_payload
    if plugin_id == PLUGIN_DIALOGUE_PROCESSOR:
        dialogue_processor_payload = _dialogue_processor_default_payload_from_chorus(payload)
        dialogue_processor_digest = hashlib.sha256(dialogue_processor_payload).hexdigest()
        if dialogue_processor_digest != DIALOGUE_PROCESSOR_DEFAULT_PAYLOAD_SHA256:
            raise RuntimeError("Packaged Dialogue Processor FL::ClipFX payload failed SHA-256 verification.")
        return dialogue_processor_payload
    if plugin_id == PLUGIN_NOISE_REDUCTION:
        noise_reduction_payload = _noise_reduction_default_payload_from_chorus(payload)
        noise_reduction_digest = hashlib.sha256(noise_reduction_payload).hexdigest()
        if noise_reduction_digest != NOISE_REDUCTION_DEFAULT_PAYLOAD_SHA256:
            raise RuntimeError("Packaged Noise Reduction FL::ClipFX payload failed SHA-256 verification.")
        return noise_reduction_payload
    if plugin_id == PLUGIN_FLANGER:
        flanger_payload = base64.b64decode(FLANGER_DEFAULT_PAYLOAD_B64)
        flanger_digest = hashlib.sha256(flanger_payload).hexdigest()
        if flanger_digest != FLANGER_DEFAULT_PAYLOAD_SHA256:
            raise RuntimeError("Packaged Flanger FL::ClipFX payload failed SHA-256 verification.")
        return flanger_payload
    if plugin_id == PLUGIN_ECHO:
        echo_payload = base64.b64decode(ECHO_DEFAULT_PAYLOAD_B64)
        echo_digest = hashlib.sha256(echo_payload).hexdigest()
        if echo_digest != ECHO_DEFAULT_PAYLOAD_SHA256:
            raise RuntimeError("Packaged Echo FL::ClipFX payload failed SHA-256 verification.")
        return echo_payload
    if plugin_id == PLUGIN_DELAY:
        delay_payload = base64.b64decode(DELAY_DEFAULT_PAYLOAD_B64)
        delay_digest = hashlib.sha256(delay_payload).hexdigest()
        if delay_digest != DELAY_DEFAULT_PAYLOAD_SHA256:
            raise RuntimeError("Packaged Delay FL::ClipFX payload failed SHA-256 verification.")
        return delay_payload
    if plugin_id == PLUGIN_DEHUMMER:
        dehummer_payload = base64.b64decode(DEHUMMER_DEFAULT_PAYLOAD_B64)
        dehummer_digest = hashlib.sha256(dehummer_payload).hexdigest()
        if dehummer_digest != DEHUMMER_DEFAULT_PAYLOAD_SHA256:
            raise RuntimeError("Packaged De-Hummer FL::ClipFX payload failed SHA-256 verification.")
        return dehummer_payload
    if plugin_id == PLUGIN_GAIN:
        gain_payload = base64.b64decode(GAIN_DEFAULT_PAYLOAD_B64)
        gain_digest = hashlib.sha256(gain_payload).hexdigest()
        if gain_digest != GAIN_DEFAULT_PAYLOAD_SHA256:
            raise RuntimeError("Packaged Gain FL::ClipFX payload failed SHA-256 verification.")
        return gain_payload
    if plugin_id == PLUGIN_VOCAL_CHANNEL:
        vocal_channel_payload = base64.b64decode(VOCAL_CHANNEL_DEFAULT_PAYLOAD_B64)
        vocal_channel_digest = hashlib.sha256(vocal_channel_payload).hexdigest()
        if vocal_channel_digest != VOCAL_CHANNEL_DEFAULT_PAYLOAD_SHA256:
            raise RuntimeError("Packaged Vocal Channel FL::ClipFX payload failed SHA-256 verification.")
        return vocal_channel_payload
    if plugin_id == PLUGIN_LIMITER:
        limiter_payload = base64.b64decode(LIMITER_DEFAULT_PAYLOAD_B64)
        limiter_digest = hashlib.sha256(limiter_payload).hexdigest()
        if limiter_digest != LIMITER_DEFAULT_PAYLOAD_SHA256:
            raise RuntimeError("Packaged Limiter FL::ClipFX payload failed SHA-256 verification.")
        return limiter_payload
    if plugin_id == PLUGIN_STEREO_WIDTH:
        stereo_width_payload = base64.b64decode(STEREO_WIDTH_DEFAULT_PAYLOAD_B64)
        stereo_width_digest = hashlib.sha256(stereo_width_payload).hexdigest()
        if stereo_width_digest != STEREO_WIDTH_DEFAULT_PAYLOAD_SHA256:
            raise RuntimeError("Packaged Stereo Width FL::ClipFX payload failed SHA-256 verification.")
        return stereo_width_payload
    if plugin_id == PLUGIN_STEREO_FIXER:
        stereo_fixer_payload = base64.b64decode(STEREO_FIXER_DEFAULT_PAYLOAD_B64)
        stereo_fixer_digest = hashlib.sha256(stereo_fixer_payload).hexdigest()
        if stereo_fixer_digest != STEREO_FIXER_DEFAULT_PAYLOAD_SHA256:
            raise RuntimeError("Packaged Stereo Fixer FL::ClipFX payload failed SHA-256 verification.")
        return stereo_fixer_payload
    if plugin_id == PLUGIN_SOFT_CLIPPER:
        soft_clipper_payload = base64.b64decode(SOFT_CLIPPER_DEFAULT_PAYLOAD_B64)
        soft_clipper_digest = hashlib.sha256(soft_clipper_payload).hexdigest()
        if soft_clipper_digest != SOFT_CLIPPER_DEFAULT_PAYLOAD_SHA256:
            raise RuntimeError("Packaged Soft Clipper FL::ClipFX payload failed SHA-256 verification.")
        return soft_clipper_payload
    if plugin_id == PLUGIN_PITCH:
        pitch_payload = base64.b64decode(PITCH_DEFAULT_PAYLOAD_B64)
        pitch_digest = hashlib.sha256(pitch_payload).hexdigest()
        if pitch_digest != PITCH_DEFAULT_PAYLOAD_SHA256:
            raise RuntimeError("Packaged Pitch FL::ClipFX payload failed SHA-256 verification.")
        return pitch_payload
    if plugin_id == PLUGIN_MODULATION:
        modulation_payload = base64.b64decode(MODULATION_DEFAULT_PAYLOAD_B64)
        modulation_digest = hashlib.sha256(modulation_payload).hexdigest()
        if modulation_digest != MODULATION_DEFAULT_PAYLOAD_SHA256:
            raise RuntimeError("Packaged Modulation FL::ClipFX payload failed SHA-256 verification.")
        return modulation_payload
    if plugin_id == PLUGIN_FAIRLIGHT_EQ:
        fairlight_eq_payload = base64.b64decode(FAIRLIGHT_EQ_DEFAULT_PAYLOAD_B64)
        fairlight_eq_digest = hashlib.sha256(fairlight_eq_payload).hexdigest()
        if fairlight_eq_digest != FAIRLIGHT_EQ_DEFAULT_PAYLOAD_SHA256:
            raise RuntimeError("Packaged Fairlight EQ FL::ClipFX payload failed SHA-256 verification.")
        return fairlight_eq_payload
    return None


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ClipFxParam:
    name: str
    value: float
    offset: int = 0  # byte offset in decompressed payload


@dataclass
class ClipFxPlugin:
    plugin_id: str
    name: str
    params: list[ClipFxParam] = field(default_factory=list)
    offset: int = 0
    size: int = 0


@dataclass
class ClipFxState:
    plugins: list[ClipFxPlugin] = field(default_factory=list)
    raw_payload: bytes = b""
    
    def get_param(self, plugin_id: str, param_name: str) -> float | None:
        for p in self.plugins:
            if p.plugin_id == plugin_id:
                for param in p.params:
                    if param.name == param_name:
                        return param.value
        return None
    
    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"plugins": []}
        for p in self.plugins:
            entry = {
                "plugin_id": p.plugin_id,
                "name": p.name,
                "params": {param.name: param.value for param in p.params},
            }
            result["plugins"].append(entry)
        
        # High-level summary
        vi_mix = self.get_param(PLUGIN_VOICE_ISOLATION, PARAM_VOICE_ISO_DRY_MIX)
        if vi_mix is not None:
            result["voice_isolation"] = {"amount": vi_mix * 100}
        
        dl_lifter = self.get_param(PLUGIN_DIALOGUE_LEVELER, PARAM_DL_LIFTER_ON)
        dl_cleaner = self.get_param(PLUGIN_DIALOGUE_LEVELER, PARAM_DL_CLEANER_ON)
        dl_gain = self.get_param(PLUGIN_DIALOGUE_LEVELER, PARAM_DL_OUTPUT_GAIN)
        if any(v is not None for v in [dl_lifter, dl_cleaner, dl_gain]):
            result["dialogue_leveler"] = {
                "lifter_on": bool(dl_lifter) if dl_lifter is not None else None,
                "cleaner_on": bool(dl_cleaner) if dl_cleaner is not None else None,
                "output_gain": dl_gain,
            }
        
        mr_voice = self.get_param(PLUGIN_MUSIC_REMIXER, PARAM_MR_VOICE_LEVEL)
        if mr_voice is not None:
            result["music_remixer"] = {
                "voice": self.get_param(PLUGIN_MUSIC_REMIXER, PARAM_MR_VOICE_LEVEL),
                "drums": self.get_param(PLUGIN_MUSIC_REMIXER, PARAM_MR_DRUMS_LEVEL),
                "bass": self.get_param(PLUGIN_MUSIC_REMIXER, PARAM_MR_BASS_LEVEL),
                "other": self.get_param(PLUGIN_MUSIC_REMIXER, PARAM_MR_OTHER_LEVEL),
                "guitar": self.get_param(PLUGIN_MUSIC_REMIXER, PARAM_MR_GUITAR_LEVEL),
            }
        
        return result


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

FX_MAGIC = b'\x66\x88\x66\x77'  # f88f6677 but as bytes in the data


def _find_float_near_param(data: bytes, param_end: int, scan_range: int = 68) -> float:
    """Find the most likely float32 value after a param name."""
    # The value is typically at a fixed offset after the param name
    # Look for non-zero float in a reasonable range
    for off in range(0, min(scan_range, len(data) - param_end - 4)):
        pos = param_end + off
        if pos % 4 != 0:
            continue
        val = struct.unpack('<f', data[pos:pos + 4])[0]
        if val != 0.0 and abs(val) < 10000 and abs(val) > 0.0001:
            # Check if this looks like a real param value (not garbage)
            # Real values include booleans, dB levels, and frequency controls.
            if 0.0 <= val <= 48000.0 or -100.0 <= val < 0.0:
                return val
    return 0.0


def _fixed_param_value_offset(data: bytes, param_start: int, param_end: int) -> int | None:
    """Return the canonical value offset for fixed-size FL::ClipFX param entries."""
    pos = param_start + 64
    if pos + 4 > len(data):
        return None
    if any(data[param_end:pos]):
        return None
    return pos


def parse_clip_fx(data: bytes) -> ClipFxState:
    """Parse decompressed FL::ClipFX payload."""
    state = ClipFxState(raw_payload=data)
    
    if len(data) < 20:
        return state
    
    # Verify magic
    if data[:4] != FX_MAGIC:
        return state
    
    # Find plugin markers
    import re
    markers = list(re.finditer(rb'bmd:[^:\x00]+:\d+', data))
    
    for i, m in enumerate(markers):
        plugin_id = m.group().decode('ascii')
        parts = plugin_id.split(':')
        name = parts[1] if len(parts) >= 2 else plugin_id
        
        # Determine plugin block boundaries
        start = m.start()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(data)
        
        plugin = ClipFxPlugin(
            plugin_id=plugin_id,
            name=name,
            offset=start,
            size=end - start,
        )
        
        # Find params within this plugin block
        block = data[start:end]
        param_patterns = [
            rb'BMD[A-Za-z0-9]+::[A-Z0-9_]+',
            rb'UI_[A-Z_]+',
            rb'WRITE_[A-Z_]+',
        ]
        
        for pattern in param_patterns:
            for pm in re.finditer(pattern, block):
                param_name = pm.group().decode('ascii')
                param_end_in_block = pm.end()
                
                value_pos = _fixed_param_value_offset(block, pm.start(), param_end_in_block)
                if value_pos is not None:
                    value = struct.unpack('<f', block[value_pos:value_pos + 4])[0]
                else:
                    value = _find_float_near_param(block, param_end_in_block)
                
                plugin.params.append(ClipFxParam(
                    name=param_name,
                    value=value,
                    offset=start + pm.start(),
                ))
        
        state.plugins.append(plugin)
    
    return state


def set_param_in_payload(
    data: bytes,
    param_name: str,
    value: float,
) -> bytes:
    """Modify a parameter value in the decompressed FL::ClipFX payload.
    
    Finds the param by name and overwrites its float32 value.
    """
    name_bytes = param_name.encode('ascii')
    idx = data.find(name_bytes)
    if idx < 0:
        raise ValueError(f"Parameter '{param_name}' not found in FX payload")
    
    param_end = idx + len(name_bytes)
    
    fixed_value_pos = _fixed_param_value_offset(data, idx, param_end)
    if fixed_value_pos is not None:
        new_data = bytearray(data)
        struct.pack_into('<f', new_data, fixed_value_pos, value)
        return bytes(new_data)

    # Find the current value location
    for off in range(0, 68):
        pos = param_end + off
        if pos + 4 > len(data):
            break
        if pos % 4 != 0:
            continue
        val = struct.unpack('<f', data[pos:pos + 4])[0]
        if val != 0.0 and abs(val) < 10000 and abs(val) > 0.0001:
            # Found the value — replace it
            new_data = bytearray(data)
            struct.pack_into('<f', new_data, pos, value)
            return bytes(new_data)
    
    # Value might be zero — find the canonical value offset
    # For most params it's at name_end + padding to next 4-byte boundary + some fixed offset
    # Use offset 48 as default (observed in multiple params)
    pos = param_end + 48
    if pos + 4 <= len(data):
        new_data = bytearray(data)
        struct.pack_into('<f', new_data, pos, value)
        return bytes(new_data)
    
    raise ValueError(f"Could not find value location for '{param_name}'")


# ---------------------------------------------------------------------------
# FieldsBlob integration
# ---------------------------------------------------------------------------

def read_clip_fx_from_db(
    cursor: sqlite3.Cursor,
    clip_id: str,
) -> ClipFxState | None:
    """Read FL::ClipFX from an audio clip's FieldsBlob."""
    row = cursor.execute(
        "SELECT FieldsBlob FROM Sm2TiItem WHERE Sm2TiItem_id = ?",
        (clip_id,),
    ).fetchone()
    
    if not row or not row["FieldsBlob"]:
        return None
    
    fb = row["FieldsBlob"]
    if len(fb) < 10:
        return None
    
    if zstandard is None:
        raise RuntimeError("zstandard required")
    
    dctx = zstandard.ZstdDecompressor()
    try:
        proto = dctx.decompress(fb[9:], max_output_size=16 * 1024 * 1024)
    except Exception:
        return None
    
    # Find zlib stream (FL::ClipFX payload)
    idx = proto.find(b'\x78\x9c')
    if idx < 0:
        return None
    
    # Decompress zlib
    for end in range(len(proto) - idx, 10, -1):
        try:
            data = zlib.decompress(proto[idx:idx + end])
            break
        except Exception:
            continue
    else:
        return None
    
    return parse_clip_fx(data)


# ---------------------------------------------------------------------------
# Protobuf helpers (minimal, no external dependency)
# ---------------------------------------------------------------------------

def _encode_varint(value: int) -> bytes:
    """Encode an integer as a protobuf varint."""
    parts = []
    while value > 0x7F:
        parts.append((value & 0x7F) | 0x80)
        value >>= 7
    parts.append(value & 0x7F)
    return bytes(parts)


def _encode_length_delimited(field_number: int, data: bytes) -> bytes:
    """Encode a length-delimited protobuf field."""
    tag = _encode_varint((field_number << 3) | 2)
    return tag + _encode_varint(len(data)) + data


def _encode_varint_field(field_number: int, value: int) -> bytes:
    """Encode a varint protobuf field."""
    tag = _encode_varint((field_number << 3) | 0)
    return tag + _encode_varint(value)


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    shift = 0
    value = 0
    cursor = int(offset)
    while cursor < len(data):
        byte = data[cursor]
        cursor += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, cursor
        shift += 7
    raise ValueError("Unexpected end of protobuf varint.")


def _iter_proto_fields(data: bytes) -> list[tuple[int, int, int, bytes, int, int]]:
    fields: list[tuple[int, int, int, bytes, int, int]] = []
    cursor = 0
    while cursor < len(data):
        field_start = cursor
        tag, cursor = _read_varint(data, cursor)
        field_number = tag >> 3
        wire_type = tag & 7
        if wire_type == 0:
            _value, cursor = _read_varint(data, cursor)
        elif wire_type == 1:
            cursor += 8
        elif wire_type == 5:
            cursor += 4
        elif wire_type == 2:
            length, value_start = _read_varint(data, cursor)
            value_end = value_start + length
            if value_end > len(data):
                raise ValueError("Length-delimited protobuf field exceeds payload size.")
            fields.append((field_start, value_end, field_number, data[value_start:value_end], value_start, value_end))
            cursor = value_end
            continue
        else:
            raise ValueError(f"Unsupported protobuf wire type {wire_type}.")
        fields.append((field_start, cursor, field_number, b"", cursor, cursor))
    return fields


def _decode_clipfx_child_name(child_message: bytes) -> str | None:
    try:
        for _start, _end, field_number, value, _value_start, _value_end in _iter_proto_fields(child_message):
            if field_number == 1:
                return value.decode("ascii", errors="ignore")
    except ValueError:
        return None
    return None


def _build_clipfx_child_message(fx_payload: bytes) -> bytes:
    compressed_fx = zlib.compress(fx_payload)
    size_hint = struct.pack('>I', len(fx_payload))
    return _encode_length_delimited(1, b"FL::ClipFX") + _encode_length_delimited(2, size_hint + compressed_fx)


def _replace_clipfx_child_recursive(message: bytes, fx_payload: bytes) -> tuple[bytes, bool]:
    parts: list[bytes] = []
    cursor = 0
    replaced = False
    for start, end, field_number, value, _value_start, _value_end in _iter_proto_fields(message):
        parts.append(message[cursor:start])
        if value and _decode_clipfx_child_name(value) == "FL::ClipFX":
            parts.append(_encode_length_delimited(field_number, _build_clipfx_child_message(fx_payload)))
            replaced = True
        elif value:
            try:
                updated_value, child_replaced = _replace_clipfx_child_recursive(value, fx_payload)
            except ValueError:
                child_replaced = False
                updated_value = value
            if child_replaced:
                parts.append(_encode_length_delimited(field_number, updated_value))
                replaced = True
            else:
                parts.append(message[start:end])
        else:
            parts.append(message[start:end])
        cursor = end
    parts.append(message[cursor:])
    return b"".join(parts), replaced


def _replace_clipfx_payload_in_proto(proto: bytes, fx_payload: bytes) -> tuple[bytes, bool]:
    return _replace_clipfx_child_recursive(proto, fx_payload)


def _remove_clipfx_child_recursive(message: bytes) -> tuple[bytes, bool]:
    parts: list[bytes] = []
    cursor = 0
    removed = False
    for start, end, field_number, value, _value_start, _value_end in _iter_proto_fields(message):
        parts.append(message[cursor:start])
        if value and _decode_clipfx_child_name(value) == "FL::ClipFX":
            removed = True
        elif value:
            try:
                updated_value, child_removed = _remove_clipfx_child_recursive(value)
            except ValueError:
                child_removed = False
                updated_value = value
            if child_removed:
                parts.append(_encode_length_delimited(field_number, updated_value))
                removed = True
            else:
                parts.append(message[start:end])
        else:
            parts.append(message[start:end])
        cursor = end
    parts.append(message[cursor:])
    return b"".join(parts), removed


def _remove_clipfx_payload_in_proto(proto: bytes) -> tuple[bytes, bool]:
    return _remove_clipfx_child_recursive(proto)


def _single_length_delimited_field(
    fields: list[tuple[int, int, int, bytes, int, int]],
    *,
    field_number: int,
    context: str,
) -> tuple[int, int, int, bytes, int, int]:
    matches = [field for field in fields if field[2] == field_number and field[3]]
    if len(matches) != 1:
        raise ValueError(f"{context} must contain exactly one message field {field_number}.")
    return matches[0]


def _replace_length_delimited_field_value(
    message: bytes,
    field: tuple[int, int, int, bytes, int, int],
    value: bytes,
) -> bytes:
    start, end, field_number, _old_value, _value_start, _value_end = field
    return message[:start] + _encode_length_delimited(field_number, value) + message[end:]


def _insert_clipfx_payload_in_proto(proto: bytes, fx_payload: bytes) -> tuple[bytes, bool]:
    """Insert ClipFX into the canonical DaVinci Resolve FieldsBlob envelope.

    Length-delimited siblings inside the ClipFX container can hold opaque Qt
    payloads (for example clip gain). They are not protobuf messages and must
    never be recursively parsed or replaced. The two outer field-1 wrappers are
    the verified container path shared by empty, opaque-sibling, and FL sibling
    blobs.
    """
    top_fields = _iter_proto_fields(proto)
    top_wrapper = _single_length_delimited_field(
        top_fields,
        field_number=1,
        context="FieldsBlob protobuf",
    )
    wrapper_fields = _iter_proto_fields(top_wrapper[3])
    clipfx_containers = [field for field in wrapper_fields if field[2] == 1 and field[3]]
    if not clipfx_containers:
        # Resolve also emits a canonical minimal audio-mix wrapper containing
        # only field 4 (enabled), e.g. 0a022001. Seed the missing field-1
        # container while preserving that sibling flag.
        if top_wrapper[3] != _encode_varint_field(4, 1):
            raise ValueError(
                "FieldsBlob wrapper without field 1 must be the canonical enabled audio-mix wrapper."
            )
        container_value = _encode_length_delimited(2, _build_clipfx_child_message(fx_payload))
        updated_wrapper = _encode_length_delimited(1, container_value) + top_wrapper[3]
        return _replace_length_delimited_field_value(proto, top_wrapper, updated_wrapper), True
    if len(clipfx_containers) != 1:
        raise ValueError("FieldsBlob wrapper must contain at most one message field 1.")
    clipfx_container = clipfx_containers[0]
    container_value = clipfx_container[3]
    container_fields = _iter_proto_fields(container_value)
    direct_child_names = [_decode_clipfx_child_name(field[3]) for field in container_fields]
    if "FL::ClipFX" in direct_child_names:
        raise ValueError("FieldsBlob already contains FL::ClipFX.")

    insertion = _encode_length_delimited(2, _build_clipfx_child_message(fx_payload))
    insertion_offset = len(container_value)
    for container_field, child_name in zip(container_fields, direct_child_names, strict=True):
        if child_name and child_name.startswith("FL::"):
            insertion_offset = container_field[0]
            break
    updated_container = container_value[:insertion_offset] + insertion + container_value[insertion_offset:]
    updated_wrapper = _replace_length_delimited_field_value(
        top_wrapper[3],
        clipfx_container,
        updated_container,
    )
    updated_proto = _replace_length_delimited_field_value(proto, top_wrapper, updated_wrapper)
    return updated_proto, True


def build_clip_fx_fieldsblob(
    fx_payload: bytes,
    enabled: bool = True,
) -> bytes:
    """Build a complete FieldsBlob with FL::ClipFX data and enable flags.

    Protobuf structure (confirmed via DB analysis 2026-04-05):
      field 1 (message) {
        field 1 (message) {
          field 1 (string) = "FL::ClipFX"
          field 2 (bytes)  = zlib(fx_payload)
        }
        field 4 (varint) = 1   // <-- FX enabled flag
      }
      field 15 (varint) = 4    // <-- clip AI features marker
    """
    if zstandard is None:
        raise RuntimeError("zstandard required")

    inner_msg = _build_clipfx_child_message(fx_payload)

    # Extra field 2 wrapper around the inner message (confirmed via byte diff)
    field2_wrapper = _encode_length_delimited(2, inner_msg)

    # Level 2 wrapper: field 1 { field 2 { ... } }
    level2 = _encode_length_delimited(1, field2_wrapper)

    # Level 1 wrapper: field 1 { ... } + enable flag
    wrapper = level2
    if enabled:
        wrapper += _encode_varint_field(4, 1)

    # Top-level: wrapper + field 15 = 4
    proto = _encode_length_delimited(1, wrapper)
    proto += _encode_varint_field(15, 4)

    # ZSTD compress
    cctx = zstandard.ZstdCompressor(level=3)
    compressed = cctx.compress(proto)

    # FieldsBlob: [4B version=2 BE] [4B body_len BE] [0x81 + ZSTD]
    body = bytes([0x81]) + compressed
    header = struct.pack('>I', 2) + struct.pack('>I', len(body))

    return header + body


def _wrap_zstd_fieldsblob(proto: bytes) -> bytes:
    compressed = zstandard.ZstdCompressor(level=3).compress(proto)
    body = bytes([0x81]) + compressed
    return struct.pack('>I', 2) + struct.pack('>I', len(body)) + body


def write_clip_fx_to_fieldsblob(
    original_fieldsblob: bytes,
    modified_fx_payload: bytes,
) -> bytes:
    """Replace the FL::ClipFX zlib payload in a FieldsBlob.

    Preserves sibling payloads such as FL::Retimer when an existing ClipFX child
    can be replaced in place. Falls back to a standalone ClipFX payload only when
    the original blob does not contain a replaceable ClipFX child.
    """
    if original_fieldsblob and zstandard is not None and len(original_fieldsblob) >= 10:
        try:
            proto = zstandard.ZstdDecompressor().decompress(original_fieldsblob[9:], max_output_size=16 * 1024 * 1024)
            updated_proto, replaced = _replace_clipfx_payload_in_proto(proto, modified_fx_payload)
            if replaced:
                compressed = zstandard.ZstdCompressor(level=3).compress(updated_proto)
                body = bytes([0x81]) + compressed
                return struct.pack('>I', 2) + struct.pack('>I', len(body)) + body
            if b"FL::" in proto:
                raise ValueError("Could not replace FL::ClipFX while preserving sibling FL payloads.")
        except ValueError:
            raise
        except Exception:
            pass
    return build_clip_fx_fieldsblob(modified_fx_payload, enabled=True)


def remove_clip_fx_from_fieldsblob(original_fieldsblob: bytes) -> bytes:
    """Remove the FL::ClipFX child from a FieldsBlob while preserving siblings."""
    if not original_fieldsblob or zstandard is None or len(original_fieldsblob) < 10:
        raise ValueError("Original FieldsBlob does not contain a removable FL::ClipFX payload.")
    proto = zstandard.ZstdDecompressor().decompress(original_fieldsblob[9:], max_output_size=16 * 1024 * 1024)
    updated_proto, removed = _remove_clipfx_payload_in_proto(proto)
    if not removed:
        raise ValueError("Could not remove FL::ClipFX from the original FieldsBlob.")
    compressed = zstandard.ZstdCompressor(level=3).compress(updated_proto)
    body = bytes([0x81]) + compressed
    return struct.pack('>I', 2) + struct.pack('>I', len(body)) + body


def insert_clip_fx_into_fieldsblob(original_fieldsblob: bytes, fx_payload: bytes) -> bytes:
    """Insert an FL::ClipFX child while preserving sibling clip payloads."""
    if not original_fieldsblob:
        return build_clip_fx_fieldsblob(fx_payload, enabled=True)
    if zstandard is None or len(original_fieldsblob) < 10:
        raise ValueError("Original FieldsBlob cannot accept an FL::ClipFX payload.")
    if original_fieldsblob[8] == 0x80 and original_fieldsblob.endswith(b"\x78\x04"):
        proto = original_fieldsblob[9:-2]
    else:
        proto = zstandard.ZstdDecompressor().decompress(original_fieldsblob[9:], max_output_size=16 * 1024 * 1024)
    if b"FL::ClipFX" in proto:
        raise ValueError("Original FieldsBlob already contains FL::ClipFX.")
    updated_proto, inserted = _insert_clipfx_payload_in_proto(proto, fx_payload)
    if not inserted:
        raise ValueError("Could not insert FL::ClipFX while preserving existing FieldsBlob payloads.")
    return _wrap_zstd_fieldsblob(updated_proto)
