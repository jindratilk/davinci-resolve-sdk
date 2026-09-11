import crypto from "node:crypto";
import {
  sdkTimelineEditMutationOutputSchema,
  sdkTimelineEditMutationRequestSchema,
} from "../contracts/generated/sdk-operations.js";

const ACTIONS = Object.freeze({
  "cutagent.action.edit.insert": "insert",
  "cutagent.action.edit.overwrite": "overwrite",
  "cutagent.action.edit.trim": "trim",
});

function digest(value) {
  return `sha256:${crypto.createHash("sha256").update(JSON.stringify(value), "utf8").digest("hex")}`;
}

function evidence(modality, summary, value) {
  return {
    evidenceId: `evidence_${crypto.randomUUID()}`,
    modality,
    summary,
    capturedAt: new Date().toISOString(),
    digest: digest(value),
  };
}

function failure(code, message, context, possibleMutation = "none", usage = possibleMutation === "none" ? "released" : "unknown") {
  const kind = code === "STALE_REVISION" ? "stale_revision"
    : code === "CAPABILITY_UNAVAILABLE" ? "capability_unavailable"
      : code === "RECOVERY_FAILED" ? "recovery_failed"
        : code === "VERIFICATION_FAILED" ? "verification_failed" : "operation_failed";
  return {
    kind,
    code,
    message,
    retrySafe: false,
    possibleMutation,
    usage,
    recovery: possibleMutation === "none" ? ["inspect_state"] : ["inspect_state", "manual_recovery"],
    recoveryGuidance: [possibleMutation === "none" ? "Inspect the timeline and create a fresh immutable impact preview." : "Inspect the current timeline before any further mutation."],
    readbackRequired: possibleMutation !== "none",
    requestId: context.requestId,
    operationId: context.operationId,
    executionId: context.executionId,
  };
}

function clipValue(clip, track) {
  return {
    id: clip.id,
    trackType: track.type,
    trackIndex: track.index,
    recordStartFrame: clip.recordRange.start,
    recordEndFrameExclusive: clip.recordRange.endExclusive,
    sourceStartFrame: clip.sourceRange?.start ?? null,
    sourceEndFrameExclusive: clip.sourceRange?.endExclusive ?? null,
    sourceFrameRate: clip.sourceFrameRate ?? null,
  };
}

function locate(snapshot, id) {
  for (const track of snapshot.tracks) {
    const clip = track.clips.find((candidate) => candidate.id === id);
    if (clip) return { track, clip };
  }
  return null;
}

function stableClipValue(clip, track) {
  return {
    track: { type: track.type, index: track.index },
    id: clip.id,
    name: clip.name,
    recordRange: clip.recordRange,
    duration: clip.duration,
    sourceRange: clip.sourceRange,
    sourceFrameRate: clip.sourceFrameRate ?? null,
    mediaPoolItemId: clip.mediaPoolItemId,
    linkedItemIds: clip.linkedItemIds,
  };
}

function sameProtectedItem(before, after, target) {
  const left = locate(before, target.id);
  const right = locate(after, target.id);
  if (!left || !right) return false;
  return digest(stableClipValue(left.clip, left.track)) === digest(stableClipValue(right.clip, right.track));
}

function expectedResult(before, after, expected) {
  const track = after.tracks.find((candidate) => candidate.type === expected.track.type && candidate.index === expected.track.index);
  const beforeItem = expected.beforeItemId === null ? null : locate(before, expected.beforeItemId);
  const matches = (track?.clips ?? []).filter((clip) => clip.recordRange.start === expected.recordRange.start
    && clip.recordRange.endExclusive === expected.recordRange.endExclusive
    && clip.sourceRange?.start === expected.sourceRange.start
    && clip.sourceRange?.endExclusive !== undefined
    && Math.abs(clip.sourceRange.endExclusive - expected.sourceRange.endExclusive) <= expected.sourceEndToleranceFrames
    && clip.mediaPoolItemId === expected.mediaPoolItemId
    && clip.name === expected.name
    && (beforeItem === null || JSON.stringify(clip.sourceFrameRate) === JSON.stringify(beforeItem.clip.sourceFrameRate))
    && clip.linkedItemIds !== null
    && (expected.role !== "unlinked" || clip.linkedItemIds.length === 0)
    && (!["trimmed", "unlinked"].includes(expected.role) || clip.id === expected.beforeItemId));
  return matches.length === 1 ? { located: { track, clip: matches[0] }, value: clipValue(matches[0], track) } : null;
}

function expectedLinksMatch(impact, matches) {
  return matches.every((match, index) => {
    const expected = impact.expectedItems[index];
    const expectedIds = [
      ...expected.linkedExpectedItemIndexes.map((linkedIndex) => matches[linkedIndex]?.value.id),
      ...expected.linkedExistingItemIds,
    ];
    const actualIds = match.located.clip.linkedItemIds;
    return expectedIds.every((id) => typeof id === "string")
      && actualIds.length === expectedIds.length
      && new Set(actualIds).size === actualIds.length
      && actualIds.every((id) => expectedIds.includes(id));
  });
}

function invariantTimelineState(snapshot) {
  return {
    project: snapshot.project,
    timeline: snapshot.timeline,
    frameRate: snapshot.frameRate,
    start: snapshot.start,
    markers: (snapshot.markers ?? []).map(({ snapshotRevision: _snapshotRevision, ...marker }) => marker),
    tracks: snapshot.tracks.map((track) => ({
      timelineId: track.timelineId,
      type: track.type,
      index: track.index,
      name: track.name,
      enabled: track.enabled,
      locked: track.locked,
    })),
  };
}

export function createSdkTimelineEditActions({
  liveInspectionService,
  resolveService,
}) {
  const hasStructuralRead = typeof liveInspectionService?.readTimelineStructure === "function";
  const readTimelineStructure = liveInspectionService?.readTimelineStructure?.bind(liveInspectionService)
    ?? liveInspectionService?.readWithMutationGuard?.bind(liveInspectionService);
  if (typeof liveInspectionService?.prepareTimelineEdit !== "function"
    || typeof liveInspectionService?.readWithMutationGuard !== "function"
    || typeof readTimelineStructure !== "function"
    || (hasStructuralRead && typeof liveInspectionService?.readWorkflowBinding !== "function")) {
    throw new TypeError("Timeline edit actions require authoritative impact preparation and guarded readback.");
  }
  if (typeof resolveService?.executeSdkTimelineEdit !== "function") throw new TypeError("Timeline edit actions require the CutAgent CLI mutation boundary.");

  return Object.fromEntries(Object.entries(ACTIONS).map(([actionId, action]) => [actionId, {
    inputSchema: sdkTimelineEditMutationRequestSchema,
    resultSchema: sdkTimelineEditMutationOutputSchema,
    idempotency: "required",
    async execute(context, rawInput) {
      const input = sdkTimelineEditMutationRequestSchema.parse(rawInput);
      const batch = "impacts" in input;
      const impacts = batch ? input.impacts : [input.impact];
      const audioInsertBatch = batch && action === "insert"
        && impacts.every((impact) => impact.intent.placement === "audio");
      const trimBatch = batch && action === "trim";
      if (impacts.some((impact) => impact.action !== action)) {
        return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("OPERATION_FAILED", "The durable action does not match the immutable edit impact.", context) };
      }
      if (batch && action === "insert" && !audioInsertBatch
        && impacts.some((impact) => impact.intent.placement === "audio")) {
        return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("OPERATION_FAILED", "Plural timeline inserts must use one homogeneous video or audio placement mode.", context) };
      }
      let prepared;
      try {
        const preparationOptions = { deadlineAtMs: Date.now() + 60_000, sdkSessionId: context.sdkSessionId, signal: context.signal };
        prepared = liveInspectionService.takePreparedTimelineEdits?.(impacts, { sdkSessionId: context.sdkSessionId }) ?? null;
        if (!prepared && !batch) {
          const retained = liveInspectionService.takePreparedTimelineEdit?.(impacts[0], { sdkSessionId: context.sdkSessionId }) ?? null;
          if (retained) prepared = { ...retained, impacts: [retained.impact], executionContexts: [retained.executionContext] };
        }
        if (!prepared && audioInsertBatch) {
          if (typeof liveInspectionService.prepareTimelineAudioInserts !== "function") {
            throw new TypeError("Plural audio inserts require consolidated impact preparation.");
          }
          prepared = await liveInspectionService.prepareTimelineAudioInserts(impacts.map((impact) => impact.intent), preparationOptions);
        } else if (!prepared && batch) {
          if (typeof liveInspectionService.prepareTimelineEdits !== "function") {
            throw new TypeError("Plural timeline edits require consolidated impact preparation.");
          }
          prepared = await liveInspectionService.prepareTimelineEdits(impacts.map((impact) => impact.intent), preparationOptions);
        } else if (!prepared) {
          const single = await liveInspectionService.prepareTimelineEdit(impacts[0].intent, preparationOptions);
          prepared = { ...single, impacts: [single.impact], executionContexts: [single.executionContext] };
        }
      } catch (error) {
        if (context.isCancellationRequested?.()) {
          const requestedAt = context.cancellationRequestedAt?.() ?? new Date().toISOString();
          return {
            status: "cancelled",
            possibleMutation: "none",
            usage: "released",
            cancellation: { state: "confirmed", requestedAt, confirmedAt: new Date().toISOString() },
            failure: {
              kind: "cancelled",
              code: "CANCELLED",
              message: "The timeline edit was cancelled before native execution.",
              retrySafe: false,
              possibleMutation: "none",
              usage: "released",
              recovery: ["continue"],
              recoveryGuidance: ["No project mutation was started."],
              readbackRequired: false,
            },
          };
        }
        const reportedCode = error?.code ?? error?.cli_error_code;
        const code = ["CAPABILITY_UNAVAILABLE", "STALE_REVISION"].includes(reportedCode) ? reportedCode : "OPERATION_FAILED";
        return { status: "failed", possibleMutation: "none", usage: "released", failure: failure(code, error?.message ?? "The edit impact could not be refreshed.", context) };
      }
      if (!Array.isArray(prepared.impacts) || prepared.impacts.length !== impacts.length
        || prepared.impacts.some((impact, index) => digest(impact) !== digest(impacts[index]))) {
        return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "The timeline or exact edit impact changed after preview.", context) };
      }
      if (context.isCancellationRequested?.()) {
        const requestedAt = context.cancellationRequestedAt?.() ?? new Date().toISOString();
        return {
          status: "cancelled",
          possibleMutation: "none",
          usage: "not_reserved",
          cancellation: { state: "confirmed", requestedAt, confirmedAt: new Date().toISOString() },
          failure: {
            kind: "cancelled",
            code: "CANCELLED",
            message: "The timeline edit was cancelled before native execution.",
            retrySafe: false,
            possibleMutation: "none",
            usage: "not_reserved",
            recovery: ["continue"],
            recoveryGuidance: ["Inspect current state before deciding whether to create new work."],
            readbackRequired: false,
          },
        };
      }
      let executionError = null;
      try {
        const executionOptions = { mutationGuard: prepared.mutationGuard, onAuthorization() {}, signal: context.signal };
        if (audioInsertBatch) {
          if (typeof resolveService.executeSdkTimelineAudioInsert !== "function") {
            throw new TypeError("Plural audio inserts require one consolidated native execution.");
          }
          await resolveService.executeSdkTimelineAudioInsert(impacts.map((impact) => impact.intent), prepared.executionContext, executionOptions);
        } else if (trimBatch) {
          await resolveService.executeSdkTimelineEdit(
            impacts.map((impact) => impact.intent),
            prepared.executionContexts[0],
            executionOptions,
          );
        } else if (batch) {
          if (typeof resolveService.executeSdkTimelineEdits !== "function") {
            throw new TypeError("Plural timeline edits require one consolidated native execution.");
          }
          await resolveService.executeSdkTimelineEdits(impacts.map((impact) => impact.intent), prepared.executionContexts, executionOptions);
        } else {
          await resolveService.executeSdkTimelineEdit(impacts[0].intent, prepared.executionContexts[0], executionOptions);
        }
      }
      catch (error) { executionError = error; }
      let after;
      let canonicalAfterRevision;
      try {
        if (batch && hasStructuralRead) {
          const binding = await liveInspectionService.readWorkflowBinding({
            operation: "timeline.snapshot",
            projectId: impacts[0].projectId,
            timelineId: impacts[0].timelineId,
          }, { deadlineAtMs: Date.now() + 60_000 });
          if (binding.projectId !== impacts[0].projectId || binding.timelineId !== impacts[0].timelineId) {
            throw new Error("Canonical post-edit timeline binding changed during grouped verification.");
          }
          canonicalAfterRevision = binding.revision;
          after = (await readTimelineStructure({
            operation: "timeline.structure",
            projectId: impacts[0].projectId,
            timelineId: impacts[0].timelineId,
            expectedRevision: canonicalAfterRevision,
          }, { deadlineAtMs: Date.now() + 60_000 })).value;
        } else {
          after = (await liveInspectionService.readWithMutationGuard({
            operation: "timeline.snapshot",
            projectId: impacts[0].projectId,
            timelineId: impacts[0].timelineId,
          }, { deadlineAtMs: Date.now() + 60_000 })).value;
          canonicalAfterRevision = after.revision;
        }
      } catch {
        return {
          status: "verification_failed", possibleMutation: "possible", usage: "unknown",
          failure: failure("VERIFICATION_FAILED", "Timeline readback was unavailable after semantic edit execution.", context, "possible"),
          verification: { outcome: "failed", summary: "Post-mutation timeline readback was unavailable.", evidence: [evidence("readback", "Post-mutation timeline readback failed.", { actionId })], protectedStatePreserved: null },
        };
      }
      const affectedBeforeIds = new Set(impacts.flatMap((impact) => impact.affectedItems.map((item) => item.id)));
      const protectedTargets = impacts.flatMap((impact) => impact.protectedItems)
        .filter((item) => !affectedBeforeIds.has(item.id));
      const protectedPreserved = protectedTargets.every((target) => sameProtectedItem(prepared.snapshot, after, target));
      const expectedResults = impacts.map((impact) => impact.expectedItems.map((expected) => expectedResult(prepared.snapshot, after, expected)));
      const affectedClips = expectedResults.map((matches) => matches.filter(Boolean).map((match) => match.value));
      const beforeIds = new Set(prepared.snapshot.tracks.flatMap((track) => track.clips.map((clip) => clip.id)));
      const afterRows = after.tracks.flatMap((track) => track.clips.map((clip) => ({ track, clip })));
      const afterIds = new Set(afterRows.map(({ clip }) => clip.id));
      const unrelatedItemsPreserved = prepared.snapshot.tracks
        .flatMap((track) => track.clips)
        .filter((clip) => !affectedBeforeIds.has(clip.id))
        .every((clip) => sameProtectedItem(prepared.snapshot, after, clip));
      const expectedNewIds = new Set(expectedResults.flatMap((matches, impactIndex) => matches.flatMap((match, itemIndex) => (
        match && ["replacement", "preserved_edge"].includes(impacts[impactIndex].expectedItems[itemIndex].role) ? [match.value.id] : []
      ))));
      const actualNewIds = new Set(afterRows.filter(({ clip }) => !beforeIds.has(clip.id)).map(({ clip }) => clip.id));
      const removedAffectedIds = impacts.flatMap((impact) => impact.affectedItems)
        .filter((item) => item.role === "replace")
        .every((item) => !afterIds.has(item.id));
      const invariantStatePreserved = digest(invariantTimelineState(prepared.snapshot)) === digest(invariantTimelineState(after));
      const closedWorld = afterRows.every(({ clip }) => typeof clip.id === "string")
        && invariantStatePreserved
        && unrelatedItemsPreserved
        && actualNewIds.size === expectedNewIds.size
        && [...actualNewIds].every((id) => expectedNewIds.has(id));
      const revisionChanged = after.revision !== prepared.snapshot.revision;
      const resultMatches = executionError === null && revisionChanged
        && expectedResults.every((matches) => matches.every(Boolean))
        && removedAffectedIds
        && closedWorld
        && impacts.every((impact, index) => expectedLinksMatch(impact, expectedResults[index]));
      const report = {
        outcome: resultMatches && protectedPreserved ? "passed" : "failed",
        summary: resultMatches && protectedPreserved ? "Exact semantic edit and declared protected targets matched independent readback." : "Semantic edit readback or a declared protected target did not match.",
        evidence: [
          evidence("readback", "Read back the timeline after execution.", { structuralRevision: after.revision, canonicalRevision: canonicalAfterRevision, revisionChanged, affectedClips: affectedClips.flat() }),
          evidence("structural", "Compared the closed declared post-state and every unrelated and protected item.", { protectedItemIds: protectedTargets.map((item) => item.id), protectedPreserved, unrelatedItemsPreserved, removedAffectedIds, invariantStatePreserved, closedWorld }),
        ],
        protectedStatePreserved: protectedPreserved,
      };
      if (resultMatches && protectedPreserved) {
        const results = impacts.map((impact, index) => ({
          action,
          impactId: impact.impactId,
          timelineRevision: canonicalAfterRevision,
          affectedClips: affectedClips[index],
          protectedItemIds: impact.protectedItems.filter((item) => !affectedBeforeIds.has(item.id)).map((item) => item.id),
          protectedStatePreserved: true,
        }));
        return {
          status: "succeeded", possibleMutation: "confirmed", usage: "consumed", verification: report,
          result: batch ? { results } : results[0],
        };
      }
      const unchanged = !revisionChanged;
      if (unchanged && executionError && context.isCancellationRequested?.()) {
        const requestedAt = context.cancellationRequestedAt?.() ?? new Date().toISOString();
        const recoverySummary = "Authoritative timeline readback proved that the pre-mutation state was preserved after Stop interrupted native execution.";
        return {
          status: "cancelled",
          possibleMutation: "none",
          usage: "released",
          cancellation: { state: "confirmed", requestedAt, confirmedAt: new Date().toISOString() },
          failure: {
            kind: "cancelled",
            code: "CANCELLED",
            message: "The timeline edit was cancelled during native execution, and readback confirmed no persisted mutation.",
            retrySafe: false,
            possibleMutation: "none",
            usage: "released",
            recovery: ["continue"],
            recoveryGuidance: ["The pre-mutation timeline state was preserved."],
            recoveryOutcome: { status: "succeeded", summary: recoverySummary },
            readbackRequired: false,
          },
          recovery: {
            state: "restored",
            summary: recoverySummary,
            evidence: report.evidence,
            manualRecoveryRequired: false,
          },
        };
      }
      if (unchanged && executionError?.cli_error_code === "EDIT_MUTATION_RESTORED") {
        const recoverySummary = "Authoritative timeline readback proved that the pre-mutation state was restored after the overwrite failed.";
        const originalErrorCode = executionError?.cli_error_details?.original_error_code;
        const causeCode = typeof originalErrorCode === "string" && /^[A-Z][A-Z0-9_]{0,99}$/.test(originalErrorCode)
          ? originalErrorCode
          : "EDIT_MUTATION_RESTORED";
        const restoredVerification = {
          ...report,
          outcome: "failed",
          summary: "The requested overwrite did not persist; authoritative readback matched the pre-mutation timeline after recovery.",
          protectedStatePreserved: true,
        };
        return {
          status: "failed",
          possibleMutation: "none",
          usage: "released",
          failure: {
            ...failure("OPERATION_FAILED", "The requested overwrite failed, and the prior timeline state was restored.", context),
            cause: {
              code: causeCode,
              message: "The native timeline placement failed before verified checkpoint restoration.",
            },
            recoveryOutcome: { status: "succeeded", summary: recoverySummary },
          },
          recovery: {
            state: "restored",
            summary: recoverySummary,
            evidence: restoredVerification.evidence,
            manualRecoveryRequired: false,
          },
        };
      }
      if (unchanged) {
        return { status: "failed", possibleMutation: "none", usage: "released", failure: failure(executionError?.cli_error_code === "STALE_REVISION" ? "STALE_REVISION" : "OPERATION_FAILED", executionError?.message ?? "The semantic edit made no verified change.", context) };
      }
      if (executionError?.cli_error_code === "EDIT_MUTATION_RECOVERY_FAILED") {
        return { status: "recovery_failed", possibleMutation: "partial", usage: "consumed", postTimelineRevision: canonicalAfterRevision, failure: failure("RECOVERY_FAILED", executionError.message, context, "partial", "consumed"), verification: report, recovery: { state: "failed", summary: "Automatic edit recovery did not restore the expected timeline.", evidence: report.evidence, manualRecoveryRequired: true } };
      }
      return { status: "verification_failed", possibleMutation: "possible", usage: "consumed", postTimelineRevision: canonicalAfterRevision, failure: failure("VERIFICATION_FAILED", executionError?.message ?? "The semantic edit produced an unexpected timeline state.", context, "possible", "consumed"), verification: report, recovery: { state: "manual_required", summary: "Inspect the current timeline before retrying this semantic edit.", evidence: report.evidence, manualRecoveryRequired: true } };
    },
  }]));
}
