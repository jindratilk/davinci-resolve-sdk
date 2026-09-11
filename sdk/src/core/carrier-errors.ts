import { z } from "zod";
import {
  sdkRuntimeFailureSchema,
  sdkRuntimeReadFailureSchema,
  sdkTransportErrorCodeSchema,
} from "../generated/sdk-runtime.js";
import {
  CutAgentSdkError,
  PUBLIC_ERROR_KIND_BY_CODE,
  PublicFailureSchema,
  type PublicErrorCode,
  type PublicFailure,
  type Recovery,
} from "../protocol/errors.js";
import type { RequestId } from "../value-types/identities.js";
import { CarrierFault } from "./carrier-contract.js";

export type RetryBasis = "pre_execution" | "read_only";
export type RequestSemantics = RetryBasis | "uncertain_control";
type CarrierPublicErrorCode = Exclude<
  PublicErrorCode,
  "OPERATION_EXPIRED" | "IDEMPOTENCY_CONFLICT"
>;

type TransportFailure = z.infer<typeof sdkRuntimeFailureSchema>;
type ReadFailure = z.infer<typeof sdkRuntimeReadFailureSchema>;
type TransportErrorCode = z.infer<typeof sdkTransportErrorCodeSchema>;

export function publicFailure(input: {
  code: CarrierPublicErrorCode;
  message: string;
  recovery: Recovery[];
  requestId?: RequestId;
  retrySafe?: boolean;
  retryBasis?: RetryBasis;
  possibleMutation?: "none" | "unknown";
  usage?: "not_reserved" | "unknown";
  readbackRequired?: boolean;
}): CutAgentSdkError {
  const retrySafe = input.retrySafe ?? false;
  return new CutAgentSdkError({
    kind: PUBLIC_ERROR_KIND_BY_CODE[input.code],
    code: input.code,
    message: input.message,
    retrySafe,
    ...(retrySafe ? { retrySafetyProof: { basis: input.retryBasis ?? "pre_execution" } } : {}),
    possibleMutation: input.possibleMutation ?? "none",
    usage: input.usage ?? "not_reserved",
    recovery: input.recovery,
    recoveryGuidance: [input.message],
    readbackRequired: input.readbackRequired ?? false,
    ...(input.requestId ? { requestId: input.requestId } : {}),
  });
}

export function uncertainControlFailure(
  code: Extract<CarrierPublicErrorCode, "CANCELLED" | "RUNTIME_TIMEOUT" | "RUNTIME_CRASHED" | "RUNTIME_UNAVAILABLE" | "INVALID_RESPONSE">,
  message: string,
  requestId?: RequestId,
): CutAgentSdkError {
  return publicFailure({
    code,
    message,
    recovery: ["reconnect", "inspect_state"],
    ...(requestId ? { requestId } : {}),
    possibleMutation: "unknown",
    usage: "unknown",
    readbackRequired: true,
  });
}

export function projectControlFailureAfterDispatch(
  failure: PublicFailure,
  requestId: RequestId,
): CutAgentSdkError {
  if (failure.code === "IDEMPOTENCY_CONFLICT"
    && failure.possibleMutation === "none" && failure.usage === "not_reserved") {
    return new CutAgentSdkError({ ...failure, requestId });
  }
  if (failure.retrySafe && failure.retrySafetyProof?.basis === "pre_execution") {
    return new CutAgentSdkError({ ...failure, requestId });
  }
  const withoutRetryProof: Record<string, unknown> = { ...failure };
  delete withoutRetryProof.retrySafetyProof;
  const recovery = [...new Set<Recovery>([
    ...failure.recovery.filter((action) => action !== "retry"),
    "reconnect",
    "inspect_state",
  ])];
  const candidate = PublicFailureSchema.safeParse({
    ...withoutRetryProof,
    requestId,
    retrySafe: false,
    possibleMutation: failure.possibleMutation === "none" ? "unknown" : failure.possibleMutation,
    usage: failure.usage === "not_reserved" ? "unknown" : failure.usage,
    recovery,
    recoveryGuidance: ["Reconnect and inspect the original operation before retrying this control request."],
    readbackRequired: true,
  });
  return candidate.success
    ? new CutAgentSdkError(candidate.data)
    : uncertainControlFailure(
      "RUNTIME_UNAVAILABLE",
      `${failure.message} The operation-control outcome is unknown.`,
      requestId,
    );
}

function retryMessage(semantics: RequestSemantics, general: string, readOnly: string): string {
  return semantics === "read_only" ? readOnly : general;
}

export function projectCarrierFault(
  error: unknown,
  requestId: RequestId | undefined,
  semantics: RequestSemantics,
): CutAgentSdkError {
  if (error instanceof CutAgentSdkError) {
    if (requestId === undefined || error.failure.requestId === requestId) return error;
    return new CutAgentSdkError({ ...error.failure, requestId });
  }
  if (error instanceof CarrierFault && error.kind === "invalid_response") {
    if (semantics === "uncertain_control") {
      return uncertainControlFailure("INVALID_RESPONSE", "CutAgent returned an invalid operation-control response; the request outcome is unknown.", requestId);
    }
    return publicFailure({
      code: "INVALID_RESPONSE",
      message: "CutAgent runtime returned an invalid carrier response.",
      recovery: ["contact_support"],
      ...(requestId ? { requestId } : {}),
    });
  }
  if (error instanceof CarrierFault && error.kind === "incompatible") {
    if (semantics === "uncertain_control") {
      return uncertainControlFailure("RUNTIME_UNAVAILABLE", "CutAgent compatibility changed while an operation-control outcome was pending.", requestId);
    }
    return publicFailure({
      code: "SDK_INCOMPATIBLE",
      message: "The installed CutAgent runtime is incompatible with this SDK.",
      recovery: ["update_required"],
      ...(requestId ? { requestId } : {}),
    });
  }
  if (error instanceof CarrierFault && error.kind === "authentication_required") {
    if (semantics === "uncertain_control") {
      return uncertainControlFailure("RUNTIME_UNAVAILABLE", "Authentication changed while an operation-control outcome was pending.", requestId);
    }
    return publicFailure({
      code: "AUTHENTICATION_REQUIRED",
      message: "Sign in to CutAgent before connecting the SDK.",
      recovery: ["sign_in"],
      ...(requestId ? { requestId } : {}),
    });
  }
  if (error instanceof CarrierFault && error.kind === "disconnected") {
    if (semantics === "uncertain_control") {
      return uncertainControlFailure("RUNTIME_CRASHED", "The CutAgent connection ended before the operation-control outcome was received.", requestId);
    }
    return publicFailure({
      code: "RUNTIME_CRASHED",
      message: retryMessage(
        semantics,
        "The CutAgent runtime connection ended unexpectedly.",
        "The CutAgent runtime connection ended during a semantic read.",
      ),
      recovery: ["restart_runtime", "retry"],
      ...(requestId ? { requestId } : {}),
      retrySafe: true,
      retryBasis: semantics,
    });
  }
  if (semantics === "uncertain_control") {
    return uncertainControlFailure("RUNTIME_UNAVAILABLE", "CutAgent did not return an operation-control outcome; inspect the original operation before retrying.", requestId);
  }
  return publicFailure({
    code: "RUNTIME_UNAVAILABLE",
    message: retryMessage(
      semantics,
      "CutAgent runtime is not reachable.",
      "CutAgent runtime could not complete the semantic read.",
    ),
    recovery: ["restart_runtime", "retry"],
    ...(requestId ? { requestId } : {}),
    retrySafe: true,
    retryBasis: semantics,
  });
}

function uncorrelatedFailure(
  response: TransportFailure | ReadFailure,
  expectedRequestId: RequestId,
): CutAgentSdkError | null {
  if (response.requestId !== undefined && String(response.requestId) !== String(expectedRequestId)) {
    return publicFailure({
      code: "INVALID_RESPONSE",
      message: "CutAgent runtime returned an uncorrelated failure.",
      recovery: ["contact_support"],
      requestId: expectedRequestId,
    });
  }
  return null;
}

function mapTransportError(
  code: TransportErrorCode,
  expectedRequestId: RequestId,
  semantics: RetryBasis,
): CutAgentSdkError {
  switch (code) {
    case "AUTHENTICATION_REQUIRED":
      return publicFailure({ code: "AUTHENTICATION_REQUIRED", message: "Sign in to CutAgent before connecting the SDK.", recovery: ["sign_in"], requestId: expectedRequestId });
    case "SUBSCRIPTION_REQUIRED":
      return publicFailure({ code: "SUBSCRIPTION_REQUIRED", message: "An active CutAgent subscription is required to connect the SDK.", recovery: ["upgrade_or_wait"], requestId: expectedRequestId });
    case "SDK_INCOMPATIBLE":
      return publicFailure({ code: "SDK_INCOMPATIBLE", message: "The installed CutAgent runtime is incompatible with this SDK.", recovery: ["update_required"], requestId: expectedRequestId });
    case "SESSION_REJECTED":
      return publicFailure({ code: "CONNECTION_CLOSED", message: "The CutAgent SDK session is closed or expired.", recovery: ["reconnect"], requestId: expectedRequestId, retrySafe: true, retryBasis: semantics });
    case "BOOTSTRAP_REJECTED":
      return publicFailure({ code: "RUNTIME_UNAVAILABLE", message: "CutAgent runtime could not establish the SDK connection.", recovery: ["restart_runtime", "retry"], requestId: expectedRequestId, retrySafe: true, retryBasis: "pre_execution" });
    case "RUNTIME_UNAVAILABLE":
      return publicFailure({
        code: "RUNTIME_UNAVAILABLE",
        message: retryMessage(semantics, "CutAgent runtime is temporarily unavailable.", "CutAgent runtime could not complete the semantic read."),
        recovery: ["restart_runtime", "retry"],
        requestId: expectedRequestId,
        retrySafe: true,
        retryBasis: semantics,
      });
    case "SESSION_LIMIT_REACHED":
      return publicFailure({ code: "RUNTIME_UNAVAILABLE", message: "CutAgent runtime cannot accept another SDK session.", recovery: ["reconnect", "contact_support"], requestId: expectedRequestId });
    case "INVALID_REQUEST":
      return publicFailure({ code: "INVALID_REQUEST", message: "CutAgent runtime rejected the SDK wire request.", recovery: ["update_required"], requestId: expectedRequestId });
    case "INTERNAL_ERROR":
      return publicFailure({ code: "RUNTIME_UNAVAILABLE", message: "CutAgent runtime could not complete the SDK control request.", recovery: ["restart_runtime", "contact_support"], requestId: expectedRequestId });
  }
}

export function mapTransportFailure(
  response: TransportFailure,
  expectedRequestId: RequestId,
  semantics: RetryBasis,
): CutAgentSdkError {
  return uncorrelatedFailure(response, expectedRequestId)
    ?? mapTransportError(response.error.code, expectedRequestId, semantics);
}

export function mapReadFailure(
  response: ReadFailure,
  expectedRequestId: RequestId,
): CutAgentSdkError {
  const uncorrelated = uncorrelatedFailure(response, expectedRequestId);
  if (uncorrelated) return uncorrelated;
  switch (response.error.code) {
    case "RUNTIME_TIMEOUT":
      return publicFailure({ code: "RUNTIME_TIMEOUT", message: "CutAgent runtime did not complete the semantic read before its absolute deadline.", recovery: ["retry"], requestId: expectedRequestId, retrySafe: true, retryBasis: "read_only" });
    case "RUNTIME_UNAVAILABLE":
      if (response.error.recovery === "retry") {
        return publicFailure({ code: "RUNTIME_UNAVAILABLE", message: "CutAgent runtime is temporarily unable to complete this request. Retry the request.", recovery: ["retry"], requestId: expectedRequestId, retrySafe: true, retryBasis: "read_only" });
      }
      return mapTransportError(response.error.code, expectedRequestId, "read_only");
    case "CAPABILITY_UNAVAILABLE":
      return publicFailure({
        code: "CAPABILITY_UNAVAILABLE",
        message: "The requested CutAgent capability is not available in this release.",
        recovery: [response.error.recovery === "upgrade_or_wait" ? "upgrade_or_wait" : "update_required"],
        requestId: expectedRequestId,
      });
    case "TARGET_NOT_FOUND":
      return publicFailure({ code: "TARGET_NOT_FOUND", message: "The requested DaVinci Resolve object was not found.", recovery: ["inspect_state"], requestId: expectedRequestId, retrySafe: true, retryBasis: "read_only" });
    case "AMBIGUOUS_TARGET":
      return publicFailure({ code: "AMBIGUOUS_TARGET", message: "The requested DaVinci Resolve object is ambiguous.", recovery: ["inspect_state"], requestId: expectedRequestId });
    case "STALE_REVISION":
      return publicFailure({ code: "STALE_REVISION", message: "The referenced DaVinci Resolve state is stale.", recovery: ["inspect_state"], requestId: expectedRequestId, retrySafe: true, retryBasis: "read_only" });
    case "INVALID_REQUEST":
      return publicFailure({ code: "INVALID_REQUEST", message: response.error.message, recovery: ["inspect_state"], requestId: expectedRequestId });
    case "INVALID_RESPONSE":
      return publicFailure({ code: "INVALID_RESPONSE", message: "CutAgent runtime returned invalid live inspection data.", recovery: ["contact_support"], requestId: expectedRequestId });
    case "USAGE_EXHAUSTED":
      return publicFailure({ code: "USAGE_EXHAUSTED", message: "The signed-in account has no available hosted usage for this request.", recovery: ["upgrade_or_wait"], requestId: expectedRequestId });
    case "TEMPORARY_PROVIDER_FAILURE":
      return publicFailure({ code: "TEMPORARY_PROVIDER_FAILURE", message: "The hosted voice catalog is temporarily unavailable.", recovery: ["retry"], requestId: expectedRequestId, retrySafe: true, retryBasis: "read_only" });
    default:
      return mapTransportError(response.error.code, expectedRequestId, "read_only");
  }
}
