import crypto from "node:crypto";
import { z } from "zod";
import {
  sdkMulticamCreateInputSchema,
  sdkMulticamCreateResultSchema,
  sdkMulticamFlattenInputSchema,
  sdkMulticamFlattenResultSchema,
  sdkMulticamSwitchInputSchema,
  sdkMulticamSwitchResultSchema,
} from "../contracts/generated/sdk-operations.js";
import {
  sdkMediaPoolItemIdSchema,
  sdkMulticamAngleIdSchema,
  sdkMulticamIdSchema,
  sdkProjectIdSchema,
  sdkRevisionSchema,
  sdkTimelineIdSchema,
} from "../contracts/generated/sdk-identities.js";
import { projectSdkMediaPoolItemIdentity } from "./sdk-live-inspection-service.js";

const sdkMulticamMatchFrameInputSchema = z.object({
  projectId: sdkProjectIdSchema,
  multicamId: sdkMulticamIdSchema,
  multicamRevision: sdkRevisionSchema,
  angleId: sdkMulticamAngleIdSchema,
  recordFrame: z.number().int().safe().nonnegative(),
}).strict();
const sdkMulticamMatchFrameResultSchema = z.object({
  actionId: z.literal("cutagent.action.multicam.match_frame"),
  projectId: sdkProjectIdSchema,
  multicamId: sdkMulticamIdSchema,
  multicamRevision: sdkRevisionSchema,
  angleId: sdkMulticamAngleIdSchema,
  recordFrame: z.number().int().safe().nonnegative(),
  status: z.enum(["matched", "intentional_gap"]),
  source: z.object({
    mediaPoolItemId: sdkMediaPoolItemIdSchema,
    name: z.string().min(1).max(1024),
    sourceFrame: z.number().int().safe().nonnegative(),
    durationFrames: z.number().int().safe().positive(),
  }).strict().nullable(),
}).strict().superRefine((result, context) => {
  if ((result.status === "matched") !== (result.source !== null)) {
    context.addIssue({ code: "custom", path: ["source"], message: "Matched frame status and source presence must agree" });
  }
});

const ACTIONS = Object.freeze({
  "cutagent.action.multicam.create": { action: "create", inputSchema: sdkMulticamCreateInputSchema, resultSchema: sdkMulticamCreateResultSchema },
  "cutagent.action.multicam.switch": { action: "switch", inputSchema: sdkMulticamSwitchInputSchema, resultSchema: sdkMulticamSwitchResultSchema },
  "cutagent.action.multicam.flatten": { action: "flatten", inputSchema: sdkMulticamFlattenInputSchema, resultSchema: sdkMulticamFlattenResultSchema },
});
const MULTICAM_PREPARE_DEADLINE_MS = 110_000;

const frame = z.number().int().safe().nonnegative();
const positiveFrame = z.number().int().safe().positive();
const targetFields = { projectId: sdkProjectIdSchema, multicamId: sdkMulticamIdSchema, multicamRevision: sdkRevisionSchema };
const target = (fields = {}) => z.object({ ...targetFields, ...fields }).strict();
const angleTarget = (fields = {}) => target({ angleId: sdkMulticamAngleIdSchema, ...fields });
const sourceTarget = (fields = {}) => angleTarget({ sourceMediaPoolItemId: sdkMediaPoolItemIdSchema, ...fields });
const avScope = z.enum(["video", "audio", "both"]);
const replacement = z.object({ angleId: sdkMulticamAngleIdSchema, mediaPoolItemId: sdkMediaPoolItemIdSchema,
  sourceStartFrame: frame, recordStartFrame: frame, durationFrames: positiveFrame }).strict();
const audioReplacement = z.object({ angleId: sdkMulticamAngleIdSchema, mediaPoolItemId: sdkMediaPoolItemIdSchema,
  offsetFrames: z.number().int().safe() }).strict();
const RESIDUAL_ACTIONS = Object.freeze({
  "cutagent.action.multicam.angle.remove": { action: "angle.remove", schema: angleTarget() },
  "cutagent.action.multicam.angle.rename": { action: "angle.rename", schema: angleTarget({ name: z.string().min(1).max(1024), scope: avScope }) },
  "cutagent.action.multicam.angle.set_enabled": { action: "angle.set_enabled", schema: angleTarget({ enabled: z.boolean(), scope: avScope }) },
  "cutagent.action.multicam.source.move": { action: "source.move", schema: sourceTarget({ recordStartFrame: frame, scope: avScope }) },
  "cutagent.action.multicam.source.remove": { action: "source.remove", schema: sourceTarget({ scope: avScope }) },
  "cutagent.action.multicam.source.property_set": { action: "source.property_set", schema: sourceTarget({ recordFrame: frame, mediaType: z.enum(["video", "audio"]), property: z.string().min(1).max(256), value: z.string().min(1).max(4096) }) },
  "cutagent.action.multicam.source.raw_braw_set": { action: "source.raw_braw_set", schema: sourceTarget({ recordFrame: frame, adjustments: z.object({ iso: z.number().int().min(1).max(204800).optional(), exposure: z.number().min(-20).max(20).optional(), whiteBalanceKelvin: z.number().int().min(1000).max(50000).optional(), whiteBalanceTint: z.number().min(-200).max(200).optional() }).strict().refine((settings) => Object.keys(settings).length > 0, { message: "At least one Blackmagic RAW adjustment is required" }) }) },
  "cutagent.action.multicam.reorder_angles": { action: "reorder_angles", schema: target({ angleIds: z.array(sdkMulticamAngleIdSchema).min(2).max(256), includeAudio: z.boolean(), renameTracks: z.boolean(), strict: z.boolean() }).refine((input) => new Set(input.angleIds).size === input.angleIds.length, { message: "Angle identities must be unique" }) },
  "cutagent.action.multicam.set_start_timecode": { action: "set_start_timecode", schema: target({ startTimecode: z.string().regex(/^\d{2,3}:\d{2}:\d{2}[:;]\d{2}$/).max(12) }) },
  "cutagent.action.multicam.strip_embedded_audio": { action: "strip_embedded_audio", schema: target({ allowMissingAudio: z.boolean() }) },
  "cutagent.action.multicam.recover_timing": { action: "recover_timing", schema: target({ sources: z.array(z.object({ mediaPoolItemId: sdkMediaPoolItemIdSchema, sourceStartFrame: frame, durationFrames: positiveFrame }).strict()).min(1).max(256), applyTimeMap: z.boolean(), applySourceStartTimecode: z.boolean(), applyMediaExtents: z.boolean(), verifyReopen: z.boolean() }).refine((input) => input.applyTimeMap || input.applySourceStartTimecode || input.applyMediaExtents, { message: "At least one timing repair must be selected" }) },
  "cutagent.action.multicam.replace.audio": { action: "replace.audio", schema: target({ replacements: z.array(audioReplacement).min(1).max(256), unmappedPolicy: z.enum(["keep", "remove", "error"]), allowShortSource: z.literal(false) }) },
  "cutagent.action.multicam.replace.video": { action: "replace.video", schema: target({ replacements: z.array(replacement).min(1).max(256), unmappedPolicy: z.literal("keep"), allowShortSource: z.boolean() }) },
  "cutagent.action.multicam.convert": { action: "convert", schema: z.object({ projectId: sdkProjectIdSchema, timelineId: sdkTimelineIdSchema, timelineRevision: sdkRevisionSchema, name: z.string().min(1).max(1024) }).strict(), timeline: true },
  "cutagent.action.multicam.seed_timeline": { action: "seed_timeline", schema: target({ timelineId: sdkTimelineIdSchema, timelineRevision: sdkRevisionSchema, atRecordFrame: frame, requireEmpty: z.boolean() }), timeline: true },
  "cutagent.action.multicam.smart_switch": { action: "smart_switch", schema: target({ timelineId: sdkTimelineIdSchema, timelineRevision: sdkRevisionSchema,
    audioSources: z.array(z.object({ mediaPoolItemId: sdkMediaPoolItemIdSchema, angleId: sdkMulticamAngleIdSchema }).strict()).min(1).max(256),
    audioSync: z.enum(["prealigned", "waveform"]), scope: z.enum(["video", "linked"]), minimumEditDurationMs: z.number().int().min(1).max(3_600_000),
    editChangeDelayMs: z.number().int().min(0).max(3_600_000), wideAngleMode: z.enum(["automatic", "manual"]), wideAngleId: sdkMulticamAngleIdSchema.optional(),
    wideAngleFrequency: z.enum(["off", "low", "medium", "high"]), useWideAngleForIntroOutro: z.boolean(), useWideAngleForSilence: z.boolean(),
    useAudioOnlyFastAnalysis: z.boolean(), analysisWindowMs: z.number().int().min(1).max(60_000), activityFloorDb: z.number().min(-160).max(24),
    activityMarginDb: z.number().min(0).max(60), dominanceMarginDb: z.number().min(0).max(60), maxSilenceHoldMs: z.number().int().min(0).max(3_600_000),
    videoSourceOffsets: z.array(z.object({ angleId: sdkMulticamAngleIdSchema, offsetFrames: z.number().int().safe() }).strict()).max(256),
  }).superRefine((input, context) => {
    if (input.wideAngleMode === "manual" && input.wideAngleId === undefined) context.addIssue({ code: "custom", path: ["wideAngleId"], message: "Manual wide-angle mode requires wideAngleId" });
    if (input.wideAngleMode === "automatic" && input.wideAngleId !== undefined) context.addIssue({ code: "custom", path: ["wideAngleId"], message: "Automatic wide-angle mode cannot bind a manual wide angle" });
    if (new Set(input.audioSources.map((source) => source.mediaPoolItemId)).size !== input.audioSources.length) context.addIssue({ code: "custom", path: ["audioSources"], message: "SmartSwitch audio source identities must be unique" });
    if (new Set(input.videoSourceOffsets.map((offset) => offset.angleId)).size !== input.videoSourceOffsets.length) context.addIssue({ code: "custom", path: ["videoSourceOffsets"], message: "SmartSwitch angle offsets must be unique" });
  }), timeline: true },
});
const settingsSchema = z.object({ projectId: sdkProjectIdSchema, mediaPoolRevision: sdkRevisionSchema, name: z.string().min(1).max(1024), timelineName: z.string().min(1).max(1024),
  sources: z.array(z.object({ mediaPoolItemId: sdkMediaPoolItemIdSchema, angleLabel: z.string().min(1).max(256) }).strict()).min(2).max(256),
  syncMode: z.enum(["in", "out", "timecode", "sound", "marker"]), sourceLayout: z.enum(["contiguous", "sparse"]),
  audioMode: z.enum(["all_angles", "reference_audio"]), fullClipExtents: z.boolean(),
}).strict();
const settingsResultSchema = z.object({ actionId: z.literal("cutagent.action.multicam.settings"), projectId: sdkProjectIdSchema, mediaPoolRevision: sdkRevisionSchema,
  effectiveSettings: z.object({ multicamName: z.string().min(1).max(1024), timelineName: z.string().min(1).max(1024), angleOrder: z.array(z.string().min(1).max(256)).min(2).max(256),
    syncMode: z.string().min(1).max(64), sourceLayout: z.enum(["contiguous", "sparse"]), audioMode: z.string().min(1).max(64), fullClipExtents: z.boolean(),
    defaultVideoAngle: z.string().min(1).max(256), defaultAudioAngle: z.string().min(1).max(256),
  }).strict(),
}).strict();
const calibrationSchema = z.object({ projectId: sdkProjectIdSchema, mediaPoolRevision: sdkRevisionSchema,
  videoSources: z.array(z.object({ mediaPoolItemId: sdkMediaPoolItemIdSchema, angleLabel: z.string().min(1).max(256) }).strict()).min(2).max(256),
  audioSources: z.array(z.object({ mediaPoolItemId: sdkMediaPoolItemIdSchema, angleLabel: z.string().min(1).max(256) }).strict()).min(1).max(256),
  audioSync: z.enum(["prealigned", "waveform"]), style: z.enum(["balanced", "reactive", "calm"]), rankedCandidates: z.number().int().min(1).max(50),
}).strict();
const residualMulticamResultSchema = z.object({ actionId: z.string().startsWith("cutagent.action.multicam."), projectId: sdkProjectIdSchema,
  multicamId: sdkMulticamIdSchema, previousRevision: sdkRevisionSchema, multicamRevision: sdkRevisionSchema,
  changedAngleIds: z.array(sdkMulticamAngleIdSchema), affectedMediaPoolItemIds: z.array(sdkMediaPoolItemIdSchema),
}).strict();
const residualTimelineResultSchema = z.object({ actionId: z.string().startsWith("cutagent.action.multicam."), projectId: sdkProjectIdSchema,
  timelineId: sdkTimelineIdSchema, timelineRevision: sdkRevisionSchema, multicamId: sdkMulticamIdSchema,
  multicamRevision: sdkRevisionSchema, changedSegments: z.number().int().positive(),
}).strict();
const calibrationResultSchema = z.object({ actionId: z.literal("cutagent.action.multicam.audio_activity.calibrate"), projectId: sdkProjectIdSchema,
  mediaPoolRevision: sdkRevisionSchema, candidates: z.array(z.object({ rank: z.number().int().min(1).max(50), minimumEditDurationMs: z.number().int().positive(), activityFloorDb: z.number(), activityMarginDb: z.number(), dominanceMarginDb: z.number() }).strict()).min(1).max(50),
}).strict();

const digest = (value) => `sha256:${crypto.createHash("sha256").update(JSON.stringify(value), "utf8").digest("hex")}`;
const evidence = (modality, summary, value) => ({
  evidenceId: `evidence_${crypto.randomUUID()}`, modality, summary,
  capturedAt: new Date().toISOString(), digest: digest(value),
});

function failure(code, message, context, possibleMutation = "none", usage = possibleMutation === "none" ? "released" : "unknown") {
  return {
    kind: code === "STALE_REVISION" ? "stale_revision"
      : code === "TARGET_NOT_FOUND" ? "target_not_found"
        : code === "AMBIGUOUS_TARGET" ? "ambiguous_target"
      : code === "AUTHENTICATION_REQUIRED" ? "authentication_required"
      : code === "INVALID_REQUEST" ? "invalid_request"
        : code === "CAPABILITY_UNAVAILABLE" ? "capability_unavailable"
          : code === "RECOVERY_FAILED" ? "recovery_failed"
            : code === "VERIFICATION_FAILED" ? "verification_failed" : "operation_failed",
    code, message, retrySafe: false, possibleMutation, usage,
    recovery: possibleMutation === "none" ? ["inspect_state"] : ["inspect_state", "manual_recovery"],
    recoveryGuidance: [possibleMutation === "none"
      ? "Inspect current multicam state and create a fresh immutable impact preview."
      : "Inspect the exact multicam and timeline before any further mutation."],
    readbackRequired: possibleMutation !== "none",
    ...(code === "RECOVERY_FAILED" ? { recoveryOutcome: { status: "failed", summary: "Automatic multicam recovery was not proven.", manualRecoveryRequired: true } } : {}),
    requestId: context.requestId, operationId: context.operationId, executionId: context.executionId,
  };
}

function readFailure(code, message, context, usage = "unknown") {
  return {
    ...failure(code, message, context, "none", usage),
    retrySafe: true,
    retrySafetyProof: { basis: "read_only" },
    recovery: ["retry"],
    recoveryGuidance: ["Retry the exact multicam frame read after reconnecting to the CutAgent runtime."],
    readbackRequired: false,
  };
}

function changedMulticamState(before, after) {
  const beforeAngles = new Map(before.angles.map((angle) => [angle.id, angle]));
  const afterAngles = new Map(after.angles.map((angle) => [angle.id, angle]));
  const changedAngleIds = [...new Set([...beforeAngles.keys(), ...afterAngles.keys()])].filter((id) => (
    JSON.stringify(beforeAngles.get(id) ?? null) !== JSON.stringify(afterAngles.get(id) ?? null)
  ));
  const affectedMediaPoolItemIds = [...new Set(changedAngleIds.flatMap((id) => [
    ...(beforeAngles.get(id)?.sources ?? []), ...(afterAngles.get(id)?.sources ?? []),
  ].map((source) => source.mediaPoolItemId)))];
  return { changedAngleIds, affectedMediaPoolItemIds };
}

function verifiedResidualExecution(action, execution, input) {
  if (!execution || typeof execution !== "object" || execution.changed === false) return false;
  if (execution.verification?.status !== "verified") return false;
  if (action === "source.property_set") return String(execution.verification.actual) === input.value;
  if (action === "source.raw_braw_set") return execution.verification.requested_patch_retained === true
    && execution.verification.davinci_resolve_api_reserialized === true;
  if (action === "smart_switch") return execution.smart_switch && Number.isSafeInteger(execution.segments_applied) && execution.segments_applied > 0;
  return true;
}

function exactResidualPostcondition(action, before, after, input) {
  const beforeById = new Map(before.angles.map((angle) => [angle.id, angle]));
  const afterById = new Map(after.angles.map((angle) => [angle.id, angle]));
  if (action === "angle.remove") return !afterById.has(input.angleId)
    && after.angles.length === before.angles.length - 1
    && after.angles.every((angle) => JSON.stringify(angle) === JSON.stringify(beforeById.get(angle.id)));
  if (action === "angle.rename") {
    const angle = afterById.get(input.angleId);
    return Boolean(angle) && (input.scope === "audio" || angle.label === input.name);
  }
  if (action === "angle.set_enabled" && input.scope === "both") return afterById.get(input.angleId)?.enabled === input.enabled;
  if (action === "reorder_angles") return after.angles.map((angle) => angle.id).join("\0") === input.angleIds.join("\0");
  if (action === "replace.video") return input.replacements.every((replacement) =>
    afterById.get(replacement.angleId)?.sources.some((source) => source.mediaPoolItemId === replacement.mediaPoolItemId));
  if (action === "source.remove" && input.scope !== "audio") return !afterById.get(input.angleId)?.sources.some((source) => source.mediaPoolItemId === input.sourceMediaPoolItemId);
  if (new Set(["source.move", "source.property_set", "source.grade_cdl", "source.raw_braw_set"]).has(action)) {
    return afterById.get(input.angleId)?.sources.some((source) => source.mediaPoolItemId === input.sourceMediaPoolItemId) === true;
  }
  return true;
}

function timelineInvariant(snapshot, mutableTrackTypes) {
  return {
    project: snapshot.project, timeline: snapshot.timeline, frameRate: snapshot.frameRate, start: snapshot.start,
    markers: snapshot.markers.map(({ snapshotRevision: _revision, ...marker }) => marker),
    tracks: snapshot.tracks.map((track) => ({
      type: track.type, index: track.index, name: track.name, enabled: track.enabled, locked: track.locked,
      ...(mutableTrackTypes.has(track.type) ? {} : {
        clips: track.clips.map(({ snapshotRevision: _revision, snapshotId: _snapshotId, snapshotTrackId: _snapshotTrackId, ...clip }) => clip),
      }),
    })),
  };
}

function mutableTrackTypes(action, input) {
  const scope = action === "switch" ? input.switches[0]?.scope : input.scope;
  if (scope === "video") return new Set(["video"]);
  if (scope === "audio") return new Set(["audio"]);
  return new Set(["video", "audio"]);
}

function isolatedSwitchProgram(snapshot, input, multicamMediaPoolItemId) {
  if (!multicamMediaPoolItemId) return false;
  const types = mutableTrackTypes("switch", input);
  const expectedStart = snapshot.start.value.value;
  let expectedEnd = null;
  for (const type of types) {
    const populated = snapshot.tracks.filter((track) => track.type === type && track.clips.length > 0);
    if (populated.length !== 1 || populated[0].index !== 1) return false;
    const clips = [...populated[0].clips].sort((left, right) => left.recordRange.start - right.recordRange.start);
    let cursor = expectedStart;
    for (const clip of clips) {
      if (clip.mediaPoolItemId !== multicamMediaPoolItemId
        || clip.recordRange.start !== cursor
        || clip.recordRange.endExclusive <= clip.recordRange.start) return false;
      cursor = clip.recordRange.endExclusive;
    }
    if (expectedEnd !== null && cursor !== expectedEnd) return false;
    expectedEnd = cursor;
  }
  return expectedEnd !== null;
}

function sameSources(snapshot, input) {
  const actual = snapshot.angles.flatMap((angle) => angle.sources.map((source) => `${angle.label}\0${source.mediaPoolItemId}`)).sort();
  const expected = input.sources.map((source) => `${source.angleLabel}\0${source.mediaPoolItemId}`).sort();
  return actual.length === expected.length && actual.every((value, index) => value === expected[index]);
}

function changedCount(action, execution, input) {
  if (action === "switch") {
    const count = execution?.segments_applied ?? execution?.segment_count ?? execution?.switch?.segments_applied;
    return Number.isSafeInteger(count) && count > 0 ? count : input.switches.length;
  }
  const rows = execution?.flattened_wrappers ?? execution?.result?.flattened_wrappers;
  const count = execution?.flattened_wrapper_count ?? (Array.isArray(rows) ? rows.length : null);
  return Number.isSafeInteger(count) && count > 0 ? count : null;
}

function switchWriteMatches(execution, input, prepared) {
  const scope = input.switches[0]?.scope;
  const write = execution?.segment_write;
  if (!write || typeof write !== "object") return false;
  const labels = new Map(prepared.multicam.value.angles.map((angle) => [angle.id, angle.label]));
  const timelineStart = prepared.timeline.start.value.value;
  const expected = input.switches.map((point, index) => ({
    angle: labels.get(point.angleId),
    start: point.atRecordFrame - timelineStart,
    duration: (input.switches[index + 1]?.atRecordFrame ?? prepared.endFrame) - point.atRecordFrame,
  }));
  const matches = (rows) => Array.isArray(rows) && rows.length === expected.length && rows.every((row, index) => (
    row.angle === expected[index].angle
    && Number(row.start) === expected[index].start
    && Number(row.duration) === expected[index].duration
  ));
  return (scope === "audio" || matches(write.video_items))
    && (scope === "video" || matches(write.audio_items));
}

function executionVerified(action, execution, input, prepared) {
  if (!execution || typeof execution !== "object") return false;
  if (action === "create") {
    const verification = execution.verification ?? execution.create?.verification;
    return verification?.status === "verified"
      && (execution.multicam_name ?? execution.create?.multicam_name) === input.name;
  }
  if (action === "switch") {
    const requestedScope = input.switches[0]?.scope;
    return execution.verification?.status === "verified"
      && execution.segments_applied === input.switches.length
      && execution.switch_scope === requestedScope
      && switchWriteMatches(execution, input, prepared);
  }
  return execution.verification?.status === "verified"
    && execution.flattened_wrapper_count > 0
    && execution.scope === input.scope
    && execution.grade_policy === input.gradePolicy;
}

export function createSdkMulticamActions({ liveInspectionService, resolveService }) {
  if (typeof liveInspectionService?.prepareMulticamCreate !== "function"
    || typeof liveInspectionService?.prepareMulticamTimelineMutation !== "function"
    || typeof liveInspectionService?.readMulticamById !== "function"
    || typeof liveInspectionService?.readMulticamByName !== "function"
    || typeof liveInspectionService?.prepareMulticamMatchFrame !== "function") {
    throw new TypeError("Multicam actions require exact private target preparation and public readback.");
  }
  if (typeof resolveService?.executeSdkMulticamMutation !== "function"
    || typeof resolveService?.executeSdkMulticamMatchFrame !== "function") throw new TypeError("Multicam actions require the CutAgent CLI boundary.");


  const mutationActions = Object.fromEntries(Object.entries(ACTIONS).map(([actionId, definition]) => [actionId, {
    inputSchema: definition.inputSchema,
    resultSchema: definition.resultSchema,
    idempotency: "required",
    async execute(context, rawInput) {
      const input = definition.inputSchema.parse(rawInput);
      if (definition.action === "switch" && new Set(input.switches.map((point) => point.scope)).size !== 1) {
        return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("OPERATION_FAILED", "All multicam switch points must use one coherent audio/video scope.", context) };
      }
      let prepared;
      try {
        prepared = definition.action === "create"
          ? await liveInspectionService.prepareMulticamCreate(input, { deadlineAtMs: Date.now() + MULTICAM_PREPARE_DEADLINE_MS })
          : await liveInspectionService.prepareMulticamTimelineMutation(input, { deadlineAtMs: Date.now() + MULTICAM_PREPARE_DEADLINE_MS });
      } catch (error) {
        const reported = error?.code ?? error?.cli_error_code;
        const code = ["STALE_REVISION", "TARGET_NOT_FOUND", "AMBIGUOUS_TARGET", "CAPABILITY_UNAVAILABLE"].includes(reported)
          ? reported : "OPERATION_FAILED";
        return { status: "failed", possibleMutation: "none", usage: "released", failure: failure(code, error?.message ?? "The multicam target could not be prepared.", context) };
      }
      if (definition.action === "switch"
        && !isolatedSwitchProgram(prepared.timeline, input, prepared.multicam?.mediaPoolItemId)) {
        return { status: "failed", possibleMutation: "none", usage: "released",
          failure: failure("CAPABILITY_UNAVAILABLE", "Multicam switching requires an isolated, contiguous exact-target program on track 1; unrelated timeline content is never replaced.", context) };
      }
      let execution = null;
      let executionError = null;
      let executionStarted = false;
      try {
        execution = await resolveService.executeSdkMulticamMutation(definition.action, input, prepared, {
          onSpawnAttempt() {
            context.reportExecutionStarted();
            executionStarted = true;
          },
        });
      } catch (error) { executionError = error; }

      if (executionError && !executionStarted) {
        const reported = executionError?.cli_error_code ?? executionError?.code;
        const code = ["STALE_REVISION", "TARGET_NOT_FOUND", "AMBIGUOUS_TARGET", "CAPABILITY_UNAVAILABLE", "AUTHENTICATION_REQUIRED"].includes(reported)
          ? reported : "OPERATION_FAILED";
        const usage = code === "AUTHENTICATION_REQUIRED" ? "not_reserved" : "released";
        return { status: "failed", possibleMutation: "none", usage,
          failure: failure(code, executionError.message ?? "The multicam mutation failed before execution.", context, "none", usage) };
      }

      if (definition.action === "create") {
        let multicam;
        let timeline = null;
        let readbackError = null;
        try {
          multicam = await liveInspectionService.readMulticamByName(input.projectId, input.name, { deadlineAtMs: Date.now() + 60_000 });
          if (input.createTimeline) {
            const current = await liveInspectionService.read({ operation: "timeline.current", projectId: input.projectId }, { deadlineAtMs: Date.now() + 60_000 });
            const snapshot = await liveInspectionService.read({ operation: "timeline.snapshot", projectId: input.projectId, timelineId: current.id }, { deadlineAtMs: Date.now() + 60_000 });
            timeline = { id: current.id, projectId: input.projectId, revision: snapshot.revision, name: current.name };
          }
        } catch (error) {
          readbackError = error;
        }
        if (readbackError) {
          const reported = executionError?.cli_error_code ?? executionError?.code;
          const missingTarget = ["TARGET_NOT_FOUND", "MULTICAM_NOT_FOUND"].includes(readbackError?.code ?? readbackError?.cli_error_code);
          if (reported === "STALE_REVISION" && missingTarget) {
            return { status: "failed", possibleMutation: "none", usage: "released",
              failure: failure("STALE_REVISION", executionError.message ?? "The Media Pool changed before multicam creation.", context) };
          }
          return {
            status: "verification_failed", possibleMutation: "possible", usage: "unknown",
            failure: failure("VERIFICATION_FAILED", "Multicam creation readback was unavailable after execution.", context, "possible"),
            verification: { outcome: "failed", summary: "Post-create multicam readback was unavailable.", evidence: [evidence("readback", "Post-create readback failed.", { actionId })], protectedStatePreserved: null },
          };
        }
        const ok = executionVerified(definition.action, execution, input, prepared)
          && multicam.projectId === input.projectId && multicam.name === input.name && sameSources(multicam, input)
          && input.createTimeline === (timeline !== null) && (!timeline || timeline.name === input.timelineName);
        const report = {
          outcome: ok ? "passed" : "failed",
          summary: ok ? "Created multicam identity, source bindings, optional timeline, and independent readback matched." : "Created multicam readback did not match the immutable request.",
          evidence: [evidence("readback", "Read back the created native multicam structure.", multicam), ...(timeline ? [evidence("readback", "Read back the created timeline identity and revision.", timeline)] : [])],
          protectedStatePreserved: ok,
        };
        if (ok) {
          return { status: "succeeded", possibleMutation: "confirmed", usage: "consumed", verification: report,
            ...(timeline ? { postTimelineRevision: timeline.revision } : {}),
            result: { actionId, multicam, timeline } };
        }
        return {
          status: "verification_failed", possibleMutation: "possible", usage: "consumed",
          failure: failure("VERIFICATION_FAILED", executionError?.message ?? "Created multicam state did not match the request.", context, "possible", "consumed"),
          verification: report,
          recovery: { state: "manual_required", summary: "Inspect the created multicam before any retry.", evidence: report.evidence, manualRecoveryRequired: true },
        };
      }

      let after;
      let multicam;
      try {
        after = await liveInspectionService.read({ operation: "timeline.snapshot", projectId: input.projectId, timelineId: input.timelineId }, { deadlineAtMs: Date.now() + 60_000 });
        multicam = await liveInspectionService.readMulticamById(input.projectId, input.multicamId, input.multicamRevision, { deadlineAtMs: Date.now() + 60_000 });
      } catch {
        return {
          status: "verification_failed", possibleMutation: "possible", usage: "unknown",
          failure: failure("VERIFICATION_FAILED", "Timeline or multicam readback was unavailable after execution.", context, "possible"),
          verification: { outcome: "failed", summary: "Post-mutation readback was unavailable.", evidence: [evidence("readback", "Post-mutation readback failed.", { actionId })], protectedStatePreserved: null },
        };
      }
      const count = changedCount(definition.action, execution, input);
      const mutableTypes = mutableTrackTypes(definition.action, input);
      const invariantPreserved = digest(timelineInvariant(prepared.timeline, mutableTypes)) === digest(timelineInvariant(after, mutableTypes));
      const changed = after.revision !== input.timelineRevision;
      const ok = executionVerified(definition.action, execution, input, prepared)
        && changed && invariantPreserved && multicam.id === input.multicamId && multicam.revision === input.multicamRevision && count !== null;
      const exactSwitchProgramPreserved = definition.action !== "switch"
        || isolatedSwitchProgram(after, input, prepared.multicam.mediaPoolItemId);
      const verifiedOk = ok && exactSwitchProgramPreserved;
      const report = {
        outcome: verifiedOk ? "passed" : "failed",
        summary: verifiedOk ? "Exact multicam identity, advanced timeline revision, and protected structural state matched." : "Multicam mutation readback did not match the immutable target and expected structural change.",
        evidence: [
          evidence("readback", "Read back the exact multicam revision after execution.", multicam),
          evidence("readback", "Read back the complete timeline after execution.", after),
          evidence("structural", "Compared protected timeline structure before and after execution.", {
            before: timelineInvariant(prepared.timeline, mutableTypes), after: timelineInvariant(after, mutableTypes),
          }),
        ],
        protectedStatePreserved: invariantPreserved && exactSwitchProgramPreserved,
      };
      if (verifiedOk) {
        return { status: "succeeded", possibleMutation: "confirmed", usage: "consumed", verification: report, postTimelineRevision: after.revision,
          result: { actionId, multicam, timeline: { id: after.timeline.id, projectId: after.project.id, revision: after.revision, name: after.timeline.name }, changedSegments: count } };
      }
      if (!changed) {
        const reported = executionError?.cli_error_code;
        const code = ["STALE_REVISION", "CAPABILITY_UNAVAILABLE", "AUTHENTICATION_REQUIRED"].includes(reported) ? reported : "OPERATION_FAILED";
        return { status: "failed", possibleMutation: "none", usage: reported === "AUTHENTICATION_REQUIRED" ? "not_reserved" : "released",
          failure: failure(code, executionError?.message ?? "The multicam mutation made no verified change.", context, "none", reported === "AUTHENTICATION_REQUIRED" ? "not_reserved" : "released") };
      }
      if (executionError?.cli_error_code === "EDIT_MUTATION_RECOVERY_FAILED") {
        return { status: "recovery_failed", possibleMutation: "partial", usage: "consumed", postTimelineRevision: after.revision,
          failure: failure("RECOVERY_FAILED", executionError.message, context, "partial", "consumed"), verification: report,
          recovery: { state: "failed", summary: "Automatic multicam recovery did not restore the inspected state.", evidence: report.evidence, manualRecoveryRequired: true } };
      }
      return { status: "verification_failed", possibleMutation: "possible", usage: "consumed", postTimelineRevision: after.revision,
        failure: failure("VERIFICATION_FAILED", executionError?.message ?? "The multicam mutation produced unexpected state.", context, "possible", "consumed"), verification: report,
        recovery: { state: "manual_required", summary: "Inspect the current multicam timeline before retrying.", evidence: report.evidence, manualRecoveryRequired: true } };
    },
  }]));
  const residualActions = Object.fromEntries(Object.entries(RESIDUAL_ACTIONS).map(([actionId, definition]) => [actionId, {
    inputSchema: definition.schema,
    resultSchema: definition.timeline ? residualTimelineResultSchema : residualMulticamResultSchema,
    idempotency: "required",
    async execute(context, rawInput) {
      const input = definition.schema.parse(rawInput);
      let prepared;
      try {
        prepared = await liveInspectionService.prepareMulticamResidualAction(definition.action, input, { deadlineAtMs: Date.now() + 60_000 });
      } catch (error) {
        const reported = error?.code ?? error?.cli_error_code;
        const code = ["STALE_REVISION", "TARGET_NOT_FOUND", "AMBIGUOUS_TARGET", "CAPABILITY_UNAVAILABLE"].includes(reported) ? reported : "OPERATION_FAILED";
        return { status: "failed", possibleMutation: "none", usage: "released", failure: failure(code, error?.message ?? "The exact multicam action could not be prepared.", context) };
      }
      if (definition.action === "reorder_angles") {
        const current = prepared.multicam.value.angles.map((angle) => angle.id).sort();
        if (JSON.stringify([...input.angleIds].sort()) !== JSON.stringify(current)) {
          return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("INVALID_REQUEST", "Angle reordering must name every exact angle once.", context) };
        }
      }
      if (definition.action === "smart_switch"
        && !isolatedSwitchProgram(prepared.timeline, { switches: [{ scope: input.scope }] }, prepared.multicam?.mediaPoolItemId)) {
        return { status: "failed", possibleMutation: "none", usage: "released",
          failure: failure("CAPABILITY_UNAVAILABLE", "SmartSwitch requires an isolated, contiguous exact-target multicam program on track 1.", context) };
      }
      let executionStarted = false;
      let execution;
      try {
        execution = await resolveService.executeSdkMulticamResidual(definition.action, input, prepared, {
          onSpawnAttempt() { executionStarted = true; context.reportExecutionStarted(); },
        });
      } catch (error) {
        const reported = error?.cli_error_code ?? error?.code;
        const code = ["STALE_REVISION", "TARGET_NOT_FOUND", "AMBIGUOUS_TARGET", "CAPABILITY_UNAVAILABLE", "AUTHENTICATION_REQUIRED", "RECOVERY_FAILED"].includes(reported) ? reported : "OPERATION_FAILED";
        return { status: "failed", possibleMutation: executionStarted ? "possible" : "none", usage: executionStarted ? "unknown" : "released",
          failure: failure(code, error?.message ?? "The exact multicam action failed.", context, executionStarted ? "possible" : "none", executionStarted ? "unknown" : "released") };
      }
      try {
        if (definition.timeline) {
          const after = await liveInspectionService.read({ operation: "timeline.snapshot", projectId: input.projectId, timelineId: input.timelineId }, { deadlineAtMs: Date.now() + 60_000 });
          const multicam = definition.action === "convert"
            ? await liveInspectionService.readMulticamByName(input.projectId, input.name, { deadlineAtMs: Date.now() + 60_000 })
            : await liveInspectionService.readMulticamById(input.projectId, input.multicamId, null, { deadlineAtMs: Date.now() + 60_000 });
          const changed = after.revision !== input.timelineRevision;
          const mutableTypes = definition.action === "convert" ? new Set() : definition.action === "seed_timeline" ? new Set(["video"]) : new Set(["video", ...(input.scope === "linked" ? ["audio"] : [])]);
          const protectedStatePreserved = digest(timelineInvariant(prepared.timeline, mutableTypes)) === digest(timelineInvariant(after, mutableTypes));
          const requestedEffect = definition.action === "convert"
            ? multicam.name === input.name
            : definition.action === "seed_timeline"
              ? after.tracks.some((track) => track.type === "video" && track.clips.some((clip) => clip.mediaPoolItemId === multicam.mediaPoolItemId && clip.recordRange.start === input.atRecordFrame))
              : changed && isolatedSwitchProgram(after, { switches: [{ scope: input.scope }] }, multicam.mediaPoolItemId);
          if (!verifiedResidualExecution(definition.action, execution, input) || !requestedEffect || !protectedStatePreserved) {
            throw Object.assign(new Error("The requested multicam timeline effect or protected-state readback did not match."), { code: "VERIFICATION_FAILED" });
          }
          const changedSegments = definition.action === "smart_switch" ? execution.segments_applied
            : Number.isSafeInteger(execution?.created_item_count) && execution.created_item_count > 0 ? execution.created_item_count : 1;
          const result = residualTimelineResultSchema.parse({ actionId, projectId: input.projectId, timelineId: input.timelineId,
            timelineRevision: after.revision, multicamId: multicam.id, multicamRevision: multicam.revision,
            changedSegments });
          const report = { outcome: "passed", summary: "The requested timeline effect and unaffected timeline structure were independently read back.",
            evidence: [evidence("readback", "Read back the exact timeline and multicam postcondition.", result),
              evidence("structural", "Compared every unaffected timeline track and marker before and after execution.", { before: timelineInvariant(prepared.timeline, mutableTypes), after: timelineInvariant(after, mutableTypes) })],
            protectedStatePreserved };
          return { status: "succeeded", result, possibleMutation: "confirmed", usage: "consumed", postTimelineRevision: after.revision, verification: report };
        }
        const before = prepared.multicam.value;
        const after = await liveInspectionService.readMulticamById(input.projectId, input.multicamId, null, { deadlineAtMs: Date.now() + 60_000 });
        if (after.revision === before.revision) throw Object.assign(new Error("The multicam revision did not advance after the action."), { code: "VERIFICATION_FAILED" });
        if (!verifiedResidualExecution(definition.action, execution, input) || !exactResidualPostcondition(definition.action, before, after, input)) {
          throw Object.assign(new Error("The requested exact multicam postcondition was not proven by execution and structural readback."), { code: "VERIFICATION_FAILED" });
        }
        const observed = changedMulticamState(before, after);
        const expectedChangedAngleIds = input.angleId ? [input.angleId]
          : input.replacements ? input.replacements.map((replacement) => replacement.angleId)
            : input.angleIds ?? before.angles.map((angle) => angle.id);
        const changedAngleIds = observed.changedAngleIds;
        const affectedMediaPoolItemIds = [...new Set([
          ...observed.affectedMediaPoolItemIds,
          ...(input.sourceMediaPoolItemId ? [input.sourceMediaPoolItemId] : []),
          ...(input.replacements ?? []).map((replacement) => replacement.mediaPoolItemId),
          ...(input.sources ?? []).map((source) => source.mediaPoolItemId),
        ])];
        const targetSet = new Set(expectedChangedAngleIds);
        const unrelatedBefore = before.angles.filter((angle) => !targetSet.has(angle.id));
        const unrelatedAfter = after.angles.filter((angle) => !targetSet.has(angle.id));
        const protectedStructurePreserved = expectedChangedAngleIds.length === before.angles.length
          ? true : digest(unrelatedBefore) === digest(unrelatedAfter);
        if (!protectedStructurePreserved) throw Object.assign(new Error("Unrelated multicam angle structure changed."), { code: "VERIFICATION_FAILED" });
        const result = residualMulticamResultSchema.parse({ actionId, projectId: input.projectId, multicamId: after.id,
          previousRevision: before.revision, multicamRevision: after.revision, changedAngleIds, affectedMediaPoolItemIds });
        const report = { outcome: "passed", summary: "The exact multicam revision and complete angle/source structure were read back after mutation.",
          evidence: [evidence("structural", "Compared complete multicam structure before and after execution.", { before, after })], protectedStatePreserved: protectedStructurePreserved };
        return { status: "succeeded", result, possibleMutation: "confirmed", usage: "consumed", verification: report };
      } catch (error) {
        return { status: "verification_failed", possibleMutation: "possible", usage: "consumed",
          failure: failure("VERIFICATION_FAILED", error?.message ?? "The exact multicam readback failed.", context, "possible", "consumed"),
          verification: { outcome: "failed", summary: "Post-mutation multicam verification did not prove the requested state.", evidence: [evidence("readback", "Multicam verification failed.", { actionId })], protectedStatePreserved: null },
          recovery: { state: "manual_required", summary: "Inspect the exact multicam and timeline before retrying.", evidence: [], manualRecoveryRequired: true } };
      }
    },
  }]));
  return {
    ...mutationActions,
    ...residualActions,
    "cutagent.action.multicam.settings": {
      inputSchema: settingsSchema, resultSchema: settingsResultSchema, idempotency: "optional",
      async execute(context, rawInput) {
        const input = settingsSchema.parse(rawInput);
        try {
          const prepared = await liveInspectionService.prepareMulticamResidualAction("settings", input, { deadlineAtMs: Date.now() + 60_000 });
          const raw = await resolveService.executeSdkMulticamResidual("settings", input, prepared, { onSpawnAttempt() { context.reportExecutionStarted(); } });
          const settings = raw?.effective_settings;
          const result = settingsResultSchema.parse({ actionId: "cutagent.action.multicam.settings", projectId: input.projectId, mediaPoolRevision: input.mediaPoolRevision,
            effectiveSettings: { multicamName: settings?.multicam_name, timelineName: settings?.timeline_name, angleOrder: settings?.angle_order,
              syncMode: settings?.sync_mode, sourceLayout: settings?.source_layout, audioMode: settings?.audio_mode,
              fullClipExtents: settings?.full_clip_extents, defaultVideoAngle: settings?.default_video_angle, defaultAudioAngle: settings?.default_audio_angle } });
          return { status: "succeeded", result, possibleMutation: "none", usage: "consumed",
            verification: { outcome: "passed", summary: "Resolved the effective settings from the exact stable source set.",
              evidence: [evidence("readback", "CutAgent CLI resolved the closed multicam job settings.", result)], protectedStatePreserved: true } };
        } catch (error) {
          return { status: "failed", possibleMutation: "none", usage: "unknown",
            failure: readFailure(error?.code ?? error?.cli_error_code ?? "OPERATION_FAILED", error?.message ?? "Multicam settings resolution failed.", context) };
        }
      },
    },
    "cutagent.action.multicam.audio_activity.calibrate": {
      inputSchema: calibrationSchema, resultSchema: calibrationResultSchema, idempotency: "optional",
      async execute(context, rawInput) {
        const input = calibrationSchema.parse(rawInput);
        try {
          const prepared = await liveInspectionService.prepareMulticamResidualAction("audio_activity.calibrate", input, { deadlineAtMs: Date.now() + 60_000 });
          const raw = await resolveService.executeSdkMulticamResidual("audio_activity.calibrate", input, prepared, { onSpawnAttempt() { context.reportExecutionStarted(); } });
          const rows = Array.isArray(raw?.ranked_candidates) ? raw.ranked_candidates : [];
          const candidates = rows.slice(0, input.rankedCandidates).map((row, index) => ({ rank: index + 1,
            minimumEditDurationMs: Number(row.minimum_edit_duration_ms), activityFloorDb: Number(row.activity_floor_db),
            activityMarginDb: Number(row.activity_margin_db), dominanceMarginDb: Number(row.dominance_margin_db) }));
          const result = calibrationResultSchema.parse({ actionId: "cutagent.action.multicam.audio_activity.calibrate", projectId: input.projectId, mediaPoolRevision: input.mediaPoolRevision, candidates });
          return { status: "succeeded", result, possibleMutation: "none", usage: "consumed", verification: { outcome: "passed", summary: "Audio activity candidates were computed from the exact selected media revisions.", evidence: [evidence("audition", "Calibrated exact selected audio sources.", result)], protectedStatePreserved: true } };
        } catch (error) {
          const reported = error?.cli_error_code ?? error?.code;
          const code = ["STALE_REVISION", "TARGET_NOT_FOUND", "CAPABILITY_UNAVAILABLE", "VERIFICATION_FAILED"].includes(reported) ? reported : "OPERATION_FAILED";
          return { status: "failed", possibleMutation: "none", usage: "released", failure: readFailure(code, error?.message ?? "Multicam audio calibration failed.", context, "released") };
        }
      },
    },
    "cutagent.action.multicam.match_frame": {
      inputSchema: sdkMulticamMatchFrameInputSchema,
      resultSchema: sdkMulticamMatchFrameResultSchema,
      idempotency: "optional",
      async reconcile(context) {
        const usage = context?.snapshot?.usage ?? "unknown";
        return {
          status: "failed", possibleMutation: "none", usage,
          failure: readFailure("OPERATION_FAILED", "The multicam frame read was interrupted before its result was retained.", context, usage),
        };
      },
      async execute(context, rawInput) {
        const input = sdkMulticamMatchFrameInputSchema.parse(rawInput);
        let prepared;
        try {
          prepared = await liveInspectionService.prepareMulticamMatchFrame(input, { deadlineAtMs: Date.now() + 60_000 });
        } catch (error) {
          const reported = error?.code ?? error?.cli_error_code;
          const code = ["STALE_REVISION", "TARGET_NOT_FOUND", "AMBIGUOUS_TARGET", "CAPABILITY_UNAVAILABLE"].includes(reported)
            ? reported : "OPERATION_FAILED";
          return { status: "failed", possibleMutation: "none", usage: "released", failure: readFailure(code, error?.message ?? "The multicam frame target could not be prepared.", context, "released") };
        }
        try {
          const execution = await resolveService.executeSdkMulticamMatchFrame(input, prepared, {
            onSpawnAttempt() { context.reportExecutionStarted(); },
          });
          const verifiedMulticam = await liveInspectionService.readMulticamById(
            input.projectId,
            input.multicamId,
            input.multicamRevision,
            { deadlineAtMs: Date.now() + 60_000 },
          );
          const selectedAngle = verifiedMulticam.angles[prepared.angleNumber - 1];
          const status = execution?.status;
          if (verifiedMulticam.revision !== prepared.multicam.value.revision
            || !selectedAngle || selectedAngle.id !== input.angleId
            || execution?.multicam_media_id !== prepared.multicam.nativeId
            || execution?.multicam_name !== prepared.multicam.name
            || execution?.angle_number !== prepared.angleNumber
            || execution?.record_frame !== input.recordFrame
            || execution?.media_type !== "video"
            || !["matched", "intentional_gap"].includes(status)) {
            throw Object.assign(new Error("CutAgent CLI returned contradictory multicam match evidence."), { code: "VERIFICATION_FAILED" });
          }
          let source = null;
          if (status === "matched") {
            const rawSource = execution?.source;
            const mediaPoolItemId = projectSdkMediaPoolItemIdentity(input.projectId, rawSource?.media_id);
            const publicSource = selectedAngle.sources.find((candidate) => candidate.mediaPoolItemId === mediaPoolItemId);
            if (!publicSource || publicSource.name !== rawSource?.clip_name
              || !Number.isSafeInteger(rawSource?.source_frame) || rawSource.source_frame < 0
              || !Number.isSafeInteger(rawSource?.duration_frames) || rawSource.duration_frames < 1) {
              throw Object.assign(new Error("CutAgent CLI did not prove one public multicam source frame."), { code: "VERIFICATION_FAILED" });
            }
            source = { mediaPoolItemId, name: publicSource.name, sourceFrame: rawSource.source_frame, durationFrames: rawSource.duration_frames };
          } else if (execution?.source !== null) {
            throw Object.assign(new Error("An intentional multicam gap unexpectedly contained a source."), { code: "VERIFICATION_FAILED" });
          }
          const result = sdkMulticamMatchFrameResultSchema.parse({
            actionId: "cutagent.action.multicam.match_frame",
            projectId: input.projectId, multicamId: input.multicamId, multicamRevision: input.multicamRevision,
            angleId: input.angleId, recordFrame: input.recordFrame, status, source,
          });
          return {
            status: "succeeded", result, possibleMutation: "none", usage: "consumed",
            verification: { outcome: "passed", summary: "The exact multicam source-frame relationship was structurally read back.", evidence: [evidence("readback", "Matched one stable multicam angle and source frame.", result)], protectedStatePreserved: true },
          };
        } catch (error) {
          const reported = error?.cli_error_code ?? error?.code;
          const code = ["STALE_REVISION", "TARGET_NOT_FOUND", "AMBIGUOUS_TARGET", "CAPABILITY_UNAVAILABLE", "VERIFICATION_FAILED"].includes(reported)
            ? reported : "OPERATION_FAILED";
          return { status: "failed", possibleMutation: "none", usage: "unknown", failure: readFailure(code, error?.message ?? "The multicam frame read failed.", context) };
        }
      },
    },
  };
}
