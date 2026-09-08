import type { ActionInput } from "../generated/actions.js";
import {
  frames,
  sourceRange,
  timelineRecordPosition,
  timelineRecordRange,
  type BoundFrames,
  type Frames,
  type TimelineRecordPositionOf,
} from "../value-types/time.js";
import { lowerSourceRange, lowerTimelineRecordPosition, lowerTimelineRecordRange } from "../wire/time-adapter.js";
import type { ClipSnapshot, TimelineSnapshot, TrackSnapshot } from "./object-model.js";

/** Exact project, timeline, and revision precondition captured by one timeline snapshot. @beta */
export interface TimelineActionBinding {
  readonly projectId: TimelineSnapshot["projectId"];
  readonly timelineId: TimelineSnapshot["timelineId"];
  readonly timelineRevision: TimelineSnapshot["revision"];
}

/** Exact video target accepted by Inspector, keyframe, and reviewed effect actions. @beta */
export type TimelineVideoActionTarget = ActionInput<"cutagent.action.clip.transform">["target"];

/** Exact video target accepted by native speed-ramp actions. @beta */
export type TimelineVideoRetimeTarget = ActionInput<"cutagent.action.clip.speed_ramp">["incoming"];

/** Exact video or audio target accepted by the native blade action. @beta */
export type TimelineBladeActionTarget = ActionInput<"cutagent.action.edit.blade">["target"];

/**
 * Snapshot-bound helpers for generic timeline Actions.
 *
 * Create a new context after every successful mutation. The captured revision
 * remains an explicit stale-state precondition; operation waiting, verification,
 * retry identity, and recovery stay owned by the caller and `client.actions`.
 *
 * @beta
 */
export interface TimelineActionContext {
  /** Exact binding added to an action input by `input()`. */
  readonly binding: TimelineActionBinding;

  /** Add this snapshot's exact identity and revision to action-specific fields. */
  input<const T extends object>(fields: T & {
    readonly projectId?: never;
    readonly timelineId?: never;
    readonly timelineRevision?: never;
  }): Readonly<T & TimelineActionBinding>;

  /** Build a fully linked video target for Inspector, keyframe, and reviewed effect actions. */
  videoTarget(clip: ClipSnapshot): TimelineVideoActionTarget;

  /** Build the narrower exact target required by native blade. */
  bladeTarget(clip: ClipSnapshot): TimelineBladeActionTarget;

  /** Build a frame-domain, source-bound video target for native speed ramps. */
  videoRetimeTarget(clip: ClipSnapshot): TimelineVideoRetimeTarget;
}

/**
 * Convert a non-negative frame offset from a timeline's start into its absolute
 * record-domain position. DaVinci Resolve timelines commonly begin at 01:00:00:00,
 * so a raw record frame of zero is not a portable timeline-start coordinate.
 *
 * @beta
 */
export function timelineRecordOffset(
  snapshot: TimelineSnapshot,
  offset: Frames | BoundFrames,
): TimelineRecordPositionOf<BoundFrames> {
  if (offset.value < 0) {
    throw new TypeError("Timeline record offsets cannot be negative.");
  }
  const start = lowerTimelineRecordPosition(snapshot.start, { frameRate: snapshot.frameRate });
  if (start.value.kind !== "frames") {
    throw new TypeError("Timeline snapshot start has no exact frame-domain position.");
  }
  const absolute = frames(start.value.value, snapshot.frameRate).add(offset);
  return timelineRecordPosition(absolute, snapshot.frameRate);
}

function owningTrack(snapshot: TimelineSnapshot, clip: ClipSnapshot): TrackSnapshot {
  if (clip.snapshotRevision !== snapshot.revision) {
    throw new TypeError("Timeline action targets must come from the bound snapshot revision.");
  }
  const matches = snapshot.tracks.filter((track) => track.clips.includes(clip));
  if (matches.length !== 1) {
    throw new TypeError("Timeline action targets must be the exact clip object from the bound snapshot.");
  }
  const track = matches[0]!;
  if (track.timelineId !== snapshot.timelineId
    || track.snapshotRevision !== snapshot.revision
    || track.snapshotId !== clip.snapshotTrackId) {
    throw new TypeError("Timeline action target identity does not match its containing snapshot track.");
  }
  return track;
}

function durableTarget(snapshot: TimelineSnapshot, clip: ClipSnapshot) {
  const track = owningTrack(snapshot, clip);
  if (clip.id === null) {
    throw new TypeError(`Clip ${JSON.stringify(clip.name)} has no durable timeline-item identity.`);
  }
  const recordRange = lowerTimelineRecordRange(clip.recordRange, { frameRate: snapshot.frameRate });
  if (recordRange.unit !== "frames") {
    throw new TypeError(`Clip ${JSON.stringify(clip.name)} has no exact frame-domain record range.`);
  }
  return { id: clip.id, track, recordRange } as const;
}

/** Bind exact timeline action input and target helpers to one immutable snapshot. @beta */
export function timelineActionContext(snapshot: TimelineSnapshot): TimelineActionContext {
  const binding = Object.freeze({
    projectId: snapshot.projectId,
    timelineId: snapshot.timelineId,
    timelineRevision: snapshot.revision,
  });

  return Object.freeze({
    binding,
    input<const T extends object>(fields: T & {
      readonly projectId?: never;
      readonly timelineId?: never;
      readonly timelineRevision?: never;
    }): Readonly<T & TimelineActionBinding> {
      if (["projectId", "timelineId", "timelineRevision"].some((key) => Object.hasOwn(fields, key))) {
        throw new TypeError("Snapshot-bound action identity and revision cannot be overridden.");
      }
      return Object.freeze({ ...fields, ...binding });
    },
    videoTarget(clip: ClipSnapshot): TimelineVideoActionTarget {
      const { id, track, recordRange } = durableTarget(snapshot, clip);
      if (track.type !== "video" || clip.linkedItemIds === null) {
        throw new TypeError(`Clip ${JSON.stringify(clip.name)} is not a fully linked video target.`);
      }
      return Object.freeze({
        id,
        snapshotId: clip.snapshotId,
        mediaPoolItemId: clip.mediaPoolItemId,
        name: clip.name,
        trackType: "video",
        trackIndex: track.index,
        recordStartFrame: recordRange.start,
        recordEndFrame: recordRange.endExclusive,
        linkedItemIds: Object.freeze([...clip.linkedItemIds]),
      });
    },
    bladeTarget(clip: ClipSnapshot): TimelineBladeActionTarget {
      const { id, track, recordRange } = durableTarget(snapshot, clip);
      if (track.type === "subtitle") {
        throw new TypeError(`Clip ${JSON.stringify(clip.name)} is not a video or audio blade target.`);
      }
      return Object.freeze({
        id,
        snapshotId: clip.snapshotId,
        mediaPoolItemId: clip.mediaPoolItemId,
        name: clip.name,
        trackType: track.type,
        trackIndex: track.index,
        recordStartFrame: recordRange.start,
        recordEndFrame: recordRange.endExclusive,
      });
    },
    videoRetimeTarget(clip: ClipSnapshot): TimelineVideoRetimeTarget {
      const { id, track, recordRange } = durableTarget(snapshot, clip);
      if (track.type !== "video" || clip.mediaPoolItemId === null
        || clip.linkedItemIds === null || (clip.sourceRange === null && clip.retimeSource === null) || clip.sourceFrameRate === null) {
        throw new TypeError(`Clip ${JSON.stringify(clip.name)} is not a fully sourced, linked video retime target.`);
      }
      // A ramp may sample handles outside the current trimmed interval. Prefer
      // native available-media authority without changing the clip's placement.
      const authoringSource = clip.retimeSource?.availableRange ?? clip.sourceRange!;
      const loweredSourceRange = lowerSourceRange(authoringSource, { frameRate: clip.sourceFrameRate });
      if (loweredSourceRange.unit !== "frames") {
        throw new TypeError(`Clip ${JSON.stringify(clip.name)} has no exact frame-domain source range and rate.`);
      }
      return Object.freeze({
        id,
        snapshotId: clip.snapshotId,
        mediaPoolItemId: clip.mediaPoolItemId,
        name: clip.name,
        trackType: "video",
        trackIndex: track.index,
        recordRange: timelineRecordRange(
          frames(recordRange.start),
          frames(recordRange.endExclusive),
          snapshot.frameRate,
        ),
        sourceRange: sourceRange(
          frames(loweredSourceRange.start),
          frames(loweredSourceRange.endExclusive),
          clip.sourceFrameRate,
        ),
        ...(clip.retimeSource !== null ? { sourceOriginFrame: clip.retimeSource.originFrame } : {}),
        linkedItemIds: Object.freeze([...clip.linkedItemIds]),
      });
    },
  });
}
