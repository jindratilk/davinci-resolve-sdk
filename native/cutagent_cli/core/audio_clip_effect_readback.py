"""Strict read-only Project.db inspection for audio clip effects."""

from __future__ import annotations

import hashlib
import math
import re
import sqlite3
import struct
from typing import Any
import zlib

from . import audio_clip_fx, audio_eq_db, clip_effects_db


class AudioClipEffectReadbackError(ValueError):
    """Persisted audio clip effect state was malformed or ambiguous."""


_PLUGIN_PATTERN = re.compile(rb"bmd:[^:\x00]+:\d+")
_PARAM_PATTERNS = (
    re.compile(rb"BMD[A-Za-z0-9]+::[A-Z0-9_]+"),
    re.compile(rb"UI_[A-Z_]+"),
    re.compile(rb"WRITE_[A-Z_]+"),
)


def _fields(message: bytes) -> list[tuple[int, int, int, bytes, int, int]]:
    try:
        return audio_clip_fx._iter_proto_fields(message)
    except ValueError as exc:
        raise AudioClipEffectReadbackError("malformed FieldsBlob protobuf") from exc


def _named_clip_fx_children(message: bytes) -> list[bytes]:
    matches: list[bytes] = []
    for _start, _end, _number, value, _value_start, _value_end in _fields(message):
        if not value:
            continue
        try:
            child_fields = _fields(value)
        except AudioClipEffectReadbackError:
            continue
        names = [
            field_value
            for _s, _e, number, field_value, _vs, _ve in child_fields
            if number == 1 and field_value
        ]
        if names == [b"FL::ClipFX"]:
            matches.append(value)
            continue
        matches.extend(_named_clip_fx_children(value))
    return matches


def _decode_named_clip_fx(fields_blob: bytes) -> bytes | None:
    if len(fields_blob) < 10:
        raise AudioClipEffectReadbackError("FieldsBlob is too short")
    version, body_size = struct.unpack(">II", fields_blob[:8])
    if version != 2 or body_size != len(fields_blob) - 8 or fields_blob[8] not in (0x80, 0x81):
        raise AudioClipEffectReadbackError("unsupported FieldsBlob envelope")
    if fields_blob[8] == 0x80:
        proto = fields_blob[9:]
    else:
        if audio_clip_fx.zstandard is None:
            raise AudioClipEffectReadbackError("zstandard is unavailable")
        try:
            proto = audio_clip_fx.zstandard.ZstdDecompressor().decompress(
                fields_blob[9:], max_output_size=16 * 1024 * 1024
            )
        except Exception as exc:
            raise AudioClipEffectReadbackError("FieldsBlob zstd payload is unreadable") from exc

    children = _named_clip_fx_children(proto)
    if not children:
        return None
    if len(children) != 1:
        raise AudioClipEffectReadbackError("FieldsBlob must contain exactly one named FL::ClipFX child")
    child_fields = _fields(children[0])
    if len(child_fields) != 2 or [field[2] for field in child_fields] != [1, 2]:
        raise AudioClipEffectReadbackError("FL::ClipFX child has an unsupported field structure")
    if child_fields[0][3] != b"FL::ClipFX":
        raise AudioClipEffectReadbackError("FL::ClipFX child name is invalid")
    wrapped = child_fields[1][3]
    if len(wrapped) < 6:
        raise AudioClipEffectReadbackError("FL::ClipFX compressed payload is too short")
    expected_size = struct.unpack(">I", wrapped[:4])[0]
    decoder = zlib.decompressobj()
    try:
        payload = decoder.decompress(wrapped[4:]) + decoder.flush()
    except zlib.error as exc:
        raise AudioClipEffectReadbackError("FL::ClipFX zlib payload is unreadable") from exc
    if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise AudioClipEffectReadbackError("FL::ClipFX zlib payload has trailing or incomplete data")
    if len(payload) != expected_size or not payload.startswith(audio_clip_fx.FX_MAGIC):
        raise AudioClipEffectReadbackError("FL::ClipFX payload size or magic is invalid")
    return payload


def _strict_plugins(payload: bytes) -> tuple[list[dict[str, str]], dict[str, list[str]]]:
    markers = list(_PLUGIN_PATTERN.finditer(payload))
    if not markers:
        raise AudioClipEffectReadbackError("FL::ClipFX payload has no BMD plugin identity")
    if len(payload) < 20:
        raise AudioClipEffectReadbackError("FL::ClipFX binary header is truncated")
    version, total_size, _field_count, plugin_count = struct.unpack("<IIII", payload[4:20])
    if version != 1 or total_size != len(payload) - 12 or plugin_count != len(markers):
        raise AudioClipEffectReadbackError("FL::ClipFX binary header does not match its payload")
    plugins: list[dict[str, str]] = []
    unknown: dict[str, list[str]] = {}
    seen_ids: set[str] = set()
    for index, marker in enumerate(markers):
        plugin_id = marker.group().decode("ascii")
        if plugin_id in seen_ids:
            raise AudioClipEffectReadbackError("FL::ClipFX payload has duplicate plugin identity")
        seen_ids.add(plugin_id)
        name = plugin_id.split(":", 2)[1]
        plugins.append({"pluginId": plugin_id, "name": name})
        block_end = markers[index + 1].start() if index + 1 < len(markers) else len(payload)
        block = payload[marker.start():block_end]
        names = sorted({
            match.group().decode("ascii")
            for pattern in _PARAM_PATTERNS
            for match in pattern.finditer(block)
        })
        unknown[plugin_id] = names
    return plugins, unknown


def _exact_default_fairlight_eq(payload: bytes) -> dict[str, float] | None:
    digest = hashlib.sha256(payload).hexdigest()
    if digest != audio_clip_fx.FAIRLIGHT_EQ_DEFAULT_PAYLOAD_SHA256:
        return None
    state = audio_clip_fx.parse_clip_fx(payload)
    if len(state.plugins) != 1 or state.plugins[0].plugin_id != audio_clip_fx.PLUGIN_FAIRLIGHT_EQ:
        raise AudioClipEffectReadbackError("recognized Fairlight EQ fixture has invalid plugin identity")
    values: dict[str, float] = {}
    for param in state.plugins[0].params:
        start = int(param.offset)
        end = start + len(param.name.encode("ascii"))
        value_offset = audio_clip_fx._fixed_param_value_offset(payload, start, end)
        if value_offset != start + 64:
            raise AudioClipEffectReadbackError("recognized Fairlight EQ parameter is not canonical")
        value = float(struct.unpack("<f", payload[value_offset:value_offset + 4])[0])
        if not math.isfinite(value) or param.name in values:
            raise AudioClipEffectReadbackError("recognized Fairlight EQ parameters are invalid")
        values[param.name] = round(value, 6)
    if not values:
        raise AudioClipEffectReadbackError("recognized Fairlight EQ fixture has no parameters")
    return values


def _decode_native_audio_controls(blob: bytes) -> tuple[list[dict[str, Any]], bool]:
    """Read known controls and prove whether every effect group has a known identity."""
    result = []
    saw_known_group = False
    identities_complete = True
    names = {124: {95: "gainDb", 97: "fadeInFrames", 98: "fadeOutFrames",
                   99: "fadeInControlPoint", 100: "fadeOutControlPoint"},
             144: {96: "pan"}}
    for entry in clip_effects_db.split_packed_blob_chain(blob):
        fields = clip_effects_db._parse_wire_fields(clip_effects_db._effect_proto(entry))
        if not fields:
            return [], False
        for top in fields:
            if top.number != 1 or top.wire_type != 2 or not isinstance(top.value, bytes):
                identities_complete = False
                continue
            effect_id = clip_effects_db._effect_message_id(top.value)
            if effect_id not in names:
                identities_complete = False
                continue
            effect_fields = clip_effects_db._parse_wire_fields(top.value)
            if effect_fields is None:
                identities_complete = False
                continue
            saw_known_group = True
            params = {}
            unread = []
            seen = set()
            for field in effect_fields:
                if field.number == 1 and field.wire_type == 0:
                    continue
                if field.number != 9 or field.wire_type != 2:
                    unread.append({"field": field.number, "wireType": field.wire_type, "rawHex": field.raw.hex()})
                    continue
                nested = clip_effects_db._parse_wire_fields(field.value)
                parameter_id = clip_effects_db._audio_param_id(field.value)
                key = names[effect_id].get(parameter_id)
                if parameter_id in seen and key:
                    params.pop(key, None)
                if (not key or parameter_id in seen or nested is None or
                        [(f.number, f.wire_type) for f in nested] != [(1, 0), (3, 2)]):
                    unread.append({"field": 9, "parameterId": parameter_id, "rawHex": field.raw.hex()})
                    continue
                seen.add(parameter_id)
                payload = nested[1].value
                value = None
                if parameter_id in (99, 100) and len(payload) == 20 and payload[:4] == b"\x0a\x12\x3a\x10":
                    x, y = struct.unpack(">dd", payload[4:])
                    if math.isfinite(x) and math.isfinite(y):
                        value = {"x": x, "y": y}
                elif parameter_id not in (99, 100) and len(payload) == 11 and payload[:3] == b"\x0a\x09\x11":
                    number = struct.unpack("<d", payload[3:])[0]
                    if math.isfinite(number):
                        value = number
                if value is None:
                    unread.append({"field": 9, "parameterId": parameter_id, "rawHex": field.raw.hex()})
                else:
                    params[key] = value
            if any(
                not (
                    (field.get("field"), field.get("wireType")) == (7, 0)
                    or (field.get("field"), field.get("rawHex")) == (9, "4a00")
                )
                for field in unread
            ):
                identities_complete = False
            result.append({"effectId": effect_id, "kind": "audioMix" if effect_id == 124 else "audioPan",
                           "parameters": params, "unreadFields": unread})
    return result, bool(saw_known_group and identities_complete)


def _native_audio_controls(blob: bytes) -> list[dict[str, Any]]:
    """Read exact known parameter encodings; retain every other field explicitly."""
    return _decode_native_audio_controls(blob)[0]


def read_audio_clip_effects(cursor: sqlite3.Cursor, *, item_id: str) -> dict[str, Any]:
    """Read exact, non-heuristic effect evidence for one audio timeline item."""

    normalized_id = str(item_id or "").strip()
    if not normalized_id:
        raise AudioClipEffectReadbackError("audio item identity is required")
    rows = cursor.execute(
        """
        SELECT Sm2TiItem_id, DbType, FieldsBlob, EffectFiltersBA
        FROM Sm2TiItem WHERE Sm2TiItem_id = ?
        """,
        (normalized_id,),
    ).fetchall()
    if len(rows) != 1:
        raise AudioClipEffectReadbackError("audio item identity was not found in Project.db")
    row = rows[0]
    persisted_id = str(row[0] if isinstance(row, tuple) else row["Sm2TiItem_id"])
    db_type = str(row[1] if isinstance(row, tuple) else row["DbType"])
    fields_blob = row[2] if isinstance(row, tuple) else row["FieldsBlob"]
    effect_filters = row[3] if isinstance(row, tuple) else row["EffectFiltersBA"]
    if persisted_id != normalized_id or db_type != "Sm2TiAudioClip":
        raise AudioClipEffectReadbackError("Project.db row does not match the exact audio item identity")

    clip_fx = None
    if fields_blob:
        payload = _decode_named_clip_fx(bytes(fields_blob))
        if payload is not None:
            plugins, unknown = _strict_plugins(payload)
            exact_eq = _exact_default_fairlight_eq(payload)
            if exact_eq is not None:
                unknown[audio_clip_fx.PLUGIN_FAIRLIGHT_EQ] = []
            clip_fx = {
                "payloadSha256": hashlib.sha256(payload).hexdigest(),
                "payloadBytes": len(payload),
                "plugins": plugins,
                "exactFixtureParameters": (
                    {audio_clip_fx.PLUGIN_FAIRLIGHT_EQ: exact_eq} if exact_eq is not None else {}
                ),
                "unknownParameterRemainder": [
                    {"pluginId": plugin["pluginId"], "names": unknown[plugin["pluginId"]]}
                    for plugin in plugins
                ],
            }

    archive_eq = None
    if effect_filters:
        eq_state = audio_eq_db.read_eq_state(cursor, audio_item_id=normalized_id)
        if bool(eq_state.get("recognized")):
            archive_eq = {
                "preset": eq_state.get("preset"),
                "summary": eq_state.get("summary"),
                "family": eq_state.get("effect_filters_family"),
                "payloadSha256": hashlib.sha256(bytes(effect_filters)).hexdigest(),
                "payloadBytes": len(bytes(effect_filters)),
            }

    native_controls, native_identities_complete = (
        _decode_native_audio_controls(bytes(effect_filters)) if effect_filters else ([], False)
    )
    unknown_effect_filters = None
    if effect_filters and archive_eq is None and not native_identities_complete:
        raw = bytes(effect_filters)
        unknown_effect_filters = {
            "payloadSha256": hashlib.sha256(raw).hexdigest(),
            "payloadBytes": len(raw),
            "reason": "EffectFiltersBA is not fully decoded; known native audio controls are reported separately",
        }
    return {
        "itemId": normalized_id,
        "clipFx": clip_fx,
        "archiveEq": archive_eq,
        "nativeAudioControls": native_controls,
        "unknownEffectFilters": unknown_effect_filters,
        "source": "Project.db Sm2TiItem.FieldsBlob/EffectFiltersBA",
    }
