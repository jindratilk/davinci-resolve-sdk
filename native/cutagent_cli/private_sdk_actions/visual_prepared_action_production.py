"""Production activation and classification truth for visual SDK actions.

This module is compiled only into the proprietary CutAgent CLI runtime.  It
keeps the visual packet partition reviewable without projecting command
lowering, native routes, filesystem paths, or recovery implementation into the
public TypeScript package.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping

from .fusion_descriptor_summary import (
    FUSION_PACKET_CALLABLE_IDS,
    FUSION_PACKET_DELEGATED,
    FUSION_PACKET_UNSUPPORTED,
)
from .color import COLOR_ACTION_DESCRIPTORS
from .color_prepared_action import (
    CALLABLE_COLOR_ACTION_IDS,
    UNAVAILABLE_COLOR_ACTION_IDS,
)


# These bounded reads already have active typed low-level executors and do not
# need a second prepared-action route.
VISUAL_EXISTING_TYPED_READ_ACTION_IDS = frozenset(
    {
        "cutagent.action.fusion.preview",
        "cutagent.action.fusion.template.list",
        "cutagent.action.page.current",
    }
)

# Existing semantic executors remain the primary route. Their private visual
# descriptors stay in the production registry so the same lifecycle contract
# is available to the carrier, but reachability must classify them as semantic
# rather than duplicate low-level actions.
VISUAL_EXISTING_SEMANTIC_ACTION_IDS = frozenset(
    {
        "cutagent.action.color.grade_apply",
        "cutagent.action.color.node.label_set",
        "cutagent.action.color.page.node_add",
        "cutagent.action.color.page.primary_set",
        "cutagent.action.color.page.resolvefx_add",
        "cutagent.action.fusion.apply",
    }
)

# These are already registered by the residual audiovisual production packet.
# They remain visual-owned for classification but must not be duplicated here.
VISUAL_EXISTING_PREPARED_ACTION_IDS = frozenset(
    {
        "cutagent.action.burnin.load",
        "cutagent.action.burnin.preset.export",
        "cutagent.action.burnin.preset.import",
    }
)

VISUAL_SUPPORTED_PREPARED_ACTION_IDS = frozenset(
    (
        FUSION_PACKET_CALLABLE_IDS
        | frozenset(CALLABLE_COLOR_ACTION_IDS)
        | VISUAL_EXISTING_PREPARED_ACTION_IDS
        | frozenset({"cutagent.action.fusion.apply"})
    )
)

# The Bridge already captures exact live bindings for the non-artifact Fusion
# subset.  These artifact-backed actions are intentionally release-gated by
# the Bridge until its retained-handle/reserved-destination custody is complete.
VISUAL_ARTIFACT_CUSTODY_PENDING_ACTION_IDS = frozenset(
    {
        "cutagent.action.dctl.apply",
        "cutagent.action.fusion.generate",
        "cutagent.action.fusion.image.set",
        "cutagent.action.fusion.insert_setting",
        "cutagent.action.fusion.setting.inspect",
        "cutagent.action.fusion.setting.summary",
        "cutagent.action.fusion.setting.validate",
        "cutagent.action.fusion.template.apply",
        "cutagent.action.fusion.template.assets.add",
        "cutagent.action.fusion.template.assets.list",
        "cutagent.action.fusion.template.dir",
        "cutagent.action.fusion.template.icon.set",
        "cutagent.action.fusion.template.install",
        "cutagent.action.fusion.template.package_drfx",
        "cutagent.action.fusion.template.scaffold",
        "cutagent.action.fusion.template.show",
        "cutagent.action.fusion.template.uninstall",
        "cutagent.action.fusion.template.validate",
        "cutagent.action.lut.convert",
        "cutagent.action.lut.generate.identity",
        "cutagent.action.lut.inspect",
        "cutagent.action.lut.install",
        "cutagent.action.lut.list",
        "cutagent.action.lut.remove",
        "cutagent.action.lut.validate",
    }
)

# These read-only actions target the exact active Color clip.  The Bridge can
# close their public identity to the private native clip identity without a
# selector supplied by the caller. Mutation-capable Color reads remain on the
# guarded prepared-action lifecycle instead of this direct-read set.
VISUAL_COLOR_EXACT_READ_ACTION_IDS = frozenset(
    {
        "cutagent.action.color.comp.doctor",
        "cutagent.action.color.fx.list",
        "cutagent.action.color.graph.inspect",
        "cutagent.action.color.graph.validate",
        "cutagent.action.color.inspect",
        "cutagent.action.color.mask.inspect",
        "cutagent.action.color.node.graph",
        "cutagent.action.color.node.list",
        "cutagent.action.color.nodes",
        "cutagent.action.color.page.qualifier_panel_probe",
        "cutagent.action.color.page.read",
        "cutagent.action.color.page.resolvefx_list",
        "cutagent.action.color.power_grade.list",
        "cutagent.action.color.primary.get",
        "cutagent.action.color.qualifier.list",
        "cutagent.action.color.tracker.list",
        "cutagent.action.color.version.list",
        "cutagent.action.color.window.list",
    }
)

VISUAL_COLOR_ARTIFACT_CUSTODY_PENDING_ACTION_IDS = frozenset(
    action_id
    for action_id in CALLABLE_COLOR_ACTION_IDS
    if any(
        binding == "managed_artifact" or binding.startswith("artifact:")
        for _, binding in COLOR_ACTION_DESCRIPTORS[action_id].private_bindings
    )
)
VISUAL_COLOR_ARTIFACT_CUSTODY_ACTION_IDS = frozenset(
    VISUAL_COLOR_ARTIFACT_CUSTODY_PENDING_ACTION_IDS
    - VISUAL_EXISTING_SEMANTIC_ACTION_IDS
)

_COLOR_UNBOUND_SELECTOR_FIELDS = frozenset(
    {"stillSelector", "qualifierName", "trackerName", "versionName", "windowName"}
)
VISUAL_COLOR_EXACT_SELECTOR_PENDING_ACTION_IDS = frozenset(
    action_id
    for action_id in CALLABLE_COLOR_ACTION_IDS
    if action_id not in VISUAL_COLOR_ARTIFACT_CUSTODY_PENDING_ACTION_IDS
    and (
        ".group." in action_id
        or ".gallery." in action_id
        or action_id == "cutagent.action.color.power_grade.album.create"
        or any(
            field_name in _COLOR_UNBOUND_SELECTOR_FIELDS
            for field_name, _ in COLOR_ACTION_DESCRIPTORS[action_id].private_bindings
        )
    )
)

VISUAL_COLOR_VERSION_SELECTOR_PENDING_ACTION_IDS = frozenset(
    ()
)

VISUAL_COLOR_SAFE_PREPARED_ACTION_IDS = frozenset(
    set(CALLABLE_COLOR_ACTION_IDS)
    - VISUAL_COLOR_ARTIFACT_CUSTODY_PENDING_ACTION_IDS
    - VISUAL_EXISTING_SEMANTIC_ACTION_IDS
    - VISUAL_COLOR_VERSION_SELECTOR_PENDING_ACTION_IDS
)

VISUAL_PRODUCTION_CALLABLE_ACTION_IDS = frozenset(
    FUSION_PACKET_CALLABLE_IDS
    | VISUAL_COLOR_SAFE_PREPARED_ACTION_IDS
    | VISUAL_COLOR_ARTIFACT_CUSTODY_ACTION_IDS
    | VISUAL_EXISTING_PREPARED_ACTION_IDS
)
VISUAL_PACKET_CALLABLE_ACTION_IDS = frozenset(
    VISUAL_PRODUCTION_CALLABLE_ACTION_IDS - VISUAL_EXISTING_PREPARED_ACTION_IDS
)

VISUAL_SDK_ACTIVATION_PENDING_ACTION_REASONS = MappingProxyType(
    {
        **{
            action_id: "bridge_persistent_selector_identity_pending"
            for action_id in VISUAL_COLOR_VERSION_SELECTOR_PENDING_ACTION_IDS
        },
    }
)

VISUAL_HIGH_LEVEL_EQUIVALENT_ACTION_REASONS = MappingProxyType(
    {
        **{
            action_id: reason
            for action_id, reason in FUSION_PACKET_DELEGATED.items()
            if action_id != "cutagent.action.fusion.apply"
        },
        "cutagent.action.fusion.image.batch": "compose_typed_fusion_graph_operations",
        "cutagent.action.fusion.insert_settings.batch": "compose_typed_fusion_graph_operations",
        "cutagent.action.fusion.nested_text.batch": "compose_typed_fusion_graph_operations",
        "cutagent.action.fusion.text.batch": "compose_typed_fusion_graph_operations",
    }
)

VISUAL_UNSATISFIED_HIGH_LEVEL_EQUIVALENT_ACTION_IDS = frozenset()

VISUAL_UNAVAILABLE_ACTION_REASONS = MappingProxyType(
    {
        **dict(FUSION_PACKET_UNSUPPORTED),
        "cutagent.action.fusion.template.unpack_drfx": (
            "No reviewed public managed-artifact composition can accept and unpack an arbitrary .drfx bundle."
        ),
        **{
            action_id: str(COLOR_ACTION_DESCRIPTORS[action_id].unavailability_reason)
            for action_id in UNAVAILABLE_COLOR_ACTION_IDS
        },
    }
)

VISUAL_OWNED_ACTION_IDS = frozenset(
    VISUAL_SUPPORTED_PREPARED_ACTION_IDS
    | VISUAL_EXISTING_SEMANTIC_ACTION_IDS
    | VISUAL_EXISTING_TYPED_READ_ACTION_IDS
    | frozenset(VISUAL_HIGH_LEVEL_EQUIVALENT_ACTION_REASONS)
    | VISUAL_UNSATISFIED_HIGH_LEVEL_EQUIVALENT_ACTION_IDS
    | frozenset(VISUAL_UNAVAILABLE_ACTION_REASONS)
)

VISUAL_RESIDUAL_SUPPORTED_ACTION_IDS = frozenset(
    VISUAL_SUPPORTED_PREPARED_ACTION_IDS
    - VISUAL_EXISTING_SEMANTIC_ACTION_IDS
    - VISUAL_PRODUCTION_CALLABLE_ACTION_IDS
)


def visual_prepared_action_contributions() -> tuple[
    tuple[str, Mapping[str, Any]], ...
]:
    """Build the reviewed private Fusion and Color contribution packets."""

    from .color_prepared_action import (
        COLOR_PREPARED_ACTION_CONTRIBUTION_NAME,
        color_prepared_action_contribution,
    )
    from .fusion_prepared_action import fusion_prepared_action_descriptors
    from .fusion_timeline_production import ProductionFusionPreparedActionRuntime

    fusion_owner = "fusion"
    fusion = fusion_prepared_action_descriptors(
        runtime=ProductionFusionPreparedActionRuntime()
    )
    production_fusion = MappingProxyType({
        action_id: (
            descriptor
            if action_id in VISUAL_PRODUCTION_CALLABLE_ACTION_IDS
            else object()
        )
        for action_id, descriptor in fusion.items()
    })
    color = color_prepared_action_contribution()
    production_color = MappingProxyType({
        action_id: (
            descriptor
            if action_id in (
                VISUAL_COLOR_SAFE_PREPARED_ACTION_IDS
                | VISUAL_COLOR_ARTIFACT_CUSTODY_ACTION_IDS
            )
            else object()
        )
        for action_id, descriptor in color.items()
    })
    return (
        (fusion_owner, production_fusion),
        (
            COLOR_PREPARED_ACTION_CONTRIBUTION_NAME,
            production_color,
        ),
    )


def _visual_packet(index: int) -> Any:
    from ..prepared_action_contributions import PreparedActionContributionPacket

    owner, descriptors = visual_prepared_action_contributions()[index]
    return PreparedActionContributionPacket(
        owner=owner,
        descriptors=descriptors,
        execution_authorities=MappingProxyType({}),
    )


def visual_fusion_prepared_action_contribution_packet() -> Any:
    """Return the production Fusion packet for central composition."""

    return _visual_packet(0)


def visual_color_prepared_action_contribution_packet() -> Any:
    """Return the production Color packet for central composition."""

    return _visual_packet(1)


if (
    len(VISUAL_OWNED_ACTION_IDS) != 251
    or len(VISUAL_SUPPORTED_PREPARED_ACTION_IDS) != 237
    or len(VISUAL_RESIDUAL_SUPPORTED_ACTION_IDS) != 0
    or len(VISUAL_ARTIFACT_CUSTODY_PENDING_ACTION_IDS) != 25
    or len(VISUAL_COLOR_ARTIFACT_CUSTODY_PENDING_ACTION_IDS) != 18
    or len(VISUAL_COLOR_ARTIFACT_CUSTODY_ACTION_IDS) != 17
    or len(VISUAL_COLOR_EXACT_SELECTOR_PENDING_ACTION_IDS) != 31
    or len(VISUAL_COLOR_VERSION_SELECTOR_PENDING_ACTION_IDS) != 0
    or len(VISUAL_COLOR_EXACT_READ_ACTION_IDS) != 18
    or len(VISUAL_COLOR_SAFE_PREPARED_ACTION_IDS) != 147
    or len(VISUAL_PRODUCTION_CALLABLE_ACTION_IDS) != 231
    or len(VISUAL_PACKET_CALLABLE_ACTION_IDS) != 228
    or len(VISUAL_SDK_ACTIVATION_PENDING_ACTION_REASONS) != 0
    or len(VISUAL_EXISTING_TYPED_READ_ACTION_IDS) != 3
    or len(VISUAL_EXISTING_SEMANTIC_ACTION_IDS) != 6
    or len(VISUAL_HIGH_LEVEL_EQUIVALENT_ACTION_REASONS) != 4
    or len(VISUAL_UNSATISFIED_HIGH_LEVEL_EQUIVALENT_ACTION_IDS) != 0
    or len(VISUAL_EXISTING_PREPARED_ACTION_IDS) != 3
    or len(VISUAL_UNAVAILABLE_ACTION_REASONS) != 7
):
    raise RuntimeError("Visual prepared-action production partition drifted.")
