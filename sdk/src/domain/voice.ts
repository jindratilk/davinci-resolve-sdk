import { z } from "zod";
import {
  sdkGeneratedVoiceAssetSchema,
  sdkVoiceGenerateInputSchema,
  sdkVoiceGenerateResultSchema,
  sdkVoicePlacementInputSchema,
  sdkVoicePlacementResultSchema,
  type SdkOperationEvent,
} from "../generated/sdk-operations.js";
import { sdkIdempotencyKeySchema } from "../generated/sdk-identities.js";
import { createTypedOperationHandle } from "../core/operations.js";
import type { EstablishedCarrierSession } from "../core/carrier-session.js";
import type { ConnectionControlOptions } from "../core/public-client-types.js";
import type { OperationHandle } from "../protocol/operations.js";
import {
  ArtifactIdSchema,
  IdempotencyKeySchema,
  ProjectIdSchema,
  RevisionSchema,
  TimelineIdSchema,
  type ArtifactId,
  type IdempotencyKey,
  type ProjectId,
  type Revision,
  type TimelineId,
} from "../value-types/identities.js";
import type { TimelineRecordPosition } from "../value-types/time.js";
import { hydrateTimecode, lowerTimelineRecordPosition } from "../wire/time-adapter.js";
import type { TimelineSnapshot, TrackSnapshot } from "./object-model.js";

/** Provider-neutral request for one hosted voice asset. @beta */
export interface VoiceGenerationRequest {
  /** Exact speech text; 1–10,000 Unicode characters. */
  readonly text: string;
  /** Voice identifier selected from CutAgent's hosted voice catalog. */
  readonly voiceId: string;
  /** Reviewed multilingual hosted model. */
  readonly model?: "multilingual_v2";
  /** Reviewed MP3 output profile. */
  readonly outputFormat?: "mp3_44khz_128kbps";
  /** Delivery consistency from zero through one. */
  readonly stability?: number;
  /** Source-voice similarity from zero through one. */
  readonly similarityBoost?: number;
  /** Style exaggeration from zero through one. */
  readonly style?: number;
  /** Whether the provider should apply its speaker-similarity boost. */
  readonly useSpeakerBoost?: boolean;
}

/** Required control values for replay-safe paid work. @beta */
export interface VoiceOperationOptions extends ConnectionControlOptions {
  readonly idempotencyKey: IdempotencyKey;
}

/** Stable, content-addressed voice artifact produced independently of timeline placement. @beta */
export interface GeneratedVoiceAsset {
  /** Opaque artifact identity used for subsequent placement. */
  readonly id: ArtifactId;
  /** Stable semantic artifact kind. */
  readonly kind: "generated_voice";
  /** Sanitized retained file name; no local directory is exposed. */
  readonly fileName: string;
  /** Verified media type. */
  readonly contentType: "audio/mpeg";
  /** Verified retained byte length. */
  readonly sizeBytes: number;
  /** SHA-256 digest verified from the retained bytes. */
  readonly digest: `sha256:${string}`;
  /** Measured duration when available, otherwise `null`. */
  readonly durationSeconds: number | null;
  /** Provider-neutral hosted model profile used for generation. */
  readonly model: "multilingual_v2";
  /** Encoded output profile. */
  readonly outputFormat: "mp3_44khz_128kbps";
  /** ISO timestamp at which the retained asset was created. */
  readonly createdAt: string;
}

/** Truthful billed-usage summary returned with a generated asset. @beta */
export interface VoiceGenerationResult {
  /** Retained asset available independently of any placement outcome. */
  readonly asset: GeneratedVoiceAsset;
  /** Truthful consumed hosted-usage summary. */
  readonly usage: { readonly state: "consumed"; readonly characters: number; readonly estimatedCostUsd: number | null };
}

/** One provider-neutral voice available for hosted generation. @beta */
export interface VoiceCatalogEntry {
  readonly voiceId: string;
  readonly name: string;
  readonly description: string | null;
  readonly language: string | null;
  readonly accent: string | null;
}

/** One bounded page from the hosted voice catalog. @beta */
export interface VoiceCatalogPage {
  readonly voices: readonly VoiceCatalogEntry[];
  readonly hasMore: boolean;
  readonly nextPageToken: string | null;
}

/** Exact timeline impact preview required before placing a generated voice asset. @beta */
export interface VoicePlacementPreview {
  /** Exact retained asset to place. */
  readonly asset: GeneratedVoiceAsset;
  /** Project identity observed by the preview. */
  readonly projectId: ProjectId;
  /** Timeline identity observed by the preview. */
  readonly timelineId: TimelineId;
  /** Timeline revision that must still be current at dispatch. */
  readonly timelineRevision: Revision;
  /** Exact unlocked audio track observed by the preview. */
  readonly track: TrackSnapshot;
  /** Record-domain placement position. */
  readonly position: TimelineRecordPosition;
  /** Human-readable exact-impact summary. */
  readonly summary: string;
}

/** Verified timeline placement result; generation success remains independently retained. @beta */
export interface VoicePlacementResult {
  /** Retained generated asset that was placed. */
  readonly assetId: ArtifactId;
  /** Project containing the verified placement. */
  readonly projectId: ProjectId;
  /** Timeline containing the verified placement. */
  readonly timelineId: TimelineId;
  /** Fresh timeline revision after verified placement. */
  readonly timelineRevision: Revision;
  /** One-based target audio track index. */
  readonly trackIndex: number;
  /** Absolute timeline record frame used for placement. */
  readonly recordFrame: number;
  /** Durable timeline-item identity when DaVinci Resolve proves one. */
  readonly timelineItemId: string | null;
  /** Durable Media Pool identity when DaVinci Resolve proves one. */
  readonly mediaPoolItemId: string | null;
}

/** Hosted voice generation entry point. @beta */
export interface Voice {
  /** List generation-ready voices without exposing provider internals. */
  list(options?: { readonly search?: string; readonly pageToken?: string; readonly limit?: number } & ConnectionControlOptions): Promise<VoiceCatalogPage>;
  /** Start replay-safe hosted generation; local abort never claims provider cancellation. */
  generate(request: VoiceGenerationRequest, options: VoiceOperationOptions): Promise<OperationHandle<VoiceGenerationResult, "cutagent.action.audio.voice_generate">>;
}

/** Semantic generated-voice placement bound to one exact timeline. @beta */
export interface Voiceovers {
  /** Inspect and bind one exact generated asset, audio track, position, and revision. */
  previewPlace(asset: GeneratedVoiceAsset, track: TrackSnapshot, position: TimelineRecordPosition): Promise<VoicePlacementPreview>;
  /** Start a separate replay-safe placement operation from its exact preview. */
  place(preview: VoicePlacementPreview, options: VoiceOperationOptions): Promise<OperationHandle<VoicePlacementResult, "cutagent.action.audio.voice_place">>;
}

export interface VoiceRuntime {
  sessionAtGeneration(generation: number): EstablishedCarrierSession;
  createOperationAtGeneration(
    generation: number,
    request: Parameters<EstablishedCarrierSession["operation"]>[0],
    options?: ConnectionControlOptions,
  ): Promise<SdkOperationEvent>;
}

const previewOwners = new WeakMap<object, object>();

function freeze<T extends object>(value: T): Readonly<T> {
  Object.setPrototypeOf(value, null);
  return Object.freeze(value);
}

function hydrateAsset(value: unknown): GeneratedVoiceAsset {
  const parsed = sdkGeneratedVoiceAssetSchema.parse(value);
  return freeze({ ...parsed, id: ArtifactIdSchema.parse(parsed.id), digest: parsed.digest as `sha256:${string}` });
}

function hydrateGeneration(value: unknown): VoiceGenerationResult {
  const parsed = sdkVoiceGenerateResultSchema.parse(value);
  return freeze({ asset: hydrateAsset(parsed.asset), usage: freeze(parsed.usage) });
}

function hydratePlacement(value: unknown): VoicePlacementResult {
  const parsed = sdkVoicePlacementResultSchema.parse(value);
  return freeze({
    ...parsed,
    assetId: ArtifactIdSchema.parse(parsed.assetId),
    projectId: ProjectIdSchema.parse(parsed.projectId),
    timelineId: TimelineIdSchema.parse(parsed.timelineId),
    timelineRevision: RevisionSchema.parse(parsed.timelineRevision),
  });
}

function recordFrame(position: TimelineRecordPosition, snapshot: TimelineSnapshot): number {
  const lowered = lowerTimelineRecordPosition(position, { frameRate: snapshot.frameRate });
  return lowered.value.kind === "frames" ? lowered.value.value : hydrateTimecode(lowered.value).toFrames().value;
}

/** Construct the hosted voice service for one client generation. @internal */
export function createVoice(runtime: VoiceRuntime, generation: number): Voice {
  return freeze({
    async list(options = {}) {
      const response = await runtime.sessionAtGeneration(generation).read({
        operation: "voice.catalog",
        query: {
          search: typeof options.search === "string" && options.search.trim() ? options.search.trim() : null,
          pageToken: typeof options.pageToken === "string" && options.pageToken.trim() ? options.pageToken.trim() : null,
          limit: options.limit ?? 50,
        },
      }, options);
      if (response.operation !== "voice.catalog") throw new TypeError("CutAgent returned the wrong voice catalog response.");
      return freeze({
        voices: Object.freeze(response.data.voices.map((entry) => freeze({ ...entry }))),
        hasMore: response.data.hasMore,
        nextPageToken: response.data.nextPageToken,
      });
    },
    async generate(request, options) {
      IdempotencyKeySchema.parse(options.idempotencyKey);
      const input = sdkVoiceGenerateInputSchema.parse(request);
      const event = await runtime.createOperationAtGeneration(generation, {
        operation: "operation.create",
        actionId: "cutagent.action.audio.voice_generate",
        input,
        idempotencyKey: sdkIdempotencyKeySchema.parse(options.idempotencyKey),
      }, options);
      return createTypedOperationHandle(
        { session: () => runtime.sessionAtGeneration(generation) },
        event,
        "cutagent.action.audio.voice_generate",
        z.unknown().transform(hydrateGeneration),
      );
    },
  });
}

/** Construct generated-voice placement for one exact timeline generation. @internal */
export function createVoiceovers(
  runtime: VoiceRuntime,
  generation: number,
  readSnapshot: (options?: ConnectionControlOptions) => Promise<TimelineSnapshot>,
): Voiceovers {
  const owner = Object.freeze({});
  return freeze({
    async previewPlace(asset, track, position) {
      const parsedAsset = hydrateAsset(asset);
      const snapshot = await readSnapshot();
      if (track.type !== "audio" || track.timelineId !== snapshot.timelineId || track.snapshotRevision !== snapshot.revision) {
        throw new TypeError("Voice placement requires an audio track from the current timeline snapshot.");
      }
      const currentTrack = snapshot.audioTracks.find((candidate) => candidate.snapshotId === track.snapshotId);
      if (!currentTrack || currentTrack.index !== track.index || currentTrack.locked !== false) {
        throw new TypeError("Voice placement target is stale, missing, or locked.");
      }
      const frame = recordFrame(position, snapshot);
      const preview = freeze({
        asset: parsedAsset,
        projectId: snapshot.projectId,
        timelineId: snapshot.timelineId,
        timelineRevision: snapshot.revision,
        track: currentTrack,
        position,
        summary: `Place generated voice asset ${parsedAsset.id} on audio track ${currentTrack.index} at record frame ${frame}.`,
      });
      previewOwners.set(preview, owner);
      return preview;
    },
    async place(preview, options) {
      if (previewOwners.get(preview) !== owner) throw new TypeError("Voice placement requires its matching CutAgent impact preview.");
      IdempotencyKeySchema.parse(options.idempotencyKey);
      const snapshot = await readSnapshot(options);
      if (snapshot.revision !== preview.timelineRevision) throw new TypeError("Voice placement preview is stale; inspect the timeline again.");
      const input = sdkVoicePlacementInputSchema.parse({
        assetId: preview.asset.id,
        assetDigest: preview.asset.digest,
        projectId: preview.projectId,
        timelineId: preview.timelineId,
        timelineRevision: preview.timelineRevision,
        trackIndex: preview.track.index,
        recordFrame: recordFrame(preview.position, snapshot),
      });
      const event = await runtime.createOperationAtGeneration(generation, {
        operation: "operation.create",
        actionId: "cutagent.action.audio.voice_place",
        input,
        idempotencyKey: sdkIdempotencyKeySchema.parse(options.idempotencyKey),
      }, options);
      return createTypedOperationHandle(
        { session: () => runtime.sessionAtGeneration(generation) },
        event,
        "cutagent.action.audio.voice_place",
        z.unknown().transform(hydratePlacement),
      );
    },
  });
}
