import crypto from "node:crypto";
import {
  sdkTimelineItemMoveInputSchema,
  sdkTimelineItemMoveResultSchema,
} from "../contracts/generated/sdk-operations.js";
import {resolveSdkDirectMutationScope, sdkMutationScopeCandidates} from "./sdk-direct-mutation-scope.js";

const ACTION_ID = "cutagent.action.timeline.items.move";

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
    recoveryGuidance: [possibleMutation === "none" ? "Inspect the current timeline and create a fresh move preview." : "Inspect the current timeline before any further mutation."],
    readbackRequired: possibleMutation !== "none",
    ...(code === "RECOVERY_FAILED" ? { recoveryOutcome: { status: "failed", summary: "Automatic timeline-item recovery did not restore the expected state.", manualRecoveryRequired: true } } : {}),
    requestId: context.requestId, operationId: context.operationId, executionId: context.executionId,
  };
}

function exactScope(gate, accountFingerprint, input, directScope = null) {
  const scopes = sdkMutationScopeCandidates(gate, accountFingerprint, directScope).filter((scope) => (
    scope.binding.level === "project+timeline"
    && scope.binding.projectId === input.projectId
    && scope.binding.timelineId === input.timelineId
    && scope.binding.timelineRevision === input.timelineRevision
    && (scope.constraints.allowedOperations.length === 0 || scope.constraints.allowedOperations.includes("timeline.items.move"))
  ));
  if (scopes.length !== 1) {
    const error = new Error("Exactly one current user-owned timeline-item constraint scope is required.");
    error.code = "EDIT_CONSTRAINT_VIOLATION";
    throw error;
  }
  return scopes[0];
}

function locateByDurableId(snapshot, id) {
  const matches = snapshot.tracks.flatMap((track) => track.clips
    .filter((clip) => clip.id === id)
    .map((clip) => ({ track, clip })));
  return matches.length === 1 ? matches[0] : null;
}

function exactDescriptor(found, expected) {
  return found.track.index === expected.trackIndex
    && found.clip.id === expected.id
    && found.clip.name === expected.name
    && found.clip.recordRange.start === expected.recordStartFrame
    && found.clip.recordRange.endExclusive === expected.recordEndFrame
    && found.clip.mediaPoolItemId === expected.mediaPoolItemId;
}

function overlapsFrames(clip, startFrame, endFrame) {
  return clip.recordRange.start < endFrame && startFrame < clip.recordRange.endExclusive;
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

function stableTarget(found, revision) {
  return {
    kind: "clip",
    stableId: found.clip.id ?? found.clip.snapshotId,
    revision,
    trackType: found.track.type,
    trackIndex: found.track.index,
  };
}

function findPost(snapshot, before, trackType, trackIndex, startFrame, endFrame) {
  const matches = snapshot.tracks.flatMap((track) => track.type === trackType && track.index === trackIndex
    ? track.clips.filter((clip) => (
      (before.clip.id !== null ? clip.id === before.clip.id : true)
      && clip.name === before.clip.name
      && clip.mediaPoolItemId === before.clip.mediaPoolItemId
      && clip.recordRange.start === startFrame
      && clip.recordRange.endExclusive === endFrame
    )).map((clip) => ({ track, clip }))
    : []);
  return matches.length === 1 ? matches[0] : null;
}

function observation(before, after, role) {
  const sourceObservable = before.clip.sourceRange !== null && after.clip.sourceRange !== null;
  return {
    id: after.clip.id,
    role,
    name: after.clip.name,
    mediaPoolItemId: after.clip.mediaPoolItemId,
    before: { trackIndex: before.track.index, recordStartFrame: before.clip.recordRange.start, recordEndFrame: before.clip.recordRange.endExclusive },
    after: { trackIndex: after.track.index, recordStartFrame: after.clip.recordRange.start, recordEndFrame: after.clip.recordRange.endExclusive },
    sourceRangePreservation: sourceObservable ? "preserved" : "not_observable",
  };
}

export function createSdkTimelineItemMoveActions({ liveInspectionService, resolveService, mutationPolicyGate, directMutationPolicyAuthority = null }) {
  if (typeof liveInspectionService?.readWithMutationGuard !== "function") throw new TypeError("Timeline-item moves require guarded live inspection.");
  if (typeof resolveService?.executeSdkTimelineItemMove !== "function") throw new TypeError("Timeline-item moves require the CutAgent CLI mutation boundary.");
  return {
    [ACTION_ID]: {
      inputSchema: sdkTimelineItemMoveInputSchema,
      resultSchema: sdkTimelineItemMoveResultSchema,
      idempotency: "required",
      async execute(context, rawInput) {
        const input = sdkTimelineItemMoveInputSchema.parse(rawInput);
        const inspectRequest = { operation: "timeline.snapshot", projectId: input.projectId, timelineId: input.timelineId };
        const inspected = await liveInspectionService.readWithMutationGuard(inspectRequest, { deadlineAtMs: Date.now() + 60_000 });
        const before = inspected.value;
        if (before.revision !== input.timelineRevision) {
          return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "The timeline changed after the item move preview.", context) };
        }
        const target = locateByDurableId(before, input.target.id);
        if (!target || target.track.type !== "video" || target.clip.id === null || !exactDescriptor(target, input.target)) {
          return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "The exact video item changed or disappeared after preview.", context) };
        }
        const privateTargetNativeId = inspected.privateTimelineItemNativeIdByPublicId?.get(input.target.id);
        if (typeof privateTargetNativeId !== "string" || !privateTargetNativeId) {
          return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "Private video-item execution identity was unavailable after preview.", context) };
        }
        const privateTarget = { ...input.target, id: privateTargetNativeId };
        const destinationTrack = before.tracks.find((track) => track.type === "video" && track.index === input.destination.trackIndex);
        if (!destinationTrack) return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "The destination video track changed or disappeared.", context) };
        if (target.track.locked !== false || destinationTrack.locked !== false) {
          return { status: "failed", possibleMutation: "none", usage: "not_reserved", failure: failure("EDIT_CONSTRAINT_VIOLATION", "Authoritative unlocked state is required for the source and destination video tracks.", context, "none", "not_reserved") };
        }
        const linked = input.linkedAudioTargets.map((expected) => {
          const found = locateByDurableId(before, expected.id);
          return found && found.track.type === "audio" && exactDescriptor(found, expected) ? found : null;
        });
        if (linked.some((item) => item === null)) {
          return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "A linked audio target changed or became ambiguous.", context) };
        }
        const linkedFound = linked.filter(Boolean);
        const privateLinkedAudioTargets = input.linkedAudioTargets.map((expected) => {
          const nativeId = inspected.privateTimelineItemNativeIdByPublicId?.get(expected.id);
          return typeof nativeId === "string" && nativeId ? { ...expected, id: nativeId } : null;
        });
        if (privateLinkedAudioTargets.some((target) => target === null)) {
          return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "Private linked-audio execution identity was unavailable after preview.", context) };
        }
        const targetLinkedIds = target.clip.linkedItemIds;
        const changesRecordPosition = input.destination.recordStartFrame !== input.target.recordStartFrame;
        const closedGroupIds = new Set([target.clip.id, ...linkedFound.map((item) => item.clip.id)]);
        if (targetLinkedIds === null || targetLinkedIds.length !== linkedFound.length
          || linkedFound.some((item) => item.clip.id === null || !targetLinkedIds.includes(item.clip.id)
            || item.clip.linkedItemIds === null || !item.clip.linkedItemIds.includes(target.clip.id)
            || item.clip.linkedItemIds.some((linkedId) => !closedGroupIds.has(linkedId)))) {
          return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "Authoritative linked A/V topology no longer matches the preview.", context) };
        }
        if (input.linkedAudio === "preserve" && changesRecordPosition && linkedFound.some((item) => item.track.locked !== false)) {
          return { status: "failed", possibleMutation: "none", usage: "not_reserved", failure: failure("EDIT_CONSTRAINT_VIOLATION", "Authoritative unlocked state is required for every affected linked-audio track.", context, "none", "not_reserved") };
        }
        if (input.collisionPolicy === "reject") {
          const targetDuration = input.target.recordEndFrame - input.target.recordStartFrame;
          const destinationEnd = input.destination.recordStartFrame + targetDuration;
          const videoCollision = destinationTrack.clips.some((clip) => (
            clip.snapshotId !== target.clip.snapshotId
            && overlapsFrames(clip, input.destination.recordStartFrame, destinationEnd)
          ));
          const delta = input.destination.recordStartFrame - input.target.recordStartFrame;
          const movingLinkedSnapshotIds = new Set(linkedFound.map((item) => item.clip.snapshotId));
          const linkedCollision = input.linkedAudio === "preserve" && linkedFound.some((item) => item.track.clips.some((clip) => (
            !movingLinkedSnapshotIds.has(clip.snapshotId)
            && overlapsFrames(clip, item.clip.recordRange.start + delta, item.clip.recordRange.endExclusive + delta)
          )));
          if (videoCollision || linkedCollision) {
            return { status: "failed", possibleMutation: "none", usage: "not_reserved", failure: failure("EDIT_CONSTRAINT_VIOLATION", "The destination range now collides with another timeline item.", context, "none", "not_reserved") };
          }
        }
        let scope;
        try {
          const directScope = await resolveSdkDirectMutationScope({directMutationPolicyAuthority, context, liveInspectionService, level: "project+timeline", projectId: input.projectId, timelineId: input.timelineId, timelineRevision: input.timelineRevision});
          scope = exactScope(mutationPolicyGate, context.accountFingerprint, input, directScope);
        } catch (error) {
          return { status: "failed", possibleMutation: "none", usage: "not_reserved", failure: failure("EDIT_CONSTRAINT_VIOLATION", error.message, context, "none", "not_reserved") };
        }
        const movesLinkedAudio = input.linkedAudio === "preserve" && changesRecordPosition;
        const resolvedTargets = [
          stableTarget(target, input.timelineRevision),
          { kind: "track", stableId: target.track.snapshotId, revision: input.timelineRevision, trackType: "video", trackIndex: target.track.index },
          { kind: "track", stableId: destinationTrack.snapshotId, revision: input.timelineRevision, trackType: "video", trackIndex: destinationTrack.index },
          ...(movesLinkedAudio ? linkedFound.flatMap((item) => [
            stableTarget(item, input.timelineRevision),
            { kind: "track", stableId: item.track.snapshotId, revision: input.timelineRevision, trackType: "audio", trackIndex: item.track.index },
          ]) : []),
        ];
        const policyContext = {
          requestId: context.requestId, operationId: context.operationId, executionId: context.executionId,
          scopeId: scope.scopeId, scopeRevision: scope.revision,
          projectLibraryId: scope.binding.projectLibraryId, projectId: input.projectId, timelineId: input.timelineId,
          projectRevision: scope.binding.projectRevision, timelineRevision: input.timelineRevision,
          resolvedTargets, closedComposition: true, executableStableTargetPrecondition: true,
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
            await resolveService.executeSdkTimelineItemMove(input, {
              mutationGuard: inspected.mutationGuard,
              privateTarget,
              privateLinkedAudioTargets,
              policyContext,
              onAuthorization(value) { authorization = value; },
            });
          } catch (error) { executionError = error; }
        } finally { releaseProof(); }

        let after;
        try { after = (await liveInspectionService.readWithMutationGuard(inspectRequest, { deadlineAtMs: Date.now() + 60_000 })).value; } catch {
          return {
            status: "verification_failed", possibleMutation: "possible", usage: "unknown",
            failure: failure("VERIFICATION_FAILED", "Timeline readback was unavailable after the item move.", context, "possible"),
            verification: { outcome: "failed", summary: "Post-mutation timeline readback was unavailable.", evidence: [evidence("readback", "Post-mutation timeline readback failed.", { actionId: ACTION_ID })], protectedStatePreserved: null },
          };
        }
        const delta = input.destination.recordStartFrame - input.target.recordStartFrame;
        const expectedTarget = findPost(after, target, "video", input.destination.trackIndex, input.destination.recordStartFrame, input.destination.recordStartFrame + (input.target.recordEndFrame - input.target.recordStartFrame));
        const linkedDelta = input.linkedAudio === "preserve" ? delta : 0;
        const expectedLinked = linkedFound.map((item) => findPost(
          after, item, "audio", item.track.index,
          item.clip.recordRange.start + linkedDelta,
          item.clip.recordRange.endExclusive + linkedDelta,
        ));
        const excludedIds = new Set([target.clip.id, ...(input.linkedAudio === "preserve" ? linkedFound.map((item) => item.clip.id) : [])]);
        const protectedPreserved = digest(protectedState(before, excludedIds)) === digest(protectedState(after, excludedIds));
        const linkTopologyPreserved = Boolean(expectedTarget)
          && digest(expectedTarget.clip.linkedItemIds) === digest(target.clip.linkedItemIds)
          && expectedLinked.every((item, index) => Boolean(item)
            && digest(item.clip.linkedItemIds) === digest(linkedFound[index].clip.linkedItemIds));
        const sourceAndMediaPreserved = Boolean(expectedTarget)
          && expectedTarget.clip.mediaPoolItemId === target.clip.mediaPoolItemId
          && expectedTarget.clip.duration.value.value === target.clip.duration.value.value
          && digest(expectedTarget.clip.sourceRange) === digest(target.clip.sourceRange)
          && expectedLinked.every((item, index) => Boolean(item)
            && item.clip.mediaPoolItemId === linkedFound[index].clip.mediaPoolItemId
            && item.clip.duration.value.value === linkedFound[index].clip.duration.value.value
            && digest(item.clip.sourceRange) === digest(linkedFound[index].clip.sourceRange));
        const expected = Boolean(expectedTarget)
          && expectedLinked.every(Boolean)
          && sourceAndMediaPreserved
          && linkTopologyPreserved
          && protectedPreserved
          && executionError === null
          && Boolean(authorization?.policyDecision);
        const report = {
          outcome: expected ? "passed" : "failed",
          summary: expected ? "Exact item placement, linked A/V topology, media/source evidence, and protected neighbors matched." : "Timeline-item placement or protected-state readback did not match.",
          evidence: [
            evidence("readback", "Read back the complete timeline after execution.", after.tracks),
            evidence("structural", "Compared complete non-target timeline state before and after execution.", { before: protectedState(before, excludedIds), after: protectedState(after, excludedIds) }),
          ],
          protectedStatePreserved: protectedPreserved,
        };
        if (expected) {
          mutationPolicyGate.assertProtectedStateEvidence(authorization.policyDecision.decisionId, report);
          const movedItems = [observation(target, expectedTarget, "video"), ...(input.linkedAudio === "preserve" && changesRecordPosition ? expectedLinked.map((item, index) => observation(linkedFound[index], item, "linked_audio")) : [])];
          return {
            status: "succeeded", possibleMutation: "confirmed", usage: "consumed", verification: report,
            result: {
              actionId: ACTION_ID,
              target: movedItems[0],
              linkedAudio: linkedFound.length > 0 ? (input.linkedAudio === "preserve" ? "preserved" : "excluded") : "not_linked",
              movedItems,
              timelineRevision: after.revision,
            },
          };
        }
        const unchanged = digest(protectedState(before)) === digest(protectedState(after));
        if (unchanged) {
          const policyDenied = executionError?.cli_error_code === "EDIT_CONSTRAINT_VIOLATION";
          return {
            status: "failed", possibleMutation: "none", usage: policyDenied ? "not_reserved" : "released",
            failure: failure(policyDenied ? "EDIT_CONSTRAINT_VIOLATION" : "OPERATION_FAILED", executionError?.message ?? "The timeline-item move made no verified change.", context, "none", policyDenied ? "not_reserved" : "released"),
            ...(executionError?.cli_error_code === "EDIT_MUTATION_RESTORED" ? { recovery: { state: "restored", summary: "The original timeline state was restored.", evidence: report.evidence, manualRecoveryRequired: false } } : {}),
          };
        }
        if (executionError?.cli_error_code === "EDIT_MUTATION_RECOVERY_FAILED") {
          return {
            status: "recovery_failed", possibleMutation: "partial", usage: "consumed",
            failure: failure("RECOVERY_FAILED", executionError.message, context, "partial", "consumed"), verification: report,
            recovery: { state: "failed", summary: "Automatic timeline-item recovery did not restore the expected state.", evidence: report.evidence, manualRecoveryRequired: true },
          };
        }
        return {
          status: "verification_failed", possibleMutation: "possible", usage: "consumed",
          failure: failure("VERIFICATION_FAILED", executionError?.message ?? "The timeline-item move produced an unexpected project state.", context, "possible", "consumed"),
          verification: report,
          recovery: { state: "manual_required", summary: "Inspect the current timeline before retrying this move.", evidence: report.evidence, manualRecoveryRequired: true },
        };
      },
    },
  };
}
