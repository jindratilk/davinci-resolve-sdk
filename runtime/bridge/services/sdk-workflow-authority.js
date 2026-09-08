import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { ensureCanonicalPrivateDirectory, writePrivateJsonDurableAtomic } from "./private-storage.js";
import { sdkWorkflowSnapshotSchema } from "../contracts/generated/sdk-operations.js";
import { sdkManagedTimelineExportSchema, sdkManagedTimelinePreviewSchema } from "../contracts/generated/sdk-runtime.js";
import { CUTAGENT_SDK_ACTION_SCHEMA_DIGEST } from "../contracts/generated/sdk-operation-actions.js";
import { CUTAGENT_MUTATION_POLICY_CONTRACT_VERSION } from "../contracts/generated/sdk-mutation-policy.js";
import { mutationPolicyDigest, PRIVATE_IMPACT_REGISTRY_DIGEST } from "./mutation-policy/impact-lowering.js";
import { resolveSdkDirectMutationScope } from "./sdk-direct-mutation-scope.js";
import { getSdkOwnerSession } from "./sdk-owner-session-context.js";

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
const managedEvidence = (summary, value, modality = "structural") => ({ modality, summary, digest: sha256(value) });
const managedInspectionDeadline = () => Date.now() + MANAGED_INSPECTION_PHASE_TIMEOUT_MS;
const isCancellationOrTimeout = (error) => error?.name === "AbortError" || error?.name === "TimeoutError";
const sameManagedAssetCustody = (left, right) => {
  if (!left || !right) return left === right;
  return left.stableInventoryDigest === right.stableInventoryDigest
    && canonical(left.assets.map(({ id, fingerprint }) => ({ id, fingerprint })))
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
        throw Object.assign(new Error("Workflow ownership binding is incomplete."), { code: "EDIT_CONSTRAINT_VIOLATION" });
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

export function createSdkWorkflowAuthority({ storageDir, operationAuthority, checkpointService, mutationPolicyGate, directMutationPolicyAuthority = null, liveInspectionService, persistState = writePrivateJsonDurableAtomic, recoveryCrashInjector = null, clock = Date.now }) {
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
      record.public.retentionExpiresAt ??= new Date(Date.parse(record.public.updatedAt) + WORKFLOW_JOURNAL_RETENTION_MS).toISOString();
      record.public.authorityKind ??= record.managedClaim || record.public.binding?.managedClaim ? "managed" : "generic";
      if (!Object.hasOwn(record, "currentProjectRevision")) record.currentProjectRevision = record.currentStateHash;
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
    const projectId = input?.projectId ?? input?.impact?.intent?.projectId;
    const timelineId = input?.timelineId ?? input?.impact?.intent?.timelineId;
    const timelineRevision = input?.timelineRevision ?? input?.precondition ?? input?.impact?.intent?.timelineRevision;
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
      throw Object.assign(new Error("Managed ownership has unresolved provisional or recovery-required state."), { code: "EDIT_CONSTRAINT_VIOLATION" });
    }
    if (previous && (previous.projectId !== binding.projectId || previous.timelineId !== binding.timelineId
      || JSON.stringify(previous.scope) !== JSON.stringify(claim.scope))) {
      throw Object.assign(new Error("Managed ownership cannot be rebound to another project, timeline, or scope."), { code: "EDIT_CONSTRAINT_VIOLATION" });
    }
    for (const [candidateKey, candidate] of Object.entries(state.managedOwnerships)) {
      if (candidateKey === key || candidate.accountFingerprint !== accountFingerprint || candidate.projectId !== binding.projectId
        || candidate.timelineId !== binding.timelineId || candidate.status === "restored") continue;
      if (scopesOverlap(candidate.scope, claim.scope)) throw Object.assign(new Error("Managed ownership overlaps another active managed scope."), { code: "EDIT_CONSTRAINT_VIOLATION" });
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
      elements.push({key: binding.key, assetId: asset.id, assetName: asset.name, assetRevision: asset.snapshotRevision,
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
      const exact = track.type === "video" && track.index === element.videoTrack
        && clip.recordRange.start === element.atFrame
        && clip.recordRange.endExclusive === desiredEnd
        && clip.mediaPoolItemId === element.assetId
        && clip.sourceRange?.start === element.sourceStartFrame
        && clip.sourceRange?.endExclusive === element.sourceEndExclusiveFrame
        && sameFrameRate(clip.sourceFrameRate, element.sourceFrameRate)
        && linkedAudioExact;
      const positionOnly = !exact
        && element.linkedAudio === "exclude"
        && track.type === "video" && track.index === element.videoTrack
        && clip.recordRange.start !== element.atFrame
        && clip.recordRange.endExclusive - clip.recordRange.start === recordDuration
        && clip.mediaPoolItemId === element.assetId
        && clip.sourceRange?.start === element.sourceStartFrame
        && clip.sourceRange?.endExclusive === element.sourceEndExclusiveFrame
        && sameFrameRate(clip.sourceFrameRate, element.sourceFrameRate)
        && linkedAudioExact;
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
    let scope = [];
    if (directMutationPolicyAuthority !== null && sdkSessionId !== null) {
      try {
        const directScope = await resolveSdkDirectMutationScope({
          directMutationPolicyAuthority,
          context: { sdkSessionId, accountFingerprint },
          liveInspectionService,
          level: "project+timeline",
          projectId: program.projectId,
          timelineId: program.timelineId,
          timelineRevision: snapshot.revision,
        });
        scope = directScope === null ? [] : [directScope];
      } catch (error) {
        if (isCancellationOrTimeout(error)) throw error;
      }
    } else {
      scope = mutationPolicyGate.listScopes({ accountFingerprint }).filter((candidate) => candidate.binding?.projectId === program.projectId
        && candidate.binding?.timelineId === program.timelineId && (candidate.binding?.timelineRevision ?? candidate.binding?.revision) === snapshot.revision);
    }
    if (scope.length !== 1) blockers.push({ code: "protected_state_unproven", message: "The exact Mutation Policy generation is unavailable or ambiguous." });
    if (scope.length === 1 && scope[0].constraints.protectedMediaRoles.length > 0
      && drift.some((entry) => entry.kind === "create" || (entry.kind === "update" && !positionMoveKeys.has(entry.key)))) {
      blockers.push({ code: "protected_state_unproven", message: "Managed insertion cannot prove an authoritative media role against this scope's protected media roles." });
    }
    const desiredStateDigest = sha256({ ownershipId: program.ownershipId, projectId: program.projectId, timelineId: program.timelineId, scope: program.scope, elements: program.elements });
    let managedAssetCustody = null;
    if (program.elements.length > 0) {
      const revisions = new Set(program.elements.map((element) => element.assetRevision));
      if (revisions.size !== 1) blockers.push({ code: "stale_revision", message: "Managed source assets do not share one admitted Media Pool revision." });
      else try {
        managedAssetCustody = await liveInspectionService.captureManagedTimelineAssets({
          projectId: program.projectId,
          timelineId: program.timelineId,
          assetIds: program.elements.map((element) => element.assetId),
          expectedRevision: ownershipOverride ? null : [...revisions][0],
        }, inspectionOptions);
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
      policyRevision: scope.length === 1 ? `policy_revision_${scope[0].revision}` : "policy_revision_1",
      capabilityDigest: `sha256:${CUTAGENT_SDK_ACTION_SCHEMA_DIGEST}`,
      protectedStateDigest: sha256({ timeline: protectedSnapshot(snapshot, excludedManagedIds), protectedFamilies: protectedFamilyAttestation?.protectedStateDigest ?? null }),
    };
    const contextDigest = sha256(context);
    const status = blockers.length ? "blocked" : drift.some((entry) => entry.kind !== "preserve") || adoptionNeeded || !ownership ? "ready" : "no_change";
    const base = { status, projectId: program.projectId, timelineId: program.timelineId, revision: snapshot.revision, ownershipId: program.ownershipId, scope: program.scope, desiredStateDigest, contextDigest, protectedStateDigest: context.protectedStateDigest, ownershipGeneration: context.ownershipGeneration, policyRevision: context.policyRevision, capabilityDigest: context.capabilityDigest, drift, blockers };
    const result = sdkManagedTimelinePreviewSchema.parse({ ...base, previewDigest: sha256(base) });
    managedPreviewEvidence.set(result.previewDigest, { protectedFamilyDigest: protectedFamilyAttestation?.protectedStateDigest ?? null,
      affectedStateDigest: protectedFamilyAttestation?.affectedStateDigest ?? null,
      affectedNativeItemIds: protectedFamilyAttestation?.privateAffectedNativeItemIds ?? null,
      affectedItemIds: [...attestationAffectedIds].sort(), positionMoveKeys: [...positionMoveKeys].sort(),
      snapshot: structuredClone(snapshot), managedAssetCustody: structuredClone(managedAssetCustody) });
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
  const findScope = async (accountFingerprint, binding, { sdkSessionId = null, accessToken = null, deadlineAtMs = null } = {}) => {
    if (directMutationPolicyAuthority !== null) {
      const inspectedProjectContext = await liveInspectionService.readWithMutationGuard(
        { operation: "project.context" },
        { accessToken, deadlineAtMs: deadlineAtMs ?? managedInspectionDeadline() },
      );
      return resolveSdkDirectMutationScope({
        directMutationPolicyAuthority,
        context: { sdkSessionId, accountFingerprint },
        liveInspectionService,
        level: "project+timeline",
        projectId: binding.projectId,
        timelineId: binding.timelineId,
        timelineRevision: binding.revision,
        inspectedProjectContext,
      });
    }
    const matches = mutationPolicyGate.listScopes({ accountFingerprint }).filter((scope) => {
      const candidate = scope.binding ?? {};
      return candidate.projectId === binding.projectId && candidate.timelineId === binding.timelineId
        && (candidate.timelineRevision ?? candidate.revision) === binding.revision;
    });
    if (matches.length !== 1) throw Object.assign(new Error("Exact Mutation Policy scope is unavailable or ambiguous."), { code: "EDIT_CONSTRAINT_VIOLATION" });
    const scope = matches[0];
    return scope;
  };
  const preflightManagedAggregate = ({ accountFingerprint, binding, scope, preview, claim }) => {
    const evidence = managedPreviewEvidence.get(preview.previewDigest);
    const snapshot = evidence?.snapshot;
    if (!snapshot) throw Object.assign(new Error("Managed aggregate impact lost its authoritative preview evidence."), { code: "EDIT_CONSTRAINT_VIOLATION", admissionState: "not_admitted" });
    const rows = snapshot.tracks.flatMap((track) => track.clips.map((clip) => ({ track, clip })));
    const elements = new Map(claim.elements.map((element) => [element.key, element]));
    const timelineTarget = { kind: "timeline", stableId: binding.timelineId, revision: binding.revision };
    const trackTarget = (type, index) => {
      const track = snapshot.tracks.find((candidate) => candidate.type === type && candidate.index === index);
      return track ? { kind: "track", stableId: track.snapshotId, revision: binding.revision, trackType: type, trackIndex: index } : null;
    };
    const clipTargets = (timelineItemId) => {
      const target = rows.find(({ clip }) => clip.id === timelineItemId);
      if (!target) return [];
      return [target, ...rows.filter(({ clip }) => target.clip.linkedItemIds?.includes(clip.id))].map(({ track, clip }) => ({
        kind: "clip", stableId: clip.id, revision: binding.revision, trackType: track.type, trackIndex: track.index,
      }));
    };
    const effects = [];
    for (const entry of preview.drift.filter((candidate) => candidate.kind !== "preserve")) {
      const element = elements.get(entry.key);
      const positionMove = entry.kind === "update" && evidence.positionMoveKeys?.includes(entry.key);
      if (positionMove) {
        const targets = [timelineTarget, ...clipTargets(entry.timelineItemId), trackTarget("video", element.videoTrack)].filter(Boolean);
        effects.push({ operation: "timeline.items.move", kind: "update", trackTypes: ["video"], targets,
          placementIntent: "explicit", broad: false, ambiguous: targets.length < 3, complete: targets.length >= 3 });
        continue;
      }
      if (entry.kind === "remove" || entry.kind === "update") {
        const targets = [timelineTarget, ...clipTargets(entry.timelineItemId)];
        effects.push({ operation: "timeline.items.delete", kind: "delete", trackTypes: [...new Set(targets.map((target) => target.trackType).filter(Boolean))], targets,
          placementIntent: "explicit", broad: false, ambiguous: targets.length < 2, complete: targets.length >= 2 });
      }
      if (entry.kind === "create" || entry.kind === "update") {
        const targets = [timelineTarget, trackTarget("video", element.videoTrack), ...(element.linkedAudio === "include" ? [trackTarget("audio", element.audioTrack)] : []),
          { kind: "media", stableId: element.assetId, revision: element.assetRevision }].filter(Boolean);
        const rolesProven = (scope.constraints.protectedMediaRoles ?? []).length === 0;
        effects.push({ operation: "edit.insert", kind: "create", trackTypes: [...new Set(["video", ...(element.linkedAudio === "include" ? ["audio"] : [])])], targets,
          placementIntent: "explicit", broad: false, ambiguous: !rolesProven, complete: rolesProven && targets.length === (element.linkedAudio === "include" ? 4 : 3) });
      }
    }
    const correlation = crypto.randomUUID().replaceAll("-", "");
    const executionId = `execution_managed_${correlation}`;
    const impact = { contractVersion: CUTAGENT_MUTATION_POLICY_CONTRACT_VERSION, carrier: "composition", status: "mutation", minimumBinding: "project+timeline",
      registryDigest: PRIVATE_IMPACT_REGISTRY_DIGEST, canonicalRequestDigest: mutationPolicyDigest({ ownershipId: claim.ownershipId, previewDigest: preview.previewDigest, effects }), referencedPayloadDigests: [],
      requestId: `request_managed_${correlation}`, operationId: `operation_managed_${correlation}`, executionId,
      scopeId: scope.scopeId, scopeRevision: scope.revision, projectLibraryId: scope.binding.projectLibraryId, projectId: binding.projectId, timelineId: binding.timelineId,
      projectRevision: scope.binding.projectRevision, timelineRevision: binding.revision, effects, closedComposition: true,
      complete: effects.length > 0 && effects.every((effect) => effect.complete), ambiguous: effects.some((effect) => effect.ambiguous), broad: false,
      executableStableTargetPrecondition: true, verificationPolicy: { minimumEvidence: ["readback", "structural"], requireProtectedStatePreserved: true, protectedTargetEvidence: "every_declared_target" } };
    try { return mutationPolicyGate.preflight({ accountFingerprint, impact }); }
    catch (error) { error.admissionState = "not_admitted"; throw error; }
    finally { mutationPolicyGate.onSessionClose?.({ accountFingerprint, executionId }); }
  };
  const assertScopeCurrent = (record) => {
    const scope = mutationPolicyGate.getScope({ accountFingerprint: record.accountFingerprint, scopeId: record.scopeId });
    const binding = scope?.binding ?? {};
    if (!scope || scope.revision !== record.scopeRevision || binding.projectId !== record.public.binding.projectId
      || binding.timelineId !== record.public.binding.timelineId || (binding.projectRevision ?? null) !== record.currentProjectRevision
      || (binding.timelineRevision ?? binding.revision) !== record.currentRevision) {
      throw Object.assign(new Error("Mutation Policy revision changed after workflow admission."), { code: "EDIT_CONSTRAINT_VIOLATION" });
    }
    return scope;
  };
  const advanceScopeRevision = (record, timelineRevision, stateHash = record.currentStateHash) => {
    let scope = mutationPolicyGate.getScope({ accountFingerprint: record.accountFingerprint, scopeId: record.scopeId });
    if (scope?.revision === record.scopeRevision + 1
      && (scope.binding?.timelineRevision ?? scope.binding?.revision) === timelineRevision
      && (scope.binding?.projectRevision ?? null) === record.currentProjectRevision
      && JSON.stringify(scope.constraints) === JSON.stringify(record.scopeConstraints)) {
      return commitRecord(record, (draft) => {
        draft.scopeRevision = scope.revision;
        draft.currentRevision = timelineRevision;
        draft.currentStateHash = stateHash;
        draft.currentProjectRevision = scope.binding.projectRevision ?? null;
        draft.public.binding.policyRevision = `policy_revision_${scope.revision}`;
      });
    }
    scope = assertScopeCurrent(record);
    const advanced = mutationPolicyGate.updateScope({
      accountFingerprint: record.accountFingerprint,
      scopeId: record.scopeId,
      expectedRevision: record.scopeRevision,
      binding: { ...scope.binding, timelineRevision },
      constraints: record.scopeConstraints,
    });
    if (!advanced) throw Object.assign(new Error("Mutation Policy scope disappeared during workflow progression."), { code: "EDIT_CONSTRAINT_VIOLATION" });
    recoveryCrashInjector?.("after_policy_cas_before_journal", record.public.workflowId);
    return commitRecord(record, (draft) => {
      draft.scopeRevision = advanced.revision;
      draft.currentRevision = timelineRevision;
      draft.currentStateHash = stateHash;
      draft.currentProjectRevision = advanced.binding.projectRevision ?? null;
      draft.public.binding.policyRevision = `policy_revision_${advanced.revision}`;
    });
  };
  const bindScopeStateHashForRestore = (record, stateHash) => {
    let scope = mutationPolicyGate.getScope({ accountFingerprint: record.accountFingerprint, scopeId: record.scopeId });
    if (scope?.revision === record.scopeRevision + 1
      && scope.binding?.projectRevision === stateHash
      && (scope.binding?.timelineRevision ?? scope.binding?.revision) === record.currentRevision
      && JSON.stringify(scope.constraints) === JSON.stringify(record.scopeConstraints)) {
      return commitRecord(record, (draft) => {
        draft.scopeRevision = scope.revision;
        draft.currentProjectRevision = stateHash;
        draft.public.binding.policyRevision = `policy_revision_${scope.revision}`;
      });
    }
    scope = assertScopeCurrent(record);
    const advanced = mutationPolicyGate.updateScope({
      accountFingerprint: record.accountFingerprint,
      scopeId: record.scopeId,
      expectedRevision: record.scopeRevision,
      binding: { ...scope.binding, projectRevision: stateHash },
      constraints: record.scopeConstraints,
    });
    if (!advanced) throw Object.assign(new Error("Mutation Policy scope disappeared before workflow recovery."), { code: "EDIT_CONSTRAINT_VIOLATION" });
    recoveryCrashInjector?.("after_policy_cas_before_journal", record.public.workflowId);
    return commitRecord(record, (draft) => {
      draft.scopeRevision = advanced.revision;
      draft.currentProjectRevision = stateHash;
      draft.public.binding.policyRevision = `policy_revision_${advanced.revision}`;
    });
  };
  const checkpointPolicyContext = ({ workflowId, accountFingerprint, scope, binding, phase, expectedCurrentStateHash = null }) => {
    const correlation = crypto.createHash("sha256")
      .update(`${accountFingerprint}\0${workflowId}\0${phase}\0${scope.revision}\0${binding.revision}`)
      .digest("hex").slice(0, 24);
    return {
      requestId: `request_workflow_${correlation}`,
      operationId: `operation_workflow_${correlation}`,
      executionId: `execution_workflow_${correlation}`,
      scopeId: scope.scopeId,
      scopeRevision: scope.revision,
      projectLibraryId: scope.binding.projectLibraryId,
      projectId: binding.projectId,
      timelineId: binding.timelineId,
      projectRevision: scope.binding.projectRevision,
      timelineRevision: binding.revision,
      resolvedTargets: [{ kind: "timeline", stableId: binding.timelineId, revision: binding.revision }],
      workflowCheckpointAuthority: "sdk_workflow_v1",
      ...(expectedCurrentStateHash ? { expectedCurrentStateHash } : {}),
      closedComposition: true,
      executableStableTargetPrecondition: true,
    };
  };
  const restoreWorkflowStart = async (record, accessToken, expectedLiveRevision) => {
    let scope = mutationPolicyGate.getScope({ accountFingerprint: record.accountFingerprint, scopeId: record.scopeId });
    if (!scope) throw Object.assign(new Error("Mutation Policy scope disappeared during recovery."), { code: "WORKFLOW_RECOVERY_LINEAGE_UNPROVEN" });
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
      record = advanceScopeRevision(record, record.public.binding.revision, record.startStateHash);
      record = bindScopeStateHashForRestore(record, record.startStateHash);
      recoveryCrashInjector?.("after_policy_cas", record.public.workflowId);
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
      record = advanceScopeRevision(record, expectedLiveRevision);
      scope = assertScopeCurrent(record);
    }
    record = bindScopeStateHashForRestore(record, status.state_hash);
    scope = assertScopeCurrent(record);
    record = commitRecord(record, (draft) => {
      draft.recoveryIntent = { expectedLiveRevision, expectedStateHash: status.state_hash, phase: "prepared", preparedAt: nowIso() };
    });
    const restored = await checkpointService.restoreCheckpoint({
      session: { id: record.public.workflowId }, checkpointId: record.checkpointId, accessToken,
      policyContext: checkpointPolicyContext({
        workflowId: record.public.workflowId,
        accountFingerprint: record.accountFingerprint,
        scope,
        binding: { ...record.public.binding, revision: record.currentRevision },
        phase: `restore:${record.public.sequence}`,
        expectedCurrentStateHash: record.recoveryIntent.expectedStateHash,
      }),
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
    record = advanceScopeRevision(record, record.public.binding.revision, record.startStateHash);
    record = bindScopeStateHashForRestore(record, record.startStateHash);
    recoveryCrashInjector?.("after_policy_cas", record.public.workflowId);
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
    resolveStepScope({ accountFingerprint, sdkSessionId, idempotencyKey, binding }) {
      if (typeof idempotencyKey !== "string" || !idempotencyKey) return null;
      const matches = Object.values(state.workflows).filter((record) => record.accountFingerprint === accountFingerprint
        && record.public.status === "active"
        && record.currentRevision === binding.timelineRevision
        && record.public.binding.projectId === binding.projectId
        && record.public.binding.timelineId === binding.timelineId
        && record.public.steps.some((step) => step.idempotencyKey === idempotencyKey && !step.outcome));
      if (matches.length === 0) return null;
      if (matches.length !== 1) throw new Error("Workflow step scope ownership is ambiguous.");
      const record = matches[0];
      const scope = mutationPolicyGate.getScope({ accountFingerprint, scopeId: record.scopeId });
      if (!scope || scope.revision !== record.scopeRevision
        || scope.binding?.projectLibraryId !== binding.projectLibraryId
        || scope.binding?.projectId !== binding.projectId
        || (scope.binding?.projectRevision ?? null) !== record.currentProjectRevision
        || scope.binding?.timelineId !== binding.timelineId
        || scope.binding?.timelineRevision !== binding.timelineRevision
        || JSON.stringify(scope.constraints) !== JSON.stringify(record.scopeConstraints)) {
        throw Object.assign(new Error("Workflow step Mutation Policy scope changed before execution."), { code: "EDIT_CONSTRAINT_VIOLATION" });
      }
      return scope;
    },
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
        if (!sameWorkflowBinding(admitting.binding, binding) || JSON.stringify(admitting.managedClaim ?? null) !== JSON.stringify(managedClaim)) throw Object.assign(new Error("Workflow idempotency key is being admitted for a different target, revision, or authority kind."), { code: "EDIT_CONSTRAINT_VIOLATION" });
        return admitting.task;
      }
      const task = (async () => {
        const targetKey = binding.projectId;
        if (admittingTargets.has(targetKey)) throw Object.assign(new Error("Another mutating workflow is being admitted for this project."), { code: "EDIT_CONSTRAINT_VIOLATION" });
        if (Object.values(state.workflows).some((record) => ownsMutationTarget(record) && record.public.binding.projectId === binding.projectId)) {
          throw Object.assign(new Error("Another mutating workflow already owns this project."), { code: "EDIT_CONSTRAINT_VIOLATION" });
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
            throw Object.assign(new Error("Managed preview or captured runtime context changed before admission."), { code: "EDIT_CONSTRAINT_VIOLATION" });
          }
          admittedManagedPreview = currentPreview;
        }
        const managedReservation = managedClaim ? assertManagedClaimAvailable(accountFingerprint, binding, managedClaim) : null;
        let scope = await findScope(accountFingerprint, binding, { sdkSessionId, accessToken, deadlineAtMs });
        if (admittedManagedPreview) {
          if (admittedManagedPreview.protectedStateDigest !== managedClaim.protectedStateDigest) throw Object.assign(new Error("Protected state changed before managed admission."), { code: "EDIT_CONSTRAINT_VIOLATION" });
          const mutating = admittedManagedPreview.drift.filter((entry) => entry.kind !== "preserve");
          if (mutating.length > 0) preflightManagedAggregate({ accountFingerprint, binding, scope, preview: admittedManagedPreview, claim: managedClaim });
        }
        const workflowId = opaque("workflow_");
        const at = nowIso();
        const authoritativeBinding = { ...binding, policyRevision: `policy_revision_${scope.revision}` };
        const previewEvidence = admittedManagedPreview ? managedPreviewEvidence.get(admittedManagedPreview.previewDigest) : null;
        const previewRows = previewEvidence?.snapshot?.tracks.flatMap((track) => track.clips.map((clip) => ({ track, clip }))) ?? [];
        const plan = admittedManagedPreview?.drift.filter((entry) => entry.kind !== "preserve").map((entry) => {
          const kind = entry.kind === "update" && previewEvidence?.positionMoveKeys?.includes(entry.key) ? "move" : entry.kind;
          const base = { kind, key: entry.key, timelineItemId: entry.timelineItemId ?? null };
          if (kind === "move") return base;
          if (!entry.timelineItemId || (entry.kind !== "remove" && entry.kind !== "update")) return base;
          const target = previewRows.find(({ clip }) => clip.id === entry.timelineItemId);
          if (!target) throw Object.assign(new Error("Managed removal plan lost its exact preview target."), { code: "EDIT_CONSTRAINT_VIOLATION" });
          const closure = new Set([target.clip.id, ...(target.clip.linkedItemIds ?? [])]);
          const closureRows = previewRows.filter(({ clip }) => closure.has(clip.id));
          const removalTargets = closureRows.map(({ track, clip }) => ({
            track: { type: track.type, index: track.index }, affectedItemIds: [clip.id], clipId: clip.id,
            range: structuredClone(clip.recordRange), name: clip.name,
          })).sort((left, right) => left.track.type.localeCompare(right.track.type) || left.track.index - right.track.index || left.clipId.localeCompare(right.clipId));
          if (removalTargets.length !== closure.size) throw Object.assign(new Error("Managed removal plan could not persist its complete exact linked closure."), { code: "EDIT_CONSTRAINT_VIOLATION" });
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
        const record = { accountFingerprint, ownerSessionId, checkpointId: null, nativeTimelineId: null, startStateHash: null, currentStateHash: null, currentProjectRevision: scope.binding.projectRevision ?? null, stepReservations: {}, scopeId: scope.scopeId, scopeRevision: scope.revision, scopeConstraints: structuredClone(scope.constraints), currentRevision: binding.revision, executablePlan: plan, managedAffectedItemIds: structuredClone(previewEvidence?.affectedItemIds ?? []), managedAffectedNativeItemIds: structuredClone(previewEvidence?.affectedNativeItemIds ?? []), managedAssetCustody: structuredClone(previewEvidence?.managedAssetCustody ?? null), protectedStateDigest: managedClaim?.protectedStateDigest ?? null, protectedFamilyDigest: previewEvidence?.protectedFamilyDigest ?? null, ...(managedClaim ? { managedClaim: structuredClone(managedClaim) } : {}), ...(managedReservation ? { managedOwnershipKey: managedReservation.key, priorManagedOwnership: structuredClone(managedReservation.previous) } : {}), public: { workflowId, authorityKind: managedClaim ? "managed" : "generic", binding: authoritativeBinding, sequence: 1, status: "checkpoint_pending", steps: [], createdAt: at, updatedAt: at, retentionExpiresAt: new Date(clock() + WORKFLOW_JOURNAL_RETENTION_MS).toISOString(), manualRecoveryRequired: false, cancellationDoesNotRollback: true } };
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
          throw Object.assign(new Error("Live timeline revision changed before workflow checkpoint capture."), { code: "EDIT_CONSTRAINT_VIOLATION" });
        }
        const checkpoint = await checkpointService.createBeforePromptCheckpoint({
          session: { id: workflowId }, prompt: "SDK checkpoint-backed workflow", accessToken,
          policyContext: checkpointPolicyContext({ workflowId, accountFingerprint, scope, binding, phase: "create" }),
        });
        if (checkpoint.project_name !== before.projectName || checkpoint.timeline_name !== before.timelineName
          || checkpoint.timeline_id !== before.nativeTimelineId) throw new Error("Checkpoint native project or timeline identity changed.");
        const checkpointStateHash = checkpoint.db_hash ?? checkpoint.state_hash;
        const checkpointStatus = await checkpointService.getStatus({ session: { id: workflowId }, accessToken });
        if (typeof checkpointStateHash !== "string" || checkpointStatus?.state_hash !== checkpointStateHash
          || checkpointStatus.project_name !== before.projectName || checkpointStatus.timeline_name !== before.timelineName
          || checkpointStatus.timeline_id !== before.nativeTimelineId) {
          throw Object.assign(new Error("Project state changed during workflow checkpoint capture."), { code: "EDIT_CONSTRAINT_VIOLATION" });
        }
        const after = await inspectBinding();
        if (after.projectId !== before.projectId || after.timelineId !== before.timelineId || after.revision !== before.revision
          || after.nativeTimelineId !== before.nativeTimelineId) throw Object.assign(new Error("Live timeline changed during workflow checkpoint capture."), { code: "EDIT_CONSTRAINT_VIOLATION" });
        const startStateHash = checkpointStateHash;
        return mutate(owned(workflowId, accountFingerprint), (draft) => {
          draft.checkpointId = checkpoint.id; draft.nativeTimelineId = before.nativeTimelineId; draft.startStateHash = startStateHash; draft.currentStateHash = startStateHash;
          draft.scopeRevision = scope.revision; draft.public.binding.policyRevision = `policy_revision_${scope.revision}`; draft.public.status = "active";
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
      assertScopeCurrent(record);
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
      if (record.public.status !== "active" || !record.managedClaim) throw Object.assign(new Error("Only an active managed workflow can prepare a step."), { code: "EDIT_CONSTRAINT_VIOLATION" });
      const step = record.public.steps.find((item) => item.name === name);
      if (!step || step.operationId || step.outcome) throw Object.assign(new Error("Managed step is not an unresolved reservation."), { code: "EDIT_CONSTRAINT_VIOLATION" });
      return mutate(record, (draft) => { draft.stepReservations[name] = { ...(draft.stepReservations[name] ?? {}), expectedActionId: actionId, expectedInputDigest: sha256(input), preparedAt: nowIso() }; });
    },
    async attach({ accountFingerprint, workflowId, name, operationId, assertRequestCurrent = () => {} }) {
      let record = owned(workflowId, accountFingerprint);
      if (record.public.status !== "active" && record.public.status !== "cancellation_requested") throw Object.assign(new Error("Workflow is no longer attachable."), { code: "OPERATION_EXPIRED", workflowId });
      assertScopeCurrent(record);
      const step = record.public.steps.find((item) => item.name === name);
      if (!step || step.outcome) throw Object.assign(new Error("Workflow step was not reserved or is already terminal."), { code: "EDIT_CONSTRAINT_VIOLATION" });
      const operation = operationAuthority.inspectOwned({ accountFingerprint, operationId });
      const input = operation.private.normalizedInput;
      if (!operationMatchesReservation(record, step, operation)) throw Object.assign(new Error("Workflow operation ownership does not match its exact binding, action, and input."), { code: "EDIT_CONSTRAINT_VIOLATION" });
      if (step.operationId && step.operationId !== operationId) throw Object.assign(new Error("Workflow step operation cannot be replaced."), { code: "EDIT_CONSTRAINT_VIOLATION" });
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
          if (!operationMatchesReservation(record, step, operation)) throw Object.assign(new Error("Recovered workflow operation does not match its exact binding, action, and input."), { code: "EDIT_CONSTRAINT_VIOLATION" });
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
        ?? operation.result?.value?.timelineRevision
        ?? operation.result?.value?.payload?.revision?.after;
      if (outcome === "completed" && operation.possibleMutation === "confirmed") {
        if (typeof nextRevision !== "string") outcome = "manual_recovery_required";
        else {
          try {
            const liveBeforeStatus = await liveInspectionService.readWorkflowBinding({
              operation: "timeline.snapshot", projectId: record.public.binding.projectId, timelineId: record.public.binding.timelineId,
            }, { accessToken });
            if (liveBeforeStatus.nativeTimelineId !== record.nativeTimelineId || liveBeforeStatus.revision !== nextRevision) throw new Error("Workflow live revision does not match the operation result.");
            const status = await checkpointService.getStatus({ session: { id: record.public.workflowId }, accessToken });
            if (status?.timeline_id !== record.nativeTimelineId || typeof status?.state_hash !== "string") throw new Error("Workflow state hash readback is unavailable.");
            const liveAfterStatus = await liveInspectionService.readWorkflowBinding({
              operation: "timeline.snapshot", projectId: record.public.binding.projectId, timelineId: record.public.binding.timelineId,
            }, { accessToken });
            if (liveAfterStatus.nativeTimelineId !== record.nativeTimelineId || liveAfterStatus.revision !== nextRevision) throw new Error("Workflow live revision changed during state-hash capture.");
            record = advanceScopeRevision(record, nextRevision, status.state_hash);
          }
          catch { outcome = "manual_recovery_required"; }
        }
      }
      return mutate(record, (draft, next) => {
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
          const mappings = [];
          for (const element of draft.managedClaim.elements) {
            const planEntry = draft.executablePlan?.find((entry) => entry.key === element.key);
            let timelineItemId = planEntry?.kind === "create" || planEntry?.kind === "update" ? null : element.adoptTimelineItemId
              ?? draft.priorManagedOwnership?.elementMappings?.find((entry) => entry.key === element.key)?.timelineItemId;
            if (!timelineItemId) {
              const step = draft.public.steps.find((candidate) => candidate.name === `managed-${element.key}-create`);
              if (!step?.operationId || step.outcome !== "completed") throw new Error(`Managed element ${element.key} has no verified workflow operation.`);
              const operation = operationAuthority.inspectOwned({ accountFingerprint, operationId: step.operationId });
              timelineItemId = operation.public.result?.value?.affectedClips?.find((clip) => clip.trackType === "video")?.id;
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
        delete binding.policyRevision;
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
      const verifyProtectedAfterStep = async (name) => {
        const record = owned(snapshot.workflowId, accountFingerprint);
        const current = await liveInspectionService.read({ operation: "timeline.snapshot", projectId: binding.projectId, timelineId: binding.timelineId }, { accessToken, deadlineAtMs: managedInspectionDeadline() });
        if (current.revision !== record.currentRevision) return false;
        const rows = current.tracks.flatMap((track) => track.clips.map((clip) => ({ track, clip })));
        const managedIds = new Set([
          ...(record.managedAffectedItemIds ?? []),
          ...(record.priorManagedOwnership?.elementMappings ?? []).map((entry) => entry.timelineItemId),
          ...binding.managedClaim.elements.map((element) => element.adoptTimelineItemId).filter(Boolean),
        ]);
        for (const step of record.public.steps) {
          if (!step.operationId || step.outcome !== "completed" || !step.name.endsWith("-create")) continue;
          const operation = operationAuthority.inspectOwned({ accountFingerprint, operationId: step.operationId });
          for (const clip of operation.public.result?.value?.affectedClips ?? []) if (typeof clip.id === "string") managedIds.add(clip.id);
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
          } catch { return false; }
          if (familyDigest !== record.protectedFamilyDigest) return false;
        }
        const digest = sha256({ timeline: protectedSnapshot(current, managedIds), protectedFamilies: familyDigest });
        if (digest !== record.protectedStateDigest) return false;
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
        if (current.revision !== currentRevision) throw Object.assign(new Error("Managed removal must resolve against the workflow's current revision."), { code: "EDIT_CONSTRAINT_VIOLATION" });
        const rows = current.tracks.flatMap((track) => track.clips.map((clip) => ({ track, clip })));
        const target = rows.filter(({ clip }) => clip.id === removalTarget.clipId);
        if (target.length !== 1) throw Object.assign(new Error(`Managed element ${entry.key} no longer has one exact removal target.`), { code: "EDIT_CONSTRAINT_VIOLATION" });
        if (target[0].track.type !== removalTarget.track.type || target[0].track.index !== removalTarget.track.index
          || target[0].clip.name !== removalTarget.name || target[0].clip.recordRange.start !== removalTarget.range.start
          || target[0].clip.recordRange.endExclusive !== removalTarget.range.endExclusive) throw Object.assign(new Error(`Managed element ${entry.key} removal selector changed after admission.`), { code: "EDIT_CONSTRAINT_VIOLATION" });
        const affectedItemIds = structuredClone(removalTarget.affectedItemIds);
        const affectedTracks = [structuredClone(removalTarget.track)];
        const expectedLinkTransitions = structuredClone(removalTarget.expectedLinkTransitions ?? []);
        for (const transition of expectedLinkTransitions) {
          const survivor = rows.find(({ clip }) => clip.id === transition.itemId);
          if (!survivor || JSON.stringify([...(survivor.clip.linkedItemIds ?? [])].sort()) !== JSON.stringify([...transition.beforeLinkedItemIds].sort())) {
            throw Object.assign(new Error(`Managed element ${entry.key} reciprocal-link transition changed after admission.`), { code: "EDIT_CONSTRAINT_VIOLATION" });
          }
        }
        const transitionIds = new Set(expectedLinkTransitions.map((transition) => transition.itemId));
        return { operation: "clip_remove", projectId: binding.projectId, timelineId: binding.timelineId, timelineRevision: currentRevision,
          affectedTracks, affectedItemIds, expectedLinkTransitions,
          protectedItemIds: rows.map(({ clip }) => clip.id).filter((id) => !affectedItemIds.includes(id) && !transitionIds.has(id)),
          clipId: removalTarget.clipId, track: structuredClone(removalTarget.track),
          range: { start: removalTarget.range.start, endExclusive: removalTarget.range.endExclusive }, name: removalTarget.name };
      };
      const insertionInput = async (element, currentRevision) => {
        const record = owned(snapshot.workflowId, accountFingerprint);
        const baseline = record.managedAssetCustody;
        if (!baseline) throw Object.assign(new Error("Managed source-asset custody is unavailable."), { code: "EDIT_CONSTRAINT_VIOLATION" });
        const refreshed = await liveInspectionService.captureManagedTimelineAssets({
          projectId: binding.projectId,
          timelineId: binding.timelineId,
          assetIds: binding.managedClaim.elements.map((candidate) => candidate.assetId),
        }, { accessToken, deadlineAtMs: managedInspectionDeadline() });
        if (!sameManagedAssetCustody(refreshed, baseline)) {
          throw Object.assign(new Error("Managed source assets or unrelated Media Pool content changed after admission."), { code: "EDIT_CONSTRAINT_VIOLATION" });
        }
        const refreshedAsset = refreshed.assets.find((candidate) => candidate.id === element.assetId);
        if (!refreshedAsset) throw Object.assign(new Error("Managed source asset lost exact custody."), { code: "EDIT_CONSTRAINT_VIOLATION" });
        const prepared = await liveInspectionService.prepareTimelineEdit({
          action: "insert", projectId: binding.projectId, timelineId: binding.timelineId, timelineRevision: currentRevision,
          source: { id: element.assetId, name: element.assetName, snapshotRevision: refreshedAsset.revision },
          sourceRange: { domain: "source_range", unit: "frames", start: element.sourceStartFrame, endExclusive: element.sourceEndExclusiveFrame },
          at: { domain: "timeline_record", value: { kind: "frames", value: element.atFrame } },
          videoTrackIndex: element.videoTrack, audioTrackIndex: element.audioTrack, linkedAudio: element.linkedAudio,
        }, { accessToken, deadlineAtMs: Date.now() + 60_000 });
        const expectedDuration = managedRecordDuration(element.sourceStartFrame, element.sourceEndExclusiveFrame,
          element.sourceFrameRate, binding.managedClaim.timelineFrameRate);
        if (expectedDuration === null || prepared.impact.recordRange?.start !== element.atFrame
          || prepared.impact.recordRange?.endExclusive !== element.atFrame + expectedDuration) {
          throw Object.assign(new Error("Managed insertion preview returned different mixed-rate record geometry."), { code: "EDIT_CONSTRAINT_VIOLATION" });
        }
        return { impact: prepared.impact };
      };
      const moveInput = async (entry, element, currentRevision) => {
        const current = await liveInspectionService.read({ operation: "timeline.snapshot", projectId: binding.projectId, timelineId: binding.timelineId }, { accessToken, deadlineAtMs: managedInspectionDeadline() });
        if (current.revision !== currentRevision) throw Object.assign(new Error("Managed move must resolve against the workflow's current revision."), { code: "EDIT_CONSTRAINT_VIOLATION" });
        const matches = current.tracks.flatMap((track) => track.clips.map((clip) => ({ track, clip })))
          .filter(({ clip }) => clip.id === entry.timelineItemId);
        const expectedDuration = managedRecordDuration(element.sourceStartFrame, element.sourceEndExclusiveFrame,
          element.sourceFrameRate, binding.managedClaim.timelineFrameRate);
        if (matches.length !== 1 || expectedDuration === null) throw Object.assign(new Error(`Managed element ${entry.key} no longer has one exact move target.`), { code: "EDIT_CONSTRAINT_VIOLATION" });
        const { track, clip } = matches[0];
        if (element.linkedAudio !== "exclude" || track.type !== "video" || track.index !== element.videoTrack
          || clip.linkedItemIds?.length !== 0 || clip.recordRange.endExclusive - clip.recordRange.start !== expectedDuration
          || clip.mediaPoolItemId !== element.assetId || clip.sourceRange?.start !== element.sourceStartFrame
          || clip.sourceRange?.endExclusive !== element.sourceEndExclusiveFrame
          || !sameFrameRate(clip.sourceFrameRate, element.sourceFrameRate)) {
          throw Object.assign(new Error(`Managed element ${entry.key} is no longer a position-only move.`), { code: "EDIT_CONSTRAINT_VIOLATION" });
        }
        return { projectId: binding.projectId, timelineId: binding.timelineId, timelineRevision: currentRevision,
          target: { snapshotId: clip.snapshotId, id: clip.id, trackIndex: track.index,
            recordStartFrame: clip.recordRange.start, recordEndFrame: clip.recordRange.endExclusive,
            name: clip.name, mediaPoolItemId: clip.mediaPoolItemId },
          linkedAudioTargets: [], destination: { trackIndex: element.videoTrack, recordStartFrame: element.atFrame },
          linkedAudio: "exclude", collisionPolicy: "reject" };
      };
      for (const entry of plan.filter((candidate) => candidate.kind === "move")) {
        const element = elements.get(entry.key);
        if (!element) throw new Error(`Managed executable plan refers to absent element ${entry.key}.`);
        if (!await runStep(`managed-${entry.key}-move`, "cutagent.action.timeline.items.move", (revision) => moveInput(entry, element, revision))) return snapshot;
      }
      for (const entry of plan.filter((candidate) => candidate.kind === "remove" || candidate.kind === "update")) {
        if (!Array.isArray(entry.removalTargets) || entry.removalTargets.length === 0) return authority.fail({ accountFingerprint, accessToken, workflowId: snapshot.workflowId });
        for (const removalTarget of entry.removalTargets) {
          const stepName = `managed-${entry.key}-remove-${removalTarget.track.type}-${removalTarget.track.index}`;
          if (!await runStep(stepName, "cutagent.action.timeline.items.delete", (revision) => removalInput(entry, removalTarget, revision))) return snapshot;
        }
      }
      for (const entry of plan.filter((candidate) => candidate.kind === "create" || candidate.kind === "update")) {
        const element = elements.get(entry.key);
        if (!element) throw new Error(`Managed executable plan refers to absent element ${entry.key}.`);
        if (!await runStep(`managed-${entry.key}-create`, "cutagent.action.edit.insert", (revision) => insertionInput(element, revision))) return snapshot;
      }
      const record = owned(snapshot.workflowId, accountFingerprint);
      const finalSnapshot = await liveInspectionService.read({ operation: "timeline.snapshot", projectId: binding.projectId, timelineId: binding.timelineId }, { accessToken, deadlineAtMs: managedInspectionDeadline() });
      if (finalSnapshot.revision !== record.currentRevision) return authority.fail({ accountFingerprint, accessToken, workflowId: snapshot.workflowId });
      const mappings = binding.managedClaim.elements.map((element) => {
        const planEntry = record.executablePlan?.find((entry) => entry.key === element.key);
        const retained = planEntry?.kind === "create" || planEntry?.kind === "update" ? null : element.adoptTimelineItemId
          ?? record.priorManagedOwnership?.elementMappings?.find((entry) => entry.key === element.key)?.timelineItemId;
        const step = record.public.steps.find((entry) => entry.name === `managed-${element.key}-create`);
        const created = step?.operationId ? operationAuthority.inspectOwned({ accountFingerprint, operationId: step.operationId }).public.result?.value?.affectedClips?.find((clip) => clip.trackType === "video")?.id : null;
        return { key: element.key, timelineItemId: retained ?? created };
      });
      if (mappings.some((entry) => typeof entry.timelineItemId !== "string")) return authority.fail({ accountFingerprint, accessToken, workflowId: snapshot.workflowId });
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
        catch { return authority.fail({ accountFingerprint, accessToken, workflowId: snapshot.workflowId }); }
        if (finalProtectedFamilyDigest !== record.protectedFamilyDigest) return authority.fail({ accountFingerprint, accessToken, workflowId: snapshot.workflowId });
      }
      const finalPreview = await previewManaged({ accountFingerprint, accessToken, sdkSessionId, ownershipOverride: { accountFingerprint, ownershipId: binding.managedClaim.ownershipId,
        projectId: binding.projectId, timelineId: binding.timelineId, scope: binding.managedClaim.scope, status: "active", generation: 1,
        revision: record.currentRevision, desiredStateDigest: binding.managedClaim.desiredStateDigest, elementMappings: mappings,
        managedElements: binding.managedClaim.elements, managedAffectedStateDigest: finalAffectedStateDigest },
        program: { projectId: binding.projectId, timelineId: binding.timelineId, revision: record.currentRevision, ownershipId: binding.managedClaim.ownershipId, scope: binding.managedClaim.scope, timelineFrameRate: binding.managedClaim.timelineFrameRate, elements: binding.managedClaim.elements },
        deadlineAtMs: managedInspectionDeadline() });
      const finalAssetCustody = managedPreviewEvidence.get(finalPreview.previewDigest)?.managedAssetCustody ?? null;
      if (!sameManagedAssetCustody(finalAssetCustody, record.managedAssetCustody)) return authority.fail({ accountFingerprint, accessToken, workflowId: snapshot.workflowId });
      if (finalPreview.status !== "no_change" || finalPreview.blockers.length) return authority.fail({ accountFingerprint, accessToken, workflowId: snapshot.workflowId });
      const combinedFinalProtectedStateDigest = sha256({ timeline: protectedSnapshot(finalSnapshot, finalManagedIds), protectedFamilies: finalProtectedFamilyDigest });
      const expectedManagedStateDigest = sha256(binding.managedClaim.elements.map((element) => ({ key: element.key, timelineItemId: mappings.find((entry) => entry.key === element.key).timelineItemId,
        assetId: element.assetId, videoTrack: element.videoTrack, audioTrack: element.audioTrack, atFrame: element.atFrame, sourceStartFrame: element.sourceStartFrame, sourceEndExclusiveFrame: element.sourceEndExclusiveFrame, sourceFrameRate: element.sourceFrameRate, linkedAudio: element.linkedAudio })));
      if (combinedFinalProtectedStateDigest !== record.protectedStateDigest) return authority.fail({ accountFingerprint, accessToken, workflowId: snapshot.workflowId });
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
