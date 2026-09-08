import { z } from "zod";
import {
  sdkTimelineItemMoveInputSchema,
  sdkTimelineItemMoveResultSchema,
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
  RevisionSchema,
  TimelineItemIdSchema,
  type IdempotencyKey,
  type ProjectId,
  type Revision,
  type TimelineId,
  type TimelineItemId,
} from "../value-types/identities.js";
import type { FrameRate, TimelineRecordPosition, TimelineRecordRange } from "../value-types/time.js";
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

/** Required replay-safe control values for a timeline-item move. @beta */
export interface TimelineItemMoveOptions extends ConnectionControlOptions {
  readonly idempotencyKey: IdempotencyKey;
}

/** Semantic timeline-item inspection, impact preview, and durable mutation API. @beta */
export interface TimelineItems {
  previewMove(item: ClipSnapshot, destination: TimelineItemMoveDestination): Promise<TimelineItemMoveImpactPreview>;
  move(preview: TimelineItemMoveImpactPreview, options: TimelineItemMoveOptions): Promise<OperationHandle<TimelineItemMoveResult, "cutagent.action.timeline.items.move">>;
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

function hydrateResult(value: unknown, frameRate: FrameRate): TimelineItemMoveResult {
  const parsed = sdkTimelineItemMoveResultSchema.parse(value);
  const item = (entry: typeof parsed.target): TimelineItemMoveObservation => freeze({
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

/** Construct timeline-item authoring for one exact client generation. @internal */
export function createTimelineItems(
  runtime: TimelineItemRuntime,
  generation: number,
  readSnapshot: (options?: ConnectionControlOptions) => Promise<TimelineSnapshot>,
): TimelineItems {
  const collection = Object.freeze({});
  return freeze({
    async previewMove(item, destination) {
      const snapshot = await readSnapshot();
      if (item.snapshotRevision !== snapshot.revision || destination.track.snapshotRevision !== snapshot.revision) {
        throw new TypeError("Timeline item move references must belong to the current snapshot revision.");
      }
      const targetMatches = snapshot.tracks.flatMap((track) => track.clips
        .filter((clip) => item.id === null ? clip.snapshotId === item.snapshotId : clip.id === item.id)
        .map((clip) => ({ track, clip })));
      const targetMatch = targetMatches.length === 1 ? targetMatches[0] : undefined;
      const sourceTrack = targetMatch?.track;
      const exactTarget = targetMatch?.clip;
      const destinationTracks = snapshot.tracks.filter((track) => (
        track.timelineId === destination.track.timelineId
        && track.type === destination.track.type
        && track.index === destination.track.index
      ));
      const destinationTrack = destinationTracks.length === 1 ? destinationTracks[0] : undefined;
      if (!sourceTrack || !exactTarget) throw new TypeError("Timeline item reference is stale or no longer present.");
      if (!destinationTrack || destinationTrack.type !== "video" || sourceTrack.type !== "video") {
        throw new TypeError("Timeline video items can move only between video tracks.");
      }
      const start = destination.start ?? exactTarget.recordRange.start;
      const startFrame = frame(start, snapshot.frameRate);
      const duration = frame(exactTarget.recordRange.endExclusive, snapshot.frameRate) - frame(exactTarget.recordRange.start, snapshot.frameRate);
      const after = hydrateTimelineRecordRange({ domain: "timeline_record_range", unit: "frames", start: startFrame, endExclusive: startFrame + duration }, { frameRate: snapshot.frameRate });
      if (startFrame < frame(snapshot.start, snapshot.frameRate)) throw new TypeError("Timeline item move cannot precede the timeline start.");
      if (destinationTrack.type === sourceTrack.type && destinationTrack.index === sourceTrack.index && startFrame === frame(exactTarget.recordRange.start, snapshot.frameRate)) {
        throw new TypeError("Timeline item move must change the record position or video track.");
      }
      const linkedAudioPolicy = destination.linkedAudio ?? "preserve";
      const changesRecordPosition = startFrame !== frame(exactTarget.recordRange.start, snapshot.frameRate);
      const linkedAudioItems: ClipSnapshot[] = [];
      const linkedAudioMatches: { readonly track: TrackSnapshot; readonly clip: ClipSnapshot }[] = [];
      const linkedAudioDescriptors: ReturnType<typeof clipDescriptor>[] = [];
      const blockers: TimelineItemMoveBlocker[] = [];
      const collisionPolicy = destination.collisionPolicy ?? "reject";
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
        const movingLinkedSnapshotIds = new Set(linkedAudioItems.map((linkedItem) => linkedItem.snapshotId));
        for (const linkedMatch of linkedAudioMatches) {
          const linkedAfter = hydrateTimelineRecordRange({
            domain: "timeline_record_range",
            unit: "frames",
            start: frame(linkedMatch.clip.recordRange.start, snapshot.frameRate) + (startFrame - frame(exactTarget.recordRange.start, snapshot.frameRate)),
            endExclusive: frame(linkedMatch.clip.recordRange.endExclusive, snapshot.frameRate) + (startFrame - frame(exactTarget.recordRange.start, snapshot.frameRate)),
          }, { frameRate: snapshot.frameRate });
          const linkedCollisions = linkedMatch.track.clips.filter((clip) => !movingLinkedSnapshotIds.has(clip.snapshotId) && overlaps(clip.recordRange, linkedAfter, snapshot.frameRate));
          if (linkedAudioPolicy === "preserve" && changesRecordPosition && collisionPolicy === "reject" && linkedCollisions.length > 0) {
            blockers.push(freeze({ code: "linked_audio_collision", summary: `Linked audio would overlap ${linkedCollisions.length} item(s) on A${linkedMatch.track.index}.` }));
          }
        }
      }
      const collisions = destinationTrack.clips.filter((clip) => clip.snapshotId !== exactTarget.snapshotId && overlaps(clip.recordRange, after, snapshot.frameRate));
      if (collisionPolicy === "reject" && collisions.length > 0) {
        blockers.push(freeze({ code: "destination_collision", summary: `The destination range overlaps ${collisions.length} existing video item(s).` }));
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
    },
    async move(impact, options) {
      const internal = previewInternals.get(impact);
      if (!internal || internal.public !== impact || internal.collection !== collection) {
        throw new TypeError("Timeline item move requires a preview created by this timeline reference.");
      }
      if (!impact.canApply) throw new TypeError("Timeline item move preview contains blockers and cannot be applied.");
      IdempotencyKeySchema.parse(options.idempotencyKey);
      const input = sdkTimelineItemMoveInputSchema.parse({
        projectId: String(impact.projectId),
        timelineId: String(impact.timelineId),
        timelineRevision: String(impact.timelineRevision),
        target: clipDescriptor(impact.target, impact.sourceTrack.index, internal.frameRate),
        linkedAudioTargets: internal.linkedAudioDescriptors,
        destination: {
          trackIndex: impact.destinationTrack.index,
          recordStartFrame: frame(impact.after.start, internal.frameRate),
        },
        linkedAudio: impact.linkedAudioPolicy,
        collisionPolicy: internal.collisionPolicy,
      });
      const request: CarrierOperationRequest = {
        operation: "operation.create",
        actionId: "cutagent.action.timeline.items.move",
        input,
        idempotencyKey: sdkIdempotencyKeySchema.parse(options.idempotencyKey),
      };
      const event = await runtime.createOperationAtGeneration(generation, request, options);
      const resultSchema = z.object({}).passthrough().transform((result) => hydrateResult(result, internal.frameRate));
      return createTypedOperationHandle({ session: () => runtime.sessionAtGeneration(generation) }, event, "cutagent.action.timeline.items.move", resultSchema);
    },
  });
}
