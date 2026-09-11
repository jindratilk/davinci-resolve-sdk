import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { ensureCanonicalPrivateDirectory, writePrivateJsonDurableAtomic } from "./private-storage.js";
import { sdkWorkflowSnapshotSchema } from "../contracts/generated/sdk-operations.js";
import { sdkManagedTimelineExportSchema, sdkManagedTimelinePreviewSchema } from "../contracts/generated/sdk-runtime.js";
import { CUTAGENT_SDK_ACTION_SCHEMA_DIGEST } from "../contracts/generated/sdk-operation-actions.js";
import { getSdkOwnerSession } from "./sdk-owner-session-context.js";
import { readLegacySdkPublicFailure } from "./sdk-legacy-public-failure.js";
import { sdkOperationPostTimelineRevision } from "./sdk-operation-terminal.js";

const opaque = (prefix) => `${prefix}${crypto.randomUUID()}`;
const terminalOperationStatuses = new Set(["succeeded", "failed", "cancelled", "partially_applied", "verification_failed", "recovery_failed"]);
const SAFE_UNATTACHED_STEP_AGE_MS = 23 * 60 * 60 * 1_000;
const WORKFLOW_JOURNAL_RETENTION_MS = 30 * 24 * 60 * 60 * 1_000;
const MANAGED_INSPECTION_PHASE_TIMEOUT_MS = 60_000;
const canonical = (value) => JSON.stringify(value, (_key, nested) => nested && typeof nested === "object" && !Array.isArray(nested)
  ? Object.fromEntries(Object.entries(nested).sort(([left], [right]) => left.localeCompare(right))) : nested);
const sha256 = (value) => `sha256:${crypto.createHash("sha256").update(canonical(value)).digest("hex")}`;
const sameFrameRate = (left, right) => Boolean(left && right
  && left.numerator === right.numerator && left.denominator === right.denominator
  && left.nominalTimebase === right.nominalTimebase);
const managedRecordDuration = (sourceStartFrame, sourceEndExclusiveFrame, sourceFrameRate, timelineFrameRate) => {
  if (!Number.isSafeInteger(sourceStartFrame) || !Number.isSafeInteger(sourceEndExclusiveFrame)
    || sourceEndExclusiveFrame <= sourceStartFrame
    || ![sourceFrameRate?.numerator, sourceFrameRate?.denominator, timelineFrameRate?.numerator, timelineFrameRate?.denominator]
      .every((value) => Number.isSafeInteger(value) && value > 0)) return null;
  const numerator = BigInt(sourceEndExclusiveFrame - sourceStartFrame)
    * BigInt(timelineFrameRate.numerator) * BigInt(sourceFrameRate.denominator);
  const denominator = BigInt(timelineFrameRate.denominator) * BigInt(sourceFrameRate.numerator);
  const rounded = (2n * numerator + denominator) / (2n * denominator);
  const result = Number(rounded > 0n ? rounded : 1n);
  return Number.isSafeInteger(result) ? result : null;
};
const protectedSnapshot = (snapshot, excludedIds) => ({
  project: snapshot.project, timeline: snapshot.timeline, frameRate: snapshot.frameRate, start: snapshot.start,
  markers: (snapshot.markers ?? []).map(({ snapshotRevision: _revision, ...marker }) => marker),
  tracks: snapshot.tracks.map((track) => ({ type: track.type, index: track.index, name: track.name, enabled: track.enabled, locked: track.locked,
    clips: track.clips.filter((clip) => !excludedIds.has(clip.id)).map(({ snapshotId: _snapshotId, snapshotTrackId: _trackId, snapshotRevision: _revision, ...clip }) => clip) })),
});
const protectedSnapshotComponentDigests = (snapshot, excludedIds) => {
  const value = protectedSnapshot(snapshot, excludedIds);
  return {
    project: sha256(value.project), timeline: sha256(value.timeline), frameRate: sha256(value.frameRate), start: sha256(value.start),
    markers: sha256(value.markers),
    trackProperties: sha256(value.tracks.map(({ clips: _clips, ...track }) => track)),
    clips: sha256(value.tracks.map((track) => ({ type: track.type, index: track.index, clips: track.clips }))),
  };
};
const managedEvidence = (summary, value, modality = "structural") => ({ modality, summary, digest: sha256(value) });
const managedInspectionDeadline = () => Date.now() + MANAGED_INSPECTION_PHASE_TIMEOUT_MS;
const isCancellationOrTimeout = (error) => error?.name === "AbortError" || error?.name === "TimeoutError";
const operationResultValues = (operation) => {
  const value = operation?.public?.result?.value;
  if (!value || typeof value !== "object") return [];
  return Array.isArray(value.results) ? value.results : [value];
};
const chunksOf = (values, size) => Array.from({ length: Math.ceil(values.length / size) }, (_, index) => values.slice(index * size, (index + 1) * size));
const sameManagedAssetCustody = (left, right) => {
  if (!left || !right) return left === right;
  return canonical(left.assets.map(({ id, fingerprint }) => ({ id, fingerprint })))
    === canonical(right.assets.map(({ id, fingerprint }) => ({ id, fingerprint })));
};

/**
 * Read-only ownership seam used before the operation authority exists. The
 * workflow journal is the durable source of truth for account ownership; a
 * checkpoint record must never be allowed to declare that ownership itself.
 */
export function createSdkWorkflowOwnershipResolver({ storageDir, clock = Date.now }) {
  const root = ensureCanonicalPrivateDirectory(storageDir, { label: "SDK workflow authority directory" });
  const file = path.join(root, "sdk-workflows-v1.json");
  return Object.freeze({
    assertOwnedBinding({ accountFingerprint, workflowId, projectId, timelineId }) {
      if (![accountFingerprint, workflowId, projectId, timelineId].every((value) => typeof value === "string" && value)) {
        throw Object.assign(new Error("Workflow ownership binding is incomplete."), { code: "INVALID_REQUEST" });
      }
      let journal;
      try {
        journal = JSON.parse(fs.readFileSync(file, "utf8"));
      } catch {
        throw Object.assign(new Error("Workflow ownership is unavailable."), { code: "OPERATION_EXPIRED" });
      }
      const record = journal?.version === 1 ? journal.workflows?.[workflowId] : null;
      const binding = record?.public?.binding;
      if (!record || record.accountFingerprint !== accountFingerprint
        || !binding || binding.projectId !== projectId || binding.timelineId !== timelineId
        || !Number.isFinite(Date.parse(record.public?.retentionExpiresAt))
        || Date.parse(record.public.retentionExpiresAt) <= clock()) {
        throw Object.assign(new Error("Workflow is unavailable."), { code: "OPERATION_EXPIRED" });
      }
      return Object.freeze({
        authority: "sdk_workflow_account_binding_v1",
        workflowId,
        projectId,
        timelineId,
      });
    },
  });
}

export function createSdkWorkflowAuthority({ storageDir, operationAuthority, checkpointService, liveInspectionService, persistState = writePrivateJsonDurableAtomic, recoveryCrashInjector = null, clock = Date.now }) {
  for (const method of ["inspectOwned", "findOwnedByIdempotency", "retainForWorkflow", "get", "cancel"]) {
    if (typeof operationAuthority?.[method] !== "function") {
      throw new Error(`SDK workflow authority requires operationAuthority.${method}().`);
    }
  }
  const nowIso = () => new Date(clock()).toISOString();
  const root = ensureCanonicalPrivateDirectory(storageDir, { label: "SDK workflow authority directory" });
  const file = path.join(root, "sdk-workflows-v1.json");
  const admittingTargets = new Set();
  const admittingIdempotency = new Map();
  const recoveryLocks = new Map();
  const managedExecutions = new Map();
  const managedPreviewEvidence = new Map();
  let state = { version: 1, workflows: {}, idempotency: {}, checkpointPrunes: [], managedOwnerships: {} };
  if (fs.existsSync(file)) {
    state = JSON.parse(fs.readFileSync(file, "utf8"));
    state.checkpointPrunes ??= [];
    state.managedOwnerships ??= {};
    for (const record of Object.values(state.workflows ?? {})) {
      if (record.public?.failure) record.public.failure = readLegacySdkPublicFailure(record.public.failure);
      record.public.retentionExpiresAt ??= new Date(Date.parse(record.public.updatedAt) + WORKFLOW_JOURNAL_RETENTION_MS).toISOString();
      record.public.authorityKind ??= record.managedClaim || record.public.binding?.managedClaim ? "managed" : "generic";
      if (!record.managedClaim && record.public.binding?.managedClaim) { record.managedClaim = record.public.binding.managedClaim; delete record.public.binding.managedClaim; }
    }
  }
  const saveState = (next) => persistState(file, next);
  const expireRecords = () => {
    const expired = Object.values(state.workflows).filter((record) => Date.parse(record.public.retentionExpiresAt) <= clock());
    if (expired.length === 0) return;
    const next = structuredClone(state);
    for (const record of expired) {
      const workflowId = record.public.workflowId;
      delete next.workflows[workflowId];
      for (const [key, value] of Object.entries(next.idempotency)) if (value === workflowId) delete next.idempotency[key];
      if (!next.checkpointPrunes.includes(workflowId)) next.checkpointPrunes.push(workflowId);
    }
    saveState(next);
    state = next;
  };
  let checkpointCleanup = null;
  const drainCheckpointPrunes = () => (checkpointCleanup ??= (async () => {
    expireRecords();
    for (const workflowId of [...state.checkpointPrunes]) {
      try {
        await checkpointService.pruneSessionCheckpoints?.({ session: { id: workflowId } });
      } catch {
        continue;
      }
      const next = structuredClone(state);
      next.checkpointPrunes = next.checkpointPrunes.filter((candidate) => candidate !== workflowId);
      saveState(next);
      state = next;
    }
  })().finally(() => { checkpointCleanup = null; }));
  const owned = (workflowId, accountFingerprint) => {
    expireRecords();
    const record = state.workflows[workflowId];
    const contextualOwnerSessionId = getSdkOwnerSession()?.id;
    if (!record
      || record.accountFingerprint !== accountFingerprint
      || (contextualOwnerSessionId !== undefined && (record.ownerSessionId ?? null) !== contextualOwnerSessionId)) {
      throw Object.assign(new Error("Workflow is unavailable."), { code: "OPERATION_EXPIRED" });
    }
    return record;
  };
  const publicSnapshot = (record) => sdkWorkflowSnapshotSchema.parse(record.public);
  const reservationIsExpired = (record, stepName, timestampKey = "reservedAt") => {
    const timestamp = Date.parse(record.stepReservations?.[stepName]?.[timestampKey] ?? record.public.updatedAt);
    return !Number.isFinite(timestamp) || clock() - timestamp >= SAFE_UNATTACHED_STEP_AGE_MS;
  };
  const operationMatchesReservation = (record, step, operation) => {
    const input = operation?.private?.normalizedInput;
    const reservation = record.stepReservations?.[step.name];
    const representative = input?.moves?.[0] ?? input?.removals?.[0] ?? input?.impacts?.[0] ?? input;
    const bindingInput = representative?.intent ?? representative;
    const projectId = input?.projectId ?? input?.impact?.intent?.projectId ?? bindingInput?.projectId;
    const timelineId = input?.timelineId ?? input?.impact?.intent?.timelineId ?? bindingInput?.timelineId;
    const timelineRevision = input?.timelineRevision ?? input?.precondition ?? input?.impact?.intent?.timelineRevision ?? bindingInput?.timelineRevision;
    const managedPreparationMatches = !record.managedClaim || Boolean(reservation?.expectedActionId && reservation?.expectedInputDigest
      && operation.public.actionId === reservation.expectedActionId && sha256(input) === reservation.expectedInputDigest);
    return Boolean(input && managedPreparationMatches
      && projectId === record.public.binding.projectId && timelineId === record.public.binding.timelineId
      && timelineRevision === record.currentRevision
      && operation.public.idempotency?.key === step.idempotencyKey);
  };
  const sameWorkflowBinding = (left, right) => left.projectId === right.projectId
    && left.timelineId === right.timelineId && left.revision === right.revision;
  const scopesOverlap = (left, right) => left.kind === "whole_timeline" || right.kind === "whole_timeline"
    || (left.startFrame < right.endExclusiveFrame && right.startFrame < left.endExclusiveFrame);
  const ownershipKey = (accountFingerprint, ownershipId) => `${accountFingerprint}:${ownershipId}`;
  const assertManagedClaimAvailable = (accountFingerprint, binding, claim) => {
    if (!claim) return null;
    const key = ownershipKey(accountFingerprint, claim.ownershipId);
    const previous = state.managedOwnerships[key] ?? null;
    if (previous && previous.status !== "active" && previous.status !== "restored") {
      throw Object.assign(new Error("Managed ownership has unresolved provisional or recovery-required state."), { code: "INVALID_REQUEST" });
    }
    if (previous && (previous.projectId !== binding.projectId || previous.timelineId !== binding.timelineId
      || JSON.stringify(previous.scope) !== JSON.stringify(claim.scope))) {
      throw Object.assign(new Error("Managed ownership cannot be rebound to another project, timeline, or scope."), { code: "INVALID_REQUEST" });
    }
    for (const [candidateKey, candidate] of Object.entries(state.managedOwnerships)) {
      if (candidateKey === key || candidate.accountFingerprint !== accountFingerprint || candidate.projectId !== binding.projectId
        || candidate.timelineId !== binding.timelineId || candidate.status === "restored") continue;
      if (scopesOverlap(candidate.scope, claim.scope)) throw Object.assign(new Error("Managed ownership overlaps another active managed scope."), { code: "INVALID_REQUEST" });
    }
    return { key, previous };
  };
  const managedExportBlockers = (blockers) => sdkManagedTimelineExportSchema.parse({
    status: "blocked", dialect: "cutagent.managed-timeline", version: 1, document: null,
    blockers: blockers.sort((left, right) => (left.key ?? "").localeCompare(right.key ?? "") || left.code.localeCompare(right.code)),
  });
  const exportManaged = async ({ accountFingerprint, accessToken, request, deadlineAtMs = null, signal = null }) => {
    const inspectionOptions = { accessToken, deadlineAtMs: deadlineAtMs ?? managedInspectionDeadline(), signal };
    const snapshot = await liveInspectionService.read({
      operation: "timeline.snapshot", projectId: request.projectId, timelineId: request.timelineId,
    }, inspectionOptions);
    const blockers = [];
    if (snapshot.project.id !== request.projectId || snapshot.timeline.id !== request.timelineId || snapshot.revision !== request.revision) {
      blockers.push({code: "stale_revision", message: "The timeline export snapshot revision is no longer current."});
    }
    const ownership = state.managedOwnerships[ownershipKey(accountFingerprint, request.ownershipId)] ?? null;
    if (ownership && (ownership.status !== "active" && ownership.status !== "restored")) {
      blockers.push({code: "protected_state_unproven", message: "Managed ownership requires verified recovery before export."});
    }
    if (ownership && (ownership.projectId !== request.projectId || ownership.timelineId !== request.timelineId
      || JSON.stringify(ownership.scope) !== JSON.stringify(request.scope))) {
      blockers.push({code: "ownership_overlap", message: "Managed ownership is bound to another project, timeline, or scope."});
    }
    if (request.selection.kind === "existing_ownership" && !ownership) {
      blockers.push({code: "ambiguous_identity", message: "Existing managed ownership has no durable author-key mapping."});
    }
    if (request.selection.kind === "existing_ownership" && ownership
      && !/^sha256:[a-f0-9]{64}$/.test(ownership.managedAffectedStateDigest ?? "")) {
      blockers.push({code: "protected_state_unproven", message: "Existing managed ownership lacks its protected-family baseline."});
    }
    if (request.selection.kind === "adopt" && ownership) {
      blockers.push({code: "ownership_overlap", message: "First-adoption export cannot replace existing managed ownership."});
    }
    for (const [candidateKey, candidate] of Object.entries(state.managedOwnerships)) {
      if (candidateKey === ownershipKey(accountFingerprint, request.ownershipId) || candidate.accountFingerprint !== accountFingerprint
        || candidate.projectId !== request.projectId || candidate.timelineId !== request.timelineId || candidate.status === "restored") continue;
      if (scopesOverlap(candidate.scope, request.scope)) blockers.push({code: "ownership_overlap", message: "The export scope overlaps another managed ownership."});
    }
    const rows = snapshot.tracks.flatMap((track) => track.clips.map((clip) => ({track, clip})));
    if (snapshot.tracks.some((track) => track.enabled === null || track.locked === null)) {
      blockers.push({code: "protected_state_unproven", message: "Timeline track properties are unavailable."});
    }
    if (rows.some(({clip}) => clip.id === null || clip.linkedItemIds === null)) {
      blockers.push({code: "protected_state_unproven", message: "Timeline item or link identity is unavailable."});
    }
    if (request.scope.kind === "region") for (const {clip} of rows) {
      if ((clip.recordRange.start < request.scope.startFrame && clip.recordRange.endExclusive > request.scope.startFrame)
        || (clip.recordRange.start < request.scope.endExclusiveFrame && clip.recordRange.endExclusive > request.scope.endExclusiveFrame)) {
        blockers.push({code: "scope_crossing", message: `Clip ${clip.name} crosses the export boundary.`});
      }
    }
    const bindings = request.selection.kind === "existing_ownership"
      ? (ownership?.elementMappings ?? []).map((entry) => ({key: entry.key, timelineItemId: entry.timelineItemId}))
      : request.selection.clips;
    if (bindings.length > 32) {
      blockers.push({code: "unsupported_change", message: "Managed timeline dialect v1 exports at most 32 authored clip placements."});
    }
    if (new Set(bindings.map((entry) => entry.key)).size !== bindings.length
      || new Set(bindings.map((entry) => entry.timelineItemId)).size !== bindings.length) {
      blockers.push({code: "ambiguous_identity", message: "Author keys and live adoption identities must be unique."});
    }
    if (request.selection.kind === "existing_ownership") {
      const managedKeys = (ownership?.managedElements ?? []).map((entry) => entry.key).sort();
      const mappedKeys = bindings.map((entry) => entry.key).sort();
      if (managedKeys.length !== mappedKeys.length || JSON.stringify(managedKeys) !== JSON.stringify(mappedKeys)) {
        blockers.push({code: "ambiguous_identity", message: "Durable author keys and managed element mappings disagree."});
      }
    }
    const selected = [];
    const affectedIds = new Set();
    for (const binding of [...bindings].sort((left, right) => left.key.localeCompare(right.key))) {
      const matches = rows.filter(({clip}) => clip.id === binding.timelineItemId);
      if (matches.length !== 1 || matches[0].track.type !== "video") {
        blockers.push({code: "ambiguous_identity", key: binding.key, message: `Author key ${binding.key} has no exact video item.`});
        continue;
      }
      const {track, clip} = matches[0];
      if (!clip.sourceRange || !clip.sourceFrameRate || !clip.mediaPoolItemId || clip.linkedItemIds === null) {
        blockers.push({code: "protected_state_unproven", key: binding.key, message: `Author key ${binding.key} lacks source, Media Pool, or link custody.`});
        continue;
      }
      const expectedRecordDuration = managedRecordDuration(clip.sourceRange.start, clip.sourceRange.endExclusive,
        clip.sourceFrameRate, snapshot.frameRate);
      if (expectedRecordDuration === null
        || clip.recordRange.endExclusive - clip.recordRange.start !== expectedRecordDuration) {
        blockers.push({code: "unsupported_change", key: binding.key, message: `Author key ${binding.key} has retimed source and record durations that dialect v1 cannot represent.`});
        continue;
      }
      if (request.scope.kind === "region"
        && (clip.recordRange.start < request.scope.startFrame || clip.recordRange.endExclusive > request.scope.endExclusiveFrame)) {
        blockers.push({code: "scope_crossing", key: binding.key, message: `Author key ${binding.key} is outside the export region.`});
        continue;
      }
      const linked = clip.linkedItemIds.map((id) => rows.filter((row) => row.clip.id === id));
      if (linked.some((matchesForId) => matchesForId.length !== 1)
        || linked.some(([row]) => row.track.type !== "audio" || row.clip.linkedItemIds?.length !== 1 || row.clip.linkedItemIds[0] !== clip.id)
        || linked.length > 1) {
        blockers.push({code: "protected_state_unproven", key: binding.key, message: `Author key ${binding.key} has an unsupported linked-item closure.`});
        continue;
      }
      const linkedAudio = linked[0]?.[0] ?? null;
      if (linkedAudio && (linkedAudio.clip.mediaPoolItemId !== clip.mediaPoolItemId
        || linkedAudio.clip.recordRange.start !== clip.recordRange.start
        || linkedAudio.clip.recordRange.endExclusive !== clip.recordRange.endExclusive
        || linkedAudio.clip.sourceRange?.start !== clip.sourceRange.start
        || linkedAudio.clip.sourceRange?.endExclusive !== clip.sourceRange.endExclusive
        || !sameFrameRate(linkedAudio.clip.sourceFrameRate, clip.sourceFrameRate))) {
        blockers.push({code: "protected_state_unproven", key: binding.key, message: `Author key ${binding.key} has mismatched linked-audio placement or source state.`});
        continue;
      }
      affectedIds.add(clip.id);
      for (const id of clip.linkedItemIds) affectedIds.add(id);
      selected.push({binding, track, clip, linkedAudio});
    }
    let attestation = null;
    try {
      attestation = await liveInspectionService.attestManagedProtectedState({operation: "managed.protected",
        projectId: request.projectId, timelineId: request.timelineId, timelineRevision: snapshot.revision,
        affectedItemIds: [...affectedIds].sort()}, inspectionOptions);
      if (request.selection.kind === "adopt" && affectedIds.size > 0 && attestation.affectedProtectedStateEmpty !== true) {
        blockers.push({code: "protected_state_unproven", message: "First adoption would take ownership of authored protected state."});
      }
      if (request.selection.kind === "existing_ownership" && ownership?.managedAffectedStateDigest
        && attestation.affectedStateDigest !== ownership.managedAffectedStateDigest) {
        blockers.push({code: "protected_state_unproven", message: "Managed protected-family state changed after ownership was verified."});
      }
    } catch (error) {
      if (isCancellationOrTimeout(error)) throw error;
      blockers.push({code: "protected_state_unproven", message: "The runtime could not attest every protected timeline family."});
    }
    const assets = [];
    let offset = 0; let mediaRevision = null;
    do {
      const page = await liveInspectionService.read({operation: "mediaPool.page", projectId: request.projectId,
        offset, pageSize: 32, expectedRevision: mediaRevision, search: null}, inspectionOptions);
      mediaRevision ??= page.revision;
      assets.push(...page.assets);
      offset = page.nextOffset;
    } while (offset !== null);
    const elements = [];
    const resolvedAssets = new Map();
    for (const {binding, track, clip, linkedAudio} of selected) {
      const matches = assets.filter((asset) => asset.id === clip.mediaPoolItemId);
      if (matches.length !== 1) {
        blockers.push({code: "ambiguous_identity", key: binding.key, message: `Author key ${binding.key} has no unique Media Pool asset.`});
        continue;
      }
      const asset = matches[0];
      resolvedAssets.set(asset.id, asset);
      elements.push({key: binding.key, assetId: asset.id, assetName: asset.name, assetRevision: asset.assetCustodyRevision,
        videoTrack: track.index, audioTrack: linkedAudio?.track.index ?? null, atFrame: clip.recordRange.start,
        sourceStartFrame: clip.sourceRange.start, sourceEndExclusiveFrame: clip.sourceRange.endExclusive,
        sourceFrameRate: clip.sourceFrameRate,
        linkedAudio: linkedAudio ? "include" : "exclude", adoptTimelineItemId: request.selection.kind === "adopt" ? clip.id : null});
    }
    if (blockers.length) return managedExportBlockers(blockers);
    const excluded = new Set(affectedIds);
    const protectedStateDigest = sha256({timeline: protectedSnapshot(snapshot, excluded), protectedFamilies: attestation.protectedStateDigest});
    return sdkManagedTimelineExportSchema.parse({status: "ready", dialect: "cutagent.managed-timeline", version: 1,
      program: {projectId: request.projectId, timelineId: request.timelineId, revision: snapshot.revision,
        ownershipId: request.ownershipId, scope: request.scope, timelineFrameRate: snapshot.frameRate, elements}, assets: [...resolvedAssets.values()],
      coverage: {represented: ["clip_placement/v1"], preservedButNotRepresented: ["unmanaged_clips", "track_properties", "markers", "fusion", "color", "fairlight", "retime", "transitions", "effects", "captions"], protectedStateDigest}, blockers: []});
  };
  const previewManaged = async ({ accountFingerprint, accessToken, sdkSessionId = null, program, ownershipOverride = null, deadlineAtMs = null, signal = null }) => {
    const inspectionOptions = { accessToken, deadlineAtMs: deadlineAtMs ?? managedInspectionDeadline(), signal };
    const snapshot = await liveInspectionService.read({
      operation: "timeline.snapshot", projectId: program.projectId, timelineId: program.timelineId,
    }, inspectionOptions);
    const blockers = [];
    if (snapshot.project.id !== program.projectId || snapshot.timeline.id !== program.timelineId || snapshot.revision !== program.revision) {
      blockers.push({ code: "stale_revision", message: "The managed program revision is no longer current." });
    }
    if (!sameFrameRate(snapshot.frameRate, program.timelineFrameRate)) {
      blockers.push({ code: "stale_revision", message: "The managed program Timeline frame rate is no longer current." });
    }
    const key = ownershipKey(accountFingerprint, program.ownershipId);
    const ownership = ownershipOverride ?? state.managedOwnerships[key] ?? null;
    if (ownership && ownership.status !== "active" && ownership.status !== "restored") {
      blockers.push({ code: "protected_state_unproven", message: "Managed ownership is provisional or requires verified recovery before reuse." });
    }
    if (ownership && (ownership.projectId !== program.projectId || ownership.timelineId !== program.timelineId
      || JSON.stringify(ownership.scope) !== JSON.stringify(program.scope))) {
      blockers.push({ code: "ownership_overlap", message: "Managed ownership is already bound to another project, timeline, or scope." });
    }
    for (const [candidateKey, candidate] of Object.entries(state.managedOwnerships)) {
      if (candidateKey === key || candidate.accountFingerprint !== accountFingerprint || candidate.projectId !== program.projectId
        || candidate.timelineId !== program.timelineId || candidate.status === "restored") continue;
      if (scopesOverlap(candidate.scope, program.scope)) blockers.push({ code: "ownership_overlap", message: "The requested managed scope overlaps another ownership boundary." });
    }
    const clips = snapshot.tracks.flatMap((track) => track.clips.map((clip) => ({ track, clip })));
    if (snapshot.tracks.some((track) => track.enabled === null || track.locked === null)) blockers.push({ code: "protected_state_unproven", message: "Timeline track enabled or lock state is unavailable, so protected metadata cannot be proven." });
    if (clips.some(({ clip }) => clip.id === null)) blockers.push({ code: "protected_state_unproven", message: "A timeline item lacks durable identity, so protected-state closure cannot be proven." });
    if (clips.some(({ clip }) => clip.linkedItemIds === null)) blockers.push({ code: "protected_state_unproven", message: "Timeline linkage identities are unavailable, so protected-state closure cannot be proven." });
    if (program.scope.kind === "region") for (const { clip } of clips) {
      const range = clip.recordRange;
      if ((range.start < program.scope.startFrame && range.endExclusive > program.scope.startFrame)
        || (range.start < program.scope.endExclusiveFrame && range.endExclusive > program.scope.endExclusiveFrame)) {
        blockers.push({ code: "scope_crossing", message: `Clip ${clip.name} crosses the managed region boundary and is protected in full.` });
      }
    }
    const mappings = new Map((ownership?.elementMappings ?? []).map((entry) => [entry.key, entry.timelineItemId]));
    const priorElements = new Map((ownership?.managedElements ?? []).map((entry) => [entry.key, entry]));
    const desired = new Map(program.elements.map((element) => [element.key, element]));
    const drift = [];
    const positionMoveKeys = new Set();
    const attestationAffectedIds = new Set();
    let adoptionNeeded = false;
    for (const element of [...program.elements].sort((left, right) => left.key.localeCompare(right.key))) {
      const recordDuration = managedRecordDuration(element.sourceStartFrame, element.sourceEndExclusiveFrame,
        element.sourceFrameRate, program.timelineFrameRate);
      if (recordDuration === null) {
        blockers.push({ code: "unsupported_change", key: element.key, message: `Managed clip ${element.key} has an invalid source-to-record frame-rate conversion.` });
        continue;
      }
      const desiredEnd = element.atFrame + recordDuration;
      if (program.scope.kind === "region" && (element.atFrame < program.scope.startFrame || desiredEnd > program.scope.endExclusiveFrame)) {
        blockers.push({ code: "scope_crossing", key: element.key, message: `Managed clip ${element.key} is not wholly contained by its ownership region.` });
      }
      const mappedId = mappings.get(element.key) ?? element.adoptTimelineItemId;
      if (!mappedId) {
        drift.push({ kind: "create", key: element.key, summary: `Create managed clip ${element.key}.` });
        continue;
      }
      if (!mappings.has(element.key)) adoptionNeeded = true;
      const matches = clips.filter(({ clip }) => clip.id === mappedId);
      if (matches.length !== 1) {
        blockers.push({ code: "ambiguous_identity", key: element.key, message: `The authoritative identity for ${element.key} is absent or ambiguous.` });
        continue;
      }
      const { track, clip } = matches[0];
      for (const id of [mappedId, ...(clip.linkedItemIds ?? [])]) attestationAffectedIds.add(id);
      const linkedAudio = clip.linkedItemIds?.flatMap((linkedId) => clips.filter((candidate) => candidate.clip.id === linkedId && candidate.track.type === "audio")) ?? [];
      const allowedLinkedIds = new Set(linkedAudio.map((candidate) => candidate.clip.id));
      const extraLinkedIds = (clip.linkedItemIds ?? []).filter((linkedId) => !allowedLinkedIds.has(linkedId));
      const exactLinkedIdentityClosure = element.linkedAudio === "exclude" ? (clip.linkedItemIds ?? []).length === 0
        : (clip.linkedItemIds ?? []).length === 1 && linkedAudio.length === 1 && linkedAudio[0].track.index === element.audioTrack;
      if (!exactLinkedIdentityClosure || extraLinkedIds.length > 0 || linkedAudio.some((candidate) => candidate.clip.linkedItemIds === null || !candidate.clip.linkedItemIds.includes(mappedId)
        || candidate.clip.linkedItemIds.some((linkedId) => linkedId !== mappedId))) {
        blockers.push({ code: "protected_state_unproven", key: element.key, message: "Managed clip linkage contains an identity outside the exact permitted video and linked-audio closure." });
      }
      const linkedAudioExact = element.linkedAudio === "exclude" ? linkedAudio.length === 0
        : element.audioTrack !== null && linkedAudio.length === 1 && linkedAudio[0].track.index === element.audioTrack
          && linkedAudio[0].clip.mediaPoolItemId === element.assetId
          && linkedAudio[0].clip.recordRange.start === element.atFrame
          && linkedAudio[0].clip.recordRange.endExclusive === desiredEnd
          && linkedAudio[0].clip.sourceRange?.start === element.sourceStartFrame
          && linkedAudio[0].clip.sourceRange?.endExclusive === element.sourceEndExclusiveFrame
          && sameFrameRate(linkedAudio[0].clip.sourceFrameRate, element.sourceFrameRate);
      const linkedAudioPositionOnly = element.linkedAudio === "exclude" ? linkedAudio.length === 0
        : element.audioTrack !== null && linkedAudio.length === 1 && linkedAudio[0].track.index === element.audioTrack
          && linkedAudio[0].clip.mediaPoolItemId === element.assetId
          && linkedAudio[0].clip.recordRange.start === clip.recordRange.start
          && linkedAudio[0].clip.recordRange.endExclusive === clip.recordRange.endExclusive
          && linkedAudio[0].clip.sourceRange?.start === element.sourceStartFrame
          && linkedAudio[0].clip.sourceRange?.endExclusive === element.sourceEndExclusiveFrame
          && sameFrameRate(linkedAudio[0].clip.sourceFrameRate, element.sourceFrameRate);
      const exact = track.type === "video" && track.index === element.videoTrack
        && clip.recordRange.start === element.atFrame
        && clip.recordRange.endExclusive === desiredEnd
        && clip.mediaPoolItemId === element.assetId
        && clip.sourceRange?.start === element.sourceStartFrame
        && clip.sourceRange?.endExclusive === element.sourceEndExclusiveFrame
        && sameFrameRate(clip.sourceFrameRate, element.sourceFrameRate)
        && linkedAudioExact;
      const positionOnly = !exact
        && track.type === "video" && track.index === element.videoTrack
        && clip.recordRange.start !== element.atFrame
        && clip.recordRange.endExclusive - clip.recordRange.start === recordDuration
        && clip.mediaPoolItemId === element.assetId
        && clip.sourceRange?.start === element.sourceStartFrame
        && clip.sourceRange?.endExclusive === element.sourceEndExclusiveFrame
        && sameFrameRate(clip.sourceFrameRate, element.sourceFrameRate)
        && linkedAudioPositionOnly;
      if (positionOnly) positionMoveKeys.add(element.key);
      drift.push({ kind: exact ? "preserve" : "update", key: element.key, timelineItemId: mappedId, summary: exact ? `Preserve managed clip ${element.key}.` : `Managed clip ${element.key} differs from desired state.` });
      if (!exact && !positionOnly) {
        const affected = new Set([mappedId, ...(clip.linkedItemIds ?? [])]);
        for (const id of affected) attestationAffectedIds.add(id);
        const unsafe = clips.some((candidate) => !affected.has(candidate.clip.id) && candidate.clip.recordRange.start >= clip.recordRange.start && candidate.clip.recordRange.endExclusive <= clip.recordRange.endExclusive
          && (affected.size > 1 || (candidate.track.type === track.type && candidate.track.index === track.index)));
        if (unsafe) blockers.push({ code: "protected_state_unproven", key: element.key, message: "Exact replacement removal would share its selector range with protected timeline state." });
      }
    }
    for (const [mappedKey, timelineItemId] of [...mappings].sort(([left], [right]) => left.localeCompare(right))) {
      if (desired.has(mappedKey)) continue;
      drift.push({ kind: "remove", key: mappedKey, timelineItemId, summary: `Remove managed clip ${mappedKey}.` });
      const target = clips.find(({ clip }) => clip.id === timelineItemId);
      if (!target) blockers.push({ code: "ambiguous_identity", key: mappedKey, message: `The authoritative removal identity for ${mappedKey} is absent.` });
      else {
        const affected = new Set([timelineItemId, ...(target.clip.linkedItemIds ?? [])]);
        const priorElement = priorElements.get(mappedKey);
        if (!priorElement) blockers.push({ code: "protected_state_unproven", key: mappedKey, message: "Managed removal lacks its prior typed linked-media closure." });
        const linkedRows = [...affected].filter((id) => id !== timelineItemId).map((id) => clips.find((candidate) => candidate.clip.id === id)).filter(Boolean);
        const exactLinkedClosure = priorElement?.linkedAudio === "exclude" ? linkedRows.length === 0
          : linkedRows.length === 1 && linkedRows[0].track.type === "audio" && linkedRows[0].track.index === priorElement?.audioTrack
            && linkedRows[0].clip.linkedItemIds?.length === 1 && linkedRows[0].clip.linkedItemIds[0] === timelineItemId;
        if (!exactLinkedClosure) blockers.push({ code: "protected_state_unproven", key: mappedKey, message: "Managed removal linkage is outside its prior exact video and linked-audio closure." });
        for (const id of affected) attestationAffectedIds.add(id);
        const unsafe = clips.some(({ track, clip }) => !affected.has(clip.id) && clip.recordRange.start >= target.clip.recordRange.start && clip.recordRange.endExclusive <= target.clip.recordRange.endExclusive
          && (affected.size > 1 || (track.type === target.track.type && track.index === target.track.index)));
        if (unsafe) blockers.push({ code: "protected_state_unproven", key: mappedKey, message: "Exact non-ripple removal would share its selector range with protected timeline state." });
      }
    }
    let protectedFamilyAttestation = null;
    {
      try {
        protectedFamilyAttestation = await liveInspectionService.attestManagedProtectedState({ operation: "managed.protected",
          projectId: program.projectId, timelineId: program.timelineId, timelineRevision: snapshot.revision,
          affectedItemIds: [...attestationAffectedIds].sort() }, inspectionOptions);
        const admittedAffectedDigest = ownership?.managedAffectedStateDigest ?? null;
        if (attestationAffectedIds.size > 0 && admittedAffectedDigest && protectedFamilyAttestation.affectedStateDigest !== admittedAffectedDigest) {
          blockers.push({ code: "protected_state_unproven", message: "Managed replacement/removal would discard changed Fusion, Color, Fairlight, transition, effect, or caption state." });
        } else if (attestationAffectedIds.size > 0 && !admittedAffectedDigest && protectedFamilyAttestation.affectedProtectedStateEmpty !== true) {
          blockers.push({ code: "protected_state_unproven", message: "Managed adoption cannot prove the exact affected closure is free of authored Fusion, Color, Fairlight, transition, effect, or caption state." });
        } else if (attestationAffectedIds.size === 0 && protectedFamilyAttestation.affectedProtectedStateEmpty !== true) {
          blockers.push({ code: "protected_state_unproven", message: "The empty managed affected closure could not be proven free of protected state." });
        }
      } catch (error) {
        if (isCancellationOrTimeout(error)) throw error;
        blockers.push({ code: "protected_state_unproven", message: "The proprietary runtime could not attest every protected timeline family." });
      }
    }
    const mappedIds = new Set(mappings.values());
    const excludedManagedIds = new Set([...mappedIds, ...program.elements.map((element) => element.adoptTimelineItemId).filter(Boolean)]);
    for (const { clip } of clips) if (excludedManagedIds.has(clip.id)) for (const linkedId of clip.linkedItemIds ?? []) excludedManagedIds.add(linkedId);
    for (const { clip } of clips) {
      if (clip.id && mappedIds.has(clip.id)) continue;
      const range = clip.recordRange;
      const inside = program.scope.kind === "whole_timeline" || (range.start >= program.scope.startFrame && range.endExclusive <= program.scope.endExclusiveFrame);
      if (inside) drift.push({ kind: "preserve", key: `protected:${clip.id ?? clip.snapshotId}`, ...(clip.id ? { timelineItemId: clip.id } : {}), summary: `Preserve undeclared protected clip ${clip.name}.` });
    }
    drift.sort((left, right) => left.key.localeCompare(right.key) || left.kind.localeCompare(right.kind));
    const desiredStateDigest = sha256({ ownershipId: program.ownershipId, projectId: program.projectId, timelineId: program.timelineId, scope: program.scope, elements: program.elements });
    let managedAssetCustody = null;
    if (program.elements.length > 0) {
      try {
        managedAssetCustody = await liveInspectionService.captureManagedTimelineAssets({
          projectId: program.projectId,
          timelineId: program.timelineId,
          assetIds: program.elements.map((element) => element.assetId),
        }, inspectionOptions);
        const currentAssets = new Map(managedAssetCustody.assets.map((asset) => [asset.id, asset]));
        if (program.elements.some((element) => currentAssets.get(element.assetId)?.revision !== element.assetRevision)) {
          blockers.push({ code: "stale_revision", message: "A managed source asset changed after it was selected." });
        }
      } catch (error) {
        if (isCancellationOrTimeout(error)) throw error;
        blockers.push({ code: "stale_revision", message: "Managed source-asset custody changed before admission." });
      }
    }
    blockers.sort((left, right) => (left.key ?? "").localeCompare(right.key ?? "") || left.code.localeCompare(right.code) || left.message.localeCompare(right.message));
    const context = {
      currentRevision: snapshot.revision,
      ownershipGeneration: ownership?.generation ?? 0,
      ownershipDigest: sha256(ownership ?? null),
      capabilityDigest: `sha256:${CUTAGENT_SDK_ACTION_SCHEMA_DIGEST}`,
      protectedStateDigest: sha256({ timeline: protectedSnapshot(snapshot, excludedManagedIds), protectedFamilies: protectedFamilyAttestation?.protectedStateDigest ?? null }),
    };
    const contextDigest = sha256(context);
    const status = blockers.length ? "blocked" : drift.some((entry) => entry.kind !== "preserve") || adoptionNeeded || !ownership ? "ready" : "no_change";
    const base = { status, projectId: program.projectId, timelineId: program.timelineId, revision: snapshot.revision, ownershipId: program.ownershipId, scope: program.scope, desiredStateDigest, contextDigest, protectedStateDigest: context.protectedStateDigest, ownershipGeneration: context.ownershipGeneration, capabilityDigest: context.capabilityDigest, drift, blockers };
    const result = sdkManagedTimelinePreviewSchema.parse({ ...base, previewDigest: sha256(base) });
    managedPreviewEvidence.set(result.previewDigest, { protectedFamilyDigest: protectedFamilyAttestation?.protectedStateDigest ?? null,
      affectedStateDigest: protectedFamilyAttestation?.affectedStateDigest ?? null,
      affectedNativeItemIds: protectedFamilyAttestation?.privateAffectedNativeItemIds ?? null,
      affectedItemIds: [...attestationAffectedIds].sort(), positionMoveKeys: [...positionMoveKeys].sort(),
      snapshot: structuredClone(snapshot), protectedComponentDigests: protectedSnapshotComponentDigests(snapshot, excludedManagedIds),
      managedAssetCustody: structuredClone(managedAssetCustody) });
    return result;
  };
  const commitRecord = (record, change) => {
    const workflowId = record.public.workflowId;
    const next = structuredClone(state);
    const draft = next.workflows[workflowId];
    if (!draft) throw new Error("Workflow disappeared before durable state transition.");
    change(draft, next);
    draft.public.sequence += 1;
    draft.public.updatedAt = nowIso();
    draft.public.retentionExpiresAt = new Date(clock() + WORKFLOW_JOURNAL_RETENTION_MS).toISOString();
    draft.public = publicSnapshot(draft);
    saveState(next);
    state = next;
    return state.workflows[workflowId];
  };
  const mutate = (record, change) => publicSnapshot(commitRecord(record, change));
  const restoreManagedOwnership = (draft, next) => {
    if (!draft.managedOwnershipKey) return;
    if (draft.priorManagedOwnership) {
      next.managedOwnerships[draft.managedOwnershipKey] = structuredClone(draft.priorManagedOwnership);
      if (draft.priorManagedOwnership.verification) draft.public.managedState = {
        ownershipId: draft.priorManagedOwnership.ownershipId, generation: draft.priorManagedOwnership.generation,
        revision: draft.priorManagedOwnership.revision, desiredStateDigest: draft.priorManagedOwnership.desiredStateDigest,
        elements: draft.priorManagedOwnership.elementMappings ?? [], verification: draft.priorManagedOwnership.verification,
      }; else delete draft.public.managedState;
    } else {
      delete next.managedOwnerships[draft.managedOwnershipKey];
      delete draft.public.managedState;
    }
  };
  const advanceWorkflowRevision = (record, timelineRevision, stateHash = record.currentStateHash) => commitRecord(record, (draft) => {
    draft.currentRevision = timelineRevision;
    draft.currentStateHash = stateHash;
  });
  const restoreWorkflowStart = async (record, accessToken, expectedLiveRevision) => {
    if (typeof expectedLiveRevision !== "string") {
      throw Object.assign(new Error("Workflow recovery has no authoritative post-state revision."), {
        code: "WORKFLOW_RECOVERY_LINEAGE_UNPROVEN",
      });
    }
    const live = await liveInspectionService.readWorkflowBinding({
      operation: "timeline.snapshot",
      projectId: record.public.binding.projectId,
      timelineId: record.public.binding.timelineId,
    }, { accessToken });
    const exactLiveIdentity = live.projectId === record.public.binding.projectId
      && live.timelineId === record.public.binding.timelineId
      && live.nativeTimelineId === record.nativeTimelineId;
    if (record.recoveryIntent && exactLiveIdentity && live.revision === record.public.binding.revision) {
      const restoredStatus = await checkpointService.getStatus({ session: { id: record.public.workflowId }, accessToken });
      if (restoredStatus?.project_name !== live.projectName || restoredStatus?.timeline_name !== live.timelineName
        || restoredStatus?.timeline_id !== record.nativeTimelineId || restoredStatus?.state_hash !== record.startStateHash) {
        throw Object.assign(new Error("Recovered checkpoint restore does not match the workflow-start Project.db hash."), {
          code: "WORKFLOW_RESTORE_VERIFICATION_FAILED",
        });
      }
      const liveAfterRecoveredStatus = await liveInspectionService.readWorkflowBinding({
        operation: "timeline.snapshot", projectId: record.public.binding.projectId, timelineId: record.public.binding.timelineId,
      }, { accessToken });
      if (liveAfterRecoveredStatus.projectId !== record.public.binding.projectId
        || liveAfterRecoveredStatus.timelineId !== record.public.binding.timelineId
        || liveAfterRecoveredStatus.nativeTimelineId !== record.nativeTimelineId
        || liveAfterRecoveredStatus.revision !== record.public.binding.revision) {
        throw Object.assign(new Error("Live timeline changed while recovered restore truth was being verified."), {
          code: "WORKFLOW_RECOVERY_LINEAGE_UNPROVEN",
        });
      }
      record = advanceWorkflowRevision(record, record.public.binding.revision, record.startStateHash);
      return commitRecord(record, (draft) => { delete draft.recoveryIntent; });
    }
    if (!exactLiveIdentity || live.revision !== expectedLiveRevision) {
      throw Object.assign(new Error("Live timeline lineage changed outside the workflow before recovery."), {
        code: "WORKFLOW_RECOVERY_LINEAGE_UNPROVEN",
      });
    }
    const status = await checkpointService.getStatus({ session: { id: record.public.workflowId }, accessToken });
    if (status?.project_name !== live.projectName || status?.timeline_name !== live.timelineName
      || status?.timeline_id !== record.nativeTimelineId || typeof status?.state_hash !== "string"
      || (expectedLiveRevision === record.currentRevision && status.state_hash !== record.currentStateHash)) {
      throw Object.assign(new Error("Project DB lineage does not match the workflow recovery target."), {
        code: "WORKFLOW_RECOVERY_LINEAGE_UNPROVEN",
      });
    }
    const liveAfterStatus = await liveInspectionService.readWorkflowBinding({
      operation: "timeline.snapshot", projectId: record.public.binding.projectId, timelineId: record.public.binding.timelineId,
    }, { accessToken });
    if (liveAfterStatus.nativeTimelineId !== record.nativeTimelineId || liveAfterStatus.revision !== expectedLiveRevision) {
      throw Object.assign(new Error("Live timeline changed while recovery was being prepared."), {
        code: "WORKFLOW_RECOVERY_LINEAGE_UNPROVEN",
      });
    }
    if (record.currentRevision !== expectedLiveRevision) {
      record = advanceWorkflowRevision(record, expectedLiveRevision);
    }
    record = commitRecord(record, (draft) => {
      draft.recoveryIntent = { expectedLiveRevision, expectedStateHash: status.state_hash, phase: "prepared", preparedAt: nowIso() };
    });
    const restored = await checkpointService.restoreCheckpoint({
      session: { id: record.public.workflowId }, checkpointId: record.checkpointId, accessToken,
      expectedCurrentStateHash: record.recoveryIntent.expectedStateHash,
    });
    if (restored?.restored_on_disk !== true || restored?.reopened !== true
      || restored?.verified !== true || restored?.verification_status !== "verified") {
      throw Object.assign(new Error("Workflow checkpoint restore was not fully reopened and verified."), {
        code: "WORKFLOW_RESTORE_VERIFICATION_FAILED",
      });
    }
    recoveryCrashInjector?.("after_restore", record.public.workflowId);
    record = commitRecord(record, (draft) => { draft.recoveryIntent.phase = "restore_applied"; });
    const afterRestore = await liveInspectionService.readWorkflowBinding({
      operation: "timeline.snapshot",
      projectId: record.public.binding.projectId,
      timelineId: record.public.binding.timelineId,
    }, { accessToken });
    if (afterRestore.projectId !== record.public.binding.projectId
      || afterRestore.timelineId !== record.public.binding.timelineId
      || afterRestore.nativeTimelineId !== record.nativeTimelineId
      || afterRestore.revision !== record.public.binding.revision) {
      throw Object.assign(new Error("Checkpoint restore did not reproduce the workflow-start live timeline."), {
        code: "WORKFLOW_RESTORE_VERIFICATION_FAILED",
      });
    }
    const afterRestoreStatus = await checkpointService.getStatus({ session: { id: record.public.workflowId }, accessToken });
    if (afterRestoreStatus?.project_name !== afterRestore.projectName
      || afterRestoreStatus?.timeline_name !== afterRestore.timelineName
      || afterRestoreStatus?.timeline_id !== record.nativeTimelineId
      || afterRestoreStatus?.state_hash !== record.startStateHash) {
      throw Object.assign(new Error("Checkpoint restore did not reproduce the workflow-start Project.db hash."), {
        code: "WORKFLOW_RESTORE_VERIFICATION_FAILED",
      });
    }
    const liveAfterRestoreStatus = await liveInspectionService.readWorkflowBinding({
      operation: "timeline.snapshot", projectId: record.public.binding.projectId, timelineId: record.public.binding.timelineId,
    }, { accessToken });
    if (liveAfterRestoreStatus.projectId !== record.public.binding.projectId
      || liveAfterRestoreStatus.timelineId !== record.public.binding.timelineId
      || liveAfterRestoreStatus.nativeTimelineId !== record.nativeTimelineId
      || liveAfterRestoreStatus.revision !== record.public.binding.revision) {
      throw Object.assign(new Error("Live timeline changed while checkpoint restore truth was being verified."), {
        code: "WORKFLOW_RECOVERY_LINEAGE_UNPROVEN",
      });
    }
    record = advanceWorkflowRevision(record, record.public.binding.revision, record.startStateHash);
    return commitRecord(record, (draft) => { delete draft.recoveryIntent; });
  };
  const reconcileCancellation = async (record, assertRequestCurrent = () => {}) => {
    if (record.public.status !== "cancellation_requested") return record;
    const unresolved = record.public.steps.find((step) => step.operationId && !step.outcome);
    if (!unresolved?.operationId) return record;
    let operation;
    try { operation = operationAuthority.get({ accountFingerprint: record.accountFingerprint, operationId: unresolved.operationId }); }
    catch (error) {
      if (!reservationIsExpired(record, unresolved.name, "attachedAt")) throw error;
      mutate(record, (draft) => {
        draft.public.steps.find((step) => step.name === unresolved.name).outcome = "manual_recovery_required";
        draft.public.status = "manual_recovery_required";
        draft.public.manualRecoveryRequired = true;
      });
      return owned(record.public.workflowId, record.accountFingerprint);
    }
    if (!terminalOperationStatuses.has(operation.status)) {
      assertRequestCurrent();
      operation = await operationAuthority.cancel({ accountFingerprint: record.accountFingerprint, operationId: unresolved.operationId, assertRequestCurrent });
    }
    if (terminalOperationStatuses.has(operation.status)) {
      mutate(record, (draft) => {
        draft.public.steps.find((step) => step.operationId === unresolved.operationId).outcome = "cancellation_requested";
        draft.public.manualRecoveryRequired = operation.possibleMutation !== "none";
      });
    } else if (!record.public.manualRecoveryRequired) {
      mutate(record, (draft) => { draft.public.manualRecoveryRequired = operation.possibleMutation !== "none"; });
    }
    return owned(record.public.workflowId, record.accountFingerprint);
  };
  const ownsMutationTarget = (record) => {
    if (record.public.status === "checkpoint_pending" || record.public.status === "active") return true;
    if (record.public.status !== "cancellation_requested") return false;
    const unresolved = record.public.steps.find((step) => !step.outcome);
    if (!unresolved?.operationId) return Boolean(unresolved);
    try {
      const operation = operationAuthority.get({ accountFingerprint: record.accountFingerprint, operationId: unresolved.operationId });
      return !terminalOperationStatuses.has(operation.status);
    } catch { return true; }
  };
  const withRecoveryLease = async (workflowId, task) => {
    const previous = recoveryLocks.get(workflowId) ?? Promise.resolve();
    let release;
    const turn = new Promise((resolve) => { release = resolve; });
    const tail = previous.catch(() => {}).then(() => turn);
    recoveryLocks.set(workflowId, tail);
    await previous.catch(() => {});
    try { return await task(); }
    finally {
      release();
      if (recoveryLocks.get(workflowId) === tail) recoveryLocks.delete(workflowId);
    }
  };
  const authority = {
    exportManaged,
    previewManaged,
    async reconcileStartup() {
      await drainCheckpointPrunes();
      for (const initial of Object.values(state.workflows)) {
        let record = initial;
        if (record.public.status === "checkpoint_pending") {
          mutate(record, (draft, next) => {
            draft.public.status = "failed_before_mutation";
            restoreManagedOwnership(draft, next);
            if (!next.checkpointPrunes.includes(draft.public.workflowId)) next.checkpointPrunes.push(draft.public.workflowId);
          });
          record = owned(record.public.workflowId, record.accountFingerprint);
        }
        if (record.public.status === "active") for (const step of record.public.steps.filter((candidate) => !candidate.operationId && !candidate.outcome)) {
          let recovered = null;
          try { recovered = operationAuthority.findOwnedByIdempotency({ accountFingerprint: record.accountFingerprint, idempotencyKey: step.idempotencyKey }); }
          catch {
            mutate(record, (draft, next) => { draft.public.status = "manual_recovery_required"; draft.public.manualRecoveryRequired = true;
              if (draft.managedOwnershipKey && next.managedOwnerships[draft.managedOwnershipKey]) next.managedOwnerships[draft.managedOwnershipKey].status = "recovery_required"; });
            record = owned(record.public.workflowId, record.accountFingerprint); break;
          }
          if (!recovered) continue;
          if (!operationMatchesReservation(record, step, recovered)) {
            mutate(record, (draft, next) => { draft.public.status = "manual_recovery_required"; draft.public.manualRecoveryRequired = true;
              if (draft.managedOwnershipKey && next.managedOwnerships[draft.managedOwnershipKey]) next.managedOwnerships[draft.managedOwnershipKey].status = "recovery_required"; });
            record = owned(record.public.workflowId, record.accountFingerprint); break;
          }
          try { operationAuthority.retainForWorkflow({ accountFingerprint: record.accountFingerprint, operationId: recovered.public.operationId, retentionExpiresAt: record.public.retentionExpiresAt }); }
          catch { /* The durable correlation remains recovery-required below. */ }
          mutate(record, (draft) => { const target = draft.public.steps.find((candidate) => candidate.name === step.name);
            target.operationId = recovered.public.operationId; target.actionId = recovered.public.actionId;
            draft.stepReservations[step.name].attachedAt = nowIso(); });
          record = owned(record.public.workflowId, record.accountFingerprint);
        }
        if (record.public.status === "active" && record.managedOwnershipKey
          && state.managedOwnerships[record.managedOwnershipKey]?.status === "provisional") {
          const possibleMutation = record.public.steps.some((step) => step.operationId || step.outcome === "completed");
          mutate(record, (draft, next) => {
            if (possibleMutation) {
              draft.public.status = "manual_recovery_required";
              draft.public.manualRecoveryRequired = true;
              const ownership = next.managedOwnerships[draft.managedOwnershipKey];
              if (ownership?.workflowId === draft.public.workflowId) ownership.status = "recovery_required";
            } else {
              draft.public.status = "failed_before_mutation";
              restoreManagedOwnership(draft, next);
            }
          });
          record = owned(record.public.workflowId, record.accountFingerprint);
        }
        for (const step of record.public.steps) {
          if (!step.operationId || step.outcome) continue;
          try {
            operationAuthority.retainForWorkflow({
              accountFingerprint: record.accountFingerprint,
              operationId: step.operationId,
              retentionExpiresAt: record.public.retentionExpiresAt,
            });
          } catch {
            // Observation owns truthful expiry/manual-recovery classification.
          }
        }
      }
    },
    async create({ accountFingerprint, accessToken, sdkSessionId = null, binding, managedClaim = null, deadlineAtMs = null, signal = null }) {
      await drainCheckpointPrunes();
      const ownerSessionId = getSdkOwnerSession()?.id ?? null;
      const idempotencyKey = `${accountFingerprint}:${binding.idempotencyKey}`;
      const reservation = state.idempotency[idempotencyKey];
      if (reservation) {
        const record = owned(reservation, accountFingerprint);
        if (!sameWorkflowBinding(record.public.binding, binding) || JSON.stringify(record.managedClaim ?? null) !== JSON.stringify(managedClaim)) throw Object.assign(new Error("Workflow idempotency key is already bound to a different target, revision, or authority kind."), { code: "IDEMPOTENCY_CONFLICT", workflowId: record.public.workflowId, idempotencyKey: binding.idempotencyKey });
        return publicSnapshot(record);
      }
      const admitting = admittingIdempotency.get(idempotencyKey);
      if (admitting) {
        if (admitting.ownerSessionId !== ownerSessionId) {
          throw Object.assign(new Error("Workflow is unavailable."), { code: "OPERATION_EXPIRED" });
        }
        if (!sameWorkflowBinding(admitting.binding, binding) || JSON.stringify(admitting.managedClaim ?? null) !== JSON.stringify(managedClaim)) throw Object.assign(new Error("Workflow idempotency key is being admitted for a different target, revision, or authority kind."), { code: "INVALID_REQUEST" });
        return admitting.task;
      }
      const task = (async () => {
        const targetKey = binding.projectId;
        if (admittingTargets.has(targetKey)) throw Object.assign(new Error("Another mutating workflow is being admitted for this project."), { code: "INVALID_REQUEST" });
        if (Object.values(state.workflows).some((record) => ownsMutationTarget(record) && record.public.binding.projectId === binding.projectId)) {
          throw Object.assign(new Error("Another mutating workflow already owns this project."), { code: "INVALID_REQUEST" });
        }
        admittingTargets.add(targetKey);
      try {
        let admittedManagedPreview = null;
        if (managedClaim) {
          const currentPreview = await previewManaged({ accountFingerprint, accessToken, sdkSessionId, program: {
            projectId: binding.projectId, timelineId: binding.timelineId, revision: binding.revision,
            ownershipId: managedClaim.ownershipId, scope: managedClaim.scope, timelineFrameRate: managedClaim.timelineFrameRate, elements: managedClaim.elements,
          }, deadlineAtMs: deadlineAtMs ?? managedInspectionDeadline(), signal });
          if (currentPreview.status !== "ready" || currentPreview.previewDigest !== managedClaim.previewDigest
            || currentPreview.contextDigest !== managedClaim.contextDigest || currentPreview.desiredStateDigest !== managedClaim.desiredStateDigest) {
            throw Object.assign(new Error("Managed preview or captured runtime context changed before admission."), { code: "STALE_REVISION" });
          }
          admittedManagedPreview = currentPreview;
        }
        const managedReservation = managedClaim ? assertManagedClaimAvailable(accountFingerprint, binding, managedClaim) : null;
        if (admittedManagedPreview) {
          if (admittedManagedPreview.protectedStateDigest !== managedClaim.protectedStateDigest) throw Object.assign(new Error("Protected state changed before managed admission."), { code: "STALE_REVISION" });
        }
        const workflowId = opaque("workflow_");
        const at = nowIso();
        const authoritativeBinding = { ...binding };
        const previewEvidence = admittedManagedPreview ? managedPreviewEvidence.get(admittedManagedPreview.previewDigest) : null;
        const previewRows = previewEvidence?.snapshot?.tracks.flatMap((track) => track.clips.map((clip) => ({ track, clip }))) ?? [];
        const plan = admittedManagedPreview?.drift.filter((entry) => entry.kind !== "preserve").map((entry) => {
          const kind = entry.kind === "update" && previewEvidence?.positionMoveKeys?.includes(entry.key) ? "move" : entry.kind;
          const base = { kind, key: entry.key, timelineItemId: entry.timelineItemId ?? null };
          if (kind === "move") return base;
          if (!entry.timelineItemId || (entry.kind !== "remove" && entry.kind !== "update")) return base;
          const target = previewRows.find(({ clip }) => clip.id === entry.timelineItemId);
          if (!target) throw Object.assign(new Error("Managed removal plan lost its exact preview target."), { code: "STALE_REVISION" });
          const closure = new Set([target.clip.id, ...(target.clip.linkedItemIds ?? [])]);
          const closureRows = previewRows.filter(({ clip }) => closure.has(clip.id));
          const removalTargets = closureRows.map(({ track, clip }) => ({
            track: { type: track.type, index: track.index }, affectedItemIds: [clip.id], clipId: clip.id,
            range: structuredClone(clip.recordRange), name: clip.name,
          })).sort((left, right) => left.track.type.localeCompare(right.track.type) || left.track.index - right.track.index || left.clipId.localeCompare(right.clipId));
          if (removalTargets.length !== closure.size) throw Object.assign(new Error("Managed removal plan could not persist its complete exact linked closure."), { code: "STALE_REVISION" });
          const simulatedLinks = new Map(closureRows.map(({ clip }) => [clip.id, [...(clip.linkedItemIds ?? [])]]));
          const remainingIds = new Set(closure);
          for (const removalTarget of removalTargets) {
            const deleted = new Set(removalTarget.affectedItemIds); remainingIds.delete(removalTarget.clipId);
            removalTarget.expectedLinkTransitions = [...remainingIds].map((itemId) => {
              const beforeLinkedItemIds = [...(simulatedLinks.get(itemId) ?? [])];
              const afterLinkedItemIds = beforeLinkedItemIds.filter((id) => !deleted.has(id));
              simulatedLinks.set(itemId, afterLinkedItemIds);
              return { itemId, beforeLinkedItemIds, afterLinkedItemIds };
            }).filter((transition) => JSON.stringify(transition.beforeLinkedItemIds) !== JSON.stringify(transition.afterLinkedItemIds));
          }
          return { ...base, removalTargets };
        }) ?? [];
        const record = { accountFingerprint, ownerSessionId, checkpointId: null, nativeTimelineId: null, startStateHash: null, currentStateHash: null, stepReservations: {}, currentRevision: binding.revision, executablePlan: plan, managedAffectedItemIds: structuredClone(previewEvidence?.affectedItemIds ?? []), managedAffectedNativeItemIds: structuredClone(previewEvidence?.affectedNativeItemIds ?? []), managedAssetCustody: structuredClone(previewEvidence?.managedAssetCustody ?? null), managedProtectedComponentDigests: structuredClone(previewEvidence?.protectedComponentDigests ?? null), protectedStateDigest: managedClaim?.protectedStateDigest ?? null, protectedFamilyDigest: previewEvidence?.protectedFamilyDigest ?? null, ...(managedClaim ? { managedClaim: structuredClone(managedClaim) } : {}), ...(managedReservation ? { managedOwnershipKey: managedReservation.key, priorManagedOwnership: structuredClone(managedReservation.previous) } : {}), public: { workflowId, authorityKind: managedClaim ? "managed" : "generic", binding: authoritativeBinding, sequence: 1, status: "checkpoint_pending", steps: [], createdAt: at, updatedAt: at, retentionExpiresAt: new Date(clock() + WORKFLOW_JOURNAL_RETENTION_MS).toISOString(), manualRecoveryRequired: false, cancellationDoesNotRollback: true } };
        const admittedState = structuredClone(state);
        admittedState.workflows[workflowId] = record;
        admittedState.idempotency[idempotencyKey] = workflowId;
        if (managedReservation) admittedState.managedOwnerships[managedReservation.key] = {
          accountFingerprint, ownershipId: managedClaim.ownershipId, projectId: binding.projectId,
          timelineId: binding.timelineId, scope: managedClaim.scope, status: "provisional",
          workflowId, generation: (managedReservation.previous?.generation ?? 0) + 1,
          revision: binding.revision, desiredStateDigest: managedClaim.desiredStateDigest,
          elementMappings: structuredClone(managedReservation.previous?.elementMappings ?? []),
        };
        saveState(admittedState);
        state = admittedState;
        const inspectBinding = () => liveInspectionService.readWorkflowBinding({ operation: "timeline.snapshot", projectId: binding.projectId, timelineId: binding.timelineId }, { accessToken });
        try {
        const before = await inspectBinding();
        if (before.projectId !== binding.projectId || before.timelineId !== binding.timelineId || before.revision !== binding.revision) {
          throw Object.assign(new Error("Live timeline revision changed before workflow checkpoint capture."), { code: "STALE_REVISION" });
        }
        const checkpoint = await checkpointService.createBeforePromptCheckpoint({
          session: { id: workflowId }, prompt: "SDK checkpoint-backed workflow", accessToken,
        });
        if (checkpoint.project_name !== before.projectName || checkpoint.timeline_name !== before.timelineName
          || checkpoint.timeline_id !== before.nativeTimelineId) throw new Error("Checkpoint native project or timeline identity changed.");
        const checkpointStateHash = checkpoint.db_hash ?? checkpoint.state_hash;
        const checkpointStatus = await checkpointService.getStatus({ session: { id: workflowId }, accessToken });
        if (typeof checkpointStateHash !== "string" || checkpointStatus?.state_hash !== checkpointStateHash
          || checkpointStatus.project_name !== before.projectName || checkpointStatus.timeline_name !== before.timelineName
          || checkpointStatus.timeline_id !== before.nativeTimelineId) {
          throw Object.assign(new Error("Project state changed during workflow checkpoint capture."), { code: "STALE_REVISION" });
        }
        const after = await inspectBinding();
        if (after.projectId !== before.projectId || after.timelineId !== before.timelineId || after.revision !== before.revision
          || after.nativeTimelineId !== before.nativeTimelineId) throw Object.assign(new Error("Live timeline changed during workflow checkpoint capture."), { code: "STALE_REVISION" });
        const startStateHash = checkpointStateHash;
        return mutate(owned(workflowId, accountFingerprint), (draft) => {
          draft.checkpointId = checkpoint.id; draft.nativeTimelineId = before.nativeTimelineId; draft.startStateHash = startStateHash; draft.currentStateHash = startStateHash;
          draft.public.status = "active";
        });
        } catch (error) {
          const pending = owned(workflowId, accountFingerprint);
          mutate(pending, (draft, next) => { draft.public.status = "failed_before_mutation"; restoreManagedOwnership(draft, next); if (!next.checkpointPrunes.includes(workflowId)) next.checkpointPrunes.push(workflowId); });
          error.workflowId = workflowId; error.idempotencyKey = binding.idempotencyKey; throw error;
        }
      } finally {
        admittingTargets.delete(targetKey);
      }
      })();
      admittingIdempotency.set(idempotencyKey, { ownerSessionId, binding: structuredClone(binding), managedClaim: structuredClone(managedClaim), task });
      try { return await task; }
      finally {
        if (admittingIdempotency.get(idempotencyKey)?.task === task) admittingIdempotency.delete(idempotencyKey);
      }
    },
    async get({ accountFingerprint, workflowId, assertRequestCurrent = () => {} }) {
      await drainCheckpointPrunes();
      let record = owned(workflowId, accountFingerprint);
      record = await reconcileCancellation(record, assertRequestCurrent);
      return publicSnapshot(record);
    },
    reserve({ accountFingerprint, workflowId, name }) {
      const record = owned(workflowId, accountFingerprint);
      if (record.public.status !== "active") return publicSnapshot(record);
      const existing = record.public.steps.find((step) => step.name === name);
      if (existing) return publicSnapshot(record);
      if (record.public.steps.some((step) => !step.outcome)) throw new Error("Parallel workflow mutation is denied.");
      if (record.public.steps.length >= 1_000) throw new Error("Workflow step limit is 1000.");
      return mutate(record, (draft) => {
        draft.public.steps.push({ name, idempotencyKey: `idempotency_${crypto.randomUUID()}` });
        draft.stepReservations ??= {};
        draft.stepReservations[name] = { reservedAt: nowIso() };
      });
    },
    prepareManagedStep({ accountFingerprint, workflowId, name, actionId, input }) {
      const record = owned(workflowId, accountFingerprint);
      if (record.public.status !== "active" || !record.managedClaim) throw Object.assign(new Error("Only an active managed workflow can prepare a step."), { code: "INVALID_REQUEST" });
      const step = record.public.steps.find((item) => item.name === name);
      if (!step || step.operationId || step.outcome) throw Object.assign(new Error("Managed step is not an unresolved reservation."), { code: "INVALID_REQUEST" });
      return mutate(record, (draft) => { draft.stepReservations[name] = { ...(draft.stepReservations[name] ?? {}), expectedActionId: actionId, expectedInputDigest: sha256(input), preparedAt: nowIso() }; });
    },
    async attach({ accountFingerprint, workflowId, name, operationId, assertRequestCurrent = () => {} }) {
      let record = owned(workflowId, accountFingerprint);
      if (record.public.status !== "active" && record.public.status !== "cancellation_requested") throw Object.assign(new Error("Workflow is no longer attachable."), { code: "OPERATION_EXPIRED", workflowId });
      const step = record.public.steps.find((item) => item.name === name);
      if (!step || step.outcome) throw Object.assign(new Error("Workflow step was not reserved or is already terminal."), { code: "INVALID_REQUEST" });
      const operation = operationAuthority.inspectOwned({ accountFingerprint, operationId });
      const input = operation.private.normalizedInput;
      if (!operationMatchesReservation(record, step, operation)) throw Object.assign(new Error("Workflow operation ownership does not match its exact binding, action, and input."), { code: "INVALID_REQUEST" });
      if (step.operationId && step.operationId !== operationId) throw Object.assign(new Error("Workflow step operation cannot be replaced."), { code: "INVALID_REQUEST" });
      operationAuthority.retainForWorkflow({
        accountFingerprint,
        operationId,
        retentionExpiresAt: record.public.retentionExpiresAt,
      });
      mutate(record, (draft) => {
        const draftStep = draft.public.steps.find((item) => item.name === name);
        draftStep.operationId = operationId;
        draftStep.actionId = operation.public.actionId;
        draft.stepReservations ??= {};
        draft.stepReservations[name] = { ...(draft.stepReservations[name] ?? {}), attachedAt: nowIso() };
      });
      record = owned(workflowId, accountFingerprint);
      if (record.public.status === "cancellation_requested") {
        assertRequestCurrent();
        const cancellation = await operationAuthority.cancel({ accountFingerprint, operationId, assertRequestCurrent });
        return mutate(record, (draft) => {
          if (terminalOperationStatuses.has(cancellation?.status)) draft.public.steps.find((item) => item.name === name).outcome = "cancellation_requested";
          draft.public.manualRecoveryRequired = cancellation?.possibleMutation !== "none" || cancellation?.status === "cancellation_requested";
        });
      }
      return publicSnapshot(record);
    },
    async failBeforeMutation({ accountFingerprint, accessToken, workflowId, name }) {
      return withRecoveryLease(workflowId, async () => {
      const record = owned(workflowId, accountFingerprint);
      const step = record.public.steps.find((item) => item.name === name);
      if (!step || step.operationId || step.outcome) throw new Error("Only an unadmitted workflow step can fail before mutation.");
      let outcome = "failed_before_mutation";
      if (record.public.steps.some((item) => item.outcome === "completed")) {
        try { await restoreWorkflowStart(record, accessToken, record.currentRevision); outcome = "checkpoint_restored"; }
        catch (error) {
          if (!['WORKFLOW_RECOVERY_LINEAGE_UNPROVEN', 'WORKFLOW_RESTORE_VERIFICATION_FAILED'].includes(error?.code)) throw error;
          outcome = error.code === "WORKFLOW_RECOVERY_LINEAGE_UNPROVEN" ? "manual_recovery_required" : "restore_failed";
        }
      }
      return mutate(record, (draft, next) => {
        draft.public.steps.find((item) => item.name === name).outcome = outcome;
        if (outcome === "checkpoint_restored") for (const prior of draft.public.steps) if (prior.outcome === "completed") prior.outcome = "checkpoint_restored";
        if (outcome === "checkpoint_restored" || outcome === "failed_before_mutation") restoreManagedOwnership(draft, next);
        draft.public.status = outcome;
        draft.public.manualRecoveryRequired = outcome === "restore_failed" || outcome === "manual_recovery_required";
      });
      });
    },
    async fail({ accountFingerprint, accessToken, workflowId }) {
      return withRecoveryLease(workflowId, async () => {
        let record = owned(workflowId, accountFingerprint);
        if (record.public.status !== "active") return publicSnapshot(record);
        if (record.public.steps.some((step) => !step.outcome)) {
          const unresolved = record.public.steps.find((step) => !step.outcome);
          throw Object.assign(new Error("Workflow callback failure cannot overtake an unresolved operation."), { code: "IDEMPOTENCY_CONFLICT", workflowId, idempotencyKey: unresolved?.idempotencyKey });
        }
        let outcome = "failed_before_mutation";
        if (record.public.steps.some((step) => step.outcome === "completed")) {
          try {
            record = await restoreWorkflowStart(record, accessToken, record.currentRevision);
            outcome = "checkpoint_restored";
          } catch (error) {
            if (!["WORKFLOW_RECOVERY_LINEAGE_UNPROVEN", "WORKFLOW_RESTORE_VERIFICATION_FAILED"].includes(error?.code)) throw error;
            outcome = error.code === "WORKFLOW_RECOVERY_LINEAGE_UNPROVEN" ? "manual_recovery_required" : "restore_failed";
          }
        }
        return mutate(record, (draft, next) => {
          if (outcome === "checkpoint_restored") for (const step of draft.public.steps) if (step.outcome === "completed") step.outcome = "checkpoint_restored";
          if (outcome === "checkpoint_restored" || outcome === "failed_before_mutation") restoreManagedOwnership(draft, next);
          draft.public.status = outcome;
          draft.public.manualRecoveryRequired = outcome === "restore_failed" || outcome === "manual_recovery_required";
        });
      });
    },
    async observe({ accountFingerprint, accessToken, workflowId, name, assertRequestCurrent = () => {} }) {
      return withRecoveryLease(workflowId, async () => {
      let record = owned(workflowId, accountFingerprint);
      record = await reconcileCancellation(record, assertRequestCurrent);
      let step = record.public.steps.find((item) => item.name === name);
      if (step && !step.operationId) {
        const operation = operationAuthority.findOwnedByIdempotency({ accountFingerprint, idempotencyKey: step.idempotencyKey });
        if (operation) {
          if (!operationMatchesReservation(record, step, operation)) throw Object.assign(new Error("Recovered workflow operation does not match its exact binding, action, and input."), { code: "STALE_REVISION" });
          operationAuthority.retainForWorkflow({
            accountFingerprint,
            operationId: operation.public.operationId,
            retentionExpiresAt: record.public.retentionExpiresAt,
          });
          mutate(record, (draft) => {
            const draftStep = draft.public.steps.find((item) => item.name === name);
            draftStep.operationId = operation.public.operationId;
            draftStep.actionId = operation.public.actionId;
          });
          record = owned(workflowId, accountFingerprint);
          step = record.public.steps.find((item) => item.name === name);
        } else {
          if (reservationIsExpired(record, name)) {
            return mutate(record, (draft) => {
              draft.public.steps.find((item) => item.name === name).outcome = "manual_recovery_required";
              draft.public.status = "manual_recovery_required";
              draft.public.manualRecoveryRequired = true;
            });
          }
        }
      }
      if (!step?.operationId) return publicSnapshot(record);
      if (step.outcome) return publicSnapshot(record);
      let ownedOperation;
      try { ownedOperation = operationAuthority.inspectOwned({ accountFingerprint, operationId: step.operationId }); }
      catch (error) {
        if (!reservationIsExpired(record, name, "attachedAt")) throw error;
        return mutate(record, (draft) => {
          draft.public.steps.find((item) => item.name === name).outcome = "manual_recovery_required";
          draft.public.status = "manual_recovery_required";
          draft.public.manualRecoveryRequired = true;
        });
      }
      const operation = ownedOperation.public;
      if (!terminalOperationStatuses.has(operation.status)) return publicSnapshot(record);
      let outcome = operation.status === "succeeded" ? "completed" : operation.possibleMutation === "none" ? "failed_before_mutation" : "partially_applied";
      const recovery = operation.recovery;
      if (recovery?.state === "compensated") outcome = "compensated";
      if (operation.status === "cancelled") outcome = "cancellation_requested";
      const priorMutationApplied = record.public.steps.some((item) => item !== step && item.outcome === "completed");
      if (outcome !== "completed" && outcome !== "cancellation_requested"
        && (operation.possibleMutation !== "none" || priorMutationApplied)) {
        try {
          const recoveryRevision = operation.possibleMutation === "none"
            ? record.currentRevision
            : ownedOperation.private.postTimelineRevision;
          await restoreWorkflowStart(record, accessToken, recoveryRevision);
          outcome = "checkpoint_restored";
        } catch (error) {
          if (!["WORKFLOW_RECOVERY_LINEAGE_UNPROVEN", "WORKFLOW_RESTORE_VERIFICATION_FAILED"].includes(error?.code)) throw error;
          outcome = error.code === "WORKFLOW_RECOVERY_LINEAGE_UNPROVEN" ? "manual_recovery_required" : "restore_failed";
        }
      }
      const nextRevision = ownedOperation.private.postTimelineRevision
        ?? sdkOperationPostTimelineRevision(operation.result?.value);
      let observationFailure = null;
      if (outcome === "completed" && operation.possibleMutation === "confirmed") {
        if (typeof nextRevision !== "string") {
          observationFailure = {
            phase: "advance_revision",
            code: "WORKFLOW_OBSERVATION_REVISION_UNAVAILABLE",
            message: "The terminal operation did not provide one canonical post-timeline revision.",
            details: { expectedNativeTimelineId: record.nativeTimelineId, expectedRevision: null },
          };
          outcome = "manual_recovery_required";
        }
        else {
          const details = { expectedNativeTimelineId: record.nativeTimelineId, expectedRevision: nextRevision };
          try {
            const liveBeforeStatus = await liveInspectionService.readWorkflowBinding({
              operation: "timeline.snapshot", projectId: record.public.binding.projectId, timelineId: record.public.binding.timelineId,
            }, { accessToken });
            Object.assign(details, { observedBeforeNativeTimelineId: liveBeforeStatus.nativeTimelineId, observedBeforeRevision: liveBeforeStatus.revision });
            if (liveBeforeStatus.nativeTimelineId !== record.nativeTimelineId || liveBeforeStatus.revision !== nextRevision) {
              throw Object.assign(new Error("Workflow live revision does not match the operation result."), { code: "WORKFLOW_OBSERVATION_REVISION_MISMATCH" });
            }
            const status = await checkpointService.getStatus({ session: { id: record.public.workflowId }, accessToken });
            Object.assign(details, { checkpointTimelineId: status?.timeline_id ?? null, checkpointStateHash: status?.state_hash ?? null });
            if (status?.timeline_id !== record.nativeTimelineId || typeof status?.state_hash !== "string") {
              throw Object.assign(new Error("Workflow state hash readback is unavailable."), { code: "WORKFLOW_OBSERVATION_CHECKPOINT_UNAVAILABLE" });
            }
            const liveAfterStatus = await liveInspectionService.readWorkflowBinding({
              operation: "timeline.snapshot", projectId: record.public.binding.projectId, timelineId: record.public.binding.timelineId,
            }, { accessToken });
            Object.assign(details, { observedAfterNativeTimelineId: liveAfterStatus.nativeTimelineId, observedAfterRevision: liveAfterStatus.revision });
            if (liveAfterStatus.nativeTimelineId !== record.nativeTimelineId || liveAfterStatus.revision !== nextRevision) {
              throw Object.assign(new Error("Workflow live revision changed during state-hash capture."), { code: "WORKFLOW_OBSERVATION_REVISION_RACE" });
            }
            record = advanceWorkflowRevision(record, nextRevision, status.state_hash);
          }
          catch (error) {
            observationFailure = {
              phase: "advance_revision",
              code: typeof error?.code === "string" ? error.code : "WORKFLOW_OBSERVATION_FAILED",
              message: typeof error?.message === "string" ? error.message : "Workflow revision observation failed.",
              details,
            };
            outcome = "manual_recovery_required";
          }
        }
      }
      return mutate(record, (draft, next) => {
        if (observationFailure) draft.lastObservationFailure = { ...observationFailure, observedAt: nowIso() };
        else if (outcome === "completed") delete draft.lastObservationFailure;
        draft.public.steps.find((item) => item.name === name).outcome = outcome;
        if (outcome === "checkpoint_restored") {
          for (const prior of draft.public.steps) if (prior.outcome === "completed") prior.outcome = "checkpoint_restored";
        }
        if (outcome !== "completed") {
          if (outcome === "checkpoint_restored" || outcome === "failed_before_mutation") restoreManagedOwnership(draft, next);
          draft.public.status = outcome;
          draft.public.manualRecoveryRequired = outcome === "restore_failed" || outcome === "manual_recovery_required"
            || (outcome === "cancellation_requested" && operation.possibleMutation !== "none");
        }
      });
      });
    },
    complete({ accountFingerprint, workflowId, managedVerification = null, managedAffectedStateDigest = null }) {
      const record = owned(workflowId, accountFingerprint);
      if (record.public.status !== "active" || record.public.steps.some((step) => step.outcome !== "completed")) throw new Error("Workflow cannot complete before every step completes.");
      return mutate(record, (draft, next) => {
        draft.public.status = "completed";
        if (draft.managedOwnershipKey) {
          const ownership = next.managedOwnerships[draft.managedOwnershipKey];
          if (!ownership || ownership.workflowId !== workflowId) throw new Error("Managed ownership admission disappeared before completion.");
          const groupedCreatedIds = new Map();
          const groupedCreatePlan = [...(draft.executablePlan ?? [])]
            .filter((entry) => entry.kind === "create" || entry.kind === "update")
            .sort((left, right) => left.key.localeCompare(right.key));
          const groupedCreateChunks = chunksOf(groupedCreatePlan, 256);
          for (const [index, createChunk] of groupedCreateChunks.entries()) {
            const name = groupedCreateChunks.length === 1 ? "managed-creates" : `managed-creates-${index + 1}`;
            const step = draft.public.steps.find((candidate) => candidate.name === name);
            if (!step?.operationId || step.outcome !== "completed") continue;
            const values = operationResultValues(operationAuthority.inspectOwned({ accountFingerprint, operationId: step.operationId }));
            if (values.length !== createChunk.length) continue;
            values.forEach((value, resultIndex) => {
              const id = value.affectedClips?.find((clip) => clip.trackType === "video")?.id;
              if (typeof id === "string") groupedCreatedIds.set(createChunk[resultIndex].key, id);
            });
          }
          const mappings = [];
          for (const element of draft.managedClaim.elements) {
            const planEntry = draft.executablePlan?.find((entry) => entry.key === element.key);
            let timelineItemId = planEntry?.kind === "create" || planEntry?.kind === "update" ? null : element.adoptTimelineItemId
              ?? draft.priorManagedOwnership?.elementMappings?.find((entry) => entry.key === element.key)?.timelineItemId;
            if (!timelineItemId) {
              const step = draft.public.steps.find((candidate) => candidate.name === `managed-${element.key}-create`);
              if (step?.operationId && step.outcome === "completed") {
                const operation = operationAuthority.inspectOwned({ accountFingerprint, operationId: step.operationId });
                timelineItemId = operationResultValues(operation)[0]?.affectedClips?.find((clip) => clip.trackType === "video")?.id;
              } else timelineItemId = groupedCreatedIds.get(element.key);
            }
            if (typeof timelineItemId !== "string") throw new Error(`Managed element ${element.key} has no authoritative verified timeline-item identity.`);
            mappings.push({ key: element.key, timelineItemId });
          }
          ownership.status = "active";
          ownership.revision = draft.currentRevision;
          ownership.elementMappings = mappings;
          ownership.managedElements = structuredClone(draft.managedClaim.elements);
          if (!/^sha256:[a-f0-9]{64}$/.test(managedAffectedStateDigest ?? "")) throw new Error("Managed completion requires an authoritative affected-state baseline.");
          ownership.managedAffectedStateDigest = managedAffectedStateDigest;
          if (!managedVerification || managedVerification.finalRevision !== draft.currentRevision || managedVerification.outcome !== "passed") throw new Error("Managed completion requires exact final aggregate verification.");
          ownership.verification = structuredClone(managedVerification);
          draft.public.managedState = {
            ownershipId: ownership.ownershipId,
            generation: ownership.generation,
            revision: ownership.revision,
            desiredStateDigest: ownership.desiredStateDigest,
            elements: mappings,
            verification: managedVerification,
          };
        }
      });
    },
    async beginManaged({ accountFingerprint, accessToken, sdkSessionId = null, binding, cancellationRequested = false, assertRequestCurrent = () => {}, deadlineAtMs = null, signal = null }) {
      const { managedClaim, ...ordinaryBinding } = binding;
      const admitted = await authority.create({ accountFingerprint, accessToken, sdkSessionId, binding: ordinaryBinding, managedClaim, deadlineAtMs, signal });
      if (admitted.status !== "active") return admitted;
      if (!managedExecutions.has(admitted.workflowId)) {
        const task = Promise.resolve().then(() => authority.executeManaged({ accountFingerprint, accessToken, sdkSessionId, binding, cancellationRequested, assertRequestCurrent })).catch(async (error) => {
          const record = owned(admitted.workflowId, accountFingerprint);
          if (record.public.status === "active") {
            if (record.public.steps.some((step) => !step.outcome || step.outcome === "completed")) return mutate(record, (draft, next) => { draft.public.status = "manual_recovery_required"; draft.public.manualRecoveryRequired = true; const ownership = draft.managedOwnershipKey ? next.managedOwnerships[draft.managedOwnershipKey] : null; if (ownership) ownership.status = "recovery_required"; });
            return authority.fail({ accountFingerprint, accessToken, workflowId: admitted.workflowId });
          }
          throw error;
        });
        managedExecutions.set(admitted.workflowId, task);
        void task.finally(() => managedExecutions.delete(admitted.workflowId)).catch(() => {});
      }
      return admitted;
    },
    async waitManaged({ accountFingerprint, accessToken, sdkSessionId = null, workflowId, assertRequestCurrent = () => {} }) {
      let current = owned(workflowId, accountFingerprint);
      if (current.public.status === "checkpoint_pending") throw Object.assign(new Error("Managed workflow checkpoint admission is not terminal; reattach by WorkflowId."), { code: "IDEMPOTENCY_CONFLICT", workflowId, idempotencyKey: current.public.binding.idempotencyKey });
      if (current.public.status === "active" && !managedExecutions.has(workflowId) && current.managedClaim) {
        const binding = { ...current.public.binding, managedClaim: current.managedClaim };
        const task = Promise.resolve().then(() => authority.executeManaged({ accountFingerprint, accessToken, sdkSessionId, binding, assertRequestCurrent })).catch(() => {
          const record = owned(workflowId, accountFingerprint);
          if (record.public.status !== "active") return publicSnapshot(record);
          return mutate(record, (draft, next) => { draft.public.status = "manual_recovery_required"; draft.public.manualRecoveryRequired = true; const ownership = draft.managedOwnershipKey ? next.managedOwnerships[draft.managedOwnershipKey] : null; if (ownership) ownership.status = "recovery_required"; });
        });
        managedExecutions.set(workflowId, task); void task.finally(() => managedExecutions.delete(workflowId)).catch(() => {});
      }
      await managedExecutions.get(workflowId);
      let snapshot = await authority.get({ accountFingerprint, workflowId, assertRequestCurrent });
      if (snapshot.status === "cancellation_requested") {
        const record = owned(workflowId, accountFingerprint);
        snapshot = mutate(record, (draft, next) => {
          const mutationCannotBeExcluded = draft.public.manualRecoveryRequired
            || draft.public.steps.some((step) => step.outcome === "completed");
          if (mutationCannotBeExcluded) {
            draft.public.status = "manual_recovery_required";
            draft.public.manualRecoveryRequired = true;
            const ownership = draft.managedOwnershipKey ? next.managedOwnerships[draft.managedOwnershipKey] : null;
            if (ownership) ownership.status = "recovery_required";
          } else {
            for (const step of draft.public.steps) if (step.outcome === "cancellation_requested") step.outcome = "failed_before_mutation";
            draft.public.status = "failed_before_mutation";
            draft.public.manualRecoveryRequired = false;
            restoreManagedOwnership(draft, next);
          }
        });
      }
      if (snapshot.status === "active" || snapshot.status === "checkpoint_pending") throw Object.assign(new Error("Managed workflow remains non-terminal; reattach by WorkflowId."), { code: "IDEMPOTENCY_CONFLICT", workflowId, idempotencyKey: snapshot.binding.idempotencyKey });
      return snapshot;
    },
    async executeManaged({ accountFingerprint, accessToken, sdkSessionId = null, binding, cancellationRequested = false, assertRequestCurrent = () => {} }) {
      const { managedClaim, ...ordinaryBinding } = binding;
      let snapshot = await authority.create({ accountFingerprint, accessToken, sdkSessionId, binding: ordinaryBinding, managedClaim });
      if (snapshot.status !== "active") return snapshot;
      if (cancellationRequested) return authority.fail({ accountFingerprint, accessToken, workflowId: snapshot.workflowId });
      const recordAtAdmission = owned(snapshot.workflowId, accountFingerprint);
      const plan = [...(recordAtAdmission.executablePlan ?? [])].sort((left, right) => left.key.localeCompare(right.key));
      const elements = new Map(binding.managedClaim.elements.map((element) => [element.key, element]));
      const resumeLegacySteps = recordAtAdmission.public.steps.some((step) => (
        /^managed-.+-move$/.test(step.name)
        || /^managed-.+-create$/.test(step.name)
        || /^managed-.+-remove-(video|audio|subtitle)-\d+$/.test(step.name)
      ));
      const verifyProtectedAfterStep = async (name) => {
        const record = owned(snapshot.workflowId, accountFingerprint);
        const failStepVerification = (code, message, details = {}) => {
          mutate(owned(snapshot.workflowId, accountFingerprint), (draft) => {
            draft.lastManagedVerificationFailure = {
              phase: "managed_step_verification", stepName: name, code, message,
              details: structuredClone(details), observedAt: nowIso(),
            };
          });
          return false;
        };
        const current = await liveInspectionService.read({ operation: "timeline.snapshot", projectId: binding.projectId, timelineId: binding.timelineId }, { accessToken, deadlineAtMs: managedInspectionDeadline() });
        if (current.revision !== record.currentRevision) return failStepVerification(
          "STEP_REVISION_MISMATCH",
          "The post-step live timeline revision does not match the workflow revision.",
          { expectedRevision: record.currentRevision, observedRevision: current.revision },
        );
        const rows = current.tracks.flatMap((track) => track.clips.map((clip) => ({ track, clip })));
        const managedIds = new Set([
          ...(record.managedAffectedItemIds ?? []),
          ...(record.priorManagedOwnership?.elementMappings ?? []).map((entry) => entry.timelineItemId),
          ...binding.managedClaim.elements.map((element) => element.adoptTimelineItemId).filter(Boolean),
        ]);
        for (const step of record.public.steps) {
          if (!step.operationId || step.outcome !== "completed") continue;
          const operation = operationAuthority.inspectOwned({ accountFingerprint, operationId: step.operationId });
          for (const value of operationResultValues(operation)) {
            for (const clip of value.affectedClips ?? []) if (typeof clip.id === "string") managedIds.add(clip.id);
          }
        }
        for (const { clip } of rows) if (managedIds.has(clip.id)) for (const linkedId of clip.linkedItemIds ?? []) managedIds.add(linkedId);
        let familyDigest = null;
        if (record.protectedFamilyDigest) {
          try {
            const attestation = await liveInspectionService.attestManagedProtectedState({ operation: "managed.protected", projectId: binding.projectId,
              timelineId: binding.timelineId, timelineRevision: current.revision,
              affectedNativeItemIds: record.managedAffectedNativeItemIds ?? [],
              affectedItemIds: [...managedIds].filter((id) => rows.some(({ clip }) => clip.id === id)).sort() }, { accessToken, deadlineAtMs: managedInspectionDeadline() });
            familyDigest = attestation.protectedStateDigest;
          } catch (error) {
            return failStepVerification(
              "STEP_ATTESTATION_FAILED",
              "The post-step managed protected-state attestation failed.",
              { causeName: typeof error?.name === "string" ? error.name : null,
                causeCode: typeof error?.code === "string" ? error.code : null,
                causeMessage: typeof error?.message === "string" ? error.message.slice(0, 500) : null,
                timelineRevision: current.revision, affectedItemCount: managedIds.size },
            );
          }
          if (familyDigest !== record.protectedFamilyDigest) return failStepVerification(
            "STEP_PROTECTED_FAMILY_DIGEST_MISMATCH",
            "The post-step protected-family digest does not match the admitted baseline.",
            { expectedDigest: record.protectedFamilyDigest, observedDigest: familyDigest },
          );
        }
        const digest = sha256({ timeline: protectedSnapshot(current, managedIds), protectedFamilies: familyDigest });
        if (digest !== record.protectedStateDigest) {
          const observedComponents = protectedSnapshotComponentDigests(current, managedIds);
          const expectedComponents = record.managedProtectedComponentDigests ?? {};
          const changedComponents = Object.keys(observedComponents).filter((key) => observedComponents[key] !== expectedComponents[key]);
          return failStepVerification(
            "STEP_PROTECTED_STATE_DIGEST_MISMATCH",
            "The post-step canonical protected-state digest does not match the admitted baseline.",
            { expectedDigest: record.protectedStateDigest, observedDigest: digest, changedComponents,
              expectedComponents, observedComponents },
          );
        }
        mutate(record, (draft) => {
          draft.managedStepEvidence ??= [];
          if (!draft.managedStepEvidence.some((entry) => entry.name === name)) draft.managedStepEvidence.push({ name, revision: current.revision, protectedStateDigest: digest });
        });
        return true;
      };
      const runStep = async (name, actionId, resolveInput) => {
        const acceptTerminalStep = async (step) => {
          if (step.outcome !== "completed") return false;
          if (await verifyProtectedAfterStep(name)) return true;
          snapshot = await authority.fail({ accountFingerprint, accessToken, workflowId: snapshot.workflowId });
          return false;
        };
        snapshot = authority.reserve({ accountFingerprint, workflowId: snapshot.workflowId, name });
        let step = snapshot.steps.find((entry) => entry.name === name);
        if (step?.outcome) return acceptTerminalStep(step);
        snapshot = await authority.observe({ accountFingerprint, accessToken, workflowId: snapshot.workflowId, name, assertRequestCurrent });
        step = snapshot.steps.find((entry) => entry.name === name);
        if (step?.outcome) return acceptTerminalStep(step);
        const currentRevision = owned(snapshot.workflowId, accountFingerprint).currentRevision;
        let input;
        try { input = await resolveInput(currentRevision); }
        catch { snapshot = await authority.failBeforeMutation({ accountFingerprint, accessToken, workflowId: snapshot.workflowId, name }); return false; }
        snapshot = authority.prepareManagedStep({ accountFingerprint, workflowId: snapshot.workflowId, name, actionId, input });
        step = snapshot.steps.find((entry) => entry.name === name);
        let operation;
        try { operation = operationAuthority.create({ accountFingerprint, sdkSessionId, requestId: `request_${crypto.randomUUID()}`, actionId, input, idempotencyKey: step.idempotencyKey }); }
        catch {
          snapshot = await authority.observe({ accountFingerprint, accessToken, workflowId: snapshot.workflowId, name, assertRequestCurrent });
          const recoveredStep = snapshot.steps.find((entry) => entry.name === name);
          if (!recoveredStep?.operationId) snapshot = await authority.failBeforeMutation({ accountFingerprint, accessToken, workflowId: snapshot.workflowId, name });
          return false;
        }
        snapshot = await authority.attach({ accountFingerprint, workflowId: snapshot.workflowId, name, operationId: operation.snapshot.operationId, assertRequestCurrent });
        await operationAuthority.waitForIdle?.();
        snapshot = await authority.observe({ accountFingerprint, accessToken, workflowId: snapshot.workflowId, name, assertRequestCurrent });
        if (snapshot.status !== "active" || snapshot.steps.find((entry) => entry.name === name)?.outcome !== "completed") return false;
        if (await verifyProtectedAfterStep(name)) return true;
        snapshot = await authority.fail({ accountFingerprint, accessToken, workflowId: snapshot.workflowId });
        return false;
      };
      const removalInput = async (entry, removalTarget, currentRevision) => {
        const current = await liveInspectionService.read({ operation: "timeline.snapshot", projectId: binding.projectId, timelineId: binding.timelineId }, { accessToken, deadlineAtMs: managedInspectionDeadline() });
        if (current.revision !== currentRevision) throw Object.assign(new Error("Managed removal must resolve against the workflow's current revision."), { code: "STALE_REVISION" });
        const rows = current.tracks.flatMap((track) => track.clips.map((clip) => ({ track, clip })));
        const target = rows.filter(({ clip }) => clip.id === removalTarget.clipId);
        if (target.length !== 1) throw Object.assign(new Error(`Managed element ${entry.key} no longer has one exact removal target.`), { code: "STALE_REVISION" });
        if (target[0].track.type !== removalTarget.track.type || target[0].track.index !== removalTarget.track.index
          || target[0].clip.name !== removalTarget.name || target[0].clip.recordRange.start !== removalTarget.range.start
          || target[0].clip.recordRange.endExclusive !== removalTarget.range.endExclusive) throw Object.assign(new Error(`Managed element ${entry.key} removal selector changed after admission.`), { code: "STALE_REVISION" });
        const affectedItemIds = structuredClone(removalTarget.affectedItemIds);
        const affectedTracks = [structuredClone(removalTarget.track)];
        const expectedLinkTransitions = structuredClone(removalTarget.expectedLinkTransitions ?? []);
        for (const transition of expectedLinkTransitions) {
          const survivor = rows.find(({ clip }) => clip.id === transition.itemId);
          if (!survivor || JSON.stringify([...(survivor.clip.linkedItemIds ?? [])].sort()) !== JSON.stringify([...transition.beforeLinkedItemIds].sort())) {
            throw Object.assign(new Error(`Managed element ${entry.key} reciprocal-link transition changed after admission.`), { code: "STALE_REVISION" });
          }
        }
        const transitionIds = new Set(expectedLinkTransitions.map((transition) => transition.itemId));
        return { operation: "clip_remove", projectId: binding.projectId, timelineId: binding.timelineId, timelineRevision: currentRevision,
          affectedTracks, affectedItemIds, expectedLinkTransitions,
          protectedItemIds: rows.map(({ clip }) => clip.id).filter((id) => !affectedItemIds.includes(id) && !transitionIds.has(id)),
          clipId: removalTarget.clipId, track: structuredClone(removalTarget.track),
          range: { start: removalTarget.range.start, endExclusive: removalTarget.range.endExclusive }, name: removalTarget.name };
      };
      const groupedRemovalInput = async (targets, currentRevision) => {
        const current = await liveInspectionService.read({ operation: "timeline.snapshot", projectId: binding.projectId, timelineId: binding.timelineId }, { accessToken, deadlineAtMs: managedInspectionDeadline() });
        if (current.revision !== currentRevision) throw Object.assign(new Error("Managed removals must resolve against the workflow's current revision."), { code: "STALE_REVISION" });
        const rows = current.tracks.flatMap((track) => track.clips.map((clip) => ({ track, clip })));
        const affectedItemIds = targets.flatMap(({ removalTarget }) => removalTarget.affectedItemIds);
        if (new Set(affectedItemIds).size !== affectedItemIds.length) throw Object.assign(new Error("Managed removal targets overlap."), { code: "STALE_REVISION" });
        const affected = new Set(affectedItemIds);
        const removals = targets.map(({ entry, removalTarget }) => {
          const matches = rows.filter(({ clip }) => clip.id === removalTarget.clipId);
          if (matches.length !== 1) throw Object.assign(new Error(`Managed element ${entry.key} no longer has one exact removal target.`), { code: "STALE_REVISION" });
          const { track, clip } = matches[0];
          if (track.type !== removalTarget.track.type || track.index !== removalTarget.track.index
            || clip.name !== removalTarget.name || clip.recordRange.start !== removalTarget.range.start
            || clip.recordRange.endExclusive !== removalTarget.range.endExclusive) {
            throw Object.assign(new Error(`Managed element ${entry.key} removal selector changed after admission.`), { code: "STALE_REVISION" });
          }
          const expectedLinkTransitions = structuredClone(removalTarget.expectedLinkTransitions ?? [])
            .filter((transition) => !affected.has(transition.itemId));
          for (const transition of expectedLinkTransitions) {
            const survivor = rows.find(({ clip: candidate }) => candidate.id === transition.itemId);
            if (!survivor || JSON.stringify([...(survivor.clip.linkedItemIds ?? [])].sort()) !== JSON.stringify([...transition.beforeLinkedItemIds].sort())) {
              throw Object.assign(new Error(`Managed element ${entry.key} reciprocal-link transition changed after admission.`), { code: "STALE_REVISION" });
            }
          }
          return { operation: "clip_remove", projectId: binding.projectId, timelineId: binding.timelineId, timelineRevision: currentRevision,
            affectedTracks: [structuredClone(removalTarget.track)], affectedItemIds: structuredClone(removalTarget.affectedItemIds), expectedLinkTransitions,
            protectedItemIds: [], clipId: removalTarget.clipId, track: structuredClone(removalTarget.track),
            range: { start: removalTarget.range.start, endExclusive: removalTarget.range.endExclusive }, name: removalTarget.name };
        });
        const transitionIds = new Set(removals.flatMap((removal) => removal.expectedLinkTransitions.map((transition) => transition.itemId)));
        const protectedItemIds = rows.map(({ clip }) => clip.id).filter((id) => !affected.has(id) && !transitionIds.has(id));
        for (const removal of removals) removal.protectedItemIds = structuredClone(protectedItemIds);
        return { operation: "clip_remove_many", removals };
      };
      const insertionInput = async (insertionElements, currentRevision, plural) => {
        const record = owned(snapshot.workflowId, accountFingerprint);
        const baseline = record.managedAssetCustody;
        if (!baseline) throw Object.assign(new Error("Managed source-asset custody is unavailable."), { code: "STALE_REVISION" });
        const intents = [];
        for (const element of insertionElements) {
          const admittedAsset = baseline.assets.find((candidate) => candidate.id === element.assetId);
          if (!admittedAsset) throw Object.assign(new Error("Managed source asset lacks admitted custody."), { code: "STALE_REVISION" });
          const refreshed = await liveInspectionService.refreshManagedTimelineAsset({
            projectId: binding.projectId,
            timelineId: binding.timelineId,
            assetId: element.assetId,
            expectedFingerprint: admittedAsset.fingerprint,
          }, { accessToken, deadlineAtMs: managedInspectionDeadline() });
          intents.push({
            action: "insert", projectId: binding.projectId, timelineId: binding.timelineId, timelineRevision: currentRevision,
            source: { id: element.assetId, name: element.assetName, snapshotRevision: refreshed.revision },
            sourceRange: { domain: "source_range", unit: "frames", start: element.sourceStartFrame, endExclusive: element.sourceEndExclusiveFrame },
            at: { domain: "timeline_record", value: { kind: "frames", value: element.atFrame } },
            videoTrackIndex: element.videoTrack, audioTrackIndex: element.audioTrack, linkedAudio: element.linkedAudio,
          });
        }
        const preparationOptions = { accessToken, sdkSessionId, deadlineAtMs: managedInspectionDeadline() };
        const prepared = plural
          ? await liveInspectionService.prepareTimelineEdits(intents, preparationOptions)
          : { impacts: [(await liveInspectionService.prepareTimelineEdit(intents[0], preparationOptions)).impact] };
        prepared.impacts.forEach((impact, index) => {
          const element = insertionElements[index];
          const expectedDuration = managedRecordDuration(element.sourceStartFrame, element.sourceEndExclusiveFrame,
            element.sourceFrameRate, binding.managedClaim.timelineFrameRate);
          if (expectedDuration === null || impact.recordRange?.start !== element.atFrame
            || impact.recordRange?.endExclusive !== element.atFrame + expectedDuration) {
            throw Object.assign(new Error("Managed insertion preview returned different mixed-rate record geometry."), { code: "STALE_REVISION" });
          }
        });
        return plural ? { impacts: prepared.impacts } : { impact: prepared.impacts[0] };
      };
      const moveInput = async (entries, currentRevision) => {
        const current = await liveInspectionService.read({ operation: "timeline.snapshot", projectId: binding.projectId, timelineId: binding.timelineId }, { accessToken, deadlineAtMs: managedInspectionDeadline() });
        if (current.revision !== currentRevision) throw Object.assign(new Error("Managed move must resolve against the workflow's current revision."), { code: "STALE_REVISION" });
        const rows = current.tracks.flatMap((track) => track.clips.map((clip) => ({ track, clip })));
        return { moves: entries.map(({ entry, element }) => {
          const matches = rows.filter(({ clip }) => clip.id === entry.timelineItemId);
          const expectedDuration = managedRecordDuration(element.sourceStartFrame, element.sourceEndExclusiveFrame,
            element.sourceFrameRate, binding.managedClaim.timelineFrameRate);
          if (matches.length !== 1 || expectedDuration === null) throw Object.assign(new Error(`Managed element ${entry.key} no longer has one exact move target.`), { code: "STALE_REVISION" });
          const { track, clip } = matches[0];
          const linkedRows = (clip.linkedItemIds ?? []).map((id) => rows.find(({ clip: candidate }) => candidate.id === id)).filter(Boolean);
          const exactLinkedAudio = element.linkedAudio === "exclude" ? linkedRows.length === 0
            : element.audioTrack !== null && linkedRows.length === 1 && linkedRows[0].track.type === "audio"
              && linkedRows[0].track.index === element.audioTrack
              && linkedRows[0].clip.linkedItemIds?.length === 1 && linkedRows[0].clip.linkedItemIds[0] === clip.id
              && linkedRows[0].clip.mediaPoolItemId === element.assetId
              && linkedRows[0].clip.recordRange.start === clip.recordRange.start
              && linkedRows[0].clip.recordRange.endExclusive === clip.recordRange.endExclusive
              && linkedRows[0].clip.sourceRange?.start === element.sourceStartFrame
              && linkedRows[0].clip.sourceRange?.endExclusive === element.sourceEndExclusiveFrame
              && sameFrameRate(linkedRows[0].clip.sourceFrameRate, element.sourceFrameRate);
          if (track.type !== "video" || track.index !== element.videoTrack
            || !exactLinkedAudio || clip.recordRange.endExclusive - clip.recordRange.start !== expectedDuration
            || clip.mediaPoolItemId !== element.assetId || clip.sourceRange?.start !== element.sourceStartFrame
            || clip.sourceRange?.endExclusive !== element.sourceEndExclusiveFrame
            || !sameFrameRate(clip.sourceFrameRate, element.sourceFrameRate)) {
            throw Object.assign(new Error(`Managed element ${entry.key} is no longer a position-only move.`), { code: "STALE_REVISION" });
          }
          return { projectId: binding.projectId, timelineId: binding.timelineId, timelineRevision: currentRevision,
            target: { snapshotId: clip.snapshotId, id: clip.id, trackIndex: track.index,
              recordStartFrame: clip.recordRange.start, recordEndFrame: clip.recordRange.endExclusive,
              name: clip.name, mediaPoolItemId: clip.mediaPoolItemId },
            linkedAudioTargets: linkedRows.map(({ track: linkedTrack, clip: linkedClip }) => ({
              snapshotId: linkedClip.snapshotId, id: linkedClip.id, trackIndex: linkedTrack.index,
              recordStartFrame: linkedClip.recordRange.start, recordEndFrame: linkedClip.recordRange.endExclusive,
              name: linkedClip.name, mediaPoolItemId: linkedClip.mediaPoolItemId,
            })), destination: { trackIndex: element.videoTrack, recordStartFrame: element.atFrame },
            linkedAudio: element.linkedAudio === "include" ? "preserve" : "exclude", collisionPolicy: "reject" };
        }) };
      };
      const moves = plan.filter((candidate) => candidate.kind === "move").map((entry) => {
        const element = elements.get(entry.key);
        if (!element) throw new Error(`Managed executable plan refers to absent element ${entry.key}.`);
        return { entry, element };
      });
      const moveChunks = chunksOf(moves, 100);
      if (resumeLegacySteps) {
        for (const move of moves) {
          if (!await runStep(`managed-${move.entry.key}-move`, "cutagent.action.timeline.items.move", async (revision) => (
            await moveInput([move], revision)
          ).moves[0])) return snapshot;
        }
      } else for (const [index, moveChunk] of moveChunks.entries()) {
          const name = moveChunks.length === 1 ? "managed-moves" : `managed-moves-${index + 1}`;
          if (!await runStep(name, "cutagent.action.timeline.items.move", (revision) => moveInput(moveChunk, revision))) return snapshot;
      }
      const removalGroups = [];
      for (const entry of plan.filter((candidate) => candidate.kind === "remove" || candidate.kind === "update")) {
        if (!Array.isArray(entry.removalTargets) || entry.removalTargets.length === 0) return authority.fail({ accountFingerprint, accessToken, workflowId: snapshot.workflowId });
        if (entry.removalTargets.length > 256) return authority.fail({ accountFingerprint, accessToken, workflowId: snapshot.workflowId });
        removalGroups.push(entry.removalTargets.map((removalTarget) => ({ entry, removalTarget })));
      }
      const removals = removalGroups.flat();
      const removalChunks = [];
      for (const group of removalGroups) {
        const currentChunk = removalChunks.at(-1);
        if (!currentChunk || currentChunk.length + group.length > 256) removalChunks.push([...group]);
        else currentChunk.push(...group);
      }
      if (resumeLegacySteps) {
        for (const { entry, removalTarget } of removals) {
          const stepName = `managed-${entry.key}-remove-${removalTarget.track.type}-${removalTarget.track.index}`;
          if (!await runStep(stepName, "cutagent.action.timeline.items.delete", (revision) => removalInput(entry, removalTarget, revision))) return snapshot;
        }
      } else for (const [index, removalChunk] of removalChunks.entries()) {
        const name = removalChunks.length === 1 ? "managed-removes" : `managed-removes-${index + 1}`;
        if (!await runStep(name, "cutagent.action.timeline.items.delete", (revision) => groupedRemovalInput(removalChunk, revision))) return snapshot;
      }
      const creates = plan.filter((candidate) => candidate.kind === "create" || candidate.kind === "update").map((entry) => {
        const element = elements.get(entry.key);
        if (!element) throw new Error(`Managed executable plan refers to absent element ${entry.key}.`);
        return { entry, element };
      });
      const createChunks = chunksOf(creates, 256);
      if (resumeLegacySteps) {
        for (const create of creates) {
          if (!await runStep(`managed-${create.entry.key}-create`, "cutagent.action.edit.insert", (revision) => insertionInput([create.element], revision, false))) return snapshot;
        }
      } else for (const [index, createChunk] of createChunks.entries()) {
        const name = createChunks.length === 1 ? "managed-creates" : `managed-creates-${index + 1}`;
        if (!await runStep(name, "cutagent.action.edit.insert", (revision) => insertionInput(createChunk.map(({ element }) => element), revision, true))) return snapshot;
      }
      const record = owned(snapshot.workflowId, accountFingerprint);
      const failManagedVerification = async (code, message, details = {}) => {
        const current = owned(snapshot.workflowId, accountFingerprint);
        mutate(current, (draft) => {
          draft.lastManagedVerificationFailure = {
            phase: "final_managed_verification",
            code,
            message,
            details: structuredClone(details),
            observedAt: nowIso(),
          };
        });
        return authority.fail({ accountFingerprint, accessToken, workflowId: snapshot.workflowId });
      };
      const finalSnapshot = await liveInspectionService.read({ operation: "timeline.snapshot", projectId: binding.projectId, timelineId: binding.timelineId }, { accessToken, deadlineAtMs: managedInspectionDeadline() });
      if (finalSnapshot.revision !== record.currentRevision) return failManagedVerification(
        "FINAL_REVISION_MISMATCH",
        "The final live timeline revision does not match the workflow revision.",
        { expectedRevision: record.currentRevision, observedRevision: finalSnapshot.revision },
      );
      const createdIdsByKey = new Map();
      if (resumeLegacySteps) {
        for (const { entry } of creates) {
          const step = record.public.steps.find((candidate) => candidate.name === `managed-${entry.key}-create`);
          const operation = step?.operationId ? operationAuthority.inspectOwned({ accountFingerprint, operationId: step.operationId }) : null;
          const created = operationResultValues(operation)[0]?.affectedClips?.find((clip) => clip.trackType === "video")?.id;
          if (typeof created === "string") createdIdsByKey.set(entry.key, created);
        }
      } else for (const [index, createChunk] of createChunks.entries()) {
        const name = createChunks.length === 1 ? "managed-creates" : `managed-creates-${index + 1}`;
        const step = record.public.steps.find((candidate) => candidate.name === name);
        const operation = step?.operationId ? operationAuthority.inspectOwned({ accountFingerprint, operationId: step.operationId }) : null;
        const values = operationResultValues(operation);
        if (values.length !== createChunk.length) return failManagedVerification(
          "CREATED_RESULT_COUNT_MISMATCH",
          "The grouped create result count does not match the admitted create plan.",
          { stepName: name, expectedCount: createChunk.length, observedCount: values.length },
        );
        values.forEach((value, resultIndex) => {
          const created = value.affectedClips?.find((clip) => clip.trackType === "video")?.id;
          if (typeof created === "string") createdIdsByKey.set(createChunk[resultIndex].entry.key, created);
        });
      }
      const mappings = binding.managedClaim.elements.map((element) => {
        const planEntry = record.executablePlan?.find((entry) => entry.key === element.key);
        const retained = planEntry?.kind === "create" || planEntry?.kind === "update" ? null : element.adoptTimelineItemId
          ?? record.priorManagedOwnership?.elementMappings?.find((entry) => entry.key === element.key)?.timelineItemId;
        return { key: element.key, timelineItemId: retained ?? createdIdsByKey.get(element.key) };
      });
      const missingMappingKeys = mappings.filter((entry) => typeof entry.timelineItemId !== "string").map((entry) => entry.key);
      if (missingMappingKeys.length) return failManagedVerification(
        "MANAGED_MAPPING_UNAVAILABLE",
        "One or more managed elements have no authoritative timeline-item identity.",
        { missingKeys: missingMappingKeys },
      );
      const finalManagedIds = new Set(mappings.map((entry) => entry.timelineItemId));
      const finalRows = finalSnapshot.tracks.flatMap((track) => track.clips.map((clip) => ({ track, clip })));
      for (const { clip } of finalRows) if (finalManagedIds.has(clip.id)) for (const linkedId of clip.linkedItemIds ?? []) finalManagedIds.add(linkedId);
      let finalProtectedFamilyDigest = null;
      let finalAffectedStateDigest = null;
      if (record.protectedFamilyDigest) {
        try {
          const finalAttestation = await liveInspectionService.attestManagedProtectedState({ operation: "managed.protected", projectId: binding.projectId,
            timelineId: binding.timelineId, timelineRevision: finalSnapshot.revision,
            affectedNativeItemIds: record.managedAffectedNativeItemIds ?? [], affectedItemIds: [...finalManagedIds].sort() }, { accessToken, deadlineAtMs: managedInspectionDeadline() });
          finalProtectedFamilyDigest = finalAttestation.protectedStateDigest;
          finalAffectedStateDigest = finalAttestation.affectedStateDigest;
        }
        catch (error) {
          return failManagedVerification(
            "FINAL_ATTESTATION_FAILED",
            "The final managed protected-state attestation failed.",
            {
              causeName: typeof error?.name === "string" ? error.name : null,
              causeCode: typeof error?.code === "string" ? error.code : null,
              causeMessage: typeof error?.message === "string" ? error.message.slice(0, 500) : null,
              timelineRevision: finalSnapshot.revision,
              affectedNativeItemCount: (record.managedAffectedNativeItemIds ?? []).length,
              affectedItemCount: finalManagedIds.size,
            },
          );
        }
        if (finalProtectedFamilyDigest !== record.protectedFamilyDigest) return failManagedVerification(
          "PROTECTED_FAMILY_DIGEST_MISMATCH",
          "The final protected-family digest does not match the admitted baseline.",
          { expectedDigest: record.protectedFamilyDigest, observedDigest: finalProtectedFamilyDigest },
        );
      }
      const finalPreview = await previewManaged({ accountFingerprint, accessToken, sdkSessionId, ownershipOverride: { accountFingerprint, ownershipId: binding.managedClaim.ownershipId,
        projectId: binding.projectId, timelineId: binding.timelineId, scope: binding.managedClaim.scope, status: "active", generation: 1,
        revision: record.currentRevision, desiredStateDigest: binding.managedClaim.desiredStateDigest, elementMappings: mappings,
        managedElements: binding.managedClaim.elements, managedAffectedStateDigest: finalAffectedStateDigest },
        program: { projectId: binding.projectId, timelineId: binding.timelineId, revision: record.currentRevision, ownershipId: binding.managedClaim.ownershipId, scope: binding.managedClaim.scope, timelineFrameRate: binding.managedClaim.timelineFrameRate, elements: binding.managedClaim.elements },
        deadlineAtMs: managedInspectionDeadline() });
      const finalAssetCustody = managedPreviewEvidence.get(finalPreview.previewDigest)?.managedAssetCustody ?? null;
      if (!sameManagedAssetCustody(finalAssetCustody, record.managedAssetCustody)) return failManagedVerification(
        "MANAGED_ASSET_CUSTODY_MISMATCH",
        "The final managed Media Pool custody does not match the admitted source custody.",
        { expectedAssetCount: record.managedAssetCustody?.assets?.length ?? 0, observedAssetCount: finalAssetCustody?.assets?.length ?? 0 },
      );
      if (finalPreview.status !== "no_change" || finalPreview.blockers.length) return failManagedVerification(
        "FINAL_PREVIEW_NOT_CONVERGED",
        "The final managed preview did not converge to no_change.",
        { status: finalPreview.status, blockerCodes: finalPreview.blockers.slice(0, 20).map((blocker) => blocker.code ?? null), blockerCount: finalPreview.blockers.length },
      );
      const combinedFinalProtectedStateDigest = sha256({ timeline: protectedSnapshot(finalSnapshot, finalManagedIds), protectedFamilies: finalProtectedFamilyDigest });
      const expectedManagedStateDigest = sha256(binding.managedClaim.elements.map((element) => ({ key: element.key, timelineItemId: mappings.find((entry) => entry.key === element.key).timelineItemId,
        assetId: element.assetId, videoTrack: element.videoTrack, audioTrack: element.audioTrack, atFrame: element.atFrame, sourceStartFrame: element.sourceStartFrame, sourceEndExclusiveFrame: element.sourceEndExclusiveFrame, sourceFrameRate: element.sourceFrameRate, linkedAudio: element.linkedAudio })));
      if (combinedFinalProtectedStateDigest !== record.protectedStateDigest) return failManagedVerification(
        "PROTECTED_STATE_DIGEST_MISMATCH",
        "The final canonical protected-state digest does not match the admitted baseline.",
        { expectedDigest: record.protectedStateDigest, observedDigest: combinedFinalProtectedStateDigest },
      );
      const verification = { outcome: "passed", finalRevision: record.currentRevision, protectedStateDigest: combinedFinalProtectedStateDigest, expectedManagedStateDigest,
        evidence: [managedEvidence("Verified canonical protected state after every durable managed substep and against the admitted baseline.", { baseline: record.protectedStateDigest, final: combinedFinalProtectedStateDigest, protectedFamilyDigest: finalProtectedFamilyDigest, steps: record.managedStepEvidence ?? [] }), managedEvidence("Read back the complete converged managed program at the exact final revision.", { finalRevision: record.currentRevision, mappings, previewDigest: finalPreview.previewDigest }, "readback")] };
      return authority.complete({ accountFingerprint, workflowId: snapshot.workflowId, managedVerification: verification,
        managedAffectedStateDigest: finalAffectedStateDigest });
    },
    async interrupt({ accountFingerprint, workflowId, assertRequestCurrent = () => {} }) {
      return withRecoveryLease(workflowId, async () => {
        const record = owned(workflowId, accountFingerprint);
        if (record.public.status !== "active") return publicSnapshot(record);
        const activeStep = record.public.steps.find((step) => step.operationId && !step.outcome);
        let cancellation = null;
        if (activeStep?.operationId) {
          assertRequestCurrent();
          cancellation = await operationAuthority.cancel({ accountFingerprint, operationId: activeStep.operationId, assertRequestCurrent });
        }
        return mutate(record, (draft) => {
          if (activeStep && terminalOperationStatuses.has(cancellation?.status)) {
            draft.public.steps.find((step) => step.operationId === activeStep.operationId).outcome = "cancellation_requested";
          }
          draft.public.status = "cancellation_requested";
          draft.public.manualRecoveryRequired = Boolean(activeStep)
            && (cancellation?.possibleMutation !== "none" || cancellation?.status === "cancellation_requested");
        });
      });
    },
  };
  return Object.freeze(authority);
}
