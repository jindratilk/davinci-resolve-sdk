import { z } from "zod";
import { sdkMediaPoolItemIdSchema, sdkProjectIdSchema, sdkRevisionSchema, sdkSnapshotTrackIdSchema, sdkTimelineIdSchema, sdkTimelineItemIdSchema, } from "./sdk-identities.js";
const frameRangeSchema = (domain) => z.object({
    domain: z.literal(domain),
    unit: z.literal("frames"),
    start: z.number().int(),
    endExclusive: z.number().int(),
}).strict().refine((range) => range.endExclusive > range.start, { message: "Frame range must be non-empty" });
const sdkSourceRangeSchema = frameRangeSchema("source_range");
const sdkTimelineRecordRangeSchema = frameRangeSchema("timeline_record_range");
const sdkTimelineRecordTimeSchema = z.object({
    domain: z.literal("timeline_record"),
    value: z.object({ kind: z.literal("frames"), value: z.number().int() }).strict(),
}).strict();
const placementIntent = z.object({
    action: z.enum(["insert", "overwrite"]),
    placement: z.enum(["video", "audio"]).default("video"),
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    timelineRevision: sdkRevisionSchema,
    source: z.object({ id: sdkMediaPoolItemIdSchema, name: z.string().min(1).max(4096), snapshotRevision: sdkRevisionSchema }).strict(),
    sourceRange: sdkSourceRangeSchema,
    at: sdkTimelineRecordTimeSchema,
    videoTrackIndex: z.number().int().min(1).max(4096).nullable(),
    audioTrackIndex: z.number().int().min(1).max(4096).nullable(),
    linkedAudio: z.enum(["include", "exclude"]),
}).strict().superRefine((intent, context) => {
    if (intent.placement === "video" && intent.videoTrackIndex === null) {
        context.addIssue({ code: "custom", path: ["videoTrackIndex"], message: "Video placement requires a video track" });
    }
    if (intent.placement === "audio" && (intent.action !== "insert" || intent.videoTrackIndex !== null
        || intent.audioTrackIndex === null || intent.linkedAudio !== "exclude")) {
        context.addIssue({ code: "custom", message: "Audio placement must be an unlinked insert on one audio track" });
    }
});
const trimIntent = z.object({
    action: z.literal("trim"),
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    timelineRevision: sdkRevisionSchema,
    clipId: sdkTimelineItemIdSchema,
    clipName: z.string().min(1).max(4096),
    trackIndex: z.number().int().min(1).max(4096),
    currentRecordRange: sdkTimelineRecordRangeSchema,
    headFrames: z.number().int().min(0).max(2_147_483_647),
    tailFrames: z.number().int().min(0).max(2_147_483_647),
    linkedAudio: z.enum(["preserve", "exclude"]),
}).strict().refine((intent) => intent.headFrames > 0 || intent.tailFrames > 0, { message: "Trim intent must change at least one edge" });
const removeIntent = z.object({
    action: z.literal("remove"),
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    timelineRevision: sdkRevisionSchema,
    clipId: sdkTimelineItemIdSchema,
    clipName: z.string().min(1).max(4096),
    trackType: z.enum(["video", "audio", "subtitle"]),
    trackIndex: z.number().int().min(1).max(4096),
    currentRecordRange: sdkTimelineRecordRangeSchema,
    linkedItems: z.literal("exclude"),
}).strict();
export const sdkTimelineEditIntentSchema = z.discriminatedUnion("action", [placementIntent, trimIntent, removeIntent]);
const trackTarget = z.object({
    type: z.enum(["video", "audio", "subtitle"]),
    index: z.number().int().min(1).max(4096),
    snapshotId: sdkSnapshotTrackIdSchema,
}).strict();
const itemTarget = z.object({
    id: sdkTimelineItemIdSchema,
    track: trackTarget,
    recordRange: sdkTimelineRecordRangeSchema,
    role: z.enum(["replace", "trim", "remove", "linked", "protected_overlap", "protected_neighbor"]),
}).strict();
const linkTransition = z.object({
    itemId: sdkTimelineItemIdSchema,
    beforeLinkedItemIds: z.array(sdkTimelineItemIdSchema).max(4096),
    afterLinkedItemIds: z.array(sdkTimelineItemIdSchema).max(4096),
}).strict();
const expectedItem = z.object({
    role: z.enum(["replacement", "preserved_edge", "trimmed", "unlinked"]),
    beforeItemId: sdkTimelineItemIdSchema.nullable(),
    track: trackTarget,
    recordRange: sdkTimelineRecordRangeSchema,
    sourceRange: sdkSourceRangeSchema,
    sourceEndToleranceFrames: z.number().int().min(0).max(4096),
    mediaPoolItemId: sdkMediaPoolItemIdSchema,
    name: z.string().min(1).max(4096),
    linkedExpectedItemIndexes: z.array(z.number().int().nonnegative()).max(256),
    linkedExistingItemIds: z.array(sdkTimelineItemIdSchema).max(256),
}).strict();
export const sdkTimelineEditImpactSchema = z.object({
    impactId: z.string().regex(/^impact_[A-Za-z0-9_-]{16,128}$/),
    action: z.enum(["insert", "overwrite", "trim", "remove"]),
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    timelineRevision: sdkRevisionSchema,
    intent: sdkTimelineEditIntentSchema,
    recordRange: sdkTimelineRecordRangeSchema,
    affectedTracks: z.array(trackTarget).min(1).max(16),
    affectedItems: z.array(itemTarget).max(4096),
    protectedItems: z.array(itemTarget).max(4096),
    expectedItems: z.array(expectedItem).max(4096),
    expectedLinkTransitions: z.array(linkTransition).max(4096).default([]),
    linkedAudio: z.object({ behavior: z.enum(["include", "exclude", "preserve"]), topologyProven: z.boolean() }).strict(),
    capabilityId: z.enum(["edit.insert_overwrite", "edit.trim_workaround", "timeline.items_delete"]),
    summary: z.string().min(1).max(1000),
}).strict().superRefine((impact, context) => {
    if (impact.action !== impact.intent.action || impact.projectId !== impact.intent.projectId
        || impact.timelineId !== impact.intent.timelineId || impact.timelineRevision !== impact.intent.timelineRevision) {
        context.addIssue({ code: "custom", message: "Timeline edit impact must remain bound to its exact intent and revision" });
    }
    const affectedIds = new Set(impact.affectedItems.map((item) => item.id));
    if (impact.protectedItems.some((item) => affectedIds.has(item.id))) {
        context.addIssue({ code: "custom", path: ["protectedItems"], message: "Affected and protected item identities must be disjoint" });
    }
    if ((impact.action === "remove") !== (impact.expectedItems.length === 0)) {
        context.addIssue({ code: "custom", path: ["expectedItems"], message: "Remove impacts must not declare output items; other edits must declare at least one" });
    }
    impact.expectedItems.forEach((item, index) => {
        const linkedIndexes = new Set(item.linkedExpectedItemIndexes);
        if (linkedIndexes.size !== item.linkedExpectedItemIndexes.length || linkedIndexes.has(index)
            || item.linkedExpectedItemIndexes.some((linkedIndex) => linkedIndex >= impact.expectedItems.length)) {
            context.addIssue({ code: "custom", path: ["expectedItems", index, "linkedExpectedItemIndexes"], message: "Expected-item links must be unique, in range, and must not self-link" });
        }
        if (new Set(item.linkedExistingItemIds).size !== item.linkedExistingItemIds.length) {
            context.addIssue({ code: "custom", path: ["expectedItems", index, "linkedExistingItemIds"], message: "Existing linked-item identities must be unique" });
        }
        for (const linkedIndex of item.linkedExpectedItemIndexes) {
            if (!impact.expectedItems[linkedIndex]?.linkedExpectedItemIndexes.includes(index)) {
                context.addIssue({ code: "custom", path: ["expectedItems", index, "linkedExpectedItemIndexes"], message: "Expected-item links must be symmetric" });
            }
        }
    });
});
