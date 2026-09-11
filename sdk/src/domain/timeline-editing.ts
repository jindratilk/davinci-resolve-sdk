import { z } from "zod";
import type { CarrierOperationRequest, CarrierReadRequest, CarrierReadSuccess, EstablishedCarrierSession } from "../core/carrier-session.js";
import type { ConnectionControlOptions } from "../core/public-client-types.js";
import { createTypedOperationHandle } from "../core/operations.js";
import {
  sdkTimelineEditImpactSchema,
  sdkTimelineEditIntentSchema,
  type SdkTimelineEditIntent,
} from "../generated/sdk-runtime.js";
import { sdkTimelineEditMutationBatchResultSchema, sdkTimelineEditMutationResultSchema, sdkTimelineRemoveBatchMutationResultSchema, sdkTimelineRemoveMutationResultSchema, type SdkOperationEvent } from "../generated/sdk-operations.js";
import { sdkIdempotencyKeySchema } from "../generated/sdk-identities.js";
import type { OperationHandle } from "../protocol/operations.js";
import {
  IdempotencyKeySchema,
  MediaPoolItemIdSchema,
  RevisionSchema,
  TimelineItemIdSchema,
  ProjectIdSchema,
  SnapshotTrackIdSchema,
  TimelineIdSchema,
  TrackIndexSchema,
  type IdempotencyKey,
  type ProjectId,
  type Revision,
  type SnapshotTrackId,
  type TimelineId,
  type TimelineItemId,
  type TrackIndex,
} from "../value-types/identities.js";
import {
  frameRate as createFrameRate,
  type BoundFrames,
  type Duration,
  type FrameRate,
  type Frames,
  type Seconds,
  type SourceRange,
  type TimeRounding,
  type TimelineRecordPosition,
  type TimelineRecordRange,
} from "../value-types/time.js";
import {
  hydrateFrameRate,
  hydrateSourceRange,
  hydrateTimecode,
  hydrateTimelineRecordRange,
  lowerSourceRange,
  lowerTimelineRecordPosition,
} from "../wire/time-adapter.js";
import type { MediaPoolAssetSnapshot } from "./media-pool.js";
import type { ClipSnapshot, TimelineSnapshot, TimelineTrackType } from "./object-model.js";
import { freezeRecursively as freeze } from "./internal-utilities.js";

/** Accepted semantic timeline edit actions. @beta */
export type TimelineEditAction = "insert" | "overwrite" | "trim" | "remove";
/** Durable public action identities for semantic timeline edits. @beta */
export type TimelineEditActionId = "cutagent.action.edit.insert" | "cutagent.action.edit.overwrite" | "cutagent.action.edit.trim" | "cutagent.action.timeline.items.delete";

/** Exact one-based track affected by a resolved edit preview. @beta */
export interface TimelineEditTrackTarget {
  readonly type: TimelineTrackType;
  readonly index: TrackIndex;
  readonly snapshotId: SnapshotTrackId;
}

/** Exact durable clip and range affected or protected by a resolved edit preview. @beta */
export interface TimelineEditItemTarget {
  readonly id: TimelineItemId;
  readonly track: TimelineEditTrackTarget;
  readonly recordRange: TimelineRecordRange;
  readonly role: "replace" | "trim" | "remove" | "linked" | "protected_overlap" | "protected_neighbor";
}

/** Immutable runtime-resolved edit impact tied to one live timeline revision. @beta */
export interface TimelineEditImpact<TAction extends TimelineEditAction = TimelineEditAction> {
  readonly impactId: string;
  readonly action: TAction;
  readonly projectId: ProjectId;
  readonly timelineId: TimelineId;
  readonly timelineRevision: Revision;
  readonly recordRange: TimelineRecordRange;
  readonly affectedTracks: readonly TimelineEditTrackTarget[];
  readonly affectedItems: readonly TimelineEditItemTarget[];
  readonly protectedItems: readonly TimelineEditItemTarget[];
  readonly linkedAudio: Readonly<{ behavior: "include" | "exclude" | "preserve"; topologyProven: boolean }>;
  readonly capabilityId: "edit.insert_overwrite" | "edit.trim_workaround" | "timeline.items_delete";
  readonly summary: string;
}

/** Options shared by semantic edit mutations. Idempotency is mandatory. @beta */
export interface TimelineEditMutationOptions extends ConnectionControlOptions {
  readonly idempotencyKey: IdempotencyKey;
}

/** Explicit placement options used to resolve an immutable insert or overwrite preview. @beta */
export interface TimelinePlacementPreviewOptions {
  readonly at: TimelineRecordPosition;
  readonly sourceRange: SourceRange;
  readonly videoTrack: TrackIndex;
  readonly audioTrack?: TrackIndex;
  /** Explicitly include linked source audio on `audioTrack`, or place video only. */
  readonly linkedAudio: "include" | "exclude";
  /** Required when a seconds-based value is not an integral frame. */
  readonly rounding?: TimeRounding;
}

/** Exact options for inserting one audio-only Media Pool asset. @beta */
export interface TimelineAudioPlacementPreviewOptions {
  /** Exact record-domain position on the target timeline. */
  readonly at: TimelineRecordPosition;
  /** Half-open range in the source asset's time domain. */
  readonly sourceRange: SourceRange;
  /** Exact one-based audio track that must receive the item. */
  readonly audioTrack: TrackIndex;
  /** Required when a seconds-based value is not an integral frame. */
  readonly rounding?: TimeRounding;
}

/** One independently configured video placement in a plural preview. @beta */
export interface TimelinePlacementPreview {
  readonly source: MediaPoolAssetSnapshot;
  readonly options: TimelinePlacementPreviewOptions;
}

/** One independently configured audio-only placement in a plural preview. @beta */
export interface TimelineAudioPlacementPreview {
  readonly source: MediaPoolAssetSnapshot;
  readonly options: TimelineAudioPlacementPreviewOptions;
}

/** Signed edge movement used by trim previews. Positive values move inward; negative values extend outward. @beta */
export type TimelineTrimEdgeDelta = Frames | BoundFrames | Seconds;

/** Explicit edge and linked-audio policy used to resolve an immutable trim preview. @beta */
export interface TimelineTrimPreviewOptions {
  readonly head?: TimelineTrimEdgeDelta;
  readonly tail?: TimelineTrimEdgeDelta;
  /**
   * `preserve` trims an authoritatively linked video/audio relationship together.
   * `exclude` trims video alone and requires the linked audio state to remain protected.
   */
  readonly linkedAudio: "preserve" | "exclude";
  /** Required when a seconds-based duration is not an integral frame. */
  readonly rounding?: TimeRounding;
}

/** One independently configured trim target in a plural preview. @beta */
export interface TimelineTrimPreview {
  readonly clip: ClipSnapshot;
  readonly options: TimelineTrimPreviewOptions;
}

/** Explicit non-ripple policy for removing one exact timeline item. @beta */
export interface TimelineRemovePreviewOptions {
  /** Remove only this occurrence; linked survivors are preserved with verified topology updates. */
  readonly linkedItems: "exclude";
}

/** One independently configured removal target in a plural preview. @beta */
export interface TimelineRemovePreview {
  readonly clip: ClipSnapshot;
  readonly options: TimelineRemovePreviewOptions;
}

/** Independently verified semantic timeline edit result. @beta */
export interface TimelineEditMutationResult<TAction extends TimelineEditAction = TimelineEditAction> {
  readonly action: TAction;
  readonly impactId: string;
  readonly timelineRevision: Revision;
  readonly affectedClips: readonly Readonly<{
    id: TimelineItemId;
    trackType: TimelineTrackType;
    trackIndex: TrackIndex;
    recordRange: TimelineRecordRange;
    sourceRange: SourceRange | null;
    sourceFrameRate: FrameRate | null;
  }>[];
  readonly protectedItemIds: readonly TimelineItemId[];
  readonly protectedStatePreserved: true;
}

/** Ordered verified results from one plural timeline edit operation. @beta */
export interface TimelineEditMutationBatchResult<TAction extends TimelineEditAction = TimelineEditAction> {
  readonly results: readonly TimelineEditMutationResult<TAction>[];
}

/** High-level semantic timeline editing. Preview is mandatory and never mutates. @beta */
export interface TimelineEditor {
  previewInsert(snapshot: TimelineSnapshot, source: MediaPoolAssetSnapshot, options: TimelinePlacementPreviewOptions): Promise<TimelineEditImpact<"insert">>;
  previewInsert(snapshot: TimelineSnapshot, placements: readonly TimelinePlacementPreview[]): Promise<readonly TimelineEditImpact<"insert">[]>;
  /** Resolve one immutable, non-ripple audio-only insert impact. */
  previewInsertAudio(snapshot: TimelineSnapshot, source: MediaPoolAssetSnapshot, options: TimelineAudioPlacementPreviewOptions): Promise<TimelineEditImpact<"insert">>;
  previewInsertAudio(snapshot: TimelineSnapshot, placements: readonly TimelineAudioPlacementPreview[]): Promise<readonly TimelineEditImpact<"insert">[]>;
  previewOverwrite(snapshot: TimelineSnapshot, source: MediaPoolAssetSnapshot, options: TimelinePlacementPreviewOptions): Promise<TimelineEditImpact<"overwrite">>;
  previewOverwrite(snapshot: TimelineSnapshot, placements: readonly TimelinePlacementPreview[]): Promise<readonly TimelineEditImpact<"overwrite">[]>;
  previewTrim(snapshot: TimelineSnapshot, clip: ClipSnapshot, options: TimelineTrimPreviewOptions): Promise<TimelineEditImpact<"trim">>;
  previewTrim(snapshot: TimelineSnapshot, trims: readonly TimelineTrimPreview[]): Promise<readonly TimelineEditImpact<"trim">[]>;
  previewRemove(snapshot: TimelineSnapshot, clip: ClipSnapshot, options: TimelineRemovePreviewOptions): Promise<TimelineEditImpact<"remove">>;
  previewRemove(snapshot: TimelineSnapshot, removals: readonly TimelineRemovePreview[]): Promise<readonly TimelineEditImpact<"remove">[]>;
  insert(impact: TimelineEditImpact<"insert">, options: TimelineEditMutationOptions): Promise<OperationHandle<TimelineEditMutationResult<"insert">, "cutagent.action.edit.insert">>;
  insert(impacts: readonly TimelineEditImpact<"insert">[], options: TimelineEditMutationOptions): Promise<OperationHandle<TimelineEditMutationBatchResult<"insert">, "cutagent.action.edit.insert">>;
  overwrite(impact: TimelineEditImpact<"overwrite">, options: TimelineEditMutationOptions): Promise<OperationHandle<TimelineEditMutationResult<"overwrite">, "cutagent.action.edit.overwrite">>;
  overwrite(impacts: readonly TimelineEditImpact<"overwrite">[], options: TimelineEditMutationOptions): Promise<OperationHandle<TimelineEditMutationBatchResult<"overwrite">, "cutagent.action.edit.overwrite">>;
  trim(impact: TimelineEditImpact<"trim">, options: TimelineEditMutationOptions): Promise<OperationHandle<TimelineEditMutationResult<"trim">, "cutagent.action.edit.trim">>;
  trim(impacts: readonly TimelineEditImpact<"trim">[], options: TimelineEditMutationOptions): Promise<OperationHandle<TimelineEditMutationBatchResult<"trim">, "cutagent.action.edit.trim">>;
  remove(impact: TimelineEditImpact<"remove">, options: TimelineEditMutationOptions): Promise<OperationHandle<TimelineEditMutationResult<"remove">, "cutagent.action.timeline.items.delete">>;
  remove(impacts: readonly TimelineEditImpact<"remove">[], options: TimelineEditMutationOptions): Promise<OperationHandle<TimelineEditMutationBatchResult<"remove">, "cutagent.action.timeline.items.delete">>;
}

export interface TimelineEditRuntime {
  readonly generation: number;
  sessionAtGeneration(generation: number): EstablishedCarrierSession;
  readAtGeneration(generation: number, request: CarrierReadRequest, options?: ConnectionControlOptions): Promise<CarrierReadSuccess>;
  createOperationAtGeneration(generation: number, request: CarrierOperationRequest, options?: ConnectionControlOptions): Promise<SdkOperationEvent>;
}

type WireImpact = z.infer<typeof sdkTimelineEditImpactSchema>;
type ImpactInternal = { wire: WireImpact; rate: FrameRate; signature: string };
const issuedImpacts = new WeakMap<TimelineEditRuntime, Map<number, Map<string, ImpactInternal>>>();

function framePosition(value: TimelineRecordPosition, rate: FrameRate, rounding?: TimeRounding): number {
  const wire = lowerTimelineRecordPosition(value, { frameRate: rate, ...(rounding ? { rounding } : {}) });
  if (wire.value.kind === "frames") return wire.value.value;
  return hydrateTimecode(wire.value).toFrames().value;
}

function positionValueFrame(value: SourceRange["start"]["value"], rate: FrameRate, rounding?: TimeRounding): number {
  if (value.kind === "frames") return value.value;
  if (value.kind === "timecode") return value.toFrames().value;
  return value.toFrames(rate, rounding).value;
}

function frameSourceRange(value: SourceRange, rate: FrameRate | null | undefined, rounding?: TimeRounding) {
  const wire = lowerSourceRange(value, rounding ? { rounding } : {});
  if (wire.unit !== "frames") {
    if (!rate) throw new TypeError("Seconds-based source ranges require an authoritative source frame rate or an explicit source-bound frame rate.");
    return { domain: "source_range" as const, unit: "frames" as const, start: positionValueFrame(value.start.value, rate, rounding), endExclusive: positionValueFrame(value.endExclusive.value, rate, rounding) };
  }
  return wire;
}

function sourceBoundaryIsExactlyRepresentable(frame: number, sourceRate: FrameRate, timelineRate: FrameRate): boolean {
  const sourceFps = sourceRate.numerator / sourceRate.denominator;
  const timelineFps = timelineRate.numerator / timelineRate.denominator;
  const nominalSourceFps = Math.round(sourceFps);
  if (nominalSourceFps > 0 && Math.abs(sourceFps - nominalSourceFps) > 0.000001) return true;
  if (sourceFps >= timelineFps) return true;
  const recordBoundary = Math.ceil((frame * timelineFps / sourceFps) - 1e-9);
  const nativeBoundary = Math.ceil((recordBoundary * sourceFps / timelineFps) - 1e-9);
  const projectedRecord = Math.floor((nativeBoundary * timelineFps / sourceFps) + 1e-9);
  const projectedSource = Math.floor((projectedRecord * sourceFps / timelineFps) + 1e-9);
  return projectedSource === frame;
}

/** @internal */
export function assertSourceRangeIsExactlyRepresentable(
  range: { readonly start: number; readonly endExclusive: number },
  sourceRate: FrameRate,
  timelineRate: FrameRate,
): void {
  for (const [label, frame] of [["start", range.start], ["end", range.endExclusive]] as const) {
    if (!sourceBoundaryIsExactlyRepresentable(frame, sourceRate, timelineRate)) {
      throw new TypeError(
        `Source range ${label} frame ${frame} cannot be represented exactly at the ${timelineRate.numerator}/${timelineRate.denominator} timeline rate. Choose another source-frame boundary.`,
      );
    }
  }
}

/** @internal */
export function reportedSourceFrameRate(value: string | null): FrameRate | null {
  const match = String(value ?? "").trim().match(/^(\d+)(?:\.(\d+))?(?:\s*fps)?$/i);
  if (!match) return null;
  const numeric = Number(`${match[1]}.${match[2] ?? "0"}`);
  if (!Number.isFinite(numeric) || numeric <= 0 || numeric > 1000) return null;
  try {
    const ntsc = [24, 30, 48, 60, 120].find((nominal) => Math.abs(numeric - (nominal * 1000 / 1001)) < 0.001);
    if (ntsc) return createFrameRate(ntsc * 1000, 1001, ntsc);
    const decimals = (match[2] ?? "").slice(0, 6);
    let denominator = 10 ** decimals.length;
    let numerator = Number(match[1]) * denominator + Number(decimals || 0);
    const gcd = (left: number, right: number): number => right === 0 ? left : gcd(right, left % right);
    const divisor = gcd(numerator, denominator);
    numerator /= divisor;
    denominator /= divisor;
    return createFrameRate(numerator, denominator, Math.max(1, Math.round(numeric)));
  } catch {
    return null;
  }
}

function durationFrames(value: Duration | undefined, rate: FrameRate, rounding?: TimeRounding): number {
  if (!value) return 0;
  return value.unit === "frames" ? value.value.value : value.toFrames(rate, rounding).value.value;
}

function trimEdgeDeltaFrames(value: TimelineTrimEdgeDelta | undefined, rate: FrameRate, rounding?: TimeRounding): number {
  if (!value) return 0;
  if (value.kind === "seconds") return value.toFrames(rate, rounding).value;
  if (value.rate !== null && !value.rate.equals(rate)) {
    throw new TypeError("Trim edge frame rate must match the timeline snapshot frame rate.");
  }
  return value.value;
}

function assertSnapshot(snapshot: TimelineSnapshot, projectId: ProjectId, timelineId: TimelineId): void {
  if (!snapshot || snapshot.projectId !== projectId || snapshot.timelineId !== timelineId) {
    throw new TypeError("Timeline edit preview requires a snapshot from this exact timeline.");
  }
}

function publicImpactSignature(impact: TimelineEditImpact, rate: FrameRate): string {
  const range = (value: TimelineRecordRange) => {
    const start = lowerTimelineRecordPosition(value.start, { frameRate: rate }).value;
    const end = lowerTimelineRecordPosition(value.endExclusive, { frameRate: rate }).value;
    return [start.kind === "frames" ? start.value : hydrateTimecode(start).toFrames().value, end.kind === "frames" ? end.value : hydrateTimecode(end).toFrames().value];
  };
  const track = (value: TimelineEditTrackTarget) => [value.type, TrackIndexSchema.parse(value.index), String(SnapshotTrackIdSchema.parse(value.snapshotId))];
  const item = (value: TimelineEditItemTarget) => [String(TimelineItemIdSchema.parse(value.id)), track(value.track), range(value.recordRange), value.role];
  return JSON.stringify([
    impact.impactId,
    impact.action,
    String(ProjectIdSchema.parse(impact.projectId)),
    String(TimelineIdSchema.parse(impact.timelineId)),
    String(RevisionSchema.parse(impact.timelineRevision)),
    range(impact.recordRange),
    impact.affectedTracks.map(track),
    impact.affectedItems.map(item),
    impact.protectedItems.map(item),
    impact.linkedAudio.behavior,
    impact.linkedAudio.topologyProven,
    impact.capabilityId,
    impact.summary,
  ]);
}

function registerImpact(runtime: TimelineEditRuntime, generation: number, impact: TimelineEditImpact, wire: WireImpact, rate: FrameRate): void {
  let generations = issuedImpacts.get(runtime);
  if (!generations) {
    generations = new Map();
    issuedImpacts.set(runtime, generations);
  }
  let impacts = generations.get(generation);
  if (!impacts) {
    impacts = new Map();
    generations.set(generation, impacts);
  }
  const signature = publicImpactSignature(impact, rate);
  const existing = impacts.get(impact.impactId);
  if (existing && (existing.signature !== signature || JSON.stringify(existing.wire) !== JSON.stringify(wire))) {
    throw new TypeError("CutAgent runtime reused a timeline impact identity for different content.");
  }
  impacts.set(impact.impactId, { wire, rate, signature });
}

function hydrateImpact<TAction extends TimelineEditAction>(wire: WireImpact & { action: TAction }, rate: FrameRate, runtime: TimelineEditRuntime, generation: number): TimelineEditImpact<TAction> {
  const track = (value: WireImpact["affectedTracks"][number]): TimelineEditTrackTarget => freeze({
    type: value.type,
    index: TrackIndexSchema.parse(value.index),
    snapshotId: SnapshotTrackIdSchema.parse(value.snapshotId),
  });
  const item = (value: WireImpact["affectedItems"][number]): TimelineEditItemTarget => freeze({
    id: TimelineItemIdSchema.parse(value.id),
    track: track(value.track),
    recordRange: hydrateTimelineRecordRange(value.recordRange, { frameRate: rate }),
    role: value.role,
  });
  const impact: TimelineEditImpact<TAction> = freeze({
    impactId: wire.impactId,
    action: wire.action,
    projectId: ProjectIdSchema.parse(wire.projectId),
    timelineId: TimelineIdSchema.parse(wire.timelineId),
    timelineRevision: RevisionSchema.parse(wire.timelineRevision),
    recordRange: hydrateTimelineRecordRange(wire.recordRange, { frameRate: rate }),
    affectedTracks: wire.affectedTracks.map(track),
    affectedItems: wire.affectedItems.map(item),
    protectedItems: wire.protectedItems.map(item),
    linkedAudio: wire.linkedAudio,
    capabilityId: wire.capabilityId,
    summary: wire.summary,
  });
  registerImpact(runtime, generation, impact, wire, rate);
  return impact;
}

function hydrateResult<TAction extends TimelineEditAction>(value: unknown, rate: FrameRate, expectedAction: TAction): TimelineEditMutationResult<TAction> {
  const parsed = sdkTimelineEditMutationResultSchema.parse(value);
  if (parsed.action !== expectedAction) throw new TypeError("CutAgent runtime returned the wrong timeline edit action result.");
  return freeze({
    action: parsed.action as TAction,
    impactId: parsed.impactId,
    timelineRevision: RevisionSchema.parse(parsed.timelineRevision),
    affectedClips: parsed.affectedClips.map((clip) => {
      const sourceFrameRate = clip.sourceFrameRate === null ? null : hydrateFrameRate(clip.sourceFrameRate);
      return freeze({
      id: TimelineItemIdSchema.parse(clip.id),
      trackType: clip.trackType,
      trackIndex: TrackIndexSchema.parse(clip.trackIndex),
      recordRange: hydrateTimelineRecordRange({ domain: "timeline_record_range", unit: "frames", start: clip.recordStartFrame, endExclusive: clip.recordEndFrameExclusive }, { frameRate: rate }),
      sourceRange: clip.sourceStartFrame === null || clip.sourceEndFrameExclusive === null
        ? null
        : hydrateSourceRange(
          { domain: "source_range", unit: "frames", start: clip.sourceStartFrame, endExclusive: clip.sourceEndFrameExclusive },
          sourceFrameRate === null ? {} : { frameRate: sourceFrameRate },
        ),
      sourceFrameRate,
    }); }),
    protectedItemIds: parsed.protectedItemIds.map((id) => TimelineItemIdSchema.parse(id)),
    protectedStatePreserved: true,
  });
}

function hydrateBatchResult<TAction extends TimelineEditAction>(
  value: unknown,
  internals: readonly ImpactInternal[],
  expectedAction: TAction,
): TimelineEditMutationBatchResult<TAction> {
  const parsed = sdkTimelineEditMutationBatchResultSchema.parse(value);
  if (parsed.results.length !== internals.length) throw new TypeError("CutAgent runtime returned the wrong number of timeline edit results.");
  return freeze({
    results: parsed.results.map((result, index) => {
      if (result.impactId !== internals[index]!.wire.impactId) throw new TypeError("CutAgent runtime returned timeline edit results out of order.");
      return hydrateResult(result, internals[index]!.rate, expectedAction);
    }),
  });
}

/** Construct the timeline editing surface for one exact timeline reference. @internal */
export function createTimelineEditor(
  runtime: TimelineEditRuntime,
  generation: number,
  projectId: ProjectId,
  timelineId: TimelineId,
): TimelineEditor {
  const preview = async <TAction extends TimelineEditAction>(intent: SdkTimelineEditIntent & { action: TAction }, rate: FrameRate): Promise<TimelineEditImpact<TAction>> => {
    const response = await runtime.readAtGeneration(generation, { operation: "timeline.edit.preview", intent });
    if (response.operation !== "timeline.edit.preview") throw new TypeError("CutAgent runtime returned the wrong timeline edit preview.");
    const wire = sdkTimelineEditImpactSchema.parse(response.data);
    if (wire.action !== intent.action) throw new TypeError("CutAgent runtime returned the wrong timeline edit preview action.");
    return hydrateImpact(wire as WireImpact & { action: TAction }, rate, runtime, generation);
  };
  const previewMany = async <TAction extends TimelineEditAction>(intents: readonly (SdkTimelineEditIntent & { action: TAction })[], rate: FrameRate): Promise<readonly TimelineEditImpact<TAction>[]> => {
    if (intents.length < 1 || intents.length > 256) throw new TypeError("Timeline edit plural preview requires between 1 and 256 items.");
    const response = await runtime.readAtGeneration(generation, { operation: "timeline.edit.preview", intents: [...intents] });
    if (response.operation !== "timeline.edit.preview" || !("impacts" in response.data)) throw new TypeError("CutAgent runtime returned the wrong plural timeline edit preview.");
    const wires = z.array(sdkTimelineEditImpactSchema).length(intents.length).parse(response.data.impacts);
    return freeze(wires.map((wire, index) => {
      if (wire.action !== intents[index]!.action) throw new TypeError("CutAgent runtime returned plural timeline edit previews out of order.");
      return hydrateImpact(wire as WireImpact & { action: TAction }, rate, runtime, generation);
    }));
  };
  const placementIntent = <TAction extends "insert" | "overwrite">(action: TAction, snapshot: TimelineSnapshot, source: MediaPoolAssetSnapshot, options: TimelinePlacementPreviewOptions): SdkTimelineEditIntent & { action: TAction } => {
    assertSnapshot(snapshot, projectId, timelineId);
    if (!source?.id) throw new TypeError("Timeline placement requires an authoritative Media Pool item identity.");
    if (!options || typeof options !== "object") throw new TypeError("Timeline placement options are required.");
    if (options.linkedAudio !== "include" && options.linkedAudio !== "exclude") {
      throw new TypeError("Timeline placement requires an explicit linkedAudio policy: include or exclude.");
    }
    const sourceRate = reportedSourceFrameRate(source.frameRate) ?? options.sourceRange.rate;
    const sourceRange = frameSourceRange(options.sourceRange, sourceRate, options.rounding);
    if (sourceRate) assertSourceRangeIsExactlyRepresentable(sourceRange, sourceRate, snapshot.frameRate);
    const at = framePosition(options.at, snapshot.frameRate, options.rounding);
    const intent = sdkTimelineEditIntentSchema.parse({
      action,
      placement: "video",
      projectId: String(projectId),
      timelineId: String(timelineId),
      timelineRevision: String(snapshot.revision),
      source: { id: String(MediaPoolItemIdSchema.parse(source.id)), name: source.name, snapshotRevision: String(source.snapshotRevision) },
      sourceRange,
      at: { domain: "timeline_record", value: { kind: "frames", value: at } },
      videoTrackIndex: TrackIndexSchema.parse(options.videoTrack),
      audioTrackIndex: options.audioTrack === undefined ? null : TrackIndexSchema.parse(options.audioTrack),
      linkedAudio: options.linkedAudio,
    });
    return intent as SdkTimelineEditIntent & { action: TAction };
  };
  const placement = <TAction extends "insert" | "overwrite">(action: TAction, snapshot: TimelineSnapshot, source: MediaPoolAssetSnapshot, options: TimelinePlacementPreviewOptions): Promise<TimelineEditImpact<TAction>> => {
    return preview(placementIntent(action, snapshot, source, options), snapshot.frameRate);
  };
  const placementMany = <TAction extends "insert" | "overwrite">(action: TAction, snapshot: TimelineSnapshot, placements: readonly TimelinePlacementPreview[]): Promise<readonly TimelineEditImpact<TAction>[]> => {
    assertSnapshot(snapshot, projectId, timelineId);
    if (!Array.isArray(placements) || placements.length < 1 || placements.length > 256) throw new TypeError("Timeline edit plural preview requires between 1 and 256 items.");
    return previewMany(placements.map(({ source, options }) => placementIntent(action, snapshot, source, options)), snapshot.frameRate);
  };
  const registeredImpact = <TAction extends TimelineEditAction>(expected: TAction, impact: TimelineEditImpact<TAction>, options: TimelineEditMutationOptions) => {
    const internal = issuedImpacts.get(runtime)?.get(generation)?.get(impact?.impactId);
    if (!internal || impact.action !== expected || internal.wire.action !== expected || internal.wire.impactId !== impact.impactId || internal.wire.projectId !== String(projectId) || internal.wire.timelineId !== String(timelineId) || internal.wire.timelineRevision !== String(impact.timelineRevision) || internal.signature !== publicImpactSignature(impact, internal.rate)) {
      throw new TypeError("Timeline mutation requires its matching runtime-resolved impact preview.");
    }
    IdempotencyKeySchema.parse(options?.idempotencyKey);
    return internal;
  };
  const start = async <TAction extends Exclude<TimelineEditAction, "remove">, TActionId extends Exclude<TimelineEditActionId, "cutagent.action.timeline.items.delete">>(actionId: TActionId, expected: TAction, impact: TimelineEditImpact<TAction>, options: TimelineEditMutationOptions) => {
    const internal = registeredImpact(expected, impact, options);
    const event = await runtime.createOperationAtGeneration(generation, {
      operation: "operation.create",
      actionId,
      input: { impact: internal.wire },
      idempotencyKey: sdkIdempotencyKeySchema.parse(options.idempotencyKey),
    }, options);
    return createTypedOperationHandle({ session: () => runtime.sessionAtGeneration(generation) }, event, actionId, z.object({}).passthrough().transform((value) => hydrateResult(value, internal.rate, expected)));
  };
  const startMany = async <TAction extends Exclude<TimelineEditAction, "remove">, TActionId extends Exclude<TimelineEditActionId, "cutagent.action.timeline.items.delete">>(actionId: TActionId, expected: TAction, impacts: readonly TimelineEditImpact<TAction>[], options: TimelineEditMutationOptions) => {
    if (!Array.isArray(impacts) || impacts.length < 1 || impacts.length > 256) throw new TypeError("Timeline edit plural mutation requires between 1 and 256 impacts.");
    const internals = impacts.map((impact) => registeredImpact(expected, impact, options));
    const first = internals[0]!.wire;
    const seen = new Set<string>();
    internals.forEach(({ wire }, index) => {
      if (seen.has(wire.impactId)) throw new TypeError("Timeline edit plural mutation requires unique impacts.");
      seen.add(wire.impactId);
      if (wire.action !== first.action || wire.projectId !== first.projectId || wire.timelineId !== first.timelineId || wire.timelineRevision !== first.timelineRevision) {
        throw new TypeError("Timeline edit plural mutation requires one action, project, timeline, and base revision.");
      }
      for (let previousIndex = 0; previousIndex < index; previousIndex += 1) {
        const previous = internals[previousIndex]!.wire;
        const sharesTrack = wire.affectedTracks.some((track) => previous.affectedTracks.some(
          (candidate) => candidate.type === track.type && candidate.index === track.index,
        ));
        if (sharesTrack && wire.recordRange.start < previous.recordRange.endExclusive && previous.recordRange.start < wire.recordRange.endExclusive) {
          throw new TypeError("Timeline edit plural mutation ranges must not overlap on the same track.");
        }
      }
    });
    const event = await runtime.createOperationAtGeneration(generation, {
      operation: "operation.create",
      actionId,
      input: { impacts: internals.map(({ wire }) => wire) },
      idempotencyKey: sdkIdempotencyKeySchema.parse(options.idempotencyKey),
    }, options);
    return createTypedOperationHandle({ session: () => runtime.sessionAtGeneration(generation) }, event, actionId, z.object({}).passthrough().transform((value) => hydrateBatchResult(value, internals, expected)));
  };
  const removeInput = (impact: TimelineEditImpact<"remove">, options: TimelineEditMutationOptions) => {
    const internal = registeredImpact("remove", impact, options);
    if (internal.wire.intent.action !== "remove") throw new TypeError("Remove requires its matching runtime-resolved impact preview.");
    return {
      operation: "clip_remove" as const,
      projectId: internal.wire.projectId,
      timelineId: internal.wire.timelineId,
      timelineRevision: internal.wire.timelineRevision,
      affectedTracks: internal.wire.affectedTracks.map(({ type, index }) => ({ type, index })),
      affectedItemIds: internal.wire.affectedItems.map((item) => item.id),
      protectedItemIds: internal.wire.protectedItems.map((item) => item.id),
      clipId: internal.wire.intent.clipId,
      track: { type: internal.wire.intent.trackType, index: internal.wire.intent.trackIndex },
      expectedLinkTransitions: internal.wire.expectedLinkTransitions,
      range: { start: internal.wire.recordRange.start, endExclusive: internal.wire.recordRange.endExclusive },
      name: internal.wire.intent.clipName,
    };
  };
  const hydrateRemoveResult = (value: unknown, input: ReturnType<typeof removeInput>, impactId: string): TimelineEditMutationResult<"remove"> => {
    const parsed = sdkTimelineRemoveMutationResultSchema.parse(value);
    const sameIds = (left: readonly string[], right: readonly string[]) => left.length === right.length
      && [...left].sort().every((id, index) => id === [...right].sort()[index]);
    if (!sameIds(parsed.affectedItemIds, input.affectedItemIds)
      || !sameIds(parsed.protectedItemIds, input.protectedItemIds)
      || JSON.stringify(parsed.affectedTracks) !== JSON.stringify(input.affectedTracks)
      || parsed.outputItemIds.length !== 0
      || parsed.timelineRevision === input.timelineRevision) {
      throw new TypeError("CutAgent runtime returned a remove result that did not match its exact preview impact.");
    }
    return freeze({
      action: "remove", impactId, timelineRevision: RevisionSchema.parse(parsed.timelineRevision),
      affectedClips: [], protectedItemIds: parsed.protectedItemIds.map((id) => TimelineItemIdSchema.parse(id)), protectedStatePreserved: true,
    });
  };
  const startRemove = async (impact: TimelineEditImpact<"remove">, options: TimelineEditMutationOptions) => {
    const input = removeInput(impact, options);
    const event = await runtime.createOperationAtGeneration(generation, {
      operation: "operation.create",
      actionId: "cutagent.action.timeline.items.delete",
      input,
      idempotencyKey: sdkIdempotencyKeySchema.parse(options.idempotencyKey),
    }, options);
    const result = z.unknown().transform((value) => hydrateRemoveResult(value, input, impact.impactId));
    return createTypedOperationHandle({ session: () => runtime.sessionAtGeneration(generation) }, event, "cutagent.action.timeline.items.delete", result);
  };
  const startRemoveMany = async (impacts: readonly TimelineEditImpact<"remove">[], options: TimelineEditMutationOptions) => {
    if (!Array.isArray(impacts) || impacts.length < 1 || impacts.length > 256) throw new TypeError("Timeline edit plural mutation requires between 1 and 256 impacts.");
    const removals = impacts.map((impact) => removeInput(impact, options));
    const first = removals[0]!;
    if (new Set(removals.map((removal) => removal.clipId)).size !== removals.length
      || removals.some((removal) => removal.projectId !== first.projectId || removal.timelineId !== first.timelineId || removal.timelineRevision !== first.timelineRevision)) {
      throw new TypeError("Timeline remove plural mutation requires unique clips from one project, timeline, and base revision.");
    }
    const event = await runtime.createOperationAtGeneration(generation, {
      operation: "operation.create",
      actionId: "cutagent.action.timeline.items.delete",
      input: { operation: "clip_remove_many", removals },
      idempotencyKey: sdkIdempotencyKeySchema.parse(options.idempotencyKey),
    }, options);
    const result = sdkTimelineRemoveBatchMutationResultSchema.transform((value): TimelineEditMutationBatchResult<"remove"> => {
      if (value.results.length !== removals.length) throw new TypeError("CutAgent runtime returned the wrong number of timeline remove results.");
      return freeze({ results: value.results.map((row, index) => hydrateRemoveResult(row, removals[index]!, impacts[index]!.impactId)) });
    });
    return createTypedOperationHandle({ session: () => runtime.sessionAtGeneration(generation) }, event, "cutagent.action.timeline.items.delete", result);
  };
  const audioPlacementIntent = (snapshot: TimelineSnapshot, source: MediaPoolAssetSnapshot, options: TimelineAudioPlacementPreviewOptions): SdkTimelineEditIntent & { action: "insert" } => {
    assertSnapshot(snapshot, projectId, timelineId);
    if (!source?.id) throw new TypeError("Timeline placement requires an authoritative Media Pool item identity.");
    if (!options || typeof options !== "object") throw new TypeError("Audio placement options are required.");
    const sourceRate = reportedSourceFrameRate(source.frameRate) ?? options.sourceRange.rate ?? snapshot.frameRate;
    const resolvedSourceRange = frameSourceRange(options.sourceRange, sourceRate, options.rounding);
    if (sourceRate) assertSourceRangeIsExactlyRepresentable(resolvedSourceRange, sourceRate, snapshot.frameRate);
    return sdkTimelineEditIntentSchema.parse({
      action: "insert",
      placement: "audio",
      projectId: String(projectId),
      timelineId: String(timelineId),
      timelineRevision: String(snapshot.revision),
      source: { id: String(MediaPoolItemIdSchema.parse(source.id)), name: source.name, snapshotRevision: String(source.snapshotRevision) },
      sourceRange: resolvedSourceRange,
      at: { domain: "timeline_record", value: { kind: "frames", value: framePosition(options.at, snapshot.frameRate, options.rounding) } },
      videoTrackIndex: null,
      audioTrackIndex: TrackIndexSchema.parse(options.audioTrack),
      linkedAudio: "exclude",
    }) as SdkTimelineEditIntent & { action: "insert" };
  };
  const previewInsert = ((snapshot: TimelineSnapshot, sourceOrPlacements: MediaPoolAssetSnapshot | readonly TimelinePlacementPreview[], options?: TimelinePlacementPreviewOptions) => {
      return Array.isArray(sourceOrPlacements)
        ? placementMany("insert", snapshot, sourceOrPlacements as readonly TimelinePlacementPreview[])
        : placement("insert", snapshot, sourceOrPlacements as MediaPoolAssetSnapshot, options as TimelinePlacementPreviewOptions);
    }) as TimelineEditor["previewInsert"];
  const previewInsertAudio = ((snapshot: TimelineSnapshot, sourceOrPlacements: MediaPoolAssetSnapshot | readonly TimelineAudioPlacementPreview[], options?: TimelineAudioPlacementPreviewOptions) => {
      if (Array.isArray(sourceOrPlacements)) {
        const placements = sourceOrPlacements as readonly TimelineAudioPlacementPreview[];
        if (placements.length < 1 || placements.length > 256) throw new TypeError("Timeline edit plural preview requires between 1 and 256 items.");
        return previewMany(placements.map(({ source, options: placementOptions }) => audioPlacementIntent(snapshot, source, placementOptions)), snapshot.frameRate);
      }
      return preview(audioPlacementIntent(snapshot, sourceOrPlacements as MediaPoolAssetSnapshot, options as TimelineAudioPlacementPreviewOptions), snapshot.frameRate);
    }) as TimelineEditor["previewInsertAudio"];
  const previewOverwrite = ((snapshot: TimelineSnapshot, sourceOrPlacements: MediaPoolAssetSnapshot | readonly TimelinePlacementPreview[], options?: TimelinePlacementPreviewOptions) => {
      return Array.isArray(sourceOrPlacements)
        ? placementMany("overwrite", snapshot, sourceOrPlacements as readonly TimelinePlacementPreview[])
        : placement("overwrite", snapshot, sourceOrPlacements as MediaPoolAssetSnapshot, options as TimelinePlacementPreviewOptions);
    }) as TimelineEditor["previewOverwrite"];
  const insert = ((impactOrImpacts: TimelineEditImpact<"insert"> | readonly TimelineEditImpact<"insert">[], options: TimelineEditMutationOptions) => Array.isArray(impactOrImpacts)
    ? startMany("cutagent.action.edit.insert", "insert", impactOrImpacts as readonly TimelineEditImpact<"insert">[], options)
    : start("cutagent.action.edit.insert", "insert", impactOrImpacts as TimelineEditImpact<"insert">, options)) as TimelineEditor["insert"];
  const overwrite = ((impactOrImpacts: TimelineEditImpact<"overwrite"> | readonly TimelineEditImpact<"overwrite">[], options: TimelineEditMutationOptions) => Array.isArray(impactOrImpacts)
    ? startMany("cutagent.action.edit.overwrite", "overwrite", impactOrImpacts as readonly TimelineEditImpact<"overwrite">[], options)
    : start("cutagent.action.edit.overwrite", "overwrite", impactOrImpacts as TimelineEditImpact<"overwrite">, options)) as TimelineEditor["overwrite"];
  const remove = ((impactOrImpacts: TimelineEditImpact<"remove"> | readonly TimelineEditImpact<"remove">[], options: TimelineEditMutationOptions) => Array.isArray(impactOrImpacts)
    ? startRemoveMany(impactOrImpacts as readonly TimelineEditImpact<"remove">[], options)
    : startRemove(impactOrImpacts as TimelineEditImpact<"remove">, options)) as TimelineEditor["remove"];
  const trim = ((impactOrImpacts: TimelineEditImpact<"trim"> | readonly TimelineEditImpact<"trim">[], options: TimelineEditMutationOptions) => Array.isArray(impactOrImpacts)
    ? startMany("cutagent.action.edit.trim", "trim", impactOrImpacts as readonly TimelineEditImpact<"trim">[], options)
    : start("cutagent.action.edit.trim", "trim", impactOrImpacts as TimelineEditImpact<"trim">, options)) as TimelineEditor["trim"];
  const trimIntent = (snapshot: TimelineSnapshot, clip: ClipSnapshot, options: TimelineTrimPreviewOptions): SdkTimelineEditIntent & { action: "trim" } => {
    assertSnapshot(snapshot, projectId, timelineId);
    if (!clip?.id || clip.snapshotRevision !== snapshot.revision) throw new TypeError("Trim requires a durable clip from this exact snapshot.");
    if (!options || (options.linkedAudio !== "preserve" && options.linkedAudio !== "exclude")) {
      throw new TypeError("Trim requires an explicit linkedAudio policy: preserve or exclude.");
    }
    const headFrames = trimEdgeDeltaFrames(options?.head, snapshot.frameRate, options?.rounding);
    const tailFrames = trimEdgeDeltaFrames(options?.tail, snapshot.frameRate, options?.rounding);
    const clipDurationFrames = durationFrames(clip.duration, snapshot.frameRate);
    if (headFrames === 0 && tailFrames === 0) throw new TypeError("Trim must change at least one edge.");
    if (clipDurationFrames - headFrames - tailFrames < 1) throw new TypeError("Trim must preserve at least one frame.");
    const currentRecordRange = {
      domain: "timeline_record_range" as const,
      unit: "frames" as const,
      start: framePosition(clip.recordRange.start, snapshot.frameRate),
      endExclusive: framePosition(clip.recordRange.endExclusive, snapshot.frameRate),
    };
    return sdkTimelineEditIntentSchema.parse({
      action: "trim", projectId: String(projectId), timelineId: String(timelineId), timelineRevision: String(snapshot.revision),
      clipId: String(clip.id), clipName: clip.name,
      trackIndex: TrackIndexSchema.parse(snapshot.tracks.find((track) => track.snapshotId === clip.snapshotTrackId)?.index),
      currentRecordRange, headFrames, tailFrames, linkedAudio: options.linkedAudio,
    }) as SdkTimelineEditIntent & { action: "trim" };
  };
  const removeIntent = (snapshot: TimelineSnapshot, clip: ClipSnapshot, options: TimelineRemovePreviewOptions): SdkTimelineEditIntent & { action: "remove" } => {
    assertSnapshot(snapshot, projectId, timelineId);
    if (!clip?.id || clip.snapshotRevision !== snapshot.revision) throw new TypeError("Remove requires a durable clip from this exact snapshot.");
    if (!options || options.linkedItems !== "exclude") throw new TypeError("Remove requires the explicit linkedItems policy: exclude.");
    const track = snapshot.tracks.find((candidate) => candidate.snapshotId === clip.snapshotTrackId);
    if (!track) throw new TypeError("Remove target track is absent from the exact snapshot.");
    const currentRecordRange = {
      domain: "timeline_record_range" as const,
      unit: "frames" as const,
      start: framePosition(clip.recordRange.start, snapshot.frameRate),
      endExclusive: framePosition(clip.recordRange.endExclusive, snapshot.frameRate),
    };
    return sdkTimelineEditIntentSchema.parse({
      action: "remove", projectId: String(projectId), timelineId: String(timelineId), timelineRevision: String(snapshot.revision),
      clipId: String(clip.id), clipName: clip.name, trackType: track.type, trackIndex: TrackIndexSchema.parse(track.index), currentRecordRange,
      linkedItems: "exclude",
    }) as SdkTimelineEditIntent & { action: "remove" };
  };
  const previewTrim = ((snapshot: TimelineSnapshot, clipOrTrims: ClipSnapshot | readonly TimelineTrimPreview[], options?: TimelineTrimPreviewOptions) => Array.isArray(clipOrTrims)
    ? previewMany((clipOrTrims as readonly TimelineTrimPreview[]).map(({ clip, options: trimOptions }) => trimIntent(snapshot, clip, trimOptions)), snapshot.frameRate)
    : preview(trimIntent(snapshot, clipOrTrims as ClipSnapshot, options as TimelineTrimPreviewOptions), snapshot.frameRate)) as TimelineEditor["previewTrim"];
  const previewRemove = ((snapshot: TimelineSnapshot, clipOrRemovals: ClipSnapshot | readonly TimelineRemovePreview[], options?: TimelineRemovePreviewOptions) => Array.isArray(clipOrRemovals)
    ? previewMany((clipOrRemovals as readonly TimelineRemovePreview[]).map(({ clip, options: removeOptions }) => removeIntent(snapshot, clip, removeOptions)), snapshot.frameRate)
    : preview(removeIntent(snapshot, clipOrRemovals as ClipSnapshot, options as TimelineRemovePreviewOptions), snapshot.frameRate)) as TimelineEditor["previewRemove"];
  const editor: TimelineEditor = {
    previewInsert,
    previewInsertAudio,
    previewOverwrite,
    previewTrim,
    previewRemove,
    insert,
    overwrite,
    trim,
    remove,
  };
  Object.setPrototypeOf(editor, null);
  return Object.freeze(editor);
}
