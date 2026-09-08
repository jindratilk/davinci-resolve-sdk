"""Packaged private Fusion activation truth used by the SDK carrier."""

from __future__ import annotations

from .._sdk_fusion_descriptor_packet import PRIVATE_FUSION_PACKET


FUSION_PACKET_UNSUPPORTED = {
    descriptor.action_id: descriptor.unavailable_reason
    for descriptor in PRIVATE_FUSION_PACKET.values()
    if descriptor.availability == "unavailable"
}
FUSION_PACKET_DELEGATED = {
    descriptor.action_id: descriptor.unavailable_reason
    for descriptor in PRIVATE_FUSION_PACKET.values()
    if descriptor.availability == "delegated"
}
FUSION_PACKET_CALLABLE_IDS = frozenset(
    descriptor.action_id
    for descriptor in PRIVATE_FUSION_PACKET.values()
    if descriptor.availability == "callable" and descriptor.complete
)
