import type { CarrierReadRequest, CarrierReadSuccess } from "../core/carrier-session.js";
import type { ConnectionControlOptions } from "../core/public-client-types.js";
import {
  sdkMediaPoolItemIdSchema,
  sdkProjectIdSchema,
  sdkRevisionSchema,
  sdkSnapshotTimelineItemIdSchema,
  sdkSnapshotTrackIdSchema,
  sdkTimelineIdSchema,
  sdkTimelineItemIdSchema,
} from "../generated/sdk-identities.js";
import { CutAgentSdkError, PUBLIC_ERROR_KIND_BY_CODE } from "../protocol/errors.js";
import {
  ProjectIdSchema,
  RequestIdSchema,
  MediaPoolItemIdSchema,
  RevisionSchema,
  SnapshotTimelineItemIdSchema,
  SnapshotTrackIdSchema,
  TimelineIdSchema,
  TimelineItemIdSchema,
  TrackIndexSchema,
  type MediaPoolItemId,
  type ProjectId,
  type RequestId,
  type Revision,
  type SnapshotTimelineItemId,
  type SnapshotTrackId,
  type TimelineId,
  type TimelineItemId,
  type TrackIndex,
  type WorkflowId,
} from "../value-types/identities.js";
import { createMarkers, immutableMarker, type MarkerRuntime, type Markers, type MarkerSnapshot } from "./markers.js";
import { createTimelineCaptionDomains, type CaptionRuntime, type TimelineCaptions, type TimelineTranscript } from "./captions.js";
import { createVoiceovers, type VoiceRuntime, type Voiceovers } from "./voice.js";
import { createTimelineItems, type TimelineItemRuntime, type TimelineItems } from "./timeline-items.js";
import {
  timelineRecordPosition,
  type BoundFrames,
  type FrameRate,
  type Frames,
  type HydratedDuration,
  type Seconds,
  type SourceRange,
  type Timecode,
  type TimelineRecordPosition,
  type TimelineRecordRange,
} from "../value-types/time.js";
import {
  hydrateDuration,
  hydrateFrameRate,
  hydrateSourceRange,
  hydrateTimecode,
  hydrateTimelineRecordPosition,
  hydrateTimelineRecordRange,
  lowerFrameRate,
  lowerTimelineRecordPosition,
  lowerDuration,
  lowerSourceRange,
  lowerTimelineRecordRange,
} from "../wire/time-adapter.js";
import { createMediaPool, type MediaPool } from "./media-pool.js";
import { createColor, type Color } from "./color.js";
import { createProjectRender, type ProjectRender } from "./render.js";
import { createTimelineEditor, type TimelineEditRuntime, type TimelineEditor } from "./timeline-editing.js";
import {
  createProjectMulticams,
  createTimelineMulticam,
  type MulticamRuntime,
  type Multicams,
  type TimelineMulticam,
} from "./multicam.js";
import { createFusionCompositions, type FusionCompositions, type FusionObjectRuntime } from "../fusion/runtime.js";
import { createFairlight, type Fairlight, type FairlightRuntime, type FairlightSnapshotReadback } from "./fairlight.js";
import {
  createProjectBoundMutations,
  createProjectCollectionMutations,
  contextObservation,
  type ProjectContextObservation,
  type ProjectBoundMutations,
  type ProjectCollectionMutations,
  type ProjectManagementRuntime,
} from "./project-management.js";
import { createManagedTimeline, type ManagedTimeline } from "./managed-timeline.js";
import type { WorkflowResult, Workflows } from "../core/workflows.js";

type WireSnapshot = Extract<CarrierReadSuccess, { operation: "timeline.snapshot" }>["data"];
type WireColorTarget = Extract<CarrierReadSuccess, { operation: "color.current" }>["data"];
type WireTrack = WireSnapshot["tracks"][number];
type WireClip = WireTrack["clips"][number];
const timelineSnapshotOrigins = new WeakMap<object, Readonly<{
  runtime: ObjectModelRuntime;
  generation: number;
  projectId: ProjectId;
  timelineId: TimelineId;
  fairlight: FairlightSnapshotReadback;
}>>();
const clipSnapshotOrigins = new WeakMap<object, Readonly<{
  runtime: ObjectModelRuntime;
  generation: number;
  timelineFacade: object;
  projectId: ProjectId;
  timelineId: TimelineId;
  trackType: "video" | "audio" | "subtitle";
  trackIndex: TrackIndex;
}>>();

/** Options for one bounded read-only live-state request. @beta */
export interface ReadControlOptions {
  /** Maximum time for this read request. */
  timeoutMs?: number;
  /** Abort only this local read request; it never implies a project mutation. */
  signal?: AbortSignal;
}

/** Supported DaVinci Resolve timeline track categories. @beta */
export type TimelineTrackType = "video" | "audio" | "subtitle";

/** Immutable clip data bound to one timeline snapshot revision. @beta */
export interface ClipSnapshot {
  /** Durable clip identity only when DaVinci Resolve proves an authoritative unique identifier, otherwise `null`. */
  readonly id: TimelineItemId | null;
  /** Snapshot-scoped identity for this exact clip observation. */
  readonly snapshotId: SnapshotTimelineItemId;
  /** Snapshot-scoped identity of the containing track coordinate. */
  readonly snapshotTrackId: SnapshotTrackId;
  /** Revision that owns this immutable clip reference. */
  readonly snapshotRevision: Revision;
  /** Display name reported by DaVinci Resolve. */
  readonly name: string;
  /** Half-open placement range in timeline record frames. */
  readonly recordRange: TimelineRecordRange;
  /** Clip duration expressed in an explicit duration domain. */
  readonly duration: HydratedDuration;
  /** Source-media range when the runtime can prove it, otherwise `null`. */
  readonly sourceRange: SourceRange | null;
  /** Available source bounds and exact fractional frame origin for speed-curve authoring. */
  readonly retimeSource: Readonly<{ availableRange: SourceRange; originFrame: number }> | null;
  /** Exact source-media frame rate when DaVinci Resolve exposes it, otherwise `null`. */
  readonly sourceFrameRate: FrameRate | null;
  /** Opaque source-media identity when available, otherwise `null`. */
  readonly mediaPoolItemId: MediaPoolItemId | null;
  /** Authoritative linked timeline-item identities, or `null` when DaVinci Resolve cannot prove link topology. */
  readonly linkedItemIds: readonly TimelineItemId[] | null;
}

/** Immutable one-based track data bound to one timeline snapshot revision. @beta */
export interface TrackSnapshot {
  /** Snapshot-scoped identity for this track coordinate; never persist it as a durable mutation target. */
  readonly snapshotId: SnapshotTrackId;
  /** Opaque identity of the containing timeline. */
  readonly timelineId: TimelineId;
  /** Revision that owns this immutable track reference. */
  readonly snapshotRevision: Revision;
  /** DaVinci Resolve track category. */
  readonly type: TimelineTrackType;
  /** One-based index matching DaVinci Resolve and CutAgent CLI. */
  readonly index: TrackIndex;
  /** Display name reported by DaVinci Resolve. */
  readonly name: string;
  /** Enabled state when DaVinci Resolve exposes it, otherwise `null`. */
  readonly enabled: boolean | null;
  /** Locked state when DaVinci Resolve exposes it, otherwise `null`. */
  readonly locked: boolean | null;
  /** Immutable clips observed on this track. */
  readonly clips: readonly ClipSnapshot[];
  /** Resolve exactly one clip covering a record-domain position. */
  clipAt(position: Frames | BoundFrames | Seconds | Timecode | TimelineRecordPosition): ClipSnapshot;
}

/** Immutable coherent read of the current timeline. @beta */
export interface TimelineSnapshot {
  /** Opaque identity of the containing project. */
  readonly projectId: ProjectId;
  /** Opaque identity of the observed timeline. */
  readonly timelineId: TimelineId;
  /** Content revision derived from the complete observable timeline state. */
  readonly revision: Revision;
  /** Exact rational frame-rate identity for timeline time values. */
  readonly frameRate: FrameRate;
  /** Timeline start in the timeline record domain. */
  readonly start: TimelineRecordPosition;
  /** All observed tracks in stable runtime order. */
  readonly tracks: readonly TrackSnapshot[];
  /** All timeline markers observed in this exact revision. */
  readonly markers: readonly MarkerSnapshot[];
  /** Video tracks from `tracks`, preserving one-based indexes. */
  readonly videoTracks: readonly TrackSnapshot[];
  /** Audio tracks from `tracks`, preserving one-based indexes. */
  readonly audioTracks: readonly TrackSnapshot[];
  /** Subtitle tracks from `tracks`, preserving one-based indexes. */
  readonly subtitleTracks: readonly TrackSnapshot[];
  /** Resolve the exact reciprocal linked items for a clip in this snapshot. */
  linkedItems(clip: ClipSnapshot): readonly ClipSnapshot[];
  /** Resolve one video track by its one-based DaVinci Resolve index. */
  videoTrack(index: number): TrackSnapshot;
  /** Resolve one audio track by its one-based DaVinci Resolve index. */
  audioTrack(index: number): TrackSnapshot;
  /** Resolve one subtitle track by its one-based DaVinci Resolve index. */
  subtitleTrack(index: number): TrackSnapshot;
}

/** Truthful availability of one live Color inspection field. @beta */
export type ColorReadCapability =
  | Readonly<{ status: "supported" }>
  | Readonly<{ status: "unavailable"; reason: "not_exposed_by_runtime" }>;

/** Explicit requirements that must be checked by the live runtime before a Color write. @beta */
export interface ColorMutationCapability {
  readonly status: "runtime_check_required";
  readonly edition: "studio_or_free" | "studio_required";
  readonly projectStorage: "disk_required" | "any";
  readonly plugin: "not_required" | "installed_effect_required";
}

/** One node in its exact one-based Color graph order for this revision. @beta */
export interface ColorNodeSnapshot {
  /** One-based node position. This is revision-scoped, not a durable node identity. */
  readonly index: number;
  /** Public node label, or `null` when the live runtime cannot read labels. */
  readonly label: string | null;
  /** Enabled state, or `null` when DaVinci Resolve exposes no authoritative readback. */
  readonly enabled: boolean | null;
  /** Sanitized applied-LUT metadata; local paths are never exposed. */
  readonly lut: Readonly<{ applied: boolean; displayName: string | null }>;
  /** Public effect/tool names reported for this node in stable runtime order. */
  readonly effects: readonly string[];
}

/** Exact containing video-track coordinate for a Color target observation. @beta */
export interface ColorTargetTrackSnapshot {
  /** Snapshot-scoped identity for this exact video-track coordinate. */
  readonly snapshotId: SnapshotTrackId;
  /** One-based video-track index matching DaVinci Resolve and CutAgent CLI. */
  readonly index: TrackIndex;
  /** Display name reported by DaVinci Resolve. */
  readonly name: string;
}

/** Exact active Color target clip; unlike generic timeline rows, durable identity is required. @beta */
export type ColorTargetClipSnapshot = Readonly<Omit<ClipSnapshot, "id"> & {
  readonly id: TimelineItemId;
}>;

/** Immutable readback of the exact current Color target and grade structure. @beta */
export interface ColorTargetSnapshot {
  /** Opaque identity of the containing project. */
  readonly projectId: ProjectId;
  /** Opaque identity of the containing timeline. */
  readonly timelineId: TimelineId;
  /** Color-state revision that owns the exact target, graph order, and every node index. */
  readonly revision: Revision;
  /** Timeline-content revision that owns the clip and track observation. */
  readonly timelineRevision: Revision;
  /** One-based DaVinci Resolve node-stack layer owning `nodeGraph` and every node index. */
  readonly nodeStackLayerIndex: number;
  /** Exact rational frame rate used to hydrate target clip ranges. */
  readonly frameRate: FrameRate;
  /** Exact containing video-track observation. */
  readonly track: ColorTargetTrackSnapshot;
  /** Exact active video clip observation bound to `timelineRevision`. */
  readonly clip: ColorTargetClipSnapshot;
  /** Live availability for every optional Color readback family. */
  readonly capabilities: Readonly<{
    nodeGraph: ColorReadCapability;
    labels: ColorReadCapability;
    enabledState: ColorReadCapability;
    luts: ColorReadCapability;
    effects: ColorReadCapability;
    versions: ColorReadCapability;
    colorGroup: ColorReadCapability;
  }>;
  /** Edition, storage, and plug-in requirements for mutation families; execution still fails closed if the live check does not pass. */
  readonly mutationCapabilities: Readonly<{
    primary: ColorMutationCapability;
    nodes: ColorMutationCapability;
    lutAssets: ColorMutationCapability;
    drxAssets: ColorMutationCapability;
    effects: ColorMutationCapability;
  }>;
  /** Ordered Color node graph. Node indexes are valid only for this revision. */
  readonly nodeGraph: Readonly<{
    nodeCount: number;
    nodes: readonly ColorNodeSnapshot[];
  }>;
  /** Local/remote grade-version names reported for this target. */
  readonly versions: Readonly<{
    current: string | null;
    local: readonly string[];
    remote: readonly string[];
  }>;
  /** Current Color group display name when authoritative readback is available. */
  readonly colorGroup: string | null;
}

/** Read-only Color inspection scoped to one exact live timeline reference. @beta */
/** Compatibility name for the high-level Color facade. @beta */
export type ColorInspector = Color;

/** Lightweight reference to one live DaVinci Resolve timeline. @beta */
export interface Timeline {
  /** Opaque timeline identity stable within this CutAgent installation/profile; the reference is client-generation scoped. */
  readonly id: TimelineId;
  /** Opaque identity of the containing project. */
  readonly projectId: ProjectId;
  /** Display name reported by DaVinci Resolve. */
  readonly name: string;
  /** Semantic marker inspection, impact previews, and durable mutation operations. */
  readonly markers: Markers;
  /** Exact snapshot-bound video-item move and reposition operations. */
  readonly items: TimelineItems;
  /** Read-only Color object model for this exact timeline reference. */
  readonly color: ColorInspector;
  /** Native subtitle and designed Text+ caption workflows bound to this exact timeline. */
  readonly captions: TimelineCaptions;
  /** Hosted durable transcript workflow bound to this exact timeline. */
  readonly transcript: TimelineTranscript;
  /** Semantic insert, overwrite, and trim authoring with mandatory impact previews. */
  readonly edit: TimelineEditor;
  /** Declaratively own and reconcile one whole timeline or bounded region. */
  readonly managed: ManagedTimeline;
  /** Generated-voice placement bound to this exact timeline. */
  readonly voiceovers: Voiceovers;
  /** Semantic native-multicam inspection, previews, and durable timeline mutations. */
  readonly multicam: TimelineMulticam;
  /** Exact Fusion compositions addressable on durable timeline items. */
  readonly fusion: FusionCompositions;
  /** Revision-safe Fairlight tracks, clips, buses, mix, processing, synchronization, loudness, and proof. */
  readonly fairlight: Fairlight;
  /** Independently inspect the exact native retime curve of a snapshot-bound clip. */
  readonly retime: {
    read(clip: ClipSnapshot, options?: ReadControlOptions): Promise<Readonly<{
      projectId: ProjectId;
      timelineId: TimelineId;
      timelineRevision: Revision;
      timelineItemId: TimelineItemId;
      durationFrames: number;
      speedMultiplier: number;
      reversed: boolean;
      frozen: boolean;
      points: readonly Readonly<{
        recordFrame: number;
        recordPositionFrames: number;
        sourceFrame: number;
        incomingControl: Readonly<{ recordPositionFrames: number; sourceFrame: number }>;
        outgoingControl: Readonly<{ recordPositionFrames: number; sourceFrame: number }>;
        speed: number;
        interpolation: "linear" | "bezier" | "hold";
      }>[];
    }>>;
  };
  /** Read one coherent immutable snapshot, failing if project or timeline identity drifts. */
  snapshot(options?: ReadControlOptions): Promise<TimelineSnapshot>;
}

/** Live timelines scoped to one explicit project reference. @beta */
export interface Timelines {
  /** Resolve the uniquely active timeline without falling back to a similarly named timeline. */
  current(options?: ReadControlOptions): Promise<Timeline>;
}

/** Lightweight reference to one live DaVinci Resolve project. @beta */
export interface Project {
  /** Opaque project identity stable within this CutAgent installation/profile; the reference is client-generation scoped. */
  readonly id: ProjectId;
  /** Display name reported by DaVinci Resolve. */
  readonly name: string;
  /** Read-only Media Pool hierarchy and asset inspection scoped to this exact project. */
  readonly mediaPool: MediaPool;
  /** Complete render discovery, settings, queue, status, export, and managed-artifact surface. */
  readonly render: ProjectRender;
  /** Timeline collection scoped to this exact project reference. */
  readonly timelines: Timelines;
  /** Semantic native-multicam inspection, previews, and durable project mutations. */
  readonly multicams: Multicams;
  /** Verified backup and other mutations bound to this exact current project observation. */
  readonly mutations: ProjectBoundMutations;
}

/** Live projects visible to one CutAgent client session. @beta */
export interface Projects extends ProjectCollectionMutations {
  /** Inspect the authoritative current project-library/project context and acquire its mutation revision. */
  context(options?: ReadControlOptions): Promise<ProjectContextObservation>;
  /** Resolve the currently open DaVinci Resolve project. */
  current(options?: ReadControlOptions): Promise<Project>;
}

interface ObjectModelRuntime extends MarkerRuntime, CaptionRuntime, TimelineEditRuntime, TimelineItemRuntime, VoiceRuntime, MulticamRuntime, FusionObjectRuntime, FairlightRuntime, ProjectManagementRuntime {
  readonly generation: number;
  readonly workflows: Workflows;
  readAtGeneration(
    generation: number,
    request: CarrierReadRequest,
    options?: ReadControlOptions,
  ): Promise<CarrierReadSuccess>;
  managedStartAtGeneration(generation: number, binding: unknown, cancellationRequested: boolean, options?: ReadControlOptions): Promise<{ workflowId: WorkflowId; status: string }>;
  managedWaitAtGeneration(generation: number, workflowId: WorkflowId, options?: ReadControlOptions): Promise<WorkflowResult>;
  managedInterruptAtGeneration(generation: number, workflowId: WorkflowId): Promise<void>;
}

function readFailure(code: "TARGET_NOT_FOUND" | "AMBIGUOUS_TARGET", message: string): CutAgentSdkError {
  return new CutAgentSdkError({
    kind: PUBLIC_ERROR_KIND_BY_CODE[code],
    code,
    message,
    retrySafe: code === "TARGET_NOT_FOUND",
    ...(code === "TARGET_NOT_FOUND" ? { retrySafetyProof: { basis: "read_only" } } : {}),
    possibleMutation: "none",
    usage: "not_reserved",
    recovery: ["inspect_state"],
    recoveryGuidance: [message],
    readbackRequired: false,
  });
}

function invalidResponse(message: string, requestId?: RequestId): CutAgentSdkError {
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
    ...(requestId ? { requestId } : {}),
  });
}

function deepFreeze<T>(value: T): T {
  if (value === null || typeof value !== "object" || Object.isFrozen(value)) return value;
  for (const nested of Object.values(value)) deepFreeze(nested);
  return Object.freeze(value);
}

function trackByIndex(tracks: readonly TrackSnapshot[], type: TimelineTrackType, index: number): TrackSnapshot {
  const validatedIndex = TrackIndexSchema.parse(index);
  const matches = tracks.filter((track) => track.type === type && track.index === validatedIndex);
  if (matches.length === 0) throw readFailure("TARGET_NOT_FOUND", `${type} track ${index} was not found in this snapshot.`);
  if (matches.length > 1) throw readFailure("AMBIGUOUS_TARGET", `${type} track ${index} is ambiguous in this snapshot.`);
  const match = matches[0];
  if (!match) throw invalidResponse("CutAgent could not resolve a validated track selection.");
  return match;
}

function immutableClip(raw: WireClip, rate: FrameRate): ClipSnapshot {
  const sourceFrameRate = raw.sourceFrameRate === null ? null : hydrateFrameRate(raw.sourceFrameRate);
  return deepFreeze({
    id: raw.id === null ? null : TimelineItemIdSchema.parse(raw.id),
    snapshotId: SnapshotTimelineItemIdSchema.parse(raw.snapshotId),
    snapshotTrackId: SnapshotTrackIdSchema.parse(raw.snapshotTrackId),
    snapshotRevision: RevisionSchema.parse(raw.snapshotRevision),
    name: raw.name,
    recordRange: hydrateTimelineRecordRange(raw.recordRange, { frameRate: rate }),
    duration: hydrateDuration(raw.duration, { frameRate: rate }) as HydratedDuration,
    sourceRange: raw.sourceRange === null ? null : hydrateSourceRange(raw.sourceRange, sourceFrameRate === null ? {} : { frameRate: sourceFrameRate }),
    retimeSource: raw.retimeSource == null ? null : {
      availableRange: hydrateSourceRange(raw.retimeSource.availableRange, sourceFrameRate === null ? {} : { frameRate: sourceFrameRate }),
      originFrame: raw.retimeSource.originFrame,
    },
    sourceFrameRate,
    mediaPoolItemId: raw.mediaPoolItemId === null ? null : MediaPoolItemIdSchema.parse(raw.mediaPoolItemId),
    linkedItemIds: raw.linkedItemIds === null
      ? null
      : raw.linkedItemIds.map((id) => TimelineItemIdSchema.parse(id)),
  });
}

function wirePositionFrame(value: ReturnType<typeof lowerTimelineRecordPosition>["value"]): number {
  return value.kind === "frames" ? value.value : hydrateTimecode(value).toFrames().value;
}

function immutableTrack(raw: WireTrack, rate: FrameRate): TrackSnapshot {
  const clips = deepFreeze(raw.clips.map((clip) => immutableClip(clip, rate)));
  const track: TrackSnapshot = {
    snapshotId: SnapshotTrackIdSchema.parse(raw.snapshotId),
    timelineId: TimelineIdSchema.parse(raw.timelineId),
    snapshotRevision: RevisionSchema.parse(raw.snapshotRevision),
    type: raw.type,
    index: TrackIndexSchema.parse(raw.index),
    name: raw.name,
    enabled: raw.enabled,
    locked: raw.locked,
    clips,
    clipAt(position): ClipSnapshot {
      const recordPosition = typeof position === "object" && position !== null && "domain" in position
        ? position as TimelineRecordPosition
        : timelineRecordPosition(position, rate);
      const wire = lowerTimelineRecordPosition(recordPosition, { frameRate: rate });
      const frame = wirePositionFrame(wire.value);
      const matches = clips.filter((clip) => {
        const range = clip.recordRange;
        const start = lowerTimelineRecordPosition(range.start, { frameRate: rate }).value;
        const end = lowerTimelineRecordPosition(range.endExclusive, { frameRate: rate }).value;
        const startFrame = wirePositionFrame(start);
        const endFrame = wirePositionFrame(end);
        return startFrame <= frame && frame < endFrame;
      });
      const match = matches[0];
      if (!match) throw readFailure("TARGET_NOT_FOUND", `No ${raw.type} clip covers record frame ${frame} on track ${raw.index}.`);
      if (matches.length > 1) throw readFailure("AMBIGUOUS_TARGET", `More than one ${raw.type} clip covers record frame ${frame} on track ${raw.index}.`);
      return match;
    },
  };
  Object.setPrototypeOf(track, null);
  return deepFreeze(track);
}

function immutableSnapshot(raw: WireSnapshot): TimelineSnapshot {
  const rate = hydrateFrameRate(raw.frameRate);
  const tracks = deepFreeze(raw.tracks.map((track) => immutableTrack(track, rate)));
  const videoTracks = deepFreeze(tracks.filter((track) => track.type === "video"));
  const audioTracks = deepFreeze(tracks.filter((track) => track.type === "audio"));
  const subtitleTracks = deepFreeze(tracks.filter((track) => track.type === "subtitle"));
  const clips = tracks.flatMap((track) => track.clips);
  const markers = deepFreeze(raw.markers.map((marker) => immutableMarker({
    id: marker.id,
    snapshotRevision: marker.snapshotRevision,
    recordFrame: marker.position.value.value,
    color: marker.color,
    name: marker.name,
    note: marker.note,
    durationFrames: marker.duration.value.value,
  }, rate)));
  const snapshot: TimelineSnapshot = {
    projectId: ProjectIdSchema.parse(raw.project.id),
    timelineId: TimelineIdSchema.parse(raw.timeline.id),
    revision: RevisionSchema.parse(raw.revision),
    frameRate: rate,
    start: hydrateTimelineRecordPosition(raw.start, { frameRate: rate }),
    tracks,
    markers,
    videoTracks,
    audioTracks,
    subtitleTracks,
    linkedItems(clip) {
      const member = clips.find((candidate) => candidate.snapshotId === clip?.snapshotId);
      if (!member || String(member.snapshotRevision) !== raw.revision) {
        throw new TypeError("Linked-item lookup requires a clip from this exact snapshot.");
      }
      if (member.linkedItemIds === null) {
        throw invalidResponse("DaVinci Resolve did not expose authoritative link topology for this clip.");
      }
      return deepFreeze(member.linkedItemIds.map((linkedId) => {
        const matches = clips.filter((candidate) => candidate.id === linkedId);
        if (matches.length !== 1 || !matches[0]) {
          throw readFailure(matches.length === 0 ? "TARGET_NOT_FOUND" : "AMBIGUOUS_TARGET", "A linked timeline item could not be resolved uniquely in this snapshot.");
        }
        if (matches[0].linkedItemIds === null || member.id === null || !matches[0].linkedItemIds.includes(member.id)) {
          throw invalidResponse("DaVinci Resolve did not expose reciprocal link topology for this clip relationship.");
        }
        return matches[0];
      }));
    },
    videoTrack(index) { return trackByIndex(tracks, "video", index); },
    audioTrack(index) { return trackByIndex(tracks, "audio", index); },
    subtitleTrack(index) { return trackByIndex(tracks, "subtitle", index); },
  };
  Object.setPrototypeOf(snapshot, null);
  return deepFreeze(snapshot);
}

function immutableColorTarget(raw: WireColorTarget): ColorTargetSnapshot {
  const rate = hydrateFrameRate(raw.frameRate);
  const clip = immutableClip(raw.clip, rate);
  return deepFreeze({
    projectId: ProjectIdSchema.parse(raw.project.id),
    timelineId: TimelineIdSchema.parse(raw.timeline.id),
    revision: RevisionSchema.parse(raw.revision),
    timelineRevision: RevisionSchema.parse(raw.timelineRevision),
    nodeStackLayerIndex: raw.nodeStackLayerIndex,
    frameRate: rate,
    track: {
      snapshotId: SnapshotTrackIdSchema.parse(raw.track.snapshotId),
      index: TrackIndexSchema.parse(raw.track.index),
      name: raw.track.name,
    },
    clip: {
      ...clip,
      id: TimelineItemIdSchema.parse(raw.clip.id),
    },
    capabilities: raw.capabilities,
    mutationCapabilities: raw.mutationCapabilities,
    nodeGraph: raw.nodeGraph,
    versions: raw.versions,
    colorGroup: raw.colorGroup,
  });
}

function createTimeline(runtime: ObjectModelRuntime, generation: number, raw: { id: string; projectId: string; name: string }): Timeline {
  const wireId = sdkTimelineIdSchema.parse(raw.id);
  const wireProjectId = sdkProjectIdSchema.parse(raw.projectId);
  const id = TimelineIdSchema.parse(wireId);
  const projectId = ProjectIdSchema.parse(wireProjectId);
  const timelineFacade = Object.freeze(Object.create(null) as object);
  const readSnapshot = async (options: ConnectionControlOptions = {}) => {
    const response = await runtime.readAtGeneration(generation, { operation: "timeline.snapshot", projectId: wireProjectId, timelineId: wireId }, options);
    if (response.operation !== "timeline.snapshot") throw invalidResponse("CutAgent runtime returned the wrong semantic read result.", RequestIdSchema.parse(response.requestId));
    const snapshot = immutableSnapshot(response.data);
    timelineSnapshotOrigins.set(snapshot, { runtime, generation, projectId, timelineId: id, fairlight: response.data.fairlight });
    for (const track of snapshot.tracks) {
      for (const clip of track.clips) {
        clipSnapshotOrigins.set(clip, { runtime, generation, timelineFacade, projectId, timelineId: id, trackType: track.type, trackIndex: track.index });
      }
    }
    return snapshot;
  };
  const captionDomains = createTimelineCaptionDomains(runtime, generation, projectId, id);
  const edit = createTimelineEditor(runtime, generation, projectId, id);
  const timeline: Timeline = {
    id,
    projectId,
    name: raw.name,
    markers: createMarkers(runtime, generation, readSnapshot),
    edit,
    managed: createManagedTimeline(runtime, projectId, id),
    items: createTimelineItems(runtime, generation, readSnapshot),
    color: createColor(runtime, generation, async (nodeStackLayerIndex, options = {}) => {
        const response = await runtime.readAtGeneration(generation, { operation: "color.current", projectId: wireProjectId, timelineId: wireId, nodeStackLayerIndex }, options);
        if (response.operation !== "color.current") throw invalidResponse("CutAgent runtime returned the wrong semantic Color read result.", RequestIdSchema.parse(response.requestId));
        if (response.data.project.id !== wireProjectId || response.data.timeline.id !== wireId) {
          throw invalidResponse("CutAgent runtime returned a Color target for another project or timeline.", RequestIdSchema.parse(response.requestId));
        }
        if (response.data.nodeStackLayerIndex !== nodeStackLayerIndex) {
          throw invalidResponse("CutAgent runtime returned a Color target for another node-stack layer.", RequestIdSchema.parse(response.requestId));
        }
        return immutableColorTarget(response.data);
      }),
    captions: captionDomains.captions,
    transcript: captionDomains.transcript,
    voiceovers: createVoiceovers(runtime, generation, readSnapshot),
    multicam: createTimelineMulticam(runtime, generation, readSnapshot),
    fusion: createFusionCompositions(runtime, generation, projectId, id),
    retime: Object.freeze({
      async read(clip: ClipSnapshot, options: ReadControlOptions = {}) {
        const origin = clipSnapshotOrigins.get(clip);
        if (!origin || origin.runtime !== runtime || origin.generation !== generation
          || origin.timelineFacade !== timelineFacade
          || origin.projectId !== projectId || origin.timelineId !== id) {
          throw new TypeError("Retime inspection requires a clip from this exact Timeline snapshot.");
        }
        if (clip.id === null || (clip.sourceRange === null && clip.retimeSource === null)
          || clip.mediaPoolItemId === null || clip.linkedItemIds === null
          || origin.trackType === "subtitle") {
          throw invalidResponse("Retime inspection requires durable clip, source-media, and linked-topology identity.");
        }
        const wireRecordRange = lowerTimelineRecordRange(clip.recordRange);
        const wireDuration = lowerDuration(clip.duration);
        const wireSourceRange = lowerSourceRange(clip.sourceRange ?? clip.retimeSource!.availableRange);
        if (wireRecordRange.unit !== "frames" || wireDuration.value.kind !== "frames" || wireSourceRange.unit !== "frames") {
          throw invalidResponse("Retime inspection requires exact frame-domain clip ranges.");
        }
        const wireTimelineItemId = sdkTimelineItemIdSchema.parse(clip.id);
        const wireSnapshotId = sdkSnapshotTimelineItemIdSchema.parse(clip.snapshotId);
        const wireSnapshotTrackId = sdkSnapshotTrackIdSchema.parse(clip.snapshotTrackId);
        const wireSnapshotRevision = sdkRevisionSchema.parse(clip.snapshotRevision);
        const wireMediaPoolItemId = sdkMediaPoolItemIdSchema.parse(clip.mediaPoolItemId);
        const wireLinkedItemIds = clip.linkedItemIds.map((itemId) => sdkTimelineItemIdSchema.parse(itemId));
        const response = await runtime.readAtGeneration(generation, {
          operation: "timeline.retime",
          projectId: wireProjectId,
          timelineId: wireId,
          timelineRevision: wireSnapshotRevision,
          target: {
            id: wireTimelineItemId,
            snapshotId: wireSnapshotId,
            snapshotTrackId: wireSnapshotTrackId,
            snapshotRevision: wireSnapshotRevision,
            trackType: origin.trackType,
            trackIndex: origin.trackIndex,
            name: clip.name,
            recordRange: wireRecordRange,
            duration: {
              domain: "duration",
              value: { kind: "frames", value: wireDuration.value.value },
            },
            sourceRange: wireSourceRange,
            sourceFrameRate: clip.sourceFrameRate === null ? null : lowerFrameRate(clip.sourceFrameRate),
            mediaPoolItemId: wireMediaPoolItemId,
            linkedItemIds: wireLinkedItemIds,
          },
        }, options);
        if (response.operation !== "timeline.retime" || response.data.projectId !== wireProjectId
          || response.data.timelineId !== wireId || String(response.data.timelineItemId) !== String(clip.id)
          || String(response.data.timelineRevision) !== String(clip.snapshotRevision)) {
          throw invalidResponse("CutAgent runtime returned retime state for another target.", RequestIdSchema.parse(response.requestId));
        }
        return deepFreeze({
          projectId: ProjectIdSchema.parse(response.data.projectId),
          timelineId: TimelineIdSchema.parse(response.data.timelineId),
          timelineRevision: RevisionSchema.parse(response.data.timelineRevision),
          timelineItemId: TimelineItemIdSchema.parse(response.data.timelineItemId),
          durationFrames: response.data.durationFrames,
          speedMultiplier: response.data.speedMultiplier,
          reversed: response.data.reversed,
          frozen: response.data.frozen,
          points: response.data.points.map((point) => ({
            recordFrame: point.recordFrame,
            recordPositionFrames: point.recordPositionFrames,
            sourceFrame: point.sourceFrame,
            incomingControl: { ...point.incomingControl },
            outgoingControl: { ...point.outgoingControl },
            speed: point.speed,
            interpolation: point.interpolation,
          })),
        });
      },
    }),
    fairlight: createFairlight(runtime, generation, projectId, id, (snapshot) => {
      const origin = timelineSnapshotOrigins.get(snapshot);
      return origin?.runtime === runtime && origin.generation === generation && origin.projectId === projectId && origin.timelineId === id;
    }, (snapshot) => {
      const origin = timelineSnapshotOrigins.get(snapshot);
      return origin?.runtime === runtime && origin.generation === generation && origin.projectId === projectId && origin.timelineId === id
        ? origin.fairlight
        : null;
    }),
    snapshot: readSnapshot,
  };
  Object.setPrototypeOf(timeline, null);
  return Object.freeze(timeline);
}

function createProject(runtime: ObjectModelRuntime, generation: number, raw: { id: string; name: string }): Project {
  const wireId = sdkProjectIdSchema.parse(raw.id);
  const id = ProjectIdSchema.parse(wireId);
  const timelines: Timelines = Object.freeze({
    async current(options = {}) {
      const response = await runtime.readAtGeneration(generation, { operation: "timeline.current", projectId: wireId }, options);
      if (response.operation !== "timeline.current") throw invalidResponse("CutAgent runtime returned the wrong semantic read result.", RequestIdSchema.parse(response.requestId));
      return createTimeline(runtime, generation, response.data);
    },
  });
  const project: Project = {
    id,
    name: raw.name,
    mediaPool: createMediaPool(runtime, generation, wireId),
    render: createProjectRender(runtime, generation, wireId),
    timelines,
    multicams: createProjectMulticams(runtime, generation, id),
    mutations: createProjectBoundMutations(runtime, generation, { id, name: raw.name }, async (options = {}) => {
      const response = await runtime.readAtGeneration(generation, { operation: "project.context" }, options);
      if (response.operation !== "project.context") throw invalidResponse("CutAgent runtime returned the wrong project-context result before mutation.", RequestIdSchema.parse(response.requestId));
      return contextObservation(response.data);
    }),
  };
  Object.setPrototypeOf(project, null);
  return Object.freeze(project);
}

/** Create the live project collection bound to one client generation. @internal */
export function createProjects(runtime: ObjectModelRuntime): Projects {
  const mutations = createProjectCollectionMutations(runtime, () => runtime.generation);
  const projects: Projects = {
    ...mutations,
    async context(options = {}) {
      const generation = runtime.generation;
      const response = await runtime.readAtGeneration(generation, { operation: "project.context" }, options);
      if (response.operation !== "project.context") throw invalidResponse("CutAgent runtime returned the wrong semantic read result.", RequestIdSchema.parse(response.requestId));
      return contextObservation(response.data);
    },
    async current(options = {}) {
      const generation = runtime.generation;
      const response = await runtime.readAtGeneration(generation, { operation: "project.current" }, options);
      if (response.operation !== "project.current") throw invalidResponse("CutAgent runtime returned the wrong semantic read result.", RequestIdSchema.parse(response.requestId));
      return createProject(runtime, generation, response.data);
    },
  };
  Object.setPrototypeOf(projects, null);
  return Object.freeze(projects);
}
