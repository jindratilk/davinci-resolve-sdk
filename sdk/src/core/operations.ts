import {
  CUTAGENT_SDK_ACTION_CONTRACT_VERSION,
  OperationEventSchema,
  OperationResultCollectionReferenceSchema,
  OperationResultPageSchema,
  PublicActionResultSchema,
  type AnyOperationHandle,
  type OperationHandle,
  type OperationRef,
  type OperationResultCollectionReference,
  type OperationResultPage,
  type OperationResultPageOptions,
  type Operations,
  type OperationSnapshot,
  type OperationSubscribeOptions,
  type OperationWaitOptions,
  type PublicActionId,
  type PublicActionResult,
  type TerminalOperationSnapshot,
} from "../protocol/operations.js";
import { CutAgentSdkError, PUBLIC_ERROR_KIND_BY_CODE } from "../protocol/errors.js";
import { OperationIdSchema, type OperationId } from "../value-types/identities.js";
import { sdkIdempotencyKeySchema, sdkOperationIdSchema } from "../generated/sdk-identities.js";
import type { EstablishedCarrierSession } from "./carrier-session.js";
import type { CarrierOperationRequest } from "./carrier-contract.js";
import type { ConnectionControlOptions } from "./public-client-types.js";

const DEFAULT_OPERATION_POLL_INTERVAL_MS = 250;
const MIN_OPERATION_POLL_INTERVAL_MS = 100;
const MAX_OPERATION_POLL_INTERVAL_MS = 10_000;
const MAX_OPERATION_WAIT_TIMEOUT_MS = 24 * 60 * 60 * 1_000;
const MAX_OPERATION_POLL_REQUEST_TIMEOUT_MS = 10_000;
const TERMINAL_STATUSES = new Set([
  "succeeded",
  "failed",
  "cancelled",
  "partially_applied",
  "verification_failed",
  "recovery_failed",
]);
const STATUS_TRANSITIONS: Readonly<Record<string, ReadonlySet<string>>> = Object.freeze({
  queued: new Set(["queued", "running", "waiting", "cancellation_requested", ...TERMINAL_STATUSES]),
  running: new Set(["running", "waiting", "cancellation_requested", ...TERMINAL_STATUSES]),
  waiting: new Set(["waiting", "running", "cancellation_requested", ...TERMINAL_STATUSES]),
  cancellation_requested: new Set(["cancellation_requested", "running", "waiting", ...TERMINAL_STATUSES]),
});

type WireEvent = ReturnType<typeof OperationEventSchema.parse>;
type WireSnapshot = WireEvent["snapshot"];
type ResultDecoder<TResult> = (result: PublicActionResult, snapshot: WireSnapshot) => TResult;
const refDecoders = new WeakMap<object, ResultDecoder<unknown>>();

function invalidResponse(message: string): CutAgentSdkError {
  return new CutAgentSdkError({
    kind: PUBLIC_ERROR_KIND_BY_CODE.INVALID_RESPONSE,
    code: "INVALID_RESPONSE",
    message,
    retrySafe: false,
    possibleMutation: "none",
    usage: "not_reserved",
    recovery: ["contact_support"],
    recoveryGuidance: ["Stop using this operation handle and contact CutAgent support."],
    readbackRequired: false,
  });
}

function invalidOperationResultResponse(message: string, snapshot: WireSnapshot): CutAgentSdkError {
  const readbackRequired = snapshot.possibleMutation !== "none";
  return new CutAgentSdkError({
    kind: PUBLIC_ERROR_KIND_BY_CODE.INVALID_RESPONSE,
    code: "INVALID_RESPONSE",
    message,
    retrySafe: false,
    possibleMutation: snapshot.possibleMutation,
    usage: snapshot.usage,
    recovery: readbackRequired ? ["inspect_state", "contact_support"] : ["contact_support"],
    recoveryGuidance: [readbackRequired
      ? "Inspect the authoritative operation state before continuing, then contact CutAgent support."
      : "Stop using this operation handle and contact CutAgent support."],
    readbackRequired,
    requestId: snapshot.requestId,
    operationId: snapshot.operationId,
    executionId: snapshot.executionId,
  });
}

function uncertainCancellationResponse(message: string): CutAgentSdkError {
  return new CutAgentSdkError({
    kind: PUBLIC_ERROR_KIND_BY_CODE.INVALID_RESPONSE,
    code: "INVALID_RESPONSE",
    message,
    retrySafe: false,
    possibleMutation: "unknown",
    usage: "unknown",
    recovery: ["reconnect", "inspect_state"],
    recoveryGuidance: ["Reconnect and inspect the original operation before retrying cancellation."],
    readbackRequired: true,
  });
}

function pollInterval(value: number | undefined): number {
  if (value === undefined) return DEFAULT_OPERATION_POLL_INTERVAL_MS;
  if (!Number.isInteger(value) || value < MIN_OPERATION_POLL_INTERVAL_MS || value > MAX_OPERATION_POLL_INTERVAL_MS) {
    throw new TypeError(`pollIntervalMs must be an integer from ${MIN_OPERATION_POLL_INTERVAL_MS} through ${MAX_OPERATION_POLL_INTERVAL_MS}.`);
  }
  return value;
}

function terminal<TResult, TAction extends PublicActionId>(
  snapshot: OperationSnapshot<TResult, TAction>,
): snapshot is TerminalOperationSnapshot<TResult, TAction> {
  return TERMINAL_STATUSES.has(snapshot.status);
}

function resultContainsCollectionReference(
  value: unknown,
  expected: OperationResultCollectionReference,
): boolean {
  if (Array.isArray(value)) {
    return value.some((entry) => resultContainsCollectionReference(entry, expected));
  }
  if (value === null || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  const candidate = OperationResultCollectionReferenceSchema.safeParse(record.resultPage);
  if (candidate.success
    && candidate.data.collectionId === expected.collectionId
    && candidate.data.kind === expected.kind
    && candidate.data.totalItems === expected.totalItems
    && candidate.data.digest === expected.digest
    && candidate.data.defaultPageSize === expected.defaultPageSize) {
    return true;
  }
  return Object.values(record).some((entry) => resultContainsCollectionReference(entry, expected));
}

function sameSnapshot(left: WireSnapshot, right: WireSnapshot): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function validateTransition(previous: WireSnapshot, event: WireEvent): "accept" | "ignore" {
  const next = event.snapshot;
  if (next.operationId !== previous.operationId
    || next.actionId !== previous.actionId
    || next.actionContractVersion !== previous.actionContractVersion
    || next.requestId !== previous.requestId
    || next.executionId !== previous.executionId) {
    throw invalidResponse("CutAgent runtime returned mismatched operation correlation.");
  }
  if (next.sequence < previous.sequence) return "ignore";
  if (next.sequence === previous.sequence) {
    if (sameSnapshot(previous, next)) return "ignore";
    throw invalidResponse("CutAgent runtime changed an operation without advancing authority sequence.");
  }
  if (TERMINAL_STATUSES.has(previous.status)) {
    throw invalidResponse("CutAgent runtime changed an immutable terminal operation.");
  }
  if (!STATUS_TRANSITIONS[previous.status]?.has(next.status)) {
    throw invalidResponse(`CutAgent runtime returned an invalid operation status transition: ${previous.status} -> ${next.status}.`);
  }
  const beforeProgress = "progress" in previous ? previous.progress : undefined;
  const afterProgress = "progress" in next ? next.progress : undefined;
  if (beforeProgress?.overallFraction !== undefined
    && afterProgress?.overallFraction !== undefined
    && afterProgress.overallFraction < beforeProgress.overallFraction) {
    throw invalidResponse("CutAgent runtime regressed overall operation progress.");
  }
  if (beforeProgress?.phase === afterProgress?.phase
    && beforeProgress?.phaseFraction !== undefined
    && afterProgress?.phaseFraction !== undefined
    && afterProgress.phaseFraction < beforeProgress.phaseFraction) {
    throw invalidResponse("CutAgent runtime regressed progress within one phase.");
  }
  return "accept";
}

function localWait(ms: number, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) return Promise.reject(signal.reason ?? new DOMException("Aborted", "AbortError"));
  return new Promise((resolve, reject) => {
    const timer = setTimeout(finish, ms);
    function cleanup() {
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
    }
    function finish() {
      cleanup();
      resolve();
    }
    function abort() {
      cleanup();
      reject(signal?.reason ?? new DOMException("Aborted", "AbortError"));
    }
    signal?.addEventListener("abort", abort, { once: true });
  });
}

function project<TResult, TAction extends PublicActionId>(
  snapshot: WireSnapshot,
  decode: ResultDecoder<TResult>,
): OperationSnapshot<TResult, TAction> {
  if (!("result" in snapshot) || snapshot.result === undefined) return snapshot as OperationSnapshot<TResult, TAction>;
  return Object.freeze({ ...snapshot, result: decode(PublicActionResultSchema.parse(snapshot.result), snapshot) }) as OperationSnapshot<TResult, TAction>;
}

interface OperationRuntime {
  session(): EstablishedCarrierSession;
  /** Deterministic internal test seam; public callers never supply timers. */
  setOperationTimeout?: typeof setTimeout;
  clearOperationTimeout?: typeof clearTimeout;
}

interface ActionResultSchema<TResult> {
  parse(value: unknown): TResult;
}

function createHandle<TResult, TAction extends PublicActionId>(
  runtime: OperationRuntime,
  initialEvent: WireEvent,
  decode: ResultDecoder<TResult>,
): OperationHandle<TResult, TAction> {
  let wire = initialEvent.snapshot;
  let current = project<TResult, TAction>(wire, decode);
  let pollTimer: ReturnType<typeof setTimeout> | null = null;
  let scheduledPollIntervalMs: number | null = null;
  const subscriptions = new Set<{
    listener: (snapshot: OperationSnapshot<TResult, TAction>) => void;
    intervalMs: number;
  }>();
  const setOperationTimeout = runtime.setOperationTimeout ?? setTimeout;
  const clearOperationTimeout = runtime.clearOperationTimeout ?? clearTimeout;

  const accept = (raw: unknown): OperationSnapshot<TResult, TAction> => {
    const event = OperationEventSchema.parse(raw);
    if (validateTransition(wire, event) === "ignore") return current;
    const projected = project<TResult, TAction>(event.snapshot, decode);
    wire = event.snapshot;
    current = projected;
    for (const subscription of [...subscriptions]) {
      try {
        subscription.listener(current);
      } catch {
        // Subscriber code is observational and cannot poison operation truth
        // or prevent other subscribers from receiving the same authority state.
      }
    }
    return current;
  };

  const refresh = async (options: ConnectionControlOptions = {}) => accept(await runtime.session().operation({
    operation: "operation.get",
    operationId: sdkOperationIdSchema.parse(wire.operationId),
  }, options));

  const schedulePoll = () => {
    if (pollTimer) {
      clearOperationTimeout(pollTimer);
      pollTimer = null;
      scheduledPollIntervalMs = null;
    }
    if (subscriptions.size === 0 || TERMINAL_STATUSES.has(wire.status)) {
      return;
    }
    const intervalMs = Math.min(...[...subscriptions].map((subscription) => subscription.intervalMs));
    scheduledPollIntervalMs = intervalMs;
    pollTimer = setOperationTimeout(async () => {
      pollTimer = null;
      scheduledPollIntervalMs = null;
      try {
        await refresh();
      } catch {
        // A subscription is observational. A transient carrier failure is not
        // an operation event and never mutates or terminalizes local truth.
      }
      schedulePoll();
    }, intervalMs);
    pollTimer.unref?.();
  };

  const reconcilePollSchedule = () => {
    if (subscriptions.size === 0 || TERMINAL_STATUSES.has(wire.status)) {
      if (pollTimer) clearOperationTimeout(pollTimer);
      pollTimer = null;
      scheduledPollIntervalMs = null;
      return;
    }
    const nextIntervalMs = Math.min(...[...subscriptions].map((subscription) => subscription.intervalMs));
    if (pollTimer && scheduledPollIntervalMs === nextIntervalMs) return;
    schedulePoll();
  };

  const ref = Object.freeze({
    operationId: wire.operationId,
    actionId: wire.actionId,
    actionContractVersion: wire.actionContractVersion,
  }) as unknown as OperationRef<TAction, TResult>;
  refDecoders.set(ref, decode as ResultDecoder<unknown>);

  const handle: OperationHandle<TResult, TAction> = {
    get operationId() { return wire.operationId; },
    get actionId() { return wire.actionId as TAction; },
    ref,
    get current() { return current; },
    refresh,
    async wait(options: OperationWaitOptions = {}) {
      const interval = pollInterval(options.pollIntervalMs);
      const startedAt = Date.now();
      const timeoutMs = options.timeoutMs;
      if (timeoutMs !== undefined && (!Number.isInteger(timeoutMs) || timeoutMs < 100 || timeoutMs > MAX_OPERATION_WAIT_TIMEOUT_MS)) {
        throw new TypeError(`timeoutMs must be an integer from 100 through ${MAX_OPERATION_WAIT_TIMEOUT_MS}.`);
      }
      while (!terminal(current)) {
        if (options.signal?.aborted) throw options.signal.reason ?? new DOMException("Aborted", "AbortError");
        const remaining = timeoutMs === undefined ? Number.POSITIVE_INFINITY : timeoutMs - (Date.now() - startedAt);
        if (remaining <= 0) throw new DOMException("Local operation wait timed out.", "TimeoutError");
        await localWait(Math.min(interval, remaining), options.signal);
        const afterWaitRemaining = timeoutMs === undefined ? undefined : timeoutMs - (Date.now() - startedAt);
        if (afterWaitRemaining !== undefined && afterWaitRemaining <= 0) {
          throw new DOMException("Local operation wait timed out.", "TimeoutError");
        }
        if (afterWaitRemaining !== undefined && afterWaitRemaining < 100) {
          throw new DOMException("Local operation wait timed out.", "TimeoutError");
        }
        const requestRemaining = afterWaitRemaining === undefined
          ? MAX_OPERATION_POLL_REQUEST_TIMEOUT_MS
          : Math.min(MAX_OPERATION_POLL_REQUEST_TIMEOUT_MS, afterWaitRemaining);
        await refresh({
          timeoutMs: requestRemaining,
          ...(options.signal ? { signal: options.signal } : {}),
        });
      }
      return current;
    },
    subscribe(listener, options: OperationSubscribeOptions = {}) {
      if (typeof listener !== "function") throw new TypeError("Operation subscriber must be a function.");
      const interval = pollInterval(options.pollIntervalMs);
      let active = true;
      const subscription = { listener, intervalMs: interval };
      subscriptions.add(subscription);
      try {
        listener(current);
      } catch {
        // Initial delivery follows the same observational isolation rule as
        // subsequent authority updates.
      }
      const unsubscribe = () => {
        if (!active) return;
        active = false;
        subscriptions.delete(subscription);
        options.signal?.removeEventListener("abort", unsubscribe);
        reconcilePollSchedule();
      };
      options.signal?.addEventListener("abort", unsubscribe, { once: true });
      if (options.signal?.aborted) unsubscribe();
      reconcilePollSchedule();
      return unsubscribe;
    },
    async requestCancellation(options: ConnectionControlOptions = {}) {
      const response = await runtime.session().operation({
        operation: "operation.cancel",
        operationId: sdkOperationIdSchema.parse(wire.operationId),
      }, options);
      try {
        return accept(response);
      } catch {
        throw uncertainCancellationResponse(
          "CutAgent returned invalid operation state after cancellation dispatch; the operation outcome is unknown.",
        );
      }
    },
    async getResultPage(reference: OperationResultCollectionReference, options: OperationResultPageOptions = {}): Promise<OperationResultPage> {
      const parsedReference = OperationResultCollectionReferenceSchema.parse(reference);
      const retainedSnapshot = wire;
      if (!("result" in retainedSnapshot) || retainedSnapshot.result === undefined
        || !resultContainsCollectionReference(retainedSnapshot.result.value, parsedReference)) {
        throw new TypeError("Result page reference is not retained by this operation handle.");
      }
      const { offset = 0, pageSize = parsedReference.defaultPageSize, ...controlOptions } = options;
      if (!Number.isInteger(offset) || offset < 0 || offset > parsedReference.totalItems) {
        throw new TypeError("Result page offset must be an integer within the referenced collection.");
      }
      if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > 256) {
        throw new TypeError("Result page size must be an integer from 1 through 256.");
      }
      const page = OperationResultPageSchema.parse(await runtime.session().operation({
        operation: "operation.result.page",
        operationId: sdkOperationIdSchema.parse(retainedSnapshot.operationId),
        collectionId: parsedReference.collectionId,
        expectedDigest: parsedReference.digest,
        offset,
        pageSize,
      }, controlOptions));
      if (String(page.operationId) !== String(retainedSnapshot.operationId) || page.actionId !== retainedSnapshot.actionId
        || page.actionContractVersion !== retainedSnapshot.actionContractVersion
        || page.collectionId !== parsedReference.collectionId || page.kind !== parsedReference.kind
        || page.digest !== parsedReference.digest || page.totalItems !== parsedReference.totalItems
        || page.offset !== offset || page.retentionExpiresAt !== retainedSnapshot.retentionExpiresAt
        || page.entries.length > pageSize) {
        throw invalidResponse("CutAgent runtime returned an uncorrelated operation result page.");
      }
      return page;
    },
  };
  Object.setPrototypeOf(handle, null);
  return Object.freeze(handle);
}

/** Trusted construction seam for later accepted action APIs. @internal */
export function createTypedOperationHandle<TResult, TAction extends PublicActionId>(
  runtime: OperationRuntime,
  initialEvent: unknown,
  actionId: TAction,
  resultSchema: ActionResultSchema<TResult>,
): OperationHandle<TResult, TAction> {
  const event = OperationEventSchema.parse(initialEvent);
  if (event.snapshot.actionId !== actionId) {
    throw invalidResponse("CutAgent runtime returned an operation for a different action.");
  }
  return createHandle(runtime, event, (result, snapshot) => {
    const parsed = PublicActionResultSchema.parse(result);
    if (parsed.actionId !== actionId || parsed.actionContractVersion !== CUTAGENT_SDK_ACTION_CONTRACT_VERSION) {
      throw invalidOperationResultResponse("CutAgent runtime returned a result for a different action contract.", snapshot);
    }
    try {
      return resultSchema.parse(parsed.value);
    } catch {
      throw invalidOperationResultResponse("CutAgent runtime returned an invalid result for this operation action.", snapshot);
    }
  });
}

/** Start one accepted semantic action through the shared durable authority. @internal */
export async function startTypedOperation<TResult, TAction extends PublicActionId>(
  runtime: OperationRuntime,
  actionId: TAction,
  input: unknown,
  resultSchema: ActionResultSchema<TResult>,
  options: ConnectionControlOptions & { idempotencyKey?: string } = {},
): Promise<OperationHandle<TResult, TAction>> {
  const request = {
    operation: "operation.create",
    actionId,
    input,
    ...(options.idempotencyKey !== undefined
      ? { idempotencyKey: sdkIdempotencyKeySchema.parse(options.idempotencyKey) }
      : {}),
  } as CarrierOperationRequest;
  const event = await runtime.session().operation(request, options);
  return createTypedOperationHandle(runtime, event, actionId, resultSchema);
}

/** Build the shared operation lifecycle used by every carrier. @internal */
export function createOperations(runtime: OperationRuntime): Operations {
  async function raw(operationId: OperationId, options: ConnectionControlOptions): Promise<AnyOperationHandle> {
    const validatedId = OperationIdSchema.parse(operationId);
    const event = OperationEventSchema.parse(await runtime.session().operation({
      operation: "operation.get",
      operationId: sdkOperationIdSchema.parse(validatedId),
    }, options));
    return createHandle(runtime, event, (result) => PublicActionResultSchema.parse(result));
  }

  function reattach(operationId: OperationId, options?: ConnectionControlOptions): Promise<AnyOperationHandle>;
  function reattach<TAction extends PublicActionId, TResult>(
    operation: OperationRef<TAction, TResult>,
    options?: ConnectionControlOptions,
  ): Promise<OperationHandle<TResult, TAction>>;
  async function reattach<TAction extends PublicActionId, TResult>(
    operation: OperationId | OperationRef<TAction, TResult>,
    options: ConnectionControlOptions = {},
  ): Promise<AnyOperationHandle | OperationHandle<TResult, TAction>> {
    if (typeof operation === "string") return raw(operation, options);
    const decode = refDecoders.get(operation) as ResultDecoder<TResult> | undefined;
    if (!decode) throw new TypeError("OperationRef must originate from this installed CutAgent SDK instance.");
    const event = OperationEventSchema.parse(await runtime.session().operation({
      operation: "operation.get",
      operationId: sdkOperationIdSchema.parse(OperationIdSchema.parse(operation.operationId)),
    }, options));
    if (event.snapshot.actionId !== operation.actionId
      || event.snapshot.actionContractVersion !== operation.actionContractVersion) {
      throw invalidResponse("CutAgent runtime returned an operation that does not match its typed reference.");
    }
    return createHandle<TResult, TAction>(runtime, event, decode);
  }

  const operations: Operations = { reattach };
  Object.setPrototypeOf(operations, null);
  return Object.freeze(operations);
}
