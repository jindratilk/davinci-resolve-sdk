import crypto from "node:crypto";
import {
  sdkTimelineEditMutationInputSchema,
  sdkTimelineEditMutationResultSchema,
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
    : code === "EDIT_CONSTRAINT_VIOLATION" ? "edit_constraint_violation"
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

function exactScope(gate, accountFingerprint, impact, actionId, directScope = null) {
  const operation = actionId.replace("cutagent.action.", "");
  const scopes = (directScope === null ? gate.listScopes({ accountFingerprint }) : [directScope]).filter((scope) => (
    scope.binding.level === "project+timeline"
    && scope.binding.projectId === impact.projectId
    && scope.binding.timelineId === impact.timelineId
    && scope.binding.timelineRevision === impact.timelineRevision
    && (scope.constraints.allowedOperations.length === 0 || scope.constraints.allowedOperations.includes(operation))
    && impact.affectedTracks.every((track) => scope.constraints.allowedTrackTypes.length === 0 || scope.constraints.allowedTrackTypes.includes(track.type))
  ));
  if (scopes.length !== 1) {
    const error = new Error("Exactly one current user-owned constraint scope must authorize every affected track and the exact semantic edit.");
    error.code = "EDIT_CONSTRAINT_VIOLATION";
    throw error;
  }
  return scopes[0];
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
  mutationPolicyGate,
  directMutationPolicyAuthority = null,
}) {
  if (typeof liveInspectionService?.prepareTimelineEdit !== "function" || typeof liveInspectionService?.readWithMutationGuard !== "function") {
    throw new TypeError("Timeline edit actions require authoritative impact preparation and guarded readback.");
  }
  if (typeof resolveService?.executeSdkTimelineEdit !== "function") throw new TypeError("Timeline edit actions require the CutAgent CLI mutation boundary.");
  if (typeof mutationPolicyGate?.bindVerifiedProtectedTargets !== "function") throw new TypeError("Timeline edit actions require protected-target proof binding.");

  return Object.fromEntries(Object.entries(ACTIONS).map(([actionId, action]) => [actionId, {
    inputSchema: sdkTimelineEditMutationInputSchema,
    resultSchema: sdkTimelineEditMutationResultSchema,
    idempotency: "required",
    async execute(context, rawInput) {
      const input = sdkTimelineEditMutationInputSchema.parse(rawInput);
      if (input.impact.action !== action) {
        return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("OPERATION_FAILED", "The durable action does not match the immutable edit impact.", context) };
      }
      let prepared;
      try {
        prepared = await liveInspectionService.prepareTimelineEdit(input.impact.intent, { deadlineAtMs: Date.now() + 60_000 });
      } catch (error) {
        const reportedCode = error?.code ?? error?.cli_error_code;
        const code = ["CAPABILITY_UNAVAILABLE", "STALE_REVISION"].includes(reportedCode) ? reportedCode : "OPERATION_FAILED";
        return { status: "failed", possibleMutation: "none", usage: "released", failure: failure(code, error?.message ?? "The edit impact could not be refreshed.", context) };
      }
      if (digest(prepared.impact) !== digest(input.impact)) {
        return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "The timeline or exact edit impact changed after preview.", context) };
      }
      let directScope = null;
      if (directMutationPolicyAuthority !== null) {
        try {
          const inspected = await liveInspectionService.readWithMutationGuard(
            { operation: "project.context" },
            { deadlineAtMs: Date.now() + 60_000 },
          );
          const project = inspected.value?.project;
          const timeline = inspected.value?.timeline;
          const projectRevision = inspected.value?.projectRevision;
          const projectLibraryId = inspected.privateExecutionIdentity?.projectLibraryId;
          if (project?.id !== input.impact.projectId
            || timeline?.id !== input.impact.timelineId
            || projectRevision?.status !== "available"
            || typeof projectRevision.revision !== "string"
            || typeof projectLibraryId !== "string") {
            throw Object.assign(new Error("The direct SDK editing-constraint scope lost its exact live project binding."), { code: "STALE_REVISION" });
          }
          directScope = await directMutationPolicyAuthority.resolveScope({
            sdkSessionId: context.sdkSessionId,
            accountFingerprint: context.accountFingerprint,
            binding: {
              level: "project+timeline",
              projectLibraryId,
              projectId: input.impact.projectId,
              projectRevision: projectRevision.revision,
              timelineId: input.impact.timelineId,
              timelineRevision: input.impact.timelineRevision,
            },
          });
        } catch (error) {
          const code = error?.code === "STALE_REVISION" ? "STALE_REVISION" : "EDIT_CONSTRAINT_VIOLATION";
          return { status: "failed", possibleMutation: "none", usage: "not_reserved", failure: failure(code, error.message, context, "none", "not_reserved") };
        }
      }
      let scope;
      try { scope = exactScope(mutationPolicyGate, context.accountFingerprint, input.impact, actionId, directScope); } catch (error) {
        return { status: "failed", possibleMutation: "none", usage: "not_reserved", failure: failure("EDIT_CONSTRAINT_VIOLATION", error.message, context, "none", "not_reserved") };
      }
      const stableTargets = [
        { kind: "timeline", stableId: input.impact.timelineId, revision: input.impact.timelineRevision },
        ...input.impact.affectedItems.map((item) => ({ kind: "clip", stableId: item.id, revision: input.impact.timelineRevision, trackType: item.track.type, trackIndex: item.track.index })),
      ];
      const policyContext = {
        requestId: context.requestId,
        operationId: context.operationId,
        executionId: context.executionId,
        scopeId: scope.scopeId,
        scopeRevision: scope.revision,
        projectLibraryId: scope.binding.projectLibraryId,
        projectId: input.impact.projectId,
        timelineId: input.impact.timelineId,
        projectRevision: scope.binding.projectRevision,
        timelineRevision: input.impact.timelineRevision,
        resolvedTargets: stableTargets,
        affectedTrackTypes: [...new Set(input.impact.affectedTracks.map((track) => track.type))],
        semanticEditAction: input.impact.action,
        closedComposition: true,
        executableStableTargetPrecondition: true,
      };
      let releaseProof;
      try {
        releaseProof = mutationPolicyGate.bindVerifiedProtectedTargets({
          accountFingerprint: context.accountFingerprint,
          executionId: context.executionId,
          scopeId: scope.scopeId,
          scopeRevision: scope.revision,
          timelineRevision: input.impact.timelineRevision,
        });
      } catch (error) {
        return { status: "failed", possibleMutation: "none", usage: "not_reserved", failure: failure("EDIT_CONSTRAINT_VIOLATION", error.message, context, "none", "not_reserved") };
      }
      let authorization = null;
      let executionError = null;
      try {
        try {
          await resolveService.executeSdkTimelineEdit(input.impact.intent, prepared.executionContext, {
            mutationGuard: prepared.mutationGuard,
            policyContext,
            onAuthorization(value) { authorization = value; },
          });
        } catch (error) { executionError = error; }
      } finally {
        releaseProof();
      }
      let after;
      try {
        after = (await liveInspectionService.readWithMutationGuard({
          operation: "timeline.snapshot",
          projectId: input.impact.projectId,
          timelineId: input.impact.timelineId,
        }, { deadlineAtMs: Date.now() + 60_000 })).value;
      } catch {
        return {
          status: "verification_failed", possibleMutation: "possible", usage: "unknown",
          failure: failure("VERIFICATION_FAILED", "Timeline readback was unavailable after semantic edit execution.", context, "possible"),
          verification: { outcome: "failed", summary: "Post-mutation timeline readback was unavailable.", evidence: [evidence("readback", "Post-mutation timeline readback failed.", { actionId })], protectedStatePreserved: null },
        };
      }
      const protectedPreserved = input.impact.protectedItems.every((target) => sameProtectedItem(prepared.snapshot, after, target));
      const expectedResults = input.impact.expectedItems.map((expected) => expectedResult(prepared.snapshot, after, expected));
      const affectedClips = expectedResults.filter(Boolean).map((match) => match.value);
      const beforeIds = new Set(prepared.snapshot.tracks.flatMap((track) => track.clips.map((clip) => clip.id)));
      const afterRows = after.tracks.flatMap((track) => track.clips.map((clip) => ({ track, clip })));
      const afterIds = new Set(afterRows.map(({ clip }) => clip.id));
      const expectedNewIds = new Set(expectedResults.flatMap((match, index) => (
        match && ["replacement", "preserved_edge"].includes(input.impact.expectedItems[index].role) ? [match.value.id] : []
      )));
      const actualNewIds = new Set(afterRows.filter(({ clip }) => !beforeIds.has(clip.id)).map(({ clip }) => clip.id));
      const removedAffectedIds = input.impact.affectedItems
        .filter((item) => item.role === "replace")
        .every((item) => !afterIds.has(item.id));
      const invariantStatePreserved = digest(invariantTimelineState(prepared.snapshot)) === digest(invariantTimelineState(after));
      const closedWorld = afterRows.every(({ clip }) => typeof clip.id === "string")
        && invariantStatePreserved
        && actualNewIds.size === expectedNewIds.size
        && [...actualNewIds].every((id) => expectedNewIds.has(id));
      const revisionChanged = after.revision !== prepared.snapshot.revision;
      const authorizationProven = Boolean(authorization?.policyDecision);
      const resultMatches = executionError === null && revisionChanged && authorizationProven
        && expectedResults.every(Boolean)
        && removedAffectedIds
        && closedWorld
        && expectedLinksMatch(input.impact, expectedResults);
      const report = {
        outcome: resultMatches && protectedPreserved ? "passed" : "failed",
        summary: resultMatches && protectedPreserved ? "Exact semantic edit and declared protected targets matched independent readback." : "Semantic edit readback or a declared protected target did not match.",
        evidence: [
          evidence("readback", "Read back the complete timeline after execution.", { revision: after.revision, revisionChanged, affectedClips }),
          evidence("structural", "Confirmed the mutation was authorized before execution.", { authorizationProven }),
          evidence("structural", "Compared the closed declared post-state and every protected item.", { protectedItemIds: input.impact.protectedItems.map((item) => item.id), protectedPreserved, removedAffectedIds, invariantStatePreserved, closedWorld }),
        ],
        protectedStatePreserved: protectedPreserved,
      };
      if (resultMatches && protectedPreserved) {
        try {
          mutationPolicyGate.assertProtectedStateEvidence(authorization.policyDecision.decisionId, report);
        } catch (error) {
          return {
            status: "verification_failed", possibleMutation: "confirmed", usage: "consumed",
            postTimelineRevision: after.revision,
            failure: failure("VERIFICATION_FAILED", error?.message ?? "Protected-state evidence was rejected after the semantic edit.", context, "confirmed", "consumed"),
            verification: { ...report, outcome: "failed", summary: "The edit matched readback, but protected-state evidence was rejected." },
          };
        }
        return {
          status: "succeeded", possibleMutation: "confirmed", usage: "consumed", verification: report,
          result: {
            action,
            impactId: input.impact.impactId,
            timelineRevision: after.revision,
            affectedClips,
            protectedItemIds: input.impact.protectedItems.map((item) => item.id),
            protectedStatePreserved: true,
          },
        };
      }
      const unchanged = !revisionChanged;
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
        return { status: "recovery_failed", possibleMutation: "partial", usage: "consumed", postTimelineRevision: after.revision, failure: failure("RECOVERY_FAILED", executionError.message, context, "partial", "consumed"), verification: report, recovery: { state: "failed", summary: "Automatic edit recovery did not restore the expected timeline.", evidence: report.evidence, manualRecoveryRequired: true } };
      }
      return { status: "verification_failed", possibleMutation: "possible", usage: "consumed", postTimelineRevision: after.revision, failure: failure("VERIFICATION_FAILED", executionError?.message ?? "The semantic edit produced an unexpected timeline state.", context, "possible", "consumed"), verification: report, recovery: { state: "manual_required", summary: "Inspect the current timeline before retrying this semantic edit.", evidence: report.evidence, manualRecoveryRequired: true } };
    },
  }]));
}
