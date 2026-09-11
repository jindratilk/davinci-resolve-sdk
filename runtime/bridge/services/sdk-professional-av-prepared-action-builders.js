import Ajv2020 from "ajv/dist/2020.js";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import {isDeepStrictEqual} from "node:util";
import {z} from "zod";

import {SDK_RESIDUAL_AV_PREPARED_INPUTS} from "../contracts/sdk-residual-av-inputs.generated.js";
import {
  sdkBulkClipStateInputSchema,
  sdkBulkClipStateResultSchema,
  sdkBulkClipPropertyInputSchema,
  sdkClipFreezeInputSchema,
  sdkClipKeyframeAddInputSchema,
  sdkClipKeyframeAddResultSchema,
  sdkClipKeyframeDeleteInputSchema,
  sdkClipKeyframeDeleteResultSchema,
  sdkClipKeyframeGetInputSchema,
  sdkClipKeyframeGetResultSchema,
  sdkClipKeyframeSetInterpolationInputSchema,
  sdkClipKeyframeSetInterpolationResultSchema,
  sdkClipReverseInputSchema,
  sdkClipSpeedInputSchema,
  sdkClipSpeedRampInputSchema,
  sdkClipTransformInputSchema,
  sdkExactRetimeCurveSchema,
} from "../contracts/generated/sdk-operations.js";
import {CUTAGENT_PREPARED_ACTION_ACTION_METADATA} from "../contracts/sdk-prepared-action-metadata.generated.js";
import {createSdkPreparedActionBuilderContribution} from "./sdk-prepared-action-carrier.js";

const ajv = new Ajv2020({allErrors: true, strict: true, strictRequired: false});
const PROFESSIONAL_INPUTS = Object.freeze({
  "cutagent.action.bulk.disable": sdkBulkClipStateInputSchema,
  "cutagent.action.bulk.enable": sdkBulkClipStateInputSchema,
  "cutagent.action.bulk.property_set": sdkBulkClipPropertyInputSchema,
  "cutagent.action.edit.fx.add": z.object({
    projectId: z.string().min(1), timelineId: z.string().min(1), timelineRevision: z.string().min(1),
    target: z.object({
      snapshotId: z.string().min(1), id: z.string().min(1), trackType: z.literal("video"),
      trackIndex: z.number().int().min(1).max(4096), recordStartFrame: z.number().int().nonnegative(),
      recordEndFrame: z.number().int().positive(), name: z.string().min(1).max(4096),
      mediaPoolItemId: z.string().min(1).nullable(), linkedItemIds: z.array(z.string().min(1)).max(64),
    }).strict(),
    effect: z.discriminatedUnion("effectId", [
      z.object({effectId: z.literal("fusion.soft_glow"), parameters: z.object({Gain: z.number().min(0).max(5).optional(), Blend: z.number().min(0).max(1).optional()}).strict().optional()}).strict(),
      z.object({effectId: z.literal("fusion.blur"), parameters: z.object({XBlurSize: z.number().min(0).max(100).optional(), YBlurSize: z.number().min(0).max(100).optional(), Blend: z.number().min(0).max(1).optional()}).strict().optional()}).strict(),
      z.object({effectId: z.literal("fusion.unsharp_mask"), parameters: z.object({Gain: z.number().min(0).max(5).optional(), Blend: z.number().min(0).max(1).optional()}).strict().optional()}).strict(),
      z.object({effectId: z.literal("fusion.color_corrector"), parameters: z.object({MasterRGBGain: z.number().min(0).max(5).optional(), MasterRGBGamma: z.number().min(0.01).max(5).optional(), Saturation1: z.number().min(0).max(5).optional(), Blend: z.number().min(0).max(1).optional()}).strict().optional()}).strict(),
      z.object({effectId: z.literal("fusion.transform"), parameters: z.object({Size: z.number().min(0.01).max(10).optional(), Angle: z.number().min(-360).max(360).optional(), Aspect: z.number().min(-5).max(5).optional(), Blend: z.number().min(0).max(1).optional()}).strict().optional()}).strict(),
    ]),
  }).strict(),
  "cutagent.action.clip.keyframe.add": sdkClipKeyframeAddInputSchema,
  "cutagent.action.clip.keyframe.delete": sdkClipKeyframeDeleteInputSchema,
  "cutagent.action.clip.keyframe.get": sdkClipKeyframeGetInputSchema,
  "cutagent.action.clip.keyframe.set_interpolation": sdkClipKeyframeSetInterpolationInputSchema,
  "cutagent.action.clip.transform": sdkClipTransformInputSchema,
  "cutagent.action.clip.speed": sdkClipSpeedInputSchema,
  "cutagent.action.clip.speed_ramp": sdkClipSpeedRampInputSchema,
  "cutagent.action.clip.freeze": sdkClipFreezeInputSchema,
  "cutagent.action.clip.reverse": sdkClipReverseInputSchema,
  "cutagent.action.system.keyframe_mode.set": z.object({mode: z.enum(["all", "color", "sizing"])}).strict(),
});
const KEYFRAME_RESULT_SCHEMAS = Object.freeze({
  "cutagent.action.clip.keyframe.add": sdkClipKeyframeAddResultSchema,
  "cutagent.action.clip.keyframe.delete": sdkClipKeyframeDeleteResultSchema,
  "cutagent.action.clip.keyframe.get": sdkClipKeyframeGetResultSchema,
  "cutagent.action.clip.keyframe.set_interpolation": sdkClipKeyframeSetInterpolationResultSchema,
});
const RETIME_ACTIONS = new Set([
  "cutagent.action.clip.speed",
  "cutagent.action.clip.speed_ramp",
  "cutagent.action.clip.freeze",
  "cutagent.action.clip.reverse",
]);
const publicId = (prefix) => z.string().regex(new RegExp(`^${prefix}[A-Za-z0-9][A-Za-z0-9._~-]*$`)).max(256);
const publicFrameRange = (domain) => z.object({
  domain: z.literal(domain), unit: z.literal("frames"),
  start: z.number().int().safe(), endExclusive: z.number().int().safe(),
}).strict();
const publicRetimeTarget = z.object({
  projectId: publicId("project_"), timelineId: publicId("timeline_"),
  timelineItemId: publicId("timeline_item_"),
  snapshotTimelineItemId: publicId("snapshot_timeline_item_"),
  name: z.string().min(1).max(4096),
  track: z.object({type: z.enum(["video", "audio"]), index: z.number().int().min(1).safe()}).strict(),
  recordRange: publicFrameRange("timeline_record_range"),
  sourceRange: publicFrameRange("source_range"),
  linkedTimelineItemIds: z.array(publicId("timeline_item_")).max(64),
  protectedNeighbors: z.array(z.object({
    timelineItemId: publicId("timeline_item_"),
    relationship: z.enum(["previous", "next", "overlapping"]),
    recordRange: publicFrameRange("timeline_record_range"),
  }).strict()).max(16),
}).strict();
const publicTimeMap = z.object({
  recordRange: publicFrameRange("timeline_record_range"),
  sourceRange: publicFrameRange("source_range"),
  reversed: z.boolean(), frozen: z.boolean(),
  points: z.array(z.object({
    recordFrame: z.number().int().safe(), sourceFrame: z.number().int().safe(),
    speed: z.number().finite().min(-1e15).max(1e15),
    interpolation: z.enum(["linear", "bezier", "hold"]),
  }).strict()).max(4096),
  curves: z.array(sdkExactRetimeCurveSchema).min(1).max(514).optional(),
}).strict();
export function publicRetimeResultSchema(actionId) {
  return z.object({
    actionId: z.literal(actionId),
    payload: z.object({
      status: z.literal("completed"), changed: z.literal(true),
      revision: z.object({
        relationship: z.literal("advanced"),
        before: publicId("revision_"), after: publicId("revision_"),
      }).strict(),
      targets: z.array(publicRetimeTarget).min(1).max(3),
      change: z.object({kind: z.literal("time_map"), before: publicTimeMap, after: publicTimeMap}).strict(),
      verification: z.object({
        outcome: z.literal("passed"),
        evidence: z.array(z.object({
          kind: z.enum(["structural_readback", "rendered_frame", "visual_review", "audition", "artifact_readback", "manual_review"]),
          summary: z.string().min(1).max(500), artifactId: publicId("artifact_").nullable(),
        }).strict()).min(1).max(32),
        protectedState: z.literal("preserved"),
      }).strict(),
      recovery: z.object({
        state: z.literal("not_needed"),
        retry: z.enum(["safe", "same_idempotency_key_required", "inspect_state_first", "manual_only"]),
        guidance: z.string().min(1).max(500),
      }).strict(),
    }).strict(),
  }).strict();
}
const RETIME_RESULT_SCHEMAS = Object.freeze(Object.fromEntries(
  [...RETIME_ACTIONS].map((actionId) => [actionId, publicRetimeResultSchema(actionId)]),
));

function publicKeyframeInterpolation(value) {
  const normalized = String(value ?? "").trim().toLowerCase().replaceAll("-", "_");
  if (!["linear", "bezier", "ease_in", "ease_out"].includes(normalized)) {
    throw new TypeError("Prepared keyframe result returned an unsupported interpolation.");
  }
  return normalized;
}

function projectKeyframeResult(actionId, raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw) || raw.actionId !== actionId
    || !Array.isArray(raw.keyframes)) {
    throw new TypeError("Prepared keyframe result omitted its exact native readback.");
  }
  return KEYFRAME_RESULT_SCHEMAS[actionId].parse({
    actionId,
    targetId: raw.targetId,
    timelineRevision: raw.timelineRevision,
    protectedStatePreserved: raw.protectedStatePreserved,
    property: raw.property,
    ...(raw.property === "RetimeFrame" ? {curve: raw.curve} : {}),
    keyframes: raw.keyframes.map((row) => {
      if (!row || typeof row !== "object" || Array.isArray(row)) {
        throw new TypeError("Prepared keyframe result contained an invalid readback row.");
      }
      return {
        property: row.property ?? raw.property,
        recordFrame: row.recordFrame ?? row.frame,
        value: row.value,
        interpolation: publicKeyframeInterpolation(row.interpolation),
      };
    }),
  });
}

function projectRetimeResult(actionId, raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)
    || raw.actionId !== actionId || !raw.publicResult
    || raw.publicResult.actionId !== actionId) {
    throw new TypeError("Prepared retime result omitted its semantic public projection.");
  }
  return structuredClone(raw.publicResult);
}

const RESIDUAL_EDIT_ACTIONS = new Set([
  "cutagent.action.edit.auto_subtitle", "cutagent.action.edit.camera_pip",
  "cutagent.action.edit.delete_through_edit", "cutagent.action.edit.from_edl",
  "cutagent.action.edit.remove", "cutagent.action.edit.remove_range",
  "cutagent.action.edit.ripple_delete", "cutagent.action.edit.ripple_delete_selected",
  "cutagent.action.edit.scene_detect", "cutagent.action.edit.slide_selected",
  "cutagent.action.edit.slip_selected", "cutagent.action.edit.social_crop",
  "cutagent.action.edit.split", "cutagent.action.edit.transition.add",
  "cutagent.action.edit.transition.batch",
]);

function minimumBinding(authority) {
  if (["managed_artifact_revision", "managed_file"].includes(authority)) return "account/project-library";
  if (["exact_project_revision", "managed_artifact_and_optional_exact_media_revision", "exact_media_revision_or_managed_file"].includes(authority)) return "project";
  return "project+timeline";
}

function jsonInputSchema(actionId, schema) {
  const validate = ajv.compile(schema);
  return Object.freeze({
    parse(value) {
      if (!validate(value)) {
        throw Object.assign(new TypeError(`Prepared action input violated its authoritative schema: ${actionId}`), {
          validationErrors: structuredClone(validate.errors ?? []),
        });
      }
      return structuredClone(value);
    },
  });
}

function sha256(value) { return crypto.createHash("sha256").update(value).digest("hex"); }
function timelineItems(snapshot) {
  return (snapshot?.tracks ?? []).flatMap((track) => (track.clips ?? []).map((clip) => ({track, clip})));
}
function transitionBatchEntries(input) {
  if (!input || typeof input !== "object" || Array.isArray(input)) return [];
  return Array.isArray(input.transitions) ? input.transitions : [input.transitions].filter(Boolean);
}
function exactPublicTimelineTargets(input) {
  return [
    input.target, input.outgoing, input.incoming, input.leftNeighbor, input.rightNeighbor,
    ...(input.targets ?? []), ...(input.sourceTargets ?? []), ...(input.sourceAudioTargets ?? []),
    ...(input.linkedAudioTargets ?? []), ...(input.items ?? []).map((item) => item.target),
    ...transitionBatchEntries(input).flatMap((transition) => [
      transition.outgoing, transition.incoming, ...(transition.linkedAudioTargets ?? []),
    ]),
  ].filter((value) => value && typeof value.id === "string");
}
function assertPublicTimelineTarget(target, track, clip, actionId) {
  const curveAuthority = target.sourceOriginFrame !== undefined;
  if (curveAuthority && (actionId !== "cutagent.action.clip.speed_ramp" || !clip.retimeSource)) {
    throw new Error("Only speed-curve authoring accepts exact retime source authority.");
  }
  const sourceBounds = curveAuthority ? clip.retimeSource.availableRange : clip.sourceRange;
  const retimeTarget = target.recordRange !== undefined || target.sourceRange !== undefined;
  const expected = retimeTarget ? {
    snapshotId: clip.snapshotId, id: clip.id, trackType: track.type, trackIndex: track.index,
    recordRange: {
      domain: "timeline_record_range", unit: "frames",
      start: clip.recordRange?.start, endExclusive: clip.recordRange?.endExclusive,
    },
    sourceRange: {
      domain: "source_range", unit: "frames",
      start: sourceBounds?.start, endExclusive: sourceBounds?.endExclusive,
    },
    ...(curveAuthority ? {sourceOriginFrame: clip.retimeSource.originFrame} : {}),
    name: clip.name, mediaPoolItemId: clip.mediaPoolItemId ?? null,
    linkedItemIds: clip.linkedItemIds ?? [],
  } : {
    snapshotId: clip.snapshotId, id: clip.id, trackType: track.type, trackIndex: track.index,
    recordStartFrame: clip.recordRange?.start, recordEndFrame: clip.recordRange?.endExclusive,
    name: clip.name, mediaPoolItemId: clip.mediaPoolItemId ?? null,
    linkedItemIds: clip.linkedItemIds ?? [],
  };
  if (!isDeepStrictEqual(target, expected)) {
    throw new Error("Prepared professional target fields are stale or incomplete.");
  }
}
async function captureMediaIdentity(liveInspectionService, projectId, media) {
  let offset = 0; let revision = null; const matches = []; const sameName = [];
  do {
    const inspected = await liveInspectionService.readWithMutationGuard({operation: "mediaPool.page", projectId, offset, pageSize: 32, expectedRevision: revision, search: null});
    revision ??= inspected.value.revision;
    if (inspected.value.revision !== revision) throw new Error("Media Pool revision changed during Edit preparation.");
    matches.push(...inspected.value.assets.filter((asset) => asset.id === media.id && asset.name === media.name));
    sameName.push(...inspected.value.assets.filter((asset) => asset.name === media.name));
    offset = inspected.value.nextOffset;
  } while (offset !== null);
  if (matches.length !== 1 || sameName.length !== 1 || sameName[0].id !== media.id) {
    throw new Error("Prepared Edit media identity is missing or ambiguous for the private name selector.");
  }
  return revision;
}

function sameIds(left, right) {
  return left.length === right.length && new Set(left).size === left.length
    && left.every((id) => right.includes(id));
}

function assertResidualEditHandlerScope(actionId, input, snapshot, rows) {
  const allRows = timelineItems(snapshot);
  const publicIds = rows.map(({clip}) => clip.id);
  const byId = new Map(allRows.map((row) => [row.clip.id, row]));
  if (actionId === "cutagent.action.edit.auto_subtitle") {
    const completeAudioIds = allRows.filter(({track}) => track.type === "audio").map(({clip}) => clip.id);
    if (!sameIds(publicIds, completeAudioIds)) {
      throw new Error("Prepared auto-subtitle targets must be the complete live audio scope.");
    }
  }
  if (actionId === "cutagent.action.edit.scene_detect") {
    const completeVideoIds = allRows.filter(({track}) => track.type === "video").map(({clip}) => clip.id);
    if (!sameIds(publicIds, completeVideoIds)) {
      throw new Error("Prepared scene-detect targets must be the complete live video scope.");
    }
  }
  if (actionId === "cutagent.action.edit.social_crop") {
    const completeVideoIds = allRows.filter(({track}) => track.type === "video").map(({clip}) => clip.id);
    if (publicIds.length > 1 && !sameIds(publicIds, completeVideoIds)) {
      throw new Error("Prepared multi-clip social crop targets must be the complete live video scope.");
    }
    if (publicIds.length === 1) {
      const name = rows[0].clip.name;
      if (allRows.filter(({track, clip}) => track.type === "video" && clip.name === name).length !== 1) {
        throw new Error("Prepared social-crop target name is ambiguous for private execution.");
      }
    }
  }
  if (actionId === "cutagent.action.edit.remove") {
    const {track, clip} = rows[0] ?? {};
    if (!clip || track.type !== input.target.trackType || track.index !== input.target.trackIndex
      || !(clip.recordRange.start <= input.recordFrame && input.recordFrame < clip.recordRange.endExclusive)) {
      throw new Error("Prepared remove frame does not resolve to its exact target.");
    }
  }
  if (actionId === "cutagent.action.edit.remove_range") {
    const first = rows[0];
    if (!first || rows.some(({track}) => track.type !== first.track.type || track.index !== first.track.index)) {
      throw new Error("Prepared remove-range targets must share one exact track.");
    }
    const completeRangeIds = allRows.filter(({track, clip}) => track.type === first.track.type
      && track.index === first.track.index
      && clip.recordRange.start < input.rangeEndFrameExclusive
      && clip.recordRange.endExclusive > input.rangeStartFrame).map(({clip}) => clip.id);
    if (!sameIds(publicIds, completeRangeIds)) {
      throw new Error("Prepared remove-range targets must cover every live item intersecting the native range.");
    }
  }
  if (actionId === "cutagent.action.edit.ripple_delete") {
    const completeRangeIds = allRows.filter(({clip}) => clip.recordRange.start < input.rangeEndFrameExclusive
      && clip.recordRange.endExclusive > input.rangeStartFrame).map(({clip}) => clip.id);
    if (!sameIds(publicIds, completeRangeIds)) {
      throw new Error("Prepared ripple-delete targets must cover every live item intersecting the native range.");
    }
  }
  if ([
    "cutagent.action.edit.ripple_delete_selected", "cutagent.action.edit.slide_selected",
    "cutagent.action.edit.slip_selected",
  ].includes(actionId)) {
    const target = byId.get(input.target.id);
    if (!target || !(target.clip.recordRange.start <= input.recordFrame
      && input.recordFrame < target.clip.recordRange.endExclusive)) {
      throw new Error("Prepared selected Edit frame does not resolve to its exact target.");
    }
  }
  if (actionId === "cutagent.action.edit.split") {
    if (rows.some(({clip}) => !(clip.recordRange.start < input.recordFrame
      && input.recordFrame < clip.recordRange.endExclusive))) {
      throw new Error("Prepared split frame must be internal to every exact target.");
    }
  }
  if (["cutagent.action.edit.delete_through_edit", "cutagent.action.edit.transition.add"].includes(actionId)) {
    const outgoing = rows.find(({clip}) => clip.id === input.outgoing.id);
    const incoming = rows.find(({clip}) => clip.id === input.incoming.id);
    if (!outgoing || !incoming || outgoing.track.type !== incoming.track.type
      || outgoing.track.index !== incoming.track.index
      || outgoing.clip.recordRange.endExclusive !== incoming.clip.recordRange.start
      || input.editFrame !== incoming.clip.recordRange.start) {
      throw new Error("Prepared edit-point neighbors do not describe one exact live edit.");
    }
  }
  if (actionId === "cutagent.action.edit.transition.batch") {
    for (const transition of transitionBatchEntries(input)) {
      const outgoing = rows.find(({clip}) => clip.id === transition.outgoing.id);
      const incoming = rows.find(({clip}) => clip.id === transition.incoming.id);
      if (!outgoing || !incoming || outgoing.track.type !== "video"
        || incoming.track.type !== "video" || outgoing.track.index !== incoming.track.index
        || outgoing.clip.recordRange.endExclusive !== incoming.clip.recordRange.start
        || transition.editFrame !== incoming.clip.recordRange.start) {
        throw new Error("Prepared transition batch contains a stale or non-video edit seam.");
      }
      const declared = transition.linkedAudioTargets.map((item) => item.id);
      const expected = [...new Set([
        ...(outgoing.clip.linkedItemIds ?? []), ...(incoming.clip.linkedItemIds ?? []),
      ])].filter((id) => byId.get(id)?.track.type === "audio");
      if (!sameIds(declared, expected)) {
        throw new Error("Prepared transition batch linked-audio custody is incomplete.");
      }
    }
  }
  if (actionId === "cutagent.action.edit.ripple_delete") {
    if (!Number.isFinite(snapshot.frameRate) || snapshot.frameRate <= 0
      || input.timelineFrameRate !== snapshot.frameRate) {
      throw new Error("Prepared ripple-delete frame rate is stale or unavailable.");
    }
  }
  if (actionId === "cutagent.action.edit.ripple_delete_selected") {
    const expectedType = input.scope === "audio" ? "audio" : "video";
    if (input.target.trackType !== expectedType) {
      throw new Error("Prepared ripple-delete target type does not match its native scope.");
    }
  }
  if (actionId === "cutagent.action.edit.transition.add") {
    const expectedType = input.scope === "audio" ? "audio" : "video";
    if (input.outgoing.trackType !== expectedType || input.incoming.trackType !== expectedType) {
      throw new Error("Prepared transition edit-point types do not match its native scope.");
    }
    if (input.scope === "linked") {
      const linked = input.linkedAudioTargets.map((item) => byId.get(item.id));
      const outgoingAudio = linked.filter((row) => row && input.outgoing.linkedItemIds.includes(row.clip.id));
      const incomingAudio = linked.filter((row) => row && input.incoming.linkedItemIds.includes(row.clip.id));
      if (linked.length !== 2 || linked.some((row) => !row)
        || outgoingAudio.length !== 1 || incomingAudio.length !== 1
        || outgoingAudio[0].track.type !== "audio" || incomingAudio[0].track.type !== "audio"
        || outgoingAudio[0].track.index !== incomingAudio[0].track.index
        || outgoingAudio[0].clip.recordRange.endExclusive !== incomingAudio[0].clip.recordRange.start
        || incomingAudio[0].clip.recordRange.start !== input.editFrame) {
        throw new Error("Prepared linked transition requires one exact adjacent native audio companion track.");
      }
    }
  }
  if (Array.isArray(input.linkedAudioTargets)) {
    const declared = input.linkedAudioTargets.map((item) => item.id);
    const primaries = [input.target, input.outgoing, input.incoming]
      .filter(Boolean).map((item) => byId.get(item.id)).filter(Boolean);
    const expected = [...new Set(primaries.flatMap(({clip}) => clip.linkedItemIds ?? []))]
      .filter((id) => byId.get(id)?.track.type === "audio");
    if (!sameIds(declared, expected)) {
      throw new Error("Prepared linked-audio targets do not match the exact live link topology.");
    }
  }
}
function canonicalMarkerSourceFrame(clip, input) {
  const raw = Number(input.maybeData !== undefined ? input.frameOrData : (input.frame ?? input.clipOrFrame));
  if (!Number.isSafeInteger(raw)) return null;
  if (input.frameOrData !== undefined || input.maybeData !== undefined) return raw;
  const domain = input.frameDomain ?? "auto";
  const sourceStart = clip.sourceRange?.start;
  const sourceEnd = clip.sourceRange?.endExclusive;
  const duration = Number.isSafeInteger(sourceStart) && Number.isSafeInteger(sourceEnd)
    ? sourceEnd - sourceStart : null;
  if (domain === "offset") return Number.isSafeInteger(sourceStart) ? sourceStart + raw : null;
  if (["source", "raw"].includes(domain)) return raw;
  if (domain !== "auto") throw new Error("Prepared clip marker frame domain is invalid.");
  if (Number.isSafeInteger(duration) && raw >= 0 && raw < duration) return sourceStart + raw;
  return raw;
}
function markerSourceFrame(marker) {
  const value = Number(marker?.sourceFrame ?? marker?.source_frame ?? marker?.frame);
  return Number.isSafeInteger(value) ? value : null;
}
function selectorNames(actionId, input) {
  if (actionId === "cutagent.action.clip.link" && Array.isArray(input.clips)) return input.clips;
  if (actionId === "cutagent.action.clip.marker.custom_data") {
    return [input.maybeData !== undefined ? input.clipOrFrame : input.clip]
      .filter((value) => typeof value === "string" && value);
  }
  if (actionId === "cutagent.action.clip.marker.delete_custom") {
    return [input.maybeData !== undefined ? input.clipOrData : input.clip]
      .filter((value) => typeof value === "string" && value);
  }
  return [input.name, input.clipName, input.clip, input.oldName, input.clipOrName, input.clipOrFrame, input.clipOrData]
    .filter((value) => typeof value === "string" && value);
}
const AUDIO_ONLY_CLIP_ACTIONS = new Set([
  "cutagent.action.clip.audio_eq",
  "cutagent.action.clip.audio_gain",
  "cutagent.action.clip.audio_normalize",
  "cutagent.action.clip.audio_pan",
  "cutagent.action.clip.audio_pitch",
]);
function roundHalfToEven(value) {
  if (!Number.isFinite(value)) throw new Error("Prepared residual record-frame selector is not finite.");
  const lower = Math.floor(value);
  const fraction = value - lower;
  if (fraction < 0.5) return lower;
  if (fraction > 0.5) return lower + 1;
  return lower % 2 === 0 ? lower : lower + 1;
}
function timelineFramesPerSecond(snapshot) {
  const numerator = snapshot?.frameRate?.numerator;
  const denominator = snapshot?.frameRate?.denominator;
  if (!Number.isSafeInteger(numerator) || numerator <= 0
    || !Number.isSafeInteger(denominator) || denominator <= 0) {
    throw new Error("Prepared residual target lacks an exact Timeline frame rate.");
  }
  return numerator / denominator;
}
function timelineNominalTimebase(snapshot) {
  const nominalTimebase = snapshot?.frameRate?.nominalTimebase;
  if (!Number.isSafeInteger(nominalTimebase) || nominalTimebase <= 0) {
    throw new Error("Prepared residual target lacks an exact nominal Timeline timebase.");
  }
  return nominalTimebase;
}
function finiteDecimal(value) {
  if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/u.test(value)) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}
function canonicalRecordFrameSelector(snapshot, value) {
  if (value === undefined) return null;
  if (Number.isSafeInteger(value)) {
    if (value < 0) throw new Error("Prepared residual record-frame selector must not be negative.");
    return value;
  }
  if (typeof value !== "string") throw new Error("Prepared residual record-frame selector must be a string or integer.");
  const source = value.trim();
  if (!source) throw new Error("Prepared residual record-frame selector must not be empty.");
  let frame;
  const integer = /^[+-]?\d+$/u;
  if (source.endsWith("f")) {
    const rawFrames = source.slice(0, -1).trim();
    if (!integer.test(rawFrames)) throw new Error("Prepared residual frame-count selector is invalid.");
    frame = Number(rawFrames);
  } else if (integer.test(source)) {
    frame = Number(source);
  } else {
    const fps = timelineFramesPerSecond(snapshot);
    let seconds;
    if (source.endsWith("s")) {
      seconds = finiteDecimal(source.slice(0, -1));
    } else if (source.includes(":")) {
      const fullTimecode = /^(\d{1,3}):(\d{2}):(\d{2})([:;])(\d{2})$/u.exec(source);
      if (fullTimecode) {
        const nominalTimebase = timelineNominalTimebase(snapshot);
        const [, hoursRaw, minutesRaw, secondsRaw, separator, framesRaw] = fullTimecode;
        const hours = Number(hoursRaw);
        const minutes = Number(minutesRaw);
        const timecodeSeconds = Number(secondsRaw);
        const frameNumber = Number(framesRaw);
        if (minutes >= 60 || timecodeSeconds >= 60 || frameNumber >= nominalTimebase) {
          throw new Error("Prepared residual timecode component is outside the Timeline rate.");
        }
        const totalMinutes = hours * 60 + minutes;
        frame = ((hours * 3600 + minutes * 60 + timecodeSeconds) * nominalTimebase) + frameNumber;
        if (separator === ";") {
          const dropFrames = Math.abs(fps - (30_000 / 1_001)) <= 0.000001 ? 2
            : Math.abs(fps - (60_000 / 1_001)) <= 0.000001 ? 4 : 0;
          if (dropFrames === 0) {
            throw new Error("Prepared residual drop-frame timecode requires a 29.97 or 59.94 Timeline.");
          }
          if (timecodeSeconds === 0 && minutes % 10 !== 0 && frameNumber < dropFrames) {
            throw new Error("Prepared residual timecode names a dropped frame.");
          }
          frame -= dropFrames * (totalMinutes - Math.floor(totalMinutes / 10));
        }
      } else {
        const parts = source.split(":");
        if (parts.length !== 3 || parts.some((part) => !integer.test(part))) {
          throw new Error("Prepared residual timecode selector is invalid.");
        }
        const values = parts.map(Number);
        seconds = values[0] * 3600 + values[1] * 60 + values[2];
      }
      if (frame === undefined && seconds === undefined) {
        throw new Error("Prepared residual timecode selector is invalid.");
      }
    } else {
      seconds = finiteDecimal(source);
    }
    if (frame === undefined) {
      if (seconds === null) throw new Error("Prepared residual time selector is invalid.");
      frame = roundHalfToEven(seconds * fps);
    }
  }
  if (!Number.isSafeInteger(frame)) {
    throw new Error("Prepared residual record-frame selector exceeds the safe-integer range.");
  }
  if (frame < 0) throw new Error("Prepared residual record-frame selector must not be negative.");
  return frame;
}
function absoluteTimelineRecordFrame(snapshot, value) {
  const recordFrame = canonicalRecordFrameSelector(snapshot, value);
  if (recordFrame === null) return null;
  const timelineStart = snapshot?.start?.value?.value;
  if (!Number.isSafeInteger(timelineStart)) {
    throw new Error("Prepared residual target lacks an exact Timeline start frame.");
  }
  const absoluteRecordFrame = timelineStart + recordFrame;
  if (!Number.isSafeInteger(absoluteRecordFrame)) {
    throw new Error("Prepared residual record-frame selector exceeds the safe-integer range after Timeline-start conversion.");
  }
  return absoluteRecordFrame;
}
function validateFusionCreateSelector(actionId, input) {
  const name = actionId === "cutagent.action.clip.fusion.import" ? input.clipName : input.name;
  const hasName = typeof name === "string" && name.length > 0;
  const hasTrack = input.track !== undefined;
  const hasRecordFrame = input.recordFrame !== undefined;
  if (hasTrack !== hasRecordFrame || (hasName && hasTrack)
    || (hasTrack && (!Number.isSafeInteger(input.track) || input.track < 1))) {
    throw new Error("Prepared Fusion target must use either a clip name or a one-based track with recordFrame.");
  }
}
function selectTimelineItems(actionId, snapshot, input) {
  const fusionCreate = ["cutagent.action.clip.fusion.add", "cutagent.action.clip.fusion.import"].includes(actionId);
  if (fusionCreate) validateFusionCreateSelector(actionId, input);
  const fusionRecordFrame = fusionCreate
    ? absoluteTimelineRecordFrame(snapshot, input.recordFrame)
    : null;
  const selectorRecordFrame = input.at === undefined
    ? fusionRecordFrame
    : absoluteTimelineRecordFrame(snapshot, input.at);
  const exactFusionRecordFrame = fusionCreate ? fusionRecordFrame : null;
  const requiredTrackType = AUDIO_ONLY_CLIP_ACTIONS.has(actionId) ? "audio" : null;
  const explicitIds = [input.timelineItemId, input.clipId].filter((value) => typeof value === "string" && value);
  if (explicitIds.length) {
    const rows = timelineItems(snapshot).filter(({clip}) => explicitIds.includes(clip.id)
      && (exactFusionRecordFrame === null || (clip.recordRange?.start <= exactFusionRecordFrame && exactFusionRecordFrame < clip.recordRange?.endExclusive)));
    if (rows.length !== explicitIds.length) throw new Error("Prepared residual target identity is missing or ambiguous.");
    return rows;
  }
  const names = selectorNames(actionId, input);
  if (requiredTrackType === "audio" && names.length === 0 && selectorRecordFrame === null) {
    throw new Error("Prepared audio mutation requires an exact clip name or record-domain at selector.");
  }
  const trackIndex = Number.isSafeInteger(input.videoTrackIndex) ? input.videoTrackIndex
    : Number.isSafeInteger(input.track) ? input.track : null;
  if (names.length) {
    const rows = timelineItems(snapshot).filter(({track, clip}) => names.includes(clip.name)
      && (requiredTrackType === null || track.type === requiredTrackType)
      && (trackIndex === null || track.index === trackIndex)
      && (selectorRecordFrame === null || (clip.recordRange?.start <= selectorRecordFrame && selectorRecordFrame < clip.recordRange?.endExclusive)));
    if (rows.length !== new Set(names).size) throw new Error("Prepared residual target name is missing or ambiguous.");
    return rows;
  }
  const recordPosition = selectorRecordFrame
    ?? (Number.isSafeInteger(input.recordFrame) ? input.recordFrame : null)
    ?? (Number.isSafeInteger(input.recordPosition) ? input.recordPosition : null);
  if (recordPosition !== null) {
    const rows = timelineItems(snapshot).filter(({track, clip}) => (requiredTrackType === null || track.type === requiredTrackType)
      && (trackIndex === null || track.index === trackIndex)
      && clip.recordRange?.start <= recordPosition && recordPosition < clip.recordRange?.endExclusive);
    if (rows.length !== 1) throw new Error("Prepared residual record-frame target is missing or ambiguous.");
    return rows;
  }
  return [];
}
function managedRoots(secretDir) {
  return [
    process.env.CUTAGENT_USER_UPLOADS_DIR, process.env.CUTAGENT_USER_EXPORTS_DIR,
    process.env.CUTAGENT_CHECKPOINT_DIR, process.env.CUTAGENT_ARTIFACTS_DIR,
    ...(typeof secretDir === "string" ? [secretDir] : []),
  ].filter(Boolean).map((value) => path.resolve(value));
}
function captureManagedPath(rawPath, {secretDir, allowAbsent = false} = {}) {
  const resolvedPath = path.resolve(rawPath);
  const roots = managedRoots(secretDir).filter((root) => resolvedPath === root || resolvedPath.startsWith(`${root}${path.sep}`));
  if (roots.length !== 1) throw new Error("Prepared artifact escaped one exact managed root.");
  const exists = fs.existsSync(resolvedPath);
  if (!exists && !allowAbsent) throw new Error("Prepared managed input is unavailable.");
  if (exists && (!fs.statSync(resolvedPath).isFile() || fs.lstatSync(resolvedPath).isSymbolicLink())) {
    throw new Error("Prepared artifact must be a regular non-symlink file.");
  }
  const contentDigest = exists ? `sha256:${sha256(fs.readFileSync(resolvedPath))}` : null;
  const stableId = `artifact_${sha256(resolvedPath).slice(0, 32)}`;
  return {
    stableId, resolvedPath, contentDigest,
    revision: `revision_${sha256(`${resolvedPath}${contentDigest ?? ":absent"}`).slice(0, 32)}`,
  };
}

async function captureExactBinding(actionId, input, context, scope, minimum, dependencies) {
  const projectContext = await dependencies.liveInspectionService.readWithMutationGuard({operation: "project.context"});
  const projectLibraryId = projectContext.privateExecutionIdentity?.projectLibraryId;
  const projectLibraryRevision = projectContext.mutationGuard;
  const projectRevision = projectContext.value?.projectRevision?.revision;
  const projectId = input.projectId ?? scope?.binding?.projectId ?? projectContext.value?.project?.id;
  const timelineId = input.timelineId ?? scope?.binding?.timelineId ?? projectContext.value?.timeline?.id;
  if (!projectLibraryId || !projectLibraryRevision || !projectRevision || !projectId || !timelineId) {
    throw new Error(`Prepared action live project binding is incomplete: ${actionId}`);
  }
  const inspected = await dependencies.liveInspectionService.readWithMutationGuard({operation: "timeline.snapshot", projectId, timelineId});
  const snapshot = inspected?.value ?? null;
  if (!snapshot || snapshot.timeline?.id !== timelineId) {
    throw new Error(`Prepared action live timeline binding is incomplete: ${actionId}`);
  }
  if (typeof input.timelineRevision === "string" && input.timelineRevision !== snapshot.revision) {
    throw new Error(`Prepared action live timeline revision is stale: ${actionId}`);
  }
  const targetIds = [];
  const targetRevisions = {};
  const referencedPayloadDigests = [];
  const privateArtifacts = {};
  let fusionBeforeReferences = null;
  let fusionImportMode = null;
  let exactTimelineItemTarget = null;
  let exactTransitionTargets = null;
  let exactTransitionBatchTargets = null;
  const inputPaths = [input.inputPath, input.referencePath, input.targetPath, input.templatePath, input.imagePath,
    actionId === "cutagent.action.clip.fusion.import" ? input.path : null]
    .filter((value) => typeof value === "string" && value);
  const requestedOutputPath = typeof input.outputPath === "string" ? input.outputPath
    : (typeof input.path === "string" && actionId.endsWith(".export") ? input.path : null);
  // Reverb's public outputPath is optional, but execution still owns a private
  // output artifact. The input extension selects its format; the public input
  // path is never used as the destination.
  const outputPath = requestedOutputPath ?? (actionId === "cutagent.action.audio.reverb" ? input.inputPath : null);
  const pathBindings = [
    ...inputPaths.map((rawPath, index) => [index === 0 ? "input" : `input${index + 1}`, rawPath]),
    ["output", outputPath],
  ].filter(([, value]) => value);
  for (const [role, rawPath] of pathBindings) {
    let artifact;
    if (role === "output") {
      if (typeof dependencies.artifactService?.reservePrivateOutputArtifact !== "function") {
        throw new Error("Prepared residual output requires carrier-owned artifact custody.");
      }
      const extension = path.extname(rawPath).slice(1).toLowerCase();
      if (!/^[a-z0-9]{1,12}$/u.test(extension)) throw new Error("Prepared residual output extension is invalid.");
      const stableId = `artifact_${sha256(`${context.operationId}:${actionId}:output`).slice(0, 32)}`;
      const reservation = dependencies.artifactService.reservePrivateOutputArtifact({
        artifactId: stableId,
        operationId: context.operationId,
        accountFingerprint: context.accountFingerprint,
        extension,
      });
      artifact = {
        stableId,
        resolvedPath: reservation.absolutePath,
        revision: `revision_reserved_${sha256(`${stableId}:${context.operationId}`).slice(0, 24)}`,
        reservationId: `reservation_${sha256(`${stableId}:${context.operationId}:${context.accountFingerprint}`).slice(0, 32)}`,
        allowedRootId: "carrier_private_output_artifacts",
        pathDigest: `sha256:${sha256(reservation.absolutePath)}`,
        reservationIdentity: reservation.identity,
      };
    } else {
      artifact = captureManagedPath(rawPath, {secretDir: dependencies.secretDir});
    }
    targetIds.push(artifact.stableId);
    targetRevisions[artifact.stableId] = artifact.revision;
    if (artifact.contentDigest) referencedPayloadDigests.push(artifact.contentDigest);
    privateArtifacts[role] = artifact;
  }
  if (typeof input.inputArtifactId === "string") {
    if (typeof dependencies.artifactService?.capturePrivateManagedArtifact !== "function") {
      throw new Error("Prepared Edit import requires carrier-owned managed artifact custody.");
    }
    const captured = dependencies.artifactService.capturePrivateManagedArtifact({
      artifactId: input.inputArtifactId, accountFingerprint: context.accountFingerprint,
    });
    if (!captured || captured.artifactId !== input.inputArtifactId || typeof captured.absolutePath !== "string"
      || !/^[a-f0-9]{64}$/u.test(captured.sha256)) {
      throw new Error("Prepared Edit managed artifact capture is malformed.");
    }
    const artifact = {
      stableId: captured.artifactId, resolvedPath: captured.absolutePath,
      contentDigest: `sha256:${captured.sha256}`,
      revision: `revision_${sha256(`${captured.artifactId}:${captured.sha256}:${JSON.stringify(captured.identity)}`).slice(0, 32)}`,
      allowedRootId: "carrier_managed_artifacts", reservationIdentity: captured.identity,
    };
    targetIds.push(artifact.stableId); targetRevisions[artifact.stableId] = artifact.revision;
    referencedPayloadDigests.push(artifact.contentDigest); privateArtifacts.input = artifact;
  }
  if (actionId === "cutagent.action.system.keyframe_mode.set") {
    if (typeof dependencies.resolveService?.executeSdkLowLevelAction !== "function") throw new Error("Prepared system setting readback is unavailable.");
    const observed = await dependencies.resolveService.executeSdkLowLevelAction({actionId: "cutagent.action.system.keyframe_mode.get", input: {}});
    const mode = observed?.mode ?? observed?.keyframe_mode ?? observed?.data?.mode;
    const normalized = ({0: "all", 1: "color", 2: "sizing"})[mode] ?? mode;
    if (!["all", "color", "sizing"].includes(normalized)) throw new Error("Prepared system setting readback is malformed.");
    targetIds.push("resolve.keyframe_mode"); targetRevisions["resolve.keyframe_mode"] = `revision_keyframe_mode_${normalized}`;
  } else if (snapshot) {
    if (RESIDUAL_EDIT_ACTIONS.has(actionId)) {
      targetIds.push(timelineId); targetRevisions[timelineId] = snapshot.revision;
    }
    const publicTargets = exactPublicTimelineTargets(input);
    const rows = publicTargets.length
      ? publicTargets.map((target) => {
        const matches = timelineItems(snapshot).filter(({clip}) => clip.id === target.id && clip.snapshotId === target.snapshotId);
        if (matches.length !== 1) throw new Error("Prepared professional target is missing or ambiguous.");
        assertPublicTimelineTarget(target, matches[0].track, matches[0].clip, actionId);
        return matches[0];
      })
      : selectTimelineItems(actionId, snapshot, input);
    if (actionId.startsWith("cutagent.action.clip.keyframe.") && !actionId.endsWith(".get")
      && rows.some(({clip}) => !inspected.privateInspectorStateDigestByPublicId?.has(clip.id))) {
      throw new Error("Exact persisted Inspector state is unavailable for keyframe mutation.");
    }
    if (RESIDUAL_EDIT_ACTIONS.has(actionId)) {
      assertResidualEditHandlerScope(actionId, input, snapshot, rows);
    }
    if (["cutagent.action.edit.transition.add", "cutagent.action.edit.transition.batch"].includes(actionId)) {
      const nativeIds = new Map(inspected.privateTimelineItemNativeIdByPublicId ?? []);
      const privateTarget = (target) => {
        const id = nativeIds.get(target.id);
        const linkedItemIds = target.linkedItemIds.map((linkedId) => nativeIds.get(linkedId));
        if (typeof id !== "string" || !id || linkedItemIds.some((linkedId) => typeof linkedId !== "string" || !linkedId)) {
          throw new Error("Prepared transition lacks complete private native target custody.");
        }
        return {
          id, trackType: target.trackType, trackIndex: target.trackIndex,
          recordStartFrame: target.recordStartFrame, recordEndFrame: target.recordEndFrame,
          name: target.name, linkedItemIds,
        };
      };
      if (actionId === "cutagent.action.edit.transition.add") {
        exactTransitionTargets = {
          outgoing: privateTarget(input.outgoing),
          incoming: privateTarget(input.incoming),
          linkedAudioTargets: input.linkedAudioTargets.map(privateTarget),
          editFrame: input.editFrame,
          placement: input.placement,
          scope: input.scope,
        };
      } else {
        exactTransitionBatchTargets = transitionBatchEntries(input).map((transition) => ({
          outgoing: privateTarget(transition.outgoing),
          incoming: privateTarget(transition.incoming),
          linkedAudioTargets: transition.linkedAudioTargets.map(privateTarget),
          editFrame: transition.editFrame,
          placement: transition.placement,
          scope: "video",
        }));
      }
    }
    for (const {clip} of rows) {
      if (!targetIds.includes(clip.id)) { targetIds.push(clip.id); targetRevisions[clip.id] = snapshot.revision; }
    }
    for (const media of [input.cameraMedia, input.backgroundMedia].filter(Boolean)) {
      const mediaRevision = await captureMediaIdentity(dependencies.liveInspectionService, projectId, media);
      targetIds.push(media.id); targetRevisions[media.id] = mediaRevision;
    }
    if (actionId === "cutagent.action.clip.fade_in" && (input.scope ?? "linked") === "linked") {
      const linkedIds = rows.flatMap(({clip}) => clip.linkedItemIds ?? []);
      for (const linkedId of linkedIds) {
        const matches = timelineItems(snapshot).filter(({clip}) => clip.id === linkedId);
        if (matches.length !== 1) throw new Error("Prepared linked fade target is missing or ambiguous.");
        if (!targetIds.includes(linkedId)) {
          targetIds.push(linkedId); targetRevisions[linkedId] = snapshot.revision;
        }
      }
    }
    if (actionId.startsWith("cutagent.action.clip.marker.") || actionId === "cutagent.action.clip.offset") {
      if (rows.length !== 1) throw new Error("Prepared clip child action requires one exact clip target.");
      const nativeIds = new Map(inspected.privateTimelineItemNativeIdByPublicId ?? []);
      exactTimelineItemTarget = {
        id: nativeIds.get(rows[0].clip.id), trackType: rows[0].track.type,
        trackIndex: rows[0].track.index, recordStartFrame: rows[0].clip.recordRange?.start,
        recordEndFrame: rows[0].clip.recordRange?.endExclusive, name: rows[0].clip.name,
        linkedItemIds: (rows[0].clip.linkedItemIds ?? []).map((id) => nativeIds.get(id)),
      };
      if (!exactTimelineItemTarget.id || exactTimelineItemTarget.linkedItemIds.some((id) => !id)) {
        throw new Error("Prepared clip child action lacks exact private native target custody.");
      }
    }
    if (actionId.startsWith("cutagent.action.clip.marker.")) {
      const markerInput = {name: rows[0].clip.name};
      const listed = await dependencies.resolveService.executeSdkLowLevelAction({
        actionId: "cutagent.action.clip.marker.list", input: markerInput,
      }, {
        extraEnv: {CUTAGENT_SDK_EXPECTED_CLIP_MOTION_TARGET: JSON.stringify(exactTimelineItemTarget)},
      });
      const markers = listed?.payload?.data?.markers ?? listed?.data?.markers
        ?? listed?.markers ?? (Array.isArray(listed) ? listed : null);
      if (!Array.isArray(markers)) throw new Error("Prepared clip marker collection readback is unavailable.");
      const wantedFrame = canonicalMarkerSourceFrame(rows[0].clip, input);
      const customRoute = actionId === "cutagent.action.clip.marker.delete_custom";
      const wantedCustom = customRoute ? (input.maybeData ?? input.clipOrData) : null;
      const matches = markers.filter((marker) => customRoute
        ? marker.customData === wantedCustom
        : markerSourceFrame(marker) === wantedFrame);
      const creating = actionId.endsWith("marker.add");
      if (!customRoute && wantedFrame === null) throw new Error("Prepared clip marker source frame is unavailable.");
      if (!creating && matches.length !== 1) throw new Error("Prepared clip marker target is missing or ambiguous.");
      if (creating && matches.length !== 0) throw new Error("Prepared clip marker create collides with an existing marker.");
      const canonicalSourceFrame = creating ? wantedFrame : markerSourceFrame(matches[0]);
      if (canonicalSourceFrame === null) throw new Error("Prepared clip marker readback omitted its canonical source frame.");
      if (!creating && typeof matches[0]?.customData !== "string") {
        throw new Error("Prepared clip marker readback omitted customData custody.");
      }
      const markerId = `marker_${sha256(JSON.stringify({sourceFrame: canonicalSourceFrame, timelineItemId: rows[0].clip.id})).slice(0, 32)}`;
      targetIds.push(markerId);
      targetRevisions[markerId] = creating
        ? `revision_planned_${sha256(markerId).slice(0, 24)}` : snapshot.revision;
    }
    if ([
      "cutagent.action.clip.fusion.add", "cutagent.action.clip.fusion.delete",
      "cutagent.action.clip.fusion.export", "cutagent.action.clip.fusion.import",
      "cutagent.action.clip.fusion.load", "cutagent.action.clip.fusion.tool_set",
    ].includes(actionId)) {
      if (rows.length !== 1) throw new Error("Prepared Fusion action requires one exact clip target.");
      const references = await dependencies.liveInspectionService.read({
        operation: "fusion.compositions", projectId, timelineId,
        timelineItemId: rows[0].clip.id, expectedRevision: snapshot.revision,
      });
      if (!Array.isArray(references)) throw new Error("Prepared Fusion composition collection is unavailable.");
      const requestedIndex = Number(input.index ?? input.compIndex ?? input.comp ?? 1);
      const matches = references.filter((reference) => Number(reference.index) === requestedIndex);
      const creating = ["cutagent.action.clip.fusion.add", "cutagent.action.clip.fusion.import"].includes(actionId);
      if (!creating && matches.length !== 1) throw new Error("Prepared Fusion composition target is missing or ambiguous.");
      if (creating || actionId === "cutagent.action.clip.fusion.delete") {
        if (references.some((reference) => typeof reference?.id !== "string" || !reference.id)) {
          throw new Error("Prepared Fusion composition collection lacks stable identities.");
        }
        fusionBeforeReferences = references.map((reference) => {
          const captured = {
            id: reference.id, index: reference.index, name: reference.name,
            revision: reference.revision, graphDigest: reference.graphDigest,
          };
          if (!Number.isSafeInteger(captured.index) || captured.index < 1 || typeof captured.name !== "string"
              || !captured.name || typeof captured.revision !== "string" || typeof captured.graphDigest !== "string") {
            throw new Error("Prepared Fusion composition collection lacks full reference and graph-revision custody.");
          }
          return captured;
        });
        if (new Set(fusionBeforeReferences.map((reference) => reference.id)).size !== fusionBeforeReferences.length
            || new Set(fusionBeforeReferences.map((reference) => reference.index)).size !== fusionBeforeReferences.length) {
          throw new Error("Prepared Fusion composition collection is ambiguous.");
        }
        if (actionId === "cutagent.action.clip.fusion.import") {
          const clip = rows[0].clip;
          const blank = fusionBeforeReferences.length === 1 && fusionBeforeReferences[0].index === 1
            && fusionBeforeReferences[0].name === "Composition 1";
          fusionImportMode = blank && clip.name === "Fusion Composition" && clip.mediaPoolItemId === null
            ? "replace_single_blank_holder" : "append";
        }
      }
      const compositionId = creating
        ? `planned_fusion_comp_${sha256(`${context.operationId}:${rows[0].clip.id}:${requestedIndex}`).slice(0, 32)}`
        : matches[0].id;
      targetIds.push(compositionId);
      targetRevisions[compositionId] = creating
        ? `revision_planned_${sha256(compositionId).slice(0, 24)}` : snapshot.revision;
    }
    const mediaName = input.mediaName ?? input.replaceMediaName ?? input.replaceMedia;
    if ((actionId === "cutagent.action.clip.take.add" || actionId === "cutagent.action.audio.duck")
      && typeof mediaName === "string" && mediaName) {
      const page = (await dependencies.liveInspectionService.readWithMutationGuard({
        operation: "mediaPool.page", projectId, offset: 0, pageSize: 32,
        expectedRevision: null, search: {query: mediaName, match: "exact", fields: ["name"]},
      }))?.value;
      const assets = page?.assets;
      if (!Array.isArray(assets) || assets.length !== 1 || typeof assets[0]?.id !== "string") {
        throw new Error("Prepared Media Pool target is missing or ambiguous.");
      }
      targetIds.push(assets[0].id); targetRevisions[assets[0].id] = page.revision;
    }
    if (actionId.startsWith("cutagent.action.text.insert")) {
      const count = actionId.endsWith("template_batch") ? input.items.length : 1;
      for (let index = 0; index < count; index += 1) {
        const id = `planned_timeline_item_${sha256(`${context.operationId}:${index}`).slice(0, 24)}`;
        targetIds.push(id); targetRevisions[id] = `revision_planned_${sha256(id).slice(0, 24)}`;
      }
    }
    if (actionId === "cutagent.action.edit.camera_pip") {
      for (let index = 0; index < 2; index += 1) {
        const id = `planned_timeline_item_${sha256(`${context.operationId}:edit.camera_pip:${index}`).slice(0, 24)}`;
        targetIds.push(id); targetRevisions[id] = `revision_planned_${sha256(id).slice(0, 24)}`;
      }
    }
    if (["cutagent.action.edit.ripple_delete", "cutagent.action.edit.from_edl"].includes(actionId)) {
      const expectedName = input.newTimelineName ?? input.expectedTimelineName;
      const id = `planned_timeline_${sha256(`${context.operationId}:${actionId}:${expectedName}`).slice(0, 24)}`;
      targetIds.push(id); targetRevisions[id] = `revision_planned_${sha256(id).slice(0, 24)}`;
    }
  }
  const burninAction = actionId.startsWith("cutagent.action.burnin.");
  if (burninAction && minimum !== "account/project-library" && !targetIds.includes(projectId)) {
    targetIds.push(projectId);
    targetRevisions[projectId] = projectRevision;
  }
  if (burninAction && minimum === "project+timeline" && !targetIds.includes(timelineId)) {
    targetIds.push(timelineId);
    targetRevisions[timelineId] = snapshot.revision;
  }
  if (targetIds.length === 0) {
    targetIds.push(projectLibraryId);
    targetRevisions[projectLibraryId] = projectLibraryRevision;
  }
  if (new Set(targetIds).size !== targetIds.length) throw new Error(`Prepared action resolved duplicate targets: ${actionId}`);
  const identities = {
    projectLibraryId,
    projectId,
    timelineId,
    targetIds,
  };
  const revisions = {
    projectLibrary: projectLibraryRevision,
    project: projectRevision,
    timeline: snapshot.revision,
    targets: targetRevisions,
  };
  return {
    identities, revisions, referencedPayloadDigests,
    privateContext: {
      ...(inspected ? {
        timeline: {mutationGuard: inspected.mutationGuard},
        privateTimelineItemNativeIds: Object.fromEntries(inspected.privateTimelineItemNativeIdByPublicId ?? []),
      } : {}),
      artifacts: privateArtifacts,
      ...(exactTimelineItemTarget ? {exactTimelineItemTarget} : {}),
      ...(exactTransitionTargets ? {exactTransitionTargets} : {}),
      ...(exactTransitionBatchTargets ? {exactTransitionBatchTargets} : {}),
      ...(fusionBeforeReferences ? {fusionBeforeReferences} : {}),
      ...(fusionImportMode ? {fusionImportMode} : {}),
    },
  };
}

function assertBinding(actionId, captured, minimum) {
  const binding = captured && {
    projectLibraryId: captured.identities?.projectLibraryId,
    projectLibraryRevision: captured.revisions?.projectLibrary,
    projectId: captured.identities?.projectId,
    projectRevision: captured.revisions?.project,
    timelineId: captured.identities?.timelineId,
    timelineRevision: captured.revisions?.timeline,
    targetIds: captured.identities?.targetIds,
    targetRevisions: captured.revisions?.targets,
  };
  if (!binding || typeof binding.projectLibraryId !== "string"
    || typeof binding.projectLibraryRevision !== "string" || !Array.isArray(binding.targetIds)
    || binding.targetIds.length === 0 || new Set(binding.targetIds).size !== binding.targetIds.length
    || !binding.targetIds.every((targetId) => typeof targetId === "string" && targetId)
    || !binding.targetRevisions || typeof binding.targetRevisions !== "object"
    || Object.keys(binding.targetRevisions).length !== binding.targetIds.length
    || binding.targetIds.some((targetId) => typeof binding.targetRevisions[targetId] !== "string" || !binding.targetRevisions[targetId])) {
    throw new Error(`Prepared action live identity capture is incomplete: ${actionId}`);
  }
  if (minimum !== "account/project-library"
    && (!binding.projectId || !binding.projectRevision)) {
    throw new Error(`Prepared action project binding is incomplete: ${actionId}`);
  }
  if (minimum === "project+timeline"
    && (!binding.timelineId || !binding.timelineRevision)) {
    throw new Error(`Prepared action timeline binding is incomplete: ${actionId}`);
  }
  return binding;
}

function builder({actionId, inputSchema, operationClass, authority}, dependencies) {
  const minimum = minimumBinding(authority);
  const payloadDigests = new Map();
  const mutationBinding = operationClass === "read" ? null : Object.freeze({
    minimumBinding: minimum,
    async resolveReferencedPayloadDigests({request}) {
      const digests = payloadDigests.get(request.operationId);
      payloadDigests.delete(request.operationId);
      if (!digests) throw new Error(`Prepared action lost managed payload custody: ${actionId}`);
      return [...digests];
    },
  });
  return createSdkPreparedActionBuilderContribution({
    inputSchema,
    ...(KEYFRAME_RESULT_SCHEMAS[actionId] ? {
      resultSchema: KEYFRAME_RESULT_SCHEMAS[actionId],
      projectResult: (value) => projectKeyframeResult(actionId, value),
    } : {}),
    ...(RETIME_ACTIONS.has(actionId) ? {
      resultSchema: RETIME_RESULT_SCHEMAS[actionId],
      projectResult: (value) => projectRetimeResult(actionId, value),
    } : {}),
    ...(["cutagent.action.bulk.disable", "cutagent.action.bulk.enable"].includes(actionId) ? {
      resultSchema: sdkBulkClipStateResultSchema,
      projectResult: (value) => value,
    } : {}),
    ...(mutationBinding ? {mutationBinding} : {}),
    async captureRequestBinding({context, input}) {
      if (["cutagent.action.clip.fusion.add", "cutagent.action.clip.fusion.import"].includes(actionId)) {
        validateFusionCreateSelector(actionId, input);
      }
      const captured = await captureExactBinding(actionId, input, context, null, minimum, dependencies);
      assertBinding(actionId, captured, minimum);
      const referencedPayloadDigests = captured.referencedPayloadDigests ?? [];
      if (!Array.isArray(referencedPayloadDigests)
        || referencedPayloadDigests.some((digest) => !/^sha256:[a-f0-9]{64}$/u.test(digest))) {
        throw new Error(`Prepared action managed payload custody is malformed: ${actionId}`);
      }
      if (mutationBinding) payloadDigests.set(context.operationId, Object.freeze([...referencedPayloadDigests]));
      return {
        identities: captured.identities,
        revisions: captured.revisions,
        privateContext: captured.privateContext,
      };
    },
  });
}

/** Exact private 14 + 73 builder contribution consumed by the sole carrier. */
export function createProfessionalAvPreparedActionBuilderContributions(dependencies = {}) {
  const rows = [
    ...Object.entries(PROFESSIONAL_INPUTS).map(([actionId, inputSchema]) => ({
      actionId,
      inputSchema,
      operationClass: CUTAGENT_PREPARED_ACTION_ACTION_METADATA[actionId]?.operationClass,
      authority: actionId === "cutagent.action.system.keyframe_mode.set" ? "managed_artifact_revision" : "exact_timeline_item_revision",
    })),
    ...SDK_RESIDUAL_AV_PREPARED_INPUTS.map((row) => ({...row, inputSchema: jsonInputSchema(row.actionId, row.inputSchema)})),
  ];
  if (rows.length !== 87 || new Set(rows.map(({actionId}) => actionId)).size !== 87) {
    throw new Error("Professional AV builder composition must own exactly 14 + 73 actions.");
  }
  const selectedRows = dependencies.enabledActionIds == null
    ? rows
    : rows.filter(({actionId}) => dependencies.enabledActionIds.has(actionId));
  return Object.freeze(Object.fromEntries(selectedRows.map((row) => [
    row.actionId,
    builder(row, dependencies),
  ])));
}

export const PROFESSIONAL_PREPARED_ACTION_IDS = Object.freeze(Object.keys(PROFESSIONAL_INPUTS));
