import crypto from "node:crypto";

const EMPTY_CONSTRAINTS = Object.freeze({
  protectedTargets: [],
  protectedMediaRoles: [],
  allowedTrackTypes: [],
  allowedOperations: [],
  markerIntent: null,
});

function ownerKey(sdkSessionId, accountFingerprint, binding) {
  const stable = [
    "direct-sdk:v1",
    sdkSessionId,
    accountFingerprint,
    binding.level,
    binding.projectLibraryId,
    binding.projectId ?? "",
    binding.timelineId ?? "",
  ].join("\0");
  return `scope_owner_${crypto.createHash("sha256").update(stable, "utf8").digest("hex")}`;
}

/** Proprietary owner for direct-SDK mutation scopes; never selects unrelated session scopes. */
export function createSdkDirectMutationPolicyAuthority({ sdkRuntimeService, mutationPolicyGate } = {}) {
  if (typeof sdkRuntimeService?.ownsActiveSession !== "function"
    || typeof mutationPolicyGate?.reconcileOwnedScope !== "function") {
    throw new TypeError("Direct SDK mutation policy requires runtime-session and durable scope authority.");
  }
  let workflowScopeResolver = null;
  return Object.freeze({
    bindWorkflowScopeResolver(resolver) {
      if (workflowScopeResolver !== null || typeof resolver !== "function") {
        throw new TypeError("Direct SDK mutation policy workflow resolver can only be bound once.");
      }
      workflowScopeResolver = resolver;
    },
    resolveScope({ sdkSessionId, accountFingerprint, binding, idempotencyKey = null }) {
      if (!sdkRuntimeService.ownsActiveSession({ sessionId: sdkSessionId, accountFingerprint })) {
        throw new TypeError("Prepared SDK mutation requires an active account-bound runtime session.");
      }
      const workflowScope = workflowScopeResolver?.({ sdkSessionId, accountFingerprint, idempotencyKey, binding }) ?? null;
      if (workflowScope !== null) return workflowScope;
      return mutationPolicyGate.reconcileOwnedScope({
        ownerKey: ownerKey(sdkSessionId, accountFingerprint, binding),
        accountFingerprint,
        binding,
        defaultConstraints: EMPTY_CONSTRAINTS,
      });
    },
  });
}
