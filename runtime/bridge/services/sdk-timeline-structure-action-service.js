import crypto from "node:crypto";
import {
  sdkTimelineRemoveMutationOutputSchema as resultSchema,
  sdkTimelineRemoveMutationRequestSchema as inputSchema,
} from "../contracts/generated/sdk-operations.js";

const digest = (value) => `sha256:${crypto.createHash("sha256").update(JSON.stringify(value), "utf8").digest("hex")}`;
const evidence = (modality, summary, value) => ({ evidenceId: `evidence_${crypto.randomUUID()}`, modality, summary, capturedAt: new Date().toISOString(), digest: digest(value) });
const rows = (snapshot) => snapshot.tracks.flatMap((track) => track.clips.map((clip) => ({ track, clip })));
const markerValues = (snapshot) => (snapshot.markers ?? []).map(({ snapshotRevision: _revision, ...marker }) => marker);
const locate = (snapshot, id) => rows(snapshot).find(({ clip }) => clip.id === id) ?? null;
const clipValue = (located) => located ? { track: { type: located.track.type, index: located.track.index }, id: located.clip.id, name: located.clip.name,
  recordRange: located.clip.recordRange, duration: located.clip.duration, sourceRange: located.clip.sourceRange, mediaPoolItemId: located.clip.mediaPoolItemId, linkedItemIds: located.clip.linkedItemIds } : null;
const clipValueWithoutLinks = (located) => { const value = clipValue(located); if (!value) return null; const { linkedItemIds: _discard, ...rest } = value; return rest; };
const sameIds = (left, right) => left.length === right.length && [...left].sort().every((value, index) => value === [...right].sort()[index]);
const failure = (code, message, context, possibleMutation = "none", usage = possibleMutation === "none" ? "released" : "unknown") => ({
  kind: code === "STALE_REVISION" ? "stale_revision" : code === "CAPABILITY_UNAVAILABLE" ? "capability_unavailable" : code === "VERIFICATION_FAILED" ? "verification_failed" : "operation_failed",
  code, message, retrySafe: false, possibleMutation, usage, recovery: possibleMutation === "none" ? ["inspect_state"] : ["inspect_state", "manual_recovery"],
  recoveryGuidance: [possibleMutation === "none" ? "Inspect the timeline and create a fresh managed preview." : "Inspect the current timeline before any further mutation."],
  readbackRequired: possibleMutation !== "none", requestId: context.requestId, operationId: context.operationId, executionId: context.executionId,
});

export function createSdkTimelineStructureActions({ liveInspectionService, resolveService }) {
  if (typeof liveInspectionService?.readWithMutationGuard !== "function" || typeof resolveService?.executeSdkTimelineStructure !== "function") throw new TypeError("Managed removal requires guarded inspection and the CutAgent CLI mutation boundary.");
  return { "cutagent.action.timeline.items.delete": {
    inputSchema, resultSchema, idempotency: "required",
    async execute(context, rawInput) {
      const input = inputSchema.parse(rawInput);
      const removals = input.operation === "clip_remove_many" ? input.removals : [input];
      const first = removals[0];
      let inspected;
      try { inspected = await liveInspectionService.readWithMutationGuard({ operation: "timeline.snapshot", projectId: first.projectId, timelineId: first.timelineId }, { deadlineAtMs: Date.now() + 60_000 }); }
      catch (error) { return { status: "failed", possibleMutation: "none", usage: "released", failure: failure(error?.code ?? "OPERATION_FAILED", error?.message ?? "Timeline inspection failed.", context) }; }
      const before = inspected.value;
      if (before.revision !== first.timelineRevision) return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "The timeline changed after managed preview.", context) };
      const allRows = rows(before);
      const affected = removals.flatMap((removal) => removal.affectedItemIds);
      if (new Set(affected).size !== affected.length || !sameIds(affected, removals.map((removal) => removal.clipId))) {
        return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("INVALID_REQUEST", "Plural removal targets must exactly match unique affected item identities.", context) };
      }
      for (const removal of removals) {
        const target = locate(before, removal.clipId);
        if (!target || target.track.type !== removal.track.type || target.track.index !== removal.track.index || target.clip.name !== removal.name
          || target.clip.recordRange.start !== removal.range.start || target.clip.recordRange.endExclusive !== removal.range.endExclusive) {
          return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "An exact managed removal target changed.", context) };
        }
        if (removal.affectedItemIds.length !== 1 || removal.affectedItemIds[0] !== removal.clipId
          || removal.affectedTracks.length !== 1 || removal.affectedTracks[0].type !== removal.track.type
          || removal.affectedTracks[0].index !== removal.track.index) {
          return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("INVALID_REQUEST", "Each plural removal entry must bind one exact clip and track.", context) };
        }
        if (input.operation === "clip_remove") {
          const selectorMatches = allRows.filter(({ track, clip }) => track.type === removal.track.type && track.index === removal.track.index
            && clip.recordRange.start >= removal.range.start && clip.recordRange.endExclusive <= removal.range.endExclusive).map(({ clip }) => clip.id);
          if (!sameIds(selectorMatches, removal.affectedItemIds)) {
            return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("INVALID_REQUEST", "The exact executable selector would include undeclared or protected timeline items.", context) };
          }
        }
      }
      const transitionById = new Map();
      for (const removal of removals) {
        for (const transition of removal.expectedLinkTransitions) {
          const prior = transitionById.get(transition.itemId);
          if (prior && digest(prior) !== digest(transition)) {
            return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("INVALID_REQUEST", "Plural removal link transitions disagree.", context) };
          }
          transitionById.set(transition.itemId, transition);
        }
      }
      const transitions = [...transitionById.values()];
      const transitionIds = transitions.map((transition) => transition.itemId);
      if (transitionIds.some((id) => affected.includes(id))) return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("INVALID_REQUEST", "Managed link transitions must be disjoint from deleted identities.", context) };
      const transitionsCurrent = transitions.every((transition) => {
        const located = locate(before, transition.itemId);
        return located && sameIds(located.clip.linkedItemIds ?? [], transition.beforeLinkedItemIds);
      });
      if (!transitionsCurrent) return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "The managed reciprocal-link transition changed before execution.", context) };
      const protectedIds = allRows.map(({ clip }) => clip.id).filter((id) => !affected.includes(id) && !transitionIds.includes(id));
      if (removals.some((removal) => !sameIds(protectedIds, removal.protectedItemIds))) return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "The closed managed removal impact changed.", context) };
      let executionError = null;
      try { await resolveService.executeSdkTimelineStructure(input, before, { mutationGuard: inspected.mutationGuard, onAuthorization() {} }); } catch (error) { executionError = error; }
      let after; try { after = (await liveInspectionService.readWithMutationGuard({ operation: "timeline.snapshot", projectId: first.projectId, timelineId: first.timelineId }, { deadlineAtMs: Date.now() + 60_000 })).value; }
      catch (error) {
        const cause = [error?.name, error?.code, error?.message].filter((value) => typeof value === "string" && value).join(": ").slice(0, 500).replace(/[.\s]+$/u, "");
        return { status: "verification_failed", possibleMutation: "possible", usage: "unknown", failure: failure("VERIFICATION_FAILED", `Timeline readback was unavailable after managed removal${cause ? `: ${cause}` : ""}.`, context, "possible"), verification: { outcome: "failed", summary: "Post-mutation readback was unavailable.", evidence: [evidence("readback", "Post-mutation timeline readback failed.", { input, cause })], protectedStatePreserved: null } };
      }
      const afterIds = new Set(rows(after).map(({ clip }) => clip.id)); const outputItemIds = [...afterIds].filter((id) => !allRows.some(({ clip }) => clip.id === id));
      const ordinaryProtectedStatePreserved = protectedIds.every((id) => digest(clipValue(locate(before, id))) === digest(clipValue(locate(after, id))));
      const linkTransitionsPreserved = transitions.every((transition) => {
        const beforeLocated = locate(before, transition.itemId); const afterLocated = locate(after, transition.itemId);
        return beforeLocated && afterLocated
          && digest(clipValueWithoutLinks(beforeLocated)) === digest(clipValueWithoutLinks(afterLocated))
          && sameIds(afterLocated.clip.linkedItemIds ?? [], transition.afterLinkedItemIds);
      });
      const protectedStatePreserved = ordinaryProtectedStatePreserved && linkTransitionsPreserved;
      const matched = affected.every((id) => !afterIds.has(id)) && outputItemIds.length === 0 && digest(markerValues(before)) === digest(markerValues(after));
      const passed = !executionError && after.revision !== before.revision && matched && protectedStatePreserved;
      const report = { outcome: passed ? "passed" : "failed", summary: passed ? "Exact non-ripple managed removal and protected items matched readback." : "Managed removal readback did not match.",
        evidence: [evidence("readback", "Read back the complete timeline after managed removal.", { beforeRevision: before.revision, afterRevision: after.revision }), evidence("structural", "Compared affected, protected, and exact reciprocal-link transition identities.", { affected, protectedIds, transitions, matched, ordinaryProtectedStatePreserved, linkTransitionsPreserved })], protectedStatePreserved };
      if (passed) {
        const results = removals.map((removal) => ({ operation: "clip_remove", timelineRevision: after.revision, affectedTracks: removal.affectedTracks,
          affectedItemIds: removal.affectedItemIds, protectedItemIds: removal.protectedItemIds, outputItemIds, protectedStatePreserved: true }));
        return { status: "succeeded", possibleMutation: "confirmed", usage: "consumed", verification: report,
          result: input.operation === "clip_remove_many" ? { operation: "clip_remove_many", results } : results[0] };
      }
      if (after.revision === before.revision) return { status: "failed", possibleMutation: "none", usage: "released", failure: failure(executionError?.code ?? "OPERATION_FAILED", executionError?.message ?? "Managed removal made no verified change.", context) };
      return { status: "verification_failed", possibleMutation: "possible", usage: "consumed", failure: failure("VERIFICATION_FAILED", executionError?.message ?? "Managed removal produced unexpected state.", context, "possible", "consumed"), verification: report, recovery: { state: "manual_required", summary: "Inspect the timeline before retrying managed authoring.", evidence: report.evidence, manualRecoveryRequired: true } };
    },
  } };
}
