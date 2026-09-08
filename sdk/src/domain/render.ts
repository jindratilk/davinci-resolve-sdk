import type { CarrierReadRequest, CarrierReadSuccess, EstablishedCarrierSession } from "../core/carrier-session.js";
import type { CarrierOperationRequest } from "../core/carrier-contract.js";
import { createTypedOperationHandle } from "../core/operations.js";
import type { ConnectionControlOptions } from "../core/public-client-types.js";
import { sdkIdempotencyKeySchema, sdkProjectIdSchema, sdkRenderQueueCursorSchema } from "../generated/sdk-identities.js";
import { sdkRenderExportInputSchema, sdkRenderExportResultSchema, type SdkOperationEvent } from "../generated/sdk-operations.js";
import { CutAgentSdkError, PUBLIC_ERROR_KIND_BY_CODE } from "../protocol/errors.js";
import type { OperationHandle } from "../protocol/operations.js";
import {
  ArtifactIdSchema,
  IdempotencyKeySchema,
  ProjectIdSchema,
  RenderQueueCursorSchema,
  RequestIdSchema,
  RevisionSchema,
  SnapshotRenderJobIdSchema,
  type ProjectId,
  type ArtifactId,
  type IdempotencyKey,
  type RenderQueueCursor,
  type Revision,
  type SnapshotRenderJobId,
} from "../value-types/identities.js";
import type { ReadControlOptions, Timeline } from "./object-model.js";

type WireQueue = Extract<CarrierReadSuccess, { operation: "render.queue" }>["data"];
type WireJob = WireQueue["jobs"][number];

/** Known render containers and output families with stable SDK semantics. @beta */
export type KnownRenderFormat = "quicktime" | "mp4" | "mxf" | "wave" | "aiff" | "dcp" | "image_sequence";
/** Known render codec families with stable SDK semantics. @beta */
export type KnownRenderCodec = "h264" | "h265" | "prores" | "dnxhr" | "av1" | "linear_pcm" | "aac" | "flac" | "exr" | "dpx" | "tiff" | "jpeg";
/** A known semantic format or a value introduced by a newer DaVinci Resolve version. @beta */
export type RenderFormat = Readonly<{ kind: "known"; value: KnownRenderFormat }> | Readonly<{ kind: "unknown_version"; label: string }>;
/** A known semantic codec or a value introduced by a newer DaVinci Resolve version. @beta */
export type RenderCodec = Readonly<{ kind: "known"; value: KnownRenderCodec }> | Readonly<{ kind: "unknown_version"; label: string }>;
/** Capability truth for one render discovery sub-surface. @beta */
export type RenderSupport =
  | Readonly<{ availability: "supported" }>
  | Readonly<{ availability: "unavailable"; reason: "api_unavailable" | "edition_unavailable" | "temporarily_unavailable" }>
  | Readonly<{ availability: "unknown_version"; reason: "unrecognized_response" }>;
/** One supported render resolution. @beta */
export interface RenderResolution {
  /** Output width in pixels. */
  readonly width: number;
  /** Output height in pixels. */
  readonly height: number;
}
/** Codec discovery within one format. @beta */
export interface RenderCodecOption {
  /** Stable semantic codec family, or an explicit forward-version value. */
  readonly codec: RenderCodec;
  /** Display label reported by DaVinci Resolve. */
  readonly label: string;
  /** Whether resolution discovery is trustworthy for this codec. */
  readonly resolutionSupport: RenderSupport;
  /** Deduplicated supported resolutions. */
  readonly resolutions: readonly RenderResolution[];
}
/** Format discovery with its capability-aware codec and resolution inventory. @beta */
export interface RenderFormatOption {
  /** Stable semantic output family, or an explicit forward-version value. */
  readonly format: RenderFormat;
  /** Display label reported by DaVinci Resolve. */
  readonly label: string;
  /** Public filename extension when reported, without an output path. */
  readonly extension: string | null;
  /** Whether codec discovery is trustworthy for this format. */
  readonly codecSupport: RenderSupport;
  /** Capability-aware codec inventory. */
  readonly codecs: readonly RenderCodecOption[];
}
/** Immutable render format/codec/resolution discovery for one exact project. @beta */
export interface RenderDiscovery {
  /** Exact project owning this discovery snapshot. */
  readonly projectId: ProjectId;
  /** Whether format discovery is trustworthy in the active environment. */
  readonly formatSupport: RenderSupport;
  /** Bounded immutable format inventory. */
  readonly formats: readonly RenderFormatOption[];
}
/** One named DaVinci Resolve render preset. @beta */
export interface RenderPreset {
  /** Exact preset display name; reading it does not load the preset. */
  readonly name: string;
}
/** Immutable capability-aware render preset inventory. @beta */
export interface RenderPresetSnapshot {
  /** Exact project owning this preset inventory. */
  readonly projectId: ProjectId;
  /** Whether preset discovery is trustworthy in the active environment. */
  readonly support: RenderSupport;
  /** Bounded immutable preset inventory. */
  readonly presets: readonly RenderPreset[];
}
/** Current render mode, preserving values introduced by newer DaVinci Resolve versions. @beta */
export type RenderMode =
  | Readonly<{ kind: "known"; value: "individual_clips" | "single_clip" }>
  | Readonly<{ kind: "unknown_version"; value: string }>;
/** Sanitized render range, preserving uncertainty without exposing raw native settings. @beta */
export type RenderRange =
  | Readonly<{ kind: "full_timeline" }>
  | Readonly<{ kind: "custom"; markInFrame: number; markOutFrame: number }>
  | Readonly<{ kind: "unknown" }>;
/** Sanitized immutable current render settings. Raw setting dictionaries and target paths are intentionally excluded. @beta */
export interface RenderSettingsSnapshot {
  /** Exact project owning these settings. */
  readonly projectId: ProjectId;
  /** Revision of this sanitized settings projection; it is not a timeline revision. */
  readonly revision: Revision;
  /** Whether the native settings surface is available. */
  readonly support: RenderSupport;
  /** Current output format when reported. */
  readonly format: RenderFormat | null;
  /** Current codec when reported. */
  readonly codec: RenderCodec | null;
  /** Current output resolution when both dimensions are valid. */
  readonly resolution: RenderResolution | null;
  /** Current render frame rate when reported. */
  readonly frameRate: number | null;
  /** Current individual-clip or single-clip mode when reported. */
  readonly mode: RenderMode | null;
  /** Current full-timeline or custom range when it can be established safely. */
  readonly range: RenderRange;
  /** Whether video export is enabled when reported. */
  readonly exportVideo: boolean | null;
  /** Whether audio export is enabled when reported. */
  readonly exportAudio: boolean | null;
  /** Whether subtitle export is enabled when reported. */
  readonly exportSubtitles: boolean | null;
  /** Current output base name; output directories are deliberately excluded. */
  readonly customName: string | null;
  /** Number of jobs observed in the same bounded inspection. */
  readonly queueCount: number;
}
/** Current render-job status with explicit forward-version handling. @beta */
export type RenderJobStatus =
  | Readonly<{ kind: "known"; value: "queued" | "rendering" | "completed" | "failed" | "cancelled" }>
  | Readonly<{ kind: "unknown_version"; value: string }>;
/** Immutable job observation bound to one render-queue structure revision. This is not a durable SDK operation. @beta */
export interface RenderJobSnapshot {
  /** Snapshot-scoped job identity; never pass it to durable operation APIs. */
  readonly id: SnapshotRenderJobId;
  /** Exact project owning this queue snapshot. */
  readonly projectId: ProjectId;
  /** Structural queue revision that owns this job reference. */
  readonly queueRevision: Revision;
  /** One-based queue position observed in this snapshot. */
  readonly index: number;
  /** Sanitized job display name without target-directory disclosure. */
  readonly name: string;
  /** Whether per-job status readback is trustworthy in the active environment. */
  readonly statusSupport: RenderSupport;
  /** Current status or an explicit forward-version value. */
  readonly status: RenderJobStatus;
  /** Completion percentage when DaVinci Resolve reports a valid value. */
  readonly progressPercent: number | null;
  /** Refresh this job's status, failing stale if queue structure changed or the job disappeared. */
  refreshStatus(options?: ReadControlOptions): Promise<RenderJobSnapshot>;
}
/** Options for one bounded render-queue page. @beta */
export interface RenderQueueListOptions extends ReadControlOptions {
  /** Maximum jobs returned in this page; defaults to 50 and cannot exceed 100. */
  pageSize?: number;
  /** Opaque next-page cursor from the immediately preceding queue snapshot page. */
  cursor?: RenderQueueCursor;
}
/** One immutable bounded page of render jobs. @beta */
export interface RenderQueuePage {
  /** Exact project owning this queue page. */
  readonly projectId: ProjectId;
  /** Structural revision shared by every job and cursor in this page. */
  readonly queueRevision: Revision;
  /** Whether queue discovery is trustworthy in the active environment. */
  readonly support: RenderSupport;
  /** Jobs in one-based queue order. */
  readonly jobs: readonly RenderJobSnapshot[];
  /** Opaque next-page cursor, or `null` after the final page. */
  readonly nextCursor: RenderQueueCursor | null;
  /** Total jobs in this queue snapshot. */
  readonly total: number;
}
/** Stable single-file formats currently accepted by the semantic render workflow. @beta */
export type RenderMutationFormat = "quicktime" | "mp4" | "mxf" | "wave" | "aiff";
/** Stable codec families currently accepted by the semantic render workflow. @beta */
export type RenderMutationCodec = "h264" | "h265" | "prores" | "dnxhr" | "av1" | "linear_pcm" | "aac" | "flac";
/** Native settings configured before one managed render. @beta */
export interface RenderMutationSettings {
  readonly format: RenderMutationFormat;
  readonly codec: RenderMutationCodec;
  readonly width?: number;
  readonly height?: number;
  readonly frameRate?: number;
  readonly exportVideo: boolean;
  readonly exportAudio: boolean;
}
/** Exact record-domain range rendered by one managed export. End is exclusive. @beta */
export type RenderMutationRange =
  | Readonly<{ kind: "full_timeline" }>
  | Readonly<{ kind: "custom"; startFrame: number; endExclusiveFrame: number }>;
/** Semantic render request bound to an exact live timeline revision. @beta */
export interface RenderMutationRequest {
  readonly timeline: Timeline;
  readonly precondition: Revision;
  /** Defaults to the complete timeline. Custom frame positions are record-domain offsets from timeline start. */
  readonly range?: RenderMutationRange;
  /** Public base name only. CutAgent owns the approved managed destination and never accepts a filesystem path here. */
  readonly output: Readonly<{ baseName: string }>;
  readonly settings: RenderMutationSettings;
}
/** Replay-safe controls for starting a render operation. @beta */
export interface RenderMutationOptions extends ConnectionControlOptions {
  readonly idempotencyKey: IdempotencyKey;
}
/** Sanitized technical metadata independently read from the completed output. @beta */
export interface RenderArtifactMedia {
  readonly durationSeconds: number | null;
  readonly width: number | null;
  readonly height: number | null;
  readonly frameRate: number | null;
  readonly videoCodec: string | null;
  readonly audioCodec: string | null;
  readonly audioChannels: number | null;
}
/** Sanitized render artifact identity. No local output directory is exposed. @beta */
export interface RenderArtifact {
  readonly artifactId: ArtifactId;
  readonly basename: string;
  readonly extension: string;
  readonly sizeBytes: number;
  readonly sha256: `sha256:${string}`;
  /** Last instant at which the desktop-managed content remains retrievable. */
  readonly availableUntil: string;
  readonly media: RenderArtifactMedia;
  /** Read one bounded content chunk without exposing the bridge's private path. */
  readContent(options: Readonly<{ offset: number; length: number }> & ReadControlOptions): Promise<Uint8Array>;
  /** Copy and verify the complete artifact into a new caller-owned local file without overwriting. */
  copyTo(destinationPath: string, options?: ReadControlOptions): Promise<void>;
}
/** Verified terminal result for one managed native render. @beta */
export interface RenderMutationResult {
  readonly projectId: ProjectId;
  readonly timelineId: Timeline["id"];
  readonly timelineRevision: Revision;
  /** Exact public queue identity of the native job that produced `artifact`. */
  readonly job: Readonly<{ id: SnapshotRenderJobId; queueRevision: Revision }>;
  readonly artifact: RenderArtifact;
}
/** Read-only render queue for one exact project. Adding, deleting, starting, stopping, and waiting are intentionally excluded. @beta */
export interface RenderQueue {
  /** Read one bounded immutable page without mutating queue order or contents. */
  list(options?: RenderQueueListOptions): Promise<RenderQueuePage>;
}
/** Complete read-only render discovery and status surface for one exact project. @beta */
export interface ProjectRender {
  /** Discover supported formats, codecs, and resolutions without changing current settings. */
  discovery(options?: ReadControlOptions): Promise<RenderDiscovery>;
  /** List named presets without loading or changing a preset. */
  presets(options?: ReadControlOptions): Promise<RenderPresetSnapshot>;
  /** Read the sanitized current settings snapshot without exposing output paths or raw setting keys. */
  settings(options?: ReadControlOptions): Promise<RenderSettingsSnapshot>;
  /** Inspect the current render queue through bounded immutable pages. */
  readonly queue: RenderQueue;
  /** Configure, enqueue, start, monitor, and independently verify one managed render. */
  export(request: RenderMutationRequest, options: RenderMutationOptions): Promise<OperationHandle<RenderMutationResult, "cutagent.action.render.export">>;
}

interface RenderRuntime {
  sessionAtGeneration(generation: number): EstablishedCarrierSession;
  createOperationAtGeneration(
    generation: number,
    request: CarrierOperationRequest,
    options?: ConnectionControlOptions,
  ): Promise<SdkOperationEvent>;
  readAtGeneration(generation: number, request: CarrierReadRequest, options?: ReadControlOptions): Promise<CarrierReadSuccess>;
}

function invalidResponse(message: string, requestId?: string): CutAgentSdkError {
  return new CutAgentSdkError({
    kind: PUBLIC_ERROR_KIND_BY_CODE.INVALID_RESPONSE,
    code: "INVALID_RESPONSE",
    message,
    retrySafe: false,
    possibleMutation: "none",
    usage: "not_reserved",
    recovery: ["contact_support"],
    recoveryGuidance: [message],
    readbackRequired: false,
    ...(requestId ? { requestId: RequestIdSchema.parse(requestId) } : {}),
  });
}

function deepFreeze<T>(value: T): T {
  if (value === null || typeof value !== "object" || Object.isFrozen(value)) return value;
  for (const nested of Object.values(value)) deepFreeze(nested);
  return Object.freeze(value);
}

function immutableJob(runtime: RenderRuntime, generation: number, raw: WireJob): RenderJobSnapshot {
  const projectId = ProjectIdSchema.parse(raw.projectId);
  const queueRevision = RevisionSchema.parse(raw.queueRevision);
  const id = SnapshotRenderJobIdSchema.parse(raw.id);
  const wireProjectId = sdkProjectIdSchema.parse(raw.projectId);
  const wireQueueRevision = raw.queueRevision;
  const wireJobId = raw.id;
  const job: RenderJobSnapshot = {
    id,
    projectId,
    queueRevision,
    index: raw.index,
    name: raw.name,
    statusSupport: deepFreeze(raw.statusSupport),
    status: deepFreeze(raw.status),
    progressPercent: raw.progressPercent,
    async refreshStatus(options = {}) {
      const response = await runtime.readAtGeneration(generation, {
        operation: "render.job_status", projectId: wireProjectId, queueRevision: wireQueueRevision, jobId: wireJobId,
      }, options);
      if (response.operation !== "render.job_status") throw invalidResponse("CutAgent runtime returned the wrong render job status result.", response.requestId);
      if (
        response.data.projectId !== wireProjectId
        || response.data.queueRevision !== wireQueueRevision
        || response.data.job.id !== wireJobId
      ) {
        throw invalidResponse("CutAgent runtime returned render job status for a different snapshot identity.", response.requestId);
      }
      return immutableJob(runtime, generation, response.data.job);
    },
  };
  Object.setPrototypeOf(job, null);
  return deepFreeze(job);
}

function immutableArtifact(
  runtime: RenderRuntime,
  generation: number,
  raw: ReturnType<typeof sdkRenderExportResultSchema.parse>["artifact"],
): RenderArtifact {
  const artifactId = ArtifactIdSchema.parse(raw.artifactId);
  const wireArtifactId = raw.artifactId;
  const readChunk = async (offset: number, length: number, options: ReadControlOptions): Promise<Uint8Array> => {
    if (!Number.isSafeInteger(offset) || offset < 0) throw new RangeError("Artifact offset must be a non-negative safe integer.");
    if (!Number.isInteger(length) || length < 1 || length > 1024 * 1024) throw new RangeError("Artifact length must be from 1 through 1048576 bytes.");
    const response = await runtime.readAtGeneration(generation, {
      operation: "artifact.content", artifactId: wireArtifactId, offset, length,
    }, options);
    if (response.operation !== "artifact.content") throw invalidResponse("CutAgent runtime returned the wrong artifact content result.", response.requestId);
    const data = response.data;
    if (data.artifactId !== wireArtifactId || data.offset !== offset || data.totalSize !== raw.sizeBytes
      || data.sha256 !== raw.sha256 || data.availableUntil !== raw.availableUntil) {
      throw invalidResponse("CutAgent runtime returned content for a different artifact identity.", response.requestId);
    }
    return Uint8Array.from(Buffer.from(data.bytesBase64, "base64"));
  };
  const artifact: RenderArtifact = {
    ...raw,
    artifactId,
    sha256: raw.sha256 as `sha256:${string}`,
    async readContent({ offset, length, ...options }) {
      return readChunk(offset, length, options);
    },
    async copyTo(destinationPath, options = {}) {
      if (typeof destinationPath !== "string" || !path.isAbsolute(destinationPath)) {
        throw new TypeError("Artifact destinationPath must be absolute.");
      }
      let handle;
      let created = false;
      try {
        handle = await open(destinationPath, "wx+", 0o600);
        created = true;
        let offset = 0;
        while (offset < raw.sizeBytes) {
          const bytes = await readChunk(offset, Math.min(1024 * 1024, raw.sizeBytes - offset), options);
          if (bytes.length < 1 || offset + bytes.length > raw.sizeBytes) {
            throw invalidResponse("CutAgent runtime returned inconsistent artifact content.");
          }
          let written = 0;
          while (written < bytes.length) {
            const result = await handle.write(bytes, written, bytes.length - written, offset + written);
            if (!Number.isInteger(result.bytesWritten) || result.bytesWritten < 1 || result.bytesWritten > bytes.length - written) {
              throw invalidResponse("Artifact destination stopped before the verified chunk was written.");
            }
            written += result.bytesWritten;
          }
          offset += bytes.length;
        }
        await handle.sync();
        const stat = await handle.stat();
        if (stat.size !== raw.sizeBytes) throw invalidResponse("Copied artifact size did not match its verified size.");
        const hash = createHash("sha256");
        const readBuffer = Buffer.alloc(Math.min(1024 * 1024, raw.sizeBytes));
        let verifiedOffset = 0;
        while (verifiedOffset < raw.sizeBytes) {
          const requested = Math.min(readBuffer.length, raw.sizeBytes - verifiedOffset);
          const result = await handle.read(readBuffer, 0, requested, verifiedOffset);
          if (result.bytesRead !== requested) throw invalidResponse("Copied artifact ended before its verified size.");
          hash.update(readBuffer.subarray(0, result.bytesRead));
          verifiedOffset += result.bytesRead;
        }
        const digest = `sha256:${hash.digest("hex")}`;
        if (digest !== raw.sha256) throw invalidResponse("Copied artifact content did not match its verified digest.");
      } catch (error) {
        await handle?.close().catch(() => {});
        handle = undefined;
        if (created) await unlink(destinationPath).catch(() => {});
        throw error;
      } finally {
        await handle?.close();
      }
    },
  };
  Object.setPrototypeOf(artifact, null);
  return deepFreeze(artifact);
}

/** Create a project-scoped render object bound to one client generation. @internal */
export function createProjectRender(runtime: RenderRuntime, generation: number, projectIdValue: string): ProjectRender {
  const wireProjectId = sdkProjectIdSchema.parse(projectIdValue);
  const queue: RenderQueue = Object.freeze({
    async list(options: RenderQueueListOptions = {}) {
      const pageSize = options.pageSize ?? 50;
      if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > 100) {
        throw new RangeError("Render queue pageSize must be an integer from 1 through 100.");
      }
      const cursorResult = options.cursor === undefined
        ? { success: true as const, data: null }
        : sdkRenderQueueCursorSchema.safeParse(options.cursor);
      if (!cursorResult.success) throw new TypeError("Render queue cursor must be an opaque cursor returned by the preceding page.");
      const cursor = cursorResult.data;
      const response = await runtime.readAtGeneration(generation, { operation: "render.queue", projectId: wireProjectId, pageSize, cursor }, options);
      if (response.operation !== "render.queue") throw invalidResponse("CutAgent runtime returned the wrong render queue result.", response.requestId);
      if (response.data.projectId !== wireProjectId) throw invalidResponse("CutAgent runtime returned a render queue for a different project.", response.requestId);
      if (response.data.cursor !== cursor || response.data.pageSize !== pageSize) {
        throw invalidResponse("CutAgent runtime returned a render queue for different page coordinates.", response.requestId);
      }
      return deepFreeze({
        projectId: ProjectIdSchema.parse(response.data.projectId),
        queueRevision: RevisionSchema.parse(response.data.queueRevision),
        support: response.data.support,
        jobs: response.data.jobs.map((raw) => immutableJob(runtime, generation, raw)),
        nextCursor: response.data.nextCursor === null ? null : RenderQueueCursorSchema.parse(response.data.nextCursor),
        total: response.data.total,
      });
    },
  });
  const render: ProjectRender = {
    queue,
    async discovery(options = {}) {
      const response = await runtime.readAtGeneration(generation, { operation: "render.discovery", projectId: wireProjectId }, options);
      if (response.operation !== "render.discovery") throw invalidResponse("CutAgent runtime returned the wrong render discovery result.", response.requestId);
      if (response.data.projectId !== wireProjectId) throw invalidResponse("CutAgent runtime returned render discovery for a different project.", response.requestId);
      return deepFreeze({ ...response.data, projectId: ProjectIdSchema.parse(response.data.projectId) }) as RenderDiscovery;
    },
    async presets(options = {}) {
      const response = await runtime.readAtGeneration(generation, { operation: "render.presets", projectId: wireProjectId }, options);
      if (response.operation !== "render.presets") throw invalidResponse("CutAgent runtime returned the wrong render preset result.", response.requestId);
      if (response.data.projectId !== wireProjectId) throw invalidResponse("CutAgent runtime returned render presets for a different project.", response.requestId);
      return deepFreeze({ ...response.data, projectId: ProjectIdSchema.parse(response.data.projectId) }) as RenderPresetSnapshot;
    },
    async settings(options = {}) {
      const response = await runtime.readAtGeneration(generation, { operation: "render.settings", projectId: wireProjectId }, options);
      if (response.operation !== "render.settings") throw invalidResponse("CutAgent runtime returned the wrong render settings result.", response.requestId);
      if (response.data.projectId !== wireProjectId) throw invalidResponse("CutAgent runtime returned render settings for a different project.", response.requestId);
      return deepFreeze({
        ...response.data,
        projectId: ProjectIdSchema.parse(response.data.projectId),
        revision: RevisionSchema.parse(response.data.revision),
      }) as RenderSettingsSnapshot;
    },
    async export(request, options) {
      if (!request || typeof request !== "object" || !request.timeline) throw new TypeError("Render export requires an exact timeline reference.");
      if (String(request.timeline.projectId) !== wireProjectId) throw new TypeError("Render timeline belongs to a different project.");
      IdempotencyKeySchema.parse(options?.idempotencyKey);
      const input = sdkRenderExportInputSchema.parse({
        projectId: wireProjectId,
        timelineId: String(request.timeline.id),
        timelineRevision: String(RevisionSchema.parse(request.precondition)),
        range: request.range ?? { kind: "full_timeline" },
        output: request.output,
        settings: request.settings,
      });
      const operationRequest: CarrierOperationRequest = {
        operation: "operation.create",
        actionId: "cutagent.action.render.export",
        input,
        idempotencyKey: sdkIdempotencyKeySchema.parse(options.idempotencyKey),
      };
      const event = await runtime.createOperationAtGeneration(generation, operationRequest, options);
      const resultSchema = {
        parse(value: unknown): RenderMutationResult {
          const parsed = sdkRenderExportResultSchema.parse(value);
          if (parsed.projectId !== wireProjectId || parsed.timelineId !== String(request.timeline.id)) {
            throw invalidResponse("CutAgent runtime returned a render result for a different target.");
          }
          return deepFreeze({
            ...parsed,
            projectId: ProjectIdSchema.parse(parsed.projectId),
            timelineId: request.timeline.id,
            timelineRevision: RevisionSchema.parse(parsed.timelineRevision),
            job: {
              id: SnapshotRenderJobIdSchema.parse(parsed.job.id),
              queueRevision: RevisionSchema.parse(parsed.job.queueRevision),
            },
            artifact: immutableArtifact(runtime, generation, parsed.artifact),
          });
        },
      };
      return createTypedOperationHandle(
        { session: () => runtime.sessionAtGeneration(generation) },
        event,
        "cutagent.action.render.export",
        resultSchema,
      );
    },
  };
  Object.setPrototypeOf(render, null);
  return Object.freeze(render);
}
import { createHash } from "node:crypto";
import { open, unlink } from "node:fs/promises";
import path from "node:path";
