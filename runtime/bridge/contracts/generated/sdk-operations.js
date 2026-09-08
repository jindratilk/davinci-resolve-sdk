import { z } from "zod";
import { CUTAGENT_SDK_ACTION_CONTRACT_VERSION, CUTAGENT_SDK_ACTION_INVENTORY_DIGEST, CUTAGENT_SDK_PUBLIC_ACTION_IDS, } from "./sdk-operation-actions.js";
import { CUTAGENT_SDK_LOW_LEVEL_READ_ACTION_IDS } from "./sdk-low-level-read-actions.js";
import { sdkArtifactIdSchema, sdkEvidenceIdSchema, sdkExecutionIdSchema, sdkIdempotencyKeySchema, sdkIncidentIdSchema, sdkMarkerIdSchema, sdkMediaPoolItemIdSchema, sdkMulticamAngleIdSchema, sdkMulticamIdSchema, sdkOperationIdSchema, sdkProjectIdSchema, sdkRequestIdSchema, sdkRevisionSchema, sdkSessionIdSchema, sdkSnapshotRenderJobIdSchema, sdkSnapshotTimelineItemIdSchema, sdkTimelineIdSchema, sdkTimelineItemIdSchema, sdkWorkflowIdSchema, } from "./sdk-identities.js";
import { sdkTimelineEditImpactSchema, } from "./sdk-timeline-editing.js";
import { sdkFusionGraphApplyInputSchema } from "./sdk-fusion.js";
import { sdkFairlightPlanInputSchema, sdkFairlightSemanticResultSchema, } from "./sdk-fairlight.js";
import { CUTAGENT_SDK_FAIRLIGHT_PREPARED_ACTION_IDS, CUTAGENT_SDK_FAIRLIGHT_CARRIER_OWNED_ACTION_IDS, sdkFairlightPreparedOperationInputSchema, } from "./sdk-fairlight-prepared-actions.js";
import { sdkMediaPoolCreateBinInputSchema, sdkMediaPoolCreateBinResultSchema, sdkMediaPoolImportInputSchema, sdkMediaPoolImportResultSchema, sdkMediaPoolRelinkInputSchema, sdkMediaPoolRelinkResultSchema, sdkMediaPoolSetMetadataInputSchema, sdkMediaPoolSetMetadataResultSchema, sdkMediaPoolSyncAudioInputSchema, sdkMediaPoolSyncAudioResultSchema, sdkProjectBackupInputSchema, sdkProjectCreateInputSchema, sdkProjectLibraryBackupInputSchema, sdkProjectLibraryCreateInputSchema, sdkProjectLibraryOpenInputSchema, sdkProjectLibraryRestoreInputSchema, sdkProjectOpenInputSchema, sdkProjectRestoreInputSchema, } from "./sdk-project-media.js";
export { CUTAGENT_SDK_ACTION_CONTRACT_VERSION, CUTAGENT_SDK_ACTION_INVENTORY_DIGEST, CUTAGENT_SDK_PUBLIC_ACTION_IDS, } from "./sdk-operation-actions.js";
export { CUTAGENT_SDK_LOW_LEVEL_READ_ACTION_IDS } from "./sdk-low-level-read-actions.js";
export * from "./sdk-fairlight.js";
export * from "./sdk-fairlight-prepared-actions.js";
export * from "./sdk-project-media.js";
export const sdkPublicActionIdSchema = z.enum(CUTAGENT_SDK_PUBLIC_ACTION_IDS);
export const sdkLowLevelReadActionIdSchema = z.enum(CUTAGENT_SDK_LOW_LEVEL_READ_ACTION_IDS);
const utf16BoundedTextSchema = (maximumCodeUnits, field) => z.string().min(1).refine((value) => value.length <= maximumCodeUnits, `${field} must contain at most ${maximumCodeUnits} UTF-16 code units`);
export const CUTAGENT_SDK_PUBLIC_ACTION_RESULT_MAX_BYTES = 12 * 1024 * 1024;
export const CUTAGENT_SDK_OPERATION_REQUEST_MAX_BYTES = 8 * 1024 * 1024;
const CUTAGENT_SDK_PUBLIC_TIMESTAMP_MAX_CHARS = 64;
const sdkPublicTimestampSchema = z.string()
    .max(CUTAGENT_SDK_PUBLIC_TIMESTAMP_MAX_CHARS)
    .datetime({ offset: true });
const utf8Encoder = new TextEncoder();
export const sdkFailureKindSchema = z.enum([
    "usage_exhausted",
    "request_too_large",
    "output_limit_reached",
    "runtime_unavailable",
    "runtime_timeout",
    "runtime_crashed",
    "runtime_incompatible",
    "authentication_required",
    "subscription_required",
    "connection_closed",
    "dependency_unavailable",
    "temporary_provider_failure",
    "operation_failed",
    "operation_expired",
    "idempotency_conflict",
    "edit_constraint_violation",
    "target_not_found",
    "ambiguous_target",
    "stale_revision",
    "capability_unavailable",
    "verification_failed",
    "recovery_failed",
    "cancelled",
    "invalid_request",
    "invalid_response",
    "unknown",
]);
export const sdkPublicErrorCodeSchema = z.enum([
    "SDK_INCOMPATIBLE",
    "AUTHENTICATION_REQUIRED",
    "SUBSCRIPTION_REQUIRED",
    "CONNECTION_CLOSED",
    "INVALID_REQUEST",
    "INVALID_RESPONSE",
    "CAPABILITY_UNAVAILABLE",
    "TARGET_NOT_FOUND",
    "AMBIGUOUS_TARGET",
    "STALE_REVISION",
    "EDIT_CONSTRAINT_VIOLATION",
    "USAGE_EXHAUSTED",
    "REQUEST_TOO_LARGE",
    "OUTPUT_LIMIT_REACHED",
    "RUNTIME_UNAVAILABLE",
    "RUNTIME_TIMEOUT",
    "RUNTIME_CRASHED",
    "DEPENDENCY_UNAVAILABLE",
    "TEMPORARY_PROVIDER_FAILURE",
    "OPERATION_FAILED",
    "OPERATION_EXPIRED",
    "IDEMPOTENCY_CONFLICT",
    "VERIFICATION_FAILED",
    "RECOVERY_FAILED",
    "CANCELLED",
    "UNKNOWN",
]);
export const SDK_PUBLIC_ERROR_KIND_BY_CODE = Object.freeze({
    SDK_INCOMPATIBLE: "runtime_incompatible",
    AUTHENTICATION_REQUIRED: "authentication_required",
    SUBSCRIPTION_REQUIRED: "subscription_required",
    CONNECTION_CLOSED: "connection_closed",
    INVALID_REQUEST: "invalid_request",
    INVALID_RESPONSE: "invalid_response",
    CAPABILITY_UNAVAILABLE: "capability_unavailable",
    TARGET_NOT_FOUND: "target_not_found",
    AMBIGUOUS_TARGET: "ambiguous_target",
    STALE_REVISION: "stale_revision",
    EDIT_CONSTRAINT_VIOLATION: "edit_constraint_violation",
    USAGE_EXHAUSTED: "usage_exhausted",
    REQUEST_TOO_LARGE: "request_too_large",
    OUTPUT_LIMIT_REACHED: "output_limit_reached",
    RUNTIME_UNAVAILABLE: "runtime_unavailable",
    RUNTIME_TIMEOUT: "runtime_timeout",
    RUNTIME_CRASHED: "runtime_crashed",
    DEPENDENCY_UNAVAILABLE: "dependency_unavailable",
    TEMPORARY_PROVIDER_FAILURE: "temporary_provider_failure",
    OPERATION_FAILED: "operation_failed",
    OPERATION_EXPIRED: "operation_expired",
    IDEMPOTENCY_CONFLICT: "idempotency_conflict",
    VERIFICATION_FAILED: "verification_failed",
    RECOVERY_FAILED: "recovery_failed",
    CANCELLED: "cancelled",
    UNKNOWN: "unknown",
});
export const sdkRecoveryActionSchema = z.enum([
    "upgrade_or_wait",
    "continue",
    "start_continuation",
    "restart_runtime",
    "update_required",
    "sign_in",
    "reconnect",
    "retry",
    "inspect_state",
    "manual_recovery",
    "contact_support",
]);
export const sdkPossibleMutationStateSchema = z.enum(["none", "possible", "confirmed", "partial", "unknown"]);
export const sdkUsageStateSchema = z.enum(["not_reserved", "reserved", "consumed", "released", "unknown"]);
export const sdkRecoveryOutcomeSchema = z.discriminatedUnion("status", [
    z.object({ status: z.literal("not_attempted") }).strict(),
    z.object({ status: z.literal("succeeded"), summary: z.string().min(1).max(500) }).strict(),
    z.object({
        status: z.literal("failed"),
        summary: z.string().min(1).max(500),
        manualRecoveryRequired: z.boolean(),
    }).strict(),
]);
export const sdkRetrySafetyProofSchema = z.discriminatedUnion("basis", [
    z.object({ basis: z.literal("pre_execution") }).strict(),
    z.object({ basis: z.literal("read_only") }).strict(),
    z.object({
        basis: z.literal("idempotent_replay"),
        idempotencyKey: sdkIdempotencyKeySchema,
        operationId: sdkOperationIdSchema,
    }).strict(),
]);
export const sdkPublicErrorCauseSchema = z.object({
    code: z.string().min(1).max(100).regex(/^[A-Z][A-Z0-9_]*$/),
    message: z.string().min(1).max(1000),
}).strict();
const publicFailureCommon = {
    message: z.string().min(1).max(2000),
    recoveryGuidance: z.array(z.string().min(1).max(500)).min(1).max(5),
    recoveryOutcome: sdkRecoveryOutcomeSchema.optional(),
    requestId: sdkRequestIdSchema.optional(),
    operationId: sdkOperationIdSchema.optional(),
    workflowId: sdkWorkflowIdSchema.optional(),
    executionId: sdkExecutionIdSchema.optional(),
    idempotencyKey: sdkIdempotencyKeySchema.optional(),
    incidentId: sdkIncidentIdSchema.optional(),
    cause: sdkPublicErrorCauseSchema.optional(),
};
const sdkEditConstraintViolationFailureSchema = z.object({
    ...publicFailureCommon,
    kind: z.literal("edit_constraint_violation"),
    code: z.literal("EDIT_CONSTRAINT_VIOLATION"),
    retrySafe: z.literal(false),
    possibleMutation: z.literal("none"),
    usage: z.literal("not_reserved"),
    recovery: z.array(sdkRecoveryActionSchema.exclude(["retry"])).min(1).max(5),
    readbackRequired: z.literal(false),
}).strict();
const sdkOtherPublicFailureSchema = z.object({
    ...publicFailureCommon,
    kind: sdkFailureKindSchema,
    code: sdkPublicErrorCodeSchema.exclude(["EDIT_CONSTRAINT_VIOLATION"]),
    retrySafe: z.boolean(),
    retrySafetyProof: sdkRetrySafetyProofSchema.optional(),
    possibleMutation: sdkPossibleMutationStateSchema,
    usage: sdkUsageStateSchema,
    recovery: z.array(sdkRecoveryActionSchema).min(1).max(5),
    readbackRequired: z.boolean(),
}).strict().superRefine((failure, context) => {
    if (failure.kind !== SDK_PUBLIC_ERROR_KIND_BY_CODE[failure.code]) {
        context.addIssue({ code: "custom", path: ["kind"], message: `${failure.code} has a contradictory failure kind` });
    }
    if (failure.retrySafe !== (failure.retrySafetyProof !== undefined)) {
        context.addIssue({ code: "custom", path: ["retrySafetyProof"], message: "Retry safety requires matching proof" });
    }
    if (failure.retrySafetyProof !== undefined
        && failure.retrySafetyProof.basis !== "idempotent_replay"
        && failure.possibleMutation !== "none") {
        context.addIssue({ code: "custom", path: ["retrySafetyProof"], message: "Pre-execution and read-only retry proof require no possible mutation" });
    }
    if (failure.retrySafetyProof?.basis === "idempotent_replay"
        && (failure.retrySafetyProof.operationId !== failure.operationId
            || failure.retrySafetyProof.idempotencyKey !== failure.idempotencyKey)) {
        context.addIssue({ code: "custom", path: ["retrySafetyProof"], message: "Idempotent replay proof must preserve operation and idempotency identity" });
    }
    if (failure.code === "SDK_INCOMPATIBLE"
        && (failure.retrySafe || failure.possibleMutation !== "none" || failure.usage !== "not_reserved"
            || failure.readbackRequired || failure.recovery.length !== 1 || failure.recovery[0] !== "update_required"
            || failure.recoveryOutcome !== undefined)) {
        context.addIssue({ code: "custom", path: ["code"], message: "SDK_INCOMPATIBLE must remain a non-mutating pre-run update failure" });
    }
    if (failure.code === "RECOVERY_FAILED"
        && (failure.recoveryOutcome?.status !== "failed" || !failure.recoveryOutcome.manualRecoveryRequired)) {
        context.addIssue({ code: "custom", path: ["recoveryOutcome"], message: "RECOVERY_FAILED requires failed recovery and manual intervention" });
    }
    if (failure.code === "OPERATION_EXPIRED"
        && (!(failure.operationId || failure.workflowId) || failure.retrySafe
            || !((failure.possibleMutation === "none" && !failure.readbackRequired)
                || ((failure.possibleMutation === "possible" || failure.possibleMutation === "unknown")
                    && failure.readbackRequired)))) {
        context.addIssue({ code: "custom", path: ["code"], message: "OPERATION_EXPIRED requires correlated conservative mutation and readback truth" });
    }
    if (failure.code === "IDEMPOTENCY_CONFLICT"
        && (!(failure.operationId || failure.workflowId) || !failure.idempotencyKey || failure.retrySafe
            || failure.possibleMutation !== "none" || failure.readbackRequired)) {
        context.addIssue({ code: "custom", path: ["code"], message: "IDEMPOTENCY_CONFLICT requires the original operation and key without a retry claim" });
    }
});
export const sdkPublicFailureSchema = z.discriminatedUnion("code", [
    sdkEditConstraintViolationFailureSchema,
    sdkOtherPublicFailureSchema,
]);
export const sdkVerificationOutcomeSchema = z.enum(["passed", "failed", "partial", "not_performed", "manual_review_required"]);
export const sdkEvidenceModalitySchema = z.enum(["readback", "structural", "file", "rendered", "visual", "auditioned"]);
export const sdkVerificationEvidenceSchema = z.object({
    evidenceId: sdkEvidenceIdSchema,
    modality: sdkEvidenceModalitySchema,
    summary: z.string().min(1).max(1000),
    capturedAt: sdkPublicTimestampSchema,
    artifactId: sdkArtifactIdSchema.optional(),
    digest: z.string().regex(/^sha256:[a-f0-9]{64}$/).optional(),
}).strict();
export const sdkVerificationReportSchema = z.object({
    outcome: sdkVerificationOutcomeSchema,
    summary: z.string().min(1).max(1000),
    evidence: z.array(sdkVerificationEvidenceSchema).max(100),
    protectedStatePreserved: z.boolean().nullable(),
}).strict().superRefine((report, context) => {
    if (report.outcome === "not_performed") {
        if (report.evidence.length !== 0 || report.protectedStatePreserved !== null) {
            context.addIssue({ code: "custom", path: ["outcome"], message: "Not-performed verification cannot claim evidence or protected-state proof" });
        }
        return;
    }
    if (report.evidence.length === 0) {
        context.addIssue({ code: "custom", path: ["evidence"], message: "Performed verification requires evidence" });
    }
    if (new Set(report.evidence.map((item) => item.evidenceId)).size !== report.evidence.length) {
        context.addIssue({ code: "custom", path: ["evidence"], message: "Verification evidence IDs must be unique" });
    }
    if (report.outcome === "passed" && report.protectedStatePreserved === false) {
        context.addIssue({ code: "custom", path: ["protectedStatePreserved"], message: "Passed verification cannot report changed protected state" });
    }
});
export const sdkOperationStatusSchema = z.enum([
    "queued",
    "running",
    "waiting",
    "cancellation_requested",
    "succeeded",
    "failed",
    "cancelled",
    "partially_applied",
    "verification_failed",
    "recovery_failed",
]);
export const sdkOperationProgressSchema = z.object({
    phase: z.string().min(1).max(100),
    overallFraction: z.number().min(0).max(1).optional(),
    phaseFraction: z.number().min(0).max(1).optional(),
    completedUnits: z.number().int().nonnegative().optional(),
    totalUnits: z.number().int().positive().optional(),
    message: z.string().min(1).max(500).optional(),
}).strict().superRefine((progress, context) => {
    if ((progress.completedUnits === undefined) !== (progress.totalUnits === undefined)) {
        context.addIssue({ code: "custom", path: ["completedUnits"], message: "Completed and total units must be reported together" });
    }
    if (progress.completedUnits !== undefined && progress.totalUnits !== undefined && progress.completedUnits > progress.totalUnits) {
        context.addIssue({ code: "custom", path: ["completedUnits"], message: "Completed units cannot exceed total units" });
    }
});
export const sdkOperationCancellationRequestedSchema = z.object({
    state: z.literal("requested"),
    requestedAt: sdkPublicTimestampSchema,
}).strict();
export const sdkOperationCancellationConfirmedSchema = z.object({
    state: z.literal("confirmed"),
    requestedAt: sdkPublicTimestampSchema,
    confirmedAt: sdkPublicTimestampSchema,
}).strict().refine((value) => Date.parse(value.confirmedAt) >= Date.parse(value.requestedAt), {
    path: ["confirmedAt"], message: "Cancellation confirmation cannot precede its request",
});
export const sdkOperationCancellationRejectedSchema = z.object({
    state: z.literal("rejected"),
    requestedAt: sdkPublicTimestampSchema,
    resolvedAt: sdkPublicTimestampSchema,
    reason: z.string().min(1).max(500),
}).strict().refine((value) => Date.parse(value.resolvedAt) >= Date.parse(value.requestedAt), {
    path: ["resolvedAt"], message: "Cancellation resolution cannot precede its request",
});
const sdkOperationFailedRecoverySchema = z.object({
    state: z.literal("failed"),
    summary: z.string().min(1).max(1000),
    evidence: z.array(sdkVerificationEvidenceSchema).max(100),
    manualRecoveryRequired: z.literal(true),
}).strict();
export const sdkOperationRecoverySchema = z.discriminatedUnion("state", [
    z.object({ state: z.literal("not_attempted"), summary: z.string().min(1).max(1000), manualRecoveryRequired: z.boolean() }).strict(),
    z.object({ state: z.literal("restored"), summary: z.string().min(1).max(1000), evidence: z.array(sdkVerificationEvidenceSchema).min(1).max(100), manualRecoveryRequired: z.literal(false) }).strict(),
    z.object({ state: z.literal("compensated"), summary: z.string().min(1).max(1000), evidence: z.array(sdkVerificationEvidenceSchema).min(1).max(100) }).strict(),
    sdkOperationFailedRecoverySchema,
    z.object({ state: z.literal("manual_required"), summary: z.string().min(1).max(1000), evidence: z.array(sdkVerificationEvidenceSchema).max(100), manualRecoveryRequired: z.literal(true) }).strict(),
]);
const sdkOperationBaseSchema = z.object({
    operationId: sdkOperationIdSchema,
    requestId: sdkRequestIdSchema,
    executionId: sdkExecutionIdSchema,
    actionId: sdkPublicActionIdSchema,
    actionContractVersion: z.literal(CUTAGENT_SDK_ACTION_CONTRACT_VERSION),
    sequence: z.number().int().safe().positive(),
    createdAt: sdkPublicTimestampSchema,
    updatedAt: sdkPublicTimestampSchema,
    possibleMutation: sdkPossibleMutationStateSchema,
    usage: sdkUsageStateSchema,
    idempotency: z.object({
        key: sdkIdempotencyKeySchema,
        tombstoneExpiresAt: sdkPublicTimestampSchema,
    }).strict().optional(),
}).strict();
const sdkTerminalOperationBaseSchema = sdkOperationBaseSchema.extend({
    retentionExpiresAt: sdkPublicTimestampSchema,
}).strict();
const sdkTerminalFailureSchema = sdkPublicFailureSchema.refine((failure) => (failure.requestId !== undefined
    && failure.operationId !== undefined
    && failure.executionId !== undefined), { message: "Terminal operation failures require request, operation, and execution correlation" });
const mediaResultContractExclusions = new Set([
    "cutagent.action.media.append.batch",
    "cutagent.action.media.third_party_metadata.bulk_set",
]);
const mediaActionIds = CUTAGENT_SDK_PUBLIC_ACTION_IDS.filter((actionId) => (actionId.startsWith("cutagent.action.media.") && !mediaResultContractExclusions.has(actionId)));
if (mediaActionIds.length !== 53)
    throw new Error("Media action result registry must contain exactly 53 actions");
const mediaActionIdSchema = z.enum(mediaActionIds);
const mediaAbsolutePathPattern = /^(?:\/|~(?:\/|$)|[A-Za-z]:[\\/]|\\\\|file:)/i;
const mediaRelativePathPattern = /(?:^|[\\/])\.\.?([\\/]|$)/;
const mediaEmbeddedDrivePattern = /(?:^|\/)[A-Za-z]:\//;
const isSafeMediaUserText = (value, allowLogicalPath = false) => (value === value.trim()
    && !mediaAbsolutePathPattern.test(value)
    && !mediaRelativePathPattern.test(value)
    && !mediaEmbeddedDrivePattern.test(value)
    && (allowLogicalPath ? (!value.includes("\\") && !value.includes(":")) : (!value.includes("/") && !value.includes("\\"))));
const mediaSafeUserTextSchema = (maximum, allowLogicalPath = false) => z.string().min(1).max(maximum)
    .refine((value) => isSafeMediaUserText(value, allowLogicalPath), "Media result text cannot expose filesystem paths");
// Implementation-specific leak classification is enforced by the proprietary
// projector before transport. This public contract stays positive and generic.
const mediaSafeIdentifierSchema = (maximum) => mediaSafeUserTextSchema(maximum);
const mediaIdentitySchema = z.object({
    kind: z.enum(["media_asset", "media_folder", "timeline", "marker", "matte", "artifact"]),
    id: mediaSafeIdentifierSchema(160).regex(/^(?:media_pool_item|media_pool_folder|timeline|marker|artifact)_[a-z0-9][a-z0-9.-]*$/).nullable(),
    addressability: z.enum(["addressable", "not_addressable"]),
    name: mediaSafeUserTextSchema(256).nullable(),
    folderName: mediaSafeUserTextSchema(512, true).nullable(),
}).strict().superRefine((identity, context) => {
    const prefixes = {
        media_asset: "media_pool_item_", media_folder: "media_pool_folder_", timeline: "timeline_",
        marker: "marker_", matte: "artifact_", artifact: "artifact_",
    };
    if (identity.id !== null && !identity.id.startsWith(prefixes[identity.kind])) {
        context.addIssue({ code: "custom", path: ["id"], message: "Media identity ID prefix must match its kind" });
    }
    if ((identity.id === null) !== (identity.addressability === "not_addressable")) {
        context.addIssue({ code: "custom", path: ["addressability"], message: "Media identity addressability must match opaque ID availability" });
    }
    if (identity.id === null && (identity.name === null || identity.folderName === null)) {
        context.addIssue({ code: "custom", message: "Media identity requires an opaque ID or an exact scoped name" });
    }
});
const mediaIdentityOfKind = (kind) => (mediaIdentitySchema.refine((identity) => identity.kind === kind, { path: ["kind"], message: `Expected ${kind} identity` }));
const mediaKeyValueSchema = z.object({
    key: mediaSafeUserTextSchema(128).regex(/^[A-Za-z][A-Za-z0-9 ._\[\]-]{0,127}$/),
    value: z.union([
        mediaSafeUserTextSchema(1024),
        z.number().safe(), z.boolean(), z.null(),
    ]),
}).strict();
const mediaDeclaredApplicabilitySchema = z.object({
    overall: z.literal("unknown"),
    operatingSystem: z.object({ macos: z.literal("unknown"), windows: z.literal("unknown") }).strict(),
    architecture: z.object({ arm64: z.literal("unknown"), x86_64: z.literal("unknown") }).strict(),
    edition: z.object({ free: z.literal("declared_unverified"), studio: z.literal("declared_unverified") }).strict(),
    transport: z.object({ embeddedFree: z.literal("declared_unverified"), studioExternal: z.literal("declared_unverified") }).strict(),
}).strict();
const mediaUnknownApplicabilitySchema = z.object({
    overall: z.literal("unknown"),
    operatingSystem: z.object({ macos: z.literal("unknown"), windows: z.literal("unknown") }).strict(),
    architecture: z.object({ arm64: z.literal("unknown"), x86_64: z.literal("unknown") }).strict(),
    edition: z.object({ free: z.literal("unknown"), studio: z.literal("unknown") }).strict(),
    transport: z.object({ embeddedFree: z.literal("unknown"), studioExternal: z.literal("unknown") }).strict(),
}).strict();
const mediaUnknownApplicabilityActionIds = new Set([
    "cutagent.action.media.info",
    "cutagent.action.media.clear_transcription",
    "cutagent.action.media.transcribe",
]);
const mediaApplicabilitySchema = z.union([mediaDeclaredApplicabilitySchema, mediaUnknownApplicabilitySchema]);
const mediaVerificationSchema = z.object({
    outcome: z.enum(["passed", "partial", "manual_review_required"]),
    evidence: z.array(z.object({
        kind: z.enum(["command_read", "structural_readback", "manual_review"]),
        summary: mediaSafeIdentifierSchema(500),
    }).strict()).min(1).max(32),
    protectedState: z.enum(["preserved", "not_applicable", "not_proven", "partial"]),
}).strict();
const mediaReadPayload = (data) => z.object({
    status: z.literal("completed"), data, verification: mediaVerificationSchema,
}).strict().superRefine((payload, context) => {
    if (payload.verification.outcome !== "passed" || payload.verification.protectedState !== "not_applicable") {
        context.addIssue({ code: "custom", path: ["verification"], message: "Media reads require passed non-mutating verification" });
    }
});
const mediaMutationPayload = (data) => z.object({
    status: z.enum(["completed", "no_op", "partial", "manual_review_required"]),
    changed: z.boolean(), data, verification: mediaVerificationSchema,
}).strict().superRefine((payload, context) => {
    if (["completed", "no_op"].includes(payload.status) && payload.verification.outcome !== "passed") {
        context.addIssue({ code: "custom", path: ["verification", "outcome"], message: "Verified media terminal requires passed readback" });
    }
    if (payload.status === "partial" && payload.verification.outcome !== "partial") {
        context.addIssue({ code: "custom", path: ["verification", "outcome"], message: "Partial media terminal requires partial verification" });
    }
    const expected = {
        completed: { changed: true, protectedState: "preserved" },
        no_op: { changed: false, protectedState: "preserved" },
        partial: { changed: true, protectedState: "not_proven" },
        manual_review_required: { changed: false, protectedState: "not_proven" },
    };
    const contract = expected[payload.status];
    if (payload.changed !== contract.changed) {
        context.addIssue({ code: "custom", path: ["changed"], message: "Media mutation status and changed flag contradict" });
    }
    if (payload.verification.protectedState !== contract.protectedState) {
        context.addIssue({ code: "custom", path: ["verification", "protectedState"], message: "Media mutation status and protected-state proof contradict" });
    }
    if (payload.status === "manual_review_required" && payload.verification.outcome !== "manual_review_required") {
        context.addIssue({ code: "custom", path: ["verification", "outcome"], message: "Manual-review media terminal requires manual-review verification" });
    }
});
const mediaOutcome = (value) => z.literal(value);
const mediaResultPayloadSchemas = new Map();
for (const actionId of ["cutagent.action.media.list", "cutagent.action.media.search", "cutagent.action.media.selected.list"]) {
    mediaResultPayloadSchemas.set(actionId, mediaReadPayload(z.object({
        outcome: mediaOutcome(actionId.slice("cutagent.action.media.".length)), scope: mediaIdentityOfKind("media_folder"),
        items: z.array(mediaIdentityOfKind("media_asset")).max(1024),
    }).strict()));
}
mediaResultPayloadSchemas.set("cutagent.action.media.folders.list", mediaReadPayload(z.object({
    outcome: mediaOutcome("folders.list"), scope: mediaIdentityOfKind("media_folder"),
    folders: z.array(mediaIdentityOfKind("media_folder")).max(1024),
}).strict()));
mediaResultPayloadSchemas.set("cutagent.action.media.folders.tree", mediaReadPayload(z.object({
    outcome: mediaOutcome("folders.tree"), root: mediaIdentityOfKind("media_folder"),
    folders: z.array(mediaIdentityOfKind("media_folder")).min(1).max(1024),
}).strict()));
mediaResultPayloadSchemas.set("cutagent.action.media.info", mediaReadPayload(z.object({
    outcome: mediaOutcome("info"), item: mediaIdentityOfKind("media_asset"), properties: z.array(mediaKeyValueSchema).max(512),
}).strict()));
mediaResultPayloadSchemas.set("cutagent.action.media.audio_mapping", mediaReadPayload(z.object({
    outcome: mediaOutcome("audio_mapping"), item: mediaIdentityOfKind("media_asset"), mapping: z.array(mediaKeyValueSchema).max(256),
}).strict()));
mediaResultPayloadSchemas.set("cutagent.action.media.mark.get", mediaReadPayload(z.object({
    outcome: mediaOutcome("mark.get"), item: mediaIdentityOfKind("media_asset"),
    marks: z.array(z.object({ kind: mediaSafeUserTextSchema(64), inFrame: z.number().int().safe().nullable(), outFrame: z.number().int().safe().nullable() }).strict()).max(32),
}).strict()));
mediaResultPayloadSchemas.set("cutagent.action.media.marker.list", mediaReadPayload(z.object({
    outcome: mediaOutcome("marker.list"), item: mediaIdentityOfKind("media_asset"),
    markers: z.array(z.object({ frame: z.number().int().safe(), color: mediaSafeUserTextSchema(64).nullable(), name: mediaSafeUserTextSchema(512).nullable(), note: mediaSafeUserTextSchema(512).nullable(), durationFrames: z.number().int().safe().nonnegative().nullable() }).strict()).max(1024),
}).strict()));
mediaResultPayloadSchemas.set("cutagent.action.media.matte.list", mediaReadPayload(z.object({
    outcome: mediaOutcome("matte.list"), item: mediaIdentityOfKind("media_asset"), matteCount: z.number().int().nonnegative(),
}).strict()));
mediaResultPayloadSchemas.set("cutagent.action.media.third_party_metadata.get", mediaReadPayload(z.object({
    outcome: mediaOutcome("third_party_metadata.get"), item: mediaIdentityOfKind("media_asset"), metadata: z.array(mediaKeyValueSchema).max(512),
}).strict()));
mediaResultPayloadSchemas.set("cutagent.action.media.timeline_matte.list", mediaReadPayload(z.object({
    outcome: mediaOutcome("timeline_matte.list"), folder: mediaIdentityOfKind("media_folder"), matteCount: z.number().int().nonnegative(),
}).strict()));
mediaResultPayloadSchemas.set("cutagent.action.media.import", mediaMutationPayload(z.object({
    outcome: mediaOutcome("import"), importedItems: z.array(mediaIdentityOfKind("media_asset")).max(1024),
}).strict()));
mediaResultPayloadSchemas.set("cutagent.action.media.create_timeline", mediaMutationPayload(z.object({
    outcome: mediaOutcome("create_timeline"), targetIds: z.array(mediaSafeIdentifierSchema(256)).max(1024),
}).strict()));
for (const actionId of [
    "cutagent.action.media.folders.open",
    "cutagent.action.media.folders.root",
    "cutagent.action.media.proxy",
]) {
    mediaResultPayloadSchemas.set(actionId, mediaMutationPayload(z.object({
        outcome: mediaOutcome(actionId.slice("cutagent.action.media.".length)),
        targetIds: z.array(mediaSafeIdentifierSchema(256)).max(1024),
    }).strict()));
}
for (const actionId of ["cutagent.action.media.folders.create", "cutagent.action.media.folders.delete"]) {
    mediaResultPayloadSchemas.set(actionId, mediaMutationPayload(z.object({
        outcome: mediaOutcome(actionId.slice("cutagent.action.media.".length)), folder: mediaIdentityOfKind("media_folder"),
    }).strict()));
}
for (const actionId of ["cutagent.action.media.metadata", "cutagent.action.media.property_set", "cutagent.action.media.third_party_metadata.set"]) {
    mediaResultPayloadSchemas.set(actionId, mediaMutationPayload(z.object({
        outcome: mediaOutcome(actionId.slice("cutagent.action.media.".length)), item: mediaIdentityOfKind("media_asset"),
        metadata: z.array(mediaKeyValueSchema).max(512),
    }).strict()));
}
const unsupportedMediaPayloadSchema = z.object({
    status: z.literal("unsupported"), reason: z.literal("action_not_available"),
    message: z.literal("This action is not available through the public SDK."),
}).strict();
const unsupportedMediaActionIds = new Set(mediaActionIds.filter((actionId) => !mediaResultPayloadSchemas.has(actionId)));
for (const actionId of mediaActionIds) {
    if (!mediaResultPayloadSchemas.has(actionId))
        mediaResultPayloadSchemas.set(actionId, unsupportedMediaPayloadSchema);
}
export const sdkMediaActionResultValueSchema = z.object({
    actionId: mediaActionIdSchema,
    applicability: mediaApplicabilitySchema,
    payload: z.unknown(),
}).strict().superRefine((result, context) => {
    const schema = mediaResultPayloadSchemas.get(result.actionId);
    if (!schema) {
        context.addIssue({ code: "custom", path: ["actionId"], message: "Unknown media result action" });
        return;
    }
    const parsed = schema.safeParse(result.payload);
    if (!parsed.success) {
        for (const issue of parsed.error.issues)
            context.addIssue({ ...issue, path: ["payload", ...issue.path] });
    }
    const expectedApplicability = mediaUnknownApplicabilityActionIds.has(result.actionId)
        ? mediaUnknownApplicabilitySchema
        : mediaDeclaredApplicabilitySchema;
    const applicability = expectedApplicability.safeParse(result.applicability);
    if (!applicability.success) {
        for (const issue of applicability.error.issues)
            context.addIssue({ ...issue, path: ["applicability", ...issue.path] });
    }
});
/** Bounded result for the explicit typed long-tail carrier. It contains no lowering metadata. */
export const sdkLowLevelRawResultSchema = z.object({
    actionId: sdkLowLevelReadActionIdSchema,
    operationClass: z.literal("read"),
    data: z.unknown(),
    sanitized: z.literal(true),
}).strict();
export const sdkPublicActionResultSchema = z.object({
    actionId: sdkPublicActionIdSchema,
    actionContractVersion: z.literal(CUTAGENT_SDK_ACTION_CONTRACT_VERSION),
    value: z.json().refine((value) => utf8Encoder.encode(JSON.stringify(value)).byteLength
        <= CUTAGENT_SDK_PUBLIC_ACTION_RESULT_MAX_BYTES, { message: "Serialized public action result exceeds the 12 MiB carrier budget" }),
}).strict().superRefine((result, context) => {
    const lowLevel = sdkLowLevelRawResultSchema.safeParse(result.value);
    if (lowLevel.success) {
        if (lowLevel.data.actionId !== result.actionId) {
            context.addIssue({ code: "custom", path: ["value", "actionId"], message: "Low-level result action correlation must match" });
        }
        return;
    }
    if (mediaResultContractExclusions.has(result.actionId)) {
        context.addIssue({ code: "custom", path: ["actionId"], message: "This batch alias has no public semantic result surface" });
        return;
    }
    if (result.actionId === "cutagent.action.sdk.fairlight.plan.apply") {
        const parsed = sdkFairlightSemanticResultSchema.safeParse(result.value);
        if (!parsed.success) {
            for (const issue of parsed.error.issues) {
                context.addIssue({ ...issue, path: ["value", ...issue.path] });
            }
        }
        return;
    }
    if (!result.actionId.startsWith("cutagent.action.media."))
        return;
    const semanticMediaResultSchemas = {
        "cutagent.action.media.folders.create": sdkMediaPoolCreateBinResultSchema,
        "cutagent.action.media.import": sdkMediaPoolImportResultSchema,
        "cutagent.action.media.relink": sdkMediaPoolRelinkResultSchema,
        "cutagent.action.media.metadata": sdkMediaPoolSetMetadataResultSchema,
        "cutagent.action.media.sync_audio": sdkMediaPoolSyncAudioResultSchema,
    };
    const semanticMediaResultSchema = semanticMediaResultSchemas[result.actionId];
    if (semanticMediaResultSchema?.safeParse(result.value).success)
        return;
    const parsed = sdkMediaActionResultValueSchema.safeParse(result.value);
    if (!parsed.success) {
        for (const issue of parsed.error.issues) {
            context.addIssue({ ...issue, path: ["value", ...issue.path] });
        }
        return;
    }
    if (parsed.data.actionId !== result.actionId) {
        context.addIssue({ code: "custom", path: ["value", "actionId"], message: "Media result action correlation must match" });
    }
});
export const CUTAGENT_SDK_OPERATION_RESULT_PAGE_MAX_ITEMS = 256;
export const CUTAGENT_SDK_OPERATION_RESULT_PAGE_MAX_BYTES = 2 * 1024 * 1024;
export const sdkOperationResultCollectionIdSchema = z.string()
    .min(1)
    .max(160)
    .regex(/^[A-Za-z][A-Za-z0-9_.-]*$/);
export const sdkOperationResultCollectionDigestSchema = z.string().regex(/^sha256:[a-f0-9]{64}$/);
export const sdkOperationResultCollectionReferenceSchema = z.object({
    collectionId: sdkOperationResultCollectionIdSchema,
    kind: z.enum(["identity_map", "array"]),
    totalItems: z.number().int().min(0).max(10_000),
    digest: sdkOperationResultCollectionDigestSchema,
    defaultPageSize: z.number().int().min(1).max(CUTAGENT_SDK_OPERATION_RESULT_PAGE_MAX_ITEMS),
}).strict();
const sdkOperationIdentityMapResultPageSchema = z.object({
    operationId: sdkOperationIdSchema,
    actionId: sdkPublicActionIdSchema,
    actionContractVersion: z.literal(CUTAGENT_SDK_ACTION_CONTRACT_VERSION),
    collectionId: sdkOperationResultCollectionIdSchema,
    kind: z.literal("identity_map"),
    digest: sdkOperationResultCollectionDigestSchema,
    totalItems: z.number().int().min(0).max(10_000),
    offset: z.number().int().min(0).max(10_000),
    entries: z.array(z.object({
        key: z.string().min(1).max(160),
        value: z.json(),
    }).strict()).max(CUTAGENT_SDK_OPERATION_RESULT_PAGE_MAX_ITEMS),
    nextOffset: z.number().int().min(1).max(10_000).nullable(),
    retentionExpiresAt: sdkPublicTimestampSchema,
}).strict();
const sdkOperationArrayResultPageSchema = sdkOperationIdentityMapResultPageSchema.omit({ entries: true, kind: true }).extend({
    kind: z.literal("array"),
    entries: z.array(z.object({
        index: z.number().int().min(0).max(9_999),
        value: z.json(),
    }).strict()).max(CUTAGENT_SDK_OPERATION_RESULT_PAGE_MAX_ITEMS),
}).strict();
export const sdkOperationResultPageSchema = z.discriminatedUnion("kind", [
    sdkOperationIdentityMapResultPageSchema,
    sdkOperationArrayResultPageSchema,
]).superRefine((page, context) => {
    if (page.offset > page.totalItems || page.entries.length > page.totalItems - page.offset) {
        context.addIssue({ code: "custom", path: ["entries"], message: "Result page entries exceed collection bounds" });
    }
    const expectedNext = page.offset + page.entries.length < page.totalItems
        ? page.offset + page.entries.length
        : null;
    if (page.nextOffset !== expectedNext) {
        context.addIssue({ code: "custom", path: ["nextOffset"], message: "Result page continuation is contradictory" });
    }
    if (page.entries.some((entry, index) => (page.kind === "array" && "index" in entry ? entry.index !== page.offset + index : false))) {
        context.addIssue({ code: "custom", path: ["entries"], message: "Array result page indexes must be contiguous" });
    }
    if (utf8Encoder.encode(JSON.stringify(page)).byteLength > CUTAGENT_SDK_OPERATION_RESULT_PAGE_MAX_BYTES) {
        context.addIssue({ code: "custom", message: "Serialized operation result page exceeds the 2 MiB carrier budget" });
    }
});
const queued = sdkOperationBaseSchema.extend({ status: z.literal("queued") }).strict();
const running = sdkOperationBaseSchema.extend({
    status: z.literal("running"),
    progress: sdkOperationProgressSchema,
    cancellation: sdkOperationCancellationRejectedSchema.optional(),
}).strict();
const waiting = sdkOperationBaseSchema.extend({
    status: z.literal("waiting"),
    progress: sdkOperationProgressSchema,
    waitingFor: z.enum(["runtime", "external_service", "user", "resource"]),
    cancellation: sdkOperationCancellationRejectedSchema.optional(),
}).strict();
const cancellationRequested = sdkOperationBaseSchema.extend({
    status: z.literal("cancellation_requested"),
    cancellation: sdkOperationCancellationRequestedSchema,
    progress: sdkOperationProgressSchema.optional(),
}).strict();
const succeeded = sdkTerminalOperationBaseSchema.extend({
    status: z.literal("succeeded"),
    result: sdkPublicActionResultSchema,
    verification: sdkVerificationReportSchema,
    cancellation: sdkOperationCancellationRejectedSchema.optional(),
}).strict();
const failed = sdkTerminalOperationBaseSchema.extend({
    status: z.literal("failed"),
    result: sdkPublicActionResultSchema.optional(),
    failure: sdkTerminalFailureSchema,
    recovery: sdkOperationRecoverySchema.optional(),
    cancellation: sdkOperationCancellationRejectedSchema.optional(),
}).strict();
const cancelled = sdkTerminalOperationBaseSchema.extend({
    status: z.literal("cancelled"),
    failure: sdkTerminalFailureSchema,
    cancellation: sdkOperationCancellationConfirmedSchema,
    verification: sdkVerificationReportSchema.optional(),
    recovery: sdkOperationRecoverySchema.optional(),
}).strict();
const partiallyApplied = sdkTerminalOperationBaseSchema.extend({
    status: z.literal("partially_applied"),
    possibleMutation: z.literal("partial"),
    failure: sdkTerminalFailureSchema,
    result: sdkPublicActionResultSchema.optional(),
    verification: sdkVerificationReportSchema.optional(),
    recovery: sdkOperationRecoverySchema,
    cancellation: sdkOperationCancellationRejectedSchema.optional(),
}).strict();
const verificationFailed = sdkTerminalOperationBaseSchema.extend({
    status: z.literal("verification_failed"),
    failure: sdkTerminalFailureSchema,
    result: sdkPublicActionResultSchema.optional(),
    verification: sdkVerificationReportSchema,
    recovery: sdkOperationRecoverySchema.optional(),
    cancellation: sdkOperationCancellationRejectedSchema.optional(),
}).strict();
const recoveryFailed = sdkTerminalOperationBaseSchema.extend({
    status: z.literal("recovery_failed"),
    failure: sdkTerminalFailureSchema,
    result: sdkPublicActionResultSchema.optional(),
    recovery: sdkOperationFailedRecoverySchema,
    verification: sdkVerificationReportSchema.optional(),
    cancellation: sdkOperationCancellationRejectedSchema.optional(),
}).strict();
export const sdkOperationSnapshotSchema = z.discriminatedUnion("status", [
    queued,
    running,
    waiting,
    cancellationRequested,
    succeeded,
    failed,
    cancelled,
    partiallyApplied,
    verificationFailed,
    recoveryFailed,
]).superRefine((operation, context) => {
    if (Date.parse(operation.updatedAt) < Date.parse(operation.createdAt)) {
        context.addIssue({ code: "custom", path: ["updatedAt"], message: "Operation update cannot precede creation" });
    }
    if ("retentionExpiresAt" in operation && Date.parse(operation.retentionExpiresAt) <= Date.parse(operation.updatedAt)) {
        context.addIssue({ code: "custom", path: ["retentionExpiresAt"], message: "Operation retention must outlive its final update" });
    }
    if (operation.idempotency && Date.parse(operation.idempotency.tombstoneExpiresAt) <= Date.parse(operation.createdAt)) {
        context.addIssue({ code: "custom", path: ["idempotency", "tombstoneExpiresAt"], message: "Idempotency horizon must outlive operation creation" });
    }
    if (operation.status === "queued" && operation.possibleMutation !== "none") {
        context.addIssue({ code: "custom", path: ["possibleMutation"], message: "Queued work cannot claim a possible mutation" });
    }
    const terminalResult = "result" in operation ? operation.result : undefined;
    if (terminalResult !== undefined) {
        if (terminalResult.actionId !== operation.actionId || terminalResult.actionContractVersion !== operation.actionContractVersion) {
            context.addIssue({ code: "custom", path: ["result"], message: "Result action identity must match the operation" });
        }
    }
    if (terminalResult !== undefined && operation.actionId === "cutagent.action.sdk.fairlight.plan.apply") {
        const value = terminalResult?.value;
        const parsedValue = sdkFairlightSemanticResultSchema.safeParse(value);
        if (!parsedValue.success) {
            context.addIssue({ code: "custom", path: ["result"], message: "Fairlight terminal work requires its exact typed semantic result" });
            return;
        }
        if (operation.status !== "succeeded" && operation.status !== "partially_applied") {
            context.addIssue({
                code: "custom",
                path: ["result"],
                message: "A typed Fairlight result is allowed only on its correlated succeeded or partially-applied terminal branch",
            });
            return;
        }
        const fairlightResult = parsedValue.data;
        const innerOutcome = fairlightResult.outcome;
        const expectedProtectedState = fairlightResult.evidence.protectedState.status === "passed"
            ? true
            : fairlightResult.evidence.protectedState.status === "failed" ? false : null;
        if (operation.status === "succeeded") {
            const expectedMutation = innerOutcome === "succeeded" ? "confirmed" : innerOutcome === "no_change" ? "none" : null;
            if (expectedMutation === null || operation.possibleMutation !== expectedMutation || operation.verification.outcome !== "passed"
                || operation.verification.protectedStatePreserved !== expectedProtectedState) {
                context.addIssue({ code: "custom", path: ["result"], message: "Succeeded Fairlight outer status must match its inner outcome, mutation, and verification truth" });
            }
        }
        else {
            const innerRecovery = fairlightResult.recovery;
            const recoveryMatches = operation.recovery.summary === innerRecovery.guidance
                && ((innerRecovery.state === "readback_required" && operation.recovery.state === "not_attempted" && operation.recovery.manualRecoveryRequired === false)
                    || (innerRecovery.state === "manual_recovery_required"
                        && (operation.recovery.state === "manual_required" || operation.recovery.state === "failed")
                        && operation.recovery.manualRecoveryRequired === true));
            const expectedRecoveryActions = innerRecovery.state === "readback_required"
                ? ["inspect_state"]
                : ["inspect_state", "manual_recovery"];
            const failureRecoveryMatches = JSON.stringify(operation.failure.recovery) === JSON.stringify(expectedRecoveryActions)
                && JSON.stringify(operation.failure.recoveryGuidance) === JSON.stringify([innerRecovery.guidance]);
            if (innerOutcome !== "partial" || !operation.verification
                || operation.verification.outcome !== fairlightResult.evidence.outcome
                || operation.verification.protectedStatePreserved !== expectedProtectedState || !recoveryMatches || !failureRecoveryMatches) {
                context.addIssue({ code: "custom", path: ["result"], message: "Partially-applied Fairlight outer status must match its inner evidence and recovery truth" });
            }
        }
    }
    if (operation.status === "succeeded") {
        if (!["passed", "not_performed"].includes(operation.verification.outcome)) {
            context.addIssue({ code: "custom", path: ["verification"], message: "Succeeded operation has a contradictory verification outcome" });
        }
        if (operation.possibleMutation === "confirmed" && operation.verification.outcome !== "passed") {
            context.addIssue({ code: "custom", path: ["verification"], message: "Confirmed mutation success requires passed verification" });
        }
        if (!(operation.possibleMutation === "none" || operation.possibleMutation === "confirmed")) {
            context.addIssue({ code: "custom", path: ["possibleMutation"], message: "Succeeded work must truthfully prove either no mutation or a confirmed mutation" });
        }
    }
    if ("result" in operation && operation.result) {
        if (operation.result.actionId !== operation.actionId || operation.result.actionContractVersion !== operation.actionContractVersion) {
            context.addIssue({ code: "custom", path: ["result"], message: "Result action identity must match the operation" });
        }
        if (mediaActionIds.includes(operation.actionId)) {
            const parsed = sdkMediaActionResultValueSchema.safeParse(operation.result.value);
            if (parsed.success) {
                const payload = parsed.data.payload;
                const expectedTerminal = {
                    completed: "succeeded", no_op: "succeeded", partial: "partially_applied",
                    manual_review_required: "verification_failed", unsupported: "failed",
                };
                if (operation.status !== expectedTerminal[payload.status]) {
                    context.addIssue({ code: "custom", path: ["status"], message: "Operation terminal contradicts the media result status" });
                }
                if (payload.status === "completed") {
                    const expectedMutation = payload.changed === true ? "confirmed" : "none";
                    if (operation.possibleMutation !== expectedMutation) {
                        context.addIssue({ code: "custom", path: ["possibleMutation"], message: "Completed media result contradicts the outer mutation state" });
                    }
                }
                if (payload.status === "no_op" && operation.possibleMutation !== "none") {
                    context.addIssue({ code: "custom", path: ["possibleMutation"], message: "No-op media mutation requires no mutation state" });
                }
                if ((payload.status === "completed" || payload.status === "no_op")
                    && (!("verification" in operation) || operation.verification?.outcome !== "passed")) {
                    context.addIssue({ code: "custom", path: ["verification"], message: "Completed media result requires a passed outer verification" });
                }
                if (payload.status === "partial" && (!("verification" in operation) || operation.verification?.outcome !== "partial")) {
                    context.addIssue({ code: "custom", path: ["verification"], message: "Partial media result requires a partial outer verification" });
                }
                if (payload.status === "manual_review_required" && (!("verification" in operation) || operation.verification?.outcome !== "manual_review_required")) {
                    context.addIssue({ code: "custom", path: ["verification"], message: "Manual-review media result requires a matching outer verification" });
                }
                if (payload.status === "manual_review_required" && operation.possibleMutation !== "unknown") {
                    context.addIssue({ code: "custom", path: ["possibleMutation"], message: "Manual-review media result requires unknown mutation state" });
                }
                if (payload.status === "unsupported" && operation.possibleMutation !== "none") {
                    context.addIssue({ code: "custom", path: ["possibleMutation"], message: "Unsupported media action cannot claim a mutation" });
                }
                if ("verification" in operation && operation.verification && payload.verification) {
                    const expectedOuterProtectedState = {
                        preserved: true, not_applicable: null, partial: false, not_proven: null,
                    };
                    if (operation.verification.protectedStatePreserved !== expectedOuterProtectedState[payload.verification.protectedState]) {
                        context.addIssue({ code: "custom", path: ["verification", "protectedStatePreserved"], message: "Outer protected-state proof contradicts the media result" });
                    }
                }
            }
        }
    }
    if (mediaActionIds.includes(operation.actionId)) {
        // Post-dispatch readback can fail before a truthful semantic result exists.
        // Preserve that as a result-free verification terminal, never fabricated success.
        const needsSupportedResult = operation.status === "succeeded"
            || operation.status === "partially_applied";
        const needsUnsupportedResult = unsupportedMediaActionIds.has(operation.actionId)
            && operation.status === "failed"
            && !("failure" in operation && operation.failure);
        if ((needsSupportedResult || needsUnsupportedResult) && (!("result" in operation) || !operation.result)) {
            context.addIssue({ code: "custom", path: ["result"], message: "Media terminal requires its typed semantic result" });
        }
    }
    if ("cancellation" in operation && operation.cancellation) {
        if (Date.parse(operation.cancellation.requestedAt) > Date.parse(operation.updatedAt)) {
            context.addIssue({ code: "custom", path: ["cancellation", "requestedAt"], message: "Cancellation request cannot follow the operation update" });
        }
        const resolvedAt = operation.cancellation.state === "confirmed"
            ? operation.cancellation.confirmedAt
            : operation.cancellation.state === "rejected"
                ? operation.cancellation.resolvedAt
                : undefined;
        if (resolvedAt && Date.parse(resolvedAt) > Date.parse(operation.updatedAt)) {
            context.addIssue({ code: "custom", path: ["cancellation"], message: "Cancellation resolution cannot follow the operation update" });
        }
    }
    if (operation.status === "verification_failed" && !["failed", "partial", "manual_review_required"].includes(operation.verification.outcome)) {
        context.addIssue({ code: "custom", path: ["verification"], message: "Verification failure has a contradictory verification outcome" });
    }
    if ("failure" in operation) {
        if (operation.failure.requestId !== operation.requestId
            || operation.failure.operationId !== operation.operationId
            || operation.failure.executionId !== operation.executionId
            || operation.failure.possibleMutation !== operation.possibleMutation
            || operation.failure.usage !== operation.usage) {
            context.addIssue({ code: "custom", path: ["failure"], message: "Terminal failure correlation and truth must match the operation" });
        }
    }
    if (operation.status === "verification_failed" && operation.failure.code !== "VERIFICATION_FAILED") {
        context.addIssue({ code: "custom", path: ["failure", "code"], message: "Verification failure requires VERIFICATION_FAILED" });
    }
    if (operation.status === "failed" && (operation.possibleMutation === "partial" || operation.possibleMutation === "confirmed")) {
        context.addIssue({ code: "custom", path: ["possibleMutation"], message: "Applied work requires a dedicated partial or verification terminal outcome" });
    }
    if (operation.status === "failed"
        && !new Set([
            "OPERATION_FAILED",
            "CAPABILITY_UNAVAILABLE",
            "STALE_REVISION",
            "EDIT_CONSTRAINT_VIOLATION",
            "AUTHENTICATION_REQUIRED",
            "SUBSCRIPTION_REQUIRED",
            "USAGE_EXHAUSTED",
            "REQUEST_TOO_LARGE",
            "DEPENDENCY_UNAVAILABLE",
            "TEMPORARY_PROVIDER_FAILURE",
            "RUNTIME_UNAVAILABLE",
            "RUNTIME_TIMEOUT",
            "OUTPUT_LIMIT_REACHED",
            "INVALID_RESPONSE",
        ]).has(operation.failure.code)) {
        context.addIssue({ code: "custom", path: ["failure", "code"], message: "Failed operations require a pre-effect domain failure or OPERATION_FAILED" });
    }
    if (operation.status === "partially_applied" && operation.failure.code !== "OPERATION_FAILED") {
        context.addIssue({ code: "custom", path: ["failure", "code"], message: "Partially-applied failures require OPERATION_FAILED" });
    }
    if (operation.status === "recovery_failed" && operation.failure.code !== "RECOVERY_FAILED") {
        context.addIssue({ code: "custom", path: ["failure", "code"], message: "Recovery failure requires RECOVERY_FAILED" });
    }
    if (operation.status === "cancelled" && operation.failure.code !== "CANCELLED") {
        context.addIssue({ code: "custom", path: ["failure", "code"], message: "Cancelled operation requires CANCELLED" });
    }
});
export const sdkOperationEventSchema = z.object({
    operationId: sdkOperationIdSchema,
    sequence: z.number().int().safe().positive(),
    snapshot: sdkOperationSnapshotSchema,
}).strict().superRefine((event, context) => {
    if (event.operationId !== event.snapshot.operationId || event.sequence !== event.snapshot.sequence) {
        context.addIssue({ code: "custom", path: ["snapshot"], message: "Operation event correlation must match its snapshot" });
    }
});
const operationDeadlineSchema = z.number().int().safe().positive();
const operationControlBase = z.object({
    protocolVersion: z.literal(1),
    requestId: sdkRequestIdSchema,
    sessionId: sdkSessionIdSchema,
    deadlineAtMs: operationDeadlineSchema,
}).strict();
const markerValueSchema = z.object({
    recordFrame: z.number().int().safe().nonnegative(),
    color: z.string().min(1).max(64),
    name: z.string().max(4096),
    note: z.string().max(65_536),
    durationFrames: z.number().int().positive().max(2_147_483_647),
}).strict();
const markerMutationBase = z.object({
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    timelineRevision: sdkRevisionSchema,
}).strict();
export const sdkMarkerCreateInputSchema = markerMutationBase.extend({ marker: markerValueSchema }).strict();
export const sdkMarkerUpdateInputSchema = markerMutationBase.extend({ markerId: sdkMarkerIdSchema, marker: markerValueSchema }).strict();
export const sdkMarkerDeleteInputSchema = markerMutationBase.extend({ markerId: sdkMarkerIdSchema }).strict();
export const sdkMarkerMutationResultSchema = z.object({
    action: z.enum(["create", "update", "delete"]),
    marker: z.object({ id: sdkMarkerIdSchema, ...markerValueSchema.shape }).strict().nullable(),
    previousMarker: z.object({ id: sdkMarkerIdSchema, ...markerValueSchema.shape }).strict().nullable(),
    timelineRevision: sdkRevisionSchema,
}).strict();
const sdkVoiceModelSchema = z.enum(["multilingual_v2"]);
const sdkVoiceOutputFormatSchema = z.enum(["mp3_44khz_128kbps"]);
export const sdkVoiceGenerateInputSchema = z.object({
    text: z.string().min(1).max(10_000),
    voiceId: z.string().min(1).max(200),
    model: sdkVoiceModelSchema.default("multilingual_v2"),
    outputFormat: sdkVoiceOutputFormatSchema.default("mp3_44khz_128kbps"),
    stability: z.number().min(0).max(1).optional(),
    similarityBoost: z.number().min(0).max(1).optional(),
    style: z.number().min(0).max(1).optional(),
    useSpeakerBoost: z.boolean().optional(),
}).strict();
export const sdkGeneratedVoiceAssetSchema = z.object({
    id: sdkArtifactIdSchema,
    kind: z.literal("generated_voice"),
    fileName: z.string().min(1).max(255),
    contentType: z.literal("audio/mpeg"),
    sizeBytes: z.number().int().positive(),
    digest: z.string().regex(/^sha256:[a-f0-9]{64}$/),
    durationSeconds: z.number().positive().nullable(),
    model: sdkVoiceModelSchema,
    outputFormat: sdkVoiceOutputFormatSchema,
    createdAt: sdkPublicTimestampSchema,
}).strict();
export const sdkVoiceGenerateResultSchema = z.object({
    asset: sdkGeneratedVoiceAssetSchema,
    usage: z.object({
        state: z.literal("consumed"),
        characters: z.number().int().positive(),
        estimatedCostUsd: z.number().nonnegative().nullable(),
    }).strict(),
}).strict();
export const sdkVoicePlacementInputSchema = z.object({
    assetId: sdkArtifactIdSchema,
    assetDigest: z.string().regex(/^sha256:[a-f0-9]{64}$/),
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    timelineRevision: sdkRevisionSchema,
    trackIndex: z.number().int().positive(),
    recordFrame: z.number().int().safe().nonnegative(),
}).strict();
export const sdkVoicePlacementResultSchema = z.object({
    assetId: sdkArtifactIdSchema,
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    timelineRevision: sdkRevisionSchema,
    trackIndex: z.number().int().positive(),
    recordFrame: z.number().int().safe(),
    timelineItemId: z.string().min(1).nullable(),
    mediaPoolItemId: z.string().min(1).nullable(),
}).strict();
const timelineMoveItemSchema = z.object({
    snapshotId: sdkSnapshotTimelineItemIdSchema,
    id: sdkTimelineItemIdSchema,
    trackIndex: z.number().int().min(1).max(4096),
    recordStartFrame: z.number().int().safe().nonnegative(),
    recordEndFrame: z.number().int().safe().positive(),
    name: z.string().min(1).max(4096),
    mediaPoolItemId: sdkMediaPoolItemIdSchema.nullable(),
}).strict().refine((value) => value.recordEndFrame > value.recordStartFrame, {
    message: "Timeline move item end must follow its start.",
    path: ["recordEndFrame"],
});
const timelineMoveBindingSchema = z.object({
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    timelineRevision: sdkRevisionSchema,
}).strict();
export const sdkTimelineItemMoveInputSchema = timelineMoveBindingSchema.extend({
    target: timelineMoveItemSchema,
    linkedAudioTargets: z.array(timelineMoveItemSchema).max(256),
    destination: z.object({
        trackIndex: z.number().int().min(1).max(4096),
        recordStartFrame: z.number().int().safe().nonnegative(),
    }).strict(),
    linkedAudio: z.enum(["preserve", "exclude"]),
    collisionPolicy: z.enum(["reject", "allow"]),
}).strict();
const timelineMoveObservedItemSchema = z.object({
    id: sdkTimelineItemIdSchema,
    role: z.enum(["video", "linked_audio"]),
    name: z.string().min(1).max(4096),
    mediaPoolItemId: sdkMediaPoolItemIdSchema.nullable(),
    before: z.object({
        trackIndex: z.number().int().min(1).max(4096),
        recordStartFrame: z.number().int().safe().nonnegative(),
        recordEndFrame: z.number().int().safe().positive(),
    }).strict(),
    after: z.object({
        trackIndex: z.number().int().min(1).max(4096),
        recordStartFrame: z.number().int().safe().nonnegative(),
        recordEndFrame: z.number().int().safe().positive(),
    }).strict(),
    sourceRangePreservation: z.enum(["preserved", "not_observable"]),
}).strict();
export const sdkTimelineItemMoveResultSchema = z.object({
    actionId: z.literal("cutagent.action.timeline.items.move"),
    target: timelineMoveObservedItemSchema,
    linkedAudio: z.enum(["preserved", "excluded", "not_linked"]),
    movedItems: z.array(timelineMoveObservedItemSchema).min(1).max(257),
    timelineRevision: sdkRevisionSchema,
}).strict();
const sdkTimelineBladeTargetSchema = z.object({
    snapshotId: sdkSnapshotTimelineItemIdSchema,
    id: sdkTimelineItemIdSchema,
    trackType: z.enum(["video", "audio"]),
    trackIndex: z.number().int().min(1).max(4096),
    recordStartFrame: z.number().int().safe().nonnegative(),
    recordEndFrame: z.number().int().safe().positive(),
    name: z.string().min(1).max(4096),
    mediaPoolItemId: sdkMediaPoolItemIdSchema.nullable(),
}).strict().refine((value) => value.recordEndFrame > value.recordStartFrame, {
    message: "Blade target end must follow its start.",
    path: ["recordEndFrame"],
});
export const sdkTimelineBladeInputSchema = z.object({
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    timelineRevision: sdkRevisionSchema,
    target: sdkTimelineBladeTargetSchema,
    recordFrame: z.number().int().safe().nonnegative(),
    linkedMedia: z.literal("preserve"),
}).strict().refine((value) => (value.recordFrame > value.target.recordStartFrame
    && value.recordFrame < value.target.recordEndFrame), { message: "Blade position must be strictly inside the target item.", path: ["recordFrame"] });
const sdkTimelineBladeSegmentSchema = z.object({
    id: sdkTimelineItemIdSchema,
    originalId: sdkTimelineItemIdSchema,
    role: z.enum(["target", "linked"]),
    side: z.enum(["left", "right"]),
    trackType: z.enum(["video", "audio"]),
    trackIndex: z.number().int().min(1).max(4096),
    recordStartFrame: z.number().int().safe().nonnegative(),
    recordEndFrame: z.number().int().safe().positive(),
    sourceStartFrame: z.number().int().safe().nonnegative().nullable(),
    sourceEndFrame: z.number().int().safe().positive().nullable(),
    mediaPoolItemId: sdkMediaPoolItemIdSchema.nullable(),
}).strict().superRefine((segment, context) => {
    if (segment.recordEndFrame <= segment.recordStartFrame)
        context.addIssue({ code: "custom", path: ["recordEndFrame"], message: "Blade segment must be non-empty." });
    if ((segment.sourceStartFrame === null) !== (segment.sourceEndFrame === null))
        context.addIssue({ code: "custom", path: ["sourceStartFrame"], message: "Blade source range must be complete or unavailable." });
    if (segment.sourceStartFrame !== null && segment.sourceEndFrame !== null && segment.sourceEndFrame <= segment.sourceStartFrame)
        context.addIssue({ code: "custom", path: ["sourceEndFrame"], message: "Blade source segment must be non-empty." });
});
export const sdkTimelineBladeResultSchema = z.object({
    actionId: z.literal("cutagent.action.edit.blade"),
    timelineRevision: sdkRevisionSchema,
    splitFrame: z.number().int().safe().nonnegative(),
    segments: z.array(sdkTimelineBladeSegmentSchema).min(2).max(514),
    protectedStatePreserved: z.literal(true),
}).strict();
const sdkClipMotionTargetSchema = z.object({
    snapshotId: sdkSnapshotTimelineItemIdSchema,
    id: sdkTimelineItemIdSchema,
    trackType: z.literal("video"),
    trackIndex: z.number().int().min(1).max(4096),
    recordStartFrame: z.number().int().safe().nonnegative(),
    recordEndFrame: z.number().int().safe().positive(),
    name: z.string().min(1).max(4096),
    mediaPoolItemId: sdkMediaPoolItemIdSchema.nullable(),
    linkedItemIds: z.array(sdkTimelineItemIdSchema).max(64),
}).strict().refine((value) => value.recordEndFrame > value.recordStartFrame, {
    message: "Clip motion target end must follow its start.", path: ["recordEndFrame"],
});
const sdkClipMotionBindingSchema = z.object({
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    timelineRevision: sdkRevisionSchema,
    target: sdkClipMotionTargetSchema,
}).strict();
export const sdkClipKeyframePropertySchema = z.enum([
    "Pan", "Tilt", "ZoomX", "ZoomY", "Rotation", "Pitch", "Yaw",
    "Opacity", "CropLeft", "CropRight", "CropTop", "CropBottom",
]);
export const sdkClipKeyframeInterpolationSchema = z.enum(["linear", "bezier", "ease_in", "ease_out"]);
export const sdkClipKeyframeGetInputSchema = sdkClipMotionBindingSchema.extend({ property: z.union([sdkClipKeyframePropertySchema, z.literal("RetimeFrame")]) }).strict();
export const sdkClipKeyframeAddInputSchema = sdkClipKeyframeGetInputSchema.extend({
    property: sdkClipKeyframePropertySchema,
    recordFrame: z.number().int().safe().nonnegative(),
    value: z.number().finite().min(-1e12).max(1e12),
    interpolation: sdkClipKeyframeInterpolationSchema,
}).strict();
export const sdkClipKeyframeDeleteInputSchema = sdkClipKeyframeGetInputSchema.extend({
    property: sdkClipKeyframePropertySchema,
    recordFrame: z.number().int().safe().nonnegative(),
}).strict();
export const sdkClipKeyframeSetInterpolationInputSchema = sdkClipKeyframeDeleteInputSchema.extend({
    interpolation: sdkClipKeyframeInterpolationSchema,
}).strict();
export const sdkClipTransformValuesSchema = z.object({
    zoomX: z.number().finite().optional(), zoomY: z.number().finite().optional(),
    positionX: z.number().finite().optional(), positionY: z.number().finite().optional(),
    rotation: z.number().finite().optional(), anchorX: z.number().finite().optional(),
    anchorY: z.number().finite().optional(), pitch: z.number().finite().optional(), yaw: z.number().finite().optional(),
    flipX: z.boolean().optional(), flipY: z.boolean().optional(), opacity: z.number().finite().min(0).max(100).optional(),
    cropLeft: z.number().finite().optional(), cropRight: z.number().finite().optional(),
    cropTop: z.number().finite().optional(), cropBottom: z.number().finite().optional(), distortion: z.number().finite().optional(),
    dynamicZoomEase: z.enum(["linear", "in", "out", "inout"]).optional(),
}).strict().refine((value) => Object.keys(value).length > 0, { message: "At least one transform value is required." });
export const sdkClipTransformInputSchema = sdkClipMotionBindingSchema.extend({ transform: sdkClipTransformValuesSchema }).strict();
const sdkClipKeyframeResultBaseSchema = z.object({
    targetId: sdkTimelineItemIdSchema,
    timelineRevision: sdkRevisionSchema,
    protectedStatePreserved: z.literal(true),
    property: sdkClipKeyframePropertySchema,
    keyframes: z.array(z.object({
        property: sdkClipKeyframePropertySchema,
        recordFrame: z.number().int().safe().nonnegative(),
        value: z.number().finite(),
        interpolation: sdkClipKeyframeInterpolationSchema,
    }).strict()).max(4096),
}).strict();
const sdkExactRetimeSecondsSchema = z.object({
    unit: z.literal("seconds"), value: z.number().finite().min(-1e15).max(1e15),
}).strict();
const sdkExactRetimeHandleSchema = z.object({
    recordDelta: sdkExactRetimeSecondsSchema, sourceDelta: sdkExactRetimeSecondsSchema,
}).strict();
export const sdkExactRetimeCurveSchema = z.object({
    timelineItemId: sdkTimelineItemIdSchema,
    recordFrameRate: z.number().positive().max(1000000),
    sourceFrameRate: z.number().positive().max(1000000),
    recordStartFrame: z.number().int().safe().nonnegative(),
    sourceStartFrame: z.number().finite().nonnegative().max(Number.MAX_SAFE_INTEGER),
    kind: z.enum(["explicit_points", "identity"]),
    points: z.array(z.object({
        recordTime: sdkExactRetimeSecondsSchema, sourceTime: sdkExactRetimeSecondsSchema,
        incomingHandle: sdkExactRetimeHandleSchema, outgoingHandle: sdkExactRetimeHandleSchema,
        interpolationCode: z.number().int().min(0).max(2147483647),
    }).strict()).min(1).max(4096),
}).strict();
export const sdkClipKeyframeGetResultSchema = z.union([
    sdkClipKeyframeResultBaseSchema.extend({ actionId: z.literal("cutagent.action.clip.keyframe.get") }).strict(),
    sdkClipKeyframeResultBaseSchema.extend({
        actionId: z.literal("cutagent.action.clip.keyframe.get"), property: z.literal("RetimeFrame"),
        keyframes: z.array(z.never()).max(0), curve: sdkExactRetimeCurveSchema,
    }).strict(),
]);
export const sdkClipKeyframeAddResultSchema = sdkClipKeyframeResultBaseSchema.extend({ actionId: z.literal("cutagent.action.clip.keyframe.add") }).strict();
export const sdkClipKeyframeDeleteResultSchema = sdkClipKeyframeResultBaseSchema.extend({ actionId: z.literal("cutagent.action.clip.keyframe.delete") }).strict();
export const sdkClipKeyframeSetInterpolationResultSchema = sdkClipKeyframeResultBaseSchema.extend({ actionId: z.literal("cutagent.action.clip.keyframe.set_interpolation") }).strict();
const sdkClipTransformStateSchema = z.object({ values: sdkClipTransformValuesSchema }).strict();
export const sdkClipTransformResultSchema = z.object({
    actionId: z.literal("cutagent.action.clip.transform"), targetId: sdkTimelineItemIdSchema,
    timelineRevision: sdkRevisionSchema, protectedStatePreserved: z.literal(true),
    before: sdkClipTransformStateSchema, after: sdkClipTransformStateSchema,
}).strict();
const sdkRetimeFrameRangeSchema = (domain) => z.object({
    domain: z.literal(domain),
    unit: z.literal("frames"),
    start: z.number().int().safe().nonnegative(),
    endExclusive: z.number().int().safe().positive(),
}).strict().refine((value) => value.endExclusive > value.start, {
    message: "Retime ranges must be non-empty.",
    path: ["endExclusive"],
});
const sdkRetimeTargetSchema = (trackType) => z.object({
    snapshotId: sdkSnapshotTimelineItemIdSchema,
    id: sdkTimelineItemIdSchema,
    trackType: z.literal(trackType),
    trackIndex: z.number().int().min(1).max(4096),
    recordRange: sdkRetimeFrameRangeSchema("timeline_record_range"),
    sourceRange: sdkRetimeFrameRangeSchema("source_range"),
    name: z.string().min(1).max(4096),
    mediaPoolItemId: sdkMediaPoolItemIdSchema,
    linkedItemIds: z.array(sdkTimelineItemIdSchema).max(256),
}).strict();
const sdkRetimeProtectedNeighborSchema = z.object({
    id: sdkTimelineItemIdSchema,
    trackType: z.enum(["video", "audio", "subtitle"]),
    trackIndex: z.number().int().min(1).max(4096),
    recordRange: sdkRetimeFrameRangeSchema("timeline_record_range"),
    name: z.string().min(1).max(4096),
}).strict();
const sdkRetimeBindingShape = {
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    timelineRevision: sdkRevisionSchema,
};
const sdkSingleItemRetimeInputSchema = z.object({
    ...sdkRetimeBindingShape,
    target: sdkRetimeTargetSchema("video"),
    linkedAudioTargets: z.array(sdkRetimeTargetSchema("audio")).max(256),
    protectedNeighbors: z.array(sdkRetimeProtectedNeighborSchema).max(4096),
    linkedMedia: z.literal("preserve"),
}).strict().superRefine((value, context) => {
    const expected = new Set(value.target.linkedItemIds);
    const linked = new Set(value.linkedAudioTargets.map((target) => target.id));
    if (expected.size !== value.target.linkedItemIds.length || linked.size !== value.linkedAudioTargets.length
        || expected.size !== linked.size || [...expected].some((id) => !linked.has(id))) {
        context.addIssue({ code: "custom", path: ["linkedAudioTargets"], message: "Retime input must declare the complete linked-audio topology." });
    }
    for (const target of value.linkedAudioTargets) {
        if (!target.linkedItemIds.includes(value.target.id)
            || target.recordRange.start !== value.target.recordRange.start
            || target.recordRange.endExclusive !== value.target.recordRange.endExclusive) {
            context.addIssue({ code: "custom", path: ["linkedAudioTargets"], message: "Linked retime targets must be reciprocal and record-synchronized." });
        }
    }
    const affected = new Set([value.target.id, ...value.linkedAudioTargets.map((target) => target.id)]);
    if (value.protectedNeighbors.some((target) => affected.has(target.id))) {
        context.addIssue({ code: "custom", path: ["protectedNeighbors"], message: "Affected and protected retime targets must be disjoint." });
    }
});
const sdkFrameDurationSchema = z.object({
    domain: z.literal("duration"),
    value: z.object({ kind: z.literal("frames"), value: z.number().int().safe().positive() }).strict(),
}).strict();
export const sdkClipSpeedInputSchema = sdkSingleItemRetimeInputSchema.safeExtend({
    control: z.discriminatedUnion("kind", [
        z.object({ kind: z.literal("multiplier"), multiplier: z.number().positive().max(1000) }).strict(),
        z.object({ kind: z.literal("duration"), duration: sdkFrameDurationSchema }).strict(),
    ]),
    rippleTimeline: z.literal(false),
    pitchCorrection: z.boolean().nullable(),
    keyframes: z.enum(["maintain_timing", "stretch_to_fit"]),
});
export const sdkClipFreezeInputSchema = sdkSingleItemRetimeInputSchema;
export const sdkClipReverseInputSchema = sdkSingleItemRetimeInputSchema;
const sdkRetimeSecondsSchema = z.object({
    unit: z.literal("seconds"),
    value: z.number().min(-1e12).max(1e12),
}).strict();
const sdkSpeedRampHandleSchema = z.object({
    recordDelta: sdkRetimeSecondsSchema,
    sourceDelta: sdkRetimeSecondsSchema,
}).strict();
const sdkRawRetimeInterpolationCodeSchema = z.number().int().min(0).max(2_147_483_647);
const sdkSpeedRampSideControlSchema = z.discriminatedUnion("kind", [
    z.object({
        kind: z.literal("preset"),
        easing: z.enum(["none", "in", "out", "in_out"]).optional(),
        startHandle: sdkSpeedRampHandleSchema.optional(),
        endHandle: sdkSpeedRampHandleSchema.optional(),
        startInterpolationCode: sdkRawRetimeInterpolationCodeSchema.optional(),
        endInterpolationCode: sdkRawRetimeInterpolationCodeSchema.optional(),
    }).strict(),
    z.object({
        kind: z.literal("explicit_points"),
        points: z.array(z.object({
            recordTime: sdkRetimeSecondsSchema,
            sourceTime: sdkRetimeSecondsSchema,
            incomingHandle: sdkSpeedRampHandleSchema.optional(),
            outgoingHandle: sdkSpeedRampHandleSchema.optional(),
            interpolationCode: sdkRawRetimeInterpolationCodeSchema.optional(),
        }).strict()).min(2).max(4096),
    }).strict(),
]);
const sdkSpeedRampTargetSchema = (trackType) => sdkRetimeTargetSchema(trackType).extend({
    sourceOriginFrame: z.number().finite().nonnegative().max(Number.MAX_SAFE_INTEGER).optional(),
}).strict();
export const sdkClipSpeedRampInputSchema = z.object({
    ...sdkRetimeBindingShape,
    outgoing: sdkSpeedRampTargetSchema("video"),
    incoming: sdkSpeedRampTargetSchema("video"),
    linkedAudioTargets: z.array(sdkSpeedRampTargetSchema("audio")).max(512),
    protectedNeighbors: z.array(sdkRetimeProtectedNeighborSchema).max(4096),
    cut: z.object({
        domain: z.literal("timeline_record"),
        value: z.object({ kind: z.literal("frames"), value: z.number().int().safe().nonnegative() }).strict(),
    }).strict(),
    outDuration: sdkFrameDurationSchema,
    inDuration: sdkFrameDurationSchema,
    outStartSpeed: z.number().positive().max(1000),
    outEndSpeed: z.number().positive().max(1000),
    inStartSpeed: z.number().positive().max(1000),
    inEndSpeed: z.number().positive().max(1000),
    curve: z.enum(["linear", "normal_s", "sharp_s"]),
    curveControl: z.object({
        outgoing: sdkSpeedRampSideControlSchema,
        incoming: sdkSpeedRampSideControlSchema,
    }).strict().optional(),
    reverseIncoming: z.boolean(),
    linkedMedia: z.literal("preserve"),
}).strict().superRefine((value, context) => {
    if (value.outgoing.id === value.incoming.id
        || value.outgoing.trackIndex !== value.incoming.trackIndex
        || value.outgoing.recordRange.endExclusive !== value.cut.value.value
        || value.incoming.recordRange.start !== value.cut.value.value) {
        context.addIssue({ code: "custom", path: ["cut"], message: "Speed ramp requires one exact adjacent outgoing/incoming cut." });
    }
    const videoIds = new Set([value.outgoing.id, value.incoming.id]);
    const expectedAudioIds = new Set([...value.outgoing.linkedItemIds, ...value.incoming.linkedItemIds]);
    const audioIds = new Set(value.linkedAudioTargets.map((target) => target.id));
    if (expectedAudioIds.size !== value.outgoing.linkedItemIds.length + value.incoming.linkedItemIds.length
        || audioIds.size !== value.linkedAudioTargets.length
        || expectedAudioIds.size !== audioIds.size
        || [...expectedAudioIds].some((id) => !audioIds.has(id))) {
        context.addIssue({ code: "custom", path: ["linkedAudioTargets"], message: "Speed ramp must declare the complete linked-audio topology for both sides." });
    }
    for (const target of value.linkedAudioTargets) {
        const linkedVideos = [value.outgoing, value.incoming].filter((video) => target.linkedItemIds.includes(video.id));
        if (linkedVideos.length !== 1
            || target.recordRange.start !== linkedVideos[0]?.recordRange.start
            || target.recordRange.endExclusive !== linkedVideos[0]?.recordRange.endExclusive) {
            context.addIssue({ code: "custom", path: ["linkedAudioTargets"], message: "Every linked-audio target must link back to exactly one record-synchronized affected video target." });
        }
    }
    const affected = new Set([...videoIds, ...audioIds]);
    if (value.protectedNeighbors.some((target) => affected.has(target.id))) {
        context.addIssue({ code: "custom", path: ["protectedNeighbors"], message: "Affected and protected speed-ramp targets must be disjoint." });
    }
});
const sdkObservedRetimeTargetSchema = z.object({
    id: sdkTimelineItemIdSchema,
    role: z.enum(["target", "outgoing", "incoming", "linked_audio"]),
    trackType: z.enum(["video", "audio"]),
    trackIndex: z.number().int().min(1).max(4096),
    recordRange: sdkRetimeFrameRangeSchema("timeline_record_range"),
    sourceRange: sdkRetimeFrameRangeSchema("source_range"),
    linkedItemIds: z.array(sdkTimelineItemIdSchema).max(256),
}).strict();
const sdkRetimeTimeMapPointSchema = z.object({
    recordFrame: z.number().int().safe().nonnegative(),
    sourceFrame: z.number().nonnegative().max(1e15),
    speed: z.number().min(-1000).max(1000),
    interpolation: z.enum(["linear", "bezier", "hold"]),
}).strict();
const sdkRetimeTimeMapStateSchema = z.object({
    timelineItemId: sdkTimelineItemIdSchema,
    durationFrames: z.number().int().safe().positive(),
    speedMultiplier: z.number().nonnegative().max(1000),
    reversed: z.boolean(),
    frozen: z.boolean(),
    points: z.array(sdkRetimeTimeMapPointSchema).min(1).max(4096),
}).strict();
const sdkRetimeResultBaseSchema = z.object({
    timelineRevision: sdkRevisionSchema,
    targets: z.array(sdkObservedRetimeTargetSchema).min(1).max(514),
    before: z.array(sdkRetimeTimeMapStateSchema).min(1).max(514),
    after: z.array(sdkRetimeTimeMapStateSchema).min(1).max(514),
    verification: z.object({
        protectedStatePreserved: z.literal(true),
        structuralEvidenceCount: z.number().int().positive().max(10_000),
    }).strict(),
}).strict();
export const sdkClipSpeedResultSchema = sdkRetimeResultBaseSchema.extend({ actionId: z.literal("cutagent.action.clip.speed") }).strict();
export const sdkClipSpeedRampResultSchema = sdkRetimeResultBaseSchema.extend({ actionId: z.literal("cutagent.action.clip.speed_ramp") }).strict();
export const sdkClipFreezeResultSchema = sdkRetimeResultBaseSchema.extend({ actionId: z.literal("cutagent.action.clip.freeze") }).strict();
export const sdkClipReverseResultSchema = sdkRetimeResultBaseSchema.extend({ actionId: z.literal("cutagent.action.clip.reverse") }).strict();
const captionBindingSchema = z.object({
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    precondition: sdkRevisionSchema,
}).strict();
const trackIndexSchema = z.number().int().min(1).max(4096);
export const sdkSubtitleListInputSchema = captionBindingSchema.extend({ track: trackIndexSchema.optional() }).strict();
export const sdkSubtitleInsertInputSchema = captionBindingSchema.extend({
    srt: z.string().min(1).max(2_000_000).superRefine((value, context) => {
        const blocks = value.replace(/\r\n/g, "\n").trim().split(/\n{2,}/);
        const timestamp = /^(\d{2}):([0-5]\d):([0-5]\d)[,.](\d{3})\s+-->\s+(\d{2}):([0-5]\d):([0-5]\d)[,.](\d{3})$/;
        const toMilliseconds = (match, offset) => (((Number(match[offset]) * 60 + Number(match[offset + 1])) * 60 + Number(match[offset + 2])) * 1000) + Number(match[offset + 3]);
        let cueCount = 0;
        const invalid = blocks.some((block) => {
            const lines = block.split("\n").filter((line) => line.trim());
            const timingIndex = lines[0]?.trim().match(/^\d+$/) ? 1 : 0;
            if (!lines[timingIndex]?.includes("-->"))
                return true;
            cueCount += 1;
            const match = timestamp.exec(lines[timingIndex].trim());
            return !match || !lines.slice(timingIndex + 1).join("\n").trim() || toMilliseconds(match, 1) >= toMilliseconds(match, 5);
        });
        if (invalid || cueCount === 0) {
            context.addIssue({ code: "custom", message: "SRT must contain valid, non-empty cues with increasing timestamps." });
        }
    }),
    ensureTrack: z.boolean(),
}).strict();
export const sdkSubtitleExportInputSchema = captionBindingSchema.extend({
    format: z.enum(["srt", "vtt", "ttml"]),
    track: trackIndexSchema.optional(),
    allTracks: z.boolean(),
}).strict().refine((value) => !(value.track !== undefined && value.allTracks), { message: "Choose either one track or all tracks." });
export const sdkAutoCaptionInputSchema = captionBindingSchema.extend({
    language: z.enum(["auto", "danish", "dutch", "english", "french", "german", "italian", "japanese", "korean", "mandarin-simplified", "mandarin-traditional", "norwegian", "portuguese", "russian", "spanish", "swedish"]).optional(),
    preset: z.enum(["default", "teletext", "netflix"]).optional(),
    charsPerLine: z.number().int().min(1).max(60).optional(),
    lineBreak: z.enum(["single", "double"]).optional(),
    gap: z.number().int().min(0).max(10).optional(),
}).strict();
const captionTimingSchema = z.union([
    z.object({ domain: z.literal("timeline_record_range"), unit: z.literal("frames"), start: z.number().int(), endExclusive: z.number().int() }).strict(),
    z.object({ domain: z.literal("timeline_record_range"), unit: z.literal("seconds"), start: z.number(), endExclusive: z.number() }).strict(),
    z.object({ domain: z.literal("transcript_relative_range"), unit: z.literal("frames"), start: z.number().int().min(0), endExclusive: z.number().int().positive() }).strict(),
    z.object({ domain: z.literal("transcript_relative_range"), unit: z.literal("seconds"), start: z.number().min(0), endExclusive: z.number().positive() }).strict(),
]).refine((value) => value.endExclusive > value.start, { message: "Caption end must follow its start." });
const designedCaptionCueSchema = z.object({
    text: z.string().min(1).max(4096),
    timing: captionTimingSchema,
}).strict();
const captionSegmentationSchema = z.object({
    unit: z.enum(["words", "characters"]),
    target: z.number().int().min(1).max(512),
    preferredMin: z.number().int().min(1).max(512),
    preferredMax: z.number().int().min(1).max(512),
    hardMax: z.number().int().min(1).max(512),
    maxCharactersPerLine: z.number().int().min(1).max(512),
    maxLines: z.number().int().min(1).max(8),
    preferredCps: z.number().positive().max(100),
    hardCps: z.number().positive().max(100),
    minimumDurationSeconds: z.number().positive().max(10),
    pauseThresholdSeconds: z.number().positive().max(10),
}).strict().refine((value) => value.preferredMin <= value.target
    && value.target <= value.preferredMax
    && value.preferredMax <= value.hardMax
    && value.preferredCps <= value.hardCps, { message: "Caption segmentation bounds must be monotonic." });
export const sdkDesignedCaptionInputSchema = captionBindingSchema.extend({
    template: z.object({ kind: z.literal("runtime_path"), path: z.string().min(1).max(4096) }).strict(),
    trackIndex: trackIndexSchema,
    cues: z.array(designedCaptionCueSchema).min(1).max(10_000).superRefine((cues, context) => {
        for (let index = 1; index < cues.length; index += 1) {
            if (cues[index].timing.domain !== cues[0].timing.domain || cues[index].timing.unit !== cues[0].timing.unit) {
                context.addIssue({ code: "custom", path: [index, "timing"], message: "Designed caption cues must use one explicit time domain and unit." });
            }
            else if (cues[index].timing.start < cues[index - 1].timing.endExclusive) {
                context.addIssue({ code: "custom", path: [index, "timing", "start"], message: "Designed caption cues must be ordered and non-overlapping." });
            }
        }
    }),
    segmentation: captionSegmentationSchema,
}).strict();
export const sdkTranscriptCreateInputSchema = captionBindingSchema.extend({
    languageCode: z.string().min(1).max(128).optional(),
    diarize: z.boolean(),
    numSpeakers: z.number().int().min(1).max(32).optional(),
    keyterms: z.array(z.string().min(1).max(256)).max(1000),
    verbatim: z.boolean(),
    resumeJobId: z.string().regex(/^[A-Za-z0-9_-]{1,128}$/).optional(),
    newJob: z.boolean(),
}).strict().refine((value) => !(value.resumeJobId && value.newJob), { message: "Resume and new-job controls are mutually exclusive." });
const colorMutationTargetSchema = z.object({
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    colorRevision: sdkRevisionSchema,
    timelineRevision: sdkRevisionSchema,
    nodeStackLayerIndex: z.number().int().min(1).max(4096),
    clipId: sdkTimelineItemIdSchema,
    trackIndex: z.number().int().min(1).max(4096),
    recordFrame: z.number().int().safe().nonnegative(),
}).strict();
const colorNodeIndexSchema = z.number().int().min(1).max(4096);
const colorAssetReferenceSchema = z.object({
    assetId: z.string().min(1).max(256).regex(/^[A-Za-z0-9._:-]+$/),
    fileId: z.string().min(1).max(256).regex(/^[A-Za-z0-9._:-]+$/),
}).strict();
export const sdkColorPrimarySetInputSchema = colorMutationTargetSchema.extend({
    nodeIndex: colorNodeIndexSchema,
    correction: z.object({
        contrast: z.number().finite().min(0).max(4).optional(),
        pivot: z.number().finite().min(0).max(1).optional(),
        temperature: z.number().finite().min(-100).max(100).optional(),
        tint: z.number().finite().min(-100).max(100).optional(),
        hue: z.number().finite().min(-1).max(1).optional(),
        colorBoost: z.number().finite().min(-100).max(100).optional(),
        midtoneDetail: z.number().finite().min(-100).max(100).optional(),
        shadows: z.number().finite().min(-100).max(100).optional(),
        highlights: z.number().finite().min(-100).max(100).optional(),
    }).strict().refine((value) => Object.keys(value).length > 0, "At least one primary correction is required"),
}).strict();
export const sdkColorNodeAddInputSchema = colorMutationTargetSchema.extend({
    afterNodeIndex: colorNodeIndexSchema,
    topology: z.enum(["serial", "parallel", "layer"]),
}).strict().refine((value) => value.topology === "serial" || value.afterNodeIndex === 1, { message: "Parallel and layer nodes can only be added after node 1", path: ["afterNodeIndex"] });
export const sdkColorNodeLabelSetInputSchema = colorMutationTargetSchema.extend({
    nodeIndex: colorNodeIndexSchema,
    label: z.string().min(1).max(128),
}).strict();
export const sdkColorGradeApplyInputSchema = colorMutationTargetSchema.extend({
    asset: colorAssetReferenceSchema,
    alignment: z.enum(["none", "source_timecode", "start_frame"]),
}).strict();
export const sdkColorEffectAddInputSchema = colorMutationTargetSchema.extend({
    nodeIndex: colorNodeIndexSchema,
    effect: z.enum(["gaussian_blur", "sharpen", "film_grain"]),
}).strict();
export const sdkColorMutationResultSchema = z.object({
    kind: z.enum(["primary_set", "node_add", "node_label_set", "grade_apply", "effect_add"]),
    colorRevision: sdkRevisionSchema,
    timelineRevision: sdkRevisionSchema,
    nodeStackLayerIndex: z.number().int().min(1).max(4096),
    clipId: sdkTimelineItemIdSchema,
    nodeCount: z.number().int().min(0).max(4096),
    affectedNodeIndex: colorNodeIndexSchema.nullable(),
    checkpoint: z.object({
        availability: z.enum(["available", "unavailable"]),
        restored: z.boolean(),
    }).strict(),
}).strict();
const sdkRenderFormatSchema = z.enum(["quicktime", "mp4", "mxf", "wave", "aiff"]);
const sdkRenderCodecSchema = z.enum(["h264", "h265", "prores", "dnxhr", "av1", "linear_pcm", "aac", "flac"]);
const sdkRenderSettingsInputSchema = z.object({
    format: sdkRenderFormatSchema,
    codec: sdkRenderCodecSchema,
    width: z.number().int().min(16).max(32_768).optional(),
    height: z.number().int().min(16).max(32_768).optional(),
    frameRate: z.number().positive().max(1_000).optional(),
    exportVideo: z.boolean(),
    exportAudio: z.boolean(),
}).strict().superRefine((value, context) => {
    if (!value.exportVideo && !value.exportAudio) {
        context.addIssue({ code: "custom", path: ["exportVideo"], message: "A render must export video, audio, or both." });
    }
    if ((value.width === undefined) !== (value.height === undefined)) {
        context.addIssue({ code: "custom", path: ["width"], message: "Render width and height must be supplied together." });
    }
    if (["wave", "aiff"].includes(value.format) && value.exportVideo) {
        context.addIssue({ code: "custom", path: ["exportVideo"], message: "Audio-only formats cannot export video." });
    }
});
export const sdkRenderExportInputSchema = z.object({
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    timelineRevision: sdkRevisionSchema,
    range: z.discriminatedUnion("kind", [
        z.object({ kind: z.literal("full_timeline") }).strict(),
        z.object({
            kind: z.literal("custom"),
            startFrame: z.number().int().min(0).max(Number.MAX_SAFE_INTEGER),
            endExclusiveFrame: z.number().int().min(1).max(Number.MAX_SAFE_INTEGER),
        }).strict().refine((value) => value.endExclusiveFrame > value.startFrame, {
            message: "Custom render range must contain at least one frame.",
            path: ["endExclusiveFrame"],
        }),
    ]),
    output: z.object({
        baseName: z.string().min(1).max(180)
            .regex(/^[A-Za-z0-9][A-Za-z0-9._ -]*[A-Za-z0-9]$|^[A-Za-z0-9]$/)
            .refine((value) => value !== "." && value !== ".." && !value.includes(".."), "Render base name cannot contain path traversal."),
    }).strict(),
    settings: sdkRenderSettingsInputSchema,
}).strict();
const nullablePositiveFinite = z.number().positive().finite().nullable();
const sdkResultFrameRateSchema = z.object({
    numerator: z.number().int().positive().max(1_000_000),
    denominator: z.number().int().positive().max(1_000_000),
    nominalTimebase: z.number().int().positive().max(1000),
}).strict().superRefine((rate, context) => {
    let left = rate.numerator;
    let right = rate.denominator;
    while (right !== 0)
        [left, right] = [right, left % right];
    if (left !== 1)
        context.addIssue({ code: "custom", message: "Frame rate rational must be reduced" });
    if (Math.ceil(rate.numerator / rate.denominator) !== rate.nominalTimebase) {
        context.addIssue({ code: "custom", message: "Nominal timebase must equal the ceiling of the actual rate" });
    }
});
export const sdkRenderExportResultSchema = z.object({
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    timelineRevision: sdkRevisionSchema,
    job: z.object({
        id: sdkSnapshotRenderJobIdSchema,
        queueRevision: sdkRevisionSchema,
    }).strict(),
    artifact: z.object({
        artifactId: sdkArtifactIdSchema,
        basename: z.string().min(1).max(255),
        extension: z.string().regex(/^[a-z0-9]{1,16}$/),
        sizeBytes: z.number().int().safe().positive(),
        sha256: z.string().regex(/^sha256:[a-f0-9]{64}$/),
        availableUntil: z.string().datetime({ offset: true }),
        media: z.object({
            durationSeconds: nullablePositiveFinite,
            width: z.number().int().positive().nullable(),
            height: z.number().int().positive().nullable(),
            frameRate: nullablePositiveFinite,
            videoCodec: z.string().min(1).max(128).nullable(),
            audioCodec: z.string().min(1).max(128).nullable(),
            audioChannels: z.number().int().positive().nullable(),
        }).strict(),
    }).strict(),
}).strict();
export const sdkTimelineEditMutationInputSchema = z.object({
    impact: sdkTimelineEditImpactSchema,
}).strict();
export const sdkTimelineRemoveMutationInputSchema = z.object({
    operation: z.literal("clip_remove"),
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    timelineRevision: sdkRevisionSchema,
    affectedTracks: z.array(z.object({ type: z.enum(["video", "audio", "subtitle"]), index: z.number().int().min(1).max(4096) }).strict()).max(12_288),
    affectedItemIds: z.array(sdkTimelineItemIdSchema).min(1).max(4096),
    protectedItemIds: z.array(sdkTimelineItemIdSchema).max(4096),
    clipId: sdkTimelineItemIdSchema,
    track: z.object({ type: z.enum(["video", "audio", "subtitle"]), index: z.number().int().min(1).max(4096) }).strict(),
    expectedLinkTransitions: z.array(z.object({ itemId: sdkTimelineItemIdSchema, beforeLinkedItemIds: z.array(sdkTimelineItemIdSchema).max(4096), afterLinkedItemIds: z.array(sdkTimelineItemIdSchema).max(4096) }).strict()).max(4096).default([]),
    range: z.object({ start: z.number().int().safe(), endExclusive: z.number().int().safe() }).strict().refine((value) => value.endExclusive > value.start),
    name: z.string().min(1).max(4096),
}).strict();
export const sdkTimelineRemoveMutationResultSchema = z.object({
    operation: z.literal("clip_remove"),
    timelineRevision: sdkRevisionSchema,
    affectedTracks: z.array(z.object({ type: z.enum(["video", "audio", "subtitle"]), index: z.number().int().min(1).max(4096) }).strict()).max(12_288),
    affectedItemIds: z.array(sdkTimelineItemIdSchema).max(4096),
    protectedItemIds: z.array(sdkTimelineItemIdSchema).max(4096),
    outputItemIds: z.array(sdkTimelineItemIdSchema).max(4096),
    protectedStatePreserved: z.literal(true),
}).strict();
const sdkTimelineEditMutationClipResultSchema = z.object({
    id: sdkTimelineItemIdSchema,
    trackType: z.enum(["video", "audio", "subtitle"]),
    trackIndex: z.number().int().min(1).max(4096),
    recordStartFrame: z.number().int(),
    recordEndFrameExclusive: z.number().int(),
    sourceStartFrame: z.number().int().nullable(),
    sourceEndFrameExclusive: z.number().int().nullable(),
    sourceFrameRate: sdkResultFrameRateSchema.nullable(),
}).strict().superRefine((clip, context) => {
    if ((clip.sourceStartFrame === null) !== (clip.sourceEndFrameExclusive === null)) {
        context.addIssue({ code: "custom", message: "Source boundaries must both be present or both be null" });
    }
    if (clip.sourceStartFrame !== null && clip.sourceEndFrameExclusive !== null && clip.sourceEndFrameExclusive <= clip.sourceStartFrame) {
        context.addIssue({ code: "custom", message: "Source range end must be greater than start", path: ["sourceEndFrameExclusive"] });
    }
    if (clip.sourceStartFrame === null && clip.sourceFrameRate !== null) {
        context.addIssue({ code: "custom", message: "A source frame rate requires observable source boundaries", path: ["sourceFrameRate"] });
    }
});
export const sdkTimelineEditMutationResultSchema = z.object({
    action: z.enum(["insert", "overwrite", "trim"]),
    impactId: z.string().regex(/^impact_[A-Za-z0-9_-]{16,128}$/),
    timelineRevision: sdkRevisionSchema,
    affectedClips: z.array(sdkTimelineEditMutationClipResultSchema).max(256),
    protectedItemIds: z.array(sdkTimelineItemIdSchema).max(4096),
    protectedStatePreserved: z.literal(true),
}).strict();
export const sdkMulticamSourceSchema = z.object({
    mediaPoolItemId: sdkMediaPoolItemIdSchema,
    name: utf16BoundedTextSchema(1024, "Multicam source name"),
}).strict();
export const sdkMulticamAngleSchema = z.object({
    id: sdkMulticamAngleIdSchema,
    label: utf16BoundedTextSchema(256, "Multicam angle label"),
    enabled: z.boolean().nullable(),
    sources: z.array(sdkMulticamSourceSchema).min(1).max(256),
}).strict();
export const sdkMulticamSnapshotSchema = z.object({
    id: sdkMulticamIdSchema,
    projectId: sdkProjectIdSchema,
    revision: sdkRevisionSchema,
    name: utf16BoundedTextSchema(1024, "Multicam name"),
    angles: z.array(sdkMulticamAngleSchema).min(2).max(6),
}).strict().superRefine((snapshot, context) => {
    if (new Set(snapshot.angles.map((angle) => angle.id)).size !== snapshot.angles.length) {
        context.addIssue({ code: "custom", path: ["angles"], message: "Multicam angle identities must be unique" });
    }
    const sourceIds = snapshot.angles.flatMap((angle) => angle.sources.map((source) => source.mediaPoolItemId));
    if (new Set(sourceIds).size !== sourceIds.length) {
        context.addIssue({ code: "custom", path: ["angles"], message: "A source item cannot be bound to more than one multicam angle" });
    }
});
const multicamSourceInputSchema = z.object({
    mediaPoolItemId: sdkMediaPoolItemIdSchema,
    angleLabel: utf16BoundedTextSchema(256, "Multicam angle label"),
}).strict();
export const sdkMulticamCreateInputSchema = z.object({
    projectId: sdkProjectIdSchema,
    mediaPoolRevision: sdkRevisionSchema,
    name: utf16BoundedTextSchema(1024, "Multicam name"),
    timelineName: utf16BoundedTextSchema(1024, "Multicam timeline name").optional(),
    sources: z.array(multicamSourceInputSchema).min(2).max(256),
    syncMode: z.enum(["in", "out", "timecode", "sound", "marker"]),
    createTimeline: z.boolean(),
}).strict().superRefine((input, context) => {
    const labels = new Set(input.sources.map((source) => source.angleLabel));
    if (labels.size < 2 || labels.size > 6)
        context.addIssue({ code: "custom", path: ["sources"], message: "Multicam creation requires two through six distinct angles" });
    if (new Set(input.sources.map((source) => source.mediaPoolItemId)).size !== input.sources.length) {
        context.addIssue({ code: "custom", path: ["sources"], message: "Multicam source identities must be unique" });
    }
    if (input.createTimeline !== (input.timelineName !== undefined)) {
        context.addIssue({ code: "custom", path: ["timelineName"], message: "Timeline name is required exactly when timeline creation is requested" });
    }
});
export const sdkMulticamSwitchInputSchema = z.object({
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    timelineRevision: sdkRevisionSchema,
    multicamId: sdkMulticamIdSchema,
    multicamRevision: sdkRevisionSchema,
    switches: z.array(z.object({
        atRecordFrame: z.number().int().safe().nonnegative(),
        angleId: sdkMulticamAngleIdSchema,
        scope: z.enum(["linked", "video", "audio"]),
    }).strict()).min(1).max(10_000),
    // JSON Schema 2020-12 cannot express a relational comparison between adjacent
    // array items. Keep the portable wire schema aligned with the CLI contract;
    // the authoring workflow enforces strictly increasing record frames before it
    // creates an operation.
}).strict();
export const sdkMulticamFlattenInputSchema = z.object({
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    timelineRevision: sdkRevisionSchema,
    multicamId: sdkMulticamIdSchema,
    multicamRevision: sdkRevisionSchema,
    scope: z.enum(["video", "audio", "both"]),
    gradePolicy: z.enum(["copy_multicam", "retain_angle"]),
}).strict();
const multicamTimelineResultSchema = z.object({
    id: sdkTimelineIdSchema,
    projectId: sdkProjectIdSchema,
    revision: sdkRevisionSchema,
    name: z.string().min(1).max(1024),
}).strict();
export const sdkMulticamCreateResultSchema = z.object({
    actionId: z.literal("cutagent.action.multicam.create"),
    multicam: sdkMulticamSnapshotSchema,
    timeline: multicamTimelineResultSchema.nullable(),
}).strict().superRefine((result, context) => {
    if (result.timeline !== null && result.timeline.projectId !== result.multicam.projectId) {
        context.addIssue({ code: "custom", path: ["timeline", "projectId"], message: "Created timeline and multicam must belong to the same project" });
    }
});
export const sdkMulticamSwitchResultSchema = z.object({
    actionId: z.literal("cutagent.action.multicam.switch"),
    multicam: sdkMulticamSnapshotSchema,
    timeline: multicamTimelineResultSchema,
    changedSegments: z.number().int().positive(),
}).strict().superRefine((result, context) => {
    if (result.timeline.projectId !== result.multicam.projectId) {
        context.addIssue({ code: "custom", path: ["timeline", "projectId"], message: "Switched timeline and multicam must belong to the same project" });
    }
});
export const sdkMulticamFlattenResultSchema = z.object({
    actionId: z.literal("cutagent.action.multicam.flatten"),
    multicam: sdkMulticamSnapshotSchema,
    timeline: multicamTimelineResultSchema,
    changedSegments: z.number().int().positive(),
}).strict().superRefine((result, context) => {
    if (result.timeline.projectId !== result.multicam.projectId) {
        context.addIssue({ code: "custom", path: ["timeline", "projectId"], message: "Flattened timeline and multicam must belong to the same project" });
    }
});
const operationCreateRequestOptions = [
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.project.create"), input: sdkProjectCreateInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.project.open"), input: sdkProjectOpenInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.project.export"), input: sdkProjectBackupInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.project.restore"), input: sdkProjectRestoreInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.project.library.create"), input: sdkProjectLibraryCreateInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.project.library.switch"), input: sdkProjectLibraryOpenInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.project.library.backup"), input: sdkProjectLibraryBackupInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.project.library.restore"), input: sdkProjectLibraryRestoreInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.media.folders.create"), input: sdkMediaPoolCreateBinInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.media.import"), input: sdkMediaPoolImportInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.media.relink"), input: sdkMediaPoolRelinkInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.media.sync_audio"), input: sdkMediaPoolSyncAudioInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.media.metadata"), input: sdkMediaPoolSetMetadataInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.timeline.marker.add"), input: sdkMarkerCreateInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.timeline.marker.update"), input: sdkMarkerUpdateInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.timeline.marker.delete"), input: sdkMarkerDeleteInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.timeline.items.move"), input: sdkTimelineItemMoveInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.timeline.subtitle.list"), input: sdkSubtitleListInputSchema, idempotencyKey: sdkIdempotencyKeySchema.optional() }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.timeline.subtitle.insert"), input: sdkSubtitleInsertInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.timeline.subtitle.export"), input: sdkSubtitleExportInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.timeline.auto_caption"), input: sdkAutoCaptionInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.text.insert_captions"), input: sdkDesignedCaptionInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.transcript.create"), input: sdkTranscriptCreateInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.color.page.primary_set"), input: sdkColorPrimarySetInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.color.page.node_add"), input: sdkColorNodeAddInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.color.node.label_set"), input: sdkColorNodeLabelSetInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.color.grade_apply"), input: sdkColorGradeApplyInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.color.page.resolvefx_add"), input: sdkColorEffectAddInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.render.export"), input: sdkRenderExportInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.edit.insert"), input: sdkTimelineEditMutationInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.edit.overwrite"), input: sdkTimelineEditMutationInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.edit.trim"), input: sdkTimelineEditMutationInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.timeline.items.delete"), input: sdkTimelineRemoveMutationInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.edit.blade"), input: sdkTimelineBladeInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.audio.voice_generate"), input: sdkVoiceGenerateInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.audio.voice_place"), input: sdkVoicePlacementInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.multicam.create"), input: sdkMulticamCreateInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.multicam.switch"), input: sdkMulticamSwitchInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.multicam.flatten"), input: sdkMulticamFlattenInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.fusion.apply"), input: sdkFusionGraphApplyInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.create"), actionId: z.literal("cutagent.action.sdk.fairlight.plan.apply"), input: sdkFairlightPlanInputSchema, idempotencyKey: sdkIdempotencyKeySchema }).strict(),
];
const operationCreateRequestSchema = z.discriminatedUnion("actionId", operationCreateRequestOptions).superRefine((value, context) => {
    if (value.actionId === "cutagent.action.fusion.apply"
        && value.idempotencyKey !== value.input.idempotencyKey) {
        context.addIssue({
            code: "custom",
            path: ["input", "idempotencyKey"],
            message: "Fusion operation and action input must share one idempotency key",
        });
    }
});
const typedOperationCreateActionIds = new Set(operationCreateRequestOptions.map((schema) => schema.shape.actionId.value));
const fairlightPreparedOperationCreateRequestSchema = operationControlBase.extend({
    operation: z.literal("operation.create"),
    actionId: z.enum(CUTAGENT_SDK_FAIRLIGHT_PREPARED_ACTION_IDS),
    input: z.record(z.string(), z.unknown()),
    idempotencyKey: sdkIdempotencyKeySchema,
}).strict().superRefine((value, context) => {
    // Carrier-owned Fairlight actions derive their private binding from a fresh
    // live snapshot. Other reviewed routes retain their internal evaluation
    // envelope until their distinct selector and custody requirements migrate.
    if (CUTAGENT_SDK_FAIRLIGHT_CARRIER_OWNED_ACTION_IDS.includes(value.actionId)) {
        if (Object.hasOwn(value.input, "actionInput") || Object.hasOwn(value.input, "carrierBinding")) {
            context.addIssue({
                code: "custom",
                path: ["input"],
                message: "Public Fairlight input cannot provide internal carrier binding fields",
            });
        }
        return;
    }
    const parsed = sdkFairlightPreparedOperationInputSchema.safeParse(value.input);
    if (!parsed.success) {
        context.addIssue({
            code: "custom",
            path: ["input"],
            message: "This Fairlight action has not migrated to carrier-owned live binding",
        });
    }
});
const fairlightPreparedActionIds = new Set(CUTAGENT_SDK_FAIRLIGHT_PREPARED_ACTION_IDS);
const registeredOperationCreateRequestSchema = operationControlBase.extend({
    operation: z.literal("operation.create"),
    // The authoritative in-process registry applies the exact contributed input
    // schema before durable creation. This transport envelope only admits IDs
    // from the generated final public registry; unknown IDs still fail here.
    actionId: sdkPublicActionIdSchema,
    input: z.record(z.string(), z.unknown()),
    idempotencyKey: sdkIdempotencyKeySchema.optional(),
}).strict().superRefine((value, context) => {
    if (typedOperationCreateActionIds.has(value.actionId)
        || fairlightPreparedActionIds.has(value.actionId)) {
        context.addIssue({
            code: "custom",
            path: ["actionId"],
            message: "Typed SDK actions must satisfy their exact operation schema",
        });
    }
});
export const sdkOperationControlRequestSchema = z.union([
    operationControlBase.extend({ operation: z.literal("operation.get"), operationId: sdkOperationIdSchema }).strict(),
    operationControlBase.extend({
        operation: z.literal("operation.result.page"),
        operationId: sdkOperationIdSchema,
        collectionId: sdkOperationResultCollectionIdSchema,
        expectedDigest: sdkOperationResultCollectionDigestSchema,
        offset: z.number().int().min(0).max(10_000),
        pageSize: z.number().int().min(1).max(CUTAGENT_SDK_OPERATION_RESULT_PAGE_MAX_ITEMS),
    }).strict(),
    operationControlBase.extend({ operation: z.literal("operation.cancel"), operationId: sdkOperationIdSchema }).strict(),
    z.union([
        operationCreateRequestSchema,
        fairlightPreparedOperationCreateRequestSchema,
        registeredOperationCreateRequestSchema,
    ]),
]);
const sdkOperationEventControlSuccessSchema = z.object({
    ok: z.literal(true),
    protocolVersion: z.literal(1),
    requestId: sdkRequestIdSchema,
    operation: z.enum(["operation.get", "operation.cancel", "operation.create"]),
    event: sdkOperationEventSchema,
}).strict();
const sdkOperationResultPageControlSuccessSchema = z.object({
    ok: z.literal(true),
    protocolVersion: z.literal(1),
    requestId: sdkRequestIdSchema,
    operation: z.literal("operation.result.page"),
    page: sdkOperationResultPageSchema,
}).strict();
export const sdkOperationControlSuccessSchema = z.union([
    sdkOperationEventControlSuccessSchema,
    sdkOperationResultPageControlSuccessSchema,
]);
export const sdkOperationControlFailureSchema = z.object({
    ok: z.literal(false),
    protocolVersion: z.literal(1),
    requestId: sdkRequestIdSchema,
    error: sdkPublicFailureSchema,
}).strict().superRefine((response, context) => {
    if (response.error.requestId !== response.requestId) {
        context.addIssue({ code: "custom", path: ["error", "requestId"], message: "Operation control failure request correlation must match" });
    }
    if (response.error.workflowId !== undefined) {
        context.addIssue({ code: "custom", path: ["error", "workflowId"], message: "Operation control failures cannot carry workflow identity" });
    }
});
export const sdkOperationControlResponseSchema = z.union([
    sdkOperationControlSuccessSchema,
    sdkOperationControlFailureSchema,
]);
export const sdkWorkflowStepOutcomeSchema = z.enum(["completed", "failed_before_mutation", "partially_applied", "checkpoint_restored", "compensated", "restore_failed", "manual_recovery_required", "cancellation_requested"]);
export const sdkManagedOwnershipIdSchema = z.string().min(1).max(200).regex(/^[a-z0-9][a-z0-9._/-]*$/);
export const sdkManagedScopeSchema = z.discriminatedUnion("kind", [
    z.object({ kind: z.literal("whole_timeline") }).strict(),
    z.object({
        kind: z.literal("region"),
        startFrame: z.number().int().safe().nonnegative(),
        endExclusiveFrame: z.number().int().safe().positive(),
    }).strict().refine((scope) => scope.endExclusiveFrame > scope.startFrame, "Managed region must be a non-empty half-open range"),
]);
export const sdkManagedWorkflowClaimSchema = z.object({
    ownershipId: sdkManagedOwnershipIdSchema,
    scope: sdkManagedScopeSchema,
    timelineFrameRate: sdkResultFrameRateSchema,
    previewDigest: z.string().regex(/^sha256:[a-f0-9]{64}$/),
    contextDigest: z.string().regex(/^sha256:[a-f0-9]{64}$/),
    protectedStateDigest: z.string().regex(/^sha256:[a-f0-9]{64}$/),
    desiredStateDigest: z.string().regex(/^sha256:[a-f0-9]{64}$/),
    elements: z.array(z.object({
        key: z.string().regex(/^[a-z][a-z0-9_-]{0,63}$/),
        assetId: sdkMediaPoolItemIdSchema,
        assetName: z.string().min(1).max(4096),
        assetRevision: sdkRevisionSchema,
        videoTrack: z.number().int().min(1).max(4096),
        audioTrack: z.number().int().min(1).max(4096).nullable(),
        atFrame: z.number().int().safe().nonnegative(),
        sourceStartFrame: z.number().int().safe().nonnegative(),
        sourceEndExclusiveFrame: z.number().int().safe().positive(),
        sourceFrameRate: sdkResultFrameRateSchema,
        linkedAudio: z.enum(["include", "exclude"]),
        adoptTimelineItemId: sdkTimelineItemIdSchema.nullable(),
    }).strict().refine((element) => element.sourceEndExclusiveFrame > element.sourceStartFrame, "Managed source range must be non-empty")).max(1000),
}).strict();
export const sdkManagedElementMappingSchema = z.object({
    key: z.string().regex(/^[a-z][a-z0-9_-]{0,63}$/),
    timelineItemId: sdkTimelineItemIdSchema,
}).strict();
const sdkWorkflowCreateBindingSchema = z.object({
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    revision: sdkRevisionSchema,
    idempotencyKey: sdkIdempotencyKeySchema,
}).strict();
const sdkManagedWorkflowCreateBindingSchema = sdkWorkflowCreateBindingSchema.extend({
    managedClaim: sdkManagedWorkflowClaimSchema,
}).strict();
const sdkWorkflowBindingSchema = sdkWorkflowCreateBindingSchema.extend({
    policyRevision: z.string().regex(/^policy_revision_[1-9][0-9]*$/),
}).strict();
const sdkWorkflowStepSchema = z.object({
    name: z.string().regex(/^[a-z][a-z0-9_-]{0,63}$/),
    idempotencyKey: sdkIdempotencyKeySchema,
    operationId: sdkOperationIdSchema.optional(),
    actionId: sdkPublicActionIdSchema.optional(),
    outcome: sdkWorkflowStepOutcomeSchema.optional(),
}).strict();
export const sdkWorkflowSnapshotSchema = z.object({
    workflowId: sdkWorkflowIdSchema,
    authorityKind: z.enum(["generic", "managed"]).default("generic"),
    binding: sdkWorkflowBindingSchema,
    sequence: z.number().int().positive(),
    status: z.enum(["checkpoint_pending", "active", "completed", "failed_before_mutation", "partially_applied", "checkpoint_restored", "compensated", "restore_failed", "manual_recovery_required", "cancellation_requested"]),
    steps: z.array(sdkWorkflowStepSchema).max(1000),
    createdAt: z.string().datetime({ offset: true }),
    updatedAt: z.string().datetime({ offset: true }),
    retentionExpiresAt: z.string().datetime({ offset: true }),
    manualRecoveryRequired: z.boolean(),
    cancellationDoesNotRollback: z.literal(true),
    managedState: z.object({
        ownershipId: sdkManagedOwnershipIdSchema,
        generation: z.number().int().positive(),
        revision: sdkRevisionSchema,
        desiredStateDigest: z.string().regex(/^sha256:[a-f0-9]{64}$/),
        elements: z.array(sdkManagedElementMappingSchema).max(1000),
        verification: z.object({
            outcome: z.literal("passed"),
            finalRevision: sdkRevisionSchema,
            protectedStateDigest: z.string().regex(/^sha256:[a-f0-9]{64}$/),
            expectedManagedStateDigest: z.string().regex(/^sha256:[a-f0-9]{64}$/),
            evidence: z.array(z.object({ modality: z.enum(["readback", "structural"]), summary: z.string().min(1).max(500), digest: z.string().regex(/^sha256:[a-f0-9]{64}$/) }).strict()).min(2).max(20),
        }).strict(),
    }).strict().optional(),
}).strict();
export const sdkWorkflowControlRequestSchema = z.union([
    operationControlBase.extend({ operation: z.literal("workflow.managed.start"), binding: sdkManagedWorkflowCreateBindingSchema, cancellationRequested: z.boolean() }).strict(),
    operationControlBase.extend({ operation: z.literal("workflow.managed.wait"), workflowId: sdkWorkflowIdSchema }).strict(),
    operationControlBase.extend({ operation: z.literal("workflow.create"), binding: sdkWorkflowCreateBindingSchema }).strict(),
    operationControlBase.extend({ operation: z.literal("workflow.get"), workflowId: sdkWorkflowIdSchema }).strict(),
    operationControlBase.extend({ operation: z.literal("workflow.step.reserve"), workflowId: sdkWorkflowIdSchema, name: sdkWorkflowStepSchema.shape.name }).strict(),
    operationControlBase.extend({ operation: z.literal("workflow.step.attach"), workflowId: sdkWorkflowIdSchema, name: sdkWorkflowStepSchema.shape.name, operationId: sdkOperationIdSchema }).strict(),
    operationControlBase.extend({ operation: z.literal("workflow.step.observe"), workflowId: sdkWorkflowIdSchema, name: sdkWorkflowStepSchema.shape.name }).strict(),
    operationControlBase.extend({ operation: z.literal("workflow.step.fail_before_mutation"), workflowId: sdkWorkflowIdSchema, name: sdkWorkflowStepSchema.shape.name }).strict(),
    operationControlBase.extend({ operation: z.literal("workflow.fail"), workflowId: sdkWorkflowIdSchema }).strict(),
    operationControlBase.extend({ operation: z.literal("workflow.complete"), workflowId: sdkWorkflowIdSchema }).strict(),
    operationControlBase.extend({ operation: z.literal("workflow.interrupt"), workflowId: sdkWorkflowIdSchema }).strict(),
]);
export const sdkWorkflowControlFailureSchema = z.object({
    ok: z.literal(false),
    protocolVersion: z.literal(1),
    requestId: sdkRequestIdSchema,
    workflowId: sdkWorkflowIdSchema.optional(),
    error: sdkPublicFailureSchema,
}).strict().superRefine((response, context) => {
    if (response.error.requestId !== response.requestId) {
        context.addIssue({ code: "custom", path: ["error", "requestId"], message: "Workflow control failure request correlation must match" });
    }
    if ((response.workflowId === undefined) !== (response.error.workflowId === undefined)
        || (response.workflowId !== undefined && response.error.workflowId !== response.workflowId)) {
        context.addIssue({ code: "custom", path: ["error", "workflowId"], message: "Workflow control failure identity correlation must match" });
    }
    if (response.error.operationId !== undefined) {
        context.addIssue({ code: "custom", path: ["error", "operationId"], message: "Workflow control failures cannot carry operation identity" });
    }
});
export const sdkWorkflowControlResponseSchema = z.union([
    z.object({ ok: z.literal(true), protocolVersion: z.literal(1), requestId: sdkRequestIdSchema, operation: z.string().startsWith("workflow."), snapshot: sdkWorkflowSnapshotSchema }).strict(),
    sdkWorkflowControlFailureSchema,
]);
