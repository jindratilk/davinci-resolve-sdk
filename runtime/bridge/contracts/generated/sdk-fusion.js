import { z } from "zod";
import { sdkFusionCompositionIdSchema, sdkIdempotencyKeySchema, sdkProjectIdSchema, sdkRevisionSchema, sdkTimelineIdSchema, sdkTimelineItemIdSchema, } from "./sdk-identities.js";
export const CUTAGENT_SDK_FUSION_GRAPH_ACTION_ID = "cutagent.action.fusion.apply";
export const CUTAGENT_SDK_FUSION_GRAPH_CONTRACT_VERSION = 1;
export const CUTAGENT_SDK_FUSION_IMAGE_REPLACE_ACTION_ID = "cutagent.action.fusion.image.batch";
export const CUTAGENT_SDK_FUSION_IMAGE_REPLACE_CONTRACT_VERSION = 1;
export const CUTAGENT_SDK_FUSION_TEXT_ACTION_ID = "cutagent.action.fusion.text.batch";
export const CUTAGENT_SDK_FUSION_NESTED_TEXT_ACTION_ID = "cutagent.action.fusion.nested_text.batch";
const sdkFusionValueSchema = z.union([
    z.number().finite(),
    z.string().max(65_536),
    z.boolean(),
    z.tuple([z.number().finite(), z.number().finite()]),
    z.tuple([z.number().finite(), z.number().finite(), z.number().finite()]),
    z.tuple([z.number().finite(), z.number().finite(), z.number().finite(), z.number().finite()]),
]);
const sdkFusionFrameSchema = z.number().int().safe();
const sdkFusionKeyframeSchema = z.object({ time: sdkFusionFrameSchema, value: sdkFusionValueSchema }).strict();
export const sdkFusionAnimationSchema = z.object({
    kind: z.literal("keyframes"),
    keyframes: z.array(sdkFusionKeyframeSchema).min(1).max(10_000),
}).strict();
const sdkFusionGraphNodeSchema = z.object({
    id: z.string().regex(/^[A-Za-z][A-Za-z0-9_]{0,127}$/),
    inputs: z.record(z.string(), sdkFusionValueSchema),
    type: z.string().regex(/^[A-Za-z][A-Za-z0-9_.:-]{0,127}$/),
}).strict();
const sdkFusionGraphConnectionSchema = z.object({
    source: z.object({ node: z.string(), port: z.string() }).strict(),
    target: z.object({ node: z.string(), port: z.string() }).strict(),
}).strict();
const sdkFusionGraphAnimationSchema = z.object({
    node: z.string(),
    input: z.string(),
    animation: sdkFusionAnimationSchema,
}).strict();
export const sdkFusionGraphRequestSchema = z.object({
    graph: z.object({
        animations: z.array(sdkFusionGraphAnimationSchema),
        connections: z.array(sdkFusionGraphConnectionSchema),
        nodes: z.array(sdkFusionGraphNodeSchema).min(1).max(1_024),
        outputs: z.array(z.string()).min(1).max(64),
    }).strict(),
    registryDigest: z.string().regex(/^sha256:[0-9a-f]{64}$/),
    schema: z.literal("cutagent.fusion.graph-request"),
    schemaVersion: z.literal(1),
}).strict();
export const sdkFusionCompositionReferenceSchema = z.object({
    id: sdkFusionCompositionIdSchema,
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    timelineItemId: sdkTimelineItemIdSchema,
    index: z.number().int().positive().max(128),
    name: z.string().min(1).max(1_024),
    projectRevision: sdkRevisionSchema,
    timelineRevision: sdkRevisionSchema,
    revision: sdkRevisionSchema,
    graphDigest: z.string().regex(/^sha256:[0-9a-f]{64}$/),
}).strict();
export const sdkFusionTextUpdateSchema = z.object({
    target: sdkFusionCompositionReferenceSchema,
    toolName: z.string().min(1).max(1_024),
    inputName: z.string().min(1).max(1_024),
    text: z.string().min(1).max(1_024),
}).strict();
const sdkFusionTextActionUpdateSchema = z.object({
    timelineItemId: sdkTimelineItemIdSchema,
    compositionIndex: z.number().int().positive().max(128),
    compositionRevision: sdkRevisionSchema,
    toolName: z.string().min(1).max(1_024),
    inputName: z.string().min(1).max(1_024),
    text: z.string().min(1).max(1_024),
}).strict();
export const sdkFusionTextActionInputSchema = z.object({
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    revision: sdkRevisionSchema,
    updates: z.array(sdkFusionTextActionUpdateSchema).min(1).max(256),
}).strict();
const sdkFusionRevisionTransitionSchema = z.object({
    revisionBefore: sdkRevisionSchema,
    revisionAfter: sdkRevisionSchema,
    changed: z.boolean(),
}).strict();
export const sdkFusionTextActionResultSchema = z.object({
    actionId: z.literal(CUTAGENT_SDK_FUSION_TEXT_ACTION_ID),
    textUpdates: z.object({
        updates: z.array(z.object({
            timelineItemId: sdkTimelineItemIdSchema,
            compositionIndex: z.number().int().positive().max(128),
            toolName: z.string().min(1).max(1_024),
            inputName: z.string().min(1).max(1_024),
            text: z.string().min(1).max(1_024),
            verified: z.literal(true),
        }).strict()).min(1).max(256),
        revision: sdkFusionRevisionTransitionSchema,
    }).strict(),
}).strict();
export const sdkFusionGraphImpactPreviewSchema = z.object({
    kind: z.literal("fusion_graph_replace"),
    target: sdkFusionCompositionReferenceSchema,
    precondition: sdkRevisionSchema,
    registryDigest: z.string().regex(/^sha256:[0-9a-f]{64}$/),
    graphDigest: z.string().regex(/^sha256:[0-9a-f]{64}$/),
    intendedEffects: z.array(z.enum(["replace_nodes", "replace_connections", "replace_inputs", "replace_animation"])).min(1).max(4),
    protectedState: z.array(z.enum(["project_identity", "timeline_identity", "timeline_item_identity", "other_timeline_items", "other_fusion_compositions"])).length(5),
    minimumEvidence: z.tuple([z.literal("readback"), z.literal("structural")]),
}).strict();
export const sdkFusionGraphApplyInputSchema = z.object({
    contractVersion: z.literal(CUTAGENT_SDK_FUSION_GRAPH_CONTRACT_VERSION),
    target: sdkFusionCompositionReferenceSchema,
    precondition: sdkRevisionSchema,
    graph: sdkFusionGraphRequestSchema,
    preview: sdkFusionGraphImpactPreviewSchema,
    idempotencyKey: sdkIdempotencyKeySchema,
}).strict().superRefine((value, context) => {
    if (value.target.revision !== value.precondition || value.preview.precondition !== value.precondition) {
        context.addIssue({ code: "custom", path: ["precondition"], message: "Fusion target and preview must share the exact live revision" });
    }
    if (value.preview.target.id !== value.target.id
        || value.preview.registryDigest !== value.graph.registryDigest) {
        context.addIssue({ code: "custom", path: ["preview"], message: "Fusion preview does not match the requested target and registry" });
    }
});
const sdkFusionReadbackNodeSchema = z.object({
    id: z.string().min(1).max(128),
    type: z.string().min(1).max(128),
    inputsDigest: z.string().regex(/^sha256:[0-9a-f]{64}$/),
}).strict();
const sdkFusionReadbackConnectionSchema = z.object({
    source: z.object({ node: z.string().min(1).max(128), port: z.string().min(1).max(128) }).strict(),
    target: z.object({ node: z.string().min(1).max(128), port: z.string().min(1).max(128) }).strict(),
}).strict();
export const sdkFusionGraphApplyResultSchema = z.object({
    target: sdkFusionCompositionReferenceSchema,
    registryDigest: z.string().regex(/^sha256:[0-9a-f]{64}$/),
    appliedGraphDigest: z.string().regex(/^sha256:[0-9a-f]{64}$/),
    readback: z.object({
        graphDigest: z.string().regex(/^sha256:[0-9a-f]{64}$/),
        nodes: z.array(sdkFusionReadbackNodeSchema).min(1).max(1_024),
        connections: z.array(sdkFusionReadbackConnectionSchema).max(4_096),
        animatedInputs: z.number().int().nonnegative().max(10_000),
    }).strict(),
    renderedEvidence: z.array(z.object({
        frame: sdkFusionFrameSchema,
        artifactId: z.string().regex(/^artifact_[A-Za-z0-9][A-Za-z0-9._~-]*$/),
        digest: z.string().regex(/^sha256:[0-9a-f]{64}$/),
        mediaType: z.literal("image/jpeg"),
    }).strict()).length(0),
    renderedReview: z.object({ outcome: z.literal("not_run") }).strict(),
    semanticReview: z.object({ outcome: z.literal("not_run") }).strict(),
    temporalReview: z.object({
        required: z.boolean(),
        sampledFrames: z.array(sdkFusionFrameSchema).length(0),
        outcome: z.literal("not_run"),
    }).strict(),
    protectedStatePreserved: z.literal(true),
}).strict();
const sdkFusionImageReplacementItemSchema = z.object({
    timelineItemId: sdkTimelineItemIdSchema,
    compositionIndex: z.number().int().positive(),
    compositionRevision: sdkRevisionSchema,
    imageArtifactId: z.string().regex(/^artifact_[A-Za-z0-9][A-Za-z0-9._~-]*$/),
    groupToolName: z.string().min(1).max(1_024).optional(),
    groupInputName: z.string().min(1).max(1_024).optional(),
    importMedia: z.boolean().optional(),
    zoom: z.object({ x: z.number().finite(), y: z.number().finite() }).strict().optional(),
    position: z.object({ x: z.number().finite(), y: z.number().finite() }).strict().optional(),
}).strict();
export const sdkFusionImageReplaceInputSchema = z.object({
    contractVersion: z.literal(CUTAGENT_SDK_FUSION_IMAGE_REPLACE_CONTRACT_VERSION),
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    revision: sdkRevisionSchema,
    items: z.array(sdkFusionImageReplacementItemSchema).min(1).max(512),
}).strict().superRefine((value, context) => {
    const ids = new Set();
    value.items.forEach((item, index) => {
        const id = `${item.timelineItemId}:fusion:${item.compositionIndex}`;
        if (ids.has(id)) {
            context.addIssue({ code: "custom", path: ["items", index], message: "Fusion image targets must be unique" });
        }
        ids.add(id);
    });
});
const sdkFusionImageReplacementSuccessSchema = z.object({
    index: z.number().int().nonnegative().max(511),
    ok: z.literal(true),
    timelineItemId: sdkTimelineItemIdSchema,
    compositionIndex: z.number().int().positive(),
    imageArtifactId: z.string().regex(/^artifact_[A-Za-z0-9][A-Za-z0-9._~-]*$/),
    durationMs: z.number().finite().nonnegative(),
    toolName: z.string().min(1).max(1_024),
    inputName: z.string().min(1).max(1_024),
    verified: z.literal(true),
    revisionBefore: sdkRevisionSchema,
    revisionAfter: sdkRevisionSchema,
}).strict();
const sdkFusionImageReplacementFailureSchema = z.object({
    index: z.number().int().nonnegative().max(511),
    ok: z.literal(false),
    timelineItemId: sdkTimelineItemIdSchema,
    compositionIndex: z.number().int().positive(),
    imageArtifactId: z.string().regex(/^artifact_[A-Za-z0-9][A-Za-z0-9._~-]*$/),
    durationMs: z.number().finite().nonnegative(),
    error: z.object({ code: z.string().min(1).max(128), message: z.string().min(1).max(4_096) }).strict(),
}).strict();
export const sdkFusionImageReplaceResultSchema = z.object({
    actionId: z.literal(CUTAGENT_SDK_FUSION_IMAGE_REPLACE_ACTION_ID),
    results: z.array(z.discriminatedUnion("ok", [
        sdkFusionImageReplacementSuccessSchema,
        sdkFusionImageReplacementFailureSchema,
    ])).min(1).max(512),
    successCount: z.number().int().nonnegative().max(512),
    failureCount: z.number().int().nonnegative().max(512),
    durationMs: z.number().finite().nonnegative(),
    protectedStatePreserved: z.literal(true),
}).strict().superRefine((value, context) => {
    if (value.successCount !== value.results.filter((row) => row.ok).length
        || value.failureCount !== value.results.filter((row) => !row.ok).length) {
        context.addIssue({ code: "custom", path: ["results"], message: "Fusion image result counts must match the per-item results" });
    }
    value.results.forEach((row, index) => {
        if (row.index !== index)
            context.addIssue({ code: "custom", path: ["results", index, "index"], message: "Fusion image results must preserve request order" });
    });
});
const sdkFusionNestedTextUpdateSchema = z.object({
    timelineItemId: sdkTimelineItemIdSchema,
    compositionIndex: z.number().int().positive().max(128),
    header: z.string().min(1).max(1_024).optional(),
    body: z.string().min(1).max(1_024).optional(),
    headerClipName: z.string().min(1).max(1_024).optional(),
    bodyClipName: z.string().min(1).max(1_024).optional(),
    headerUppercase: z.boolean().optional(),
    headerDoubleSpaces: z.boolean().optional(),
    boldStyle: z.string().min(1).max(1_024).optional(),
}).strict().refine((value) => value.header !== undefined || value.body !== undefined, {
    message: "A nested Fusion text update requires header or body text",
});
export const sdkFusionNestedTextInputSchema = z.object({
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    revision: sdkRevisionSchema,
    updates: z.array(sdkFusionNestedTextUpdateSchema).min(1).max(256),
}).strict();
const sdkFusionNestedTextSuccessSchema = z.object({
    index: z.number().int().nonnegative().max(255),
    status: z.literal("succeeded"),
    timelineItemId: sdkTimelineItemIdSchema,
    headerUpdated: z.boolean(),
    bodyUpdated: z.boolean(),
    revisionBefore: sdkRevisionSchema,
    revisionAfter: sdkRevisionSchema,
}).strict();
const sdkFusionNestedTextFailureSchema = z.object({
    index: z.number().int().nonnegative().max(255),
    status: z.literal("failed"),
    timelineItemId: sdkTimelineItemIdSchema,
    code: z.string().min(1).max(128),
    message: z.string().min(1).max(4_096),
}).strict();
export const sdkFusionNestedTextResultSchema = z.object({
    actionId: z.literal(CUTAGENT_SDK_FUSION_NESTED_TEXT_ACTION_ID),
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    revisionBefore: sdkRevisionSchema,
    revisionAfter: sdkRevisionSchema,
    changed: z.boolean(),
    successCount: z.number().int().nonnegative().max(256),
    failureCount: z.number().int().nonnegative().max(256),
    results: z.array(z.discriminatedUnion("status", [
        sdkFusionNestedTextSuccessSchema,
        sdkFusionNestedTextFailureSchema,
    ])).min(1).max(256),
    protectedStatePreserved: z.literal(true),
}).strict().superRefine((value, context) => {
    if (value.successCount + value.failureCount !== value.results.length) {
        context.addIssue({ code: "custom", path: ["results"], message: "Nested Fusion text result counts must match the returned items" });
    }
    if (value.results.some((row, index) => row.index !== index)) {
        context.addIssue({ code: "custom", path: ["results"], message: "Nested Fusion text results must preserve input order" });
    }
    if (value.changed !== value.results.some((row) => row.status === "succeeded" && (row.headerUpdated || row.bodyUpdated))) {
        context.addIssue({ code: "custom", path: ["changed"], message: "Nested Fusion text change truth must match item readback" });
    }
});
