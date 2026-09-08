"""Private readiness ledger for the Fusion, DCTL, and LUT contribution.

Packet 0 owns the shared carrier and registry. This module exposes the domain
contribution without importing that owner or inventing a second execution path.
"""

from __future__ import annotations

from dataclasses import dataclass

from .private_sdk_actions.fusion_prepared_action import (
    DELEGATED_ACTIONS,
    UNAVAILABLE_ACTIONS,
    fusion_prepared_action_descriptors,
)


class FusionPacketUnavailable(ValueError):
    """Raised before policy or authorization for a non-callable descriptor."""


_STAGES = (
    "validate_input", "prepare", "resolve_current", "execute", "verify",
    "recover", "project_result", "validate_public_result",
)


@dataclass(frozen=True)
class PrivateActionDescriptor:
    action_id: str
    operation_class: str
    availability: str
    unavailable_reason: str | None = None
    long_running: bool = False
    runtime_descriptor: object | None = None

    @property
    def complete(self) -> bool:
        return self.runtime_descriptor is not None and all(
            callable(getattr(self.runtime_descriptor, stage, None)) for stage in _STAGES
        )


_EXECUTABLE = fusion_prepared_action_descriptors()
PRIVATE_FUSION_PACKET: dict[str, PrivateActionDescriptor] = {}
for action_id, runtime_descriptor in _EXECUTABLE.items():
    command_id = action_id.removeprefix("cutagent.action.")
    operation_class = runtime_descriptor.public_operation_class
    PRIVATE_FUSION_PACKET[command_id] = PrivateActionDescriptor(
        action_id=action_id,
        operation_class=operation_class,
        availability="callable",
        long_running=operation_class == "long_running",
        runtime_descriptor=runtime_descriptor,
    )
for action_id, reason in DELEGATED_ACTIONS.items():
    PRIVATE_FUSION_PACKET[action_id.removeprefix("cutagent.action.")] = PrivateActionDescriptor(
        action_id=action_id,
        operation_class="mutation",
        availability="delegated",
        unavailable_reason=reason,
    )
for action_id, reason in UNAVAILABLE_ACTIONS.items():
    operation_class = "long_running" if action_id == "cutagent.action.fusion.comp.render" else "mutation"
    PRIVATE_FUSION_PACKET[action_id.removeprefix("cutagent.action.")] = PrivateActionDescriptor(
        action_id=action_id,
        operation_class=operation_class,
        availability="unavailable",
        long_running=operation_class == "long_running",
        unavailable_reason=reason,
    )


def private_fusion_packet_descriptor(action_id: str) -> PrivateActionDescriptor | None:
    return PRIVATE_FUSION_PACKET.get(action_id.removeprefix("cutagent.action."))


def private_fusion_executable_descriptors() -> dict[str, object]:
    return {
        descriptor.action_id: descriptor.runtime_descriptor
        for descriptor in PRIVATE_FUSION_PACKET.values()
        if descriptor.availability == "callable" and descriptor.complete
    }


def prepare_private_fusion_action(action_id: str, *_args: object, **_kwargs: object) -> object:
    descriptor = private_fusion_packet_descriptor(action_id)
    if descriptor is None:
        raise FusionPacketUnavailable("unknown_fusion_packet_action")
    if not descriptor.complete:
        raise FusionPacketUnavailable(descriptor.unavailable_reason or "incomplete_descriptor")
    return descriptor.runtime_descriptor
