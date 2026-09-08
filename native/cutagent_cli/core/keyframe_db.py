"""DB-backed timeline item Inspector keyframe helpers."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import sqlite3
import struct
from typing import Any, Callable

try:  # pragma: no cover - covered by runtime dependency tests elsewhere
    import zstandard
except Exception:  # pragma: no cover
    zstandard = None

from ..errors import APICallFailed, ClipNotFound, SdkMutationStaleRevision, ValidationError
from . import clip_effects_db, db_session, db_timeline_rows, db_timeline_selection
from .db_timeline_selection import LiveItemRef
from .sdk_clip_motion import expected_target, resolve_exact_timeline_item
from .video_fade_readback import is_strict_video_fade_entry


_PACKED_HEADER_SIZE = 8
_DEFAULT_KEYFRAME_FLAGS = 0x000C0000

_INTERPOLATION_TO_CODE = {
    "linear": 0,
    "bezier": 1,
    "ease-in": 2,
    "ease-out": 3,
}
_CODE_TO_INTERPOLATION = {
    0: "Linear",
    1: "Bezier",
    2: "Ease-In",
    3: "Ease-Out",
}
_INTERPOLATION_TO_FLAGS = {
    0: _DEFAULT_KEYFRAME_FLAGS,
    1: _DEFAULT_KEYFRAME_FLAGS | 0x01,
    2: _DEFAULT_KEYFRAME_FLAGS | 0x02,
    3: _DEFAULT_KEYFRAME_FLAGS | 0x03,
}


@dataclass(frozen=True)
class _GroupSpec:
    kind: int
    slot_count: int
    slot_by_param: dict[int, int]


_GROUP_SPECS: dict[str, _GroupSpec] = {
    "transform": _GroupSpec(
        kind=4,
        slot_count=12,
        slot_by_param={
            42: 0,  # ZoomX
            43: 1,  # ZoomY
            44: 2,  # ZoomGang
            40: 3,  # Pan
            41: 4,  # Tilt
            47: 5,  # RotationAngle
            48: 6,  # AnchorPoint vector, not exposed until X/Y vector encoding is supported
            45: 8,  # Pitch
            46: 9,  # Yaw
        },
    ),
    "crop": _GroupSpec(
        kind=6,
        slot_count=6,
        slot_by_param={
            54: 0,
            55: 1,
            56: 2,
            57: 3,
            58: 4,
        },
    ),
    "opacity": _GroupSpec(kind=2, slot_count=2, slot_by_param={1: 1}),
    "audio_gain": _GroupSpec(kind=124, slot_count=5, slot_by_param={95: 0}),
    "audio_pan": _GroupSpec(kind=144, slot_count=1, slot_by_param={96: 0}),
}


@dataclass(frozen=True)
class PropertySpec:
    public_name: str
    param_id: int
    group_name: str
    media_kind: str
    scale_axis: str | None = None
    aliases: tuple[str, ...] = ()

    @property
    def group(self) -> _GroupSpec:
        return _GROUP_SPECS[self.group_name]


_VIDEO_PROPERTY_SPECS: dict[str, PropertySpec] = {
    "Pan": PropertySpec("Pan", 40, "transform", "video", scale_axis="width"),
    "Tilt": PropertySpec("Tilt", 41, "transform", "video", scale_axis="height"),
    "ZoomX": PropertySpec("ZoomX", 42, "transform", "video"),
    "ZoomY": PropertySpec("ZoomY", 43, "transform", "video"),
    "Rotation": PropertySpec("Rotation", 47, "transform", "video", aliases=("RotationAngle",)),
    "Pitch": PropertySpec("Pitch", 45, "transform", "video"),
    "Yaw": PropertySpec("Yaw", 46, "transform", "video"),
    "Opacity": PropertySpec("Opacity", 1, "opacity", "video"),
    "CropLeft": PropertySpec("CropLeft", 54, "crop", "video", scale_axis="width"),
    "CropRight": PropertySpec("CropRight", 55, "crop", "video", scale_axis="width"),
    "CropTop": PropertySpec("CropTop", 56, "crop", "video", scale_axis="height"),
    "CropBottom": PropertySpec("CropBottom", 57, "crop", "video", scale_axis="height"),
}
_AUDIO_PROPERTY_SPECS: dict[str, PropertySpec] = {
    "Volume": PropertySpec("Volume", 95, "audio_gain", "audio"),
    "AudioPan": PropertySpec("AudioPan", 96, "audio_pan", "audio", aliases=("Audio Pan",)),
}
_PROPERTY_SPECS: dict[str, PropertySpec] = {**_VIDEO_PROPERTY_SPECS, **_AUDIO_PROPERTY_SPECS}
_PROPERTY_BY_PARAM_ID: dict[int, PropertySpec] = {spec.param_id: spec for spec in _PROPERTY_SPECS.values()}
_PROPERTY_ALIASES: dict[str, str] = {}
for _name, _spec in _PROPERTY_SPECS.items():
    _PROPERTY_ALIASES[_name.casefold()] = _name
    for _alias in _spec.aliases:
        _PROPERTY_ALIASES[_alias.casefold()] = _name


@dataclass(frozen=True)
class InspectorKeyframe:
    local_frame: int
    value: float
    interpolation_code: int = 0
    interpolation_flags: int = _DEFAULT_KEYFRAME_FLAGS

    def to_dict(self, *, item_start: int = 0, spec: PropertySpec | None = None, resolution: tuple[int, int] = (1920, 1080)) -> dict[str, Any]:
        public_value = _to_public_value(self.value, spec, resolution) if spec is not None else float(self.value)
        return {
            "frame": int(item_start) + int(self.local_frame),
            "local_frame": int(self.local_frame),
            "value": float(public_value),
            "db_value": float(self.value),
            "interpolation": _CODE_TO_INTERPOLATION.get(int(self.interpolation_code), "Unknown"),
            "interpolation_code": int(self.interpolation_code),
            "interpolation_flags": int(self.interpolation_flags),
        }


@dataclass
class _Group:
    kind: int
    entries: list[bytes]
    native_header: bytes = b""


@dataclass(frozen=True)
class _KeyframeTarget:
    item_ref: LiveItemRef
    db_type: str
    spec: PropertySpec


def supported_properties() -> list[str]:
    return sorted(_PROPERTY_SPECS)


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    pos = int(offset)
    while pos < len(data) and shift <= 63:
        byte = data[pos]
        value |= (byte & 0x7F) << shift
        pos += 1
        if not byte & 0x80:
            return value, pos
        shift += 7
    raise ValueError("truncated varint")


def _write_varint(value: int) -> bytes:
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


def _pack_field(field_number: int, wire_type: int) -> bytes:
    return _write_varint((int(field_number) << 3) | int(wire_type))


def _length_field(field_number: int, payload: bytes) -> bytes:
    raw = bytes(payload)
    return _pack_field(field_number, 2) + _write_varint(len(raw)) + raw


def _pack_blob_payload(payload: bytes, *, compress: bool = True) -> bytes:
    if compress and zstandard is not None:
        compressed = zstandard.ZstdCompressor(level=3).compress(bytes(payload))
        body = b"\x81" + compressed
    else:
        body = b"\x80" + bytes(payload)
    return struct.pack(">II", 2, len(body)) + body


def _unpack_blob_payload(blob: bytes | bytearray | memoryview | None) -> bytes:
    raw = bytes(blob or b"")
    if len(raw) < _PACKED_HEADER_SIZE:
        return raw
    version, body_size = struct.unpack(">II", raw[:_PACKED_HEADER_SIZE])
    body = raw[_PACKED_HEADER_SIZE:]
    if version != 2 or body_size != len(body):
        return raw
    if body.startswith(b"\x80"):
        return body[1:]
    if body.startswith(b"\x81"):
        if zstandard is None:
            raise ValidationError(
                "Project.db Inspector keyframe payload is zstd-compressed, but zstandard is unavailable.",
                details={"reason": "missing_zstandard"},
                recoverability="manual",
            )
        return zstandard.ZstdDecompressor().decompress(body[1:])
    return body


def _parse_groups(payload: bytes) -> list[_Group]:
    groups: list[_Group] = []
    offset = 0
    while offset < len(payload):
        if payload[offset] != 0x0A:
            raise ValidationError(
                "Could not decode timeline item EffectFiltersBA groups.",
                details={"reason": "unexpected_group_tag", "offset": offset, "byte": payload[offset]},
                recoverability="manual",
            )
        length, start = _read_varint(payload, offset + 1)
        end = start + length
        if end > len(payload):
            raise ValidationError(
                "Could not decode timeline item EffectFiltersBA groups.",
                details={"reason": "truncated_group", "offset": offset, "length": length},
                recoverability="manual",
            )
        inner = payload[start:end]
        if not inner or inner[0] != 0x08:
            raise ValidationError(
                "Could not decode timeline item EffectFiltersBA group kind.",
                details={"reason": "missing_group_kind", "offset": offset},
                recoverability="manual",
            )
        kind, entry_offset = _read_varint(inner, 1)
        # DaVinci Resolve can persist field 7 before the parameter entries on
        # reopen. Preserve its encoded value without assigning it semantics.
        native_header = b""
        if entry_offset < len(inner) and inner[entry_offset] == 0x38:
            header_start = entry_offset
            _value, entry_offset = _read_varint(inner, entry_offset + 1)
            native_header = inner[header_start:entry_offset]
        entries: list[bytes] = []
        while entry_offset < len(inner):
            if inner[entry_offset] != 0x4A:
                raise ValidationError(
                    "Could not decode timeline item EffectFiltersBA group entry.",
                    details={"reason": "unexpected_entry_tag", "offset": entry_offset, "kind": kind},
                    recoverability="manual",
                )
            entry_length, entry_start = _read_varint(inner, entry_offset + 1)
            entry_end = entry_start + entry_length
            if entry_end > len(inner):
                raise ValidationError(
                    "Could not decode timeline item EffectFiltersBA group entry.",
                    details={"reason": "truncated_entry", "kind": kind, "entry_length": entry_length},
                    recoverability="manual",
                )
            entries.append(inner[entry_start:entry_end])
            entry_offset = entry_end
        groups.append(_Group(kind=int(kind), entries=entries, native_header=native_header))
        offset = end
    return groups


def _encode_groups(groups: list[_Group]) -> bytes:
    payload = bytearray()
    for group in groups:
        inner = bytearray(b"\x08" + _write_varint(int(group.kind)))
        inner += group.native_header
        for entry in group.entries:
            inner += b"\x4A" + _write_varint(len(entry)) + entry
        payload += _length_field(1, bytes(inner))
    return bytes(payload)


def _entry_param_id(entry: bytes) -> int | None:
    if not entry or entry[0] != 0x08:
        return None
    try:
        param_id, _ = _read_varint(entry, 1)
        return int(param_id)
    except Exception:
        return None


def _entry_keyframe_payload(entry: bytes) -> bytes | None:
    if not entry or entry[0] != 0x08:
        return None
    try:
        _param_id, offset = _read_varint(entry, 1)
    except Exception:
        return None
    while offset < len(entry):
        tag = entry[offset]
        offset += 1
        field_number = tag >> 3
        wire_type = tag & 0x07
        if wire_type != 2:
            return None
        length, start = _read_varint(entry, offset)
        end = start + length
        if end > len(entry):
            return None
        payload = entry[start:end]
        if field_number == 10:
            return payload
        offset = end
    return None


def _decode_keyframe_payload(
    payload: bytes | None,
    *,
    frame_origin: int = 0,
) -> list[InspectorKeyframe]:
    if not payload:
        return []
    raw = bytes(payload)
    if len(raw) < 4:
        return []
    marker = struct.unpack(">i", raw[:4])[0]
    if marker >= 0 or marker % 16 != 0:
        return []
    point_count = -marker // 16
    if len(raw) != 4 + point_count * 16:
        return []
    rows: list[InspectorKeyframe] = []
    offset = 4
    for _index in range(point_count):
        stored_frame = int.from_bytes(raw[offset : offset + 4], "little", signed=False)
        flags = int.from_bytes(raw[offset + 4 : offset + 8], "little", signed=False)
        value = struct.unpack("<d", raw[offset + 8 : offset + 16])[0]
        rows.append(
            InspectorKeyframe(
                local_frame=stored_frame - int(frame_origin),
                value=float(value),
                interpolation_code=_interpolation_code_from_flags(flags),
                interpolation_flags=flags,
            )
        )
        offset += 16
    return sorted(rows, key=lambda row: row.local_frame)


def _encode_keyframe_payload(
    points: list[InspectorKeyframe],
    *,
    frame_origin: int = 0,
) -> bytes:
    if not points:
        raise ValidationError("Timeline item keyframe payload requires at least one point.")
    marker = -16 * len(points)
    if marker < -(2**31):
        raise ValidationError("Timeline item keyframe payload has too many points.")
    sentinel = struct.pack(">i", marker)
    payload = bytearray(sentinel)
    for point in sorted(points, key=lambda row: row.local_frame):
        flags = _INTERPOLATION_TO_FLAGS.get(int(point.interpolation_code), int(point.interpolation_flags))
        stored_frame = int(frame_origin) + int(point.local_frame)
        if stored_frame < 0:
            raise ValidationError("Timeline item keyframe storage frame is negative.")
        payload += stored_frame.to_bytes(4, "little", signed=False)
        payload += int(flags).to_bytes(4, "little", signed=False)
        payload += struct.pack("<d", float(point.value))
    return bytes(payload)


def _encode_keyframe_entry(
    param_id: int,
    points: list[InspectorKeyframe],
    *,
    frame_origin: int = 0,
) -> bytes:
    payload = _encode_keyframe_payload(points, frame_origin=frame_origin)
    return b"\x08" + _write_varint(int(param_id)) + _length_field(10, payload)


def _interpolation_code_from_flags(flags: int) -> int:
    low = int(flags) & 0x03
    return low if low in _CODE_TO_INTERPOLATION else 0


def normalize_property(property_name: str) -> PropertySpec:
    key = str(property_name or "").strip()
    canonical = _PROPERTY_ALIASES.get(key.casefold())
    if canonical is None:
        raise ValidationError(
            "Unsupported timeline item Inspector keyframe property.",
            details={
                "property": property_name,
                "supported": supported_properties(),
            },
            recoverability="not_applicable",
        )
    return _PROPERTY_SPECS[canonical]


def normalize_interpolation(interpolation: str | int | None) -> int:
    if interpolation is None:
        return 0
    if isinstance(interpolation, int):
        if interpolation in _CODE_TO_INTERPOLATION:
            return int(interpolation)
        failure = ValidationError(
            "Invalid interpolation type.",
            details={"interpolation": interpolation, "allowed": list(_CODE_TO_INTERPOLATION.values())},
            recoverability="not_applicable",
        )
        failure.possible_mutation = "none"
        raise failure
    # Public SDK action schemas use snake_case (ease_in/ease_out), while the
    # native DB vocabulary and CLI display names use hyphens. Normalize both
    # spellings at the shared backend boundary so a schema-valid SDK request
    # cannot fail after the prepared action has begun mutating Resolve.
    key = str(interpolation).strip().lower().replace("_", "-")

    if key not in _INTERPOLATION_TO_CODE:
        failure = ValidationError(
            "Invalid interpolation type.",
            details={"interpolation_type": interpolation, "allowed": list(_CODE_TO_INTERPOLATION.values())},
            recoverability="not_applicable",
        )
        failure.possible_mutation = "none"
        raise failure
    return _INTERPOLATION_TO_CODE[key]


def _finite_value(value: float) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValidationError(
            "Keyframe value must be finite.",
            details={"value": str(value)},
            recoverability="not_applicable",
        )
    return number


def _timeline_resolution(conn: Any) -> tuple[int, int]:
    timeline = getattr(conn, "timeline", None)

    def _read_setting(name: str, default: int) -> int:
        if timeline is None or not hasattr(timeline, "GetSetting"):
            return default
        try:
            value = timeline.GetSetting(name)
            if value is None or value == "":
                return default
            return max(1, int(float(value)))
        except Exception:
            return default

    return (
        _read_setting("timelineResolutionWidth", 1920),
        _read_setting("timelineResolutionHeight", 1080),
    )


def _scale_for_spec(spec: PropertySpec | None, resolution: tuple[int, int]) -> float:
    if spec is None or spec.scale_axis is None:
        return 1.0
    if spec.scale_axis == "width":
        return float(resolution[0])
    if spec.scale_axis == "height":
        return float(resolution[1])
    return 1.0


def _to_db_value(public_value: float, spec: PropertySpec, resolution: tuple[int, int]) -> float:
    return float(public_value) / _scale_for_spec(spec, resolution)


def _to_public_value(db_value: float, spec: PropertySpec | None, resolution: tuple[int, int]) -> float:
    return float(db_value) * _scale_for_spec(spec, resolution)


def _timeline_name(conn: Any) -> str | None:
    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        return None
    try:
        return str(timeline.GetName() or "")
    except Exception:
        return None


def _resolve_keyframe_target(conn: Any, clip_name: str | None, spec: PropertySpec) -> _KeyframeTarget:
    sdk_target = expected_target()
    if sdk_target is not None:
        if spec.media_kind != "video":
            raise ValidationError("SDK clip motion keyframes support exact video targets only.")
        resolve_exact_timeline_item(conn, sdk_target)
        item_ref = LiveItemRef(
            track_type="video", track_index=int(sdk_target["trackIndex"]), name=str(sdk_target["name"]),
            start=int(sdk_target["recordStartFrame"]),
            duration=int(sdk_target["recordEndFrame"]) - int(sdk_target["recordStartFrame"]),
            item_id=str(sdk_target["id"]), linked_item_ids=tuple(sdk_target["linkedItemIds"]),
        )
        return _KeyframeTarget(item_ref=item_ref, db_type="Sm2TiVideoClip", spec=spec)
    if spec.media_kind == "audio":
        item_ref = db_timeline_selection.resolve_audio_group(conn, clip_name=clip_name)["audio"]
        return _KeyframeTarget(item_ref=item_ref, db_type="Sm2TiAudioClip", spec=spec)
    if spec.public_name == "Pan":
        try:
            item_ref = db_timeline_selection.resolve_video_group(conn, clip_name=clip_name)["video"]
            return _KeyframeTarget(item_ref=item_ref, db_type="Sm2TiVideoClip", spec=spec)
        except ClipNotFound:
            item_ref = db_timeline_selection.resolve_audio_group(conn, clip_name=clip_name)["audio"]
            return _KeyframeTarget(
                item_ref=item_ref,
                db_type="Sm2TiAudioClip",
                spec=_AUDIO_PROPERTY_SPECS["AudioPan"],
            )
    item_ref = db_timeline_selection.resolve_video_group(conn, clip_name=clip_name)["video"]
    return _KeyframeTarget(item_ref=item_ref, db_type="Sm2TiVideoClip", spec=spec)


def _check_record_frame(item_ref: LiveItemRef, frame: int) -> int:
    record_frame = int(frame)
    if record_frame < item_ref.start or record_frame >= item_ref.end:
        raise ValidationError(
            "Frame is outside clip bounds.",
            details={
                "frame": record_frame,
                "clip_start": int(item_ref.start),
                "clip_end": int(item_ref.end),
                "expected_domain": "record_frame",
            },
            recoverability="not_applicable",
        )
    return record_frame - int(item_ref.start)


def _read_points_from_groups(
    groups: list[_Group],
    spec: PropertySpec,
    *,
    frame_origin: int = 0,
) -> list[InspectorKeyframe]:
    for group in groups:
        if int(group.kind) != spec.group.kind:
            continue
        for entry in group.entries:
            if _entry_param_id(entry) != spec.param_id:
                continue
            return _decode_keyframe_payload(
                _entry_keyframe_payload(entry),
                frame_origin=frame_origin,
            )
    return []


def _ensure_group(groups: list[_Group], spec: PropertySpec) -> _Group:
    for group in groups:
        if int(group.kind) == spec.group.kind:
            while len(group.entries) < spec.group.slot_count:
                group.entries.append(b"")
            return group
    group = _Group(kind=spec.group.kind, entries=[b""] * spec.group.slot_count)
    groups.append(group)
    return group


def _write_points_to_groups(
    groups: list[_Group],
    spec: PropertySpec,
    points: list[InspectorKeyframe],
    *,
    frame_origin: int = 0,
) -> None:
    group = _ensure_group(groups, spec)
    slot = spec.group.slot_by_param.get(spec.param_id)
    if slot is None:
        raise ValidationError(
            "Unsupported timeline item Inspector keyframe property layout.",
            details={"property": spec.public_name, "param_id": spec.param_id, "group": spec.group_name},
            recoverability="manual",
        )
    while len(group.entries) <= slot:
        group.entries.append(b"")
    if points:
        group.entries[slot] = _encode_keyframe_entry(
            spec.param_id,
            points,
            frame_origin=frame_origin,
        )
    else:
        group.entries[slot] = b""


def _sync_zoom_counterpart(
    groups: list[_Group],
    spec: PropertySpec,
    before: list[InspectorKeyframe],
    updated: list[InspectorKeyframe],
    *,
    frame_origin: int = 0,
) -> None:
    counterpart_param_id = {42: 43, 43: 42}.get(spec.param_id)
    if counterpart_param_id is None:
        return
    counterpart = _PROPERTY_BY_PARAM_ID[counterpart_param_id]
    counterpart_before = _read_points_from_groups(
        groups,
        counterpart,
        frame_origin=frame_origin,
    )
    if counterpart_before and counterpart_before != before:
        return
    _write_points_to_groups(
        groups,
        counterpart,
        updated,
        frame_origin=frame_origin,
    )


def _decode_effect_filters(effect_filters: bytes | None) -> tuple[list[bytes], list[_Group]]:
    entries = clip_effects_db.split_packed_blob_chain(effect_filters)
    if not entries:
        return [], []
    if is_strict_video_fade_entry(entries[0]):
        return list(entries), []
    primary_payload = _unpack_blob_payload(entries[0])
    return list(entries[1:]), _parse_groups(primary_payload) if primary_payload else []


def _encode_effect_filters(extra_entries: list[bytes], groups: list[_Group]) -> bytes | None:
    payload = _encode_groups(groups)
    entries = [_pack_blob_payload(payload, compress=True), *extra_entries] if payload else list(extra_entries)
    return clip_effects_db.join_packed_blob_chain(entries)


def _reject_unsafe_video_fade_keyframe_write(
    extra_entries: list[bytes],
    *,
    spec: PropertySpec,
    item_id: str,
) -> None:
    if spec.media_kind != "video" or not any(
        is_strict_video_fade_entry(entry) for entry in extra_entries
    ):
        return
    failure = ValidationError(
        "Inspector keyframe mutation is unavailable while the video clip has a native fade.",
        details={
            "reason": "video_fade_keyframe_coexistence_not_native_safe",
            "item_id": item_id,
            "property": spec.public_name,
            "preserved": "existing_video_fade",
            "native_evidence": (
                "DaVinci Resolve canonicalized the combined payload after reopen and dropped the fade."
            ),
        },
        recoverability="manual",
    )
    failure.possible_mutation = "none"
    raise failure


def _ensure_effect_fields_blob(fields_blob: bytes | None) -> bytes | None:
    if not fields_blob:
        return fields_blob
    entries = clip_effects_db.split_packed_blob_chain(fields_blob)
    if not entries:
        return fields_blob
    try:
        payload = _unpack_blob_payload(entries[0])
    except Exception:
        return fields_blob
    updated = _ensure_effect_fields_marker(payload)
    if updated == payload:
        return fields_blob
    return clip_effects_db.join_packed_blob_chain([_pack_blob_payload(updated), *entries[1:]])


def _ensure_effect_fields_marker(payload: bytes) -> bytes:
    marker = bytes.fromhex("1a07080110a6bec32e")

    def patch_container(data: bytes, depth: int) -> tuple[bytes, int]:
        fields = clip_effects_db._parse_wire_fields(data)
        if fields is None:
            return data, 0
        # FieldsBlob wraps clip metadata in field 1; its linked-item payload is
        # opaque. Match actual protobuf fields, never bytes inside that payload.
        anchors = [index for index, field in enumerate(fields)
                   if field.number == 4 and field.wire_type == 0 and field.value == 1]
        if anchors:
            if len(anchors) != 1:
                return data, len(anchors)
            if any(field.raw == marker for field in fields):
                return data, 1
            parts = [field.raw for field in fields]
            parts.insert(anchors[0], marker)
            return b"".join(parts), 1
        if depth == 2:
            return data, 0
        parts = []
        matches = 0
        for field in fields:
            if field.number == 1 and field.wire_type == 2 and isinstance(field.value, bytes):
                updated, count = patch_container(field.value, depth + 1)
                matches += count
                parts.append(_length_field(1, updated) if updated != field.value else field.raw)
            else:
                parts.append(field.raw)
        return b"".join(parts), matches

    updated, matches = patch_container(payload, 0)
    if matches > 1:
        raise ValidationError("Timeline item Inspector metadata has ambiguous effect containers.")
    return updated


def _row_keyframe_origin(row: dict[str, Any], spec: PropertySpec) -> int:
    # Retained native evidence establishes the Sm2TiItem.In coordinate for
    # video Inspector curves. Audio automation has a separate payload family
    # and may use fractional native In values, so preserve its current domain
    # until an audio-specific fixture proves the corresponding conversion.
    if spec.media_kind != "video":
        return 0
    raw = row.get("In")
    if raw is None or raw == "":
        return 0
    try:
        return int(float(str(raw).strip()))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValidationError(
            "Timeline item keyframe storage origin is invalid.",
            details={"in": raw},
            recoverability="manual",
        ) from exc


def _row_keyframes(row: dict[str, Any], spec: PropertySpec) -> list[InspectorKeyframe]:
    _extra, groups = _decode_effect_filters(row.get("EffectFiltersBA"))
    return _read_points_from_groups(
        groups,
        spec,
        frame_origin=_row_keyframe_origin(row, spec),
    )


def _rows_payload(
    *,
    clip: str,
    item_ref: LiveItemRef,
    spec: PropertySpec,
    points: list[InspectorKeyframe],
    resolution: tuple[int, int],
) -> dict[str, Any]:
    rows = [point.to_dict(item_start=item_ref.start, spec=spec, resolution=resolution) for point in points]
    return {
        "clip": clip,
        "property": spec.public_name,
        "count": len(rows),
        "keyframes": rows,
        "route": "keyframe_db",
        "storage_domain": "clip_local_frame",
        "readback_domain": "record_frame",
    }


def get_keyframes(conn: Any, clip_name: str | None, property_name: str | None = None) -> dict[str, Any]:
    resolution = _timeline_resolution(conn)
    current_database = db_session.resolve_current_disk_project_db(conn, allow_project_name_inference=True)
    project_db_path = str(current_database["project_db_path"])
    timeline_name = _timeline_name(conn)

    if property_name:
        spec = normalize_property("ZoomX" if property_name == "RetimeFrame" else property_name)
        target = _resolve_keyframe_target(conn, clip_name, spec)
        item_ref = target.item_ref
        db_type = target.db_type
        spec = target.spec
        connection = sqlite3.connect(project_db_path)
        connection.row_factory = sqlite3.Row
        try:
            cursor = connection.cursor()
            row = db_timeline_rows.find_ti_item_row(cursor, item=item_ref, db_type=db_type, timeline_name=timeline_name)
            if property_name == "RetimeFrame":
                from .clip_speed_db import normalized_time_map_state
                from .retime_curve_readback import curve_coordinates

                state = normalized_time_map_state(
                    row, fps=float(conn.fps), record_start_frame=item_ref.start,
                    fallback_duration_frames=item_ref.duration,
                )
                curve = curve_coordinates(
                    state, record_start=item_ref.start,
                    source_start=state["native_record_origin_seconds"] * state["source_fps"],
                )
                return {"clip": item_ref.name, "property": "RetimeFrame", "count": len(curve["points"]),
                        "keyframes": [], "curve": curve, "route": "keyframe_db",
                        "storage_domain": "persisted_time_map", "readback_domain": "clip_relative_seconds"}
            points = _row_keyframes(row, spec)
        finally:
            connection.close()
        data = _rows_payload(clip=item_ref.name, item_ref=item_ref, spec=spec, points=points, resolution=resolution)
        data["project_db_path"] = project_db_path
        return data

    try:
        target = _resolve_keyframe_target(conn, clip_name, _VIDEO_PROPERTY_SPECS["ZoomX"])
    except ClipNotFound:
        audio_ref = db_timeline_selection.resolve_audio_group(conn, clip_name=clip_name)["audio"]
        target = _KeyframeTarget(
            item_ref=audio_ref,
            db_type="Sm2TiAudioClip",
            spec=_AUDIO_PROPERTY_SPECS["Volume"],
        )
    item_ref = target.item_ref
    db_type = target.db_type
    connection = sqlite3.connect(
        f"{Path(project_db_path).resolve().as_uri()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        row = db_timeline_rows.find_ti_item_row(cursor, item=item_ref, db_type=db_type, timeline_name=timeline_name)
        payload: dict[str, list[dict[str, Any]]] = {}
        if item_ref.track_type == "video":
            _extra, groups = _decode_effect_filters(row.get("EffectFiltersBA"))
            for spec in _VIDEO_PROPERTY_SPECS.values():
                frame_origin = _row_keyframe_origin(row, spec)
                points = _read_points_from_groups(groups, spec, frame_origin=frame_origin)
                if points:
                    payload[spec.public_name] = [
                        point.to_dict(item_start=item_ref.start, spec=spec, resolution=resolution) for point in points
                    ]
        try:
            audio_ref = db_timeline_selection.resolve_audio_group(conn, clip_name=clip_name)["audio"]
            audio_row = db_timeline_rows.find_ti_item_row(
                cursor,
                item=audio_ref,
                db_type="Sm2TiAudioClip",
                timeline_name=timeline_name,
            )
            _audio_extra, audio_groups = _decode_effect_filters(audio_row.get("EffectFiltersBA"))
            for spec in _AUDIO_PROPERTY_SPECS.values():
                audio_frame_origin = _row_keyframe_origin(audio_row, spec)
                points = _read_points_from_groups(
                    audio_groups,
                    spec,
                    frame_origin=audio_frame_origin,
                )
                if points:
                    payload[spec.public_name] = [
                        point.to_dict(item_start=audio_ref.start, spec=spec, resolution=resolution) for point in points
                    ]
        except Exception:
            pass
    finally:
        connection.close()
    return {
        "clip": item_ref.name,
        "properties": sorted(payload),
        "keyframes": payload,
        "route": "keyframe_db",
        "project_db_path": project_db_path,
        "storage_domain": "clip_local_frame",
        "readback_domain": "record_frame",
    }


def list_audio_volume_envelopes(conn: Any, *, limit: int = 50) -> dict[str, Any]:
    """Read verified clip-volume envelope points for audio items on the current timeline."""
    resolution = _timeline_resolution(conn)
    current_database = db_session.resolve_current_disk_project_db(
        conn, allow_project_name_inference=True
    )
    project_db_path = str(current_database["project_db_path"])
    timeline_name = _timeline_name(conn)
    item_refs = sorted(
        db_timeline_selection._read_live_items(conn, track_type="audio"),
        key=lambda item: (item.track_index, item.start, item.item_id or ""),
    )
    envelopes: list[dict[str, Any]] = []
    connection = sqlite3.connect(
        f"{Path(project_db_path).resolve().as_uri()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        for item_ref in item_refs:
            row = db_timeline_rows.find_ti_item_row(
                cursor,
                item=item_ref,
                db_type="Sm2TiAudioClip",
                timeline_name=timeline_name,
            )
            if str(row.get("Sm2TiItem_id") or "") != str(item_ref.item_id or ""):
                raise ValidationError(
                    "Audio keyframe readback did not bind the exact native item identity.",
                    details={
                        "reason": "persisted_item_identity_mismatch",
                        "expected_item_id": item_ref.item_id,
                        "actual_item_id": row.get("Sm2TiItem_id"),
                    },
                )
            points = _row_keyframes(row, _AUDIO_PROPERTY_SPECS["Volume"])
            if not points:
                continue
            envelopes.append(
                {
                    "clip": {
                        "item_id": item_ref.item_id,
                        "name": item_ref.name,
                        "track": int(item_ref.track_index),
                        "record_start_frame": int(item_ref.start),
                        "record_end_frame": int(item_ref.end),
                    },
                    "mode": "volume",
                    "points": [
                        point.to_dict(
                            item_start=item_ref.start,
                            spec=_AUDIO_PROPERTY_SPECS["Volume"],
                            resolution=resolution,
                        )
                        for point in points
                    ],
                }
            )
    finally:
        connection.close()
    total = len(envelopes)
    return {
        "envelopes": envelopes[: int(limit)],
        "count": min(total, int(limit)),
        "total_count": total,
        "truncated": total > int(limit),
        "route": "keyframe_db",
        "storage_domain": "clip_local_frame",
        "readback_domain": "record_frame",
        "project_db_path": project_db_path,
    }


def _verify(
    session: db_session.DiskDbMutationSession,
    mutation_result: dict[str, Any],
    spec: PropertySpec,
    expected: list[InspectorKeyframe],
) -> dict[str, Any]:
    connection = sqlite3.connect(session.project_db_path)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        row = cursor.execute(
            "SELECT * FROM Sm2TiItem WHERE Sm2TiItem_id = ?",
            (mutation_result["item_id"],),
        ).fetchone()
        if not row:
            raise APICallFailed(
                "Timeline item keyframe DB verification could not find the mutated item.",
                details={"item_id": mutation_result["item_id"]},
                recoverability="manual",
            )
        row_dict = db_timeline_rows._row_to_dict(cursor, row)  # type: ignore[attr-defined]
        actual = _row_keyframes(row_dict, spec)
    finally:
        connection.close()
    expected_rows = [
        point.to_dict(
            item_start=int(mutation_result["item_start"]),
            spec=spec,
            resolution=tuple(mutation_result["resolution"]),
        )
        for point in sorted(expected, key=lambda row: row.local_frame)
    ]
    actual_rows = [
        point.to_dict(
            item_start=int(mutation_result["item_start"]),
            spec=spec,
            resolution=tuple(mutation_result["resolution"]),
        )
        for point in actual
    ]
    if actual_rows != expected_rows:
        raise APICallFailed(
            "Timeline item keyframe DB write did not verify after project reload.",
            details={
                "property": spec.public_name,
                "expected": expected_rows,
                "actual": actual_rows,
                "item_id": mutation_result["item_id"],
                "project_db_path": session.project_db_path,
            },
            recoverability="manual",
        )
    return {
        "status": "verified",
        "property": spec.public_name,
        "keyframes": actual_rows,
        "readback_count": len(actual_rows),
        "route": "project_db_readback",
    }


def mutate_keyframes(
    conn: Any,
    clip_name: str | None,
    property_name: str,
    mutator: Callable[[list[InspectorKeyframe], int], list[InspectorKeyframe]],
    *,
    context: str,
    frame: int | None = None,
    target: _KeyframeTarget | None = None,
    validate_exact_live_target: bool = False,
) -> dict[str, Any]:
    requested_spec = normalize_property(property_name)
    target = target or _resolve_keyframe_target(conn, clip_name, requested_spec)
    spec = target.spec
    resolution = _timeline_resolution(conn)
    item_ref = target.item_ref
    db_type = target.db_type
    timeline_name = _timeline_name(conn)
    local_frame = _check_record_frame(item_ref, int(frame)) if frame is not None else -1

    sdk_target = expected_target()

    def validate_sdk_target_at_pre_close(locked_conn: Any, _session: Any) -> None:
        from . import timeline_ops

        timeline_ops.require_sdk_marker_mutation_guard(locked_conn)
        if sdk_target is not None:
            resolve_exact_timeline_item(locked_conn, sdk_target)
            return
        try:
            candidates = locked_conn.timeline.GetItemListInTrack(
                item_ref.track_type, int(item_ref.track_index)
            ) or []
        except Exception as exc:
            raise SdkMutationStaleRevision(
                "Exact timeline-item target track became unavailable before keyframe mutation."
            ) from exc
        matches = []
        for candidate in candidates:
            try:
                candidate_id = str(candidate.GetUniqueId() or "").strip()
                if (
                    candidate_id == item_ref.item_id
                    and int(candidate.GetStart()) == int(item_ref.start)
                    and int(candidate.GetEnd()) == int(item_ref.end)
                    and str(candidate.GetName() or "") == item_ref.name
                ):
                    matches.append(candidate)
            except Exception:
                continue
        if len(matches) != 1:
            raise SdkMutationStaleRevision(
                "Exact audio timeline-item target changed before keyframe mutation.",
                details={"match_count": len(matches), "item_id": item_ref.item_id},
            )

    def writer(_connection: Any, cursor: sqlite3.Cursor, session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        row = db_timeline_rows.find_ti_item_row(cursor, item=item_ref, db_type=db_type, timeline_name=timeline_name)
        extra_entries, groups = _decode_effect_filters(row.get("EffectFiltersBA"))
        _reject_unsafe_video_fade_keyframe_write(
            extra_entries,
            spec=spec,
            item_id=str(row["Sm2TiItem_id"]),
        )
        frame_origin = _row_keyframe_origin(row, spec)
        current = _read_points_from_groups(groups, spec, frame_origin=frame_origin)
        updated = sorted(mutator(current, local_frame), key=lambda point: point.local_frame)
        _write_points_to_groups(groups, spec, updated, frame_origin=frame_origin)
        _sync_zoom_counterpart(
            groups,
            spec,
            current,
            updated,
            frame_origin=frame_origin,
        )
        effect_filters = _encode_effect_filters(extra_entries, groups)
        fields_blob = _ensure_effect_fields_blob(row.get("FieldsBlob"))
        updates: dict[str, Any] = {"EffectFiltersBA": sqlite3.Binary(effect_filters) if effect_filters else None}
        if fields_blob is not row.get("FieldsBlob"):
            updates["FieldsBlob"] = sqlite3.Binary(fields_blob) if fields_blob else None
        db_timeline_rows.update_row(cursor, "Sm2TiItem", "Sm2TiItem_id", row["Sm2TiItem_id"], updates)
        session.steps.append("update_inspector_keyframes_effect_filters")
        return {
            "clip": item_ref.name,
            "item_id": row["Sm2TiItem_id"],
            "item_start": int(item_ref.start),
            "item_end": int(item_ref.end),
            "property": spec.public_name,
            "requested_property": property_name,
            "param_id": int(spec.param_id),
            "group": spec.group_name,
            "resolution": list(resolution),
            "keyframes": [
                point.to_dict(item_start=item_ref.start, spec=spec, resolution=resolution) for point in updated
            ],
            "readback": _rows_payload(
                clip=item_ref.name,
                item_ref=item_ref,
                spec=spec,
                points=updated,
                resolution=resolution,
            ),
        }

    def verifier(_fresh_conn: Any, mutation_result: dict[str, Any], session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        expected = [
            InspectorKeyframe(
                local_frame=int(point["local_frame"]),
                value=float(point["db_value"]),
                interpolation_code=int(point["interpolation_code"]),
                interpolation_flags=int(point["interpolation_flags"]),
            )
            for point in mutation_result["keyframes"]
        ]
        return _verify(session, mutation_result, spec, expected)

    result = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context=context,
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
        **(
            {"pre_close_validator": validate_sdk_target_at_pre_close}
            if sdk_target is not None or validate_exact_live_target
            else {}
        ),
    )
    db_session_route = result.pop("route", None)
    result["route"] = "keyframe_db"
    result["db_session_route"] = db_session_route
    return result


def add_keyframe(
    conn: Any,
    clip_name: str | None,
    property_name: str,
    frame: int,
    value: float,
    interpolation: str | int | None = None,
    *,
    target: _KeyframeTarget | None = None,
    validate_exact_live_target: bool = False,
) -> dict[str, Any]:
    requested_spec = normalize_property(property_name)
    target = target or _resolve_keyframe_target(conn, clip_name, requested_spec)
    spec = target.spec
    resolution = _timeline_resolution(conn)
    interp = normalize_interpolation(interpolation)
    db_value = _to_db_value(_finite_value(value), spec, resolution)

    def mutator(current: list[InspectorKeyframe], local_frame: int) -> list[InspectorKeyframe]:
        point = InspectorKeyframe(
            local_frame=int(local_frame),
            value=db_value,
            interpolation_code=interp,
            interpolation_flags=_INTERPOLATION_TO_FLAGS[interp],
        )
        return [row for row in current if row.local_frame != point.local_frame] + [point]

    result = mutate_keyframes(
        conn,
        clip_name,
        property_name,
        mutator,
        context="clip keyframe add",
        frame=int(frame),
        target=target,
        validate_exact_live_target=validate_exact_live_target,
    )
    result["added"] = {
        "frame": int(frame),
        "value": float(value),
        "db_value": db_value,
        "interpolation": _CODE_TO_INTERPOLATION[interp],
        "interpolation_code": interp,
        "interpolation_flags": _INTERPOLATION_TO_FLAGS[interp],
    }
    return result


def add_audio_volume_keyframe(
    conn: Any,
    *,
    track: int,
    at: str,
    value_db: float,
    interpolation: str | int | None = None,
) -> dict[str, Any]:
    """Write one exact clip-volume envelope point selected by audio track and record time."""
    record_frame = db_timeline_selection.resolve_record_frame(conn, at=at)
    item_ref = db_timeline_selection.resolve_audio_group(conn, track=int(track), at=at)["audio"]
    target = _KeyframeTarget(
        item_ref=item_ref,
        db_type="Sm2TiAudioClip",
        spec=_AUDIO_PROPERTY_SPECS["Volume"],
    )
    result = add_keyframe(
        conn,
        item_ref.name,
        "Volume",
        record_frame,
        value_db,
        interpolation,
        target=target,
        validate_exact_live_target=True,
    )
    result.update(
        {
            "action": "fairlight.automation.write",
            "automation_owner": "audio_clip",
            "lane": "volume",
            "requested_track": int(track),
            "requested_time": at,
            "requested_record_frame": int(record_frame),
            "requested_value_db": float(value_db),
        }
    )
    return result


def delete_keyframe(conn: Any, clip_name: str | None, property_name: str, frame: int) -> dict[str, Any]:
    target_frame = int(frame)

    def mutator(current: list[InspectorKeyframe], local_frame: int) -> list[InspectorKeyframe]:
        updated = [row for row in current if row.local_frame != int(local_frame)]
        if len(updated) == len(current):
            raise ValidationError(
                "No keyframe found at frame.",
                details={"property": property_name, "frame": target_frame, "local_frame": int(local_frame)},
                recoverability="not_applicable",
            )
        return updated

    result = mutate_keyframes(
        conn,
        clip_name,
        property_name,
        mutator,
        context="clip keyframe delete",
        frame=target_frame,
    )
    result["deleted"] = {"frame": target_frame}
    return result


def set_keyframe_interpolation(
    conn: Any,
    clip_name: str | None,
    property_name: str,
    frame: int,
    interpolation_type: str,
) -> dict[str, Any]:
    target_frame = int(frame)
    interp = normalize_interpolation(interpolation_type)

    def mutator(current: list[InspectorKeyframe], local_frame: int) -> list[InspectorKeyframe]:
        updated: list[InspectorKeyframe] = []
        found = False
        for row in current:
            if row.local_frame == int(local_frame):
                updated.append(
                    InspectorKeyframe(
                        local_frame=row.local_frame,
                        value=row.value,
                        interpolation_code=interp,
                        interpolation_flags=_INTERPOLATION_TO_FLAGS[interp],
                    )
                )
                found = True
            else:
                updated.append(row)
        if not found:
            raise ValidationError(
                "No keyframe found at frame.",
                details={"property": property_name, "frame": target_frame, "local_frame": int(local_frame)},
                recoverability="not_applicable",
            )
        return updated

    result = mutate_keyframes(
        conn,
        clip_name,
        property_name,
        mutator,
        context="clip keyframe set-interpolation",
        frame=target_frame,
    )
    result["updated"] = {
        "frame": target_frame,
        "interpolation": _CODE_TO_INTERPOLATION[interp],
        "interpolation_code": interp,
        "interpolation_flags": _INTERPOLATION_TO_FLAGS[interp],
    }
    return result
