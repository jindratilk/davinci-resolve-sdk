import { z } from "zod";
import { randomUUID } from "node:crypto";
import {
  sdkArtifactIdSchema,
  sdkConnectionIdSchema,
  sdkEvidenceIdSchema,
  sdkExecutionIdSchema,
  sdkFusionCompositionIdSchema,
  sdkIdempotencyKeySchema,
  sdkIncidentIdSchema,
  sdkMediaPoolFolderIdSchema,
  sdkMediaPoolItemIdSchema,
  sdkMarkerIdSchema,
  sdkMulticamAngleIdSchema,
  sdkMulticamIdSchema,
  sdkOperationIdSchema,
  sdkProjectIdSchema,
  sdkRenderQueueCursorSchema,
  sdkRequestIdSchema,
  sdkRevisionSchema,
  sdkSessionIdSchema,
  sdkSnapshotTimelineItemIdSchema,
  sdkSnapshotMediaPoolFolderIdSchema,
  sdkSnapshotMediaPoolItemIdSchema,
  sdkSnapshotRenderJobIdSchema,
  sdkSnapshotTrackIdSchema,
  sdkTimelineIdSchema,
  sdkTimelineItemIdSchema,
  sdkWorkflowIdSchema,
} from "../generated/sdk-identities.js";

/** Opaque public string identity. The payload is never an internal native or filesystem identifier. @beta */
export type OpaqueIdentity<Name extends string> = string & z.core.$brand<Name>;

/** Opaque project identity derived from an authoritative native identifier in one stable CutAgent installation profile. @beta */
export const ProjectIdSchema = sdkProjectIdSchema as unknown as z.ZodType<ProjectId>;
/** Opaque project identity derived from an authoritative native identifier in one stable CutAgent installation profile. @beta */
export type ProjectId = OpaqueIdentity<"ProjectId">;
/** Opaque timeline identity derived from authoritative native project and timeline identifiers. @beta */
export const TimelineIdSchema = sdkTimelineIdSchema as unknown as z.ZodType<TimelineId>;
/** Opaque timeline identity derived from authoritative native project and timeline identifiers. @beta */
export type TimelineId = OpaqueIdentity<"TimelineId">;
/** Opaque identity for one exact timeline-marker observation. @beta */
export const MarkerIdSchema = sdkMarkerIdSchema as unknown as z.ZodType<MarkerId>;
/** Opaque identity for one exact timeline-marker observation. @beta */
export type MarkerId = OpaqueIdentity<"MarkerId">;
/** Opaque identity for one native multicam clip. @beta */
export const MulticamIdSchema = sdkMulticamIdSchema as unknown as z.ZodType<MulticamId>;
/** Opaque identity for one native multicam clip. @beta */
export type MulticamId = OpaqueIdentity<"MulticamId">;
/** Opaque identity for one angle within an exact native multicam clip. @beta */
export const MulticamAngleIdSchema = sdkMulticamAngleIdSchema as unknown as z.ZodType<MulticamAngleId>;
/** Opaque identity for one angle within an exact native multicam clip. @beta */
export type MulticamAngleId = OpaqueIdentity<"MulticamAngleId">;
/** Opaque identity for one track coordinate in exactly one snapshot revision. @beta */
export const SnapshotTrackIdSchema = sdkSnapshotTrackIdSchema as unknown as z.ZodType<SnapshotTrackId>;
/** Opaque identity for one track coordinate in exactly one snapshot revision. @beta */
export type SnapshotTrackId = OpaqueIdentity<"SnapshotTrackId">;
/** Opaque timeline-item identity derived only from authoritative native identity. @beta */
export const TimelineItemIdSchema = sdkTimelineItemIdSchema as unknown as z.ZodType<TimelineItemId>;
/** Opaque timeline-item identity derived only from authoritative native identity. @beta */
export type TimelineItemId = OpaqueIdentity<"TimelineItemId">;
/** Opaque identity for one exact Fusion composition on a durable timeline item. @beta */
export const FusionCompositionIdSchema = sdkFusionCompositionIdSchema as unknown as z.ZodType<FusionCompositionId>;
/** Opaque identity for one exact Fusion composition on a durable timeline item. @beta */
export type FusionCompositionId = OpaqueIdentity<"FusionCompositionId">;
/** Opaque identity for one timeline item observation in exactly one snapshot revision. @beta */
export const SnapshotTimelineItemIdSchema = sdkSnapshotTimelineItemIdSchema as unknown as z.ZodType<SnapshotTimelineItemId>;
/** Opaque identity for one timeline item observation in exactly one snapshot revision. @beta */
export type SnapshotTimelineItemId = OpaqueIdentity<"SnapshotTimelineItemId">;
/** Opaque Media Pool folder identity derived only from authoritative native identity. @beta */
export const MediaPoolFolderIdSchema = sdkMediaPoolFolderIdSchema as unknown as z.ZodType<MediaPoolFolderId>;
/** Opaque Media Pool folder identity derived only from authoritative native identity. @beta */
export type MediaPoolFolderId = OpaqueIdentity<"MediaPoolFolderId">;
/** Opaque Media Pool identity derived only from authoritative native identity. @beta */
export const MediaPoolItemIdSchema = sdkMediaPoolItemIdSchema as unknown as z.ZodType<MediaPoolItemId>;
/** Opaque Media Pool identity derived only from authoritative native identity. @beta */
export type MediaPoolItemId = OpaqueIdentity<"MediaPoolItemId">;
/** Opaque identity for one Media Pool folder observation in exactly one snapshot revision. @beta */
export const SnapshotMediaPoolFolderIdSchema = sdkSnapshotMediaPoolFolderIdSchema as unknown as z.ZodType<SnapshotMediaPoolFolderId>;
/** Opaque identity for one Media Pool folder observation in exactly one snapshot revision. @beta */
export type SnapshotMediaPoolFolderId = OpaqueIdentity<"SnapshotMediaPoolFolderId">;
/** Opaque identity for one Media Pool asset observation in exactly one snapshot revision. @beta */
export const SnapshotMediaPoolItemIdSchema = sdkSnapshotMediaPoolItemIdSchema as unknown as z.ZodType<SnapshotMediaPoolItemId>;
/** Opaque identity for one Media Pool asset observation in exactly one snapshot revision. @beta */
export type SnapshotMediaPoolItemId = OpaqueIdentity<"SnapshotMediaPoolItemId">;
/** Opaque cursor for the next page of one immutable render-queue snapshot. @beta */
export const RenderQueueCursorSchema = sdkRenderQueueCursorSchema as unknown as z.ZodType<RenderQueueCursor>;
/** Opaque cursor for the next page of one immutable render-queue snapshot. @beta */
export type RenderQueueCursor = OpaqueIdentity<"RenderQueueCursor">;
/** Snapshot-scoped render-job identity; it is never a durable SDK operation identity. @beta */
export const SnapshotRenderJobIdSchema = sdkSnapshotRenderJobIdSchema as unknown as z.ZodType<SnapshotRenderJobId>;
/** Snapshot-scoped render-job identity; it becomes stale when queue structure changes. @beta */
export type SnapshotRenderJobId = OpaqueIdentity<"SnapshotRenderJobId">;
/** Opaque live-state revision used as a mutation precondition. @beta */
export const RevisionSchema = sdkRevisionSchema as unknown as z.ZodType<Revision>;
/** Opaque live-state revision used as a mutation precondition. @beta */
export type Revision = OpaqueIdentity<"Revision">;
/** Caller-generated request identity. @beta */
export const RequestIdSchema = sdkRequestIdSchema as unknown as z.ZodType<RequestId>;
/** Caller-generated request identity. @beta */
export type RequestId = OpaqueIdentity<"RequestId">;
/** Opaque identity for one SDK client connection. @beta */
export const ConnectionIdSchema = sdkConnectionIdSchema as unknown as z.ZodType<ConnectionId>;
/** Opaque identity for one SDK client connection. @beta */
export type ConnectionId = OpaqueIdentity<"ConnectionId">;
/** Opaque identity for one runtime-backed SDK session. @beta */
export const SdkSessionIdSchema = sdkSessionIdSchema as unknown as z.ZodType<SdkSessionId>;
/** Opaque identity for one runtime-backed SDK session. @beta */
export type SdkSessionId = OpaqueIdentity<"SdkSessionId">;
/** Caller-generated idempotency key for replay-safe requests. @beta */
export const IdempotencyKeySchema = sdkIdempotencyKeySchema as unknown as z.ZodType<IdempotencyKey>;
/** Caller-generated idempotency key for replay-safe requests. @beta */
export type IdempotencyKey = OpaqueIdentity<"IdempotencyKey">;
/** Create a caller-owned replay key that can be retained across retries. @beta */
export function idempotencyKey(): IdempotencyKey {
  return IdempotencyKeySchema.parse(`idempotency_${randomUUID()}`);
}
/** Validate a caller-owned replay key retained across retries and process restarts. @beta */
export function persistedIdempotencyKey(value: string): IdempotencyKey {
  return IdempotencyKeySchema.parse(value);
}
/** Durable operation identity. @beta */
export const OperationIdSchema = sdkOperationIdSchema as unknown as z.ZodType<OperationId>;
/** Durable operation identity. @beta */
export type OperationId = OpaqueIdentity<"OperationId">;
/** Validate a durable operation identity retained across process restarts. @beta */
export function operationId(value: string): OperationId {
  return OperationIdSchema.parse(value);
}
/** Durable checkpoint workflow identity. @beta */
export const WorkflowIdSchema = sdkWorkflowIdSchema as unknown as z.ZodType<WorkflowId>;
/** Durable checkpoint workflow identity. @beta */
export type WorkflowId = OpaqueIdentity<"WorkflowId">;
/** Public execution correlation identity. @beta */
export const ExecutionIdSchema = sdkExecutionIdSchema as unknown as z.ZodType<ExecutionId>;
/** Public execution correlation identity. @beta */
export type ExecutionId = OpaqueIdentity<"ExecutionId">;
/** Public incident correlation identity. @beta */
export const IncidentIdSchema = sdkIncidentIdSchema as unknown as z.ZodType<IncidentId>;
/** Public incident correlation identity. @beta */
export type IncidentId = OpaqueIdentity<"IncidentId">;
/** Verification-evidence identity. @beta */
export const EvidenceIdSchema = sdkEvidenceIdSchema as unknown as z.ZodType<EvidenceId>;
/** Verification-evidence identity. @beta */
export type EvidenceId = OpaqueIdentity<"EvidenceId">;
/** Opaque artifact identity; it is not a filesystem path. @beta */
export const ArtifactIdSchema = sdkArtifactIdSchema as unknown as z.ZodType<ArtifactId>;
/** Opaque artifact identity; it is not a filesystem path. @beta */
export type ArtifactId = OpaqueIdentity<"ArtifactId">;
/** Validate an opaque managed-artifact identity. @beta */
export function artifactId(value: string): ArtifactId {
  return ArtifactIdSchema.parse(value);
}

/** One-based track index. Zero is always invalid. @beta */
export const TrackIndexSchema = z.number().int().min(1).max(4096).brand<"TrackIndex">() as unknown as z.ZodType<TrackIndex>;
/** One-based track index. @beta */
export type TrackIndex = number & z.core.$brand<"TrackIndex">;
/** Validate a one-based DaVinci Resolve track index for use with typed SDK APIs. @beta */
export function trackIndex(value: number): TrackIndex {
  return TrackIndexSchema.parse(value);
}
