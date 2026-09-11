"""Complete signed-carrier contribution for residual Clip/Text/Audio actions.

The descriptor packet never accepts a command identity from its caller. Each
registered action is permanently bound to one reviewed descriptor and delegates
its seven domain stages to the connected semantic owner after signed carrier
admission. The eighth stage is the carrier's authorization/admission gate.
Frozen-protocol conflicts and failed native production proof remain explicitly
unavailable.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence

from ..errors import ValidationError
from .._sdk_prepared_action_contract import PREPARED_ACTION_ACTION_METADATA
from .residual_av import RESIDUAL_AV_ACTION_DESCRIPTORS, ResidualAvActionDescriptor
from .residual_av_handler_runtime import (
    canonical_residual_av_handler_args,
)


UNAVAILABLE_RESIDUAL_AV_ACTIONS = MappingProxyType(
    {
        "cutagent.action.clip.magic_mask": "native_magic_mask_method_failed_live_production_proof",
    }
)
CARRIER_CALLABLE_RESIDUAL_AV_ACTIONS = frozenset(
    descriptor.action_id
    for descriptor in RESIDUAL_AV_ACTION_DESCRIPTORS
    if descriptor.action_id not in UNAVAILABLE_RESIDUAL_AV_ACTIONS
)

_ALLOWED_EVIDENCE = frozenset(
    {"readback", "structural", "file", "rendered", "visual", "auditioned"}
)
_MODALITY = {
    "structural_readback": frozenset({"readback", "structural"}),
    "artifact_readback": frozenset({"file"}),
    "rendered_frame": frozenset({"rendered"}),
    "audition": frozenset({"auditioned"}),
}
_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
_OPAQUE_ID = {
    "requestId": re.compile(r"^request_[A-Za-z0-9][A-Za-z0-9._~-]{0,151}$"),
    "operationId": re.compile(r"^operation_[A-Za-z0-9][A-Za-z0-9._~-]{0,149}$"),
    "executionId": re.compile(r"^execution_[A-Za-z0-9][A-Za-z0-9._~-]{0,149}$"),
}
_STABLE_TARGET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:~+/-]{2,255}$")
_STATE_REVISION = re.compile(r"^(?:sha256:)?[A-Za-z0-9_-]{16,128}$")
_PRIVATE_KEYS = frozenset(
    {
        "argv", "command", "commandId", "commandPath", "engine", "lowering",
        "preState", "recoveryPlan", "verificationPlan",
    }
)


def _mutable_copy(value: Any) -> Any:
    """Thaw carrier-frozen handler inputs without pickle-based copying."""

    if isinstance(value, Mapping):
        return {key: _mutable_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_mutable_copy(item) for item in value]
    return deepcopy(value)


class ResidualAvSemanticOwner(Protocol):
    """One action-specific semantic owner; no method receives an action id."""

    def normalize_input(self, value: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def resolve_exact(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def build_impact(
        self, context: Mapping[str, Any], value: Mapping[str, Any], authority: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...
    def execute(
        self, context: Mapping[str, Any], value: Mapping[str, Any], prepared: Mapping[str, Any]
    ) -> Any: ...
    def read_evidence(
        self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any
    ) -> Mapping[str, Any]: ...
    def recover(
        self, context: Mapping[str, Any], prepared: Mapping[str, Any], failure: BaseException
    ) -> Mapping[str, Any]: ...
    def project_result(
        self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any
    ) -> Any: ...


class ResidualAvExecutionAuthority(Protocol):
    """Process-local native authority bound by the sole carrier composer."""

    def resolve_exact(
        self,
        action_id: str,
        context: Mapping[str, Any],
        value: Mapping[str, Any],
        *,
        phase: str,
    ) -> Mapping[str, Any]: ...
    def resolve_managed_artifact(self, input_path: str) -> Mapping[str, Any]: ...
    def invoke_admitted_handler(
        self,
        action_id: str,
        context: Mapping[str, Any],
        prepared: Mapping[str, Any],
        handler_input: Mapping[str, Any],
    ) -> Any: ...
    def recover(
        self,
        action_id: str,
        context: Mapping[str, Any],
        prepared: Mapping[str, Any],
        failure: BaseException,
    ) -> Mapping[str, Any]: ...


class _AudioInfoSemanticOwner:
    """Production file-inspection owner; no DaVinci Resolve mutation is involved."""

    def __init__(self, authority: ResidualAvExecutionAuthority):
        self.authority = authority

    def normalize_input(self, value):
        return {"inputPath": str(value["inputPath"])}

    def resolve_exact(self, context, value):
        artifact = self.authority.resolve_managed_artifact(value["inputPath"])
        required = {"stableId", "revision", "digest", "allowedRootId", "resolvedPath"}
        if not isinstance(artifact, Mapping) or not required <= set(artifact):
            raise ValidationError("Audio info managed-artifact authority is incomplete.")
        binding = {"role": "managed_input", **{key: artifact[key] for key in required}}
        return {
            "targets": [{
                "kind": "managed_artifact",
                "stableId": artifact["stableId"],
                "revision": artifact["revision"],
            }],
            "preState": {"digest": artifact["digest"], "revision": artifact["revision"]},
            "lowering": {"commandId": "audio.info", "args": [artifact["resolvedPath"]]},
            "artifactBindings": [binding],
            "protectedState": {},
        }

    def build_impact(self, _context, _value, authority):
        return {
            "contractVersion": 1,
            "status": "read",
            "complete": True,
            "targetDigests": [
                _mutation_policy_digest(_public_target_from_authority(target))
                for target in authority["targets"]
            ],
            "resultMaximumBytes": 64 * 1024,
        }

    def execute(self, _context, _value, prepared):
        from ..core import audio_ops

        binding = prepared["domain"]["artifactBindings"][0]
        return audio_ops.info(binding["resolvedPath"])

    def project_result(self, _context, prepared, result):
        binding = prepared["domain"]["artifactBindings"][0]
        if not isinstance(result, Mapping) or result.get("error"):
            raise ValidationError("Audio info returned no inspectable audio stream.")
        codec = result.get("codec")
        if not isinstance(codec, str) or not codec.strip():
            raise ValidationError("Audio info returned no valid codec name.")
        try:
            duration_seconds = float(result["duration"])
            sample_rate = int(result["sample_rate"])
            channel_count = int(result["channels"])
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValidationError("Audio info returned invalid stream fields.") from exc
        if not math.isfinite(duration_seconds) or duration_seconds < 0 \
                or sample_rate < 1 or channel_count < 1:
            raise ValidationError("Audio info returned invalid stream fields.")
        return {
            "actionId": "cutagent.action.audio.info",
            "data": {
                "inputPath": (
                    f"cutagent-artifact:{binding['stableId']}@{binding['revision']}"
                ),
                "durationSeconds": duration_seconds,
                "sampleRate": sample_rate,
                "channelCount": channel_count,
                "codec": codec,
            },
        }

    def read_evidence(self, context, prepared, result):
        projected = self.project_result(context, prepared, result)
        value = prepared.get("lowering", {}).get("normalizedInput")
        prepared_bindings = prepared.get("domain", {}).get("artifactBindings")
        if not isinstance(value, Mapping) or not isinstance(prepared_bindings, list) \
                or len(prepared_bindings) != 1:
            raise ValidationError("Audio info prepared artifact custody is incomplete.")
        current = self.resolve_exact(context, value)
        current_bindings = current.get("artifactBindings")
        if not isinstance(current_bindings, list) or len(current_bindings) != 1 \
                or current_bindings[0] != prepared_bindings[0]:
            raise ValidationError("Audio info artifact changed during inspection.")
        from ..core import audio_ops

        independent = audio_ops.info(prepared_bindings[0]["resolvedPath"])
        independently_projected = self.project_result(context, prepared, independent)
        if independently_projected != projected:
            raise ValidationError("Audio info result did not match an independent second read.")
        projection_digest = _mutation_policy_digest(projected)
        artifact_digest = prepared_bindings[0]["digest"]
        return {
            "outcome": "passed",
            "evidence": [
                {
                    "modality": "readback",
                    "digest": projection_digest,
                    "summary": "Audio stream fields were read back from the managed artifact.",
                },
                {
                    "modality": "structural",
                    "digest": projection_digest,
                    "summary": "Audio stream structure satisfies the typed action result.",
                },
                {
                    "modality": "file",
                    "digest": artifact_digest,
                    "summary": "Post-read artifact custody matches the prepared digest and revision.",
                },
            ],
            "protectedStatePreserved": True,
        }

    def recover(self, _context, _prepared, _failure):
        return {"outcome": "not_needed", "attempted": False, "manualActionRequired": False}


_CLIP_READ_RESULT_FIELDS = MappingProxyType({
    "cutagent.action.clip.fusion.list": "compositions",
    "cutagent.action.clip.linked.list": "links",
    "cutagent.action.clip.offset": "offsets",
    "cutagent.action.clip.source_range": "range",
    "cutagent.action.clip.take.list": "takeStack",
    "cutagent.action.clip.track_info": "trackBinding",
})

_CLIP_CHANGE_KINDS = MappingProxyType({
    "cutagent.action.clip.audio_eq": "audio_eq",
    "cutagent.action.clip.audio_gain": "audio_gain",
    "cutagent.action.clip.audio_normalize": "audio_normalize",
    "cutagent.action.clip.audio_pan": "audio_pan",
    "cutagent.action.clip.audio_pitch": "audio_pitch",
    "cutagent.action.clip.burnin.load": "burnin_preset",
    "cutagent.action.clip.cache": "cache",
    "cutagent.action.clip.cache_set": "cache",
    "cutagent.action.clip.color": "color",
    "cutagent.action.clip.composite": "composite",
    "cutagent.action.clip.disable": "enabled",
    "cutagent.action.clip.dynamic_zoom": "dynamic_zoom",
    "cutagent.action.clip.enable": "enabled",
    "cutagent.action.clip.fade_in": "fade",
    "cutagent.action.clip.flag": "flags",
    "cutagent.action.clip.fusion.add": "fusion_compositions",
    "cutagent.action.clip.fusion.delete": "fusion_compositions",
    "cutagent.action.clip.fusion.import": "fusion_compositions",
    "cutagent.action.clip.fusion.load": "fusion_compositions",
    "cutagent.action.clip.fusion.tool_set": "fusion_tool_input",
    "cutagent.action.clip.link": "links",
    "cutagent.action.clip.marker.add": "markers",
    "cutagent.action.clip.marker.custom_data": "markers",
    "cutagent.action.clip.marker.delete": "markers",
    "cutagent.action.clip.marker.delete_custom": "markers",
    "cutagent.action.clip.properties": "properties",
    "cutagent.action.clip.rename": "name",
    "cutagent.action.clip.reset_node_colors": "node_colors",
    "cutagent.action.clip.take.add": "takes",
    "cutagent.action.clip.take.delete": "takes",
    "cutagent.action.clip.take.finalize": "takes",
    "cutagent.action.clip.take.select": "takes",
    "cutagent.action.clip.unlink": "links",
    "cutagent.action.clip.voice_isolation": "voice_isolation",
})

_SPECIAL_CLIP_CHANGES = frozenset({
    "cutagent.action.clip.fusion.export",
    "cutagent.action.clip.update_sidecar",
})


def _require_carrier_binding(
    descriptor: ResidualAvActionDescriptor,
    context: Mapping[str, Any],
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    binding = context.get("exactRequestBinding")
    execution = context.get("execution")
    if not isinstance(binding, Mapping) or not isinstance(execution, Mapping):
        raise ValidationError("Residual action lacks its immutable carrier request binding.")
    correlations = ("requestId", "operationId", "executionId", "idempotencyKey")
    if binding.get("actionId") != descriptor.action_id \
            or binding.get("actionContractVersion") != 1 \
            or _canonical(binding.get("input")) != _canonical(value) \
            or any(binding.get(key) != execution.get(key) for key in correlations) \
            or context.get("actionId", descriptor.action_id) != descriptor.action_id \
            or any(context.get(key, execution.get(key)) != execution.get(key)
                   for key in ("operationId", "executionId")) \
            or not isinstance(binding.get("identities"), Mapping) \
            or not isinstance(binding.get("revisions"), Mapping):
        raise ValidationError("Residual action drifted from its carrier request binding.")
    if descriptor.operation_class == "mutation":
        mutation_base = context.get("mutationBase")
        identities = binding["identities"]
        revisions = binding["revisions"]
        exact_pairs = {
            "projectLibraryId": identities.get("projectLibraryId"),
            "projectId": identities.get("projectId"),
            "timelineId": identities.get("timelineId"),
            "projectRevision": revisions.get("project"),
            "timelineRevision": revisions.get("timeline"),
        }
        if not isinstance(mutation_base, Mapping) \
                or any(mutation_base.get(key) != binding.get(key)
                       for key in ("requestId", "operationId", "executionId")) \
                or any(key in mutation_base and mutation_base.get(key) != expected
                       for key, expected in exact_pairs.items()):
            raise ValidationError("Residual mutation drifted from its carrier mutation base.")
    elif context.get("mutationBase") is not None:
        raise ValidationError("Residual read action cannot carry a mutation base.")
    return binding


class _HandlerSemanticOwner:
    """Action-specific semantic wrapper around one authoritative CLI handler."""

    def __init__(
        self,
        descriptor: ResidualAvActionDescriptor,
        authority: ResidualAvExecutionAuthority,
    ):
        self.descriptor = descriptor
        self.authority = authority

    def normalize_input(self, value):
        return value

    def _resolve(self, context, value, *, phase: str):
        snapshot = self.authority.resolve_exact(
            self.descriptor.action_id,
            context,
            deepcopy(value),
            phase=phase,
        )
        required = {
            "targets", "preState", "artifactBindings", "protectedState", "handlerInput"
        }
        if not isinstance(snapshot, Mapping) or set(snapshot) != required \
                or not isinstance(snapshot.get("handlerInput"), Mapping):
            raise ValidationError("Residual AV authority resolver returned an incomplete snapshot.")
        handler_input = _canonical(snapshot["handlerInput"])
        args = canonical_residual_av_handler_args(
            self.descriptor.action_id, handler_input
        )
        return {
            "targets": snapshot["targets"],
            "preState": snapshot["preState"],
            "lowering": {
                "commandId": self.descriptor.command_id,
                "args": args,
                "canonicalRequestDigest": _mutation_policy_digest({
                    "commandId": self.descriptor.command_id,
                    "args": args,
                }),
                "handlerInput": handler_input,
            },
            "artifactBindings": snapshot["artifactBindings"],
            "protectedState": snapshot["protectedState"],
        }

    def resolve_exact(self, context, value):
        return self._resolve(context, value, phase="current")

    def build_impact(self, context, value, authority):
        return _build_handler_impact(self.descriptor, context, value, authority)

    def execute(self, context, value, prepared):
        if context.get("executionAuthority") is not self.authority:
            raise ValidationError(
                "Residual handler execution lacks carrier admission authority."
            )
        handler_input = prepared["domain"]["lowering"]["handlerInput"]
        raw = self.authority.invoke_admitted_handler(
            self.descriptor.action_id,
            context,
            prepared,
            _mutable_copy(handler_input),
        )
        after = _validate_authority(
            self.descriptor,
            value,
            self._resolve(context, value, phase="after"),
        )
        _validate_post_artifact_custody(
            self.descriptor,
            prepared["domain"]["artifactBindings"],
            after["artifactBindings"],
        )
        return {"raw": raw, "afterAuthority": after}

    def project_result(self, _context, prepared, result):
        return _project_handler_result(self.descriptor, prepared, result)

    def read_evidence(self, context, prepared, result):
        return _handler_evidence(self.descriptor, prepared, result)

    def recover(self, context, prepared, failure):
        if self.descriptor.operation_class == "read":
            return {
                "outcome": "not_needed",
                "attempted": False,
                "manualActionRequired": False,
            }
        if context.get("executionAuthority") is not self.authority:
            raise ValidationError(
                "Residual recovery lacks carrier admission authority."
            )
        recovery = self.authority.recover(
            self.descriptor.action_id, context, prepared, failure
        )
        if not isinstance(recovery, Mapping) or set(recovery) != {
            "outcome", "attempted", "manualActionRequired"
        }:
            raise ValidationError("Residual action recovery authority is incomplete.")
        if recovery.get("outcome") != "succeeded":
            return recovery
        value = prepared.get("lowering", {}).get("normalizedInput")
        if not isinstance(value, Mapping):
            raise ValidationError("Residual recovery input is unavailable.")
        recovered = _validate_authority(
            self.descriptor,
            value,
            self._resolve(context, value, phase="recovery"),
        )
        _validate_recovered_state(self.descriptor, prepared, recovered)
        return recovery


def _canonical(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if abs(value) > 9_007_199_254_740_991:
            raise ValidationError("Prepared action integer exceeds the canonical JSON range.")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValidationError("Prepared action numbers must be finite.")
        return 0 if value == 0 else value
    if isinstance(value, Mapping) and all(isinstance(key, str) for key in value):
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    raise ValidationError("Prepared action data must be canonical JSON.")


def _mutation_policy_digest(value: Any) -> str:
    encoded = json.dumps(
        _canonical(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


@lru_cache(maxsize=1)
def _contract_definitions() -> Mapping[str, Any]:
    path = Path(__file__).resolve().parents[1] / "public_contract" / "action-contracts.schema.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    definitions = document.get("$defs")
    if not isinstance(definitions, Mapping):
        raise RuntimeError("SDK action contract registry is unavailable.")
    return definitions


def _schema(action_id: str, kind: str) -> Mapping[str, Any] | bool:
    value = _contract_definitions().get(f"{action_id}.{kind}", False)
    if value is False or isinstance(value, Mapping):
        return value
    raise RuntimeError(f"SDK {kind} contract is malformed for {action_id}.")


def _validate_schema(value: Any, schema: Mapping[str, Any] | bool, path: str = "$") -> None:
    if schema is True:
        return
    if schema is False:
        raise ValidationError(f"The action contract is unavailable at {path}.")
    if "$ref" in schema:
        ref = schema["$ref"]
        prefix = "#/$defs/"
        if not isinstance(ref, str) or not ref.startswith(prefix):
            raise RuntimeError("Only local action-contract references are supported.")
        _validate_schema(value, _contract_definitions()[ref[len(prefix) :]], path)
        return
    for part in schema.get("allOf", ()):
        _validate_schema(value, part, path)
    if "not" in schema:
        try:
            _validate_schema(value, schema["not"], path)
        except ValidationError:
            pass
        else:
            raise ValidationError(f"Value matches a forbidden contract at {path}.")
    if "if" in schema:
        try:
            _validate_schema(value, schema["if"], path)
        except ValidationError:
            branch = schema.get("else")
        else:
            branch = schema.get("then")
        if branch is not None:
            _validate_schema(value, branch, path)
    if "oneOf" in schema:
        matches = 0
        for part in schema["oneOf"]:
            try:
                _validate_schema(value, part, path)
            except ValidationError:
                continue
            matches += 1
        if matches != 1:
            raise ValidationError(f"Value must match exactly one contract branch at {path}.")
        return
    if "anyOf" in schema:
        for part in schema["anyOf"]:
            try:
                _validate_schema(value, part, path)
                break
            except ValidationError:
                continue
        else:
            raise ValidationError(f"Value does not match any contract branch at {path}.")
        return
    if "const" in schema and value != schema["const"]:
        raise ValidationError(f"Value violates the constant contract at {path}.")
    if "enum" in schema and value not in schema["enum"]:
        raise ValidationError(f"Value is outside the contract enumeration at {path}.")
    expected = schema.get("type")
    expected_types = set(expected if isinstance(expected, list) else [expected]) if expected else set()
    valid_type = (
        not expected_types
        or ("null" in expected_types and value is None)
        or ("boolean" in expected_types and isinstance(value, bool))
        or ("integer" in expected_types and isinstance(value, int) and not isinstance(value, bool))
        or ("number" in expected_types and isinstance(value, (int, float)) and not isinstance(value, bool))
        or ("string" in expected_types and isinstance(value, str))
        or ("array" in expected_types and isinstance(value, list))
        or ("object" in expected_types and isinstance(value, Mapping))
    )
    if not valid_type:
        raise ValidationError(f"Value has the wrong type at {path}.")
    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)) or len(value) > int(schema.get("maxLength", 2**31)):
            raise ValidationError(f"String length is outside the contract at {path}.")
        if schema.get("pattern") and re.fullmatch(str(schema["pattern"]), value) is None:
            raise ValidationError(f"String format is invalid at {path}.")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            raise ValidationError(f"Number must be finite at {path}.")
        if "minimum" in schema and value < schema["minimum"]:
            raise ValidationError(f"Number is below the contract minimum at {path}.")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise ValidationError(f"Number is below the exclusive contract minimum at {path}.")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValidationError(f"Number exceeds the contract maximum at {path}.")
    if isinstance(value, list):
        if len(value) < int(schema.get("minItems", 0)) or len(value) > int(schema.get("maxItems", 2**31)):
            raise ValidationError(f"Array size is outside the contract at {path}.")
        if schema.get("uniqueItems"):
            encoded = [json.dumps(_canonical(item), separators=(",", ":"), sort_keys=True) for item in value]
            if len(set(encoded)) != len(encoded):
                raise ValidationError(f"Array contains duplicate items at {path}.")
        for index, item in enumerate(value):
            _validate_schema(item, schema.get("items", True), f"{path}[{index}]")
    if isinstance(value, Mapping):
        required = set(schema.get("required", ()))
        if not required <= set(value):
            raise ValidationError(f"Object is missing required fields at {path}.")
        properties = schema.get("properties", {})
        pattern_properties = schema.get("patternProperties", {})
        matched_patterns = {
            key: [
                child_schema
                for pattern, child_schema in pattern_properties.items()
                if re.fullmatch(str(pattern), str(key)) is not None
            ]
            for key in value
        }
        if schema.get("additionalProperties") is False and any(
            key not in properties and not matched_patterns[key]
            for key in value
        ):
            raise ValidationError(f"Object contains unreviewed fields at {path}.")
        if len(value) < int(schema.get("minProperties", 0)) \
                or len(value) > int(schema.get("maxProperties", 2**31)):
            raise ValidationError(f"Object size is outside the contract at {path}.")
        property_names = schema.get("propertyNames")
        if property_names is not None:
            for key in value:
                _validate_schema(key, property_names, f"{path}.<propertyName>")
        for key, child in value.items():
            if key in properties:
                _validate_schema(child, properties[key], f"{path}.{key}")
            for child_schema in matched_patterns[key]:
                _validate_schema(child, child_schema, f"{path}.{key}")


def _assert_public(value: Any) -> Any:
    normalized = _canonical(value)

    def visit(current: Any) -> None:
        if isinstance(current, Mapping):
            if _PRIVATE_KEYS.intersection(current):
                raise ValidationError("Private action metadata reached a public projection.")
            for child in current.values():
                visit(child)
        elif isinstance(current, list):
            for child in current:
                visit(child)

    visit(normalized)
    return normalized


def _validate_targets(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise ValidationError("Prepared action resolution requires exact stable targets.")
    targets = []
    identities = set()
    for target in value:
        if not isinstance(target, Mapping):
            raise ValidationError("Prepared stable targets must be objects.")
        stable_id = target.get("stableId")
        revision = target.get("revision")
        kind = target.get("kind")
        if not all(isinstance(item, str) and item for item in (stable_id, revision, kind)):
            raise ValidationError("Prepared targets require stable identity, kind and revision.")
        if stable_id in identities:
            raise ValidationError("Prepared stable targets must be unique.")
        identities.add(stable_id)
        targets.append(_canonical(target))
    return targets


def _validate_artifacts(descriptor: ResidualAvActionDescriptor, authority: Mapping[str, Any]) -> None:
    expected = set(descriptor.artifact_roles)
    artifacts = authority.get("artifactBindings", [])
    if not isinstance(artifacts, list):
        raise ValidationError("Prepared artifact bindings must be a list.")
    actual = {item.get("role") for item in artifacts if isinstance(item, Mapping)}
    if actual != expected or len(actual) != len(artifacts):
        raise ValidationError("Prepared artifacts do not match the action-specific roles.")
    for artifact in artifacts:
        if not isinstance(artifact.get("stableId"), str) or not isinstance(artifact.get("revision"), str):
            raise ValidationError("Prepared artifacts require stable identity and revision.")
        if artifact["role"].startswith("managed_input"):
            if _DIGEST.fullmatch(str(artifact.get("digest", ""))) is None \
                    or not isinstance(artifact.get("allowedRootId"), str) or not artifact["allowedRootId"]:
                raise ValidationError("Prepared inputs require managed-root custody and an exact digest.")
        elif artifact["role"] == "reserved_output":
            if not all(isinstance(artifact.get(key), str) and artifact[key]
                       for key in ("reservationId", "allowedRootId")) \
                    or _DIGEST.fullmatch(str(artifact.get("pathDigest", ""))) is None:
                raise ValidationError("Prepared outputs require exact reservation and allowed-root custody.")
        elif artifact["role"] == "derived_sidecar_output" and not all(
            isinstance(artifact.get(key), str) and artifact[key]
            for key in ("sourceArtifactId", "sourceRevision", "allowedRootId")
        ):
            raise ValidationError("Prepared sidecar output lacks source and allowed-root custody.")
        if "contentDigest" in artifact \
                and _DIGEST.fullmatch(str(artifact["contentDigest"])) is None:
            raise ValidationError("Artifact content digest is malformed.")
        if "byteCount" in artifact \
                and (not isinstance(artifact["byteCount"], int) or artifact["byteCount"] < 1):
            raise ValidationError("Artifact byte count is malformed.")


def _validate_post_artifact_custody(
    descriptor: ResidualAvActionDescriptor,
    before_value: Any,
    after_value: Any,
) -> None:
    before = {item["role"]: item for item in before_value}
    after = {item["role"]: item for item in after_value}
    if set(before) != set(after) or set(before) != set(descriptor.artifact_roles):
        raise ValidationError("Post-state artifact roles drifted from the prepared receipt.")
    for role, prepared in before.items():
        current = after[role]
        if current.get("stableId") != prepared.get("stableId"):
            raise ValidationError("Post-state artifact identity drifted from the prepared receipt.")
        if role.startswith("managed_input"):
            if current != prepared:
                raise ValidationError("Managed input changed after carrier admission.")
            continue
        custody_keys = (
            ("reservationId", "allowedRootId", "pathDigest")
            if role == "reserved_output"
            else ("sourceArtifactId", "sourceRevision", "allowedRootId")
        )
        if any(current.get(key) != prepared.get(key) for key in custody_keys):
            raise ValidationError("Post-state output custody drifted from its reservation.")
        if current.get("revision") == prepared.get("revision") \
                or _DIGEST.fullmatch(str(current.get("contentDigest", ""))) is None \
                or not isinstance(current.get("byteCount"), int) \
                or current["byteCount"] < 1:
            raise ValidationError(
                "Reserved output lacks a new revision, content digest, or byte readback."
            )


def _validate_authority(
    descriptor: ResidualAvActionDescriptor, input_value: Mapping[str, Any], value: Any
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError("The private exact authority resolver returned no authority.")
    required = {"targets", "preState", "lowering", "artifactBindings", "protectedState"}
    if set(value) != required or not isinstance(value["preState"], Mapping) \
            or not isinstance(value["lowering"], Mapping) or not value["lowering"] \
            or not isinstance(value["protectedState"], Mapping):
        raise ValidationError("The private exact authority resolution is incomplete.")
    result = {key: _canonical(value[key]) for key in required}
    result["targets"] = _validate_targets(value["targets"])
    _validate_artifacts(descriptor, result)
    if descriptor.operation_class == "mutation" \
            and not isinstance(result["preState"].get("semanticState"), Mapping):
        raise ValidationError(
            "Mutation authority omitted action-specific semantic state."
        )
    target_ids = {target["stableId"] for target in result["targets"]}
    artifact_ids = {artifact["stableId"] for artifact in result["artifactBindings"]}
    if not artifact_ids <= target_ids:
        raise ValidationError("Prepared artifacts are not receipt-bound stable targets.")
    kinds = [target["kind"] for target in result["targets"]]
    item_targets = [target for target in result["targets"] if target["kind"] == "timeline_item"]
    if descriptor.authority == "managed_artifact_revision" and set(kinds) != {"managed_artifact"}:
        raise ValidationError("File actions require only exact managed artifact targets.")
    if descriptor.authority == "exact_project_revision" and "project" not in kinds:
        raise ValidationError("Project action authority omitted the exact project target.")
    if descriptor.authority == "exact_project_timeline_revision" and "timeline" not in kinds:
        raise ValidationError("Timeline action authority omitted the exact timeline target.")
    if descriptor.action_id.startswith("cutagent.action.text.insert"):
        created_items = [
            target for target in item_targets
            if target.get("existence") in {"planned_absent", "existing"}
        ]
        expected_count = (
            len(input_value.get("items", ()))
            if descriptor.action_id == "cutagent.action.text.insert_template_batch"
            else 1
        )
        if len(created_items) != expected_count:
            raise ValidationError("Text insertion lacks exact planned timeline-item authority.")
    if descriptor.authority in {"exact_timeline_item_revision", "exact_timeline_item_set_revision"} \
            and len(item_targets) < (2 if descriptor.authority.endswith("set_revision") else 1):
        raise ValidationError("Timeline-item action authority omitted exact item targets.")
    if descriptor.authority == "exact_timeline_item_and_media_pool_revision" \
            and (not item_targets or "media_pool_item" not in kinds):
        raise ValidationError("Take insertion requires exact timeline-item and Media Pool targets.")
    if descriptor.authority == "managed_artifact_and_optional_exact_media_revision" \
            and (input_value.get("replaceMediaName") or input_value.get("replaceMedia")) \
            and "media_pool_item" not in kinds:
        raise ValidationError("Audio relinking requires an exact Media Pool target.")
    if descriptor.action_id == "cutagent.action.clip.fade_in":
        scope = str(input_value.get("scope", "linked")).strip().lower()
        required_tracks = {"video", "audio"} if scope == "linked" else {scope}
        if scope not in {"linked", "video", "audio"} \
                or {target.get("trackType") for target in item_targets} != required_tracks:
            raise ValidationError("Clip fade authority does not close over its exact scope.")
    marker_actions = {
        "cutagent.action.clip.marker.add",
        "cutagent.action.clip.marker.custom_data",
        "cutagent.action.clip.marker.delete",
        "cutagent.action.clip.marker.delete_custom",
    }
    if descriptor.action_id in marker_actions:
        markers = [target for target in result["targets"] if target["kind"] == "marker"]
        allowed_existence = {"planned_absent", "existing"} \
            if descriptor.action_id.endswith("marker.add") else {"existing", "deleted"} \
            if descriptor.action_id in {"cutagent.action.clip.marker.delete", "cutagent.action.clip.marker.delete_custom"} else {"existing"}
        if len(markers) != 1 or markers[0].get("existence") not in allowed_existence:
            raise ValidationError("Clip marker action lacks its exact marker authority.")
    fusion_existing = {
        "cutagent.action.clip.fusion.delete",
        "cutagent.action.clip.fusion.export",
        "cutagent.action.clip.fusion.load",
        "cutagent.action.clip.fusion.tool_set",
    }
    fusion_create = {
        "cutagent.action.clip.fusion.add",
        "cutagent.action.clip.fusion.import",
    }
    if descriptor.action_id in fusion_existing | fusion_create:
        compositions = [
            target for target in result["targets"] if target["kind"] == "fusion_composition"
        ]
        allowed_existence = {"planned_absent", "existing"} \
            if descriptor.action_id in fusion_create else {"existing", "deleted"} \
            if descriptor.action_id == "cutagent.action.clip.fusion.delete" else {"existing"}
        if len(compositions) != 1 or compositions[0].get("existence") not in allowed_existence:
            raise ValidationError("Fusion action lacks its exact composition authority.")
    for target in item_targets:
        required_item = (
            "projectId", "timelineId", "snapshotTimelineItemId", "trackType",
            "trackIndex", "linkedTimelineItemIds",
        )
        if not all(key in target for key in required_item) or target["trackType"] not in {"video", "audio"} \
                or not isinstance(target["trackIndex"], int) or target["trackIndex"] < 1 \
                or not isinstance(target["linkedTimelineItemIds"], list):
            raise ValidationError("Timeline-item target lacks exact snapshot, track or link identity.")
    protected = result["protectedState"]
    topology = protected.get("linkedAvTopology")
    if descriptor.topology_policy != "not_applicable" and (
        not isinstance(topology, Mapping)
        or set(topology) != {"snapshotDigest", "edges"}
        or _DIGEST.fullmatch(str(topology.get("snapshotDigest", ""))) is None
        or not isinstance(topology.get("edges"), list)
    ):
        raise ValidationError("Linked A/V topology was not captured before preparation.")
    unrelated_topology = protected.get("unrelatedLinkedAvTopology")
    if descriptor.topology_policy == "mutate_declared_edges_preserve_unrelated_topology" \
            and (
                not isinstance(unrelated_topology, Mapping)
                or set(unrelated_topology) != {"snapshotDigest", "edges"}
                or _DIGEST.fullmatch(str(unrelated_topology.get("snapshotDigest", ""))) is None
                or not isinstance(unrelated_topology.get("edges"), list)
            ):
        raise ValidationError("Unrelated link topology was not protected.")
    inspector = protected.get("unrelatedInspectorState")
    if descriptor.inspector_preservation != "not_applicable" \
            and (
                not isinstance(inspector, Mapping)
                or set(inspector) != {"digest", "snapshot"}
                or _DIGEST.fullmatch(str(inspector.get("digest", ""))) is None
                or not isinstance(inspector.get("snapshot"), Mapping)
                or not inspector["snapshot"]
            ):
        raise ValidationError("Unrelated Inspector state was not captured.")
    return result


def _public_target_from_authority(target: Mapping[str, Any]) -> dict[str, Any]:
    kind = target["kind"]
    result = {
        "kind": "clip" if kind == "timeline_item" else "media"
        if kind in {"managed_artifact", "media_pool_item"}
        else kind,
        "stableId": target["stableId"],
        "revision": target["revision"],
    }
    if kind == "timeline_item":
        result.update(trackType=target["trackType"], trackIndex=target["trackIndex"])
    return result


def _expected_effect_kind(action_id: str) -> str:
    if action_id in {
        "cutagent.action.clip.fusion.add",
        "cutagent.action.clip.fusion.import",
        "cutagent.action.clip.marker.add",
        "cutagent.action.text.insert",
        "cutagent.action.text.insert_preset",
        "cutagent.action.text.insert_template",
        "cutagent.action.text.insert_template_batch",
        "cutagent.action.edit.auto_subtitle",
        "cutagent.action.edit.camera_pip",
        "cutagent.action.edit.from_edl",
        "cutagent.action.edit.scene_detect",
    }:
        return "create"
    if action_id in {
        "cutagent.action.clip.fusion.delete",
        "cutagent.action.clip.marker.delete",
        "cutagent.action.clip.marker.delete_custom",
        "cutagent.action.clip.take.delete",
        "cutagent.action.edit.delete_through_edit",
        "cutagent.action.edit.remove",
        "cutagent.action.edit.remove_range",
        "cutagent.action.edit.ripple_delete",
        "cutagent.action.edit.ripple_delete_selected",
    }:
        return "delete"
    if action_id == "cutagent.action.edit.split":
        return "blade"
    return "update"


def _expected_track_types(
    descriptor: ResidualAvActionDescriptor,
    input_value: Mapping[str, Any],
    authority: Mapping[str, Any],
) -> list[str]:
    action_id = descriptor.action_id
    if descriptor.authority in {
        "managed_artifact_revision",
        "managed_artifact_and_optional_exact_media_revision",
        "exact_project_revision",
    } or action_id == "cutagent.action.burnin.load":
        return []
    if action_id.startswith("cutagent.action.text."):
        return ["video"]
    if action_id == "cutagent.action.clip.fade_in":
        scope = str(input_value.get("scope", "linked")).strip().lower()
        return ["video", "audio"] if scope == "linked" else [scope]
    if action_id.startswith("cutagent.action.clip.audio_") \
            or action_id == "cutagent.action.clip.voice_isolation":
        return ["audio"]
    if action_id.startswith("cutagent.action.clip.fusion.") or action_id in {
        "cutagent.action.clip.color",
        "cutagent.action.clip.composite",
        "cutagent.action.clip.dynamic_zoom",
        "cutagent.action.clip.reset_node_colors",
    }:
        return ["video"]
    order = {"video": 0, "audio": 1, "subtitle": 2}
    return sorted(
        {
            target["trackType"]
            for target in authority["targets"]
            if target["kind"] == "timeline_item"
        },
        key=order.__getitem__,
    )


def _expected_effects(
    descriptor: ResidualAvActionDescriptor,
    input_value: Mapping[str, Any],
    authority: Mapping[str, Any],
) -> list[dict[str, Any]]:
    artifacts = {item["stableId"]: item["role"] for item in authority["artifactBindings"]}
    public_targets = {
        item["stableId"]: _public_target_from_authority(item)
        for item in authority["targets"]
    }
    output_ids = [
        item["stableId"]
        for item in authority["artifactBindings"]
        if item["role"] in {"reserved_output", "derived_sidecar_output"}
    ]
    marker_ids = [
        target["stableId"] for target in authority["targets"] if target["kind"] == "marker"
    ]
    fusion_ids = [
        target["stableId"]
        for target in authority["targets"]
        if target["kind"] == "fusion_composition"
    ]
    dependency_only_actions = {
        "cutagent.action.burnin.preset.export",
        "cutagent.action.clip.fusion.export",
        "cutagent.action.clip.update_sidecar",
    }
    # The frozen carrier classifies these analysis-only commands as mutations.
    # They create no output artifact and mutate no native timeline state, so
    # their only exact receipt-bound targets are the managed inputs analyzed.
    frozen_analysis_mutations = {
        "cutagent.action.audio.beat_detect",
        "cutagent.action.audio.waveform_offset",
    }
    if descriptor.action_id.startswith("cutagent.action.text.insert"):
        mutated_ids = [
            target["stableId"]
            for target in authority["targets"]
            if target["kind"] == "timeline_item"
            and target.get("existence") == "planned_absent"
        ]
    elif descriptor.action_id == "cutagent.action.clip.take.add":
        mutated_ids = [
            target["stableId"]
            for target in authority["targets"]
            if target["kind"] == "timeline_item"
            and target.get("existence", "existing") == "existing"
        ]
    else:
        mutated_ids = [
        target["stableId"]
        for target in authority["targets"]
        if (
            target["stableId"] not in artifacts
            or descriptor.action_id in frozen_analysis_mutations
        )
        and target["kind"] not in {"marker", "fusion_composition"}
        and not marker_ids
        and not fusion_ids
        and descriptor.action_id not in dependency_only_actions
        ]
    result: list[dict[str, Any]] = []
    if output_ids:
        result.append({
            "kind": "create",
            "trackTypes": [],
            "placementIntent": "explicit",
            "targetIds": output_ids,
        })
    if marker_ids:
        result.append({
            "kind": _expected_effect_kind(descriptor.action_id),
            "trackTypes": _expected_track_types(descriptor, input_value, authority),
            "placementIntent": "marker",
            "targetIds": marker_ids,
        })
    if fusion_ids and descriptor.action_id != "cutagent.action.clip.fusion.export":
        result.append({
            "kind": _expected_effect_kind(descriptor.action_id),
            "trackTypes": ["video"],
            "placementIntent": "explicit",
            "targetIds": fusion_ids,
        })
    if mutated_ids:
        result.append({
            "kind": _expected_effect_kind(descriptor.action_id),
            "trackTypes": _expected_track_types(descriptor, input_value, authority),
            "placementIntent": "explicit",
            "targetIds": mutated_ids,
        })
    if not result:
        raise ValidationError("Mutation descriptor has no exact mutated or created targets.")
    for effect in result:
        effect["targets"] = [public_targets[target_id] for target_id in effect.pop("targetIds")]
    return result


def _expected_verification_modalities(
    descriptor: ResidualAvActionDescriptor,
) -> list[str]:
    result: list[str] = []
    for obligation in descriptor.verification:
        for modality in ("readback", "structural", "file", "rendered", "auditioned"):
            if modality in _MODALITY[obligation] and modality not in result:
                result.append(modality)
    return result


def _build_handler_impact(
    descriptor: ResidualAvActionDescriptor,
    context: Mapping[str, Any],
    input_value: Mapping[str, Any],
    authority: Mapping[str, Any],
) -> dict[str, Any]:
    if descriptor.operation_class == "read":
        return {
            "contractVersion": 1,
            "status": "read",
            "complete": True,
            "targetDigests": [
                _mutation_policy_digest(_public_target_from_authority(target))
                for target in authority["targets"]
            ],
            "resultMaximumBytes": 8_388_608,
        }
    minimum_binding = (
        "account/project-library"
        if descriptor.authority == "managed_artifact_revision"
        else "project"
        if descriptor.authority in {
            "exact_project_revision",
            "managed_artifact_and_optional_exact_media_revision",
        }
        else "project+timeline"
    )
    raw_mutation_base = context.get("mutationBase")
    if not isinstance(raw_mutation_base, Mapping):
        raise ValidationError("Residual mutation lacks the carrier-owned mutation base.")
    mutation_base = _canonical(raw_mutation_base)
    expected_base_keys = {
        "contractVersion", "carrier", "minimumBinding", "registryDigest",
        "canonicalRequestDigest", "referencedPayloadDigests", "requestId",
        "operationId", "executionId", "projectLibraryId",
    }
    optional_base_keys = {
        "projectId", "timelineId", "projectRevision", "timelineRevision",
    }
    if not expected_base_keys <= set(mutation_base) \
            or set(mutation_base) - expected_base_keys - optional_base_keys \
            or mutation_base.get("minimumBinding") != minimum_binding:
        raise ValidationError("Carrier mutation base does not match action authority.")
    effects = _expected_effects(descriptor, input_value, authority)
    result = {
        **dict(mutation_base),
        "complete": True,
        "status": "mutation",
        "closedComposition": True,
        "ambiguous": False,
        "broad": False,
        "executableStableTargetPrecondition": True,
        "effects": [
            {
                "operation": descriptor.command_id,
                "placementIntent": "explicit",
                "complete": True,
                "ambiguous": False,
                "broad": False,
                **effect,
            }
            for effect in effects
        ],
        "verificationPolicy": {
            "minimumEvidence": _expected_verification_modalities(descriptor),
            "requireProtectedStatePreserved": True,
            "protectedTargetEvidence": "every_declared_target",
        },
    }
    return result


def _opaque_artifact(binding: Mapping[str, Any]) -> str:
    return f"cutagent-artifact:{binding['stableId']}@{binding['revision']}"


def _after_authority(result: Any) -> Mapping[str, Any]:
    if not isinstance(result, Mapping) or set(result) != {"raw", "afterAuthority"} \
            or not isinstance(result.get("afterAuthority"), Mapping):
        raise ValidationError("Residual handler returned no authoritative post-state.")
    return result["afterAuthority"]


def _semantic_data(authority: Mapping[str, Any]) -> Mapping[str, Any]:
    value = authority.get("preState", {}).get("semanticData")
    if not isinstance(value, Mapping):
        raise ValidationError("Residual post-state omitted action-specific semantic data.")
    return value


def _public_verification(evidence: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    kind = {
        "readback": "structural_readback",
        "structural": "structural_readback",
        "file": "artifact_readback",
        "rendered": "rendered_frame",
        "visual": "visual_review",
        "auditioned": "audition",
    }
    return {
        "outcome": "passed",
        "evidence": [
            {
                "kind": kind[item["modality"]],
                "summary": item["summary"],
                "artifactId": None,
            }
            for item in evidence
        ],
        "protectedState": "preserved",
    }


def _project_handler_result(
    descriptor: ResidualAvActionDescriptor,
    prepared: Mapping[str, Any],
    result: Any,
) -> dict[str, Any]:
    after = _after_authority(result)
    action_id = descriptor.action_id
    if action_id.startswith("cutagent.action.edit."):
        from .edit_runtime_projection import project_edit_result

        verified = after.get("preState", {}).get("verifiedSemanticState")
        if not isinstance(verified, Mapping) or verified.get("kind") != "edit_snapshot_transition":
            raise ValidationError("Edit post-state lacks its independently verified snapshot transition.")
        proof = _handler_evidence(descriptor, prepared, result)
        kind = {
            "readback": "structural_readback", "structural": "structural_readback",
            "file": "artifact_readback", "rendered": "rendered_frame",
            "visual": "visual_review",
        }
        evidence = [
            {"kind": kind[item["modality"]], "summary": item["summary"]}
            for item in proof["evidence"] if item["modality"] in kind
        ]
        return project_edit_result(
            action_id,
            prepared["lowering"]["normalizedInput"],
            verified,
            evidence,
        )
    if action_id == "cutagent.action.audio.beat_detect":
        source = next(
            item for item in after["artifactBindings"]
            if item["role"] == "managed_input"
        )
        data = _semantic_data(after)
        confidence = data.get("confidence")
        beats = data.get("beats")
        beat_frames = (
            [beat.get("frame") for beat in beats]
            if isinstance(beats, list)
            and all(isinstance(beat, Mapping) for beat in beats)
            else None
        )
        if not isinstance(confidence, Mapping) \
                or confidence.get("band") not in {"low", "medium", "high"} \
                or not isinstance(confidence.get("score"), (int, float)) \
                or isinstance(confidence.get("score"), bool) \
                or not isinstance(beat_frames, list) \
                or any(not isinstance(frame, int) or isinstance(frame, bool)
                       for frame in beat_frames) \
                or not isinstance(data.get("downbeats"), list) \
                or any(not isinstance(frame, int) or isinstance(frame, bool)
                       for frame in data["downbeats"]) \
                or not isinstance(data.get("phrase_starts"), list) \
                or any(not isinstance(frame, int) or isinstance(frame, bool)
                       for frame in data["phrase_starts"]):
            raise ValidationError("Beat analysis returned malformed semantic readback.")
        return {
            "actionId": action_id,
            "data": {
                "inputPath": _opaque_artifact(source),
                "durationSeconds": data["duration_seconds"],
                "fps": data["fps"],
                "tempoBpm": data["tempo_bpm"],
                "confidenceBand": confidence["band"],
                "confidenceScore": confidence["score"],
                "beatFrames": beat_frames,
                "downbeatFrames": data["downbeats"],
                "phraseStartFrames": data["phrase_starts"],
                "warnings": data.get("warnings", []),
            },
        }
    if action_id == "cutagent.action.audio.waveform_offset":
        bindings = after["artifactBindings"]
        reference = next(
            item for item in bindings if item["role"] == "managed_input_reference"
        )
        target = next(
            item for item in bindings if item["role"] == "managed_input_target"
        )
        data = _semantic_data(after)
        return {
            "actionId": action_id,
            "data": {
                "referencePath": _opaque_artifact(reference),
                "targetPath": _opaque_artifact(target),
                "fps": data["fps"],
                "offsetSeconds": data["offset_seconds"],
                "offsetFrames": data["offset_frames"],
                "driftFrames": data["drift_frames"],
                "confidence": data["confidence"],
                "warnings": data.get("warnings", []),
            },
        }
    if action_id.startswith("cutagent.action.clip.marker.") or action_id in {
        "cutagent.action.clip.fusion.add", "cutagent.action.clip.fusion.delete",
        "cutagent.action.clip.fusion.import",
    }:
        before_state = prepared.get("domain", {}).get("preState", {}).get("actionState")
        after_state = after.get("preState", {}).get("actionState")
        before_revision = prepared.get("domain", {}).get("preState", {}).get("semanticState", {}).get("snapshotRevision")
        after_revision = after.get("preState", {}).get("semanticState", {}).get("snapshotRevision")
        if action_id.startswith("cutagent.action.clip.fusion."):
            before_revision = (
                before_state.get("collectionRevision")
                if isinstance(before_state, Mapping)
                else None
            )
            after_revision = (
                after_state.get("collectionRevision")
                if isinstance(after_state, Mapping)
                else None
            )
        public_targets = after.get("preState", {}).get("publicTargets")
        if not isinstance(before_state, Mapping) or not isinstance(after_state, Mapping) \
                or not isinstance(before_revision, str) or not isinstance(after_revision, str) \
                or before_revision == after_revision or not isinstance(public_targets, list) \
                or not public_targets:
            raise ValidationError("Clip mutation post-state omitted fresh before/after public projection custody.")
        if action_id.startswith("cutagent.action.clip.marker."):
            before_change = {"markers": deepcopy(before_state.get("markers"))}
            after_change = {"markers": deepcopy(after_state.get("markers"))}
            if not isinstance(before_change["markers"], list) or not isinstance(after_change["markers"], list):
                raise ValidationError("Clip marker projection omitted exact before/after marker state.")
            change = {"kind": "markers", "before": before_change, "after": after_change}
        else:
            before_references = before_state.get("references")
            after_references = after_state.get("references")
            if not isinstance(before_references, list) or not isinstance(after_references, list):
                raise ValidationError("Fusion projection omitted exact before/after composition state.")
            public_before = [{"index": item["index"], "name": item["name"]} for item in before_references]
            public_after = [{"index": item["index"], "name": item["name"]} for item in after_references]
            active = None
            if action_id in {"cutagent.action.clip.fusion.add", "cutagent.action.clip.fusion.import"}:
                create_mode = after_state.get("createMode", "append")
                if create_mode == "replace_single_blank_holder":
                    if before_state.get("createMode") != create_mode:
                        raise ValidationError("Fusion holder replacement projection mode changed during execution.")
                    if len(before_references) != 1 or len(after_references) != 1:
                        raise ValidationError("Fusion holder replacement projection is incomplete.")
                    active = {"index": after_references[0]["index"], "name": after_references[0]["name"]}
                else:
                    before_ids = {item["id"] for item in before_references}
                    created = [item for item in after_references if item["id"] not in before_ids]
                    if len(created) != 1:
                        raise ValidationError("Fusion create projection lacks one exact new composition.")
                    active = {"index": created[0]["index"], "name": created[0]["name"]}
            change = {
                "kind": "fusion_compositions",
                "before": {"compositions": public_before, "activeComposition": None},
                "after": {"compositions": public_after, "activeComposition": active},
            }
        proof = _handler_evidence(descriptor, prepared, result)
        return {
            "actionId": action_id,
            "payload": {
                "status": "completed", "changed": True,
                "revision": {"relationship": "advanced", "before": before_revision, "after": after_revision},
                "targets": deepcopy(public_targets), "change": change,
                "verification": _public_verification(proof["evidence"]),
                "recovery": {
                    "state": "not_needed", "retry": "inspect_state_first",
                    "guidance": "The requested mutation and fresh post-state readback completed.",
                },
            },
        }
    if action_id in _CLIP_READ_RESULT_FIELDS:
        field = _CLIP_READ_RESULT_FIELDS[action_id]
        data = _semantic_data(after)
        return {"actionId": action_id, field: data[field]}
    if action_id == "cutagent.action.clip.fusion.export":
        before_pre_state = prepared.get("domain", {}).get("preState", {})
        after_pre_state = after.get("preState", {})
        before_outputs = [
            item for item in prepared.get("domain", {}).get("artifactBindings", ())
            if item.get("role") == "reserved_output"
        ]
        after_outputs = [
            item for item in after.get("artifactBindings", ())
            if item.get("role") == "reserved_output"
        ]
        before_semantic = before_pre_state.get("semanticState", {})
        after_semantic = after_pre_state.get("semanticState", {})
        before_references = before_pre_state.get("actionState", {}).get("references")
        references = after_pre_state.get("actionState", {}).get("references")
        public_targets = after_pre_state.get("publicTargets")
        requested_index = prepared.get("lowering", {}).get("normalizedInput", {}).get("index")
        compositions = [
            item for item in references or ()
            if isinstance(item, Mapping) and item.get("index") == requested_index
        ]
        if len(before_outputs) != 1 or len(after_outputs) != 1 \
                or before_outputs[0].get("stableId") != after_outputs[0].get("stableId") \
                or not isinstance(after_outputs[0].get("byteCount"), int) \
                or after_outputs[0]["byteCount"] < 1 \
                or _DIGEST.fullmatch(str(after_outputs[0].get("contentDigest", ""))) is None \
                or before_semantic.get("snapshotDigest") != after_semantic.get("snapshotDigest") \
                or before_semantic.get("snapshotRevision") != after_semantic.get("snapshotRevision") \
                or _canonical(before_references) != _canonical(references) \
                or len(compositions) != 1 or not isinstance(public_targets, list) \
                or not public_targets:
            raise ValidationError(
                "Fusion export post-state lacks exact composition and reserved-output custody."
            )
        before_output, after_output = before_outputs[0], after_outputs[0]
        proof = _handler_evidence(descriptor, prepared, result)
        artifact_id = after_output["stableId"]
        return {
            "actionId": action_id,
            "payload": {
                "status": "completed",
                "changed": True,
                "revision": {
                    "relationship": "advanced",
                    "before": before_output["revision"],
                    "after": after_output["revision"],
                },
                "targets": deepcopy(public_targets),
                "change": {
                    "kind": "fusion_export",
                    "composition": {
                        "index": compositions[0]["index"],
                        "name": compositions[0]["name"],
                    },
                    "before": {
                        "artifactId": artifact_id,
                        "kind": "fusion_setting",
                        "exists": False,
                        "byteCount": 0,
                        "sha256": "0" * 64,
                    },
                    "after": {
                        "artifactId": artifact_id,
                        "kind": "fusion_setting",
                        "exists": True,
                        "byteCount": after_output["byteCount"],
                        "sha256": after_output["contentDigest"].removeprefix("sha256:"),
                    },
                    "timelineChanged": False,
                },
                "verification": _public_verification(proof["evidence"]),
                "recovery": {
                    "state": "not_needed",
                    "retry": "inspect_state_first",
                    "guidance": "The Fusion setting artifact and exact composition were read back independently.",
                },
            },
        }
    if action_id == "cutagent.action.clip.audio_gain":
        before_revision = prepared.get("domain", {}).get("preState", {}).get(
            "semanticState", {}
        ).get("snapshotRevision")
        after_state = after.get("preState", {})
        after_revision = after_state.get("semanticState", {}).get("snapshotRevision")
        public_targets = after_state.get("publicTargets")
        data = _semantic_data(after)
        verification = data.get("verification")
        checks = verification.get("checks") if isinstance(verification, Mapping) else None
        exact_check = next(
            (
                check for check in checks or ()
                if isinstance(check, Mapping)
                and check.get("name") == "exact_audio_gain_db"
            ),
            None,
        )
        before_gain = data.get("existing_gain_db")
        after_gain = data.get("resulting_gain_db")
        actual_gain = (
            verification.get("actual_gain_db")
            if isinstance(verification, Mapping)
            else None
        )
        if (
            not isinstance(before_revision, str)
            or not isinstance(after_revision, str)
            or not isinstance(public_targets, list)
            or not public_targets
            or isinstance(before_gain, bool)
            or not isinstance(before_gain, (int, float))
            or isinstance(after_gain, bool)
            or not isinstance(after_gain, (int, float))
            or isinstance(actual_gain, bool)
            or not isinstance(actual_gain, (int, float))
            or not math.isfinite(float(before_gain))
            or not math.isfinite(float(after_gain))
            or not math.isfinite(float(actual_gain))
            or not math.isclose(
                float(after_gain), float(actual_gain), rel_tol=0.0, abs_tol=1e-9
            )
            or not isinstance(exact_check, Mapping)
            or exact_check.get("ok") is not True
            or verification.get("status") != "verified"
        ):
            raise ValidationError(
                "Clip audio gain post-state lacks exact native before/after readback."
            )
        changed = not math.isclose(
            float(before_gain), float(after_gain), rel_tol=0.0, abs_tol=1e-9
        )
        if changed != (before_revision != after_revision):
            raise ValidationError(
                "Clip audio gain revision relationship does not match native readback."
            )
        proof = _handler_evidence(descriptor, prepared, result)
        state = lambda value: {
            "kind": "audio_gain",
            "values": [{"name": "gainDb", "value": float(value)}],
        }
        return {
            "actionId": action_id,
            "payload": {
                "status": "completed" if changed else "no_change",
                "changed": changed,
                "revision": {
                    "relationship": "advanced" if changed else "unchanged",
                    **(
                        {"before": before_revision, "after": after_revision}
                        if changed
                        else {"current": after_revision}
                    ),
                },
                "targets": deepcopy(public_targets),
                "change": {
                    "kind": "audio_gain",
                    "before": state(before_gain),
                    "after": state(after_gain),
                },
                "verification": _public_verification(proof["evidence"]),
                "recovery": {
                    "state": "not_needed",
                    "retry": "inspect_state_first",
                    "guidance": "The exact clip gain was read back after the mutation.",
                },
            },
        }
    if action_id in {"cutagent.action.clip.audio_normalize", "cutagent.action.clip.audio_pan", "cutagent.action.clip.audio_pitch", "cutagent.action.clip.fade_in"}:
        data = _semantic_data(after)
        if "native_before" in data or "native_items" in data:
            from .native_clip_audio_result import project_native_audio

            proof = _handler_evidence(descriptor, prepared, result)
            return project_native_audio(action_id, prepared, after, data, _public_verification(proof["evidence"]))
    if action_id.startswith("cutagent.action.clip."):
        projected = after.get("preState", {}).get("publicResult")
        if not isinstance(projected, Mapping) or projected.get("actionId") != action_id:
            raise ValidationError(
                "Clip post-state omitted its exact action-specific public result."
            )
        return dict(projected)
    if action_id == "cutagent.action.audio.duck":
        bindings = prepared["domain"]["artifactBindings"]
        after_bindings = after["artifactBindings"]
        source = next(item for item in bindings if item["role"] == "managed_input")
        output = next(
            item for item in after_bindings if item["role"] == "reserved_output"
        )
        value = prepared["lowering"]["normalizedInput"]
        semantic = _semantic_data(after)
        observed_relink = semantic.get("relinked_media")
        requested_relink = value.get("replaceMediaName")
        if requested_relink is not None:
            if not isinstance(observed_relink, Mapping) \
                    or observed_relink.get("clip") != requested_relink \
                    or not isinstance(observed_relink.get("path"), str) \
                    or not observed_relink["path"]:
                raise ValidationError(
                    "Audio duck post-state did not confirm the requested Media Pool relink."
                )
            relinked_media = observed_relink["clip"]
        else:
            if observed_relink is not None:
                raise ValidationError(
                    "Audio duck reported an unrequested Media Pool relink."
                )
            relinked_media = None
        return {
            "actionId": action_id,
            "data": {
                "inputPath": _opaque_artifact(source),
                "outputPath": _opaque_artifact(output),
                "speechTrackIndex": value["speechTrackIndex"],
                "musicTrackIndex": value["musicTrackIndex"],
                "thresholdDb": value.get("thresholdDb", -20.0),
                "ratio": value.get("ratio", 8.0),
                "relinkedMedia": relinked_media,
            },
        }
    if action_id == "cutagent.action.audio.reverb":
        bindings = prepared["domain"]["artifactBindings"]
        after_bindings = after["artifactBindings"]
        source = next(item for item in bindings if item["role"] == "managed_input")
        output = next(
            item for item in after_bindings if item["role"] == "reserved_output"
        )
        return {
            "actionId": action_id,
            "data": {
                "inputPath": _opaque_artifact(source),
                "outputPath": _opaque_artifact(output),
                "durationSeconds": _semantic_data(after)["durationSeconds"],
            },
        }
    if action_id == "cutagent.action.audio.probe_subframe":
        raw = result["raw"]
        if not isinstance(raw, Mapping):
            raise ValidationError("Sub-frame probe returned no typed verdict.")
        return {
            "actionId": action_id,
            "data": {
                "resolveVersion": raw["resolve_version"],
                "supportsAudioSubframeAppend": raw["supports_audio_subframe_append"],
                "verifiedRender": raw["verified_render"],
                "metadataStartFrames": raw.get("metadata_start_frames"),
                "renderErrorMs": raw.get("render_error_ms"),
                "warnings": raw.get("warnings", []),
            },
        }
    if action_id == "cutagent.action.burnin.load":
        data = _semantic_data(after)
        if data.get("loaded") is not True or not isinstance(data.get("name"), str) or not data["name"]:
            raise ValidationError("Burn-in load returned no exact successful preset identity.")
        return {"actionId": action_id, "data": {"presetName": data["name"], "loaded": True}}
    if action_id == "cutagent.action.burnin.preset.export":
        data = _semantic_data(after)
        outputs = [item for item in after["artifactBindings"] if item["role"] == "reserved_output"]
        if data.get("exported") is not True or not isinstance(data.get("name"), str) or not data["name"] \
                or len(outputs) != 1 or not isinstance(outputs[0].get("byteCount"), int):
            raise ValidationError("Burn-in export returned no exact artifact result.")
        return {"actionId": action_id, "data": {
            "presetName": data["name"], "outputPath": _opaque_artifact(outputs[0]),
            "byteCount": outputs[0]["byteCount"],
        }}
    if action_id == "cutagent.action.burnin.preset.import":
        data = _semantic_data(after)
        inputs = [item for item in after["artifactBindings"] if item["role"].startswith("managed_input")]
        if data.get("imported") is not True or not isinstance(data.get("name"), str) or not data["name"] \
                or len(inputs) != 1:
            raise ValidationError("Burn-in import returned no exact managed preset identity.")
        return {"actionId": action_id, "data": {
            "inputPath": _opaque_artifact(inputs[0]), "presetName": data["name"], "imported": True,
        }}
    if action_id.startswith("cutagent.action.text."):
        return {"actionId": action_id, "data": dict(_semantic_data(after))}
    raise ValidationError("Residual action lacks an action-specific result projector.")


def _protected_state_preserved(
    descriptor: ResidualAvActionDescriptor,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> bool:
    keys = set(before) | set(after)
    if descriptor.topology_policy == "mutate_declared_edges_preserve_unrelated_topology":
        keys.discard("linkedAvTopology")
    return all(before.get(key) == after.get(key) for key in keys)


def _handler_evidence(
    descriptor: ResidualAvActionDescriptor,
    prepared: Mapping[str, Any],
    result: Any,
) -> dict[str, Any]:
    after = _after_authority(result)
    independent_state = {
        "actionId": descriptor.action_id,
        "targets": after["targets"],
        "artifacts": after["artifactBindings"],
        "semanticState": after["preState"].get("semanticState"),
        "verifiedSemanticState": after["preState"].get("verifiedSemanticState"),
        "actionState": after["preState"].get("actionState"),
    }
    projection_digest = _mutation_policy_digest(independent_state)
    supplied = after["preState"].get("independentEvidence", {})
    if not isinstance(supplied, Mapping):
        raise ValidationError("Residual post-state evidence is malformed.")
    evidence = []
    for modality in _expected_verification_modalities(descriptor):
        if modality in {"readback", "structural"}:
            evidence.append({
                "modality": modality,
                "digest": projection_digest,
                "summary": "Fresh exact-target authority was read independently after execution.",
            })
            continue
        if modality == "file":
            bindings = after["artifactBindings"]
            output_bindings = [
                item for item in bindings
                if item["role"] in {"reserved_output", "derived_sidecar_output"}
            ]
            source_bindings = [
                item for item in bindings if item["role"].startswith("managed_input")
            ]
            proof_bindings = output_bindings or source_bindings
            if not proof_bindings:
                raise ValidationError("Artifact readback has no receipt-bound artifact.")
            digests = [
                item.get("contentDigest", item.get("digest"))
                for item in proof_bindings
            ]
            if any(_DIGEST.fullmatch(str(digest)) is None for digest in digests):
                raise ValidationError("Artifact readback lacks a receipt-bound content digest.")
            evidence.append({
                "modality": "file",
                "digest": digests[0]
                if len(digests) == 1 else _mutation_policy_digest(digests),
                "summary": "Receipt-bound artifact content and byte custody were read back.",
            })
            continue
        item = supplied.get(modality)
        if not isinstance(item, Mapping) or set(item) != {"digest", "summary"} \
                or _DIGEST.fullmatch(str(item.get("digest", ""))) is None \
                or not isinstance(item.get("summary"), str):
            raise ValidationError(
                f"Residual action lacks independent {modality} evidence."
            )
        evidence.append({"modality": modality, **item})
    protected = _protected_state_preserved(
        descriptor,
        prepared["domain"]["protectedState"],
        after["protectedState"],
    )
    if not protected:
        raise ValidationError("Residual action changed protected topology or Inspector state.")
    return {
        "outcome": "passed",
        "evidence": evidence,
        "protectedStatePreserved": True,
    }


def _validate_recovered_state(
    descriptor: ResidualAvActionDescriptor,
    prepared: Mapping[str, Any],
    recovered: Mapping[str, Any],
) -> None:
    before = prepared["domain"]
    def recovery_identity(target: Mapping[str, Any]) -> str:
        if not isinstance(target, Mapping):
            raise ValidationError("Recovery returned a malformed target.")
        return json.dumps(
            _canonical({key: value for key, value in target.items() if key != "revision"}),
            separators=(",", ":"),
            sort_keys=True,
        )

    before_targets = {recovery_identity(target) for target in before["targets"]}
    recovered_targets = {recovery_identity(target) for target in recovered["targets"]}
    if recovered_targets != before_targets:
        raise ValidationError("Recovery did not restore every authoritative target field.")
    for target in recovered["targets"]:
        revision = target.get("revision")
        if not isinstance(revision, str) or _STATE_REVISION.fullmatch(revision) is None:
            raise ValidationError("Recovery target revision transition is not authoritative.")
    if recovered["protectedState"] != before["protectedState"]:
        raise ValidationError("Recovery did not restore protected state.")
    if recovered["preState"].get("semanticState") \
            != before["preState"].get("semanticState"):
        raise ValidationError("Recovery did not restore the action-specific semantic state.")
    if recovered["artifactBindings"] != before["artifactBindings"]:
        raise ValidationError("Recovery did not reconcile prepared artifact custody.")


def _validate_impact(
    descriptor: ResidualAvActionDescriptor,
    context: Mapping[str, Any],
    authority: Mapping[str, Any],
    input_value: Mapping[str, Any],
    value: Any,
) -> dict[str, Any]:
    impact = _assert_public(value)
    if not isinstance(impact, dict) or impact.get("complete") is not True:
        raise ValidationError("Prepared action impact is incomplete.")
    if descriptor.operation_class == "read":
        expected = {"contractVersion", "status", "complete", "targetDigests", "resultMaximumBytes"}
        target_digests = [
            _mutation_policy_digest(_public_target_from_authority(target))
            for target in authority["targets"]
        ]
        if set(impact) != expected or impact.get("contractVersion") != 1 or impact.get("status") != "read" \
                or not isinstance(impact.get("targetDigests"), list) \
                or len(impact["targetDigests"]) > 10_000 \
                or any(_DIGEST.fullmatch(str(item)) is None for item in impact["targetDigests"]) \
                or impact["targetDigests"] != target_digests \
                or not isinstance(impact.get("resultMaximumBytes"), int) \
                or not (1 <= impact["resultMaximumBytes"] <= 8_388_608):
            raise ValidationError("Prepared read impact does not match the signed carrier contract.")
    else:
        required = {
            "contractVersion", "carrier", "status", "minimumBinding", "registryDigest",
            "canonicalRequestDigest", "referencedPayloadDigests", "requestId", "operationId",
            "executionId", "projectLibraryId", "effects",
            "closedComposition", "complete", "ambiguous", "broad",
            "executableStableTargetPrecondition", "verificationPolicy",
        }
        optional = {"projectId", "timelineId", "projectRevision", "timelineRevision"}
        effects = impact.get("effects")
        raw_mutation_base = context.get("mutationBase")
        mutation_base = _canonical(raw_mutation_base) \
            if isinstance(raw_mutation_base, Mapping) else None
        lowering = authority.get("lowering")
        if not isinstance(mutation_base, Mapping) or not isinstance(lowering, Mapping):
            raise ValidationError("Prepared mutation context lacks exact carrier bindings.")
        lowering_args = lowering.get("args")
        expected_request_digest = _mutation_policy_digest(
            {"commandId": descriptor.command_id, "args": lowering_args}
        ) if isinstance(lowering_args, list) and all(
            isinstance(item, str) for item in lowering_args
        ) else None
        if lowering.get("commandId") != descriptor.command_id \
                or lowering.get("canonicalRequestDigest") != expected_request_digest:
            raise ValidationError("Private lowering is not bound to its owned action request.")
        if not required <= set(impact) or set(impact) - required - optional \
                or impact.get("contractVersion") != 1 \
                or impact.get("carrier") not in {"sdk", "desktop", "plugin", "cli", "batch", "composition"} \
                or impact.get("minimumBinding") not in {"account/project-library", "project", "project+timeline"} \
                or any(_DIGEST.fullmatch(str(impact.get(key, ""))) is None
                       for key in ("registryDigest", "canonicalRequestDigest")) \
                or not isinstance(impact.get("referencedPayloadDigests"), list) \
                or len(impact["referencedPayloadDigests"]) > 1_000 \
                or any(_DIGEST.fullmatch(str(item)) is None for item in impact["referencedPayloadDigests"]) \
                or any(_OPAQUE_ID[key].fullmatch(str(impact.get(key, ""))) is None
                       for key in ("requestId", "operationId", "executionId")) \
                or _STABLE_TARGET_ID.fullmatch(str(impact.get("projectLibraryId", ""))) is None \
                or impact.get("status") != "mutation" or impact.get("ambiguous") is not False \
                or impact.get("broad") is not False or impact.get("closedComposition") is not True \
                or impact.get("executableStableTargetPrecondition") is not True \
                or not isinstance(effects, list) or not effects or len(effects) > 10_000:
            raise ValidationError("Prepared mutation impact is not exact and closed.")
        if any(impact.get(key) != expected_value for key, expected_value in mutation_base.items()):
            raise ValidationError("Prepared mutation impact changed the carrier-owned mutation base.")
        expected_payload_digests = [
            artifact["digest"]
            for artifact in authority["artifactBindings"]
            if artifact["role"].startswith("managed_input")
        ]
        if impact["referencedPayloadDigests"] != expected_payload_digests:
            raise ValidationError("Prepared mutation payload digests do not close over managed inputs.")
        expected_binding = (
            "account/project-library"
            if descriptor.authority == "managed_artifact_revision"
            else "project"
            if descriptor.authority in {
                "exact_project_revision", "managed_artifact_and_optional_exact_media_revision"
            }
            else "project+timeline"
        )
        if impact["minimumBinding"] != expected_binding:
            raise ValidationError("Mutation Policy binding level does not match action authority.")
        if any(
            key in impact and _STABLE_TARGET_ID.fullmatch(str(impact[key])) is None
            for key in ("projectId", "timelineId")
        ) or any(
            key in impact and _STATE_REVISION.fullmatch(str(impact[key])) is None
            for key in ("projectRevision", "timelineRevision")
        ):
            raise ValidationError("Mutation Policy binding identities or revisions are invalid.")
        target_by_id = {item["stableId"]: item["revision"] for item in authority["targets"]}
        effect_keys = {
            "operation", "kind", "trackTypes", "targets", "placementIntent",
            "broad", "ambiguous", "complete",
        }
        public_target_keys = {"kind", "stableId", "revision", "trackType", "trackIndex", "mediaRole"}
        public_target_kinds = {
            "project_library", "project", "timeline", "track", "clip",
            "fusion_composition", "media", "marker",
        }
        if any(not isinstance(effect, Mapping) or set(effect) != effect_keys \
               or not isinstance(effect.get("operation"), str)
               or re.fullmatch(r"^[a-z0-9_]+(?:[.][a-z0-9_]+)*$", effect["operation"]) is None \
               or effect.get("operation") != descriptor.command_id \
               or effect.get("kind") not in {"create", "update", "delete", "blade", "unknown"} \
               or effect.get("placementIntent") not in {"marker", "explicit"} \
               or not isinstance(effect.get("trackTypes"), list) or len(effect["trackTypes"]) > 2 \
               or any(track not in {"video", "audio", "subtitle"} for track in effect["trackTypes"]) \
               or not isinstance(effect.get("targets"), list) or len(effect["targets"]) > 10_000 \
               or any(not isinstance(target, Mapping)
                      or not {"kind", "stableId", "revision"} <= set(target)
                      or set(target) - public_target_keys
                      or target.get("kind") not in public_target_kinds
                      or _STABLE_TARGET_ID.fullmatch(str(target.get("stableId", ""))) is None
                      or _STATE_REVISION.fullmatch(str(target.get("revision", ""))) is None
                      or (("trackType" in target) != ("trackIndex" in target))
                      or ("trackType" in target and (
                          target.get("trackType") not in {"video", "audio", "subtitle"}
                          or not isinstance(target.get("trackIndex"), int)
                          or target["trackIndex"] < 1
                      ))
                      or ("mediaRole" in target and target.get("mediaRole") not in {
                          "music", "dialogue", "voiceover", "ambience", "effects", "other"
                      })
                      or target_by_id.get(target.get("stableId")) != target.get("revision")
                      for target in effect["targets"]) \
               or effect.get("complete") is not True or effect.get("ambiguous") is not False \
               or effect.get("broad") is not False for effect in effects):
            raise ValidationError("Mutation Policy effects are incomplete or ambiguous.")
        expected_effects = _expected_effects(descriptor, input_value, authority)
        semantic_effects = [
            {
                "kind": effect["kind"],
                "trackTypes": effect["trackTypes"],
                "placementIntent": effect["placementIntent"],
                "targets": effect["targets"],
            }
            for effect in effects
        ]
        if semantic_effects != expected_effects:
            raise ValidationError("Mutation Policy effects do not match exact action semantics.")
        policy = impact.get("verificationPolicy")
        if not isinstance(policy, Mapping) or set(policy) != {
            "minimumEvidence", "requireProtectedStatePreserved", "protectedTargetEvidence"
        } or not isinstance(policy.get("minimumEvidence"), list) or not policy["minimumEvidence"] \
                or any(item not in _ALLOWED_EVIDENCE for item in policy["minimumEvidence"]) \
                or policy.get("requireProtectedStatePreserved") is not True \
                or policy.get("protectedTargetEvidence") != "every_declared_target":
            raise ValidationError("Mutation Policy verification policy is incomplete.")
        if policy["minimumEvidence"] != _expected_verification_modalities(descriptor):
            raise ValidationError("Mutation Policy verification evidence understates the action contract.")
        if impact["minimumBinding"] == "project+timeline" and any(
            not isinstance(impact.get(key), str) or not impact[key]
            for key in ("projectId", "timelineId", "projectRevision", "timelineRevision")
        ):
            raise ValidationError("Timeline-bound impact lacks exact project and timeline revisions.")
        if impact["minimumBinding"] == "project+timeline" and (
            impact["projectId"] != mutation_base.get("projectId")
            or impact["projectRevision"] != mutation_base.get("projectRevision")
            or impact["timelineId"] != mutation_base.get("timelineId")
            or impact["timelineRevision"] != mutation_base.get("timelineRevision")
        ):
            raise ValidationError("Timeline-bound impact does not match the exact runtime revision.")
        if impact["minimumBinding"] == "project" and any(
            not isinstance(impact.get(key), str) or not impact[key]
            for key in ("projectId", "projectRevision")
        ):
            raise ValidationError("Project-bound impact lacks exact project revision.")
        if impact["minimumBinding"] == "project" and (
            impact["projectId"] != mutation_base.get("projectId")
            or impact["projectRevision"] != mutation_base.get("projectRevision")
        ):
            raise ValidationError("Project-bound impact does not match the exact runtime revision.")
        if impact["minimumBinding"] == "account/project-library" and any(
            key in impact for key in ("projectId", "timelineId", "projectRevision", "timelineRevision")
        ):
            raise ValidationError("Project-library impact carries an over-broad project binding.")
    return impact


@dataclass(frozen=True)
class ResidualAvPreparedActionDescriptor:
    descriptor: ResidualAvActionDescriptor
    owner: ResidualAvSemanticOwner

    version = 1

    @property
    def capability_id(self) -> str | None:
        return PREPARED_ACTION_ACTION_METADATA[self.descriptor.action_id]["capabilityId"]

    @property
    def operation_class(self) -> str:
        return self.descriptor.operation_class

    def validate_input(self, value: Any) -> dict[str, Any]:
        schema = _schema(self.descriptor.action_id, "input")
        _validate_schema(value, schema)
        if not isinstance(value, Mapping):
            raise ValidationError("Residual action input must be an object.")
        normalized = self.owner.normalize_input(deepcopy(value))
        if not isinstance(normalized, Mapping):
            raise ValidationError("Residual action input normalization must return an object.")
        normalized = _canonical(normalized)
        _validate_schema(normalized, schema)
        return normalized

    def _resolve(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        return _validate_authority(
            self.descriptor, value, self.owner.resolve_exact(context, value)
        )

    def prepare(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        _require_carrier_binding(self.descriptor, context, value)
        authority = self._resolve(context, value)
        impact = _validate_impact(
            self.descriptor,
            context,
            authority,
            value,
            self.owner.build_impact(context, value, deepcopy(authority)),
        )
        return {
            "targets": authority["targets"],
            "preState": {
                "action": self.descriptor.action_id,
                "state": authority["preState"],
                "protectedState": authority["protectedState"],
                "artifactBindings": authority["artifactBindings"],
            },
            "impact": impact,
            "lowering": {"normalizedInput": value, "resolved": authority["lowering"]},
            "verification": {
                "minimumEvidence": list(self.descriptor.verification),
                "protectedState": authority["protectedState"],
            },
            "recovery": {"strategy": self.descriptor.recovery},
            "domain": authority,
        }

    def resolve_current(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        value = prepared.get("lowering", {}).get("normalizedInput")
        if not isinstance(value, Mapping):
            raise ValidationError("Prepared residual input is unavailable.")
        _require_carrier_binding(self.descriptor, context, value)
        authority = self._resolve(context, value)
        return {
            "targets": authority["targets"],
            "preState": {
                "action": self.descriptor.action_id,
                "state": authority["preState"],
                "protectedState": authority["protectedState"],
                "artifactBindings": authority["artifactBindings"],
            },
        }

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        value = prepared.get("lowering", {}).get("normalizedInput")
        if not isinstance(value, Mapping):
            raise ValidationError("Prepared residual lowering is unavailable.")
        _require_carrier_binding(self.descriptor, context, value)
        return self.owner.execute(context, value, prepared)

    def verify(
        self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any
    ) -> dict[str, Any]:
        value = prepared.get("lowering", {}).get("normalizedInput")
        if not isinstance(value, Mapping):
            raise ValidationError("Prepared residual input is unavailable.")
        _require_carrier_binding(self.descriptor, context, value)
        proof = self.owner.read_evidence(context, prepared, result)
        if not isinstance(proof, Mapping) or set(proof) != {"outcome", "evidence", "protectedStatePreserved"}:
            raise ValidationError("Residual action verification is incomplete.")
        evidence = proof["evidence"]
        if not isinstance(evidence, list) or not evidence:
            raise ValidationError("Residual action verification has no independent evidence.")
        modalities = set()
        for item in evidence:
            if not isinstance(item, Mapping) or set(item) != {"modality", "digest", "summary"} \
                    or item.get("modality") not in _ALLOWED_EVIDENCE \
                    or not isinstance(item.get("digest"), str) or _DIGEST.fullmatch(item["digest"]) is None \
                    or not isinstance(item.get("summary"), str) or not (1 <= len(item["summary"]) <= 500):
                raise ValidationError("Residual action verification evidence is malformed.")
            modalities.add(item["modality"])
        required = set().union(*(_MODALITY[item] for item in self.descriptor.verification))
        if not required <= modalities or proof.get("outcome") != "passed" \
                or proof.get("protectedStatePreserved") is not True:
            raise ValidationError("Residual action minimum proof or protected-state proof failed.")
        return _assert_public(proof)

    def recover(
        self, context: Mapping[str, Any], prepared: Mapping[str, Any], failure: BaseException
    ) -> dict[str, Any]:
        value = prepared.get("lowering", {}).get("normalizedInput")
        if not isinstance(value, Mapping):
            raise ValidationError("Prepared residual input is unavailable.")
        _require_carrier_binding(self.descriptor, context, value)
        recovery = self.owner.recover(context, prepared, failure)
        valid_read_recovery = self.operation_class == "read" and recovery == {
            "outcome": "not_needed",
            "attempted": False,
            "manualActionRequired": False,
        }
        valid_mutation_recovery = self.operation_class == "mutation" \
            and isinstance(recovery, Mapping) \
            and set(recovery) == {"outcome", "attempted", "manualActionRequired"} \
            and recovery.get("outcome") in {"succeeded", "failed", "manual_required"} \
            and recovery.get("attempted") is True \
            and isinstance(recovery.get("manualActionRequired"), bool)
        if not (valid_read_recovery or valid_mutation_recovery):
            raise ValidationError("Residual action recovery truth is incomplete.")
        return _assert_public(recovery)

    def project_result(
        self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any
    ) -> Any:
        value = prepared.get("lowering", {}).get("normalizedInput")
        if not isinstance(value, Mapping):
            raise ValidationError("Prepared residual input is unavailable.")
        _require_carrier_binding(self.descriptor, context, value)
        projected = _assert_public(
            self.owner.project_result(context, prepared, result)
        )
        _validate_schema(projected, _schema(self.descriptor.action_id, "result"))
        return projected

    def validate_public_result(self, value: Any) -> bool:
        try:
            _validate_schema(_assert_public(value), _schema(self.descriptor.action_id, "result"))
        except ValidationError:
            return False
        return True


@dataclass(frozen=True)
class _UnavailableResidualAvDescriptor:
    operation_class: str
    version: int = 1
    blocker: str = "unavailable"


def residual_av_prepared_action_descriptors(
    *,
    authority: ResidualAvExecutionAuthority,
) -> Mapping[str, ResidualAvPreparedActionDescriptor]:
    """Return the exact 73-action residual contribution for the sole signed carrier."""

    expected = {
        descriptor.action_id
        for descriptor in RESIDUAL_AV_ACTION_DESCRIPTORS
        if descriptor.action_id not in UNAVAILABLE_RESIDUAL_AV_ACTIONS
    }
    if authority is None:
        raise RuntimeError(
            "Residual prepared actions require a process-local execution authority."
        )
    all_owners: dict[str, ResidualAvSemanticOwner] = {
        descriptor.action_id: _HandlerSemanticOwner(descriptor, authority)
        for descriptor in RESIDUAL_AV_ACTION_DESCRIPTORS
        if descriptor.action_id in expected
    }
    if "cutagent.action.audio.info" in expected:
        all_owners["cutagent.action.audio.info"] = _AudioInfoSemanticOwner(authority)
    descriptors = {
        descriptor.action_id: ResidualAvPreparedActionDescriptor(
            descriptor=descriptor,
            owner=all_owners[descriptor.action_id],
        )
        for descriptor in RESIDUAL_AV_ACTION_DESCRIPTORS
        if descriptor.action_id not in UNAVAILABLE_RESIDUAL_AV_ACTIONS
    }
    if len(descriptors) != 73:
        raise RuntimeError("Residual prepared-action contribution must contain exactly 73 actions.")
    return MappingProxyType(descriptors)


def residual_av_prepared_action_contributions(
    *,
    authority: ResidualAvExecutionAuthority,
) -> tuple[tuple[str, Mapping[str, Any]], ...]:
    """Return complete and fail-closed contributions for Packet 0 composition."""

    complete = residual_av_prepared_action_descriptors(
        authority=authority,
    )
    by_id = {item.action_id: item for item in RESIDUAL_AV_ACTION_DESCRIPTORS}
    unavailable = MappingProxyType(
        {
            action_id: _UnavailableResidualAvDescriptor(
                operation_class=by_id[action_id].operation_class,
                blocker=blocker,
            )
            for action_id, blocker in UNAVAILABLE_RESIDUAL_AV_ACTIONS.items()
        }
    )
    return (
        ("residual-clip-text-audio", complete),
        ("residual-clip-text-audio-unavailable", unavailable),
    )
