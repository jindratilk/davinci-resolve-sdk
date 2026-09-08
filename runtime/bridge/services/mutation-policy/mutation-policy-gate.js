import crypto from "node:crypto";
import {
  CUTAGENT_MUTATION_POLICY_CONTRACT_VERSION,
  sdkConstraintBindingSchema,
  sdkConstraintScopeIdSchema,
  sdkConstraintScopeSchema,
  sdkEditConstraintsSchema,
  sdkMutationImpactSchema,
  sdkMutationPolicyDenialEvidenceSchema,
  sdkStableMutationTargetSchema,
} from "../../contracts/generated/sdk-mutation-policy.js";
import { sdkPublicFailureSchema } from "../../contracts/generated/sdk-operations.js";
import { mutationPolicyDigest, PRIVATE_IMPACT_REGISTRY_DIGEST } from "./impact-lowering.js";
import { createPreparedActionPolicyAttestor } from "./prepared-action-attestor.js";
import { preparedActionDigest } from "../sdk-prepared-action-digest.js";

const BINDING_RANK = Object.freeze({
  "account/project-library": 1,
  project: 2,
  "project+timeline": 3,
});

function opaque(prefix) {
  return `${prefix}${crypto.randomUUID()}`;
}

function iso(value) { return new Date(value).toISOString(); }

function normalizeArray(values, key) {
  const normalized = values.map((value) => structuredClone(value));
  normalized.sort((left, right) => JSON.stringify(left).localeCompare(JSON.stringify(right)));
  const result = [];
  const seen = new Set();
  for (const value of normalized) {
    const identity = key(value);
    if (!seen.has(identity)) {
      result.push(value);
      seen.add(identity);
    }
  }
  return result;
}

export function normalizeEditConstraints(value) {
  const parsed = sdkEditConstraintsSchema.parse(value);
  return sdkEditConstraintsSchema.parse({
    ...parsed,
    protectedTargets: normalizeArray(parsed.protectedTargets, (item) => JSON.stringify(item)),
    protectedMediaRoles: [...new Set(parsed.protectedMediaRoles)].sort(),
    allowedTrackTypes: [...new Set(parsed.allowedTrackTypes)].sort(),
    allowedOperations: [...new Set(parsed.allowedOperations)].sort(),
  });
}

function denialFailure(evidence, correlation = {}) {
  return sdkPublicFailureSchema.parse({
    kind: "edit_constraint_violation",
    code: "EDIT_CONSTRAINT_VIOLATION",
    message: evidence.summary,
    retrySafe: false,
    possibleMutation: "none",
    usage: "not_reserved",
    recovery: ["continue"],
    recoveryGuidance: ["Review the user-owned editing constraints and select an exact permitted stable target."],
    readbackRequired: false,
    ...(correlation.requestId ? { requestId: correlation.requestId } : {}),
    ...(correlation.operationId ? { operationId: correlation.operationId } : {}),
    ...(correlation.executionId ? { executionId: correlation.executionId } : {}),
  });
}

export class MutationPolicyError extends Error {
  constructor(reason, summary, { impact = null, protectedTargets = [] } = {}) {
    const evidence = sdkMutationPolicyDenialEvidenceSchema.parse({
      reason,
      summary,
      protectedTargetDigests: protectedTargets.map((target) => mutationPolicyDigest(target)),
    });
    const correlation = impact && typeof impact === "object" ? impact : {};
    const failure = denialFailure(evidence, correlation);
    super(failure.message);
    this.name = "MutationPolicyError";
    this.code = failure.code;
    this.failure = failure;
    this.evidence = evidence;
    this.bridge_error_type = "cutagent_cli_error";
    this.cli_error_code = failure.code;
    this.cli_error_details = {
      reason: evidence.reason,
      protected_target_digests: evidence.protectedTargetDigests,
      retry_safe: failure.retrySafe,
      possible_mutation: failure.possibleMutation,
      usage: failure.usage,
      recovery: failure.recovery,
      recovery_guidance: failure.recoveryGuidance,
      readback_required: failure.readbackRequired,
      ...(failure.requestId ? { request_id: failure.requestId } : {}),
      ...(failure.operationId ? { operation_id: failure.operationId } : {}),
      ...(failure.executionId ? { execution_id: failure.executionId } : {}),
    };
    this.exit_code = 2;
  }
}

function deny(reason, summary, options) { throw new MutationPolicyError(reason, summary, options); }

function assertBinding(scopeBinding, impact) {
  if (BINDING_RANK[scopeBinding.level] < BINDING_RANK[impact.minimumBinding]) {
    deny("insufficient_binding", "The editing-constraint scope is not bound deeply enough for this mutation.", { impact });
  }
  if (scopeBinding.projectLibraryId !== impact.projectLibraryId
    || (impact.minimumBinding !== "account/project-library" && scopeBinding.projectId !== impact.projectId)
    || (impact.minimumBinding === "project+timeline" && scopeBinding.timelineId !== impact.timelineId)) {
    deny("binding_mismatch", "The mutation stable resource identity does not match the user constraint scope.", { impact });
  }
  if (impact.minimumBinding !== "account/project-library"
    && scopeBinding.projectRevision !== impact.projectRevision) {
    deny("binding_mismatch", "The mutation project revision does not match the user constraint scope.", { impact });
  }
  if (impact.minimumBinding === "project+timeline"
    && scopeBinding.timelineRevision !== impact.timelineRevision) {
    deny("binding_mismatch", "The mutation timeline revision does not match the user constraint scope.", { impact });
  }
}

function assertImpactAllowed(scope, impact) {
  if (impact.status === "unknown") deny("unknown_impact", "CutAgent could not determine the complete mutation impact.", { impact });
  if (impact.broad || impact.effects.some((effect) => effect.broad)) {
    deny("broad_impact", "Broad mutation targets are not permitted by the policy gate.", { impact });
  }
  if (!impact.complete || impact.effects.some((effect) => !effect.complete)) {
    deny("incomplete_impact", "CutAgent could not resolve every mutation effect before authorization.", { impact });
  }
  if (impact.ambiguous || impact.effects.some((effect) => effect.ambiguous)) {
    deny("ambiguous_impact", "The mutation target is ambiguous.", { impact });
  }
  assertBinding(scope.binding, impact);

  const constraints = scope.constraints;
  for (const effect of impact.effects) {
    const internalWorkflowCheckpoint = effect.operation === "version.create" || effect.operation === "version.restore";
    if (!internalWorkflowCheckpoint && constraints.allowedOperations.length > 0
      && !constraints.allowedOperations.includes(effect.operation)) {
      deny("operation_not_allowed", "The requested operation is outside the user's allowed operation set.", { impact });
    }
    if (constraints.allowedTrackTypes.length > 0
      && effect.trackTypes.some((trackType) => !constraints.allowedTrackTypes.includes(trackType))) {
      deny("track_type_not_allowed", "The mutation would affect a track type the user did not allow.", { impact });
    }
    if (constraints.markerIntent === "placement"
      && effect.targets.some((target) => target.kind === "marker")) {
      deny("marker_intent_conflict", "Markers are placement positions and cannot be treated as mutation targets.", { impact });
    }
    const protectedRoles = effect.targets.filter((target) => (
      target.mediaRole && constraints.protectedMediaRoles.includes(target.mediaRole)
    ));
    if (protectedRoles.length > 0) {
      deny("protected_media_role", "The mutation would affect a protected media role.", {
        impact,
        protectedTargets: protectedRoles,
      });
    }
    for (const protectedTarget of constraints.protectedTargets) {
      const current = effect.targets.find((target) => target.stableId === protectedTarget.stableId);
      if (!current) continue;
      if (current.revision !== protectedTarget.revision) {
        deny("stale_target", "A protected target revision changed and must be reconciled by the user.", {
          impact,
          protectedTargets: [protectedTarget],
        });
      }
      deny("protected_target", "The mutation would affect a protected stable target.", {
        impact,
        protectedTargets: [protectedTarget],
      });
    }
    if (constraints.protectedMediaRoles.length > 0) {
      const unresolvedRoleTargets = effect.targets.filter((target) => (
        !target.mediaRole
        && (
          target.trackType === "audio"
          || target.kind === "media"
          || (["clip", "track"].includes(target.kind)
            && target.trackType === undefined
            && (effect.trackTypes.length === 0 || effect.trackTypes.includes("audio")))
        )
      ));
      if (unresolvedRoleTargets.length > 0) {
        deny("protected_media_role", "CutAgent could not prove that every role-bearing mutation target is outside the protected media roles.", {
          impact,
          protectedTargets: unresolvedRoleTargets,
        });
      }
    }
  }
}

/** One local proprietary authority for scopes and one-use policy decisions. */
export function createMutationPolicyGate({
  repo,
  now = () => Date.now(),
  signedExecutionScopeAvailable = false,
  resolveProtectedTargets = null,
} = {}) {
  if (!repo?.installationAuthority) throw new Error("Mutation policy gate requires its durable scope repository.");
  const decisions = new Map();
  const verifiedProtectedTargetProofs = new Map();
  const preparedActionAttestor = createPreparedActionPolicyAttestor({ now });

  function resolveCurrentProtectedTargets(scope, impact = null, suppliedCurrentTargets = null) {
    if (scope.constraints.protectedTargets.length === 0) return [];
    if (suppliedCurrentTargets === null && typeof resolveProtectedTargets !== "function") {
      deny("stale_target", "Protected targets could not be reconciled against current state.", {
        impact, protectedTargets: scope.constraints.protectedTargets,
      });
    }
    let currentProtected;
    try {
      const resolved = suppliedCurrentTargets === null
        ? resolveProtectedTargets(structuredClone(scope))
        : suppliedCurrentTargets.map((target) => sdkStableMutationTargetSchema.parse(target));
      currentProtected = normalizeEditConstraints({
        protectedTargets: resolved,
        protectedMediaRoles: [], allowedTrackTypes: [], allowedOperations: [], markerIntent: null,
      }).protectedTargets;
    } catch {
      deny("stale_target", "Protected targets could not be reconciled against current state.", {
        impact, protectedTargets: scope.constraints.protectedTargets,
      });
    }
    if (mutationPolicyDigest(currentProtected) !== mutationPolicyDigest(scope.constraints.protectedTargets)) {
      deny("stale_target", "A protected target changed or disappeared.", {
        impact, protectedTargets: scope.constraints.protectedTargets,
      });
    }
    return currentProtected;
  }

  function assertProtectedTargetsCurrent(scope, impact, suppliedCurrentTargets = null) {
    resolveCurrentProtectedTargets(scope, impact, suppliedCurrentTargets);
  }

  function revokeMatching(predicate, reason = "decision_revoked") {
    for (const decision of decisions.values()) {
      if (decision.state === "prepared" || decision.state === "authorized") {
        if (predicate(decision)) {
          decision.state = "revoked";
          decision.revokedReason = reason;
        }
      }
    }
  }

  function createScope({ accountFingerprint, binding, constraints }) {
    const at = now();
    return repo.create(sdkConstraintScopeSchema.parse({
      contractVersion: CUTAGENT_MUTATION_POLICY_CONTRACT_VERSION,
      scopeId: opaque("constraint_scope_"),
      accountFingerprint,
      revision: 1,
      binding: sdkConstraintBindingSchema.parse(binding),
      constraints: normalizeEditConstraints(constraints),
      createdAt: iso(at),
      updatedAt: iso(at),
    }));
  }

  function reconcileOwnedScope({ ownerKey, accountFingerprint, binding, defaultConstraints }) {
    if (typeof repo.reconcileOwnedScope !== "function") {
      throw new Error("Durable editing-constraint owner reconciliation is unavailable.");
    }
    const previous = repo.listForAccount(accountFingerprint);
    const reconciled = repo.reconcileOwnedScope({
      ownerKey,
      accountFingerprint,
      binding: sdkConstraintBindingSchema.parse(binding),
      defaultConstraints: normalizeEditConstraints(defaultConstraints),
      nowIso: iso(now()),
    });
    const prior = previous.find((scope) => scope.scopeId === reconciled.scopeId);
    if (prior && prior.revision !== reconciled.revision) {
      revokeMatching((decision) => decision.scopeId === reconciled.scopeId);
    }
    return reconciled;
  }

  function bindVerifiedProtectedTargets({ accountFingerprint, executionId, scopeId, scopeRevision, timelineRevision }) {
    const scope = repo.get(scopeId);
    if (!scope || scope.accountFingerprint !== accountFingerprint || scope.revision !== scopeRevision
      || scope.binding.level !== "project+timeline" || scope.binding.timelineRevision !== timelineRevision) {
      deny("stale_target", "Verified protected-target proof does not match the current constraint scope.", {
        protectedTargets: scope?.constraints?.protectedTargets ?? [],
      });
    }
    const currentTargets = resolveCurrentProtectedTargets(scope);
    const proof = Object.freeze({
      accountFingerprint,
      scopeId,
      scopeRevision,
      timelineRevision,
      protectedTargetsDigest: mutationPolicyDigest(currentTargets),
    });
    verifiedProtectedTargetProofs.set(executionId, proof);
    return () => {
      if (verifiedProtectedTargetProofs.get(executionId) === proof) verifiedProtectedTargetProofs.delete(executionId);
    };
  }

  function updateScope({ accountFingerprint, scopeId, expectedRevision, binding, constraints }) {
    const current = repo.get(sdkConstraintScopeIdSchema.parse(scopeId));
    if (!current) return null;
    if (current.accountFingerprint !== accountFingerprint) {
      deny("cross_account_scope", "The editing-constraint scope belongs to another account.");
    }
    const result = repo.compareAndSwap(scopeId, expectedRevision, {
      ...current,
      revision: current.revision + 1,
      binding: sdkConstraintBindingSchema.parse(binding),
      constraints: normalizeEditConstraints(constraints),
      updatedAt: iso(now()),
    });
    if (result === false) deny("stale_scope", "The editing-constraint scope changed before this update.");
    if (result) revokeMatching((decision) => decision.scopeId === scopeId);
    return result;
  }

  function getScope({ accountFingerprint, scopeId }) {
    const scope = repo.get(sdkConstraintScopeIdSchema.parse(scopeId));
    if (!scope) return null;
    if (scope.accountFingerprint !== accountFingerprint) {
      deny("cross_account_scope", "The editing-constraint scope belongs to another account.");
    }
    return scope;
  }

  function preflight({ accountFingerprint, impact: rawImpact, currentProtectedTargets = null }) {
    const parsed = sdkMutationImpactSchema.safeParse(rawImpact);
    if (!parsed.success) {
      deny("unknown_impact", "CutAgent could not validate the complete mutation impact.", {
        impact: rawImpact && typeof rawImpact === "object" ? rawImpact : null,
      });
    }
    const impact = parsed.data;
    if (impact.registryDigest !== PRIVATE_IMPACT_REGISTRY_DIGEST) {
      deny("unknown_impact", "The mutation impact registry is not current.", { impact });
    }
    const scope = repo.get(impact.scopeId);
    if (!scope) deny("missing_scope", "A durable editing-constraint scope is required.", { impact });
    if (scope.accountFingerprint !== accountFingerprint) {
      deny("cross_account_scope", "The editing-constraint scope belongs to another account.", { impact });
    }
    if (scope.revision !== impact.scopeRevision) {
      deny("stale_scope", "The editing-constraint scope revision is stale.", { impact });
    }
    assertProtectedTargetsCurrent(scope, impact, currentProtectedTargets);
    assertImpactAllowed(scope, impact);
    const decisionId = opaque("policy_decision_");
    const decision = {
      decisionId,
      state: "prepared",
      accountFingerprint,
      scopeId: scope.scopeId,
      scopeRevision: scope.revision,
      registryDigest: impact.registryDigest,
      canonicalRequestDigest: impact.canonicalRequestDigest,
      referencedPayloadDigests: [...impact.referencedPayloadDigests],
      resolvedTargetsDigest: mutationPolicyDigest(impact.effects.map((effect) => effect.targets)),
      projectLibraryId: impact.projectLibraryId,
      projectId: impact.projectId ?? null,
      timelineId: impact.timelineId ?? null,
      projectRevision: impact.projectRevision ?? null,
      timelineRevision: impact.timelineRevision ?? null,
      requestId: impact.requestId,
      operationId: impact.operationId,
      executionId: impact.executionId,
      executableStableTargetPrecondition: impact.executableStableTargetPrecondition,
      verificationPolicy: structuredClone(impact.verificationPolicy),
      operations: impact.effects.map((effect) => effect.operation),
      protectedTargetDigests: scope.constraints.protectedTargets.map((target) => mutationPolicyDigest(target)),
      createdAt: iso(now()),
    };
    decisions.set(decisionId, decision);
    return Object.freeze({ ...structuredClone(decision) });
  }

  function requireCurrent(decisionId, expectedState, binding, currentProtectedTargets = null) {
    const decision = decisions.get(decisionId);
    if (!decision) deny("decision_revoked", "The local mutation policy decision is unavailable.");
    if (decision.state === "consumed") deny("decision_replayed", "The one-use mutation policy decision was already consumed.");
    if (decision.state !== expectedState) deny("decision_revoked", "The mutation policy decision is no longer current.");
    const scope = repo.get(decision.scopeId);
    if (!scope || scope.accountFingerprint !== decision.accountFingerprint
      || scope.revision !== decision.scopeRevision) {
      decision.state = "revoked";
      deny("decision_revoked", "The mutation policy decision was revoked by a constraint change.", { impact: decision });
    }
    assertProtectedTargetsCurrent(scope, decision, currentProtectedTargets);
    const exact = {
      registryDigest: binding.registryDigest,
      canonicalRequestDigest: binding.canonicalRequestDigest,
      referencedPayloadDigests: binding.referencedPayloadDigests,
      resolvedTargetsDigest: binding.resolvedTargetsDigest,
      projectLibraryId: binding.projectLibraryId,
      projectId: binding.projectId ?? null,
      timelineId: binding.timelineId ?? null,
      projectRevision: binding.projectRevision ?? null,
      timelineRevision: binding.timelineRevision ?? null,
      requestId: binding.requestId,
      operationId: binding.operationId,
      executionId: binding.executionId,
    };
    for (const [key, value] of Object.entries(exact)) {
      if (JSON.stringify(decision[key]) !== JSON.stringify(value)) {
        decision.state = "revoked";
        deny("decision_binding_mismatch", "The mutation changed after policy preflight.", { impact: decision });
      }
    }
    return decision;
  }

  function revalidateBeforeAuthorization(decisionId, binding, currentProtectedTargets = null) {
    const decision = requireCurrent(decisionId, "prepared", binding, currentProtectedTargets);
    decision.state = "authorized";
    decision.authorizedAt = iso(now());
    return Object.freeze({ ...structuredClone(decision) });
  }

  function consumeBeforeSpawn(decisionId, binding, currentProtectedTargets = null) {
    const decision = requireCurrent(decisionId, "authorized", binding, currentProtectedTargets);
    const signedScopeAvailable = typeof signedExecutionScopeAvailable === "function"
      ? signedExecutionScopeAvailable(decision)
      : signedExecutionScopeAvailable;
    if (!signedScopeAvailable || !decision.executableStableTargetPrecondition) {
      decision.state = "revoked";
      deny(
        "signed_execution_scope_unavailable",
        "This mutation remains release-gated until CutAgent CLI can enforce a signed stable execution scope.",
        { impact: decision },
      );
    }
    decision.state = "consumed";
    decision.consumedAt = iso(now());
    return true;
  }

  function issuePreparedActionAttestation(decisionId, binding, authorizationBinding, currentProtectedTargets = null) {
    const decision = requireCurrent(decisionId, "authorized", binding, currentProtectedTargets);
    const required = ["accountDigest", "impactDigest", "receiptDigest", "executionDigest", "projectDigest", "timelineDigest", "targetsDigest", "preStateDigest"];
    if (!authorizationBinding || required.some((key) => !/^sha256:[a-f0-9]{64}$/.test(String(authorizationBinding[key] ?? "")))) {
      decision.state = "revoked";
      deny("decision_binding_mismatch", "Prepared-action policy attestation binding is invalid.", { impact: decision });
    }
    return preparedActionAttestor.issue({
      ...Object.fromEntries(required.map((key) => [key, authorizationBinding[key]])),
      scopeDigest: preparedActionDigest("policy-decision", {
        accountFingerprint: decision.accountFingerprint,
        scopeId: decision.scopeId,
        scopeRevision: decision.scopeRevision,
        registryDigest: decision.registryDigest,
        resolvedTargetsDigest: decision.resolvedTargetsDigest,
        projectLibraryId: decision.projectLibraryId,
        projectId: decision.projectId,
        timelineId: decision.timelineId,
        projectRevision: decision.projectRevision,
        timelineRevision: decision.timelineRevision,
        operations: decision.operations,
      }),
      resolvedTargetsDigest: decision.resolvedTargetsDigest,
      decisionIdDigest: preparedActionDigest("policy-decision", decision.decisionId),
    });
  }

  function assertProtectedStateEvidence(decisionId, report, suppliedCurrentTargets = null) {
    const decision = decisions.get(decisionId);
    if (!decision || decision.state !== "consumed") {
      deny("decision_revoked", "Protected-state evidence has no consumed policy decision.");
    }
    const scope = repo.get(decision.scopeId);
    if (!scope || scope.accountFingerprint !== decision.accountFingerprint
      || scope.revision !== decision.scopeRevision) {
      deny("decision_revoked", "Protected-state evidence no longer matches the current constraint scope.", { impact: decision });
    }
    const currentProtectedTargets = resolveCurrentProtectedTargets(scope, decision, suppliedCurrentTargets);
    const policy = decision.verificationPolicy;
    const modalities = new Set(Array.isArray(report?.evidence)
      ? report.evidence.map((item) => item?.modality)
      : []);
    const complete = policy.minimumEvidence.every((modality) => modalities.has(modality))
      && (!policy.requireProtectedStatePreserved || report?.protectedStatePreserved === true)
      && (policy.protectedTargetEvidence !== "every_declared_target"
        || mutationPolicyDigest(currentProtectedTargets) === mutationPolicyDigest(scope.constraints.protectedTargets));
    if (!complete) {
      throw new Error("Verification cannot report passed without every required protected-state proof.");
    }
    return true;
  }

  function projectSequentialAggregate({ earlierAppliedOperationIds, laterFailure }) {
    const applied = Array.isArray(earlierAppliedOperationIds)
      ? [...new Set(earlierAppliedOperationIds)]
      : [];
    if (applied.length < 1 || laterFailure?.code !== "EDIT_CONSTRAINT_VIOLATION"
      || laterFailure.possibleMutation !== "none" || laterFailure.usage !== "not_reserved") {
      throw new Error("Sequential partial-application projection requires prior applied operations and an unchanged policy denial.");
    }
    return Object.freeze({
      status: "partially_applied",
      possibleMutation: "partial",
      appliedOperationIds: applied,
      laterOperationFailure: structuredClone(laterFailure),
    });
  }

  return Object.freeze({
    createScope,
    reconcileOwnedScope,
    bindVerifiedProtectedTargets,
    updateScope,
    getScope,
    listScopes: ({ accountFingerprint }) => repo.listForAccount(accountFingerprint),
    preflight,
    revalidateBeforeAuthorization,
    consumeBeforeSpawn,
    issuePreparedActionAttestation,
    preparedActionPolicyPublicJwk: () => structuredClone(preparedActionAttestor.publicJwk),
    assertProtectedStateEvidence,
    projectSequentialAggregate,
    reconcileStartup() {
      // Decisions are intentionally process-local one-use capabilities. A
      // restart invalidates them while durable user scopes survive unchanged.
      decisions.clear();
      verifiedProtectedTargetProofs.clear();
      return { scopes: repo.inspect().scopes, outstandingDecisions: 0 };
    },
    onLogout(accountFingerprint) {
      revokeMatching((decision) => decision.accountFingerprint === accountFingerprint);
      for (const [executionId, proof] of verifiedProtectedTargetProofs) {
        if (proof.accountFingerprint === accountFingerprint) verifiedProtectedTargetProofs.delete(executionId);
      }
    },
    onSessionClose({ accountFingerprint, executionId = null }) {
      revokeMatching((decision) => decision.accountFingerprint === accountFingerprint
        && (!executionId || decision.executionId === executionId));
      if (executionId) verifiedProtectedTargetProofs.delete(executionId);
      else {
        for (const [proofExecutionId, proof] of verifiedProtectedTargetProofs) {
          if (proof.accountFingerprint === accountFingerprint) verifiedProtectedTargetProofs.delete(proofExecutionId);
        }
      }
    },
    onThreadFork() {
      // A fork receives no implicit scope or decision. Its next mutation must
      // bind an explicit current scope revision and fresh operation identities.
      return null;
    },
    inspectDecisions() { return structuredClone([...decisions.values()]); },
  });
}
