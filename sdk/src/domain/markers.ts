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

/** Verified semantic result for one plural marker mutation. @beta */
export interface MarkerMutationBatchResult {
  readonly action: "create" | "update" | "delete";
  readonly markers: readonly MarkerSnapshot[];
  readonly previousMarkers: readonly MarkerSnapshot[];
  readonly timelineRevision: Revision;
}

/** One marker and its per-item replacement values for a plural update preview. @beta */
export interface MarkerUpdate {
  readonly marker: MarkerSnapshot;
  readonly values: Partial<MarkerValues>;
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
  session(): EstablishedCarrierSession;
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
  previewCreate(values: readonly MarkerValues[]): Promise<readonly MarkerImpactPreview[]>;
  previewUpdate(marker: MarkerSnapshot, values: Partial<MarkerValues>): Promise<MarkerImpactPreview>;
  previewUpdate(updates: readonly MarkerUpdate[]): Promise<readonly MarkerImpactPreview[]>;
  previewDelete(marker: MarkerSnapshot): Promise<MarkerImpactPreview>;
  previewDelete(markers: readonly MarkerSnapshot[]): Promise<readonly MarkerImpactPreview[]>;
  create(preview: MarkerImpactPreview, options: MarkerMutationOptions): Promise<OperationHandle<MarkerMutationResult, "cutagent.action.timeline.marker.add">>;
  create(previews: readonly MarkerImpactPreview[], options: MarkerMutationOptions): Promise<OperationHandle<MarkerMutationBatchResult, "cutagent.action.timeline.marker.add">>;
  update(preview: MarkerImpactPreview, options: MarkerMutationOptions): Promise<OperationHandle<MarkerMutationResult, "cutagent.action.timeline.marker.update">>;
  update(previews: readonly MarkerImpactPreview[], options: MarkerMutationOptions): Promise<OperationHandle<MarkerMutationBatchResult, "cutagent.action.timeline.marker.update">>;
  delete(preview: MarkerImpactPreview, options: MarkerMutationOptions): Promise<OperationHandle<MarkerMutationResult, "cutagent.action.timeline.marker.delete">>;
  delete(previews: readonly MarkerImpactPreview[], options: MarkerMutationOptions): Promise<OperationHandle<MarkerMutationBatchResult, "cutagent.action.timeline.marker.delete">>;
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

function hydrateResult(value: unknown, rate: FrameRate): MarkerMutationResult | MarkerMutationBatchResult {
  const parsed = sdkMarkerMutationResultSchema.parse(value);
  const convert = (marker: WireMarker | null) => marker === null ? null : immutableMarker({ ...marker, snapshotRevision: parsed.timelineRevision }, rate);
  if ("markers" in parsed) {
    return freeze({
      action: parsed.action,
      markers: Object.freeze(parsed.markers.map((marker) => convert(marker)!)),
      previousMarkers: Object.freeze(parsed.previousMarkers.map((marker) => convert(marker)!)),
      timelineRevision: RevisionSchema.parse(parsed.timelineRevision),
    });
  }
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
  const makePreviewAt = (owner: MarkerSnapshotOwner, action: MarkerImpactPreview["action"], values?: MarkerValues, target?: MarkerSnapshot) => {
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
  const makePreview = async (action: MarkerImpactPreview["action"], values?: MarkerValues, target?: MarkerSnapshot) => (
    makePreviewAt(await readSnapshot(), action, values, target)
  );
  const makePreviews = async (action: MarkerImpactPreview["action"], entries: readonly { values?: MarkerValues; target?: MarkerSnapshot }[]) => {
    if (entries.length === 0) throw new TypeError("A plural marker preview requires at least one item.");
    if (entries.length > 10_000) throw new TypeError("A plural marker preview accepts at most 10000 items.");
    const owner = await readSnapshot();
    return Object.freeze(entries.map(({ values, target }) => makePreviewAt(owner, action, values, target)));
  };
  const start = async (expected: MarkerImpactPreview["action"], impactOrImpacts: MarkerImpactPreview | readonly MarkerImpactPreview[], options: MarkerMutationOptions) => {
    const isBatch = Array.isArray(impactOrImpacts);
    const impacts = (isBatch ? impactOrImpacts : [impactOrImpacts]) as readonly MarkerImpactPreview[];
    if (impacts.length === 0) throw new TypeError("A plural marker mutation requires at least one impact preview.");
    const internals = impacts.map((impact) => {
      const internal = previewInternals.get(impact);
      if (!internal || internal.public !== impact || internal.collection !== collection || impact.action !== expected) {
        throw new TypeError("Marker mutation requires matching CutAgent impact previews from one timeline collection.");
      }
      return internal;
    });
    const first = impacts[0]!;
    if (impacts.some((impact) => impact.projectId !== first.projectId || impact.timelineId !== first.timelineId || impact.timelineRevision !== first.timelineRevision)) {
      throw new TypeError("Plural marker mutation previews must belong to one timeline revision.");
    }
    const base = { projectId: String(first.projectId), timelineId: String(first.timelineId), timelineRevision: String(first.timelineRevision) };
    IdempotencyKeySchema.parse(options.idempotencyKey);
    const replayKey = sdkIdempotencyKeySchema.parse(options.idempotencyKey);
    const request: CarrierOperationRequest = expected === "create"
      ? { operation: "operation.create", actionId: "cutagent.action.timeline.marker.add", input: sdkMarkerCreateInputSchema.parse(isBatch
        ? { ...base, markers: internals.map((internal) => internal.marker!) }
        : { ...base, marker: internals[0]!.marker! }), idempotencyKey: replayKey }
      : expected === "update"
        ? { operation: "operation.create", actionId: "cutagent.action.timeline.marker.update", input: sdkMarkerUpdateInputSchema.parse(isBatch
          ? { ...base, updates: internals.map((internal) => ({ markerId: String(internal.target!.id), marker: internal.marker! })) }
          : { ...base, markerId: String(internals[0]!.target!.id), marker: internals[0]!.marker! }), idempotencyKey: replayKey }
        : { operation: "operation.create", actionId: "cutagent.action.timeline.marker.delete", input: sdkMarkerDeleteInputSchema.parse(isBatch
          ? { ...base, markerIds: internals.map((internal) => String(internal.target!.id)) }
          : { ...base, markerId: String(internals[0]!.target!.id) }), idempotencyKey: replayKey };
    const event = await runtime.createOperationAtGeneration(generation, request, options);
    return { event, frameRate: internals[0]!.frameRate };
  };
  const resultSchema = (rate: FrameRate) => z.object({}).passthrough().transform((result) => hydrateResult(result, rate));
  return freeze({
    async list(options = {}) { return (await readSnapshot(options)).markers; },
    previewCreate: (async (values: MarkerValues | readonly MarkerValues[]) => Array.isArray(values)
      ? makePreviews("create", values.map((item) => ({ values: item })))
      : makePreview("create", values as MarkerValues)) as Markers["previewCreate"],
    previewUpdate: (async (markerOrUpdates: MarkerSnapshot | readonly MarkerUpdate[], values?: Partial<MarkerValues>) => Array.isArray(markerOrUpdates)
      ? makePreviews("update", markerOrUpdates.map((entry) => ({ target: entry.marker, values: { ...entry.values, position: entry.values.position ?? entry.marker.position } })))
      : makePreview("update", { ...values, position: values?.position ?? (markerOrUpdates as MarkerSnapshot).position }, markerOrUpdates as MarkerSnapshot)) as Markers["previewUpdate"],
    previewDelete: (async (markerOrMarkers: MarkerSnapshot | readonly MarkerSnapshot[]) => Array.isArray(markerOrMarkers)
      ? makePreviews("delete", markerOrMarkers.map((target) => ({ target })))
      : makePreview("delete", undefined, markerOrMarkers as MarkerSnapshot)) as Markers["previewDelete"],
    create: (async (impact: MarkerImpactPreview | readonly MarkerImpactPreview[], options: MarkerMutationOptions) => {
      const started = await start("create", impact, options);
      return createTypedOperationHandle(runtime, started.event, "cutagent.action.timeline.marker.add", resultSchema(started.frameRate));
    }) as Markers["create"],
    update: (async (impact: MarkerImpactPreview | readonly MarkerImpactPreview[], options: MarkerMutationOptions) => {
      const started = await start("update", impact, options);
      return createTypedOperationHandle(runtime, started.event, "cutagent.action.timeline.marker.update", resultSchema(started.frameRate));
    }) as Markers["update"],
    delete: (async (impact: MarkerImpactPreview | readonly MarkerImpactPreview[], options: MarkerMutationOptions) => {
      const started = await start("delete", impact, options);
      return createTypedOperationHandle(runtime, started.event, "cutagent.action.timeline.marker.delete", resultSchema(started.frameRate));
    }) as Markers["delete"],
  });
}
