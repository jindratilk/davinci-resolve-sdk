import crypto from "node:crypto";
import { sdkTimelineRemoveMutationInputSchema as inputSchema, sdkTimelineRemoveMutationResultSchema as resultSchema } from "../contracts/generated/sdk-operations.js";
import {resolveSdkDirectMutationScope, sdkMutationScopeCandidates} from "./sdk-direct-mutation-scope.js";

const digest = (value) => `sha256:${crypto.createHash("sha256").update(JSON.stringify(value), "utf8").digest("hex")}`;
const evidence = (modality, summary, value) => ({ evidenceId: `evidence_${crypto.randomUUID()}`, modality, summary, capturedAt: new Date().toISOString(), digest: digest(value) });
const rows = (snapshot) => snapshot.tracks.flatMap((track) => track.clips.map((clip) => ({ track, clip })));
const locate = (snapshot, id) => rows(snapshot).find(({ clip }) => clip.id === id) ?? null;
const clipValue = (located) => located ? { track: { type: located.track.type, index: located.track.index }, id: located.clip.id, name: located.clip.name,
  recordRange: located.clip.recordRange, duration: located.clip.duration, sourceRange: located.clip.sourceRange, mediaPoolItemId: located.clip.mediaPoolItemId, linkedItemIds: located.clip.linkedItemIds } : null;
const clipValueWithoutLinks = (located) => { const value = clipValue(located); if (!value) return null; const { linkedItemIds: _discard, ...rest } = value; return rest; };
const sameIds = (left, right) => left.length === right.length && [...left].sort().every((value, index) => value === [...right].sort()[index]);
const failure = (code, message, context, possibleMutation = "none", usage = possibleMutation === "none" ? "released" : "unknown") => ({
  kind: code === "STALE_REVISION" ? "stale_revision" : code === "EDIT_CONSTRAINT_VIOLATION" ? "edit_constraint_violation" : code === "CAPABILITY_UNAVAILABLE" ? "capability_unavailable" : code === "VERIFICATION_FAILED" ? "verification_failed" : "operation_failed",
  code, message, retrySafe: false, possibleMutation, usage, recovery: possibleMutation === "none" ? ["inspect_state"] : ["inspect_state", "manual_recovery"],
  recoveryGuidance: [possibleMutation === "none" ? "Inspect the timeline and create a fresh managed preview." : "Inspect the current timeline before any further mutation."],
  readbackRequired: possibleMutation !== "none", requestId: context.requestId, operationId: context.operationId, executionId: context.executionId,
});

function exactScope(gate, accountFingerprint, input, directScope = null) {
  const affectedTypes = new Set(input.affectedTracks.map((track) => track.type));
  const scopes = sdkMutationScopeCandidates(gate, accountFingerprint, directScope).filter((scope) => scope.binding.level === "project+timeline"
    && scope.binding.projectId === input.projectId && scope.binding.timelineId === input.timelineId && scope.binding.timelineRevision === input.timelineRevision
    && (scope.constraints.allowedOperations.length === 0 || scope.constraints.allowedOperations.includes("timeline.items.delete"))
    && [...affectedTypes].every((type) => scope.constraints.allowedTrackTypes.length === 0 || scope.constraints.allowedTrackTypes.includes(type)));
  if (scopes.length !== 1) throw Object.assign(new Error("Exactly one current user-owned constraint scope must authorize managed removal."), { code: "EDIT_CONSTRAINT_VIOLATION" });
  return scopes[0];
}

export function createSdkTimelineStructureActions({ liveInspectionService, resolveService, mutationPolicyGate, directMutationPolicyAuthority = null }) {
  if (typeof liveInspectionService?.readWithMutationGuard !== "function" || typeof resolveService?.executeSdkTimelineStructure !== "function") throw new TypeError("Managed removal requires guarded inspection and the CutAgent CLI mutation boundary.");
  return { "cutagent.action.timeline.items.delete": {
    inputSchema, resultSchema, idempotency: "required",
    async execute(context, rawInput) {
      const input = inputSchema.parse(rawInput);
      let inspected;
      try { inspected = await liveInspectionService.readWithMutationGuard({ operation: "timeline.snapshot", projectId: input.projectId, timelineId: input.timelineId }, { deadlineAtMs: Date.now() + 60_000 }); }
      catch (error) { return { status: "failed", possibleMutation: "none", usage: "released", failure: failure(error?.code ?? "OPERATION_FAILED", error?.message ?? "Timeline inspection failed.", context) }; }
      const before = inspected.value;
      if (before.revision !== input.timelineRevision) return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "The timeline changed after managed preview.", context) };
      const target = locate(before, input.clipId);
      if (!target || target.track.type !== input.track.type || target.track.index !== input.track.index || target.clip.name !== input.name
        || target.clip.recordRange.start !== input.range.start || target.clip.recordRange.endExclusive !== input.range.endExclusive) return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "The exact managed removal target changed.", context) };
      const affected = [...new Set(input.affectedItemIds)];
      const allRows = rows(before);
      const affectedRows = affected.map((id) => locate(before, id));
      const selectorMatches = allRows.filter(({ track, clip }) => track.type === input.track.type && track.index === input.track.index
        && clip.recordRange.start >= input.range.start && clip.recordRange.endExclusive <= input.range.endExclusive).map(({ clip }) => clip.id);
      if (affectedRows.some((located) => !located || located.track.type !== input.track.type || located.track.index !== input.track.index)
        || !sameIds(selectorMatches, affected)) return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("EDIT_CONSTRAINT_VIOLATION", "The exact executable selector would include undeclared or protected timeline items.", context) };
      const transitionIds = input.expectedLinkTransitions.map((transition) => transition.itemId);
      if (new Set(transitionIds).size !== transitionIds.length || transitionIds.some((id) => affected.includes(id))) return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("EDIT_CONSTRAINT_VIOLATION", "Managed link transitions must be unique and disjoint from deleted identities.", context) };
      const transitionsCurrent = input.expectedLinkTransitions.every((transition) => {
        const located = locate(before, transition.itemId);
        return located && sameIds(located.clip.linkedItemIds ?? [], transition.beforeLinkedItemIds);
      });
      if (!transitionsCurrent) return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "The managed reciprocal-link transition changed before execution.", context) };
      const protectedIds = allRows.map(({ clip }) => clip.id).filter((id) => !affected.includes(id) && !transitionIds.includes(id));
      const tracks = [...new Map(allRows.filter(({ clip }) => affected.includes(clip.id))
        .map(({ track }) => [`${track.type}:${track.index}`, { type: track.type, index: track.index }])).values()];
      if (!sameIds(affected, input.affectedItemIds) || !sameIds(protectedIds, input.protectedItemIds) || digest(tracks) !== digest(input.affectedTracks)) return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "The closed managed removal impact changed.", context) };
      let scope; try {
        const directScope = await resolveSdkDirectMutationScope({directMutationPolicyAuthority, context, liveInspectionService, level: "project+timeline", projectId: input.projectId, timelineId: input.timelineId, timelineRevision: input.timelineRevision});
        scope = exactScope(mutationPolicyGate, context.accountFingerprint, input, directScope);
      } catch (error) { return { status: "failed", possibleMutation: "none", usage: "not_reserved", failure: failure(error.code ?? "EDIT_CONSTRAINT_VIOLATION", error.message, context, "none", "not_reserved") }; }
      const policyContext = { requestId: context.requestId, operationId: context.operationId, executionId: context.executionId, scopeId: scope.scopeId, scopeRevision: scope.revision,
        projectLibraryId: scope.binding.projectLibraryId, projectId: input.projectId, timelineId: input.timelineId, projectRevision: scope.binding.projectRevision, timelineRevision: input.timelineRevision,
        resolvedTargets: [{ kind: "timeline", stableId: input.timelineId, revision: input.timelineRevision },
          ...affected.map((id) => { const located = locate(before, id); return { kind: "clip", stableId: id, revision: input.timelineRevision, trackType: located.track.type, trackIndex: located.track.index }; }),
          ...transitionIds.map((id) => { const located = locate(before, id); return { kind: "clip", stableId: id, revision: input.timelineRevision, trackType: located.track.type, trackIndex: located.track.index }; }),
          ...[...new Map(allRows.filter(({ clip }) => affected.includes(clip.id)).map(({ track }) => [`${track.type}:${track.index}`, track])).values()].map((track) => ({ kind: "track", stableId: track.snapshotId, revision: input.timelineRevision, trackType: track.type, trackIndex: track.index }))],
        affectedTrackTypes: [...new Set(tracks.map((track) => track.type))], semanticOperation: "clip_remove", selectorRange: input.range,
        selectorItemIds: affected, expectedLinkTransitionIds: transitionIds,
        closedComposition: true, executableStableTargetPrecondition: true };
      let releaseProof; try { releaseProof = mutationPolicyGate.bindVerifiedProtectedTargets({ accountFingerprint: context.accountFingerprint, executionId: context.executionId, scopeId: scope.scopeId, scopeRevision: scope.revision, timelineRevision: input.timelineRevision }); }
      catch (error) { return { status: "failed", possibleMutation: "none", usage: "not_reserved", failure: failure("EDIT_CONSTRAINT_VIOLATION", error.message, context, "none", "not_reserved") }; }
      let authorization = null; let executionError = null;
      try { try { await resolveService.executeSdkTimelineStructure(input, before, { mutationGuard: inspected.mutationGuard, policyContext, onAuthorization(value) { authorization = value; } }); } catch (error) { executionError = error; } } finally { releaseProof(); }
      let after; try { after = (await liveInspectionService.readWithMutationGuard({ operation: "timeline.snapshot", projectId: input.projectId, timelineId: input.timelineId }, { deadlineAtMs: Date.now() + 60_000 })).value; }
      catch { return { status: "verification_failed", possibleMutation: "possible", usage: "unknown", failure: failure("VERIFICATION_FAILED", "Timeline readback was unavailable after managed removal.", context, "possible"), verification: { outcome: "failed", summary: "Post-mutation readback was unavailable.", evidence: [evidence("readback", "Post-mutation timeline readback failed.", input)], protectedStatePreserved: null } }; }
      const afterIds = new Set(rows(after).map(({ clip }) => clip.id)); const outputItemIds = [...afterIds].filter((id) => !allRows.some(({ clip }) => clip.id === id));
      const ordinaryProtectedStatePreserved = protectedIds.every((id) => digest(clipValue(locate(before, id))) === digest(clipValue(locate(after, id))));
      const linkTransitionsPreserved = input.expectedLinkTransitions.every((transition) => {
        const beforeLocated = locate(before, transition.itemId); const afterLocated = locate(after, transition.itemId);
        return beforeLocated && afterLocated
          && digest(clipValueWithoutLinks(beforeLocated)) === digest(clipValueWithoutLinks(afterLocated))
          && sameIds(afterLocated.clip.linkedItemIds ?? [], transition.afterLinkedItemIds);
      });
      const protectedStatePreserved = ordinaryProtectedStatePreserved && linkTransitionsPreserved;
      const matched = affected.every((id) => !afterIds.has(id)) && outputItemIds.length === 0 && digest(before.markers ?? []) === digest(after.markers ?? []);
      const passed = !executionError && after.revision !== before.revision && Boolean(authorization?.policyDecision) && matched && protectedStatePreserved;
      const report = { outcome: passed ? "passed" : "failed", summary: passed ? "Exact non-ripple managed removal and protected items matched readback." : "Managed removal readback did not match.",
        evidence: [evidence("readback", "Read back the complete timeline after managed removal.", { beforeRevision: before.revision, afterRevision: after.revision }), evidence("structural", "Compared affected, protected, and exact reciprocal-link transition identities.", { affected, protectedIds, transitions: input.expectedLinkTransitions, matched, ordinaryProtectedStatePreserved, linkTransitionsPreserved })], protectedStatePreserved };
      if (passed) { try { mutationPolicyGate.assertProtectedStateEvidence(authorization.policyDecision.decisionId, report); } catch (error) { return { status: "verification_failed", possibleMutation: "confirmed", usage: "consumed", failure: failure("VERIFICATION_FAILED", error.message, context, "confirmed", "consumed"), verification: { ...report, outcome: "failed" } }; }
        return { status: "succeeded", possibleMutation: "confirmed", usage: "consumed", verification: report, result: { operation: "clip_remove", timelineRevision: after.revision, affectedTracks: input.affectedTracks, affectedItemIds: affected, protectedItemIds: protectedIds, outputItemIds, protectedStatePreserved: true } }; }
      if (after.revision === before.revision) return { status: "failed", possibleMutation: "none", usage: "released", failure: failure(executionError?.code ?? "OPERATION_FAILED", executionError?.message ?? "Managed removal made no verified change.", context) };
      return { status: "verification_failed", possibleMutation: "possible", usage: "consumed", failure: failure("VERIFICATION_FAILED", executionError?.message ?? "Managed removal produced unexpected state.", context, "possible", "consumed"), verification: report, recovery: { state: "manual_required", summary: "Inspect the timeline before retrying managed authoring.", evidence: report.evidence, manualRecoveryRequired: true } };
    },
  } };
}
