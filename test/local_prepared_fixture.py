"""Original upstream test descriptor fixture, adapted only to local admission.
No DaVinci Resolve process is accessed; execution is a deterministic test handler.
"""
from cutagent_cli.local_prepared_authority import LocalPreparedActionAuthority
from cutagent_cli.sdk_prepared_action import PreparedActionRegistry, prepared_action_digest
from cutagent_cli._sdk_prepared_action_contract import PREPARED_ACTION_KERNEL_DIGEST, PREPARED_ACTION_CONTRACT_DIGEST, PREPARED_ACTION_CAPABILITY_DIGEST
from cutagent_cli.policy import _prepared_action_admission_scope, enforce_mutation_policy
def _admitted_marker_handler():
    enforce_mutation_policy(
        "timeline.marker_crud", intended_engine="api_native", mutating=True
    )
    return {"created": True}

class MarkerExecutionAuthority:
    def _matches_carrier_admission(self, action_id, command_id, admitted_handler):
        return (
            action_id == "cutagent.action.timeline.marker.add"
            and command_id == "timeline.marker.add"
            and admitted_handler is _admitted_marker_handler
        )

    def invoke_admitted_handler(self, context):
        with _prepared_action_admission_scope(
            "cutagent.action.timeline.marker.add",
            "timeline.marker.add",
            self,
            _admitted_marker_handler,
            context,
        ):
            return _admitted_marker_handler()

class Descriptor:
    operation_class = "mutation"
    version = 1
    capability_id = "timeline.marker_crud"

    def __init__(self, *, capability_id="timeline.marker_crud"):
        self.capability_id = capability_id
        self.targets = [
            {
                "kind": "marker",
                "stableId": "marker_125",
                "revision": "absent",
                "projectId": "project_1",
                "timelineId": "timeline_1",
            }
        ]
        self.pre_state = {"marker": None}
        self.executions = 0
        self.recoveries = 0
        self.execute_failure = None
        self.verification_outcome = "passed"
        self.evidence_digest = f"sha256:{'a' * 64}"
        self.recovery_failure = None
        self.projected_result = None
        self.replace_binding_during_execute = False
        self.replace_binding_during_resolution = False

    def validate_input(self, value):
        if getattr(self, "accept_large_input", False):
            return dict(value)
        if set(value) != {"frame"} or not isinstance(value["frame"], int):
            raise ValueError("invalid input")
        return dict(value)

    def prepare(self, context, value):
        self.observed_mutation_base = context.get("mutationBase")
        return {
            "targets": self.targets,
            "preState": self.pre_state,
            "impact": {
                **(context.get("mutationBase") or {}),
                "contractVersion": 1,
                "status": "mutation",
                "complete": True,
                "effects": [{"operation": "marker.create"}],
                "verificationPolicy": {
                    "minimumEvidence": ["readback"],
                    "requireProtectedStatePreserved": True,
                    "protectedTargetEvidence": "every_declared_target",
                },
            },
            "lowering": {
                "commandId": "timeline.marker.add",
                "argv": ["timeline", "marker", "add", str(value["frame"])],
            },
            "verification": {"minimumEvidence": ["readback", "structural"]},
            "recovery": {"mode": "checkpoint"},
        }

    def resolve_current(self, context, prepared):
        self.resolved_private_bindings = context.get("privateBindings")
        if self.replace_binding_during_resolution:
            context["exactRequestBinding"] = dict(context["exactRequestBinding"])
        return {"targets": self.targets, "preState": self.pre_state}

    def execute(self, context, prepared):
        self.executed_private_bindings = context.get("privateBindings")
        self.executions += 1
        if self.execute_failure:
            raise self.execute_failure
        if authority := context.get("executionAuthority"):
            if self.replace_binding_during_execute:
                context["exactRequestBinding"] = dict(context["exactRequestBinding"])
            return authority.invoke_admitted_handler(context)
        return {"created": True}

    def verify(self, context, prepared, result):
        return {
            "outcome": self.verification_outcome,
            "evidence": [
                {
                    "modality": "readback",
                    "digest": self.evidence_digest,
                    "summary": "Exact marker readback matched.",
                }
            ],
            "protectedStatePreserved": True,
        }

    def recover(self, context, prepared, failure):
        self.recoveries += 1
        if self.recovery_failure:
            raise self.recovery_failure
        return {
            "outcome": "succeeded",
            "attempted": True,
            "manualActionRequired": False,
        }

    def project_result(self, context, prepared, result):
        return (
            self.projected_result
            if self.projected_result is not None
            else {"created": bool(result["created"])}
        )

    def validate_public_result(self, value):
        if self.projected_result is not None and set(value) == {"outcome"}:
            return value["outcome"] in {"succeeded", "no_change"}
        if self.projected_result is not None and set(value) == {"payload"}:
            return isinstance(value["payload"], str)
        return set(value) == {"created"} and isinstance(value["created"], bool)

def authority_env():
    now = [1_800_000_000_000]
    def sha(value): return value*64
    context = {
        'localPrincipal': {'fingerprint':'local_test_owner'},
        "session": {
            "accountSubject": "account_test",
            "sdkSessionId": "sdk_session_test",
            "runtimeSessionId": "runtime_session_test",
        },
        "project": {
            "projectLibraryId": "library_1",
            "projectLibraryRevision": "library_revision_1",
            "projectId": "project_1",
            "projectRevision": "project_revision_1",
        },
        "timeline": {
            "projectId": "project_1",
            "timelineId": "timeline_1",
            "timelineRevision": "timeline_revision_1",
        },
        "artifacts": {
            "protocol": {
                "protocolVersion": 1,
                "protocolDigest": f"sha256:{sha('f')}",
                "preparedActionKernelDigest": PREPARED_ACTION_KERNEL_DIGEST,
            },
            "app": {"artifactKind": "app", "version": "2.1.3", "sha256": sha("a")},
            "runtime": {
                "artifactKind": "runtime",
                "version": "2.1.3",
                "sha256": sha("b"),
            },
            "cli": {"artifactKind": "cli", "version": "2.1.3", "sha256": sha("c")},
            "runtimeManifestDigest": f"sha256:{sha('d')}",
        },
    }
    descriptor = Descriptor()
    redeemed = set()
    custody = {}
    terminals = {}
    registry = PreparedActionRegistry()
    registry.register_contribution(
        "fixture", {"cutagent.action.timeline.marker.add": descriptor}
    )
    frozen_registry = registry.freeze()

    def claim(key, value):
        if key in custody:
            return False
        custody[key] = dict(value)
        return True

    def redeem(jti, _claims, _token):
        return False if jti in redeemed else not redeemed.add(jti)

    def record_terminal(key, terminal):
        terminals[key] = dict(terminal)

    policy_jwk = {}
    context["session"].update(
        {
            "preparedActionKernelDigest": PREPARED_ACTION_KERNEL_DIGEST,
            "preparedActionContractDigest": PREPARED_ACTION_CONTRACT_DIGEST,
            "preparedActionCapabilityDigest": PREPARED_ACTION_CAPABILITY_DIGEST,
            "preparedActionPolicyPublicJwkDigest": prepared_action_digest(
                "policy-decision", policy_jwk
            ),
        }
    )
    execution_authority = MarkerExecutionAuthority()
    authority = LocalPreparedActionAuthority(
        registry=frozen_registry,
        runtime_context=lambda: context,
        redeem_authorization_jti=redeem,
        claim_idempotency=claim,
        record_idempotency_terminal=record_terminal,
        load_idempotency_terminal=terminals.get,
        assert_protected_state_evidence=lambda _claims, _impact, _report: True,
        policy_public_jwk=policy_jwk,
        execution_authorities={
            "cutagent.action.timeline.marker.add": execution_authority
        },
        now_ms=lambda: now[0],
    )
    request = {
        "protocolVersion": 1,
        "actionId": "cutagent.action.timeline.marker.add",
        "actionContractVersion": 1,
        "input": {"frame": 125},
        "contractDigest": PREPARED_ACTION_CONTRACT_DIGEST,
        "capabilityDigest": PREPARED_ACTION_CAPABILITY_DIGEST,
        "identities": {
            "projectLibraryId": "library_1",
            "projectId": "project_1",
            "timelineId": "timeline_1",
            "targetIds": ["marker_125"],
        },
        "revisions": {
            "projectLibrary": "library_revision_1",
            "project": "project_revision_1",
            "timeline": "timeline_revision_1",
            "targets": {"marker_125": "absent"},
        },
        "idempotencyKey": "idempotency_test",
        "requestId": "request_fixture_123",
        "operationId": "operation_fixture_123",
        "executionId": "execution_fixture_123",
    }
    raw_prepare = authority.prepare

    def mutation_base(value):
        return {
            "contractVersion": 1,
            "carrier": "sdk",
            "minimumBinding": "project+timeline",
            "registryDigest": "sha256:de643beec119efb8fa9d2636cf2136638297a4adddba7d810a9adf2356ab2c98",
            "canonicalRequestDigest": f"sha256:{'9' * 64}",
            "referencedPayloadDigests": [],
            "requestId": value["requestId"],
            "operationId": value["operationId"],
            "executionId": value["executionId"],
            "scopeId": "constraint_scope_fixture_12345678",
            "scopeRevision": 1,
            "projectLibraryId": value["identities"]["projectLibraryId"],
            "projectId": value["identities"]["projectId"],
            "timelineId": value["identities"]["timelineId"],
            "projectRevision": value["revisions"]["project"],
            "timelineRevision": value["revisions"]["timeline"],
        }

    authority.prepare = lambda value, base=None: raw_prepare(
        value, mutation_base(value) if base is None else base
    )
    return {
        "authority": authority,
        "descriptor": descriptor,
        "context": context,
        "request": request,
        "policy_jwk": policy_jwk,
        "now": now,
        "custody": custody,
        "terminals": terminals,
        "registry": frozen_registry,
        "claim": claim,
        "redeem": redeem,
        "record_terminal": record_terminal,
        "raw_prepare": raw_prepare,
        "mutation_base": mutation_base,
    }
