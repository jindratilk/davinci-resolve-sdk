"""Signed-registry contribution for private Timeline/Version mutations.

The shared prepared-action authority is intentionally not imported here. This
module implements its descriptor protocol and advertises only actions whose
eight stages are backed by the private CutAgent CLI runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from jsonschema import Draft202012Validator
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional

from .._sdk_prepared_action_contract import PREPARED_ACTION_ACTION_METADATA
from ..connection import get_connection
from ..core import version_ops
from .timeline_artifact_prepared_action import (
    TIMELINE_ARTIFACT_ACTION_IDS,
    TimelineArtifactPreparedActionDescriptor,
    timeline_artifact_prepared_action_production_contribution,
)
from .timeline_contracts import timeline_action_result_schema
from .timeline_read_prepared_action import (
    TIMELINE_READ_ACTION_IDS,
    TimelineReadPreparedActionDescriptor,
    timeline_read_prepared_action_production_contribution,
)

from .timeline_version import (
    TIMELINE_VERSION_MUTATION_DESCRIPTORS,
    TimelineVersionMutationDescriptor,
    evaluate_timeline_version_recovery,
    prepare_timeline_version_action,
    public_timeline_version_policy_effect,
    verify_timeline_version_protected_state,
)

InputValidator = Callable[[str, Any], Mapping[str, Any]]
AuthorityResolver = Callable[
    [Mapping[str, Any], str, Mapping[str, Any]], Mapping[str, Any]
]
ImpactBuilder = Callable[[Mapping[str, Any], str, Mapping[str, Any]], Mapping[str, Any]]
ActionExecutor = Callable[
    [Mapping[str, Any], str, Mapping[str, Any], Mapping[str, Any]], Any
]
EvidenceReader = Callable[
    [Mapping[str, Any], str, Mapping[str, Any], Any], Mapping[str, Any]
]
PublicResultProjector = Callable[
    [Mapping[str, Any], str, Mapping[str, Any], Any], Mapping[str, Any]
]
CheckpointRestorer = Callable[
    [Mapping[str, Any], str, Mapping[str, Any], BaseException],
    Optional[Mapping[str, Any]],
]
ExactCheckpointPruner = Callable[..., Any]
ExactTimelineSyncExecutor = Callable[
    [Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]], Any
]


def _canonical_json(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        if abs(value) > 9_007_199_254_740_991:
            raise TypeError(
                "Timeline/Version integer exceeds the canonical JSON range."
            )
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("Timeline/Version number must be finite.")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("Timeline/Version object keys must be strings.")
        return {key: _canonical_json(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical_json(item) for item in value]
    raise TypeError("Timeline/Version descriptor data must be canonical JSON.")


def _ordered_kernel_targets(prepared: Mapping[str, Any]) -> list[dict[str, Any]]:
    project_id = prepared["projectId"]
    timeline_id = prepared.get("timelineId")
    return [
        {
            "kind": target["kind"],
            "stableId": target["stableId"],
            "revision": target["revision"],
            "projectId": project_id,
            "timelineId": timeline_id,
        }
        for target in prepared["resolvedTargets"]
    ]


def _assert_public_result_projection(value: Any) -> None:
    forbidden = {
        "argv",
        "command",
        "commandId",
        "commandPath",
        "engine",
        "lowering",
        "preState",
        "verificationPlan",
        "recoveryPlan",
    }

    def visit(current: Any) -> None:
        if isinstance(current, Mapping):
            if forbidden.intersection(current):
                raise ValueError(
                    "Timeline/Version public result contains private runtime data."
                )
            for item in current.values():
                visit(item)
        elif isinstance(current, list):
            for item in current:
                visit(item)
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
                raise ValueError(
                    "Timeline/Version public result contains a private local path."
                )

    visit(value)


@dataclass(frozen=True)
class TimelineVersionPreparedActionDescriptor:
    """An eight-stage descriptor composed only after every callback is real."""

    descriptor: TimelineVersionMutationDescriptor
    input_validator: InputValidator
    authority_resolver: AuthorityResolver
    impact_builder: ImpactBuilder
    action_executor: ActionExecutor
    evidence_reader: EvidenceReader
    public_result_projector: PublicResultProjector
    checkpoint_restorer: CheckpointRestorer
    exact_checkpoint_pruner: ExactCheckpointPruner
    exact_timeline_sync_executor: ExactTimelineSyncExecutor

    operation_class = "mutation"
    version = 1

    @property
    def capability_id(self) -> str | None:
        if self.descriptor.family == "version":
            return "version.checkpoint"
        metadata = PREPARED_ACTION_ACTION_METADATA.get(self.descriptor.action_id)
        return metadata.get("capabilityId") if metadata is not None else None

    def validate_input(self, value: Any) -> dict[str, Any]:
        normalized = self.input_validator(self.descriptor.action_id, value)
        if not isinstance(normalized, Mapping):
            raise TypeError("Timeline/Version input validation must return an object.")
        return _canonical_json(normalized)

    def _prepare_domain(
        self, context: Mapping[str, Any], value: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        authority = self.authority_resolver(context, self.descriptor.action_id, value)
        return prepare_timeline_version_action(
            self.descriptor.action_id, value, authority
        )

    def prepare(
        self, context: Mapping[str, Any], value: Mapping[str, Any]
    ) -> dict[str, Any]:
        domain = self._prepare_domain(context, value)
        normalized_input = dict(value)
        if self.descriptor.command_id == "version.restore":
            checkpoint_session_id = domain.get("checkpointSessionId")
            if not isinstance(checkpoint_session_id, str) or not checkpoint_session_id:
                raise ValueError("Version restore checkpoint owner is unavailable.")
            normalized_input["sessionId"] = checkpoint_session_id
        effect = _canonical_json(public_timeline_version_policy_effect(domain))
        impact = _canonical_json(
            self.impact_builder(context, self.descriptor.action_id, effect)
        )
        if (
            not isinstance(impact, dict)
            or impact.get("status") != "mutation"
            or impact.get("effects") != [effect]
            or impact.get("complete") is not True
            or impact.get("closedComposition") is not True
            or impact.get("ambiguous") is not False
            or impact.get("broad") is not False
            or impact.get("executableStableTargetPrecondition") is not True
        ):
            raise ValueError("Timeline/Version Mutation Policy impact is incomplete.")
        return {
            "targets": _ordered_kernel_targets(domain),
            "preState": _canonical_json(domain["privateCanonicalPreState"]),
            "impact": impact,
            "lowering": {
                "commandId": self.descriptor.command_id,
                "normalizedInput": _canonical_json(normalized_input),
                **(
                    {
                        "nativeProjectId": _version_native_identity(context)[0],
                        "nativeTimelineId": _version_native_identity(context)[1],
                    }
                    if self.descriptor.family == "version"
                    and "privateBindings" in context
                    else {}
                ),
                **(
                    {"resolvedCheckpointIds": list(domain["resolvedCheckpointIds"])}
                    if "resolvedCheckpointIds" in domain
                    else {}
                ),
                **(
                    {"expectedCurrentStateHash": domain["expectedCurrentStateHash"]}
                    if "expectedCurrentStateHash" in domain
                    else {}
                ),
                **(
                    {"checkpointBindingDigest": domain["checkpointBindingDigest"]}
                    if "checkpointBindingDigest" in domain
                    else {}
                ),
                **(
                    {
                        "parentCheckpointBindingDigest": domain[
                            "parentCheckpointBindingDigest"
                        ]
                    }
                    if "parentCheckpointBindingDigest" in domain
                    else {}
                ),
                **(
                    {
                        "syncPlanDigest": domain["syncPlanDigest"],
                        "affectedTrackTypes": list(domain["affectedTrackTypes"]),
                        "executionProfile": domain["privateExecutionProfile"],
                    }
                    if "syncPlanDigest" in domain
                    else {}
                ),
            },
            "verification": {
                "minimumEvidence": list(domain["minimumEvidence"]),
                "protectedState": list(domain["protectedState"]),
            },
            "recovery": {
                "checkpointPolicy": domain["checkpointPolicy"],
                "strategy": domain["recovery"],
                **(
                    {"checkpointId": domain["checkpointId"]}
                    if "checkpointId" in domain
                    else {}
                ),
            },
            "domain": _canonical_json(domain),
        }

    def resolve_current(
        self, context: Mapping[str, Any], prepared: Mapping[str, Any]
    ) -> dict[str, Any]:
        value = prepared.get("lowering", {}).get("normalizedInput")
        if not isinstance(value, Mapping):
            raise TypeError("Prepared Timeline/Version input is unavailable.")
        domain = self._prepare_domain(context, value)
        return {
            "targets": _ordered_kernel_targets(domain),
            "preState": _canonical_json(domain["privateCanonicalPreState"]),
        }

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        lowering = prepared.get("lowering")
        if (
            not isinstance(lowering, Mapping)
            or lowering.get("commandId") != self.descriptor.command_id
        ):
            raise ValueError("Prepared Timeline/Version lowering is unavailable.")
        value = lowering.get("normalizedInput")
        if not isinstance(value, Mapping):
            raise TypeError("Prepared Timeline/Version input is unavailable.")
        if self.descriptor.command_id == "version.prune":
            checkpoint_ids = lowering.get("resolvedCheckpointIds")
            session_id = value.get("sessionId")
            if (
                not isinstance(checkpoint_ids, list)
                or not checkpoint_ids
                or not isinstance(session_id, str)
                or not session_id
            ):
                raise ValueError("Prepared exact checkpoint pruning is unavailable.")
            if "privateBindings" in context:
                conn = get_connection(require_project=True, require_timeline=True)
                status = _version_status_for_bound_native_context(context, conn)
                return self.exact_checkpoint_pruner(
                    session_id,
                    tuple(checkpoint_ids),
                    project_name=str(status["project_name"]),
                    timeline_id=str(status["timeline_id"]),
                )
            return self.exact_checkpoint_pruner(session_id, tuple(checkpoint_ids))
        if self.descriptor.command_id == "timeline.sync_clips":
            if lowering.get("executionProfile") != "sdk_timeline_sync_exact_v1":
                raise ValueError(
                    "Prepared exact Timeline synchronization is unavailable."
                )
            return self.exact_timeline_sync_executor(context, value, prepared)
        return self.action_executor(
            context, self.descriptor.command_id, value, prepared
        )

    def verify(
        self,
        context: Mapping[str, Any],
        prepared: Mapping[str, Any],
        result: Any,
    ) -> dict[str, Any]:
        evidence = self.evidence_reader(
            context, self.descriptor.action_id, prepared, result
        )
        verification = verify_timeline_version_protected_state(
            prepared["domain"], evidence
        )
        evidence_digest = (
            "sha256:"
            + hashlib.sha256(
                json.dumps(
                    _canonical_json(evidence),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
        )
        return {
            "outcome": verification["outcome"],
            "evidence": [
                {
                    "modality": "readback",
                    "digest": evidence_digest,
                    "summary": "Exact checkpoint and protected-state readback completed.",
                }
            ],
            "protectedStatePreserved": verification["protectedStatePreserved"],
        }

    def recover(
        self,
        context: Mapping[str, Any],
        prepared: Mapping[str, Any],
        failure: BaseException,
    ) -> dict[str, Any]:
        possible_mutation = getattr(failure, "possible_mutation", "possible")
        if possible_mutation not in {"none", "possible", "partial", "confirmed"}:
            possible_mutation = "possible"
        checkpoint_restore = (
            prepared["domain"].get("checkpointPolicy") == "checkpoint_restore"
        )
        evidence = (
            self.checkpoint_restorer(
                context, self.descriptor.action_id, prepared, failure
            )
            if possible_mutation != "none" and checkpoint_restore
            else None
        )
        recovery = evaluate_timeline_version_recovery(
            prepared["domain"],
            possible_mutation=possible_mutation,
            restore_evidence=evidence,
        )
        return {
            "outcome": "succeeded"
            if recovery["status"] == "restored"
            else recovery["status"],
            "attempted": possible_mutation != "none",
            "manualActionRequired": recovery["manualRecoveryRequired"],
        }

    def project_result(
        self,
        context: Mapping[str, Any],
        prepared: Mapping[str, Any],
        result: Any,
    ) -> dict[str, Any]:
        """Return only the domain owner's closed public result projection."""

        projected = self.public_result_projector(
            context, self.descriptor.action_id, prepared, result
        )
        if not isinstance(projected, Mapping):
            raise TypeError("Timeline/Version public result must be an object.")
        canonical = _canonical_json(projected)
        if canonical.get("actionId") != self.descriptor.action_id:
            raise ValueError(
                "Timeline/Version public result must bind the exact action ID."
            )
        _assert_public_result_projection(canonical)
        return canonical

    def validate_public_result(self, value: Any) -> bool:
        """Fail closed against the exact public Timeline/Version result contract."""

        try:
            canonical = _canonical_json(value)
            _assert_public_result_projection(canonical)
            if self.descriptor.family == "version":
                return _validate_version_public_result(
                    self.descriptor.action_id, canonical
                )
            schema = timeline_action_result_schema(
                self.descriptor.action_id, self.descriptor.command_id
            )
            return schema is not None and not list(
                Draft202012Validator(schema).iter_errors(canonical)
            )
        except (KeyError, TypeError, ValueError):
            return False


def timeline_version_prepared_action_descriptors(
    *,
    input_validator: InputValidator,
    authority_resolver: AuthorityResolver,
    impact_builder: ImpactBuilder,
    action_executor: ActionExecutor,
    evidence_reader: EvidenceReader,
    public_result_projector: PublicResultProjector,
    checkpoint_restorer: CheckpointRestorer,
    exact_checkpoint_pruner: ExactCheckpointPruner,
    exact_timeline_sync_executor: ExactTimelineSyncExecutor,
) -> Mapping[str, TimelineVersionPreparedActionDescriptor]:
    """Compose descriptors after production supplies every private callback."""

    return MappingProxyType(
        {
            action_id: TimelineVersionPreparedActionDescriptor(
                descriptor=descriptor,
                input_validator=input_validator,
                authority_resolver=authority_resolver,
                impact_builder=impact_builder,
                action_executor=action_executor,
                evidence_reader=evidence_reader,
                public_result_projector=public_result_projector,
                checkpoint_restorer=checkpoint_restorer,
                exact_checkpoint_pruner=exact_checkpoint_pruner,
                exact_timeline_sync_executor=exact_timeline_sync_executor,
            )
            for action_id, descriptor in TIMELINE_VERSION_MUTATION_DESCRIPTORS.items()
        }
    )


@dataclass(frozen=True)
class UnavailableTimelineVersionPreparedActionDescriptor:
    """Intentional incomplete marker consumed by the sole frozen registry."""

    operation_class = "mutation"
    version = 1
    reason: str


def _unavailable_reason(descriptor: TimelineVersionMutationDescriptor) -> str:
    command_id = descriptor.command_id
    if descriptor.artifact_destination:
        gap = "exact_artifact_custody_and_destination_readback_adapter_missing"
    elif descriptor.family == "version":
        gap = "durable_checkpoint_authority_and_public_result_adapter_missing"
    elif command_id == "timeline.sync_clips":
        gap = "exact_sync_placement_execution_and_post_timeline_readback_missing"
    elif command_id == "timeline.dolby.analyze":
        gap = "exact_clip_analysis_readback_without_project_control_mutation_missing"
    elif descriptor.family == "multi_target":
        gap = "closed_multi_target_live_resolution_and_recovery_adapter_missing"
    elif descriptor.exact_track:
        gap = "exact_track_live_resolution_and_protected_state_readback_missing"
    else:
        gap = "exact_live_authority_execution_and_result_projection_missing"
    return f"{command_id}:{gap}"


_VERSION_PRUNE_ACTION_ID = "cutagent.action.version.prune"
_VERSION_CREATE_ACTION_ID = "cutagent.action.version.create"
_VERSION_RESTORE_ACTION_ID = "cutagent.action.version.restore"


def _runtime_identity(
    context: Mapping[str, Any], section: str, id_key: str, revision_key: str
) -> dict[str, str]:
    value = context.get(section)
    if not isinstance(value, Mapping):
        raise ValueError(f"Signed runtime {section} identity is unavailable.")
    identity = value.get(id_key)
    revision = value.get(revision_key)
    if (
        not isinstance(identity, str)
        or not identity
        or not isinstance(revision, str)
        or not revision
    ):
        raise ValueError(f"Signed runtime {section} identity is incomplete.")
    return {"id": identity, "revision": revision}


def _current_sdk_session_id(context: Mapping[str, Any]) -> str:
    session = context.get("session")
    session_id = session.get("sessionId") if isinstance(session, Mapping) else None
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("Signed runtime SDK session identity is unavailable.")
    return session_id


def _bind_current_sdk_session(
    context: Mapping[str, Any], value: Mapping[str, Any]
) -> tuple[str, dict[str, Any]]:
    session_id = _current_sdk_session_id(context)
    requested = value.get("sessionId")
    if requested is not None and requested != session_id:
        raise ValueError("Version action cannot target another SDK session.")
    return session_id, {**dict(value), "sessionId": session_id}


def _bind_checkpoint_owner_session(
    context: Mapping[str, Any],
    value: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Bind restore to the current transport or a durable workflow owner."""

    current_session_id = _current_sdk_session_id(context)
    requested = value.get("sessionId")
    bindings = context.get("privateBindings")
    ownership = (
        bindings.get("checkpointOwnership")
        if isinstance(bindings, Mapping)
        else None
    )
    project_id = context.get("project", {}).get("projectId")
    timeline_id = context.get("timeline", {}).get("timelineId")
    ownership_authority = (
        ownership.get("authority") if isinstance(ownership, Mapping) else None
    )
    if ownership_authority == "sdk_transport_session_account_binding_v1":
        if requested is not None and requested != current_session_id:
            raise ValueError("Version restore cannot change its transport owner.")
        requested = current_session_id
        if (
            ownership.get("sessionId") != current_session_id
            or ownership.get("projectId") != project_id
            or ownership.get("timelineId") != timeline_id
        ):
            raise ValueError("Version restore transport ownership is unavailable.")
    elif ownership_authority == "sdk_workflow_account_binding_v1":
        if (
            not isinstance(requested, str)
            or not requested.strip()
            or len(requested) > 256
        ):
            raise ValueError("Version restore workflow owner is invalid.")
        requested = requested.strip()
        if (
            not isinstance(ownership, Mapping)
            or ownership.get("authority") != "sdk_workflow_account_binding_v1"
            or ownership.get("workflowId") != requested
            or ownership.get("projectId") != project_id
            or ownership.get("timelineId") != timeline_id
        ):
            raise ValueError(
                "Version restore durable workflow ownership is unavailable."
            )
    else:
        raise ValueError("Version restore ownership is unavailable.")
    checkpoint_session_id = checkpoint.get("session_id")
    if (
        not isinstance(checkpoint_session_id, str)
        or not checkpoint_session_id.strip()
        or len(checkpoint_session_id) > 256
    ):
        raise ValueError("Version restore checkpoint session identity is unavailable.")
    checkpoint_session_id = checkpoint_session_id.strip()
    if requested != checkpoint_session_id:
        raise ValueError("Version restore checkpoint belongs to another session.")
    return checkpoint_session_id, {
        **dict(value),
        "sessionId": checkpoint_session_id,
    }


def _validate_version_prune_input(action_id: str, value: Any) -> Mapping[str, Any]:
    if action_id != _VERSION_PRUNE_ACTION_ID or not isinstance(value, Mapping):
        raise ValueError("Version prune input is unavailable.")
    if set(value) != {"sessionId"}:
        raise ValueError("Version prune accepts only sessionId.")
    session_id = value.get("sessionId")
    if (
        not isinstance(session_id, str)
        or not session_id.strip()
        or len(session_id) > 256
    ):
        raise ValueError("Version prune requires a non-empty sessionId.")
    return {"sessionId": session_id.strip()}


def _validate_version_create_input(action_id: str, value: Any) -> Mapping[str, Any]:
    if action_id != _VERSION_CREATE_ACTION_ID or not isinstance(value, Mapping):
        raise ValueError("Version create input is unavailable.")
    allowed = {
        "label",
        "kind",
        "sessionId",
        "promptEventId",
        "parentCheckpointId",
    }
    if not set(value).issubset(allowed):
        raise ValueError("Version create input contains unknown fields.")
    normalized = dict(value)
    kind = normalized.get("kind", "manual_commit")
    if kind not in {"before_prompt", "after_prompt", "manual_commit"}:
        raise ValueError("Version create checkpoint kind is invalid.")
    normalized["kind"] = kind
    for key in allowed - {"kind"}:
        candidate = normalized.get(key)
        maximum = 1024 if key == "label" else 256
        if candidate is not None and (
            not isinstance(candidate, str) or not candidate or len(candidate) > maximum
        ):
            raise ValueError(f"Version create {key} is invalid.")
    return normalized


def _validate_version_restore_input(action_id: str, value: Any) -> Mapping[str, Any]:
    if action_id != _VERSION_RESTORE_ACTION_ID or not isinstance(value, Mapping):
        raise ValueError("Version restore input is unavailable.")
    if not set(value).issubset({"checkpointId", "sessionId"}):
        raise ValueError("Version restore input contains unknown fields.")
    checkpoint_id = value.get("checkpointId")
    session_id = value.get("sessionId")
    if (
        not isinstance(checkpoint_id, str)
        or not checkpoint_id.strip()
        or len(checkpoint_id) > 256
    ):
        raise ValueError("Version restore requires checkpointId.")
    if session_id is not None and (
        not isinstance(session_id, str)
        or not session_id.strip()
        or len(session_id) > 256
    ):
        raise ValueError("Version restore workflow sessionId is invalid.")
    return {
        "checkpointId": checkpoint_id.strip(),
        **({"sessionId": session_id.strip()} if isinstance(session_id, str) else {"sessionId": None}),
    }


def _version_base_authority(
    context: Mapping[str, Any],
    value: Mapping[str, Any],
    *,
    bound_checkpoint: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    project = _runtime_identity(context, "project", "projectId", "projectRevision")
    timeline = _runtime_identity(context, "timeline", "timelineId", "timelineRevision")
    targets = [
        {
            "kind": "project",
            "stableId": project["id"],
            "publicId": project["id"],
            "revision": project["revision"],
        },
        {
            "kind": "timeline",
            "stableId": timeline["id"],
            "publicId": timeline["id"],
            "revision": timeline["revision"],
        },
    ]
    protected_digest = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                _canonical_json(
                    {
                        "project": project,
                        "timeline": timeline,
                        "input": value,
                        **(
                            {"boundCheckpoint": bound_checkpoint}
                            if bound_checkpoint is not None
                            else {}
                        ),
                    }
                ),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
    )
    return {
        "project": project,
        "timeline": timeline,
        "resolvedTargets": targets,
        "stale": False,
        "ambiguous": False,
        "broad": False,
        "complete": True,
        "closedComposition": False,
        "linkedTopologyComplete": False,
        "artifactDestinationExact": False,
        "durableWorkflowAuthority": "sdk_workflow_v1",
        "privatePreState": {
            "targetStableIds": sorted(target["stableId"] for target in targets),
            "protectedStateDigest": protected_digest,
            "activeContext": {
                "projectId": project["id"],
                "timelineId": timeline["id"],
            },
            **(dict(bound_checkpoint) if bound_checkpoint is not None else {}),
        },
    }


def _version_native_identity(context: Mapping[str, Any]) -> tuple[str, str]:
    bindings = context.get("privateBindings")
    native_project_id = (
        bindings.get("nativeProjectId") if isinstance(bindings, Mapping) else None
    )
    native_timeline_id = (
        bindings.get("nativeTimelineId") if isinstance(bindings, Mapping) else None
    )
    if (
        not isinstance(native_project_id, str)
        or not native_project_id
        or not isinstance(native_timeline_id, str)
        or not native_timeline_id
    ):
        raise ValueError(
            "Version mutation has no exact private native project and timeline binding."
        )
    return native_project_id, native_timeline_id


def _version_status_for_bound_native_context(
    context: Mapping[str, Any], conn: Any
) -> Mapping[str, Any]:
    native_project_id, native_timeline_id = _version_native_identity(context)
    status = version_ops.version_status(conn, include_private_identity=True)
    if (
        not isinstance(status, Mapping)
        or status.get("project_id") != native_project_id
        or status.get("timeline_id") != native_timeline_id
    ):
        raise ValueError("Version mutation native project or timeline identity changed.")
    return status


def _version_create_authority(
    context: Mapping[str, Any], action_id: str, value: Mapping[str, Any]
) -> Mapping[str, Any]:
    if action_id != _VERSION_CREATE_ACTION_ID:
        raise ValueError("Only Version create is production-bound here.")
    session_id, bound_value = _bind_current_sdk_session(context, value)
    parent_id = bound_value.get("parentCheckpointId")
    conn = get_connection(require_project=True, require_timeline=True)
    if parent_id is None:
        _version_status_for_bound_native_context(context, conn)
        return _version_base_authority(context, bound_value)
    parent = version_ops.inspect_checkpoint(str(parent_id))
    if not isinstance(parent, Mapping) or parent.get("id") != parent_id:
        raise ValueError("Version create parent checkpoint identity is unavailable.")
    if parent.get("session_id") != session_id:
        raise ValueError("Version create parent checkpoint belongs to another session.")
    status = _version_status_for_bound_native_context(context, conn)
    if (
        not isinstance(status, Mapping)
        or parent.get("project_name") != status.get("project_name")
        or parent.get("timeline_id") != status.get("timeline_id")
    ):
        raise ValueError(
            "Version create parent checkpoint is outside the active context."
        )
    parent_digest = version_ops.checkpoint_binding_digest(dict(parent))
    authority = _version_base_authority(
        context,
        bound_value,
        bound_checkpoint={"parentCheckpointBindingDigest": parent_digest},
    )
    authority.update(
        {
            "resolvedParentCheckpointId": parent_id,
            "parentCheckpointBindingDigest": parent_digest,
        }
    )
    return authority


def _version_restore_authority(
    context: Mapping[str, Any], action_id: str, value: Mapping[str, Any]
) -> Mapping[str, Any]:
    if action_id != _VERSION_RESTORE_ACTION_ID:
        raise ValueError("Only Version restore is production-bound here.")
    checkpoint = version_ops.inspect_checkpoint(str(value["checkpointId"]))
    if (
        not isinstance(checkpoint, Mapping)
        or checkpoint.get("id") != value["checkpointId"]
    ):
        raise ValueError("Version restore checkpoint identity is unavailable.")
    session_id, bound_value = _bind_checkpoint_owner_session(
        context, value, checkpoint
    )
    conn = get_connection(require_project=True, require_timeline=True)
    status = _version_status_for_bound_native_context(context, conn)
    if (
        not isinstance(status, Mapping)
        or checkpoint.get("project_name") != status.get("project_name")
        or checkpoint.get("timeline_id") != status.get("timeline_id")
    ):
        raise ValueError(
            "Version restore checkpoint does not match the active context."
        )
    expected_hash = status.get("state_hash")
    if not isinstance(expected_hash, str) or not expected_hash.startswith("sha256:"):
        raise ValueError("Version restore current project state hash is unavailable.")
    checkpoint_digest = version_ops.checkpoint_binding_digest(dict(checkpoint))
    authority = _version_base_authority(
        context,
        bound_value,
        bound_checkpoint={"checkpointBindingDigest": checkpoint_digest},
    )
    authority.update(
        {
            "resolvedCheckpointId": checkpoint["id"],
            "resolvedCheckpointSessionId": session_id,
            "checkpointBindingDigest": checkpoint_digest,
            "expectedCurrentStateHash": expected_hash,
            "projectStateHash": expected_hash,
        }
    )
    return authority


def _version_prune_authority(
    context: Mapping[str, Any], action_id: str, value: Mapping[str, Any]
) -> Mapping[str, Any]:
    if action_id != _VERSION_PRUNE_ACTION_ID:
        raise ValueError("Only exact Version prune is production-bound here.")
    session_id, bound_value = _bind_current_sdk_session(context, value)
    project = _runtime_identity(context, "project", "projectId", "projectRevision")
    timeline = _runtime_identity(context, "timeline", "timelineId", "timelineRevision")
    conn = get_connection(require_project=True, require_timeline=True)
    status = _version_status_for_bound_native_context(context, conn)
    if not isinstance(status, Mapping):
        raise ValueError("Version prune active project context is unavailable.")
    project_name = status.get("project_name")
    timeline_id = status.get("timeline_id")
    if not isinstance(project_name, str) or not project_name or not isinstance(timeline_id, str) or not timeline_id:
        raise ValueError("Version prune active project identity is incomplete.")
    checkpoints = version_ops.list_checkpoints(session_id=session_id)
    if not isinstance(checkpoints, list) or not checkpoints:
        raise ValueError("Version prune has no exact retained checkpoint set.")
    checkpoint_ids: list[str] = []
    for row in checkpoints:
        if not isinstance(row, Mapping) or row.get("session_id") != session_id:
            raise ValueError("Version prune checkpoint session inventory is incomplete.")
        if row.get("project_name") != project_name or row.get("timeline_id") != timeline_id:
            continue
        checkpoint_id = row.get("id") if isinstance(row, Mapping) else None
        if not isinstance(checkpoint_id, str) or not checkpoint_id:
            raise ValueError("Version prune checkpoint inventory is incomplete.")
        checkpoint_ids.append(checkpoint_id)
    if not checkpoint_ids:
        raise ValueError("Version prune has no retained checkpoints in the active context.")
    if len(set(checkpoint_ids)) != len(checkpoint_ids):
        raise ValueError("Version prune checkpoint inventory is ambiguous.")
    checkpoint_ids.sort()
    targets = [
        {
            "kind": "project",
            "stableId": project["id"],
            "publicId": project["id"],
            "revision": project["revision"],
        },
        {
            "kind": "timeline",
            "stableId": timeline["id"],
            "publicId": timeline["id"],
            "revision": timeline["revision"],
        },
    ]
    protected_digest = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                _canonical_json(
                    {
                        "project": project,
                        "timeline": timeline,
                        "sessionId": bound_value["sessionId"],
                        "checkpointIds": checkpoint_ids,
                    }
                ),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
    )
    return {
        "project": project,
        "timeline": timeline,
        "resolvedTargets": targets,
        "stale": False,
        "ambiguous": False,
        "broad": False,
        "complete": True,
        "closedComposition": True,
        "linkedTopologyComplete": False,
        "artifactDestinationExact": False,
        "durableWorkflowAuthority": "sdk_workflow_v1",
        "checkpointHistoryComplete": True,
        "resolvedCheckpointIds": checkpoint_ids,
        "privatePreState": {
            "targetStableIds": sorted(target["stableId"] for target in targets),
            "protectedStateDigest": protected_digest,
            "activeContext": {
                "projectId": project["id"],
                "timelineId": timeline["id"],
            },
            "resolvedCheckpointIds": checkpoint_ids,
        },
    }


def _version_prune_impact(
    context: Mapping[str, Any], action_id: str, effect: Mapping[str, Any]
) -> Mapping[str, Any]:
    if action_id not in {
        _VERSION_CREATE_ACTION_ID,
        _VERSION_PRUNE_ACTION_ID,
        _VERSION_RESTORE_ACTION_ID,
    }:
        raise ValueError("Only production-bound Version actions are accepted here.")
    mutation_base = context.get("mutationBase")
    request_binding = context.get("exactRequestBinding")
    if not isinstance(mutation_base, Mapping) or not isinstance(
        request_binding, Mapping
    ):
        raise ValueError("Version mutation requires the immutable carrier binding.")
    required_base_keys = {
        "contractVersion",
        "carrier",
        "minimumBinding",
        "registryDigest",
        "canonicalRequestDigest",
        "referencedPayloadDigests",
        "requestId",
        "operationId",
        "executionId",
        "scopeId",
        "scopeRevision",
        "projectLibraryId",
        "projectId",
        "timelineId",
        "projectRevision",
        "timelineRevision",
    }
    if set(mutation_base) != required_base_keys:
        raise ValueError("Version mutation carrier binding shape is incomplete.")
    if (
        mutation_base.get("contractVersion") != 1
        or mutation_base.get("carrier") != "sdk"
        or mutation_base.get("minimumBinding") != "project+timeline"
    ):
        raise ValueError("Version mutation carrier binding level is invalid.")
    identities = request_binding.get("identities")
    revisions = request_binding.get("revisions")
    if not isinstance(identities, Mapping) or not isinstance(revisions, Mapping):
        raise ValueError("Version mutation request identity binding is incomplete.")
    expected = {
        "requestId": request_binding.get("requestId"),
        "operationId": request_binding.get("operationId"),
        "executionId": request_binding.get("executionId"),
        "projectLibraryId": identities.get("projectLibraryId"),
        "projectId": identities.get("projectId"),
        "timelineId": identities.get("timelineId"),
        "projectRevision": revisions.get("project"),
        "timelineRevision": revisions.get("timeline"),
    }
    if request_binding.get("actionId") != action_id or any(
        mutation_base.get(key) != value for key, value in expected.items()
    ):
        raise ValueError("Version mutation carrier binding drifted from its request.")
    request_target_ids = identities.get("targetIds")
    target_revisions = revisions.get("targets")
    effect_targets = effect.get("targets")
    if (
        not isinstance(request_target_ids, (list, tuple))
        or not isinstance(target_revisions, Mapping)
        or not isinstance(effect_targets, (list, tuple))
    ):
        raise ValueError("Version mutation target binding is incomplete.")
    effect_target_revisions = {
        target.get("stableId"): target.get("revision")
        for target in effect_targets
        if isinstance(target, Mapping)
    }
    if (
        len(effect_target_revisions) != len(effect_targets)
        or set(request_target_ids) != set(effect_target_revisions)
        or any(
            target_revisions.get(target_id) != revision
            for target_id, revision in effect_target_revisions.items()
        )
    ):
        raise ValueError("Version mutation target binding drifted from its effect.")
    referenced_payload_digests = mutation_base.get("referencedPayloadDigests")
    if not isinstance(referenced_payload_digests, (list, tuple)) or any(
        not isinstance(digest, str)
        or len(digest) != 71
        or not digest.startswith("sha256:")
        for digest in referenced_payload_digests
    ):
        raise ValueError("Version mutation payload binding is invalid.")
    return {
        **dict(mutation_base),
        "status": "mutation",
        "effects": [dict(effect)],
        "complete": True,
        "verificationPolicy": {
            "minimumEvidence": ["readback"],
            "requireProtectedStatePreserved": True,
            "protectedTargetEvidence": "every_declared_target",
        },
        "closedComposition": True,
        "ambiguous": False,
        "broad": False,
        "executableStableTargetPrecondition": True,
    }


def _version_action_execute(
    _context: Mapping[str, Any],
    command_id: str,
    value: Mapping[str, Any],
    _prepared: Mapping[str, Any],
) -> Any:
    if command_id == "version.create":
        session_id, _ = _bind_current_sdk_session(_context, value)
        conn = get_connection(require_project=True, require_timeline=True)
        _version_status_for_bound_native_context(_context, conn)
        return version_ops.create_checkpoint(
            conn,
            label=str(value.get("label") or ""),
            kind=str(value.get("kind") or "manual_commit"),
            session_id=session_id,
            prompt_event_id=value.get("promptEventId"),
            parent_checkpoint_id=value.get("parentCheckpointId"),
            expected_parent_checkpoint_digest=_prepared.get("lowering", {}).get(
                "parentCheckpointBindingDigest"
            ),
        )
    if command_id == "version.restore":
        session_id = value.get("sessionId")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("Prepared Version restore session identity is unavailable.")
        conn = get_connection(require_project=True, require_timeline=True)
        _version_status_for_bound_native_context(_context, conn)
        expected_hash = _prepared.get("lowering", {}).get("expectedCurrentStateHash")
        checkpoint_digest = _prepared.get("lowering", {}).get("checkpointBindingDigest")
        if not isinstance(expected_hash, str) or not expected_hash:
            raise ValueError("Prepared Version restore state hash is unavailable.")
        if not isinstance(checkpoint_digest, str) or not checkpoint_digest:
            raise ValueError(
                "Prepared Version restore checkpoint binding is unavailable."
            )
        return version_ops.restore_checkpoint(
            conn,
            str(value["checkpointId"]),
            session_id=session_id,
            expected_current_state_hash=expected_hash,
            expected_checkpoint_digest=checkpoint_digest,
        )
    raise ValueError("This Version production executor does not own the action.")


def _unsupported_production_execute(*_args: Any) -> Any:
    raise ValueError("No generic Timeline/Version production executor is registered.")


def _version_prune_evidence(
    context: Mapping[str, Any],
    action_id: str,
    prepared: Mapping[str, Any],
    result: Any,
) -> Mapping[str, Any]:
    if action_id != _VERSION_PRUNE_ACTION_ID or not isinstance(result, Mapping):
        raise ValueError("Version prune result evidence is unavailable.")
    lowering = prepared.get("lowering")
    if not isinstance(lowering, Mapping):
        raise ValueError("Version prune lowering is unavailable.")
    prepared_ids = set(lowering.get("resolvedCheckpointIds") or ())
    remaining = version_ops.list_checkpoints()
    remaining_ids = {str(row.get("id") or "") for row in remaining}
    project = _runtime_identity(context, "project", "projectId", "projectRevision")
    timeline = _runtime_identity(context, "timeline", "timelineId", "timelineRevision")
    domain = prepared["domain"]
    exact = (
        bool(prepared_ids)
        and prepared_ids.isdisjoint(remaining_ids)
        and int(result.get("pruned_checkpoint_count", -1)) == len(prepared_ids)
        and int(result.get("remaining_checkpoint_count", -1)) == len(remaining)
        and int(result.get("failed_snapshot_delete_count", -1)) == 0
    )
    context_matched = (
        project["id"] == domain["projectId"]
        and project["revision"] == domain["projectRevision"]
        and timeline["id"] == domain["timelineId"]
        and timeline["revision"] == domain["timelineRevision"]
    )
    passed = exact and context_matched
    return {
        "targetMatched": passed,
        "authorizationBound": True,
        "modalities": list(domain["minimumEvidence"]) if passed else [],
        "protectedState": {
            "checkpoint_history": exact,
            "project_identity": context_matched,
            "timeline_identity": context_matched,
            "active_context": context_matched,
        },
    }


def _version_prune_public_result(
    _context: Mapping[str, Any],
    action_id: str,
    prepared: Mapping[str, Any],
    result: Any,
) -> Mapping[str, Any]:
    if action_id != _VERSION_PRUNE_ACTION_ID or not isinstance(result, Mapping):
        raise ValueError("Version prune public result is unavailable.")
    session_id = (
        prepared.get("lowering", {}).get("normalizedInput", {}).get("sessionId")
    )
    pruned = int(result.get("pruned_checkpoint_count", -1))
    remaining = int(result.get("remaining_checkpoint_count", -1))
    if not isinstance(session_id, str) or pruned < 0 or remaining < 0:
        raise ValueError("Version prune public result is incomplete.")
    return {
        "actionId": action_id,
        "payload": {
            "status": "completed",
            "changed": pruned > 0,
            "target": {"sessionId": session_id},
            "data": {
                "prunedCheckpointCount": pruned,
                "remainingCheckpointCount": remaining,
            },
            "verification": {
                "outcome": "passed",
                "protectedState": "preserved",
                "evidence": [
                    {
                        "kind": "checkpoint_readback",
                        "summary": "Exact prepared checkpoints were absent after pruning.",
                    }
                ],
            },
            "recovery": {
                "state": "not_needed",
                "retry": "same_idempotency_key_required",
                "guidance": "No recovery is required for this completed result.",
            },
        },
    }


def _checkpoint_public(
    checkpoint: Mapping[str, Any], prepared: Mapping[str, Any]
) -> dict[str, Any]:
    project_id = str(prepared["domain"]["projectId"])
    timeline_id = str(prepared["domain"]["timelineId"])
    return {
        "id": str(checkpoint["id"]),
        "createdAt": str(checkpoint["created_at"]),
        "kind": str(checkpoint["kind"]),
        "project": {
            "id": project_id,
            "name": str(checkpoint["project_name"]),
        },
        "timeline": {
            "id": timeline_id,
            "name": str(checkpoint["timeline_name"]),
            "projectId": project_id,
        },
        "sessionId": checkpoint.get("session_id"),
        "promptEventId": checkpoint.get("prompt_event_id"),
        "label": str(checkpoint.get("label") or ""),
        "stateDigest": str(checkpoint["state_hash"]),
        "parentCheckpointId": checkpoint.get("parent_checkpoint_id"),
        "changedFromParent": checkpoint.get("changed_from_parent"),
    }


def _exact_keys(value: Any, keys: set[str]) -> bool:
    return isinstance(value, Mapping) and set(value) == keys


def _bounded_text(value: Any, maximum: int, *, nullable: bool = False) -> bool:
    return (nullable and value is None) or (
        isinstance(value, str) and 0 < len(value) <= maximum
    )


def _sdk_id(value: Any, prefix: str) -> bool:
    if not _bounded_text(value, 160) or not str(value).startswith(prefix):
        return False
    suffix = str(value)[len(prefix) :]
    return (
        bool(suffix)
        and suffix[0].isalnum()
        and all(character.isalnum() or character in "._~-" for character in suffix)
    )


def _checkpoint_result_shape(value: Any) -> bool:
    keys = {
        "id",
        "createdAt",
        "kind",
        "project",
        "timeline",
        "sessionId",
        "promptEventId",
        "label",
        "stateDigest",
        "parentCheckpointId",
        "changedFromParent",
    }
    if not _exact_keys(value, keys):
        return False
    project = value["project"]
    timeline = value["timeline"]
    return (
        _bounded_text(value["id"], 256)
        and _bounded_text(value["createdAt"], 64)
        and value["kind"] in {"before_prompt", "after_prompt", "manual_commit"}
        and _exact_keys(project, {"id", "name"})
        and _sdk_id(project["id"], "project_")
        and _bounded_text(project["name"], 1024)
        and _exact_keys(timeline, {"id", "projectId", "name"})
        and _sdk_id(timeline["id"], "timeline_")
        and timeline["projectId"] == project["id"]
        and _bounded_text(timeline["name"], 1024)
        and _bounded_text(value["sessionId"], 256, nullable=True)
        and _bounded_text(value["promptEventId"], 256, nullable=True)
        and _bounded_text(value["label"], 1024)
        and isinstance(value["stateDigest"], str)
        and len(value["stateDigest"]) == 71
        and value["stateDigest"].startswith("sha256:")
        and all(
            character in "0123456789abcdef" for character in value["stateDigest"][7:]
        )
        and _bounded_text(value["parentCheckpointId"], 256, nullable=True)
        and (
            value["changedFromParent"] is None
            or isinstance(value["changedFromParent"], bool)
        )
    )


def _completed_mutation_envelope(
    value: Any, action_id: str
) -> Mapping[str, Any] | None:
    if (
        not _exact_keys(value, {"actionId", "payload"})
        or value["actionId"] != action_id
    ):
        return None
    payload = value["payload"]
    if not _exact_keys(
        payload,
        {"status", "changed", "target", "data", "verification", "recovery"},
    ):
        return None
    verification = payload["verification"]
    recovery = payload["recovery"]
    evidence = (
        verification.get("evidence") if isinstance(verification, Mapping) else None
    )
    if (
        payload["status"] != "completed"
        or not isinstance(payload["changed"], bool)
        or not _exact_keys(verification, {"outcome", "protectedState", "evidence"})
        or verification["outcome"] != "passed"
        or verification["protectedState"] != "preserved"
        or not isinstance(evidence, list)
        or not 1 <= len(evidence) <= 32
        or any(
            not _exact_keys(item, {"kind", "summary"})
            or item["kind"]
            not in {
                "structural_readback",
                "artifact_readback",
                "context_readback",
                "checkpoint_readback",
                "manual_review",
            }
            or not _bounded_text(item["summary"], 500)
            for item in evidence
        )
        or not any(item.get("kind") == "checkpoint_readback" for item in evidence)
        or not _exact_keys(recovery, {"state", "retry", "guidance"})
        or recovery["state"] != "not_needed"
        or recovery["retry"] != "same_idempotency_key_required"
        or not _bounded_text(recovery["guidance"], 500)
    ):
        return None
    return payload


def _validate_version_public_result(action_id: str, value: Any) -> bool:
    payload = _completed_mutation_envelope(value, action_id)
    if payload is None:
        return False
    target = payload["target"]
    data = payload["data"]
    if action_id == _VERSION_CREATE_ACTION_ID:
        return (
            payload["changed"] is True
            and _exact_keys(target, {"id"})
            and _bounded_text(target["id"], 256)
            and _exact_keys(data, {"checkpoint"})
            and _checkpoint_result_shape(data["checkpoint"])
            and target["id"] == data["checkpoint"]["id"]
        )
    if action_id == _VERSION_PRUNE_ACTION_ID:
        return (
            _exact_keys(target, {"sessionId"})
            and _bounded_text(target["sessionId"], 256)
            and _exact_keys(data, {"prunedCheckpointCount", "remainingCheckpointCount"})
            and isinstance(data["prunedCheckpointCount"], int)
            and not isinstance(data["prunedCheckpointCount"], bool)
            and data["prunedCheckpointCount"] >= 0
            and isinstance(data["remainingCheckpointCount"], int)
            and not isinstance(data["remainingCheckpointCount"], bool)
            and data["remainingCheckpointCount"] >= 0
            and payload["changed"] == (data["prunedCheckpointCount"] > 0)
        )
    if action_id == _VERSION_RESTORE_ACTION_ID:
        return (
            payload["changed"] is True
            and _checkpoint_result_shape(target)
            and _exact_keys(data, {"reopened", "verified"})
            and data["reopened"] is True
            and data["verified"] is True
        )
    return False


def _version_create_evidence(
    context: Mapping[str, Any],
    action_id: str,
    prepared: Mapping[str, Any],
    result: Any,
) -> Mapping[str, Any]:
    if action_id != _VERSION_CREATE_ACTION_ID or not isinstance(result, Mapping):
        raise ValueError("Version create result evidence is unavailable.")
    checkpoint_id = result.get("id")
    persisted = version_ops.inspect_checkpoint(str(checkpoint_id or ""))
    project = _runtime_identity(context, "project", "projectId", "projectRevision")
    timeline = _runtime_identity(context, "timeline", "timelineId", "timelineRevision")
    domain = prepared["domain"]
    exact = persisted == result and bool(checkpoint_id)
    context_matched = (
        project["id"] == domain["projectId"]
        and project["revision"] == domain["projectRevision"]
        and timeline["id"] == domain["timelineId"]
        and timeline["revision"] == domain["timelineRevision"]
    )
    passed = exact and context_matched
    return {
        "targetMatched": passed,
        "authorizationBound": True,
        "modalities": list(domain["minimumEvidence"]) if passed else [],
        "protectedState": {
            "checkpoint_history": exact,
            "project_identity": context_matched,
            "timeline_identity": context_matched,
            "active_context": context_matched,
        },
    }


def _version_create_public_result(
    _context: Mapping[str, Any],
    action_id: str,
    prepared: Mapping[str, Any],
    result: Any,
) -> Mapping[str, Any]:
    if action_id != _VERSION_CREATE_ACTION_ID or not isinstance(result, Mapping):
        raise ValueError("Version create public result is unavailable.")
    checkpoint = _checkpoint_public(result, prepared)
    return {
        "actionId": action_id,
        "payload": {
            "status": "completed",
            "changed": True,
            "target": {"id": checkpoint["id"]},
            "data": {"checkpoint": checkpoint},
            "verification": {
                "outcome": "passed",
                "protectedState": "preserved",
                "evidence": [
                    {
                        "kind": "checkpoint_readback",
                        "summary": "Created checkpoint matched durable readback.",
                    }
                ],
            },
            "recovery": {
                "state": "not_needed",
                "retry": "same_idempotency_key_required",
                "guidance": "No recovery is required for this completed result.",
            },
        },
    }


def _version_restore_evidence(
    _context: Mapping[str, Any],
    action_id: str,
    prepared: Mapping[str, Any],
    result: Any,
) -> Mapping[str, Any]:
    if action_id != _VERSION_RESTORE_ACTION_ID or not isinstance(result, Mapping):
        raise ValueError("Version restore result evidence is unavailable.")
    checkpoint_id = (
        prepared.get("lowering", {}).get("normalizedInput", {}).get("checkpointId")
    )
    persisted = version_ops.inspect_checkpoint(str(checkpoint_id or ""))
    exact = (
        isinstance(persisted, Mapping)
        and persisted.get("id") == checkpoint_id
        and result.get("checkpoint", {}).get("id") == checkpoint_id
        and result.get("active_project_name") == persisted.get("project_name")
        and result.get("active_timeline_name") == persisted.get("timeline_name")
        and result.get("restored_on_disk") is True
        and result.get("reopened") is True
        and result.get("verified") is True
        and result.get("verification_status") == "verified"
    )
    domain = prepared["domain"]
    return {
        "targetMatched": exact,
        "authorizationBound": True,
        "modalities": list(domain["minimumEvidence"]) if exact else [],
        "protectedState": {
            "checkpoint_history": exact,
            "project_identity": exact,
            "timeline_identity": exact,
            "active_context": exact,
        },
    }


def _version_restore_public_result(
    _context: Mapping[str, Any],
    action_id: str,
    prepared: Mapping[str, Any],
    result: Any,
) -> Mapping[str, Any]:
    if action_id != _VERSION_RESTORE_ACTION_ID or not isinstance(result, Mapping):
        raise ValueError("Version restore public result is unavailable.")
    checkpoint = _checkpoint_public(result["checkpoint"], prepared)
    reopened = result.get("reopened") is True
    verified = result.get("verified") is True
    if not reopened or not verified:
        raise ValueError("Version restore did not prove reopened verified state.")
    return {
        "actionId": action_id,
        "payload": {
            "status": "completed",
            "changed": True,
            "target": checkpoint,
            "data": {"reopened": reopened, "verified": verified},
            "verification": {
                "outcome": "passed",
                "protectedState": "preserved",
                "evidence": [
                    {
                        "kind": "checkpoint_readback",
                        "summary": "Restored project and timeline matched checkpoint readback.",
                    }
                ],
            },
            "recovery": {
                "state": "not_needed",
                "retry": "same_idempotency_key_required",
                "guidance": "No recovery is required for this completed result.",
            },
        },
    }


def _version_prune_descriptor() -> TimelineVersionPreparedActionDescriptor:
    return TimelineVersionPreparedActionDescriptor(
        descriptor=TIMELINE_VERSION_MUTATION_DESCRIPTORS[_VERSION_PRUNE_ACTION_ID],
        input_validator=_validate_version_prune_input,
        authority_resolver=_version_prune_authority,
        impact_builder=_version_prune_impact,
        action_executor=_unsupported_production_execute,
        evidence_reader=_version_prune_evidence,
        public_result_projector=_version_prune_public_result,
        checkpoint_restorer=lambda *_args: None,
        exact_checkpoint_pruner=version_ops.prune_checkpoints_exact,
        exact_timeline_sync_executor=_unsupported_production_execute,
    )


def _version_create_descriptor() -> TimelineVersionPreparedActionDescriptor:
    return TimelineVersionPreparedActionDescriptor(
        descriptor=TIMELINE_VERSION_MUTATION_DESCRIPTORS[_VERSION_CREATE_ACTION_ID],
        input_validator=_validate_version_create_input,
        authority_resolver=_version_create_authority,
        impact_builder=_version_prune_impact,
        action_executor=_version_action_execute,
        evidence_reader=_version_create_evidence,
        public_result_projector=_version_create_public_result,
        checkpoint_restorer=lambda *_args: None,
        exact_checkpoint_pruner=version_ops.prune_checkpoints_exact,
        exact_timeline_sync_executor=_unsupported_production_execute,
    )


def _version_restore_descriptor() -> TimelineVersionPreparedActionDescriptor:
    return TimelineVersionPreparedActionDescriptor(
        descriptor=TIMELINE_VERSION_MUTATION_DESCRIPTORS[_VERSION_RESTORE_ACTION_ID],
        input_validator=_validate_version_restore_input,
        authority_resolver=_version_restore_authority,
        impact_builder=_version_prune_impact,
        action_executor=_version_action_execute,
        evidence_reader=_version_restore_evidence,
        public_result_projector=_version_restore_public_result,
        checkpoint_restorer=lambda *_args: None,
        exact_checkpoint_pruner=version_ops.prune_checkpoints_exact,
        exact_timeline_sync_executor=_unsupported_production_execute,
    )


_TIMELINE_VERSION_MUTATION_CALLABLE_ACTION_IDS: tuple[str, ...] = (
    *TIMELINE_ARTIFACT_ACTION_IDS,
    _VERSION_CREATE_ACTION_ID,
    _VERSION_PRUNE_ACTION_ID,
    _VERSION_RESTORE_ACTION_ID,
    "cutagent.action.timeline.compound_create",
    "cutagent.action.timeline.fusion_clip.create",
    "cutagent.action.timeline.fusion_composition.insert",
    "cutagent.action.timeline.import_into",
    "cutagent.action.timeline.insert_generator",
    "cutagent.action.timeline.insert_title",
    "cutagent.action.timeline.items.set_duration",
    "cutagent.action.timeline.layer.ensure_media",
    "cutagent.action.timeline.sync_clips",
    "cutagent.action.timeline.track.add",
    "cutagent.action.timeline.track.delete",
    "cutagent.action.timeline.track.disable",
    "cutagent.action.timeline.track.enable",
    "cutagent.action.timeline.track.lock",
    "cutagent.action.timeline.track.rename",
    "cutagent.action.timeline.track.unlock",
    "cutagent.action.timeline.voice_isolation.set",
)
_TIMELINE_ORDINARY_MUTATION_CALLABLE_ACTION_IDS: tuple[str, ...] = (
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
TIMELINE_VERSION_CALLABLE_ACTION_IDS: tuple[str, ...] = (
    *TIMELINE_READ_ACTION_IDS,
    *_TIMELINE_ORDINARY_MUTATION_CALLABLE_ACTION_IDS,
    *_TIMELINE_VERSION_MUTATION_CALLABLE_ACTION_IDS,
)
TIMELINE_VERSION_DELEGATED_ACTION_IDS: tuple[str, ...] = (
    "cutagent.action.timeline.items.delete",
)
TIMELINE_VERSION_UNAVAILABLE_ACTION_IDS: tuple[str, ...] = tuple(
    sorted(
        set(TIMELINE_VERSION_MUTATION_DESCRIPTORS)
        - set(_TIMELINE_VERSION_MUTATION_CALLABLE_ACTION_IDS)
        - set(_TIMELINE_ORDINARY_MUTATION_CALLABLE_ACTION_IDS)
        - set(TIMELINE_VERSION_DELEGATED_ACTION_IDS)
    )
)


def timeline_version_prepared_action_production_contribution() -> Mapping[
    str,
    TimelineVersionPreparedActionDescriptor
    | TimelineReadPreparedActionDescriptor
    | TimelineArtifactPreparedActionDescriptor
    | UnavailableTimelineVersionPreparedActionDescriptor,
]:
    """Return truthful production registrations until real callbacks exist."""

    from .timeline_topology_production import timeline_topology_prepared_action_packet

    topology, _authorities = timeline_topology_prepared_action_packet()
    # Lazy import avoids a protocol/production-owner import cycle.
    from .timeline_ordinary_prepared_action import (
        TIMELINE_ORDINARY_PRODUCTION_ACTION_IDS,
        timeline_ordinary_prepared_action_production_contribution,
    )

    if TIMELINE_ORDINARY_PRODUCTION_ACTION_IDS != _TIMELINE_ORDINARY_MUTATION_CALLABLE_ACTION_IDS:
        raise RuntimeError("Ordinary Timeline production ownership drifted.")
    return MappingProxyType(
        {
            **timeline_read_prepared_action_production_contribution(),
            **timeline_artifact_prepared_action_production_contribution(),
            **timeline_ordinary_prepared_action_production_contribution(),
            _VERSION_CREATE_ACTION_ID: _version_create_descriptor(),
            _VERSION_PRUNE_ACTION_ID: _version_prune_descriptor(),
            _VERSION_RESTORE_ACTION_ID: _version_restore_descriptor(),
            **topology,
            **{
                action_id: UnavailableTimelineVersionPreparedActionDescriptor(
                    reason=_unavailable_reason(
                        TIMELINE_VERSION_MUTATION_DESCRIPTORS[action_id]
                    )
                )
                for action_id in TIMELINE_VERSION_UNAVAILABLE_ACTION_IDS
            },
        }
    )


def public_timeline_version_registration_summary() -> dict[str, Any]:
    """Project activation truth without exposing any private lowering."""

    unavailable = timeline_version_prepared_action_production_contribution()
    return {
        "schemaVersion": 1,
        "packet": "timeline_version_mutations_v1",
        "counts": {
            "callable": len(TIMELINE_VERSION_CALLABLE_ACTION_IDS),
            "delegated": len(TIMELINE_VERSION_DELEGATED_ACTION_IDS),
            "unavailable": len(TIMELINE_VERSION_UNAVAILABLE_ACTION_IDS),
            "total": (
                len(TIMELINE_VERSION_CALLABLE_ACTION_IDS)
                + len(TIMELINE_VERSION_DELEGATED_ACTION_IDS)
                + len(TIMELINE_VERSION_UNAVAILABLE_ACTION_IDS)
            ),
        },
        "actions": [
            *[
                {"actionId": action_id, "status": "callable"}
                for action_id in TIMELINE_VERSION_CALLABLE_ACTION_IDS
            ],
            *[
                {
                    "actionId": action_id,
                    "status": "delegated",
                    "owner": "existing_semantic_timeline_structure",
                }
                for action_id in TIMELINE_VERSION_DELEGATED_ACTION_IDS
            ],
            *[
                {
                    "actionId": action_id,
                    "status": "unavailable",
                    "reason": unavailable[action_id].reason,
                }
                for action_id in TIMELINE_VERSION_UNAVAILABLE_ACTION_IDS
            ],
        ],
    }
