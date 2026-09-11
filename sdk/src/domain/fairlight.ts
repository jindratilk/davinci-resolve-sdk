import { z } from "zod";
import {
  sdkFairlightClipFadeInputSchema,
  sdkFairlightClipFadeCurveInputSchema,
  sdkFairlightClipGainInputSchema,
  sdkFairlightClipPanInputSchema,
  sdkFairlightDynamicsInputSchema,
  sdkFairlightEffectInputSchema,
  sdkFairlightEqInputSchema,
  sdkFairlightLoudnessInputSchema,
  sdkFairlightPlanInputSchema,
  sdkFairlightRouteInputSchema,
  sdkFairlightSemanticResultSchema,
  sdkFairlightSynchronizeInputSchema,
  sdkFairlightTrackMixInputSchema,
} from "../generated/sdk-fairlight.js";
import type { SdkOperationEvent } from "../generated/sdk-operations.js";
import { sdkIdempotencyKeySchema } from "../generated/sdk-identities.js";
import type { CarrierOperationRequest } from "../core/carrier-contract.js";
import type { EstablishedCarrierSession } from "../core/carrier-session.js";
import { createTypedOperationHandle } from "../core/operations.js";
import type { ConnectionControlOptions } from "../core/public-client-types.js";
import type { OperationHandle } from "../protocol/operations.js";
import {
  IdempotencyKeySchema,
  ProjectIdSchema,
  RevisionSchema,
  TimelineIdSchema,
  TimelineItemIdSchema,
  TrackIndexSchema,
  type IdempotencyKey,
  type ProjectId,
  type Revision,
  type SnapshotTimelineItemId,
  type SnapshotTrackId,
  type TimelineId,
  type TimelineItemId,
  type TrackIndex,
} from "../value-types/identities.js";
import type { FrameDuration, TimelineRecordPosition, TimelineRecordRange } from "../value-types/time.js";
import { lowerDuration } from "../wire/time-adapter.js";
import type { ClipSnapshot, TimelineSnapshot } from "./object-model.js";

/** Fairlight actions exposed by the semantic audio object model. @beta */
export type FairlightActionId = "cutagent.action.sdk.fairlight.plan.apply";

/** Stable semantic kinds composed inside one Fairlight plan. @beta */
export type FairlightChangeKind = "clip_gain" | "clip_pan" | "clip_fade" | "clip_fade_curve" | "track_mix" | "routing" | "eq" | "dynamics" | "effect" | "synchronization" | "loudness";

/** One EQ band with explicit units and bounded Fairlight semantics. @beta */
export interface FairlightEqBand {
  /** One-based Fairlight band index. */
  readonly band: number;
  /** Whether this band participates in processing. */
  readonly enabled: boolean;
  /** Stable filter family. */
  readonly filterType: "low_cut" | "low_shelf" | "bell" | "high_shelf" | "high_cut";
  /** Center or cutoff frequency in hertz. */
  readonly frequencyHz: number;
  /** Band gain in decibels. */
  readonly gainDb: number;
  /** Dimensionless Q factor. */
  readonly q: number;
}

/** One dynamics processor state. @beta */
export interface FairlightDynamicsProcessor {
  /** Whether this processor participates in the dynamics chain. */
  readonly enabled: boolean;
  /** Threshold in decibels. */
  readonly thresholdDb: number;
  /** Compression/expansion ratio, or `null` when the processor has no ratio. */
  readonly ratio: number | null;
}

/** Closed dynamics state for a track. @beta */
export interface FairlightDynamics {
  /** Compressor state. */
  readonly compressor: FairlightDynamicsProcessor;
  /** Gate state. */
  readonly gate: FairlightDynamicsProcessor;
  /** Limiter state. */
  readonly limiter: FairlightDynamicsProcessor;
}

/** Truthful availability of one immutable Fairlight observation. @beta */
export type FairlightObserved<T> =
  | Readonly<{ status: "available"; value: T }>
  | Readonly<{ status: "unavailable"; reason: "readback_unavailable" | "not_exposed_by_runtime" }>;

/** Immutable clip processing state observed at the snapshot revision. @beta */
export interface FairlightClipState {
  /** Native curve control points; null means the default linear envelope. */
  readonly fadeInCurve: FairlightObserved<Readonly<{controlPoint: Readonly<{x: number; y: number}> | null}>>;
  /** Independent fade-out native curve control point. */
  readonly fadeOutCurve: FairlightObserved<Readonly<{controlPoint: Readonly<{x: number; y: number}> | null}>>;
  /** Absolute clip gain when current readback is supported. */
  readonly gainDb: FairlightObserved<number>;
  /** Normalized clip pan when current readback is supported. */
  readonly pan: FairlightObserved<number>;
  /** Fade-in duration in frames when current readback is supported. */
  readonly fadeInFrames: FairlightObserved<number>;
  /** Fade-out duration in frames when current readback is supported. */
  readonly fadeOutFrames: FairlightObserved<number>;
  /** Closed clip EQ state when current readback is supported. */
  readonly eq: FairlightObserved<Readonly<{ enabled: boolean; bands: readonly FairlightEqBand[] }>>;
  /** Ordered clip effect identities when current readback is supported. */
  readonly effects: FairlightObserved<readonly (Readonly<{ pluginId: string; presetId: string | null }>)[]>;
}

/** Immutable track mixing and processing state observed at the snapshot revision. @beta */
export interface FairlightTrackState {
  /** Absolute fader level in decibels. */
  readonly levelDb: FairlightObserved<number>;
  /** Normalized track pan from -1 left through +1 right. */
  readonly pan: FairlightObserved<number>;
  /** Current exact bus destination when routing readback is supported. */
  readonly routing: FairlightObserved<Readonly<{ busName: string; busKind: "main" | "bus" }>>;
  /** Closed dynamics state when processor readback is supported. */
  readonly dynamics: FairlightObserved<FairlightDynamics>;
  /** Current measured loudness when analysis readback is supported. */
  readonly loudness: FairlightObserved<Readonly<{ integratedLufs: number; truePeakDbtp: number }>>;
}

/** Sanitized before/after state returned by a Fairlight mutation. @beta */
export type FairlightSemanticChange =
  | Readonly<{ kind: "clip_gain"; beforeDb: number | null; afterDb: number | null }>
  | Readonly<{ kind: "clip_pan"; before: number | null; after: number | null }>
  | Readonly<{ kind: "clip_fade_curve"; direction: "in" | "out"; before: Readonly<{controlPoint: Readonly<{x: number; y: number}> | null}>; after: Readonly<{controlPoint: Readonly<{x: number; y: number}> | null}> }>
  | Readonly<{ kind: "clip_fade"; direction: "in" | "out"; beforeFrames: number | null; afterFrames: number | null }>
  | Readonly<{ kind: "track_mix"; before: Readonly<{ levelDb: number; pan: number }> | null; after: Readonly<{ levelDb: number; pan: number }> | null }>
  | Readonly<{ kind: "routing"; before: Readonly<{ busName: string; busKind: "main" | "bus" }> | null; after: Readonly<{ busName: string; busKind: "main" | "bus" }> | null }>
  | Readonly<{ kind: "eq"; before: Readonly<{ enabled: boolean; bands: readonly FairlightEqBand[] }> | null; after: Readonly<{ enabled: boolean; bands: readonly FairlightEqBand[] }> | null }>
  | Readonly<{ kind: "dynamics"; before: FairlightDynamics | null; after: FairlightDynamics | null }>
  | Readonly<{ kind: "effect"; pluginId: string; presetId: string | null; beforePresent: boolean | null; afterPresent: boolean | null }>
  | Readonly<{ kind: "synchronization"; mode: "timecode" | "waveform"; before: readonly Readonly<{ clipId: TimelineItemId; recordStartFrame: number }>[]; after: readonly Readonly<{ clipId: TimelineItemId; recordStartFrame: number }>[] }>
  | Readonly<{ kind: "loudness"; before: Readonly<{ integratedLufs: number; truePeakDbtp: number }> | null; after: Readonly<{ integratedLufs: number; truePeakDbtp: number }> | null }>;

/** Exact public-safe semantic values requested by one Fairlight preview. @beta */
export type FairlightRequestedChange =
  | Readonly<{ kind: "clip_gain"; gainDb: number }>
  | Readonly<{ kind: "clip_pan"; pan: number }>
  | Readonly<{ kind: "clip_fade_curve"; direction: "in" | "out"; curve: Readonly<{controlPoint: Readonly<{x: number; y: number}> | null}> }>
  | Readonly<{ kind: "clip_fade"; direction: "in" | "out"; durationFrames: number }>
  | Readonly<{ kind: "track_mix"; levelDb: number; pan: number }>
  | Readonly<{ kind: "routing"; destination: Readonly<{ busName: string; busKind: "main" | "bus" }> }>
  | Readonly<{ kind: "eq"; enabled: boolean; bands: readonly FairlightEqBand[] }>
  | Readonly<{ kind: "dynamics"; dynamics: FairlightDynamics }>
  | Readonly<{ kind: "effect"; pluginId: string; presetId: string | null }>
  | Readonly<{ kind: "synchronization"; mode: "timecode" | "waveform"; preserveLinkedMedia: true }>
  | Readonly<{ kind: "loudness"; integratedLufs: number; truePeakDbtp: number }>;

/** Exact named Fairlight bus reference, revision-scoped to one snapshot. @beta */
export interface FairlightBus {
  /** Snapshot-scoped identity proving this bus came from live inspection. */
  readonly snapshotId: string;
  /** Whether this is the main output or a named auxiliary bus. */
  readonly kind: "main" | "bus";
  /** Exact live bus display name; matching is never fuzzy. */
  readonly name: string;
  /** Timeline revision that scopes this reference. */
  readonly timelineRevision: Revision;
  /** Current bus processing state, with explicit unavailability for unmapped readbacks. */
  readonly state: Readonly<{
    levelDb: FairlightObserved<number>;
    pan: FairlightObserved<number>;
    loudness: FairlightObserved<Readonly<{ integratedLufs: number; truePeakDbtp: number }>>;
  }>;
}

/** Authoritative bus discovery for one Fairlight snapshot. @beta */
export type FairlightBusDirectory =
  | Readonly<{
      status: "available";
      buses: readonly FairlightBus[];
      named(name: string): FairlightBus;
    }>
  | Readonly<{
      status: "unavailable";
      reason: "readback_unavailable" | "not_exposed_by_runtime";
      buses: readonly [];
      named(name: string): never;
    }>;

/** A durable audio clip target plus semantic mutation builders. @beta */
export interface FairlightClip {
  /** Durable timeline-item identity, or `null` when this observed clip cannot safely be mutated. */
  readonly id: TimelineItemId | null;
  /** Snapshot-scoped identity for this exact clip observation. */
  readonly snapshotId: SnapshotTimelineItemId;
  /** Display name from the inspected timeline. */
  readonly name: string;
  /** One-based containing audio-track index. */
  readonly trackIndex: TrackIndex;
  /** Timeline revision that owns this clip observation. */
  readonly timelineRevision: Revision;
  /** Half-open placement range in the timeline record domain. */
  readonly recordRange: TimelineRecordRange;
  /** Exact proven linked-media identities, or `null` when topology is unavailable. */
  readonly linkedItemIds: readonly TimelineItemId[] | null;
  /** Current immutable clip processing state. Unsupported readbacks remain explicit. */
  readonly state: FairlightClipState;
  /** Preview an absolute clip gain in decibels. */
  gain(gainDb: number): FairlightImpactPreview;
  /** Preview normalized pan from -1 left through +1 right. */
  pan(pan: number): FairlightImpactPreview;
  /** Preview a frame-domain fade-in duration. */
  fadeIn(duration: FrameDuration): FairlightImpactPreview;
  /** Preview a frame-domain fade-out duration. */
  fadeOut(duration: FrameDuration): FairlightImpactPreview;
  /** Set an independent native fade control point, or null to reset to linear. Does not change duration. */
  fadeCurve(direction: "in" | "out", controlPoint: Readonly<{x: number; y: number}> | null): FairlightImpactPreview;
  /** Preview the complete bounded EQ state for this clip. */
  eq(input: { readonly enabled: boolean; readonly bands: readonly FairlightEqBand[] }): FairlightImpactPreview;
  /** Preview adding one exact runtime plug-in and optional preset. */
  addEffect(input: { readonly pluginId: string; readonly presetId?: string }): FairlightImpactPreview;
}

/** One revision-scoped audio track plus mix, routing, and dynamics builders. @beta */
export interface FairlightTrack {
  /** One-based audio-track index. */
  readonly index: TrackIndex;
  /** Snapshot-scoped track-coordinate identity. */
  readonly snapshotId: SnapshotTrackId;
  /** Display name from the inspected timeline. */
  readonly name: string;
  /** Timeline revision that owns this track observation. */
  readonly timelineRevision: Revision;
  /** Current immutable track mix and processing state. */
  readonly state: FairlightTrackState;
  /** Durable Fairlight-capable clips on this track. */
  readonly clips: readonly FairlightClip[];
  /** Resolve exactly one clip at a timeline-record position. */
  clipAt(position: TimelineRecordPosition): FairlightClip;
  /** Preview absolute fader level and pan together. */
  mix(input: { readonly levelDb: number; readonly pan: number }): FairlightImpactPreview;
  /** Preview exact routing to a revision-compatible bus. */
  routeTo(bus: FairlightBus): FairlightImpactPreview;
  /** Preview a closed compressor, gate, and limiter state. */
  dynamics(input: FairlightDynamics): FairlightImpactPreview;
}

/** Coherent audio topology derived from one immutable timeline snapshot. @beta */
export interface FairlightSnapshot {
  /** Exact containing project. */
  readonly projectId: ProjectId;
  /** Exact containing timeline. */
  readonly timelineId: TimelineId;
  /** Revision shared by every contained reference. */
  readonly revision: Revision;
  /** Whether the runtime supplied a bracketed Fairlight state readback for this revision. */
  readonly readbackStatus: "available" | "unavailable";
  /** Audio tracks in stable one-based order. */
  readonly tracks: readonly FairlightTrack[];
  /** Snapshot-observed buses, or explicit unavailability when live inspection cannot prove them. */
  readonly buses: FairlightBusDirectory;
  /** Resolve exactly one audio track by one-based index. */
  track(index: number): FairlightTrack;
  /** Preview synchronization of distinct clips while preserving linked media. */
  synchronize(clips: readonly FairlightClip[], mode: "timecode" | "waveform"): FairlightImpactPreview;
  /** Preview loudness normalization for one exact track or bus. */
  normalizeLoudness(target: FairlightTrack | FairlightBus, input: { readonly integratedLufs: number; readonly truePeakDbtp: number }): FairlightImpactPreview;
  /** Compose one or more same-revision changes into an immutable plan verified through native readback. */
  compose(changes: readonly FairlightImpactPreview[]): FairlightPlan;
}

/** Inspectable immutable Fairlight mutation plan. It contains no private command arguments. @beta */
export interface FairlightImpactPreview {
  /** Stable semantic change discriminator. */
  readonly kind: FairlightChangeKind;
  /** Exact project identity resolved at inspection. */
  readonly projectId: ProjectId;
  /** Exact timeline identity resolved at inspection. */
  readonly timelineId: TimelineId;
  /** Required mutation precondition. */
  readonly timelineRevision: Revision;
  /** Sanitized exact target identity. */
  readonly target: Readonly<
    | { kind: "clip"; clipId: TimelineItemId; trackIndex: TrackIndex }
    | { kind: "track"; trackIndex: TrackIndex }
    | { kind: "bus"; busName: string; busKind: "main" | "bus" }
    | { kind: "clips"; clips: readonly Readonly<{ clipId: TimelineItemId; trackIndex: TrackIndex }>[] }
  >;
  /** Exact sanitized semantic values that will be submitted for this target. */
  readonly requested: FairlightRequestedChange;
  /** Minimum proof contract for changed audio. */
  readonly verification: "structural_readback";
  /** Recovery is reported by the durable terminal result, never assumed client-side. */
  readonly recovery: "result_declared";
  /** Human-readable bounded intent summary. */
  readonly summary: string;
}

/** Immutable multi-change Fairlight plan with one durable aggregate outcome. @beta */
export interface FairlightPlan {
  /** Distinct SDK aggregate action; private lowering maps its steps to accepted CLI actions. */
  readonly actionId: FairlightActionId;
  /** Exact project identity shared by every change. */
  readonly projectId: ProjectId;
  /** Exact timeline identity shared by every change. */
  readonly timelineId: TimelineId;
  /** Required timeline revision shared by every change. */
  readonly timelineRevision: Revision;
  /** Ordered immutable semantic changes. */
  readonly changes: readonly FairlightImpactPreview[];
  /** Required proof scope for every changed audio result. */
  /** Linked media must be preserved across the complete plan. */
  readonly preserveLinkedMedia: true;
}

/** Semantic verified Fairlight operation result. @beta */
export interface FairlightMutationResult {
  /** Executed semantic action. */
  readonly actionId: FairlightActionId;
  /** Exact project identity inherited from the submitted plan. */
  readonly projectId: ProjectId;
  /** Exact timeline identity inherited from the submitted plan. */
  readonly timelineId: TimelineId;
  /** Truthful terminal semantic outcome. */
  readonly outcome: "succeeded" | "no_change" | "partial";
  /** Independently read post-operation timeline revision. */
  readonly timelineRevision: Revision;
  /** Exact affected clip identities. */
  readonly affectedClipIds: readonly TimelineItemId[];
  /** Exact affected one-based track indexes. */
  readonly affectedTrackIndexes: readonly TrackIndex[];
  /** Exact affected Fairlight bus identities. */
  readonly affectedBuses: readonly Readonly<{ busName: string; busKind: "main" | "bus" }>[];
  /** Ordered per-step truth, preserving partial application boundaries. */
  readonly steps: readonly Readonly<{
    stepIndex: number;
    outcome: "succeeded" | "no_change" | "partial";
    target: FairlightImpactPreview["target"];
    change: FairlightSemanticChange;
    structuralEvidenceId: string;
    auditionEvidenceId: string | null;
  }>[];
  /** Per-step structural proof plus an optional aggregate audio preview, kept distinct from the outcome. */
  readonly evidence: Readonly<{
    outcome: "passed" | "partial" | "failed" | "manual_review_required";
    structuralReadback: "passed" | "failed" | "unavailable";
    audition: Readonly<{ required: boolean; status: "not_run" | "passed" | "failed" | "unavailable" }>;
    checks: readonly Readonly<{
      evidenceId: string;
      stepIndex: number | null;
      kind: "structural_readback" | "audio_audition";
      status: "passed" | "failed" | "unavailable";
      target: FairlightImpactPreview["target"] | null;
      summary: string;
      stateDigest: string | null;
      artifact: Readonly<{ artifactId: string; sha256: string; mediaType: "audio/wav" | "audio/flac" | "audio/mp4" | "audio/mpeg" }> | null;
    }>[];
    protectedState: Readonly<{
      evidenceId: string;
      status: "passed" | "failed" | "unavailable";
      linkedMedia: "preserved" | "changed" | "unavailable";
      unexpectedChanges: boolean | null;
      stateDigest: string | null;
      summary: string;
    }>;
  }>;
  /** Explicit recovery truth for partial or uncertain work. */
  readonly recovery: Readonly<{
    state: "none" | "readback_required" | "manual_recovery_required";
    manualRecoveryRequired: boolean;
    guidance: string | null;
  }>;
}

/** Replay-safe controls for one Fairlight mutation. @beta */
export interface FairlightMutationOptions extends ConnectionControlOptions {
  /** Stable key used to reattach instead of duplicating an uncertain mutation. */
  readonly idempotencyKey: IdempotencyKey;
}

/** One exact clip gain entry for public batch composition. @beta */
export interface FairlightClipGainBatchEntry {
  /** Exact snapshot-bound clip. */
  readonly clip: FairlightClip;
  /** Absolute gain in decibels. */
  readonly gainDb: number;
}

/** One exact clip pan entry for public batch composition. @beta */
export interface FairlightClipPanBatchEntry {
  /** Exact snapshot-bound clip. */
  readonly clip: FairlightClip;
  /** Normalized pan from -1 left through +1 right. */
  readonly pan: number;
}

/** One exact clip fade entry for public batch composition. @beta */
export interface FairlightClipFadeBatchEntry {
  /** Exact snapshot-bound clip. */
  readonly clip: FairlightClip;
  /** Explicit frame-domain fade duration. */
  readonly duration: FrameDuration;
}

/** One adjacent clip pair for public crossfade composition. @beta */
export interface FairlightCrossfadeBatchEntry {
  /** Exact outgoing snapshot-bound clip. */
  readonly outgoing: FairlightClip;
  /** Exact incoming snapshot-bound clip. */
  readonly incoming: FairlightClip;
  /** Explicit frame-domain duration applied to both fades. */
  readonly duration: FrameDuration;
}

function requireBatch<T>(entries: readonly T[], name: string): readonly T[] {
  if (!Array.isArray(entries) || entries.length === 0) {
    throw new TypeError(`${name} requires at least one exact Fairlight clip.`);
  }
  if (entries.length > 1_000) throw new TypeError(`${name} may contain at most 1,000 clips.`);
  return entries;
}

function requireUniqueClips(clips: readonly FairlightClip[], name: string): void {
  const ids = clips.map((clip) => clip.id);
  if (ids.some((id) => id === null) || new Set(ids).size !== ids.length) {
    throw new TypeError(`${name} requires distinct durable Fairlight clip identities.`);
  }
}

/** Compose a verified absolute-gain plan for exact snapshot-bound clips. @beta */
export function defineFairlightGainBatch(snapshot: FairlightSnapshot, entries: readonly FairlightClipGainBatchEntry[]): FairlightPlan {
  const batch = requireBatch(entries, "Fairlight gain batch");
  requireUniqueClips(batch.map(({ clip }) => clip), "Fairlight gain batch");
  return snapshot.compose(batch.map(({ clip, gainDb }) => clip.gain(gainDb)));
}

/** Compose a verified pan plan for exact snapshot-bound clips. @beta */
export function defineFairlightPanBatch(snapshot: FairlightSnapshot, entries: readonly FairlightClipPanBatchEntry[]): FairlightPlan {
  const batch = requireBatch(entries, "Fairlight pan batch");
  requireUniqueClips(batch.map(({ clip }) => clip), "Fairlight pan batch");
  return snapshot.compose(batch.map(({ clip, pan }) => clip.pan(pan)));
}

/** Compose a verified fade-in plan for exact snapshot-bound clips. @beta */
export function defineFairlightFadeInBatch(snapshot: FairlightSnapshot, entries: readonly FairlightClipFadeBatchEntry[]): FairlightPlan {
  const batch = requireBatch(entries, "Fairlight fade-in batch");
  requireUniqueClips(batch.map(({ clip }) => clip), "Fairlight fade-in batch");
  return snapshot.compose(batch.map(({ clip, duration }) => clip.fadeIn(duration)));
}

/** Compose a verified fade-out plan for exact snapshot-bound clips. @beta */
export function defineFairlightFadeOutBatch(snapshot: FairlightSnapshot, entries: readonly FairlightClipFadeBatchEntry[]): FairlightPlan {
  const batch = requireBatch(entries, "Fairlight fade-out batch");
  requireUniqueClips(batch.map(({ clip }) => clip), "Fairlight fade-out batch");
  return snapshot.compose(batch.map(({ clip, duration }) => clip.fadeOut(duration)));
}

/** Compose paired outgoing/incoming fades as one verified Fairlight plan. @beta */
export function defineFairlightCrossfadeBatch(snapshot: FairlightSnapshot, entries: readonly FairlightCrossfadeBatchEntry[]): FairlightPlan {
  const batch = requireBatch(entries, "Fairlight crossfade batch");
  requireUniqueClips(batch.flatMap(({ outgoing, incoming }) => [outgoing, incoming]), "Fairlight crossfade batch");
  for (const { outgoing, incoming } of batch) {
    const outgoingEnd = JSON.stringify(outgoing.recordRange.endExclusive.value.toJSON());
    const incomingStart = JSON.stringify(incoming.recordRange.start.value.toJSON());
    if (outgoing.trackIndex !== incoming.trackIndex || outgoingEnd !== incomingStart) {
      throw new TypeError("Fairlight crossfade pairs must be adjacent clips on the same audio track.");
    }
  }
  return snapshot.compose(batch.flatMap(({ outgoing, incoming, duration }) => [
    outgoing.fadeOut(duration),
    incoming.fadeIn(duration),
  ]));
}

/** High-level semantic Fairlight API bound to one live timeline generation. @beta */
export interface Fairlight {
  /** Derive exact audio object references from a timeline snapshot. */
  from(snapshot: TimelineSnapshot): FairlightSnapshot;
  /** Submit a previously composed plan as one durable aggregate operation. */
  apply(plan: FairlightPlan, options: FairlightMutationOptions): Promise<OperationHandle<FairlightMutationResult, FairlightActionId>>;
}

export interface FairlightRuntime {
  sessionAtGeneration(generation: number): EstablishedCarrierSession;
  createOperationAtGeneration(generation: number, request: Parameters<EstablishedCarrierSession["operation"]>[0], options?: ConnectionControlOptions): Promise<SdkOperationEvent>;
}

type Provenance = Readonly<{
  runtime: FairlightRuntime;
  generation: number;
  projectId: ProjectId;
  timelineId: TimelineId;
  revision: Revision;
}>;
type PreviewInternal = Readonly<{ provenance: Provenance; input: Record<string, unknown> }>;
type PlanInternal = Readonly<{ provenance: Provenance; input: Record<string, unknown> }>;
type FairlightNumericReadback = Readonly<
  | { status: "available"; value: number }
  | { status: "unavailable"; reason: "readback_unavailable" | "not_exposed_by_runtime" }
>;
export type FairlightSnapshotReadback = Readonly<
  | {
      status: "available";
      tracks: readonly Readonly<{ trackIndex: number; levelDb: FairlightNumericReadback; pan: FairlightNumericReadback }>[];
      clips: readonly Readonly<{
        clipId: TimelineItemId;
        trackIndex: number;
        gainDb: FairlightNumericReadback;
        pan: FairlightNumericReadback;
        fadeInFrames: FairlightNumericReadback;
        fadeOutFrames: FairlightNumericReadback;
    fadeInCurve?: FairlightClipState["fadeInCurve"] | undefined;
    fadeOutCurve?: FairlightClipState["fadeOutCurve"] | undefined;
      }>[];
      buses: Readonly<
        | { status: "available"; buses: readonly Readonly<{ name: string; kind: "main" | "bus" }>[] }
        | { status: "unavailable"; reason: "readback_unavailable" | "not_exposed_by_runtime"; buses: readonly [] }
      >;
    }
  | {
      status: "unavailable";
      reason: "readback_unavailable" | "not_exposed_by_runtime";
      tracks: readonly [];
      buses: Readonly<{ status: "unavailable"; reason: "readback_unavailable" | "not_exposed_by_runtime"; buses: readonly [] }>;
    }
>;
const origins = new WeakMap<object, Provenance>();
const previewInternals = new WeakMap<object, PreviewInternal>();
const planInternals = new WeakMap<object, PlanInternal>();

function freeze<T extends object>(value: T): Readonly<T> {
  if (!Array.isArray(value)) Object.setPrototypeOf(value, null);
  return Object.freeze(value);
}

function deepFreeze<T>(value: T): T {
  if (value === null || typeof value !== "object" || Object.isFrozen(value)) return value;
  for (const nested of Object.values(value)) deepFreeze(nested);
  return Object.freeze(value);
}

function requestedChange(kind: FairlightChangeKind, input: Record<string, unknown>): FairlightRequestedChange {
  if (kind === "clip_gain") return deepFreeze({ kind, gainDb: input.gainDb as number });
  if (kind === "clip_pan") return deepFreeze({ kind, pan: input.pan as number });
  if (kind === "clip_fade_curve") return deepFreeze({ kind, direction: input.direction as "in" | "out", curve: input.curve as {controlPoint: {x: number; y: number} | null} });
  if (kind === "clip_fade") return deepFreeze({ kind, direction: input.direction as "in" | "out", durationFrames: input.durationFrames as number });
  if (kind === "track_mix") return deepFreeze({ kind, levelDb: input.levelDb as number, pan: input.pan as number });
  if (kind === "routing") {
    const destination = input.destination as { busName: string; busKind: "main" | "bus" };
    return deepFreeze({ kind, destination: { busName: destination.busName, busKind: destination.busKind } });
  }
  if (kind === "eq") return deepFreeze({
    kind,
    enabled: input.enabled as boolean,
    bands: (input.bands as readonly FairlightEqBand[]).map((band) => ({ ...band })),
  });
  if (kind === "dynamics") return deepFreeze({
    kind,
    dynamics: {
      compressor: { ...(input.compressor as FairlightDynamicsProcessor) },
      gate: { ...(input.gate as FairlightDynamicsProcessor) },
      limiter: { ...(input.limiter as FairlightDynamicsProcessor) },
    },
  });
  if (kind === "effect") return deepFreeze({ kind, pluginId: input.pluginId as string, presetId: (input.presetId as string | undefined) ?? null });
  if (kind === "synchronization") return deepFreeze({ kind, mode: input.mode as "timecode" | "waveform", preserveLinkedMedia: true });
  return deepFreeze({ kind: "loudness", integratedLufs: input.integratedLufs as number, truePeakDbtp: input.truePeakDbtp as number });
}

function unavailable<T>(reason: "readback_unavailable" | "not_exposed_by_runtime"): FairlightObserved<T> {
  return freeze({ status: "unavailable" as const, reason });
}

function observedNumber(value: FairlightNumericReadback | undefined, fallbackReason: "readback_unavailable" | "not_exposed_by_runtime"): FairlightObserved<number> {
  return value?.status === "available"
    ? freeze({ status: "available" as const, value: value.value })
    : unavailable(value?.reason ?? fallbackReason);
}

function provenanceOf(value: object): Provenance {
  const provenance = origins.get(value);
  if (!provenance) throw new TypeError("Fairlight references must come from timeline.fairlight.from().");
  return provenance;
}

function preview(provenance: Provenance, kind: FairlightChangeKind, target: FairlightImpactPreview["target"], input: Record<string, unknown>, summary: string): FairlightImpactPreview {
  const value = freeze({
    kind,
    projectId: provenance.projectId,
    timelineId: provenance.timelineId,
    timelineRevision: provenance.revision,
    target: freeze({ ...target }),
    requested: requestedChange(kind, input),
    verification: "structural_readback" as const,
    recovery: "result_declared" as const,
    summary,
  });
  previewInternals.set(value, { provenance, input });
  return value;
}

function sameBinding(left: Provenance, right: Provenance): boolean {
  return left.runtime === right.runtime && left.generation === right.generation && left.projectId === right.projectId
    && left.timelineId === right.timelineId && left.revision === right.revision;
}

function binding(provenance: Provenance) {
  return { projectId: provenance.projectId, timelineId: provenance.timelineId, timelineRevision: provenance.revision };
}

function exactClip(
  raw: ClipSnapshot,
  trackIndex: TrackIndex,
  provenance: Provenance,
  snapshot: TimelineSnapshot,
  readback: Readonly<{
    gainDb: FairlightNumericReadback;
    pan: FairlightNumericReadback;
    fadeInFrames: FairlightNumericReadback;
    fadeOutFrames: FairlightNumericReadback;
    fadeInCurve?: FairlightClipState["fadeInCurve"] | undefined;
    fadeOutCurve?: FairlightClipState["fadeOutCurve"] | undefined;
  }> | undefined,
  unavailableReason: "readback_unavailable" | "not_exposed_by_runtime",
): FairlightClip {
  function target() {
    if (raw.id === null || raw.linkedItemIds === null) {
      throw new TypeError("Fairlight mutation references require durable clip identity and proven linked-media topology.");
    }
    snapshot.linkedItems(raw);
    return freeze({ kind: "clip" as const, clipId: raw.id, trackIndex });
  }
  const clip: FairlightClip = {
    id: raw.id,
    snapshotId: raw.snapshotId,
    name: raw.name,
    trackIndex,
    timelineRevision: provenance.revision,
    recordRange: raw.recordRange,
    linkedItemIds: raw.linkedItemIds === null ? null : freeze([...raw.linkedItemIds]),
    state: freeze({
      gainDb: observedNumber(readback?.gainDb, unavailableReason),
      pan: observedNumber(readback?.pan, unavailableReason),
      fadeInFrames: observedNumber(readback?.fadeInFrames, unavailableReason),
      fadeOutFrames: observedNumber(readback?.fadeOutFrames, unavailableReason),
      fadeInCurve: readback?.fadeInCurve ?? unavailable(unavailableReason),
      fadeOutCurve: readback?.fadeOutCurve ?? unavailable(unavailableReason),
      eq: unavailable<Readonly<{ enabled: boolean; bands: readonly FairlightEqBand[] }>>(unavailableReason),
      effects: unavailable<readonly Readonly<{ pluginId: string; presetId: string | null }>[]>(unavailableReason),
    }),
    gain(gainDb) {
      const exactTarget = target();
      const input = sdkFairlightClipGainInputSchema.parse({ ...binding(provenance), kind: "clip_gain", target: exactTarget, gainDb });
      return preview(provenance, "clip_gain", exactTarget, input, `Set ${raw.name} gain to ${gainDb} dB.`);
    },
    pan(pan) {
      const exactTarget = target();
      const input = sdkFairlightClipPanInputSchema.parse({ ...binding(provenance), kind: "clip_pan", target: exactTarget, pan });
      return preview(provenance, "clip_pan", exactTarget, input, `Set ${raw.name} pan to ${pan}.`);
    },
    fadeCurve(direction, controlPoint) {
      const exactTarget = target();
      const input = sdkFairlightClipFadeCurveInputSchema.parse({...binding(provenance), kind: "clip_fade_curve", direction, target: exactTarget, curve: {controlPoint}});
      return preview(provenance, "clip_fade_curve", exactTarget, input, `Shape ${raw.name} fade ${direction}.`);
    },
    fadeIn(duration) { return fade("in", duration); },
    fadeOut(duration) { return fade("out", duration); },
    eq(values) {
      const exactTarget = target();
      const input = sdkFairlightEqInputSchema.parse({ ...binding(provenance), kind: "eq", target: exactTarget, enabled: values.enabled, bands: values.bands });
      return preview(provenance, "eq", exactTarget, input, `Set bounded EQ on ${raw.name}.`);
    },
    addEffect(values) {
      const exactTarget = target();
      const input = sdkFairlightEffectInputSchema.parse({ ...binding(provenance), kind: "effect", target: exactTarget, ...values });
      return preview(provenance, "effect", exactTarget, input, `Add effect ${values.pluginId} to ${raw.name}.`);
    },
  };
  function fade(direction: "in" | "out", duration: FrameDuration): FairlightImpactPreview {
    const exactTarget = target();
    const lowered = lowerDuration(duration, {});
    if (lowered.value.kind !== "frames") throw new TypeError("Fairlight fades require an explicit frame duration.");
    const input = sdkFairlightClipFadeInputSchema.parse({ ...binding(provenance), kind: "clip_fade", direction, target: exactTarget, durationFrames: lowered.value.value });
    return preview(provenance, "clip_fade", exactTarget, input, `Set ${raw.name} fade ${direction} to ${lowered.value.value} frames.`);
  }
  origins.set(clip, provenance);
  return freeze(clip);
}

function exactTrack(
  raw: TimelineSnapshot["audioTracks"][number],
  provenance: Provenance,
  snapshot: TimelineSnapshot,
  readback: Readonly<{ trackIndex: number; levelDb: FairlightNumericReadback; pan: FairlightNumericReadback }> | undefined,
  clipReadbacks: readonly Readonly<{
    clipId: TimelineItemId;
    trackIndex: number;
    gainDb: FairlightNumericReadback;
    pan: FairlightNumericReadback;
    fadeInFrames: FairlightNumericReadback;
    fadeOutFrames: FairlightNumericReadback;
    fadeInCurve?: FairlightClipState["fadeInCurve"] | undefined;
    fadeOutCurve?: FairlightClipState["fadeOutCurve"] | undefined;
  }>[],
  unavailableReason: "readback_unavailable" | "not_exposed_by_runtime",
): FairlightTrack {
  const index = TrackIndexSchema.parse(raw.index);
  const target = freeze({ kind: "track" as const, trackIndex: index });
  const clips = freeze(raw.clips.map((clip) => exactClip(
    clip,
    index,
    provenance,
    snapshot,
    clip.id === null ? undefined : clipReadbacks.find((value) => value.clipId === clip.id && value.trackIndex === index),
    unavailableReason,
  )));
  const track: FairlightTrack = {
    index,
    snapshotId: raw.snapshotId,
    name: raw.name,
    timelineRevision: provenance.revision,
    state: freeze({
      levelDb: observedNumber(readback?.levelDb, unavailableReason),
      pan: observedNumber(readback?.pan, unavailableReason),
      routing: unavailable<Readonly<{ busName: string; busKind: "main" | "bus" }>>(unavailableReason),
      dynamics: unavailable<FairlightDynamics>(unavailableReason),
      loudness: unavailable<Readonly<{ integratedLufs: number; truePeakDbtp: number }>>(unavailableReason),
    }),
    clips,
    clipAt(position) {
      const selected = raw.clipAt(position);
      const match = clips.find((clip) => clip.snapshotId === selected.snapshotId);
      if (!match) throw new TypeError("The selected audio clip is not part of this Fairlight observation.");
      return match;
    },
    mix(values) {
      const input = sdkFairlightTrackMixInputSchema.parse({ ...binding(provenance), kind: "track_mix", target, ...values });
      return preview(provenance, "track_mix", target, input, `Set track ${index} level and pan.`);
    },
    routeTo(bus) {
      const busProvenance = provenanceOf(bus);
      if (!sameBinding(busProvenance, provenance)) {
        throw new TypeError("Fairlight routing requires a bus from the same timeline revision.");
      }
      const destination = { kind: "bus" as const, busName: bus.name, busKind: bus.kind };
      const input = sdkFairlightRouteInputSchema.parse({ ...binding(provenance), kind: "routing", target, destination });
      return preview(provenance, "routing", target, input, `Route track ${index} to ${bus.name}.`);
    },
    dynamics(values) {
      const input = sdkFairlightDynamicsInputSchema.parse({ ...binding(provenance), kind: "dynamics", target, ...values });
      return preview(provenance, "dynamics", target, input, `Set closed dynamics state on track ${index}.`);
    },
  };
  origins.set(track, provenance);
  return freeze(track);
}

function orderedStrings(values: Iterable<string>): readonly string[] {
  return [...values].sort((left, right) => left.localeCompare(right));
}

function sameStrings(left: Iterable<string>, right: Iterable<string>): boolean {
  return JSON.stringify(orderedStrings(left)) === JSON.stringify(orderedStrings(right));
}

/** Validate that terminal Fairlight truth is correlated to the exact submitted immutable plan. @internal */
export function validateFairlightResultAgainstPlan(
  result: z.infer<typeof sdkFairlightSemanticResultSchema>,
  plan: FairlightPlan,
  requestedInput: unknown,
): void {
  const requestedPlan = sdkFairlightPlanInputSchema.parse(requestedInput);
  if (String(result.projectId) !== String(plan.projectId) || result.projectId !== requestedPlan.projectId
    || String(result.timelineId) !== String(plan.timelineId) || result.timelineId !== requestedPlan.timelineId) {
    throw new TypeError("Fairlight result project and timeline identities do not match the submitted plan.");
  }
  if (String(requestedPlan.timelineRevision) !== String(plan.timelineRevision)) {
    throw new TypeError("Fairlight submitted plan revision does not match its immutable authoring plan.");
  }
  if ((result.outcome === "no_change") !== (String(result.timelineRevision) === String(plan.timelineRevision))) {
    throw new TypeError("Fairlight result revision does not match its terminal mutation outcome.");
  }
  if (result.steps.length !== plan.changes.length) {
    throw new TypeError("Fairlight result step count does not match the submitted plan.");
  }

  const expectedClipIds = new Set<string>();
  const expectedTrackIndexes = new Set<string>();
  const expectedBuses = new Set<string>();
  for (const [index, step] of result.steps.entries()) {
    const planned = plan.changes[index]!;
    const requested = requestedPlan.changes[index]!;
    if (step.stepIndex !== index || step.change.kind !== planned.kind
      || JSON.stringify(step.target) !== JSON.stringify(planned.target)) {
      throw new TypeError(`Fairlight result step ${index} does not match the submitted plan.`);
    }
    const requestedEffectMatches = fairlightRequestedEffectMatches(
      step.change,
      requested,
      step.outcome === "no_change" ? "no_change" : "succeeded",
    );
    if (step.outcome !== "partial" && !requestedEffectMatches) {
      throw new TypeError(`Fairlight result step ${index} does not prove the requested effect.`);
    }
    if (step.outcome === "partial" && !requestedEffectMatches) {
      const structuralProof = result.evidence.checks.find((check) => check.evidenceId === step.structuralEvidenceId);
      if (structuralProof?.status !== "failed") {
        throw new TypeError(`Fairlight partial result step ${index} must mark a mismatched requested effect as failed proof.`);
      }
    }
    const changed = step.change.kind === "effect"
      ? step.change.beforePresent !== null && step.change.afterPresent !== null && step.change.beforePresent !== step.change.afterPresent
      : step.change.kind === "synchronization"
        ? JSON.stringify([...step.change.before].sort((left, right) => left.clipId.localeCompare(right.clipId)))
          !== JSON.stringify([...step.change.after].sort((left, right) => left.clipId.localeCompare(right.clipId)))
        : step.change.kind === "clip_gain"
          ? step.change.beforeDb !== null && step.change.afterDb !== null && step.change.beforeDb !== step.change.afterDb
          : step.change.kind === "clip_pan"
            ? step.change.before !== null && step.change.after !== null && step.change.before !== step.change.after
            : step.change.kind === "clip_fade"
              ? step.change.beforeFrames !== null && step.change.afterFrames !== null && step.change.beforeFrames !== step.change.afterFrames
              : step.change.kind === "eq"
                ? step.change.before !== null && step.change.after !== null
                  && JSON.stringify({ ...step.change.before, bands: [...step.change.before.bands].sort((left, right) => left.band - right.band) })
                    !== JSON.stringify({ ...step.change.after, bands: [...step.change.after.bands].sort((left, right) => left.band - right.band) })
              : step.change.before !== null && step.change.after !== null && JSON.stringify(step.change.before) !== JSON.stringify(step.change.after);
    if (!changed) continue;
    if (step.target.kind === "clip") {
      expectedClipIds.add(step.target.clipId);
      expectedTrackIndexes.add(String(step.target.trackIndex));
    } else if (step.target.kind === "track") {
      expectedTrackIndexes.add(String(step.target.trackIndex));
    } else if (step.target.kind === "clips") {
      for (const clip of step.target.clips) {
        expectedClipIds.add(clip.clipId);
        expectedTrackIndexes.add(String(clip.trackIndex));
      }
    } else {
      expectedBuses.add(`${step.target.busKind}:${step.target.busName}`);
    }
  }
  if (!sameStrings(result.affectedClipIds, expectedClipIds)
    || !sameStrings(result.affectedTrackIndexes.map(String), expectedTrackIndexes)
    || !sameStrings(result.affectedBuses.map((bus) => `${bus.busKind}:${bus.busName}`), expectedBuses)) {
    throw new TypeError("Fairlight result affected identities do not match its changed plan steps.");
  }
}

function fairlightRequestedEffectMatches(
  change: z.infer<typeof sdkFairlightSemanticResultSchema>["steps"][number]["change"],
  requested: z.infer<typeof sdkFairlightPlanInputSchema>["changes"][number],
  outcome: "succeeded" | "no_change",
): boolean {
  if (change.kind !== requested.kind) return false;
  const observed = outcome === "succeeded" ? "after" : "before";
  if (change.kind === "clip_gain" && requested.kind === "clip_gain") return (observed === "after" ? change.afterDb : change.beforeDb) === requested.gainDb;
  if (change.kind === "clip_pan" && requested.kind === "clip_pan") return (observed === "after" ? change.after : change.before) === requested.pan;
  if (change.kind === "clip_fade_curve" && requested.kind === "clip_fade_curve") return change.direction === requested.direction && JSON.stringify(change[observed]) === JSON.stringify(requested.curve);
  if (change.kind === "clip_fade" && requested.kind === "clip_fade") return change.direction === requested.direction && (observed === "after" ? change.afterFrames : change.beforeFrames) === requested.durationFrames;
  if (change.kind === "track_mix" && requested.kind === "track_mix") return JSON.stringify(observed === "after" ? change.after : change.before) === JSON.stringify({ levelDb: requested.levelDb, pan: requested.pan });
  if (change.kind === "routing" && requested.kind === "routing") return JSON.stringify(observed === "after" ? change.after : change.before) === JSON.stringify({ busName: requested.destination.busName, busKind: requested.destination.busKind });
  if (change.kind === "eq" && requested.kind === "eq") {
    const state = observed === "after" ? change.after : change.before;
    return state !== null && state.enabled === requested.enabled
      && JSON.stringify([...state.bands].sort((left, right) => left.band - right.band)) === JSON.stringify([...requested.bands].sort((left, right) => left.band - right.band));
  }
  if (change.kind === "dynamics" && requested.kind === "dynamics") {
    return JSON.stringify(observed === "after" ? change.after : change.before) === JSON.stringify({ compressor: requested.compressor, gate: requested.gate, limiter: requested.limiter });
  }
  if (change.kind === "effect" && requested.kind === "effect") {
    return change.pluginId === requested.pluginId && change.presetId === (requested.presetId ?? null)
      && (observed === "after" ? change.afterPresent : change.beforePresent) === true;
  }
  if (change.kind === "synchronization" && requested.kind === "synchronization") {
    const state = observed === "after" ? change.after : change.before;
    return change.mode === requested.mode && sameStrings(state.map((position) => position.clipId), requested.target.clips.map((clip) => clip.clipId));
  }
  if (change.kind === "loudness" && requested.kind === "loudness") {
    const measured = observed === "after" ? change.after : change.before;
    return measured !== null && Math.abs(measured.integratedLufs - requested.integratedLufs) <= 0.3
      && measured.truePeakDbtp <= requested.truePeakDbtp;
  }
  return false;
}

function hydrateResult(value: unknown, plan: FairlightPlan, requestedInput: unknown): FairlightMutationResult {
  const result = sdkFairlightSemanticResultSchema.parse(value);
  validateFairlightResultAgainstPlan(result, plan, requestedInput);
  const hydrateTarget = (target: (typeof result.steps)[number]["target"]): FairlightImpactPreview["target"] => {
    if (target.kind === "clip") return freeze({ kind: "clip", clipId: TimelineItemIdSchema.parse(target.clipId), trackIndex: TrackIndexSchema.parse(target.trackIndex) });
    if (target.kind === "track") return freeze({ kind: "track", trackIndex: TrackIndexSchema.parse(target.trackIndex) });
    if (target.kind === "clips") return freeze({
      kind: "clips",
      clips: freeze(target.clips.map((clip) => freeze({
        clipId: TimelineItemIdSchema.parse(clip.clipId),
        trackIndex: TrackIndexSchema.parse(clip.trackIndex),
      }))),
    });
    return freeze({ ...target });
  };
  return freeze({
    ...result,
    projectId: ProjectIdSchema.parse(result.projectId),
    timelineId: TimelineIdSchema.parse(result.timelineId),
    timelineRevision: RevisionSchema.parse(result.timelineRevision),
    affectedClipIds: freeze(result.affectedClipIds.map((id) => TimelineItemIdSchema.parse(id))),
    affectedTrackIndexes: freeze(result.affectedTrackIndexes.map((index) => TrackIndexSchema.parse(index))),
    affectedBuses: freeze(result.affectedBuses.map((bus) => freeze({ ...bus }))),
    steps: freeze(result.steps.map((step) => freeze({ ...step, target: hydrateTarget(step.target), change: deepFreeze(step.change) as FairlightSemanticChange }))),
    evidence: freeze({
      ...result.evidence,
      audition: freeze({ ...result.evidence.audition }),
      checks: freeze(result.evidence.checks.map((check) => freeze({
        ...check,
        target: check.target === null ? null : hydrateTarget(check.target),
        artifact: check.artifact === null ? null : freeze({ ...check.artifact }),
      }))),
      protectedState: freeze({ ...result.evidence.protectedState }),
    }),
    recovery: freeze({ ...result.recovery }),
  });
}

/** Construct the Fairlight facade for one exact timeline generation. @internal */
export function createFairlight(
  runtime: FairlightRuntime,
  generation: number,
  projectId: ProjectId,
  timelineId: TimelineId,
  ownsSnapshot: (snapshot: TimelineSnapshot) => boolean,
  readbackOf: (snapshot: TimelineSnapshot) => FairlightSnapshotReadback | null,
): Fairlight {
  return freeze({
    from(snapshot) {
      if (!ownsSnapshot(snapshot) || snapshot.projectId !== projectId || snapshot.timelineId !== timelineId) {
        throw new TypeError("Fairlight snapshot belongs to another project or timeline.");
      }
      const provenance: Provenance = freeze({ runtime, generation, projectId, timelineId, revision: snapshot.revision });
      const readback = readbackOf(snapshot);
      if (readback === null) throw new TypeError("Fairlight snapshot readback belongs to another client generation.");
      const unavailableReason = readback.status === "available" ? "readback_unavailable" : readback.reason;
      const tracks = freeze(snapshot.audioTracks.map((track) => exactTrack(
        track,
        provenance,
        snapshot,
        readback.status === "available" ? readback.tracks.find((value) => value.trackIndex === track.index) : undefined,
        readback.status === "available" ? readback.clips : [],
        unavailableReason,
      )));
      const buses: FairlightBusDirectory = readback.buses.status === "available"
        ? (() => {
            const observed = freeze(readback.buses.buses.map((bus, index) => {
              const value: FairlightBus = {
                snapshotId: `fairlight_bus_${snapshot.revision}_${index + 1}`,
                kind: bus.kind,
                name: bus.name,
                timelineRevision: snapshot.revision,
                state: freeze({
                  levelDb: unavailable<number>("readback_unavailable"),
                  pan: unavailable<number>("readback_unavailable"),
                  loudness: unavailable<Readonly<{ integratedLufs: number; truePeakDbtp: number }>>("readback_unavailable"),
                }),
              };
              origins.set(value, provenance);
              return freeze(value);
            }));
            return freeze({
              status: "available" as const,
              buses: observed,
              named(name: string): FairlightBus {
                const matches = observed.filter((bus) => bus.name === name);
                if (matches.length !== 1) throw new TypeError(`Fairlight bus ${name} is missing or ambiguous in this revision.`);
                return matches[0]!;
              },
            });
          })()
        : freeze({
            status: "unavailable" as const,
            reason: readback.buses.reason,
            buses: freeze([]) as readonly [],
            named(_name: string): never {
              throw new TypeError("Fairlight buses are unavailable because this timeline snapshot did not expose authoritative bus identities.");
            },
          });
      const value: FairlightSnapshot = {
        projectId,
        timelineId,
        revision: snapshot.revision,
        readbackStatus: readback.status,
        tracks,
        buses,
        track(index) {
          const exact = TrackIndexSchema.parse(index);
          const matches = tracks.filter((track) => track.index === exact);
          if (matches.length !== 1) throw new TypeError(`Fairlight audio track ${index} is missing or ambiguous in this revision.`);
          return matches[0]!;
        },
        synchronize(selected, mode) {
          const clips = selected.map((clip) => {
            const origin = provenanceOf(clip);
            if (!sameBinding(origin, provenance)) {
              throw new TypeError("Fairlight synchronization requires clips from the same live revision.");
            }
            if (clip.id === null || clip.linkedItemIds === null) {
              throw new TypeError("Fairlight synchronization requires durable clip identities and proven linked-media topology.");
            }
            const source = snapshot.audioTracks.flatMap((track) => track.clips).find((candidate) => candidate.id === clip.id);
            if (!source) throw new TypeError("Fairlight synchronization requires clips from the exact observed snapshot.");
            snapshot.linkedItems(source);
            return freeze({ clipId: clip.id, trackIndex: clip.trackIndex });
          });
          const target = freeze({ kind: "clips" as const, clips: freeze(clips) });
          const input = sdkFairlightSynchronizeInputSchema.parse({ ...binding(provenance), kind: "synchronization", target, mode, preserveLinkedMedia: true });
          return preview(provenance, "synchronization", target, input, `Synchronize ${clips.length} clips by ${mode} while preserving linked media.`);
        },
        normalizeLoudness(targetValue, values) {
          const origin = provenanceOf(targetValue);
          if (!sameBinding(origin, provenance)) {
            throw new TypeError("Fairlight loudness targets must come from the same live revision.");
          }
          const target = "index" in targetValue
            ? { kind: "track" as const, trackIndex: targetValue.index }
            : { kind: "bus" as const, busName: targetValue.name, busKind: targetValue.kind };
          const input = sdkFairlightLoudnessInputSchema.parse({ ...binding(provenance), kind: "loudness", target, ...values });
          return preview(provenance, "loudness", target, input, "Normalize the exact Fairlight target to bounded loudness and true-peak goals.");
        },
        compose(changes) {
          const inputs = changes.map((change) => {
            const internal = previewInternals.get(change);
            if (!internal || !sameBinding(internal.provenance, provenance)) {
              throw new TypeError("Every Fairlight plan change must come from this exact project, timeline, generation, and revision.");
            }
            return internal.input;
          });
          const input = sdkFairlightPlanInputSchema.parse({
            ...binding(provenance),
            changes: inputs,
            preserveLinkedMedia: true,
          });
          const plan = freeze({
            actionId: "cutagent.action.sdk.fairlight.plan.apply" as const,
            ...binding(provenance),
            changes: freeze([...changes]),
            preserveLinkedMedia: true as const,
          });
          planInternals.set(plan, { provenance, input });
          return plan;
        },
      };
      origins.set(value, provenance);
      return freeze(value);
    },
    async apply(plan, options) {
      const internal = planInternals.get(plan);
      if (!internal
        || internal.provenance.runtime !== runtime
        || internal.provenance.generation !== generation
        || internal.provenance.projectId !== projectId
        || internal.provenance.timelineId !== timelineId) {
        throw new TypeError("Fairlight mutation requires a composed plan from this client generation and timeline.");
      }
      IdempotencyKeySchema.parse(options.idempotencyKey);
      const request = {
        operation: "operation.create",
        actionId: plan.actionId,
        input: internal.input,
        idempotencyKey: sdkIdempotencyKeySchema.parse(options.idempotencyKey),
      } as CarrierOperationRequest;
      const event = await runtime.createOperationAtGeneration(generation, request, options);
      return createTypedOperationHandle(
        { session: () => runtime.sessionAtGeneration(generation) },
        event,
        plan.actionId,
        z.unknown().transform((value) => hydrateResult(value, plan, internal.input)),
      );
    },
  });
}
