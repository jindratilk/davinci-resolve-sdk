import crypto from "node:crypto";
import {
  sdkTimelineItemMoveInputSchema,
  sdkTimelineItemMoveResultSchema,
} from "../contracts/generated/sdk-operations.js";

const ACTION_ID = "cutagent.action.timeline.items.move";

function digest(value) {
  return `sha256:${crypto.createHash("sha256").update(JSON.stringify(value), "utf8").digest("hex")}`;
}

function evidence(modality, summary, value) {
  return { evidenceId: `evidence_${crypto.randomUUID()}`, modality, summary, capturedAt: new Date().toISOString(), digest: digest(value) };
}

function failure(code, message, context, possibleMutation = "none", usage = possibleMutation === "none" ? "released" : "unknown") {
  const kind = code === "STALE_REVISION" ? "stale_revision"
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

async function executePlural(context, inputs, { readTimelineStructure, readPostMutationTimeline, resolveService }) {
  const binding = inputs[0];
  if (inputs.some((input) => input.projectId !== binding.projectId || input.timelineId !== binding.timelineId || input.timelineRevision !== binding.timelineRevision)) {
    return { status: "failed", possibleMutation: "none", usage: "not_reserved", failure: failure("INVALID_REQUEST", "Plural timeline-item moves must share one project, timeline, and revision.", context, "none", "not_reserved") };
  }
  const inspectRequest = {
    operation: "timeline.structure",
    projectId: binding.projectId,
    timelineId: binding.timelineId,
    expectedRevision: binding.timelineRevision,
  };
  const inspected = await readTimelineStructure(inspectRequest, { deadlineAtMs: Date.now() + 60_000 });
  const before = inspected.value;
  if (before.revision !== binding.timelineRevision) return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "The timeline changed after the item move preview.", context) };
  const prepared = [];
  for (const input of inputs) {
    const target = locateByDurableId(before, input.target.id);
    if (!target || target.track.type !== "video" || target.clip.id === null || !exactDescriptor(target, input.target)) {
      return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "An exact video item changed or disappeared after preview.", context) };
    }
    const nativeTargetId = inspected.privateTimelineItemNativeIdByPublicId?.get(input.target.id);
    const destinationTrack = before.tracks.find((track) => track.type === "video" && track.index === input.destination.trackIndex);
    if (typeof nativeTargetId !== "string" || !nativeTargetId || !destinationTrack) return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "A private target identity or destination track became unavailable.", context) };
    if (target.track.locked !== false || destinationTrack.locked !== false) return { status: "failed", possibleMutation: "none", usage: "not_reserved", failure: failure("INVALID_REQUEST", "Authoritative unlocked state is required for every affected video track.", context, "none", "not_reserved") };
    const linked = input.linkedAudioTargets.map((expected) => {
      const found = locateByDurableId(before, expected.id);
      return found && found.track.type === "audio" && exactDescriptor(found, expected) ? found : null;
    });
    if (linked.some((item) => item === null)) return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "A linked audio target changed or became ambiguous.", context) };
    const linkedFound = linked.filter(Boolean);
    const privateLinkedAudioTargets = input.linkedAudioTargets.map((expected) => {
      const id = inspected.privateTimelineItemNativeIdByPublicId?.get(expected.id);
      return typeof id === "string" && id ? { ...expected, id } : null;
    });
    if (privateLinkedAudioTargets.some((item) => item === null)) return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "A private linked-audio identity became unavailable.", context) };
    const closedIds = new Set([target.clip.id, ...linkedFound.map((item) => item.clip.id)]);
    if (target.clip.linkedItemIds === null || target.clip.linkedItemIds.length !== linkedFound.length
      || linkedFound.some((item) => item.clip.id === null || !target.clip.linkedItemIds.includes(item.clip.id)
        || item.clip.linkedItemIds === null || !item.clip.linkedItemIds.includes(target.clip.id)
        || item.clip.linkedItemIds.some((id) => !closedIds.has(id)))) {
      return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "Authoritative linked A/V topology no longer matches a preview.", context) };
    }
    const changesRecordPosition = input.destination.recordStartFrame !== input.target.recordStartFrame;
    if (input.linkedAudio === "preserve" && changesRecordPosition && linkedFound.some((item) => item.track.locked !== false)) return { status: "failed", possibleMutation: "none", usage: "not_reserved", failure: failure("INVALID_REQUEST", "Authoritative unlocked state is required for every affected linked-audio track.", context, "none", "not_reserved") };
    prepared.push({ input, target, destinationTrack, linkedFound, privateTarget: { ...input.target, id: nativeTargetId }, privateLinkedAudioTargets, changesRecordPosition });
  }
  const targetIds = new Set(prepared.map(({ target }) => target.clip.id));
  const linkedIds = new Set(prepared.flatMap(({ input, linkedFound, changesRecordPosition }) => input.linkedAudio === "preserve" && changesRecordPosition ? linkedFound.map((item) => item.clip.id) : []));
  if (targetIds.size !== prepared.length || linkedIds.size !== prepared.flatMap(({ input, linkedFound, changesRecordPosition }) => input.linkedAudio === "preserve" && changesRecordPosition ? linkedFound : []).length) {
    return { status: "failed", possibleMutation: "none", usage: "not_reserved", failure: failure("INVALID_REQUEST", "Plural timeline-item moves cannot repeat a target or linked companion.", context, "none", "not_reserved") };
  }
  for (let index = 0; index < prepared.length; index += 1) {
    const current = prepared[index];
    if (current.input.collisionPolicy !== "reject") continue;
    const duration = current.input.target.recordEndFrame - current.input.target.recordStartFrame;
    const end = current.input.destination.recordStartFrame + duration;
    const staticCollision = current.destinationTrack.clips.some((clip) => !targetIds.has(clip.id) && overlapsFrames(clip, current.input.destination.recordStartFrame, end));
    const peerCollision = prepared.some((peer, peerIndex) => peerIndex !== index && peer.input.destination.trackIndex === current.input.destination.trackIndex
      && overlapsFrames({ recordRange: { start: peer.input.destination.recordStartFrame, endExclusive: peer.input.destination.recordStartFrame + peer.input.target.recordEndFrame - peer.input.target.recordStartFrame } }, current.input.destination.recordStartFrame, end));
    const delta = current.input.destination.recordStartFrame - current.input.target.recordStartFrame;
    const linkedCollision = current.input.linkedAudio === "preserve" && current.changesRecordPosition && current.linkedFound.some((item) => item.track.clips.some((clip) => !linkedIds.has(clip.id) && overlapsFrames(clip, item.clip.recordRange.start + delta, item.clip.recordRange.endExclusive + delta)));
    if (staticCollision || peerCollision || linkedCollision) return { status: "failed", possibleMutation: "none", usage: "not_reserved", failure: failure("INVALID_REQUEST", "The jointly evaluated destination layout contains a collision.", context, "none", "not_reserved") };
  }
  let executionError = null;
  try {
    await resolveService.executeSdkTimelineItemMove({ moves: inputs }, {
      mutationGuard: inspected.mutationGuard,
      privateMoves: prepared.map(({ privateTarget, privateLinkedAudioTargets }) => ({ privateTarget, privateLinkedAudioTargets })),
      onAuthorization() {},
    });
  } catch (error) { executionError = error; }
  let after;
  let canonicalAfterRevision;
  try {
    ({ after, canonicalRevision: canonicalAfterRevision } = await readPostMutationTimeline(binding.projectId, binding.timelineId));
  } catch {
    return { status: "verification_failed", possibleMutation: "possible", usage: "unknown", failure: failure("VERIFICATION_FAILED", "Timeline readback was unavailable after the plural item move.", context, "possible") };
  }
  const excludedIds = new Set([...targetIds, ...linkedIds]);
  const protectedPreserved = digest(protectedState(before, excludedIds)) === digest(protectedState(after, excludedIds));
  const results = prepared.map(({ input, target, linkedFound, changesRecordPosition }) => {
    const delta = input.destination.recordStartFrame - input.target.recordStartFrame;
    const expectedTarget = findPost(after, target, "video", input.destination.trackIndex, input.destination.recordStartFrame, input.destination.recordStartFrame + input.target.recordEndFrame - input.target.recordStartFrame);
    const linkedDelta = input.linkedAudio === "preserve" ? delta : 0;
    const expectedLinked = linkedFound.map((item) => findPost(after, item, "audio", item.track.index, item.clip.recordRange.start + linkedDelta, item.clip.recordRange.endExclusive + linkedDelta));
    const valid = Boolean(expectedTarget) && expectedLinked.every(Boolean)
      && expectedTarget.clip.mediaPoolItemId === target.clip.mediaPoolItemId
      && digest(expectedTarget.clip.sourceRange) === digest(target.clip.sourceRange)
      && digest(expectedTarget.clip.linkedItemIds) === digest(target.clip.linkedItemIds)
      && expectedLinked.every((item, linkedIndex) => digest(item.clip.sourceRange) === digest(linkedFound[linkedIndex].clip.sourceRange) && digest(item.clip.linkedItemIds) === digest(linkedFound[linkedIndex].clip.linkedItemIds));
    const movedItems = valid ? [observation(target, expectedTarget, "video"), ...(input.linkedAudio === "preserve" && changesRecordPosition ? expectedLinked.map((item, linkedIndex) => observation(linkedFound[linkedIndex], item, "linked_audio")) : [])] : [];
    return { valid, result: valid ? { actionId: ACTION_ID, target: movedItems[0], linkedAudio: linkedFound.length > 0 ? (input.linkedAudio === "preserve" ? "preserved" : "excluded") : "not_linked", movedItems, timelineRevision: canonicalAfterRevision } : null };
  });
  const expected = executionError === null && protectedPreserved && results.every(({ valid }) => valid);
  const report = { outcome: expected ? "passed" : "failed", summary: expected ? "All requested placements and protected neighbors matched one live readback." : "Plural placement or protected-state readback did not match.", evidence: [evidence("readback", "Read back the complete timeline after plural execution.", after.tracks)], protectedStatePreserved: protectedPreserved };
  if (expected) return { status: "succeeded", possibleMutation: "confirmed", usage: "consumed", verification: report, result: { actionId: ACTION_ID, results: results.map(({ result }) => result), timelineRevision: canonicalAfterRevision } };
  const unchanged = digest(protectedState(before)) === digest(protectedState(after));
  if (unchanged) return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("OPERATION_FAILED", executionError?.message ?? "The plural timeline-item move made no verified change.", context, "none", "released") };
  return { status: "verification_failed", possibleMutation: "possible", usage: "consumed", postTimelineRevision: canonicalAfterRevision, failure: failure("VERIFICATION_FAILED", executionError?.message ?? "The plural timeline-item move produced unexpected state.", context, "possible", "consumed"), verification: report };
}

export function createSdkTimelineItemMoveActions({ liveInspectionService, resolveService }) {
  const hasStructuralRead = typeof liveInspectionService?.readTimelineStructure === "function";
  const readTimelineStructure = liveInspectionService?.readTimelineStructure?.bind(liveInspectionService)
    ?? liveInspectionService?.readWithMutationGuard?.bind(liveInspectionService);
  if (typeof readTimelineStructure !== "function"
    || (hasStructuralRead && typeof liveInspectionService?.readWorkflowBinding !== "function")) {
    throw new TypeError("Timeline-item moves require structural live inspection.");
  }
  if (typeof resolveService?.executeSdkTimelineItemMove !== "function") throw new TypeError("Timeline-item moves require the CutAgent CLI mutation boundary.");
  const readPostMutationTimeline = async (projectId, timelineId) => {
    if (!hasStructuralRead) {
      const inspected = await readTimelineStructure({ operation: "timeline.structure", projectId, timelineId }, { deadlineAtMs: Date.now() + 60_000 });
      return { after: inspected.value, canonicalRevision: inspected.value.revision };
    }
    const binding = await liveInspectionService.readWorkflowBinding({ operation: "timeline.snapshot", projectId, timelineId }, { deadlineAtMs: Date.now() + 60_000 });
    if (binding.projectId !== projectId || binding.timelineId !== timelineId) {
      throw new Error("Canonical post-move timeline binding changed during verification.");
    }
    const inspected = await readTimelineStructure({
      operation: "timeline.structure", projectId, timelineId, expectedRevision: binding.revision,
    }, { deadlineAtMs: Date.now() + 60_000 });
    return { after: inspected.value, canonicalRevision: binding.revision };
  };
  return {
    [ACTION_ID]: {
      inputSchema: sdkTimelineItemMoveInputSchema,
      resultSchema: sdkTimelineItemMoveResultSchema,
      idempotency: "required",
      async execute(context, rawInput) {
        const input = sdkTimelineItemMoveInputSchema.parse(rawInput);
        if ("moves" in input) return executePlural(context, input.moves, { readTimelineStructure, readPostMutationTimeline, resolveService });
        const inspectRequest = {
          operation: "timeline.structure",
          projectId: input.projectId,
          timelineId: input.timelineId,
          expectedRevision: input.timelineRevision,
        };
        const inspected = await readTimelineStructure(inspectRequest, { deadlineAtMs: Date.now() + 60_000 });
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
          return { status: "failed", possibleMutation: "none", usage: "not_reserved", failure: failure("INVALID_REQUEST", "Authoritative unlocked state is required for the source and destination video tracks.", context, "none", "not_reserved") };
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
          return { status: "failed", possibleMutation: "none", usage: "not_reserved", failure: failure("INVALID_REQUEST", "Authoritative unlocked state is required for every affected linked-audio track.", context, "none", "not_reserved") };
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
            return { status: "failed", possibleMutation: "none", usage: "not_reserved", failure: failure("INVALID_REQUEST", "The destination range now collides with another timeline item.", context, "none", "not_reserved") };
          }
        }
        let executionError = null;
        try { await resolveService.executeSdkTimelineItemMove(input, { mutationGuard: inspected.mutationGuard, privateTarget, privateLinkedAudioTargets, onAuthorization() {} }); }
        catch (error) { executionError = error; }

        let after;
        let canonicalAfterRevision;
        try {
          ({ after, canonicalRevision: canonicalAfterRevision } = await readPostMutationTimeline(input.projectId, input.timelineId));
        } catch {
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
          && executionError === null;
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
          const movedItems = [observation(target, expectedTarget, "video"), ...(input.linkedAudio === "preserve" && changesRecordPosition ? expectedLinked.map((item, index) => observation(linkedFound[index], item, "linked_audio")) : [])];
          return {
            status: "succeeded", possibleMutation: "confirmed", usage: "consumed", verification: report,
            result: {
              actionId: ACTION_ID,
              target: movedItems[0],
              linkedAudio: linkedFound.length > 0 ? (input.linkedAudio === "preserve" ? "preserved" : "excluded") : "not_linked",
              movedItems,
              timelineRevision: canonicalAfterRevision,
            },
          };
        }
        const unchanged = digest(protectedState(before)) === digest(protectedState(after));
        if (unchanged) {
          return {
            status: "failed", possibleMutation: "none", usage: "released",
            failure: failure("OPERATION_FAILED", executionError?.message ?? "The timeline-item move made no verified change.", context, "none", "released"),
            ...(executionError?.cli_error_code === "EDIT_MUTATION_RESTORED" ? { recovery: { state: "restored", summary: "The original timeline state was restored.", evidence: report.evidence, manualRecoveryRequired: false } } : {}),
          };
        }
        if (executionError?.cli_error_code === "EDIT_MUTATION_RECOVERY_FAILED") {
          return {
            status: "recovery_failed", possibleMutation: "partial", usage: "consumed",
            postTimelineRevision: canonicalAfterRevision,
            failure: failure("RECOVERY_FAILED", executionError.message, context, "partial", "consumed"), verification: report,
            recovery: { state: "failed", summary: "Automatic timeline-item recovery did not restore the expected state.", evidence: report.evidence, manualRecoveryRequired: true },
          };
        }
        return {
          status: "verification_failed", possibleMutation: "possible", usage: "consumed",
          postTimelineRevision: canonicalAfterRevision,
          failure: failure("VERIFICATION_FAILED", executionError?.message ?? "The timeline-item move produced an unexpected project state.", context, "possible", "consumed"),
          verification: report,
          recovery: { state: "manual_required", summary: "Inspect the current timeline before retrying this move.", evidence: report.evidence, manualRecoveryRequired: true },
        };
      },
    },
  };
}
