"""Wheel-safe production contribution truth for signed prepared actions."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType
try:
    from typing import TypeAlias
except ImportError:  # Python 3.9 runtime supported by the packaged CLI.
    from typing_extensions import TypeAlias

from .sdk_prepared_action import PreparedActionDescriptor
from .prepared_action_marker import marker_contribution, marker_execution_authorities
from .private_sdk_descriptors import professional_primitive_prepared_action_descriptors
from .private_sdk_descriptors.professional_primitive_production import (
    professional_primitive_production_owners,
)
from .sdk_action_descriptors import residual_av_prepared_action_contributions
from .sdk_action_descriptors.residual_av_prepared_action import (
    CARRIER_CALLABLE_RESIDUAL_AV_ACTIONS,
)
from .sdk_action_descriptors.residual_av_production import ResidualAvProductionAuthority
from .private_sdk_descriptors.timeline_version_prepared_action import (
    timeline_version_prepared_action_production_contribution,
)
from .private_sdk_descriptors.timeline_artifact_prepared_action import (
    TIMELINE_ARTIFACT_ACTION_IDS,
    timeline_artifact_prepared_action_production_contribution,
)
from .private_sdk_descriptors.project_render_storage_media_prepared_action import (
    project_render_storage_media_prepared_action_descriptors,
)
from .private_sdk_descriptors.project_media_extended_prepared_action import (
    PROJECT_RUNTIME_ACTION_IDS,
)
from .private_sdk_descriptors.timeline_topology_production import (
    timeline_topology_prepared_action_packet,
)
from .private_sdk_descriptors.media_residual_prepared_action import (
    MEDIA_RESIDUAL_CALLABLE_ACTION_IDS,
    MediaExecutionAuthority,
    residual_media_execution_authorities,
)


@dataclass(frozen=True)
class PreparedActionContributionPacket:
    """One domain's descriptors and admitted in-process execution authorities."""

    owner: str
    descriptors: Mapping[str, PreparedActionDescriptor]
    execution_authorities: Mapping[str, object]


PreparedActionContributionFactory: TypeAlias = Callable[[], PreparedActionContributionPacket]


def _marker_packet() -> PreparedActionContributionPacket:
    return PreparedActionContributionPacket(
        owner="timeline-marker",
        descriptors=marker_contribution(),
        execution_authorities=marker_execution_authorities(),
    )


def _professional_primitive_packet() -> PreparedActionContributionPacket:
    owners = professional_primitive_production_owners()
    return PreparedActionContributionPacket(
        owner="professional-primitives",
        descriptors=professional_primitive_prepared_action_descriptors(owners=owners),
        execution_authorities=owners,
    )


def _residual_av_packets() -> tuple[PreparedActionContributionPacket, ...]:
    authority = ResidualAvProductionAuthority()
    packets = []
    for owner, descriptors in residual_av_prepared_action_contributions(authority=authority):
        packets.append(
            PreparedActionContributionPacket(
                owner=owner,
                descriptors=descriptors,
                execution_authorities=MappingProxyType(
                    {
                        action_id: authority
                        for action_id in descriptors
                        if action_id in CARRIER_CALLABLE_RESIDUAL_AV_ACTIONS
                    }
                ),
            )
        )
    return tuple(packets)


def _residual_av_callable_packet() -> PreparedActionContributionPacket:
    return _residual_av_packets()[0]


def _residual_av_unavailable_packet() -> PreparedActionContributionPacket:
    return _residual_av_packets()[1]


def _fairlight_packet() -> PreparedActionContributionPacket:
    descriptors, authorities = _new_fairlight_bundle(FAIRLIGHT_PRODUCTION_ACTION_IDS)
    return PreparedActionContributionPacket(
        owner="fairlight",
        descriptors=MappingProxyType(
            {
                **descriptors,
            }
        ),
        execution_authorities=authorities,
    )


def _visual_packet(index: int) -> PreparedActionContributionPacket:
    from .private_sdk_actions.visual_prepared_action_production import (
        visual_prepared_action_contributions,
    )

    contributions = visual_prepared_action_contributions()
    owner, descriptors = contributions[index]
    return PreparedActionContributionPacket(
        owner=owner,
        descriptors=descriptors,
        execution_authorities=MappingProxyType({}),
    )


def _visual_fusion_packet() -> PreparedActionContributionPacket:
    return _visual_packet(0)


def _visual_color_packet() -> PreparedActionContributionPacket:
    return _visual_packet(1)


_EDITORIAL_TIMELINE_READ_ACTION_IDS = (
    "cutagent.action.timeline.clip_markers.list",
    "cutagent.action.timeline.current_item",
    "cutagent.action.timeline.duration",
    "cutagent.action.timeline.info",
    "cutagent.action.timeline.item_at",
    "cutagent.action.timeline.list",
    "cutagent.action.timeline.mark.get",
    "cutagent.action.timeline.marker.list",
    "cutagent.action.timeline.media_pool_item",
    "cutagent.action.timeline.node_graph.inspect",
    "cutagent.action.timeline.playhead.get",
    "cutagent.action.timeline.settings",
    "cutagent.action.timeline.summarize",
    "cutagent.action.timeline.track.items",
    "cutagent.action.timeline.track.list",
    "cutagent.action.timeline.track.subtype",
    "cutagent.action.timeline.voice_isolation.get",
)
_EDITORIAL_TIMELINE_ORDINARY_ACTION_IDS = (
    "cutagent.action.timeline.create",
    "cutagent.action.timeline.delete",
    "cutagent.action.timeline.duplicate",
    "cutagent.action.timeline.fairlight_preset.apply",
    "cutagent.action.timeline.import",
    "cutagent.action.timeline.mark.clear",
    "cutagent.action.timeline.mark.set",
    "cutagent.action.timeline.playhead.set",
    "cutagent.action.timeline.rename",
    "cutagent.action.timeline.set_start_tc",
    "cutagent.action.timeline.settings_set",
    "cutagent.action.timeline.start_tc",
    "cutagent.action.timeline.switch",
    "cutagent.action.timeline.dolby.analyze",
)
EDITORIAL_PROJECT_PRODUCTION_CALLABLE_ACTION_IDS = (
    *_EDITORIAL_TIMELINE_READ_ACTION_IDS,
    *_EDITORIAL_TIMELINE_ORDINARY_ACTION_IDS,
    "cutagent.action.project.rename",
    "cutagent.action.project.settings_set",
    *PROJECT_RUNTIME_ACTION_IDS,
    "cutagent.action.media.folders.create",
    "cutagent.action.media.folders.delete",
    "cutagent.action.media.metadata",
    "cutagent.action.media.property_set",
    "cutagent.action.media.third_party_metadata.set",
)

OPERATIONS_RENDER_PRODUCTION_CALLABLE_ACTION_IDS = (
    "cutagent.action.render.alpha",
    "cutagent.action.render.encoding",
    "cutagent.action.render.mode.set",
    "cutagent.action.render.subtitles",
)

VERSION_PRODUCTION_CALLABLE_ACTION_IDS = (
    "cutagent.action.version.create",
    "cutagent.action.version.prune",
    "cutagent.action.version.restore",
)


def _editorial_project_packet() -> PreparedActionContributionPacket:
    timeline = timeline_version_prepared_action_production_contribution()
    project = project_render_storage_media_prepared_action_descriptors()
    descriptors = MappingProxyType(
        {
            **{
                action_id: timeline[action_id]
                for action_id in (
                    *_EDITORIAL_TIMELINE_READ_ACTION_IDS,
                    *_EDITORIAL_TIMELINE_ORDINARY_ACTION_IDS,
                )
            },
            **{
                action_id: project[action_id]
                for action_id in EDITORIAL_PROJECT_PRODUCTION_CALLABLE_ACTION_IDS
                if action_id.startswith(("cutagent.action.project.", "cutagent.action.media."))
            },
        }
    )
    if set(descriptors) != set(EDITORIAL_PROJECT_PRODUCTION_CALLABLE_ACTION_IDS):
        raise RuntimeError("Editorial/project production packet drifted.")
    return PreparedActionContributionPacket(
        owner="editorial-project",
        descriptors=descriptors,
        execution_authorities=MappingProxyType({}),
    )


def _media_residual_packet() -> PreparedActionContributionPacket:
    authority = MediaExecutionAuthority()
    available = project_render_storage_media_prepared_action_descriptors()
    descriptors = MappingProxyType({action_id: available[action_id] for action_id in MEDIA_RESIDUAL_CALLABLE_ACTION_IDS})
    return PreparedActionContributionPacket(
        owner="media-residual",
        descriptors=descriptors,
        execution_authorities=residual_media_execution_authorities(authority),
    )


def _operations_render_packet() -> PreparedActionContributionPacket:
    available = project_render_storage_media_prepared_action_descriptors()
    descriptors = MappingProxyType(
        {action_id: available[action_id] for action_id in OPERATIONS_RENDER_PRODUCTION_CALLABLE_ACTION_IDS}
    )
    return PreparedActionContributionPacket(
        owner="operations-render",
        descriptors=descriptors,
        execution_authorities=MappingProxyType({}),
    )


def _timeline_topology_packet() -> PreparedActionContributionPacket:
    descriptors, authorities = timeline_topology_prepared_action_packet()
    return PreparedActionContributionPacket(
        owner="timeline-topology",
        descriptors=descriptors,
        execution_authorities=authorities,
    )


def _timeline_artifact_packet() -> PreparedActionContributionPacket:
    descriptors = timeline_artifact_prepared_action_production_contribution()
    if set(descriptors) != set(TIMELINE_ARTIFACT_ACTION_IDS):
        raise RuntimeError("Timeline managed-artifact production packet drifted.")
    return PreparedActionContributionPacket(
        owner="timeline-managed-artifacts",
        descriptors=descriptors,
        execution_authorities=MappingProxyType(dict(descriptors)),
    )


def _version_packet() -> PreparedActionContributionPacket:
    available = timeline_version_prepared_action_production_contribution()
    descriptors = MappingProxyType(
        {action_id: available[action_id] for action_id in VERSION_PRODUCTION_CALLABLE_ACTION_IDS}
    )
    return PreparedActionContributionPacket(
        owner="version",
        descriptors=descriptors,
        # Timeline/Version descriptors own their complete prepared lifecycle
        # directly; unlike handler-backed packets, they do not dispatch through
        # an admitted command-handler authority.
        execution_authorities=MappingProxyType({}),
    )


# Domain owners add their reviewed private packet factory here. A packet remains
# unavailable unless its descriptor independently passes all eight registry stages.
PRODUCTION_PREPARED_ACTION_CONTRIBUTION_FACTORIES: tuple[
    PreparedActionContributionFactory, ...
] = (
    _marker_packet,
    _professional_primitive_packet,
    _residual_av_callable_packet,
    _residual_av_unavailable_packet,
    _fairlight_packet,
    _visual_fusion_packet,
    _visual_color_packet,
    _editorial_project_packet,
    _media_residual_packet,
    _operations_render_packet,
    _timeline_topology_packet,
    _timeline_artifact_packet,
    _version_packet,
)


def compose_prepared_action_contribution_packets(
    factories: Iterable[PreparedActionContributionFactory],
) -> tuple[
    tuple[tuple[str, Mapping[str, PreparedActionDescriptor]], ...],
    Mapping[str, object],
]:
    contributions: list[tuple[str, Mapping[str, PreparedActionDescriptor]]] = []
    authorities: dict[str, object] = {}
    owners: set[str] = set()
    for factory in factories:
        packet = factory()
        if not isinstance(packet, PreparedActionContributionPacket) or not packet.owner:
            raise TypeError("Prepared-action contribution factory returned an invalid packet.")
        if packet.owner in owners:
            raise ValueError(f"Duplicate prepared-action contribution owner: {packet.owner}")
        owners.add(packet.owner)
        descriptor_ids = set(packet.descriptors)
        authority_ids = set(packet.execution_authorities)
        if not authority_ids.issubset(descriptor_ids):
            raise ValueError(f"Prepared-action contribution authority has no descriptor: {packet.owner}")
        duplicate_authorities = authority_ids.intersection(authorities)
        if duplicate_authorities:
            raise ValueError(
                f"Duplicate prepared-action execution authority: {sorted(duplicate_authorities)[0]}"
            )
        contributions.append((packet.owner, MappingProxyType(dict(packet.descriptors))))
        authorities.update(packet.execution_authorities)
    return tuple(contributions), MappingProxyType(authorities)


@lru_cache(maxsize=1)
def build_production_prepared_action_composition() -> tuple[
    tuple[tuple[str, Mapping[str, PreparedActionDescriptor]], ...],
    Mapping[str, object],
]:
    return compose_prepared_action_contribution_packets(
        PRODUCTION_PREPARED_ACTION_CONTRIBUTION_FACTORIES
    )


# This public action-id surface already exists in the packaged SDK contracts.
# Keep the partition here at the wheel-safe composition boundary so a private
# inventory/report module can never accidentally advertise production routes.
FAIRLIGHT_PRODUCTION_ACTION_IDS = (
    "cutagent.action.fairlight.add",
    "cutagent.action.fairlight.ai.dialogue_leveler",
    "cutagent.action.fairlight.ai.music_remixer",
    "cutagent.action.fairlight.ai.voice_isolation",
    "cutagent.action.fairlight.automation.write",
    "cutagent.action.fairlight.bounce.mix_to_track",
    "cutagent.action.fairlight.bounce.track",
    "cutagent.action.fairlight.bus.assign",
    "cutagent.action.fairlight.bus.level",
    "cutagent.action.fairlight.channel_map.clip",
    "cutagent.action.fairlight.channel_map.set",
    "cutagent.action.fairlight.clip.delete",
    "cutagent.action.fairlight.clip.link",
    "cutagent.action.fairlight.clip.linked.list",
    "cutagent.action.fairlight.clip.move",
    "cutagent.action.fairlight.clip.nudge",
    "cutagent.action.fairlight.clip.slip",
    "cutagent.action.fairlight.clip.source_range",
    "cutagent.action.fairlight.clip.split",
    "cutagent.action.fairlight.clip.track_info",
    "cutagent.action.fairlight.clip.trim",
    "cutagent.action.fairlight.clip.unlink",
    "cutagent.action.fairlight.delete",
    "cutagent.action.fairlight.dynamics.disable",
    "cutagent.action.fairlight.dynamics.enable",
    "cutagent.action.fairlight.dynamics.set",
    "cutagent.action.fairlight.effect.add",
    "cutagent.action.fairlight.effect.remove",
    "cutagent.action.fairlight.effect.set_param",
    "cutagent.action.fairlight.elastic.enable",
    "cutagent.action.fairlight.elastic.keyframe",
    "cutagent.action.fairlight.ensure_stereo_tracks",
    "cutagent.action.fairlight.ensure_tracks",
    "cutagent.action.fairlight.eq.set",
    "cutagent.action.fairlight.export.audio",
    "cutagent.action.fairlight.insert",
    "cutagent.action.fairlight.item_source.patch",
    "cutagent.action.fairlight.lock",
    "cutagent.action.fairlight.mixer.fader",
    "cutagent.action.fairlight.mixer.pan",
    "cutagent.action.fairlight.mute",
    "cutagent.action.fairlight.preset.apply",
    "cutagent.action.fairlight.rename",
    "cutagent.action.fairlight.solo",
    "cutagent.action.fairlight.solo_restore",
    "cutagent.action.fairlight.sound_library.delete",
    "cutagent.action.fairlight.sound_library.index_file",
    "cutagent.action.fairlight.sound_library.index_folder",
    "cutagent.action.fairlight.sound_library.insert",
    "cutagent.action.fairlight.sound_library.list",
    "cutagent.action.fairlight.sound_library.search",
    "cutagent.action.fairlight.sound_library.source_list",
    "cutagent.action.fairlight.sound_library.source_rebuild",
    "cutagent.action.fairlight.sound_library.source_remove",
    "cutagent.action.fairlight.track.duplicate",
    "cutagent.action.fairlight.track_color",
    "cutagent.action.fairlight.track_format.set",
    "cutagent.action.fairlight.track_order.move",
    "cutagent.action.fairlight.transition.add",
    "cutagent.action.fairlight.unlock",
    "cutagent.action.fairlight.unmute",
    "cutagent.action.fairlight.voice_isolation.set",
)

FAIRLIGHT_TECHNICALLY_UNAVAILABLE_ACTION_IDS = ()

FAIRLIGHT_PRODUCTION_READ_ACTION_IDS = (
    "cutagent.action.fairlight.channel_map.clip",
    "cutagent.action.fairlight.clip.linked.list",
    "cutagent.action.fairlight.clip.source_range",
    "cutagent.action.fairlight.clip.track_info",
    "cutagent.action.fairlight.sound_library.list",
    "cutagent.action.fairlight.sound_library.search",
    "cutagent.action.fairlight.sound_library.source_list",
)

FAIRLIGHT_PRODUCTION_MUTATION_ACTION_IDS = tuple(
    action_id
    for action_id in FAIRLIGHT_PRODUCTION_ACTION_IDS
    if action_id not in FAIRLIGHT_PRODUCTION_READ_ACTION_IDS
)

FAIRLIGHT_EVALUATION_ADAPTER_ACTION_IDS = tuple(
    action_id
    for action_id in FAIRLIGHT_PRODUCTION_ACTION_IDS
)

FAIRLIGHT_PRODUCTION_UNAVAILABLE_ACTION_IDS: tuple[str, ...] = ()

if (
    len(FAIRLIGHT_PRODUCTION_ACTION_IDS) != 62
    or len(set(FAIRLIGHT_PRODUCTION_ACTION_IDS)) != 62
    or len(FAIRLIGHT_PRODUCTION_MUTATION_ACTION_IDS) != 55
    or len(FAIRLIGHT_PRODUCTION_READ_ACTION_IDS) != 7
    or len(FAIRLIGHT_TECHNICALLY_UNAVAILABLE_ACTION_IDS) != 0
    or len(FAIRLIGHT_EVALUATION_ADAPTER_ACTION_IDS) != 62
):
    raise RuntimeError("Packaged Fairlight prepared-action partition drifted.")


def build_production_prepared_action_contributions(
) -> tuple[tuple[str, Mapping[str, PreparedActionDescriptor]], ...]:
    return build_production_prepared_action_composition()[0]


def build_production_prepared_action_execution_authorities() -> Mapping[str, object]:
    return build_production_prepared_action_composition()[1]


def build_fairlight_evaluation_contribution(
) -> Mapping[str, PreparedActionDescriptor]:
    """Compose every Fairlight adapter without maintainer-only imports."""

    descriptors, _authorities = _new_fairlight_evaluation_bundle()
    contribution: dict[str, PreparedActionDescriptor] = dict(descriptors)
    contribution.update(
        {action_id: object() for action_id in FAIRLIGHT_TECHNICALLY_UNAVAILABLE_ACTION_IDS}
    )
    return MappingProxyType(contribution)


def build_fairlight_evaluation_execution_authorities(
) -> Mapping[str, object]:
    """Return shared live authorities for every evaluation descriptor."""

    _descriptors, authorities = _new_fairlight_evaluation_bundle()
    return authorities


def _new_fairlight_evaluation_bundle():
    return _new_fairlight_bundle(FAIRLIGHT_EVALUATION_ADAPTER_ACTION_IDS)


def _new_fairlight_bundle(action_ids: tuple[str, ...]):
    from .fairlight_prepared_evaluation import build_evaluation_bundle
    from .fairlight_plan_prepared_action import build_fairlight_plan_prepared_action

    descriptors, authorities = build_evaluation_bundle(action_ids)
    plan_descriptor, plan_authority = build_fairlight_plan_prepared_action()
    return (
        MappingProxyType({**descriptors, plan_descriptor.action_id: plan_descriptor}),
        MappingProxyType({**authorities, plan_descriptor.action_id: plan_authority}),
    )


def build_fairlight_evaluation_composition():
    """Build one isolated descriptor/authority graph for an evaluation host."""

    descriptors, authorities = _new_fairlight_evaluation_bundle()
    contribution: dict[str, PreparedActionDescriptor] = dict(descriptors)
    contribution.update(
        {action_id: object() for action_id in FAIRLIGHT_TECHNICALLY_UNAVAILABLE_ACTION_IDS}
    )
    return (
        (("fairlight-evaluation", MappingProxyType(contribution)),),
        authorities,
    )


def fairlight_evaluation_composition_report() -> Mapping[str, object]:
    """Return the production composition truth used by wheel checks."""

    return MappingProxyType(
        {
            "implementedEvaluationAdapters": len(FAIRLIGHT_EVALUATION_ADAPTER_ACTION_IDS),
            "mutationAdapters": len(FAIRLIGHT_PRODUCTION_MUTATION_ACTION_IDS),
            "readAdapters": len(FAIRLIGHT_PRODUCTION_READ_ACTION_IDS),
            "evaluationGated": len(FAIRLIGHT_EVALUATION_ADAPTER_ACTION_IDS)
            - len(FAIRLIGHT_PRODUCTION_READ_ACTION_IDS),
            "technicallyUnavailable": len(FAIRLIGHT_TECHNICALLY_UNAVAILABLE_ACTION_IDS),
            "productionAdvertised": len(FAIRLIGHT_PRODUCTION_ACTION_IDS),
        }
    )
