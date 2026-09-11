import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import Ajv2020 from "ajv/dist/2020.js";
import {SDK_FUSION_TIMELINE_PREPARED_INPUTS} from "../contracts/sdk-fusion-timeline-inputs.generated.js";

// The authoritative action contracts use conditional `required` constraints whose
// properties are declared by the enclosing object schema. Keep strict validation,
// but do not reject those valid schemas while compiling them.
const ajv = new Ajv2020({allErrors: true, strict: true, strictRequired: false});

export const FUSION_PREPARED_ACTION_IDS = Object.freeze([
  "cutagent.action.dctl.apply", "cutagent.action.fusion.comp.current", "cutagent.action.fusion.comp.delete",
  "cutagent.action.fusion.comp.range", "cutagent.action.fusion.comp.rename", "cutagent.action.fusion.effect.blur",
  "cutagent.action.fusion.effect.color_correct", "cutagent.action.fusion.effect.glow", "cutagent.action.fusion.effect.sharpen",
  "cutagent.action.fusion.effect.transform", "cutagent.action.fusion.generate", "cutagent.action.fusion.image.batch", "cutagent.action.fusion.image.set",
  "cutagent.action.fusion.insert_setting", "cutagent.action.fusion.insert_settings.batch", "cutagent.action.fusion.keyer.chroma", "cutagent.action.fusion.keyframe.add",
  "cutagent.action.fusion.keyframe.clear", "cutagent.action.fusion.keyframe.delete", "cutagent.action.fusion.keyframe.list",
  "cutagent.action.fusion.keyframe.set", "cutagent.action.fusion.mask.ellipse", "cutagent.action.fusion.mask.polygon",
  "cutagent.action.fusion.mask.rectangle", "cutagent.action.fusion.nested_text.batch", "cutagent.action.fusion.nested_text.update", "cutagent.action.fusion.node.add",
  "cutagent.action.fusion.node.connect", "cutagent.action.fusion.node.delete", "cutagent.action.fusion.node.disconnect",
  "cutagent.action.fusion.setting.center_to_polypath", "cutagent.action.fusion.setting.inspect",
  "cutagent.action.fusion.setting.polypath_to_center", "cutagent.action.fusion.setting.summary",
  "cutagent.action.fusion.setting.validate", "cutagent.action.fusion.template.apply",
  "cutagent.action.fusion.template.assets.add", "cutagent.action.fusion.template.assets.list",
  "cutagent.action.fusion.template.dir", "cutagent.action.fusion.template.icon.set",
  "cutagent.action.fusion.template.install", "cutagent.action.fusion.template.package_drfx",
  "cutagent.action.fusion.template.scaffold", "cutagent.action.fusion.template.show",
  "cutagent.action.fusion.template.uninstall", "cutagent.action.fusion.template.validate",
  "cutagent.action.fusion.text.batch", "cutagent.action.fusion.text.set", "cutagent.action.fusion.tool.active", "cutagent.action.fusion.tool.add",
  "cutagent.action.fusion.tool.attrs", "cutagent.action.fusion.tool.connect", "cutagent.action.fusion.tool.delete",
  "cutagent.action.fusion.tool.disconnect", "cutagent.action.fusion.tool.get", "cutagent.action.fusion.tool.inputs",
  "cutagent.action.fusion.tool.list", "cutagent.action.fusion.tool.registry", "cutagent.action.fusion.tool.outputs", "cutagent.action.fusion.tool.set",
  "cutagent.action.fusion.tracker.add", "cutagent.action.lut.convert", "cutagent.action.lut.generate.identity",
  "cutagent.action.lut.inspect", "cutagent.action.lut.install", "cutagent.action.lut.list",
  "cutagent.action.lut.remove", "cutagent.action.lut.validate", "cutagent.action.lut_refresh",
]);

export const FUSION_DELEGATED_ACTION_IDS = Object.freeze(["cutagent.action.fusion.apply"]);
export const FUSION_UNAVAILABLE_ACTION_IDS = Object.freeze([
  "cutagent.action.fusion.comp.play", "cutagent.action.fusion.comp.stop", "cutagent.action.fusion.tool.copy",
  "cutagent.action.fusion.tool.paste", "cutagent.action.fusion.macro.apply", "cutagent.action.fusion.comp.render",
]);

export const TIMELINE_VERSION_PREPARED_ACTION_IDS = Object.freeze([
  "cutagent.action.timeline.clip_color.batch", "cutagent.action.timeline.clip_markers.list", "cutagent.action.timeline.current_item",
  "cutagent.action.timeline.create", "cutagent.action.timeline.delete", "cutagent.action.timeline.dolby.analyze",
  "cutagent.action.timeline.duration", "cutagent.action.timeline.info", "cutagent.action.timeline.item_at",
  "cutagent.action.timeline.duplicate", "cutagent.action.timeline.fairlight_preset.apply", "cutagent.action.timeline.import",
  "cutagent.action.timeline.list", "cutagent.action.timeline.mark.get", "cutagent.action.timeline.marker.list",
  "cutagent.action.timeline.mark.clear", "cutagent.action.timeline.mark.set", "cutagent.action.timeline.playhead.set",
  "cutagent.action.timeline.media_pool_item", "cutagent.action.timeline.node_graph.inspect",
  "cutagent.action.timeline.playhead.get", "cutagent.action.timeline.settings", "cutagent.action.timeline.output_blanking.get", "cutagent.action.timeline.summarize",
  "cutagent.action.timeline.rename", "cutagent.action.timeline.set_start_tc", "cutagent.action.timeline.settings_set", "cutagent.action.timeline.output_blanking.set",
  "cutagent.action.timeline.start_tc", "cutagent.action.timeline.switch",
  "cutagent.action.timeline.track.items", "cutagent.action.timeline.track.list",
  "cutagent.action.timeline.track.subtype", "cutagent.action.timeline.voice_isolation.get",
  "cutagent.action.timeline.export", "cutagent.action.timeline.inspect_export", "cutagent.action.timeline.frame_export",
  "cutagent.action.timeline.grab_still", "cutagent.action.timeline.preview_export",
  "cutagent.action.timeline.still.grab_all", "cutagent.action.timeline.thumbnail",
  "cutagent.action.version.create", "cutagent.action.version.prune", "cutagent.action.version.restore",
  "cutagent.action.timeline.compound_create", "cutagent.action.timeline.fusion_clip.create",
  "cutagent.action.timeline.fusion_composition.insert", "cutagent.action.timeline.import_into",
  "cutagent.action.timeline.insert_generator", "cutagent.action.timeline.insert_title",
  "cutagent.action.timeline.items.set_duration", "cutagent.action.timeline.layer.ensure_media",
  "cutagent.action.timeline.sync_clips",
  "cutagent.action.timeline.track.add", "cutagent.action.timeline.track.delete",
  "cutagent.action.timeline.track.disable", "cutagent.action.timeline.track.enable",
  "cutagent.action.timeline.track.lock", "cutagent.action.timeline.track.rename",
  "cutagent.action.timeline.track.unlock", "cutagent.action.timeline.voice_isolation.set",
]);

export const TIMELINE_VERSION_DELEGATED_ACTION_IDS = Object.freeze(["cutagent.action.timeline.items.delete"]);
export const TIMELINE_ARTIFACT_PREPARED_ACTION_IDS = Object.freeze([
  "cutagent.action.timeline.export", "cutagent.action.timeline.inspect_export", "cutagent.action.timeline.frame_export",
  "cutagent.action.timeline.grab_still", "cutagent.action.timeline.preview_export",
  "cutagent.action.timeline.still.grab_all", "cutagent.action.timeline.thumbnail",
]);
export const TIMELINE_VERSION_UNAVAILABLE_ACTION_IDS = Object.freeze([
  "cutagent.action.timeline.stereo_convert",
]);
export const TIMELINE_TOPOLOGY_ACTION_IDS = Object.freeze([
  "cutagent.action.timeline.compound_create", "cutagent.action.timeline.fusion_clip.create",
  "cutagent.action.timeline.fusion_composition.insert", "cutagent.action.timeline.import_into",
  "cutagent.action.timeline.insert_generator", "cutagent.action.timeline.insert_title",
  "cutagent.action.timeline.items.set_duration", "cutagent.action.timeline.layer.ensure_media",
  "cutagent.action.timeline.sync_clips",
  "cutagent.action.timeline.track.add", "cutagent.action.timeline.track.delete",
  "cutagent.action.timeline.track.disable", "cutagent.action.timeline.track.enable",
  "cutagent.action.timeline.track.lock", "cutagent.action.timeline.track.rename",
  "cutagent.action.timeline.track.unlock", "cutagent.action.timeline.voice_isolation.set",
]);
const TIMELINE_TOPOLOGY_ACTION_ID_SET = new Set(TIMELINE_TOPOLOGY_ACTION_IDS);

const ARTIFACT_FIELDS = Object.freeze([
  "artifactId", "assetArtifactId", "dctlArtifactId", "destinationArtifactId", "directoryArtifactId",
  "imageArtifactId", "installedArtifactId", "pngArtifactId", "settingArtifactId", "sourceArtifactId",
  "templateArtifactId",
]);
const ARTIFACT_INPUT_FIELDS = new Set(ARTIFACT_FIELDS);
const UNBOUND_FILESYSTEM_ACTION_IDS = new Set([
  "cutagent.action.fusion.template.apply",
  "cutagent.action.fusion.template.show",
  "cutagent.action.fusion.template.uninstall",
  "cutagent.action.lut.list",
]);
export const FUSION_ARTIFACT_BACKED_ACTION_IDS = Object.freeze(
  FUSION_PREPARED_ACTION_IDS.filter((actionId) => UNBOUND_FILESYSTEM_ACTION_IDS.has(actionId)
    || schemaContainsArtifactField(SDK_FUSION_TIMELINE_PREPARED_INPUTS[actionId])),
);
const DESTINATION_FIELDS = new Set(["destinationArtifactId"]);
const DIRECTORY_FIELDS = new Set(["directoryArtifactId"]);
const VERSION_ACTIONS = new Set(["cutagent.action.version.create", "cutagent.action.version.prune", "cutagent.action.version.restore"]);
const TIMELINE_ORDINARY_MUTATION_ACTIONS = new Set([
  "cutagent.action.timeline.clip_color.batch", "cutagent.action.timeline.create", "cutagent.action.timeline.delete", "cutagent.action.timeline.dolby.analyze",
  "cutagent.action.timeline.duplicate", "cutagent.action.timeline.fairlight_preset.apply", "cutagent.action.timeline.import",
  "cutagent.action.timeline.mark.clear", "cutagent.action.timeline.mark.set", "cutagent.action.timeline.playhead.set",
  "cutagent.action.timeline.rename", "cutagent.action.timeline.set_start_tc", "cutagent.action.timeline.settings_set", "cutagent.action.timeline.output_blanking.set",
  "cutagent.action.timeline.start_tc", "cutagent.action.timeline.switch",
]);
const TIMELINE_PROJECT_MUTATION_ACTIONS = new Set([
  "cutagent.action.timeline.create", "cutagent.action.timeline.delete", "cutagent.action.timeline.duplicate",
  "cutagent.action.timeline.import", "cutagent.action.timeline.rename", "cutagent.action.timeline.switch",
]);
const OFFLINE_ACTIONS = new Set([
  "cutagent.action.fusion.setting.center_to_polypath", "cutagent.action.fusion.setting.polypath_to_center",
]);
const READ_ACTIONS = new Set([
  "cutagent.action.fusion.comp.current", "cutagent.action.fusion.keyframe.list",
  "cutagent.action.fusion.setting.center_to_polypath", "cutagent.action.fusion.setting.inspect",
  "cutagent.action.fusion.setting.polypath_to_center", "cutagent.action.fusion.setting.summary",
  "cutagent.action.fusion.template.assets.list", "cutagent.action.fusion.template.show",
  "cutagent.action.fusion.template.validate", "cutagent.action.fusion.tool.attrs",
  "cutagent.action.fusion.tool.get", "cutagent.action.fusion.tool.inputs", "cutagent.action.fusion.tool.list", "cutagent.action.fusion.tool.registry",
  "cutagent.action.fusion.tool.outputs", "cutagent.action.lut.convert", "cutagent.action.lut.inspect",
  "cutagent.action.lut.list", "cutagent.action.lut.validate",
  ...TIMELINE_VERSION_PREPARED_ACTION_IDS.filter((id) => !VERSION_ACTIONS.has(id)
    && !TIMELINE_TOPOLOGY_ACTION_ID_SET.has(id)
    && !TIMELINE_ORDINARY_MUTATION_ACTIONS.has(id)
    && !TIMELINE_ARTIFACT_PREPARED_ACTION_IDS.includes(id)),
]);

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === "object") return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  return value;
}

function sha256(value) {
  return crypto.createHash("sha256").update(JSON.stringify(canonical(value)), "utf8").digest("hex");
}

function inputSchema(actionId) {
  const schema = SDK_FUSION_TIMELINE_PREPARED_INPUTS[actionId];
  if (!schema) throw new Error(`Prepared-action input schema is unavailable: ${actionId}`);
  const validate = ajv.compile(schema);
  return Object.freeze({
    parse(value) {
      if (!validate(value)) {
        const error = new TypeError(`Prepared-action input violated its exact schema: ${actionId}`);
        error.validationErrors = structuredClone(validate.errors ?? []);
        throw error;
      }
      if (actionId === "cutagent.action.timeline.dolby.analyze"
        && (!Array.isArray(value.timelineItemIds) || value.timelineItemIds.length === 0 || value.enableProjectControls !== false)) {
        throw new TypeError("Dolby analysis requires explicit Timeline item identities and disabled project-control mutation.");
      }
      return structuredClone(value);
    },
  });
}

function targetBinding(project, timeline = null) {
  const timelineId = timeline?.timeline?.id ?? timeline?.id;
  const targetIds = timeline ? [project.id, timelineId] : [project.id];
  const targets = timeline
    ? {[project.id]: project.revision, [timelineId]: timeline.revision}
    : {[project.id]: project.revision};
  return {
    identities: {
      projectLibraryId: project.projectLibraryId,
      projectId: project.id,
      timelineId: timelineId ?? null,
      targetIds,
    },
    revisions: {
      projectLibrary: project.projectLibraryRevision,
      project: project.revision,
      timeline: timeline?.revision ?? null,
      targets,
    },
  };
}

async function liveProject(liveInspectionService, expectedProjectId = null) {
  const context = await liveProjectLibrary(liveInspectionService);
  if (!context.projectId || (expectedProjectId && context.projectId !== expectedProjectId)) {
    throw new Error("Prepared action lost its exact live project identity.");
  }
  return Object.freeze({
    id: context.projectId,
    revision: context.projectRevision,
    projectLibraryId: context.projectLibraryId,
    projectLibraryRevision: context.projectLibraryRevision,
    nativeProjectId: context.nativeProjectId ?? null,
    currentTimelineId: context.currentTimelineId ?? null,
    nativeTimelineId: context.nativeTimelineId ?? null,
  });
}

async function liveProjectLibrary(liveInspectionService) {
  const inspected = await liveInspectionService.readWithMutationGuard({operation: "project.context"});
  const value = inspected?.value;
  const identity = inspected?.privateExecutionIdentity;
  const projectId = value?.project?.id;
  const projectRevision = value?.projectRevision?.revision;
  const projectLibraryRevision = inspected?.mutationGuard;
  if (!projectRevision || !projectLibraryRevision || !identity?.projectLibraryId) {
    throw new Error("Prepared action lost its exact project-library identity.");
  }
  return Object.freeze({
    projectId: projectId ?? null,
    projectRevision,
    projectLibraryId: identity.projectLibraryId,
    projectLibraryRevision,
    nativeProjectId: identity?.nativeProjectId ?? null,
    currentTimelineId: value?.timeline?.id ?? null,
    nativeTimelineId: identity?.nativeTimelineId ?? null,
  });
}

function projectLibraryBinding(context) {
  return {
    identities: {
      projectLibraryId: context.projectLibraryId,
      projectId: null,
      timelineId: null,
      targetIds: [],
    },
    revisions: {
      projectLibrary: context.projectLibraryRevision,
      project: null,
      timeline: null,
      targets: {},
    },
  };
}

function exactTimelineTopology(actionId, input, inspected) {
  const snapshot = inspected.value;
  const tracks = snapshot.tracks ?? [];
  const rows = tracks.flatMap((track) => (track.clips ?? []).map((clip) => ({track, clip})));
  if (tracks.some((track) => !Array.isArray(track.clips))
    || rows.some(({clip}) => !Array.isArray(clip.linkedItemIds))) {
    throw new Error(`Prepared Timeline topology is incomplete: ${actionId}`);
  }
  const byId = new Map(rows.map((row) => [row.clip.id, row]));
  if (byId.size !== rows.length || rows.some(({clip}) => clip.linkedItemIds.some((id) => {
    const linked = byId.get(id);
    return !linked || !linked.clip.linkedItemIds.includes(clip.id);
  }))) throw new Error(`Prepared Timeline linked topology is not reciprocal: ${actionId}`);
  const track = (type, index) => {
    const matches = tracks.filter((candidate) => candidate.type === type && candidate.index === index);
    if (matches.length !== 1 || typeof matches[0].snapshotId !== "string") {
      throw new Error(`Prepared Timeline exact track is unavailable: ${actionId}`);
    }
    return matches[0];
  };
  const clips = (ids, includeLinks = false) => {
    const selected = ids.map((id) => byId.get(id));
    if (selected.some((row) => !row)) throw new Error(`Prepared Timeline item identity is stale: ${actionId}`);
    const closed = new Map(selected.map((row) => [row.clip.id, row]));
    if (includeLinks) for (const row of selected) for (const id of row.clip.linkedItemIds) closed.set(id, byId.get(id));
    return [...closed.values()];
  };
  let targets = [];
  let mediaIds = [];
  if (actionId === "cutagent.action.timeline.track.add") {
    targets = [{kind: "timeline", stableId: snapshot.timeline.id}];
  } else if (actionId.includes("timeline.track.") || actionId === "cutagent.action.timeline.voice_isolation.set") {
    const type = actionId === "cutagent.action.timeline.voice_isolation.set" ? "audio" : input.trackType;
    const index = actionId === "cutagent.action.timeline.voice_isolation.set" ? input.trackIndex : input.index;
    const selected = track(type, index);
    targets = [{kind: "track", stableId: selected.snapshotId, trackType: type, trackIndex: index}];
  } else if (["cutagent.action.timeline.fusion_composition.insert", "cutagent.action.timeline.insert_generator", "cutagent.action.timeline.insert_title"].includes(actionId)) {
    if (!Number.isSafeInteger(input.trackIndex) || !input.recordPosition || !input.duration) {
      throw new Error(`Prepared Timeline insertion requires exact track, position, and duration: ${actionId}`);
    }
    const selected = track("video", input.trackIndex);
    targets = [
      {kind: "timeline", stableId: snapshot.timeline.id},
      {kind: "track", stableId: selected.snapshotId, trackType: "video", trackIndex: input.trackIndex},
    ];
  } else if (actionId === "cutagent.action.timeline.compound_create") {
    const selectedTrack = track(input.trackType, input.trackIndex);
    const ids = selectedTrack.clips.filter((clip) => clip.recordRange.start < input.range.endExclusive
      && clip.recordRange.endExclusive > input.range.start).map((clip) => clip.id);
    if (!ids.length) throw new Error("Prepared compound creation has no exact items in its range.");
    targets = clips(ids, true).map(({track: owner, clip}) => ({kind: "clip", stableId: clip.id, publicId: clip.id, trackType: owner.type, trackIndex: owner.index}));
  } else if (actionId === "cutagent.action.timeline.fusion_clip.create") {
    targets = clips(input.timelineItemIds, true).map(({track: owner, clip}) => ({kind: "clip", stableId: clip.id, publicId: clip.id, trackType: owner.type, trackIndex: owner.index}));
  } else if (actionId === "cutagent.action.timeline.items.set_duration") {
    const ids = Array.isArray(input.updates)
      ? input.updates.map((update) => update.timelineItemId)
      : [input.timelineItemId];
    if (!ids.length || ids.some((id) => typeof id !== "string") || new Set(ids).size !== ids.length) {
      throw new Error("Prepared duration mutation requires unique timelineItemId values.");
    }
    targets = clips(ids, true).map(({track: owner, clip}) => ({kind: "clip", stableId: clip.id, publicId: clip.id, trackType: owner.type, trackIndex: owner.index}));
  } else if (actionId === "cutagent.action.timeline.layer.ensure_media") {
    const selected = track("video", input.trackIndex);
    mediaIds = [input.mediaPoolItemId];
    const affected = clips(
      selected.clips
        .filter((clip) => clip.mediaPoolItemId === input.mediaPoolItemId)
        .map((clip) => clip.id),
      true,
    );
    targets = [
      {kind: "media", stableId: input.mediaPoolItemId, publicId: input.mediaPoolItemId},
      {kind: "track", stableId: selected.snapshotId, trackType: "video", trackIndex: input.trackIndex},
      ...affected.map(({track: owner, clip}) => ({
        kind: "clip", stableId: clip.id, publicId: clip.id,
        trackType: owner.type, trackIndex: owner.index,
      })),
    ];
  } else if (actionId === "cutagent.action.timeline.sync_clips") {
    mediaIds = [...input.sourceItemIds];
    targets = [
      ...mediaIds.map((id) => ({kind: "media", stableId: id, publicId: id})),
      {kind: "timeline", stableId: snapshot.timeline.id, publicId: snapshot.timeline.id},
    ];
  } else {
    targets = [{kind: "timeline", stableId: snapshot.timeline.id}];
  }
  const targetIds = targets.map((target) => target.stableId);
  if (new Set(targetIds).size !== targetIds.length) throw new Error(`Prepared Timeline target closure contains duplicates: ${actionId}`);
  return {snapshot, targets, mediaIds};
}

function captureInputFile(input, secretDir, operationId) {
  if (typeof input.inputPath !== "string") return null;
  const sourcePath = path.resolve(input.inputPath);
  const sourceLstat = fs.lstatSync(sourcePath, {bigint: true});
  if (!sourceLstat.isFile() || sourceLstat.isSymbolicLink() || sourceLstat.size > 64n * 1024n * 1024n) {
    throw new Error("Prepared Timeline import source must be a regular file no larger than 64 MiB.");
  }
  const stagingDir = path.join(secretDir, "sdk-timeline-inputs");
  fs.mkdirSync(stagingDir, {recursive: true, mode: 0o700});
  const stagedPath = path.join(stagingDir, `${operationId}.timeline-input`);
  const sourceFlags = fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW ?? 0);
  const sourceFd = fs.openSync(sourcePath, sourceFlags);
  let stagedFd;
  let captured = false;
  try {
    const before = fs.fstatSync(sourceFd, {bigint: true});
    if (!before.isFile() || before.dev !== sourceLstat.dev || before.ino !== sourceLstat.ino) {
      throw new Error("Prepared Timeline import source identity changed during capture.");
    }
    stagedFd = fs.openSync(stagedPath, fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL, 0o400);
    const buffer = Buffer.allocUnsafe(1024 * 1024);
    for (;;) {
      const read = fs.readSync(sourceFd, buffer, 0, buffer.length, null);
      if (read === 0) break;
      let written = 0;
      while (written < read) written += fs.writeSync(stagedFd, buffer, written, read - written);
    }
    fs.fsyncSync(stagedFd);
    const after = fs.fstatSync(sourceFd, {bigint: true});
    if (after.dev !== before.dev || after.ino !== before.ino || after.size !== before.size || after.mtimeNs !== before.mtimeNs) {
      throw new Error("Prepared Timeline import source changed while it was staged.");
    }
    captured = true;
  } finally {
    if (stagedFd !== undefined) fs.closeSync(stagedFd);
    fs.closeSync(sourceFd);
    if (!captured) fs.rmSync(stagedPath, {force: true});
  }
  const stat = fs.lstatSync(stagedPath, {bigint: true});
  const sha256 = crypto.createHash("sha256").update(fs.readFileSync(stagedPath)).digest("hex");
  return {absolutePath: stagedPath, device: String(stat.dev), inode: String(stat.ino), size: String(stat.size), mtimeNs: String(stat.mtimeNs), sha256: `sha256:${sha256}`};
}

async function liveTimeline(liveInspectionService, input) {
  const inspected = await liveInspectionService.readWithMutationGuard({
    operation: "timeline.snapshot", projectId: input.projectId, timelineId: input.timelineId,
  });
  if (!inspected?.value?.timeline?.id
    || inspected.value.timeline.id !== input.timelineId
    || !inspected.value.revision) {
    throw new Error("Prepared action lost its exact live timeline identity.");
  }
  if (input.revision && inspected.value.revision !== input.revision) throw new Error("Prepared action timeline revision is stale.");
  return inspected;
}

function schemaContainsArtifactField(schema) {
  if (!schema || typeof schema !== "object") return false;
  if (Object.keys(schema.properties ?? {}).some((field) => ARTIFACT_INPUT_FIELDS.has(field))) return true;
  return Object.values(schema.properties ?? {}).some(schemaContainsArtifactField)
    || (schema.items ? schemaContainsArtifactField(schema.items) : false)
    || (schema.oneOf ?? []).some(schemaContainsArtifactField);
}

function artifactRequests(actionId, input) {
  const requests = [];
  const visit = (value) => {
    if (Array.isArray(value)) {
      value.forEach(visit);
      return;
    }
    if (!value || typeof value !== "object") return;
    for (const [field, child] of Object.entries(value)) {
      if (ARTIFACT_INPUT_FIELDS.has(field) && typeof child === "string") {
        requests.push({artifactId: child, field, mode: DESTINATION_FIELDS.has(field) ? "destination" : DIRECTORY_FIELDS.has(field) ? "directory" : "existing"});
      } else {
        visit(child);
      }
    }
  };
  visit(input);
  if (actionId === "cutagent.action.fusion.template.apply"
    && /^artifact_[A-Za-z0-9][A-Za-z0-9._~-]*$/.test(input.template)) {
    requests.push({artifactId: input.template, field: "template", mode: "existing"});
  }
  return [...new Map(requests.map((request) => [`${request.mode}:${request.artifactId}`, request])).values()];
}

async function captureArtifacts(artifactService, {actionId, input, context, secretDir}) {
  const requests = artifactRequests(actionId, input);
  const needsPrivateStore = UNBOUND_FILESYSTEM_ACTION_IDS.has(actionId)
    || [
      "cutagent.action.fusion.template.assets.add",
      "cutagent.action.fusion.template.icon.set",
      "cutagent.action.fusion.template.install",
      "cutagent.action.lut.install",
      "cutagent.action.lut.remove",
    ].includes(actionId);
  if (!requests.length && !needsPrivateStore) return {records: {}, targetIds: [], targetRevisions: {}, referencedPayloadDigests: []};
  if (typeof artifactService?.capturePrivateManagedArtifact !== "function"
    || typeof artifactService?.reservePrivateOutputArtifact !== "function"
    || (requests.some((request) => request.mode === "directory")
      && typeof artifactService?.capturePrivateManagedDirectory !== "function")) {
    throw new Error(`Prepared action requires private artifact capture authority: ${actionId}`);
  }
  void secretDir;
  if (needsPrivateStore && typeof artifactService?.privateArtifactStoreRoot !== "function") {
    throw new Error(`Prepared action requires private output-adoption custody: ${actionId}`);
  }
  const artifactStoreRoot = needsPrivateStore
    ? artifactService.privateArtifactStoreRoot({operationId: context.operationId, accountFingerprint: context.accountFingerprint})
    : null;
  const artifactCustodyNamespace = needsPrivateStore
    ? `sha256:${sha256({accountFingerprint: context.accountFingerprint, purpose: "handler_adopted_artifact"})}`
    : null;
  const records = {};
  const targets = [];
  const referencedPayloadDigests = [];
  for (const request of requests) {
    const extension = actionId === "cutagent.action.fusion.generate" || actionId === "cutagent.action.fusion.template.scaffold" ? "setting"
      : actionId === "cutagent.action.fusion.template.package_drfx" ? "drfx"
        : actionId === "cutagent.action.lut.generate.identity" ? "cube" : "bin";
    const captured = request.mode === "destination"
      ? await artifactService.reservePrivateOutputArtifact({
        artifactId: request.artifactId, operationId: context.operationId,
        accountFingerprint: context.accountFingerprint, extension,
      })
      : request.mode === "directory"
        ? await artifactService.capturePrivateManagedDirectory({
          artifactId: request.artifactId, accountFingerprint: context.accountFingerprint,
        })
        : await artifactService.capturePrivateManagedArtifact({
        artifactId: request.artifactId, accountFingerprint: context.accountFingerprint,
      });
    if (captured?.artifactId !== request.artifactId || typeof captured.absolutePath !== "string") {
      throw new Error(`Prepared action artifact capture is incomplete: ${actionId}`);
    }
    const payloadDigest = request.mode === "directory" ? captured.treeDigest : captured.sha256;
    const revision = request.mode === "destination"
      ? `revision_${sha256({artifactId: request.artifactId, identity: captured.identity, state: "reserved"})}`
      : `revision_${sha256({artifactId: request.artifactId, payloadDigest, identity: captured.identity})}`;
    records[request.artifactId] = request.mode === "destination"
      ? {path: captured.absolutePath, reservationId: context.operationId, reservationIdentity: captured.identity, overwrite: input.overwrite === true}
      : request.mode === "directory"
        ? {
          path: captured.absolutePath, treeDigest: captured.treeDigest, totalBytes: captured.totalBytes,
          entries: captured.entries, directories: captured.directories,
          directoryEntries: captured.directoryEntries, identity: captured.identity,
        }
        : {path: captured.absolutePath, sha256: captured.sha256, byteCount: captured.sizeBytes, identity: captured.identity};
    targets.push({stableId: request.artifactId, revision});
    if (request.mode !== "destination") referencedPayloadDigests.push(payloadDigest);
  }
  const targetIds = targets.map((row) => row.stableId);
  const targetRevisions = Object.fromEntries(targets.map((row) => [row.stableId, row.revision]));
  return {
    records, targetIds, targetRevisions, referencedPayloadDigests,
    ...(artifactStoreRoot ? {artifactStoreRoot} : {}),
    ...(artifactCustodyNamespace ? {artifactCustodyNamespace} : {}),
  };
}

function timelineArtifactRequests(actionId, input) {
  const imageExtension = input.format === "jpeg" ? "jpg" : input.format;
  if (actionId === "cutagent.action.timeline.export") {
    return [{artifactId: input.destinationArtifactId, extension: input.format === "xml" ? "fcpxml" : input.format}];
  }
  if (actionId === "cutagent.action.timeline.inspect_export") {
    return [{artifactId: input.destinationArtifactId, extension: "json"}];
  }
  if (actionId === "cutagent.action.timeline.frame_export" || actionId === "cutagent.action.timeline.thumbnail") {
    return [{artifactId: input.destinationArtifactId, extension: imageExtension}];
  }
  if (actionId === "cutagent.action.timeline.grab_still") {
    return input.operation.kind === "export"
      ? [{artifactId: input.operation.destinationArtifactId, extension: input.operation.format === "jpeg" ? "jpg" : input.operation.format}]
      : [];
  }
  if (actionId === "cutagent.action.timeline.preview_export") {
    return [
      {artifactId: input.destinationArtifactId, extension: input.format},
      ...input.frameArtifactIds.map((artifactId) => ({artifactId, extension: "png"})),
    ];
  }
  if (actionId === "cutagent.action.timeline.still.grab_all") {
    return input.destinationArtifactIds.map((artifactId) => ({artifactId, extension: imageExtension}));
  }
  throw new Error(`Timeline artifact action is not owned: ${actionId}`);
}

async function captureTimelineOutputArtifacts(actionId, input, artifactService, context) {
  const requests = timelineArtifactRequests(actionId, input);
  if (!requests.length) return {records: {}, targetIds: [], targetRevisions: {}};
  if (typeof artifactService?.reservePrivateOutputArtifact !== "function") {
    throw new Error(`Timeline output requires carrier-owned artifact reservation: ${actionId}`);
  }
  if (new Set(requests.map(({artifactId}) => artifactId)).size !== requests.length) {
    throw new Error(`Timeline output artifact identities must be unique: ${actionId}`);
  }
  const records = {};
  const targetRevisions = {};
  for (const request of requests) {
    const reserved = await artifactService.reservePrivateOutputArtifact({
      artifactId: request.artifactId,
      operationId: context.operationId,
      accountFingerprint: context.accountFingerprint,
      extension: request.extension,
    });
    if (reserved?.artifactId !== request.artifactId || typeof reserved.absolutePath !== "string"
      || !reserved.identity || typeof reserved.identity.device !== "number" || typeof reserved.identity.inode !== "number") {
      throw new Error(`Timeline output artifact reservation is incomplete: ${actionId}`);
    }
    records[request.artifactId] = {
      path: reserved.absolutePath,
      reservationId: context.operationId,
      reservationIdentity: reserved.identity,
      extension: request.extension,
    };
    targetRevisions[request.artifactId] = `revision_${sha256({
      artifactId: request.artifactId,
      operationId: context.operationId,
      identity: reserved.identity,
      state: "reserved",
    })}`;
  }
  return {records, targetIds: requests.map(({artifactId}) => artifactId), targetRevisions};
}

async function captureTimeline(actionId, input, context, dependencies) {
  const project = await liveProject(dependencies.liveInspectionService, input.projectId);
  if (actionId === "cutagent.action.timeline.list") return targetBinding(project);
  if (TIMELINE_PROJECT_MUTATION_ACTIONS.has(actionId)) {
    const base = targetBinding(project);
    const requestedTimelineId = actionId.endsWith(".duplicate") ? input.sourceTimelineId : input.timelineId;
    const targetIds = requestedTimelineId ? [requestedTimelineId] : [project.id];
    const inputFile = actionId === "cutagent.action.timeline.import"
      ? captureInputFile(input, dependencies.secretDir, context.operationId)
      : null;
    return {
      identities: {...base.identities, targetIds},
      revisions: {...base.revisions, targets: Object.fromEntries(targetIds.map((id) => [id, project.revision]))},
      privateContext: {
        ...(project.nativeProjectId ? {nativeProjectId: project.nativeProjectId} : {}),
        ...(inputFile ? {timelineTopology: {inputFile}} : {}),
      },
      referencedPayloadDigests: inputFile ? [inputFile.sha256] : [],
    };
  }
  let exactInput = input;
  let nativeVersionIdentity = null;
  if (VERSION_ACTIONS.has(actionId)) {
    const nativeProjectId = project.nativeProjectId;
    const nativeTimelineId = project.nativeTimelineId;
    if (!project.currentTimelineId || typeof nativeProjectId !== "string" || !nativeProjectId
      || typeof nativeTimelineId !== "string" || !nativeTimelineId) {
      throw new Error("Version action has no exact current native project and timeline identity.");
    }
    nativeVersionIdentity = Object.freeze({nativeProjectId, nativeTimelineId});
    exactInput = {...input, projectId: project.id, timelineId: project.currentTimelineId};
  }
  const timelineRead = await liveTimeline(dependencies.liveInspectionService, exactInput);
  if (nativeVersionIdentity && timelineRead.nativeTimelineId !== nativeVersionIdentity.nativeTimelineId) {
    throw new Error("Version action native timeline identity changed during capture.");
  }
  const binding = targetBinding(project, timelineRead.value);
  const artifacts = TIMELINE_ARTIFACT_PREPARED_ACTION_IDS.includes(actionId)
    ? await captureTimelineOutputArtifacts(actionId, input, dependencies.artifactService, context)
    : {records: {}, targetIds: [], targetRevisions: {}};
  if (TIMELINE_ORDINARY_MUTATION_ACTIONS.has(actionId)
    && !TIMELINE_PROJECT_MUTATION_ACTIONS.has(actionId)) {
    const targetId = timelineRead.value.timeline.id;
    binding.identities.targetIds = [targetId];
    binding.revisions.targets = {[targetId]: timelineRead.value.revision};
  }
  if (TIMELINE_ARTIFACT_PREPARED_ACTION_IDS.includes(actionId)
    && (typeof timelineRead.mutationGuard !== "string" || !timelineRead.mutationGuard)) {
    throw new Error("Timeline artifact action lacks an authoritative live Timeline mutation guard.");
  }
  if (TIMELINE_TOPOLOGY_ACTION_ID_SET.has(actionId)) {
    if (typeof project.nativeProjectId !== "string" || !project.nativeProjectId
      || typeof timelineRead.nativeTimelineId !== "string" || !timelineRead.nativeTimelineId) {
      throw new Error(`Prepared Timeline native project/timeline identity is unavailable: ${actionId}`);
    }
    const topology = exactTimelineTopology(actionId, input, timelineRead);
    const media = topology.mediaIds.length
      ? await dependencies.liveInspectionService.resolvePreparedTimelineMedia({
        projectId: project.id, mediaPoolItemIds: topology.mediaIds,
      })
      : [];
    const targetIds = topology.targets.map((target) => target.stableId);
    const mediaById = new Map(media.map((row) => [row.mediaPoolItemId, row]));
    const targets = Object.fromEntries(topology.targets.map((target) => [
      target.stableId,
      target.kind === "media" ? mediaById.get(target.stableId)?.revision : timelineRead.value.revision,
    ]));
    if (Object.values(targets).some((revision) => typeof revision !== "string" || !revision)) {
      throw new Error(`Prepared Timeline target revision is unavailable: ${actionId}`);
    }
    return {
      identities: {...binding.identities, targetIds},
      revisions: {...binding.revisions, targets},
      privateContext: {
        nativeProjectId: project.nativeProjectId,
        nativeTimelineId: timelineRead.nativeTimelineId,
        timeline: {mutationGuard: timelineRead.mutationGuard},
        timelineTopology: {
          snapshot: structuredClone(topology.snapshot),
          targets: structuredClone(topology.targets),
          timelineItemNativeIdByPublicId: Object.fromEntries(timelineRead.privateTimelineItemNativeIdByPublicId ?? []),
          media: structuredClone(media),
          inputFile: captureInputFile(input, dependencies.secretDir, context.operationId),
        },
      },
    };
  }
  let checkpointOwnership = null;
  if (actionId === "cutagent.action.version.restore") {
    if (typeof input.sessionId === "string") {
      checkpointOwnership = dependencies.workflowOwnershipResolver?.assertOwnedBinding({
        accountFingerprint: context.accountFingerprint,
        workflowId: input.sessionId,
        projectId: project.id,
        timelineId: timelineRead.value.timeline.id,
      });
    } else {
      if (typeof context.sdkSessionId !== "string" || !context.sdkSessionId) {
        throw new Error("Version restore transport-session ownership is unavailable.");
      }
      checkpointOwnership = Object.freeze({
        authority: "sdk_transport_session_account_binding_v1",
        sessionId: context.sdkSessionId,
        projectId: project.id,
        timelineId: timelineRead.value.timeline.id,
      });
    }
  }
  const requestedItemIds = actionId === "cutagent.action.timeline.dolby.analyze"
    ? input.timelineItemIds
    : actionId === "cutagent.action.timeline.clip_color.batch"
      ? input.updates.map((update) => update.timelineItemId)
      : null;
  if (requestedItemIds) {
    const nativeBindings = new Map(timelineRead.privateTimelineItemNativeIdByPublicId ?? []);
    if (requestedItemIds.some((id) => !nativeBindings.has(id))) {
      throw new Error("Timeline mutation lost an exact Timeline item identity.");
    }
    binding.identities.targetIds = [...requestedItemIds];
    binding.revisions.targets = Object.fromEntries(requestedItemIds.map((id) => [id, timelineRead.value.revision]));
  }
  return {
    identities: {...binding.identities, targetIds: [...binding.identities.targetIds, ...artifacts.targetIds]},
    revisions: {...binding.revisions, targets: {...binding.revisions.targets, ...artifacts.targetRevisions}},
    privateContext: {
      timelineItemNativeIdByPublicId: Object.fromEntries(timelineRead.privateTimelineItemNativeIdByPublicId ?? []),
      ...(typeof timelineRead.mutationGuard === "string" && timelineRead.mutationGuard
        ? {timeline: {mutationGuard: timelineRead.mutationGuard}}
        : {}),
      ...(timelineRead.nativeTimelineId ? {nativeTimelineId: timelineRead.nativeTimelineId} : {}),
      ...(project.nativeProjectId ? {nativeProjectId: project.nativeProjectId} : {}),
      ...(nativeVersionIdentity ? {nativeProjectId: nativeVersionIdentity.nativeProjectId} : {}),
      ...(checkpointOwnership ? {checkpointOwnership} : {}),
      privateManagedArtifacts: artifacts.records,
    },
  };
}

async function captureFusion(actionId, input, context, dependencies) {
  const artifacts = await captureArtifacts(dependencies.artifactService, {actionId, input, context, secretDir: dependencies.secretDir});
  const requiresProject = typeof input.projectId === "string" || typeof input.timelineId === "string"
    || actionId === "cutagent.action.lut_refresh";
  const projectContext = requiresProject
    ? await liveProject(dependencies.liveInspectionService, input.projectId ?? null)
    : await liveProjectLibrary(dependencies.liveInspectionService);
  const project = requiresProject ? projectContext : null;
  let timelineRead = null;
  if (input.timelineId) timelineRead = await liveTimeline(dependencies.liveInspectionService, input);
  const base = project ? targetBinding(project, timelineRead?.value ?? null) : projectLibraryBinding(projectContext);
  let targetIds = [...artifacts.targetIds];
  let targetRevisions = {...artifacts.targetRevisions};
  const targetKinds = Object.fromEntries(targetIds.map((id) => [id, "media"]));
  const nativeBindings = timelineRead ? Object.fromEntries(timelineRead.privateTimelineItemNativeIdByPublicId ?? []) : {};
  if (actionId === "cutagent.action.fusion.image.batch") {
    const items = Array.isArray(input.items) ? input.items : [];
    const referencesByItemId = await dependencies.liveInspectionService.readFusionCompositionTargets(items.map((item) => ({
      operation: "fusion.compositions", projectId: input.projectId, timelineId: input.timelineId,
      timelineItemId: item.timelineItemId, expectedRevision: input.revision,
    })));
    for (const item of items) {
      const references = referencesByItemId.get(item.timelineItemId);
      const reference = references?.find((row) => row.index === item.compositionIndex);
      if (!reference || reference.revision !== item.compositionRevision) {
        throw new Error("Prepared action exact Fusion image composition is stale or unavailable.");
      }
      const id = `${item.timelineItemId}:fusion:${item.compositionIndex}`;
      if (targetKinds[id]) throw new Error("Prepared Fusion image targets must be unique.");
      targetIds.push(id);
      targetRevisions[id] = reference.revision;
      targetKinds[id] = "fusion_composition";
    }
  } else if (actionId === "cutagent.action.fusion.text.batch") {
    const referencesByItemId = await dependencies.liveInspectionService.readFusionCompositionTargets(input.updates.map((update) => ({
      operation: "fusion.compositions", projectId: input.projectId, timelineId: input.timelineId,
      timelineItemId: update.timelineItemId, expectedRevision: input.revision,
    })));
    for (const update of input.updates) {
      const references = referencesByItemId.get(update.timelineItemId);
      const reference = references?.find((row) => row.index === update.compositionIndex);
      if (!reference || reference.revision !== update.compositionRevision) {
        throw new Error("Prepared action exact Fusion text composition is stale or unavailable.");
      }
      const id = `${update.timelineItemId}:fusion:${update.compositionIndex}`;
      targetIds.unshift(id);
      targetRevisions[id] = reference.revision;
      targetKinds[id] = "fusion_composition";
    }
  } else if (input.timelineItemId && input.compositionIndex) {
    const references = await dependencies.liveInspectionService.read({
      operation: "fusion.compositions", projectId: input.projectId, timelineId: input.timelineId,
      timelineItemId: input.timelineItemId, expectedRevision: input.revision ?? null,
    });
    const reference = references?.find((row) => row.index === input.compositionIndex);
    if (!reference) throw new Error("Prepared action exact Fusion composition is unavailable.");
    const id = `${input.timelineItemId}:fusion:${input.compositionIndex}`;
    targetIds.unshift(id);
    targetRevisions[id] = reference.revision;
    targetKinds[id] = "fusion_composition";
  } else if (input.timelineItemId) {
    targetIds.unshift(input.timelineItemId);
    targetRevisions[input.timelineItemId] = input.revision ?? timelineRead.value.revision;
    targetKinds[input.timelineItemId] = "clip";
  } else if (input.timelineId) {
    targetIds.unshift(input.timelineId);
    targetRevisions[input.timelineId] = input.revision ?? timelineRead.value.revision;
    targetKinds[input.timelineId] = "timeline";
  } else if (input.projectId && project) {
    targetIds.unshift(input.projectId);
    targetRevisions[input.projectId] = input.revision ?? project.revision;
    targetKinds[input.projectId] = "project";
  } else if (OFFLINE_ACTIONS.has(actionId)) {
    const digest = `sha256:${sha256(input)}`;
    const id = `coordinate_${digest.slice(7)}`;
    targetIds.unshift(id);
    targetRevisions[id] = digest;
    targetKinds[id] = "runtime_setting";
  } else if (targetIds.length === 0) {
    const digest = sha256({actionId, input});
    const id = `private_target_${digest.slice(0, 32)}`;
    targetIds.push(id);
    targetRevisions[id] = `revision_${digest}`;
    targetKinds[id] = "runtime_setting";
  }
  targetIds = [...new Set(targetIds)];
  return {
    identities: {...base.identities, targetIds},
    revisions: {...base.revisions, targets: Object.fromEntries(targetIds.map((id) => [id, targetRevisions[id]]))},
    privateContext: {
      privateTargetBindings: Object.fromEntries(Object.entries(nativeBindings).map(([id, nativeId]) => [id, {kind: "timeline_item", nativeId}])),
      privateManagedArtifacts: artifacts.records,
      ...(artifacts.artifactStoreRoot ? {privateArtifactStoreRoot: artifacts.artifactStoreRoot} : {}),
      ...(artifacts.artifactCustodyNamespace ? {privateArtifactCustodyNamespace: artifacts.artifactCustodyNamespace} : {}),
      fusionRequestTargetIds: targetIds,
      fusionRequestTargetRevisions: Object.fromEntries(targetIds.map((id) => [id, targetRevisions[id]])),
      fusionRequestTargetKinds: Object.fromEntries(targetIds.map((id) => [id, targetKinds[id]])),
    },
    referencedPayloadDigests: artifacts.referencedPayloadDigests,
  };
}

function contribution(actionId, dependencies) {
  const mutation = !READ_ACTIONS.has(actionId);
  const payloadDigests = new Map();
  const minimumBinding = TIMELINE_PROJECT_MUTATION_ACTIONS.has(actionId) ? "project" : actionId.startsWith("cutagent.action.timeline.") || VERSION_ACTIONS.has(actionId) || actionId.includes("dctl.apply")
    || actionId.includes("fusion.insert_setting") || actionId.includes("fusion.comp.") || actionId.includes("fusion.node.")
    || actionId.includes("fusion.tool.") || actionId.includes("fusion.effect.") || actionId.includes("fusion.keyframe.")
    || actionId.includes("fusion.mask.") || actionId.includes("fusion.text.") || actionId.includes("fusion.image.")
    || actionId.includes("fusion.tracker.") || actionId.includes("fusion.keyer.") || actionId.includes("fusion.template.apply")
    || actionId.includes("fusion.nested_text.") ? "project+timeline" : actionId === "cutagent.action.lut_refresh" ? "project" : "account/project-library";
  return Object.freeze({
    inputSchema: inputSchema(actionId),
    ...(mutation ? {mutationBinding: Object.freeze({
      minimumBinding,
      async resolveReferencedPayloadDigests({request}) {
        const value = payloadDigests.get(request.operationId);
        payloadDigests.delete(request.operationId);
        if (!value) throw new Error(`Prepared action lost referenced payload custody: ${actionId}`);
        return [...value];
      },
    })} : {}),
    async captureRequestBinding({context, input}) {
      const captured = TIMELINE_VERSION_PREPARED_ACTION_IDS.includes(actionId)
        ? await captureTimeline(actionId, input, context, dependencies)
        : await captureFusion(actionId, input, context, dependencies);
      if (mutation) payloadDigests.set(context.operationId, Object.freeze([...(captured.referencedPayloadDigests ?? [])]));
      return captured;
    },
  });
}

/** Domain factory consumed by the carrier's frozen contribution seam. */
export function createFusionTimelinePreparedActionBuilderContributions(dependencies = {}) {
  if (typeof dependencies.liveInspectionService?.readWithMutationGuard !== "function") {
    throw new TypeError("Fusion/Timeline prepared actions require live DaVinci Resolve inspection.");
  }
  if (dependencies.enabledActionIds != null && !(dependencies.enabledActionIds instanceof Set)) {
    throw new Error("Fusion/Timeline contribution selection contains an unavailable action.");
  }
  if ((dependencies.enabledActionIds == null || dependencies.enabledActionIds.has("cutagent.action.version.restore"))
    && typeof dependencies.workflowOwnershipResolver?.assertOwnedBinding !== "function") {
    throw new TypeError("Version restore requires durable account-bound workflow ownership.");
  }
  const availableIds = [...FUSION_PREPARED_ACTION_IDS, ...TIMELINE_VERSION_PREPARED_ACTION_IDS];
  const expected = FUSION_PREPARED_ACTION_IDS.length + TIMELINE_VERSION_PREPARED_ACTION_IDS.length;
  if (availableIds.length !== expected || new Set(availableIds).size !== expected) throw new Error("Fusion/Timeline contribution action ownership drifted.");
  const requestedIds = dependencies.enabledActionIds == null
    ? availableIds
    : availableIds.filter((actionId) => dependencies.enabledActionIds.has(actionId));
  if (dependencies.enabledActionIds != null && requestedIds.length !== dependencies.enabledActionIds.size) {
    throw new Error("Fusion/Timeline contribution selection contains an unavailable action.");
  }
  const ids = requestedIds;
  return Object.freeze(Object.fromEntries(ids.map((actionId) => [actionId, contribution(actionId, dependencies)])));
}
