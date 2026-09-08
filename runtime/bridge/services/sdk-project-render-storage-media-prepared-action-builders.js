import Ajv2020 from "ajv/dist/2020.js";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import {
  CUTAGENT_PREPARED_ACTION_CAPABILITY_DIGEST,
  CUTAGENT_PREPARED_ACTION_CONTRACT_DIGEST,
} from "../contracts/generated/sdk-prepared-action.js";
import {
  sdkMediaPoolCreateBinInputSchema,
  sdkMediaPoolRelinkInputSchema,
  sdkMediaPoolSetMetadataInputSchema,
  sdkMediaPoolSyncAudioInputSchema,
  sdkProjectBackupInputSchema,
  sdkProjectLibraryBackupInputSchema,
  sdkProjectLibraryCreateInputSchema,
  sdkProjectLibraryOpenInputSchema,
  sdkProjectLibraryRestoreInputSchema,
  sdkProjectOpenInputSchema,
  sdkProjectRestoreInputSchema,
} from "../contracts/generated/sdk-project-media.js";
import {SDK_MEDIA_PREPARED_INPUTS} from "../contracts/sdk-media-prepared-inputs.generated.js";
import {z} from "zod";
import {resolveSdkPreparedMutationScope, sdkMutationScopeCandidates} from "./sdk-direct-mutation-scope.js";

const ajv = new Ajv2020({allErrors: true, strict: true, strictRequired: false});

export const MEDIA_PENDING_PREPARED_ACTION_IDS = Object.freeze(SDK_MEDIA_PREPARED_INPUTS.map(({actionId}) => actionId));

export const PROJECT_RENDER_STORAGE_MEDIA_PREPARED_ACTION_IDS = Object.freeze([
  "cutagent.action.project.rename",
  "cutagent.action.project.settings_set",
  "cutagent.action.render.alpha",
  "cutagent.action.render.encoding",
  "cutagent.action.render.mode.set",
  "cutagent.action.render.subtitles",
  "cutagent.action.media.folders.create",
  "cutagent.action.media.folders.delete",
  "cutagent.action.media.metadata",
  "cutagent.action.media.property_set",
  "cutagent.action.media.third_party_metadata.set",
  "cutagent.action.project.archive",
  "cutagent.action.project.cleanup_scratch",
  "cutagent.action.project.close",
  "cutagent.action.project.cloud.create",
  "cutagent.action.project.cloud.import",
  "cutagent.action.project.cloud.open",
  "cutagent.action.project.cloud.restore",
  "cutagent.action.project.delete",
  "cutagent.action.project.export",
  "cutagent.action.project.folders.create",
  "cutagent.action.project.folders.delete",
  "cutagent.action.project.folders.open",
  "cutagent.action.project.folders.root",
  "cutagent.action.project.folders.up",
  "cutagent.action.project.import",
  "cutagent.action.project.library.backup",
  "cutagent.action.project.library.create",
  "cutagent.action.project.library.restore",
  "cutagent.action.project.library.switch",
  "cutagent.action.project.open",
  "cutagent.action.project.preset.load",
  "cutagent.action.project.preset.save",
  "cutagent.action.project.restore",
  "cutagent.action.project.save",
]);

export const PROJECT_PRODUCTION_PREPARED_ACTION_IDS = Object.freeze([
  "cutagent.action.project.rename",
  "cutagent.action.project.settings_set",
  "cutagent.action.media.folders.create",
  "cutagent.action.media.folders.delete",
  "cutagent.action.media.metadata",
  "cutagent.action.media.property_set",
  "cutagent.action.media.third_party_metadata.set",
  ...MEDIA_PENDING_PREPARED_ACTION_IDS,
  ...PROJECT_RENDER_STORAGE_MEDIA_PREPARED_ACTION_IDS.filter((actionId) => (
    actionId.startsWith("cutagent.action.project.")
    && actionId !== "cutagent.action.project.rename"
    && actionId !== "cutagent.action.project.settings_set"
  )),
]);

if (PROJECT_PRODUCTION_PREPARED_ACTION_IDS.length !== 65
  || new Set(PROJECT_PRODUCTION_PREPARED_ACTION_IDS).size !== 65) {
  throw new Error("Project/Media production prepared-action selection is not exact and unique.");
}

/**
 * Project/Media actions whose production descriptors independently enforce an
 * exact executable target. Keep this as an explicit reviewed subset: adding a
 * prepared-action descriptor must not silently grant desktop execution.
 */
export const PROJECT_NAMESPACE_SIGNED_EXECUTION_ACTION_IDS = Object.freeze([
  "cutagent.action.project.import",
  "cutagent.action.project.preset.load",
  "cutagent.action.project.preset.save",
  "cutagent.action.project.restore",
  "cutagent.action.project.save",
  "cutagent.action.project.library.backup",
  "cutagent.action.project.library.create",
  "cutagent.action.project.library.restore",
  "cutagent.action.project.library.switch",
].sort());

export const PROJECT_NAMESPACE_REMAINING_DEBT_ACTION_IDS = Object.freeze([
  "cutagent.action.project.cloud.create",
  "cutagent.action.project.cloud.import",
  "cutagent.action.project.cloud.open",
  "cutagent.action.project.cloud.restore",
].sort());

export const PROJECT_MEDIA_SIGNED_EXECUTION_ACTION_IDS = Object.freeze([
  "cutagent.action.project.rename",
  "cutagent.action.project.close",
  ...PROJECT_NAMESPACE_SIGNED_EXECUTION_ACTION_IDS,
  "cutagent.action.media.folders.create",
  "cutagent.action.media.folders.delete",
  "cutagent.action.media.metadata",
  "cutagent.action.media.property_set",
  "cutagent.action.media.third_party_metadata.set",
  "cutagent.action.media.clear_transcription",
  "cutagent.action.media.color.clear",
  "cutagent.action.media.color.set",
  "cutagent.action.media.delete",
  "cutagent.action.media.duplicate",
  "cutagent.action.media.extract_template",
  "cutagent.action.media.flag.add",
  "cutagent.action.media.flag.clear",
  "cutagent.action.media.folder.export_drb",
  "cutagent.action.media.folder.import_drb",
  "cutagent.action.media.folders.move",
  "cutagent.action.media.folders.open",
  "cutagent.action.media.folders.root",
  "cutagent.action.media.growing_file.monitor",
  "cutagent.action.media.mark.clear",
  "cutagent.action.media.mark.set",
  "cutagent.action.media.marker.add",
  "cutagent.action.media.marker.delete",
  "cutagent.action.media.matte.delete",
  "cutagent.action.media.metadata.export",
  "cutagent.action.media.move",
  "cutagent.action.media.proxy",
  "cutagent.action.media.proxy.link_fullres",
  "cutagent.action.media.relink",
  "cutagent.action.media.rename",
  "cutagent.action.media.replace",
  "cutagent.action.media.replace_preserve_subclip",
  "cutagent.action.media.selected.set",
  "cutagent.action.media.stereo_create",
  "cutagent.action.media.sync_audio",
  "cutagent.action.media.transcode",
  "cutagent.action.media.transcribe",
  "cutagent.action.media.unlink",
].sort());

const EXPECTED_PROJECT_MEDIA_SIGNED_EXECUTION_ACTION_ID_SET = new Set([
  "cutagent.action.project.rename",
  "cutagent.action.project.close",
  "cutagent.action.media.folders.create",
  "cutagent.action.media.folders.delete",
  "cutagent.action.media.metadata",
  "cutagent.action.media.property_set",
  "cutagent.action.media.third_party_metadata.set",
  ...PROJECT_NAMESPACE_SIGNED_EXECUTION_ACTION_IDS,
  ...MEDIA_PENDING_PREPARED_ACTION_IDS.filter((actionId) => actionId !== "cutagent.action.media.create_timeline"),
]);
if (PROJECT_MEDIA_SIGNED_EXECUTION_ACTION_IDS.length !== 49
  || new Set(PROJECT_MEDIA_SIGNED_EXECUTION_ACTION_IDS).size !== 49
  || PROJECT_MEDIA_SIGNED_EXECUTION_ACTION_IDS.some((actionId) => !PROJECT_PRODUCTION_PREPARED_ACTION_IDS.includes(actionId))
  || EXPECTED_PROJECT_MEDIA_SIGNED_EXECUTION_ACTION_ID_SET.size !== 49
  || PROJECT_MEDIA_SIGNED_EXECUTION_ACTION_IDS.some((actionId) => !EXPECTED_PROJECT_MEDIA_SIGNED_EXECUTION_ACTION_ID_SET.has(actionId))
  || PROJECT_MEDIA_SIGNED_EXECUTION_ACTION_IDS.includes("cutagent.action.project.settings_set")
  || PROJECT_NAMESPACE_REMAINING_DEBT_ACTION_IDS.some((actionId) => PROJECT_MEDIA_SIGNED_EXECUTION_ACTION_IDS.includes(actionId))
  || PROJECT_MEDIA_SIGNED_EXECUTION_ACTION_IDS.includes("cutagent.action.media.create_timeline")) {
  throw new Error("Reviewed Project/Media signed-execution selection is not exact and isolated.");
}

export const RENDER_PRODUCTION_PREPARED_ACTION_IDS = Object.freeze([
  "cutagent.action.render.alpha",
  "cutagent.action.render.encoding",
  "cutagent.action.render.mode.set",
  "cutagent.action.render.subtitles",
]);

const BASE_INPUT_SCHEMAS = {
  "cutagent.action.project.rename": z.object({
    name: z.string().min(1).max(1024),
  }).strict(),
  "cutagent.action.project.settings_set": z.object({
    key: z.string().min(1).max(1024),
    value: z.string().min(1).max(4096),
  }).strict(),
  "cutagent.action.media.create_timeline": z.object({
    timelineName: z.string().min(1).max(1024),
    clips: z.array(z.string().min(1).max(1024)).min(1).max(1000),
  }).strict(),
  "cutagent.action.media.folders.create": z.union([
    sdkMediaPoolCreateBinInputSchema,
    z.object({path: z.string().min(1).max(4096)}).strict(),
  ]),
  "cutagent.action.media.folders.delete": z.object({path: z.string().min(1).max(4096)}).strict(),
  "cutagent.action.media.metadata": z.union([
    sdkMediaPoolSetMetadataInputSchema,
    z.object({operation: z.discriminatedUnion("kind", [
      z.object({kind: z.literal("list"), clipName: z.string().min(1)}).strict(),
      z.object({kind: z.literal("get"), clipName: z.string().min(1), key: z.string().min(1)}).strict(),
      z.object({kind: z.literal("set"), clipName: z.string().min(1), key: z.string().min(1), value: z.string()}).strict(),
    ])}).strict(),
  ]),
  "cutagent.action.media.property_set": z.object({name: z.string().min(1), key: z.string().min(1), value: z.string()}).strict(),
  "cutagent.action.media.third_party_metadata.set": z.object({clip: z.string().min(1), key: z.string().min(1), value: z.string()}).strict(),
  "cutagent.action.media.relink": sdkMediaPoolRelinkInputSchema,
  "cutagent.action.media.sync_audio": sdkMediaPoolSyncAudioInputSchema,
  "cutagent.action.media.transcribe": z.union([
    z.object({clip: z.string().min(1), language: z.string().optional()}).strict(),
    z.object({folder: z.string().min(1), language: z.string().optional()}).strict(),
  ]),
  "cutagent.action.project.archive": z.object({name: z.string().min(1).max(1024), destinationArtifactId: z.string().regex(/^artifact_[A-Za-z0-9][A-Za-z0-9._~-]*$/)}).strict(),
  "cutagent.action.project.cleanup_scratch": z.object({prefixes: z.array(z.string().min(1).max(256)).min(1).max(64).optional(), limit: z.number().int().min(1).max(1024).optional(), includeCurrent: z.boolean().optional()}).strict(),
  "cutagent.action.project.close": z.object({}).strict(),
  "cutagent.action.project.cloud.create": z.object({name: z.string().min(1).max(1024), mediaPath: z.string().max(4096).nullable().optional(), syncMode: z.enum(["none", "proxy_only", "proxy_and_original"]).nullable().optional(), collaboration: z.boolean().optional()}).strict(),
  "cutagent.action.project.cloud.import": z.object({sourceArtifactId: z.string().regex(/^artifact_[A-Za-z0-9][A-Za-z0-9._~-]*$/), name: z.string().min(1).max(1024), mediaPath: z.string().max(4096).nullable().optional()}).strict(),
  "cutagent.action.project.cloud.open": z.object({name: z.string().min(1).max(1024), mediaPath: z.string().max(4096).nullable().optional(), syncMode: z.enum(["none", "proxy_only", "proxy_and_original"]).nullable().optional()}).strict(),
  "cutagent.action.project.cloud.restore": z.object({sourceArtifactId: z.string().regex(/^artifact_[A-Za-z0-9][A-Za-z0-9._~-]*$/), name: z.string().min(1).max(1024), mediaPath: z.string().max(4096).nullable().optional()}).strict(),
  "cutagent.action.project.delete": z.object({name: z.string().min(1).max(1024)}).strict(),
  "cutagent.action.project.export": z.union([sdkProjectBackupInputSchema, z.object({name: z.string().min(1).max(1024), destinationArtifactId: z.string().regex(/^artifact_[A-Za-z0-9][A-Za-z0-9._~-]*$/), withStills: z.boolean().optional()}).strict()]),
  "cutagent.action.project.folders.create": z.object({name: z.string().min(1).max(1024)}).strict(),
  "cutagent.action.project.folders.delete": z.object({name: z.string().min(1).max(1024)}).strict(),
  "cutagent.action.project.folders.open": z.object({name: z.string().min(1).max(1024)}).strict(),
  "cutagent.action.project.folders.root": z.object({}).strict(),
  "cutagent.action.project.folders.up": z.object({}).strict(),
  "cutagent.action.project.import": z.object({sourceArtifactId: z.string().regex(/^artifact_[A-Za-z0-9][A-Za-z0-9._~-]*$/), name: z.string().min(1).max(1024)}).strict(),
  "cutagent.action.project.library.backup": z.union([sdkProjectLibraryBackupInputSchema, z.object({libraryName: z.string().min(1).max(1024), destinationArtifactId: z.string().regex(/^artifact_[A-Za-z0-9][A-Za-z0-9._~-]*$/)}).strict()]),
  "cutagent.action.project.library.create": z.union([sdkProjectLibraryCreateInputSchema, z.object({libraryName: z.string().min(1).max(1024), directoryPath: z.string().min(1).max(4096)}).strict()]),
  "cutagent.action.project.library.restore": z.union([sdkProjectLibraryRestoreInputSchema, z.object({sourceArtifactId: z.string().regex(/^artifact_[A-Za-z0-9][A-Za-z0-9._~-]*$/), libraryName: z.string().min(1).max(1024), directoryPath: z.string().min(1).max(4096)}).strict()]),
  "cutagent.action.project.library.switch": z.union([sdkProjectLibraryOpenInputSchema, z.object({libraryName: z.string().min(1).max(1024), libraryKind: z.literal("disk").optional()}).strict()]),
  "cutagent.action.project.open": z.union([sdkProjectOpenInputSchema, z.object({name: z.string().min(1).max(1024)}).strict()]),
  "cutagent.action.project.preset.load": z.object({name: z.string().min(1).max(1024)}).strict(),
  "cutagent.action.project.preset.save": z.object({name: z.string().min(1).max(1024)}).strict(),
  "cutagent.action.project.restore": z.union([sdkProjectRestoreInputSchema, z.object({sourceArtifactId: z.string().regex(/^artifact_[A-Za-z0-9][A-Za-z0-9._~-]*$/), name: z.string().min(1).max(1024)}).strict()]),
  "cutagent.action.project.save": z.object({}).strict(),
  "cutagent.action.render.alpha": z.object({
    enabled: z.boolean().optional(),
    mode: z.enum(["premultiplied", "straight"]).optional(),
  }).strict(),
  "cutagent.action.render.encoding": z.object({
    profile: z.string().min(1),
    multiPass: z.boolean().optional(),
    networkOptimization: z.boolean().optional(),
  }).strict(),
  "cutagent.action.render.mode.set": z.object({
    mode: z.enum(["individual", "single"]),
  }).strict(),
  "cutagent.action.render.delete": z.object({
    selection: z.union([
      z.object({kind: z.literal("all")}).strict(),
      z.object({
        kind: z.literal("job"),
        jobId: z.string().min(1),
      }).strict(),
    ]),
  }).strict(),
  "cutagent.action.render.subtitles": z.object({
    format: z.enum(["BurnIn", "EmbeddedCaptions", "SeparateFile"]),
    enabled: z.boolean().optional(),
  }).strict(),
};

const INPUT_SCHEMAS = Object.freeze({
  ...Object.fromEntries(SDK_MEDIA_PREPARED_INPUTS.map(({actionId, inputSchema: schema}) => {
    const validate = ajv.compile(schema);
    return [actionId, Object.freeze({
      parse(value) {
        if (!validate(value)) {
          throw Object.assign(new TypeError(`Prepared action input violated its authoritative schema: ${actionId}`), {
            validationErrors: structuredClone(validate.errors ?? []),
          });
        }
        for (const field of ["clips", "paths"]) {
          if (Array.isArray(value?.[field]) && value[field].length > 1000) {
            throw new TypeError(`Prepared Media ${field} exceeds the bounded 1,000-entry authority.`);
          }
        }
        return structuredClone(value);
      },
    })];
  })),
  ...Object.fromEntries(Object.entries(BASE_INPUT_SCHEMAS).map(([actionId, schema]) => {
    if (!["cutagent.action.media.relink", "cutagent.action.media.sync_audio"].includes(actionId)) return [actionId, schema];
    const generated = SDK_MEDIA_PREPARED_INPUTS.find((row) => row.actionId === actionId);
    const validate = ajv.compile(generated.inputSchema);
    return [actionId, z.union([schema, z.custom((value) => (
      validate(value) && (!Array.isArray(value?.clips) || value.clips.length <= 1000)
    ))])];
  })),
});

function exactProjectScope(mutationPolicyGate, accountFingerprint, directScope = null) {
  const scopes = sdkMutationScopeCandidates(mutationPolicyGate, accountFingerprint, directScope).filter((scope) => (
    scope?.binding?.level === "project"
    && typeof scope.binding.projectLibraryId === "string"
    && typeof scope.binding.projectId === "string"
    && typeof scope.binding.projectRevision === "string"
  )) ?? [];
  if (scopes.length !== 1) {
    throw new Error("Prepared project/render mutation requires one exact project scope.");
  }
  return scopes[0];
}

function exactProjectLibraryScope(mutationPolicyGate, accountFingerprint, directScope = null) {
  const scopes = sdkMutationScopeCandidates(mutationPolicyGate, accountFingerprint, directScope).filter((scope) => (
    scope?.binding?.level === "account/project-library"
    && typeof scope.binding.projectLibraryId === "string"
  )) ?? [];
  if (scopes.length !== 1) {
    throw new Error("Prepared project-open mutation requires one exact project-library scope.");
  }
  return scopes[0];
}

function inputSchema(actionId) {
  return INPUT_SCHEMAS[actionId];
}

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === "object") return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  return value;
}

function digest(value) {
  return `sha256:${crypto.createHash("sha256").update(JSON.stringify(canonical(value)), "utf8").digest("hex")}`;
}

function opaque(prefix, value) {
  return `${prefix}${crypto.createHash("sha256").update(value, "utf8").digest("hex").slice(0, 32)}`;
}

function namedProjectTarget(projectLibraryId, activeProject, name, projectRevision) {
  return {
    stableId: name === activeProject.name ? activeProject.id : opaque("project_", `${projectLibraryId}:${name}`),
    revision: name === activeProject.name ? projectRevision : digest({library: projectLibraryId, name}),
  };
}

export const PROJECT_MANAGER_CUSTODY_ACTION_IDS = Object.freeze([
  "cutagent.action.project.archive",
  "cutagent.action.project.cleanup_scratch",
  "cutagent.action.project.delete",
  "cutagent.action.project.export",
  "cutagent.action.project.open",
  "cutagent.action.project.folders.create",
  "cutagent.action.project.folders.delete",
  "cutagent.action.project.folders.open",
  "cutagent.action.project.folders.root",
  "cutagent.action.project.folders.up",
  "cutagent.action.project.import",
  "cutagent.action.project.restore",
]);

export const PROJECT_LIBRARY_CUSTODY_ACTION_IDS = Object.freeze([
  "cutagent.action.project.library.backup",
  "cutagent.action.project.library.create",
  "cutagent.action.project.library.restore",
  "cutagent.action.project.library.switch",
]);

function projectManagerCustody(projectLibraryId, nativeProjectLibrary, folderIdentity, inventoryRows, actionId, input) {
  if (!folderIdentity || typeof folderIdentity.path !== "string" || !folderIdentity.path
    || typeof folderIdentity.nativeId !== "string" || !folderIdentity.nativeId
    || !Array.isArray(folderIdentity.children) || !Array.isArray(folderIdentity.projects)
    || !Array.isArray(folderIdentity.ancestors) || !Array.isArray(inventoryRows)) {
    throw new Error("Prepared Project Manager mutation requires exact folder and project inventory custody.");
  }
  const currentFolder = {path: folderIdentity.path, nativeId: folderIdentity.nativeId};
  const byUtf8Path = (left, right) => Buffer.compare(Buffer.from(left.path, "utf8"), Buffer.from(right.path, "utf8"));
  const children = folderIdentity.children.map((child) => ({name: child.name, path: child.path, nativeId: child.nativeId}))
    .sort(byUtf8Path);
  const ancestors = folderIdentity.ancestors.map((ancestor) => ({path: ancestor.path, nativeId: ancestor.nativeId}))
    .sort(byUtf8Path);
  const projectRecords = Array.isArray(folderIdentity.projectRecords) ? folderIdentity.projectRecords : [];
  const nativeIdByName = new Map(projectRecords.map((row) => [row?.name, row?.nativeId]));
  const projects = inventoryRows.map((row) => ({
    id: row?.project?.id, name: row?.project?.name, current: row?.current === true,
    index: row?.index, nativeId: nativeIdByName.get(row?.project?.name),
  }))
    .sort((left, right) => Buffer.compare(Buffer.from(left.name ?? "", "utf8"), Buffer.from(right.name ?? "", "utf8")));
  if (children.some((row) => !row.name || !row.path || !row.nativeId)
    || ancestors.some((row) => !row.path || !row.nativeId)
    || projectRecords.length !== projects.length
    || nativeIdByName.size !== projectRecords.length
    || new Set(projectRecords.map((row) => row?.nativeId)).size !== projectRecords.length
    || projects.some((row) => !row.id || !row.name || !row.nativeId || !Number.isSafeInteger(row.index))
    || new Set(projects.map((row) => row.name)).size !== projects.length
    || JSON.stringify(projects.map((row) => row.name).sort()) !== JSON.stringify([...folderIdentity.projects].sort())) {
    throw new Error("Prepared Project Manager inventory is incomplete or ambiguous.");
  }
  const inventoryRevision = digest({projectLibraryId, nativeProjectLibrary, currentFolder, children, projects, ancestors});
  const folderAction = actionId.startsWith("cutagent.action.project.folders.");
  let targets;
  if (folderAction) {
    const currentParts = currentFolder.path.split(" / ");
    let path = currentFolder.path;
    let nativeId = currentFolder.nativeId;
    let state = "existing";
    if (actionId.endsWith(".root")) path = "Projects";
    else if (actionId.endsWith(".up")) path = currentParts.length > 1 ? currentParts.slice(0, -1).join(" / ") : "Projects";
    else path = `${currentFolder.path} / ${input.name}`;
    if (actionId.endsWith(".create")) {
      if (children.some((child) => child.path === path)) throw new Error("Prepared Project-folder create target is no longer absent.");
      nativeId = null; state = "absent";
    } else if (!actionId.endsWith(".root") && !actionId.endsWith(".up")) {
      const matches = children.filter((child) => child.path === path && child.name === input.name);
      if (matches.length !== 1) throw new Error("Prepared Project-folder target identity is missing or ambiguous.");
      nativeId = matches[0].nativeId;
    } else {
      const matches = ancestors.filter((ancestor) => ancestor.path === path);
      if (matches.length !== 1) throw new Error("Prepared Project-folder ancestor identity is missing or ambiguous.");
      nativeId = matches[0].nativeId;
    }
    const stableId = opaque("project_folder_", `${projectLibraryId}:${path}`);
    targets = [{kind: "project_folder", stableId, revision: digest({inventoryRevision, actionId, path, nativeId, state}), path, nativeId, state}];
  } else if (["cutagent.action.project.import", "cutagent.action.project.restore"].includes(actionId)) {
    const name = input.name;
    if (typeof name !== "string" || !name || projects.some((row) => row.name === name)) {
      throw new Error("Prepared Project import/restore target is invalid or no longer absent.");
    }
    const stableId = stableDigest("project_", {projectLibraryId, projectFolderId: currentFolder.nativeId, name});
    targets = [{kind: "project", stableId, revision: digest({inventoryRevision, actionId, name, state: "absent"}), name, state: "absent"}];
  } else {
    let names;
    if (actionId.endsWith("cleanup_scratch")) {
      const allowed = new Set(["CA CLI Color Proof", "CA Color Slice", "CA Color Warper", "CA Local Color", "CA ResolveFX", "CA Sky Isolation", "CutAgent Color Proof", "CutAgent ResolveFX", "CutAgent Scratch"]);
      const prefixes = input.prefixes ?? [...allowed];
      if (prefixes.some((prefix) => !allowed.has(prefix)) || input.includeCurrent === true) throw new Error("Scratch cleanup is limited to reviewed non-current CutAgent scratch projects.");
      names = projects.filter((row) => !row.current && prefixes.some((prefix) => row.name.startsWith(prefix))).map((row) => row.name);
      if (!names.length || names.length > (input.limit ?? 32)) throw new Error("Scratch cleanup candidate set is empty or exceeds its signed limit.");
    } else names = [input.project?.name ?? input.name];
    targets = names.map((name) => {
      const matches = projects.filter((row) => row.name === name);
      if (matches.length !== 1) throw new Error("Prepared Project target is missing or ambiguous in the exact folder inventory.");
      if (actionId.endsWith(".delete") && matches[0].current) throw new Error("Prepared Project deletion cannot target the active project.");
      return {...matches[0], kind: "project", stableId: matches[0].id, revision: digest({inventoryRevision, actionId, project: matches[0]})};
    });
  }
  return {projectLibraryId, nativeProjectLibrary: structuredClone(nativeProjectLibrary), currentFolder, children, projects, ancestors, inventoryRevision, targets};
}

function stableDigest(prefix, value) {
  return `${prefix}f${crypto.createHash("sha256").update(JSON.stringify(canonical(value)), "utf8").digest("base64url")}`;
}

function normalizedProjectLibraryInventory(inventory) {
  if (!inventory || typeof inventory !== "object" || !inventory.currentDatabase
    || !Array.isArray(inventory.databases) || inventory.databases.length > 1024) {
    throw new Error("Prepared project-library mutation requires exact native database inventory custody.");
  }
  const databases = inventory.databases.map((row) => structuredClone(row)).sort((left, right) => Buffer.compare(
    Buffer.from(JSON.stringify(canonical(left.database)), "utf8"),
    Buffer.from(JSON.stringify(canonical(right.database)), "utf8"),
  ));
  if (databases.some((row) => typeof row.stableId !== "string" || !row.stableId
    || !row.nativeProjectLibrary || !new Set(["disk", "postgresql"]).has(row.nativeProjectLibrary.kind)
    || !row.database || typeof row.database.DbName !== "string" || !row.database.DbName
    || !new Set(["Disk", "PostgreSQL"]).has(row.database.DbType))) {
    throw new Error("Prepared project-library inventory contains an incomplete native identity.");
  }
  const nativeKeys = databases.map((row) => JSON.stringify(canonical(row.database)));
  if (new Set(nativeKeys).size !== databases.length || new Set(databases.map((row) => row.stableId)).size !== databases.length) {
    throw new Error("Prepared project-library inventory contains ambiguous native identities.");
  }
  const inventoryRevision = digest({currentDatabase: inventory.currentDatabase, databases});
  return {currentDatabase: structuredClone(inventory.currentDatabase), databases, inventoryRevision};
}

function projectLibraryCustody(inventory, actionId, input, destination = null) {
  const normalized = normalizedProjectLibraryInventory(inventory);
  const {databases, inventoryRevision} = normalized;
  const name = input.library?.name ?? input.libraryName;
  const matches = databases.filter((row) => row.database.DbType === "Disk" && row.database.DbName === name);
  if (["cutagent.action.project.library.create", "cutagent.action.project.library.restore"].includes(actionId)) {
    if (matches.length !== 0) throw new Error("Prepared Disk project-library destination name already exists.");
    if (!destination || destination.libraryName !== name || destination.namespaceRevision !== inventoryRevision
      || destination.state !== "reserved" || typeof destination.libraryDestinationId !== "string"
      || typeof destination.absenceRevision !== "string") {
      throw new Error("Prepared Disk project-library destination custody is incomplete.");
    }
    const target = {kind: "project_library", stableId: destination.libraryDestinationId,
      revision: digest({inventoryRevision, actionId, libraryName: name, absenceRevision: destination.absenceRevision}),
      database: {DbType: "Disk", DbName: name}, destinationId: destination.libraryDestinationId};
    return {...normalized, target};
  }
  if (matches.length !== 1) throw new Error("Prepared Disk project-library target is missing or ambiguous.");
  const selected = matches[0];
  const target = {
    kind: "project_library",
    stableId: selected.stableId,
    revision: digest({inventoryRevision, actionId, database: selected.database}),
    database: structuredClone(selected.database),
  };
  return {...normalized, target};
}

function namedLibraryTarget(projectLibraryId, name) {
  return {stableId: opaque("project_library_", `${projectLibraryId}:${name}`), revision: digest({name, kind: "disk"})};
}

function projectTargetNames(actionId, input, value) {
  if (["cutagent.action.project.archive", "cutagent.action.project.delete", "cutagent.action.project.export", "cutagent.action.project.open"].includes(actionId)) {
    return [input.project?.name ?? input.name];
  }
  if (actionId.startsWith("cutagent.action.project.cloud.")) {
    return [input.name].filter(Boolean);
  }
  if (["cutagent.action.project.close", "cutagent.action.project.save", "cutagent.action.project.preset.load", "cutagent.action.project.preset.save"].includes(actionId)) {
    return [value.project.name];
  }
  return [];
}

const PROJECT_ARTIFACT_REQUESTS = Object.freeze({
  "cutagent.action.project.archive": {field: "destinationArtifactId", mode: "destination_directory"},
  "cutagent.action.project.export": {field: "destinationArtifactId", mode: "destination_file", extension: "drp"},
  "cutagent.action.project.library.backup": {field: "destinationArtifactId", mode: "destination_output_directory"},
  "cutagent.action.project.library.restore": {field: "sourceArtifactId", mode: "source_directory", singleDirectoryName: "backup"},
  "cutagent.action.project.restore": {field: "sourceArtifactId", mode: "source_directory", singleDirectorySuffix: ".dra"},
  "cutagent.action.project.import": {field: "sourceArtifactId", mode: "source_file"},
  "cutagent.action.project.cloud.import": {field: "sourceArtifactId", mode: "source_file"},
  "cutagent.action.project.cloud.restore": {field: "sourceArtifactId", mode: "source_directory"},
});

function compareUnicodeCodePoints(left, right) {
  const leftPoints = Array.from(left, (value) => value.codePointAt(0));
  const rightPoints = Array.from(right, (value) => value.codePointAt(0));
  for (let index = 0; index < Math.min(leftPoints.length, rightPoints.length); index += 1) {
    if (leftPoints[index] !== rightPoints[index]) return leftPoints[index] - rightPoints[index];
  }
  return leftPoints.length - rightPoints.length;
}

function portableDirectoryContentDigest(captured) {
  if (!Array.isArray(captured?.directories) || !Array.isArray(captured?.entries)) return null;
  const rows = [
    ...captured.directories.map((relativePath) => ({kind: "directory", relativePath})),
    ...captured.entries.map((entry) => ({kind: "file", relativePath: entry.relativePath, sha256: entry.sha256})),
  ].sort((left, right) => compareUnicodeCodePoints(left.relativePath, right.relativePath));
  const hash = crypto.createHash("sha256");
  for (const row of rows) {
    hash.update(`${row.kind}\0${row.relativePath}\0`, "utf8");
    if (row.kind === "file") {
      const contentSha256 = String(row.sha256).replace(/^sha256:/u, "");
      if (!/^[a-f0-9]{64}$/u.test(contentSha256)) throw new Error("Managed Project artifact has an invalid file digest.");
      hash.update(Buffer.from(contentSha256, "hex"));
    }
  }
  return `sha256:${hash.digest("hex")}`;
}

async function captureProjectArtifact(artifactService, actionId, input, context) {
  const request = PROJECT_ARTIFACT_REQUESTS[actionId];
  if (!request) return null;
  const artifactId = input[request.field];
  if (typeof artifactService?.privateManagedRoot !== "function") {
    throw new Error(`Prepared Project action requires private artifact custody: ${actionId}`);
  }
  let captured;
  if (request.mode === "destination_output_directory") {
    if (typeof artifactService.reservePrivateOutputDirectory !== "function") {
      throw new Error(`Prepared Project action requires directory-output publication custody: ${actionId}`);
    }
    captured = await artifactService.reservePrivateOutputDirectory({artifactId, operationId: context.operationId, accountFingerprint: context.accountFingerprint});
  } else if (request.mode === "destination_directory") {
    captured = await artifactService.reservePrivateManagedDirectory({artifactId, operationId: context.operationId, accountFingerprint: context.accountFingerprint});
  } else if (request.mode === "destination_file") {
    captured = await artifactService.reservePrivateManagedArtifact({artifactId, operationId: context.operationId, accountFingerprint: context.accountFingerprint, extension: request.extension});
  } else if (request.mode === "source_directory") {
    captured = await artifactService.capturePrivateManagedDirectory({
      artifactId,
      accountFingerprint: context.accountFingerprint,
      ...(request.singleDirectorySuffix ? {singleDirectorySuffix: request.singleDirectorySuffix} : {}),
      ...(request.singleDirectoryName ? {singleDirectoryName: request.singleDirectoryName} : {}),
    });
  } else {
    captured = await artifactService.capturePrivateManagedArtifact({artifactId, accountFingerprint: context.accountFingerprint});
  }
  if (captured?.artifactId !== artifactId || typeof captured.absolutePath !== "string") {
    throw new Error(`Prepared Project artifact capture is incomplete: ${actionId}`);
  }
  const destination = request.mode.startsWith("destination_");
  const directory = request.mode.endsWith("_directory");
  const payloadDigest = directory ? captured.treeDigest : captured.sha256;
  const revision = destination
    ? `revision_${digest({artifactId, identity: captured.identity, state: "reserved"}).slice(7)}`
    : `revision_${digest({artifactId, payloadDigest, identity: captured.identity}).slice(7)}`;
  const record = destination
    ? {path: captured.absolutePath, reservationId: context.operationId, reservationIdentity: captured.identity}
    : directory
      ? {path: captured.absolutePath, treeDigest: captured.treeDigest, contentTreeDigest: portableDirectoryContentDigest(captured), totalBytes: captured.totalBytes, entries: captured.entries, identity: captured.identity}
      : {path: captured.absolutePath, sha256: captured.sha256, byteCount: captured.sizeBytes, identity: captured.identity};
  return {artifactId, revision, record, root: artifactService.privateManagedRoot(), payloadDigest: destination ? null : payloadDigest};
}

async function exactMediaPoolSnapshot(liveInspectionService, projectId) {
  let offset = 0;
  let revision = null;
  const folders = [];
  const assets = [];
  const privateEntries = [];
  let currentFolderId;
  do {
    const inspected = await liveInspectionService.readWithMutationGuard({operation: "mediaPool.page", projectId, offset, pageSize: 32, expectedRevision: revision, search: null});
    revision ??= inspected.value.revision;
    if (inspected.value.revision !== revision) throw new Error("Media Pool revision changed during exact target resolution.");
    folders.push(...inspected.value.folders);
    assets.push(...inspected.value.assets);
    privateEntries.push(...(inspected.privateMediaPoolState?.entries ?? []));
    if (currentFolderId === undefined) currentFolderId = inspected.privateMediaPoolState?.currentFolderId;
    else if (currentFolderId !== inspected.privateMediaPoolState?.currentFolderId) throw new Error("Current Media Pool folder changed during exact target resolution.");
    offset = inspected.value.nextOffset;
  } while (offset !== null);
  if (typeof revision !== "string" || privateEntries.length !== folders.length + assets.length) {
    throw new Error("Prepared Media Pool inspection omitted private exact identity evidence.");
  }
  const publicEntities = [...folders.map((row) => ["folder", row]), ...assets.map((row) => ["asset", row])]
    .map(([entryKind, row]) => `${entryKind}\0${row.id}\0${row.name}`).sort();
  const privateEntities = privateEntries
    .map((row) => `${row.entryKind}\0${row.id}\0${row.name}`).sort();
  if (JSON.stringify(publicEntities) !== JSON.stringify(privateEntities)) {
    throw new Error("Prepared Media Pool public and private exact identity evidence drifted.");
  }
  return {revision, folders, assets, privateEntries, currentFolderId};
}

function exactFolderRows(snapshot) {
  const rows = snapshot.privateEntries.filter((entry) => entry.entryKind === "folder");
  const byCoordinate = new Map(rows.map((row) => [JSON.stringify(row.coordinate), row]));
  const pathCache = new Map();
  const pathFor = (row, visiting = new Set()) => {
    if (!row) throw new Error("Prepared Media Pool folder ancestry references a missing parent.");
    const key = JSON.stringify(row.coordinate);
    if (pathCache.has(key)) return pathCache.get(key);
    if (visiting.has(key)) throw new Error("Prepared Media Pool folder ancestry is cyclic.");
    visiting.add(key);
    const path = row.parentCoordinate === null
      ? row.name
      : `${pathFor(byCoordinate.get(JSON.stringify(row.parentCoordinate)), visiting)}/${row.name}`;
    visiting.delete(key);
    pathCache.set(key, path);
    return path;
  };
  return rows.map((row) => ({...row, path: pathFor(row)}));
}

function exactFolderBinding(snapshot, actionId, input) {
  const rows = exactFolderRows(snapshot);
  const roots = rows.filter((row) => row.parentCoordinate === null);
  if (roots.length !== 1 || typeof roots[0].id !== "string") throw new Error("Prepared Media Pool root has no unique durable identity.");
  const root = roots[0];
  if (actionId.endsWith("folders.create") && "projectId" in input) {
    const parent = input.parent.kind === "root"
      ? root
      : rows.find((row) => row.id === input.parent.id);
    if (!parent || typeof parent.id !== "string") throw new Error("Prepared Media Pool parent folder is missing or ambiguous.");
    const targetPath = `${parent.path}/${input.name}`;
    if (rows.some((row) => row.path === targetPath)) throw new Error("Prepared Media Pool create target already exists.");
    return {operation: "create", parentId: parent.id, targetId: null, targetPath, targetName: input.name};
  }
  const logical = input.path.split("/").filter(Boolean).join("/");
  const targetPath = logical === root.name || logical.startsWith(`${root.name}/`) ? logical : `${root.name}/${logical}`;
  const target = rows.filter((row) => row.path === targetPath);
  if (actionId.endsWith("folders.create")) {
    if (target.length) throw new Error("Prepared Media Pool create target already exists.");
    const parentPath = targetPath.split("/").slice(0, -1).join("/");
    const parent = rows.find((row) => row.path === parentPath);
    if (!parent || typeof parent.id !== "string") throw new Error("Prepared Media Pool parent folder has no durable identity.");
    return {operation: "create", parentId: parent.id, targetId: null, targetPath, targetName: targetPath.split("/").at(-1)};
  }
  if (target.length !== 1 || typeof target[0].id !== "string" || target[0].id === root.id) {
    throw new Error("Prepared Media Pool delete target is missing, ambiguous, or is the root folder.");
  }
  return {operation: "delete", parentId: null, targetId: target[0].id, targetPath, targetName: target[0].name};
}

function sha256(value) { return crypto.createHash("sha256").update(value).digest("hex"); }

function logicalFolder(rows, rawPath) {
  const roots = rows.filter((row) => row.parentCoordinate === null);
  if (roots.length !== 1) throw new Error("Prepared Media Pool root folder is ambiguous.");
  const logical = String(rawPath ?? "").split("/").filter(Boolean).join("/");
  const full = !logical || logical === roots[0].name || logical.startsWith(`${roots[0].name}/`)
    ? (logical || roots[0].name) : `${roots[0].name}/${logical}`;
  const matches = rows.filter((row) => row.path === full);
  if (matches.length !== 1 || typeof matches[0].id !== "string") {
    throw new Error(`Prepared Media Pool folder is missing or ambiguous: ${full}`);
  }
  return matches[0];
}

function managedRoots(secretDir) {
  return [process.env.CUTAGENT_USER_UPLOADS_DIR, process.env.CUTAGENT_USER_EXPORTS_DIR,
    process.env.CUTAGENT_CHECKPOINT_DIR, process.env.CUTAGENT_ARTIFACTS_DIR,
    ...(typeof secretDir === "string" ? [secretDir] : [])]
    .filter(Boolean).map((value) => path.resolve(value));
}

function managedPathDigest(resolvedPath) {
  const stat = fs.lstatSync(resolvedPath);
  if (stat.isSymbolicLink()) throw new Error("Prepared Media artifact cannot be a symlink.");
  if (stat.isFile()) return `sha256:${sha256(fs.readFileSync(resolvedPath))}`;
  if (!stat.isDirectory()) throw new Error("Prepared Media artifact must be a file or directory.");
  const hash = crypto.createHash("sha256");
  const framed = (kind, relative, contentDigest = null) => {
    const encoded = Buffer.from(relative, "utf8");
    const length = Buffer.alloc(8); length.writeBigUInt64BE(BigInt(encoded.length));
    hash.update(kind); hash.update(length); hash.update(encoded);
    if (contentDigest) hash.update(contentDigest);
  };
  const visit = (directory, prefix = "") => {
    for (const name of fs.readdirSync(directory).sort()) {
      const child = path.join(directory, name);
      const relative = path.posix.join(prefix, name);
      const childStat = fs.lstatSync(child);
      if (childStat.isSymbolicLink()) throw new Error("Prepared Media artifact tree cannot contain symlinks.");
      if (childStat.isDirectory()) { framed("d", relative); visit(child, relative); }
      else if (childStat.isFile()) { framed("f", relative, crypto.createHash("sha256").update(fs.readFileSync(child)).digest()); }
      else throw new Error("Prepared Media artifact tree contains an unsupported entry.");
    }
  };
  visit(resolvedPath);
  return `sha256:${hash.digest("hex")}`;
}

function captureManagedMediaInput(rawPath, secretDir, {allowExactExternalFile = false} = {}) {
  const resolvedPath = path.resolve(rawPath);
  const roots = managedRoots(secretDir).filter((root) => resolvedPath === root || resolvedPath.startsWith(`${root}${path.sep}`));
  if (!fs.existsSync(resolvedPath)) throw new Error("Prepared Media input escaped custody or is unavailable.");
  const stat = fs.lstatSync(resolvedPath);
  if (stat.isSymbolicLink() || (roots.length !== 1 && !(allowExactExternalFile && stat.isFile()))) {
    throw new Error("Prepared Media input escaped custody or is unavailable.");
  }
  const contentDigest = managedPathDigest(resolvedPath);
  const stableId = `artifact_${sha256(resolvedPath).slice(0, 32)}`;
  return {stableId, resolvedPath, contentDigest, revision: `revision_${sha256(`${resolvedPath}:${contentDigest}`).slice(0, 32)}`};
}

function captureMediaArtifact(actionId, role, rawPath, context, {artifactService, secretDir}, options = {}) {
  if (role === "input") return captureManagedMediaInput(rawPath, secretDir, options);
  if (typeof artifactService?.reservePrivateOutputArtifact !== "function") {
    throw new Error("Prepared Media output requires carrier-owned artifact custody.");
  }
  const extension = path.extname(rawPath).slice(1).toLowerCase();
  if (!/^[a-z0-9]{1,12}$/u.test(extension)) throw new Error("Prepared Media output extension is invalid.");
  const stableId = `artifact_${sha256(`${context.operationId}:${actionId}:output`).slice(0, 32)}`;
  const reservation = artifactService.reservePrivateOutputArtifact({artifactId: stableId, operationId: context.operationId, accountFingerprint: context.accountFingerprint, extension});
  const parentStat = fs.lstatSync(path.dirname(reservation.absolutePath));
  return {
    stableId, resolvedPath: reservation.absolutePath, reservationId: `reservation_${sha256(`${stableId}:${context.operationId}`).slice(0, 32)}`,
    revision: `revision_reserved_${sha256(`${stableId}:${context.operationId}`).slice(0, 24)}`, reservationIdentity: reservation.identity,
    reservationParentIdentity: {device: parentStat.dev, inode: parentStat.ino},
  };
}

function genericMediaBinding(snapshot, actionId, input, context, dependencies) {
  const folderRows = exactFolderRows(snapshot);
  const semanticRelink = actionId === "cutagent.action.media.relink" && typeof input.assetId === "string";
  const semanticSync = actionId === "cutagent.action.media.sync_audio" && typeof input.videoAssetId === "string";
  if ((semanticRelink || semanticSync) && input.precondition !== snapshot.revision) {
    throw new Error("Prepared Media Pool input revision is stale.");
  }
  const semanticAssetIds = semanticRelink ? [input.assetId]
    : semanticSync ? [input.videoAssetId, ...input.audioAssetIds] : [];
  const assetNames = [input.name, input.clipName, input.clip, input.old, input.left, input.right, ...(input.clips ?? [])]
    .filter((value) => typeof value === "string" && value);
  const assets = [];
  for (const id of semanticAssetIds) {
    const matches = snapshot.assets.filter((asset) => asset.id === id);
    if (matches.length !== 1) throw new Error(`Prepared Media Pool durable asset is missing or ambiguous: ${id}`);
    if (snapshot.assets.filter((asset) => asset.name === matches[0].name).length !== 1) {
      throw new Error(`Prepared Media Pool durable asset cannot be lowered through an ambiguous native name: ${id}`);
    }
    assets.push(matches[0]);
  }
  for (const name of [...new Set(assetNames)]) {
    const matches = snapshot.assets.filter((asset) => asset.name === name && typeof asset.id === "string");
    if (matches.length !== 1) throw new Error(`Prepared Media Pool asset is missing or ambiguous: ${name}`);
    assets.push(matches[0]);
  }
  const folders = [];
  const folderValues = [];
  if (typeof input.folder === "string" && input.folder) folderValues.push(input.folder);
  if (typeof input.target === "string" && input.target) folderValues.push(input.target);
  if (typeof input.targetPath === "string" && input.targetPath) folderValues.push(input.targetPath);
  if (typeof input.path === "string" && actionId.includes("folders.")) folderValues.push(input.path);
  if (actionId.endsWith("folders.root")) {
    folderValues.push("");
  } else if (actionId.endsWith("folder.import_drb") || actionId === "cutagent.action.media.duplicate"
    || (["cutagent.action.media.transcribe", "cutagent.action.media.clear_transcription"].includes(actionId) && assets.length === 0 && folderValues.length === 0)) {
    const current = folderRows.find((row) => row.id === snapshot.currentFolderId);
    if (!current) throw new Error("Prepared Media mutation requires an exact current Media Pool folder.");
    folderValues.push(current.path);
  }
  for (const folderPath of [...new Set(folderValues)]) folders.push(logicalFolder(folderRows, folderPath));
  if (actionId === "cutagent.action.media.folders.move" && folders.length > 0) {
    const source = logicalFolder(folderRows, input.path);
    const destination = logicalFolder(folderRows, input.targetPath);
    if (source.parentCoordinate === null || source.id === destination.id
      || destination.path.startsWith(`${source.path}/`)) {
      throw new Error("Prepared Media Pool folder move has an invalid source/destination topology.");
    }
    const sourcePath = source.path;
    for (const row of folderRows.filter((candidate) => candidate.path.startsWith(`${sourcePath}/`))) {
      if (!folders.some((candidate) => candidate.id === row.id)) folders.push(row);
    }
    for (const asset of snapshot.assets.filter((candidate) => candidate.folder === sourcePath || candidate.folder?.startsWith(`${sourcePath}/`))) {
      if (!assets.some((candidate) => candidate.id === asset.id)) assets.push(asset);
    }
  }
  if (["cutagent.action.media.transcribe", "cutagent.action.media.clear_transcription"].includes(actionId)
    && assets.length === 0 && folders.length > 0) {
    const folderPath = folders[0].path;
    for (const asset of snapshot.assets.filter((candidate) => candidate.folder === folderPath || candidate.folder?.startsWith(`${folderPath}/`))) {
      assets.push(asset);
    }
  }

  const handlerInput = semanticRelink
    ? {name: assets[0].name, path: input.path}
    : semanticSync ? {
      clips: assets.map((asset) => asset.name),
      mode: input.method,
      retainEmbeddedAudio: input.appendTracks,
    } : structuredClone(input);
  const artifacts = {};
  const outputField = actionId.endsWith("folder.export_drb") || actionId.endsWith("metadata.export") ? "file"
    : actionId.endsWith("transcode") ? "outputPath" : null;
  const inputFields = [];
  if (actionId.endsWith("folder.import_drb")) inputFields.push("file", ...(input.sourceClipsPath ? ["sourceClipsPath"] : []));
  if (["proxy.link_fullres", "relink", "replace", "replace_preserve_subclip"].some((suffix) => actionId.endsWith(suffix))) inputFields.push("path");
  if (actionId.endsWith("proxy") && input.operation?.kind === "link") inputFields.push("operation.path");
  if (actionId.endsWith("matte.delete")) inputFields.push(...input.paths.map((_value, index) => `paths.${index}`));
  const get = (field) => field.split(".").reduce((value, key) => value?.[key], handlerInput);
  const set = (field, value) => {
    const keys = field.split("."); let target = handlerInput;
    for (const key of keys.slice(0, -1)) target = target[key];
    target[keys.at(-1)] = value;
  };
  if (outputField) {
    const artifact = captureMediaArtifact(actionId, "output", get(outputField), context, dependencies);
    artifacts.output = artifact; set(outputField, artifact.resolvedPath);
  }
  for (const [index, field] of inputFields.entries()) {
    const artifact = captureMediaArtifact(actionId, "input", get(field), context, dependencies, {
      allowExactExternalFile: (semanticRelink && field === "path")
        || (actionId === "cutagent.action.media.proxy" && field === "operation.path"),
    });
    artifacts[`input${index}`] = artifact; set(field, artifact.resolvedPath);
  }
  const timelineTargets = [];
  if (actionId === "cutagent.action.media.create_timeline") {
    if (!Array.isArray(snapshot.timelines) || typeof snapshot.projectId !== "string") {
      throw new Error("Prepared Media timeline creation requires an exact Timeline inventory.");
    }
    if (snapshot.timelines.some((timeline) => timeline?.name === input.timelineName)) {
      throw new Error("Prepared Media timeline creation target already exists.");
    }
    const stableId = opaque("timeline_", `${snapshot.projectId}:${input.timelineName}`);
    timelineTargets.push({
      id: stableId,
      name: input.timelineName,
      kind: "timeline",
      state: "absent",
      revision: `revision_${digest({projectId: snapshot.projectId, timelineName: input.timelineName, state: "absent"}).slice(7)}`,
    });
  }
  const targets = [...assets.map((asset) => ({id: asset.id, name: asset.name, kind: "asset"})),
    ...folders.map((folder) => ({id: folder.id, name: folder.name, path: folder.path, kind: "folder"})),
    ...timelineTargets,
    ...Object.values(artifacts).map((artifact) => ({id: artifact.stableId, kind: "artifact"}))];
  if (targets.length === 0) throw new Error("Prepared Media mutation resolved no exact target.");
  if (actionId === "cutagent.action.media.create_timeline" && targets.length > 1001) {
    throw new Error("Prepared Media timeline creation exceeds its bounded 1,000-source authority.");
  }
  if (actionId !== "cutagent.action.media.create_timeline" && targets.length > 1000) {
    throw new Error("Prepared Media mutation exceeds the bounded 1,000-target authority.");
  }
  return {operation: "generic", revision: snapshot.revision, targets, handlerInput, artifacts};
}

function exactTargets(actionId, input, binding) {
  if (actionId.startsWith("cutagent.action.media.")) {
    const target = binding.mediaTargets?.[actionId];
    if (!target || typeof target.stableId !== "string" || typeof target.revision !== "string") {
      throw new Error("Prepared Media Pool mutation requires one exact stable target binding.");
    }
    return [target];
  }
  if (actionId !== "cutagent.action.render.delete") {
    return [{stableId: binding.projectId, revision: binding.projectRevision}];
  }
  if (!Array.isArray(binding.renderJobs)) {
    throw new Error("Prepared render deletion requires exact stable render-job bindings.");
  }
  const rows = binding.renderJobs.filter((row) => row
    && typeof row.jobId === "string" && /^render_job_[A-Za-z0-9._~-]+$/.test(row.jobId)
    && typeof row.revision === "string" && row.revision.startsWith("revision_"));
  if (rows.length !== binding.renderJobs.length
    || new Set(rows.map((row) => row.jobId)).size !== rows.length) {
    throw new Error("Prepared render deletion received ambiguous stable render-job bindings.");
  }
  const selected = input.selection.kind === "all"
    ? [...rows].sort((left, right) => left.jobId.localeCompare(right.jobId))
    : rows.filter((row) => row.jobId === input.selection.jobId);
  if (selected.length === 0 || (input.selection.kind === "job" && selected.length !== 1)) {
    throw new Error("Prepared render deletion target is absent from the exact queue snapshot.");
  }
  return selected.map((row) => ({stableId: row.jobId, revision: row.revision}));
}

function builder(actionId, mutationPolicyGate, requestBindingAuthority) {
  return Object.freeze({
    inputSchema: inputSchema(actionId),
    mutationBinding: Object.freeze({
      minimumBinding: "project",
      referencedPayloadDigests: Object.freeze([]),
    }),
    async buildRequest({context, input}) {
      const scope = exactProjectScope(mutationPolicyGate, context.accountFingerprint);
      if (typeof requestBindingAuthority?.capture !== "function") {
        throw new Error("Prepared project/render mutation requires carrier-owned identity capture.");
      }
      const binding = await requestBindingAuthority.capture({
        actionId,
        accountFingerprint: context.accountFingerprint,
        requestId: context.requestId,
        operationId: context.operationId,
        executionId: context.executionId,
        scope: structuredClone(scope),
        input: structuredClone(input),
      });
      if (binding?.projectLibraryId !== scope.binding.projectLibraryId
        || typeof binding?.projectLibraryRevision !== "string"
        || binding?.projectId !== scope.binding.projectId
        || binding?.projectRevision !== scope.binding.projectRevision) {
        throw new Error("Prepared project/render live identity capture drifted from the exact scope.");
      }
      const targets = exactTargets(actionId, input, binding);
      return {
        protocolVersion: 1,
        actionId,
        actionContractVersion: 1,
        input,
        contractDigest: CUTAGENT_PREPARED_ACTION_CONTRACT_DIGEST,
        capabilityDigest: CUTAGENT_PREPARED_ACTION_CAPABILITY_DIGEST,
        identities: {
          projectLibraryId: binding.projectLibraryId,
          projectId: binding.projectId,
          timelineId: null,
          targetIds: targets.map((target) => target.stableId),
        },
        revisions: {
          projectLibrary: binding.projectLibraryRevision,
          project: binding.projectRevision,
          timeline: null,
          targets: Object.fromEntries(targets.map((target) => [target.stableId, target.revision])),
        },
        idempotencyKey: context.idempotencyKey,
        requestId: context.requestId,
        operationId: context.operationId,
        executionId: context.executionId,
      };
    },
  });
}

export function buildProjectRenderStorageMediaPreparedActionBuilders({
  mutationPolicyGate,
  requestBindingAuthority,
} = {}) {
  return Object.freeze(Object.fromEntries(
    PROJECT_RENDER_STORAGE_MEDIA_PREPARED_ACTION_IDS.map((actionId) => [
      actionId,
      builder(actionId, mutationPolicyGate, requestBindingAuthority),
    ]),
  ));
}

/** Production contribution for project mutations with exact private native identity custody. */
export function createProjectPreparedActionBuilderContributions({
  mutationPolicyGate,
  directMutationPolicyAuthority,
  liveInspectionService,
  artifactService,
  projectLibraryDestinationService,
  secretDir,
} = {}) {
  if (typeof liveInspectionService?.readWithMutationGuard !== "function") {
    throw new TypeError("Prepared project mutations require live DaVinci Resolve inspection.");
  }
  return Object.freeze(Object.fromEntries(PROJECT_PRODUCTION_PREPARED_ACTION_IDS.map((actionId) => {
    const payloadDigests = new Map();
    return [actionId, Object.freeze({
    inputSchema: inputSchema(actionId),
    mutationBinding: actionId.startsWith("cutagent.action.project.")
      ? Object.freeze({
        minimumBinding: actionId === "cutagent.action.project.open" ? "account/project-library" : "project",
        async resolveReferencedPayloadDigests({request}) {
          const digests = payloadDigests.get(request.operationId);
          payloadDigests.delete(request.operationId);
          if (!digests) throw new Error(`Prepared Project action lost managed payload custody: ${actionId}`);
          return [...digests];
        },
      })
      : Object.freeze({minimumBinding: "project", referencedPayloadDigests: Object.freeze([])}),
    async captureRequestBinding({context, input}) {
      const inspected = await liveInspectionService.readWithMutationGuard({
        operation: PROJECT_MANAGER_CUSTODY_ACTION_IDS.includes(actionId)
          ? "project.folder_context"
          : PROJECT_LIBRARY_CUSTODY_ACTION_IDS.includes(actionId)
            ? "project.library_context"
            : "project.context",
      });
      const value = inspected?.value;
      const privateIdentity = inspected?.privateExecutionIdentity;
      const nativeProjectLibrary = privateIdentity?.nativeProjectLibrary;
      const projectOpen = actionId === "cutagent.action.project.open";
      if (typeof privateIdentity?.projectLibraryId !== "string"
        || typeof inspected?.mutationGuard !== "string"
        || !nativeProjectLibrary || typeof nativeProjectLibrary !== "object"
        || (!projectOpen && (typeof value?.project?.id !== "string"
          || typeof value?.projectRevision?.revision !== "string"
          || typeof privateIdentity?.nativeProjectId !== "string" || !privateIdentity.nativeProjectId))) {
        throw new Error("Prepared project mutation live identity is incomplete.");
      }
      const minimumBinding = projectOpen ? "account/project-library" : "project";
      const directScope = await resolveSdkPreparedMutationScope({
        directMutationPolicyAuthority, mutationPolicyGate, context, minimumBinding,
        binding: {projectLibraryId: privateIdentity?.projectLibraryId, projectId: value?.project?.id, projectRevision: value?.projectRevision?.revision},
      });
      const scope = projectOpen
        ? exactProjectLibraryScope(mutationPolicyGate, context.accountFingerprint, directScope)
        : exactProjectScope(mutationPolicyGate, context.accountFingerprint, directScope);
      if (privateIdentity?.projectLibraryId !== scope.binding.projectLibraryId
        || (!projectOpen && (value?.project?.id !== scope.binding.projectId
          || value?.projectRevision?.revision !== scope.binding.projectRevision))) {
        throw new Error("Prepared project mutation live identity drifted from the exact scope.");
      }
      let targetId = value?.project?.id ?? null;
      let targetRevision = value?.projectRevision?.revision ?? null;
      let mediaBinding = null;
      let exactProjectTargets = null;
      let projectManagerBinding = null;
      let projectLibraryBinding = null;
      let projectLibraryDestination = null;
      if (PROJECT_MANAGER_CUSTODY_ACTION_IDS.includes(actionId)) {
        if (typeof liveInspectionService.readProjectInventory !== "function") {
          throw new Error("Prepared Project Manager mutation requires exact project inventory inspection.");
        }
        const projectInventory = await liveInspectionService.readProjectInventory();
        const confirmed = await liveInspectionService.readWithMutationGuard({operation: "project.folder_context"});
        if (confirmed?.mutationGuard !== inspected.mutationGuard
          || JSON.stringify(canonical(confirmed?.value)) !== JSON.stringify(canonical(value))
          || JSON.stringify(canonical(confirmed?.privateExecutionIdentity)) !== JSON.stringify(canonical(privateIdentity))) {
          throw new Error("Project Manager custody changed during exact inventory capture.");
        }
        projectManagerBinding = projectManagerCustody(
          privateIdentity.projectLibraryId,
          nativeProjectLibrary,
          privateIdentity.nativeProjectFolder,
          projectInventory,
          actionId,
          input,
        );
        if (actionId === "cutagent.action.project.open" && input.project) {
          const [target] = projectManagerBinding.targets;
          if (input.project?.id !== target?.stableId || input.project?.name !== target?.name) {
            throw new Error("Prepared Project open input does not match its exact inventory target.");
          }
        }
        exactProjectTargets = projectManagerBinding.targets.map(({stableId, revision}) => ({stableId, revision}));
        if (projectOpen) {
          targetId = exactProjectTargets[0].stableId;
          targetRevision = exactProjectTargets[0].revision;
        }
      } else if (PROJECT_LIBRARY_CUSTODY_ACTION_IDS.includes(actionId)) {
        if (["cutagent.action.project.library.create", "cutagent.action.project.library.restore"].includes(actionId)) {
          if (typeof projectLibraryDestinationService?.reserve !== "function") {
            throw new Error("Prepared project-library creation requires durable destination custody.");
          }
        }
        const rawInventory = privateIdentity.nativeProjectLibraries;
        if (["cutagent.action.project.library.create", "cutagent.action.project.library.restore"].includes(actionId)) {
          const normalizedInventory = normalizedProjectLibraryInventory(rawInventory);
          if (normalizedInventory.databases.some((row) => row.database.DbType === "Disk" && row.database.DbName === input.libraryName)) {
            throw new Error("Prepared Disk project-library destination name already exists.");
          }
          const namespaceRevision = normalizedInventory.inventoryRevision;
          projectLibraryDestination = projectLibraryDestinationService.reserve({operationId: context.operationId, accountFingerprint: context.accountFingerprint,
            libraryName: input.libraryName, directoryPath: input.directoryPath, namespaceRevision});
        }
        projectLibraryBinding = projectLibraryCustody(rawInventory, actionId, input, projectLibraryDestination);
        exactProjectTargets = [{
          stableId: projectLibraryBinding.target.stableId,
          revision: projectLibraryBinding.target.revision,
        }];
      } else if (actionId.startsWith("cutagent.action.media.")) {
        const snapshot = await exactMediaPoolSnapshot(liveInspectionService, value.project.id);
        if (["cutagent.action.media.folders.create", "cutagent.action.media.folders.delete"].includes(actionId)) {
          if ("projectId" in input && input.projectId !== value.project.id) throw new Error("Prepared Media Pool input belongs to another project.");
          if ("precondition" in input && snapshot.revision !== input.precondition) throw new Error("Prepared Media Pool input revision is stale.");
          mediaBinding = exactFolderBinding(snapshot, actionId, input);
          targetId = mediaBinding.operation === "create" ? mediaBinding.parentId : mediaBinding.targetId;
          targetRevision = snapshot.revision;
        } else if ("assetId" in input && !MEDIA_PENDING_PREPARED_ACTION_IDS.includes(actionId)) {
          if (input.projectId !== value.project.id) throw new Error("Prepared Media Pool input belongs to another project.");
          const matches = snapshot.assets.filter((asset) => asset.id === input.assetId);
          if (matches.length !== 1) throw new Error("Prepared Media Pool durable target is missing or ambiguous.");
          if (snapshot.revision !== input.precondition) throw new Error("Prepared Media Pool input revision is stale.");
          targetId = input.assetId;
          targetRevision = snapshot.revision;
          mediaBinding = {operation: "asset", targetId, parentId: null, targetPath: null, targetName: matches[0].name};
        } else if (!MEDIA_PENDING_PREPARED_ACTION_IDS.includes(actionId)) {
          const name = input.operation?.clipName ?? input.name ?? input.clip;
          const matches = snapshot.assets.filter((asset) => asset.name === name && typeof asset.id === "string");
          if (matches.length !== 1) throw new Error("Prepared Media Pool target name is missing or ambiguous.");
          targetId = matches[0].id;
          targetRevision = snapshot.revision;
          mediaBinding = {operation: "asset", targetId, parentId: null, targetPath: null, targetName: matches[0].name};
        } else {
          if ("projectId" in input && input.projectId !== value.project.id) throw new Error("Prepared Media Pool input belongs to another project.");
          if ("precondition" in input && input.precondition !== snapshot.revision) throw new Error("Prepared Media Pool input revision is stale.");
          let bindingSnapshot = snapshot;
          if (actionId === "cutagent.action.media.create_timeline") {
            if (typeof liveInspectionService.read !== "function") {
              throw new Error("Prepared Media timeline creation requires Timeline inventory inspection.");
            }
            const timelines = await liveInspectionService.read({
              operation: "timeline.list",
              projectId: value.project.id,
              expectedRevision: value.projectRevision.revision,
            });
            bindingSnapshot = {...snapshot, projectId: value.project.id, timelines};
          }
          mediaBinding = genericMediaBinding(bindingSnapshot, actionId, input, context, {artifactService, secretDir});
          const targetIds = mediaBinding.targets.map(({id}) => id);
          if (new Set(targetIds).size !== targetIds.length) throw new Error("Prepared Media targets are not exact and unique.");
          return {
            identities: {
              projectLibraryId: privateIdentity.projectLibraryId,
              projectId: value.project.id,
              timelineId: null,
              targetIds,
            },
            revisions: {
              projectLibrary: inspected.mutationGuard,
              project: value.projectRevision.revision,
              timeline: null,
              targets: Object.fromEntries(targetIds.map((id) => {
                const boundTarget = mediaBinding.targets.find((target) => target.id === id);
                return [id, id.startsWith("artifact_")
                  ? Object.values(mediaBinding.artifacts).find((artifact) => artifact.stableId === id).revision
                  : boundTarget?.revision ?? snapshot.revision];
              })),
            },
            privateContext: {
              project: {nativeProjectId: privateIdentity.nativeProjectId, nativeProjectLibrary: structuredClone(nativeProjectLibrary)},
              mediaPool: mediaBinding,
            },
          };
        }
        mediaBinding = {...mediaBinding, revision: snapshot.revision};
      } else if (actionId.startsWith("cutagent.action.project.library.")) {
        const name = input.library?.name ?? input.libraryName ?? value.library?.name;
        exactProjectTargets = [namedLibraryTarget(privateIdentity.projectLibraryId, name)];
      } else if (["cutagent.action.project.import", "cutagent.action.project.restore"].includes(actionId)) {
        exactProjectTargets = [namedLibraryTarget(privateIdentity.projectLibraryId, privateIdentity.projectLibraryId)];
      } else {
        const names = projectTargetNames(actionId, input, value);
        if (names.length) exactProjectTargets = names.map((name) => namedProjectTarget(privateIdentity.projectLibraryId, value.project, name, value.projectRevision.revision));
      }
      let artifact;
      try {
        artifact = await captureProjectArtifact(artifactService, actionId, input, context);
      } catch (error) {
        if (projectLibraryDestination) {
          projectLibraryDestinationService.settleTerminal({operationId: context.operationId, accountFingerprint: context.accountFingerprint, terminal: {status: "failed"}});
        }
        throw error;
      }
      const targets = exactProjectTargets ?? [{stableId: targetId, revision: targetRevision}];
      if (artifact) targets.push({stableId: artifact.artifactId, revision: artifact.revision});
      const referencedPayloadDigests = artifact?.payloadDigest ? [artifact.payloadDigest] : [];
      if (referencedPayloadDigests.some((payloadDigest) => !/^sha256:[a-f0-9]{64}$/u.test(payloadDigest))) {
        throw new Error(`Prepared Project action captured a malformed payload digest: ${actionId}`);
      }
      payloadDigests.set(context.operationId, Object.freeze([...referencedPayloadDigests]));
      return {
        identities: {
          projectLibraryId: privateIdentity.projectLibraryId,
          projectId: targetId,
          timelineId: null,
          targetIds: targets.map((target) => target.stableId),
        },
        revisions: {
          projectLibrary: inspected.mutationGuard,
          project: targetRevision,
          timeline: null,
          targets: Object.fromEntries(targets.map((target) => [target.stableId, target.revision])),
        },
        privateContext: {
          project: {
            nativeProjectId: projectOpen ? projectManagerBinding.targets[0].nativeId : privateIdentity.nativeProjectId,
            nativeProjectLibrary: structuredClone(nativeProjectLibrary),
          },
          privateManagedArtifacts: artifact ? {[artifact.artifactId]: artifact.record} : {},
          ...(artifact ? {privateArtifactStoreRoot: artifact.root} : {}),
          ...(mediaBinding ? {mediaPool: mediaBinding} : {}),
          ...(projectManagerBinding ? {projectManager: projectManagerBinding} : {}),
          ...(projectLibraryBinding ? {projectLibraries: projectLibraryBinding} : {}),
          ...(projectLibraryDestination ? {projectLibraryDestination} : {}),
        },
      };
    },
  })];
  })));
}

/** Production contribution for render-setting mutations with exact project custody. */
export function createRenderPreparedActionBuilderContributions({
  mutationPolicyGate,
  directMutationPolicyAuthority,
  liveInspectionService,
} = {}) {
  if (typeof liveInspectionService?.readWithMutationGuard !== "function") {
    throw new TypeError("Prepared render mutations require live DaVinci Resolve inspection.");
  }
  return Object.freeze(Object.fromEntries(RENDER_PRODUCTION_PREPARED_ACTION_IDS.map((actionId) => [actionId, Object.freeze({
    inputSchema: inputSchema(actionId),
    mutationBinding: Object.freeze({minimumBinding: "project", referencedPayloadDigests: Object.freeze([])}),
    async captureRequestBinding({context}) {
      const inspected = await liveInspectionService.readWithMutationGuard({operation: "project.context"});
      const value = inspected?.value;
      const privateIdentity = inspected?.privateExecutionIdentity;
      const nativeProjectLibrary = privateIdentity?.nativeProjectLibrary;
      if (typeof privateIdentity?.projectLibraryId !== "string" || typeof value?.project?.id !== "string"
        || typeof value?.projectRevision?.revision !== "string") {
        throw new Error("Prepared render mutation live identity is incomplete.");
      }
      const directScope = await resolveSdkPreparedMutationScope({
        directMutationPolicyAuthority, mutationPolicyGate, context, minimumBinding: "project",
        binding: {projectLibraryId: privateIdentity?.projectLibraryId, projectId: value?.project?.id, projectRevision: value?.projectRevision?.revision},
      });
      const scope = exactProjectScope(mutationPolicyGate, context.accountFingerprint, directScope);
      if (value?.project?.id !== scope.binding.projectId
        || value?.projectRevision?.revision !== scope.binding.projectRevision
        || privateIdentity?.projectLibraryId !== scope.binding.projectLibraryId
        || typeof inspected?.mutationGuard !== "string"
        || typeof privateIdentity?.nativeProjectId !== "string" || !privateIdentity.nativeProjectId
        || !nativeProjectLibrary || typeof nativeProjectLibrary !== "object") {
        throw new Error("Prepared render mutation live identity drifted from the exact scope.");
      }
      return {
        identities: {
          projectLibraryId: privateIdentity.projectLibraryId,
          projectId: value.project.id,
          timelineId: null,
          targetIds: [value.project.id],
        },
        revisions: {
          projectLibrary: inspected.mutationGuard,
          project: value.projectRevision.revision,
          timeline: null,
          targets: {[value.project.id]: value.projectRevision.revision},
        },
        privateContext: {project: {
          nativeProjectId: privateIdentity.nativeProjectId,
          nativeProjectLibrary: structuredClone(nativeProjectLibrary),
        }},
      };
    },
  })])));
}
