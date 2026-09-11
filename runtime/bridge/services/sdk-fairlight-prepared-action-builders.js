import {
  CUTAGENT_SDK_FAIRLIGHT_PREPARED_ACTION_IDS,
  CUTAGENT_SDK_FAIRLIGHT_RAW_AUDIO_CLIP_ACTION_BINDINGS,
  CUTAGENT_SDK_FAIRLIGHT_RAW_AUDIO_TRACK_ACTION_BINDINGS,
  sdkFairlightPreparedOperationInputSchema,
} from "../contracts/generated/sdk-fairlight-prepared-actions.js";
import {sdkFairlightPlanInputSchema} from "../contracts/generated/sdk-fairlight.js";
import {CUTAGENT_PREPARED_ACTION_ACTION_METADATA} from "../contracts/sdk-prepared-action-metadata.generated.js";
import {createSdkPreparedActionBuilderContribution} from "./sdk-prepared-action-carrier.js";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

export const FAIRLIGHT_PREPARED_ACTION_IDS = Object.freeze([...CUTAGENT_SDK_FAIRLIGHT_PREPARED_ACTION_IDS]);
export const FAIRLIGHT_PRODUCTION_READ_ACTION_IDS = Object.freeze([
  "cutagent.action.fairlight.channel_map.clip",
  "cutagent.action.fairlight.clip.linked.list",
  "cutagent.action.fairlight.clip.source_range",
  "cutagent.action.fairlight.clip.track_info",
  "cutagent.action.fairlight.sound_library.list",
  "cutagent.action.fairlight.sound_library.search",
  "cutagent.action.fairlight.sound_library.source_list",
]);
const MANAGED_INPUT_ACTION_IDS = new Set([
  "cutagent.action.fairlight.insert",
  "cutagent.action.fairlight.sound_library.index_file",
  "cutagent.action.fairlight.sound_library.index_folder",
  "cutagent.action.fairlight.sound_library.source_rebuild",
  "cutagent.action.fairlight.sound_library.source_remove",
]);
export const FAIRLIGHT_PLAN_ACTION_ID = "cutagent.action.sdk.fairlight.plan.apply";
const FAIRLIGHT_BOUNCE_ACTION_IDS = new Set([
  "cutagent.action.fairlight.bounce.mix_to_track",
  "cutagent.action.fairlight.bounce.track",
]);
const RAW_AUDIO_TRACK_BINDING_BY_ACTION = new Map(
  CUTAGENT_SDK_FAIRLIGHT_RAW_AUDIO_TRACK_ACTION_BINDINGS.map((binding) => [binding.actionId, binding]),
);
const RAW_AUDIO_CLIP_BINDING_BY_ACTION = new Map(
  CUTAGENT_SDK_FAIRLIGHT_RAW_AUDIO_CLIP_ACTION_BINDINGS.map((binding) => [binding.actionId, binding]),
);

function cancellationFiles(secretDir, operationId) {
  if (typeof secretDir !== "string" || !secretDir || !/^operation_[A-Za-z0-9._~-]+$/u.test(operationId)) {
    throw new Error("Prepared Fairlight bounce cancellation custody is unavailable.");
  }
  const root = path.join(secretDir, "sdk-operation-cancellation");
  const requestPath = path.join(root, `${operationId}.cancel`);
  return Object.freeze({requestPath, acknowledgedPath: `${requestPath}.ack`});
}

async function waitForCancellationAcknowledgement(files, timeoutMs = 10_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (fs.existsSync(files.acknowledgedPath)) return true;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  return false;
}

function reserveLoudnessAnalysisArtifact(artifactCustody, context, actionId) {
  if (typeof artifactCustody?.reservePrivateOutputArtifact !== "function") {
    throw new Error("Prepared Fairlight normalization requires carrier-owned analysis artifact custody.");
  }
  const digest = crypto.createHash("sha256").update(`${context.operationId}:${actionId}:loudness-analysis`).digest("hex");
  const artifactId = `artifact_${digest.slice(0, 32)}`;
  const reservation = artifactCustody.reservePrivateOutputArtifact({
    artifactId,
    operationId: context.operationId,
    accountFingerprint: context.accountFingerprint,
    extension: "wav",
  });
  if (typeof reservation?.absolutePath !== "string" || !reservation.absolutePath
    || !Number.isSafeInteger(reservation.identity?.device) || reservation.identity.device < 0
    || !Number.isSafeInteger(reservation.identity?.inode) || reservation.identity.inode < 0) {
    throw new Error("Prepared Fairlight loudness analysis artifact reservation is malformed.");
  }
  return Object.freeze({artifactId, absolutePath: reservation.absolutePath,
    reservationIdentity: Object.freeze({...reservation.identity})});
}

function withLoudnessAnalysisArtifact(captured, loudnessAnalysisArtifact) {
  return Object.freeze({
    ...captured,
    privateContext: {
      ...captured.privateContext,
      fairlight: {...captured.privateContext.fairlight, loudnessAnalysisArtifact},
    },
  });
}

const stale = (detail) => {
  const error = new Error(`Prepared Fairlight live binding is stale: ${detail}`);
  error.code = "STALE_REVISION";
  throw error;
};
const sameDigests = (left, right) => JSON.stringify([...left].sort()) === JSON.stringify([...right].sort());

function locateSnapshotTarget(target, snapshot, inspected) {
  const clipRows = snapshot.tracks.flatMap((track) => track.clips.map((clip) => ({track, clip})));
  let revision;
  let locator;
  if (target.kind === "track") {
    const matches = snapshot.tracks.filter((track) => track.snapshotId === target.stableId
      && (target.trackType === undefined || track.type === target.trackType)
      && (target.trackIndex === undefined || track.index === target.trackIndex));
    if (matches.length !== 1) stale(`${target.stableId} is not one exact live track`);
    const track = matches[0];
    revision = track.snapshotRevision;
    locator = {kind: "track", stableId: track.snapshotId, trackType: track.type, trackIndex: track.index, trackName: track.name};
  } else if (target.kind === "clip") {
    const matches = clipRows.filter(({track, clip}) => clip.id === target.stableId
      && (target.trackType === undefined || track.type === target.trackType)
      && (target.trackIndex === undefined || track.index === target.trackIndex));
    if (matches.length !== 1) stale(`${target.stableId} is not one exact live clip`);
    const {track, clip} = matches[0];
    const nativeId = inspected.privateTimelineItemNativeIdByPublicId?.get(clip.id);
    if (!nativeId) stale(`${target.stableId} has no authoritative native identity`);
    revision = clip.snapshotRevision;
    locator = {
      kind: "clip", stableId: clip.id, nativeId, trackType: track.type, trackIndex: track.index,
      trackName: track.name, clipName: clip.name, recordStartFrame: clip.recordRange.start,
      recordEndFrameExclusive: clip.recordRange.endExclusive, sourceStartFrame: clip.sourceRange?.start ?? null,
      sourceEndFrameExclusive: clip.sourceRange?.endExclusive ?? null,
      sourceFrameRate: clip.sourceFrameRate ?? null,
      sourcePath: inspected.privateTimelineItemSourcePathByPublicId?.get(clip.id) ?? null,
      linkedItemIds: clip.linkedItemIds,
    };
  } else if (target.kind === "media") {
    const matches = clipRows.filter(({track, clip}) => clip.mediaPoolItemId === target.stableId
      && (target.trackType === undefined || track.type === target.trackType)
      && (target.trackIndex === undefined || track.index === target.trackIndex));
    if (matches.length !== 1) stale(`${target.stableId} is not one exact live media placement`);
    const {track, clip} = matches[0];
    revision = clip.snapshotRevision;
    locator = {kind: "media", stableId: clip.mediaPoolItemId, trackType: track.type, trackIndex: track.index, trackName: track.name, clipName: clip.name, recordStartFrame: clip.recordRange.start};
  } else if (target.kind === "marker") {
    const matches = snapshot.markers.filter((marker) => marker.id === target.stableId);
    if (matches.length !== 1) stale(`${target.stableId} is not one exact live marker`);
    revision = matches[0].snapshotRevision;
    locator = {kind: "marker", stableId: matches[0].id, recordFrame: matches[0].position.value.value};
  } else {
    return null;
  }
  if (revision !== target.revision) stale(`${target.stableId} revision changed`);
  return {stableId: locator.stableId, revision, locator};
}

async function captureLiveBinding(liveInspectionService, claims, actionId) {
  const readContext = () => liveInspectionService.readWithMutationGuard({operation: "project.context"});
  const before = await readContext();
  const libraryId = before.privateExecutionIdentity?.projectLibraryId;
  const nativeProjectId = before.privateExecutionIdentity?.nativeProjectId;
  const project = before.value?.project;
  const timeline = before.value?.timeline;
  const libraryRevision = before.mutationGuard;
  const projectRevision = before.value?.projectRevision?.revision;
  if (libraryId !== claims.projectLibraryId || typeof nativeProjectId !== "string" || !nativeProjectId
    || project?.id !== claims.projectId || timeline?.id !== claims.timelineId
    || libraryRevision !== claims.projectLibraryRevision || projectRevision !== claims.projectRevision) {
    stale("the project-library or project identity/revision changed");
  }
  const inspected = await liveInspectionService.readWithMutationGuard({operation: "timeline.snapshot", projectId: project.id, timelineId: timeline.id});
  const after = await readContext();
  if (after.privateExecutionIdentity?.projectLibraryId !== libraryId
    || after.privateExecutionIdentity?.nativeProjectId !== nativeProjectId
    || after.mutationGuard !== libraryRevision
    || after.value?.project?.id !== project.id || after.value?.timeline?.id !== timeline.id
    || after.value?.projectRevision?.revision !== projectRevision) {
    stale("the project context changed during the bracketed timeline read");
  }
  const snapshot = inspected.value;
  if (snapshot.project.id !== project.id || snapshot.timeline.id !== timeline.id || snapshot.revision !== claims.timelineRevision) {
    stale("the timeline identity/revision changed");
  }
  let claimedTargets = claims.targets;
  if (actionId === "cutagent.action.fairlight.delete") {
    if (claimedTargets.length !== 1 || claimedTargets[0].kind !== "track") {
      stale("track deletion requires one exact live track root");
    }
    const root = locateSnapshotTarget(claimedTargets[0], snapshot, inspected);
    const liveTrack = snapshot.tracks.find((track) => track.snapshotId === root?.stableId);
    if (!liveTrack) stale("track deletion root disappeared before closure capture");
    claimedTargets = [
      claimedTargets[0],
      ...liveTrack.clips.map((clip) => ({
        kind: "clip",
        stableId: clip.id,
        revision: clip.snapshotRevision,
        trackType: liveTrack.type,
        trackIndex: liveTrack.index,
      })),
    ];
  }
  const targetIds = [];
  const targets = {};
  const privateTargets = [];
  for (const target of claimedTargets) {
    let found = null;
    if (target.kind === "project_library" && target.stableId === libraryId) {
      found = {stableId: libraryId, revision: libraryRevision, locator: {kind: target.kind, stableId: libraryId}};
    } else if (target.kind === "project" && target.stableId === project.id) {
      found = {stableId: project.id, revision: projectRevision, locator: {kind: target.kind, stableId: project.id}};
    } else if (target.kind === "timeline" && target.stableId === snapshot.timeline.id) {
      found = {stableId: snapshot.timeline.id, revision: snapshot.revision, locator: {kind: target.kind, stableId: snapshot.timeline.id, nativeTimelineId: inspected.nativeTimelineId}};
    } else {
      found = locateSnapshotTarget(target, snapshot, inspected);
    }
    if (!found || found.revision !== target.revision) stale(`${target.stableId} is not the exact live target`);
    targetIds.push(found.stableId);
    targets[found.stableId] = found.revision;
    privateTargets.push(found.locator);
  }
  return Object.freeze({
    identities: {projectLibraryId: libraryId, projectId: project.id, timelineId: snapshot.timeline.id, targetIds},
    revisions: {projectLibrary: libraryRevision, project: projectRevision, timeline: snapshot.revision, targets},
    privateContext: {fairlight: {
      projectMutationGuard: before.mutationGuard,
      timelineMutationGuard: inspected.mutationGuard,
      nativeProjectId,
      nativeTimelineId: inspected.nativeTimelineId,
      timelineFrameRate: snapshot.frameRate,
      targets: privateTargets,
    }},
  });
}

async function captureCurrentAudioTrackBinding(liveInspectionService, input, actionId, binding) {
  if (binding.alternateSelectorKey && input[binding.alternateSelectorKey] !== undefined) {
    const bus = input[binding.alternateSelectorKey];
    if (typeof bus !== "string" || !bus) stale("the requested Fairlight bus is invalid");
    const current = await liveInspectionService.readWithMutationGuard({operation: "project.context"});
    const projectLibraryId = current.privateExecutionIdentity?.projectLibraryId;
    const projectId = current.value?.project?.id;
    const timelineId = current.value?.timeline?.id;
    const projectRevision = current.value?.projectRevision?.revision;
    if (![projectLibraryId, projectId, timelineId, projectRevision, current.mutationGuard].every((entry) => typeof entry === "string" && entry)) {
      stale("the active project or timeline identity is unavailable");
    }
    const inspected = await liveInspectionService.readWithMutationGuard({operation: "timeline.snapshot", projectId, timelineId});
    const snapshot = inspected.value;
    const buses = snapshot?.fairlight?.buses?.buses;
    const matches = Array.isArray(buses) ? buses.filter((entry) => entry?.name === bus) : [];
    if (snapshot?.project?.id !== projectId || snapshot?.timeline?.id !== timelineId
      || typeof snapshot.revision !== "string" || !snapshot.revision || matches.length !== 1) {
      stale(`${bus} is not one exact live Fairlight bus`);
    }
    return captureLiveBinding(liveInspectionService, {
      projectLibraryId,
      projectId,
      timelineId,
      projectLibraryRevision: current.mutationGuard,
      projectRevision,
      timelineRevision: snapshot.revision,
      targets: [{kind: "timeline", stableId: timelineId, revision: snapshot.revision}],
      referencedPayloadDigests: [],
    }, actionId);
  }
  const trackIndex = input[binding.selectorKey];
  if (!Number.isInteger(trackIndex) || trackIndex < 1) stale("the requested audio track index is invalid");
  const current = await liveInspectionService.readWithMutationGuard({operation: "project.context"});
  const projectLibraryId = current.privateExecutionIdentity?.projectLibraryId;
  const projectId = current.value?.project?.id;
  const timelineId = current.value?.timeline?.id;
  const projectRevision = current.value?.projectRevision?.revision;
  if (![projectLibraryId, projectId, timelineId, projectRevision, current.mutationGuard].every((entry) => typeof entry === "string" && entry)) {
    stale("the active project or timeline identity is unavailable");
  }
  const inspected = await liveInspectionService.readWithMutationGuard({operation: "timeline.snapshot", projectId, timelineId});
  const snapshot = inspected.value;
  if (snapshot?.project?.id !== projectId || snapshot?.timeline?.id !== timelineId
    || typeof snapshot.revision !== "string" || !snapshot.revision) {
    stale("the active timeline snapshot is unavailable");
  }
  if (!Array.isArray(snapshot.tracks)) stale("the active timeline track inventory is unavailable");
  const matches = snapshot.tracks.filter((track) => track.type === "audio" && track.index === trackIndex);
  if (matches.length !== 1 || typeof matches[0].snapshotId !== "string" || !matches[0].snapshotId
    || typeof matches[0].snapshotRevision !== "string" || !matches[0].snapshotRevision) {
    stale(`audio track ${trackIndex} is not one exact live track`);
  }
  return captureLiveBinding(liveInspectionService, {
    projectLibraryId,
    projectId,
    timelineId,
    projectLibraryRevision: current.mutationGuard,
    projectRevision,
    timelineRevision: snapshot.revision,
    targets: [{
      kind: "track",
      stableId: matches[0].snapshotId,
      revision: matches[0].snapshotRevision,
      trackType: "audio",
      trackIndex,
    }],
    referencedPayloadDigests: [],
  }, actionId);
}

function exactFrameReference(value, field) {
  if (value === undefined) return null;
  const match = /^(-?\d+)f$/u.exec(value);
  if (!match || !Number.isSafeInteger(Number(match[1]))) {
    stale(`${field} must be an exact frame reference`);
  }
  return Number(match[1]);
}

async function captureCurrentAudioClipBinding(liveInspectionService, input, actionId, binding) {
  const selector = input[binding.selectorKey];
  if ((binding.required && selector === undefined)
    || (selector !== undefined && (typeof selector !== "string" || !selector))) {
    stale("the requested audio clip selector is invalid");
  }
  const current = await liveInspectionService.readWithMutationGuard({operation: "project.context"});
  const projectLibraryId = current.privateExecutionIdentity?.projectLibraryId;
  const projectId = current.value?.project?.id;
  const timelineId = current.value?.timeline?.id;
  const projectRevision = current.value?.projectRevision?.revision;
  if (![projectLibraryId, projectId, timelineId, projectRevision, current.mutationGuard].every((entry) => typeof entry === "string" && entry)) {
    stale("the active project or timeline identity is unavailable");
  }
  const inspected = await liveInspectionService.readWithMutationGuard({operation: "timeline.snapshot", projectId, timelineId});
  const snapshot = inspected.value;
  if (snapshot?.project?.id !== projectId || snapshot?.timeline?.id !== timelineId
    || typeof snapshot.revision !== "string" || !snapshot.revision || !Array.isArray(snapshot.tracks)) {
    stale("the active timeline snapshot is unavailable");
  }
  const audioClips = snapshot.tracks
    .filter((track) => track.type === "audio")
    .flatMap((track) => (track.clips ?? []).map((clip) => ({track, clip})));
  const matches = selector === undefined && binding.defaultFirstAudioClip
    ? audioClips.slice(0, 1)
    : audioClips.filter(({clip}) => clip.id === selector || (!binding.idOnly && clip.name === selector));
  if (matches.length !== 1) {
    stale(selector === undefined
      ? "the current timeline has no default audio clip"
      : `${selector} is not one exact live audio clip`);
  }
  const [{track, clip}] = matches;
  const recordStart = clip.recordRange?.start;
  const recordEnd = clip.recordRange?.endExclusive;
  if (binding.exactRecordRangeChecks && (
    !Number.isSafeInteger(recordStart) || !Number.isSafeInteger(recordEnd) || recordEnd < recordStart
    || (input.trackIndex !== undefined && input.trackIndex !== track.index)
    || (input.recordFrame !== undefined && exactFrameReference(input.recordFrame, "recordFrame") !== recordStart)
    || (input.recordDuration !== undefined
      && exactFrameReference(input.recordDuration, "recordDuration") !== recordEnd - recordStart)
    || (input.recordEnd !== undefined && exactFrameReference(input.recordEnd, "recordEnd") !== recordEnd)
  )) {
    stale("the requested audio clip selector does not match its exact live record range");
  }
  return captureLiveBinding(liveInspectionService, {
    projectLibraryId,
    projectId,
    timelineId,
    projectLibraryRevision: current.mutationGuard,
    projectRevision,
    timelineRevision: snapshot.revision,
    targets: [{
      kind: "clip",
      stableId: clip.id,
      revision: clip.snapshotRevision,
      trackType: "audio",
      trackIndex: track.index,
    }],
    referencedPayloadDigests: [],
  }, actionId);
}

async function capturePlanBinding(liveInspectionService, input) {
  const projectContext = await liveInspectionService.readWithMutationGuard({operation: "project.context"});
  const inspected = await liveInspectionService.readWithMutationGuard({
    operation: "timeline.snapshot",
    projectId: input.projectId,
    timelineId: input.timelineId,
  });
  const snapshot = inspected.value;
  const projectLibraryId = projectContext.privateExecutionIdentity?.projectLibraryId;
  const projectRevision = projectContext.value?.projectRevision?.revision;
  if (!projectLibraryId || !projectRevision
    || projectContext.value?.project?.id !== input.projectId
    || projectContext.value?.timeline?.id !== input.timelineId
    || snapshot?.project?.id !== input.projectId
    || snapshot?.timeline?.id !== input.timelineId
    || snapshot.revision !== input.timelineRevision) {
    stale("the Fairlight plan binding changed before target capture");
  }
  const rows = snapshot.tracks.flatMap((track) => (track.clips ?? []).map((clip) => ({track, clip})));
  const targets = [];
  const seen = new Set();
  const append = (target) => {
    if (seen.has(target.stableId)) return;
    seen.add(target.stableId);
    targets.push(target);
  };
  for (const change of input.changes) {
    const semanticTargets = change.target.kind === "clips" ? change.target.clips : [change.target];
    for (const target of semanticTargets) {
      if (target.kind === "clip" || Object.hasOwn(target, "clipId")) {
        const matches = rows.filter(({track, clip}) => clip.id === target.clipId
          && track.type === "audio" && track.index === target.trackIndex);
        if (matches.length !== 1) stale(`${target.clipId} is not one exact audio clip`);
        append({kind: "clip", stableId: target.clipId, revision: input.timelineRevision,
          trackType: "audio", trackIndex: target.trackIndex});
      } else if (target.kind === "track") {
        const matches = snapshot.tracks.filter((track) => track.type === "audio" && track.index === target.trackIndex);
        if (matches.length !== 1) stale(`audio track ${target.trackIndex} is not one exact live track`);
        append({kind: "track", stableId: matches[0].snapshotId, revision: input.timelineRevision,
          trackType: "audio", trackIndex: target.trackIndex});
      } else if (target.kind === "bus") {
        append({kind: "timeline", stableId: input.timelineId, revision: input.timelineRevision});
      } else {
        stale("the Fairlight plan contains an unsupported target kind");
      }
    }
  }
  const captured = await captureLiveBinding(liveInspectionService, {
    projectLibraryId,
    projectId: input.projectId,
    timelineId: input.timelineId,
    projectLibraryRevision: projectContext.mutationGuard,
    projectRevision,
    timelineRevision: input.timelineRevision,
    targets,
  }, FAIRLIGHT_PLAN_ACTION_ID);
  if (input.changes.some((change) => change.kind === "synchronization")) {
    const clips = captured.privateContext.fairlight.targets.filter((target) => target.kind === "clip");
    if (clips.some((target) => typeof target.sourcePath !== "string" || !target.sourcePath
      || target.sourceStartFrame === null || target.sourceEndFrameExclusive === null
      || target.sourceFrameRate === null || !Array.isArray(target.linkedItemIds))) {
      stale("Fairlight synchronization lacks exact source-range, rate, path, or linked-topology custody");
    }
  }
  return captured;
}

/** Build only explicitly enabled Fairlight packets for the signed production carrier. */
export function createFairlightPreparedActionBuilderContributions({
  liveInspectionService,
  artifactCustody = null,
  secretDir = null,
  authoritativeActionInputSchemas = {},
  enabledActionIds = new Set(FAIRLIGHT_PREPARED_ACTION_IDS),
} = {}) {
  if (typeof liveInspectionService?.readWithMutationGuard !== "function") {
    throw new TypeError("Fairlight prepared contributions require SDK live-inspection authority.");
  }
  if (!(enabledActionIds instanceof Set) || [...enabledActionIds].some((actionId) => !FAIRLIGHT_PREPARED_ACTION_IDS.includes(actionId))) {
    throw new TypeError("Enabled Fairlight prepared actions must be an exact subset of the reviewed packet.");
  }
  const contributions = Object.fromEntries([...enabledActionIds].sort().map((actionId) => {
    const metadata = CUTAGENT_PREPARED_ACTION_ACTION_METADATA[actionId];
    if (!metadata || !new Set(["read", "mutation"]).has(metadata.operationClass)) {
      throw new TypeError(`Fairlight prepared action is absent from authoritative metadata: ${actionId}`);
    }
    const actionSchema = authoritativeActionInputSchemas[actionId] ?? null;
    if (actionSchema !== null && typeof actionSchema?.parse !== "function") {
      throw new TypeError(`Fairlight prepared action input schema is invalid: ${actionId}`);
    }
    const rawAudioTrackBinding = RAW_AUDIO_TRACK_BINDING_BY_ACTION.get(actionId) ?? null;
    const rawAudioClipBinding = RAW_AUDIO_CLIP_BINDING_BY_ACTION.get(actionId) ?? null;
    const carrierOwnedPublicBinding = rawAudioTrackBinding !== null || rawAudioClipBinding !== null;
    const inputSchema = Object.freeze({parse(raw) {
      if (carrierOwnedPublicBinding) {
        if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new TypeError("Public Fairlight input must be an object.");
        if (Object.hasOwn(raw, "actionInput") || Object.hasOwn(raw, "carrierBinding")) {
          throw new TypeError("Public Fairlight input cannot provide internal carrier binding fields.");
        }
        const candidate = {...raw};
        if (rawAudioTrackBinding && candidate[rawAudioTrackBinding.selectorKey] === undefined
          && rawAudioTrackBinding.defaultTrackIndex !== undefined) {
          candidate[rawAudioTrackBinding.selectorKey] = rawAudioTrackBinding.defaultTrackIndex;
        }
        const normalized = actionSchema?.parse(candidate) ?? candidate;
        if (rawAudioClipBinding) {
          const selector = normalized[rawAudioClipBinding.selectorKey];
          if ((rawAudioClipBinding.required && selector === undefined)
            || (selector !== undefined && (typeof selector !== "string" || !selector))) {
            throw new TypeError("Public Fairlight audio-clip selector must be a non-empty string.");
          }
          return Object.freeze(normalized);
        }
        const hasPrimary = normalized[rawAudioTrackBinding.selectorKey] !== undefined;
        const hasAlternate = rawAudioTrackBinding.alternateSelectorKey !== undefined
          && normalized[rawAudioTrackBinding.alternateSelectorKey] !== undefined;
        if (hasPrimary === hasAlternate && rawAudioTrackBinding.alternateSelectorKey !== undefined) {
          throw new TypeError("Public Fairlight input must provide exactly one target selector.");
        }
        if ((!Number.isInteger(normalized[rawAudioTrackBinding.selectorKey])
            || normalized[rawAudioTrackBinding.selectorKey] < 1)
          && !hasAlternate) {
          throw new TypeError("Public Fairlight audio-track selector must be a positive integer.");
        }
        if (hasAlternate && (typeof normalized[rawAudioTrackBinding.alternateSelectorKey] !== "string"
          || !normalized[rawAudioTrackBinding.alternateSelectorKey])) {
          throw new TypeError("Public Fairlight bus selector must be a non-empty string.");
        }
        return Object.freeze(normalized);
      }
      const normalized = sdkFairlightPreparedOperationInputSchema.parse(raw);
      return Object.freeze({actionInput: actionSchema?.parse(normalized.actionInput) ?? normalized.actionInput, carrierBinding: normalized.carrierBinding});
    }});
    const mutationBinding = metadata.operationClass === "mutation" ? {
      minimumBinding: "project+timeline",
      async resolveReferencedPayloadDigests({request}) {
        const normalized = inputSchema.parse(request.input);
        if (carrierOwnedPublicBinding) return [];
        const declared = normalized.carrierBinding.referencedPayloadDigests;
        if (MANAGED_INPUT_ACTION_IDS.has(actionId) && declared.length === 0) throw new Error("Prepared Fairlight managed input omitted its content digest.");
        if (declared.length === 0) return [];
        if (typeof artifactCustody?.resolveReferencedPayloadDigests !== "function") throw new Error("Prepared Fairlight payload custody authority is unavailable.");
        const verified = await artifactCustody.resolveReferencedPayloadDigests({actionId, actionInput: structuredClone(normalized.actionInput), declaredDigests: [...declared], request: structuredClone(request)});
        if (!Array.isArray(verified) || !sameDigests(verified, declared)) throw new Error("Prepared Fairlight payload digest did not match managed artifact custody.");
        return [...verified];
      },
    } : null;
    const bounceCancellation = FAIRLIGHT_BOUNCE_ACTION_IDS.has(actionId) ? {
      async requestCancellation(context) {
        const files = cancellationFiles(secretDir, context.operationId);
        fs.mkdirSync(path.dirname(files.requestPath), {recursive: true, mode: 0o700});
        fs.writeFileSync(files.requestPath, "cancel\n", {encoding: "utf8", mode: 0o600});
        const confirmed = await waitForCancellationAcknowledgement(files);
        if (confirmed) {
          fs.rmSync(files.requestPath, {force: true});
          fs.rmSync(files.acknowledgedPath, {force: true});
        }
        return confirmed
          ? {confirmed: true, possibleMutation: "possible", usage: "consumed", readbackRequired: true}
          : {confirmed: false, reason: "The Fairlight bounce runtime did not confirm render cancellation."};
      },
    } : {};
    return [actionId, createSdkPreparedActionBuilderContribution({
      inputSchema,
      ...(mutationBinding ? {mutationBinding} : {}),
      ...bounceCancellation,
      async captureRequestBinding({context, input}) {
        const normalized = inputSchema.parse(input);
        const captured = carrierOwnedPublicBinding
          ? rawAudioTrackBinding
            ? await captureCurrentAudioTrackBinding(liveInspectionService, normalized, actionId, rawAudioTrackBinding)
            : await captureCurrentAudioClipBinding(liveInspectionService, normalized, actionId, rawAudioClipBinding)
          : await captureLiveBinding(
            liveInspectionService,
            normalized.carrierBinding,
            actionId,
          );
        if (metadata.operationClass !== "mutation") return captured;
        if (!FAIRLIGHT_BOUNCE_ACTION_IDS.has(actionId)) return captured;
        const files = cancellationFiles(secretDir, context.operationId);
        fs.rmSync(files.requestPath, {force: true});
        fs.rmSync(files.acknowledgedPath, {force: true});
        return Object.freeze({
          ...captured,
          privateContext: {
            ...captured.privateContext,
            fairlight: {...captured.privateContext.fairlight, cancellation: files},
          },
        });
      },
    })];
  }));
  contributions[FAIRLIGHT_PLAN_ACTION_ID] = createSdkPreparedActionBuilderContribution({
    inputSchema: sdkFairlightPlanInputSchema,
    mutationBinding: Object.freeze({minimumBinding: "project+timeline", referencedPayloadDigests: Object.freeze([])}),
    async captureRequestBinding({context, input}) {
      const captured = await capturePlanBinding(liveInspectionService, input);
      return input.changes.some((change) => change.kind === "loudness")
        ? withLoudnessAnalysisArtifact(captured, reserveLoudnessAnalysisArtifact(artifactCustody, context, FAIRLIGHT_PLAN_ACTION_ID))
        : captured;
    },
  });
  return Object.freeze(contributions);
}

/** Retained for isolated evaluator fixtures. */
export const buildEvaluationFairlightPreparedActionContributions =
  createFairlightPreparedActionBuilderContributions;
