// Generated from sdk-prepared-action-kernel.json. Do not edit.
import { z } from "zod";
import { CUTAGENT_MUTATION_POLICY_CONTRACT_VERSION, sdkConstraintBindingLevelSchema, sdkMutationImpactSchema, sdkSha256DigestSchema, sdkStableTargetIdSchema, sdkStateRevisionSchema, } from "./sdk-mutation-policy.js";
import { sdkPublicActionResultSchema } from "./sdk-operations.js";
export const CUTAGENT_PREPARED_ACTION_PROTOCOL_VERSION = 2;
export const CUTAGENT_PREPARED_ACTION_KERNEL_DIGEST = "sha256:e76c8d3035abb0847eafc519cea1a2125a0d2f9d9c52491f1dd696b5a53a4c90";
export const CUTAGENT_PREPARED_ACTION_CONTRACT_DIGEST = "sha256:0de84120b23f26fcd90d8ed327ceb52da731bb512263247c2fd5ff88997134d9";
export const CUTAGENT_PREPARED_ACTION_CAPABILITY_DIGEST = "sha256:9094f2a43290856f5be0fa80feab68a21b6d2aaa30aace394601b682e83ff89a";
export const CUTAGENT_PREPARED_ACTION_RECEIPT_TTL_MS = 30000;
export const CUTAGENT_PREPARED_ACTION_MAX_OUTSTANDING_RECEIPTS = 1024;
export const CUTAGENT_PREPARED_ACTION_MAX_RESULT_BYTES = 16777216;
const digestSchema = z.string().regex(/^sha256:[a-f0-9]{64}$/);
const opaqueSchema = z.string().min(16).max(512).regex(/^[A-Za-z0-9_.~-]+$/);
const jsonSchema = z.lazy(() => z.union([
    z.null(), z.boolean(), z.number().finite(), z.string(), z.array(jsonSchema), z.record(z.string(), jsonSchema),
]));
export const sdkPreparedActionIdentitiesSchema = z.object({
    projectLibraryId: z.string().min(1).max(512),
    projectId: z.string().min(1).max(512).nullable(),
    timelineId: z.string().min(1).max(512).nullable(),
    targetIds: z.array(z.string().min(1).max(512)).max(10_000),
}).strict();
export const sdkPreparedActionRevisionsSchema = z.object({
    projectLibrary: z.string().min(1).max(512),
    project: z.string().min(1).max(512).nullable(),
    timeline: z.string().min(1).max(512).nullable(),
    targets: z.record(z.string(), z.string().min(1).max(512)),
}).strict();
export const sdkPrepareActionRequestSchema = z.object({
    protocolVersion: z.literal(CUTAGENT_PREPARED_ACTION_PROTOCOL_VERSION),
    actionId: z.string().regex(/^cutagent\.action\.[a-z0-9_.]+$/),
    actionContractVersion: z.number().int().positive(),
    input: jsonSchema,
    contractDigest: digestSchema,
    capabilityDigest: digestSchema,
    identities: sdkPreparedActionIdentitiesSchema,
    revisions: sdkPreparedActionRevisionsSchema,
    idempotencyKey: opaqueSchema,
    requestId: opaqueSchema,
    operationId: opaqueSchema,
    executionId: opaqueSchema,
}).strict();
/** Private carrier-owned base copied verbatim into every prepared mutation impact. */
export const sdkPreparedActionMutationBaseSchema = z.object({
    contractVersion: z.literal(CUTAGENT_MUTATION_POLICY_CONTRACT_VERSION),
    carrier: z.literal("sdk"),
    minimumBinding: sdkConstraintBindingLevelSchema,
    registryDigest: sdkSha256DigestSchema,
    canonicalRequestDigest: sdkSha256DigestSchema,
    referencedPayloadDigests: z.array(sdkSha256DigestSchema).max(1_000),
    requestId: opaqueSchema,
    operationId: opaqueSchema,
    executionId: opaqueSchema,
    projectLibraryId: sdkStableTargetIdSchema,
    projectId: sdkStableTargetIdSchema.optional(),
    timelineId: sdkStableTargetIdSchema.optional(),
    projectRevision: sdkStateRevisionSchema.optional(),
    timelineRevision: sdkStateRevisionSchema.optional(),
}).strict();
export const sdkPreparedReadImpactSchema = z.object({
    contractVersion: z.literal(1),
    status: z.literal("read"),
    complete: z.literal(true),
    targetDigests: z.array(digestSchema).max(10_000),
    resultMaximumBytes: z.number().int().positive().max(CUTAGENT_PREPARED_ACTION_MAX_RESULT_BYTES),
}).strict();
export const sdkPreparedActionImpactSchema = z.union([sdkPreparedReadImpactSchema, sdkMutationImpactSchema]);
export const sdkPreparedActionAuthorizationBindingSchema = z.object({
    accountDigest: digestSchema,
    subscriptionDigest: digestSchema,
    sessionDigest: digestSchema,
    actionDigest: digestSchema,
    inputDigest: digestSchema,
    contractDigest: digestSchema,
    capabilityDigest: digestSchema,
    protocolDigest: digestSchema,
    projectDigest: digestSchema,
    timelineDigest: digestSchema,
    targetsDigest: digestSchema,
    preStateDigest: digestSchema,
    impactDigest: digestSchema,
    receiptDigest: digestSchema,
    executionDigest: digestSchema,
    appArtifactDigest: digestSchema,
    runtimeArtifactDigest: digestSchema,
    cliArtifactDigest: digestSchema,
    packagedAncestryDigest: digestSchema,
    expiresAt: z.number().int().positive(),
}).strict();
export const sdkPrepareActionResultSchema = z.object({
    protocolVersion: z.literal(CUTAGENT_PREPARED_ACTION_PROTOCOL_VERSION),
    receipt: z.string().min(32).max(4096),
    receiptDigest: digestSchema,
    expiresAt: z.string().datetime({ offset: true }),
    operationClass: z.enum(["read", "mutation"]),
    impact: sdkPreparedActionImpactSchema,
    authorizationBinding: sdkPreparedActionAuthorizationBindingSchema,
}).strict().superRefine((value, context) => {
    if ((value.operationClass === "read") !== (value.impact.status === "read")) {
        context.addIssue({ code: "custom", path: ["impact", "status"], message: "Prepared impact class mismatch" });
    }
});
export const sdkAdmitPreparedActionRequestSchema = z.object({
    receipt: z.string().min(32).max(4096),
    authorizationToken: z.string().min(64).max(16_384),
}).strict();
export const sdkExecutePreparedActionRequestSchema = z.object({
    receipt: z.string().min(32).max(4096),
}).strict();
const sdkPreparedEvidenceSchema = z.object({
    modality: z.enum(["readback", "structural", "file", "rendered", "visual", "auditioned"]),
    digest: digestSchema,
    summary: z.string().min(1).max(500),
}).strict();
const sdkPreparedVerificationSchema = z.object({
    outcome: z.enum(["passed", "failed", "partial", "not_performed", "manual_review_required"]),
    evidence: z.array(sdkPreparedEvidenceSchema).max(1_000),
    protectedStatePreserved: z.boolean().nullable(),
}).strict();
const sdkPreparedRecoverySchema = z.object({
    outcome: z.enum(["not_needed", "succeeded", "failed", "manual_required"]),
    attempted: z.boolean(),
    manualActionRequired: z.boolean(),
    cause: z.object({ code: z.string().min(1).max(128) }).strict().optional(),
}).strict();
const sdkPreparedFailureSchema = z.object({
    code: z.string().min(1).max(128), kind: z.string().min(1).max(128),
    message: z.string().min(1).max(500), cause: z.object({ code: z.string().min(1).max(128) }).strict(),
    readbackRequired: z.boolean(), recoveryGuidance: z.array(z.string().min(1).max(500)).max(20),
}).strict();
export const sdkPreparedActionTerminalSchema = z.object({
    status: z.enum(["succeeded", "failed", "recovered", "recovery_failed"]),
    operationId: opaqueSchema, executionId: opaqueSchema,
    actionId: z.string().regex(/^cutagent\.action\.[a-z0-9_.]+$/),
    possibleMutation: z.enum(["none", "possible", "confirmed", "partial", "unknown"]),
    usage: z.enum(["not_reserved", "released", "consumed", "unknown"]),
    verification: sdkPreparedVerificationSchema,
    recovery: sdkPreparedRecoverySchema,
    retrySafe: z.literal(false),
    result: sdkPublicActionResultSchema.optional(),
    resultOmitted: z.object({ code: z.literal("OUTPUT_LIMIT_REACHED"), digest: digestSchema }).strict().optional(),
    failure: sdkPreparedFailureSchema.optional(),
    custody: z.literal("terminal_persistence_unavailable").optional(),
}).strict().superRefine((value, context) => {
    if ((value.status === "succeeded") !== (value.failure === undefined))
        context.addIssue({ code: "custom", path: ["failure"], message: "Terminal failure/status mismatch" });
    if (value.status === "succeeded" && value.verification.outcome !== "passed")
        context.addIssue({ code: "custom", path: ["verification"], message: "Success requires passed verification" });
    if (value.status === "succeeded" && value.possibleMutation !== "none" && value.verification.protectedStatePreserved !== true)
        context.addIssue({ code: "custom", path: ["verification", "protectedStatePreserved"], message: "Mutation success requires protected-state proof" });
}).refine((value) => new TextEncoder().encode(JSON.stringify(value)).byteLength <= CUTAGENT_PREPARED_ACTION_MAX_RESULT_BYTES, "Prepared terminal exceeds output bound");
