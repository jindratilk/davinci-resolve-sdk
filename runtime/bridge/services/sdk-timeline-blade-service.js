import crypto from "node:crypto";
import {
  sdkTimelineBladeInputSchema,
  sdkTimelineBladeResultSchema,
} from "../contracts/generated/sdk-operations.js";
import {resolveSdkDirectMutationScope, sdkMutationScopeCandidates} from "./sdk-direct-mutation-scope.js";

const ACTION_ID = "cutagent.action.edit.blade";

function digest(value) {
  return `sha256:${crypto.createHash("sha256").update(JSON.stringify(value), "utf8").digest("hex")}`;
}

function evidence(modality, summary, value) {
  return { evidenceId: `evidence_${crypto.randomUUID()}`, modality, summary, capturedAt: new Date().toISOString(), digest: digest(value) };
}

function failure(code, message, context, possibleMutation = "none", usage = possibleMutation === "none" ? "released" : "unknown") {
  const kind = code === "STALE_REVISION" ? "stale_revision"
    : code === "EDIT_CONSTRAINT_VIOLATION" ? "edit_constraint_violation"
      : code === "RECOVERY_FAILED" ? "recovery_failed"
        : code === "VERIFICATION_FAILED" ? "verification_failed" : "operation_failed";
  return {
    kind, code, message, retrySafe: false, possibleMutation, usage,
    recovery: possibleMutation === "none" ? ["inspect_state"] : ["inspect_state", "manual_recovery"],
    recoveryGuidance: [possibleMutation === "none" ? "Inspect the current timeline and submit a fresh exact split target." : "Inspect the current timeline before any further mutation."],
    readbackRequired: possibleMutation !== "none",
    requestId: context.requestId, operationId: context.operationId, executionId: context.executionId,
  };
}

function locate(snapshot, id) {
  const matches = snapshot.tracks.flatMap((track) => track.clips
    .filter((clip) => clip.id === id)
    .map((clip) => ({ track, clip })));
  return matches.length === 1 ? matches[0] : null;
}

function locateSnapshotTarget(snapshot, target) {
  const matches = snapshot.tracks.flatMap((track) => track.clips
    .filter((clip) => clip.snapshotId === target.snapshotId)
    .map((clip) => ({ track, clip })));
  if (matches.length !== 1) return null;
  const found = matches[0];
  return found.clip.id === target.id
    && found.track.type === target.trackType
    && found.track.index === target.trackIndex
    && found.clip.recordRange.start === target.recordStartFrame
    && found.clip.recordRange.endExclusive === target.recordEndFrame
    && found.clip.name === target.name
    && found.clip.mediaPoolItemId === target.mediaPoolItemId
    ? found : null;
}

function protectedState(snapshot, excludedIds = new Set()) {
  return {
    project: snapshot.project,
    timeline: snapshot.timeline,
    frameRate: snapshot.frameRate,
    start: snapshot.start,
    markers: snapshot.markers.map(({ snapshotRevision: _revision, ...marker }) => marker),
    tracks: snapshot.tracks.map((track) => ({
      type: track.type,
      index: track.index,
      name: track.name,
      enabled: track.enabled,
      locked: track.locked,
      clips: track.clips.filter((clip) => !excludedIds.has(clip.id)).map((clip) => ({
        id: clip.id,
        name: clip.name,
        recordRange: clip.recordRange,
        duration: clip.duration,
        sourceRange: clip.sourceRange,
        mediaPoolItemId: clip.mediaPoolItemId,
        linkedItemIds: clip.linkedItemIds,
      })),
    })),
  };
}

function exactScope(gate, accountFingerprint, input, targets, directScope = null) {
  const affectedTrackTypes = new Set(targets.map((target) => target.track.type));
  const scopes = sdkMutationScopeCandidates(gate, accountFingerprint, directScope).filter((scope) => (
    scope.binding.level === "project+timeline"
    && scope.binding.projectId === input.projectId
    && scope.binding.timelineId === input.timelineId
    && scope.binding.timelineRevision === input.timelineRevision
    && (scope.constraints.allowedOperations.length === 0 || scope.constraints.allowedOperations.includes("edit.blade"))
    && [...affectedTrackTypes].every((type) => scope.constraints.allowedTrackTypes.length === 0 || scope.constraints.allowedTrackTypes.includes(type))
  ));
  if (scopes.length !== 1) {
    const error = new Error("Exactly one current user-owned scope must authorize the exact split and every affected track.");
    error.code = "EDIT_CONSTRAINT_VIOLATION";
    throw error;
  }
  return scopes[0];
}

function collectClosedTargets(snapshot, target, splitFrame) {
  if (target.clip.id === null || target.clip.sourceRange === null || target.clip.linkedItemIds === null) return null;
  const targets = [target];
  const expectedIds = new Set([target.clip.id, ...target.clip.linkedItemIds]);
  for (const linkedId of target.clip.linkedItemIds) {
    const linked = locate(snapshot, linkedId);
    if (!linked || linked.clip.id === null || linked.clip.sourceRange === null || linked.clip.linkedItemIds === null) return null;
    targets.push(linked);
  }
  if (targets.some(({ track, clip }) => (
    !["video", "audio"].includes(track.type)
    || track.locked !== false
    || clip.recordRange.start >= splitFrame
    || clip.recordRange.endExclusive <= splitFrame
    || clip.linkedItemIds.some((id) => !expectedIds.has(id))
    || !clip.linkedItemIds.every((id) => locate(snapshot, id)?.clip.linkedItemIds?.includes(clip.id))
  ))) return null;
  return targets;
}

function expectedSegment(before, after, splitFrame, side) {
  const recordStart = side === "left" ? before.clip.recordRange.start : splitFrame;
  const recordEnd = side === "left" ? splitFrame : before.clip.recordRange.endExclusive;
  const recordDuration = before.clip.recordRange.endExclusive - before.clip.recordRange.start;
  const sourceDuration = before.clip.sourceRange.endExclusive - before.clip.sourceRange.start;
  const sourceOffset = recordDuration > 0
    ? Math.round(((splitFrame - before.clip.recordRange.start) * sourceDuration) / recordDuration)
    : Number.NaN;
  const sourceSplit = before.clip.sourceRange.start + sourceOffset;
  if (!Number.isSafeInteger(sourceSplit)) return null;
  const sourceStart = side === "left" ? before.clip.sourceRange.start : sourceSplit;
  const sourceEnd = side === "left" ? sourceSplit : before.clip.sourceRange.endExclusive;
  const sourceRangeMatches = (range) => range
    && range.start === sourceStart
    && (range.endExclusive === sourceEnd
      || (side === "left" && sourceDuration !== recordDuration && range.endExclusive === sourceEnd + 1));
  const matches = after.tracks.flatMap((track) => track.type === before.track.type && track.index === before.track.index
    ? track.clips.filter((clip) => (
      clip.id !== null
      && clip.name === before.clip.name
      && clip.mediaPoolItemId === before.clip.mediaPoolItemId
      && clip.recordRange.start === recordStart
      && clip.recordRange.endExclusive === recordEnd
      // A suffixed native source origin can make DaVinci Resolve round the
      // left segment's projected end up by one frame. The right segment keeps
      // the exact calculated source origin and end.
      && sourceRangeMatches(clip.sourceRange)
    )).map((clip) => ({ track, clip }))
    : []);
  return matches.length === 1 ? matches[0] : null;
}

function segmentResult(before, after, role, side) {
  return {
    id: after.clip.id,
    originalId: before.clip.id,
    role,
    side,
    trackType: after.track.type,
    trackIndex: after.track.index,
    recordStartFrame: after.clip.recordRange.start,
    recordEndFrame: after.clip.recordRange.endExclusive,
    sourceStartFrame: after.clip.sourceRange?.start ?? null,
    sourceEndFrame: after.clip.sourceRange?.endExclusive ?? null,
    mediaPoolItemId: after.clip.mediaPoolItemId,
  };
}

export function createSdkTimelineBladeActions({ liveInspectionService, resolveService, mutationPolicyGate, directMutationPolicyAuthority = null }) {
  if (typeof liveInspectionService?.readWithMutationGuard !== "function") throw new TypeError("Timeline splits require guarded live inspection.");
  if (typeof resolveService?.executeSdkTimelineBlade !== "function") throw new TypeError("Timeline splits require the CutAgent CLI mutation boundary.");
  return {
    [ACTION_ID]: {
      inputSchema: sdkTimelineBladeInputSchema,
      resultSchema: sdkTimelineBladeResultSchema,
      idempotency: "required",
      async execute(context, rawInput) {
        const input = sdkTimelineBladeInputSchema.parse(rawInput);
        const inspectRequest = { operation: "timeline.snapshot", projectId: input.projectId, timelineId: input.timelineId };
        const inspected = await liveInspectionService.readWithMutationGuard(inspectRequest, { deadlineAtMs: Date.now() + 60_000 });
        const before = inspected.value;
        if (before.revision !== input.timelineRevision) {
          return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "The timeline changed before the split could execute.", context) };
        }
        const target = locateSnapshotTarget(before, input.target);
        const targets = target ? collectClosedTargets(before, target, input.recordFrame) : null;
        if (!target || !targets) {
          return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "The exact split target, linked topology, source ranges, or unlocked track state changed.", context) };
        }
        const privateTargets = targets.map((item) => {
          const nativeId = inspected.privateTimelineItemNativeIdByPublicId?.get(item.clip.id);
          return typeof nativeId === "string" && nativeId ? {
            id: nativeId,
            trackType: item.track.type,
            trackIndex: item.track.index,
            recordStartFrame: item.clip.recordRange.start,
            recordEndFrame: item.clip.recordRange.endExclusive,
            name: item.clip.name,
          } : null;
        });
        if (privateTargets.some((item) => item === null)) {
          return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "Private execution identity was unavailable for an exact split target.", context) };
        }
        let scope;
        try {
          const directScope = await resolveSdkDirectMutationScope({directMutationPolicyAuthority, context, liveInspectionService, level: "project+timeline", projectId: input.projectId, timelineId: input.timelineId, timelineRevision: input.timelineRevision});
          scope = exactScope(mutationPolicyGate, context.accountFingerprint, input, targets, directScope);
        } catch (error) {
          return { status: "failed", possibleMutation: "none", usage: "not_reserved", failure: failure("EDIT_CONSTRAINT_VIOLATION", error.message, context, "none", "not_reserved") };
        }
        const resolvedTargets = targets.flatMap((item) => [
          { kind: "clip", stableId: item.clip.id, revision: input.timelineRevision, trackType: item.track.type, trackIndex: item.track.index },
          { kind: "track", stableId: item.track.snapshotId, revision: input.timelineRevision, trackType: item.track.type, trackIndex: item.track.index },
        ]);
        const policyContext = {
          requestId: context.requestId, operationId: context.operationId, executionId: context.executionId,
          scopeId: scope.scopeId, scopeRevision: scope.revision,
          projectLibraryId: scope.binding.projectLibraryId, projectId: input.projectId, timelineId: input.timelineId,
          projectRevision: scope.binding.projectRevision, timelineRevision: input.timelineRevision,
          resolvedTargets, affectedTrackTypes: [...new Set(targets.map((item) => item.track.type))],
          closedComposition: true, executableStableTargetPrecondition: true,
        };
        let releaseProof;
        try {
          releaseProof = mutationPolicyGate.bindVerifiedProtectedTargets({
            accountFingerprint: context.accountFingerprint, executionId: context.executionId,
            scopeId: scope.scopeId, scopeRevision: scope.revision, timelineRevision: input.timelineRevision,
          });
        } catch (error) {
          return { status: "failed", possibleMutation: "none", usage: "not_reserved", failure: failure("EDIT_CONSTRAINT_VIOLATION", error.message, context, "none", "not_reserved") };
        }
        let authorization = null;
        let executionError = null;
        try {
          try {
            await resolveService.executeSdkTimelineBlade(input, targets, {
              mutationGuard: inspected.mutationGuard,
              privateTargets,
              policyContext,
              onAuthorization(value) { authorization = value; },
            });
          } catch (error) { executionError = error; }
        } finally { releaseProof(); }

        if (executionError?.cli_error_code === "STALE_REVISION") {
          return {
            status: "failed", possibleMutation: "none", usage: "released",
            failure: failure("STALE_REVISION", "The exact split target changed before the CutAgent CLI mutation boundary.", context),
          };
        }

        let after;
        try { after = (await liveInspectionService.readWithMutationGuard(inspectRequest, { deadlineAtMs: Date.now() + 60_000 })).value; } catch {
          return {
            status: "verification_failed", possibleMutation: "possible", usage: "unknown",
            failure: failure("VERIFICATION_FAILED", "Timeline readback was unavailable after the split.", context, "possible"),
            verification: { outcome: "failed", summary: "Post-split timeline readback was unavailable.", evidence: [evidence("readback", "Post-split timeline readback failed.", { actionId: ACTION_ID })], protectedStatePreserved: null },
          };
        }
        const pairs = targets.map((item) => ({
          before: item,
          left: expectedSegment(item, after, input.recordFrame, "left"),
          right: expectedSegment(item, after, input.recordFrame, "right"),
        }));
        const segmentIds = new Set(pairs.flatMap(({ left, right }) => [left?.clip.id, right?.clip.id]).filter(Boolean));
        const originalIds = new Set(targets.map((item) => item.clip.id));
        const protectedPreserved = digest(protectedState(before, originalIds)) === digest(protectedState(after, segmentIds));
        const topologyPreserved = pairs.every((pair, index) => pair.left && pair.right && [pair.left, pair.right].every((segment, sideIndex) => {
          const side = sideIndex === 0 ? "left" : "right";
          const expectedLinks = pair.before.clip.linkedItemIds.map((linkedId) => {
            const linkedIndex = targets.findIndex((item) => item.clip.id === linkedId);
            return linkedIndex < 0 ? null : pairs[linkedIndex]?.[side]?.clip.id;
          });
          return expectedLinks.every(Boolean)
            && segment.clip.linkedItemIds !== null
            && segment.clip.linkedItemIds.length === expectedLinks.length
            && segment.clip.linkedItemIds.every((id) => expectedLinks.includes(id));
        }));
        const expected = pairs.every(({ left, right }) => left && right) && topologyPreserved && protectedPreserved;
        const report = {
          outcome: expected ? "passed" : "failed",
          summary: expected ? "Every affected item split at the exact frame with linked topology and protected state preserved." : "Split segments, linked topology, or protected state did not match.",
          evidence: [
            evidence("readback", "Read back the complete timeline after the split.", after.tracks),
            evidence("structural", "Compared every non-target timeline item before and after the split.", { before: protectedState(before, originalIds), after: protectedState(after, segmentIds) }),
          ],
          protectedStatePreserved: protectedPreserved,
        };
        if (expected) {
          if (authorization?.policyDecision) mutationPolicyGate.assertProtectedStateEvidence(authorization.policyDecision.decisionId, report);
          return {
            status: "succeeded", possibleMutation: "confirmed", usage: "consumed", verification: report,
            result: {
              actionId: ACTION_ID,
              timelineRevision: after.revision,
              splitFrame: input.recordFrame,
              segments: pairs.flatMap(({ before: original, left, right }, index) => [
                segmentResult(original, left, index === 0 ? "target" : "linked", "left"),
                segmentResult(original, right, index === 0 ? "target" : "linked", "right"),
              ]),
              protectedStatePreserved: true,
            },
          };
        }
        const unchanged = digest(protectedState(before)) === digest(protectedState(after));
        if (unchanged) {
          const policyDenied = executionError?.cli_error_code === "EDIT_CONSTRAINT_VIOLATION";
          return {
            status: "failed", possibleMutation: "none", usage: policyDenied ? "not_reserved" : "released",
            failure: failure(policyDenied ? "EDIT_CONSTRAINT_VIOLATION" : "OPERATION_FAILED", executionError?.message ?? "The split made no verified change.", context, "none", policyDenied ? "not_reserved" : "released"),
            ...(executionError?.cli_error_code === "EDIT_MUTATION_RESTORED" ? { recovery: { state: "restored", summary: "The original timeline state was restored.", evidence: report.evidence, manualRecoveryRequired: false } } : {}),
          };
        }
        if (executionError?.cli_error_code === "EDIT_MUTATION_RECOVERY_FAILED") {
          return {
            status: "recovery_failed", possibleMutation: "partial", usage: "consumed",
            failure: failure("RECOVERY_FAILED", executionError.message, context, "partial", "consumed"), verification: report,
            recovery: { state: "failed", summary: "Automatic split recovery did not restore the expected state.", evidence: report.evidence, manualRecoveryRequired: true },
          };
        }
        return {
          status: "verification_failed", possibleMutation: "possible", usage: "consumed",
          failure: failure("VERIFICATION_FAILED", executionError?.message ?? "The split produced an unexpected timeline state.", context, "possible", "consumed"),
          verification: report,
          recovery: { state: "manual_required", summary: "Inspect the current timeline before retrying this split.", evidence: report.evidence, manualRecoveryRequired: true },
        };
      },
    },
  };
}
