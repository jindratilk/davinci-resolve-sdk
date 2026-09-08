import { z } from "zod";
import {
  sdkMulticamCreateInputSchema,
  sdkMulticamCreateResultSchema,
  sdkMulticamFlattenInputSchema,
  sdkMulticamFlattenResultSchema,
  sdkMulticamSnapshotSchema,
  sdkMulticamSwitchInputSchema,
  sdkMulticamSwitchResultSchema,
  type SdkOperationEvent,
} from "../generated/sdk-operations.js";
import {
  sdkIdempotencyKeySchema,
  sdkMediaPoolItemIdSchema,
  sdkProjectIdSchema,
} from "../generated/sdk-identities.js";
import { createTypedOperationHandle } from "../core/operations.js";
import type { ConnectionControlOptions } from "../core/public-client-types.js";
import type { EstablishedCarrierSession } from "../core/carrier-session.js";
import type { OperationHandle } from "../protocol/operations.js";
import {
  IdempotencyKeySchema,
  MediaPoolItemIdSchema,
  MulticamAngleIdSchema,
  MulticamIdSchema,
  ProjectIdSchema,
  RevisionSchema,
  TimelineIdSchema,
  type IdempotencyKey,
  type MediaPoolItemId,
  type MulticamAngleId,
  type MulticamId,
  type ProjectId,
  type Revision,
  type TimelineId,
} from "../value-types/identities.js";
import type { TimelineRecordPosition } from "../value-types/time.js";
import { hydrateTimecode, lowerTimelineRecordPosition } from "../wire/time-adapter.js";
import type { FrameRate } from "../value-types/time.js";
import type { MediaPoolAssetSnapshot } from "./media-pool.js";
import type { TimelineSnapshot } from "./object-model.js";

/** One source item assigned to a native multicam angle. @beta */
export interface MulticamSourceSnapshot {
  readonly mediaPoolItemId: MediaPoolItemId;
  readonly name: string;
}

/** One stable angle in an exact multicam revision. @beta */
export interface MulticamAngleSnapshot {
  readonly id: MulticamAngleId;
  readonly label: string;
  readonly enabled: boolean | null;
  readonly sources: readonly MulticamSourceSnapshot[];
}

/** Immutable structural readback of one native multicam clip. @beta */
export interface MulticamSnapshot {
  readonly id: MulticamId;
  readonly projectId: ProjectId;
  readonly revision: Revision;
  readonly name: string;
  readonly angles: readonly MulticamAngleSnapshot[];
  /** Resolve exactly one angle by its public label. */
  angle(label: string): MulticamAngleSnapshot;
}

/** A stable Media Pool source and the logical angle it belongs to. @beta */
export interface MulticamSourceInput {
  readonly asset: MediaPoolAssetSnapshot;
  readonly angleLabel: string;
}

/** Semantic native-multicam creation request. @beta */
export interface MulticamCreateInput {
  readonly name: string;
  readonly sources: readonly MulticamSourceInput[];
  readonly syncMode: "in" | "out" | "timecode" | "sound" | "marker";
  readonly timelineName?: string;
}

/** Public impact preview for native multicam creation. @beta */
export interface MulticamCreateImpactPreview {
  readonly action: "create";
  readonly projectId: ProjectId;
  readonly mediaPoolRevision: Revision;
  readonly name: string;
  readonly sourceCount: number;
  readonly angleLabels: readonly string[];
  readonly createsTimeline: boolean;
  readonly summary: string;
}

/** Public impact preview for multicam angle switching. @beta */
export interface MulticamSwitchImpactPreview {
  readonly action: "switch";
  readonly projectId: ProjectId;
  readonly timelineId: TimelineId;
  readonly timelineRevision: Revision;
  readonly multicamId: MulticamId;
  readonly multicamRevision: Revision;
  readonly switchCount: number;
  readonly scope: "linked" | "video" | "audio";
  readonly summary: string;
}

/** Public impact preview for replacing multicam wrappers with source items. @beta */
export interface MulticamFlattenImpactPreview {
  readonly action: "flatten";
  readonly projectId: ProjectId;
  readonly timelineId: TimelineId;
  readonly timelineRevision: Revision;
  readonly multicamId: MulticamId;
  readonly multicamRevision: Revision;
  readonly scope: "video" | "audio" | "both";
  readonly gradePolicy: "copy_multicam" | "retain_angle";
  readonly summary: string;
}

/** One explicit program-angle change in timeline record time. @beta */
export interface MulticamSwitchPoint {
  readonly at: TimelineRecordPosition;
  readonly angle: MulticamAngleSnapshot;
}

/** Required replay and local-control values for a multicam mutation. @beta */
export interface MulticamMutationOptions extends ConnectionControlOptions {
  readonly idempotencyKey: IdempotencyKey;
}

/** Verified semantic result of creating a native multicam clip. @beta */
export interface MulticamTimelineResult {
  readonly id: TimelineId;
  readonly projectId: ProjectId;
  readonly revision: Revision;
  readonly name: string;
}
/** Verified semantic result of creating a native multicam clip. @beta */
export interface MulticamCreateResult {
  readonly actionId: "cutagent.action.multicam.create";
  readonly multicam: MulticamSnapshot;
  readonly timeline: MulticamTimelineResult | null;
}
/** Verified semantic result of switching native multicam angles. @beta */
export interface MulticamSwitchResult {
  readonly actionId: "cutagent.action.multicam.switch";
  readonly multicam: MulticamSnapshot;
  readonly timeline: MulticamTimelineResult;
  readonly changedSegments: number;
}
/** Verified semantic result of flattening native multicam wrappers. @beta */
export interface MulticamFlattenResult {
  readonly actionId: "cutagent.action.multicam.flatten";
  readonly multicam: MulticamSnapshot;
  readonly timeline: MulticamTimelineResult;
  readonly changedSegments: number;
}

export interface MulticamRuntime {
  sessionAtGeneration(generation: number): EstablishedCarrierSession;
  createOperationAtGeneration(generation: number, request: Parameters<EstablishedCarrierSession["operation"]>[0], options?: ConnectionControlOptions): Promise<SdkOperationEvent>;
  readAtGeneration(generation: number, request: Parameters<EstablishedCarrierSession["read"]>[0], options?: ConnectionControlOptions): ReturnType<EstablishedCarrierSession["read"]>;
}

/** Native multicam inspection and creation rooted in one exact project. @beta */
export interface Multicams {
  inspect(asset: MediaPoolAssetSnapshot, options?: ConnectionControlOptions): Promise<MulticamSnapshot>;
  previewCreate(input: MulticamCreateInput): MulticamCreateImpactPreview;
  create(preview: MulticamCreateImpactPreview, options: MulticamMutationOptions): Promise<OperationHandle<MulticamCreateResult, "cutagent.action.multicam.create">>;
}

/** Native multicam editing rooted in one exact timeline. @beta */
export interface TimelineMulticam {
  previewSwitch(multicam: MulticamSnapshot, switches: readonly MulticamSwitchPoint[], options?: { readonly scope?: "linked" | "video" | "audio" }): Promise<MulticamSwitchImpactPreview>;
  switch(preview: MulticamSwitchImpactPreview, options: MulticamMutationOptions): Promise<OperationHandle<MulticamSwitchResult, "cutagent.action.multicam.switch">>;
  previewFlatten(multicam: MulticamSnapshot, options?: { readonly scope?: "video" | "audio" | "both"; readonly gradePolicy?: "copy_multicam" | "retain_angle" }): Promise<MulticamFlattenImpactPreview>;
  flatten(preview: MulticamFlattenImpactPreview, options: MulticamMutationOptions): Promise<OperationHandle<MulticamFlattenResult, "cutagent.action.multicam.flatten">>;
}

type Internal = { public: object; collection: object; input: unknown };
const internals = new WeakMap<object, Internal>();

function freeze<T extends object>(value: T): Readonly<T> {
  Object.setPrototypeOf(value, null);
  return Object.freeze(value);
}

function snapshot(raw: unknown): MulticamSnapshot {
  const parsed = sdkMulticamSnapshotSchema.parse(raw);
  const angles = Object.freeze(parsed.angles.map((angle) => freeze({
    id: MulticamAngleIdSchema.parse(angle.id),
    label: angle.label,
    enabled: angle.enabled,
    sources: Object.freeze(angle.sources.map((source) => freeze({ mediaPoolItemId: MediaPoolItemIdSchema.parse(source.mediaPoolItemId), name: source.name }))),
  })));
  return freeze({
    id: MulticamIdSchema.parse(parsed.id), projectId: ProjectIdSchema.parse(parsed.projectId), revision: RevisionSchema.parse(parsed.revision), name: parsed.name, angles,
    angle(label: string) {
      const matches = angles.filter((angle) => angle.label === label);
      if (matches.length !== 1) throw new TypeError(matches.length === 0 ? `Multicam angle '${label}' was not found.` : `Multicam angle '${label}' is ambiguous.`);
      return matches[0]!;
    },
  });
}

function recordFrame(position: TimelineRecordPosition, rate: FrameRate): number {
  const value = lowerTimelineRecordPosition(position, { frameRate: rate }).value;
  return value.kind === "frames" ? value.value : hydrateTimecode(value).toFrames().value;
}

function operation<TResult, TAction extends "cutagent.action.multicam.create" | "cutagent.action.multicam.switch" | "cutagent.action.multicam.flatten">(
  runtime: MulticamRuntime, generation: number, event: SdkOperationEvent, action: TAction, schema: { parse(value: unknown): TResult },
) {
  return createTypedOperationHandle({ session: () => runtime.sessionAtGeneration(generation) }, event, action, schema);
}

function timelineResult(raw: { id: string; projectId: string; revision: string; name: string }): MulticamTimelineResult {
  return freeze({
    id: TimelineIdSchema.parse(raw.id),
    projectId: ProjectIdSchema.parse(raw.projectId),
    revision: RevisionSchema.parse(raw.revision),
    name: raw.name,
  });
}

type MulticamResultBinding =
  | {
      action: "create";
      projectId: string;
      multicamName: string;
      createTimeline: boolean;
      timelineName?: string;
      sources: readonly { mediaPoolItemId: string; angleLabel: string }[];
    }
  | {
      action: "switch" | "flatten";
      projectId: string;
      timelineId: string;
      timelineRevision: string;
      multicamId: string;
      multicamRevision: string;
    };

function sortedSourceBindings(values: readonly { mediaPoolItemId: string; angleLabel: string }[]): string[] {
  return values.map((value) => `${value.angleLabel}\u0000${value.mediaPoolItemId}`).sort();
}

function resultSchema<T extends MulticamCreateResult | MulticamSwitchResult | MulticamFlattenResult>(
  wireSchema: z.ZodTypeAny,
  binding: MulticamResultBinding,
): z.ZodType<T> {
  return z.object({}).passthrough().transform((value) => {
    const parsed = wireSchema.parse(value) as z.infer<typeof sdkMulticamCreateResultSchema>
      | z.infer<typeof sdkMulticamSwitchResultSchema>
      | z.infer<typeof sdkMulticamFlattenResultSchema>;
    if (String(parsed.multicam.projectId) !== binding.projectId) throw new TypeError("Multicam result belongs to another project.");
    if (binding.action === "create") {
      if (parsed.multicam.name !== binding.multicamName) throw new TypeError("Created multicam does not match the requested name.");
      const actualSources = sortedSourceBindings(parsed.multicam.angles.flatMap((angle) =>
        angle.sources.map((source) => ({ mediaPoolItemId: String(source.mediaPoolItemId), angleLabel: angle.label }))));
      const expectedSources = sortedSourceBindings(binding.sources);
      if (actualSources.length !== expectedSources.length || actualSources.some((value, index) => value !== expectedSources[index])) {
        throw new TypeError("Created multicam does not contain the requested source-angle bindings.");
      }
      if (binding.createTimeline !== (parsed.timeline !== null)) throw new TypeError("Created timeline presence contradicts the request.");
      if (parsed.timeline !== null && parsed.timeline.name !== binding.timelineName) throw new TypeError("Created timeline does not match the requested name.");
    } else {
      if (String(parsed.multicam.id) !== binding.multicamId) throw new TypeError("Multicam result belongs to another multicam.");
      if (String(parsed.multicam.revision) !== binding.multicamRevision) throw new TypeError("Multicam result does not preserve the inspected revision.");
      if (parsed.timeline === null || String(parsed.timeline.id) !== binding.timelineId) throw new TypeError("Multicam result belongs to another timeline.");
      if (String(parsed.timeline.revision) === binding.timelineRevision) throw new TypeError("Multicam result did not advance the timeline revision.");
    }
    return freeze({
      actionId: parsed.actionId,
      multicam: snapshot(parsed.multicam),
      timeline: parsed.timeline === null ? null : timelineResult(parsed.timeline),
      ...("changedSegments" in parsed ? { changedSegments: parsed.changedSegments } : {}),
    }) as T;
  }) as z.ZodType<T>;
}

export function createProjectMulticams(runtime: MulticamRuntime, generation: number, projectId: ProjectId): Multicams {
  const collection = Object.freeze({});
  return freeze({
    async inspect(asset, options = {}) {
      if (asset.kind !== "multicam" || asset.id === null) throw new TypeError("Multicam inspection requires a durable Media Pool multicam asset.");
      const response = await runtime.readAtGeneration(generation, {
        operation: "multicam.inspect",
        projectId: sdkProjectIdSchema.parse(projectId),
        mediaPoolItemId: sdkMediaPoolItemIdSchema.parse(asset.id),
        multicamName: asset.name,
        expectedRevision: null,
      }, options);
      if (response.operation !== "multicam.inspect") throw new TypeError("CutAgent runtime returned the wrong multicam inspection result.");
      if (String(response.data.projectId) !== String(projectId)) throw new TypeError("CutAgent runtime returned a multicam from another project.");
      return snapshot(response.data);
    },
    previewCreate(input) {
      if (input.sources.length < 2) throw new TypeError("Multicam creation requires at least two source items.");
      const revisions = new Set(input.sources.map((source) => source.asset.snapshotRevision));
      if (revisions.size !== 1) throw new TypeError("Multicam sources must come from one coherent Media Pool revision.");
      for (const source of input.sources) {
        if (source.asset.id === null) throw new TypeError("Multicam creation requires durable source identities.");
        if (source.asset.kind !== "video") throw new TypeError("Standard multicam creation requires video source assets.");
      }
      const wire = sdkMulticamCreateInputSchema.parse({
        projectId, mediaPoolRevision: input.sources[0]!.asset.snapshotRevision, name: input.name,
        sources: input.sources.map((source) => ({ mediaPoolItemId: source.asset.id, angleLabel: source.angleLabel })),
        syncMode: input.syncMode, createTimeline: input.timelineName !== undefined, ...(input.timelineName ? { timelineName: input.timelineName } : {}),
      });
      const labels = Object.freeze([...new Set(wire.sources.map((source) => source.angleLabel))]);
      const value = freeze({ action: "create" as const, projectId, mediaPoolRevision: RevisionSchema.parse(wire.mediaPoolRevision), name: wire.name, sourceCount: wire.sources.length, angleLabels: labels, createsTimeline: wire.createTimeline, summary: `Create '${wire.name}' from ${wire.sources.length} source items across ${labels.length} angles${wire.createTimeline ? " and create its timeline" : ""}.` });
      internals.set(value, { public: value, collection, input: wire });
      return value;
    },
    async create(preview, options) {
      const internal = internals.get(preview);
      if (!internal || internal.public !== preview || internal.collection !== collection) throw new TypeError("Multicam creation requires its matching CutAgent impact preview.");
      IdempotencyKeySchema.parse(options.idempotencyKey);
      const input = sdkMulticamCreateInputSchema.parse(internal.input);
      const event = await runtime.createOperationAtGeneration(generation, { operation: "operation.create", actionId: "cutagent.action.multicam.create", input, idempotencyKey: sdkIdempotencyKeySchema.parse(options.idempotencyKey) }, options);
      return operation(runtime, generation, event, "cutagent.action.multicam.create", resultSchema<MulticamCreateResult>(sdkMulticamCreateResultSchema, {
        action: "create",
        projectId: String(input.projectId),
        multicamName: input.name,
        createTimeline: input.createTimeline,
        ...(input.timelineName === undefined ? {} : { timelineName: input.timelineName }),
        sources: input.sources.map((source) => ({ mediaPoolItemId: String(source.mediaPoolItemId), angleLabel: source.angleLabel })),
      }));
    },
  });
}

export function createTimelineMulticam(runtime: MulticamRuntime, generation: number, readTimeline: (options?: ConnectionControlOptions) => Promise<TimelineSnapshot>): TimelineMulticam {
  const collection = Object.freeze({});
  const bind = <T extends object>(value: T, input: unknown): T => { internals.set(value, { public: value, collection, input }); return value; };
  return freeze({
    async previewSwitch(multicam, switches, options = {}) {
      const timeline = await readTimeline();
      if (multicam.projectId !== timeline.projectId) throw new TypeError("Multicam and timeline belong to different projects.");
      const scope = options.scope ?? "linked";
      if (switches.some((point) => !multicam.angles.includes(point.angle))) throw new TypeError("Every switch angle must belong to the inspected multicam snapshot.");
      const loweredSwitches = switches.map((point) => ({ atRecordFrame: recordFrame(point.at, timeline.frameRate), angleId: point.angle.id, scope }));
      if (!loweredSwitches.every((point, index) => index === 0 || point.atRecordFrame > loweredSwitches[index - 1]!.atRecordFrame)) {
        throw new TypeError("Multicam switches must be strictly increasing by record frame.");
      }
      const wire = sdkMulticamSwitchInputSchema.parse({ projectId: timeline.projectId, timelineId: timeline.timelineId, timelineRevision: timeline.revision, multicamId: multicam.id, multicamRevision: multicam.revision, switches: loweredSwitches });
      const value = freeze({ action: "switch" as const, projectId: timeline.projectId, timelineId: timeline.timelineId, timelineRevision: timeline.revision, multicamId: multicam.id, multicamRevision: multicam.revision, switchCount: wire.switches.length, scope, summary: `Apply ${wire.switches.length} ${scope} multicam angle switch${wire.switches.length === 1 ? "" : "es"}.` });
      return bind(value, wire);
    },
    async switch(preview, options) {
      const internal = internals.get(preview);
      if (!internal || internal.public !== preview || internal.collection !== collection) throw new TypeError("Multicam switching requires its matching CutAgent impact preview.");
      IdempotencyKeySchema.parse(options.idempotencyKey);
      const input = sdkMulticamSwitchInputSchema.parse(internal.input);
      const event = await runtime.createOperationAtGeneration(generation, { operation: "operation.create", actionId: "cutagent.action.multicam.switch", input, idempotencyKey: sdkIdempotencyKeySchema.parse(options.idempotencyKey) }, options);
      return operation(runtime, generation, event, "cutagent.action.multicam.switch", resultSchema<MulticamSwitchResult>(sdkMulticamSwitchResultSchema, {
        action: "switch",
        projectId: String(input.projectId),
        timelineId: String(input.timelineId),
        timelineRevision: String(input.timelineRevision),
        multicamId: String(input.multicamId),
        multicamRevision: String(input.multicamRevision),
      }));
    },
    async previewFlatten(multicam, options = {}) {
      const timeline = await readTimeline();
      if (multicam.projectId !== timeline.projectId) throw new TypeError("Multicam and timeline belong to different projects.");
      const scope = options.scope ?? "both";
      const gradePolicy = options.gradePolicy ?? "copy_multicam";
      const wire = sdkMulticamFlattenInputSchema.parse({ projectId: timeline.projectId, timelineId: timeline.timelineId, timelineRevision: timeline.revision, multicamId: multicam.id, multicamRevision: multicam.revision, scope, gradePolicy });
      const value = freeze({ action: "flatten" as const, projectId: timeline.projectId, timelineId: timeline.timelineId, timelineRevision: timeline.revision, multicamId: multicam.id, multicamRevision: multicam.revision, scope, gradePolicy, summary: `Flatten ${scope} multicam wrappers using the ${gradePolicy} grade policy.` });
      return bind(value, wire);
    },
    async flatten(preview, options) {
      const internal = internals.get(preview);
      if (!internal || internal.public !== preview || internal.collection !== collection) throw new TypeError("Multicam flattening requires its matching CutAgent impact preview.");
      IdempotencyKeySchema.parse(options.idempotencyKey);
      const input = sdkMulticamFlattenInputSchema.parse(internal.input);
      const event = await runtime.createOperationAtGeneration(generation, { operation: "operation.create", actionId: "cutagent.action.multicam.flatten", input, idempotencyKey: sdkIdempotencyKeySchema.parse(options.idempotencyKey) }, options);
      return operation(runtime, generation, event, "cutagent.action.multicam.flatten", resultSchema<MulticamFlattenResult>(sdkMulticamFlattenResultSchema, {
        action: "flatten",
        projectId: String(input.projectId),
        timelineId: String(input.timelineId),
        timelineRevision: String(input.timelineRevision),
        multicamId: String(input.multicamId),
        multicamRevision: String(input.multicamRevision),
      }));
    },
  });
}
