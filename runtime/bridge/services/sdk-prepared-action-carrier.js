import {createSdkPreparedActionCoordinator} from "./sdk-prepared-action-coordinator.js";
import {createSdkPreparedActionOperationDefinitions} from "./sdk-prepared-action-operation-definitions.js";
import {createSdkPreparedActionMutationBaseAuthority} from "./sdk-prepared-action-mutation-base-authority.js";
import {CUTAGENT_PREPARED_ACTION_ACTION_METADATA} from "../contracts/sdk-prepared-action-metadata.generated.js";
import {
  CUTAGENT_PREPARED_ACTION_CAPABILITY_DIGEST,
  CUTAGENT_PREPARED_ACTION_CONTRACT_DIGEST,
  CUTAGENT_PREPARED_ACTION_PROTOCOL_VERSION,
  sdkPreparedActionIdentitiesSchema,
  sdkPreparedActionRevisionsSchema,
} from "../contracts/generated/sdk-prepared-action.js";

/**
 * Private domain contribution shape. Domains capture exact live identity and
 * revision truth; this carrier alone lowers the immutable prepared request.
 */
export function createSdkPreparedActionBuilderContribution({
  inputSchema,
  captureRequestBinding,
  mutationBinding = null,
  requestCancellation = null,
  resultSchema = null,
  projectResult = null,
} = {}) {
  if (typeof inputSchema?.parse !== "function" || typeof captureRequestBinding !== "function") {
    throw new TypeError("Prepared-action contribution requires an input schema and exact binding capture.");
  }
  if (requestCancellation !== null && typeof requestCancellation !== "function") {
    throw new TypeError("Prepared-action cancellation authority must be callable.");
  }
  if ((resultSchema === null) !== (projectResult === null)
    || (resultSchema !== null && typeof resultSchema?.parse !== "function")
    || (projectResult !== null && typeof projectResult !== "function")) {
    throw new TypeError("Prepared-action public result projection requires both a result schema and projector.");
  }
  return Object.freeze({
    inputSchema,
    captureRequestBinding,
    ...(mutationBinding ? {mutationBinding: Object.freeze(mutationBinding)} : {}),
    ...(requestCancellation ? {requestCancellation} : {}),
    ...(resultSchema ? {resultSchema, projectResult} : {}),
  });
}

/** Compose only explicitly contributed actions from authoritative metadata. */
export function buildProductionSdkPreparedActionBuilders({contributions = {}, capturePrivateRuntimeBinding = null, releasePrivateRuntimeBinding = null} = {}) {
  const builders = {};
  for (const [actionId, contribution] of Object.entries(contributions)) {
    if (!CUTAGENT_PREPARED_ACTION_ACTION_METADATA[actionId]) throw new Error(`Prepared-action builder contribution is not generated: ${actionId}`);
    if (Object.hasOwn(builders, actionId)) throw new Error(`Prepared-action builder contribution collides: ${actionId}`);
    if (typeof contribution?.inputSchema?.parse !== "function" || typeof contribution?.captureRequestBinding !== "function") {
      throw new TypeError(`Prepared-action builder contribution is incomplete: ${actionId}`);
    }
    const metadata = CUTAGENT_PREPARED_ACTION_ACTION_METADATA[actionId];
    if (metadata.operationClass === "mutation" && !contribution.mutationBinding) {
      throw new TypeError(`Prepared mutation contribution omitted its target binding: ${actionId}`);
    }
    if (metadata.operationClass === "read" && contribution.mutationBinding) {
      throw new TypeError(`Prepared read contribution cannot declare mutation impact: ${actionId}`);
    }
    builders[actionId] = Object.freeze({
      inputSchema: contribution.inputSchema,
      ...(contribution.resultSchema ? {
        resultSchema: contribution.resultSchema,
        projectResult: contribution.projectResult,
      } : {}),
      ...(contribution.mutationBinding ? {mutationBinding: contribution.mutationBinding} : {}),
      ...(contribution.requestCancellation ? {requestCancellation: contribution.requestCancellation} : {}),
      ...(typeof releasePrivateRuntimeBinding === "function" ? {releasePrivateRuntimeBinding} : {}),
      async buildRequest({context, input}) {
        const bindingContext = Object.freeze(Object.fromEntries([
          "accountFingerprint", "sdkSessionId", "requestId", "operationId", "executionId", "idempotencyKey",
        ].filter((key) => context[key] !== undefined).map((key) => [key, context[key]])));
        const captured = await contribution.captureRequestBinding({context: bindingContext, input: structuredClone(input)});
        const identities = sdkPreparedActionIdentitiesSchema.parse(captured?.identities);
        const revisions = sdkPreparedActionRevisionsSchema.parse(captured?.revisions);
        if (typeof capturePrivateRuntimeBinding === "function") {
          await capturePrivateRuntimeBinding({
            actionId,
            requestId: context.requestId,
            operationId: context.operationId,
            executionId: context.executionId,
            identities: structuredClone(identities),
            revisions: structuredClone(revisions),
            privateContext: structuredClone(captured?.privateContext ?? {}),
          });
        } else if (captured?.privateContext !== undefined) {
          throw new TypeError(`Prepared-action private binding has no carrier custody: ${actionId}`);
        }
        return {
          protocolVersion: CUTAGENT_PREPARED_ACTION_PROTOCOL_VERSION,
          actionId,
          actionContractVersion: metadata.version,
          input,
          contractDigest: CUTAGENT_PREPARED_ACTION_CONTRACT_DIGEST,
          capabilityDigest: CUTAGENT_PREPARED_ACTION_CAPABILITY_DIGEST,
          identities,
          revisions,
          idempotencyKey: context.idempotencyKey,
          requestId: context.requestId,
          operationId: context.operationId,
          executionId: context.executionId,
        };
      },
    });
  }
  return Object.freeze(builders);
}

/**
 * Production composition point. A fixed builder can only execute through the
 * persistent signed client whose registry independently advertises that action.
 */
export function createSdkPreparedActionCarrier({
  builders = null,
  runtimeClientFactory = null,
  authorizationService = null,
  authService = null,
  builderContributions = {},
  capturePrivateRuntimeBinding = null,
  releasePrivateRuntimeBinding = null,
  resolveLiveTargets = null,
} = {}) {
  builders ??= runtimeClientFactory
    ? buildProductionSdkPreparedActionBuilders({contributions: builderContributions, capturePrivateRuntimeBinding, releasePrivateRuntimeBinding})
    : Object.freeze({});
  if (Object.keys(builders).length === 0) return Object.freeze({actions: Object.freeze({}), close() {}});
  if (typeof runtimeClientFactory !== "function") throw new TypeError("Registered prepared actions require the signed runtime client factory.");
  const clients = new Map();
  const receiptClients = new Map();
  const clientKeys = new WeakMap();
  const clientReceiptCounts = new Map();
  let coordinator = null;
  const expectedAdvertisedActionIds = Object.freeze(Object.keys(builders).sort());
  const bindingKey = ({request, authenticated, accountFingerprint, sdkSessionId}) => JSON.stringify({
    accountFingerprint: authenticated?.accountFingerprint ?? accountFingerprint ?? null,
    sdkSessionId,
    identities: request.identities,
    revisions: request.revisions,
    operationId: request.operationId,
    executionId: request.executionId,
  });
  const clientFor = (binding) => {
    const key = bindingKey(binding);
    let entry = clients.get(key);
    if (!entry) {
      entry = Promise.resolve().then(() => runtimeClientFactory({
        ...binding,
        advertisedActionIds: expectedAdvertisedActionIds,
        ...(typeof resolveLiveTargets === "function" ? {resolveLiveTargets} : {}),
      })).then((runtime) => {
        if (!Array.isArray(runtime?.advertisedActionIds)
          || JSON.stringify([...runtime.advertisedActionIds].sort()) !== JSON.stringify(expectedAdvertisedActionIds)) {
          void runtime?.close?.().catch(() => {});
          throw new Error("Signed prepared-action advertisement differs from the exact production builder registry.");
        }
        clientKeys.set(runtime, key);
        return runtime;
      });
      clients.set(key, entry);
      void entry.catch(() => {
        if (clients.get(key) === entry) clients.delete(key);
      });
    }
    return entry;
  };
  const releaseRuntime = async (runtime) => {
    const remaining = (clientReceiptCounts.get(runtime) ?? 1) - 1;
    if (remaining > 0) {
      clientReceiptCounts.set(runtime, remaining);
      return;
    }
    clientReceiptCounts.delete(runtime);
    const key = clientKeys.get(runtime);
    if (key && await clients.get(key)?.catch(() => null) === runtime) clients.delete(key);
    await runtime.close?.().catch(() => {});
  };
  const discardIdleRuntime = async (runtime) => {
    if ((clientReceiptCounts.get(runtime) ?? 0) !== 0) return;
    const key = clientKeys.get(runtime);
    if (key && await clients.get(key)?.catch(() => null) === runtime) clients.delete(key);
    await runtime.close?.().catch(() => {});
  };
  const receiptRuntime = async (payload, method) => {
    const receipt = payload?.receipt;
    const runtime = receiptClients.get(receipt);
    if (!runtime) throw new Error("Prepared-action receipt has no exact signed runtime custody.");
    if (typeof runtime?.[method] !== "function") throw new Error(`Signed prepared-action runtime omitted ${method}.`);
    const terminalMethod = ["execute", "revoke"].includes(method);
    try {
      const value = await runtime[method](payload);
      if (method === "execute") await runtime.publishTerminalArtifacts?.(value);
      return value;
    } finally {
      if (terminalMethod) {
        receiptClients.delete(receipt);
        await releaseRuntime(runtime);
      }
    }
  };
  const signedRuntimeClient = {
    async prepare(payload, binding) {
      const runtime = await clientFor({...binding, request: payload.request});
      try {
        if (typeof runtime?.prepare !== "function") throw new Error("Signed prepared-action runtime omitted prepare.");
        if (runtime.hasAction(payload.request.actionId) !== true) throw new Error(`Prepared action is not signed-host advertised: ${payload.request.actionId}`);
        const prepared = await runtime.prepare(payload);
        receiptClients.set(prepared.receipt, runtime);
        clientReceiptCounts.set(runtime, (clientReceiptCounts.get(runtime) ?? 0) + 1);
        return prepared;
      } catch (error) {
        await runtime.releasePreDispatchReservations?.();
        await discardIdleRuntime(runtime);
        throw error;
      }
    },
    admit(payload) { return receiptRuntime(payload, "admit"); },
    execute(payload) { return receiptRuntime(payload, "execute"); },
    revoke(payload) { return receiptRuntime(payload, "revoke"); },
    async recoverTerminal(payload, binding) {
      const runtime = await clientFor({...binding, request: binding.request, terminalRecovery: true});
      try {
        if (typeof runtime?.recoverTerminal !== "function") throw new Error("Signed prepared-action runtime omitted recoverTerminal.");
        const terminal = await runtime.recoverTerminal(payload);
        if (terminal) await runtime.publishTerminalArtifacts?.(terminal);
        return terminal;
      } finally {
        await discardIdleRuntime(runtime);
      }
    },
  };
  const mutationRegistrations = Object.fromEntries(Object.entries(builders)
    .filter(([actionId]) => CUTAGENT_PREPARED_ACTION_ACTION_METADATA[actionId]?.operationClass === "mutation")
    .map(([actionId, builder]) => [actionId, builder.mutationBinding]));
  const mutationBaseAuthority = Object.keys(mutationRegistrations).length
      ? createSdkPreparedActionMutationBaseAuthority({
        registrations: mutationRegistrations,
      })
    : null;
  coordinator = createSdkPreparedActionCoordinator({
    signedRuntimeClient,
    authorizationService,
    authService,
    mutationBaseAuthority,
  });
  const actions = createSdkPreparedActionOperationDefinitions({builders, coordinator});
  return Object.freeze({
    actions: Object.freeze(actions),
    async close() {
      const active = [...clients.values()];
      clients.clear();
      receiptClients.clear();
      clientReceiptCounts.clear();
      await Promise.all(active.map(async (entry) => {
        const runtime = await entry.catch(() => null);
        await runtime?.close?.().catch(() => {});
      }));
    },
  });
}
