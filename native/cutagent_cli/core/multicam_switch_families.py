"""Switch-family registry for live-verified native multicam selector patching."""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Any

from ..errors import ValidationError
from ..multicam_support import support_tier_for_angle_count, switch_is_live_verified

_TIMELINE_ITEM_ANGLE_2_SELECTOR_FIELDS_BLOB = bytes.fromhex(
    "0000000200000025800A100A03A801001A07416E676C652032200112100000000000000005FFFFFFFFFFFFFFFF"
)


@dataclass(frozen=True)
class SwitchFamily:
    angle_count: int
    family_id: str
    live_verified: bool


_SWITCH_FAMILY_REGISTRY = {
    2: SwitchFamily(angle_count=2, family_id="resolve20x_2cam", live_verified=True),
    3: SwitchFamily(angle_count=3, family_id="resolve20x_3cam", live_verified=True),
    4: SwitchFamily(angle_count=4, family_id="resolve20x_4cam", live_verified=True),
    5: SwitchFamily(angle_count=5, family_id="resolve20x_5cam", live_verified=True),
    6: SwitchFamily(angle_count=6, family_id="resolve20x_6cam", live_verified=True),
}


def resolve_switch_family(angle_count: int | None) -> SwitchFamily | None:
    normalized = max(0, int(angle_count or 0))
    return _SWITCH_FAMILY_REGISTRY.get(normalized)


def ensure_switch_family_supported(angle_count: int | None) -> SwitchFamily:
    normalized = max(0, int(angle_count or 0))
    family = resolve_switch_family(normalized)
    if family and family.live_verified and switch_is_live_verified(normalized):
        return family
    support = support_tier_for_angle_count(normalized)
    if not bool(support.get("switch_contract_supported")):
        raise ValidationError(
            "Native multicam switch execution is unsupported for this angle count.",
            details={
                "step": "unsupported_angle_count",
                "angle_count": normalized,
                "support_tier": support,
                "live_verified_angle_counts": sorted(_SWITCH_FAMILY_REGISTRY.keys()),
            },
        )

    raise ValidationError(
        "Native multicam switch execution is not yet live-verified for this angle count.",
        details={
            "step": "angle_count_not_live_verified",
            "angle_count": normalized,
            "support_tier": support,
            "live_verified_angle_counts": sorted(_SWITCH_FAMILY_REGISTRY.keys()),
        },
    )


def resolve_template_angle_index(*, angle_count: int, segment_angle: str, local_angle_index: int) -> int:
    resolved = max(0, int(local_angle_index))
    if int(angle_count) == 3:
        return {1: 0, 0: 2, 2: 1}.get(resolved, resolved)
    if int(angle_count) >= 4:
        return resolved

    angle_label = str(segment_angle or "").strip().upper()
    if angle_label == "A":
        return 0
    if angle_label == "B":
        return 1
    return 0 if int(local_angle_index) <= 0 else 1


def build_compact_angle_selector_fields_blob(local_angle_index: int) -> bytes:
    if int(local_angle_index) == 1:
        return _TIMELINE_ITEM_ANGLE_2_SELECTOR_FIELDS_BLOB

    display_index = int(local_angle_index) + 1
    label = f"Angle {display_index}".encode("utf-8")
    payload = (
        b"\x80\x0A\x10\x0A\x03\xA8\x01\x00\x1A"
        + bytes([len(label)])
        + label
        + b"\x20\x01\x12\x10\x00\x00\x00\x00\x00\x00\x00\x05\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF"
    )
    return struct.pack(">I", display_index) + struct.pack(">I", len(payload)) + payload


def patch_multi_angle_selector_fields_blob(
    template_blob: bytes,
    *,
    position: str,
    template_angle_index: int,
    track_type: str,
) -> bytes:
    payload = bytearray(template_blob or b"")
    if len(payload) < 16:
        return bytes(payload)
    if track_type == "video":
        payload[14] = 0x83 if position == "first" else 0x86
        payload[15] = (((int(template_angle_index) + 1) & 0x0F) << 4) | 0x05
    return bytes(payload)


def patch_three_angle_selector_fields_blob(
    template_blob: bytes,
    *,
    position: str,
    template_angle_index: int,
    track_type: str,
) -> bytes:
    return patch_multi_angle_selector_fields_blob(
        template_blob,
        position=position,
        template_angle_index=template_angle_index,
        track_type=track_type,
    )


def build_switch_fields_blob(
    *,
    template: Any,
    segment_angle: str,
    local_angle_index: int,
    template_angle_index: int,
    angle_count: int,
    track_type: str,
) -> bytes:
    family = ensure_switch_family_supported(angle_count)
    if family.angle_count == 4:
        return bytes(template.fields_blob)
    if family.angle_count >= 3:
        return patch_multi_angle_selector_fields_blob(
            template.fields_blob,
            position=str(template.position),
            template_angle_index=template_angle_index,
            track_type=track_type,
        )

    angle_label = str(segment_angle or "").strip().upper()
    if angle_label == "A":
        return template.fields_blob
    if angle_label == "B":
        return _TIMELINE_ITEM_ANGLE_2_SELECTOR_FIELDS_BLOB
    if int(local_angle_index) > 0:
        return build_compact_angle_selector_fields_blob(local_angle_index)
    return template.fields_blob
