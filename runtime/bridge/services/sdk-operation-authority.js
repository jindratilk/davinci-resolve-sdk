import crypto from "node:crypto";
import {
  CUTAGENT_SDK_ACTION_CONTRACT_VERSION,
  sdkOperationProgressSchema,
  sdkOperationResultCollectionDigestSchema,
  sdkOperationResultCollectionIdSchema,
  sdkOperationResultPageSchema,
  sdkOperationSnapshotSchema,
  sdkPublicActionIdSchema,
  sdkPublicFailureSchema,
} from "../contracts/generated/sdk-operations.js";
import {
  sdkIdempotencyKeySchema,
  sdkOperationIdSchema,
  sdkRequestIdSchema,
  sdkSessionIdSchema,
} from "../contracts/generated/sdk-identities.js";
import {
  canonicalSdkOperationInput,
  sdkOperationInputDigest,
} from "./sdk-operation-input.js";
import { createSdkOperationTerminal } from "./sdk-operation-terminal.js";
import { MutationPolicyError } from "./mutation-policy/mutation-policy-gate.js";
import { getSdkOwnerSession, runWithSdkOwnerSession } from "./sdk-owner-session-context.js";

export const DEFAULT_SDK_RESULT_RETENTION_MS = 24 * 60 * 60 * 1000;
export const DEFAULT_SDK_IDEMPOTENCY_TOMBSTONE_MS = 7 * 24 * 60 * 60 * 1000;
const TERMINAL = new Set(["succeeded", "failed", "cancelled", "partially_applied", "verification_failed", "recovery_failed"]);
function opaque(prefix) {
  return `${prefix}${crypto.randomUUID()}`;
}

function iso(value) {
  return new Date(value).toISOString();
}

function operationCommon(snapshot) {
  return {
    operationId: snapshot.operationId,
    requestId: snapshot.requestId,
    executionId: snapshot.executionId,
    actionId: snapshot.actionId,
    actionContractVersion: snapshot.actionContractVersion,
    createdAt: snapshot.createdAt,
    idempotency: snapshot.idempotency,
  };
}

function expiredFailure(operationId, { retainedIdempotency = false } = {}) {
  return sdkPublicFailureSchema.parse({
    kind: "operation_expired",
    code: "OPERATION_EXPIRED",
    message: "The operation is unavailable or its retained result has expired.",
    retrySafe: false,
    possibleMutation: retainedIdempotency ? "possible" : "none",
    usage: "not_reserved",
    recovery: retainedIdempotency ? ["inspect_state", "contact_support"] : ["contact_support"],
    recoveryGuidance: ["Do not create replacement work unless the idempotency horizon has expired and current project state has been inspected."],
    readbackRequired: retainedIdempotency,
    operationId,
  });
}

function collectionUnavailableFailure(operationId) {
  return sdkPublicFailureSchema.parse({
    kind: "target_not_found",
    code: "TARGET_NOT_FOUND",
    message: "The requested retained result collection is unavailable or no longer matches its digest.",
    retrySafe: false,
    possibleMutation: "none",
    usage: "not_reserved",
    recovery: ["inspect_state", "contact_support"],
    recoveryGuidance: ["Refresh the operation and use only its current result-page reference."],
    readbackRequired: false,
    operationId,
  });
}

export class SdkOperationAuthorityError extends Error {
  constructor(failure) {
    const validated = sdkPublicFailureSchema.parse(failure);
    super(validated.message);
    this.name = "SdkOperationAuthorityError";
    this.failure = validated;
  }
}

function validateDuration(value, label) {
  if (!Number.isInteger(value) || value < 1_000 || value > 30 * 24 * 60 * 60 * 1000) {
    throw new Error(`${label} must be a bounded positive duration.`);
  }
}

/**
 * One proprietary durable SDK-operation authority. It owns persistence,
 * idempotency, sequence, cancellation truth, and restart reconciliation; SDK
 * sessions and public carriers own none of those state machines.
 */
export function createSdkOperationAuthority({
  repo,
  actions = {},
  now = () => Date.now(),
  resultRetentionMs = DEFAULT_SDK_RESULT_RETENTION_MS,
  idempotencyTombstoneMs = DEFAULT_SDK_IDEMPOTENCY_TOMBSTONE_MS,
  onExecutorError = null,
  resolveOwnerSession = null,
} = {}) {
  if (!repo?.installationAuthority) throw new Error("SDK operation authority requires its dedicated repository.");
  validateDuration(resultRetentionMs, "resultRetentionMs");
  validateDuration(idempotencyTombstoneMs, "idempotencyTombstoneMs");
  if (idempotencyTombstoneMs <= resultRetentionMs) {
    throw new Error("Idempotency tombstone retention must outlive operation result retention.");
  }
  const definitions = new Map(Object.entries(actions));
  const dispatches = new Set();
  let authorityFailure = null;

  function withOwnerSession(ownerSessionId, ownerRuntimeRequired, operation) {
    if (!ownerSessionId) return operation();
    const session = resolveOwnerSession?.(ownerSessionId, { requireRuntime: ownerRuntimeRequired === true }) ?? null;
    if (!session) {
      const error = new Error("The CutAgent chat that owns this SDK operation is no longer available.");
      error.code = "SDK_OWNER_SESSION_UNAVAILABLE";
      throw error;
    }
    return runWithSdkOwnerSession(session, operation);
  }

  function reportExecutorError(record, phase, error) {
    try {
      const errorCode = typeof error?.code === "string" && error.code ? error.code.slice(0, 120) : null;
      const hostPhase = typeof error?.hostPhase === "string" && error.hostPhase ? error.hostPhase.slice(0, 100) : null;
      const reason = typeof error?.privateReason === "string" && error.privateReason ? error.privateReason.slice(0, 500) : null;
      onExecutorError?.({
        phase,
        actionId: record.public.actionId,
        operationId: record.public.operationId,
        executionId: record.public.executionId,
        errorClass: typeof error?.name === "string" && error.name ? error.name.slice(0, 100) : "Error",
        message: typeof error?.message === "string" && error.message ? error.message.slice(0, 500) : "SDK operation executor threw a non-Error value.",
        ...(errorCode ? {errorCode} : {}),
        ...(hostPhase ? {hostPhase} : {}),
        ...(reason ? {reason} : {}),
      });
    } catch {
      // Private diagnostics must never alter durable terminal truth.
    }
  }

  const {
    genericExecutionFailure,
    normalizeTerminalOutcome,
    transitionTerminal,
  } = createSdkOperationTerminal({
    repo,
    now,
    resultRetentionMs,
    idempotencyTombstoneMs,
    terminalStatuses: TERMINAL,
    onNormalizationError: (record, error) => reportExecutorError(record, "terminal.normalize", error),
  });

  function failAuthority(error) {
    if (authorityFailure) return authorityFailure;
    authorityFailure = Object.assign(
      new Error("SDK operation durable authority became unavailable.", {cause: error}),
      {code: "SDK_OPERATION_AUTHORITY_UNAVAILABLE"},
    );
    return authorityFailure;
  }

  function assertAuthorityAvailable() {
    if (authorityFailure) throw authorityFailure;
    repo.assertOwnership?.();
  }

  function requireDefinition(actionId) {
    const definition = definitions.get(actionId);
    if (!definition) {
      throw new SdkOperationAuthorityError({
        kind: "capability_unavailable",
        code: "CAPABILITY_UNAVAILABLE",
        message: "This operation action has no accepted semantic executor.",
        retrySafe: false,
        possibleMutation: "none",
        usage: "not_reserved",
        recovery: ["update_required"],
        recoveryGuidance: ["Update CutAgent after this action is activated for the selected distribution."],
        readbackRequired: false,
      });
    }
    if (typeof definition.inputSchema?.parse !== "function"
      || typeof definition.resultSchema?.parse !== "function"
      || typeof definition.execute !== "function") {
        throw new Error(`SDK operation action definition is incomplete: ${actionId}`);
    }
    return definition;
  }

  function idempotencyConflict(reservation, idempotencyKey) {
    return new SdkOperationAuthorityError({
      kind: "idempotency_conflict",
      code: "IDEMPOTENCY_CONFLICT",
      message: "This idempotency key is already reserved for different normalized work.",
      retrySafe: false,
      possibleMutation: "none",
      usage: "not_reserved",
      recovery: ["inspect_state", "contact_support"],
      recoveryGuidance: ["Reuse a key only with the exact same action and normalized input."],
      readbackRequired: false,
      idempotencyKey,
      operationId: reservation.operationId,
    });
  }

  function requireOwned(operationId, accountFingerprint, { allowExpired = false, ownerSessionId = undefined } = {}) {
    const validatedId = sdkOperationIdSchema.parse(operationId);
    const record = repo.getOperation(validatedId, { cleanupAt: now() });
    const effectiveOwnerSessionId = ownerSessionId !== undefined
      ? ownerSessionId
      : getSdkOwnerSession()?.id;
    if (!record
      || record.private.accountFingerprint !== accountFingerprint
      || (effectiveOwnerSessionId !== undefined && (record.private.ownerSessionId ?? null) !== effectiveOwnerSessionId)
      || record.private.installationAuthority !== repo.installationAuthority) {
      throw new SdkOperationAuthorityError(expiredFailure(validatedId));
    }
    if (!allowExpired
      && record.public.retentionExpiresAt
      && Date.parse(record.public.retentionExpiresAt) <= now()) {
      throw new SdkOperationAuthorityError(expiredFailure(validatedId, {
        retainedIdempotency: Boolean(record.public.idempotency),
      }));
    }
    return record;
  }

  function activeTransition(operationId, update) {
    for (let attempts = 0; attempts < 8; attempts += 1) {
      const record = repo.getOperation(operationId);
      if (!record || TERMINAL.has(record.public.status)) return record;
      const next = update(record);
      if (!next) return record;
      const transitioned = repo.transition(operationId, record.public.sequence, () => next);
      if (transitioned !== false) return transitioned;
    }
    throw new Error("SDK operation transition contention exceeded its bound.");
  }

  async function dispatch(operationId, definition) {
    let record = activeTransition(operationId, (current) => {
      if (current.public.status !== "queued") return null;
      return {
        ...current,
        public: sdkOperationSnapshotSchema.parse({
          ...operationCommon(current.public),
          status: "running",
          sequence: current.public.sequence + 1,
          updatedAt: iso(now()),
          progress: { phase: "executing", overallFraction: 0, phaseFraction: 0 },
          possibleMutation: "none",
          usage: "reserved",
        }),
      };
    });
    if (!record || record.public.status !== "running") return;

    const context = Object.freeze({
      operationId,
      executionId: record.public.executionId,
      requestId: record.public.requestId,
      createdAt: record.public.createdAt,
      accountFingerprint: record.private.accountFingerprint,
      sdkSessionId: record.private.sdkSessionId ?? null,
      idempotencyKey: record.public.idempotency?.key ?? null,
      reportProgress(progress, { waitingFor = null } = {}) {
        const parsedProgress = sdkOperationProgressSchema.parse(progress);
        return activeTransition(operationId, (current) => {
          if (!["running", "waiting"].includes(current.public.status)) return null;
          const before = current.public.progress;
          if (before?.overallFraction !== undefined
            && parsedProgress.overallFraction !== undefined
            && parsedProgress.overallFraction < before.overallFraction) {
            throw new Error("SDK executor attempted to regress overall progress.");
          }
          if (before?.phase === parsedProgress.phase
            && before.phaseFraction !== undefined
            && parsedProgress.phaseFraction !== undefined
            && parsedProgress.phaseFraction < before.phaseFraction) {
            throw new Error("SDK executor attempted to regress phase progress.");
          }
          return {
            ...current,
            public: sdkOperationSnapshotSchema.parse({
              ...operationCommon(current.public),
              status: waitingFor ? "waiting" : "running",
              sequence: current.public.sequence + 1,
              updatedAt: iso(now()),
              progress: parsedProgress,
              ...(waitingFor ? { waitingFor } : {}),
              possibleMutation: current.public.possibleMutation,
              usage: current.public.usage,
            }),
          };
        })?.public ?? null;
      },
      reportExecutionStarted() {
        return activeTransition(operationId, (current) => {
          if (!["running", "waiting", "cancellation_requested"].includes(current.public.status)) return null;
          if (current.public.possibleMutation === "possible" && current.public.usage === "consumed") return null;
          return {
            ...current,
            public: sdkOperationSnapshotSchema.parse({
              ...current.public,
              sequence: current.public.sequence + 1,
              updatedAt: iso(now()),
              possibleMutation: "possible",
              usage: "consumed",
            }),
          };
        })?.public ?? null;
      },
      reservePreparedTerminal() {
        return repo.reservePreparedTerminal(operationId);
      },
      bindPreparedActionRequest(request) {
        return repo.bindPreparedActionRequest(operationId, request);
      },
      preparedActionRequest() {
        return structuredClone(repo.getOperation(operationId)?.private?.preparedActionRequest ?? null);
      },
      isCancellationRequested() {
        return repo.getOperation(operationId)?.public.status === "cancellation_requested";
      },
      cancellationRequestedAt() {
        const snapshot = repo.getOperation(operationId)?.public;
        return snapshot?.status === "cancellation_requested" ? snapshot.cancellation.requestedAt : null;
      },
    });

    let outcome;
    try {
      outcome = await withOwnerSession(
        record.private.ownerSessionId ?? null,
        record.private.ownerRuntimeRequired === true,
        () => definition.execute(context, structuredClone(record.private.normalizedInput)),
      );
    } catch (error) {
      const current = repo.getOperation(operationId) ?? record;
      if (TERMINAL.has(current.public.status)) return;
      reportExecutorError(current, "definition.execute", error);
      outcome = error instanceof MutationPolicyError
        && current.public.possibleMutation === "none"
        ? {
            status: "failed",
            possibleMutation: "none",
            usage: "not_reserved",
            failure: error.failure,
          }
        : genericExecutionFailure(current);
    }
    record = repo.getOperation(operationId) ?? record;
    if (TERMINAL.has(record.public.status)) return;
    const normalized = normalizeTerminalOutcome(record, definition, outcome);
    try {
      transitionTerminal(record, normalized);
    } catch (error) {
      reportExecutorError(record, "terminal.transition", error);
      const current = repo.getOperation(operationId) ?? record;
      if (!TERMINAL.has(current.public.status)) {
        try {
          transitionTerminal(current, genericExecutionFailure(current));
        } catch (fallbackError) {
          throw failAuthority(new AggregateError(
            [error, fallbackError],
            "SDK operation terminal persistence failed.",
          ));
        }
      }
    }
  }

  function trackDispatch(operationId, definition) {
    const task = Promise.resolve()
      .then(() => dispatch(operationId, definition))
      .catch((error) => { throw failAuthority(error); });
    dispatches.add(task);
    void task.finally(() => dispatches.delete(task)).catch(() => {});
  }

  async function reconcileRecord(record) {
    const definition = definitions.get(record.public.actionId);
    const preparedJournal = repo.readPreparedTerminalJournal?.(record.public.operationId);
    if (preparedJournal && typeof definition?.projectPreparedTerminal === "function") {
      const outcome = definition.projectPreparedTerminal(preparedJournal, record.public.createdAt);
      transitionTerminal(record, normalizeTerminalOutcome(record, definition, outcome));
      return;
    }
    if (record.public.status === "queued") {
      transitionTerminal(record, {
        status: "failed",
        possibleMutation: "none",
        usage: "not_reserved",
        failure: {
          kind: "operation_failed",
          code: "OPERATION_FAILED",
          message: "The operation was interrupted before execution began.",
          retrySafe: false,
          possibleMutation: "none",
          usage: "not_reserved",
          recovery: ["contact_support"],
          recoveryGuidance: ["Use the original idempotency identity when asking CutAgent support about this operation."],
          readbackRequired: false,
        },
      });
      return;
    }
    let reconcilerInput;
    try {
      reconcilerInput = canonicalSdkOperationInput(definition.inputSchema.parse(record.private.normalizedInput));
      if (sdkOperationInputDigest(reconcilerInput) !== record.private.normalizedInputDigest) {
        throw new Error("Persisted SDK operation input digest mismatch.");
      }
    } catch {
      reconcilerInput = null;
    }
    if (reconcilerInput !== null && typeof definition?.reconcile === "function") {
      try {
        const outcome = await withOwnerSession(
          record.private.ownerSessionId ?? null,
          record.private.ownerRuntimeRequired === true,
          () => definition.reconcile({
          accountFingerprint: record.private.accountFingerprint,
          operationId: record.public.operationId,
          executionId: record.public.executionId,
          requestId: record.public.requestId,
          idempotencyKey: record.public.idempotency?.key,
          sdkSessionId: record.private.sdkSessionId,
          createdAt: record.public.createdAt,
          snapshot: structuredClone(record.public),
          preparedActionRequest() {
            return structuredClone(record.private.preparedActionRequest ?? null);
          },
          }, structuredClone(reconcilerInput)),
        );
        transitionTerminal(record, normalizeTerminalOutcome(record, definition, outcome));
        return;
      } catch {
        // Fall through to truthful uncertain-work terminalization.
      }
    }
    const possibleMutation = record.public.possibleMutation === "none" ? "possible" : record.public.possibleMutation;
    transitionTerminal(record, {
      status: "recovery_failed",
      possibleMutation,
      usage: record.public.usage,
      failure: {
        kind: "recovery_failed",
        code: "RECOVERY_FAILED",
        message: "CutAgent could not reconcile an interrupted operation automatically.",
        retrySafe: false,
        possibleMutation,
        usage: record.public.usage,
        recovery: ["inspect_state", "manual_recovery"],
        recoveryGuidance: ["Inspect the affected project state before any further mutation."],
        recoveryOutcome: { status: "failed", summary: "Automatic restart reconciliation was unavailable.", manualRecoveryRequired: true },
        readbackRequired: true,
      },
      recovery: {
        state: "failed",
        summary: "The interrupted mutation could not be reconciled automatically.",
        evidence: [],
        manualRecoveryRequired: true,
      },
    });
  }

  return Object.freeze({
    get installationAuthority() { return repo.installationAuthority; },
    create({ accountFingerprint, requestId, sdkSessionId = undefined, ownerSessionId = null, ownerRuntimeRequired = false, actionId, input, idempotencyKey = undefined }) {
      assertAuthorityAvailable();
      const validatedRequestId = sdkRequestIdSchema.parse(requestId);
      const validatedSessionId = sdkSessionId === undefined ? undefined : sdkSessionIdSchema.parse(sdkSessionId);
      const contextualOwner = getSdkOwnerSession();
      const effectiveOwnerSessionId = ownerSessionId ?? contextualOwner?.id ?? null;
      const effectiveOwnerRuntimeRequired = ownerRuntimeRequired
        || contextualOwner?.resolve_runtime?.mode === "parallel_gui_beta";
      if (effectiveOwnerSessionId !== null && (typeof effectiveOwnerSessionId !== "string" || !effectiveOwnerSessionId.trim() || effectiveOwnerSessionId.length > 256)) {
        throw new TypeError("SDK operation owner session ID is invalid.");
      }
      if (typeof ownerRuntimeRequired !== "boolean" || (effectiveOwnerRuntimeRequired && !effectiveOwnerSessionId)) {
        throw new TypeError("SDK operation owner runtime binding is invalid.");
      }
      const validatedActionId = sdkPublicActionIdSchema.parse(actionId);
      const validatedKey = idempotencyKey === undefined ? undefined : sdkIdempotencyKeySchema.parse(idempotencyKey);
      const at = now();
      const reservation = validatedKey
        ? repo.getReservation(accountFingerprint, validatedKey, { cleanupAt: at })
        : null;
      if (reservation && reservation.actionId !== validatedActionId) {
        throw idempotencyConflict(reservation, validatedKey);
      }
      const definition = requireDefinition(validatedActionId);
      const normalizedInput = canonicalSdkOperationInput(definition.inputSchema.parse(input));
      const normalizedInputDigest = sdkOperationInputDigest(normalizedInput);
      if (definition.idempotency === "required" && !validatedKey) {
        throw new TypeError("This SDK operation action requires an idempotency key.");
      }
      if (validatedKey && reservation) {
          if (reservation.normalizedInputDigest !== normalizedInputDigest) {
            throw idempotencyConflict(reservation, validatedKey);
          }
          const retained = repo.getOperation(reservation.operationId, { cleanupAt: at });
          if (retained
            && (!retained.public.retentionExpiresAt
              || Date.parse(retained.public.retentionExpiresAt) > at)) {
            if ((retained.private.ownerSessionId ?? null) !== effectiveOwnerSessionId) {
              throw idempotencyConflict(reservation, validatedKey);
            }
            return { snapshot: retained.public, replayed: true };
          }
          throw new SdkOperationAuthorityError(expiredFailure(reservation.operationId, { retainedIdempotency: true }));
      }
      const operationId = sdkOperationIdSchema.parse(opaque("operation_"));
      const executionId = opaque("execution_");
      const tombstoneExpiresAt = at + idempotencyTombstoneMs;
      const snapshot = sdkOperationSnapshotSchema.parse({
        operationId,
        requestId: validatedRequestId,
        executionId,
        actionId: validatedActionId,
        actionContractVersion: CUTAGENT_SDK_ACTION_CONTRACT_VERSION,
        status: "queued",
        sequence: 1,
        createdAt: iso(at),
        updatedAt: iso(at),
        possibleMutation: "none",
        usage: "not_reserved",
        ...(validatedKey ? { idempotency: { key: validatedKey, tombstoneExpiresAt: iso(tombstoneExpiresAt) } } : {}),
      });
      const record = {
        public: snapshot,
        private: {
          accountFingerprint,
          installationAuthority: repo.installationAuthority,
          ...(validatedSessionId ? { sdkSessionId: validatedSessionId } : {}),
          ...(effectiveOwnerSessionId ? { ownerSessionId: effectiveOwnerSessionId } : {}),
          ...(effectiveOwnerRuntimeRequired ? { ownerRuntimeRequired: true } : {}),
          normalizedInput,
          normalizedInputDigest,
        },
      };
      repo.createOperationAtomic(record, validatedKey ? {
        accountFingerprint,
        installationAuthority: repo.installationAuthority,
        key: validatedKey,
        actionId: validatedActionId,
        actionContractVersion: CUTAGENT_SDK_ACTION_CONTRACT_VERSION,
        normalizedInputDigest,
        operationId,
        resultExpiresAt: at + resultRetentionMs,
        tombstoneExpiresAt,
      } : null);
      trackDispatch(operationId, definition);
      return { snapshot, replayed: false };
    },
    get({ accountFingerprint, operationId, ownerSessionId = undefined }) {
      assertAuthorityAvailable();
      return requireOwned(operationId, accountFingerprint, { ownerSessionId }).public;
    },
    getResultPage({ accountFingerprint, operationId, ownerSessionId = undefined, collectionId, expectedDigest, offset, pageSize }) {
      const record = requireOwned(operationId, accountFingerprint, { ownerSessionId });
      const validatedCollectionId = sdkOperationResultCollectionIdSchema.parse(collectionId);
      const validatedDigest = sdkOperationResultCollectionDigestSchema.parse(expectedDigest);
      if (!Number.isInteger(offset) || offset < 0 || offset > 10_000
        || !Number.isInteger(pageSize) || pageSize < 1 || pageSize > 256) {
        throw new TypeError("SDK operation result page bounds are invalid.");
      }
      const collection = record.private.resultCollections?.[validatedCollectionId];
      if (!record.public.result || !collection || collection.digest !== validatedDigest
        || offset > (collection?.entries.length ?? 0)) {
        throw new SdkOperationAuthorityError(collectionUnavailableFailure(record.public.operationId));
      }
      const entries = collection.entries.slice(offset, offset + pageSize);
      return sdkOperationResultPageSchema.parse({
        operationId: record.public.operationId,
        actionId: record.public.actionId,
        actionContractVersion: record.public.actionContractVersion,
        collectionId: validatedCollectionId,
        kind: collection.kind,
        digest: collection.digest,
        totalItems: collection.entries.length,
        offset,
        entries,
        nextOffset: offset + entries.length < collection.entries.length ? offset + entries.length : null,
        retentionExpiresAt: record.public.retentionExpiresAt,
      });
    },
    async cancel({ accountFingerprint, operationId, ownerSessionId = undefined, assertRequestCurrent = () => {} }) {
      assertAuthorityAvailable();
      let record = requireOwned(operationId, accountFingerprint, { ownerSessionId });
      if (typeof assertRequestCurrent !== "function") throw new TypeError("Cancellation currentness check must be a function.");
      // This synchronous check is the linearization boundary: no authority or
      // runtime cancellation state changes before current authorization passes.
      assertRequestCurrent();
      if (TERMINAL.has(record.public.status) || record.public.status === "cancellation_requested") return record.public;
      const requestedAt = iso(now());
      const beforeCancellation = record.public;
      const transitioned = repo.transition(record.public.operationId, record.public.sequence, (current) => ({
        ...current,
        public: sdkOperationSnapshotSchema.parse({
          ...operationCommon(current.public),
          status: "cancellation_requested",
          sequence: current.public.sequence + 1,
          updatedAt: requestedAt,
          cancellation: { state: "requested", requestedAt },
          ...(current.public.progress ? { progress: current.public.progress } : {}),
          possibleMutation: current.public.possibleMutation,
          usage: current.public.usage,
        }),
        private: { ...current.private, cancellationResume: beforeCancellation },
      }));
      record = transitioned && transitioned !== false ? transitioned : requireOwned(operationId, accountFingerprint, { ownerSessionId });
      if (record.public.status !== "cancellation_requested") return record.public;
      if (beforeCancellation.status === "queued") {
        return transitionTerminal(record, {
          status: "cancelled",
          possibleMutation: "none",
          usage: "not_reserved",
          cancellation: { state: "confirmed", requestedAt, confirmedAt: iso(now()) },
          failure: {
            kind: "cancelled",
            code: "CANCELLED",
            message: "The queued operation was cancelled before execution.",
            retrySafe: false,
            possibleMutation: "none",
            usage: "not_reserved",
            recovery: ["continue"],
            recoveryGuidance: ["No project mutation was started."],
            readbackRequired: false,
          },
        }).public;
      }
      const definition = definitions.get(record.public.actionId);
      if (typeof definition?.cancel !== "function") return record.public;
      let outcome;
      try {
        outcome = await withOwnerSession(
          record.private.ownerSessionId ?? null,
          record.private.ownerRuntimeRequired === true,
          () => definition.cancel({
            operationId: record.public.operationId,
            executionId: record.public.executionId,
            requestId: record.public.requestId,
            accountFingerprint: record.private.accountFingerprint,
          }, structuredClone(record.private.normalizedInput)),
        );
      } catch {
        // The durable request already linearized. Preserve and return that
        // authority truth instead of projecting a generic pre-effect failure.
        return requireOwned(operationId, accountFingerprint, { ownerSessionId }).public;
      }
      record = requireOwned(operationId, accountFingerprint, { ownerSessionId });
      if (TERMINAL.has(record.public.status)) return record.public;
      if (outcome?.confirmed === true) {
        const readbackRequired = outcome.readbackRequired ?? true;
        return transitionTerminal(record, {
          status: "cancelled",
          possibleMutation: outcome.possibleMutation ?? "possible",
          usage: outcome.usage ?? record.public.usage,
          cancellation: { state: "confirmed", requestedAt, confirmedAt: iso(now()) },
          failure: {
            kind: "cancelled",
            code: "CANCELLED",
            message: "The runtime confirmed operation cancellation.",
            retrySafe: false,
            possibleMutation: outcome.possibleMutation ?? "possible",
            usage: outcome.usage ?? record.public.usage,
            recovery: readbackRequired ? ["inspect_state"] : ["continue"],
            recoveryGuidance: [readbackRequired ? "Inspect current project state before continuing." : "Cancellation was confirmed."],
            readbackRequired,
          },
          ...(outcome.verification ? { verification: outcome.verification } : {}),
          ...(outcome.recovery ? { recovery: outcome.recovery } : {}),
        }).public;
      }
      const resume = record.private.cancellationResume;
      if (!resume) return record.public;
      const rejectedAt = iso(now());
      const resumed = repo.transition(record.public.operationId, record.public.sequence, (current) => ({
        ...current,
        public: sdkOperationSnapshotSchema.parse({
          ...resume,
          sequence: current.public.sequence + 1,
          updatedAt: rejectedAt,
          cancellation: {
            state: "rejected",
            requestedAt,
            resolvedAt: rejectedAt,
            reason: typeof outcome?.reason === "string" && outcome.reason ? outcome.reason : "The runtime could not confirm cancellation.",
          },
        }),
        private: { ...current.private, cancellationResume: undefined },
      }));
      return (resumed && resumed !== false
        ? resumed
        : requireOwned(operationId, accountFingerprint, { ownerSessionId })).public;
    },
    inspectOwned({ accountFingerprint, operationId }) {
      return structuredClone(requireOwned(operationId, accountFingerprint, { allowExpired: true }));
    },
    findOwnedByIdempotency({ accountFingerprint, idempotencyKey }) {
      const key = sdkIdempotencyKeySchema.parse(idempotencyKey);
      const reservation = repo.getReservation(accountFingerprint, key, { cleanupAt: now() });
      if (!reservation) return null;
      try {
        return structuredClone(requireOwned(reservation.operationId, accountFingerprint, { allowExpired: true }));
      } catch (error) {
        if (error instanceof SdkOperationAuthorityError && error.failure.code === "OPERATION_EXPIRED") return null;
        throw error;
      }
    },
    retainForWorkflow({ accountFingerprint, operationId, retentionExpiresAt }) {
      const record = requireOwned(operationId, accountFingerprint, { allowExpired: true });
      const expiresAt = Date.parse(retentionExpiresAt);
      const retentionMs = expiresAt - now();
      if (!Number.isFinite(expiresAt)
        || retentionMs <= 0
        || retentionMs > 30 * 24 * 60 * 60 * 1000) {
        throw new TypeError("Workflow operation retention must end in the future.");
      }
      const retained = repo.retainForWorkflow(record.public.operationId, accountFingerprint, new Date(expiresAt).toISOString());
      if (!retained) throw new SdkOperationAuthorityError(expiredFailure(record.public.operationId));
      return structuredClone(retained);
    },
    async reconcileOrphans() {
      assertAuthorityAvailable();
      for (const record of repo.listActive()) await reconcileRecord(record);
    },
    cleanup() { repo.cleanup(now()); },
    async waitForIdle() {
      await Promise.allSettled([...dispatches]);
      assertAuthorityAvailable();
    },
    inspect() { return repo.inspect(); },
  });
}
