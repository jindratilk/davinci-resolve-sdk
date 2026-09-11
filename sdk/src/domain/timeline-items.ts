import { z } from "zod";
import {
  sdkBulkClipStateInputSchema,
  sdkBulkClipStateResultSchema,
  sdkBulkClipPropertyInputSchema,
  sdkBulkClipPropertyResultSchema,
  sdkClipTransformValuesSchema,
  sdkTimelineItemMoveInputSchema,
  sdkTimelineItemMoveResultSchema,
  sdkTimelineItemMoveSingleResultSchema,
  sdkTimelineClipColorBatchInputSchema,
  type SdkOperationEvent,
} from "../generated/sdk-operations.js";
import { sdkIdempotencyKeySchema } from "../generated/sdk-identities.js";
import { createTypedOperationHandle } from "../core/operations.js";
import type { CarrierOperationRequest } from "../core/carrier-contract.js";
import type { EstablishedCarrierSession } from "../core/carrier-session.js";
import type { ConnectionControlOptions } from "../core/public-client-types.js";
import type { OperationHandle } from "../protocol/operations.js";
import {
  IdempotencyKeySchema,
  MediaPoolItemIdSchema,
  RevisionSchema,
  TimelineItemIdSchema,
  type IdempotencyKey,
  type MediaPoolItemId,
  type ProjectId,
  type Revision,
  type TimelineId,
  type TimelineItemId,
} from "../value-types/identities.js";
import type { Duration, FrameRate, TimeRounding, TimelineRecordPosition, TimelineRecordRange } from "../value-types/time.js";
import { hydrateTimecode, hydrateTimelineRecordRange, lowerTimelineRecordPosition } from "../wire/time-adapter.js";
import type { ClipSnapshot, TimelineSnapshot, TrackSnapshot } from "./object-model.js";

/** Linked-audio behavior for a video item record-time move. @beta */
export type LinkedAudioMovePolicy = "preserve" | "exclude";

/** Destination and collision policy for an exact timeline-item move preview. @beta */
export interface TimelineItemMoveDestination {
  readonly track: TrackSnapshot;
  readonly start?: TimelineRecordPosition;
  readonly linkedAudio?: LinkedAudioMovePolicy;
  readonly collisionPolicy?: "reject" | "allow";
}

/** One item and its independent destination in a jointly evaluated move. @beta */
export interface TimelineItemMoveRequest {
  readonly item: ClipSnapshot;
  readonly destination: TimelineItemMoveDestination;
}

/** One exact collision or safety reason that prevents applying a preview. @beta */
export interface TimelineItemMoveBlocker {
  readonly code: "locked_source_track" | "locked_destination_track" | "locked_linked_audio_track" | "unknown_track_lock_state" | "durable_identity_required" | "linked_topology_unavailable" | "unsupported_link_group" | "destination_collision" | "linked_audio_collision";
  readonly summary: string;
}

/** Agent-inspectable, revision-bound impact for moving one video item. @beta */
export interface TimelineItemMoveImpactPreview {
  readonly projectId: ProjectId;
  readonly timelineId: TimelineId;
  readonly timelineRevision: Revision;
  readonly target: ClipSnapshot;
  readonly sourceTrack: TrackSnapshot;
  readonly destinationTrack: TrackSnapshot;
  readonly before: TimelineRecordRange;
  readonly after: TimelineRecordRange;
  readonly linkedAudioPolicy: LinkedAudioMovePolicy;
  readonly linkedAudioItems: readonly ClipSnapshot[];
  readonly collisions: readonly ClipSnapshot[];
  readonly blockers: readonly TimelineItemMoveBlocker[];
  readonly canApply: boolean;
  readonly summary: string;
}

/** One independently read timeline item before and after a move. @beta */
export interface TimelineItemMoveObservation {
  readonly id: TimelineItemId;
  readonly role: "video" | "linked_audio";
  readonly name: string;
  readonly before: Readonly<{ trackIndex: number; range: TimelineRecordRange }>;
  readonly after: Readonly<{ trackIndex: number; range: TimelineRecordRange }>;
  readonly sourceRangePreservation: "preserved" | "not_observable";
}

/** Durable verified result for one semantic timeline-item move. @beta */
export interface TimelineItemMoveResult {
  readonly target: TimelineItemMoveObservation;
  readonly linkedAudio: "preserved" | "excluded" | "not_linked";
  readonly movedItems: readonly TimelineItemMoveObservation[];
  readonly timelineRevision: Revision;
}

/** Durable verified result for one plural timeline-item move operation. @beta */
export interface TimelineItemMoveBatchResult {
  readonly results: readonly TimelineItemMoveResult[];
  readonly timelineRevision: Revision;
}

/** Required replay-safe control values for a timeline-item move. @beta */
export interface TimelineItemMoveOptions extends ConnectionControlOptions {
  readonly idempotencyKey: IdempotencyKey;
}

/** One exact requested timeline-item duration change. @beta */
export interface TimelineItemDurationChange {
  readonly item: ClipSnapshot;
  readonly duration: Duration;
  readonly allowOverlap?: boolean;
  readonly enforceSourceBounds?: boolean;
}

/** Required replay-safe control values for one or more duration changes. @beta */
export interface TimelineItemDurationOptions extends ConnectionControlOptions {
  readonly idempotencyKey: IdempotencyKey;
  readonly rounding?: TimeRounding;
}

/** One timeline item observed after a duration change. @beta */
export interface TimelineItemDurationObservation {
  readonly id: TimelineItemId;
  readonly name: string;
  readonly trackType: "video" | "audio" | "subtitle";
  readonly trackIndex: number;
  readonly recordRange: TimelineRecordRange;
  readonly mediaPoolItemId: MediaPoolItemId | null;
}

/** Verified result for one plural timeline-item duration operation. @beta */
export interface TimelineItemDurationResult {
  readonly items: readonly TimelineItemDurationObservation[];
  readonly revisionChange: Readonly<{ before: Revision; after: Revision; changed: boolean }>;
}

/** One exact clip enable/disable observation from native readback. @beta */
export interface TimelineItemStateChangeObservation {
  readonly timelineItemId: TimelineItemId;
  readonly name: string;
  readonly before: boolean;
  readonly after: boolean;
  readonly changed: boolean;
}

/** Ordered verified result for one bulk clip-state operation. @beta */
export interface TimelineItemStateChangeResult {
  readonly items: readonly TimelineItemStateChangeObservation[];
  readonly timelineRevision: Revision;
}

/** Required replay-safe control values for a bulk clip-state operation. @beta */
export interface TimelineItemStateChangeOptions extends ConnectionControlOptions {
  readonly idempotencyKey: IdempotencyKey;
}

/** One exact clip or an ordered non-empty collection of exact clips. @beta */
export type TimelineItemStateChangeInput = ClipSnapshot | readonly ClipSnapshot[];

/** One snapshot-bound organizational clip-color change. `null` clears the color. @beta */
export interface TimelineClipColorChange {
  readonly clip: ClipSnapshot;
  readonly color: string | null;
}

/** One independently verified organizational clip-color result. @beta */
export interface TimelineClipColorObservation {
  readonly clipId: TimelineItemId;
  readonly name: string;
  readonly requestedColor: string | null;
  readonly actualColor: string | null;
  readonly changed: boolean;
}

/** Durable result of one plural organizational clip-color operation. @beta */
export interface TimelineClipColorResult {
  readonly clips: readonly TimelineClipColorObservation[];
  readonly timelineRevision: Revision;
}

/** Supported Inspector properties for one timeline clip. @beta */
export interface TimelineClipProperties {
  readonly zoomX?: number | undefined;
  readonly zoomY?: number | undefined;
  readonly positionX?: number | undefined;
  readonly positionY?: number | undefined;
  readonly rotation?: number | undefined;
  readonly anchorX?: number | undefined;
  readonly anchorY?: number | undefined;
  readonly pitch?: number | undefined;
  readonly yaw?: number | undefined;
  readonly flipX?: boolean | undefined;
  readonly flipY?: boolean | undefined;
  readonly opacity?: number | undefined;
  readonly cropLeft?: number | undefined;
  readonly cropRight?: number | undefined;
  readonly cropTop?: number | undefined;
  readonly cropBottom?: number | undefined;
  readonly distortion?: number | undefined;
  readonly dynamicZoomEase?: "linear" | "in" | "out" | "inout" | undefined;
}

/** One exact clip and its supported Inspector-property changes. @beta */
export interface TimelineClipPropertyChange {
  readonly clip: ClipSnapshot;
  readonly properties: TimelineClipProperties;
}

/** Independently read property state for one item in a plural mutation. @beta */
export interface TimelineClipPropertyObservation {
  readonly clipId: TimelineItemId;
  readonly before: TimelineClipProperties;
  readonly after: TimelineClipProperties;
  readonly changed: boolean;
}

/** Verified result of one shared plural property mutation. @beta */
export interface TimelineClipPropertyResult {
  readonly items: readonly TimelineClipPropertyObservation[];
  readonly timelineRevision: Revision;
  readonly protectedStatePreserved: true;
  readonly stoppedAfterFailure: false;
}
/** Required replay-safe control values for a bulk clip-property operation. @beta */
export interface TimelineClipPropertyOptions extends ConnectionControlOptions {
  readonly idempotencyKey: IdempotencyKey;
}

/** Semantic timeline-item inspection, impact preview, and durable mutation API. @beta */
export interface TimelineItems {
  disable(items: TimelineItemStateChangeInput, options: TimelineItemStateChangeOptions): Promise<OperationHandle<TimelineItemStateChangeResult, "cutagent.action.bulk.disable">>;
  enable(items: TimelineItemStateChangeInput, options: TimelineItemStateChangeOptions): Promise<OperationHandle<TimelineItemStateChangeResult, "cutagent.action.bulk.enable">>;
  previewMove(item: ClipSnapshot, destination: TimelineItemMoveDestination): Promise<TimelineItemMoveImpactPreview>;
  previewMove(requests: readonly TimelineItemMoveRequest[]): Promise<readonly TimelineItemMoveImpactPreview[]>;
  move(preview: TimelineItemMoveImpactPreview, options: TimelineItemMoveOptions): Promise<OperationHandle<TimelineItemMoveResult, "cutagent.action.timeline.items.move">>;
  move(previews: readonly TimelineItemMoveImpactPreview[], options: TimelineItemMoveOptions): Promise<OperationHandle<TimelineItemMoveBatchResult, "cutagent.action.timeline.items.move">>;
  setDuration(change: TimelineItemDurationChange | readonly TimelineItemDurationChange[], options: TimelineItemDurationOptions): Promise<OperationHandle<TimelineItemDurationResult, "cutagent.action.timeline.items.set_duration">>;
  /** Set or clear one or many organizational clip colors in one durable native operation. */
  setColor(change: TimelineClipColorChange | readonly TimelineClipColorChange[], options: TimelineItemMoveOptions): Promise<OperationHandle<TimelineClipColorResult, "cutagent.action.timeline.clip_color.batch">>;
  /** Apply supported Inspector properties to one clip or an ordered list in one native operation. */
  setProperties(change: TimelineClipPropertyChange | readonly TimelineClipPropertyChange[], options: TimelineClipPropertyOptions): Promise<OperationHandle<TimelineClipPropertyResult, "cutagent.action.bulk.property_set">>;
}

export interface TimelineItemRuntime {
  sessionAtGeneration(generation: number): EstablishedCarrierSession;
  createOperationAtGeneration(
    generation: number,
    request: Parameters<EstablishedCarrierSession["operation"]>[0],
    options?: ConnectionControlOptions,
  ): Promise<SdkOperationEvent>;
}

type PreviewInternal = {
  public: TimelineItemMoveImpactPreview;
  collection: object;
  frameRate: FrameRate;
  linkedAudioDescriptors: readonly ReturnType<typeof clipDescriptor>[];
  collisionPolicy: "reject" | "allow";
};
const previewInternals = new WeakMap<object, PreviewInternal>();

function freeze<T extends object>(value: T): Readonly<T> {
  Object.setPrototypeOf(value, null);
  return Object.freeze(value);
}

function frame(position: TimelineRecordPosition, frameRate: FrameRate): number {
  const lowered = lowerTimelineRecordPosition(position, { frameRate });
  return lowered.value.kind === "frames" ? lowered.value.value : hydrateTimecode(lowered.value).toFrames().value;
}

function clipDescriptor(item: ClipSnapshot, trackIndex: number, frameRate: FrameRate) {
  return {
    snapshotId: String(item.snapshotId),
    id: item.id === null ? null : String(item.id),
    trackIndex,
    recordStartFrame: frame(item.recordRange.start, frameRate),
    recordEndFrame: frame(item.recordRange.endExclusive, frameRate),
    name: item.name,
    mediaPoolItemId: item.mediaPoolItemId === null ? null : String(item.mediaPoolItemId),
  };
}

function overlaps(left: TimelineRecordRange, right: TimelineRecordRange, frameRate: FrameRate): boolean {
  return frame(left.start, frameRate) < frame(right.endExclusive, frameRate)
    && frame(right.start, frameRate) < frame(left.endExclusive, frameRate);
}

type TimelineItemMoveSingleWireResult = z.infer<typeof sdkTimelineItemMoveSingleResultSchema>;

function hydrateSingleResult(parsed: TimelineItemMoveSingleWireResult, frameRate: FrameRate): TimelineItemMoveResult {
  const item = (entry: TimelineItemMoveSingleWireResult["target"]): TimelineItemMoveObservation => freeze({
    id: TimelineItemIdSchema.parse(entry.id),
    role: entry.role,
    name: entry.name,
    before: freeze({
      trackIndex: entry.before.trackIndex,
      range: hydrateTimelineRecordRange({ domain: "timeline_record_range", unit: "frames", start: entry.before.recordStartFrame, endExclusive: entry.before.recordEndFrame }, { frameRate }),
    }),
    after: freeze({
      trackIndex: entry.after.trackIndex,
      range: hydrateTimelineRecordRange({ domain: "timeline_record_range", unit: "frames", start: entry.after.recordStartFrame, endExclusive: entry.after.recordEndFrame }, { frameRate }),
    }),
    sourceRangePreservation: entry.sourceRangePreservation,
  });
  return freeze({
    target: item(parsed.target),
    linkedAudio: parsed.linkedAudio,
    movedItems: Object.freeze(parsed.movedItems.map(item)),
    timelineRevision: RevisionSchema.parse(parsed.timelineRevision),
  });
}

function hydrateResult(value: unknown, frameRate: FrameRate): TimelineItemMoveResult | TimelineItemMoveBatchResult {
  const parsed = sdkTimelineItemMoveResultSchema.parse(value);
  if ("results" in parsed) return freeze({
    results: Object.freeze(parsed.results.map((result) => hydrateSingleResult(result, frameRate))),
    timelineRevision: RevisionSchema.parse(parsed.timelineRevision),
  });
  return hydrateSingleResult(parsed, frameRate);
}

const durationResultSchema = z.object({
  actionId: z.literal("cutagent.action.timeline.items.set_duration"),
  items: z.array(z.object({
    timelineItemId: z.string(),
    name: z.string(),
    trackType: z.enum(["video", "audio", "subtitle"]),
    trackIndex: z.number().int().min(1),
    recordRange: z.object({
      domain: z.literal("timeline_record_range"),
      unit: z.literal("frames"),
      start: z.number().int(),
      endExclusive: z.number().int(),
    }),
    mediaPoolItemId: z.string().optional(),
  })),
  revisionChange: z.object({
    before: z.string(),
    after: z.string(),
    changed: z.boolean(),
  }),
});

function durationFrames(value: Duration, frameRate: FrameRate, rounding?: TimeRounding): number {
  const result = value.unit === "frames" ? value.value.value : value.toFrames(frameRate, rounding).value.value;
  if (result < 1) throw new TypeError("Timeline item duration must be at least one frame.");
  return result;
}

function hydrateDurationResult(value: unknown, frameRate: FrameRate): TimelineItemDurationResult {
  const parsed = durationResultSchema.parse(value);
  return freeze({
    items: Object.freeze(parsed.items.map((item) => freeze({
      id: TimelineItemIdSchema.parse(item.timelineItemId),
      name: item.name,
      trackType: item.trackType,
      trackIndex: item.trackIndex,
      recordRange: hydrateTimelineRecordRange(item.recordRange, { frameRate }),
      mediaPoolItemId: item.mediaPoolItemId === undefined ? null : MediaPoolItemIdSchema.parse(item.mediaPoolItemId),
    }))),
    revisionChange: freeze({
      before: RevisionSchema.parse(parsed.revisionChange.before),
      after: RevisionSchema.parse(parsed.revisionChange.after),
      changed: parsed.revisionChange.changed,
    }),
  });
}

function hydrateStateChangeResult(value: unknown): TimelineItemStateChangeResult {
  const parsed = sdkBulkClipStateResultSchema.parse(value);
  return freeze({
    items: Object.freeze(parsed.items.map((item) => freeze({
      timelineItemId: TimelineItemIdSchema.parse(item.timelineItemId),
      name: item.name,
      before: item.before,
      after: item.after,
      changed: item.changed,
    }))),
    timelineRevision: RevisionSchema.parse(parsed.timelineRevision),
  });
}

const clipColorResultSchema = z.object({
  actionId: z.literal("cutagent.action.timeline.clip_color.batch"),
  clips: z.array(z.object({
    clipId: z.string(),
    name: z.string(),
    requestedColor: z.string().nullable(),
    actualColor: z.string().nullable(),
    changed: z.boolean(),
  }).strict()).min(1).max(1_000),
  timelineRevision: z.string(),
}).strict();

function hydrateClipColorResult(value: unknown): TimelineClipColorResult {
  const parsed = clipColorResultSchema.parse(value);
  return freeze({
    clips: Object.freeze(parsed.clips.map((entry) => freeze({
      clipId: TimelineItemIdSchema.parse(entry.clipId),
      name: entry.name,
      requestedColor: entry.requestedColor,
      actualColor: entry.actualColor,
      changed: entry.changed,
    }))),
    timelineRevision: RevisionSchema.parse(parsed.timelineRevision),
  });
}

/** Shared exact-target constructor for enable/disable bulk state changes. @internal */
export async function startTimelineItemStateChange<TEnabled extends boolean>(
  runtime: TimelineItemRuntime,
  generation: number,
  readSnapshot: (options?: ConnectionControlOptions) => Promise<TimelineSnapshot>,
  itemOrItems: TimelineItemStateChangeInput,
  enabled: TEnabled,
  options: TimelineItemStateChangeOptions,
): Promise<OperationHandle<TimelineItemStateChangeResult, TEnabled extends true ? "cutagent.action.bulk.enable" : "cutagent.action.bulk.disable">> {
  const supplied = Array.isArray(itemOrItems) ? itemOrItems : [itemOrItems];
  if (supplied.length === 0) throw new TypeError("Timeline item state change requires at least one clip.");
  IdempotencyKeySchema.parse(options.idempotencyKey);
  const snapshot = await readSnapshot(options);
  const allItems = snapshot.tracks.flatMap((track) => track.clips.map((clip) => ({track, clip})));
  const seen = new Set<string>();
  const targets = supplied.map((suppliedItem) => {
    if (suppliedItem.snapshotRevision !== snapshot.revision || suppliedItem.id === null) {
      throw new TypeError("Timeline item state change requires current durable clip references.");
    }
    if (seen.has(suppliedItem.id)) throw new TypeError("Timeline item state change targets must be unique.");
    seen.add(suppliedItem.id);
    const matches = allItems.filter(({clip}) => clip.id === suppliedItem.id);
    if (matches.length !== 1) throw new TypeError("Timeline item reference is stale or no longer present.");
    const match = matches[0]!;
    if (match.track.type === "subtitle"
      || match.clip.snapshotId !== suppliedItem.snapshotId
      || match.clip.name !== suppliedItem.name
      || frame(match.clip.recordRange.start, snapshot.frameRate) !== frame(suppliedItem.recordRange.start, snapshot.frameRate)
      || frame(match.clip.recordRange.endExclusive, snapshot.frameRate) !== frame(suppliedItem.recordRange.endExclusive, snapshot.frameRate)) {
      throw new TypeError("Timeline item reference no longer matches the current snapshot.");
    }
    return {
      snapshotId: String(match.clip.snapshotId),
      id: String(match.clip.id),
      trackType: match.track.type,
      trackIndex: match.track.index,
      recordStartFrame: frame(match.clip.recordRange.start, snapshot.frameRate),
      recordEndFrame: frame(match.clip.recordRange.endExclusive, snapshot.frameRate),
      name: match.clip.name,
      mediaPoolItemId: match.clip.mediaPoolItemId === null ? null : String(match.clip.mediaPoolItemId),
      linkedItemIds: match.clip.linkedItemIds === null ? [] : match.clip.linkedItemIds.map(String),
    };
  });
  const actionId = (enabled ? "cutagent.action.bulk.enable" : "cutagent.action.bulk.disable") as TEnabled extends true ? "cutagent.action.bulk.enable" : "cutagent.action.bulk.disable";
  const input = sdkBulkClipStateInputSchema.parse({
    projectId: String(snapshot.projectId), timelineId: String(snapshot.timelineId),
    timelineRevision: String(snapshot.revision), targets, failurePolicy: "stop",
  });
  const event = await runtime.createOperationAtGeneration(generation, {
    operation: "operation.create", actionId, input,
    idempotencyKey: sdkIdempotencyKeySchema.parse(options.idempotencyKey),
  }, options);
  const resultSchema = z.object({}).passthrough().transform(hydrateStateChangeResult);
  return createTypedOperationHandle({session: () => runtime.sessionAtGeneration(generation)}, event, actionId, resultSchema);
}

function hydrateClipPropertyResult(value: unknown): TimelineClipPropertyResult {
  const parsed = sdkBulkClipPropertyResultSchema.parse(value);
  return freeze({
    items: Object.freeze(parsed.items.map((item) => freeze({
      clipId: TimelineItemIdSchema.parse(item.clipId),
      before: freeze({...item.before}),
      after: freeze({...item.after}),
      changed: item.changed,
    }))),
    timelineRevision: RevisionSchema.parse(parsed.timelineRevision),
    protectedStatePreserved: true,
    stoppedAfterFailure: false,
  });
}
/** Construct timeline-item authoring for one exact client generation. @internal */
export function createTimelineItems(
  runtime: TimelineItemRuntime,
  generation: number,
  readSnapshot: (options?: ConnectionControlOptions) => Promise<TimelineSnapshot>,
  ownsClip: (clip: ClipSnapshot) => boolean,
): TimelineItems {
  const collection = Object.freeze({});
  return freeze({
    async disable(items: TimelineItemStateChangeInput, options: TimelineItemStateChangeOptions) {
      return startTimelineItemStateChange(runtime, generation, readSnapshot, items, false, options);
    },
    async enable(items: TimelineItemStateChangeInput, options: TimelineItemStateChangeOptions) {
      return startTimelineItemStateChange(runtime, generation, readSnapshot, items, true, options);
    },
    async previewMove(
      itemOrRequests: ClipSnapshot | readonly TimelineItemMoveRequest[],
      destination?: TimelineItemMoveDestination,
    ) {
      const snapshot = await readSnapshot();
      const plural = Array.isArray(itemOrRequests);
      const requests: readonly TimelineItemMoveRequest[] = plural
        ? itemOrRequests as readonly TimelineItemMoveRequest[]
        : [{ item: itemOrRequests as ClipSnapshot, destination: destination as TimelineItemMoveDestination }];
      if (requests.length === 0 || requests.length > 100) throw new TypeError("Timeline item move requires between 1 and 100 requests.");
      if (!plural && !destination) throw new TypeError("Timeline item move requires a destination.");
      const resolved = requests.map(({ item, destination: requestedDestination }) => {
        if (item.snapshotRevision !== snapshot.revision || requestedDestination.track.snapshotRevision !== snapshot.revision) {
          throw new TypeError("Timeline item move references must belong to the current snapshot revision.");
        }
        const targetMatches = snapshot.tracks.flatMap((track) => track.clips
          .filter((clip) => item.id === null ? clip.snapshotId === item.snapshotId : clip.id === item.id)
          .map((clip) => ({ track, clip })));
        const targetMatch = targetMatches.length === 1 ? targetMatches[0] : undefined;
        const sourceTrack = targetMatch?.track;
        const exactTarget = targetMatch?.clip;
        const destinationTracks = snapshot.tracks.filter((track) => (
          track.timelineId === requestedDestination.track.timelineId
          && track.type === requestedDestination.track.type
          && track.index === requestedDestination.track.index
        ));
        const destinationTrack = destinationTracks.length === 1 ? destinationTracks[0] : undefined;
        if (!sourceTrack || !exactTarget) throw new TypeError("Timeline item reference is stale or no longer present.");
        if (!destinationTrack || destinationTrack.type !== "video" || sourceTrack.type !== "video") {
          throw new TypeError("Timeline video items can move only between video tracks.");
        }
        const startFrame = frame(requestedDestination.start ?? exactTarget.recordRange.start, snapshot.frameRate);
        const duration = frame(exactTarget.recordRange.endExclusive, snapshot.frameRate) - frame(exactTarget.recordRange.start, snapshot.frameRate);
        const after = hydrateTimelineRecordRange({ domain: "timeline_record_range", unit: "frames", start: startFrame, endExclusive: startFrame + duration }, { frameRate: snapshot.frameRate });
        if (startFrame < frame(snapshot.start, snapshot.frameRate)) throw new TypeError("Timeline item move cannot precede the timeline start.");
        if (destinationTrack.index === sourceTrack.index && startFrame === frame(exactTarget.recordRange.start, snapshot.frameRate)) {
          throw new TypeError("Timeline item move must change the record position or video track.");
        }
        return {
          destination: requestedDestination, sourceTrack, exactTarget, destinationTrack, startFrame, after,
          linkedAudioPolicy: requestedDestination.linkedAudio ?? "preserve" as LinkedAudioMovePolicy,
          collisionPolicy: requestedDestination.collisionPolicy ?? "reject" as "reject" | "allow",
          changesRecordPosition: startFrame !== frame(exactTarget.recordRange.start, snapshot.frameRate),
        };
      });
      const movingVideoSnapshotIds = new Set(resolved.map(({ exactTarget }) => exactTarget.snapshotId));
      if (movingVideoSnapshotIds.size !== resolved.length) throw new TypeError("Timeline item move cannot contain the same video item more than once.");
      const movingLinkedSnapshotIds = new Set<string>();
      for (const entry of resolved) {
        if (entry.linkedAudioPolicy !== "preserve" || !entry.changesRecordPosition || entry.exactTarget.linkedItemIds === null) continue;
        for (const linkedId of entry.exactTarget.linkedItemIds) {
          for (const track of snapshot.tracks) for (const clip of track.clips) if (track.type === "audio" && clip.id === linkedId) movingLinkedSnapshotIds.add(clip.snapshotId);
        }
      }
      const impacts = resolved.map(({ sourceTrack, exactTarget, destinationTrack, startFrame, after, linkedAudioPolicy, collisionPolicy, changesRecordPosition }) => {
      const linkedAudioItems: ClipSnapshot[] = [];
      const linkedAudioMatches: { readonly track: TrackSnapshot; readonly clip: ClipSnapshot }[] = [];
      const linkedAudioDescriptors: ReturnType<typeof clipDescriptor>[] = [];
      const blockers: TimelineItemMoveBlocker[] = [];
      if (exactTarget.id === null) blockers.push(freeze({ code: "durable_identity_required", summary: "Timeline item move requires a durable native item identity." }));
      if (sourceTrack.locked === true) blockers.push(freeze({ code: "locked_source_track", summary: "The source video track is locked." }));
      if (destinationTrack.locked === true) blockers.push(freeze({ code: "locked_destination_track", summary: "The destination video track is locked." }));
      if (sourceTrack.locked === null || destinationTrack.locked === null) blockers.push(freeze({ code: "unknown_track_lock_state", summary: "DaVinci Resolve did not expose authoritative lock state for every affected video track." }));
      if (exactTarget.linkedItemIds === null) {
        blockers.push(freeze({ code: "linked_topology_unavailable", summary: "DaVinci Resolve did not expose authoritative linked-item topology." }));
      } else {
        for (const linkedId of exactTarget.linkedItemIds) {
          const matches = snapshot.tracks.flatMap((track) => track.clips.map((clip) => ({ track, clip }))).filter(({ clip }) => clip.id === linkedId);
          if (matches.length !== 1 || matches[0]?.track.type !== "audio") {
            blockers.push(freeze({ code: "unsupported_link_group", summary: "The linked group is ambiguous or contains a non-audio companion." }));
            continue;
          }
          const linkedMatch = matches[0];
          linkedAudioItems.push(linkedMatch.clip);
          linkedAudioMatches.push(linkedMatch);
          linkedAudioDescriptors.push(clipDescriptor(linkedMatch.clip, linkedMatch.track.index, snapshot.frameRate));
          if (linkedAudioPolicy === "preserve" && changesRecordPosition && linkedMatch.track.locked === true) {
            blockers.push(freeze({ code: "locked_linked_audio_track", summary: `Linked audio track A${linkedMatch.track.index} is locked.` }));
          }
          if (linkedAudioPolicy === "preserve" && changesRecordPosition && linkedMatch.track.locked === null) blockers.push(freeze({ code: "unknown_track_lock_state", summary: `DaVinci Resolve did not expose authoritative lock state for linked audio track A${linkedMatch.track.index}.` }));
        }
        const closedGroupIds = new Set([exactTarget.id, ...linkedAudioItems.map((item) => item.id)]);
        if (linkedAudioItems.some((item) => item.linkedItemIds === null
          || exactTarget.id === null
          || !item.linkedItemIds.includes(exactTarget.id)
          || item.linkedItemIds.some((linkedId) => !closedGroupIds.has(linkedId)))) {
          blockers.push(freeze({ code: "unsupported_link_group", summary: "The linked A/V group is not authoritative and closed over the selected video and audio items." }));
        }
        for (const linkedMatch of linkedAudioMatches) {
          const linkedAfter = hydrateTimelineRecordRange({
            domain: "timeline_record_range",
            unit: "frames",
            start: frame(linkedMatch.clip.recordRange.start, snapshot.frameRate) + (startFrame - frame(exactTarget.recordRange.start, snapshot.frameRate)),
            endExclusive: frame(linkedMatch.clip.recordRange.endExclusive, snapshot.frameRate) + (startFrame - frame(exactTarget.recordRange.start, snapshot.frameRate)),
          }, { frameRate: snapshot.frameRate });
          const linkedCollisions = linkedMatch.track.clips.filter((clip) => !movingLinkedSnapshotIds.has(clip.snapshotId) && overlaps(clip.recordRange, linkedAfter, snapshot.frameRate));
          const pluralLinkedCollision = resolved.some((other) => other !== resolved.find((candidate) => candidate.exactTarget === exactTarget)
            && other.linkedAudioPolicy === "preserve" && other.changesRecordPosition
            && other.exactTarget.linkedItemIds?.some((id) => {
              const match = snapshot.tracks.flatMap((track) => track.clips.map((clip) => ({ track, clip }))).find(({ clip }) => clip.id === id);
              if (!match || match.track.type !== "audio" || match.track.index !== linkedMatch.track.index) return false;
              const delta = other.startFrame - frame(other.exactTarget.recordRange.start, snapshot.frameRate);
              const otherAfter = hydrateTimelineRecordRange({ domain: "timeline_record_range", unit: "frames", start: frame(match.clip.recordRange.start, snapshot.frameRate) + delta, endExclusive: frame(match.clip.recordRange.endExclusive, snapshot.frameRate) + delta }, { frameRate: snapshot.frameRate });
              return overlaps(linkedAfter, otherAfter, snapshot.frameRate);
            }));
          if (linkedAudioPolicy === "preserve" && changesRecordPosition && collisionPolicy === "reject" && (linkedCollisions.length > 0 || pluralLinkedCollision)) {
            blockers.push(freeze({ code: "linked_audio_collision", summary: `Linked audio would overlap another item on A${linkedMatch.track.index}.` }));
          }
        }
      }
      const collisions = destinationTrack.clips.filter((clip) => !movingVideoSnapshotIds.has(clip.snapshotId) && overlaps(clip.recordRange, after, snapshot.frameRate));
      const pluralCollision = resolved.some((other) => other.exactTarget !== exactTarget
        && other.destinationTrack.index === destinationTrack.index
        && overlaps(other.after, after, snapshot.frameRate));
      if (collisionPolicy === "reject" && (collisions.length > 0 || pluralCollision)) {
        blockers.push(freeze({ code: "destination_collision", summary: "The destination range overlaps another timeline item." }));
      }
      const impact = freeze({
        projectId: snapshot.projectId,
        timelineId: snapshot.timelineId,
        timelineRevision: snapshot.revision,
        target: exactTarget,
        sourceTrack,
        destinationTrack,
        before: exactTarget.recordRange,
        after,
        linkedAudioPolicy,
        linkedAudioItems: Object.freeze(linkedAudioItems),
        collisions: Object.freeze(collisions),
        blockers: Object.freeze(blockers),
        canApply: blockers.length === 0,
        summary: `Move video item ${exactTarget.name} from V${sourceTrack.index} to V${destinationTrack.index} at record frame ${startFrame}${linkedAudioItems.length > 0 ? ` with ${linkedAudioItems.length} linked audio item(s)` : ""}.`,
      });
      previewInternals.set(impact, { public: impact, collection, frameRate: snapshot.frameRate, linkedAudioDescriptors: Object.freeze(linkedAudioDescriptors), collisionPolicy });
      return impact;
      });
      return plural ? Object.freeze(impacts) : impacts[0]!;
    },
    async move(impactOrImpacts: TimelineItemMoveImpactPreview | readonly TimelineItemMoveImpactPreview[], options: TimelineItemMoveOptions) {
      const plural = Array.isArray(impactOrImpacts);
      const impacts = plural ? impactOrImpacts as readonly TimelineItemMoveImpactPreview[] : [impactOrImpacts as TimelineItemMoveImpactPreview];
      if (impacts.length === 0 || impacts.length > 100) throw new TypeError("Timeline item move requires between 1 and 100 previews.");
      const internals = impacts.map((impact) => {
        const internal = previewInternals.get(impact);
        if (!internal || internal.public !== impact || internal.collection !== collection) {
          throw new TypeError("Timeline item move requires previews created by this timeline reference.");
        }
        if (!impact.canApply) throw new TypeError("Timeline item move preview contains blockers and cannot be applied.");
        return internal;
      });
      if (new Set(impacts.map((impact) => impact.timelineRevision)).size !== 1) throw new TypeError("Timeline item move previews must share one timeline revision.");
      IdempotencyKeySchema.parse(options.idempotencyKey);
      const moves = impacts.map((impact, index) => ({
          projectId: String(impact.projectId),
          timelineId: String(impact.timelineId),
          timelineRevision: String(impact.timelineRevision),
          target: clipDescriptor(impact.target, impact.sourceTrack.index, internals[index]!.frameRate),
          linkedAudioTargets: internals[index]!.linkedAudioDescriptors,
          destination: {
            trackIndex: impact.destinationTrack.index,
            recordStartFrame: frame(impact.after.start, internals[index]!.frameRate),
          },
          linkedAudio: impact.linkedAudioPolicy,
          collisionPolicy: internals[index]!.collisionPolicy,
      }));
      const input = sdkTimelineItemMoveInputSchema.parse(plural ? { moves } : moves[0]);
      const request: CarrierOperationRequest = {
        operation: "operation.create",
        actionId: "cutagent.action.timeline.items.move",
        input,
        idempotencyKey: sdkIdempotencyKeySchema.parse(options.idempotencyKey),
      };
      const event = await runtime.createOperationAtGeneration(generation, request, options);
      const resultSchema = z.object({}).passthrough().transform((result) => hydrateResult(result, internals[0]!.frameRate));
      return createTypedOperationHandle({ session: () => runtime.sessionAtGeneration(generation) }, event, "cutagent.action.timeline.items.move", resultSchema);
    },
    async setDuration(
      change: TimelineItemDurationChange | readonly TimelineItemDurationChange[],
      options: TimelineItemDurationOptions,
    ) {
      const changes = Array.isArray(change) ? change : [change];
      if (changes.length === 0) throw new TypeError("Timeline item duration changes require at least one item.");
      if (changes.length > 10_000) throw new TypeError("Timeline item duration changes support at most 10000 items.");
      IdempotencyKeySchema.parse(options.idempotencyKey);
      const snapshot = await readSnapshot(options);
      const currentItems = new Map(snapshot.tracks.flatMap((track) => track.clips).filter((item) => item.id !== null).map((item) => [item.id, item]));
      const requestedIds = changes.map(({ item }) => item.id);
      if (requestedIds.some((id) => id === null)) throw new TypeError("Timeline item duration changes require durable item identities.");
      if (new Set(requestedIds).size !== requestedIds.length) throw new TypeError("Timeline item duration changes cannot contain duplicate items.");
      for (const id of requestedIds) {
        if (!currentItems.has(id!)) throw new TypeError("Timeline item duration reference is stale or no longer present.");
      }
      const input = {
        projectId: String(snapshot.projectId),
        timelineId: String(snapshot.timelineId),
        revision: String(snapshot.revision),
        updates: changes.map((entry) => ({
          timelineItemId: String(entry.item.id),
          duration: { domain: "duration" as const, value: { kind: "frames" as const, value: durationFrames(entry.duration, snapshot.frameRate, options.rounding) } },
          ...(entry.allowOverlap === undefined ? {} : { allowOverlap: entry.allowOverlap }),
          ...(entry.enforceSourceBounds === undefined ? {} : { enforceSourceBounds: entry.enforceSourceBounds }),
        })),
      };
      const request = {
        operation: "operation.create",
        actionId: "cutagent.action.timeline.items.set_duration",
        input,
        idempotencyKey: sdkIdempotencyKeySchema.parse(options.idempotencyKey),
      } as unknown as CarrierOperationRequest;
      const event = await runtime.createOperationAtGeneration(generation, request, options);
      const resultSchema = z.object({}).passthrough().transform((result) => hydrateDurationResult(result, snapshot.frameRate));
      return createTypedOperationHandle({ session: () => runtime.sessionAtGeneration(generation) }, event, "cutagent.action.timeline.items.set_duration", resultSchema);
    },
    async setColor(change: TimelineClipColorChange | readonly TimelineClipColorChange[], options: TimelineItemMoveOptions) {
      const changes = Array.isArray(change) ? change : [change];
      if (changes.length === 0 || changes.length > 1_000) {
        throw new TypeError("Timeline clip-color changes require between 1 and 1,000 clips.");
      }
      IdempotencyKeySchema.parse(options.idempotencyKey);
      const snapshot = await readSnapshot(options);
      const snapshotRows = snapshot.tracks.flatMap((track) => track.clips.map((clip) => ({track, clip})));
      const seen = new Set<string>();
      const updates = changes.map((entry) => {
        if (typeof entry !== "object" || entry === null || !("clip" in entry) || !("color" in entry)) {
          throw new TypeError("Each timeline clip-color change requires a clip and color.");
        }
        const match = snapshotRows.find(({clip}) => clip.id !== null && clip.id === entry.clip.id);
        if (!ownsClip(entry.clip)
          || !match
          || entry.clip.snapshotRevision !== snapshot.revision
          || entry.clip.snapshotId !== match.clip.snapshotId
          || entry.clip.name !== match.clip.name
          || match.clip.id === null) {
          throw new TypeError("Timeline clip-color changes require durable clips from the current snapshot.");
        }
        if (seen.has(match.clip.id)) throw new TypeError("Timeline clip-color changes must target each clip at most once.");
        seen.add(match.clip.id);
        if (entry.color !== null && (typeof entry.color !== "string" || entry.color.trim().length === 0 || entry.color.length > 64)) {
          throw new TypeError("Timeline clip colors must be a non-empty color name or null.");
        }
        const descriptor = clipDescriptor(match.clip, match.track.index, snapshot.frameRate);
        return {
          timelineItemId: descriptor.id,
          snapshotTimelineItemId: descriptor.snapshotId,
          trackType: match.track.type,
          trackIndex: descriptor.trackIndex,
          recordStartFrame: descriptor.recordStartFrame,
          recordEndFrame: descriptor.recordEndFrame,
          name: descriptor.name,
          color: entry.color === null ? null : entry.color.trim(),
        };
      });
      const input = sdkTimelineClipColorBatchInputSchema.parse({
        projectId: String(snapshot.projectId),
        timelineId: String(snapshot.timelineId),
        revision: String(snapshot.revision),
        updates,
      });
      const request: CarrierOperationRequest = {
        operation: "operation.create",
        actionId: "cutagent.action.timeline.clip_color.batch",
        input,
        idempotencyKey: sdkIdempotencyKeySchema.parse(options.idempotencyKey),
      };
      const event = await runtime.createOperationAtGeneration(generation, request, options);
      const resultSchema = z.object({}).passthrough().transform(hydrateClipColorResult);
      return createTypedOperationHandle({ session: () => runtime.sessionAtGeneration(generation) }, event, "cutagent.action.timeline.clip_color.batch", resultSchema);
    },
    async setProperties(change: TimelineClipPropertyChange | readonly TimelineClipPropertyChange[], options: TimelineClipPropertyOptions) {
      const changes = Array.isArray(change) ? change : [change];
      if (changes.length === 0 || changes.length > 1_000) {
        throw new TypeError("Timeline clip property changes require between 1 and 1,000 clips.");
      }
      IdempotencyKeySchema.parse(options.idempotencyKey);
      const snapshot = await readSnapshot(options);
      const snapshotRows = snapshot.tracks.flatMap((track) => track.clips.map((clip) => ({track, clip})));
      const seen = new Set<string>();
      const items = changes.map((entry) => {
        if (typeof entry !== "object" || entry === null || !("clip" in entry) || !("properties" in entry)) {
          throw new TypeError("Each timeline clip property change requires a clip and supported properties.");
        }
        const matches = snapshotRows.filter(({clip}) => entry.clip.id !== null
          && clip.id === entry.clip.id && clip.snapshotId === entry.clip.snapshotId);
        const match = matches.length === 1 ? matches[0] : undefined;
        if (!match || entry.clip.snapshotRevision !== snapshot.revision
          || match.clip.snapshotRevision !== snapshot.revision || match.clip.id === null) {
          throw new TypeError("Timeline clip property changes require durable clips from the current snapshot.");
        }
        if (match.track.type !== "video") throw new TypeError("Supported timeline clip properties require video clips.");
        if (entry.clip.linkedItemIds === null || match.clip.linkedItemIds === null) {
          throw new TypeError("Timeline clip property changes require authoritative linked-item topology.");
        }
        const requestedDescriptor = clipDescriptor(entry.clip, match.track.index, snapshot.frameRate);
        const currentDescriptor = clipDescriptor(match.clip, match.track.index, snapshot.frameRate);
        if (JSON.stringify(requestedDescriptor) !== JSON.stringify(currentDescriptor)
          || JSON.stringify(entry.clip.linkedItemIds) !== JSON.stringify(match.clip.linkedItemIds)) {
          throw new TypeError("Timeline clip property target fields changed after the supplied snapshot.");
        }
        if (seen.has(match.clip.id)) throw new TypeError("Timeline clip property changes must target each clip at most once.");
        seen.add(match.clip.id);
        const properties = sdkClipTransformValuesSchema.parse(entry.properties);
        const descriptor = clipDescriptor(match.clip, match.track.index, snapshot.frameRate);
        return {
          target: {
            ...descriptor,
            id: String(match.clip.id),
            trackType: "video" as const,
            linkedItemIds: match.clip.linkedItemIds.map(String),
          },
          properties,
        };
      });
      const input = sdkBulkClipPropertyInputSchema.parse({
        projectId: String(snapshot.projectId),
        timelineId: String(snapshot.timelineId),
        timelineRevision: String(snapshot.revision),
        items,
        failurePolicy: "stop",
      });
      const request: CarrierOperationRequest = {
        operation: "operation.create",
        actionId: "cutagent.action.bulk.property_set",
        input,
        idempotencyKey: sdkIdempotencyKeySchema.parse(options.idempotencyKey),
      };
      const event = await runtime.createOperationAtGeneration(generation, request, options);
      const resultSchema = z.object({}).passthrough().transform(hydrateClipPropertyResult);
      return createTypedOperationHandle({ session: () => runtime.sessionAtGeneration(generation) }, event, "cutagent.action.bulk.property_set", resultSchema);
    },
  }) as unknown as TimelineItems;
}
