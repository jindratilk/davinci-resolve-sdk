import type { z } from "zod";
import {
  SDK_PUBLIC_ERROR_KIND_BY_CODE,
  sdkFailureKindSchema,
  sdkPossibleMutationStateSchema,
  sdkPublicErrorCauseSchema,
  sdkPublicErrorCodeSchema,
  sdkPublicFailureSchema,
  sdkRecoveryActionSchema,
  sdkRecoveryOutcomeSchema,
  sdkRetrySafetyProofSchema,
  sdkUsageStateSchema,
} from "../generated/sdk-operations.js";
import type {
  ExecutionId,
  IdempotencyKey,
  IncidentId,
  OperationId,
  RequestId,
  WorkflowId,
} from "../value-types/identities.js";
export { CutAgentSdkError } from "../core/sdk-error.js";

/** Stable high-level failure classification. @beta */
export type FailureKind =
  | "usage_exhausted" | "request_too_large" | "output_limit_reached"
  | "runtime_unavailable" | "runtime_timeout" | "runtime_crashed" | "runtime_incompatible"
  | "authentication_required" | "subscription_required" | "connection_closed"
  | "dependency_unavailable" | "temporary_provider_failure" | "operation_failed"
  | "operation_expired" | "idempotency_conflict"
  | "target_not_found" | "ambiguous_target" | "stale_revision" | "capability_unavailable"
  | "verification_failed" | "recovery_failed" | "cancelled" | "invalid_request" | "invalid_response" | "unknown";
/** Stable high-level failure classification. @beta */
export const FailureKindSchema: z.ZodType<FailureKind> = sdkFailureKindSchema;
/** Stable public error code. @beta */
export type PublicErrorCode =
  | "SDK_INCOMPATIBLE" | "AUTHENTICATION_REQUIRED" | "SUBSCRIPTION_REQUIRED" | "CONNECTION_CLOSED"
  | "INVALID_REQUEST" | "INVALID_RESPONSE" | "CAPABILITY_UNAVAILABLE" | "TARGET_NOT_FOUND" | "AMBIGUOUS_TARGET"
  | "STALE_REVISION" | "USAGE_EXHAUSTED" | "REQUEST_TOO_LARGE"
  | "OUTPUT_LIMIT_REACHED" | "RUNTIME_UNAVAILABLE" | "RUNTIME_TIMEOUT" | "RUNTIME_CRASHED"
  | "DEPENDENCY_UNAVAILABLE" | "TEMPORARY_PROVIDER_FAILURE" | "OPERATION_FAILED"
  | "OPERATION_EXPIRED" | "IDEMPOTENCY_CONFLICT" | "VERIFICATION_FAILED" | "RECOVERY_FAILED"
  | "CANCELLED" | "UNKNOWN";
/** Stable public error code. @beta */
export const PublicErrorCodeSchema: z.ZodType<PublicErrorCode> = sdkPublicErrorCodeSchema;
/** Canonical stable error-code to failure-kind mapping. @beta */
export const PUBLIC_ERROR_KIND_BY_CODE = SDK_PUBLIC_ERROR_KIND_BY_CODE;
/** Recommended next action for a public failure. @beta */
export type Recovery =
  | "upgrade_or_wait" | "continue" | "start_continuation" | "restart_runtime" | "update_required"
  | "sign_in" | "reconnect" | "retry" | "inspect_state" | "manual_recovery" | "contact_support";
/** Recommended next action for a public failure. @beta */
export const RecoverySchema: z.ZodType<Recovery> = sdkRecoveryActionSchema;
/** Whether a request may have changed project state. @beta */
export type PossibleMutationState = "none" | "possible" | "confirmed" | "partial" | "unknown";
/** Whether a request may have changed project state. @beta */
export const PossibleMutationStateSchema: z.ZodType<PossibleMutationState> = sdkPossibleMutationStateSchema;
/** Account usage disposition associated with an outcome. @beta */
export type UsageState = "not_reserved" | "reserved" | "consumed" | "released" | "unknown";
/** Account usage disposition associated with an outcome. @beta */
export const UsageStateSchema: z.ZodType<UsageState> = sdkUsageStateSchema;
/** Result of an attempted recovery action. @beta */
export type RecoveryOutcome =
  | { status: "not_attempted" }
  | { status: "succeeded"; summary: string }
  | { status: "failed"; summary: string; manualRecoveryRequired: boolean };
/** Result of an attempted recovery action. @beta */
export const RecoveryOutcomeSchema: z.ZodType<RecoveryOutcome> = sdkRecoveryOutcomeSchema;
/** Evidence required before the SDK may describe an immediate retry as safe. @beta */
export type RetrySafetyProof =
  | { basis: "pre_execution" }
  | { basis: "read_only" }
  | { basis: "idempotent_replay"; idempotencyKey: IdempotencyKey; operationId: OperationId };
/** Evidence required before the SDK may describe an immediate retry as safe. @beta */
export const RetrySafetyProofSchema = sdkRetrySafetyProofSchema as unknown as z.ZodType<RetrySafetyProof>;
/** Sanitized causal error. It never contains private traces. @beta */
export interface PublicErrorCause {
  code: string;
  message: string;
}
/** Sanitized causal error. @beta */
export const PublicErrorCauseSchema: z.ZodType<PublicErrorCause> = sdkPublicErrorCauseSchema;
/** Fully typed public failure and recovery contract. @beta */
/** Fully typed public failure and recovery contract. @beta */
export type PublicFailure = {
  message: string;
  recoveryGuidance: string[];
  recoveryOutcome?: RecoveryOutcome;
  requestId?: RequestId;
  operationId?: OperationId;
  workflowId?: WorkflowId;
  executionId?: ExecutionId;
  idempotencyKey?: IdempotencyKey;
  incidentId?: IncidentId;
  cause?: PublicErrorCause;
} & {
    kind: FailureKind;
    code: PublicErrorCode;
    retrySafe: boolean;
    retrySafetyProof?: RetrySafetyProof;
    possibleMutation: PossibleMutationState;
    usage: UsageState;
    recovery: Recovery[];
    readbackRequired: boolean;
};
/** Fully typed public failure and recovery contract. @beta */
export const PublicFailureSchema = sdkPublicFailureSchema as unknown as z.ZodType<PublicFailure>;
