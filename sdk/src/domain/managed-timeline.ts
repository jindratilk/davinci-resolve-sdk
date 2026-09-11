import type { CarrierReadRequest, CarrierReadSuccess } from "../core/carrier-contract.js";
import type { ConnectionControlOptions } from "../core/public-client-types.js";
import type { WorkflowResult } from "../core/workflows.js";
import type { MediaPoolAssetSnapshot } from "./media-pool.js";
import type { TimelineSnapshot } from "./object-model.js";
import { IdempotencyKeySchema, MediaPoolItemIdSchema, ProjectIdSchema, RevisionSchema, TimelineIdSchema, TimelineItemIdSchema, TrackIndexSchema, type IdempotencyKey, type ProjectId, type Revision, type TimelineId, type TimelineItemId, type TrackIndex, type WorkflowId } from "../value-types/identities.js";
import { frames, sourceRange, timelineRecordPosition, timelineRecordRange, type FrameRate, type SourceRange, type TimelineRecordPosition, type TimelineRecordRange } from "../value-types/time.js";
import { hydrateFrameRate, hydrateTimecode, lowerFrameRate, lowerSourceRange, lowerTimelineRecordPosition, lowerTimelineRecordRange } from "../wire/time-adapter.js";
import { assertSourceRangeIsExactlyRepresentable, reportedSourceFrameRate } from "./timeline-editing.js";

/** Caller-stable identity for one declaratively owned timeline boundary. @beta */
export type ManagedOwnership = Readonly<{ readonly id: string }>;
/** Explicit managed boundary. Whole-timeline ownership is never inferred. @beta */
export type ManagedTimelineScope = Readonly<{ readonly kind: "whole_timeline" }> | Readonly<{ readonly kind: "region"; readonly range: TimelineRecordRange }>;
/** Exact live binding from which a managed program was authored. @beta */
export interface ManagedTimelineBinding { readonly projectId: ProjectId; readonly timelineId: TimelineId; readonly revision: Revision }
/** One desired clip. Keys are stable within an ownership boundary. @beta */
export interface ManagedClip {
  readonly kind: "clip"; readonly key: string; readonly asset: MediaPoolAssetSnapshot;
  readonly videoTrack: TrackIndex; readonly audioTrack?: TrackIndex; readonly at: TimelineRecordPosition;
  readonly sourceRange: SourceRange; readonly linkedAudio: "include" | "exclude";
  /** Explicitly adopt this exact durable item on the first application. */ readonly adopt?: TimelineItemId;
}
/** Immutable composable desired state for one owned boundary. @beta */
export interface ManagedTimelineProgram { readonly ownership: ManagedOwnership; readonly binding: ManagedTimelineBinding; readonly scope: ManagedTimelineScope; readonly content: readonly ManagedClip[] }
/** Semantic drift reported in deterministic key order. @beta */
export interface ManagedTimelineDrift { readonly kind: "create" | "update" | "remove" | "preserve"; readonly key: string; readonly timelineItemId?: TimelineItemId; readonly summary: string }
/** Why desired state cannot currently be applied safely. @beta */
export interface ManagedTimelineBlocker { readonly code: "stale_revision" | "ambiguous_identity" | "scope_crossing" | "unsupported_change" | "protected_state_unproven" | "ownership_overlap"; readonly key?: string; readonly message: string }
/** Immutable, context-bound result of a side-effect-free runtime reconciliation. @beta */
export interface ManagedTimelinePreview {
  readonly status: "no_change" | "ready" | "blocked"; readonly ownership: ManagedOwnership;
  readonly binding: ManagedTimelineBinding; readonly scope: ManagedTimelineScope; readonly desiredStateDigest: string;
  readonly contextDigest: string; readonly previewDigest: string; readonly drift: readonly ManagedTimelineDrift[];
  readonly protectedStateDigest: string;
  readonly blockers: readonly ManagedTimelineBlocker[];
}
/** Checkpoint-backed application options. This does not promise atomic rollback. @beta */
export interface ManagedTimelineApplyOptions extends ConnectionControlOptions { readonly idempotencyKey: IdempotencyKey; readonly recovery: "checkpoint"; readonly cancellationSignal?: AbortSignal }
/** Durable application handle whose only aggregate authority is its WorkflowId. @beta */
export interface ManagedTimelineApplication { readonly workflowId: Promise<WorkflowId>; wait(): Promise<WorkflowResult> }
/** Selection for a versioned managed-timeline export. Live IDs are bootstrap bindings, never author keys. @beta */
export type ManagedTimelineExportSelection = Readonly<{ readonly kind: "existing_ownership" }> | Readonly<{
  readonly kind: "adopt"; readonly clips: readonly Readonly<{ readonly key: string; readonly clip: import("./object-model.js").ClipSnapshot }>[];
}>;
/** Exact supported and protected coverage of managed-timeline dialect v1. @beta */
export interface ManagedTimelineCoverage {
  readonly represented: readonly ["clip_placement/v1"];
  readonly preservedButNotRepresented: readonly ["unmanaged_clips", "track_properties", "markers", "fusion", "color", "fairlight", "retime", "transitions", "effects", "captions"];
  readonly protectedStateDigest: string;
}
/** Versioned export over the existing managed program, not a project serialization. @beta */
export interface ManagedTimelineDocumentV1 {
  readonly dialect: "cutagent.managed-timeline"; readonly version: 1;
  readonly program: ManagedTimelineProgram; readonly coverage: ManagedTimelineCoverage;
}
/** Supported managed-timeline roundtrip documents. @beta */
export type ManagedTimelineDocument = ManagedTimelineDocumentV1;
/** Export either yields a complete versioned document or explicit blockers. @beta */
export type ManagedTimelineExportResult = Readonly<
  | { readonly status: "ready"; readonly document: ManagedTimelineDocument; readonly blockers: readonly [] }
  | { readonly status: "blocked"; readonly document: null; readonly blockers: readonly ManagedTimelineBlocker[] }
>;
/** Exact ownership, scope, and selection used for managed export. @beta */
export interface ManagedTimelineExportOptions extends ConnectionControlOptions {
  readonly ownership: ManagedOwnership; readonly scope: ManagedTimelineScope; readonly selection: ManagedTimelineExportSelection;
}
/** Declarative timeline/region facade bound to one exact live timeline. @beta */
export interface ManagedTimeline {
  /** Export supported clip placement state while explicitly protecting every unrepresented family. */
  export(snapshot: TimelineSnapshot, options: ManagedTimelineExportOptions): Promise<ManagedTimelineExportResult>;
  /** Ask the proprietary runtime to reconcile desired and live state without side effects. */
  preview(snapshot: TimelineSnapshot, program: ManagedTimelineProgram, options?: ConnectionControlOptions): Promise<ManagedTimelinePreview>;
  /** Apply only an unmodified ready preview through accepted semantic operations. */
  apply(preview: ManagedTimelinePreview, options: ManagedTimelineApplyOptions): ManagedTimelineApplication;
}

type ManagedPreviewWire = Extract<CarrierReadSuccess, { operation: "timeline.managed.preview" }>["data"];
type ManagedExportWire = Extract<CarrierReadSuccess, { operation: "timeline.managed.export" }>["data"];
type ManagedProgramWire = Extract<CarrierReadRequest, { operation: "timeline.managed.preview" }>["program"];
type RetainedPreview = Readonly<{ program: ManagedTimelineProgram; wireProgram: ManagedProgramWire; wirePreview: ManagedPreviewWire }>;
const ownershipPattern = /^[a-z0-9][a-z0-9._/-]{0,199}$/;
const keyPattern = /^[a-z][a-z0-9_-]{0,63}$/;
const managedCoverageRepresented = ["clip_placement/v1"];
const managedCoverageProtected = ["unmanaged_clips", "track_properties", "markers", "fusion", "color", "fairlight", "retime", "transitions", "effects", "captions"];
const freeze = <T>(value: T): T => {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    for (const nested of Object.values(value)) freeze(nested);
    Object.freeze(value);
  }
  return value;
};

/** Create a validated caller-stable ownership identity. @beta */
export function managedOwnership(id: string): ManagedOwnership {
  if (!ownershipPattern.test(id)) throw new TypeError("Managed ownership must use 1-200 lowercase letters, numbers, dots, slashes, underscores, or hyphens.");
  return freeze({ id });
}
/** Explicitly own the complete timeline and no other project state. @beta */
export function managedWholeTimeline(): ManagedTimelineScope { return freeze({ kind: "whole_timeline" }); }
/** Explicitly own one non-empty half-open timeline-record range. @beta */
export function managedRegion(range: TimelineRecordRange): ManagedTimelineScope {
  if (!range || range.domain !== "timeline_record_range") throw new TypeError("Managed region requires a timeline record range.");
  return freeze({ kind: "region", range });
}
/** Create one immutable desired clip declaration. @beta */
export function managedClip(key: string, input: Omit<ManagedClip, "kind" | "key">): ManagedClip {
  if (!keyPattern.test(key)) throw new TypeError("Managed element keys must begin with a lowercase letter and contain at most 64 lowercase letters, numbers, underscores, or hyphens.");
  if (!input.asset?.id) throw new TypeError("Managed clips require an authoritative Media Pool identity.");
  MediaPoolItemIdSchema.parse(input.asset.id); TrackIndexSchema.parse(input.videoTrack);
  if (input.audioTrack !== undefined) TrackIndexSchema.parse(input.audioTrack);
  if (input.linkedAudio === "include" && input.audioTrack === undefined) throw new TypeError("Managed linked audio requires an explicit audio track.");
  return freeze({ kind: "clip", key, ...input });
}
/** Define immutable desired state without executing or lowering it. @beta */
export function defineManagedTimeline(input: ManagedTimelineProgram): ManagedTimelineProgram {
  ProjectIdSchema.parse(input.binding.projectId); TimelineIdSchema.parse(input.binding.timelineId); RevisionSchema.parse(input.binding.revision); managedOwnership(input.ownership.id);
  if (!input.scope || (input.scope.kind !== "whole_timeline" && input.scope.kind !== "region")) throw new TypeError("Managed scope must be explicit.");
  const keys = new Set<string>();
  const adopted = new Set<string>();
  for (const element of input.content) {
    managedClip(element.key, element);
    if (keys.has(element.key)) throw new TypeError(`Managed element key is duplicated: ${element.key}`);
    keys.add(element.key);
    if (element.adopt && adopted.has(String(element.adopt))) throw new TypeError(`Managed timeline item is adopted by more than one key: ${element.adopt}`);
    if (element.adopt) adopted.add(String(element.adopt));
  }
  return freeze({ ownership: input.ownership, binding: input.binding, scope: input.scope, content: [...input.content] });
}

function timelineFrame(value: TimelineRecordPosition, snapshot: TimelineSnapshot): number {
  const wire = lowerTimelineRecordPosition(value, { frameRate: snapshot.frameRate }).value;
  return wire.kind === "frames" ? wire.value : hydrateTimecode(wire).toFrames().value;
}
function lowerProgram(program: ManagedTimelineProgram, snapshot: TimelineSnapshot): ManagedProgramWire {
  const scope = program.scope.kind === "whole_timeline" ? { kind: "whole_timeline" as const } : (() => {
    const range = lowerTimelineRecordRange(program.scope.range, { frameRate: snapshot.frameRate });
    return { kind: "region" as const, startFrame: range.start, endExclusiveFrame: range.endExclusive };
  })();
  const elements = program.content.map((element) => {
    const assetRate = reportedSourceFrameRate(element.asset.frameRate);
    const sourceRate = assetRate ?? element.sourceRange.rate;
    if (!sourceRate) throw new TypeError("Managed clip source ranges require an authoritative source frame rate.");
    if (element.sourceRange.rate && !element.sourceRange.rate.equals(sourceRate)) {
      throw new TypeError("Managed clip source range rate does not match its authoritative Media Pool asset rate.");
    }
    const source = lowerSourceRange(element.sourceRange, { frameRate: sourceRate });
    if (source.unit !== "frames") throw new TypeError("Managed clip source ranges must be expressed in source frames.");
    assertSourceRangeIsExactlyRepresentable(source, sourceRate, snapshot.frameRate);
    return { key: element.key, assetId: String(element.asset.id), assetName: element.asset.name, assetRevision: String(element.asset.assetCustodyRevision), videoTrack: element.videoTrack, audioTrack: element.audioTrack ?? null,
      atFrame: timelineFrame(element.at, snapshot), sourceStartFrame: source.start, sourceEndExclusiveFrame: source.endExclusive,
      sourceFrameRate: lowerFrameRate(sourceRate),
      linkedAudio: element.linkedAudio, adoptTimelineItemId: element.adopt ? String(element.adopt) : null };
  });
  return { projectId: String(program.binding.projectId), timelineId: String(program.binding.timelineId), revision: String(program.binding.revision), ownershipId: program.ownership.id,
    scope, timelineFrameRate: lowerFrameRate(snapshot.frameRate), elements } as unknown as ManagedProgramWire;
}

function lowerScope(scope: ManagedTimelineScope, snapshot: TimelineSnapshot): ManagedProgramWire["scope"] {
  if (scope.kind === "whole_timeline") return {kind: "whole_timeline"};
  const range = lowerTimelineRecordRange(scope.range, {frameRate: snapshot.frameRate});
  return {kind: "region", startFrame: range.start, endExclusiveFrame: range.endExclusive};
}

function hydrateExport(snapshot: TimelineSnapshot, raw: ManagedExportWire): ManagedTimelineExportResult {
  if (raw.status === "blocked") return freeze({status: "blocked", document: null,
    blockers: raw.blockers.map((entry) => freeze({code: entry.code, message: entry.message, ...(entry.key === undefined ? {} : {key: entry.key})}))});
  const assets = new Map(raw.assets.map((asset) => [asset.id, freeze({...asset, projectId: snapshot.projectId}) as unknown as MediaPoolAssetSnapshot]));
  const content = raw.program.elements.map((element) => {
    const asset = assets.get(element.assetId)!;
    if (String(asset.assetCustodyRevision) !== element.assetRevision) {
      throw new Error("CutAgent runtime returned a managed export with stale Media Pool asset custody.");
    }
    const sourceFrameRate = hydrateFrameRate(element.sourceFrameRate);
    const assetFrameRate = reportedSourceFrameRate(asset.frameRate);
    if (assetFrameRate && !assetFrameRate.equals(sourceFrameRate)) {
      throw new Error("CutAgent runtime returned a managed export source rate that differs from its authoritative Media Pool asset.");
    }
    return managedClip(element.key, {
      asset, videoTrack: TrackIndexSchema.parse(element.videoTrack),
      ...(element.audioTrack === null ? {} : {audioTrack: TrackIndexSchema.parse(element.audioTrack)}),
      at: timelineRecordPosition(frames(element.atFrame), snapshot.frameRate),
      sourceRange: sourceRange(frames(element.sourceStartFrame), frames(element.sourceEndExclusiveFrame), sourceFrameRate),
      linkedAudio: element.linkedAudio,
      ...(element.adoptTimelineItemId === null ? {} : {adopt: TimelineItemIdSchema.parse(element.adoptTimelineItemId)}),
    });
  });
  const scope = raw.program.scope.kind === "whole_timeline" ? managedWholeTimeline() : managedRegion(timelineRecordRange(
    frames(raw.program.scope.startFrame), frames(raw.program.scope.endExclusiveFrame), snapshot.frameRate,
  ));
  const program = defineManagedTimeline({ownership: managedOwnership(raw.program.ownershipId),
    binding: {projectId: ProjectIdSchema.parse(raw.program.projectId), timelineId: TimelineIdSchema.parse(raw.program.timelineId), revision: RevisionSchema.parse(raw.program.revision)},
    scope, content});
  return freeze({status: "ready", document: {dialect: raw.dialect, version: raw.version, program,
    coverage: raw.coverage}, blockers: []});
}

/** Render deterministic readable TypeScript that reconstructs the same managed program. @beta */
export function renderManagedTimelineDocument(document: ManagedTimelineDocument): string {
  if (document.dialect !== "cutagent.managed-timeline" || document.version !== 1) throw new TypeError("Unsupported managed-timeline document dialect.");
  if (JSON.stringify(document.coverage?.represented) !== JSON.stringify(managedCoverageRepresented)
    || JSON.stringify(document.coverage?.preservedButNotRepresented) !== JSON.stringify(managedCoverageProtected)
    || !/^sha256:[a-f0-9]{64}$/.test(document.coverage?.protectedStateDigest ?? "")) {
    throw new TypeError("Managed timeline document coverage is incomplete or invalid.");
  }
  const program = defineManagedTimeline(document.program);
  if (program.content.length > 32) throw new TypeError("Managed timeline document v1 supports at most 32 placements.");
  const boundFrame = (value: TimelineRecordPosition["value"]): {readonly value: number; readonly rate: FrameRate} => {
    if (value.kind !== "frames" || value.rate === null) throw new TypeError("Managed timeline TypeScript export requires frame-bound positions.");
    return value;
  };
  const unboundFrame = (value: SourceRange["start"]["value"]): number => {
    if (value.kind !== "frames") throw new TypeError("Managed timeline TypeScript export requires frame source ranges.");
    return value.value;
  };
  const sourceRate = (value: SourceRange): FrameRate => {
    if (!value.rate) throw new TypeError("Managed timeline TypeScript export requires source-frame rates.");
    return value.rate;
  };
  const renderRate = (value: FrameRate): string => `frameRate(${value.numerator}, ${value.denominator}, ${value.nominalTimebase})`;
  const firstPosition = program.content[0]?.at ?? (program.scope.kind === "region" ? program.scope.range.start : undefined);
  const rate = firstPosition === undefined ? undefined : boundFrame(firstPosition.value).rate;
  const json = (value: unknown) => JSON.stringify(value);
  const requireRate = (): FrameRate => {
    if (!rate) throw new TypeError("Managed timeline TypeScript export requires frame-bound positions.");
    return rate;
  };
  const scope = program.scope.kind === "whole_timeline" ? "managedWholeTimeline()" : `managedRegion(timelineRecordRange(frames(${boundFrame(program.scope.range.start.value).value}), frames(${boundFrame(program.scope.range.endExclusive.value).value}), rate))`;
  const clips = program.content.map((clip) => `    managedClip(${json(clip.key)}, {\n      asset: ${JSON.stringify(clip.asset, null, 2).replace(/\n/g, "\n      ")} as unknown as MediaPoolAssetSnapshot,\n      videoTrack: trackIndex(${clip.videoTrack}),${clip.audioTrack === undefined ? "" : `\n      audioTrack: trackIndex(${clip.audioTrack}),`}\n      at: timelineRecordPosition(frames(${boundFrame(clip.at.value).value}), rate),\n      sourceRange: sourceRange(frames(${unboundFrame(clip.sourceRange.start.value)}), frames(${unboundFrame(clip.sourceRange.endExclusive.value)}), ${renderRate(sourceRate(clip.sourceRange))}),\n      linkedAudio: ${json(clip.linkedAudio)},${clip.adopt ? `\n      // Timeline-bound first-adoption bootstrap; the author key above remains portable.\n      adopt: ${json(String(clip.adopt))} as TimelineItemId,` : ""}\n    })`).join(",\n");
  const rateDeclaration = rate === undefined ? "" : `const rate = frameRate(${requireRate().numerator}, ${requireRate().denominator}, ${requireRate().nominalTimebase});\n\n`;
  const valueImports = ["defineManagedTimeline", "managedOwnership", program.scope.kind === "whole_timeline" ? "managedWholeTimeline" : "managedRegion"];
  if (rate) valueImports.push("frameRate");
  if (program.content.length) valueImports.push("frames", "managedClip", "sourceRange", "timelineRecordPosition", "trackIndex");
  if (program.scope.kind === "region") valueImports.push("frames", "timelineRecordRange");
  const typeImports = ["ProjectId", "Revision", "TimelineId"];
  if (program.content.length) typeImports.push("MediaPoolAssetSnapshot");
  if (program.content.some((clip) => clip.adopt !== undefined)) typeImports.push("TimelineItemId");
  typeImports.push("ManagedTimelineDocument");
  return `import { ${[...new Set(valueImports)].sort().join(", ")} } from "cutagent";\nimport type { ${typeImports.sort().join(", ")} } from "cutagent";\n\n${rateDeclaration}export const timelineProgram = defineManagedTimeline({\n  ownership: managedOwnership(${json(program.ownership.id)}),\n  binding: { projectId: ${json(String(program.binding.projectId))} as ProjectId, timelineId: ${json(String(program.binding.timelineId))} as TimelineId, revision: ${json(String(program.binding.revision))} as Revision },\n  scope: ${scope},\n  content: [\n${clips}\n  ],\n});\n\nexport const timelineDocument = {\n  dialect: "cutagent.managed-timeline",\n  version: 1,\n  program: timelineProgram,\n  coverage: ${JSON.stringify(document.coverage, null, 2).replace(/\n/g, "\n  ")},\n} satisfies ManagedTimelineDocument;\n`;
}

/** @internal */
export function createManagedTimeline(
  runtime: { readonly generation: number; readAtGeneration(generation: number, request: CarrierReadRequest, options?: ConnectionControlOptions): Promise<CarrierReadSuccess>; managedStartAtGeneration(generation: number, binding: unknown, cancellationRequested: boolean, options?: ConnectionControlOptions): Promise<{ workflowId: WorkflowId; status: string }>; managedWaitAtGeneration(generation: number, workflowId: WorkflowId, options?: ConnectionControlOptions): Promise<WorkflowResult>; managedInterruptAtGeneration(generation: number, workflowId: WorkflowId): Promise<void> },
  projectId: ProjectId, timelineId: TimelineId,
): ManagedTimeline {
  const generation = runtime.generation;
  const issued = new WeakMap<ManagedTimelinePreview, RetainedPreview>();
  const facade: ManagedTimeline = {
    async export(snapshot, options) {
      if (snapshot.projectId !== projectId || snapshot.timelineId !== timelineId) throw new TypeError("Managed export requires a snapshot from this timeline facade.");
      const ownership = managedOwnership(options.ownership.id);
      const scope = options.scope.kind === "whole_timeline" ? managedWholeTimeline() : managedRegion(options.scope.range);
      let selection: {kind: "existing_ownership"} | {kind: "adopt"; clips: {key: string; timelineItemId: string}[]};
      if (options.selection.kind === "existing_ownership") selection = {kind: "existing_ownership"};
      else {
        const keys = new Set<string>(); const ids = new Set<string>();
        selection = {kind: "adopt", clips: options.selection.clips.map(({key, clip}) => {
          if (!keyPattern.test(key) || clip.id === null || clip.snapshotRevision !== snapshot.revision
            || snapshot.tracks.flatMap((track) => track.clips).filter((candidate) => candidate.id === clip.id && candidate.snapshotId === clip.snapshotId).length !== 1
            || keys.has(key) || ids.has(String(clip.id))) throw new TypeError("Managed adoption requires unique author keys and exact durable clips from this snapshot.");
          keys.add(key); ids.add(String(clip.id)); return {key, timelineItemId: String(clip.id)};
        })};
      }
      const request = {operation: "timeline.managed.export", request: {
        projectId: String(projectId), timelineId: String(timelineId), revision: String(snapshot.revision), ownershipId: ownership.id,
        scope: lowerScope(scope, snapshot), selection,
      }} as unknown as CarrierReadRequest;
      const response = await runtime.readAtGeneration(generation, request, options);
      if (response.operation !== "timeline.managed.export") throw new Error("CutAgent runtime returned the wrong managed export result.");
      if (response.data.status === "ready") {
        const expectedScope = lowerScope(scope, snapshot);
        const program = response.data.program;
        if (program.projectId !== String(projectId) || program.timelineId !== String(timelineId)
          || program.revision !== String(snapshot.revision) || program.ownershipId !== ownership.id
          || JSON.stringify(program.timelineFrameRate) !== JSON.stringify(lowerFrameRate(snapshot.frameRate))
          || JSON.stringify(program.scope) !== JSON.stringify(expectedScope)) {
          throw new Error("CutAgent runtime returned managed export state for another binding or ownership scope.");
        }
        const assetCounts = new Map<string, number>();
        for (const asset of response.data.assets) if (asset.id !== null) assetCounts.set(asset.id, (assetCounts.get(asset.id) ?? 0) + 1);
        if (program.elements.some((element) => assetCounts.get(element.assetId) !== 1)) {
          throw new Error("CutAgent runtime returned an ambiguous managed export asset inventory.");
        }
        if (selection.kind === "adopt") {
          const expected: [string, string][] = [...selection.clips].map(({key, timelineItemId}) => [key, timelineItemId]);
          const actual: [string, string | null][] = program.elements.map(({key, adoptTimelineItemId}) => [key, adoptTimelineItemId]);
          expected.sort((left, right) => left[0].localeCompare(right[0]));
          actual.sort((left, right) => left[0].localeCompare(right[0]));
          if (JSON.stringify(actual) !== JSON.stringify(expected)) throw new Error("CutAgent runtime changed the exact managed adoption key binding.");
        } else if (program.elements.some((element) => element.adoptTimelineItemId !== null)) {
          throw new Error("Existing managed ownership export cannot reintroduce timeline-bound adoption identities.");
        }
      }
      return hydrateExport(snapshot, response.data);
    },
    async preview(snapshot, rawProgram, options = {}) {
      const program = defineManagedTimeline(rawProgram);
      if (snapshot.projectId !== projectId || snapshot.timelineId !== timelineId || program.binding.projectId !== projectId || program.binding.timelineId !== timelineId || snapshot.revision !== program.binding.revision) {
        throw new TypeError("Managed preview requires an exact program and snapshot from this timeline revision.");
      }
      const wireProgram = lowerProgram(program, snapshot);
      const response = await runtime.readAtGeneration(generation, { operation: "timeline.managed.preview", program: wireProgram }, options);
      if (response.operation !== "timeline.managed.preview") throw new Error("CutAgent runtime returned the wrong managed preview result.");
      const wirePreview = response.data;
      if (wirePreview.projectId !== String(projectId) || wirePreview.timelineId !== String(timelineId) || wirePreview.ownershipId !== program.ownership.id) throw new Error("CutAgent runtime returned a managed preview for another ownership boundary.");
      const preview: ManagedTimelinePreview = freeze({
        status: wirePreview.status, ownership: program.ownership,
        binding: { projectId, timelineId, revision: RevisionSchema.parse(wirePreview.revision) }, scope: program.scope,
        desiredStateDigest: wirePreview.desiredStateDigest, contextDigest: wirePreview.contextDigest, previewDigest: wirePreview.previewDigest,
        protectedStateDigest: wirePreview.protectedStateDigest,
        drift: wirePreview.drift.map((entry): ManagedTimelineDrift => freeze({ kind: entry.kind, key: entry.key, summary: entry.summary, ...(entry.timelineItemId ? { timelineItemId: TimelineItemIdSchema.parse(entry.timelineItemId) } : {}) })),
        blockers: wirePreview.blockers.map((entry): ManagedTimelineBlocker => freeze({ code: entry.code, message: entry.message, ...(entry.key ? { key: entry.key } : {}) })),
      });
      issued.set(preview, freeze({ program, wireProgram, wirePreview }));
      return preview;
    },
    apply(preview, options) {
      const retained = issued.get(preview);
      if (!retained || preview.status !== "ready" || runtime.generation !== generation) throw new TypeError("Managed apply requires an unmodified ready preview issued by this timeline facade and client generation.");
      IdempotencyKeySchema.parse(options?.idempotencyKey);
      if (options.recovery !== "checkpoint") throw new TypeError("Managed apply requires explicit checkpoint recovery.");
      const admitted = runtime.managedStartAtGeneration(generation,
            { projectId, timelineId, revision: preview.binding.revision, idempotencyKey: options.idempotencyKey,
              managedClaim: { ownershipId: preview.ownership.id, scope: retained.wireProgram.scope, timelineFrameRate: retained.wireProgram.timelineFrameRate, previewDigest: preview.previewDigest,
                contextDigest: preview.contextDigest, protectedStateDigest: preview.protectedStateDigest, desiredStateDigest: preview.desiredStateDigest, elements: retained.wireProgram.elements } },
            options.cancellationSignal?.aborted === true,
            options.timeoutMs === undefined ? {} : { timeoutMs: options.timeoutMs });
      let detachCancellation = () => {};
      let cancellationRequest: Promise<void> | undefined;
      if (options.cancellationSignal && !options.cancellationSignal.aborted) {
        const signal = options.cancellationSignal;
        void admitted.then((snapshot) => {
          const interrupt = () => {
            cancellationRequest ??= runtime.managedInterruptAtGeneration(generation, snapshot.workflowId);
            void cancellationRequest.catch(() => {});
          };
          signal.addEventListener("abort", interrupt, { once: true });
          detachCancellation = () => signal.removeEventListener("abort", interrupt);
          if (signal.aborted) interrupt();
        }).catch(() => {});
      }
      const workflowId = admitted.then((snapshot) => snapshot.workflowId);
      let result: Promise<WorkflowResult> | undefined;
      return freeze({ workflowId, wait: () => {
        result ??= admitted.then(async (snapshot) => {
          if (options.cancellationSignal?.aborted && cancellationRequest) await cancellationRequest;
          return runtime.managedWaitAtGeneration(generation, snapshot.workflowId, options.timeoutMs === undefined ? {} : { timeoutMs: options.timeoutMs });
        });
        void result.finally(() => detachCancellation()).catch(() => {});
        return result;
      } });
    },
  };
  Object.setPrototypeOf(facade, null);
  return Object.freeze(facade);
}
