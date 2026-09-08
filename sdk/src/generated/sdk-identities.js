// Generated from sdk-identities.json. Do not edit.
import { z } from "zod";
export const CUTAGENT_SDK_IDENTITY_REGISTRY_VERSION = 1;
export const CUTAGENT_SDK_IDENTITY_MAX_LENGTH = 160;
export const CUTAGENT_SDK_IDENTITY_FAMILIES = [
    { name: "project", prefix: "project_", brand: "ProjectId", public: true, excludedSuffixPrefixes: [] },
    { name: "timeline", prefix: "timeline_", brand: "TimelineId", public: true, excludedSuffixPrefixes: ["item_"] },
    { name: "marker", prefix: "marker_", brand: "MarkerId", public: true, excludedSuffixPrefixes: [] },
    { name: "multicam", prefix: "multicam_", brand: "MulticamId", public: true, excludedSuffixPrefixes: ["angle_"] },
    { name: "multicam_angle", prefix: "multicam_angle_", brand: "MulticamAngleId", public: true, excludedSuffixPrefixes: [] },
    { name: "snapshot_track", prefix: "snapshot_track_", brand: "SnapshotTrackId", public: true, excludedSuffixPrefixes: [] },
    { name: "timeline_item", prefix: "timeline_item_", brand: "TimelineItemId", public: true, excludedSuffixPrefixes: [] },
    { name: "fusion_composition", prefix: "fusion_comp_", brand: "FusionCompositionId", public: true, excludedSuffixPrefixes: [] },
    { name: "snapshot_timeline_item", prefix: "snapshot_timeline_item_", brand: "SnapshotTimelineItemId", public: true, excludedSuffixPrefixes: [] },
    { name: "media_pool_folder", prefix: "media_pool_folder_", brand: "MediaPoolFolderId", public: true, excludedSuffixPrefixes: [] },
    { name: "media_pool_item", prefix: "media_pool_item_", brand: "MediaPoolItemId", public: true, excludedSuffixPrefixes: [] },
    { name: "snapshot_media_pool_folder", prefix: "snapshot_media_pool_folder_", brand: "SnapshotMediaPoolFolderId", public: true, excludedSuffixPrefixes: [] },
    { name: "snapshot_media_pool_item", prefix: "snapshot_media_pool_item_", brand: "SnapshotMediaPoolItemId", public: true, excludedSuffixPrefixes: [] },
    { name: "snapshot_render_job", prefix: "snapshot_render_job_", brand: "SnapshotRenderJobId", public: true, excludedSuffixPrefixes: [] },
    { name: "render_queue_cursor", prefix: "render_queue_cursor_", brand: "RenderQueueCursor", public: true, excludedSuffixPrefixes: [] },
    { name: "revision", prefix: "revision_", brand: "Revision", public: true, excludedSuffixPrefixes: [] },
    { name: "request", prefix: "request_", brand: "RequestId", public: true, excludedSuffixPrefixes: [] },
    { name: "connection", prefix: "connection_", brand: "ConnectionId", public: true, excludedSuffixPrefixes: [] },
    { name: "sdk_session", prefix: "sdk_session_", brand: "SdkSessionId", public: true, excludedSuffixPrefixes: [] },
    { name: "idempotency", prefix: "idempotency_", brand: "IdempotencyKey", public: true, excludedSuffixPrefixes: [] },
    { name: "operation", prefix: "operation_", brand: "OperationId", public: true, excludedSuffixPrefixes: [] },
    { name: "workflow", prefix: "workflow_", brand: "WorkflowId", public: true, excludedSuffixPrefixes: [] },
    { name: "execution", prefix: "execution_", brand: "ExecutionId", public: true, excludedSuffixPrefixes: [] },
    { name: "incident", prefix: "incident_", brand: "IncidentId", public: true, excludedSuffixPrefixes: [] },
    { name: "evidence", prefix: "evidence_", brand: "EvidenceId", public: true, excludedSuffixPrefixes: [] },
    { name: "artifact", prefix: "artifact_", brand: "ArtifactId", public: true, excludedSuffixPrefixes: [] },
    { name: "runtime_instance", prefix: "runtime_instance_", brand: "SdkRuntimeInstanceId", public: false, excludedSuffixPrefixes: [] },
    { name: "runtime_fingerprint", prefix: "runtime_fingerprint_", brand: "SdkRuntimeFingerprint", public: false, excludedSuffixPrefixes: [] },
];
const escapeRegex = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const sdkIdentity = (prefix, excludedSuffixPrefixes, brand) => {
    const exclusions = excludedSuffixPrefixes.length === 0
        ? ""
        : `(?!(?:${excludedSuffixPrefixes.map(escapeRegex).join("|")}))`;
    return z.string()
        .max(CUTAGENT_SDK_IDENTITY_MAX_LENGTH)
        .regex(new RegExp(`^${escapeRegex(prefix)}${exclusions}[A-Za-z0-9][A-Za-z0-9._~-]*$`))
        .brand(brand);
};
export const sdkProjectIdSchema = sdkIdentity("project_", [], "ProjectId");
export const sdkTimelineIdSchema = sdkIdentity("timeline_", ["item_"], "TimelineId");
export const sdkMarkerIdSchema = sdkIdentity("marker_", [], "MarkerId");
export const sdkMulticamIdSchema = sdkIdentity("multicam_", ["angle_"], "MulticamId");
export const sdkMulticamAngleIdSchema = sdkIdentity("multicam_angle_", [], "MulticamAngleId");
export const sdkSnapshotTrackIdSchema = sdkIdentity("snapshot_track_", [], "SnapshotTrackId");
export const sdkTimelineItemIdSchema = sdkIdentity("timeline_item_", [], "TimelineItemId");
export const sdkFusionCompositionIdSchema = sdkIdentity("fusion_comp_", [], "FusionCompositionId");
export const sdkSnapshotTimelineItemIdSchema = sdkIdentity("snapshot_timeline_item_", [], "SnapshotTimelineItemId");
export const sdkMediaPoolFolderIdSchema = sdkIdentity("media_pool_folder_", [], "MediaPoolFolderId");
export const sdkMediaPoolItemIdSchema = sdkIdentity("media_pool_item_", [], "MediaPoolItemId");
export const sdkSnapshotMediaPoolFolderIdSchema = sdkIdentity("snapshot_media_pool_folder_", [], "SnapshotMediaPoolFolderId");
export const sdkSnapshotMediaPoolItemIdSchema = sdkIdentity("snapshot_media_pool_item_", [], "SnapshotMediaPoolItemId");
export const sdkSnapshotRenderJobIdSchema = sdkIdentity("snapshot_render_job_", [], "SnapshotRenderJobId");
export const sdkRenderQueueCursorSchema = sdkIdentity("render_queue_cursor_", [], "RenderQueueCursor");
export const sdkRevisionSchema = sdkIdentity("revision_", [], "Revision");
export const sdkRequestIdSchema = sdkIdentity("request_", [], "RequestId");
export const sdkConnectionIdSchema = sdkIdentity("connection_", [], "ConnectionId");
export const sdkSessionIdSchema = sdkIdentity("sdk_session_", [], "SdkSessionId");
export const sdkIdempotencyKeySchema = sdkIdentity("idempotency_", [], "IdempotencyKey");
export const sdkOperationIdSchema = sdkIdentity("operation_", [], "OperationId");
export const sdkWorkflowIdSchema = sdkIdentity("workflow_", [], "WorkflowId");
export const sdkExecutionIdSchema = sdkIdentity("execution_", [], "ExecutionId");
export const sdkIncidentIdSchema = sdkIdentity("incident_", [], "IncidentId");
export const sdkEvidenceIdSchema = sdkIdentity("evidence_", [], "EvidenceId");
export const sdkArtifactIdSchema = sdkIdentity("artifact_", [], "ArtifactId");
export const sdkRuntimeInstanceIdSchema = sdkIdentity("runtime_instance_", [], "SdkRuntimeInstanceId");
export const sdkRuntimeFingerprintSchema = sdkIdentity("runtime_fingerprint_", [], "SdkRuntimeFingerprint");
