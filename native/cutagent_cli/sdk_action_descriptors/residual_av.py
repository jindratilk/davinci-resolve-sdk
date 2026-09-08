"""Private Clip/Text/Audio prepared-action descriptor packet.

The signed runtime consumes these descriptors during prepare.  They contain
no public SDK transport shape and are not copied into npm, Bridge resources or
agent references.  An action is still unadvertised until the shared signed
prepared-action kernel proves that every named stage is installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


_ACTION_IDS = tuple(
    line
    for line in """
cutagent.action.audio.beat_detect
cutagent.action.audio.duck
cutagent.action.audio.info
cutagent.action.audio.probe_subframe
cutagent.action.audio.reverb
cutagent.action.audio.waveform_offset
cutagent.action.burnin.load
cutagent.action.burnin.preset.export
cutagent.action.burnin.preset.import
cutagent.action.clip.audio_eq
cutagent.action.clip.audio_gain
cutagent.action.clip.audio_normalize
cutagent.action.clip.audio_pan
cutagent.action.clip.audio_pitch
cutagent.action.clip.burnin.load
cutagent.action.clip.cache
cutagent.action.clip.cache_set
cutagent.action.clip.color
cutagent.action.clip.composite
cutagent.action.clip.disable
cutagent.action.clip.dynamic_zoom
cutagent.action.clip.enable
cutagent.action.clip.fade_in
cutagent.action.clip.flag
cutagent.action.clip.fusion.add
cutagent.action.clip.fusion.delete
cutagent.action.clip.fusion.export
cutagent.action.clip.fusion.import
cutagent.action.clip.fusion.list
cutagent.action.clip.fusion.load
cutagent.action.clip.fusion.tool_set
cutagent.action.clip.link
cutagent.action.clip.linked.list
cutagent.action.clip.magic_mask
cutagent.action.clip.marker.add
cutagent.action.clip.marker.custom_data
cutagent.action.clip.marker.delete
cutagent.action.clip.marker.delete_custom
cutagent.action.clip.offset
cutagent.action.clip.properties
cutagent.action.clip.rename
cutagent.action.clip.reset_node_colors
cutagent.action.clip.smart_reframe
cutagent.action.clip.source_range
cutagent.action.clip.stabilize
cutagent.action.clip.take.add
cutagent.action.clip.take.delete
cutagent.action.clip.take.finalize
cutagent.action.clip.take.list
cutagent.action.clip.take.select
cutagent.action.clip.track_info
cutagent.action.clip.unlink
cutagent.action.clip.update_sidecar
cutagent.action.clip.voice_isolation
cutagent.action.edit.auto_subtitle
cutagent.action.edit.camera_pip
cutagent.action.edit.delete_through_edit
cutagent.action.edit.from_edl
cutagent.action.edit.remove
cutagent.action.edit.remove_range
cutagent.action.edit.ripple_delete
cutagent.action.edit.ripple_delete_selected
cutagent.action.edit.scene_detect
cutagent.action.edit.slide_selected
cutagent.action.edit.slip_selected
cutagent.action.edit.social_crop
cutagent.action.edit.split
cutagent.action.edit.transition.add
cutagent.action.text.insert
cutagent.action.text.insert_preset
cutagent.action.text.insert_template
cutagent.action.text.insert_template_batch
cutagent.action.text.update
""".strip().splitlines()
)
_EDIT_ACTIONS = frozenset(
    action_id
    for action_id in _ACTION_IDS
    if action_id.startswith("cutagent.action.edit.")
)

_SUPPORTING_READS = frozenset(
    {
        "cutagent.action.audio.info",
        "cutagent.action.clip.fusion.list",
        "cutagent.action.clip.linked.list",
        "cutagent.action.clip.offset",
        "cutagent.action.clip.source_range",
        "cutagent.action.clip.take.list",
        "cutagent.action.clip.track_info",
    }
)
_LONG_RUNNING = frozenset(
    {
        "cutagent.action.audio.beat_detect",
        "cutagent.action.clip.smart_reframe",
        "cutagent.action.clip.stabilize",
    }
)
_FILE_INPUT = frozenset(
    {
        "cutagent.action.audio.beat_detect",
        "cutagent.action.audio.info",
        "cutagent.action.audio.reverb",
        "cutagent.action.audio.waveform_offset",
        "cutagent.action.audio.duck",
        "cutagent.action.burnin.preset.import",
        "cutagent.action.clip.fusion.import",
        "cutagent.action.edit.from_edl",
        "cutagent.action.text.insert_template",
        "cutagent.action.text.insert_template_batch",
    }
)
_FILE_OUTPUT = frozenset(
    {
        "cutagent.action.audio.duck",
        "cutagent.action.audio.reverb",
        "cutagent.action.burnin.preset.export",
        "cutagent.action.clip.fusion.export",
    }
)
_FILE_ONLY = frozenset(
    {
        "cutagent.action.audio.beat_detect",
        "cutagent.action.audio.info",
        "cutagent.action.audio.reverb",
        "cutagent.action.audio.waveform_offset",
    }
)
_EXACT_PROJECT = frozenset(
    {
        "cutagent.action.burnin.preset.export",
        "cutagent.action.burnin.preset.import",
    }
)
_EXACT_TIMELINE = frozenset(
    {
        "cutagent.action.burnin.load",
        "cutagent.action.text.insert",
        "cutagent.action.text.insert_preset",
        "cutagent.action.text.insert_template",
        "cutagent.action.text.insert_template_batch",
    }
)
_MULTI_ITEM = frozenset({"cutagent.action.clip.link", "cutagent.action.clip.unlink"})
_MEDIA_POOL_INPUT = frozenset({"cutagent.action.clip.take.add"})
_KERNEL_READS = _SUPPORTING_READS
# Retain rendered proof only where the current native readback cannot establish
# the complete visual result. Transition insertion is intentionally absent: its
# production verifier binds every inserted native item to the requested seam,
# duration, track, scope, and independently observed item identity.
_RENDERED = frozenset(
    action_id
    for action_id in _ACTION_IDS
    if action_id in {
        "cutagent.action.clip.composite",
        "cutagent.action.clip.dynamic_zoom",
        "cutagent.action.clip.magic_mask",
        "cutagent.action.clip.smart_reframe",
        "cutagent.action.clip.stabilize",
        "cutagent.action.edit.camera_pip",
        "cutagent.action.edit.social_crop",
    }
)
_ARTIFACT = frozenset(
    {
        "cutagent.action.audio.duck",
        "cutagent.action.audio.info",
        "cutagent.action.audio.reverb",
        "cutagent.action.burnin.preset.export",
        "cutagent.action.burnin.preset.import",
        "cutagent.action.clip.fusion.export",
        "cutagent.action.clip.fusion.import",
        "cutagent.action.clip.update_sidecar",
        "cutagent.action.text.insert_template",
        "cutagent.action.text.insert_template_batch",
        "cutagent.action.audio.waveform_offset",
        "cutagent.action.edit.from_edl",
    }
)

_DEDICATED_OTHER_OWNERS = frozenset(
    {
        "cutagent.action.clip.keyframe.add",
        "cutagent.action.clip.keyframe.delete",
        "cutagent.action.clip.keyframe.get",
        "cutagent.action.clip.keyframe.set_interpolation",
        "cutagent.action.clip.transform",
        "cutagent.action.clip.freeze",
        "cutagent.action.clip.reverse",
        "cutagent.action.clip.speed",
        "cutagent.action.clip.speed_ramp",
    }
)
_PREPARED_UNAVAILABLE = frozenset(
    {
        "cutagent.action.clip.magic_mask",
    }
)


@dataclass(frozen=True)
class ResidualAvActionDescriptor:
    action_id: str
    command_id: str
    operation_class: str
    authority: str
    linked_av_impact: str
    inspector_preservation: str
    verification: tuple[str, ...]
    recovery: str
    stages: tuple[str, ...]
    artifact_roles: tuple[str, ...]
    topology_policy: str
    preparation_state: str


def _authority(action_id: str) -> str:
    if action_id in _FILE_ONLY:
        return "managed_artifact_revision"
    if action_id == "cutagent.action.audio.duck":
        return "managed_artifact_and_optional_exact_media_revision"
    if action_id in _EXACT_PROJECT:
        return "exact_project_revision"
    if action_id in _MEDIA_POOL_INPUT:
        return "exact_timeline_item_and_media_pool_revision"
    if (
        action_id in _EXACT_TIMELINE
        or action_id == "cutagent.action.audio.probe_subframe"
    ):
        return "exact_project_timeline_revision"
    if action_id in _EDIT_ACTIONS:
        return "exact_project_timeline_revision"
    if action_id in _MULTI_ITEM:
        return "exact_timeline_item_set_revision"
    return "exact_timeline_item_revision"


def _verification(action_id: str) -> tuple[str, ...]:
    result = ["structural_readback"]
    if action_id in _ARTIFACT:
        result.append("artifact_readback")
    if action_id in _RENDERED:
        result.append("rendered_frame")
    return tuple(result)


def _descriptor(action_id: str) -> ResidualAvActionDescriptor:
    operation_class = "read" if action_id in _KERNEL_READS else "mutation"
    artifact_roles = []
    if action_id == "cutagent.action.audio.waveform_offset":
        artifact_roles.extend(("managed_input_reference", "managed_input_target"))
    elif action_id in _FILE_INPUT:
        artifact_roles.append("managed_input")
    if action_id in _FILE_OUTPUT:
        artifact_roles.append("reserved_output")
    if action_id == "cutagent.action.clip.update_sidecar":
        artifact_roles.append("derived_sidecar_output")
    return ResidualAvActionDescriptor(
        action_id=action_id,
        command_id=action_id.removeprefix("cutagent.action."),
        operation_class=operation_class,
        authority=_authority(action_id),
        linked_av_impact=(
            "resolve_and_preserve_complete_topology"
            if action_id.startswith(("cutagent.action.clip.", "cutagent.action.edit."))
            or action_id == "cutagent.action.audio.duck"
            else "not_applicable"
        ),
        inspector_preservation=(
            "preserve_unrelated_inspector_state"
            if action_id.startswith(("cutagent.action.clip.", "cutagent.action.text."))
            else "not_applicable"
        ),
        verification=_verification(action_id),
        recovery=(
            "reattach_cancel_or_inspect"
            if action_id in _LONG_RUNNING
            else "retry_read"
            if operation_class == "read"
            else "reconcile_artifact_and_native_state_before_retry"
            if artifact_roles
            else "inspect_exact_state_before_retry"
        ),
        stages=(
            "validate_public_contract",
            "resolve_exact_private_context",
            "capture_pre_state",
            "lower_privately",
            "project_complete_impact",
            "verify_independently",
            "recover_truthfully",
        ),
        artifact_roles=tuple(artifact_roles),
        topology_policy=(
            "not_applicable"
            if action_id == "cutagent.action.edit.ripple_delete"
            else "mutate_declared_edges_preserve_unrelated_topology"
            if action_id in _MULTI_ITEM or action_id in _EDIT_ACTIONS
            else "preserve_complete_linked_av_topology"
            if action_id.startswith("cutagent.action.clip.")
            or action_id == "cutagent.action.audio.duck"
            else "not_applicable"
        ),
        preparation_state=(
            "unavailable"
            if action_id in _PREPARED_UNAVAILABLE
            else "carrier_callable_bridge_activation_pending"
        ),
    )


RESIDUAL_AV_ACTION_DESCRIPTORS = tuple(_descriptor(item) for item in _ACTION_IDS)


def _required_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 512:
        raise ValueError(f"{name} must be a bounded non-empty identity")
    return value


def _validate_artifact_bindings(
    descriptor: ResidualAvActionDescriptor, identities: Mapping[str, Any]
) -> None:
    if not descriptor.artifact_roles:
        return
    artifacts = identities.get("artifacts")
    if not isinstance(artifacts, Sequence) or isinstance(artifacts, (str, bytes)):
        raise ValueError(
            "artifact actions require explicit managed artifact identities"
        )
    by_role: dict[str, Mapping[str, Any]] = {}
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            raise ValueError("managed artifact identity must be an object")
        role = _required_string(artifact.get("role"), "artifact role")
        if role in by_role:
            raise ValueError("managed artifact roles must be unique")
        by_role[role] = artifact
    if set(by_role) != set(descriptor.artifact_roles):
        raise ValueError("managed artifact roles do not match the action contract")
    for role, artifact in by_role.items():
        _required_string(artifact.get("artifactId"), "artifactId")
        if role.startswith("managed_input"):
            digest = _required_string(artifact.get("digest"), "artifact digest")
            if not digest.startswith("sha256:"):
                raise ValueError("managed artifact digest must use SHA-256")
        elif role == "reserved_output":
            _required_string(artifact.get("reservationId"), "reservationId")
            _required_string(artifact.get("allowedRootId"), "allowedRootId")
            path_digest = _required_string(artifact.get("pathDigest"), "pathDigest")
            if not path_digest.startswith("sha256:"):
                raise ValueError("reserved output path digest must use SHA-256")
        elif role == "derived_sidecar_output":
            _required_string(artifact.get("sourceArtifactId"), "sourceArtifactId")
            _required_string(artifact.get("sourceRevision"), "sourceRevision")
            _required_string(artifact.get("allowedRootId"), "allowedRootId")


def _validate_public_binding(
    descriptor: ResidualAvActionDescriptor,
    identities: Mapping[str, Any],
    revisions: Mapping[str, Any],
    input_payload: Mapping[str, Any],
) -> None:
    _validate_artifact_bindings(descriptor, identities)
    authority = descriptor.authority
    if authority == "managed_artifact_revision":
        return
    _required_string(identities.get("projectId"), "projectId")
    if authority == "exact_project_revision":
        _required_string(revisions.get("projectRevision"), "projectRevision")
        return
    if authority == "managed_artifact_and_optional_exact_media_revision":
        if input_payload.get("replaceMediaName") or input_payload.get("replaceMedia"):
            _required_string(identities.get("mediaPoolItemId"), "mediaPoolItemId")
            _required_string(revisions.get("projectRevision"), "projectRevision")
        return
    _required_string(identities.get("timelineId"), "timelineId")
    _required_string(revisions.get("timelineRevision"), "timelineRevision")
    if authority == "exact_project_timeline_revision":
        return
    targets = identities.get("targets")
    minimum = 2 if authority == "exact_timeline_item_set_revision" else 1
    if (
        not isinstance(targets, Sequence)
        or isinstance(targets, (str, bytes))
        or len(targets) < minimum
    ):
        raise ValueError("timeline-item actions require an exact bounded target set")
    for target in targets:
        if not isinstance(target, Mapping):
            raise ValueError("timeline-item target must be an object")
        _required_string(target.get("timelineItemId"), "timelineItemId")
        _required_string(target.get("snapshotTimelineItemId"), "snapshotTimelineItemId")
        if target.get("trackType") not in {"video", "audio"}:
            raise ValueError("timeline-item target requires an exact track type")
        if not isinstance(target.get("trackIndex"), int) or target["trackIndex"] < 1:
            raise ValueError("timeline-item target requires a positive track index")
        linked = target.get("linkedTimelineItemIds")
        if not isinstance(linked, Sequence) or isinstance(linked, (str, bytes)):
            raise ValueError("timeline-item target requires captured linked topology")
        for linked_id in linked:
            _required_string(linked_id, "linkedTimelineItemId")
    if authority == "exact_timeline_item_and_media_pool_revision":
        _required_string(identities.get("mediaPoolItemId"), "mediaPoolItemId")
        _required_string(revisions.get("projectRevision"), "projectRevision")


class ResidualAvActionUnadvertisedError(RuntimeError):
    """Raised when a requirements-only residual action is asked to prepare."""


def assert_residual_av_prepare_candidate(
    action_id: str,
    *,
    identities: Mapping[str, Any],
    revisions: Mapping[str, Any],
    input_payload: Mapping[str, Any],
    private_resolution: Mapping[str, Any],
) -> None:
    """Validate a candidate, then fail closed because no preparer is installed.

    This packet records private requirements; it does not mint kernel claims.
    Only the authoritative signed prepared-action kernel may apply RFC 8785,
    domain-separated digests and create the complete opaque receipt claim set.
    """

    descriptor = next(
        (
            item
            for item in RESIDUAL_AV_ACTION_DESCRIPTORS
            if item.action_id == action_id
        ),
        None,
    )
    if descriptor is None:
        raise KeyError("action is outside residual Clip/Text/Audio ownership")
    _validate_public_binding(descriptor, identities, revisions, input_payload)
    required_private = {
        "nativeTargets",
        "lowering",
        "preState",
        "impact",
        "verificationPlan",
        "recoveryPlan",
    }
    if set(private_resolution) != required_private:
        raise ValueError(
            "private prepared-action resolution is incomplete or contains unreviewed fields"
        )
    if not private_resolution["nativeTargets"]:
        raise ValueError(
            "private prepared-action resolution omitted exact native targets"
        )
    for stage_name, stage_value in private_resolution.items():
        if not isinstance(stage_value, Mapping) or not stage_value:
            raise ValueError(
                f"private prepared-action stage {stage_name} must be a non-empty object"
            )
    raise ResidualAvActionUnadvertisedError(
        f"{descriptor.action_id} remains unadvertised until its action-specific signed-runtime preparer is installed"
    )


def validate_residual_av_descriptor_packet() -> None:
    if len(RESIDUAL_AV_ACTION_DESCRIPTORS) != 73:
        raise ValueError(
            "residual Clip/Text/Audio/Edit packet must close exactly 73 actions"
        )
    action_ids = {item.action_id for item in RESIDUAL_AV_ACTION_DESCRIPTORS}
    if len(action_ids) != 73 or action_ids & _DEDICATED_OTHER_OWNERS:
        raise ValueError(
            "residual descriptor ownership overlaps or contains duplicates"
        )
    for descriptor in RESIDUAL_AV_ACTION_DESCRIPTORS:
        if descriptor.operation_class not in {"read", "mutation"}:
            raise ValueError(
                f"unsupported prepared-action class: {descriptor.action_id}"
            )
        if "revision" not in descriptor.authority:
            raise ValueError(
                f"stateful action lacks revision-bound authority: {descriptor.action_id}"
            )
        if (
            not descriptor.verification
            or len(descriptor.stages) != 7
            or descriptor.preparation_state
            != (
                "unavailable"
                if descriptor.action_id in _PREPARED_UNAVAILABLE
                else "carrier_callable_bridge_activation_pending"
            )
        ):
            raise ValueError(f"incomplete descriptor stages: {descriptor.action_id}")


validate_residual_av_descriptor_packet()
