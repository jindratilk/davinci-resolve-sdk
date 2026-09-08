import { z } from "zod";
import {
  sdkAutoCaptionInputSchema,
  sdkDesignedCaptionInputSchema,
  sdkSubtitleExportInputSchema,
  sdkSubtitleInsertInputSchema,
  sdkSubtitleListInputSchema,
  sdkTranscriptCreateInputSchema,
} from "../generated/sdk-operations.js";
import type { ConnectionControlOptions } from "../core/public-client-types.js";
import { CutAgentSdkError } from "../core/sdk-error.js";
import type { OperationHandle, PublicActionId } from "../protocol/operations.js";
import {
  RevisionSchema,
  SnapshotTimelineItemIdSchema,
  SnapshotTrackIdSchema,
  TimelineIdSchema,
  TrackIndexSchema,
  type IdempotencyKey,
  type ProjectId,
  type Revision,
  type SnapshotTimelineItemId,
  type SnapshotTrackId,
  type TimelineId,
  type TrackIndex,
} from "../value-types/identities.js";
import { hydrateFrameRate, hydrateTimelineRecordRange, lowerFrames, lowerSeconds, lowerTimelineRecordRange } from "../wire/time-adapter.js";
import type { FrameRate, Frames, Seconds, TimelineRecordRange } from "../value-types/time.js";
import { CutAgentValueError } from "../value-types/value-error.js";
import { mutationControl as control } from "./internal-utilities.js";

/** Caption operation controls. @beta */
export interface CaptionControlOptions extends ConnectionControlOptions {
  /** Stable caller identity. Reuse it after an uncertain response; never invent a replacement retry. */
  idempotencyKey: IdempotencyKey;
}

/** One native subtitle item read from the current timeline revision. @beta */
export interface SubtitleItemSnapshot {
  readonly id: SnapshotTimelineItemId;
  readonly trackId: SnapshotTrackId;
  readonly trackIndex: TrackIndex;
  readonly text: string;
  /** Absolute half-open range in the timeline record domain. */
  readonly recordRange: TimelineRecordRange;
}

/** Immutable native subtitle readback. @beta */
export interface SubtitleSnapshot {
  readonly timelineId: TimelineId;
  readonly revision: Revision;
  readonly frameRate: FrameRate;
  readonly items: readonly SubtitleItemSnapshot[];
}

/** Verified native subtitle import result. @beta */
export interface NativeSubtitleImportResult {
  readonly matchedEntries: number;
  readonly createdTrack: boolean;
  readonly verification: { readonly revision: Revision; readonly evidenceCount: number };
}

/** Carrier-neutral serialized subtitle result. @beta */
export interface SubtitleExportResult {
  readonly format: "srt" | "vtt" | "ttml";
  readonly content: string;
  readonly exportedEntries: number;
  readonly sha256: string;
}

/** Verified DaVinci Resolve auto-caption result. @beta */
export interface AutoCaptionResult {
  readonly createdItems: number;
  readonly verification: { readonly revision: Revision; readonly evidenceCount: number };
}

/** Reviewed DaVinci Resolve auto-caption language vocabulary. @beta */
export type AutoCaptionLanguage = "auto" | "danish" | "dutch" | "english" | "french" | "german" | "italian" | "japanese" | "korean" | "mandarin-simplified" | "mandarin-traditional" | "norwegian" | "portuguese" | "russian" | "spanish" | "swedish";

declare const transcriptRelativeRangeBrand: unique symbol;

/** Half-open offset range measured from transcript/timeline content zero. @beta */
export interface TranscriptRelativeRange {
  readonly domain: "transcript_relative_range";
  readonly unit: "frames" | "seconds";
  readonly start: Frames | Seconds;
  readonly endExclusive: Frames | Seconds;
  readonly [transcriptRelativeRangeBrand]: true;
}

const transcriptRelativeRanges = new WeakSet<object>();

/** Construct an explicit transcript-relative offset range. Both boundaries must use one unit. @beta */
export function transcriptRelativeRange(start: Frames | Seconds, endExclusive: Frames | Seconds): TranscriptRelativeRange {
  let unit: "frames" | "seconds";
  let startValue: number;
  let endValue: number;
  try {
    const startFrames = lowerFrames(start as Frames);
    const endFrames = lowerFrames(endExclusive as Frames);
    unit = "frames";
    startValue = startFrames.value;
    endValue = endFrames.value;
  } catch {
    const startSeconds = lowerSeconds(start as Seconds);
    const endSeconds = lowerSeconds(endExclusive as Seconds);
    unit = "seconds";
    startValue = startSeconds.value;
    endValue = endSeconds.value;
  }
  if (startValue < 0 || endValue <= startValue) throw new CutAgentValueError("INVALID_TIME_VALUE", "Transcript-relative range must be non-negative and non-empty.");
  const value = { domain: "transcript_relative_range" as const, unit, start, endExclusive } as unknown as TranscriptRelativeRange;
  transcriptRelativeRanges.add(value as object);
  return Object.freeze(value);
}

function lowerTranscriptRelativeRange(value: TranscriptRelativeRange) {
  if (!transcriptRelativeRanges.has(value as object)) throw new CutAgentValueError("INVALID_TIME_VALUE", "Transcript-relative timing must come from transcriptRelativeRange().");
  if (value.unit === "frames") return { domain: value.domain, unit: value.unit, start: lowerFrames(value.start as Frames).value, endExclusive: lowerFrames(value.endExclusive as Frames).value };
  return { domain: value.domain, unit: value.unit, start: lowerSeconds(value.start as Seconds).value, endExclusive: lowerSeconds(value.endExclusive as Seconds).value };
}

/** Designed-caption cue with an explicit absolute-record or transcript-relative range. @beta */
export interface DesignedCaptionCue {
  readonly text: string;
  readonly timing: TimelineRecordRange | TranscriptRelativeRange;
}

/** A template already present on the CutAgent runtime host. @beta */
export interface CaptionTemplateSource {
  readonly kind: "runtime_path";
  readonly path: string;
}

/** Explicit deterministic caption segmentation policy. @beta */
export interface CaptionSegmentation {
  readonly unit: "words" | "characters";
  readonly target: number;
  readonly preferredMin: number;
  readonly preferredMax: number;
  readonly hardMax: number;
  readonly maxCharactersPerLine: number;
  readonly maxLines: number;
  readonly preferredCps: number;
  readonly hardCps: number;
  readonly minimumDurationSeconds: number;
  readonly pauseThresholdSeconds: number;
}

/** Verified designed Text+ caption insertion result. @beta */
export interface DesignedCaptionResult {
  readonly insertedItems: number;
  readonly trackIndex: TrackIndex;
  readonly verification: { readonly revision: Revision; readonly evidenceCount: number };
}

/** Hosted transcript word timing. @beta */
export interface TranscriptWord {
  readonly text: string;
  readonly startSeconds: number;
  readonly endSeconds: number;
  readonly speaker: string | null;
}

/** Durably acknowledged hosted transcript. @beta */
export interface TranscriptResult {
  readonly provider: string;
  readonly model: string;
  readonly languageCode: string | null;
  readonly text: string;
  readonly words: readonly TranscriptWord[];
  readonly durationSeconds: number | null;
  readonly deliveryAcknowledged: true;
  readonly deliveryRecovered: boolean;
}

/** Hosted transcript request controls. @beta */
export interface TranscriptCreateOptions extends CaptionControlOptions {
  precondition: Revision;
  languageCode?: string;
  diarize?: boolean;
  numSpeakers?: number;
  keyterms?: readonly string[];
  verbatim?: boolean;
  /** Reattach to the retained hosted job after a pending or uncertain response. */
  resumeJobId?: string;
  /** Explicitly starts distinct billed work. Never use this as an automatic retry. */
  newJob?: boolean;
}

/** Hosted transcript operations for one exact timeline identity. @beta */
export interface TimelineTranscript {
  create(options: TranscriptCreateOptions): Promise<OperationHandle<TranscriptResult, "cutagent.action.transcript.create">>;
}

/** Native and designed caption operations for one exact timeline identity. @beta */
export interface TimelineCaptions {
  list(options: { precondition: Revision; track?: number } & ConnectionControlOptions): Promise<SubtitleSnapshot>;
  importSrt(options: { precondition: Revision; srt: string; ensureTrack?: boolean } & CaptionControlOptions): Promise<OperationHandle<NativeSubtitleImportResult, "cutagent.action.timeline.subtitle.insert">>;
  export(options: { precondition: Revision; format: "srt" | "vtt" | "ttml"; track?: number; allTracks?: boolean } & CaptionControlOptions): Promise<OperationHandle<SubtitleExportResult, "cutagent.action.timeline.subtitle.export">>;
  autoCreate(options: { precondition: Revision; language?: AutoCaptionLanguage; preset?: "default" | "teletext" | "netflix"; charsPerLine?: number; lineBreak?: "single" | "double"; gap?: number } & CaptionControlOptions): Promise<OperationHandle<AutoCaptionResult, "cutagent.action.timeline.auto_caption">>;
  insertDesigned(options: { precondition: Revision; template: CaptionTemplateSource; trackIndex: number; cues: readonly DesignedCaptionCue[]; segmentation: CaptionSegmentation } & CaptionControlOptions): Promise<OperationHandle<DesignedCaptionResult, "cutagent.action.text.insert_captions">>;
}

const verificationSchema = z.object({ revision: RevisionSchema, evidenceCount: z.number().int().min(1) }).strict();
const listSchema = z.object({
  timelineId: z.string().regex(/^timeline_/),
  revision: RevisionSchema,
  frameRate: z.object({ numerator: z.number().int().positive(), denominator: z.number().int().positive(), nominalTimebase: z.number().int().positive() }).strict(),
  items: z.array(z.object({
    id: SnapshotTimelineItemIdSchema,
    trackId: SnapshotTrackIdSchema,
    trackIndex: TrackIndexSchema,
    text: z.string(),
    recordRange: z.object({ domain: z.literal("timeline_record_range"), unit: z.literal("frames"), start: z.number().int(), endExclusive: z.number().int() }).strict(),
  }).strict()),
}).strict();
const importSchema = z.object({ matchedEntries: z.number().int().min(1), createdTrack: z.boolean(), verification: verificationSchema }).strict();
const exportSchema = z.object({ format: z.enum(["srt", "vtt", "ttml"]), content: z.string(), exportedEntries: z.number().int().min(0), sha256: z.string().regex(/^[a-f0-9]{64}$/) }).strict();
const autoSchema = z.object({ createdItems: z.number().int().min(1), verification: verificationSchema }).strict();
const designedSchema = z.object({ insertedItems: z.number().int().min(1), trackIndex: TrackIndexSchema, verification: verificationSchema }).strict();
const transcriptSchema = z.object({
  provider: z.string().min(1), model: z.string().min(1), languageCode: z.string().nullable(), text: z.string(),
  words: z.array(z.object({ text: z.string(), startSeconds: z.number().min(0), endSeconds: z.number().min(0), speaker: z.string().nullable() }).strict()),
  durationSeconds: z.number().min(0).nullable(),
  deliveryAcknowledged: z.literal(true), deliveryRecovered: z.boolean(),
}).strict().transform((value): TranscriptResult => value);

/** Carrier-neutral caption operation seam. @internal */
export interface CaptionRuntime {
  startAction<TResult, TAction extends PublicActionId>(generation: number, actionId: TAction, input: unknown, schema: { parse(value: unknown): TResult }, options?: ConnectionControlOptions & { idempotencyKey?: string }): Promise<OperationHandle<TResult, TAction>>;
}

function binding(projectId: ProjectId, timelineId: TimelineId, precondition: Revision) {
  return { projectId, timelineId, precondition: RevisionSchema.parse(precondition) };
}

async function readResult<TResult>(handle: OperationHandle<TResult>, options: ConnectionControlOptions): Promise<TResult> {
  const terminal = await handle.wait(options);
  if (terminal.status !== "succeeded") throw new CutAgentSdkError(terminal.failure);
  return terminal.result;
}

export function createTimelineCaptionDomains(runtime: CaptionRuntime, generation: number, projectId: ProjectId, timelineId: TimelineId) {
  const start = <TResult, TAction extends PublicActionId>(actionId: TAction, input: unknown, schema: { parse(value: unknown): TResult }, options: CaptionControlOptions) =>
    runtime.startAction(generation, actionId, input, schema, control(options));
  const captions: TimelineCaptions = {
    async list(options) {
      const input = sdkSubtitleListInputSchema.parse({ ...binding(projectId, timelineId, options.precondition), ...(options.track !== undefined ? { track: TrackIndexSchema.parse(options.track) } : {}) });
      const handle = await runtime.startAction(generation, "cutagent.action.timeline.subtitle.list", input, listSchema, options);
      const result = await readResult(handle, options);
      const rate = hydrateFrameRate(result.frameRate);
      return Object.freeze({ timelineId: TimelineIdSchema.parse(result.timelineId), revision: result.revision, frameRate: rate, items: Object.freeze(result.items.map((item) => Object.freeze({ ...item, recordRange: hydrateTimelineRecordRange(item.recordRange, { frameRate: rate }) }))) });
    },
    importSrt(options) { return start("cutagent.action.timeline.subtitle.insert", sdkSubtitleInsertInputSchema.parse({ ...binding(projectId, timelineId, options.precondition), srt: options.srt, ensureTrack: options.ensureTrack ?? true }), importSchema, options); },
    export(options) {
      if (options.track !== undefined && options.allTracks) throw new TypeError("Choose either track or allTracks, not both.");
      return start("cutagent.action.timeline.subtitle.export", sdkSubtitleExportInputSchema.parse({ ...binding(projectId, timelineId, options.precondition), format: options.format, ...(options.track !== undefined ? { track: TrackIndexSchema.parse(options.track) } : {}), allTracks: options.allTracks ?? options.track === undefined }), exportSchema, options);
    },
    autoCreate(options) { return start("cutagent.action.timeline.auto_caption", sdkAutoCaptionInputSchema.parse({ ...binding(projectId, timelineId, options.precondition), ...(options.language ? { language: options.language } : {}), ...(options.preset ? { preset: options.preset } : {}), ...(options.charsPerLine !== undefined ? { charsPerLine: options.charsPerLine } : {}), ...(options.lineBreak ? { lineBreak: options.lineBreak } : {}), ...(options.gap !== undefined ? { gap: options.gap } : {}) }), autoSchema, options); },
    insertDesigned(options) { return start("cutagent.action.text.insert_captions", sdkDesignedCaptionInputSchema.parse({ ...binding(projectId, timelineId, options.precondition), template: options.template, trackIndex: TrackIndexSchema.parse(options.trackIndex), cues: options.cues.map((cue) => ({ text: cue.text, timing: cue.timing.domain === "timeline_record_range" ? lowerTimelineRecordRange(cue.timing) : lowerTranscriptRelativeRange(cue.timing) })), segmentation: options.segmentation }), designedSchema, options); },
  };
  const transcript: TimelineTranscript = {
    create(options) {
      if (options.resumeJobId !== undefined && options.newJob === true) throw new TypeError("Choose either resumeJobId or newJob, not both.");
      return start("cutagent.action.transcript.create", sdkTranscriptCreateInputSchema.parse({ ...binding(projectId, timelineId, options.precondition), ...(options.languageCode !== undefined ? { languageCode: options.languageCode } : {}), diarize: options.diarize ?? true, ...(options.numSpeakers !== undefined ? { numSpeakers: options.numSpeakers } : {}), keyterms: [...(options.keyterms ?? [])], verbatim: options.verbatim ?? true, ...(options.resumeJobId !== undefined ? { resumeJobId: options.resumeJobId } : {}), newJob: options.newJob ?? false }), transcriptSchema, options);
    },
  };
  return { captions: Object.freeze(captions), transcript: Object.freeze(transcript) };
}
