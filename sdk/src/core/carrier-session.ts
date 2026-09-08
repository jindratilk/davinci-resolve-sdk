import { z } from "zod";
import {
  CUTAGENT_SDK_WIRE_PROTOCOL,
  sdkRuntimeReadResponseSchema,
} from "../generated/sdk-runtime.js";
import { sdkOperationControlResponseSchema } from "../generated/sdk-operations.js";
import { sdkWorkflowControlResponseSchema } from "../generated/sdk-operations.js";
import type { CompatibilityDescriptor } from "../protocol/compatibility.js";
import { CutAgentSdkError, PublicFailureSchema } from "../protocol/errors.js";
import {
  CarrierFault,
  newRequestId,
  timeoutValue,
  type CarrierChannel,
  type CarrierConnector,
  type CarrierReadRequest,
  type CarrierReadSuccess,
  type CarrierOperationRequest,
  type CarrierOperationSuccessFor,
  type CarrierWorkflowRequest,
  type CarrierWorkflowSuccess,
  type CarrierRequest,
} from "./carrier-contract.js";
import { Deadline, withinDeadline } from "./carrier-deadline.js";
import {
  mapReadFailure,
  mapTransportFailure,
  projectControlFailureAfterDispatch,
  projectCarrierFault,
  publicFailure,
  uncertainControlFailure,
} from "./carrier-errors.js";
import {
  SanitizedConnectResponseSchema,
  SanitizedConnectSuccessSchema,
  SanitizedSessionSchema,
  assertCarrierCompatible,
  assertReply,
  parseControlResponse,
  request,
  type SanitizedCarrierSession,
} from "./carrier-protocol.js";
import type { ConnectionControlOptions } from "./public-client-types.js";

export {
  CarrierFault,
  DEFAULT_CONTROL_TIMEOUT_MS,
  MAX_CONTROL_TIMEOUT_MS,
  MIN_CONTROL_TIMEOUT_MS,
  newRequestId,
  timeoutValue,
} from "./carrier-contract.js";
export type {
  CarrierChannel,
  CarrierConnector,
  CarrierDistribution,
  CarrierFaultKind,
  CarrierMethod,
  CarrierOperationRequest,
  CarrierOperationSuccess,
  CarrierOperationSuccessFor,
  CarrierReadRequest,
  CarrierReadSuccess,
  CarrierReply,
  CarrierRequest,
} from "./carrier-contract.js";
export { publicFailure } from "./carrier-errors.js";
export type { SanitizedCarrierSession } from "./carrier-protocol.js";

export interface EstablishedCarrierSession {
  readonly descriptor: CompatibilityDescriptor;
  readonly session: SanitizedCarrierSession;
  readonly closed: boolean;
  /** True only when the carrier has proved transport termination. */
  readonly terminated: boolean;
  read(request: CarrierReadRequest, options?: ConnectionControlOptions): Promise<CarrierReadSuccess>;
  operation<TRequest extends CarrierOperationRequest>(
    request: TRequest,
    options?: ConnectionControlOptions,
  ): Promise<CarrierOperationSuccessFor<TRequest>>;
  workflow(request: CarrierWorkflowRequest, options?: ConnectionControlOptions): Promise<CarrierWorkflowSuccess>;
  close(options?: ConnectionControlOptions): Promise<void>;
  retire(options?: ConnectionControlOptions): Promise<void>;
  onTerminal(listener: () => void): () => void;
}

export interface EstablishCarrierOptions extends ConnectionControlOptions {
  /** Test-only monotonic clock. Carrier adapters must not alter deadline policy. */
  deadlineClock?: () => number;
}

/** Establish and own one complete SDK session independent of its carrier. */
export async function establishCarrierSession(
  connector: CarrierConnector,
  options: EstablishCarrierOptions = {},
): Promise<EstablishedCarrierSession> {
  const timeoutMs = timeoutValue(options.timeoutMs);
  const clock = options.deadlineClock ?? Date.now;
  const connectDeadline = new Deadline(timeoutMs, clock);
  let channel: CarrierChannel | null = null;
  let session: SanitizedCarrierSession | null = null;
  try {
    channel = await withinDeadline({
      deadline: connectDeadline,
      ...(options.signal ? { controlSignal: options.signal } : {}),
      semantics: "pre_execution",
      timeoutProjection: "unavailable",
      run: (signal) => connector.open(signal),
    });
    if (channel.distribution !== connector.distribution) throw new CarrierFault("invalid_response");

    const exchangeConnect = async (
      allowAcquisitionRefresh = true,
    ): Promise<z.infer<typeof SanitizedConnectSuccessSchema>> => {
      const requestId = newRequestId();
      const reply = await withinDeadline({
        deadline: connectDeadline,
        ...(options.signal ? { controlSignal: options.signal } : {}),
        requestId,
        semantics: "pre_execution",
        run: (signal) => channel!.exchange(request("connect", requestId, connector.distribution), signal),
      });
      const payload = assertReply(reply, "connect", requestId);
      const parsed = SanitizedConnectResponseSchema.safeParse(payload);
      if (!parsed.success) {
        throw publicFailure({ code: "INVALID_RESPONSE", message: "CutAgent runtime response failed SDK validation.", recovery: ["contact_support"], requestId });
      }
      if (!parsed.data.ok) {
        if (allowAcquisitionRefresh
          && parsed.data.error.code === "BOOTSTRAP_REJECTED"
          && channel?.refreshConnectAcquisition
          && channel.acquisitionId
          && await withinDeadline({
            deadline: connectDeadline,
            ...(options.signal ? { controlSignal: options.signal } : {}),
            requestId,
            semantics: "pre_execution",
            run: (signal) => channel!.refreshConnectAcquisition!(channel!.acquisitionId!, signal),
          })) {
          return exchangeConnect(false);
        }
        throw mapTransportFailure(parsed.data, requestId, "pre_execution");
      }
      if (parsed.data.requestId !== requestId) {
        throw publicFailure({ code: "INVALID_RESPONSE", message: "CutAgent runtime returned an uncorrelated response.", recovery: ["contact_support"], requestId });
      }
      return parsed.data;
    };

    const connected = await exchangeConnect();
    session = SanitizedSessionSchema.parse(connected.session);
    const descriptor = assertCarrierCompatible(
      connected.descriptor,
      connector.distribution,
      connector.distributionRange,
    );
    if (descriptor.distribution !== connector.distribution) {
      throw publicFailure({ code: "SDK_INCOMPATIBLE", message: "CutAgent runtime returned the wrong distribution contract.", recovery: ["update_required"], requestId: connected.requestId });
    }
    const now = Date.now();
    if (Date.parse(session.issuedAt) > now + 30_000
      || Date.parse(session.expiresAt) <= now
      || Date.parse(session.idleExpiresAt) <= now) {
      throw publicFailure({
        code: "INVALID_RESPONSE",
        message: "CutAgent runtime returned an expired or invalid SDK session lifetime.",
        recovery: ["restart_runtime", "contact_support"],
        requestId: connected.requestId,
      });
    }

    const confirmId = newRequestId();
    const confirmReply = await withinDeadline({
      deadline: connectDeadline,
      ...(options.signal ? { controlSignal: options.signal } : {}),
      requestId: confirmId,
      semantics: "pre_execution",
      run: (signal) => channel!.exchange(request("confirm", confirmId, connector.distribution, session!.sessionId), signal),
    });
    parseControlResponse("confirm", assertReply(confirmReply, "confirm", confirmId), confirmId);

    let state: "active" | "closing" | "closed" = "active";
    let closePromise: Promise<void> | null = null;
    let queue: Promise<void> = Promise.resolve();
    const activeReadControllers = new Set<AbortController>();
    const terminalListeners = new Set<() => void>();
    let carrierUnsubscribe: (() => void) | null = null;
    const markClosed = () => {
      if (state === "closed") return;
      state = "closed";
      carrierUnsubscribe?.();
      carrierUnsubscribe = null;
      for (const listener of terminalListeners) listener();
      terminalListeners.clear();
    };
    const schedule = <T>(run: () => Promise<T>): Promise<T> => {
      const result = queue.then(run, run);
      queue = result.then(() => undefined, () => undefined);
      return result;
    };
    const isClosing = () => state === "closing";
    const finishCarrierCleanup = async (
      closeId: ReturnType<typeof newRequestId>,
      shouldCloseSession: boolean,
      cleanupTimeoutMs: number,
      controlSignal?: AbortSignal,
    ) => {
      let cleanupError: unknown;
      if (shouldCloseSession && !channel!.terminated) {
        try {
          const reply = await withinDeadline({
            deadline: new Deadline(cleanupTimeoutMs, clock),
            ...(controlSignal ? { controlSignal } : {}),
            requestId: closeId,
            semantics: "pre_execution",
            run: (signal) => channel!.exchange(
              request("close", closeId, connector.distribution, session!.sessionId),
              signal,
            ),
          });
          parseControlResponse("close", assertReply(reply, "close", closeId), closeId);
        } catch (error) {
          cleanupError = projectCarrierFault(error, closeId, "pre_execution");
        }
      }
      try {
        await withinDeadline({
          deadline: new Deadline(cleanupTimeoutMs, clock),
          requestId: closeId,
          semantics: "pre_execution",
          run: () => channel!.disconnect(),
        });
      } catch (error) {
        cleanupError ??= projectCarrierFault(error, closeId, "pre_execution");
      } finally {
        markClosed();
      }
      if (cleanupError !== undefined) throw cleanupError;
    };
    const deferInterruptedCleanup = (
      settlement: Promise<void>,
      closeId: ReturnType<typeof newRequestId>,
      cleanupTimeoutMs: number,
    ) => {
      const deferred = settlement.then(
        () => finishCarrierCleanup(closeId, true, cleanupTimeoutMs),
        () => finishCarrierCleanup(closeId, false, cleanupTimeoutMs),
      );
      void deferred.catch(() => {});
    };
    const terminateAfterFailure = async () => {
      if (closePromise) {
        await closePromise.catch(() => {});
        return;
      }
      if (state === "closed") return;
      state = "closing";
      const closeId = newRequestId();
      closePromise = (async () => {
        const settlement = channel!.settleInterruptedExchange();
        const cleanupDeadline = new Deadline(timeoutMs, clock);
        try {
          await withinDeadline({
            deadline: cleanupDeadline,
            requestId: closeId,
            semantics: "pre_execution",
            run: () => settlement,
          });
        } catch (error) {
          deferInterruptedCleanup(settlement, closeId, timeoutMs);
          markClosed();
          throw projectCarrierFault(error, closeId, "pre_execution");
        }
        await finishCarrierCleanup(closeId, true, timeoutMs);
      })();
      // The semantic read owns its original failure. Retain cleanup failure for
      // an explicit close/reconnect while preventing it from masking that read.
      void closePromise.catch(() => {});
      await closePromise.catch(() => {});
    };
    carrierUnsubscribe = channel.onDisconnect?.(() => {
      if (!closePromise) {
        const terminalId = newRequestId();
        closePromise = channel!.disconnect().catch((error) => {
          throw projectCarrierFault(error, terminalId, "pre_execution");
        });
        // Retain the rejection for close/reconnect while preventing an idle
        // terminal event from becoming an unhandled promise rejection.
        void closePromise.catch(() => {});
      }
      markClosed();
    }) ?? null;

    const beginClose = (
      closeOptions: ConnectionControlOptions,
      interruptReads: boolean,
    ): Promise<void> => {
      if (closePromise) return closePromise;
      if (state === "closed") return Promise.resolve();
      let closeTimeoutMs: number;
      try {
        closeTimeoutMs = timeoutValue(closeOptions.timeoutMs ?? timeoutMs);
      } catch (error) {
        return Promise.reject(error);
      }
      state = "closing";
      const interruptedRead = interruptReads && activeReadControllers.size > 0;
      if (interruptReads) {
        for (const controller of activeReadControllers) {
          controller.abort(new DOMException("Session closing", "AbortError"));
        }
      }
      closePromise = schedule(async () => {
        const closeId = newRequestId();
        if (interruptedRead) {
          const settlement = channel!.settleInterruptedExchange();
          try {
            await withinDeadline({
              deadline: new Deadline(closeTimeoutMs, clock),
              ...(closeOptions.signal ? { controlSignal: closeOptions.signal } : {}),
              requestId: closeId,
              semantics: "pre_execution",
              run: () => settlement,
            });
          } catch (error) {
            deferInterruptedCleanup(settlement, closeId, closeTimeoutMs);
            markClosed();
            throw projectCarrierFault(error, closeId, "pre_execution");
          }
        }
        // A process-bound carrier may terminate itself while honoring the
        // read interruption. Its terminal proof supersedes a dead-pipe close.
        await finishCarrierCleanup(
          closeId,
          !(interruptedRead && channel!.terminated),
          closeTimeoutMs,
          closeOptions.signal,
        );
      });
      return closePromise;
    };

    return {
      descriptor,
      session,
      get closed(): boolean { return state === "closed"; },
      get terminated(): boolean { return channel!.terminated; },
      read(readRequest, readOptions = {}) {
        if (state !== "active") {
          return Promise.reject(publicFailure({
            code: "CONNECTION_CLOSED",
            message: "This CutAgent SDK session is closed.",
            recovery: ["reconnect"],
            retrySafe: true,
            retryBasis: "read_only",
          }));
        }
        let readTimeoutMs: number;
        try {
          readTimeoutMs = timeoutValue(readOptions.timeoutMs ?? timeoutMs);
        } catch (error) {
          return Promise.reject(error);
        }
        const readDeadline = new Deadline(readTimeoutMs, clock);
        const deadlineAtMs = Date.now() + readTimeoutMs;
        const scheduled = schedule(async () => {
          if (state !== "active") {
            throw publicFailure({ code: "CONNECTION_CLOSED", message: "This CutAgent SDK session is closed.", recovery: ["reconnect"], retrySafe: true, retryBasis: "read_only" });
          }
          const requestId = newRequestId();
          const controller = new AbortController();
          activeReadControllers.add(controller);
          const controlSignal = readOptions.signal
            ? AbortSignal.any([controller.signal, readOptions.signal])
            : controller.signal;
          const readMessage: CarrierRequest = {
            method: "read",
            requestId,
            payload: {
              protocolVersion: CUTAGENT_SDK_WIRE_PROTOCOL,
              requestId,
              sessionId: session!.sessionId,
              deadlineAtMs,
              ...readRequest,
            },
          };
          let receivedCorrelatedRetryableFailure = false;
          try {
            const reply = await withinDeadline({
              deadline: readDeadline,
              controlSignal,
              requestId,
              semantics: "read_only",
              run: (signal) => channel!.exchange(readMessage, signal),
            });
            const payload = assertReply(reply, "read", requestId);
            const parsed = sdkRuntimeReadResponseSchema.safeParse(payload);
            if (!parsed.success) {
              throw publicFailure({ code: "INVALID_RESPONSE", message: "CutAgent runtime response failed SDK validation.", recovery: ["contact_support"], requestId });
            }
            if (!parsed.data.ok) {
              receivedCorrelatedRetryableFailure = String(parsed.data.requestId) === String(requestId) && (
                parsed.data.error.code === "RUNTIME_TIMEOUT"
                || (parsed.data.error.code === "RUNTIME_UNAVAILABLE" && parsed.data.error.recovery === "retry")
              );
              throw mapReadFailure(parsed.data, requestId);
            }
            if (String(parsed.data.requestId) !== String(requestId) || parsed.data.operation !== readRequest.operation) {
              throw publicFailure({ code: "INVALID_RESPONSE", message: "CutAgent runtime returned an uncorrelated read response.", recovery: ["contact_support"], requestId });
            }
            return parsed.data;
          } catch (error) {
            if (receivedCorrelatedRetryableFailure
              || (error instanceof CutAgentSdkError && ["CAPABILITY_UNAVAILABLE", "TARGET_NOT_FOUND", "AMBIGUOUS_TARGET", "STALE_REVISION"].includes(error.failure.code))) {
              throw error;
            }
            if (isClosing()) throw error;
            await terminateAfterFailure();
            throw error;
          } finally {
            activeReadControllers.delete(controller);
          }
        });
        return scheduled;
      },
      operation(operationRequest, operationOptions = {}) {
        const operationSemantics = operationRequest.operation === "operation.get" || operationRequest.operation === "operation.result.page"
          ? "read_only"
          : "uncertain_control";
        const preDispatchRetryBasis = operationSemantics === "read_only"
          ? "read_only"
          : "pre_execution";
        if (state !== "active") {
          return Promise.reject(publicFailure({
            code: "CONNECTION_CLOSED",
            message: "This CutAgent SDK session is closed.",
            recovery: ["reconnect"],
            retrySafe: true,
            retryBasis: preDispatchRetryBasis,
          }));
        }
        let operationTimeoutMs: number;
        try {
          operationTimeoutMs = timeoutValue(operationOptions.timeoutMs ?? timeoutMs);
        } catch (error) {
          return Promise.reject(error);
        }
        const operationDeadline = new Deadline(operationTimeoutMs, clock);
        const deadlineAtMs = Date.now() + operationTimeoutMs;
        return schedule(async () => {
          if (state !== "active") {
            throw publicFailure({ code: "CONNECTION_CLOSED", message: "This CutAgent SDK session is closed.", recovery: ["reconnect"], retrySafe: true, retryBasis: preDispatchRetryBasis });
          }
          const requestId = newRequestId();
          const message: CarrierRequest = {
            method: "operation",
            requestId,
            payload: {
              protocolVersion: CUTAGENT_SDK_WIRE_PROTOCOL,
              requestId,
              sessionId: session!.sessionId,
              deadlineAtMs,
              ...operationRequest,
            },
          };
          try {
            const reply = await withinDeadline({
              deadline: operationDeadline,
              ...(operationOptions.signal ? { controlSignal: operationOptions.signal } : {}),
              requestId,
              semantics: operationSemantics,
              run: (signal) => channel!.exchange(message, signal),
            });
            let payload;
            try {
              payload = assertReply(reply, "operation", requestId);
            } catch (error) {
              if (operationSemantics === "uncertain_control"
                && error instanceof CutAgentSdkError
                && error.failure.code === "INVALID_RESPONSE") {
                throw uncertainControlFailure(
                  "INVALID_RESPONSE",
                  "CutAgent returned an uncorrelated operation-control frame; the operation outcome is unknown.",
                  requestId,
                );
              }
              throw error;
            }
            const parsed = sdkOperationControlResponseSchema.safeParse(payload);
            if (!parsed.success) {
              if (operationSemantics === "uncertain_control") {
                throw uncertainControlFailure("INVALID_RESPONSE", "CutAgent returned an invalid operation-control response; the operation outcome is unknown.", requestId);
              }
              throw publicFailure({ code: "INVALID_RESPONSE", message: "CutAgent runtime operation response failed SDK validation.", recovery: ["contact_support"], requestId });
            }
            if (!parsed.data.ok) {
              const failure = PublicFailureSchema.parse(parsed.data.error);
              throw operationSemantics === "uncertain_control"
                ? projectControlFailureAfterDispatch(failure, requestId)
                : new CutAgentSdkError(failure);
            }
            const returnedOperationId = parsed.data.operation === "operation.result.page"
              ? parsed.data.page.operationId
              : parsed.data.event.operationId;
            if (String(parsed.data.requestId) !== String(requestId)
              || parsed.data.operation !== operationRequest.operation
              || (operationRequest.operation !== "operation.create" && returnedOperationId !== operationRequest.operationId)
              || (operationRequest.operation === "operation.create" && parsed.data.operation === "operation.create" && (
                parsed.data.event.snapshot.actionId !== operationRequest.actionId
                || parsed.data.event.snapshot.idempotency?.key !== operationRequest.idempotencyKey
              ))
              || (operationRequest.operation === "operation.result.page" && parsed.data.operation === "operation.result.page" && (
                parsed.data.page.collectionId !== operationRequest.collectionId
                || parsed.data.page.digest !== operationRequest.expectedDigest
                || parsed.data.page.offset !== operationRequest.offset
                || parsed.data.page.entries.length > operationRequest.pageSize
              ))) {
              if (operationSemantics === "uncertain_control") {
                throw uncertainControlFailure("INVALID_RESPONSE", "CutAgent returned an uncorrelated operation-control response; the operation outcome is unknown.", requestId);
              }
              throw publicFailure({ code: "INVALID_RESPONSE", message: "CutAgent runtime returned an uncorrelated operation response.", recovery: ["contact_support"], requestId });
            }
            return (parsed.data.operation === "operation.result.page"
              ? parsed.data.page
              : parsed.data.event) as CarrierOperationSuccessFor<typeof operationRequest>;
          } catch (error) {
            throw projectCarrierFault(error, requestId, operationSemantics);
          }
        });
      },
      workflow(workflowRequest, workflowOptions = {}) {
        if (state !== "active") return Promise.reject(publicFailure({ code: "CONNECTION_CLOSED", message: "This CutAgent SDK session is closed.", recovery: ["reconnect"], retrySafe: true, retryBasis: "pre_execution" }));
        const workflowTimeoutMs = timeoutValue(workflowOptions.timeoutMs ?? timeoutMs);
        const deadline = new Deadline(workflowTimeoutMs, clock);
        return schedule(async () => {
          const requestId = newRequestId();
          const knownWorkflowId = "workflowId" in workflowRequest ? workflowRequest.workflowId : undefined;
          try {
            const message: CarrierRequest = { method: "workflow", requestId, payload: { protocolVersion: CUTAGENT_SDK_WIRE_PROTOCOL, requestId, sessionId: session!.sessionId, deadlineAtMs: Date.now() + workflowTimeoutMs, ...workflowRequest } };
            const reply = await withinDeadline({ deadline, ...(workflowOptions.signal ? { controlSignal: workflowOptions.signal } : {}), requestId, semantics: "uncertain_control", run: (signal) => channel!.exchange(message, signal) });
            const payload = assertReply(reply, "workflow", requestId);
            const parsed = sdkWorkflowControlResponseSchema.safeParse(payload);
            if (!parsed.success) throw uncertainControlFailure("INVALID_RESPONSE", "CutAgent returned an invalid workflow-control response; reattach the workflow before continuing.", requestId);
            if (!parsed.data.ok) {
              if (knownWorkflowId !== undefined && (parsed.data.workflowId !== knownWorkflowId || parsed.data.error.workflowId !== knownWorkflowId)) {
                throw uncertainControlFailure("INVALID_RESPONSE", "CutAgent returned a workflow failure for a different authority identity; reattach the requested workflow before continuing.", requestId);
              }
              throw projectControlFailureAfterDispatch(PublicFailureSchema.parse(parsed.data.error), requestId);
            }
            if (String(parsed.data.requestId) !== String(requestId) || parsed.data.operation !== workflowRequest.operation
              || (knownWorkflowId !== undefined && String(parsed.data.snapshot.workflowId) !== String(knownWorkflowId))) {
              throw uncertainControlFailure("INVALID_RESPONSE", "CutAgent returned an uncorrelated workflow-control response; reattach the workflow before continuing.", requestId);
            }
            return parsed.data.snapshot;
          } catch (error) {
            const carrierProjection = projectCarrierFault(error, requestId, "uncertain_control");
            const projected = carrierProjection.failure.possibleMutation === "none"
              ? projectControlFailureAfterDispatch(carrierProjection.failure, requestId)
              : carrierProjection;
            if (knownWorkflowId === undefined || projected.failure.workflowId !== undefined) throw projected;
            throw new CutAgentSdkError(PublicFailureSchema.parse({ ...projected.failure, workflowId: knownWorkflowId }));
          }
        });
      },
      close(closeOptions = {}) {
        return beginClose(closeOptions, true);
      },
      retire(retireOptions = {}) {
        // Reconnect must interrupt queued/in-flight semantic reads so it can
        // prove the old carrier terminal before installing a replacement.
        return beginClose(retireOptions, true);
      },
      onTerminal(listener) {
        if (state === "closed") {
          queueMicrotask(listener);
          return () => {};
        }
        terminalListeners.add(listener);
        return () => terminalListeners.delete(listener);
      },
    };
  } catch (error) {
    await channel?.settleInterruptedExchange().catch(() => {});
    if (channel && session) {
      const cleanupId = newRequestId();
      await withinDeadline({
        deadline: new Deadline(timeoutMs, Date.now),
        requestId: cleanupId,
        semantics: "pre_execution",
        run: (signal) => channel!.exchange(
          request("close", cleanupId, connector.distribution, session!.sessionId),
          signal,
        ),
      }).then(
        (reply) => parseControlResponse("close", assertReply(reply, "close", cleanupId), cleanupId),
        () => {},
      ).catch(() => {});
    }
    await channel?.disconnect().catch(() => {});
    throw projectCarrierFault(error, undefined, "pre_execution");
  }
}
