import crypto from "node:crypto";
import {
  sdkMarkerCreateInputSchema,
  sdkMarkerDeleteInputSchema,
  sdkMarkerMutationResultSchema,
  sdkMarkerUpdateInputSchema,
} from "../contracts/generated/sdk-operations.js";

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

function findTarget(snapshot, markerId) {
  return snapshot.markers.find((marker) => marker.id === markerId) ?? null;
}

function targetIds(input) {
  return input.markerIds ?? [input.markerId];
}

function sameMarker(left, right) {
  return left?.id === right?.id
    && left?.position.value.value === right?.position.value.value
    && left?.color === right?.color
    && left?.name === right?.name
    && left?.note === right?.note
    && left?.duration.value.value === right?.duration.value.value;
}

function preservesOtherMarkers(before, after, beforeExcludedIds = [], afterExcludedIds = beforeExcludedIds) {
  const beforeExcluded = new Set(beforeExcludedIds.filter(Boolean));
  const afterExcluded = new Set(afterExcludedIds.filter(Boolean));
  const expected = before.markers.filter((marker) => !beforeExcluded.has(marker.id));
  const actual = after.markers.filter((marker) => !afterExcluded.has(marker.id));
  return expected.length === actual.length
    && expected.every((marker) => sameMarker(marker, actual.find((candidate) => candidate.id === marker.id)));
}

function markerUpdateEntries(input) {
  return input.updates ?? [{ markerId: input.markerId, marker: input.marker }];
}

function expectedUpdatePost(before, after, updates) {
  const previousMarkers = updates.map((update) => findTarget(before, update.markerId));
  if (previousMarkers.some((marker) => marker === null)) {
    return { ok: false, previousMarkers, markers: [] };
  }
  const markers = updates.map(({ marker: expected }) => after.markers.find((candidate) => (
    candidate.position.value.value === expected.recordFrame
    && candidate.color === expected.color
    && candidate.name === expected.name
    && candidate.note === expected.note
    && candidate.duration.value.value === expected.durationFrames
  )) ?? null);
  const resultingIds = new Set(markers.filter(Boolean).map((marker) => marker.id));
  const targetIds = new Set(updates.map((update) => update.markerId));
  const exactCollection = markers.every(Boolean)
    && resultingIds.size === updates.length
    && before.markers.length === after.markers.length
    && preservesOtherMarkers(before, after, [...targetIds], [...resultingIds])
    && updates.every((update, index) => findTarget(after, update.markerId) === null || markers[index]?.id === update.markerId);
  return { ok: exactCollection, previousMarkers, markers };
}

function expectedPost(action, before, after, input) {
  const ids = action === "create" ? [] : targetIds(input);
  const beforeTargets = ids.map((id) => findTarget(before, id));
  const beforeTarget = beforeTargets[0] ?? null;
  if (action !== "create" && beforeTargets.some((target) => target === null)) return { ok: false, previous: null, previousMarkers: [], marker: null, markers: [] };
  if (action === "delete") {
    return {
      ok: ids.every((id) => findTarget(after, id) === null)
        && after.markers.length === before.markers.length - ids.length
        && preservesOtherMarkers(before, after, ids),
      previous: beforeTarget,
      previousMarkers: beforeTargets,
      marker: null,
      markers: [],
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
    ? after.markers.length === before.markers.length + 1 && preservesOtherMarkers(before, after, [], [marker?.id])
    : after.markers.length === before.markers.length
      && preservesOtherMarkers(before, after, ids, [marker?.id])
      && (findTarget(after, input.markerId) === null || marker?.id === input.markerId);
  return { ok: Boolean(marker && exactCollection), previous: beforeTarget, previousMarkers: beforeTargets, marker, markers: marker ? [marker] : [] };
}

function expectedCreateBatchPost(before, after, requestedMarkers) {
  const beforeIds = new Set(before.markers.map((marker) => marker.id));
  const created = requestedMarkers.map((expected) => after.markers.find((candidate) => (
    !beforeIds.has(candidate.id)
    && candidate.position.value.value === expected.recordFrame
    && candidate.color === expected.color
    && candidate.name === expected.name
    && candidate.note === expected.note
    && candidate.duration.value.value === expected.durationFrames
  )) ?? null);
  const createdIds = new Set(created.filter(Boolean).map((marker) => marker.id));
  const preserved = before.markers.every((marker) => sameMarker(marker, after.markers.find((candidate) => candidate.id === marker.id)));
  return {
    ok: created.every(Boolean)
      && createdIds.size === requestedMarkers.length
      && after.markers.length === before.markers.length + requestedMarkers.length
      && preserved,
    markers: created.filter(Boolean),
  };
}

export function createSdkMarkerActions({ liveInspectionService, resolveService, activatedActionIds = Object.keys(ACTIONS) }) {
  if (typeof liveInspectionService?.readWithMutationGuard !== "function") throw new TypeError("Marker actions require live inspection with a mutation guard.");
  if (typeof resolveService?.executeSdkMarkerMutation !== "function") throw new TypeError("Marker actions require the CutAgent CLI mutation boundary.");
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
      const createBatch = definition.action === "create" && "markers" in input;
      const updates = definition.action === "update" ? markerUpdateEntries(input) : null;
      const ids = updates?.map((update) => update.markerId) ?? (definition.action === "delete" ? targetIds(input) : []);
      const targets = ids.map((id) => findTarget(before, id));
      const target = targets[0] ?? null;
      if (definition.action !== "create" && targets.some((item) => item === null)) {
        return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "The marker changed or disappeared after preview.", context) };
      }
      if (definition.action === "update" && !Array.isArray(input.updates) && updates.some((update, index) => {
        const current = targets[index];
        return current.position.value.value === update.marker.recordFrame
          && current.color === update.marker.color && current.name === update.marker.name
          && current.note === update.marker.note && current.duration.value.value === update.marker.durationFrames;
      })) {
        return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("OPERATION_FAILED", "Marker update must change at least one semantic value.", context) };
      }
      let executionError = null;
      const timelineStartFrame = before.start.value.value;
      const requestedMarkers = createBatch
        ? input.markers
        : updates?.map((update) => update.marker) ?? (input.marker ? [input.marker] : []);
      if (requestedMarkers.some((marker) => marker.recordFrame < timelineStartFrame)) {
        return {
          status: "failed", possibleMutation: "none", usage: "released",
          failure: failure("OPERATION_FAILED", "Marker position cannot precede the current timeline start.", context),
        };
      }
      if (updates) {
        const markerIds = updates.map((update) => update.markerId);
        const recordFrames = updates.map((update) => update.marker.recordFrame);
        const targetIdSet = new Set(markerIds);
        const occupiedDestination = updates.some((update) => before.markers.some((marker) => (
          !targetIdSet.has(marker.id) && marker.position.value.value === update.marker.recordFrame
        )));
        if (new Set(markerIds).size !== markerIds.length || new Set(recordFrames).size !== recordFrames.length || occupiedDestination) {
          return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("OPERATION_FAILED", "Marker updates require unique targets and unoccupied destination positions.", context) };
        }
      }
      try {
        const executionInput = createBatch
          ? { markers: input.markers.map((marker) => ({ ...marker, recordFrame: marker.recordFrame - timelineStartFrame })) }
          : updates
            ? { updates: updates.map((update, index) => ({
              targetFrame: targets[index].position.value.value,
              ...update.marker,
              recordFrame: update.marker.recordFrame - timelineStartFrame,
            })) }
            : {
              ...(input.marker ?? {}),
              ...(input.marker ? { recordFrame: input.marker.recordFrame - timelineStartFrame } : {}),
              ...(definition.action === "delete"
                ? { targetFrames: targets.map((item) => item.position.value.value) }
                : { targetFrame: target?.position.value.value }),
            };
        await resolveService.executeSdkMarkerMutation(definition.action, executionInput, { mutationGuard: inspected.mutationGuard });
      } catch (error) { executionError = error; }
      let after;
      try { after = (await liveInspectionService.readWithMutationGuard(inspectRequest, { deadlineAtMs: Date.now() + 60_000 })).value; } catch {
        return {
          status: "verification_failed", possibleMutation: "possible", usage: "unknown",
          failure: failure("VERIFICATION_FAILED", "Marker readback was unavailable after execution.", context, "possible"),
          verification: { outcome: "failed", summary: "Post-mutation readback was unavailable.", evidence: [evidence("readback", "Post-mutation marker readback failed.", { actionId })], protectedStatePreserved: null },
        };
      }
      const protectedPreserved = digest(protectedState(before)) === digest(protectedState(after));
      const expected = createBatch
        ? expectedCreateBatchPost(before, after, input.markers)
        : updates
          ? expectedUpdatePost(before, after, updates)
          : expectedPost(definition.action, before, after, input);
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
        const result = createBatch
          ? { action: definition.action, markers: expected.markers.map(markerValue), previousMarkers: [], timelineRevision: after.revision }
          : input.updates
            ? { action: "update", markers: expected.markers.map(markerValue), previousMarkers: expected.previousMarkers.map(markerValue), timelineRevision: after.revision }
          : definition.action === "delete" && Array.isArray(input.markerIds)
            ? { action: definition.action, markers: [], previousMarkers: expected.previousMarkers.map(markerValue), timelineRevision: after.revision }
            : { action: definition.action, marker: markerValue(expected.marker), previousMarker: markerValue(expected.previous), timelineRevision: after.revision };
        return {
          status: "succeeded", possibleMutation: "confirmed", usage: "consumed", verification: report,
          result,
        };
      }
      const unchanged = digest(semanticState(before)) === digest(semanticState(after));
      if (unchanged) {

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
