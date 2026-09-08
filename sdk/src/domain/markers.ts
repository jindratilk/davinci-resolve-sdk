import { z } from "zod";
import {
  sdkMarkerCreateInputSchema,
  sdkMarkerDeleteInputSchema,
  sdkMarkerMutationResultSchema,
  sdkMarkerUpdateInputSchema,
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
  MarkerIdSchema,
  RevisionSchema,
  type IdempotencyKey,
  type MarkerId,
  type ProjectId,
  type Revision,
  type TimelineId,
} from "../value-types/identities.js";
import {
  frames,
  timelineRecordPosition,
  type BoundFrameDuration,
  type FrameDuration,
  type FrameRate,
  type TimelineRecordPosition,
} from "../value-types/time.js";
import { hydrateDuration, hydrateTimecode, hydrateTimelineRecordPosition, lowerDuration, lowerTimelineRecordPosition } from "../wire/time-adapter.js";

/** Public action discriminators owned by the semantic marker collection. @beta */
export type MarkerActionId =
  | "cutagent.action.timeline.marker.add"
  | "cutagent.action.timeline.marker.update"
  | "cutagent.action.timeline.marker.delete";

/** Immutable marker data bound to one timeline snapshot revision. @beta */
export interface MarkerSnapshot {
  readonly id: MarkerId;
  readonly snapshotRevision: Revision;
  readonly position: TimelineRecordPosition;
  readonly color: string;
  readonly name: string;
  readonly note: string;
  readonly duration: BoundFrameDuration;
}

/** Semantic marker values accepted by create and update previews. @beta */
export interface MarkerValues {
  readonly position: TimelineRecordPosition;
  readonly color?: string;
  readonly name?: string;
  readonly note?: string;
  readonly duration?: FrameDuration | BoundFrameDuration;
}

/** Fully resolved marker values shown by an impact preview. @beta */
export interface MarkerPreviewValues {
  readonly position: TimelineRecordPosition;
  readonly color: string;
  readonly name: string;
  readonly note: string;
  readonly duration: BoundFrameDuration;
}

/** Typed, inspectable impact preview required before a marker mutation. @beta */
export interface MarkerImpactPreview {
  readonly action: "create" | "update" | "delete";
  readonly projectId: ProjectId;
  readonly timelineId: TimelineId;
  readonly timelineRevision: Revision;
  readonly targetMarkerId: MarkerId | null;
  readonly proposedMarker: MarkerPreviewValues | null;
  readonly summary: string;
}

/** Verified semantic result for a marker mutation. @beta */
export interface MarkerMutationResult {
  readonly action: "create" | "update" | "delete";
  readonly marker: MarkerSnapshot | null;
  readonly previousMarker: MarkerSnapshot | null;
  readonly timelineRevision: Revision;
}

/** Required control values for replay-safe marker writes. @beta */
export interface MarkerMutationOptions extends ConnectionControlOptions {
  readonly idempotencyKey: IdempotencyKey;
}

type WireMarker = {
  id: string;
  recordFrame: number;
  color: string;
  name: string;
  note: string;
  durationFrames: number;
};
type PreviewInternal = {
  public: MarkerImpactPreview;
  marker: Omit<WireMarker, "id"> | null;
  target: MarkerSnapshot | null;
  frameRate: FrameRate;
  collection: object;
};
const previewInternals = new WeakMap<object, PreviewInternal>();

export interface MarkerRuntime {
  sessionAtGeneration(generation: number): EstablishedCarrierSession;
  createOperationAtGeneration(
    generation: number,
    request: Parameters<EstablishedCarrierSession["operation"]>[0],
    options?: ConnectionControlOptions,
  ): Promise<SdkOperationEvent>;
}

/** Semantic inspection, preview, and durable mutation API for timeline markers. @beta */
export interface Markers {
  list(options?: ConnectionControlOptions): Promise<readonly MarkerSnapshot[]>;
  previewCreate(values: MarkerValues): Promise<MarkerImpactPreview>;
  previewUpdate(marker: MarkerSnapshot, values: Partial<MarkerValues>): Promise<MarkerImpactPreview>;
  previewDelete(marker: MarkerSnapshot): Promise<MarkerImpactPreview>;
  create(preview: MarkerImpactPreview, options: MarkerMutationOptions): Promise<OperationHandle<MarkerMutationResult, "cutagent.action.timeline.marker.add">>;
  update(preview: MarkerImpactPreview, options: MarkerMutationOptions): Promise<OperationHandle<MarkerMutationResult, "cutagent.action.timeline.marker.update">>;
  delete(preview: MarkerImpactPreview, options: MarkerMutationOptions): Promise<OperationHandle<MarkerMutationResult, "cutagent.action.timeline.marker.delete">>;
}

export interface MarkerSnapshotOwner {
  readonly projectId: ProjectId;
  readonly timelineId: TimelineId;
  readonly revision: Revision;
  readonly frameRate: FrameRate;
  readonly start: TimelineRecordPosition;
  readonly markers: readonly MarkerSnapshot[];
}

function freeze<T extends object>(value: T): Readonly<T> {
  Object.setPrototypeOf(value, null);
  return Object.freeze(value);
}

export function immutableMarker(raw: WireMarker & { snapshotRevision: string }, rate: FrameRate): MarkerSnapshot {
  return freeze({
    id: MarkerIdSchema.parse(raw.id),
    snapshotRevision: RevisionSchema.parse(raw.snapshotRevision),
    position: hydrateTimelineRecordPosition({ domain: "timeline_record", value: { kind: "frames", value: raw.recordFrame } }, { frameRate: rate }),
    color: raw.color,
    name: raw.name,
    note: raw.note,
    duration: hydrateDuration({ domain: "duration", value: { kind: "frames", value: raw.durationFrames } }, { frameRate: rate }) as BoundFrameDuration,
  });
}

function recordFrame(position: TimelineRecordPosition, rate: FrameRate): number {
  const lowered = lowerTimelineRecordPosition(position, { frameRate: rate });
  return lowered.value.kind === "frames" ? lowered.value.value : hydrateTimecode(lowered.value).toFrames().value;
}

function markerWire(values: MarkerValues, rate: FrameRate, base?: MarkerSnapshot): Omit<WireMarker, "id"> {
  const duration = values.duration ?? base?.duration ?? hydrateDuration({ domain: "duration", value: { kind: "frames", value: 1 } }, { frameRate: rate }) as BoundFrameDuration;
  const loweredDuration = lowerDuration(duration, { frameRate: rate });
  if (loweredDuration.value.kind !== "frames" || loweredDuration.value.value < 1) throw new TypeError("Marker duration must be at least one frame.");
  return {
    recordFrame: recordFrame(values.position ?? base?.position ?? timelineRecordPosition(frames(0), rate), rate),
    color: values.color ?? base?.color ?? "Blue",
    name: values.name ?? base?.name ?? "",
    note: values.note ?? base?.note ?? "",
    durationFrames: loweredDuration.value.value,
  };
}

function preview(owner: MarkerSnapshotOwner, action: MarkerImpactPreview["action"], marker: Omit<WireMarker, "id"> | null, target: MarkerSnapshot | null, collection: object): MarkerImpactPreview {
  if (target && target.snapshotRevision !== owner.revision) throw new TypeError("Marker reference belongs to a different timeline revision.");
  const proposedMarker = marker === null ? null : freeze({
    position: hydrateTimelineRecordPosition({ domain: "timeline_record", value: { kind: "frames", value: marker.recordFrame } }, { frameRate: owner.frameRate }),
    color: marker.color,
    name: marker.name,
    note: marker.note,
    duration: hydrateDuration({ domain: "duration", value: { kind: "frames", value: marker.durationFrames } }, { frameRate: owner.frameRate }) as BoundFrameDuration,
  });
  const value = freeze({
    action,
    projectId: owner.projectId,
    timelineId: owner.timelineId,
    timelineRevision: owner.revision,
    targetMarkerId: target?.id ?? null,
    proposedMarker,
    summary: action === "create" ? `Create one marker at record frame ${marker?.recordFrame}.` : action === "update" ? `Replace marker ${target?.id}.` : `Delete marker ${target?.id}.`,
  });
  previewInternals.set(value, { public: value, marker, target, frameRate: owner.frameRate, collection });
  return value;
}

function hydrateResult(value: unknown, rate: FrameRate): MarkerMutationResult {
  const parsed = sdkMarkerMutationResultSchema.parse(value);
  const convert = (marker: typeof parsed.marker) => marker === null ? null : immutableMarker({ ...marker, snapshotRevision: parsed.timelineRevision }, rate);
  return freeze({
    action: parsed.action,
    marker: convert(parsed.marker),
    previousMarker: convert(parsed.previousMarker),
    timelineRevision: RevisionSchema.parse(parsed.timelineRevision),
  });
}

/** Construct the semantic marker collection for one exact timeline generation. @internal */
export function createMarkers(
  runtime: MarkerRuntime,
  generation: number,
  readSnapshot: (options?: ConnectionControlOptions) => Promise<MarkerSnapshotOwner>,
): Markers {
  const collection = Object.freeze({});
  const makePreview = async (action: MarkerImpactPreview["action"], values?: MarkerValues, target?: MarkerSnapshot) => {
    const owner = await readSnapshot();
    const exactTarget = target ? owner.markers.find((item) => item.id === target.id) : undefined;
    if (target && (!exactTarget || exactTarget.snapshotRevision !== target.snapshotRevision)) throw new TypeError("Marker reference is stale or no longer present.");
    const wire = action === "delete" ? null : markerWire(values ?? { position: target!.position }, owner.frameRate, exactTarget);
    if (wire && wire.recordFrame < recordFrame(owner.start, owner.frameRate)) throw new TypeError("Marker position cannot precede the timeline start.");
    if (action === "update" && exactTarget && wire
      && wire.recordFrame === recordFrame(exactTarget.position, owner.frameRate)
      && wire.color === exactTarget.color && wire.name === exactTarget.name
      && wire.note === exactTarget.note && wire.durationFrames === exactTarget.duration.value.value) {
      throw new TypeError("Marker update must change at least one semantic value.");
    }
    return preview(owner, action, wire, exactTarget ?? null, collection);
  };
  const start = async (expected: MarkerImpactPreview["action"], impact: MarkerImpactPreview, options: MarkerMutationOptions) => {
    const internal = previewInternals.get(impact);
    if (!internal || internal.public !== impact || internal.collection !== collection || impact.action !== expected) throw new TypeError("Marker mutation requires its matching CutAgent impact preview.");
    const base = { projectId: String(impact.projectId), timelineId: String(impact.timelineId), timelineRevision: String(impact.timelineRevision) };
    IdempotencyKeySchema.parse(options.idempotencyKey);
    const replayKey = sdkIdempotencyKeySchema.parse(options.idempotencyKey);
    const request: CarrierOperationRequest = expected === "create"
      ? { operation: "operation.create", actionId: "cutagent.action.timeline.marker.add", input: sdkMarkerCreateInputSchema.parse({ ...base, marker: internal.marker! }), idempotencyKey: replayKey }
      : expected === "update"
        ? { operation: "operation.create", actionId: "cutagent.action.timeline.marker.update", input: sdkMarkerUpdateInputSchema.parse({ ...base, markerId: String(internal.target!.id), marker: internal.marker! }), idempotencyKey: replayKey }
        : { operation: "operation.create", actionId: "cutagent.action.timeline.marker.delete", input: sdkMarkerDeleteInputSchema.parse({ ...base, markerId: String(internal.target!.id) }), idempotencyKey: replayKey };
    const event = await runtime.createOperationAtGeneration(generation, request, options);
    return { event, frameRate: internal.frameRate };
  };
  const resultSchema = (rate: FrameRate) => z.object({}).passthrough().transform((result) => hydrateResult(result, rate));
  return freeze({
    async list(options = {}) { return (await readSnapshot(options)).markers; },
    previewCreate(values) { return makePreview("create", values); },
    previewUpdate(marker, values) { return makePreview("update", { ...values, position: values.position ?? marker.position }, marker); },
    previewDelete(marker) { return makePreview("delete", undefined, marker); },
    async create(impact, options) {
      const started = await start("create", impact, options);
      return createTypedOperationHandle({ session: () => runtime.sessionAtGeneration(generation) }, started.event, "cutagent.action.timeline.marker.add", resultSchema(started.frameRate));
    },
    async update(impact, options) {
      const started = await start("update", impact, options);
      return createTypedOperationHandle({ session: () => runtime.sessionAtGeneration(generation) }, started.event, "cutagent.action.timeline.marker.update", resultSchema(started.frameRate));
    },
    async delete(impact, options) {
      const started = await start("delete", impact, options);
      return createTypedOperationHandle({ session: () => runtime.sessionAtGeneration(generation) }, started.event, "cutagent.action.timeline.marker.delete", resultSchema(started.frameRate));
    },
  });
}
