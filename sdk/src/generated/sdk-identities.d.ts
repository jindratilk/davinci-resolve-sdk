import { z } from "zod";
export declare const CUTAGENT_SDK_IDENTITY_REGISTRY_VERSION: 1;
export declare const CUTAGENT_SDK_IDENTITY_MAX_LENGTH: 160;
export declare const CUTAGENT_SDK_IDENTITY_FAMILIES: readonly [{
    readonly name: "project";
    readonly prefix: "project_";
    readonly brand: "ProjectId";
    readonly public: true;
    readonly excludedSuffixPrefixes: readonly [];
}, {
    readonly name: "timeline";
    readonly prefix: "timeline_";
    readonly brand: "TimelineId";
    readonly public: true;
    readonly excludedSuffixPrefixes: readonly ["item_"];
}, {
    readonly name: "marker";
    readonly prefix: "marker_";
    readonly brand: "MarkerId";
    readonly public: true;
    readonly excludedSuffixPrefixes: readonly [];
}, {
    readonly name: "multicam";
    readonly prefix: "multicam_";
    readonly brand: "MulticamId";
    readonly public: true;
    readonly excludedSuffixPrefixes: readonly ["angle_"];
}, {
    readonly name: "multicam_angle";
    readonly prefix: "multicam_angle_";
    readonly brand: "MulticamAngleId";
    readonly public: true;
    readonly excludedSuffixPrefixes: readonly [];
}, {
    readonly name: "snapshot_track";
    readonly prefix: "snapshot_track_";
    readonly brand: "SnapshotTrackId";
    readonly public: true;
    readonly excludedSuffixPrefixes: readonly [];
}, {
    readonly name: "timeline_item";
    readonly prefix: "timeline_item_";
    readonly brand: "TimelineItemId";
    readonly public: true;
    readonly excludedSuffixPrefixes: readonly [];
}, {
    readonly name: "fusion_composition";
    readonly prefix: "fusion_comp_";
    readonly brand: "FusionCompositionId";
    readonly public: true;
    readonly excludedSuffixPrefixes: readonly [];
}, {
    readonly name: "snapshot_timeline_item";
    readonly prefix: "snapshot_timeline_item_";
    readonly brand: "SnapshotTimelineItemId";
    readonly public: true;
    readonly excludedSuffixPrefixes: readonly [];
}, {
    readonly name: "media_pool_folder";
    readonly prefix: "media_pool_folder_";
    readonly brand: "MediaPoolFolderId";
    readonly public: true;
    readonly excludedSuffixPrefixes: readonly [];
}, {
    readonly name: "media_pool_item";
    readonly prefix: "media_pool_item_";
    readonly brand: "MediaPoolItemId";
    readonly public: true;
    readonly excludedSuffixPrefixes: readonly [];
}, {
    readonly name: "snapshot_media_pool_folder";
    readonly prefix: "snapshot_media_pool_folder_";
    readonly brand: "SnapshotMediaPoolFolderId";
    readonly public: true;
    readonly excludedSuffixPrefixes: readonly [];
}, {
    readonly name: "snapshot_media_pool_item";
    readonly prefix: "snapshot_media_pool_item_";
    readonly brand: "SnapshotMediaPoolItemId";
    readonly public: true;
    readonly excludedSuffixPrefixes: readonly [];
}, {
    readonly name: "snapshot_render_job";
    readonly prefix: "snapshot_render_job_";
    readonly brand: "SnapshotRenderJobId";
    readonly public: true;
    readonly excludedSuffixPrefixes: readonly [];
}, {
    readonly name: "render_queue_cursor";
    readonly prefix: "render_queue_cursor_";
    readonly brand: "RenderQueueCursor";
    readonly public: true;
    readonly excludedSuffixPrefixes: readonly [];
}, {
    readonly name: "revision";
    readonly prefix: "revision_";
    readonly brand: "Revision";
    readonly public: true;
    readonly excludedSuffixPrefixes: readonly [];
}, {
    readonly name: "request";
    readonly prefix: "request_";
    readonly brand: "RequestId";
    readonly public: true;
    readonly excludedSuffixPrefixes: readonly [];
}, {
    readonly name: "connection";
    readonly prefix: "connection_";
    readonly brand: "ConnectionId";
    readonly public: true;
    readonly excludedSuffixPrefixes: readonly [];
}, {
    readonly name: "sdk_session";
    readonly prefix: "sdk_session_";
    readonly brand: "SdkSessionId";
    readonly public: true;
    readonly excludedSuffixPrefixes: readonly [];
}, {
    readonly name: "idempotency";
    readonly prefix: "idempotency_";
    readonly brand: "IdempotencyKey";
    readonly public: true;
    readonly excludedSuffixPrefixes: readonly [];
}, {
    readonly name: "operation";
    readonly prefix: "operation_";
    readonly brand: "OperationId";
    readonly public: true;
    readonly excludedSuffixPrefixes: readonly [];
}, {
    readonly name: "workflow";
    readonly prefix: "workflow_";
    readonly brand: "WorkflowId";
    readonly public: true;
    readonly excludedSuffixPrefixes: readonly [];
}, {
    readonly name: "execution";
    readonly prefix: "execution_";
    readonly brand: "ExecutionId";
    readonly public: true;
    readonly excludedSuffixPrefixes: readonly [];
}, {
    readonly name: "incident";
    readonly prefix: "incident_";
    readonly brand: "IncidentId";
    readonly public: true;
    readonly excludedSuffixPrefixes: readonly [];
}, {
    readonly name: "evidence";
    readonly prefix: "evidence_";
    readonly brand: "EvidenceId";
    readonly public: true;
    readonly excludedSuffixPrefixes: readonly [];
}, {
    readonly name: "artifact";
    readonly prefix: "artifact_";
    readonly brand: "ArtifactId";
    readonly public: true;
    readonly excludedSuffixPrefixes: readonly [];
}, {
    readonly name: "runtime_instance";
    readonly prefix: "runtime_instance_";
    readonly brand: "SdkRuntimeInstanceId";
    readonly public: false;
    readonly excludedSuffixPrefixes: readonly [];
}, {
    readonly name: "runtime_fingerprint";
    readonly prefix: "runtime_fingerprint_";
    readonly brand: "SdkRuntimeFingerprint";
    readonly public: false;
    readonly excludedSuffixPrefixes: readonly [];
}];
export declare const sdkProjectIdSchema: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
export declare const sdkTimelineIdSchema: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
export declare const sdkMarkerIdSchema: z.core.$ZodBranded<z.ZodString, "MarkerId", "out">;
export declare const sdkMulticamIdSchema: z.core.$ZodBranded<z.ZodString, "MulticamId", "out">;
export declare const sdkMulticamAngleIdSchema: z.core.$ZodBranded<z.ZodString, "MulticamAngleId", "out">;
export declare const sdkSnapshotTrackIdSchema: z.core.$ZodBranded<z.ZodString, "SnapshotTrackId", "out">;
export declare const sdkTimelineItemIdSchema: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
export declare const sdkFusionCompositionIdSchema: z.core.$ZodBranded<z.ZodString, "FusionCompositionId", "out">;
export declare const sdkSnapshotTimelineItemIdSchema: z.core.$ZodBranded<z.ZodString, "SnapshotTimelineItemId", "out">;
export declare const sdkMediaPoolFolderIdSchema: z.core.$ZodBranded<z.ZodString, "MediaPoolFolderId", "out">;
export declare const sdkMediaPoolItemIdSchema: z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">;
export declare const sdkSnapshotMediaPoolFolderIdSchema: z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolFolderId", "out">;
export declare const sdkSnapshotMediaPoolItemIdSchema: z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolItemId", "out">;
export declare const sdkSnapshotRenderJobIdSchema: z.core.$ZodBranded<z.ZodString, "SnapshotRenderJobId", "out">;
export declare const sdkRenderQueueCursorSchema: z.core.$ZodBranded<z.ZodString, "RenderQueueCursor", "out">;
export declare const sdkRevisionSchema: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
export declare const sdkRequestIdSchema: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
export declare const sdkConnectionIdSchema: z.core.$ZodBranded<z.ZodString, "ConnectionId", "out">;
export declare const sdkSessionIdSchema: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
export declare const sdkIdempotencyKeySchema: z.core.$ZodBranded<z.ZodString, "IdempotencyKey", "out">;
export declare const sdkOperationIdSchema: z.core.$ZodBranded<z.ZodString, "OperationId", "out">;
export declare const sdkWorkflowIdSchema: z.core.$ZodBranded<z.ZodString, "WorkflowId", "out">;
export declare const sdkExecutionIdSchema: z.core.$ZodBranded<z.ZodString, "ExecutionId", "out">;
export declare const sdkIncidentIdSchema: z.core.$ZodBranded<z.ZodString, "IncidentId", "out">;
export declare const sdkEvidenceIdSchema: z.core.$ZodBranded<z.ZodString, "EvidenceId", "out">;
export declare const sdkArtifactIdSchema: z.core.$ZodBranded<z.ZodString, "ArtifactId", "out">;
export declare const sdkRuntimeInstanceIdSchema: z.core.$ZodBranded<z.ZodString, "SdkRuntimeInstanceId", "out">;
export declare const sdkRuntimeFingerprintSchema: z.core.$ZodBranded<z.ZodString, "SdkRuntimeFingerprint", "out">;
