import {
  sdkPrepareActionRequestSchema,
  sdkPrepareActionResultSchema,
  sdkPreparedActionMutationBaseSchema,
  sdkPreparedActionTerminalSchema,
} from "../contracts/generated/sdk-prepared-action.js";
import {CUTAGENT_PREPARED_ACTION_ACTION_METADATA} from "../contracts/sdk-prepared-action-metadata.generated.js";
import { captureAuthenticatedSdkRequest } from "./sdk-authenticated-request.js";
import { preparedActionDigest } from "./sdk-prepared-action-digest.js";
import { preparedActionRequestDigest, PRIVATE_IMPACT_REGISTRY_DIGEST } from "./sdk-prepared-action-request-integrity.js";

/**
 * Route-neutral Bridge coordinator. It never receives command identity, argv,
 * private lowering, execution route, verifier plan, or recovery metadata.
 */
export function createSdkPreparedActionCoordinator({
  signedRuntimeClient,
  authorizationService,
  authService,
  admitOperation = async () => {},
  markExecuteDispatched = async () => {},
  mutationBaseAuthority = null,
} = {}) {
  for (const [name, method] of Object.entries({
    prepare: signedRuntimeClient?.prepare,
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
        || mutationBase.canonicalRequestDigest !== preparedActionRequestDigest(request)) {
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
    authService.assertCurrent(authenticated);
    await admitOperation({request, prepared, authenticated});
    await lifecycle.admitted?.({request, prepared, authenticated});
    await signedRuntimeClient.admit({
      receipt: prepared.receipt,
    });
    await markExecuteDispatched({request, prepared, authenticated});
    await lifecycle.executeDispatched?.({request, prepared, authenticated});
    executeDispatched = true;
    // Execute accepts the receipt and nothing else. The signed runtime owns all
    // private lowering, execution, readback, verification, and recovery.
    const terminal = sdkPreparedActionTerminalSchema.parse(
      await signedRuntimeClient.execute({receipt: prepared.receipt}),
    );
    return terminal;
    } catch (error) {
      if (prepared && !executeDispatched && typeof signedRuntimeClient.revoke === "function") {
        try { await signedRuntimeClient.revoke({receipt: prepared.receipt}); } catch { /* Original pre-dispatch failure remains authoritative. */ }
      }
      throw error;
    }
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

  return Object.freeze({execute, recoverTerminal});
}
