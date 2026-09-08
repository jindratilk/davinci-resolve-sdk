import type { RequestId } from "../value-types/identities.js";
import { CarrierFault, MAX_CONTROL_TIMEOUT_MS } from "./carrier-contract.js";
import { projectCarrierFault, publicFailure, uncertainControlFailure, type RequestSemantics } from "./carrier-errors.js";

export class Deadline {
  readonly #expiresAt: number;
  readonly #clock: () => number;

  constructor(timeoutMs: number, clock: () => number) {
    this.#clock = clock;
    this.#expiresAt = clock() + timeoutMs;
  }

  remaining(): number {
    return Math.min(MAX_CONTROL_TIMEOUT_MS, Math.max(0, this.#expiresAt - this.#clock()));
  }
}

export async function withinDeadline<T>(input: {
  deadline: Deadline;
  controlSignal?: AbortSignal;
  requestId?: RequestId;
  semantics: RequestSemantics;
  timeoutProjection?: "timeout" | "unavailable";
  run(signal: AbortSignal): Promise<T>;
}): Promise<T> {
  const remaining = input.deadline.remaining();
  if (remaining <= 0) {
    throw input.timeoutProjection === "unavailable"
      ? projectCarrierFault(new CarrierFault("unavailable"), input.requestId, input.semantics)
      : publicFailure({
        code: "RUNTIME_TIMEOUT",
        message: "CutAgent runtime did not respond before the request deadline.",
        recovery: ["retry"],
        ...(input.requestId ? { requestId: input.requestId } : {}),
        retrySafe: true,
        retryBasis: input.semantics === "uncertain_control" ? "pre_execution" : input.semantics,
      });
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new DOMException("Timed out", "TimeoutError")), remaining);
  const signal = input.controlSignal ? AbortSignal.any([controller.signal, input.controlSignal]) : controller.signal;
  let removeAbortListener = () => {};
  let requestStarted = false;
  try {
    if (signal.aborted) throw signal.reason ?? new DOMException("Aborted", "AbortError");
    const aborted = new Promise<never>((_resolve, reject) => {
      const onAbort = () => reject(signal.reason ?? new DOMException("Aborted", "AbortError"));
      removeAbortListener = () => signal.removeEventListener("abort", onAbort);
      signal.addEventListener("abort", onAbort, { once: true });
      if (signal.aborted) onAbort();
    });
    requestStarted = true;
    return await Promise.race([input.run(signal), aborted]);
  } catch (error) {
    if (input.controlSignal?.aborted) {
      if (input.semantics === "uncertain_control" && requestStarted) {
        throw uncertainControlFailure(
          "CANCELLED",
          "Local cancellation stopped waiting for the cancellation request; the operation outcome is unknown.",
          input.requestId,
        );
      }
      throw publicFailure({
        code: "CANCELLED",
        message: input.semantics === "read_only"
          ? "The CutAgent SDK semantic read was aborted locally."
          : "The CutAgent SDK control request was aborted before completion.",
        recovery: ["retry"],
        ...(input.requestId ? { requestId: input.requestId } : {}),
        retrySafe: true,
        retryBasis: input.semantics === "uncertain_control" ? "pre_execution" : input.semantics,
      });
    }
    if (controller.signal.aborted) {
      if (input.timeoutProjection === "unavailable") {
        throw projectCarrierFault(new CarrierFault("unavailable"), input.requestId, input.semantics);
      }
      if (input.semantics === "uncertain_control" && requestStarted) {
        throw uncertainControlFailure(
          "RUNTIME_TIMEOUT",
          "The local deadline stopped waiting for cancellation; the operation outcome is unknown.",
          input.requestId,
        );
      }
      throw publicFailure({
        code: "RUNTIME_TIMEOUT",
        message: input.semantics === "read_only"
          ? "CutAgent runtime did not complete the semantic read before its deadline."
          : "CutAgent runtime did not respond before the request deadline.",
        recovery: ["retry"],
        ...(input.requestId ? { requestId: input.requestId } : {}),
        retrySafe: true,
        retryBasis: input.semantics === "uncertain_control" ? "pre_execution" : input.semantics,
      });
    }
    throw projectCarrierFault(error, input.requestId, input.semantics);
  } finally {
    removeAbortListener();
    clearTimeout(timer);
  }
}
