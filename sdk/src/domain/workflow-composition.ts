import type {
  CheckpointWorkflowOptions,
  WorkflowResult,
  WorkflowOperationHandle,
  WorkflowStepResult,
  Workflows,
} from "../core/workflows.js";
import type { OperationHandle, PublicActionId } from "../protocol/operations.js";
import {
  IdempotencyKeySchema,
  type IdempotencyKey,
  type ProjectId,
  type Revision,
  type TimelineId,
  type TimelineItemId,
} from "../value-types/identities.js";
import type { FrameRate, TimelineRecordRange } from "../value-types/time.js";
import {
  hydrateTimelineRecordRange,
  lowerTimelineRecordRange,
} from "../wire/time-adapter.js";
import type {
  ClipSnapshot,
  TimelineSnapshot,
  TrackSnapshot,
} from "./object-model.js";
import type {
  MulticamAngleSnapshot,
  MulticamSwitchPoint,
} from "./multicam.js";

/** Legacy high-level actions covered by normal public TypeScript composition. @beta */
export type HighLevelWorkflowEquivalentActionId =
  | "cutagent.action.auto_edit.multicam"
  | "cutagent.action.auto_edit.podcast_edit"
  | "cutagent.action.auto_edit.podcast_multicam"
  | "cutagent.action.auto_edit.run"
  | "cutagent.action.auto_edit.silence_cut"
  | "cutagent.action.batch.run"
  | "cutagent.action.batch.validate"
  | "cutagent.action.bulk.clip_color_set"
  | "cutagent.action.bulk.disable"
  | "cutagent.action.bulk.enable"
  | "cutagent.action.bulk.lut_set"
  | "cutagent.action.bulk.property_set"
  | "cutagent.action.bulk.select"
  | "cutagent.action.edit.transition.batch"
  | "cutagent.action.timeline.clip_color.batch"
  | "cutagent.action.timeline.frame_export.batch"
  | "cutagent.action.timeline.layout.free_stack"
  | "cutagent.action.timeline.marker.batch"
  | "cutagent.action.timeline.overlay_stack.insert";

/** Public, implementation-free mapping from legacy workflow concepts to SDK composition. @beta */
export interface HighLevelWorkflowEquivalent {
  readonly actionId: HighLevelWorkflowEquivalentActionId;
  readonly publicSymbols: readonly string[];
  readonly lifecycle: "read" | "checkpoint_workflow" | "durable_operation";
  readonly targetBinding: "timeline_snapshot" | "project_and_timeline_revision";
  readonly verification: "structural_readback" | "workflow_step_verification";
}

const equivalent = (
  actionId: HighLevelWorkflowEquivalentActionId,
  publicSymbols: readonly string[],
  lifecycle: HighLevelWorkflowEquivalent["lifecycle"],
  targetBinding: HighLevelWorkflowEquivalent["targetBinding"],
): HighLevelWorkflowEquivalent => Object.freeze({
  actionId,
  publicSymbols: Object.freeze([...publicSymbols]),
  lifecycle,
  targetBinding,
  verification: lifecycle === "read" ? "structural_readback" : "workflow_step_verification",
});

/**
 * Exact source-level accounting for workflow-shaped CLI conveniences.
 *
 * Values name only public SDK symbols. They contain no command path, argument
 * lowering, native route, or proprietary orchestration metadata.
 * @beta
 */
export const HIGH_LEVEL_WORKFLOW_EQUIVALENTS: Readonly<Record<HighLevelWorkflowEquivalentActionId, HighLevelWorkflowEquivalent>> = Object.freeze({
  "cutagent.action.auto_edit.multicam": equivalent("cutagent.action.auto_edit.multicam", ["Project.multicams.create", "Timeline.multicam.switch", "executeOperationBatch"], "checkpoint_workflow", "project_and_timeline_revision"),
  "cutagent.action.auto_edit.podcast_edit": equivalent("cutagent.action.auto_edit.podcast_edit", ["planPodcastMulticamSwitches", "Project.multicams.create", "Timeline.multicam.switch", "executeOperationBatch"], "checkpoint_workflow", "project_and_timeline_revision"),
  "cutagent.action.auto_edit.podcast_multicam": equivalent("cutagent.action.auto_edit.podcast_multicam", ["planPodcastMulticamSwitches", "Project.multicams.create", "Timeline.multicam.switch", "executeOperationBatch"], "checkpoint_workflow", "project_and_timeline_revision"),
  "cutagent.action.auto_edit.run": equivalent("cutagent.action.auto_edit.run", ["defineOperationBatch", "executeOperationBatch"], "checkpoint_workflow", "project_and_timeline_revision"),
  "cutagent.action.auto_edit.silence_cut": equivalent("cutagent.action.auto_edit.silence_cut", ["planSilenceRetention", "defineManagedTimeline", "ManagedTimeline.preview", "ManagedTimeline.apply"], "checkpoint_workflow", "timeline_snapshot"),
  "cutagent.action.batch.run": equivalent("cutagent.action.batch.run", ["defineOperationBatch", "executeOperationBatch"], "checkpoint_workflow", "project_and_timeline_revision"),
  "cutagent.action.batch.validate": equivalent("cutagent.action.batch.validate", ["defineOperationBatch", "validateOperationBatch"], "read", "project_and_timeline_revision"),
  "cutagent.action.bulk.clip_color_set": equivalent("cutagent.action.bulk.clip_color_set", ["selectTimelineClips", "defineSelectedClipBatch", "executeOperationBatch"], "checkpoint_workflow", "timeline_snapshot"),
  "cutagent.action.bulk.disable": equivalent("cutagent.action.bulk.disable", ["selectTimelineClips", "defineSelectedClipBatch", "executeOperationBatch"], "checkpoint_workflow", "timeline_snapshot"),
  "cutagent.action.bulk.enable": equivalent("cutagent.action.bulk.enable", ["selectTimelineClips", "defineSelectedClipBatch", "executeOperationBatch"], "checkpoint_workflow", "timeline_snapshot"),
  "cutagent.action.bulk.lut_set": equivalent("cutagent.action.bulk.lut_set", ["selectTimelineClips", "defineSelectedClipBatch", "executeOperationBatch"], "checkpoint_workflow", "timeline_snapshot"),
  "cutagent.action.bulk.property_set": equivalent("cutagent.action.bulk.property_set", ["selectTimelineClips", "defineSelectedClipBatch", "executeOperationBatch"], "checkpoint_workflow", "timeline_snapshot"),
  "cutagent.action.bulk.select": equivalent("cutagent.action.bulk.select", ["selectTimelineClips"], "read", "timeline_snapshot"),
  "cutagent.action.edit.transition.batch": equivalent("cutagent.action.edit.transition.batch", ["defineOperationBatch", "executeOperationBatch", "Actions.invoke", "ActionIds.edit.transition.add"], "checkpoint_workflow", "timeline_snapshot"),
  "cutagent.action.timeline.clip_color.batch": equivalent("cutagent.action.timeline.clip_color.batch", ["defineOperationBatch", "executeOperationBatch", "Actions.invoke", "ActionIds.clip.color"], "checkpoint_workflow", "timeline_snapshot"),
  "cutagent.action.timeline.frame_export.batch": equivalent("cutagent.action.timeline.frame_export.batch", ["defineOperationBatch", "executeOperationBatch", "Actions.invoke", "ActionIds.timeline.frame_export"], "checkpoint_workflow", "timeline_snapshot"),
  "cutagent.action.timeline.layout.free_stack": equivalent("cutagent.action.timeline.layout.free_stack", ["defineOperationBatch", "executeOperationBatch", "Timeline.items.previewMove", "Timeline.items.move"], "checkpoint_workflow", "timeline_snapshot"),
  "cutagent.action.timeline.marker.batch": equivalent("cutagent.action.timeline.marker.batch", ["defineOperationBatch", "executeOperationBatch", "Timeline.markers.previewCreate", "Timeline.markers.create"], "checkpoint_workflow", "timeline_snapshot"),
  "cutagent.action.timeline.overlay_stack.insert": equivalent("cutagent.action.timeline.overlay_stack.insert", ["defineOperationBatch", "executeOperationBatch", "Timeline.edit.previewInsert", "Timeline.edit.insert", "Timeline.items.previewMove", "Timeline.items.move"], "checkpoint_workflow", "timeline_snapshot"),
});

/** One typed durable operation in an ordinary TypeScript batch. @beta */
export interface OperationBatchStep {
  readonly name: string;
  readonly start: (idempotencyKey: IdempotencyKey) => Promise<WorkflowOperationHandle>;
}

/** Immutable serial execution plan. The callbacks remain ordinary TypeScript and are never serialized. @beta */
export interface OperationBatch {
  readonly steps: readonly OperationBatchStep[];
  /** Checkpoint-backed batches fail closed. Continue-on-error is expressed as separate workflows. */
  readonly failurePolicy: "stop";
}

/** Side-effect-free validation result for one typed operation batch. @beta */
export interface OperationBatchValidation {
  readonly valid: true;
  readonly stepCount: number;
  readonly stepNames: readonly string[];
  readonly failurePolicy: OperationBatch["failurePolicy"];
}

/** Truthful durable batch result plus the step outcomes in declared order. @beta */
export interface OperationBatchResult {
  readonly workflow: WorkflowResult;
  readonly steps: readonly WorkflowStepResult[];
  readonly stoppedAfterFailure: boolean;
}

const stepNamePattern = /^[a-z][a-z0-9._/-]{0,127}$/;

/** Define and validate a non-empty typed operation batch without executing it. @beta */
export function defineOperationBatch(input: OperationBatch): OperationBatch {
  if (!Array.isArray(input.steps) || input.steps.length === 0) throw new TypeError("Operation batches require at least one step.");
  if (input.steps.length > 1_000) throw new TypeError("Operation batches may contain at most 1,000 steps.");
  if (input.failurePolicy !== "stop") throw new TypeError("Checkpoint-backed operation batches require failurePolicy stop.");
  const names = new Set<string>();
  const steps = input.steps.map((step) => {
    if (!stepNamePattern.test(step.name)) throw new TypeError("Operation batch step names must be stable lowercase identifiers.");
    if (names.has(step.name)) throw new TypeError(`Operation batch step name is duplicated: ${step.name}`);
    if (typeof step.start !== "function") throw new TypeError(`Operation batch step '${step.name}' requires a start function.`);
    names.add(step.name);
    return Object.freeze({ name: step.name, start: step.start });
  });
  return Object.freeze({ steps: Object.freeze(steps), failurePolicy: input.failurePolicy });
}

/** Validate a batch and return the normalized public execution shape. @beta */
export function validateOperationBatch(input: OperationBatch): OperationBatchValidation {
  const plan = defineOperationBatch(input);
  return Object.freeze({
    valid: true,
    stepCount: plan.steps.length,
    stepNames: Object.freeze(plan.steps.map((step) => step.name)),
    failurePolicy: plan.failurePolicy,
  });
}

/** Execute a typed batch through the existing checkpoint, policy, durable-operation, and verification authority. @beta */
export async function executeOperationBatch(
  workflows: Workflows,
  planInput: OperationBatch,
  options: CheckpointWorkflowOptions,
): Promise<OperationBatchResult> {
  const plan = defineOperationBatch(planInput);
  const workflow = await workflows.checkpointed(options, async (context) => {
    for (const step of plan.steps) {
      const outcome = await context.step(step.name, step.start);
      if (outcome.outcome !== "completed") break;
    }
  });
  return Object.freeze({ workflow, steps: Object.freeze([...workflow.steps]), stoppedAfterFailure: workflow.outcome !== "completed" });
}

/** One exact clip plus its snapshot-bound containing track. @beta */
export interface SelectedTimelineClip {
  readonly clip: ClipSnapshot;
  readonly track: TrackSnapshot;
  readonly timelineItemId: TimelineItemId;
}

/** Exact immutable selection produced from one coherent timeline snapshot. @beta */
export interface TimelineClipSelection {
  readonly projectId: ProjectId;
  readonly timelineId: TimelineId;
  readonly revision: Revision;
  readonly items: readonly SelectedTimelineClip[];
}

/** Normal TypeScript predicate for a snapshot-bound bulk selection. @beta */
export type TimelineClipPredicate = (clip: ClipSnapshot, track: TrackSnapshot) => boolean;

/** Select durable timeline items with ordinary TypeScript conditions and an explicit safety limit. @beta */
export function selectTimelineClips(
  snapshot: TimelineSnapshot,
  predicate: TimelineClipPredicate,
  options: Readonly<{ readonly limit?: number }> = {},
): TimelineClipSelection {
  const limit = options.limit ?? 500;
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > 1_000) throw new TypeError("Timeline clip selection limit must be an integer from 1 to 1,000.");
  if (typeof predicate !== "function") throw new TypeError("Timeline clip selection requires a predicate.");
  const items: SelectedTimelineClip[] = [];
  for (const track of snapshot.tracks) {
    for (const clip of track.clips) {
      if (!predicate(clip, track)) continue;
      if (clip.id === null) throw new TypeError("Bulk mutation selection requires durable timeline item identities.");
      if (items.length === limit) throw new TypeError(`Timeline clip selection exceeds its safety limit of ${limit}.`);
      items.push(Object.freeze({ clip, track, timelineItemId: clip.id }));
    }
  }
  return Object.freeze({
    projectId: snapshot.projectId,
    timelineId: snapshot.timelineId,
    revision: snapshot.revision,
    items: Object.freeze(items),
  });
}

/** Build one durable operation step per selected identity without exposing command strings. @beta */
export function defineSelectedClipBatch<TResult, TAction extends PublicActionId>(
  selection: TimelineClipSelection,
  start: (item: SelectedTimelineClip, idempotencyKey: IdempotencyKey) => Promise<OperationHandle<TResult, TAction>>,
  options: Readonly<{ readonly name: string }>,
): OperationBatch {
  if (selection.items.length === 0) throw new TypeError("Selected clip batches require at least one durable timeline item.");
  if (typeof start !== "function") throw new TypeError("Selected clip batches require an operation factory.");
  const prefix = options.name;
  if (!stepNamePattern.test(prefix)) throw new TypeError("Selected clip batch names must be stable lowercase identifiers.");
  return defineOperationBatch({
    failurePolicy: "stop",
    steps: selection.items.map((item, index) => ({
      name: `${prefix}/${String(index + 1).padStart(4, "0")}`,
      start: (key): Promise<WorkflowOperationHandle> => start(item, IdempotencyKeySchema.parse(key)),
    })),
  });
}

/** One speaker-labelled timeline segment for podcast camera planning. @beta */
export interface PodcastSpeakerSegment {
  readonly speaker: string;
  readonly range: TimelineRecordRange;
}

/** Immutable typed result of transcript-to-angle planning. @beta */
export interface PodcastMulticamPlan {
  readonly switches: readonly MulticamSwitchPoint[];
  readonly speakerAngles: Readonly<Record<string, MulticamAngleSnapshot>>;
  readonly segmentCount: number;
}

/** Convert speaker-labelled record ranges into stable native multicam switch points. @beta */
export function planPodcastMulticamSwitches(
  frameRate: FrameRate,
  segments: readonly PodcastSpeakerSegment[],
  speakerAngles: Readonly<Record<string, MulticamAngleSnapshot>>,
): PodcastMulticamPlan {
  if (segments.length === 0) throw new TypeError("Podcast multicam planning requires at least one speaker segment.");
  let priorEnd = -1;
  const switches: MulticamSwitchPoint[] = [];
  for (const segment of segments) {
    const range = lowerTimelineRecordRange(segment.range, { frameRate });
    if (range.start < priorEnd) throw new TypeError("Podcast speaker segments must be ordered and non-overlapping.");
    const angle = speakerAngles[segment.speaker];
    if (!angle) throw new TypeError(`Podcast speaker '${segment.speaker}' has no multicam angle.`);
    const previous = switches.at(-1);
    if (!previous || previous.angle.id !== angle.id) switches.push(Object.freeze({ at: segment.range.start, angle }));
    priorEnd = range.endExclusive;
  }
  return Object.freeze({ switches: Object.freeze(switches), speakerAngles: Object.freeze({ ...speakerAngles }), segmentCount: segments.length });
}

/** Explicit retained ranges produced by silence analysis outside the mutation boundary. @beta */
export interface SilenceRetentionPlan {
  readonly source: TimelineRecordRange;
  readonly silence: readonly TimelineRecordRange[];
  readonly retained: readonly TimelineRecordRange[];
}

/**
 * Convert proven silent ranges to retained ranges for a declaratively managed
 * destination. Audio analysis stays outside this helper; applying the result
 * still requires `ManagedTimeline.preview()` and checkpoint-backed `apply()`.
 * @beta
 */
export function planSilenceRetention(
  frameRate: FrameRate,
  source: TimelineRecordRange,
  silence: readonly TimelineRecordRange[],
): SilenceRetentionPlan {
  const whole = lowerTimelineRecordRange(source, { frameRate });
  const ordered = silence.map((range) => ({ public: range, wire: lowerTimelineRecordRange(range, { frameRate }) }))
    .sort((left, right) => left.wire.start - right.wire.start || left.wire.endExclusive - right.wire.endExclusive);
  let cursor = whole.start;
  const retained: TimelineRecordRange[] = [];
  for (const entry of ordered) {
    if (entry.wire.start < whole.start || entry.wire.endExclusive > whole.endExclusive) throw new TypeError("Silent ranges must stay inside the source range.");
    if (entry.wire.start < cursor) throw new TypeError("Silent ranges must not overlap.");
    if (cursor < entry.wire.start) retained.push(hydrateTimelineRecordRange({ domain: "timeline_record_range", unit: "frames", start: cursor, endExclusive: entry.wire.start }, { frameRate }));
    cursor = entry.wire.endExclusive;
  }
  if (cursor < whole.endExclusive) retained.push(hydrateTimelineRecordRange({ domain: "timeline_record_range", unit: "frames", start: cursor, endExclusive: whole.endExclusive }, { frameRate }));
  return Object.freeze({ source, silence: Object.freeze(ordered.map((entry) => entry.public)), retained: Object.freeze(retained) });
}
