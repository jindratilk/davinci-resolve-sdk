import {
  DEFAULT_CONTROL_TIMEOUT_MS,
  MAX_CONTROL_TIMEOUT_MS,
  MIN_CONTROL_TIMEOUT_MS,
  type CarrierRequest,
} from "../core/carrier-contract.js";

/** Bound the private broker wait to the public request deadline. @internal */
export function brokerExchangeTimeoutMs(
  request: CarrierRequest,
  nowMs = Date.now(),
): number {
  const deadlineAtMs = "deadlineAtMs" in request.payload
    ? request.payload.deadlineAtMs
    : null;
  if (typeof deadlineAtMs !== "number" || !Number.isSafeInteger(deadlineAtMs)) {
    return DEFAULT_CONTROL_TIMEOUT_MS;
  }
  return Math.min(
    MAX_CONTROL_TIMEOUT_MS,
    Math.max(MIN_CONTROL_TIMEOUT_MS, deadlineAtMs - nowMs),
  );
}
