import crypto from "node:crypto";
import path from "node:path";
import { z } from "zod";
import {
  sdkColorEffectAddInputSchema,
  sdkColorGradeApplyInputSchema,
  sdkColorMutationResultSchema,
  sdkColorNodeAddInputSchema,
  sdkColorNodeLabelSetInputSchema,
  sdkColorPrimarySetInputSchema,
} from "../contracts/generated/sdk-operations.js";

const ACTIONS = Object.freeze({
  "cutagent.action.color.page.primary_set": { kind: "primary_set", schema: sdkColorPrimarySetInputSchema },
  "cutagent.action.color.page.node_add": { kind: "node_add", schema: sdkColorNodeAddInputSchema },
  "cutagent.action.color.node.label_set": { kind: "node_label_set", schema: sdkColorNodeLabelSetInputSchema },
  "cutagent.action.color.grade_apply": { kind: "grade_apply", schema: sdkColorGradeApplyInputSchema, extension: ".drx" },
  "cutagent.action.color.page.resolvefx_add": { kind: "effect_add", schema: sdkColorEffectAddInputSchema },
});

const GRADE_PROOF_REQUIRED = new Set(["primary_set", "node_add", "grade_apply", "effect_add"]);

const verifiedStatusSchema = z.enum(["verified", "db_readback_verified"]);
const primaryVerificationSchema = z.object({
  status: z.enum(["verified", "db_readback_verified", "render_unverified"]),
  params_verified: z.record(z.string(), z.number().finite()),
  readback_status: z.literal("db_readback_verified").optional(),
  readback_verified: z.literal(true).optional(),
}).passthrough().superRefine((value, context) => {
  if (value.status === "render_unverified"
    && (value.readback_status !== "db_readback_verified" || value.readback_verified !== true)) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      message: "Render-unverified primary proof requires exact verified DB readback.",
    });
  }
});
const colorExecutionSchemas = Object.freeze({
  primary_set: z.object({
    verification: primaryVerificationSchema,
  }).passthrough(),
  node_add: z.object({
    requested_kind: z.enum(["serial", "parallel", "layer"]),
    node_index: z.number().int().positive(),
    node_count: z.number().int().positive(),
    verification: z.object({
      status: verifiedStatusSchema,
      kind: z.enum(["serial", "parallel", "layer"]),
      node_index: z.number().int().positive(),
      node_count: z.number().int().positive(),
      preserved_existing_node_count: z.number().int().positive().nullish(),
      preserved_existing_containers_verified: z.boolean().nullish(),
    }).passthrough(),
  }).passthrough(),
  node_label_set: z.object({ message: z.string().min(1) }).passthrough(),
  grade_apply: z.object({
    path: z.string().min(1), mode: z.number().int().min(0).max(2), applied: z.literal(true), verified: z.literal(true),
    verification: z.object({ changed: z.literal(true), before_signature_sha256: z.string().regex(/^[a-f0-9]{64}$/), after_signature_sha256: z.string().regex(/^[a-f0-9]{64}$/) }).passthrough(),
  }).passthrough(),
  effect_add: z.object({
    plugin_id: z.string().min(1),
    verification: z.object({ status: verifiedStatusSchema, node_index: z.number().int().positive(), plugin_id: z.string().min(1), removed: z.literal(false) }).passthrough(),
  }).passthrough(),
});

const digest = (value) => `sha256:${crypto.createHash("sha256").update(JSON.stringify(value)).digest("hex")}`;
const evidence = (modality, summary, value) => ({ evidenceId: `evidence_${crypto.randomUUID()}`, modality, summary, capturedAt: new Date().toISOString(), digest: digest(value) });
const safeExecutionMessage = (error) => error?.cli_error_code === "STALE_REVISION"
  ? "The exact Color target changed before CutAgent CLI could apply the mutation."
  : "CutAgent CLI could not complete the semantic Color mutation.";

const diagnosticToken = (value) => typeof value === "string" && /^[A-Za-z0-9_.:-]{1,160}$/.test(value.trim())
  ? value.trim()
  : null;

function colorExecutionDiagnostic(error, actionId, context) {
  const details = error?.cli_error_details && typeof error.cli_error_details === "object" && !Array.isArray(error.cli_error_details)
    ? error.cli_error_details
    : {};
  const partialResult = details.partial_result && typeof details.partial_result === "object" && !Array.isArray(details.partial_result)
    ? details.partial_result
    : {};
  const rollback = details.rollback_after_failed_render_proof
    ?? partialResult.rollback_after_failed_render_proof
    ?? null;
  const rollbackProof = rollback && typeof rollback === "object" && !Array.isArray(rollback)
    ? {
      performed: typeof rollback.rollback_performed === "boolean" ? rollback.rollback_performed : null,
      errorPresent: typeof rollback.rollback_error === "string" && rollback.rollback_error.length > 0,
      steps: Array.isArray(rollback.rollback_steps)
        ? rollback.rollback_steps.map(diagnosticToken).filter(Boolean).slice(0, 12)
        : [],
    }
    : null;
  return {
    phase: "executeSdkColorMutation",
    actionId,
    operationId: context.operationId,
    executionId: context.executionId,
    errorClass: diagnosticToken(error?.name) ?? "Error",
    errorCode: diagnosticToken(error?.cli_error_code) ?? diagnosticToken(error?.code),
    reason: diagnosticToken(details.reason),
    rollbackProof,
  };
}

function failure(code, message, context, possibleMutation = "none", usage = possibleMutation === "none" ? "released" : "unknown") {
  return {
    kind: code === "STALE_REVISION" ? "stale_revision" : code === "CAPABILITY_UNAVAILABLE" ? "capability_unavailable" : code === "VERIFICATION_FAILED" ? "verification_failed" : "operation_failed",
    code, message, retrySafe: false, possibleMutation, usage,
    recovery: possibleMutation === "none" ? ["inspect_state"] : ["inspect_state", "manual_recovery"],
    recoveryGuidance: [possibleMutation === "none" ? "Inspect Color state and create a fresh impact preview." : "Inspect the exact Color target before any further mutation."],
    readbackRequired: possibleMutation !== "none", requestId: context.requestId, operationId: context.operationId, executionId: context.executionId,
  };
}

function targetMatches(snapshot, input) {
  return snapshot.project.id === input.projectId && snapshot.timeline.id === input.timelineId
    && snapshot.clip.id === input.clipId && snapshot.track.index === input.trackIndex
    && snapshot.nodeStackLayerIndex === input.nodeStackLayerIndex
    && snapshot.clip.recordRange.start === input.recordFrame;
}

function exactTimelineStartFrame(snapshot) {
  const start = snapshot?.start?.value;
  if (start?.kind !== "frames" || !Number.isSafeInteger(start.value) || start.value < 0) {
    throw new TypeError("Color mutation requires an exact non-negative timeline start frame.");
  }
  return start.value;
}

function structuralTimeline(snapshot) {
  return { project: snapshot.project, timeline: snapshot.timeline, frameRate: snapshot.frameRate, start: snapshot.start,
    tracks: snapshot.tracks.map((track) => ({ type: track.type, index: track.index, name: track.name, enabled: track.enabled, locked: track.locked,
      clips: track.clips.map(({ snapshotId: _a, snapshotTrackId: _b, snapshotRevision: _c, ...clip }) => clip) })), markers: snapshot.markers.map(({ snapshotRevision: _r, ...marker }) => marker) };
}

const primaryNames = Object.freeze({ colorBoost: "color_boost", midtoneDetail: "mid_detail" });
const effectPluginIds = Object.freeze({
  gaussian_blur: "com.blackmagicdesign.resolvefx.boxblur",
  sharpen: "com.blackmagicdesign.resolvefx.sharpen",
  film_grain: "com.blackmagicdesign.resolvefx.filmgrain",
});
const sameNumber = (left, right) => typeof left === "number" && Math.abs(left - right) <= 0.001;

function expected(kind, beforeRead, afterRead, input, execution, assetPath) {
  const before = beforeRead.value;
  const after = afterRead.value;
  const beforePrivate = beforeRead.privateColorState;
  const afterPrivate = afterRead.privateColorState;
  if (!targetMatches(after, input) || !beforePrivate || !afterPrivate) return { ok: false, rendered: false };
  const proof = colorExecutionSchemas[kind].safeParse(execution);
  if (!proof.success) return { ok: false, rendered: false };
  const verified = proof.data;
  if (kind === "node_add") {
    const added = input.topology === "serial" ? 1 : 2;
    const expectedIndex = before.nodeGraph.nodeCount + 1;
    const priorTopology = beforePrivate.grade?.topology;
    const afterTopology = afterPrivate.grade?.topology;
    const topologyPreserved = input.topology === "serial"
      ? priorTopology?.kind === afterTopology?.kind
      : afterTopology?.kind === input.topology;
    const preservedContainers = Array.isArray(priorTopology?.containerDigests) && Array.isArray(afterTopology?.containerDigests)
      && priorTopology.containerDigests.every((hash, index) => afterTopology.containerDigests[index] === hash);
    const executionPreserved = input.topology !== "serial" || (
      verified.verification.preserved_existing_node_count === before.nodeGraph.nodeCount
      && verified.verification.preserved_existing_containers_verified === true
    );
    const renderGraphPreserved = input.topology !== "parallel"
      || digest(priorTopology?.renderDigests) === digest(afterTopology?.renderDigests);
    return { ok: verified.requested_kind === input.topology && verified.verification.kind === input.topology
      && verified.node_index === expectedIndex && verified.verification.node_index === expectedIndex
      && verified.node_count === before.nodeGraph.nodeCount + added && verified.verification.node_count === verified.node_count
      && after.nodeGraph.nodeCount === verified.node_count
      && topologyPreserved && priorTopology?.nodeCount === before.nodeGraph.nodeCount
      && afterTopology?.nodeCount === verified.node_count && priorTopology?.exact === true && afterTopology?.exact === true
      && priorTopology.structureSha256 !== afterTopology.structureSha256 && preservedContainers && executionPreserved && renderGraphPreserved, rendered: false };
  }
  const node = "nodeIndex" in input ? after.nodeGraph.nodes.find((candidate) => candidate.index === input.nodeIndex) : null;
  if (kind === "node_label_set") {
    const prior = before.nodeGraph.nodes.find((candidate) => candidate.index === input.nodeIndex);
    return { ok: prior?.label !== input.label && node?.label === input.label, rendered: false };
  }
  if (kind === "effect_add") {
    const pluginId = effectPluginIds[input.effect];
    const beforePluginId = beforePrivate.grade?.resolveFxByNode?.[String(input.nodeIndex)];
    const afterPluginId = afterPrivate.grade?.resolveFxByNode?.[String(input.nodeIndex)];
    return { ok: Boolean(node && verified.plugin_id === pluginId && verified.verification.plugin_id === pluginId
      && verified.verification.node_index === input.nodeIndex && beforePluginId === null && afterPluginId === pluginId
      && beforePrivate.grade?.topology?.structureSha256 !== afterPrivate.grade?.topology?.structureSha256), rendered: false };
  }
  if (kind === "primary_set") {
    const actual = afterPrivate.grade?.primaryByNode?.[String(input.nodeIndex)] ?? {};
    const exact = Object.entries(input.correction).every(([name, value]) => {
      const wireName = primaryNames[name] ?? name;
      return sameNumber(verified.verification.params_verified[wireName], value) && sameNumber(actual[wireName], value);
    });
    return { ok: Boolean(exact && beforePrivate.grade?.sha256 !== afterPrivate.grade?.sha256), rendered: verified.render_proof?.status === "verified" };
  }
  const mode = { none: 0, source_timecode: 1, start_frame: 2 }[input.alignment];
  return { ok: Boolean(assetPath && verified.path === assetPath && verified.mode === mode
    && beforePrivate.grade?.sha256 === verified.verification.before_signature_sha256
    && afterPrivate.grade?.sha256 === verified.verification.after_signature_sha256
    && beforePrivate.grade?.sha256 !== afterPrivate.grade?.sha256), rendered: verified.render_proof?.status === "verified" };
}

function checkpointFromExecution(execution) {
  const hasDbBackup = Boolean(execution?.backup_path || execution?.backupPath || execution?.session?.backup_path);
  return { availability: hasDbBackup ? "available" : "unavailable", restored: false };
}

export function createSdkColorActions({ liveInspectionService, resolveService, colorAssetService, incidentReporterService = null }) {
  if (typeof liveInspectionService?.readWithMutationGuard !== "function") throw new TypeError("Color actions require guarded live inspection.");
  if (typeof resolveService?.executeSdkColorMutation !== "function") throw new TypeError("Color actions require the CutAgent CLI mutation boundary.");
  return Object.fromEntries(Object.entries(ACTIONS).map(([actionId, definition]) => [actionId, {
    inputSchema: definition.schema, resultSchema: sdkColorMutationResultSchema, idempotency: "required",
    async execute(context, rawInput) {
      const input = definition.schema.parse(rawInput);
      const colorRequest = { operation: "color.current", projectId: input.projectId, timelineId: input.timelineId, nodeStackLayerIndex: input.nodeStackLayerIndex };
      const timelineRequest = { operation: "timeline.snapshot", projectId: input.projectId, timelineId: input.timelineId };
      const beforeRead = await liveInspectionService.readWithMutationGuard(colorRequest, { deadlineAtMs: Date.now() + 60_000 });
      const before = beforeRead.value;
      if (before.revision !== input.colorRevision || before.timelineRevision !== input.timelineRevision || !targetMatches(before, input)) {
        return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "The exact Color target, graph, or timeline changed after preview.", context) };
      }
      if (input.nodeStackLayerIndex !== 1 && definition.kind !== "node_label_set") {
        return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("CAPABILITY_UNAVAILABLE", "This Color mutation route is not yet node-stack-layer aware; inspect the first layer or use node-label mutation.", context) };
      }
      if ("nodeIndex" in input && !before.nodeGraph.nodes.some((node) => node.index === input.nodeIndex)) {
        return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "The selected Color node no longer exists.", context) };
      }
      if (GRADE_PROOF_REQUIRED.has(definition.kind) && !beforeRead.privateColorState?.grade) {
        return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("CAPABILITY_UNAVAILABLE", "This Color mutation requires exact Disk-project grade proof, which is unavailable for the current project storage.", context) };
      }
      const beforeTopology = beforeRead.privateColorState?.grade?.topology;
      if (definition.kind === "node_add" && (beforeTopology?.exact !== true || beforeTopology?.kind !== "serial"
        || (input.topology === "serial" && input.afterNodeIndex !== before.nodeGraph.nodeCount)
        || (input.topology !== "serial" && (before.nodeGraph.nodeCount !== 1 || input.afterNodeIndex !== 1)))) {
        return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "The inspected Color graph no longer supports the requested node topology.", context) };
      }
      if (definition.kind === "effect_add" && beforeRead.privateColorState?.grade?.resolveFxByNode?.[String(input.nodeIndex)] !== null) {
        return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "The inspected Color node already contains an effect; replacement is not exposed by this SDK slice.", context) };
      }
      const beforeTimeline = await liveInspectionService.read(timelineRequest, { deadlineAtMs: Date.now() + 60_000 });
      let assetPath;
      if (definition.extension) {
        try {
          const asset = await colorAssetService.ensure({ ...input.asset, purpose: "download", confirmed: true, pin: true });
          if (path.extname(asset.file_name ?? asset.path).toLowerCase() !== definition.extension) throw new Error(`This Color operation requires a ${definition.extension} asset.`);
          assetPath = asset.path;
        } catch {
          return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("OPERATION_FAILED", `The requested ${definition.extension} Color Library asset could not be prepared.`, context) };
        }
      }
      let execution; let executionError;
      try { execution = await resolveService.executeSdkColorMutation(definition.kind, input, { mutationGuard: beforeRead.mutationGuard, assetPath, timelineStartFrame: exactTimelineStartFrame(beforeTimeline) }); }
      catch (error) {
        executionError = error;
        const diagnostic = colorExecutionDiagnostic(error, actionId, context);
        incidentReporterService?.record?.({
          category: "runtime_failure",
          fingerprint: `sdk-color-action:${actionId}:executeSdkColorMutation:${diagnostic.errorCode ?? diagnostic.errorClass}`,
          message: "SDK Color mutation failed at the CutAgent CLI execution boundary.",
          metadata: diagnostic,
        });
      }
      let afterRead; let after; let afterTimeline;
      for (let attempt = 0; attempt < 3 && !afterRead; attempt += 1) {
        try {
          const candidateColor = await liveInspectionService.readWithMutationGuard(colorRequest, { deadlineAtMs: Date.now() + 60_000 });
          const candidateTimeline = await liveInspectionService.read(timelineRequest, { deadlineAtMs: Date.now() + 60_000 });
          afterRead = candidateColor;
          after = candidateColor.value;
          afterTimeline = candidateTimeline;
        } catch {
          afterRead = undefined;
          after = undefined;
          afterTimeline = undefined;
          if (attempt < 2) await new Promise((resolve) => setTimeout(resolve, 250));
        }
      }
      if (!afterRead) {
        return { status: "verification_failed", possibleMutation: "possible", usage: "unknown", failure: failure("VERIFICATION_FAILED", "Independent Color readback was unavailable after execution.", context, "possible"),
          verification: { outcome: "failed", summary: "Post-mutation Color readback was unavailable.", evidence: [evidence("readback", "Color readback unavailable.", { actionId })], protectedStatePreserved: null } };
      }
      const protectedPreserved = digest(structuralTimeline(beforeTimeline)) === digest(structuralTimeline(afterTimeline));
      const semantic = expected(definition.kind, beforeRead, afterRead, input, execution, assetPath);
      const report = { outcome: semantic.ok && protectedPreserved ? "passed" : "failed", summary: semantic.ok && protectedPreserved ? "The exact requested Color effect and protected timeline structure were independently verified." : "Exact Color effect proof or protected timeline structure did not match the impact preview.",
        evidence: [evidence("readback", "Validated action-specific CutAgent CLI proof and independently read back the exact stable Color target.", { kind: definition.kind, revision: after.revision, clipId: after.clip.id, nodeGraph: after.nodeGraph, privateColorState: afterRead.privateColorState, execution }), evidence("structural", "Compared non-Color timeline structure before and after execution.", { before: structuralTimeline(beforeTimeline), after: structuralTimeline(afterTimeline) }), ...(semantic.rendered ? [evidence("rendered", "CutAgent CLI returned verified before/after render proof for this Color route.", execution?.render_proof)] : [])], protectedStatePreserved: protectedPreserved };
      if (semantic.ok && protectedPreserved && !executionError) {
        return { status: "succeeded", possibleMutation: "confirmed", usage: "consumed", verification: report,
          result: { kind: definition.kind, colorRevision: after.revision, timelineRevision: after.timelineRevision, nodeStackLayerIndex: after.nodeStackLayerIndex, clipId: after.clip.id, nodeCount: after.nodeGraph.nodeCount,
          affectedNodeIndex: definition.kind === "node_add" ? before.nodeGraph.nodeCount + 1 : input.nodeIndex ?? null, checkpoint: checkpointFromExecution(execution) } };
      }
      const unchanged = before.revision === after.revision && digest(before.nodeGraph) === digest(after.nodeGraph) && protectedPreserved;
      if (unchanged) return { status: "failed", possibleMutation: "none", usage: "released", failure: failure(executionError?.cli_error_code === "STALE_REVISION" ? "STALE_REVISION" : "OPERATION_FAILED", executionError ? safeExecutionMessage(executionError) : "The Color mutation made no verified change.", context) };
      return { status: "verification_failed", possibleMutation: "possible", usage: "consumed", postTimelineRevision: after.timelineRevision, failure: failure("VERIFICATION_FAILED", executionError ? safeExecutionMessage(executionError) : "The Color mutation produced an unexpected state.", context, "possible", "consumed"), verification: report,
        recovery: { state: "manual_required", summary: "Automatic recovery could not be proven; inspect the exact Color target before continuing.", evidence: report.evidence, manualRecoveryRequired: true } };
    },
  }]));
}
