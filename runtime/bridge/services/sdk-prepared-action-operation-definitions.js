import {
  sdkPreparedActionTerminalSchema,
  sdkPrepareActionRequestSchema,
} from "../contracts/generated/sdk-prepared-action.js";

function verification(terminal, capturedAt) {
  return {
    outcome: terminal.verification.outcome,
    summary: terminal.verification.outcome === "passed" ? "The proprietary prepared-action verifier passed." : "The proprietary prepared-action verifier did not prove success.",
    evidence: terminal.verification.evidence.slice(0, 100).map((item, index) => ({
      evidenceId: `evidence_prepared_${String(index).padStart(4, "0")}_${item.digest.slice(7, 23)}`,
      modality: item.modality,
      summary: item.summary,
      capturedAt,
      digest: item.digest,
    })),
    protectedStatePreserved: terminal.verification.protectedStatePreserved,
  };
}

function failure(terminal) {
  const verificationFailure = terminal.failure?.code === "VERIFICATION_FAILED";
  const authenticatedPreMutationStale = terminal.failure?.code === "STALE_REVISION"
    && terminal.possibleMutation === "none"
    && terminal.usage === "released"
    && terminal.failure.readbackRequired === false
    && terminal.recovery.outcome === "not_needed"
    && terminal.recovery.attempted === false
    && terminal.recovery.manualActionRequired === false;
  const unprovenStale = terminal.failure?.code === "STALE_REVISION" && !authenticatedPreMutationStale;
  const possibleMutation = unprovenStale ? "possible" : terminal.possibleMutation;
  return {
    kind: authenticatedPreMutationStale ? "stale_revision" : terminal.status === "recovery_failed" ? "recovery_failed" : verificationFailure ? "verification_failed" : "operation_failed",
    code: authenticatedPreMutationStale ? "STALE_REVISION" : terminal.status === "recovery_failed" ? "RECOVERY_FAILED" : verificationFailure ? "VERIFICATION_FAILED" : "OPERATION_FAILED",
    message: terminal.failure?.message ?? "The prepared action did not complete successfully.",
    retrySafe: false,
    possibleMutation,
    usage: terminal.usage,
    recovery: terminal.recovery.manualActionRequired ? ["inspect_state", "manual_recovery"] : ["inspect_state"],
    recoveryGuidance: terminal.failure?.recoveryGuidance?.length ? terminal.failure.recoveryGuidance : ["Inspect current project state before creating replacement work."],
    readbackRequired: authenticatedPreMutationStale ? false : (terminal.failure?.readbackRequired || possibleMutation !== "none"),
    cause: {code: terminal.failure?.cause?.code ?? terminal.failure?.code ?? "PREPARED_ACTION_FAILED", message: "The proprietary prepared-action runtime reported this terminal cause."},
    ...(terminal.status === "recovery_failed" ? {recoveryOutcome: {status: "failed", summary: "Automatic prepared-action recovery failed.", manualRecoveryRequired: true}} : {}),
  };
}

function projectTerminal(terminal, createdAt, builder) {
  const exact = sdkPreparedActionTerminalSchema.parse(terminal);
  const verificationFailure = exact.failure?.code === "VERIFICATION_FAILED";
  const result = exact.result
    ? (builder.projectResult ? builder.projectResult(exact.result.value) : exact.result.value)
    : {resultOmitted: exact.resultOmitted ?? {code: "OUTPUT_LIMIT_REACHED"}};
  const projectedFailure = exact.status === "succeeded" ? null : failure(exact);
  const semanticNoChange = exact.status === "succeeded"
    && result?.actionId === "cutagent.action.sdk.fairlight.plan.apply"
    && result?.outcome === "no_change";
  const common = {
    possibleMutation: projectedFailure?.possibleMutation ?? (semanticNoChange ? "none" : exact.possibleMutation),
    usage: exact.usage,
    preparedActionTerminal: exact,
  };
  if (exact.status === "succeeded") return {...common, status: "succeeded", result, verification: verification(exact, createdAt)};
  if (exact.status === "recovery_failed") return {
    ...common, status: "recovery_failed", ...(exact.result ? {result} : {}), failure: projectedFailure,
    ...(exact.verification.evidence.length > 0 ? {verification: verification(exact, createdAt)} : {}),
    recovery: {state: "failed", summary: "Automatic prepared-action recovery failed.", evidence: verification(exact, createdAt).evidence, manualRecoveryRequired: true},
  };
  return {
    ...common,
    status: verificationFailure ? "verification_failed" : "failed",
    ...(exact.result ? {result} : {}),
    failure: projectedFailure,
    ...(verificationFailure ? {verification: verification(exact, createdAt)} : {}),
  };
}

function preDispatchCapabilityFailure(error) {
  if (!["CAPABILITY_NEGOTIATION_FAILED", "CAPABILITY_UNAVAILABLE"].includes(error?.code)) return null;
  return {
    status: "failed",
    possibleMutation: "none",
    usage: "not_reserved",
    failure: {
      kind: "capability_unavailable",
      code: "CAPABILITY_UNAVAILABLE",
      message: "The requested action is unavailable for the exact current target.",
      retrySafe: false,
      possibleMutation: "none",
      usage: "not_reserved",
      recovery: ["inspect_state"],
      recoveryGuidance: ["Inspect the exact current target and choose one that supports this action."],
      readbackRequired: false,
      cause: {
        code: error.code,
        message: "The live pre-dispatch capability check rejected the exact target.",
      },
    },
  };
}

/** Adapts fixed local builders to the durable public operation authority. */
export function createSdkPreparedActionOperationDefinitions({builders = {}, coordinator, advertisedActionIds = null, assertAdvertised = null} = {}) {
  if (typeof coordinator?.execute !== "function") throw new TypeError("Prepared-action operation definitions require a coordinator.");
  const advertised = advertisedActionIds === null ? null : new Set(advertisedActionIds);
  const lifecycles = new Map();
  return Object.fromEntries(Object.entries(builders).map(([actionId, builder]) => {
    if (advertised && !advertised.has(actionId)) throw new Error(`Prepared action is locally registered but not signed-host advertised: ${actionId}`);
    if (typeof builder?.inputSchema?.parse !== "function" || typeof builder?.buildRequest !== "function") throw new TypeError(`Prepared action builder is incomplete: ${actionId}`);
    return [actionId, {
      inputSchema: builder.inputSchema,
      resultSchema: builder.resultSchema ?? {parse(value) { return value; }},
      idempotency: "required",
      async execute(context, normalizedInput) {
        const lifecycle = {cancelled: false, dispatched: false};
        lifecycles.set(context.operationId, lifecycle);
        try {
          const request = sdkPrepareActionRequestSchema.parse(await builder.buildRequest({context, input: normalizedInput}));
          if (request.actionId !== actionId || request.requestId !== context.requestId
            || request.operationId !== context.operationId || request.executionId !== context.executionId
            || request.idempotencyKey !== context.idempotencyKey) throw new TypeError("Prepared-action builder changed durable operation identity.");
          context.bindPreparedActionRequest(request);
          const carrierBinding = {sdkSessionId: context.sdkSessionId, accountFingerprint: context.accountFingerprint};
          if (assertAdvertised && await assertAdvertised(actionId, request, carrierBinding) !== true) throw new Error(`Prepared action is not signed-host advertised: ${actionId}`);
          try {
            return projectTerminal(await coordinator.execute(request, {
              executeDispatched() {
                if (lifecycle.cancelled) {
                  const error = new Error("Prepared action was cancelled before dispatch.");
                  error.code = "CANCELLED";
                  throw error;
                }
                context.reservePreparedTerminal();
                lifecycle.dispatched = true;
                context.reportExecutionStarted();
              },
            }, carrierBinding), context.createdAt, builder);
          } catch (error) {
            const failure = lifecycle.dispatched ? null : preDispatchCapabilityFailure(error);
            if (failure) return failure;
            throw error;
          }
        } finally {
          lifecycles.delete(context.operationId);
          await builder.releasePrivateRuntimeBinding?.(context.operationId);
        }
      },
      projectPreparedTerminal(terminal, createdAt) { return projectTerminal(terminal, createdAt, builder); },
      async cancel(context) {
        const lifecycle = lifecycles.get(context.operationId);
        if (!lifecycle) return {confirmed: false, reason: "The prepared action no longer has active runtime custody."};
        if (lifecycle.dispatched) {
          if (typeof builder.requestCancellation !== "function") {
            return {confirmed: false, reason: "The prepared action already reached execution dispatch."};
          }
          return builder.requestCancellation(context);
        }
        lifecycle.cancelled = true;
        return {confirmed: true, possibleMutation: "none", usage: "released", readbackRequired: false};
      },
      async reconcile(context, normalizedInput) {
        try {
          if (context.idempotencyKey && typeof coordinator.recoverTerminal === "function") {
            const persistedRequest = context.preparedActionRequest?.();
            if (persistedRequest === null || persistedRequest === undefined) {
              throw new Error("Prepared-action recovery requires its persisted original request.");
            }
            const request = sdkPrepareActionRequestSchema.parse(persistedRequest);
            const terminal = await coordinator.recoverTerminal({
              actionId,
              idempotencyKey: context.idempotencyKey,
              operationId: context.operationId,
              executionId: context.executionId,
            }, {request, sdkSessionId: context.sdkSessionId, accountFingerprint: context.accountFingerprint});
            if (terminal) return projectTerminal(terminal, context.createdAt, builder);
          }
          return {status: "recovery_failed", possibleMutation: "unknown", usage: "unknown", failure: {
            kind: "recovery_failed", code: "RECOVERY_FAILED", message: "An interrupted prepared action requires authoritative readback.", retrySafe: false,
            possibleMutation: "unknown", usage: "unknown", recovery: ["inspect_state", "manual_recovery"], recoveryGuidance: ["Inspect affected project state before any retry."],
            recoveryOutcome: {status: "failed", summary: "The signed prepared-action terminal was unavailable after restart.", manualRecoveryRequired: true}, readbackRequired: true,
          }, recovery: {state: "failed", summary: "Prepared-action restart reconciliation requires manual readback.", evidence: [], manualRecoveryRequired: true}};
        } finally {
          await builder.releasePrivateRuntimeBinding?.(context.operationId);
        }
      },
    }];
  }));
}
