import { z } from "zod";
import { sdkExecutionIdSchema, sdkOperationIdSchema, sdkRequestIdSchema, } from "./sdk-identities.js";
export const CUTAGENT_MUTATION_POLICY_CONTRACT_VERSION = 1;
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
