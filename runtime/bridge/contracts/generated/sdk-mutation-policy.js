import { z } from "zod";
import { sdkExecutionIdSchema, sdkOperationIdSchema, sdkRequestIdSchema, } from "./sdk-identities.js";
export const CUTAGENT_MUTATION_POLICY_CONTRACT_VERSION = 1;
export const sdkConstraintScopeIdSchema = z.string()
    .regex(/^constraint_scope_[A-Za-z0-9._~-]{16,128}$/);
export const sdkConstraintScopeRevisionSchema = z.number().int().safe().positive();
export const sdkConstraintAccountFingerprintSchema = z.string()
    .regex(/^[A-Za-z0-9_-]{20,128}$/);
export const sdkStableTargetIdSchema = z.string()
    .regex(/^[A-Za-z0-9][A-Za-z0-9._:~+/-]{2,255}$/);
export const sdkStateRevisionSchema = z.string()
    .regex(/^(?:sha256:)?[A-Za-z0-9_-]{16,128}$/);
export const sdkSha256DigestSchema = z.string().regex(/^sha256:[a-f0-9]{64}$/);
export const sdkConstraintBindingLevelSchema = z.enum([
    "account/project-library",
    "project",
    "project+timeline",
]);
const projectLibraryBinding = z.object({
    level: z.literal("account/project-library"),
    projectLibraryId: sdkStableTargetIdSchema,
}).strict();
const projectBinding = z.object({
    level: z.literal("project"),
    projectLibraryId: sdkStableTargetIdSchema,
    projectId: sdkStableTargetIdSchema,
    projectRevision: sdkStateRevisionSchema,
}).strict();
const timelineBinding = z.object({
    level: z.literal("project+timeline"),
    projectLibraryId: sdkStableTargetIdSchema,
    projectId: sdkStableTargetIdSchema,
    projectRevision: sdkStateRevisionSchema,
    timelineId: sdkStableTargetIdSchema,
    timelineRevision: sdkStateRevisionSchema,
}).strict();
export const sdkConstraintBindingSchema = z.discriminatedUnion("level", [
    projectLibraryBinding,
    projectBinding,
    timelineBinding,
]);
export const sdkProtectedTargetKindSchema = z.enum([
    "project_library",
    "project",
    "timeline",
    "track",
    "clip",
    "fusion_composition",
    "media",
    "marker",
    "runtime_setting",
]);
export const sdkTrackTypeSchema = z.enum(["video", "audio", "subtitle"]);
export const sdkProtectedMediaRoleSchema = z.enum([
    "music",
    "dialogue",
    "voiceover",
    "ambience",
    "effects",
    "other",
]);
export const sdkStableMutationTargetSchema = z.object({
    kind: sdkProtectedTargetKindSchema,
    stableId: sdkStableTargetIdSchema,
    revision: sdkStateRevisionSchema,
    trackType: sdkTrackTypeSchema.optional(),
    trackIndex: z.number().int().positive().optional(),
    mediaRole: sdkProtectedMediaRoleSchema.optional(),
}).strict().superRefine((target, context) => {
    if ((target.trackType === undefined) !== (target.trackIndex === undefined)) {
        context.addIssue({
            code: "custom",
            path: ["trackType"],
            message: "Track type and index must be supplied together",
        });
    }
});
export const sdkEditConstraintsSchema = z.object({
    protectedTargets: z.array(sdkStableMutationTargetSchema).max(10_000),
    protectedMediaRoles: z.array(sdkProtectedMediaRoleSchema).max(6),
    allowedTrackTypes: z.array(sdkTrackTypeSchema).max(3),
    allowedOperations: z.array(z.string().regex(/^[a-z0-9_]+(?:\.[a-z0-9_]+)*$/)).max(1_000),
    markerIntent: z.enum(["placement", "mutation_target"]).nullable(),
}).strict();
export const sdkConstraintScopeSchema = z.object({
    contractVersion: z.literal(CUTAGENT_MUTATION_POLICY_CONTRACT_VERSION),
    scopeId: sdkConstraintScopeIdSchema,
    accountFingerprint: sdkConstraintAccountFingerprintSchema,
    revision: sdkConstraintScopeRevisionSchema,
    binding: sdkConstraintBindingSchema,
    constraints: sdkEditConstraintsSchema,
    createdAt: z.string().datetime({ offset: true }),
    updatedAt: z.string().datetime({ offset: true }),
}).strict().superRefine((scope, context) => {
    if (Date.parse(scope.updatedAt) < Date.parse(scope.createdAt)) {
        context.addIssue({ code: "custom", path: ["updatedAt"], message: "Scope update cannot precede creation" });
    }
});
export const sdkMutationCarrierSchema = z.enum([
    "sdk",
    "desktop",
    "plugin",
    "cli",
    "batch",
    "composition",
]);
export const sdkMutationImpactStatusSchema = z.enum(["read", "mutation", "unknown"]);
export const sdkMutationEffectSchema = z.object({
    operation: z.string().regex(/^[a-z0-9_]+(?:\.[a-z0-9_]+)*$/),
    kind: z.enum(["create", "update", "delete", "blade", "unknown"]),
    trackTypes: z.array(sdkTrackTypeSchema).max(2),
    targets: z.array(sdkStableMutationTargetSchema).max(10_000),
    placementIntent: z.enum(["marker", "explicit", "unknown"]),
    broad: z.boolean(),
    ambiguous: z.boolean(),
    complete: z.boolean(),
}).strict();
export const sdkMutationVerificationPolicySchema = z.object({
    minimumEvidence: z.array(z.enum(["readback", "structural", "file", "rendered", "visual", "auditioned"]))
        .min(1).max(6),
    requireProtectedStatePreserved: z.boolean(),
    protectedTargetEvidence: z.enum(["none", "every_declared_target"]),
}).strict();
export const sdkMutationImpactSchema = z.object({
    contractVersion: z.literal(CUTAGENT_MUTATION_POLICY_CONTRACT_VERSION),
    carrier: sdkMutationCarrierSchema,
    status: sdkMutationImpactStatusSchema,
    minimumBinding: sdkConstraintBindingLevelSchema,
    registryDigest: sdkSha256DigestSchema,
    canonicalRequestDigest: sdkSha256DigestSchema,
    referencedPayloadDigests: z.array(sdkSha256DigestSchema).max(1_000),
    requestId: sdkRequestIdSchema,
    operationId: sdkOperationIdSchema,
    executionId: sdkExecutionIdSchema,
    scopeId: sdkConstraintScopeIdSchema,
    scopeRevision: sdkConstraintScopeRevisionSchema,
    projectLibraryId: sdkStableTargetIdSchema,
    projectId: sdkStableTargetIdSchema.optional(),
    timelineId: sdkStableTargetIdSchema.optional(),
    projectRevision: sdkStateRevisionSchema.optional(),
    timelineRevision: sdkStateRevisionSchema.optional(),
    effects: z.array(sdkMutationEffectSchema).max(10_000),
    closedComposition: z.boolean(),
    complete: z.boolean(),
    ambiguous: z.boolean(),
    broad: z.boolean(),
    executableStableTargetPrecondition: z.boolean(),
    verificationPolicy: sdkMutationVerificationPolicySchema,
}).strict().superRefine((impact, context) => {
    if (impact.status === "read" && impact.effects.length !== 0) {
        context.addIssue({ code: "custom", path: ["effects"], message: "Read impact cannot carry mutation effects" });
    }
    if (impact.status === "mutation" && impact.effects.length === 0) {
        context.addIssue({ code: "custom", path: ["effects"], message: "Mutation impact requires at least one effect" });
    }
    if (impact.minimumBinding === "project+timeline"
        && (!impact.projectId || !impact.timelineId || !impact.projectRevision || !impact.timelineRevision)) {
        context.addIssue({
            code: "custom",
            path: ["minimumBinding"],
            message: "Timeline-bound impact requires project and timeline revisions",
        });
    }
    if (impact.minimumBinding === "project" && (!impact.projectId || !impact.projectRevision)) {
        context.addIssue({ code: "custom", path: ["projectId"], message: "Project-bound impact requires project identity and revision" });
    }
});
export const sdkMutationPolicyDenialEvidenceSchema = z.object({
    reason: z.enum([
        "missing_scope",
        "cross_account_scope",
        "stale_scope",
        "insufficient_binding",
        "binding_mismatch",
        "unknown_impact",
        "incomplete_impact",
        "ambiguous_impact",
        "broad_impact",
        "protected_target",
        "protected_media_role",
        "track_type_not_allowed",
        "operation_not_allowed",
        "marker_intent_conflict",
        "stale_target",
        "decision_revoked",
        "decision_replayed",
        "decision_binding_mismatch",
        "signed_execution_scope_unavailable",
    ]),
    summary: z.string().min(1).max(500),
    protectedTargetDigests: z.array(sdkSha256DigestSchema).max(1_000),
}).strict();
