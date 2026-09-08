"""Sequence- and track-scoped Fairlight dynamics parameter records.

The native record is [marker=1, parameter_id, lane_count, channel_values...].
The old donor-offset interpretation mistook channel values for duplicates and
could read record IDs as settings after a serialization-layout change.
"""
from __future__ import annotations

import importlib.resources as resources
import math
import sqlite3
import struct
import zlib

_FIXTURES_PACKAGE = "cutagent_cli"
_DYNAMICS_FIXTURES_DIR = ("fixtures", "dynamics")


def _dynamics_fixture_resource(fixture_name: str):
    return resources.files(_FIXTURES_PACKAGE).joinpath(*_DYNAMICS_FIXTURES_DIR, fixture_name)

# Zlib compression params (exact match not required — size field is updated)
_ZLIB_LEVEL = 6
_ZLIB_MEMLEVEL = 7
_ZLIB_STRATEGY = zlib.Z_DEFAULT_STRATEGY

# ── Param offset registry ──────────────────────────────────────────────
# Historical donor offsets retained only for fixture calibration; never used for live targeting.

PARAM_OFFSETS = {
    # Direct value params
    "make_up":            208854,  # x10 (103 = 10.3 dB)
    "comp_enable":        208926,  # 0/1
    "comp_threshold":     208974,  # x10, signed (dB)
    "comp_knee":          208998,  # direct 0-100
    "comp_mix":           209166,  # direct 0-100
    "gate_enable":        209094,  # 0/1
    "gate_threshold":     209142,  # x10, signed (dB)
    "limiter_enable":     209286,  # 0/1
    "limiter_input_enable": 209286,  # legacy read alias of limiter_enable
    "limiter_threshold":  209310,  # x10, signed (dB)

    # Normalized 0-100 params (exponential UI mapping)
    "comp_ratio":         208950,  # 0-100 → ~1.2:1 to ~20:1
    "comp_attack":        209022,  # 0-100 → 0.70ms to 100ms
    "comp_hold":          209046,  # 0-100 → 0ms to 4000ms
    "comp_release":       209070,  # 0-100 → 50ms to 4000ms
    "gate_range":         209118,  # 0-100 → 0 to ~60
    "gate_attack":        209190,  # 0-100
    "gate_hold":          209214,  # 0-100 → 0ms to ~4000ms
    "gate_release":       209238,  # 0-100
    "limiter_attack":     209334,  # 0-100
    "limiter_hold":       209358,  # 0-100
    "limiter_release":    209382,  # 0-100

    # Far-offset param (record ID 595, outside main block)
    "gate_ratio":         211758,  # 0-100 → 1:1.1 to 1:3.0
}

# Params that use x10 encoding (divide raw by 10 for display)
_X10_PARAMS = {"make_up", "comp_threshold", "gate_threshold", "limiter_threshold"}

# Params that are boolean enable/disable
_ENABLE_PARAMS = {"comp_enable", "gate_enable", "limiter_enable", "limiter_input_enable"}

# Params that use 0-100 normalized scale
_NORMALIZED_PARAMS = {
    "comp_ratio", "comp_attack", "comp_hold", "comp_release",
    "gate_ratio", "gate_range", "gate_attack", "gate_hold", "gate_release",
    "limiter_attack", "limiter_hold", "limiter_release",
}

# Direct 0-100 params (no scaling)
_DIRECT_PARAMS = {"comp_knee", "comp_mix"}


def _find_zlib_in_seq(data: bytes) -> tuple[int, int, int]:
    """Find zlib stream and size field in Sm2Sequence blob.

    Returns (zlib_offset, size_field_offset, fls_offset).
    """
    fls = "FLStudioModelBA".encode("utf-16-be")
    fls_idx = data.find(fls)
    if fls_idx < 0:
        raise ValueError("FLStudioModelBA not found in Sm2Sequence blob")

    zlib_idx = data.find(b"\x78\x9c", fls_idx)
    if zlib_idx < 0:
        raise ValueError("No zlib stream found after FLStudioModelBA")

    # Size field: BE uint32 at fls_idx + 32 (label+null) + 3
    size_field_offset = fls_idx + 32 + 3

    return zlib_idx, size_field_offset, fls_idx



# Stable parameter IDs verified against native records. Limiter enable is 285;
# parameter 283 alone does not activate limiting in native rendered audio.
PARAM_IDS = {
    "make_up": 265, "comp_enable": 268, "comp_ratio": 269,
    "comp_threshold": 270, "comp_knee": 271, "comp_attack": 272,
    "comp_hold": 273, "comp_release": 274, "gate_enable": 276,
    "gate_range": 277, "gate_threshold": 278, "comp_mix": 279,
    "gate_attack": 280, "gate_hold": 281, "gate_release": 282,
    "limiter_enable": 285,
    "limiter_threshold": 286, "limiter_attack": 287,
    "limiter_hold": 288, "limiter_release": 289, "gate_ratio": 595,
}


def _invalid(message):
    from ..errors import ValidationError
    return ValidationError(message)


def _parameter_records(decomp, table):
    """Walk the verified audio mixer table; never scan into another/bus table."""
    lanes = table["lane_count"]
    cursor = table["start_offset"]
    offsets = {}
    required = set(PARAM_IDS.values())
    for _ in range(4096):
        if cursor + 12 > len(decomp):
            break
        marker, parameter, count = struct.unpack_from("<iii", decomp, cursor)
        if marker != 1 or count < 1 or count > 65536 or cursor + 12 + 4 * count > len(decomp):
            break
        if parameter in required:
            if count != lanes:
                raise _invalid("Fairlight dynamics parameter channel count disagrees with the audio mixer.")
            if parameter in offsets:
                raise _invalid("Fairlight dynamics parameter identity is ambiguous.")
            offsets[parameter] = cursor + 12
        cursor += 12 + 4 * count
    if set(offsets) != required:
        raise _invalid("Fairlight dynamics channel records are unavailable for this timeline.")
    return offsets


def _target(cursor, *, sequence_id, track):
    from . import fairlight_ops
    if not isinstance(sequence_id, str) or not sequence_id:
        raise _invalid("Fairlight dynamics requires an exact active timeline sequence.")
    if isinstance(track, bool) or not isinstance(track, int) or track < 1:
        raise _invalid("Fairlight dynamics requires a positive audio track index.")
    rows = fairlight_ops._fetch_audio_track_rows(cursor, sequence=sequence_id)
    blob = fairlight_ops._fetch_sequence_fields_blob(cursor, sequence=sequence_id)
    decomp, zlib_idx, size_field_offset, unused, overhead = fairlight_ops._decode_fairlight_model(blob)
    target = fairlight_ops._mixer_target_from_record_table(
        cursor, rows, sequence=sequence_id, index=track, decomp=decomp,
        param_id=fairlight_ops.FAIRLIGHT_MIXER_RECORD_FADER_PARAM,
    )
    if target is None or target.get("record_table_blocker"):
        raise _invalid("Fairlight dynamics has no verified channel binding for this audio track.")
    records = _parameter_records(decomp, target["record_table"])
    offsets = {name: [records[parameter] + 4 * lane for lane in range(
        target["channel_start"], target["channel_start"] + target["channel_count"]
    )] for name, parameter in PARAM_IDS.items()}
    return {"track": target["track"], "offsets": offsets, "blob": blob,
            "decomp": decomp, "zlib_idx": zlib_idx, "size_field_offset": size_field_offset,
            "unused": unused, "overhead": overhead, "lane_scope": target["record_table_lane_scope"]}


def _decode_value(name, raw):
    if name in _ENABLE_PARAMS:
        if raw not in (0, 1):
            raise _invalid("Fairlight dynamics enable record has an invalid channel value.")
        return bool(raw)
    if name in _NORMALIZED_PARAMS | _DIRECT_PARAMS and not 0 <= raw <= 100:
        raise _invalid("Fairlight dynamics normalized record has an invalid channel value.")
    return raw / 10.0 if name in _X10_PARAMS else raw


def _encode_value(name, value):
    name = "limiter_enable" if name == "limiter_input_enable" else name
    if name not in PARAM_IDS:
        raise _invalid("Unknown Fairlight dynamics parameter.")
    if name in _ENABLE_PARAMS:
        if not isinstance(value, bool):
            raise _invalid("Fairlight dynamics enable values must be boolean.")
        return int(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise _invalid("Fairlight dynamics values must be finite numbers.")
    raw = round(value * 10) if name in _X10_PARAMS else round(value)
    if not -(2 ** 31) <= raw < 2 ** 31:
        raise _invalid("Fairlight dynamics value exceeds the native parameter range.")
    _decode_value(name, raw)
    return raw


def normalize_params(params):
    """Preserve the historical input-enable alias without writing parameter 283."""
    params = dict(params)
    if "limiter_input_enable" in params:
        value = params.pop("limiter_input_enable")
        if "limiter_enable" in params and params["limiter_enable"] != value:
            raise _invalid("Conflicting limiter enable values.")
        params["limiter_enable"] = value
    return params


def read_dynamics(db_path, *, sequence_id=None, track=1):
    from pathlib import Path
    connection = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        return read_dynamics_from_cursor(connection.cursor(), sequence_id=sequence_id, track=track)
    finally:
        connection.close()


def read_dynamics_from_cursor(cursor, *, sequence_id=None, track=1):
    target = _target(cursor, sequence_id=sequence_id, track=track)
    channels = {name: [_decode_value(name, struct.unpack_from("<i", target["decomp"], offset)[0])
                       for offset in offsets] for name, offsets in target["offsets"].items()}
    if any(len(set(values)) != 1 for values in channels.values()):
        raise _invalid("Fairlight dynamics channels disagree; no single track value can be reported.")
    channels["limiter_input_enable"] = list(channels["limiter_enable"])
    return {"status": "ok", "sequence_id": sequence_id, "track": target["track"],
            "channel_values": channels, "lane_scope": target["lane_scope"],
            **{name: values[0] for name, values in channels.items()}}


def write_dynamics_params_with_cursor(cursor, params, *, sequence_id=None, track=1, expected_track_id=None):
    from . import fairlight_ops
    encoded = {name: _encode_value(name, value) for name, value in normalize_params(params).items()}
    if not encoded:
        raise _invalid("At least one dynamics parameter is required.")
    target = _target(cursor, sequence_id=sequence_id, track=track)
    if expected_track_id is not None and target["track"]["track_id"] != expected_track_id:
        raise _invalid("Fairlight dynamics audio track changed before mutation.")
    before = read_dynamics_from_cursor(cursor, sequence_id=sequence_id, track=track)
    for name, raw in encoded.items():
        for offset in target["offsets"][name]:
            struct.pack_into("<i", target["decomp"], offset, raw)
    new_blob = fairlight_ops._encode_fairlight_model(
        seq_blob=target["blob"], decomp=bytes(target["decomp"]),
        zlib_idx=target["zlib_idx"], size_field_offset=target["size_field_offset"],
        unused=target["unused"], overhead=target["overhead"],
    )
    cursor.execute("UPDATE Sm2Sequence SET FieldsBlob = ? WHERE Sm2Sequence_id = ?", (new_blob, sequence_id))
    if cursor.rowcount != 1:
        raise _invalid("Fairlight dynamics requires one exact sequence write.")
    return {"status": "ok", "sequence_id": sequence_id, "track": target["track"],
            "params": {name: {"old": before[name], "new": _decode_value(name, raw)} for name, raw in encoded.items()},
            "blob_size": len(new_blob)}
