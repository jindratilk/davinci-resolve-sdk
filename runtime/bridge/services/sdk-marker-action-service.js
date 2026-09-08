import crypto from "node:crypto";
import {
  sdkMarkerCreateInputSchema,
  sdkMarkerDeleteInputSchema,
  sdkMarkerMutationResultSchema,
  sdkMarkerUpdateInputSchema,
} from "../contracts/generated/sdk-operations.js";
import {resolveSdkDirectMutationScope, sdkMutationScopeCandidates} from "./sdk-direct-mutation-scope.js";

const ACTIONS = Object.freeze({
  "cutagent.action.timeline.marker.add": { action: "create", schema: sdkMarkerCreateInputSchema },
  "cutagent.action.timeline.marker.update": { action: "update", schema: sdkMarkerUpdateInputSchema },
  "cutagent.action.timeline.marker.delete": { action: "delete", schema: sdkMarkerDeleteInputSchema },
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

function markerValue(marker) {
  if (!marker) return null;
  return {
    id: marker.id,
    recordFrame: marker.position.value.value,
    color: marker.color,
    name: marker.name,
    note: marker.note,
    durationFrames: marker.duration.value.value,
  };
}

function protectedState(snapshot) {
  return snapshot.tracks.map((track) => ({
    type: track.type,
    index: track.index,
    name: track.name,
    enabled: track.enabled,
    locked: track.locked,
    clips: track.clips.map(({ snapshotId: _snapshotId, snapshotTrackId: _snapshotTrackId, snapshotRevision: _snapshotRevision, ...clip }) => clip),
  }));
}

function semanticState(snapshot) {
  return {
    project: snapshot.project,
    timeline: snapshot.timeline,
    frameRate: snapshot.frameRate,
    start: snapshot.start,
    tracks: protectedState(snapshot),
    markers: snapshot.markers.map(({ snapshotRevision: _snapshotRevision, ...marker }) => marker),
  };
}

function failure(code, message, context, possibleMutation = "none", usage = possibleMutation === "none" ? "released" : "unknown") {
  const kind = code === "STALE_REVISION" ? "stale_revision"
    : code === "EDIT_CONSTRAINT_VIOLATION" ? "edit_constraint_violation"
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
    recoveryGuidance: [possibleMutation === "none" ? "Inspect the current timeline and create a fresh impact preview." : "Inspect the current timeline before any further mutation."],
    readbackRequired: possibleMutation !== "none",
    ...(code === "RECOVERY_FAILED" ? { recoveryOutcome: { status: "failed", summary: "Automatic marker recovery did not restore the expected state.", manualRecoveryRequired: true } } : {}),
    requestId: context.requestId,
    operationId: context.operationId,
    executionId: context.executionId,
  };
}

function exactScope(gate, accountFingerprint, input, actionId, directScope = null) {
  const scopes = sdkMutationScopeCandidates(gate, accountFingerprint, directScope).filter((scope) => (
    scope.binding.level === "project+timeline"
    && scope.binding.projectId === input.projectId
    && scope.binding.timelineId === input.timelineId
    && scope.binding.timelineRevision === input.timelineRevision
    && (scope.constraints.allowedOperations.length === 0 || scope.constraints.allowedOperations.includes(actionId.replace("cutagent.action.", "")))
  ));
  if (scopes.length !== 1) {
    const error = new Error("Exactly one current user-owned marker constraint scope is required.");
    error.code = "EDIT_CONSTRAINT_VIOLATION";
    throw error;
  }
  return scopes[0];
}

function findTarget(snapshot, markerId) {
  return snapshot.markers.find((marker) => marker.id === markerId) ?? null;
}

function sameMarker(left, right) {
  return left?.id === right?.id
    && left?.position.value.value === right?.position.value.value
    && left?.color === right?.color
    && left?.name === right?.name
    && left?.note === right?.note
    && left?.duration.value.value === right?.duration.value.value;
}

function preservesOtherMarkers(before, after, beforeExcludedId = null, afterExcludedId = beforeExcludedId) {
  const expected = before.markers.filter((marker) => marker.id !== beforeExcludedId);
  const actual = after.markers.filter((marker) => marker.id !== afterExcludedId);
  return expected.length === actual.length
    && expected.every((marker) => sameMarker(marker, actual.find((candidate) => candidate.id === marker.id)));
}

function expectedPost(action, before, after, input) {
  const beforeTarget = action === "create" ? null : findTarget(before, input.markerId);
  if (action !== "create" && !beforeTarget) return { ok: false, previous: null, marker: null };
  if (action === "delete") {
    return {
      ok: findTarget(after, input.markerId) === null
        && after.markers.length === before.markers.length - 1
        && preservesOtherMarkers(before, after, input.markerId),
      previous: beforeTarget,
      marker: null,
    };
  }
  const expected = input.marker;
  const marker = after.markers.find((candidate) => (
    candidate.position.value.value === expected.recordFrame
    && candidate.color === expected.color
    && candidate.name === expected.name
    && candidate.note === expected.note
    && candidate.duration.value.value === expected.durationFrames
  )) ?? null;
  const exactCollection = action === "create"
    ? after.markers.length === before.markers.length + 1 && preservesOtherMarkers(before, after, null, marker?.id)
    : after.markers.length === before.markers.length
      && preservesOtherMarkers(before, after, input.markerId, marker?.id)
      && (findTarget(after, input.markerId) === null || marker?.id === input.markerId);
  return { ok: Boolean(marker && exactCollection), previous: beforeTarget, marker };
}

export function createSdkMarkerActions({ liveInspectionService, resolveService, mutationPolicyGate, directMutationPolicyAuthority = null, activatedActionIds = Object.keys(ACTIONS) }) {
  if (typeof liveInspectionService?.readWithMutationGuard !== "function") throw new TypeError("Marker actions require live inspection with a mutation guard.");
  if (typeof resolveService?.executeSdkMarkerMutation !== "function") throw new TypeError("Marker actions require the CutAgent CLI mutation boundary.");
  if (typeof mutationPolicyGate?.bindVerifiedProtectedTargets !== "function") throw new TypeError("Marker actions require protected-target proof binding.");
  const activated = new Set(activatedActionIds);
  if (activated.size !== activatedActionIds.length || [...activated].some((actionId) => !Object.hasOwn(ACTIONS, actionId))) {
    throw new TypeError("Marker action activation must contain unique known action IDs.");
  }
  return Object.fromEntries(Object.entries(ACTIONS).filter(([actionId]) => activated.has(actionId)).map(([actionId, definition]) => [actionId, {
    inputSchema: definition.schema,
    resultSchema: sdkMarkerMutationResultSchema,
    idempotency: "required",
    async execute(context, rawInput) {
      const input = definition.schema.parse(rawInput);
      const inspectRequest = { operation: "timeline.snapshot", projectId: input.projectId, timelineId: input.timelineId };
      const inspected = await liveInspectionService.readWithMutationGuard(inspectRequest, { deadlineAtMs: Date.now() + 60_000 });
      const before = inspected.value;
      if (before.revision !== input.timelineRevision) {
        return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "The timeline changed after the marker impact preview.", context) };
      }
      const target = definition.action === "create" ? null : findTarget(before, input.markerId);
      if (definition.action !== "create" && !target) {
        return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "The marker changed or disappeared after preview.", context) };
      }
      if (definition.action === "update"
        && target.position.value.value === input.marker.recordFrame
        && target.color === input.marker.color && target.name === input.marker.name
        && target.note === input.marker.note && target.duration.value.value === input.marker.durationFrames) {
        return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("OPERATION_FAILED", "Marker update must change at least one semantic value.", context) };
      }
      let scope;
      try {
        const directScope = await resolveSdkDirectMutationScope({directMutationPolicyAuthority, context, liveInspectionService, level: "project+timeline", projectId: input.projectId, timelineId: input.timelineId, timelineRevision: input.timelineRevision});
        scope = exactScope(mutationPolicyGate, context.accountFingerprint, input, actionId, directScope);
      } catch (error) {
        return { status: "failed", possibleMutation: "none", usage: "not_reserved", failure: failure("EDIT_CONSTRAINT_VIOLATION", error.message, context, "none", "not_reserved") };
      }
      const stableTarget = definition.action === "create"
        ? { kind: "timeline", stableId: input.timelineId, revision: input.timelineRevision }
        : { kind: "marker", stableId: input.markerId, revision: input.timelineRevision };
      const policyContext = {
        requestId: context.requestId,
        operationId: context.operationId,
        executionId: context.executionId,
        scopeId: scope.scopeId,
        scopeRevision: scope.revision,
        projectLibraryId: scope.binding.projectLibraryId,
        projectId: input.projectId,
        timelineId: input.timelineId,
        projectRevision: scope.binding.projectRevision,
        timelineRevision: input.timelineRevision,
        resolvedTargets: [stableTarget],
        closedComposition: true,
        executableStableTargetPrecondition: true,
      };
      let authorization = null;
      let executionError = null;
      const timelineStartFrame = before.start.value.value;
      if (input.marker && input.marker.recordFrame < timelineStartFrame) {
        return {
          status: "failed", possibleMutation: "none", usage: "released",
          failure: failure("OPERATION_FAILED", "Marker position cannot precede the current timeline start.", context),
        };
      }
      let releaseProtectedTargetProof;
      try {
        releaseProtectedTargetProof = mutationPolicyGate.bindVerifiedProtectedTargets({
          accountFingerprint: context.accountFingerprint,
          executionId: context.executionId,
          scopeId: scope.scopeId,
          scopeRevision: scope.revision,
          timelineRevision: input.timelineRevision,
        });
      } catch (error) {
        return {
          status: "failed", possibleMutation: "none", usage: "not_reserved",
          failure: failure("EDIT_CONSTRAINT_VIOLATION", error.message, context, "none", "not_reserved"),
        };
      }
      try {
        try {
          await resolveService.executeSdkMarkerMutation(definition.action, {
            ...(input.marker ?? {}),
            ...(input.marker ? { recordFrame: input.marker.recordFrame - timelineStartFrame } : {}),
            targetFrame: target?.position.value.value,
          }, {
            mutationGuard: inspected.mutationGuard,
            policyContext,
            onAuthorization(value) { authorization = value; },
          });
        } catch (error) { executionError = error; }
      } finally {
        releaseProtectedTargetProof();
      }
      let after;
      try { after = (await liveInspectionService.readWithMutationGuard(inspectRequest, { deadlineAtMs: Date.now() + 60_000 })).value; } catch {
        return {
          status: "verification_failed", possibleMutation: "possible", usage: "unknown",
          failure: failure("VERIFICATION_FAILED", "Marker readback was unavailable after execution.", context, "possible"),
          verification: { outcome: "failed", summary: "Post-mutation readback was unavailable.", evidence: [evidence("readback", "Post-mutation marker readback failed.", { actionId })], protectedStatePreserved: null },
        };
      }
      const protectedPreserved = digest(protectedState(before)) === digest(protectedState(after));
      const expected = expectedPost(definition.action, before, after, input);
      const report = {
        outcome: expected.ok && protectedPreserved ? "passed" : "failed",
        summary: expected.ok && protectedPreserved ? "Exact marker readback and protected timeline structure matched." : "Marker readback or protected timeline structure did not match.",
        evidence: [
          evidence("readback", "Read back the complete marker collection after execution.", after.markers),
          evidence("structural", "Compared non-marker timeline structure before and after execution.", { before: protectedState(before), after: protectedState(after) }),
        ],
        protectedStatePreserved: protectedPreserved,
      };
      if (expected.ok && protectedPreserved) {
        if (authorization?.policyDecision) {
          mutationPolicyGate.assertProtectedStateEvidence(
            authorization.policyDecision.decisionId,
            report,
          );
        }
        return {
          status: "succeeded", possibleMutation: "confirmed", usage: "consumed", verification: report,
          result: { action: definition.action, marker: markerValue(expected.marker), previousMarker: markerValue(expected.previous), timelineRevision: after.revision },
        };
      }
      const unchanged = digest(semanticState(before)) === digest(semanticState(after));
      if (unchanged) {
        if (executionError?.cli_error_code === "EDIT_CONSTRAINT_VIOLATION") {
          return {
            status: "failed", possibleMutation: "none", usage: "not_reserved",
            failure: failure("EDIT_CONSTRAINT_VIOLATION", executionError.message, context, "none", "not_reserved"),
          };
        }
        return {
          status: "failed", possibleMutation: "none", usage: "released",
          failure: failure(executionError?.cli_error_code === "STALE_REVISION" ? "STALE_REVISION" : "OPERATION_FAILED", executionError?.message ?? "The marker mutation made no verified change.", context),
          ...(executionError?.cli_error_code === "EDIT_MUTATION_RESTORED" ? { recovery: { state: "restored", summary: "The original marker was restored.", evidence: report.evidence, manualRecoveryRequired: false } } : {}),
        };
      }
      if (executionError?.cli_error_code === "EDIT_MUTATION_RECOVERY_FAILED") {
        return {
          status: "recovery_failed", possibleMutation: "partial", usage: "consumed",
          postTimelineRevision: after.revision,
          failure: failure("RECOVERY_FAILED", executionError.message, context, "partial", "consumed"),
          verification: report,
          recovery: { state: "failed", summary: "Automatic marker recovery did not restore the expected state.", evidence: report.evidence, manualRecoveryRequired: true },
        };
      }
      return {
        status: "verification_failed", possibleMutation: "possible", usage: "consumed",
        postTimelineRevision: after.revision,
        failure: failure("VERIFICATION_FAILED", executionError?.message ?? "The marker mutation produced an unexpected timeline state.", context, "possible", "consumed"),
        verification: report,
        recovery: { state: "manual_required", summary: "Inspect the current timeline before retrying this marker mutation.", evidence: report.evidence, manualRecoveryRequired: true },
      };
    },
  }]));
}
