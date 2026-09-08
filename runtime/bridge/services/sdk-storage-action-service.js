import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import {z} from "zod";
import {ensureCanonicalPrivateDirectory, writePrivateJsonDurableAtomic} from "./private-storage.js";
import {resolveSdkDirectMutationScope, sdkMutationScopeCandidates} from "./sdk-direct-mutation-scope.js";
import {projectSdkMediaPoolFolderIdentity} from "./sdk-live-inspection-service.js";

const artifactId = z.string().regex(/^artifact_[A-Za-z0-9][A-Za-z0-9._~-]*$/);
const projectId = z.string().regex(/^project_[A-Za-z0-9][A-Za-z0-9._~-]*$/);
const mediaId = z.string().regex(/^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$/);
const mediaFolderId = z.string().regex(/^media_pool_folder_[A-Za-z0-9][A-Za-z0-9._~-]*$/);
const revision = z.string().regex(/^revision_[A-Za-z0-9][A-Za-z0-9._~-]*$/);
const mutationBase = {projectId, precondition: revision};
const INPUTS = Object.freeze({
  "cutagent.action.storage.files": z.object({directoryArtifactId: artifactId, offset: z.number().int().min(0).optional(), limit: z.number().int().min(1).max(100).optional()}).strict(),
  "cutagent.action.storage.import": z.object({...mutationBase, sourceArtifactId: artifactId}).strict(),
  "cutagent.action.storage.import_sequence": z.object({...mutationBase, sourceDirectoryArtifactId: artifactId, sequencePattern: z.string().min(1).max(255).regex(/^[^/\\]+$/u), sourceStartIndex: z.number().int().min(0).optional(), sourceEndIndexInclusive: z.number().int().min(0).optional()}).strict(),
  "cutagent.action.storage.import_subclip": z.object({...mutationBase, sourceArtifactId: artifactId, sourceStartFrame: z.number().int().min(0), sourceEndFrameExclusive: z.number().int().min(1)}).strict(),
  "cutagent.action.storage.matte.add": z.object({...mutationBase, mediaId, matteArtifactIds: z.array(artifactId).min(1).max(64), eye: z.enum(["left", "right"]).optional()}).strict(),
  "cutagent.action.storage.matte.timeline_add": z.object({...mutationBase, matteArtifactIds: z.array(artifactId).min(1).max(64)}).strict(),
  "cutagent.action.storage.reveal": z.object({artifactId}).strict(),
  "cutagent.action.storage.volumes": z.object({}).strict(),
});
const entry = z.object({name: z.string().min(1).max(4096), kind: z.enum(["file", "folder"]), source: z.enum(["davinci_resolve", "filesystem"])}).strict();
const item = z.object({mediaId: z.string().nullable(), name: z.string().min(1).max(4096)}).strict();
const RESULT_DATA = Object.freeze({
  "cutagent.action.storage.files": z.object({directoryArtifactId: artifactId, offset: z.number().int().min(0), limit: z.number().int().min(1), total: z.number().int().min(0), hasMore: z.boolean(), entries: z.array(entry).max(100)}).strict(),
  "cutagent.action.storage.import": z.object({projectId, sourceArtifactId: artifactId, importedItems: z.array(item).min(1).max(100), revision}).strict(),
  "cutagent.action.storage.import_sequence": z.object({projectId, sourceDirectoryArtifactId: artifactId, sequencePattern: z.string(), sourceStartIndex: z.number().int().min(0).nullable(), sourceEndIndexInclusive: z.number().int().min(0).nullable(), media: item, revision}).strict(),
  "cutagent.action.storage.import_subclip": z.object({projectId, sourceArtifactId: artifactId, sourceStartFrame: z.number().int().min(0), sourceEndFrameExclusive: z.number().int().min(1), media: item, revision}).strict(),
  "cutagent.action.storage.matte.add": z.object({projectId, mediaId, matteArtifactIds: z.array(artifactId).min(1).max(64), eye: z.enum(["left", "right"]).nullable(), addedCount: z.number().int().min(0), revision}).strict(),
  "cutagent.action.storage.matte.timeline_add": z.object({projectId, folderId: mediaFolderId, matteArtifactIds: z.array(artifactId).min(1).max(64), addedCount: z.number().int().min(0), revision}).strict(),
  "cutagent.action.storage.reveal": z.object({artifactId, revealed: z.boolean()}).strict(),
  "cutagent.action.storage.volumes": z.object({volumes: z.array(z.object({volumeId: z.string(), name: z.string(), available: z.boolean()}).strict()).max(100)}).strict(),
});

function digest(value) {
  return `sha256:${crypto.createHash("sha256").update(JSON.stringify(value), "utf8").digest("hex")}`;
}
function evidence(modality, summary, value) {
  return {evidenceId: `evidence_${crypto.randomUUID()}`, modality, summary, capturedAt: new Date().toISOString(), digest: digest(value)};
}
function failure(code, message, context, possibleMutation = "none", usage = possibleMutation === "none" ? "released" : "unknown") {
  return {
    kind: code === "STALE_REVISION" ? "stale_revision" : code === "EDIT_CONSTRAINT_VIOLATION" ? "edit_constraint_violation" : code === "CAPABILITY_UNAVAILABLE" ? "capability_unavailable" : code === "VERIFICATION_FAILED" ? "verification_failed" : "operation_failed",
    code, message, retrySafe: false, possibleMutation, usage,
    recovery: possibleMutation === "none" ? ["inspect_state"] : ["inspect_state", "manual_recovery"],
    recoveryGuidance: [possibleMutation === "none" ? "Inspect Storage and acquire a fresh managed artifact or project revision." : "Inspect the Media Pool and Storage state before any retry."],
    readbackRequired: possibleMutation !== "none", requestId: context.requestId, operationId: context.operationId, executionId: context.executionId,
  };
}
function preflightFailure(error, context) {
  const code = ["TARGET_NOT_FOUND", "STALE_REVISION", "EDIT_CONSTRAINT_VIOLATION", "CAPABILITY_UNAVAILABLE"].includes(error?.code) ? error.code : "CAPABILITY_UNAVAILABLE";
  return {status: "failed", possibleMutation: "none", usage: "released", failure: failure(code, error?.message ?? "Storage preflight failed.", context)};
}
function exactProjectScope(gate, accountFingerprint, projectContext, input, actionId, directScope = null) {
  const scopes = sdkMutationScopeCandidates(gate, accountFingerprint, directScope).filter((scope) => scope.binding.level === "project"
    && scope.binding.projectLibraryId === projectContext.privateExecutionIdentity?.projectLibraryId
    && scope.binding.projectId === input.projectId
    && scope.binding.projectRevision === projectContext.value?.projectRevision?.revision
    && (scope.constraints.allowedOperations.length === 0 || scope.constraints.allowedOperations.includes(actionId.replace("cutagent.action.", ""))));
  if (scopes.length !== 1) {
    const error = new Error("Exactly one current user-owned project constraint scope is required for Storage mutation.");
    error.code = "EDIT_CONSTRAINT_VIOLATION";
    throw error;
  }
  return scopes[0];
}
function exactLibraryScope(gate, accountFingerprint, projectContext, actionId, directScope = null) {
  const scopes = sdkMutationScopeCandidates(gate, accountFingerprint, directScope).filter((scope) => scope.binding.level === "account/project-library"
    && scope.binding.projectLibraryId === projectContext.privateExecutionIdentity?.projectLibraryId
    && (scope.constraints.allowedOperations.length === 0 || scope.constraints.allowedOperations.includes(actionId.replace("cutagent.action.", ""))));
  if (scopes.length !== 1) throw Object.assign(new Error("Exactly one current project-library scope is required for Storage reveal."), {code: "EDIT_CONSTRAINT_VIOLATION"});
  return scopes[0];
}
async function readAllMedia(liveInspectionService, rawProjectId) {
  const deadlineAtMs = Date.now() + 60_000;
  const first = await liveInspectionService.readWithMutationGuard({operation: "mediaPool.page", projectId: rawProjectId, offset: 0, pageSize: 32, expectedRevision: null, search: null}, {deadlineAtMs});
  if (!first.privateMediaPoolState || !Array.isArray(first.privateMediaPoolState.entries)) throw new Error("Private complete Media Pool verification state was unavailable.");
  const assets = [...first.value.assets];
  const privateEntries = [...first.privateMediaPoolState.entries];
  let offset = first.value.nextOffset;
  for (let pages = 1; offset !== null && pages < 31_250; pages += 1) {
    const page = await liveInspectionService.readWithMutationGuard({operation: "mediaPool.page", projectId: rawProjectId, offset, pageSize: 32, expectedRevision: first.value.revision, search: null}, {deadlineAtMs});
    if (page.privateMediaPoolState?.poolDigest !== first.privateMediaPoolState.poolDigest || !Array.isArray(page.privateMediaPoolState.entries)) throw new Error("Media Pool changed across bounded verification pages.");
    assets.push(...page.value.assets); privateEntries.push(...page.privateMediaPoolState.entries); offset = page.value.nextOffset;
  }
  if (privateEntries.length !== first.value.total) throw new Error("Bounded Media Pool verification was incomplete.");
  return {...first, assets, privateEntries, revision: first.value.revision};
}
function multiset(rows) {
  const values = new Map();
  for (const row of rows) { const key = digest(row); values.set(key, (values.get(key) ?? 0) + 1); }
  return values;
}
function containsAll(before, after) {
  const remaining = multiset(after);
  for (const [key, count] of multiset(before)) if ((remaining.get(key) ?? 0) < count) return false;
  return true;
}
function projectPolicyContext(context, scope, projectContext, input, targets, referencedPayloadDigests) {
  return {
    requestId: context.requestId, operationId: context.operationId, executionId: context.executionId,
    scopeId: scope.scopeId, scopeRevision: scope.revision,
    projectLibraryId: scope.binding.projectLibraryId, projectId: input.projectId, projectRevision: scope.binding.projectRevision,
    resolvedTargets: targets, referencedPayloadDigests, closedComposition: true, executableStableTargetPrecondition: true,
  };
}
async function projectPreflight({liveInspectionService, mutationPolicyGate, directMutationPolicyAuthority, context, input, actionId}) {
  const projectContext = await liveInspectionService.readWithMutationGuard({operation: "project.context"}, {deadlineAtMs: Date.now() + 60_000});
  if (projectContext.value?.project?.id !== input.projectId) {
    const error = new Error("The exact current project changed before Storage mutation."); error.code = "STALE_REVISION"; throw error;
  }
  const before = await readAllMedia(liveInspectionService, input.projectId);
  if (before.revision !== input.precondition) { const error = new Error("The Media Pool changed after Storage inspection."); error.code = "STALE_REVISION"; throw error; }
  const directScope = await resolveSdkDirectMutationScope({directMutationPolicyAuthority, context, liveInspectionService, level: "project", projectId: input.projectId, inspectedProjectContext: projectContext});
  return {projectContext, before, scope: exactProjectScope(mutationPolicyGate, context.accountFingerprint, projectContext, input, actionId, directScope)};
}
function captureFile(artifactService, context, id) {
  return artifactService.capturePrivateManagedArtifact({artifactId: id, accountFingerprint: context.accountFingerprint});
}
function capturedFiles(artifactService, context, ids) {
  return ids.map((id) => captureFile(artifactService, context, id));
}
function artifactGuardRecord(captured) {
  return captured.treeDigest
    ? {kind: "directory", artifactId: captured.artifactId, path: captured.absolutePath, treeDigest: captured.treeDigest, identity: captured.identity, directoryEntries: captured.directoryEntries, entries: captured.entries}
    : {kind: "file", artifactId: captured.artifactId, path: captured.absolutePath, sha256: captured.sha256, identity: captured.identity};
}
function effectiveSequenceRange(artifact, pattern, startIndex, endIndex) {
  if (startIndex !== undefined && endIndex !== undefined) return {startIndex, endIndex};
  const tokens = [...pattern.matchAll(/%(?:0([1-9][0-9]*))?d/gu)];
  if (tokens.length !== 1 || !Array.isArray(artifact.entries)) return {startIndex, endIndex};
  const token = tokens[0]; const width = token[1] === undefined ? null : Number(token[1]);
  const escape = (value) => value.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&");
  const digits = width === null ? "([0-9]+)" : `([0-9]{${width},})`;
  const matcher = new RegExp(`^${escape(pattern.slice(0, token.index))}${digits}${escape(pattern.slice(token.index + token[0].length))}$`, "u");
  const indices = artifact.entries.flatMap((entry) => {
    const relative = typeof entry?.relativePath === "string" ? entry.relativePath : "";
    if (relative.includes("/") || relative.includes("\\")) return [];
    const match = matcher.exec(relative); if (!match) return [];
    const index = Number(match[1]); return Number.isSafeInteger(index) ? [index] : [];
  }).sort((left, right) => left - right);
  if (indices.length === 0 || new Set(indices).size !== indices.length) throw new Error("Managed image sequence does not contain one exact index set.");
  const selected = indices.filter((index) => (startIndex === undefined || index >= startIndex) && (endIndex === undefined || index <= endIndex));
  if (selected.length === 0) throw new Error("Managed image sequence does not contain the requested range.");
  const effective = {startIndex: startIndex ?? selected[0], endIndex: endIndex ?? selected.at(-1)};
  if (effective.endIndex < effective.startIndex) throw new Error("Managed image sequence range is invalid.");
  return effective;
}
function exactSameRows(left, right) {
  return containsAll(left, right) && containsAll(right, left);
}
async function readMatteState(resolveService, nativeIds = []) {
  const raw = await resolveService.readSdkLiveInspection("storage.mattes", {deadlineAtMs: Date.now() + 60_000, readRequest: {nativeIds}});
  const summary = raw?.summary;
  if (!summary || typeof summary !== "object" || !summary.clip_mattes || !Array.isArray(summary.timeline_mattes) || typeof summary.current_folder_native_id !== "string" || !summary.current_folder_native_id) throw new Error("Authoritative Storage matte inspection was unavailable.");
  return summary;
}
function successfulRead(actionId, data) {
  return {status: "succeeded", possibleMutation: "none", usage: "consumed", result: {actionId, data}, verification: {outcome: "passed", summary: "The bounded managed Storage read completed.", evidence: [evidence("readback", "Read bounded Storage custody without exposing native paths.", data)], protectedStatePreserved: true}};
}

export const STORAGE_ACTION_IDS = Object.freeze(Object.keys(INPUTS));

export function createSdkStorageActions({artifactService, liveInspectionService, resolveService, mutationPolicyGate, storageDir, directMutationPolicyAuthority = null}) {
  if (typeof artifactService?.capturePrivateManagedArtifact !== "function" || typeof artifactService?.capturePrivateManagedDirectory !== "function" || typeof artifactService?.revalidatePrivateManagedDirectory !== "function") throw new TypeError("Storage actions require managed artifact custody.");
  if (typeof liveInspectionService?.readWithMutationGuard !== "function" || typeof resolveService?.executeSdkStorageAction !== "function" || typeof resolveService?.readSdkLiveInspection !== "function" || typeof mutationPolicyGate?.listScopes !== "function") throw new TypeError("Storage actions require live inspection, CutAgent CLI execution, and Mutation Policy.");
  const recoveryDir = ensureCanonicalPrivateDirectory(storageDir, {label: "SDK Storage recovery directory"});
  const journalKeyPath = path.join(recoveryDir, "journal-key.json");
  if (!fs.existsSync(journalKeyPath)) writePrivateJsonDurableAtomic(journalKeyPath, {key: crypto.randomBytes(32).toString("base64url")});
  const journalKey = JSON.parse(fs.readFileSync(journalKeyPath, "utf8")).key;
  if (typeof journalKey !== "string" || journalKey.length < 32) throw new Error("SDK Storage recovery journal key is invalid.");
  const recoveryPath = (operationId) => path.join(recoveryDir, `${crypto.createHash("sha256").update(operationId).digest("hex")}.json`);
  const receiptPath = (operationId) => path.join(recoveryDir, `${crypto.createHash("sha256").update(operationId).digest("hex")}.receipt.json`);
  const journalMac = (value) => crypto.createHmac("sha256", journalKey).update(JSON.stringify(value)).digest("hex");
  const persistRecovery = (context, value) => {
    const filePath = recoveryPath(context.operationId);
    writePrivateJsonDurableAtomic(filePath, {...value, journalMac: journalMac(value)});
    return filePath;
  };
  const readRecovery = (context) => {
    const parsed = JSON.parse(fs.readFileSync(recoveryPath(context.operationId), "utf8"));
    const {journalMac: storedMac, ...value} = parsed;
    const expectedMac = journalMac(value);
    if (typeof storedMac !== "string" || storedMac.length !== expectedMac.length || !crypto.timingSafeEqual(Buffer.from(storedMac), Buffer.from(expectedMac))) throw new Error("SDK Storage recovery journal authentication failed.");
    return value;
  };
  const prepareReceipt = (context) => {
    const filePath = receiptPath(context.operationId);
    fs.rmSync(filePath, {force: true});
    return {receiptPath: filePath, receiptNonce: crypto.randomBytes(24).toString("base64url")};
  };
  const readReceipt = (context, nonce, kind) => {
    const receipt = JSON.parse(fs.readFileSync(receiptPath(context.operationId), "utf8"));
    if (receipt?.nonce !== nonce || receipt?.kind !== kind || !receipt.data || typeof receipt.data !== "object") throw new Error("Storage execution receipt identity mismatch.");
    return receipt.data;
  };
  const actions = Object.fromEntries(STORAGE_ACTION_IDS.map((actionId) => [actionId, {inputSchema: INPUTS[actionId], resultSchema: z.object({actionId: z.literal(actionId), data: RESULT_DATA[actionId]}).strict(), idempotency: actionId.endsWith(".files") || actionId.endsWith(".volumes") ? "optional" : "required"}]));

  actions["cutagent.action.storage.files"].execute = async (context, raw) => {
    try {
      const input = INPUTS["cutagent.action.storage.files"].parse(raw);
      const directory = artifactService.capturePrivateManagedDirectory({artifactId: input.directoryArtifactId, accountFingerprint: context.accountFingerprint});
      const all = [...directory.directories.map((relativePath) => ({name: path.posix.basename(relativePath), kind: "folder", source: "filesystem"})), ...directory.entries.map((entry) => ({name: path.posix.basename(entry.relativePath), kind: "file", source: "filesystem"}))].sort((a, b) => a.name.localeCompare(b.name));
      const offset = input.offset ?? 0; const limit = input.limit ?? 32;
      if (offset > all.length) throw Object.assign(new Error("Storage page offset is outside the managed directory."), {code: "TARGET_NOT_FOUND"});
      return successfulRead("cutagent.action.storage.files", {directoryArtifactId: input.directoryArtifactId, offset, limit, total: all.length, hasMore: offset + limit < all.length, entries: all.slice(offset, offset + limit)});
    } catch (error) { return preflightFailure(error, context); }
  };
  actions["cutagent.action.storage.volumes"].execute = async (context, raw) => {
    try {
      INPUTS["cutagent.action.storage.volumes"].parse(raw);
      const payload = await resolveService.executeSdkStorageAction("volumes", {}, {carrier: "sdk"});
      const rows = Array.isArray(payload) ? payload : Array.isArray(payload?.volumes) ? payload.volumes : [];
      if (rows.length > 100) throw new Error("DaVinci Resolve returned too many mounted volumes for the bounded SDK read.");
      const volumes = rows.map((row) => {
        const nativePath = typeof row === "string" ? row : row?.path;
        if (typeof nativePath !== "string" || !nativePath) throw new Error("DaVinci Resolve returned an invalid mounted volume.");
        return {volumeId: `storage_volume_${crypto.createHash("sha256").update(nativePath).digest("base64url").slice(0, 32)}`, name: path.basename(nativePath) || "Storage volume", available: true};
      });
      return successfulRead("cutagent.action.storage.volumes", {volumes});
    } catch (error) { return preflightFailure(error, context); }
  };

  for (const actionId of STORAGE_ACTION_IDS.filter((id) => !id.endsWith(".files") && !id.endsWith(".volumes"))) {
    actions[actionId].execute = async (context, raw) => {
      const input = INPUTS[actionId].parse(raw);
      if (actionId === "cutagent.action.storage.reveal") {
        let authorization = null; let executionStarted = false;
        try {
          let captured;
          try { captured = captureFile(artifactService, context, input.artifactId); }
          catch { captured = artifactService.capturePrivateManagedDirectory({artifactId: input.artifactId, accountFingerprint: context.accountFingerprint}); }
          const inspected = await liveInspectionService.readWithMutationGuard({operation: "project.context"}, {deadlineAtMs: Date.now() + 60_000});
          const directScope = await resolveSdkDirectMutationScope({directMutationPolicyAuthority, context, liveInspectionService, level: "account/project-library", inspectedProjectContext: inspected});
          const scope = exactLibraryScope(mutationPolicyGate, context.accountFingerprint, inspected, actionId, directScope);
          const recaptured = captured.treeDigest
            ? artifactService.revalidatePrivateManagedDirectory({artifactId: input.artifactId, accountFingerprint: context.accountFingerprint, treeDigest: captured.treeDigest})
            : captureFile(artifactService, context, input.artifactId);
          if ((captured.sha256 ?? captured.treeDigest) !== (recaptured.sha256 ?? recaptured.treeDigest)) throw Object.assign(new Error("Managed artifact changed before reveal."), {code: "STALE_REVISION"});
          const projectLibraryId = inspected.privateExecutionIdentity.projectLibraryId;
          const projectLibraryRevision = inspected.value.projectRevision.revision;
          const revealProjectId = inspected.value.project?.id;
          if (typeof revealProjectId !== "string") throw Object.assign(new Error("A current project is required for protected reveal verification."), {code: "CAPABILITY_UNAVAILABLE"});
          const before = await readAllMedia(liveInspectionService, revealProjectId);
          const policyContext = {
            requestId: context.requestId, operationId: context.operationId, executionId: context.executionId,
            scopeId: scope.scopeId, scopeRevision: scope.revision, projectLibraryId, projectLibraryRevision,
            resolvedTargets: [{kind: "project_library", stableId: projectLibraryId, revision: projectLibraryRevision}],
            referencedPayloadDigests: [captured.sha256 ?? captured.treeDigest], closedComposition: true, executableStableTargetPrecondition: true,
          };
          const guardRecords = [artifactGuardRecord(recaptured)];
          const receipt = prepareReceipt(context);
          const recoveryRecord = {actionId, input, policyContext, projectId: revealProjectId, beforeRevision: before.revision, beforeEntries: before.privateEntries, artifacts: guardRecords, privateInput: {path: recaptured.absolutePath}, receiptNonce: receipt.receiptNonce};
          const artifactGuardPath = persistRecovery(context, recoveryRecord);
          const result = await resolveService.executeSdkStorageAction("reveal", {path: recaptured.absolutePath}, {carrier: "sdk", policyContext: {
            ...policyContext,
          }, artifactGuardPath, artifactDigests: [captured.sha256 ?? captured.treeDigest], artifactGuardDigest: digest(guardRecords), ...receipt, onAuthorization(value) { authorization = value; persistRecovery(context, {...recoveryRecord, decisionId: value?.policyDecision?.decisionId ?? null}); }, onSpawnAttempt() { context.reportExecutionStarted(); executionStarted = true; }});
          const durableReceipt = readReceipt(context, receipt.receiptNonce, "reveal");
          if (result?.revealed !== true || durableReceipt.revealed !== true || durableReceipt.path !== recaptured.absolutePath || !authorization?.policyDecision) throw new Error("DaVinci Resolve did not confirm the managed artifact reveal.");
          const afterContext = await liveInspectionService.readWithMutationGuard({operation: "project.context"}, {deadlineAtMs: Date.now() + 60_000});
          const after = await readAllMedia(liveInspectionService, revealProjectId);
          const preserved = afterContext.privateExecutionIdentity?.projectLibraryId === projectLibraryId
            && afterContext.value?.projectRevision?.revision === projectLibraryRevision
            && exactSameRows(before.privateEntries, after.privateEntries);
          const report = {outcome: preserved ? "passed" : "failed", summary: preserved ? "DaVinci Resolve acknowledged the exact guarded reveal; independent readback proved the project and Media Pool were preserved." : "Protected state changed during Storage reveal.", evidence: [evidence("readback", "Re-read the project and complete Media Pool after the reveal acknowledgement.", {revision: after.revision, preserved}), evidence("structural", "Recorded the native RevealInStorage acknowledgement without claiming an independent selection-state observation.", {artifactId: input.artifactId, acknowledged: result?.revealed === true})], protectedStatePreserved: preserved};
          if (!preserved) return {status: "verification_failed", possibleMutation: "possible", usage: "consumed", failure: failure("VERIFICATION_FAILED", "Storage reveal protected-state verification failed.", context, "possible", "consumed"), verification: report};
          mutationPolicyGate.assertProtectedStateEvidence(authorization.policyDecision.decisionId, report);
          const data = {artifactId: input.artifactId, revealed: true};
          return {status: "succeeded", possibleMutation: "confirmed", usage: "consumed", result: {actionId, data}, verification: report};
        } catch (error) {
          return executionStarted
            ? {status: "failed", possibleMutation: "possible", usage: "consumed", failure: failure("OPERATION_FAILED", "Managed artifact reveal failed after execution started; inspect current Storage state.", context, "possible", "consumed")}
            : preflightFailure(error, context);
        }
      }
      let preflight;
      let artifacts;
      try {
        preflight = await projectPreflight({liveInspectionService, mutationPolicyGate, directMutationPolicyAuthority, context, input, actionId});
        artifacts = actionId === "cutagent.action.storage.import_sequence"
          ? [artifactService.capturePrivateManagedDirectory({artifactId: input.sourceDirectoryArtifactId, accountFingerprint: context.accountFingerprint})]
          : actionId === "cutagent.action.storage.matte.add" || actionId === "cutagent.action.storage.matte.timeline_add"
            ? capturedFiles(artifactService, context, input.matteArtifactIds)
            : [captureFile(artifactService, context, input.sourceArtifactId)];
      } catch (error) { return preflightFailure(error, context); }
      if (actionId === "cutagent.action.storage.import_sequence" && input.sourceEndIndexInclusive !== undefined && input.sourceStartIndex !== undefined && input.sourceEndIndexInclusive < input.sourceStartIndex) return preflightFailure(Object.assign(new Error("Sequence end index precedes its start index."), {code: "CAPABILITY_UNAVAILABLE"}), context);
      if (actionId === "cutagent.action.storage.import_subclip" && input.sourceEndFrameExclusive <= input.sourceStartFrame) return preflightFailure(Object.assign(new Error("Subclip end frame must follow its start frame."), {code: "CAPABILITY_UNAVAILABLE"}), context);
      let target = null;
      let matteBefore = null;
      try {
        if (actionId === "cutagent.action.storage.matte.add") target = await liveInspectionService.resolveMediaPoolPrivateAsset(input.projectId, input.mediaId, input.precondition, {deadlineAtMs: Date.now() + 60_000});
        if (actionId === "cutagent.action.storage.matte.add" || actionId === "cutagent.action.storage.matte.timeline_add") matteBefore = await readMatteState(resolveService, target ? [target.nativeId] : []);
        if (actionId === "cutagent.action.storage.matte.timeline_add") target = {nativeId: matteBefore.current_folder_native_id, stableId: projectSdkMediaPoolFolderIdentity(input.projectId, matteBefore.current_folder_native_id), revision: preflight.before.revision};
      } catch (error) { return preflightFailure(error, context); }
      const artifactDigests = artifacts.map((entry) => entry.sha256 ?? entry.treeDigest);
      const targets = [{kind: "project", stableId: input.projectId, revision: preflight.projectContext.value.projectRevision.revision}, ...(target ? [{kind: "media", stableId: target.stableId ?? input.mediaId, revision: target.revision}] : [])];
      const policyContext = projectPolicyContext(context, preflight.scope, preflight.projectContext, input, targets, artifactDigests);
      let authorization = null; let executionStarted = false; let executionError = null; let rawResult = null; let executionReceipt = null; let privateInput = null;
      try {
        artifacts = actionId === "cutagent.action.storage.import_sequence"
          ? [artifactService.revalidatePrivateManagedDirectory({artifactId: input.sourceDirectoryArtifactId, accountFingerprint: context.accountFingerprint, treeDigest: artifacts[0].treeDigest})]
          : artifacts.map((artifact) => {
              const current = captureFile(artifactService, context, artifact.artifactId);
              if (current.sha256 !== artifact.sha256 || JSON.stringify(current.identity) !== JSON.stringify(artifact.identity)) throw Object.assign(new Error("Managed artifact changed before Storage execution."), {code: "STALE_REVISION"});
              return current;
            });
        const sequenceRange = actionId === "cutagent.action.storage.import_sequence"
          ? effectiveSequenceRange(artifacts[0], input.sequencePattern, input.sourceStartIndex, input.sourceEndIndexInclusive) : null;
        privateInput = actionId === "cutagent.action.storage.import" ? {path: artifacts[0].absolutePath}
          : actionId === "cutagent.action.storage.import_sequence" ? {pattern: path.join(artifacts[0].absolutePath, input.sequencePattern), ...sequenceRange}
            : actionId === "cutagent.action.storage.import_subclip" ? {path: artifacts[0].absolutePath, startFrame: input.sourceStartFrame, endFrame: input.sourceEndFrameExclusive}
              : actionId === "cutagent.action.storage.matte.add" ? {clip: target.name, paths: artifacts.map((entry) => entry.absolutePath), eye: input.eye, nativeMediaId: target.nativeId}
                : {paths: artifacts.map((entry) => entry.absolutePath), nativeFolderId: target.nativeId};
        const guardRecords = artifacts.map(artifactGuardRecord);
        const receipt = prepareReceipt(context);
        const recoveryRecord = {
          actionId, input, policyContext, privateInput, beforeRevision: preflight.before.revision,
          beforeEntries: preflight.before.privateEntries,
          artifacts: guardRecords, target: target ? {name: target.name, nativeId: target.nativeId, stableId: target.stableId} : null,
          matteBefore,
          receiptNonce: receipt.receiptNonce,
        };
        const artifactGuardPath = persistRecovery(context, recoveryRecord);
        rawResult = await resolveService.executeSdkStorageAction(actionId.replace("cutagent.action.storage.", ""), privateInput, {
          carrier: "sdk",
          artifactGuardPath,
          artifactDigests,
          artifactGuardDigest: digest(guardRecords),
          ...receipt,
          mutationGuard: preflight.before.mutationGuard,
          policyContext,
          onAuthorization(value) { authorization = value; persistRecovery(context, {...recoveryRecord, decisionId: value?.policyDecision?.decisionId ?? null}); },
          onSpawnAttempt() { context.reportExecutionStarted(); executionStarted = true; },
        });
        executionReceipt = readReceipt(context, receipt.receiptNonce, actionId.replace("cutagent.action.storage.", ""));
        executionStarted = true;
      } catch (error) { executionError = error; }
      let after;
      try { after = await readAllMedia(liveInspectionService, input.projectId); }
      catch { return {status: executionStarted ? "verification_failed" : "failed", possibleMutation: executionStarted ? "possible" : "none", usage: executionStarted ? "consumed" : "released", failure: failure(executionStarted ? "VERIFICATION_FAILED" : "OPERATION_FAILED", "Storage execution terminal readback is unavailable.", context, executionStarted ? "possible" : "none", executionStarted ? "consumed" : "released")}; }
      const beforeIds = new Set(preflight.before.privateEntries.map((entry) => entry.id).filter(Boolean));
      const newPrivate = after.privateEntries.filter((entry) => entry.entryKind === "asset" && entry.id && !beforeIds.has(entry.id));
      const newIds = new Set(newPrivate.map((entry) => entry.id));
      const imported = after.assets.filter((asset) => newIds.has(asset.id)).map((asset) => ({mediaId: asset.id, name: asset.name}));
      const protectedRows = after.privateEntries.filter((entry) => !newIds.has(entry.id));
      let matched = executionError === null && authorization?.policyDecision && containsAll(preflight.before.privateEntries, protectedRows);
      const receiptNativeIds = new Set(Array.isArray(executionReceipt?.native_ids) ? executionReceipt.native_ids : []);
      const correlatedNativeIds = newPrivate.length > 0 && newPrivate.every((entry) => typeof entry.nativeId === "string" && receiptNativeIds.has(entry.nativeId)) && receiptNativeIds.size === newPrivate.length;
      if (actionId === "cutagent.action.storage.import") matched &&= imported.length >= 1 && correlatedNativeIds && executionReceipt?.path === artifacts[0].absolutePath && newPrivate.some((entry) => entry.sourcePath === artifacts[0].absolutePath);
      else if (actionId === "cutagent.action.storage.import_subclip") matched &&= imported.length >= 1 && correlatedNativeIds && executionReceipt?.path === artifacts[0].absolutePath && executionReceipt?.start_frame === input.sourceStartFrame && executionReceipt?.end_frame === input.sourceEndFrameExclusive && newPrivate.some((entry) => entry.sourcePath === artifacts[0].absolutePath);
      else if (actionId === "cutagent.action.storage.import_sequence") matched &&= imported.length >= 1 && correlatedNativeIds && executionReceipt?.pattern === privateInput.pattern && executionReceipt?.start_index === privateInput.startIndex && executionReceipt?.end_index === privateInput.endIndex && newPrivate.every((entry) => typeof entry.sourcePath === "string" && entry.sourcePath.startsWith(`${artifacts[0].absolutePath}${path.sep}`));
      else if (actionId === "cutagent.action.storage.matte.timeline_add" || actionId === "cutagent.action.storage.matte.add") {
        let matteAfter = null;
        try { matteAfter = await readMatteState(resolveService, actionId.endsWith("timeline_add") ? [] : [target.nativeId]); } catch { matteAfter = null; }
        const expectedPaths = artifacts.map((entry) => entry.absolutePath);
        const beforePaths = actionId.endsWith("timeline_add") ? matteBefore?.timeline_mattes : matteBefore?.clip_mattes?.[target.nativeId];
        const afterPaths = actionId.endsWith("timeline_add") ? matteAfter?.timeline_mattes : matteAfter?.clip_mattes?.[target.nativeId];
        const sameTimelineFolder = !actionId.endsWith("timeline_add") || matteBefore?.current_folder_native_id === matteAfter?.current_folder_native_id;
        matched &&= sameTimelineFolder && Array.isArray(beforePaths) && Array.isArray(afterPaths)
          && beforePaths.every((value) => afterPaths.includes(value)) && expectedPaths.every((value) => afterPaths.includes(value));
      }
      const report = {outcome: matched ? "passed" : "failed", summary: matched ? "The exact managed Storage mutation matched independent Media Pool readback." : "Storage mutation did not match durable terminal readback.", evidence: [evidence("readback", "Read the complete bounded Media Pool after Storage execution.", {revision: after.revision, imported}), evidence("structural", "Verified pre-existing Media Pool entries remained present.", {preserved: containsAll(preflight.before.privateEntries, protectedRows)})], protectedStatePreserved: matched};
      if (!matched) return {status: executionStarted ? "verification_failed" : "failed", possibleMutation: executionStarted ? "possible" : "none", usage: executionStarted ? "consumed" : "released", failure: failure(executionStarted ? "VERIFICATION_FAILED" : "OPERATION_FAILED", "Storage mutation did not reach independently verified terminal state.", context, executionStarted ? "possible" : "none", executionStarted ? "consumed" : "released"), verification: report};
      mutationPolicyGate.assertProtectedStateEvidence(authorization.policyDecision.decisionId, report);
      if (actionId === "cutagent.action.storage.matte.add" && input.eye !== undefined) {
        const eyeReport = {
          ...report,
          summary: `DaVinci Resolve acknowledged the ${input.eye} clip-matte mutation and independent readback observed the exact matte association; no separate eye-state getter was claimed.`,
          evidence: [...report.evidence, evidence("structural", "Recorded the native clip-matte eye acknowledgement separately from the observed matte association.", {eye: input.eye, acknowledged: rawResult?.added === true})],
        };
        const data = {projectId: input.projectId, mediaId: input.mediaId, matteArtifactIds: input.matteArtifactIds, eye: input.eye, addedCount: artifacts.length, revision: after.revision};
        return {status: "succeeded", possibleMutation: "confirmed", usage: "consumed", result: {actionId, data}, verification: eyeReport};
      }
      let data;
      if (actionId === "cutagent.action.storage.import") data = {projectId: input.projectId, sourceArtifactId: input.sourceArtifactId, importedItems: imported.slice(0, 100), revision: after.revision};
      else if (actionId === "cutagent.action.storage.import_sequence") data = {projectId: input.projectId, sourceDirectoryArtifactId: input.sourceDirectoryArtifactId, sequencePattern: input.sequencePattern, sourceStartIndex: input.sourceStartIndex ?? null, sourceEndIndexInclusive: input.sourceEndIndexInclusive ?? null, media: imported[0], revision: after.revision};
      else if (actionId === "cutagent.action.storage.import_subclip") data = {projectId: input.projectId, sourceArtifactId: input.sourceArtifactId, sourceStartFrame: input.sourceStartFrame, sourceEndFrameExclusive: input.sourceEndFrameExclusive, media: imported[0], revision: after.revision};
      else if (actionId === "cutagent.action.storage.matte.add") data = {projectId: input.projectId, mediaId: input.mediaId, matteArtifactIds: input.matteArtifactIds, eye: input.eye ?? null, addedCount: artifacts.length, revision: after.revision};
      else data = {projectId: input.projectId, folderId: target.stableId, matteArtifactIds: input.matteArtifactIds, addedCount: artifacts.length, revision: after.revision};
      return {status: "succeeded", possibleMutation: "confirmed", usage: "consumed", result: {actionId, data}, verification: report};
    };
  }
  for (const [actionId, definition] of Object.entries(actions)) definition.reconcile = async (context, rawInput) => {
    if (actionId.endsWith(".files") || actionId.endsWith(".volumes")) return {status: "failed", possibleMutation: "none", usage: "released", failure: failure("OPERATION_FAILED", "Interrupted bounded Storage read can be retried safely.", context)};
    let journal;
    try {
      journal = readRecovery(context);
      if (journal.actionId !== actionId || JSON.stringify(journal.input) !== JSON.stringify(rawInput) || !Array.isArray(journal.artifacts)) throw new Error("Storage recovery journal identity mismatch.");
      const after = await readAllMedia(liveInspectionService, journal.projectId ?? rawInput.projectId);
      const beforeIds = new Set((journal.beforeEntries ?? []).map((entry) => entry.id).filter(Boolean));
      const newPrivate = after.privateEntries.filter((entry) => entry.entryKind === "asset" && entry.id && !beforeIds.has(entry.id));
      const newIds = new Set(newPrivate.map((entry) => entry.id));
      const imported = after.assets.filter((asset) => newIds.has(asset.id)).map((asset) => ({mediaId: asset.id, name: asset.name}));
      const expectedPaths = journal.artifacts.map((entry) => entry.path);
      const protectedRows = after.privateEntries.filter((entry) => !newIds.has(entry.id));
      const protectedPreserved = Array.isArray(journal.beforeEntries) && exactSameRows(journal.beforeEntries, protectedRows);
      let data = null;
      let matteObservedChange = false;
      let matteObservedPartial = false;
      const importReceipt = actionId.startsWith("cutagent.action.storage.import") ? readReceipt(context, journal.receiptNonce, actionId.replace("cutagent.action.storage.", "")) : null;
      const receiptNativeIds = new Set(Array.isArray(importReceipt?.native_ids) ? importReceipt.native_ids : []);
      const correlatedNativeIds = newPrivate.length > 0 && newPrivate.every((entry) => typeof entry.nativeId === "string" && receiptNativeIds.has(entry.nativeId)) && receiptNativeIds.size === newPrivate.length;
      if (actionId === "cutagent.action.storage.import" && imported.length && correlatedNativeIds && importReceipt.path === expectedPaths[0] && newPrivate.some((entry) => entry.sourcePath === expectedPaths[0])) data = {projectId: rawInput.projectId, sourceArtifactId: rawInput.sourceArtifactId, importedItems: imported.slice(0, 100), revision: after.revision};
      else if (actionId === "cutagent.action.storage.import_sequence" && imported.length && correlatedNativeIds && importReceipt.pattern === journal.privateInput.pattern && importReceipt.start_index === journal.privateInput.startIndex && importReceipt.end_index === journal.privateInput.endIndex && newPrivate.every((entry) => typeof entry.sourcePath === "string" && entry.sourcePath.startsWith(`${expectedPaths[0]}${path.sep}`))) data = {projectId: rawInput.projectId, sourceDirectoryArtifactId: rawInput.sourceDirectoryArtifactId, sequencePattern: rawInput.sequencePattern, sourceStartIndex: rawInput.sourceStartIndex ?? null, sourceEndIndexInclusive: rawInput.sourceEndIndexInclusive ?? null, media: imported[0], revision: after.revision};
      else if (actionId === "cutagent.action.storage.import_subclip" && imported.length && correlatedNativeIds && importReceipt.path === expectedPaths[0] && importReceipt.start_frame === rawInput.sourceStartFrame && importReceipt.end_frame === rawInput.sourceEndFrameExclusive && newPrivate.some((entry) => entry.sourcePath === expectedPaths[0])) data = {projectId: rawInput.projectId, sourceArtifactId: rawInput.sourceArtifactId, sourceStartFrame: rawInput.sourceStartFrame, sourceEndFrameExclusive: rawInput.sourceEndFrameExclusive, media: imported[0], revision: after.revision};
      else if (actionId === "cutagent.action.storage.matte.add" || actionId === "cutagent.action.storage.matte.timeline_add") {
        const matteAfter = await readMatteState(resolveService, actionId.endsWith("timeline_add") ? [] : [journal.target.nativeId]);
        const beforePaths = actionId.endsWith("timeline_add") ? journal.matteBefore?.timeline_mattes : journal.matteBefore?.clip_mattes?.[journal.target.nativeId];
        const afterPaths = actionId.endsWith("timeline_add") ? matteAfter.timeline_mattes : matteAfter.clip_mattes?.[journal.target.nativeId];
        const sameTimelineFolder = !actionId.endsWith("timeline_add") || journal.matteBefore?.current_folder_native_id === matteAfter.current_folder_native_id;
        matteObservedChange = !sameTimelineFolder || (Array.isArray(beforePaths) && Array.isArray(afterPaths) && JSON.stringify([...beforePaths].sort()) !== JSON.stringify([...afterPaths].sort()));
        matteObservedPartial = Array.isArray(afterPaths) && expectedPaths.some((value) => afterPaths.includes(value)) && !expectedPaths.every((value) => afterPaths.includes(value));
        const recoveredTimelineFolderId = actionId.endsWith("timeline_add")
          ? projectSdkMediaPoolFolderIdentity(rawInput.projectId, matteAfter.current_folder_native_id)
          : null;
        const stableTimelineFolder = !actionId.endsWith("timeline_add")
          || (typeof recoveredTimelineFolderId === "string"
            && (journal.target?.stableId === undefined || journal.target.stableId === recoveredTimelineFolderId));
        if (sameTimelineFolder && stableTimelineFolder && Array.isArray(beforePaths) && Array.isArray(afterPaths) && beforePaths.every((value) => afterPaths.includes(value)) && expectedPaths.every((value) => afterPaths.includes(value))) {
          data = actionId.endsWith("timeline_add")
            ? {projectId: rawInput.projectId, folderId: recoveredTimelineFolderId, matteArtifactIds: rawInput.matteArtifactIds, addedCount: expectedPaths.length, revision: after.revision}
            : {projectId: rawInput.projectId, mediaId: rawInput.mediaId, matteArtifactIds: rawInput.matteArtifactIds, eye: rawInput.eye ?? null, addedCount: expectedPaths.length, revision: after.revision};
        }
      } else if (actionId === "cutagent.action.storage.reveal") {
        let recaptured;
        try { recaptured = captureFile(artifactService, context, rawInput.artifactId); }
        catch { recaptured = artifactService.capturePrivateManagedDirectory({artifactId: rawInput.artifactId, accountFingerprint: context.accountFingerprint}); }
        const originalDigest = journal.artifacts[0]?.treeDigest ?? journal.artifacts[0]?.sha256;
        if ((recaptured.treeDigest ?? recaptured.sha256) !== originalDigest) throw new Error("Managed reveal artifact changed before recovery.");
        const currentContext = await liveInspectionService.readWithMutationGuard({operation: "project.context"}, {deadlineAtMs: Date.now() + 60_000});
        const directScope = await resolveSdkDirectMutationScope({directMutationPolicyAuthority, context, liveInspectionService, level: "account/project-library", inspectedProjectContext: currentContext});
        const scope = exactLibraryScope(mutationPolicyGate, context.accountFingerprint, currentContext, actionId, directScope);
        const projectLibraryId = currentContext.privateExecutionIdentity.projectLibraryId;
        const projectLibraryRevision = currentContext.value.projectRevision.revision;
        const policyContext = {requestId: context.requestId, operationId: context.operationId, executionId: context.executionId, scopeId: scope.scopeId, scopeRevision: scope.revision, projectLibraryId, projectLibraryRevision, resolvedTargets: [{kind: "project_library", stableId: projectLibraryId, revision: projectLibraryRevision}], referencedPayloadDigests: [originalDigest], closedComposition: true, executableStableTargetPrecondition: true};
        const guardRecords = [artifactGuardRecord(recaptured)];
        const privateInput = {path: recaptured.absolutePath};
        persistRecovery(context, {...journal, policyContext, artifacts: guardRecords, privateInput});
        let authorization = null;
        const result = await resolveService.executeSdkStorageAction("reveal", privateInput, {carrier: "sdk", policyContext, artifactGuardPath: recoveryPath(context.operationId), artifactDigests: [originalDigest], artifactGuardDigest: digest(guardRecords), receiptPath: receiptPath(context.operationId), receiptNonce: journal.receiptNonce, onAuthorization(value) { authorization = value; }});
        const durableReceipt = readReceipt(context, journal.receiptNonce, "reveal");
        const afterContext = await liveInspectionService.readWithMutationGuard({operation: "project.context"}, {deadlineAtMs: Date.now() + 60_000});
        const afterReplay = await readAllMedia(liveInspectionService, journal.projectId ?? rawInput.projectId);
        const preserved = result?.revealed === true && durableReceipt.revealed === true && durableReceipt.path === recaptured.absolutePath && authorization?.policyDecision
          && afterContext.privateExecutionIdentity?.projectLibraryId === projectLibraryId
          && afterContext.value?.projectRevision?.revision === projectLibraryRevision
          && afterReplay.revision === projectLibraryRevision
          && Array.isArray(journal.beforeEntries) && exactSameRows(journal.beforeEntries, afterReplay.privateEntries);
        if (preserved) {
          const report = {outcome: "passed", summary: "Replayed the guarded reveal acknowledgement and independently verified preserved project and Media Pool state.", evidence: [evidence("readback", "Re-read project and complete Media Pool state after reveal recovery replay.", {revision: afterReplay.revision}), evidence("structural", "Recorded the replayed RevealInStorage acknowledgement without claiming an independent selection-state observation.", {artifactId: rawInput.artifactId, acknowledged: true})], protectedStatePreserved: true};
          mutationPolicyGate.assertProtectedStateEvidence(authorization.policyDecision.decisionId, report);
          return {status: "succeeded", possibleMutation: "confirmed", usage: "consumed", result: {actionId, data: {artifactId: rawInput.artifactId, revealed: true}}, verification: report};
        }
        return {status: "verification_failed", possibleMutation: "possible", usage: "consumed", failure: failure("VERIFICATION_FAILED", "Reveal recovery replay did not preserve the exact authorized project and Media Pool state.", context, "possible", "consumed")};
      }
      if (data && protectedPreserved && journal.decisionId) {
        const report = {outcome: "passed", summary: "Recovered exact Storage terminal state from the durable pre-spawn journal and independent readback.", evidence: [evidence("readback", "Matched post-crash state against the durable pre-spawn Storage journal.", {revision: after.revision})], protectedStatePreserved: true};
        mutationPolicyGate.assertProtectedStateEvidence(journal.decisionId, report);
        return {status: "succeeded", possibleMutation: "confirmed", usage: "consumed", result: {actionId, data}, verification: report};
      }
      if ((actionId === "cutagent.action.storage.matte.add" || actionId === "cutagent.action.storage.matte.timeline_add") && matteObservedChange) {
        const possibleMutation = matteObservedPartial ? "partial" : "possible";
        return {status: "verification_failed", possibleMutation, usage: "consumed", failure: failure("VERIFICATION_FAILED", "Recovery observed a partial or unexpected matte association change.", context, possibleMutation, "consumed")};
      }
      if (after.revision === journal.beforeRevision) return {status: "failed", possibleMutation: "none", usage: context.snapshot?.usage ?? "released", failure: failure("OPERATION_FAILED", "Authoritative recovery readback proved the Storage mutation was not applied.", context, "none", context.snapshot?.usage ?? "released")};
    } catch {
      // Fall through to truthful uncertain recovery when the durable journal or readback is unavailable.
    }
    return {status: "recovery_failed", possibleMutation: "unknown", usage: context.snapshot?.usage ?? "unknown", failure: {kind: "recovery_failed", code: "RECOVERY_FAILED", message: "Storage recovery could not establish one exact terminal state.", retrySafe: false, possibleMutation: "unknown", usage: context.snapshot?.usage ?? "unknown", recovery: ["inspect_state", "manual_recovery"], recoveryGuidance: ["Inspect the Media Pool before retrying."], readbackRequired: true}};
  };
  return Object.freeze(actions);
}
