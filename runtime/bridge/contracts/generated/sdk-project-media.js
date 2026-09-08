import { z } from "zod";
import { sdkArtifactIdSchema, sdkMediaPoolFolderIdSchema, sdkMediaPoolItemIdSchema, sdkProjectIdSchema, sdkRevisionSchema, sdkSnapshotMediaPoolFolderIdSchema, sdkSnapshotMediaPoolItemIdSchema, sdkTimelineIdSchema, } from "./sdk-identities.js";
const name = z.string().min(1).max(1024);
const localPath = z.string().min(1).max(4096);
/** Exact public identity of one DaVinci Resolve project library. */
export const sdkProjectLibraryReferenceSchema = z.object({
    name,
    kind: z.enum(["disk", "postgresql"]),
}).strict();
/** Project identity as observed after a context-changing operation. */
export const sdkProjectObservationSchema = z.object({
    id: sdkProjectIdSchema.nullable(),
    name,
}).strict();
/** Exact durable project identity required for mutation targeting. */
export const sdkProjectReferenceSchema = sdkProjectObservationSchema.extend({
    id: sdkProjectIdSchema,
}).strict();
/** Timeline identity as observed after a context-changing operation. */
export const sdkTimelineObservationSchema = z.object({
    id: sdkTimelineIdSchema.nullable(),
    name,
}).strict();
/** Truthful project revision availability after a project-level operation. */
export const sdkProjectRevisionObservationSchema = z.discriminatedUnion("status", [
    z.object({ status: z.literal("available"), revision: sdkRevisionSchema }).strict(),
    z.object({ status: z.literal("unavailable") }).strict(),
]);
const projectMutationBinding = z.object({
    precondition: sdkRevisionSchema,
}).strict();
export const sdkProjectCreateInputSchema = projectMutationBinding.extend({
    name,
    mediaLocation: localPath.nullable().optional(),
}).strict();
export const sdkProjectOpenInputSchema = projectMutationBinding.extend({
    project: sdkProjectReferenceSchema,
}).strict();
export const sdkProjectBackupInputSchema = projectMutationBinding.extend({
    project: sdkProjectReferenceSchema,
    destinationArtifactId: sdkArtifactIdSchema,
    withStills: z.boolean(),
}).strict();
export const sdkProjectRestoreInputSchema = projectMutationBinding.extend({
    sourceArtifactId: sdkArtifactIdSchema,
    name,
}).strict();
export const sdkProjectLibraryCreateInputSchema = projectMutationBinding.extend({
    libraryName: name,
    directoryPath: localPath,
}).strict();
export const sdkProjectLibraryBackupInputSchema = projectMutationBinding.extend({
    library: sdkProjectLibraryReferenceSchema.extend({ kind: z.literal("disk") }).strict(),
    destinationArtifactId: sdkArtifactIdSchema,
}).strict();
export const sdkProjectLibraryRestoreInputSchema = projectMutationBinding.extend({
    sourceArtifactId: sdkArtifactIdSchema,
    libraryName: name,
    directoryPath: localPath,
}).strict();
export const sdkProjectLibraryOpenInputSchema = projectMutationBinding.extend({
    library: sdkProjectLibraryReferenceSchema.extend({ kind: z.literal("disk") }).strict(),
}).strict();
export const sdkProjectContextObservationSchema = z.object({
    library: sdkProjectLibraryReferenceSchema.nullable(),
    project: sdkProjectObservationSchema.nullable(),
    timeline: sdkTimelineObservationSchema.nullable(),
    projectRevision: sdkProjectRevisionObservationSchema,
}).strict();
export const sdkProjectContextMutationResultSchema = z.object({
    changed: z.boolean(),
    context: sdkProjectContextObservationSchema,
}).strict();
export const sdkProjectRestoreResultSchema = z.object({
    changed: z.boolean(),
    restoredProject: sdkProjectReferenceSchema,
    context: sdkProjectContextObservationSchema,
}).strict();
export const sdkProjectBackupResultSchema = z.object({
    project: sdkProjectObservationSchema,
    artifact: z.object({ kind: z.literal("project"), artifactId: sdkArtifactIdSchema }).strict(),
    projectRevision: sdkProjectRevisionObservationSchema,
}).strict();
export const sdkProjectLibraryMutationResultSchema = z.object({
    changed: z.boolean(),
    library: sdkProjectLibraryReferenceSchema,
    context: sdkProjectContextObservationSchema,
}).strict();
export const sdkProjectLibraryBackupResultSchema = z.object({
    library: sdkProjectLibraryReferenceSchema,
    artifact: z.object({ kind: z.literal("library_backup"), artifactId: sdkArtifactIdSchema }).strict(),
    context: sdkProjectContextObservationSchema,
}).strict();
export const sdkMediaPoolBinTargetSchema = z.discriminatedUnion("kind", [
    z.object({ kind: z.literal("root") }).strict(),
    z.object({ kind: z.literal("folder"), id: sdkMediaPoolFolderIdSchema }).strict(),
]);
const mediaMutationBinding = z.object({
    projectId: sdkProjectIdSchema,
    precondition: sdkRevisionSchema,
}).strict();
export const sdkMediaPoolCreateBinInputSchema = mediaMutationBinding.extend({
    parent: sdkMediaPoolBinTargetSchema,
    name,
}).strict();
export const sdkMediaPoolImportInputSchema = mediaMutationBinding.extend({
    destination: sdkMediaPoolBinTargetSchema,
    paths: z.array(localPath).min(1).max(256),
}).strict();
export const sdkMediaPoolRelinkInputSchema = mediaMutationBinding.extend({
    assetId: sdkMediaPoolItemIdSchema,
    path: localPath,
}).strict();
export const sdkMediaPoolSyncAudioInputSchema = mediaMutationBinding.extend({
    videoAssetId: sdkMediaPoolItemIdSchema,
    audioAssetIds: z.array(sdkMediaPoolItemIdSchema).min(1).max(64),
    method: z.enum(["waveform", "timecode"]),
    appendTracks: z.boolean(),
}).strict().superRefine((input, issue) => {
    if (new Set(input.audioAssetIds).size !== input.audioAssetIds.length) {
        issue.addIssue({ code: "custom", path: ["audioAssetIds"], message: "Audio asset identities must be unique." });
    }
    if (input.audioAssetIds.includes(input.videoAssetId)) {
        issue.addIssue({ code: "custom", path: ["audioAssetIds"], message: "The video asset cannot also be an audio target." });
    }
});
export const sdkMediaPoolMetadataKeySchema = z.enum([
    "description", "comments", "keywords", "shot", "scene", "take", "angle",
    "camera", "reel", "dateRecorded", "goodTake", "clipColor",
]);
export const sdkMediaPoolSetMetadataInputSchema = mediaMutationBinding.extend({
    assetId: sdkMediaPoolItemIdSchema,
    entries: z.array(z.object({
        key: sdkMediaPoolMetadataKeySchema,
        value: z.string().max(65_536),
    }).strict()).min(1).max(12).superRefine((entries, issue) => {
        if (new Set(entries.map((entry) => entry.key)).size !== entries.length) {
            issue.addIssue({ code: "custom", message: "Metadata keys must be unique." });
        }
    }),
}).strict();
const mediaIdentity = z.object({
    id: sdkMediaPoolItemIdSchema.nullable(),
    snapshotId: sdkSnapshotMediaPoolItemIdSchema,
    name,
}).strict();
export const sdkMediaPoolCreateBinResultSchema = z.object({
    projectId: sdkProjectIdSchema,
    folder: z.object({ id: sdkMediaPoolFolderIdSchema.nullable(), snapshotId: sdkSnapshotMediaPoolFolderIdSchema, name }).strict(),
    revision: sdkRevisionSchema,
}).strict();
export const sdkMediaPoolImportResultSchema = z.object({
    projectId: sdkProjectIdSchema,
    assets: z.array(mediaIdentity).min(1).max(256),
    revision: sdkRevisionSchema,
}).strict();
export const sdkMediaPoolRelinkResultSchema = z.object({
    projectId: sdkProjectIdSchema,
    asset: mediaIdentity.extend({ id: sdkMediaPoolItemIdSchema }).strict(),
    sourceFileName: z.string().min(1).max(4096).refine((value) => value !== "." && value !== ".." && !value.includes("/") && !value.includes("\\"), "Relink source file name must be a basename."),
    revision: sdkRevisionSchema,
}).strict();
export const sdkMediaPoolSyncAudioResultSchema = z.object({
    projectId: sdkProjectIdSchema,
    videoAssetId: sdkMediaPoolItemIdSchema,
    audioAssetIds: z.array(sdkMediaPoolItemIdSchema).min(1).max(64),
    syncedAsset: mediaIdentity.nullable(),
    revision: sdkRevisionSchema,
}).strict().superRefine((result, issue) => {
    if (new Set(result.audioAssetIds).size !== result.audioAssetIds.length) {
        issue.addIssue({ code: "custom", path: ["audioAssetIds"], message: "Synchronized audio asset identities must be unique." });
    }
});
export const sdkMediaPoolSetMetadataResultSchema = z.object({
    projectId: sdkProjectIdSchema,
    assetId: sdkMediaPoolItemIdSchema,
    entries: z.array(z.object({ key: sdkMediaPoolMetadataKeySchema, value: z.string().max(65_536) }).strict()).min(1).max(12),
    revision: sdkRevisionSchema,
}).strict().superRefine((result, issue) => {
    if (new Set(result.entries.map((entry) => entry.key)).size !== result.entries.length) {
        issue.addIssue({ code: "custom", path: ["entries"], message: "Metadata result keys must be unique." });
    }
});
