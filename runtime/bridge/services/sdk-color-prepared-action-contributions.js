import crypto from "node:crypto";
import Ajv2020 from "ajv/dist/2020.js";
import {SDK_COLOR_PREPARED_INPUTS} from "../contracts/sdk-color-inputs.generated.js";
import {CUTAGENT_PREPARED_ACTION_ACTION_METADATA} from "../contracts/sdk-prepared-action-metadata.generated.js";
import {createSdkPreparedActionBuilderContribution} from "./sdk-prepared-action-carrier.js";

const ajv = new Ajv2020({allErrors: true, strict: true});

export const COLOR_EXACT_READ_ACTION_IDS = Object.freeze([
  "cutagent.action.color.comp.doctor", "cutagent.action.color.fx.list",
  "cutagent.action.color.graph.inspect", "cutagent.action.color.graph.validate",
  "cutagent.action.color.inspect", "cutagent.action.color.mask.inspect",
  "cutagent.action.color.node.graph", "cutagent.action.color.node.list",
  "cutagent.action.color.nodes", "cutagent.action.color.page.qualifier_panel_probe",
  "cutagent.action.color.page.read", "cutagent.action.color.page.resolvefx_list",
  "cutagent.action.color.power_grade.list", "cutagent.action.color.primary.get",
  "cutagent.action.color.qualifier.list", "cutagent.action.color.tracker.list",
  "cutagent.action.color.version.list", "cutagent.action.color.window.list",
]);

export const COLOR_EXISTING_SEMANTIC_ACTION_IDS = Object.freeze([
  "cutagent.action.color.grade_apply", "cutagent.action.color.node.label_set",
  "cutagent.action.color.page.node_add", "cutagent.action.color.page.primary_set",
  "cutagent.action.color.page.resolvefx_add",
]);
export const COLOR_ARTIFACT_BACKED_ACTION_IDS = Object.freeze(Object.entries(SDK_COLOR_PREPARED_INPUTS)
  .filter(([, schema]) => Object.keys(schema.properties ?? {}).some((field) => field.endsWith("ArtifactId")))
  .map(([actionId]) => actionId));
export const COLOR_PREPARED_ACTION_IDS = Object.freeze(Object.keys(SDK_COLOR_PREPARED_INPUTS));
export const COLOR_VERSION_SELECTOR_PENDING_ACTION_IDS = Object.freeze([]);
const UNBOUND_SELECTOR_FIELDS = new Set(["stillSelector", "qualifierName", "trackerName", "versionName", "windowName"]);
export const COLOR_EXACT_SELECTOR_PENDING_ACTION_IDS = Object.freeze(COLOR_PREPARED_ACTION_IDS.filter((actionId) => (
  !COLOR_ARTIFACT_BACKED_ACTION_IDS.includes(actionId)
  && (actionId.includes(".group.")
    || actionId.includes(".gallery.")
    || actionId === "cutagent.action.color.power_grade.album.create"
    || Object.keys(SDK_COLOR_PREPARED_INPUTS[actionId].properties ?? {}).some((field) => UNBOUND_SELECTOR_FIELDS.has(field)))
)));
export const COLOR_SAFE_PREPARED_ACTION_IDS = Object.freeze(COLOR_PREPARED_ACTION_IDS.filter((actionId) => (
  !COLOR_ARTIFACT_BACKED_ACTION_IDS.includes(actionId)
  && !COLOR_EXISTING_SEMANTIC_ACTION_IDS.includes(actionId)
  && !COLOR_VERSION_SELECTOR_PENDING_ACTION_IDS.includes(actionId)
)));
export const COLOR_REVIEWED_VISUAL_ARTIFACT_ACTION_IDS = Object.freeze(COLOR_ARTIFACT_BACKED_ACTION_IDS.filter(
  (actionId) => !COLOR_EXISTING_SEMANTIC_ACTION_IDS.includes(actionId),
));

const HANDLE_PREFIX = Object.freeze({groups: "group_", albums: "album_", stills: "still_", powerGrades: "color_entity_", powerGradeAlbums: "album_", qualifiers: "color_entity_", trackers: "color_entity_", windows: "color_entity_", versions: "color_entity_"});
const COLOR_SOURCE_ARTIFACT_FIELDS = new Set(["sourceArtifactId"]);

function artifactExtension(actionId, field, input) {
  if (field === "destinationArtifactId" && typeof input.format === "string") return input.format.toLowerCase();
  if (actionId.includes("comp.export")) return "setting";
  if (actionId.includes("export_lut") || actionId.endsWith(".curves") || actionId.endsWith(".wheels.set")) return "cube";
  if (actionId.includes("gallery.still.export")) return input.format === "dpx" ? "dpx" : "drx";
  return field === "contactSheetArtifactId" ? "jpg" : "png";
}

async function captureColorArtifacts(actionId, input, context, artifactService) {
  const requests = Object.keys(SDK_COLOR_PREPARED_INPUTS[actionId]?.properties ?? {})
    .filter((field) => field.endsWith("ArtifactId") && typeof input[field] === "string")
    .map((field) => ({field, artifactId: input[field], source: COLOR_SOURCE_ARTIFACT_FIELDS.has(field)}));
  if (!requests.length) return {records: {}, targets: [], referencedPayloadDigests: []};
  if (typeof artifactService?.capturePrivateManagedArtifact !== "function"
    || typeof artifactService?.reservePrivateOutputArtifact !== "function") {
    throw new Error(`Color action requires private managed-artifact custody: ${actionId}`);
  }
  const records = {};
  const targets = [];
  const referencedPayloadDigests = [];
  for (const request of requests) {
    const captured = request.source
      ? await artifactService.capturePrivateManagedArtifact({artifactId: request.artifactId, accountFingerprint: context.accountFingerprint})
      : await artifactService.reservePrivateOutputArtifact({
        artifactId: request.artifactId, operationId: context.operationId,
        accountFingerprint: context.accountFingerprint, extension: artifactExtension(actionId, request.field, input),
      });
    if (captured?.artifactId !== request.artifactId || typeof captured.absolutePath !== "string") {
      throw new Error(`Color managed-artifact capture is incomplete: ${actionId}`);
    }
    const revision = `revision_${crypto.createHash("sha256").update(JSON.stringify({
      artifactId: request.artifactId,
      identity: captured.identity,
      digest: request.source ? captured.sha256 : "reserved-output",
    })).digest("hex")}`;
    records[request.artifactId] = request.source
      ? {path: captured.absolutePath, sha256: captured.sha256, byteCount: captured.sizeBytes, identity: captured.identity}
      : {path: captured.absolutePath, reservationId: context.operationId, reservationIdentity: captured.identity, overwrite: true};
    targets.push({stableId: request.artifactId, revision});
    if (request.source) referencedPayloadDigests.push(captured.sha256);
  }
  return {records, targets, referencedPayloadDigests};
}

function selectorHandle({kind, ordinal, label, parent, revision}) {
  const prefix = HANDLE_PREFIX[kind];
  if (!prefix || !Number.isSafeInteger(ordinal) || ordinal < 1 || typeof label !== "string" || !label || typeof revision !== "string" || !revision) {
    throw new Error("Color selector inventory cannot produce an exact snapshot handle.");
  }
  const digest = crypto.createHash("sha256").update(JSON.stringify({kind, ordinal, label, parent, revision}), "utf8").digest("base64url");
  return `${prefix}f${digest}`;
}

function selectorLabel(row) {
  for (const key of ["label", "name", "version_name", "versionName", "album", "still"]) {
    if (typeof row?.[key] === "string" && row[key].trim()) return row[key].trim();
  }
  return null;
}

function selectorOrdinal(row, fallback) {
  for (const key of ["index", "order", "position"]) {
    if (Number.isSafeInteger(row?.[key]) && row[key] > 0) return row[key];
  }
  return fallback;
}

function selectorInventoryRevision(kind, rows) {
  const items = rows.map((row, index) => ({
    ordinal: selectorOrdinal(row, index + 1),
    label: selectorLabel(row),
  }));
  const digest = crypto.createHash("sha256").update(JSON.stringify({kind, items}), "utf8").digest("hex");
  return `revision_color_selector_${digest}`;
}

function addInventoryBindings(bindings, {kind, rows, parent, rejectDuplicateLabels}) {
  const labels = rows.map(selectorLabel);
  if (kind !== "stills" && labels.some((label) => label == null)) throw new Error(`Color ${kind} inventory omitted a label.`);
  if (kind !== "stills" && rejectDuplicateLabels && new Set(labels).size !== labels.length) throw new Error(`Color ${kind} inventory contains duplicate labels.`);
  const revision = selectorInventoryRevision(kind, rows);
  rows.forEach((row, index) => {
    const ordinal = selectorOrdinal(row, index + 1);
    const inventoryLabel = labels[index] ?? "";
    const selector = kind === "stills" ? String(ordinal) : inventoryLabel;
    const stableId = selectorHandle({kind, ordinal, label: selector, parent, revision});
    bindings[stableId] = {
      kind: kind === "qualifiers" || kind === "trackers" || kind === "windows" || kind === "versions" ? "fusion_composition" : "media",
      stableId, selector, collectionKind: kind, ordinal, parent: structuredClone(parent), capturedRevision: revision,
      ...(kind === "stills" ? {inventoryLabel} : {}),
      ...(row.current === true ? {current: true} : {}),
    };
  });
}

function requiredInventories(actionId, input) {
  const kinds = new Set();
  if (actionId.includes(".group.")) kinds.add("groups");
  if (actionId.includes(".gallery.album.")) kinds.add("albums");
  if (actionId.includes(".gallery.still.")) { kinds.add("albums"); kinds.add("stills"); }
  if (actionId === "cutagent.action.color.page.still_match") { kinds.add("albums"); kinds.add("stills"); }
  if (actionId === "cutagent.action.color.power_grade.apply") kinds.add("powerGrades");
  if (actionId === "cutagent.action.color.power_grade.list") kinds.add("powerGrades");
  if (actionId === "cutagent.action.color.qualifier.list") kinds.add("qualifiers");
  if (actionId === "cutagent.action.color.tracker.list") kinds.add("trackers");
  if (actionId === "cutagent.action.color.window.list") kinds.add("windows");
  if (actionId === "cutagent.action.color.version.list") kinds.add("versions");
  if (typeof input.qualifierName === "string") kinds.add("qualifiers");
  if (typeof input.trackerName === "string") kinds.add("trackers");
  if (typeof input.windowName === "string") kinds.add("windows");
  if ([
    "cutagent.action.color.version.activate",
    "cutagent.action.color.version.delete",
    "cutagent.action.color.version.load",
    "cutagent.action.color.version.rollback",
  ].includes(actionId)) kinds.add("versions");
  return kinds;
}

function operationClass(actionId) {
  const value = CUTAGENT_PREPARED_ACTION_ACTION_METADATA[actionId]?.operationClass;
  if (!new Set(["read", "mutation"]).has(value)) throw new Error(`Color action operation class is unavailable: ${actionId}`);
  return value;
}

function inputSchema(actionId) {
  const schema = SDK_COLOR_PREPARED_INPUTS[actionId];
  if (!schema) throw new Error(`Prepared-action input schema is unavailable: ${actionId}`);
  const validate = ajv.compile(schema);
  return Object.freeze({
    parse(value) {
      if (!validate(value)) {
        const error = new TypeError(`Prepared-action input violated its exact schema: ${actionId}`);
        error.validationErrors = structuredClone(validate.errors ?? []);
        throw error;
      }
      return structuredClone(value);
    },
  });
}

function exactProjectContext(inspected) {
  const value = inspected?.value;
  const projectLibraryId = inspected?.privateExecutionIdentity?.projectLibraryId;
  const projectLibraryRevision = inspected?.mutationGuard;
  const projectId = value?.project?.id;
  const projectRevision = value?.projectRevision?.revision;
  if (![projectLibraryId, projectLibraryRevision, projectId, projectRevision].every((item) => typeof item === "string" && item)) {
    throw new Error("Color prepared read lost its exact project identity.");
  }
  return {projectLibraryId, projectLibraryRevision, projectId, projectRevision};
}

function sameProject(left, right) {
  return Object.keys(left).every((key) => left[key] === right[key]);
}

function timelineRows(timeline) {
  return (timeline?.tracks ?? []).flatMap((track) => (track.clips ?? [])
    .filter((clip) => track.type === "video" || track.type === undefined).map((clip) => ({track, clip})));
}

function clipBinding(row, nativeId) {
  if (typeof nativeId !== "string" || !nativeId || !Number.isSafeInteger(row.track.index) || row.track.index < 1
    || typeof row.clip.name !== "string" || !row.clip.name) throw new Error("Color prepared action lacks an exact private clip binding.");
  return {kind: "clip", selector: row.clip.name, stableId: row.clip.id, nativeId, trackIndex: row.track.index};
}

async function captureExactColorAction(actionId, input, context, dependencies) {
  const artifacts = await captureColorArtifacts(actionId, input, context, dependencies.artifactService);
  const liveInspectionService = dependencies.liveInspectionService;
  const projectBefore = exactProjectContext(await liveInspectionService.readWithMutationGuard({operation: "project.context"}));
  const projectId = input.projectId ?? projectBefore.projectId;
  if (projectBefore.projectId !== projectId) throw new Error("Color prepared action project identity is stale.");
  const hasTimeline = typeof input.timelineId === "string";
  const pluralLutItems = actionId === "cutagent.action.color.lut" && Array.isArray(input.items) ? input.items : null;
  const requestedTimelineItemIds = pluralLutItems?.map(({timelineItemId}) => timelineItemId)
    ?? (typeof input.timelineItemId === "string" ? [input.timelineItemId] : []);
  const nodeStackLayerIndex = pluralLutItems?.[0]?.nodeStackLayerIndex ?? input.nodeStackLayerIndex ?? 1;
  const colorRead = hasTimeline ? await liveInspectionService.readWithMutationGuard({operation: "color.current", projectId, timelineId: input.timelineId, nodeStackLayerIndex}) : null;
  const timelineRead = hasTimeline ? await liveInspectionService.readWithMutationGuard({operation: "timeline.snapshot", projectId, timelineId: input.timelineId}) : null;
  const color = colorRead?.value ?? null;
  const timeline = timelineRead?.value ?? null;
  if (hasTimeline) {
    const identityDrift = [
      ...(color?.project?.id !== projectId ? ["color_project"] : []),
      ...(color?.timeline?.id !== input.timelineId ? ["color_timeline"] : []),
      ...(!pluralLutItems && color?.clip?.id !== input.timelineItemId ? ["color_clip"] : []),
      ...(timeline?.project?.id !== projectId ? ["timeline_project"] : []),
      ...(timeline?.timeline?.id !== input.timelineId ? ["timeline"] : []),
      ...(typeof color?.revision !== "string" ? ["color_revision_missing"] : []),
      ...(typeof color?.timelineRevision !== "string" ? ["color_timeline_revision_missing"] : []),
      ...(typeof timeline?.revision !== "string" ? ["timeline_revision_missing"] : []),
    ];
    if (identityDrift.length > 0) {
      throw new Error(`Color prepared read identity changed during capture: ${identityDrift.join(",")}.`);
    }
  }
  const timelineRevision = timeline?.revision ?? null;
  const colorTimelineRevision = color?.timelineRevision ?? null;
  const colorRevision = color?.revision ?? null;
  if (operationClass(actionId) === "mutation") {
    const revisionPrecondition = hasTimeline ? timelineRevision : projectBefore.projectRevision;
    if (typeof input.revision === "string" && input.revision !== revisionPrecondition) throw new Error("Color prepared action revision is stale.");
    if (!pluralLutItems && typeof input.colorRevision === "string" && input.colorRevision !== colorRevision) throw new Error("Color prepared action Color revision is stale.");
  }
  const rows = hasTimeline ? timelineRows(timeline) : [];
  const nativeIds = timelineRead?.privateTimelineItemNativeIdByPublicId ?? new Map();
  const privateTargetBindings = {};
  const privateSelectorBindings = {};
  const privateNamedClipBindings = {};
  for (const row of rows) {
    const binding = clipBinding(row, nativeIds.get(row.clip.id));
    const {stableId: _stableId, ...targetBinding} = binding;
    privateTargetBindings[row.clip.id] = targetBinding;
    const duplicateNames = rows.filter((candidate) => candidate.clip.name === row.clip.name);
    if (duplicateNames.length === 1) {
      privateSelectorBindings[row.clip.name] = binding;
      privateNamedClipBindings[row.clip.name] = binding;
    }
  }
  if (hasTimeline && requestedTimelineItemIds.some((stableId) => !privateTargetBindings[stableId])) {
    throw new Error("Color prepared action target is absent or ambiguous.");
  }
  const inventoryReader = dependencies.resolveService?.readSdkColorSelectorInventory;
  const inventoryKinds = requiredInventories(actionId, input);
  if (inventoryKinds.size && typeof inventoryReader !== "function") throw new Error("Color prepared action requires exact selector inventory custody.");
  const projectParent = {projectId, timelineId: null, timelineItemId: null, compositionIndex: null};
  const timelineParent = {projectId, timelineId: input.timelineId ?? null, timelineItemId: input.timelineItemId ?? null, compositionIndex: input.compIndex ?? null};
  let selectedAlbum = null;
  let selectedAlbumId = null;
  for (const kind of inventoryKinds) {
    if (kind === "stills") {
      const albumRecord = privateSelectorBindings[input.albumId]
        ?? Object.values(privateSelectorBindings).find((record) => record.collectionKind === "albums" && record.current === true)
        ?? Object.values(privateSelectorBindings).find((record) => record.collectionKind === "albums");
      selectedAlbum = albumRecord?.selector ?? null;
      selectedAlbumId = albumRecord?.stableId ?? null;
      if (!selectedAlbum) throw new Error("Color still inventory has no exact parent album binding.");
    }
    const clip = hasTimeline ? privateTargetBindings[input.timelineItemId]?.selector : null;
    const rows = await inventoryReader({kind, album: selectedAlbum, clip, compIndex: input.compIndex ?? 1});
    const selectorParent = ["qualifiers", "trackers", "windows", "versions"].includes(kind) ? timelineParent : projectParent;
    addInventoryBindings(privateSelectorBindings, {
      kind, rows,
      parent: {...selectorParent, ...(kind === "stills" ? {albumId: input.albumId ?? selectedAlbumId} : {})},
      rejectDuplicateLabels: operationClass(actionId) === "mutation",
    });
  }
  if ([
    "cutagent.action.color.version.activate",
    "cutagent.action.color.version.delete",
    "cutagent.action.color.version.load",
    "cutagent.action.color.version.rollback",
  ].includes(actionId)) {
    const matches = Object.values(privateSelectorBindings).filter((record) => (
      record.collectionKind === "versions" && record.selector === input.name
    ));
    if (matches.length !== 1) throw new Error("Color version name is absent or ambiguous in the exact snapshot.");
    privateSelectorBindings[input.name] = matches[0];
  }
  const selectorFields = ["groupId", "albumId", "stillId", "stillSelector", "qualifierName", "trackerName", "windowName"];
  if ([
    "cutagent.action.color.version.activate",
    "cutagent.action.color.version.delete",
    "cutagent.action.color.version.load",
    "cutagent.action.color.version.rollback",
  ].includes(actionId)) selectorFields.push("name");
  for (const field of selectorFields) {
    if (typeof input[field] === "string" && !privateSelectorBindings[input[field]]) throw new Error(`Color ${field} snapshot handle is stale or unavailable.`);
  }
  const selectedSelectorRecords = selectorFields
    .map((field) => privateSelectorBindings[input[field]])
    .filter((record, index, records) => record && records.findIndex((candidate) => candidate?.stableId === record.stableId) === index);
  if (hasTimeline) {
    const colorAfter = (await liveInspectionService.readWithMutationGuard({operation: "color.current", projectId, timelineId: input.timelineId, nodeStackLayerIndex}))?.value;
    const timelineAfter = (await liveInspectionService.readWithMutationGuard({operation: "timeline.snapshot", projectId, timelineId: input.timelineId}))?.value;
    if (colorAfter?.project?.id !== projectId || colorAfter?.timeline?.id !== input.timelineId
      || (!pluralLutItems && colorAfter?.clip?.id !== input.timelineItemId) || colorAfter?.timelineRevision !== colorTimelineRevision
      || colorAfter?.revision !== colorRevision || colorAfter?.nodeStackLayerIndex !== nodeStackLayerIndex
      || timelineAfter?.project?.id !== projectId || timelineAfter?.timeline?.id !== input.timelineId
      || timelineAfter?.revision !== timelineRevision) {
      throw new Error("Color prepared read identity changed during selector capture.");
    }
  }
  const projectAfter = exactProjectContext(await liveInspectionService.readWithMutationGuard({operation: "project.context"}));
  if (!sameProject(projectBefore, projectAfter)) throw new Error("Color prepared read identity changed during capture.");
  const primaryIds = requestedTimelineItemIds.length > 0
    ? requestedTimelineItemIds
    : [input.stillId ?? input.albumId ?? input.groupId ?? projectId];
  const targetRevision = hasTimeline ? timelineRevision : (input.revision ?? projectBefore.projectRevision);
  if (typeof targetRevision !== "string") throw new Error("Color prepared action lost its exact target revision.");
  const targetIds = [...new Set([
    ...primaryIds,
    ...selectedSelectorRecords.map(({stableId}) => stableId),
    ...artifacts.targets.map(({stableId}) => stableId),
  ])];
  const targetRevisions = {
    ...Object.fromEntries(primaryIds.map((stableId) => [stableId, targetRevision])),
    ...Object.fromEntries(selectedSelectorRecords.map(({stableId, capturedRevision}) => [stableId, capturedRevision])),
    ...Object.fromEntries(artifacts.targets.map(({stableId, revision}) => [stableId, revision])),
  };
  return {
    identities: {
      projectLibraryId: projectBefore.projectLibraryId,
      projectId,
      timelineId: input.timelineId ?? null,
      targetIds,
    },
    revisions: {
      projectLibrary: projectBefore.projectLibraryRevision,
      project: projectBefore.projectRevision,
      timeline: timelineRevision,
      targets: Object.fromEntries(targetIds.map((id) => [id, targetRevisions[id]])),
    },
    privateContext: {
      ...(hasTimeline ? {timeline: {mutationGuard: colorRead.mutationGuard}} : {}),
      privateTargetBindings,
      privateSelectorBindings,
      privateNamedClipBindings,
      privateAllTimelineItemIds: rows.map(({clip}) => clip.id),
      privateManagedArtifacts: artifacts.records,
      privateCreatedEntityIds: {},
    },
    referencedPayloadDigests: artifacts.referencedPayloadDigests,
  };
}

export function createColorPreparedActionBuilderContributions(dependencies = {}) {
  if (typeof dependencies.liveInspectionService?.readWithMutationGuard !== "function") {
    throw new TypeError("Color prepared actions require live DaVinci Resolve inspection.");
  }
  const available = COLOR_PREPARED_ACTION_IDS.filter((actionId) => (
    COLOR_SAFE_PREPARED_ACTION_IDS.includes(actionId)
    || COLOR_REVIEWED_VISUAL_ARTIFACT_ACTION_IDS.includes(actionId)
  ));
  const enabled = dependencies.enabledActionIds == null ? new Set(available) : dependencies.enabledActionIds;
  if (!(enabled instanceof Set) || [...enabled].some((actionId) => !available.includes(actionId))) {
    throw new Error("Color prepared-action selection contains an unavailable action.");
  }
  const payloadDigests = new Map();
  return Object.freeze(Object.fromEntries(available.filter((actionId) => enabled.has(actionId)).map((actionId) => [
    actionId,
    createSdkPreparedActionBuilderContribution({
      inputSchema: inputSchema(actionId),
      ...(operationClass(actionId) === "mutation" ? {mutationBinding: Object.freeze({
        minimumBinding: SDK_COLOR_PREPARED_INPUTS[actionId].properties?.timelineId ? "project+timeline" : "project",
        async resolveReferencedPayloadDigests({request}) {
          const value = payloadDigests.get(request.operationId);
          payloadDigests.delete(request.operationId);
          if (!value) throw new Error(`Color action lost referenced payload custody: ${actionId}`);
          return [...value];
        },
      })} : {}),
      async captureRequestBinding({context = {}, input}) {
        const captured = await captureExactColorAction(actionId, input, context, dependencies);
        if (operationClass(actionId) === "mutation") {
          payloadDigests.set(context.operationId, Object.freeze([...(captured.referencedPayloadDigests ?? [])]));
        }
        return captured;
      },
    }),
  ])));
}
