import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import {
  CUTAGENT_MUTATION_POLICY_CONTRACT_VERSION,
  sdkMutationImpactSchema,
  sdkSha256DigestSchema,
  sdkStableMutationTargetSchema,
} from "../../contracts/generated/sdk-mutation-policy.js";
import {
  PRIVATE_COMMAND_IMPACT,
  PRIVATE_IMPACT_REGISTRY_DIGEST,
} from "./private-impact-registry.generated.js";

function canonical(value) {
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new TypeError("Mutation impact numbers must be finite.");
    return Object.is(value, -0) ? 0 : value;
  }
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return Object.fromEntries(Object.keys(value).sort().map((key) => {
      if (value[key] === undefined) throw new TypeError("Mutation impact values cannot be undefined.");
      return [key, canonical(value[key])];
    }));
  }
  throw new TypeError("Mutation impact must be JSON-compatible.");
}

export function mutationPolicyDigest(value) {
  const normalized = canonical(value);
  return `sha256:${crypto.createHash("sha256").update(JSON.stringify(normalized), "utf8").digest("hex")}`;
}

function option(args, name, fallback = null) {
  const exactIndex = args.lastIndexOf(name);
  if (exactIndex >= 0) return args[exactIndex + 1] ?? fallback;
  const inline = [...args].reverse().find((item) => item.startsWith(`${name}=`));
  return inline ? inline.slice(name.length + 1) : fallback;
}

function optionValues(args, name) {
  const values = [];
  for (let index = 0; index < args.length; index += 1) {
    const item = args[index];
    if (item === name) { values.push(args[index + 1] ?? null); index += 1; }
    else if (item.startsWith(`${name}=`)) values.push(item.slice(name.length + 1));
  }
  return values;
}

function readPayload(args, cwd) {
  const inline = option(args, "--batch-json");
  if (inline) {
    return { value: JSON.parse(inline), digest: mutationPolicyDigest(inline) };
  }
  const fusionIndex = args.indexOf("fusion");
  const requested = option(args, "--batch") ?? option(args, "--input") ?? option(args, "--input-file")
    ?? (args.includes("--sdk-graph-runtime") && fusionIndex >= 0 && args[fusionIndex + 1] === "apply"
      ? args[fusionIndex + 2]
      : null);
  if (!requested) return null;
  if (typeof cwd !== "string" || !cwd) throw new Error("Referenced mutation payload requires an execution directory.");
  const resolved = path.resolve(cwd, requested);
  const bytes = fs.readFileSync(resolved);
  return {
    value: JSON.parse(bytes.toString("utf8")),
    digest: `sha256:${crypto.createHash("sha256").update(bytes).digest("hex")}`,
  };
}

function normalizeBladeCuts(args, payload) {
  const defaults = {
    at: option(args, "--at") ?? option(args, "--record-frame"),
    trackType: option(args, "--track-type", "all"),
    trackIndex: Number(option(args, "--track", "0")),
  };
  if (!payload) return [defaults];
  const raw = Array.isArray(payload) ? payload : Array.isArray(payload?.cuts) ? payload.cuts : null;
  if (!raw) throw new Error("Blade batch impact is incomplete.");
  return raw.map((entry) => ({
    at: entry?.at ?? entry?.record_frame ?? defaults.at,
    trackType: entry?.trackType ?? entry?.track_type ?? defaults.trackType,
    trackIndex: Number(entry?.trackIndex ?? entry?.track ?? defaults.trackIndex),
  }));
}

function reviewedBladeEffects({ args, payload, resolvedTargets, placementIntent }) {
  const cuts = normalizeBladeCuts(args, payload?.value);
  if (cuts.length < 1) throw new Error("Blade impact contains no cuts.");
  return cuts.map((cut, index) => {
    const trackType = ["video", "audio"].includes(cut.trackType) ? cut.trackType : null;
    const matchingTargets = resolvedTargets.filter((target) => (
      target.trackType === trackType
      && (cut.trackIndex === 0 || target.trackIndex === cut.trackIndex)
    ));
    return {
      operation: "edit.blade",
      kind: "blade",
      trackTypes: trackType ? [trackType] : ["video", "audio"],
      targets: matchingTargets,
      placementIntent,
      broad: cut.trackType === "all" || cut.trackIndex === 0,
      ambiguous: cut.at === null || cut.at === undefined || matchingTargets.length < 1,
      complete: Boolean(trackType && cut.at !== null && cut.at !== undefined && matchingTargets.length >= 1),
      _index: index,
    };
  }).map(({ _index: _discard, ...effect }) => effect);
}

export function privateCommandImpact(commandId) {
  return PRIVATE_COMMAND_IMPACT.get(commandId) ?? null;
}

const REVIEWED_SDK_EDIT_PREVIEW_ACTIONS = Object.freeze({
  "edit.insert": "insert",
  "edit.overwrite": "overwrite",
  "edit.trim": "trim",
});

export function isReviewedSdkEditPreview({ args, commandId, carrier, policyContext }) {
  const action = REVIEWED_SDK_EDIT_PREVIEW_ACTIONS[commandId];
  if (!action || carrier !== "sdk" || policyContext?.semanticReadOnlyPreview !== "timeline.edit.v1") return false;
  if (!Array.isArray(args) || args.length < 4 || args[0] !== "-j" || args[1] !== "edit" || args[2] !== action) return false;
  return args.at(-1) === "--dry-run" && args.filter((value) => value === "--dry-run").length === 1;
}

/**
 * Proprietary semantic lowering. Unknown commands and every mutation without a
 * reviewed lowerer remain unknown/incomplete and therefore fail closed.
 */
export function lowerCutAgentCliMutationImpact({
  args,
  commandId,
  carrier = "cli",
  cwd = null,
  policyContext = null,
}) {
  const registry = privateCommandImpact(commandId);
  if (registry?.operationClass === "read") return Object.freeze({ status: "read", commandId });

  const context = policyContext && typeof policyContext === "object" ? policyContext : {};
  const referencedPayload = (() => {
    try { return readPayload(args, cwd); } catch { return { invalid: true }; }
  })();
  const resolvedTargets = Array.isArray(context.resolvedTargets)
    ? context.resolvedTargets.map((target) => sdkStableMutationTargetSchema.parse(target))
    : [];
  let effects = [];
  let status = registry ? "mutation" : "unknown";
  let complete = false;
  let ambiguous = true;
  let broad = false;
  let minimumBinding = "project+timeline";
  let minimumEvidence = ["readback", "structural"];

  if (["edit.blade", "edit.split"].includes(commandId) && !referencedPayload?.invalid) {
    try {
      effects = reviewedBladeEffects({
        args,
        payload: referencedPayload,
        resolvedTargets,
        placementIntent: context.placementIntent === "marker" ? "marker" : "explicit",
      });
      complete = effects.every((effect) => effect.complete);
      ambiguous = effects.some((effect) => effect.ambiguous);
      broad = effects.some((effect) => effect.broad);
    } catch {
      effects = [{
        operation: "edit.blade",
        kind: "unknown",
        trackTypes: [],
        targets: [],
        placementIntent: "unknown",
        broad: false,
        ambiguous: true,
        complete: false,
      }];
    }
  } else if (commandId === "project.create") {
    minimumBinding = "account/project-library";
    const target = context.projectLibraryRevision && context.projectLibraryId ? [{
      kind: "project_library", stableId: context.projectLibraryId, revision: context.projectLibraryRevision,
    }] : [];
    effects = [{ operation: commandId, kind: "create", trackTypes: [], targets: target,
      placementIntent: "explicit", broad: false, ambiguous: target.length !== 1, complete: target.length === 1 }];
    complete = target.length === 1; ambiguous = !complete;
  } else if (commandId === "timeline.create") {
    minimumBinding = "project";
    const target = context.projectId && context.projectRevision ? [{
      kind: "project", stableId: context.projectId, revision: context.projectRevision,
    }] : [];
    effects = [{ operation: commandId, kind: "create", trackTypes: [], targets: target,
      placementIntent: "explicit", broad: false, ambiguous: target.length !== 1, complete: target.length === 1 }];
    complete = target.length === 1; ambiguous = !complete;
  } else if (["version.create", "version.restore"].includes(commandId)
    && context.workflowCheckpointAuthority === "sdk_workflow_v1") {
    const guardedRestore = commandId !== "version.restore" || (
      /^sha256:[a-f0-9]{64}$/.test(context.expectedCurrentStateHash ?? "")
      && context.projectRevision === context.expectedCurrentStateHash
    );
    const target = context.timelineId && context.timelineRevision ? [
      ...(commandId === "version.restore" && context.projectId && context.expectedCurrentStateHash ? [{
        kind: "project", stableId: context.projectId, revision: context.expectedCurrentStateHash,
      }] : []),
      { kind: "timeline", stableId: context.timelineId, revision: context.timelineRevision },
    ] : [];
    const expectedTargets = commandId === "version.restore" ? 2 : 1;
    effects = [{ operation: commandId, kind: commandId.endsWith(".create") ? "create" : "update",
      trackTypes: [], targets: target, placementIntent: "explicit", broad: false,
      ambiguous: target.length !== expectedTargets, complete: target.length === expectedTargets && guardedRestore }];
    complete = target.length === expectedTargets && guardedRestore; ambiguous = target.length !== expectedTargets;
  } else if (commandId === "media.import") {
    minimumBinding = "project";
    const target = context.projectId && context.projectRevision ? [{
      kind: "project", stableId: context.projectId, revision: context.projectRevision,
    }] : [];
    effects = [{ operation: commandId, kind: "create", trackTypes: [], targets: target,
      placementIntent: "explicit", broad: false, ambiguous: target.length !== 1, complete: target.length === 1 }];
    complete = target.length === 1; ambiguous = !complete;
  } else if (["multicam.create", "multicam.timeline_create"].includes(commandId)
    && context.semanticMulticamAction === "create") {
    minimumBinding = "project";
    minimumEvidence = ["readback"];
    const targets = resolvedTargets.filter((target) => target.kind === "media");
    const exact = targets.length === resolvedTargets.length
      && targets.length >= 2
      && new Set(targets.map((target) => target.stableId)).size === targets.length;
    effects = [{ operation: "multicam.create", kind: "create", trackTypes: [], targets,
      placementIntent: "explicit", broad: false, ambiguous: !exact, complete: exact }];
    complete = exact; ambiguous = !exact;
  } else if (["multicam.switch", "multicam.flatten"].includes(commandId)
    && context.semanticMulticamAction === commandId.slice("multicam.".length)) {
    const targets = resolvedTargets.filter((target) => target.kind === "timeline");
    const trackTypes = Array.isArray(context.affectedTrackTypes)
      ? [...new Set(context.affectedTrackTypes.filter((value) => ["video", "audio"].includes(value)))] : [];
    const exact = targets.length === 1 && targets.length === resolvedTargets.length && trackTypes.length > 0;
    effects = [{ operation: commandId, kind: "update", trackTypes, targets,
      placementIntent: "explicit", broad: false, ambiguous: !exact, complete: exact }];
    complete = exact; ambiguous = !exact;
  } else if (["storage.import", "storage.import_sequence", "storage.import_subclip", "storage.matte.add", "storage.matte.timeline_add"].includes(commandId)) {
    minimumBinding = "project";
    const targets = resolvedTargets.filter((target) => target.kind === "project" || (commandId.startsWith("storage.matte.") && target.kind === "media"));
    const projectTargets = targets.filter((target) => target.kind === "project");
    const exact = targets.length === resolvedTargets.length
      && projectTargets.length === 1
      && (!commandId.startsWith("storage.matte.") || (targets.length === 2 && targets.filter((target) => target.kind === "media").length === 1));
    effects = [{ operation: commandId, kind: commandId.startsWith("storage.matte.") ? "update" : "create", trackTypes: [], targets,
      placementIntent: "explicit", broad: false, ambiguous: !exact, complete: exact }];
    complete = exact; ambiguous = !exact;
  } else if (commandId === "storage.reveal") {
    minimumBinding = "account/project-library";
    const targets = resolvedTargets.filter((target) => target.kind === "project_library");
    const exact = targets.length === 1 && resolvedTargets.length === 1;
    effects = [{ operation: commandId, kind: "update", trackTypes: [], targets,
      placementIntent: "explicit", broad: false, ambiguous: !exact, complete: exact }];
    complete = exact; ambiguous = !complete;
  } else if (["timeline.marker.add", "timeline.marker.update", "timeline.marker.delete"].includes(commandId)) {
    const kind = commandId.endsWith(".add") ? "create" : commandId.endsWith(".update") ? "update" : "delete";
    effects = [{ operation: commandId, kind, trackTypes: [], targets: resolvedTargets,
      placementIntent: "marker", broad: false, ambiguous: resolvedTargets.length !== 1,
      complete: resolvedTargets.length === 1 }];
    complete = resolvedTargets.length === 1; ambiguous = !complete;
  } else if (commandId === "timeline.items.move") {
    const targets = resolvedTargets.filter((target) => target.kind === "clip" || target.kind === "track");
    const videoClips = targets.filter((target) => target.kind === "clip" && target.trackType === "video");
    const videoTracks = targets.filter((target) => target.kind === "track" && target.trackType === "video");
    const trackTypes = [...new Set(targets.map((target) => target.trackType).filter(Boolean))];
    const exact = targets.length === resolvedTargets.length && videoClips.length === 1 && videoTracks.length >= 1;
    effects = [{ operation: commandId, kind: "update", trackTypes, targets,
      placementIntent: "explicit", broad: false, ambiguous: !exact, complete: exact }];
    complete = exact; ambiguous = !exact;
  } else if (commandId === "timeline.items.delete" && context.semanticOperation === "clip_remove") {
    const targets = resolvedTargets.filter((target) => ["timeline", "clip", "track"].includes(target.kind));
    const timelines = targets.filter((target) => target.kind === "timeline");
    const clips = targets.filter((target) => target.kind === "clip");
    const tracks = targets.filter((target) => target.kind === "track");
    const validCoordinate = (target) => ["video", "audio"].includes(target.trackType)
      && Number.isInteger(target.trackIndex) && target.trackIndex >= 1;
    const coordinate = (target) => `${target.trackType}:${target.trackIndex}`;
    const selectorItemIds = Array.isArray(context.selectorItemIds) ? context.selectorItemIds : [];
    const transitionItemIds = Array.isArray(context.expectedLinkTransitionIds) ? context.expectedLinkTransitionIds : [];
    const selectorClips = clips.filter((clip) => selectorItemIds.includes(clip.stableId));
    const transitionClips = clips.filter((clip) => transitionItemIds.includes(clip.stableId));
    const selectorClipCoordinates = new Set(selectorClips.map(coordinate));
    const trackCoordinates = new Set(tracks.map(coordinate));
    const trackTypeArgs = optionValues(args, "--track-type");
    const trackIndexArgs = optionValues(args, "--track");
    const startArgs = optionValues(args, "--start-frame");
    const endArgs = optionValues(args, "--end-frame");
    const matchArgs = optionValues(args, "--match");
    const selectorTrackIndex = Number(trackIndexArgs[0]);
    const selectorCoordinate = `${trackTypeArgs[0]}:${selectorTrackIndex}`;
    const selectorRange = context.selectorRange;
    const exactSelector = trackTypeArgs.length === 1 && ["video", "audio"].includes(trackTypeArgs[0])
      && trackIndexArgs.length === 1 && Number.isInteger(selectorTrackIndex) && selectorTrackIndex >= 1
      && startArgs.length === 1 && startArgs[0] === `${selectorRange?.start}f`
      && endArgs.length === 1 && endArgs[0] === `${selectorRange?.endExclusive}f`
      && matchArgs.length === 1 && matchArgs[0] === "contained"
      && selectorClipCoordinates.size === 1 && selectorClipCoordinates.has(selectorCoordinate)
      && trackCoordinates.size === 1 && trackCoordinates.has(selectorCoordinate);
    const trackTypes = [...new Set([...clips, ...tracks].map((target) => target.trackType).filter(Boolean))];
    const exact = targets.length === resolvedTargets.length && timelines.length === 1 && selectorClips.length >= 1 && tracks.length >= 1
      && clips.every(validCoordinate) && tracks.every(validCoordinate)
      && new Set(targets.map((target) => `${target.kind}:${target.stableId}`)).size === targets.length
      && new Set([...selectorItemIds, ...transitionItemIds]).size === selectorItemIds.length + transitionItemIds.length
      && selectorClips.length === selectorItemIds.length && transitionClips.length === transitionItemIds.length
      && clips.length === selectorClips.length + transitionClips.length
      && selectorClipCoordinates.size === trackCoordinates.size && [...selectorClipCoordinates].every((value) => trackCoordinates.has(value))
      && trackCoordinates.size === tracks.length && exactSelector;
    const selectorBroad = trackTypeArgs.length !== 1 || trackTypeArgs[0] === "all" || trackIndexArgs.length !== 1
      || selectorTrackIndex === 0 || trackCoordinates.size !== 1;
    effects = [{ operation: commandId, kind: "delete", trackTypes, targets,
      placementIntent: "explicit", broad: selectorBroad, ambiguous: !exact, complete: exact }];
    complete = exact; ambiguous = !exact;
  } else if (["clip.speed", "clip.speed_ramp", "clip.freeze", "clip.reverse"].includes(commandId)
    && context.semanticRetimeAction === commandId) {
    const targets = resolvedTargets.filter((target) => target.kind === "clip" || target.kind === "track");
    const clips = targets.filter((target) => target.kind === "clip");
    const tracks = targets.filter((target) => target.kind === "track");
    const videoClips = clips.filter((target) => target.trackType === "video");
    const expectedVideoCount = commandId === "clip.speed_ramp" ? 2 : 1;
    const trackTypes = [...new Set(targets.map((target) => target.trackType).filter(Boolean))];
    const exact = targets.length === resolvedTargets.length
      && videoClips.length === expectedVideoCount
      && clips.every((clip) => tracks.some((track) => track.trackType === clip.trackType && track.trackIndex === clip.trackIndex))
      && context.closedComposition === true
      && context.executableStableTargetPrecondition === true;
    effects = [{ operation: commandId, kind: "update", trackTypes, targets,
      placementIntent: "explicit", broad: false, ambiguous: !exact, complete: exact }];
    complete = exact; ambiguous = !exact;
  } else if (["timeline.subtitle.insert", "timeline.auto_caption"].includes(commandId)) {
    const targets = resolvedTargets.filter((target) => target.kind === "track" || target.kind === "timeline");
    effects = [{ operation: commandId, kind: "create", trackTypes: ["subtitle"], targets,
      placementIntent: "explicit", broad: false, ambiguous: false, complete: targets.length > 0 }];
    complete = targets.length > 0; ambiguous = false;
  } else if (commandId === "transcript.create") {
    const targets = resolvedTargets.filter((target) => target.kind === "timeline");
    const exact = targets.length === 1 && targets.length === resolvedTargets.length;
    effects = [{ operation: commandId, kind: "update", trackTypes: [], targets,
      placementIntent: "explicit", broad: false, ambiguous: !exact, complete: exact }];
    complete = exact; ambiguous = !exact;
  } else if (commandId === "text.insert_captions") {
    const targets = resolvedTargets.filter((target) => target.kind === "track" && target.trackType === "video");
    effects = [{ operation: commandId, kind: "create", trackTypes: ["video"], targets,
      placementIntent: "explicit", broad: false, ambiguous: targets.length !== 1, complete: targets.length === 1 }];
    complete = targets.length === 1; ambiguous = !complete;
  } else if ([
    "color.page.primary_set",
    "color.page.node_add",
    "color.node.label_set",
    "color.grade_apply",
    "color.page.resolvefx_add",
  ].includes(commandId)) {
    const target = resolvedTargets.filter((candidate) => candidate.kind === "clip" && candidate.trackType === "video");
    effects = [{ operation: commandId, kind: "update", trackTypes: ["video"], targets: target,
      placementIntent: "explicit", broad: false, ambiguous: target.length !== 1,
       complete: target.length === 1 }];
    complete = target.length === 1; ambiguous = !complete;
  } else if (["edit.insert", "edit.overwrite", "edit.trim"].includes(commandId)) {
    const expectedAction = commandId.slice("edit.".length);
    const trackTypes = Array.isArray(context.affectedTrackTypes)
      ? [...new Set(context.affectedTrackTypes.filter((value) => ["video", "audio"].includes(value)))] : [];
    const targets = resolvedTargets.filter((target) => target.kind === "timeline" || target.kind === "clip");
    const actionMatches = context.semanticEditAction === expectedAction;
    complete = actionMatches && targets.length > 0 && trackTypes.length > 0;
    ambiguous = !complete;
    effects = [{ operation: commandId, kind: commandId === "edit.insert" ? "create" : "update", trackTypes, targets,
      placementIntent: "explicit", broad: false, ambiguous, complete }];
  } else if (commandId === "audio.voice_place"
    && context.semanticOperation === "audio.voice_place") {
    const targets = resolvedTargets.filter((target) => target.kind === "track" && target.trackType === "audio");
    effects = [{ operation: "audio.voice_place", kind: "create", trackTypes: ["audio"], targets,
      placementIntent: "explicit", broad: false, ambiguous: targets.length !== 1, complete: targets.length === 1 }];
    complete = targets.length === 1; ambiguous = !complete;
  } else if (commandId === "fusion.apply" && args.includes("--sdk-graph-runtime") && !referencedPayload?.invalid) {
    const targetKinds = new Set(resolvedTargets.map((target) => target.kind));
    const target = resolvedTargets.length === 2
      && targetKinds.has("clip")
      && targetKinds.has("fusion_composition")
      ? resolvedTargets
      : [];
    effects = [{
      operation: "fusion.apply",
      kind: "update",
      trackTypes: ["video"],
      targets: target,
      placementIntent: "explicit",
      broad: false,
      ambiguous: target.length !== 2,
      complete: target.length === 2,
    }];
    complete = target.length === 2;
    ambiguous = !complete;
  } else if (["render.mode.set", "render.settings_set", "render.add", "render.start", "render.cancel", "render.delete", "render.export_file"].includes(commandId)) {
    const targets = resolvedTargets.filter((target) => target.kind === "timeline");
    const operation = context.semanticOperation === "render.export" ? "render.export" : commandId;
    effects = [{ operation, kind: commandId === "render.add" ? "create" : "update", trackTypes: [], targets,
      placementIntent: "explicit", broad: false, ambiguous: targets.length !== 1, complete: targets.length === 1 }];
    complete = targets.length === 1; ambiguous = !complete;
  }

  const impact = {
    contractVersion: CUTAGENT_MUTATION_POLICY_CONTRACT_VERSION,
    carrier,
    status,
    minimumBinding,
    registryDigest: PRIVATE_IMPACT_REGISTRY_DIGEST,
    canonicalRequestDigest: mutationPolicyDigest({ commandId, args }),
    referencedPayloadDigests: commandId === "version.restore" && context.workflowCheckpointAuthority === "sdk_workflow_v1"
      && /^sha256:[a-f0-9]{64}$/.test(context.expectedCurrentStateHash ?? "")
      ? [sdkSha256DigestSchema.parse(context.expectedCurrentStateHash)]
      : commandId.startsWith("storage.") && Array.isArray(context.referencedPayloadDigests)
        ? context.referencedPayloadDigests.slice(0, 64).map((value) => sdkSha256DigestSchema.parse(value))
        : referencedPayload?.digest ? [sdkSha256DigestSchema.parse(referencedPayload.digest)] : [],
    requestId: context.requestId,
    operationId: context.operationId,
    executionId: context.executionId,
    scopeId: context.scopeId,
    scopeRevision: context.scopeRevision,
    projectLibraryId: context.projectLibraryId,
    ...(context.projectId ? { projectId: context.projectId } : {}),
    ...(context.timelineId ? { timelineId: context.timelineId } : {}),
    ...(context.projectRevision ? { projectRevision: context.projectRevision } : {}),
    ...(context.timelineRevision ? { timelineRevision: context.timelineRevision } : {}),
    effects,
    closedComposition: context.closedComposition === true,
    complete,
    ambiguous,
    broad,
    executableStableTargetPrecondition: context.executableStableTargetPrecondition === true,
    verificationPolicy: {
      minimumEvidence,
      requireProtectedStatePreserved: true,
      protectedTargetEvidence: "every_declared_target",
    },
  };
  const parsed = sdkMutationImpactSchema.safeParse(impact);
  if (parsed.success) return parsed.data;
  return Object.freeze({
    status: "unknown",
    commandId,
    reason: "malformed_impact",
    diagnostics: parsed.error.issues.map((issue) => issue.path.join(".")),
  });
}

export { PRIVATE_IMPACT_REGISTRY_DIGEST };
