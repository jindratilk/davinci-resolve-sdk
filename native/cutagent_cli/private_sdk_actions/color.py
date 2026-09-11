"""Private Color descriptor/executor packet for the prepared-action runtime.

This module owns the Color action registry plus its exact page-action handoff
inside the proprietary CutAgent CLI. It deliberately exposes no raw-command entry point: callers can
prepare and execute only an exact reviewed action id, and the executor receives
the descriptor-bound command identity rather than caller-supplied command data.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from ..command_catalog import CommandDef, get_command_catalog
from .color_runtime_contracts import (
    _action_command_id,
    InventoryValidationError,
    all_active_color_action_ids,
    color_action_input_schema,
    color_action_metadata,
    normalized_color_action_metadata,
    reviewed_page_input_schema,
)

PACKET_SCHEMA = "cutagent.private.color-action-packet"
PACKET_VERSION = 1
EXPECTED_ACTION_COUNT = 169
EXPECTED_ACTION_IDS_SHA256 = "566553e78c7b6dc8f712e628cfe2713c33ebb5321c00233c8f84ea6615425ed0"

RESIDUAL_COLOR_PAGE_ACTION_IDS = frozenset(
    f"cutagent.action.{command_id}"
    for command_id in """color.comp.doctor
color.fx.list
color.gallery.album.current
color.gallery.album.list
color.gallery.still.list
color.graph.inspect
color.graph.validate
color.group.clips
color.group.graph
color.group.list
color.inspect
color.mask.inspect
color.node.graph
color.node.label_get
color.node.list
color.node.lut_get
color.node.tools
color.nodes
color.page.false_color_read
color.page.magic_mask
color.page.qualifier_panel_probe
color.page.read
color.page.resolvefx_list
color.page.resolvefx_param_discover
color.page.resolvefx_param_list
color.page.scope_read
color.page.shot_match_analyze
color.page.snapshot
color.page.viewer_before_after
color.power_grade.list
color.primary.get
color.qualifier.list
color.source_grade.plan
color.thumbnail
color.tracker.list
color.version.list
color.window.list
page.switch""".splitlines()
)
_RESIDUAL_MUTATION_ACTION_IDS = frozenset(
    {
        "cutagent.action.color.page.false_color_read",
        "cutagent.action.color.page.scope_read",
        "cutagent.action.color.page.shot_match_analyze",
        "cutagent.action.color.page.viewer_before_after",
        "cutagent.action.color.thumbnail",
        "cutagent.action.page.switch",
    }
)

_COLOR_WORKFLOW_DUAL_REVISION_ACTION_IDS = frozenset({
    "cutagent.action.color.gallery.still.apply",
    "cutagent.action.color.gallery.still.grab",
    "cutagent.action.color.group.assign",
    "cutagent.action.color.lut",
    "cutagent.action.color.page.shot_match_apply",
    "cutagent.action.color.tracker.track_forward",
    "cutagent.action.color.window.rectangle",
})

_FORBIDDEN_PUBLIC_KEYS = frozenset(
    {
        "argv",
        "command",
        "commandId",
        "commandPath",
        "engine",
        "lowering",
        "privatePreState",
        "recoveryPlan",
        "verificationPlan",
    }
)
_FORBIDDEN_PUBLIC_KEY_NORMALIZED = frozenset(
    {
        "argv", "command", "commandid", "commandpath", "engine", "lowering",
        "privateprestate", "recoveryplan", "verificationplan", "sourcefile",
        "functionname", "filepath", "localpath", "inputpath", "outputpath",
    }
)
_PRIVATE_TEXT = re.compile(
    r"(?:^/(?:Users|home|tmp|private|Applications)/|^[A-Za-z]:\\|^\\\\|^file://|"
    r"Project[.]db|db_workaround|api_native|fusion_native|workaround_setting)",
    re.IGNORECASE,
)
_ARTIFACT_ACTION_IDS = frozenset(
    {
        "cutagent.action.color.comp.export",
        "cutagent.action.color.curves",
        "cutagent.action.color.export_lut",
        "cutagent.action.color.gallery.still.export",
        "cutagent.action.color.huesat",
    }
)
_DESTRUCTIVE_TOKENS = (".delete", ".flatten", ".repair", ".reset", ".remove", ".detach", ".cleanup")
_STRUCTURAL_PREFIXES = (
    "cutagent.action.color.comp.",
    "cutagent.action.color.gallery.",
    "cutagent.action.color.group.",
    "cutagent.action.color.node.",
    "cutagent.action.color.version.",
)
_RENDER_EXEMPT_TOKENS = (
    ".album.",
    ".group.",
    ".version.",
    ".label_set",
    ".lut_set",
    ".cache",
    ".still.export",
    ".still.import",
    ".still.delete",
    ".still.label",
)
_READBACK_VERIFIED_ACTION_IDS = frozenset({
    "cutagent.action.color.page.power_window_circle",
    "cutagent.action.color.page.power_window_track",
    "cutagent.action.color.tracker.add",
    "cutagent.action.color.window.ellipse",
})
_NAMED_OBJECT_SELECTOR_FIELDS = frozenset(
    {
        "clipName",
        "sourceClipName",
        "targetClipNames",
        "stillSelector",
        "qualifierName",
        "trackerName",
        "windowName",
    }
)
_VERSION_NAME_SELECTOR_ACTIONS = frozenset(
    {
        "cutagent.action.color.version.activate",
        "cutagent.action.color.version.delete",
        "cutagent.action.color.version.load",
        "cutagent.action.color.version.rollback",
    }
)

# These handlers have complete signed-runtime execution and verification
# contracts even though their legacy command-catalog maturity remains partial
# or inventory-only.  Keep this private admission list narrow: it does not
# change the public CutAgent CLI capability report, and each route still passes
# through exact carrier binding, Mutation Policy, checkpoint recovery, and the
# capability-specific proof enforced by ``color_prepared_action``.
_SDK_EXECUTION_SUPPORTED_ACTION_IDS = frozenset(
    {
        "cutagent.action.color.fx.apply",
        "cutagent.action.color.huesat",
        "cutagent.action.color.page.magic_mask_refine",
    }
)
_SDK_EXECUTION_CAPABILITY_OVERRIDES = {
    "cutagent.action.color.fx.apply": "edit.ofx_resolvefx_native",
    "cutagent.action.color.page.magic_mask_refine": "color.page_magic_mask_refinement",
}
_SDK_EXECUTION_HANDLER_OVERRIDES = {
    # The legacy ``color fx apply`` command is a clip-level Fusion-template
    # workflow and cannot honor the SDK's required Color node identity. Reuse
    # the reviewed node-exact ResolveFX executor for the typed SDK route.
    "cutagent.action.color.fx.apply": "page_resolvefx_add",
}

def _prepared_action_carrier_metadata() -> Mapping[str, Mapping[str, Any]]:
    """Return authoritative metadata when the generic carrier is present."""

    try:
        from .._sdk_prepared_action_contract import PREPARED_ACTION_ACTION_METADATA
    except ModuleNotFoundError:
        return {}
    return PREPARED_ACTION_ACTION_METADATA


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _canonical_digest(value: Any) -> str:
    return f"sha256:{hashlib.sha256(_canonical_bytes(value)).hexdigest()}"


def _action_set_digest(action_ids: tuple[str, ...]) -> str:
    return hashlib.sha256(("\n".join(action_ids) + "\n").encode()).hexdigest()


def _owned_action_ids() -> tuple[str, ...]:
    metadata = {**color_action_metadata(), **normalized_color_action_metadata()}
    reads = {action_id for action_id, record in metadata.items() if record["sideEffect"] == "read"}
    action_ids = tuple(sorted((all_active_color_action_ids() - reads) | RESIDUAL_COLOR_PAGE_ACTION_IDS))
    if len(action_ids) != EXPECTED_ACTION_COUNT:
        raise InventoryValidationError(
            f"private Color packet must own exactly {EXPECTED_ACTION_COUNT} actions"
        )
    if _action_set_digest(action_ids) != EXPECTED_ACTION_IDS_SHA256:
        raise InventoryValidationError("private Color packet action identity drifted")
    return action_ids


COLOR_ACTION_IDS = _owned_action_ids()


@dataclass(frozen=True)
class ColorActionDescriptor:
    action_id: str
    command_id: str
    capability_id: str | None
    capability_status: str
    target_fields: tuple[str, ...]
    revision_field: str
    impact_kind: str
    destructive: bool
    lowering_profile: str
    result_profile: str
    verification_profile: str
    recovery_profile: str
    protected_state: str
    idempotency: str
    activation_status: str
    private_bindings: tuple[tuple[str, str], ...]
    operation_class: str
    unavailability_reason: str | None

    @property
    def complete(self) -> bool:
        return all(
            (
                self.target_fields or self.action_id == "cutagent.action.page.switch",
                self.revision_field,
                self.impact_kind,
                self.lowering_profile,
                self.result_profile,
                self.verification_profile,
                self.recovery_profile,
                self.protected_state,
                self.idempotency,
                self.private_bindings,
            )
        ) and (
            self.capability_id is not None
            or self.operation_class == "read"
            or self.action_id in _SDK_EXECUTION_SUPPORTED_ACTION_IDS
        ) and not any(binding.startswith("unresolved:") for _, binding in self.private_bindings)

    @property
    def advertised(self) -> bool:
        return (
            self.complete
            and self.capability_status == "supported"
            and self.activation_status == "active"
        )


@dataclass(frozen=True)
class PreparedColorAction:
    descriptor: ColorActionDescriptor
    typed_input: Mapping[str, Any]
    input_digest: str
    targets: tuple[Mapping[str, Any], ...]
    target_digest: str
    pre_state_digest: str
    private_pre_state: Mapping[str, Any]
    private_resolution: Mapping[str, Any]
    resolution_digest: str
    public_impact: Mapping[str, Any]
    impact_digest: str


class ColorActionExecutionFailure(InventoryValidationError):
    """Sanitized failure carrying mandatory recovery truth for Packet 0."""

    def __init__(self, message: str, recovery: Mapping[str, Any]):
        super().__init__(message)
        self.recovery = dict(recovery)


class BoundColorExecutor(Protocol):
    """Signed-runtime adapter; it cannot select a command independently."""

    def execute(
        self,
        descriptor: ColorActionDescriptor,
        typed_input: Mapping[str, Any],
        resolved_targets: tuple[Mapping[str, Any], ...],
    ) -> Mapping[str, Any]: ...

    def recover(
        self,
        descriptor: ColorActionDescriptor,
        prepared: PreparedColorAction,
        failure_kind: str,
    ) -> Mapping[str, Any]: ...


class PreparedActionDigest(Protocol):
    """Packet 0 RFC8785/domain-separated digest authority."""

    def __call__(self, label: str, value: Any) -> str: ...


def _bound_digest(digest: PreparedActionDigest, label: str, value: Any) -> str:
    result = digest(label, value)
    if not isinstance(result, str) or len(result) != 71 or not result.startswith("sha256:"):
        raise InventoryValidationError("prepared-action digest authority returned an invalid digest")
    try:
        int(result[7:], 16)
    except ValueError as exc:
        raise InventoryValidationError("prepared-action digest authority returned an invalid digest") from exc
    return result


def _catalog_by_action() -> dict[str, CommandDef]:
    return {
        f"cutagent.action.{_action_command_id(command.command_id)}": command
        for command in get_command_catalog()
        if not command.legacy and (
            command.command_id.startswith("color.") or command.command_id == "page.switch"
        )
    }


def _input_schema(command_id: str) -> Mapping[str, Any]:
    if command_id == "page.switch":
        schema = reviewed_page_input_schema(command_id)
        if schema is None:
            raise InventoryValidationError("page action lacks a reviewed input schema")
        return schema
    return color_action_input_schema(command_id)


def _required_fields(schema: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(str(field) for field in schema.get("required", ()))


def _validate_typed_value(value: Any, schema: Mapping[str, Any], path: str) -> None:
    if "oneOf" in schema:
        successes = 0
        for branch in schema["oneOf"]:
            try:
                _validate_typed_value(value, branch, path)
            except InventoryValidationError:
                continue
            successes += 1
        if successes != 1:
            raise InventoryValidationError(f"Color action input does not match exactly one schema at {path}")
        return
    if "const" in schema and value != schema["const"]:
        raise InventoryValidationError(f"Color action input violates const at {path}")
    if "enum" in schema and value not in schema["enum"]:
        raise InventoryValidationError(f"Color action input violates enum at {path}")
    expected = schema.get("type")
    allowed_types = set(expected if isinstance(expected, list) else [expected]) if expected else set()
    type_ok = (
        ("null" in allowed_types and value is None)
        or ("boolean" in allowed_types and isinstance(value, bool))
        or ("integer" in allowed_types and isinstance(value, int) and not isinstance(value, bool))
        or ("number" in allowed_types and isinstance(value, (int, float)) and not isinstance(value, bool))
        or ("string" in allowed_types and isinstance(value, str))
        or ("array" in allowed_types and isinstance(value, list))
        or ("object" in allowed_types and isinstance(value, Mapping))
        or not allowed_types
    )
    if not type_ok:
        raise InventoryValidationError(f"Color action input has invalid type at {path}")
    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)) or len(value) > int(schema.get("maxLength", 2**31)):
            raise InventoryValidationError(f"Color action input has invalid length at {path}")
        if schema.get("pattern") and re.fullmatch(str(schema["pattern"]), value) is None:
            raise InventoryValidationError(f"Color action input has invalid format at {path}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            raise InventoryValidationError(f"Color action input must be finite at {path}")
        if "minimum" in schema and value < schema["minimum"]:
            raise InventoryValidationError(f"Color action input is below minimum at {path}")
        if "maximum" in schema and value > schema["maximum"]:
            raise InventoryValidationError(f"Color action input exceeds maximum at {path}")
    if isinstance(value, list):
        if len(value) < int(schema.get("minItems", 0)) or len(value) > int(schema.get("maxItems", 2**31)):
            raise InventoryValidationError(f"Color action input has invalid item count at {path}")
        if schema.get("uniqueItems") and len({_canonical_bytes(item) for item in value}) != len(value):
            raise InventoryValidationError(f"Color action input has duplicate items at {path}")
        for index, item in enumerate(value):
            _validate_typed_value(item, schema.get("items", {}), f"{path}[{index}]")
    if isinstance(value, Mapping):
        required = set(schema.get("required", ()))
        if not required <= set(value):
            raise InventoryValidationError(f"Color action input is missing nested fields at {path}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            raise InventoryValidationError(f"Color action input has nested unreviewed fields at {path}")
        for key, child in value.items():
            if key in properties:
                _validate_typed_value(child, properties[key], f"{path}.{key}")


def _target_fields(schema: Mapping[str, Any]) -> tuple[str, ...]:
    required = set(_required_fields(schema))
    for branch in schema.get("oneOf", ()):
        if isinstance(branch, Mapping):
            required.update(_required_fields(branch))
    ordered = (
        "projectId",
        "timelineId",
        "timelineItemId",
        "groupId",
        "albumId",
        "stillId",
        "trackIndex",
        "recordFrame",
        "nodeIndex",
    )
    fields = tuple(field for field in ordered if field in required)
    if "projectId" not in fields:
        raise InventoryValidationError("Color mutation lacks stable project identity")
    return fields


def _verification_profile(action_id: str, operation_class: str) -> str:
    if operation_class == "read":
        return "bounded_readback"
    if action_id in _ARTIFACT_ACTION_IDS:
        return "artifact_hash_nonempty_and_context"
    if action_id in _READBACK_VERIFIED_ACTION_IDS:
        return "structural_readback_and_revision"
    if action_id == "cutagent.action.page.switch":
        return "structural_readback_and_revision"
    if any(token in action_id for token in _RENDER_EXEMPT_TOKENS):
        return "structural_readback_and_revision"
    if action_id.startswith(_STRUCTURAL_PREFIXES) and not any(
        token in action_id for token in (".apply", ".lut_set")
    ):
        return "structural_readback_and_revision"
    return "color_readback_revision_and_rendered_frame"


def _recovery_profile(action_id: str, destructive: bool) -> str:
    if action_id in _ARTIFACT_ACTION_IDS:
        return "artifact_destination_inspection_and_cleanup"
    if destructive:
        return "restore_prestate_checkpoint_or_manual"
    return "reinspect_exact_target_then_retry_or_manual"


_BINDING_ALIASES: dict[str, tuple[str, ...]] = {
    "clipName": ("clip_name", "clip"),
    "sampleFrame": ("frame",),
    "nodeIndex": ("node_index", "node"),
    "effectName": ("fx", "name"),
    "stillSelector": ("selector", "still"),
    "sourceClipName": ("source",),
    "targetClipNames": ("targets",),
    "saturationBoost": ("sat_boost",),
    "valueBoost": ("val_boost",),
    "lutName": ("path", "apply_lut"),
    "cacheMode": ("mode",),
    "dctlName": ("name",),
    "range": ("range_value",),
    "saturation": ("sat",),
    "luminanceGain": ("lum_gain",),
    "destinationAlbum": ("folder",),
    "parameterNames": ("param",),
    "softness": ("soft_1",),
    "rotation": ("rotate",),
    "parameterName": ("param",),
    "inputSaturation": ("input_sat",),
    "inputLuminance": ("input_lum",),
    "outputSaturation": ("output_sat",),
    "luminance": ("lum",),
    "referenceFrame": ("reference_at",),
    "targetFrame": ("target_at",),
    "templateName": ("template",),
    "versionType": ("remote",),
}
_ACTION_BINDING_OVERRIDES: dict[tuple[str, str], str] = {
    ("cutagent.action.color.fx.apply", "effectName"): "fx",
    ("cutagent.action.color.fx.apply", "nodeIndex"): "select_verified_node_then_handler",
    ("cutagent.action.color.gallery.still.label", "label"): "set_label",
    ("cutagent.action.color.gallery.album.rename", "albumId"): "resolved_album:album",
    ("cutagent.action.color.gallery.album.switch", "albumId"): "resolved_album:album",
    ("cutagent.action.color.gallery.still.apply", "albumId"): "resolved_album:album",
    ("cutagent.action.color.gallery.still.apply", "stillId"): "resolved_still:selector",
    ("cutagent.action.color.gallery.still.delete", "albumId"): "resolved_album:album",
    ("cutagent.action.color.gallery.still.delete", "stillId"): "resolved_still:selector",
    ("cutagent.action.color.gallery.still.export", "albumId"): "resolved_album:album",
    ("cutagent.action.color.gallery.still.export", "stillId"): "resolved_still:selector",
    ("cutagent.action.color.gallery.still.export", "destinationArtifactId"): "artifact:output_path_or_dir",
    ("cutagent.action.color.gallery.still.import", "albumId"): "resolved_album:album",
    ("cutagent.action.color.gallery.still.import", "sourceArtifactId"): "artifact:path",
    ("cutagent.action.color.grade_apply", "sourceArtifactId"): "artifact:path",
    ("cutagent.action.color.group.assign", "groupId"): "resolved_group:group_name",
    ("cutagent.action.color.group.delete", "groupId"): "resolved_group:group_name",
    ("cutagent.action.color.group.rename", "groupId"): "resolved_group:group",
    ("cutagent.action.color.group.add", "name"): "group_name",
    ("cutagent.action.color.page.hdr_detail_set", "saturation"): "sat",
    ("cutagent.action.color.page.hdr_zone_set", "saturation"): "sat",
    ("cutagent.action.color.page.alpha_output_connect", "timelineItemId"): "resolved_clip:clip_name",
    ("cutagent.action.color.page.magic_mask_draw_stroke", "timelineItemId"): "resolved_clip:clip_name",
    ("cutagent.action.color.page.lut_library_import", "lutName"): "apply_lut",
    ("cutagent.action.color.page.power_window_circle_detail", "softness"): "softness_to_all_channels",
    ("cutagent.action.color.page.power_window_linear", "softness"): "softness_to_all_channels",
    ("cutagent.action.color.page.power_window_overlay_transform", "softness"): "softness_to_all_channels",
    ("cutagent.action.color.page.power_window_rectangle", "softness"): "softness_to_all_channels",
    ("cutagent.action.color.page.power_window_set", "rotation"): "rotate",
    ("cutagent.action.color.page.primary_set", "offset"): "components:offset_r,offset_g,offset_b",
    ("cutagent.action.color.cdl", "offset"): "cdl_triplet:offset",
    ("cutagent.action.color.cdl", "power"): "cdl_triplet:power",
    ("cutagent.action.color.cdl", "slope"): "cdl_triplet:slope",
    ("cutagent.action.color.tracker.add", "patternCenter"): "xy_pair:pattern_center",
    ("cutagent.action.color.window.ellipse", "center"): "xy_pair:center",
    ("cutagent.action.color.page.shot_match_apply", "referenceArtifactId"): "artifact:reference_output",
    ("cutagent.action.color.page.shot_match_apply", "targetArtifactId"): "artifact:target_output",
    ("cutagent.action.color.page.shot_match_analyze", "referenceArtifactId"): "artifact:reference_output",
    ("cutagent.action.color.page.shot_match_analyze", "targetArtifactId"): "artifact:target_output",
    ("cutagent.action.color.page.viewer_before_after", "beforeFrame"): "before_at",
    ("cutagent.action.color.page.viewer_before_after", "afterFrame"): "after_at",
    ("cutagent.action.color.page.viewer_before_after", "beforeArtifactId"): "artifact:before_output",
    ("cutagent.action.color.page.viewer_before_after", "afterArtifactId"): "artifact:after_output",
    ("cutagent.action.color.page.viewer_before_after", "contactSheetArtifactId"): "artifact:contact_sheet",
    ("cutagent.action.color.page.still_match", "stillSelector"): "still",
    ("cutagent.action.color.source_grade.apply_cdl", "versionName"): "version_name",
    ("cutagent.action.color.page.warper_set", "target"): "warper_point_to",
    ("cutagent.action.color.power_grade.template_apply", "templateName"): "template",
    ("cutagent.action.color.version.add", "name"): "version_add_name:name_or_clip",
}

for _action_id, _field, _parameter in (
    ("cutagent.action.color.page.still_match", "stillSelector", "still"),
    ("cutagent.action.color.power_grade.apply", "stillSelector", "selector"),
    ("cutagent.action.color.qualifier.attach", "qualifierName", "qualifier_name"),
    ("cutagent.action.color.qualifier.detach", "qualifierName", "qualifier_name"),
    ("cutagent.action.color.tracker.attach_qualifier", "trackerName", "tracker_name"),
    ("cutagent.action.color.tracker.attach_qualifier", "qualifierName", "qualifier_name"),
    ("cutagent.action.color.tracker.attach_window", "trackerName", "tracker_name"),
    ("cutagent.action.color.tracker.attach_window", "windowName", "window_name"),
    ("cutagent.action.color.tracker.set_target", "trackerName", "tracker_name"),
    ("cutagent.action.color.tracker.track_forward", "trackerName", "tracker_name"),
    ("cutagent.action.color.tracker.track_reverse", "trackerName", "tracker_name"),
    ("cutagent.action.color.window.attach", "windowName", "window_name"),
    ("cutagent.action.color.window.detach", "windowName", "window_name"),
):
    _ACTION_BINDING_OVERRIDES[(_action_id, _field)] = f"resolved_selector:{_parameter}"

for _action_id in _VERSION_NAME_SELECTOR_ACTIONS:
    _ACTION_BINDING_OVERRIDES[(_action_id, "name")] = "resolved_selector:name"


def _private_bindings(
    action_id: str,
    schema: Mapping[str, Any],
    command: CommandDef,
) -> tuple[tuple[str, str], ...]:
    if action_id == "cutagent.action.color.lut" and "oneOf" in schema:
        return (
            ("projectId", "resolved_target"),
            ("timelineId", "resolved_target"),
            ("timelineItemId", "resolved_target"),
            ("revision", "prepared_guard"),
            ("colorRevision", "prepared_guard"),
            ("nodeStackLayerIndex", "node_stack_layer_index"),
            ("nodeIndex", "node"),
            ("lutName", "path"),
            ("clear", "clear"),
            ("items", "prepared_items"),
            ("failurePolicy", "failure_policy"),
        )
    parameters = {parameter.python_name for parameter in command.parameters}
    bindings: list[tuple[str, str]] = []
    for field in schema.get("properties", {}):
        if (action_id, field) in _ACTION_BINDING_OVERRIDES:
            binding = _ACTION_BINDING_OVERRIDES[(action_id, field)]
        elif field in {"projectId", "timelineId", "timelineItemId", "groupId", "albumId", "stillId"}:
            binding = "resolved_target"
        elif field == "revision" or (
            field == "colorRevision"
            and action_id in _COLOR_WORKFLOW_DUAL_REVISION_ACTION_IDS
        ):
            binding = "prepared_guard"
        elif field == "trackIndex":
            binding = "track" if "track" in parameters else "resolved_target"
        elif field == "recordFrame":
            binding = "at" if "at" in parameters else "record_frame" if "record_frame" in parameters else "resolved_target"
        elif field in {"sourceArtifactId", "destinationArtifactId"}:
            candidates = (
                ("input_file", "source", "folder")
                if field == "sourceArtifactId"
                else ("output_path", "lut_output", "output", "proof_dir")
            )
            parameter = next((candidate for candidate in candidates if candidate in parameters), None)
            binding = f"artifact:{parameter}" if parameter else "managed_artifact"
        else:
            snake = re.sub(r"(?<!^)(?=[A-Z])", "_", field).lower()
            if snake in parameters:
                binding = snake
            elif field in {"offset", "gamma", "gain", "lift"} and all(
                f"{snake}_{channel}" in parameters for channel in ("r", "g", "b")
            ):
                binding = f"components:{snake}_r,{snake}_g,{snake}_b"
            else:
                alias = next(
                    (candidate for candidate in _BINDING_ALIASES.get(field, ()) if candidate in parameters), ""
                )
                binding = f"enum_remote:{alias}" if field == "versionType" and alias else alias
        if not binding:
            binding = f"unresolved:{field}"
        bindings.append((field, binding))
    return tuple(bindings)


def _build_descriptors() -> dict[str, ColorActionDescriptor]:
    catalog = _catalog_by_action()
    carrier_metadata = _prepared_action_carrier_metadata()
    exact_metadata = color_action_metadata()
    normalized_metadata = normalized_color_action_metadata()
    descriptors: dict[str, ColorActionDescriptor] = {}
    for action_id in COLOR_ACTION_IDS:
        command = catalog.get(action_id)
        if command is None:
            raise InventoryValidationError(f"Color action lacks a bound command handler: {action_id}")
        command_id = command.command_id
        schema = _input_schema(command_id)
        metadata = exact_metadata.get(action_id) or normalized_metadata.get(action_id) or {
            "sideEffect": "project_mutation",
            "idempotency": "idempotent" if action_id == "cutagent.action.page.switch" else "not_idempotent",
            "protectedState": "active_project_and_timeline",
        }
        destructive = any(token in action_id for token in _DESTRUCTIVE_TOKENS)
        impact_kind = "filesystem_write" if action_id in _ARTIFACT_ACTION_IDS else "project_mutation"
        bindings = _private_bindings(action_id, schema, command)
        complete_bindings = bool(bindings) and not any(
            binding.startswith("unresolved:") for _, binding in bindings
        )
        authoritative = carrier_metadata.get(action_id)
        operation_class = str(authoritative["operationClass"]) if authoritative else (
            "read"
            if metadata.get("sideEffect") == "read" and action_id not in _RESIDUAL_MUTATION_ACTION_IDS
            else "mutation"
        )
        capability_id = (
            _SDK_EXECUTION_CAPABILITY_OVERRIDES.get(action_id)
            or (authoritative["capabilityId"] if authoritative else command.capability_id)
        )
        capability_status = (
            "supported"
            if action_id in _SDK_EXECUTION_SUPPORTED_ACTION_IDS
            else command.capability_status or "unadvertised"
        )
        if operation_class == "read" and authoritative is not None:
            capability_status = "supported"
        capability_bound = (
            capability_id is not None
            or operation_class == "read"
            or action_id in _SDK_EXECUTION_SUPPORTED_ACTION_IDS
        )
        signed_runtime_active = True
        descriptor = ColorActionDescriptor(
            action_id=action_id,
            command_id=command_id,
            capability_id=capability_id,
            capability_status=capability_status,
            target_fields=() if command_id == "page.switch" else _target_fields(schema),
            revision_field="revision",
            impact_kind=impact_kind,
            destructive=destructive,
            lowering_profile=(
                f"bound_handler:{_SDK_EXECUTION_HANDLER_OVERRIDES.get(action_id, command.function_name)}"
            ),
            result_profile="exact" if action_id in exact_metadata else "normalized",
            verification_profile=_verification_profile(action_id, operation_class),
            recovery_profile=_recovery_profile(action_id, destructive),
            protected_state=str(metadata.get("protectedState") or "active_project_and_timeline"),
            idempotency=str(metadata.get("idempotency") or "not_idempotent"),
            activation_status=(
                "active"
                if (
                    signed_runtime_active
                    and capability_status == "supported"
                    and complete_bindings
                    and capability_bound
                )
                else "unavailable"
            ),
            private_bindings=bindings,
            operation_class=operation_class,
            unavailability_reason=(
                None
                if (
                    capability_status == "supported"
                    and complete_bindings
                    and capability_bound
                )
                else (
                    "Runtime capability is partial and cannot guarantee exact native verification."
                    if capability_status == "partial"
                    else "No supported runtime capability is assigned to this action."
                )
            ),
        )
        descriptors[action_id] = descriptor
    if len(descriptors) != EXPECTED_ACTION_COUNT:
        raise InventoryValidationError("private Color descriptor count drifted")
    return descriptors


COLOR_ACTION_DESCRIPTORS = _build_descriptors()


def color_action_descriptor(action_id: str, *, require_advertised: bool = True) -> ColorActionDescriptor:
    try:
        descriptor = COLOR_ACTION_DESCRIPTORS[action_id]
    except KeyError as exc:
        raise InventoryValidationError("unreviewed or read-only Color action") from exc
    if require_advertised and not descriptor.advertised:
        raise InventoryValidationError("Color action capability is not currently supported")
    return descriptor


def _reject_private_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized_key = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if key in _FORBIDDEN_PUBLIC_KEYS or normalized_key in _FORBIDDEN_PUBLIC_KEY_NORMALIZED:
                raise InventoryValidationError(f"private Color field crossed the public boundary: {key}")
            _reject_private_keys(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _reject_private_keys(child)
    elif isinstance(value, str) and _PRIVATE_TEXT.search(value):
        raise InventoryValidationError("private Color text crossed the public boundary")


def prepare_color_action(
    action_id: str,
    typed_input: Mapping[str, Any],
    private_live_state: Mapping[str, Any],
    digest: PreparedActionDigest,
    *,
    expected_revision: str | None = None,
) -> PreparedColorAction:
    """Bind one typed action to exact live identities, revision, pre-state and impact."""

    descriptor = color_action_descriptor(action_id)
    return _prepare_bound_descriptor(
        descriptor,
        typed_input,
        private_live_state,
        digest,
        expected_revision=expected_revision,
    )


def _prepare_bound_descriptor(
    descriptor: ColorActionDescriptor,
    typed_input: Mapping[str, Any],
    private_live_state: Mapping[str, Any],
    digest: PreparedActionDigest,
    *,
    expected_revision: str | None = None,
) -> PreparedColorAction:
    """Pure binder used by the signed registry after action admission."""

    action_id = descriptor.action_id
    schema = _input_schema(descriptor.command_id)
    required = _required_fields(schema)
    missing = sorted(field for field in required if field not in typed_input)
    if missing:
        raise InventoryValidationError(f"Color action input is missing required fields: {missing}")
    unknown = sorted(set(typed_input) - set(schema.get("properties", {})))
    if unknown:
        raise InventoryValidationError(f"Color action input contains unreviewed fields: {unknown}")
    _reject_private_keys(typed_input)
    _validate_typed_value(typed_input, schema, "input")

    primary_target: dict[str, Any] = {}
    for field in descriptor.target_fields:
        expected = typed_input.get(field)
        actual = private_live_state.get(field)
        if expected is None or actual != expected:
            raise InventoryValidationError(f"Color stable target mismatch: {field}")
        primary_target[field] = actual
    bound_revision = (
        expected_revision
        if isinstance(expected_revision, str) and expected_revision
        else typed_input.get(descriptor.revision_field)
    )
    if not isinstance(bound_revision, str) or not bound_revision:
        raise InventoryValidationError("Color action requires a bound stable revision")
    if private_live_state.get("revision") != bound_revision:
        raise InventoryValidationError("Color action revision is stale")

    private_pre_state = private_live_state.get("preState")
    if not isinstance(private_pre_state, Mapping) or not private_pre_state:
        raise InventoryValidationError("Color action requires complete private pre-state")
    resolved = private_live_state.get("resolvedTargets")
    if private_live_state.get("impactComplete") is not True or not isinstance(resolved, list) or not resolved:
        raise InventoryValidationError("Color action requires complete resolved impact targets")
    allowed_target_fields = {"kind", "stableId", "revision", "trackType", "trackIndex", "mediaRole"}
    allowed_target_kinds = {
        "project", "timeline", "track", "clip", "fusion_composition", "media",
        "marker", "artifact",
    }
    targets: list[Mapping[str, Any]] = []
    for item in resolved:
        if (
            not isinstance(item, Mapping)
            or item.get("kind") not in allowed_target_kinds
            or not isinstance(item.get("stableId"), str)
            or not isinstance(item.get("revision"), str)
            or not item.get("revision")
        ):
            raise InventoryValidationError("Color impact contains an invalid resolved target")
        unknown_target_fields = set(item) - allowed_target_fields
        if unknown_target_fields:
            raise InventoryValidationError("Color impact target contains private or unstable fields")
        targets.append(dict(item))
    primary_stable_id = next(
        (primary_target[field] for field in ("timelineItemId", "stillId", "groupId", "albumId", "timelineId", "projectId") if field in primary_target),
        None,
    )
    if descriptor.action_id == "cutagent.action.page.switch":
        primary_stable_id = next((item.get("stableId") for item in targets), None)
    primary_targets = [
        item for item in targets if item.get("stableId") == primary_stable_id
    ]
    if not primary_targets:
        raise InventoryValidationError("Color impact omitted the primary stable target")
    if primary_targets[0].get("revision") != bound_revision:
        raise InventoryValidationError("Color primary target revision is stale")
    if len({_canonical_digest(item) for item in targets}) != len(targets):
        raise InventoryValidationError("Color impact contains duplicate targets")
    if private_live_state.get("closedComposition") is not True:
        raise InventoryValidationError("Color impact composition is not closed")
    if private_live_state.get("resolvedTargetCount") != len(targets):
        raise InventoryValidationError("Color impact target count is incomplete")
    if private_live_state.get("resolvedTargetsDigest") != _bound_digest(digest, "targets", targets):
        raise InventoryValidationError("Color impact target inventory digest mismatched")
    selector_fields = {
        field for field in schema.get("properties", {})
        if field in _NAMED_OBJECT_SELECTOR_FIELDS
    }
    if action_id in _VERSION_NAME_SELECTOR_ACTIONS and "name" in schema.get("properties", {}):
        selector_fields.add("name")
    if selector_fields and private_live_state.get("selectorResolutionComplete") is not True:
        raise InventoryValidationError("Color selector resolution is incomplete")
    selector_bindings = private_live_state.get("selectorBindings")
    if selector_fields and not isinstance(selector_bindings, Mapping):
        raise InventoryValidationError("Color selector bindings are missing")
    selector_values: list[str] = []
    for field in selector_fields:
        value = typed_input.get(field)
        if isinstance(value, str):
            selector_values.append(value)
        elif isinstance(value, list) and all(isinstance(item, str) for item in value):
            selector_values.extend(value)
    if selector_fields:
        target_ids = {item["stableId"] for item in targets}
        if (
            not selector_values
            or any(not isinstance(selector_bindings.get(value), str) for value in selector_values)
            or any(selector_bindings[value] not in target_ids for value in selector_values)
        ):
            raise InventoryValidationError("Color selector impact bindings are incomplete")
    if action_id == "cutagent.action.color.grade_copy":
        expected_count = len(typed_input.get("targetClipNames", ())) + 1
        expected_names = {typed_input.get("sourceClipName"), *typed_input.get("targetClipNames", ())}
        bound_ids = {selector_bindings.get(name) for name in expected_names} if isinstance(selector_bindings, Mapping) else set()
        if (
            len(targets) != expected_count
            or any(item.get("kind") != "clip" for item in targets)
            or None in bound_ids
            or bound_ids != {item["stableId"] for item in targets}
        ):
            raise InventoryValidationError("Color grade-copy impact is incomplete")
    if action_id == "cutagent.action.color.still.grab_all":
        all_item_ids = private_live_state.get("allTimelineItemIds")
        if (
            not isinstance(all_item_ids, list)
            or not all_item_ids
            or len(set(all_item_ids)) != len(all_item_ids)
            or set(all_item_ids) != {item["stableId"] for item in targets}
            or any(item.get("kind") != "clip" for item in targets)
        ):
            raise InventoryValidationError("Color grab-all impact is incomplete")
    if action_id == "cutagent.action.color.gallery.still.label" and (
        not any(item.get("kind") == "media" for item in targets)
        or not isinstance(selector_bindings, Mapping)
        or selector_bindings.get(typed_input.get("stillSelector"))
        not in {item.get("stableId") for item in targets if item.get("kind") == "media"}
    ):
        raise InventoryValidationError("Color still-label impact is incomplete")
    public_impact = {
        "schema": "cutagent.sdk.public-impact",
        "version": 1,
        "actionId": action_id,
        "kind": descriptor.impact_kind,
        "destructive": descriptor.destructive,
        "targets": targets,
        "protectedState": descriptor.protected_state,
    }
    _reject_private_keys(public_impact)
    private_resolution = {
        "closedComposition": True,
        "resolvedTargetCount": len(targets),
        "resolvedTargetsDigest": private_live_state["resolvedTargetsDigest"],
        "selectorBindings": deepcopy(dict(selector_bindings)) if isinstance(selector_bindings, Mapping) else {},
        "allTimelineItemIds": list(private_live_state.get("allTimelineItemIds", ())),
    }
    return PreparedColorAction(
        descriptor=descriptor,
        typed_input=deepcopy(dict(typed_input)),
        input_digest=_bound_digest(digest, "input", typed_input),
        targets=tuple(deepcopy(target) for target in targets),
        target_digest=_bound_digest(digest, "targets", targets),
        pre_state_digest=_bound_digest(digest, "pre-state", private_pre_state),
        private_pre_state=deepcopy(dict(private_pre_state)),
        private_resolution=private_resolution,
        resolution_digest=_bound_digest(digest, "pre-state", {"resolution": private_resolution}),
        public_impact=deepcopy(public_impact),
        impact_digest=_bound_digest(digest, "impact", public_impact),
    )


def _execute_bound_descriptor(
    prepared: PreparedColorAction,
    current: ColorActionDescriptor,
    executor: BoundColorExecutor,
    inspect_after: Callable[[ColorActionDescriptor, Mapping[str, Any]], Mapping[str, Any]],
    digest: PreparedActionDigest,
) -> Mapping[str, Any]:
    """Execute a descriptor already admitted by the private registry."""

    if (
        current != prepared.descriptor
        or _bound_digest(digest, "input", prepared.typed_input) != prepared.input_digest
        or _bound_digest(digest, "targets", list(prepared.targets)) != prepared.target_digest
        or _bound_digest(digest, "pre-state", prepared.private_pre_state) != prepared.pre_state_digest
        or _bound_digest(digest, "impact", prepared.public_impact) != prepared.impact_digest
        or _bound_digest(digest, "pre-state", {"resolution": prepared.private_resolution})
        != prepared.resolution_digest
        or prepared.private_resolution.get("resolvedTargetsDigest") != prepared.target_digest
    ):
        raise InventoryValidationError("prepared Color action binding mismatch")
    sealed_prepared = deepcopy(prepared)
    try:
        native_result = executor.execute(
            current,
            deepcopy(dict(sealed_prepared.typed_input)),
            tuple(deepcopy(dict(target)) for target in sealed_prepared.targets),
        )
    except Exception:
        _raise_with_recovery(executor, current, sealed_prepared, "execution_failed", inspect_after, digest)
        raise AssertionError("unreachable")
    try:
        if not isinstance(native_result, Mapping):
            raise InventoryValidationError("Color executor returned invalid truth")
        after = inspect_after(
            current,
            {
                "phase": "verification",
                "targets": [deepcopy(dict(target)) for target in sealed_prepared.targets],
            },
        )
        if not isinstance(after, Mapping):
            raise InventoryValidationError("Color verification returned invalid truth")
        after_targets = after.get("targets")
        if (
            not isinstance(after_targets, list)
            or _bound_digest(digest, "targets", after_targets) != sealed_prepared.target_digest
        ):
            raise InventoryValidationError("Color target set changed during execution")

        verification = after.get("verification")
        if not isinstance(verification, Mapping) or verification.get("passed") is not True:
            raise InventoryValidationError("Color action verification failed")
        _reject_private_keys(verification)
        if current.verification_profile == "color_readback_revision_and_rendered_frame" and verification.get("renderedFrameChanged") is not True:
            raise InventoryValidationError("Color mutation lacks rendered-frame proof")
        if current.verification_profile not in {
            "artifact_hash_nonempty_and_context",
            "bounded_readback",
        } and verification.get("revisionChanged") is not True:
            raise InventoryValidationError("Color mutation lacks revision transition proof")
        if current.verification_profile == "artifact_hash_nonempty_and_context":
            artifacts = verification.get("artifacts")
            if not isinstance(artifacts, list) or not artifacts or any(
                not isinstance(item, Mapping) or not item.get("sha256") or int(item.get("byteLength", 0)) < 1
                for item in artifacts
            ):
                raise InventoryValidationError("Color artifact mutation lacks hash/nonempty proof")

        public_result = native_result.get("publicResult")
        if not isinstance(public_result, Mapping):
            raise InventoryValidationError("Color executor omitted public result projection")
        _reject_private_keys(public_result)
        return {
            "actionId": current.action_id,
            "payload": dict(public_result),
            "verification": dict(verification),
            "evidenceDigest": _canonical_digest({"result": public_result, "verification": verification}),
        }
    except ColorActionExecutionFailure:
        raise
    except Exception:
        _raise_with_recovery(
            executor,
            current,
            sealed_prepared,
            "post_execution_validation_failed",
            inspect_after,
            digest,
        )
        raise AssertionError("unreachable")


def _raise_with_recovery(
    executor: BoundColorExecutor,
    descriptor: ColorActionDescriptor,
    prepared: PreparedColorAction,
    failure_kind: str,
    inspect_after: Callable[[ColorActionDescriptor, Mapping[str, Any]], Mapping[str, Any]],
    digest: PreparedActionDigest,
) -> None:
    try:
        recovery = executor.recover(descriptor, deepcopy(prepared), failure_kind)
    except Exception as exc:
        raise ColorActionExecutionFailure(
            "Color action recovery failed",
            {"outcome": "failed", "attempted": True, "manualActionRequired": True},
        ) from exc
    if not isinstance(recovery, Mapping):
        raise ColorActionExecutionFailure(
            "Color action recovery returned invalid truth",
            {"outcome": "failed", "attempted": True, "manualActionRequired": True},
        )
    _reject_private_keys(recovery)
    if recovery.get("outcome") not in {"restored", "manual_required", "failed"}:
        raise ColorActionExecutionFailure(
            "Color action recovery returned invalid truth",
            {"outcome": "failed", "attempted": True, "manualActionRequired": True},
        )
    if recovery.get("attempted") is not True or not isinstance(recovery.get("manualActionRequired"), bool):
        raise ColorActionExecutionFailure(
            "Color action recovery returned incomplete truth",
            {"outcome": "failed", "attempted": True, "manualActionRequired": True},
        )
    if (
        (recovery.get("outcome") == "restored" and recovery.get("manualActionRequired") is not False)
        or (recovery.get("outcome") in {"manual_required", "failed"} and recovery.get("manualActionRequired") is not True)
    ):
        raise ColorActionExecutionFailure(
            "Color action recovery returned contradictory truth",
            {"outcome": "failed", "attempted": True, "manualActionRequired": True},
        )
    if recovery.get("outcome") == "restored":
        try:
            restored = inspect_after(
                descriptor,
                {
                    "phase": "recovery",
                    "targets": [deepcopy(dict(target)) for target in prepared.targets],
                },
            )
            if not isinstance(restored, Mapping):
                raise InventoryValidationError("invalid recovery readback")
            restored_targets = restored.get("targets")
            restored_pre_state = restored.get("preState")
            if (
                not isinstance(restored_targets, list)
                or _bound_digest(digest, "targets", restored_targets) != prepared.target_digest
                or not isinstance(restored_pre_state, Mapping)
                or _bound_digest(digest, "pre-state", restored_pre_state) != prepared.pre_state_digest
            ):
                raise InventoryValidationError("recovery readback mismatch")
        except Exception as exc:
            raise ColorActionExecutionFailure(
                "Color action recovery could not be verified",
                {"outcome": "failed", "attempted": True, "manualActionRequired": True},
            ) from exc
    raise ColorActionExecutionFailure("Color action did not complete successfully", recovery)


def sanitized_color_packet_fixture() -> dict[str, Any]:
    """Public-safe generated proof of exact packet closure; contains no lowering."""

    actions = []
    for descriptor in COLOR_ACTION_DESCRIPTORS.values():
        actions.append(
            {
                "actionId": descriptor.action_id,
                "capabilityId": descriptor.capability_id,
                "capabilityStatus": descriptor.capability_status,
                "advertised": descriptor.advertised,
                "descriptorComplete": descriptor.complete,
                "activationStatus": descriptor.activation_status,
                "targetFields": list(descriptor.target_fields),
                "impactKind": descriptor.impact_kind,
                "destructive": descriptor.destructive,
                "resultProfile": descriptor.result_profile,
                "verificationProfile": descriptor.verification_profile,
                "recoveryProfile": descriptor.recovery_profile,
                "availabilityReason": descriptor.unavailability_reason,
            }
        )
    fixture = {
        "schema": PACKET_SCHEMA,
        "version": PACKET_VERSION,
        "actionCount": len(actions),
        "advertisedActionCount": sum(1 for action in actions if action["advertised"]),
        "descriptorCompleteActionCount": sum(1 for action in actions if action["descriptorComplete"]),
        "unadvertisedActionCount": sum(1 for action in actions if not action["advertised"]),
        "actionIdsSha256": EXPECTED_ACTION_IDS_SHA256,
        "actions": actions,
    }
    _reject_private_keys(fixture)
    return fixture
