import { z } from "zod";
import { sdkFusionCompositionIdSchema, sdkIdempotencyKeySchema, sdkProjectIdSchema, sdkRevisionSchema, sdkTimelineIdSchema, sdkTimelineItemIdSchema, } from "./sdk-identities.js";
export const CUTAGENT_SDK_FUSION_GRAPH_ACTION_ID = "cutagent.action.fusion.apply";
export const CUTAGENT_SDK_FUSION_GRAPH_CONTRACT_VERSION = 1;
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
