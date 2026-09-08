import {
  sdkPrepareActionRequestSchema,
  sdkPrepareActionResultSchema,
  sdkPreparedActionMutationBaseSchema,
  sdkPreparedActionTerminalSchema,
} from "../contracts/generated/sdk-prepared-action.js";
import {CUTAGENT_PREPARED_ACTION_ACTION_METADATA} from "../contracts/sdk-prepared-action-metadata.generated.js";
import { captureAuthenticatedSdkRequest } from "./sdk-authenticated-request.js";
import { preparedActionDigest } from "./sdk-prepared-action-digest.js";
import { mutationPolicyDigest, PRIVATE_IMPACT_REGISTRY_DIGEST } from "./mutation-policy/impact-lowering.js";

function policyBinding(decision) {
  return {
    registryDigest: decision.registryDigest,
    canonicalRequestDigest: decision.canonicalRequestDigest,
    referencedPayloadDigests: decision.referencedPayloadDigests,
    resolvedTargetsDigest: decision.resolvedTargetsDigest,
    projectLibraryId: decision.projectLibraryId,
    projectId: decision.projectId,
    timelineId: decision.timelineId,
    projectRevision: decision.projectRevision,
    timelineRevision: decision.timelineRevision,
    requestId: decision.requestId,
    operationId: decision.operationId,
    executionId: decision.executionId,
  };
}

/**
 * Route-neutral Bridge coordinator. It never receives command identity, argv,
 * private lowering, execution route, verifier plan, or recovery metadata.
 */
export function createSdkPreparedActionCoordinator({
  signedRuntimeClient,
  mutationPolicyGate,
  authorizationService,
  authService,
  admitOperation = async () => {},
  markExecuteDispatched = async () => {},
  refreshProtectedTargets = null,
  mutationBaseAuthority = null,
} = {}) {
  const activePolicyDecisions = new Map();
  for (const [name, method] of Object.entries({
    prepare: signedRuntimeClient?.prepare,
    acceptPolicy: signedRuntimeClient?.acceptPolicy,
    admit: signedRuntimeClient?.admit,
    execute: signedRuntimeClient?.execute,
  })) {
    if (typeof method !== "function") throw new TypeError(`Signed prepared-action runtime requires ${name}.`);
  }


  async function execute(rawRequest, lifecycle = {}, carrierBinding = {}) {
    const request = sdkPrepareActionRequestSchema.parse(rawRequest);
    const authenticated = await captureAuthenticatedSdkRequest(authService);
    let prepared = null;
    let executeDispatched = false;
    try {
    const operationClass = CUTAGENT_PREPARED_ACTION_ACTION_METADATA[request.actionId]?.operationClass;
    if (!operationClass) throw new TypeError("Prepared action is absent from the authoritative action registry.");
    let mutationBase = null;
    if (operationClass === "mutation") {
      if (typeof mutationBaseAuthority?.capture !== "function") throw new TypeError("Prepared mutations require a carrier-owned mutation base authority.");
      mutationBase = sdkPreparedActionMutationBaseSchema.parse(await mutationBaseAuthority.capture({
        request,
        authenticated,
        carrierBinding,
      }));
      const exact = {
        requestId: request.requestId,
        operationId: request.operationId,
        executionId: request.executionId,
        projectLibraryId: request.identities.projectLibraryId,
        ...(mutationBase.minimumBinding === "account/project-library" ? {} : {
          projectId: request.identities.projectId,
          projectRevision: request.revisions.project,
        }),
        ...(mutationBase.minimumBinding === "project+timeline" ? {
          timelineId: request.identities.timelineId,
          timelineRevision: request.revisions.timeline,
        } : {}),
      };
      for (const [key, value] of Object.entries(exact)) {
        if ((mutationBase[key] ?? null) !== (value ?? null)) throw new TypeError(`Prepared mutation base changed exact request binding: ${key}`);
      }
      const forbiddenDeeperBindings = mutationBase.minimumBinding === "account/project-library"
        ? ["projectId", "projectRevision", "timelineId", "timelineRevision"]
        : mutationBase.minimumBinding === "project"
          ? ["timelineId", "timelineRevision"]
          : [];
      if (forbiddenDeeperBindings.some((key) => Object.hasOwn(mutationBase, key))) {
        throw new TypeError("Prepared mutation base exceeded its registered binding depth.");
      }
      if (mutationBase.registryDigest !== PRIVATE_IMPACT_REGISTRY_DIGEST
        || mutationBase.canonicalRequestDigest !== mutationPolicyDigest(request)) {
        throw new TypeError("Prepared mutation base is not bound to the accepted request and private impact registry.");
      }
    }
    prepared = sdkPrepareActionResultSchema.parse(await signedRuntimeClient.prepare({
      request,
      ...(mutationBase ? {mutationBase} : {}),
    }, {...carrierBinding, authenticated}));
    if (prepared.operationClass !== operationClass) throw new TypeError("Signed runtime action class drifted from the authoritative registry.");
    const receiptDigest = preparedActionDigest("receipt", prepared.receipt);
    const impactDigest = preparedActionDigest("impact", {
      contractVersion: prepared.protocolVersion,
      sanitizedCompleteImpact: prepared.impact,
    });
    if (prepared.receiptDigest !== receiptDigest
      || prepared.authorizationBinding.receiptDigest !== receiptDigest
      || prepared.authorizationBinding.impactDigest !== impactDigest
      || Date.parse(prepared.expiresAt) !== prepared.authorizationBinding.expiresAt) {
      throw new TypeError("Signed prepared-action runtime returned inconsistent public bindings.");
    }
    let decision = null;
    let decisionBinding = null;
    let decisionDigest = null;
    let policyAttestation = null;
    if (prepared.operationClass === "mutation") {
      if (!mutationPolicyGate) throw new TypeError("Prepared mutations require Mutation Policy.");
      const protectedTargets = typeof refreshProtectedTargets === "function"
        ? await refreshProtectedTargets(prepared.impact)
        : null;
      decision = mutationPolicyGate.preflight({
        accountFingerprint: authenticated.accountFingerprint,
        impact: prepared.impact,
        currentProtectedTargets: protectedTargets,
      });
      activePolicyDecisions.set(request.executionId, decision.decisionId);
      decisionBinding = policyBinding(decision);
      mutationPolicyGate.revalidateBeforeAuthorization(decision.decisionId, decisionBinding, protectedTargets);
      policyAttestation = JSON.stringify(Object.fromEntries([
        "accountDigest", "impactDigest", "executionDigest", "projectDigest", "timelineDigest", "targetsDigest", "preStateDigest", "receiptDigest",
      ].map(key => [key, prepared.authorizationBinding[key]])));
      decisionDigest = preparedActionDigest("policy-decision", policyAttestation);
      await signedRuntimeClient.acceptPolicy({
        receipt: prepared.receipt,
        policyAttestation,
        policyDecisionDigest: decisionDigest,
      });
    }

    authService.assertCurrent(authenticated);
    await admitOperation({request, prepared, authenticated});
    await lifecycle.admitted?.({request, prepared, authenticated});
    if (decision) {
      const protectedTargets = typeof refreshProtectedTargets === "function"
        ? await refreshProtectedTargets(prepared.impact)
        : null;
      await mutationPolicyGate.consumeBeforeSpawn(decision.decisionId, decisionBinding, protectedTargets);
    }
    await signedRuntimeClient.admit({
      receipt: prepared.receipt,
      ...(decisionDigest ? {policyDecisionDigest: decisionDigest} : {}),
    });
    await markExecuteDispatched({request, prepared, authenticated});
    await lifecycle.executeDispatched?.({request, prepared, authenticated});
    executeDispatched = true;
    // Execute accepts the receipt and nothing else. The signed runtime owns all
    // private lowering, execution, readback, verification, and recovery.
    const terminal = sdkPreparedActionTerminalSchema.parse(
      await signedRuntimeClient.execute({receipt: prepared.receipt}),
    );
    activePolicyDecisions.delete(request.executionId);
    return terminal;
    } catch (error) {
      activePolicyDecisions.delete(request.executionId);
      if (prepared && !executeDispatched && typeof signedRuntimeClient.revoke === "function") {
        try { await signedRuntimeClient.revoke({receipt: prepared.receipt}); } catch { /* Original pre-dispatch failure remains authoritative. */ }
      }
      throw error;
    }
  }

  function assertProtectedState({impact, report} = {}) {
    const executionId = impact?.executionId;
    const decisionId = activePolicyDecisions.get(executionId);
    if (!decisionId || typeof mutationPolicyGate?.assertProtectedStateEvidence !== "function") {
      throw new Error("Prepared mutation protected-state decision is unavailable.");
    }
    return mutationPolicyGate.assertProtectedStateEvidence(decisionId, report);
  }

  async function recoverTerminal(binding, carrierBinding = {}) {
    if (typeof signedRuntimeClient?.recoverTerminal !== "function") throw new Error("Prepared-action terminal recovery is unavailable.");
    const authenticated = await captureAuthenticatedSdkRequest(authService);
    if (carrierBinding.accountFingerprint && carrierBinding.accountFingerprint !== authenticated.accountFingerprint) {
      throw new Error("Prepared-action recovery account binding changed.");
    }
    const terminal = await signedRuntimeClient.recoverTerminal(binding, {...carrierBinding, authenticated});
    return terminal === null ? null : sdkPreparedActionTerminalSchema.parse(terminal);
  }

  return Object.freeze({execute, recoverTerminal, assertProtectedState});
}
