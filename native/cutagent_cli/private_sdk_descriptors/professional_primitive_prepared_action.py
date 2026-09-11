"""Signed-carrier adapters for the professional native-video primitives.

The reviewed keyframe, transform, and retime implementations remain the sole
semantic owners. This packet only adapts those owners to the shared seven-stage
``PreparedActionDescriptor`` protocol. In particular, it contains no command
argv, native identifier, environment variable, or DaVinci Resolve lowering.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence

from ..errors import ValidationError


@dataclass(frozen=True)
class _ActionDefinition:
    action_id: str
    operation_class: str
    capability_id: str
    minimum_evidence: tuple[str, ...]
    recovery: str
    result_fields: frozenset[str]
    protected_state_location: str = "top_level"
    target_binding: str = "input_timeline"

    def expected_result_fields(self, value: Mapping[str, Any]) -> frozenset[str]:
        if self.action_id == "cutagent.action.clip.keyframe.get" and value.get("property") == "RetimeFrame":
            return self.result_fields | {"curve"}
        return self.result_fields


_KEYFRAME_RESULT_FIELDS = frozenset(
    {
        "actionId",
        "targetId",
        "timelineRevision",
        "protectedStatePreserved",
        "property",
        "keyframes",
    }
)
_DEFINITIONS = (
    _ActionDefinition(
        "cutagent.action.edit.fx.add",
        "mutation",
        "edit.ofx_resolvefx_native",
        ("structural_readback", "rendered_frame"),
        "restore_exact_pre_state_or_report_manual_recovery",
        frozenset(
            {
                "actionId", "status", "target", "revision", "affected",
                "details", "verification", "recovery",
            }
        ),
        "edit_verification",
    ),
    _ActionDefinition(
        "cutagent.action.clip.keyframe.add",
        "mutation",
        "clip.keyframe_crud",
        ("structural_readback",),
        "restore_exact_pre_state",
        _KEYFRAME_RESULT_FIELDS,
    ),
    _ActionDefinition(
        "cutagent.action.clip.keyframe.delete",
        "mutation",
        "clip.keyframe_crud",
        ("structural_readback",),
        "restore_exact_pre_state",
        _KEYFRAME_RESULT_FIELDS,
    ),
    _ActionDefinition(
        "cutagent.action.clip.keyframe.get",
        "read",
        "clip.keyframe_crud",
        ("structural_readback",),
        "not_applicable",
        _KEYFRAME_RESULT_FIELDS,
    ),
    _ActionDefinition(
        "cutagent.action.clip.keyframe.set_interpolation",
        "mutation",
        "clip.keyframe_crud",
        ("structural_readback",),
        "restore_exact_pre_state",
        _KEYFRAME_RESULT_FIELDS,
    ),
    _ActionDefinition(
        "cutagent.action.clip.transform",
        "mutation",
        "clip.transform",
        ("structural_readback",),
        "restore_exact_pre_state",
        frozenset(
            {
                "actionId",
                "targetId",
                "timelineRevision",
                "protectedStatePreserved",
                "before",
                "after",
            }
        ),
    ),
    *(
        _ActionDefinition(
            action_id,
            "mutation",
            capability_id,
            ("structural_readback",),
            "restore_exact_pre_state_or_report_manual_recovery",
            frozenset(
                {
                    "actionId",
                    "timelineRevision",
                    "targets",
                    "before",
                    "after",
                    "verification",
                    "publicResult",
                }
            ),
            "verification",
        )
        for action_id, capability_id in (
            ("cutagent.action.clip.speed", "clip.speed"),
            ("cutagent.action.clip.speed_ramp", "edit.speed_ramp"),
            ("cutagent.action.clip.freeze", "clip.freeze"),
            ("cutagent.action.clip.reverse", "clip.reverse"),
        )
    ),
    _ActionDefinition(
        "cutagent.action.system.keyframe_mode.set",
        "mutation",
        "system.keyframe_mode",
        ("runtime_setting_readback",),
        "restore_exact_pre_state_or_report_manual_recovery",
        frozenset({"actionId", "data"}),
        "verification_only",
        "runtime_context",
    ),
)

PROFESSIONAL_PRIMITIVE_ACTION_IDS = tuple(
    definition.action_id for definition in _DEFINITIONS
)
REVIEWED_CLIP_PRIMITIVE_ACTION_IDS = PROFESSIONAL_PRIMITIVE_ACTION_IDS[:-1]
_PRIVATE_KEYS = frozenset(
    {
        "argv",
        "args",
        "command",
        "commandId",
        "command_id",
        "commandPath",
        "command_path",
        "engine",
        "lowering",
        "nativeId",
        "nativeIds",
        "preState",
        "privateTarget",
        "privateTargets",
        "recoveryPlan",
        "route",
        "routeMetadata",
        "route_metadata",
        "stderr",
        "stdout",
        "verificationPlan",
    }
)
_EVIDENCE_MODALITIES = MappingProxyType(
    {
        "structural_readback": frozenset({"readback", "structural"}),
        "rendered_frame": frozenset({"rendered"}),
        "runtime_setting_readback": frozenset({"readback"}),
    }
)
_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
_OPERATION = re.compile(r"^[a-z0-9_]+(?:\.[a-z0-9_]+)*$")
_EFFECT_KEYS = frozenset({
    "operation", "kind", "trackTypes", "targets", "placementIntent",
    "broad", "ambiguous", "complete",
})
_TARGET_REQUIRED_KEYS = frozenset({"kind", "stableId", "revision"})
_TARGET_OPTIONAL_KEYS = frozenset({"trackType", "trackIndex", "mediaRole"})
_TARGET_KINDS = frozenset({
    "project_library", "project", "timeline", "track", "clip",
    "fusion_composition", "media", "marker", "runtime_setting",
})
_TRACK_TYPES = frozenset({"video", "audio", "subtitle"})
_MEDIA_ROLES = frozenset({"music", "dialogue", "voiceover", "ambience", "effects", "other"})
_MUTATION_BASE_REQUIRED_KEYS = frozenset(
    {
        "contractVersion", "carrier", "minimumBinding", "registryDigest",
        "canonicalRequestDigest", "referencedPayloadDigests", "requestId",
        "operationId", "executionId",
        "projectLibraryId",
    }
)
_MUTATION_BASE_OPTIONAL_KEYS = frozenset(
    {"projectId", "timelineId", "projectRevision", "timelineRevision"}
)


class ProfessionalPrimitiveSemanticOwner(Protocol):
    """One action-specific owner; no stage accepts a caller-selected action ID."""

    def normalize_input(self, value: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def resolve_exact(
        self, context: Mapping[str, Any], value: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...

    def build_impact(
        self,
        context: Mapping[str, Any],
        value: Mapping[str, Any],
        authority: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...

    def execute(
        self,
        context: Mapping[str, Any],
        value: Mapping[str, Any],
        prepared: Mapping[str, Any],
    ) -> Any: ...

    def read_evidence(
        self,
        context: Mapping[str, Any],
        prepared: Mapping[str, Any],
        result: Any,
    ) -> Mapping[str, Any]: ...

    def recover(
        self,
        context: Mapping[str, Any],
        prepared: Mapping[str, Any],
        failure: BaseException,
    ) -> Mapping[str, Any]: ...

    def project_result(
        self,
        context: Mapping[str, Any],
        prepared: Mapping[str, Any],
        result: Any,
    ) -> Any: ...

    def validate_result(self, value: Any) -> bool: ...


def _canonical(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if abs(value) > 9_007_199_254_740_991:
            raise ValidationError("Prepared action integer exceeds canonical JSON range.")
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
        elif isinstance(current, str):
            lowered = current.lower()
            if (
                current.startswith(("/Users/", "/home/", "/tmp/", "\\\\"))
                or (
                    len(current) >= 3
                    and current[0].isalpha()
                    and current[1:3] in {":\\", ":/"}
                )
                or "cutagent_cli/" in lowered
                or "cutagent_cli\\" in lowered
            ):
                raise ValidationError("A private local path reached a public projection.")

    visit(normalized)
    return normalized


def _validate_targets(
    value: Any,
    normalized_input: Mapping[str, Any],
    context: Mapping[str, Any],
    definition: _ActionDefinition,
) -> list[dict[str, Any]]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or not value
    ):
        raise ValidationError("Professional primitives require exact stable targets.")
    if definition.target_binding == "input_timeline":
        project_id = normalized_input.get("projectId")
        timeline_id = normalized_input.get("timelineId")
        expected_revision = normalized_input.get("timelineRevision")
    else:
        project_id = context.get("project", {}).get("projectId")
        timeline_id = context.get("timeline", {}).get("timelineId")
        expected_revision = None
    if not all(isinstance(item, str) and item for item in (project_id, timeline_id)):
        raise ValidationError("Professional primitives require exact project and timeline bindings.")
    if definition.target_binding == "input_timeline" and not (
        isinstance(expected_revision, str) and expected_revision
    ):
        raise ValidationError("Professional primitives require an exact timeline revision.")
    targets = []
    identities = set()
    for target in value:
        if not isinstance(target, Mapping) or set(target) != {
            "kind",
            "stableId",
            "revision",
            "projectId",
            "timelineId",
        }:
            raise ValidationError("Prepared stable targets have an invalid shape.")
        if not all(
            isinstance(target.get(key), str) and target[key]
            for key in ("kind", "stableId", "revision", "projectId", "timelineId")
        ):
            raise ValidationError("Prepared targets require stable identity and revision.")
        if target["stableId"] in identities:
            raise ValidationError("Prepared stable targets must be unique.")
        if (
            target["projectId"] != project_id
            or target["timelineId"] != timeline_id
            or (
                expected_revision is not None
                and target["revision"] != expected_revision
            )
        ):
            raise ValidationError("Prepared targets escaped the exact input binding.")
        identities.add(target["stableId"])
        targets.append(_canonical(target))
    return targets


def _validate_authority(
    value: Any,
    normalized_input: Mapping[str, Any],
    context: Mapping[str, Any],
    definition: _ActionDefinition,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "targets",
        "preState",
        "lowering",
        "protectedState",
    }:
        raise ValidationError("Professional primitive authority is incomplete.")
    if (
        not isinstance(value["preState"], Mapping)
        or not value["preState"]
        or not isinstance(value["lowering"], Mapping)
        or not value["lowering"]
        or not isinstance(value["protectedState"], Mapping)
    ):
        raise ValidationError("Professional primitive private state is incomplete.")
    return {
        "targets": _validate_targets(
            value["targets"], normalized_input, context, definition
        ),
        "preState": _canonical(value["preState"]),
        "lowering": _canonical(value["lowering"]),
        "protectedState": _canonical(value["protectedState"]),
    }


def _required_evidence(definition: _ActionDefinition) -> set[str]:
    return set().union(
        *(
            _EVIDENCE_MODALITIES[modality]
            for modality in definition.minimum_evidence
        )
    )


def _read_target_digests(authority: Mapping[str, Any]) -> list[str]:
    targets = authority.get("targets")
    if not isinstance(targets, list) or not targets:
        raise ValidationError("Prepared read authority has no exact targets.")
    return [
        "sha256:" + hashlib.sha256(json.dumps(
            _canonical({
                "kind": target["kind"],
                "stableId": target["stableId"],
                "revision": target["revision"],
            }),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        for target in targets
    ]


def _validate_impact(
    definition: _ActionDefinition,
    value: Any,
    authority: Mapping[str, Any],
) -> dict[str, Any]:
    impact = _assert_public(value)
    if not isinstance(impact, dict) or impact.get("complete") is not True:
        raise ValidationError("Professional primitive impact is incomplete.")
    if definition.operation_class == "mutation":
        effects = impact.get("effects")
        verification_policy = impact.get("verificationPolicy")
        def invalid_effect(effect: Any) -> bool:
            if not isinstance(effect, Mapping) or set(effect) != _EFFECT_KEYS:
                return True
            if (
                not isinstance(effect.get("operation"), str)
                or _OPERATION.fullmatch(effect["operation"]) is None
                or effect.get("kind") not in {"create", "update", "delete", "blade", "unknown"}
                or effect.get("placementIntent") not in {"marker", "explicit", "unknown"}
                or not isinstance(effect.get("trackTypes"), list)
                or len(effect["trackTypes"]) > 2
                or len(set(effect["trackTypes"])) != len(effect["trackTypes"])
                or any(item not in _TRACK_TYPES for item in effect["trackTypes"])
                or not isinstance(effect.get("targets"), list)
                or not effect["targets"]
            ):
                return True
            for target in effect["targets"]:
                if (
                    not isinstance(target, Mapping)
                    or not _TARGET_REQUIRED_KEYS <= set(target)
                    or set(target) - (_TARGET_REQUIRED_KEYS | _TARGET_OPTIONAL_KEYS)
                    or target.get("kind") not in _TARGET_KINDS
                    or not all(isinstance(target.get(key), str) and target[key] for key in _TARGET_REQUIRED_KEYS - {"kind"})
                    or ((target.get("trackType") is None) != (target.get("trackIndex") is None))
                    or (target.get("trackType") is not None and target["trackType"] not in _TRACK_TYPES)
                    or (target.get("trackIndex") is not None and (not isinstance(target["trackIndex"], int) or isinstance(target["trackIndex"], bool) or target["trackIndex"] < 1))
                    or (target.get("mediaRole") is not None and target["mediaRole"] not in _MEDIA_ROLES)
                ):
                    return True
            return False
        if (
            impact.get("status") != "mutation"
            or impact.get("ambiguous") is not False
            or impact.get("broad") is not False
            or not isinstance(effects, list)
            or not effects
            or any(invalid_effect(effect) for effect in effects)
            or any(effect.get("complete") is not True or effect.get("ambiguous") is not False or effect.get("broad") is not False for effect in effects)
            or impact.get("closedComposition") is not True
            or impact.get("executableStableTargetPrecondition") is not True
            or not isinstance(verification_policy, Mapping)
            or set(verification_policy)
            != {
                "minimumEvidence",
                "requireProtectedStatePreserved",
                "protectedTargetEvidence",
            }
            or not isinstance(verification_policy.get("minimumEvidence"), list)
            or set(verification_policy["minimumEvidence"])
            != _required_evidence(definition)
            or verification_policy.get("requireProtectedStatePreserved") is not True
            or verification_policy.get("protectedTargetEvidence")
            != "every_declared_target"
        ):
            raise ValidationError("Mutation Policy impact is not exact and closed.")
    elif (
        set(impact) != {
            "contractVersion", "status", "complete", "targetDigests",
            "resultMaximumBytes",
        }
        or impact.get("contractVersion") != 1
        or impact.get("status") != "read"
        or not isinstance(impact.get("targetDigests"), list)
        or len(impact["targetDigests"]) > 10_000
        or any(
            not isinstance(item, str) or _DIGEST.fullmatch(item) is None
            for item in impact["targetDigests"]
        )
        or impact["targetDigests"] != _read_target_digests(authority)
        or not isinstance(impact.get("resultMaximumBytes"), int)
        or isinstance(impact["resultMaximumBytes"], bool)
        or not 1 <= impact["resultMaximumBytes"] <= 8_388_608
    ):
        raise ValidationError("Read impact must match the prepared carrier contract.")
    return impact


def _merge_carrier_mutation_base(
    context: Mapping[str, Any], domain_impact: Any
) -> dict[str, Any]:
    base = context.get("mutationBase")
    if not isinstance(base, Mapping):
        raise ValidationError("Mutation descriptor requires the carrier-owned mutation base.")
    base_keys = set(base)
    if not _MUTATION_BASE_REQUIRED_KEYS <= base_keys or base_keys - (
        _MUTATION_BASE_REQUIRED_KEYS | _MUTATION_BASE_OPTIONAL_KEYS
    ):
        raise ValidationError("Carrier-owned mutation base has an invalid shape.")
    normalized_base = _canonical(base)
    if (
        normalized_base.get("contractVersion") != 1
        or normalized_base.get("carrier") != "sdk"
        or not all(
            isinstance(normalized_base.get(key), str) and normalized_base[key]
            for key in (
                "minimumBinding", "registryDigest", "canonicalRequestDigest",
                "requestId", "operationId", "executionId",
                "projectLibraryId",
            )
        )
        or _DIGEST.fullmatch(normalized_base["registryDigest"]) is None
        or _DIGEST.fullmatch(normalized_base["canonicalRequestDigest"]) is None
        or not isinstance(normalized_base.get("referencedPayloadDigests"), list)
        or any(
            not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None
            for digest in normalized_base["referencedPayloadDigests"]
        )
    ):
        raise ValidationError("Carrier-owned mutation base is incomplete.")
    normalized_domain = _assert_public(domain_impact)
    if not isinstance(normalized_domain, dict) or base_keys.intersection(normalized_domain):
        raise ValidationError("Domain impact must only add fields beyond the carrier mutation base.")
    return {**normalized_base, **normalized_domain}


class SystemKeyframeModeMutationError(RuntimeError):
    """Truthful failure raised after a system-setting mutation may have begun."""

    possible_mutation = "possible"
    usage = "consumed"


@dataclass(frozen=True)
class SystemKeyframeModeSemanticOwner:
    """Production owner for DaVinci Resolve's global keyframe-mode setting."""

    connection_factory: Any = None
    clip_ops_module: Any = None

    _MODE_TO_NATIVE = MappingProxyType({"all": 0, "color": 1, "sizing": 2})
    _NATIVE_TO_MODE = MappingProxyType({0: "all", 1: "color", 2: "sizing"})
    action_id = "cutagent.action.system.keyframe_mode.set"

    def _services(self) -> tuple[Any, Any]:
        connection_factory = self.connection_factory
        clip_ops_module = self.clip_ops_module
        if connection_factory is None:
            from ..connection import get_connection

            connection_factory = get_connection
        if clip_ops_module is None:
            from ..core import clip_ops

            clip_ops_module = clip_ops
        return connection_factory, clip_ops_module

    def _connection(self) -> Any:
        connection_factory, _clip_ops_module = self._services()
        return connection_factory(require_project=False)

    @classmethod
    def _readback_mode(cls, value: Any) -> str:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in cls._MODE_TO_NATIVE:
                return normalized
        if isinstance(value, int) and not isinstance(value, bool):
            mode = cls._NATIVE_TO_MODE.get(value)
            if mode is not None:
                return mode
        raise ValidationError("DaVinci Resolve returned an unknown keyframe mode.")

    def _read_mode(self, connection: Any | None = None) -> str:
        _connection_factory, clip_ops_module = self._services()
        active_connection = connection if connection is not None else self._connection()
        payload = clip_ops_module.get_keyframe_mode(active_connection)
        if not isinstance(payload, Mapping) or "keyframe_mode" not in payload:
            raise ValidationError("Keyframe-mode readback is incomplete.")
        return self._readback_mode(payload["keyframe_mode"])

    def _set_mode(self, mode: str, connection: Any | None = None) -> None:
        _connection_factory, clip_ops_module = self._services()
        active_connection = connection if connection is not None else self._connection()
        payload = clip_ops_module.set_keyframe_mode(
            active_connection, self._MODE_TO_NATIVE[mode]
        )
        if not isinstance(payload, Mapping) or payload.get("success") is not True:
            raise SystemKeyframeModeMutationError(
                "DaVinci Resolve did not confirm the keyframe-mode mutation."
            )

    @staticmethod
    def _runtime_binding(context: Mapping[str, Any]) -> tuple[str, str]:
        project_id = context.get("project", {}).get("projectId")
        timeline_id = context.get("timeline", {}).get("timelineId")
        if not all(isinstance(value, str) and value for value in (project_id, timeline_id)):
            raise ValidationError(
                "Keyframe-mode mutation requires the exact active project and timeline context."
            )
        return project_id, timeline_id

    def normalize_input(self, value: Mapping[str, Any]) -> Mapping[str, Any]:
        if set(value) != {"mode"} or value.get("mode") not in self._MODE_TO_NATIVE:
            raise ValidationError(
                "Keyframe-mode input requires exactly all, color, or sizing."
            )
        return {"mode": value["mode"]}

    def resolve_exact(
        self, context: Mapping[str, Any], value: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        project_id, timeline_id = self._runtime_binding(context)
        mode = self._read_mode()
        protected_state = {
            "projectId": project_id,
            "timelineId": timeline_id,
        }
        return {
            "targets": [
                {
                    "kind": "runtime_setting",
                    "stableId": "resolve.keyframe_mode",
                    "revision": f"revision_keyframe_mode_{mode}",
                    "projectId": project_id,
                    "timelineId": timeline_id,
                }
            ],
            "preState": {"mode": mode},
            "lowering": {"requestedMode": value["mode"]},
            "protectedState": protected_state,
        }

    def build_impact(
        self,
        context: Mapping[str, Any],
        value: Mapping[str, Any],
        authority: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        del value
        targets = authority.get("targets")
        if not isinstance(targets, list) or len(targets) != 1:
            raise ValidationError("Keyframe-mode runtime target is incomplete.")
        target = targets[0]
        if (
            not isinstance(target, Mapping)
            or target.get("kind") != "runtime_setting"
            or target.get("stableId") != "resolve.keyframe_mode"
            or not isinstance(target.get("revision"), str)
        ):
            raise ValidationError("Keyframe-mode runtime target is invalid.")
        effect = {
            "operation": "system.keyframe_mode.set",
            "kind": "update",
            "trackTypes": [],
            "targets": [
                {
                    "kind": "runtime_setting",
                    "stableId": target["stableId"],
                    "revision": target["revision"],
                }
            ],
            "placementIntent": "explicit",
            "complete": True,
            "ambiguous": False,
            "broad": False,
        }
        return {
            "status": "mutation",
            "complete": True,
            "ambiguous": False,
            "broad": False,
            "effects": [effect],
            "closedComposition": True,
            "executableStableTargetPrecondition": True,
            "verificationPolicy": {
                "minimumEvidence": ["readback"],
                "requireProtectedStatePreserved": True,
                "protectedTargetEvidence": "every_declared_target",
            },
        }

    def execute(
        self,
        _context: Mapping[str, Any],
        value: Mapping[str, Any],
        prepared: Mapping[str, Any],
    ) -> Any:
        before = prepared.get("preState", {}).get("state", {}).get("mode")
        if before not in self._MODE_TO_NATIVE:
            raise ValidationError("Prepared keyframe-mode pre-state is unavailable.")
        connection = self._connection()
        self._set_mode(value["mode"], connection)
        observed = self._read_mode(connection)
        if observed != value["mode"]:
            raise SystemKeyframeModeMutationError(
                "Keyframe-mode readback did not match the requested mode."
            )
        return {
            "beforeMode": before,
            "afterMode": observed,
            "changed": before != observed,
        }

    def read_evidence(
        self,
        context: Mapping[str, Any],
        prepared: Mapping[str, Any],
        result: Any,
    ) -> Mapping[str, Any]:
        if not isinstance(result, Mapping):
            raise ValidationError("Keyframe-mode execution result is unavailable.")
        observed = self._read_mode()
        expected = (
            prepared.get("lowering", {})
            .get("normalizedInput", {})
            .get("mode")
        )
        target = prepared.get("targets", [{}])[0]
        target_bound = (
            isinstance(target, Mapping)
            and target.get("kind") == "runtime_setting"
            and target.get("stableId") == "resolve.keyframe_mode"
            and isinstance(target.get("revision"), str)
        )
        passed = (
            expected in self._MODE_TO_NATIVE
            and observed == expected
            and observed == result.get("afterMode")
            and target_bound
        )
        material = json.dumps(
            _canonical(
                {
                    "expectedMode": expected,
                    "observedMode": observed,
                    "target": {
                        "kind": target.get("kind"),
                        "stableId": target.get("stableId"),
                    },
                }
            ),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return {
            "outcome": "passed" if passed else "failed",
            "evidence": [
                {
                    "modality": "readback",
                    "digest": f"sha256:{hashlib.sha256(material).hexdigest()}",
                    "summary": "Read back the exact DaVinci Resolve keyframe mode.",
                }
            ],
            # The descriptor mutates only the declared runtime-setting target.
            # The carrier independently re-reads every scope-protected target.
            "protectedStatePreserved": target_bound,
        }

    def recover(
        self,
        context: Mapping[str, Any],
        prepared: Mapping[str, Any],
        _failure: BaseException,
    ) -> Mapping[str, Any]:
        before = prepared.get("preState", {}).get("state", {}).get("mode")
        protected = prepared.get("preState", {}).get("protectedState")
        try:
            project_id, timeline_id = self._runtime_binding(context)
        except Exception:
            project_id, timeline_id = None, None
        protected_preserved = protected == {
            "projectId": project_id,
            "timelineId": timeline_id,
        }
        if before not in self._MODE_TO_NATIVE:
            try:
                self._read_mode()
            except Exception:
                pass
            return {
                "outcome": "manual_required",
                "attempted": True,
                "manualActionRequired": True,
            }
        try:
            connection = self._connection()
            self._set_mode(before, connection)
            restored = self._read_mode(connection) == before
        except Exception:
            restored = False
        outcome = (
            "succeeded"
            if restored and protected_preserved
            else "manual_required"
            if restored
            else "failed"
        )
        return {
            "outcome": outcome,
            "attempted": True,
            "manualActionRequired": outcome != "succeeded",
        }

    def project_result(
        self,
        _context: Mapping[str, Any],
        _prepared: Mapping[str, Any],
        result: Any,
    ) -> Any:
        if not isinstance(result, Mapping):
            raise ValidationError("Keyframe-mode result is unavailable.")
        return {
            "actionId": self.action_id,
            "data": {
                "mode": result.get("afterMode"),
                "changed": result.get("changed"),
            },
        }

    def validate_result(self, value: Any) -> bool:
        return (
            isinstance(value, Mapping)
            and set(value) == {"actionId", "data"}
            and value.get("actionId") == self.action_id
            and isinstance(value.get("data"), Mapping)
            and set(value["data"]) == {"mode", "changed"}
            and value["data"].get("mode") in self._MODE_TO_NATIVE
            and isinstance(value["data"].get("changed"), bool)
        )


@dataclass(frozen=True)
class ProfessionalPrimitivePreparedActionDescriptor:
    definition: _ActionDefinition
    owner: ProfessionalPrimitiveSemanticOwner

    version = 1

    @property
    def operation_class(self) -> str:
        return self.definition.operation_class

    @property
    def capability_id(self) -> str:
        return self.definition.capability_id

    def validate_input(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise ValidationError("Professional primitive input must be an object.")
        normalized = self.owner.normalize_input(deepcopy(value))
        if not isinstance(normalized, Mapping):
            raise ValidationError("Professional primitive input normalization failed.")
        return _canonical(normalized)

    def _resolve(
        self, context: Mapping[str, Any], value: Mapping[str, Any]
    ) -> dict[str, Any]:
        return _validate_authority(
            self.owner.resolve_exact(context, value),
            value,
            context,
            self.definition,
        )

    def prepare(
        self, context: Mapping[str, Any], value: Mapping[str, Any]
    ) -> dict[str, Any]:
        authority = self._resolve(context, value)
        domain_impact = self.owner.build_impact(context, value, authority)
        impact = _validate_impact(
            self.definition,
            _merge_carrier_mutation_base(context, domain_impact)
            if self.operation_class == "mutation"
            else domain_impact,
            authority,
        )
        return {
            "targets": authority["targets"],
            "preState": {
                "action": self.definition.action_id,
                "state": authority["preState"],
                "protectedState": authority["protectedState"],
            },
            "impact": impact,
            "lowering": {
                "normalizedInput": value,
                "resolved": authority["lowering"],
            },
            "verification": {
                "minimumEvidence": list(self.definition.minimum_evidence),
                "protectedState": authority["protectedState"],
            },
            "recovery": {"strategy": self.definition.recovery},
            "domain": authority,
        }

    def resolve_current(
        self, context: Mapping[str, Any], prepared: Mapping[str, Any]
    ) -> dict[str, Any]:
        value = prepared.get("lowering", {}).get("normalizedInput")
        if not isinstance(value, Mapping):
            raise ValidationError("Prepared professional primitive input is unavailable.")
        authority = self._resolve(context, value)
        return {
            "targets": authority["targets"],
            "preState": {
                "action": self.definition.action_id,
                "state": authority["preState"],
                "protectedState": authority["protectedState"],
            },
        }

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        value = prepared.get("lowering", {}).get("normalizedInput")
        if not isinstance(value, Mapping):
            raise ValidationError("Prepared professional primitive lowering is unavailable.")
        return self.owner.execute(context, value, prepared)

    def verify(
        self,
        context: Mapping[str, Any],
        prepared: Mapping[str, Any],
        result: Any,
    ) -> dict[str, Any]:
        proof = self.owner.read_evidence(context, prepared, result)
        if not isinstance(proof, Mapping) or set(proof) != {
            "outcome",
            "evidence",
            "protectedStatePreserved",
        }:
            raise ValidationError("Professional primitive verification is incomplete.")
        evidence = proof["evidence"]
        if not isinstance(evidence, list) or not evidence:
            raise ValidationError("Professional primitive verification has no evidence.")
        modalities = set()
        for item in evidence:
            if (
                not isinstance(item, Mapping)
                or set(item) != {"modality", "digest", "summary"}
                or item.get("modality") not in {"readback", "structural", "rendered"}
                or not isinstance(item.get("digest"), str)
                or _DIGEST.fullmatch(item["digest"]) is None
                or not isinstance(item.get("summary"), str)
                or not (1 <= len(item["summary"]) <= 500)
            ):
                raise ValidationError("Professional primitive evidence is malformed.")
            modalities.add(item["modality"])
        required = _required_evidence(self.definition)
        if (
            not required <= modalities
            or proof.get("outcome") != "passed"
            or proof.get("protectedStatePreserved") is not True
        ):
            raise ValidationError("Minimum proof or protected-state proof failed.")
        return _assert_public(proof)

    def recover(
        self,
        context: Mapping[str, Any],
        prepared: Mapping[str, Any],
        failure: BaseException,
    ) -> dict[str, Any]:
        recovery = self.owner.recover(context, prepared, failure)
        if (
            not isinstance(recovery, Mapping)
            or set(recovery)
            != {"outcome", "attempted", "manualActionRequired"}
            or not isinstance(recovery.get("attempted"), bool)
            or not isinstance(recovery.get("manualActionRequired"), bool)
        ):
            raise ValidationError("Professional primitive recovery truth is incomplete.")
        if self.operation_class == "read":
            if recovery != {
                "outcome": "not_applicable",
                "attempted": False,
                "manualActionRequired": False,
            }:
                raise ValidationError("Read recovery must remain not applicable.")
        else:
            outcome = recovery.get("outcome")
            valid_mutation_recovery = (
                outcome in {"succeeded", "failed", "manual_required"}
                and recovery["attempted"] is True
                and (
                    outcome != "succeeded"
                    or recovery["manualActionRequired"] is False
                )
            )
            if not valid_mutation_recovery:
                raise ValidationError("Mutation recovery truth is carrier-incompatible.")
        return _assert_public(recovery)

    def project_result(
        self,
        context: Mapping[str, Any],
        prepared: Mapping[str, Any],
        result: Any,
    ) -> Any:
        projected = _assert_public(
            self.owner.project_result(context, prepared, result)
        )
        protected_state_preserved = (
            projected.get("protectedStatePreserved")
            if isinstance(projected, Mapping)
            and self.definition.protected_state_location == "top_level"
            else projected.get("verification", {}).get("protectedStatePreserved")
            if isinstance(projected, Mapping)
            and isinstance(projected.get("verification"), Mapping)
            and self.definition.protected_state_location == "verification"
            else True
            if self.definition.protected_state_location == "verification_only"
            else projected.get("verification", {}).get("protectedState") == "preserved"
            if isinstance(projected, Mapping)
            and isinstance(projected.get("verification"), Mapping)
            and self.definition.protected_state_location == "edit_verification"
            else None
        )
        if (
            not isinstance(projected, Mapping)
            or set(projected) != self.definition.expected_result_fields(projected)
            or projected.get("actionId") != self.definition.action_id
            or protected_state_preserved is not True
        ):
            raise ValidationError("Professional primitive result projection is invalid.")
        return projected

    def validate_public_result(self, value: Any) -> bool:
        """Validate the projection against its bound action schema owner."""

        try:
            return self.owner.validate_result(deepcopy(value)) is True
        except Exception:
            return False


def professional_primitive_prepared_action_descriptors(
    *,
    owners: Mapping[str, ProfessionalPrimitiveSemanticOwner],
    system_keyframe_mode_owner: ProfessionalPrimitiveSemanticOwner | None = None,
) -> Mapping[str, ProfessionalPrimitivePreparedActionDescriptor]:
    """Return the exact eleven-action contribution for the sole shared registry."""

    expected = set(REVIEWED_CLIP_PRIMITIVE_ACTION_IDS)
    if set(owners) != expected:
        raise RuntimeError(
            "Reviewed professional primitive owners must close the exact ten-action set."
        )
    all_owners = {
        **owners,
        "cutagent.action.system.keyframe_mode.set": (
            system_keyframe_mode_owner or SystemKeyframeModeSemanticOwner()
        ),
    }
    required_stages = (
        "normalize_input",
        "resolve_exact",
        "build_impact",
        "execute",
        "read_evidence",
        "recover",
        "project_result",
        "validate_result",
    )
    if any(
        not all(callable(getattr(owner, stage, None)) for stage in required_stages)
        for owner in all_owners.values()
    ):
        raise RuntimeError("A professional primitive owner is incomplete.")
    descriptors = {
        definition.action_id: ProfessionalPrimitivePreparedActionDescriptor(
            definition=definition,
            owner=all_owners[definition.action_id],
        )
        for definition in _DEFINITIONS
    }
    if len(descriptors) != 11:
        raise RuntimeError("Professional primitive contribution must contain eleven actions.")
    return MappingProxyType(descriptors)
