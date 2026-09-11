import type { CarrierReadRequest, CarrierReadSuccess } from "../core/carrier-session.js";
import type { ConnectionControlOptions } from "../core/public-client-types.js";
import { sdkProjectIdSchema, sdkRevisionSchema } from "../generated/sdk-identities.js";
import { CutAgentSdkError, PUBLIC_ERROR_KIND_BY_CODE } from "../protocol/errors.js";
import {
  MediaPoolFolderIdSchema,
  MediaPoolItemIdSchema,
  ProjectIdSchema,
  RequestIdSchema,
  RevisionSchema,
  SnapshotMediaPoolFolderIdSchema,
  SnapshotMediaPoolItemIdSchema,
  type MediaPoolFolderId,
  type MediaPoolItemId,
  type ProjectId,
  type Revision,
  type SnapshotMediaPoolFolderId,
  type SnapshotMediaPoolItemId,
} from "../value-types/identities.js";
import type { ReadControlOptions } from "./object-model.js";
import type { OperationHandle, PublicActionId } from "../protocol/operations.js";
import {
  sdkMediaPoolCreateBinInputSchema,
  sdkMediaPoolCreateBinResultSchema,
  sdkMediaPoolDeleteInputSchema,
  sdkMediaPoolDeleteResultSchema,
  sdkMediaPoolImportInputSchema,
  sdkMediaPoolImportResultSchema,
  sdkMediaPoolRelinkInputSchema,
  sdkMediaPoolRelinkResultSchema,
  sdkMediaPoolSetMetadataInputSchema,
  sdkMediaPoolSetMetadataResultSchema,
  sdkMediaPoolSyncAudioInputSchema,
  sdkMediaPoolSyncAudioResultSchema,
} from "../generated/sdk-project-media.js";
import type { IdempotencyKey } from "../value-types/identities.js";
import { freezeRecursively as freeze, mutationControl } from "./internal-utilities.js";

type WirePage = Extract<CarrierReadSuccess, { operation: "mediaPool.page" }>["data"];
type WireSearch = Extract<CarrierReadRequest, { operation: "mediaPool.page" }>["search"];
type WireTranscription = Extract<CarrierReadSuccess, { operation: "mediaPool.transcription" }>["data"];

/** Public Media Pool asset categories normalized from DaVinci Resolve readback. @beta */
export type MediaPoolAssetKind = "video" | "audio" | "still" | "timeline" | "multicam" | "compound" | "fusion_composition" | "generator" | "unknown";

/** Curated, stable metadata keys available on immutable asset snapshots. @beta */
export type MediaPoolMetadataKey = "description" | "comments" | "keywords" | "shot" | "scene" | "take" | "angle" | "camera" | "reel" | "dateRecorded" | "goodTake" | "clipColor";

/** Immutable metadata value reported for one asset observation. @beta */
export interface MediaPoolMetadataEntry {
  /** Stable public metadata key. */
  readonly key: MediaPoolMetadataKey;
  /** Metadata value captured by this snapshot. */
  readonly value: string;
}

/** One word from persisted DaVinci Resolve Media Pool transcription. @beta */
export interface MediaPoolTranscriptionWord {
  readonly start: string | null;
  readonly end: string | null;
  readonly text: string;
}

/** One timed segment from persisted DaVinci Resolve Media Pool transcription. @beta */
export interface MediaPoolTranscriptionSegment {
  readonly start: string | null;
  readonly end: string | null;
  readonly text: string;
  readonly speaker: string | null;
  readonly words: readonly MediaPoolTranscriptionWord[];
}

/** Immutable existing transcription for one exact Media Pool asset. @beta */
export interface MediaPoolTranscription {
  readonly projectId: ProjectId;
  readonly assetId: MediaPoolItemId;
  readonly useNestedClipTranscription: boolean;
  readonly available: boolean;
  readonly language: string | null;
  readonly segments: readonly MediaPoolTranscriptionSegment[];
}

/** Controls existing-transcription readback for one exact Media Pool asset. @beta */
export interface MediaPoolTranscriptionOptions extends ReadControlOptions {
  readonly useNestedClipTranscription?: boolean;
}

/** Immutable Media Pool bin/folder observation bound to one pool revision. @beta */
export interface MediaPoolFolderSnapshot {
  /** Exact project identity that owns this observation. */
  readonly projectId: ProjectId;
  /** Durable identity only when DaVinci Resolve exposes an authoritative native folder identity. */
  readonly id: MediaPoolFolderId | null;
  /** Identity valid only for this exact Media Pool revision. */
  readonly snapshotId: SnapshotMediaPoolFolderId;
  /** Snapshot identity of the parent bin, or `null` for the root. */
  readonly parentSnapshotId: SnapshotMediaPoolFolderId | null;
  /** Revision that owns this immutable folder observation. */
  readonly snapshotRevision: Revision;
  /** Display name reported by DaVinci Resolve. */
  readonly name: string;
  /** Zero for the Media Pool root; descendants increase by one. */
  readonly depth: number;
}

/** Immutable Media Pool asset observation with page and exact asset-custody revisions. @beta */
export interface MediaPoolAssetSnapshot {
  /** Exact project identity that owns this observation. */
  readonly projectId: ProjectId;
  /** Durable identity only when DaVinci Resolve exposes an authoritative native media identity. */
  readonly id: MediaPoolItemId | null;
  /** Identity valid only for this exact Media Pool page revision. */
  readonly snapshotId: SnapshotMediaPoolItemId;
  readonly folderSnapshotId: SnapshotMediaPoolFolderId;
  /** Global Media Pool revision that owns this immutable page observation. */
  readonly snapshotRevision: Revision;
  /** Exact revision of this asset's managed-authoring custody. */
  readonly assetCustodyRevision: Revision;
  /** Display name reported by DaVinci Resolve. */
  readonly name: string;
  /** Normalized asset category. */
  readonly kind: MediaPoolAssetKind;
  /** Whether DaVinci Resolve reported this asset as selected at snapshot time. */
  readonly selected: boolean;
  /** Source basename only; local directory paths are not exposed by this API. */
  readonly sourceFileName: string | null;
  /** DaVinci Resolve duration text when exposed. */
  readonly duration: string | null;
  /** DaVinci Resolve resolution text when exposed. */
  readonly resolution: string | null;
  /** DaVinci Resolve source frame-rate text when exposed. */
  readonly frameRate: string | null;
  /** DaVinci Resolve source start timecode when exposed. */
  readonly startTimecode: string | null;
  /** Whether DaVinci Resolve exposed metadata for this asset. */
  readonly metadataAvailable: boolean;
  /** Curated metadata only; arbitrary DaVinci Resolve keys are not leaked through the public wire contract. */
  readonly metadata: readonly MediaPoolMetadataEntry[];
}

/** Bounded controls for a Media Pool hierarchy page. @beta */
export interface MediaPoolPageOptions extends ReadControlOptions {
  /** Maximum combined folders and assets returned. Defaults to 32; maximum 32. */
  pageSize?: number;
}

/** Deterministic Media Pool search input. @beta */
export interface MediaPoolSearchInput {
  /** Non-empty case-insensitive query. */
  readonly query: string;
  /** Exact or substring matching; defaults to `contains`. */
  readonly match?: "contains" | "exact";
  /** Curated fields to search; defaults to `name`. */
  readonly fields?: readonly ("name" | "metadata" | "sourceFileName")[];
}

/** Controls shared by every Media Pool mutation. @beta */
export interface MediaPoolMutationOptions extends ConnectionControlOptions {
  /** Exact Media Pool revision observed before the mutation. */
  readonly precondition: Revision;
  /** Stable caller identity. Reuse it after an uncertain response. */
  readonly idempotencyKey: IdempotencyKey;
}

/** Durable project-bound bin reference acquired from one immutable observation. @beta */
export interface MediaPoolBin {
  readonly id: MediaPoolFolderId;
  readonly projectId: ProjectId;
  readonly name: string;
  readonly observedRevision: Revision;
}

/** Durable project-bound Media Pool asset reference acquired from one immutable observation. @beta */
export interface MediaPoolAsset {
  readonly id: MediaPoolItemId;
  readonly projectId: ProjectId;
  readonly name: string;
  readonly kind: MediaPoolAssetKind;
  readonly observedRevision: Revision;
  /** Read the transcription already persisted by DaVinci Resolve without starting transcription. */
  transcription(options?: MediaPoolTranscriptionOptions): Promise<MediaPoolTranscription>;
  relink(input: { readonly path: string }, options: MediaPoolMutationOptions): Promise<OperationHandle<MediaPoolRelinkResult, "cutagent.action.media.relink">>;
  setMetadata(entries: readonly MediaPoolMetadataEntry[], options: MediaPoolMutationOptions): Promise<OperationHandle<MediaPoolSetMetadataResult, "cutagent.action.media.metadata">>;
}

function transcriptionResult(
  raw: WireTranscription,
  projectId: ProjectId,
  assetId: MediaPoolItemId,
  useNestedClipTranscription: boolean,
): MediaPoolTranscription {
  if (String(raw.projectId) !== String(projectId)
    || String(raw.assetId) !== String(assetId)
    || raw.useNestedClipTranscription !== useNestedClipTranscription) {
    throw invalidResponseFailure("CutAgent runtime returned transcription for a different Media Pool asset or mode.");
  }
  return freeze({
    projectId,
    assetId,
    useNestedClipTranscription,
    available: raw.available,
    language: raw.language,
    segments: raw.segments.map((segment) => ({
      ...segment,
      words: segment.words.map((word) => ({ ...word })),
    })),
  });
}

/** Verified created-bin identity and resulting Media Pool revision. @beta */
export interface MediaPoolCreateBinResult { readonly projectId: ProjectId; readonly folder: Readonly<{ id: MediaPoolFolderId | null; snapshotId: SnapshotMediaPoolFolderId; name: string }>; readonly revision: Revision; }
/** Verified imported identities and resulting Media Pool revision. @beta */
export interface MediaPoolImportResult { readonly projectId: ProjectId; readonly assets: readonly Readonly<{ id: MediaPoolItemId | null; snapshotId: SnapshotMediaPoolItemId; name: string }>[]; readonly revision: Revision; }
/** Verified relink identity and resulting Media Pool revision. @beta */
export interface MediaPoolRelinkResult { readonly projectId: ProjectId; readonly asset: Readonly<{ id: MediaPoolItemId; snapshotId: SnapshotMediaPoolItemId; name: string }>; readonly sourceFileName: string; readonly revision: Revision; }
/** Verified sync identities and resulting Media Pool revision. @beta */
export interface MediaPoolSyncAudioResult { readonly projectId: ProjectId; readonly videoAssetId: MediaPoolItemId; readonly audioAssetIds: readonly MediaPoolItemId[]; readonly syncedAsset: Readonly<{ id: MediaPoolItemId | null; snapshotId: SnapshotMediaPoolItemId; name: string }> | null; readonly revision: Revision; }
/** Verified metadata readback and resulting Media Pool revision. @beta */
export interface MediaPoolSetMetadataResult { readonly projectId: ProjectId; readonly assetId: MediaPoolItemId; readonly entries: readonly MediaPoolMetadataEntry[]; readonly revision: Revision; }
/** Per-asset verified outcome from one plural native Media Pool deletion. @beta */
export interface MediaPoolDeleteItemResult { readonly assetId: MediaPoolItemId; readonly status: "deleted"; }
/** Ordered deletion outcomes and resulting Media Pool revision. @beta */
export interface MediaPoolDeleteResult { readonly projectId: ProjectId; readonly items: readonly MediaPoolDeleteItemResult[]; readonly revision: Revision; }

/** One immutable bounded hierarchy/search page. @beta */
export interface MediaPoolSnapshotPage {
  /** Exact project identity that owns this observation. */
  readonly projectId: ProjectId;
  /** Content revision shared by every page in this observation. */
  readonly revision: Revision;
  /** Zero-based pagination offset internal to this immutable observation. */
  readonly offset: number;
  /** Maximum combined entries requested for this page. */
  readonly pageSize: number;
  /** Total matching entries at this revision. */
  readonly total: number;
  /** Folder entries included in this bounded page. */
  readonly folders: readonly MediaPoolFolderSnapshot[];
  /** Asset entries included in this bounded page. */
  readonly assets: readonly MediaPoolAssetSnapshot[];
  /** True when another page exists for this exact revision and query. */
  readonly hasNextPage: boolean;
  /** Read the next bounded page from this immutable observation, or return `null` at the end. Later active-project switches do not change an available observation; if it is unavailable, live pool drift fails with `STALE_REVISION`. */
  nextPage(options?: ReadControlOptions): Promise<MediaPoolSnapshotPage | null>;
}

/** Read-only Media Pool API scoped to one exact project reference. @beta */
export interface MediaPool {
  /** Read the first deterministic, bounded hierarchy page. */
  snapshot(options?: MediaPoolPageOptions): Promise<MediaPoolSnapshotPage>;
  /** Search all assets deterministically by curated public fields. */
  search(input: MediaPoolSearchInput, options?: MediaPoolPageOptions): Promise<MediaPoolSnapshotPage>;
  /** Resolve exactly one asset by exact display name; zero and multiple matches are typed failures. */
  assetByName(name: string, options?: ReadControlOptions): Promise<MediaPoolAssetSnapshot>;
  /** Acquire a durable mutation reference. Snapshot-only identities fail before execution. */
  asset(snapshot: MediaPoolAssetSnapshot): MediaPoolAsset;
  /** Acquire a durable bin mutation reference. Snapshot-only identities fail before execution. */
  bin(snapshot: MediaPoolFolderSnapshot): MediaPoolBin;
  /** Create a child bin under an exact durable parent, or under the root when omitted. */
  createBin(input: { readonly name: string; readonly parent?: MediaPoolBin }, options: MediaPoolMutationOptions): Promise<OperationHandle<MediaPoolCreateBinResult, "cutagent.action.media.folders.create">>;
  /** Import local media into an exact durable destination, or the root when omitted. */
  importMedia(input: { readonly paths: readonly string[]; readonly destination?: MediaPoolBin }, options: MediaPoolMutationOptions): Promise<OperationHandle<MediaPoolImportResult, "cutagent.action.media.import">>;
  /** Delete one or more exact durable assets with one native Media Pool operation. */
  delete(target: MediaPoolAsset | readonly MediaPoolAsset[], options: MediaPoolMutationOptions): Promise<OperationHandle<MediaPoolDeleteResult, "cutagent.action.media.delete">>;
  /** Synchronize exact durable audio assets to one exact durable video asset. */
  syncAudio(video: MediaPoolAsset, audio: readonly MediaPoolAsset[], input: { readonly method: "waveform" | "timecode"; readonly appendTracks?: boolean }, options: MediaPoolMutationOptions): Promise<OperationHandle<MediaPoolSyncAudioResult, "cutagent.action.media.sync_audio">>;
}

export interface MediaPoolRuntime {
  readonly generation: number;
  readAtGeneration(
    generation: number,
    request: CarrierReadRequest,
    options?: ReadControlOptions,
  ): Promise<CarrierReadSuccess>;
  startAction<TResult, TAction extends PublicActionId>(
    generation: number,
    actionId: TAction,
    input: unknown,
    schema: { parse(value: unknown): TResult },
    options?: ConnectionControlOptions & { idempotencyKey?: string },
  ): Promise<OperationHandle<TResult, TAction>>;
}

function selectionFailure(code: "TARGET_NOT_FOUND" | "AMBIGUOUS_TARGET", message: string): CutAgentSdkError {
  return new CutAgentSdkError({
    kind: PUBLIC_ERROR_KIND_BY_CODE[code],
    code,
    message,
    retrySafe: code === "TARGET_NOT_FOUND",
    ...(code === "TARGET_NOT_FOUND" ? { retrySafetyProof: { basis: "read_only" } as const } : {}),
    possibleMutation: "none",
    usage: "not_reserved",
    recovery: ["inspect_state"],
    recoveryGuidance: [message],
    readbackRequired: false,
  });
}

function invalidResponseFailure(message: string, rawRequestId?: string): CutAgentSdkError {
  return new CutAgentSdkError({
    kind: PUBLIC_ERROR_KIND_BY_CODE.INVALID_RESPONSE,
    code: "INVALID_RESPONSE",
    message,
    retrySafe: false,
    possibleMutation: "none",
    usage: "not_reserved",
    recovery: ["contact_support"],
    recoveryGuidance: [message],
    readbackRequired: false,
    ...(rawRequestId ? { requestId: RequestIdSchema.parse(rawRequestId) } : {}),
  });
}

function staleFailure(message: string): CutAgentSdkError {
  return new CutAgentSdkError({
    kind: PUBLIC_ERROR_KIND_BY_CODE.STALE_REVISION,
    code: "STALE_REVISION",
    message,
    retrySafe: false,
    possibleMutation: "none",
    usage: "not_reserved",
    recovery: ["inspect_state"],
    recoveryGuidance: [message],
    readbackRequired: false,
  });
}

function adaptSchema<TWire, TResult>(schema: { parse(value: unknown): TWire }, adapt: (wire: TWire) => TResult) {
  return { parse(value: unknown): TResult { return freeze(adapt(schema.parse(value))); } };
}

const createBinResultSchema = adaptSchema(sdkMediaPoolCreateBinResultSchema, (value): MediaPoolCreateBinResult => ({
  projectId: ProjectIdSchema.parse(value.projectId),
  folder: { id: value.folder.id === null ? null : MediaPoolFolderIdSchema.parse(value.folder.id), snapshotId: SnapshotMediaPoolFolderIdSchema.parse(value.folder.snapshotId), name: value.folder.name },
  revision: RevisionSchema.parse(value.revision),
}));
const importResultSchema = adaptSchema(sdkMediaPoolImportResultSchema, (value): MediaPoolImportResult => ({
  projectId: ProjectIdSchema.parse(value.projectId),
  assets: value.assets.map((asset) => ({ id: asset.id === null ? null : MediaPoolItemIdSchema.parse(asset.id), snapshotId: SnapshotMediaPoolItemIdSchema.parse(asset.snapshotId), name: asset.name })),
  revision: RevisionSchema.parse(value.revision),
}));
const deleteResultSchema = adaptSchema(sdkMediaPoolDeleteResultSchema, (value): MediaPoolDeleteResult => ({
  projectId: ProjectIdSchema.parse(value.projectId),
  items: value.items.map((item) => ({ assetId: MediaPoolItemIdSchema.parse(item.assetId), status: item.status })),
  revision: RevisionSchema.parse(value.revision),
}));
const relinkResultSchema = adaptSchema(sdkMediaPoolRelinkResultSchema, (value): MediaPoolRelinkResult => ({
  projectId: ProjectIdSchema.parse(value.projectId),
  asset: { id: MediaPoolItemIdSchema.parse(value.asset.id), snapshotId: SnapshotMediaPoolItemIdSchema.parse(value.asset.snapshotId), name: value.asset.name },
  sourceFileName: value.sourceFileName,
  revision: RevisionSchema.parse(value.revision),
}));
const syncAudioResultSchema = adaptSchema(sdkMediaPoolSyncAudioResultSchema, (value): MediaPoolSyncAudioResult => ({
  projectId: ProjectIdSchema.parse(value.projectId),
  videoAssetId: MediaPoolItemIdSchema.parse(value.videoAssetId),
  audioAssetIds: value.audioAssetIds.map((id) => MediaPoolItemIdSchema.parse(id)),
  syncedAsset: value.syncedAsset === null ? null : { id: value.syncedAsset.id === null ? null : MediaPoolItemIdSchema.parse(value.syncedAsset.id), snapshotId: SnapshotMediaPoolItemIdSchema.parse(value.syncedAsset.snapshotId), name: value.syncedAsset.name },
  revision: RevisionSchema.parse(value.revision),
}));
const setMetadataResultSchema = adaptSchema(sdkMediaPoolSetMetadataResultSchema, (value): MediaPoolSetMetadataResult => ({
  projectId: ProjectIdSchema.parse(value.projectId),
  assetId: MediaPoolItemIdSchema.parse(value.assetId),
  entries: value.entries,
  revision: RevisionSchema.parse(value.revision),
}));

function bindProjectResult<TResult extends { readonly projectId: ProjectId }>(
  schema: { parse(value: unknown): TResult },
  projectId: ProjectId,
  validate?: (result: TResult) => boolean,
) {
  return {
    parse(value: unknown): TResult {
      const result = schema.parse(value);
      if (String(result.projectId) !== String(projectId)) {
        throw invalidResponseFailure("CutAgent runtime returned a Media Pool mutation result for another project.");
      }
      if (validate && !validate(result)) {
        throw invalidResponseFailure("CutAgent runtime returned a Media Pool mutation result for different targets.");
      }
      return result;
    },
  };
}

function assertObservedRevision(observed: Revision, expected: Revision, label: string): void {
  if (String(observed) !== String(expected)) {
    throw staleFailure(`${label} belongs to a different Media Pool revision. Acquire a fresh durable reference before mutation.`);
  }
}

function pageSize(value: number | undefined): number {
  const normalized = value ?? 32;
  if (!Number.isInteger(normalized) || normalized < 1 || normalized > 32) {
    throw new TypeError("pageSize must be an integer from 1 through 32.");
  }
  return normalized;
}

function isWellFormedUnicode(value: string): boolean {
  for (let offset = 0; offset < value.length; offset += 1) {
    const codeUnit = value.charCodeAt(offset);
    if (codeUnit >= 0xd800 && codeUnit <= 0xdbff) {
      const next = value.charCodeAt(offset + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) return false;
      offset += 1;
    } else if (codeUnit >= 0xdc00 && codeUnit <= 0xdfff) {
      return false;
    }
  }
  return true;
}

function searchInput(input: MediaPoolSearchInput): Exclude<WireSearch, null> {
  if (!input || typeof input !== "object") throw new TypeError("Media Pool search input is required.");
  const query = typeof input.query === "string" ? input.query : "";
  if (!query.trim() || !isWellFormedUnicode(query) || new TextEncoder().encode(query).byteLength > 1024) {
    throw new TypeError("Media Pool search query must contain from 1 through 1024 well-formed UTF-8 bytes.");
  }
  const match = input.match ?? "contains";
  if (match !== "contains" && match !== "exact") throw new TypeError("Media Pool search match must be contains or exact.");
  const fields = [...(input.fields ?? ["name"])] as ("name" | "metadata" | "sourceFileName")[];
  const allowed = new Set(["name", "metadata", "sourceFileName"]);
  if (fields.length < 1 || fields.length > 3 || new Set(fields).size !== fields.length || fields.some((field) => !allowed.has(field))) {
    throw new TypeError("Media Pool search fields must be a unique subset of name, metadata, and sourceFileName.");
  }
  return { query, match, fields };
}

function immutablePage(
  runtime: MediaPoolRuntime,
  generation: number,
  projectId: ProjectId,
  raw: WirePage,
  search: WireSearch,
  expectedOffset: number,
  expectedPageSize: number,
): MediaPoolSnapshotPage {
  if (String(raw.project.id) !== String(projectId) || raw.offset !== expectedOffset || raw.pageSize !== expectedPageSize) {
    throw invalidResponseFailure("CutAgent runtime returned a Media Pool page for a different project or page coordinate.");
  }
  if (JSON.stringify(raw.search) !== JSON.stringify(search)) {
    throw invalidResponseFailure("CutAgent runtime returned a Media Pool page for a different search.");
  }
  const revision = RevisionSchema.parse(raw.revision);
  const folders = freeze(raw.folders.map((folder): MediaPoolFolderSnapshot => freeze({
    projectId,
    id: folder.id === null ? null : MediaPoolFolderIdSchema.parse(folder.id),
    snapshotId: SnapshotMediaPoolFolderIdSchema.parse(folder.snapshotId),
    parentSnapshotId: folder.parentSnapshotId === null ? null : SnapshotMediaPoolFolderIdSchema.parse(folder.parentSnapshotId),
    snapshotRevision: RevisionSchema.parse(folder.snapshotRevision),
    name: folder.name,
    depth: folder.depth,
  })));
  const assets = freeze(raw.assets.map((asset): MediaPoolAssetSnapshot => freeze({
    projectId,
    id: asset.id === null ? null : MediaPoolItemIdSchema.parse(asset.id),
    snapshotId: SnapshotMediaPoolItemIdSchema.parse(asset.snapshotId),
    folderSnapshotId: SnapshotMediaPoolFolderIdSchema.parse(asset.folderSnapshotId),
    snapshotRevision: RevisionSchema.parse(asset.snapshotRevision),
    assetCustodyRevision: RevisionSchema.parse(asset.assetCustodyRevision),
    name: asset.name,
    kind: asset.kind,
    selected: asset.selected,
    sourceFileName: asset.sourceFileName,
    duration: asset.duration,
    resolution: asset.resolution,
    frameRate: asset.frameRate,
    startTimecode: asset.startTimecode,
    metadataAvailable: asset.metadataAvailable,
    metadata: freeze(asset.metadata.map((entry) => freeze({ key: entry.key, value: entry.value }))),
  })));
  const page: MediaPoolSnapshotPage = {
    projectId,
    revision,
    offset: raw.offset,
    pageSize: raw.pageSize,
    total: raw.total,
    folders,
    assets,
    hasNextPage: raw.nextOffset !== null,
    async nextPage(options = {}) {
      if (raw.nextOffset === null) return null;
      const response = await runtime.readAtGeneration(generation, {
        operation: "mediaPool.page",
        projectId: sdkProjectIdSchema.parse(projectId),
        offset: raw.nextOffset,
        pageSize: raw.pageSize,
        expectedRevision: sdkRevisionSchema.parse(revision),
        search,
      }, options);
      if (response.operation !== "mediaPool.page") {
        throw invalidResponseFailure("CutAgent runtime did not return the requested Media Pool page.", response.requestId);
      }
      const next = immutablePage(runtime, generation, projectId, response.data, search, raw.nextOffset, raw.pageSize);
      if (String(next.revision) !== String(revision)) {
        throw staleFailure("The Media Pool changed between bounded page reads.");
      }
      return next;
    },
  };
  Object.setPrototypeOf(page, null);
  return freeze(page);
}

/** Construct one project-bound read-only Media Pool reference. @internal */
export function createMediaPool(runtime: MediaPoolRuntime, generation: number, rawProjectId: string): MediaPool {
  const wireProjectId = sdkProjectIdSchema.parse(rawProjectId);
  const projectId = ProjectIdSchema.parse(wireProjectId);
  const boundImportResultSchema = bindProjectResult(importResultSchema, projectId);
  const durableBin = (snapshot: MediaPoolFolderSnapshot): MediaPoolBin => {
    if (String(ProjectIdSchema.parse(snapshot.projectId)) !== String(projectId)) throw new TypeError("The Media Pool bin snapshot belongs to another project.");
    if (snapshot.id === null) throw selectionFailure("TARGET_NOT_FOUND", "This Media Pool bin has only a snapshot identity and cannot be a mutation target.");
    const value: MediaPoolBin = { id: MediaPoolFolderIdSchema.parse(snapshot.id), projectId, name: snapshot.name, observedRevision: RevisionSchema.parse(snapshot.snapshotRevision) };
    Object.setPrototypeOf(value, null);
    return Object.freeze(value);
  };
  const durableAsset = (snapshot: MediaPoolAssetSnapshot): MediaPoolAsset => {
    if (String(ProjectIdSchema.parse(snapshot.projectId)) !== String(projectId)) throw new TypeError("The Media Pool asset snapshot belongs to another project.");
    if (snapshot.id === null) throw selectionFailure("TARGET_NOT_FOUND", "This Media Pool asset has only a snapshot identity and cannot be a mutation target.");
    const id = MediaPoolItemIdSchema.parse(snapshot.id);
    const observedRevision = RevisionSchema.parse(snapshot.snapshotRevision);
    const value: MediaPoolAsset = {
      id,
      projectId,
      name: snapshot.name,
      kind: snapshot.kind,
      observedRevision,
      async transcription(options = {}) {
        const useNestedClipTranscription = options.useNestedClipTranscription ?? false;
        if (typeof useNestedClipTranscription !== "boolean") {
          throw new TypeError("useNestedClipTranscription must be a boolean.");
        }
        const response = await runtime.readAtGeneration(generation, {
          operation: "mediaPool.transcription",
          projectId: wireProjectId,
          mediaPoolItemId: id,
          expectedRevision: observedRevision,
          useNestedClipTranscription,
        }, options);
        if (response.operation !== "mediaPool.transcription") {
          throw invalidResponseFailure("CutAgent runtime did not return the requested Media Pool transcription.", response.requestId);
        }
        return transcriptionResult(response.data, projectId, id, useNestedClipTranscription);
      },
      relink(input, options) {
        assertObservedRevision(observedRevision, options.precondition, "The Media Pool asset");
        const sourceFileName = input.path.split(/[\\/]/).at(-1);
        const resultSchema = bindProjectResult(relinkResultSchema, projectId, (result) => (
          String(result.asset.id) === String(id) && result.sourceFileName === sourceFileName
        ));
        return runtime.startAction(generation, "cutagent.action.media.relink", sdkMediaPoolRelinkInputSchema.parse({ projectId, precondition: options.precondition, assetId: id, path: input.path }), resultSchema, mutationControl(options));
      },
      setMetadata(entries, options) {
        assertObservedRevision(observedRevision, options.precondition, "The Media Pool asset");
        const expectedEntries = new Map(entries.map((entry) => [entry.key, entry.value]));
        const resultSchema = bindProjectResult(setMetadataResultSchema, projectId, (result) => (
          String(result.assetId) === String(id)
          && result.entries.length === expectedEntries.size
          && result.entries.every((entry) => expectedEntries.get(entry.key) === entry.value)
        ));
        return runtime.startAction(generation, "cutagent.action.media.metadata", sdkMediaPoolSetMetadataInputSchema.parse({ projectId, precondition: options.precondition, assetId: id, entries }), resultSchema, mutationControl(options));
      },
    };
    Object.setPrototypeOf(value, null);
    return Object.freeze(value);
  };
  const readFirstPage = async (
    search: WireSearch,
    options: MediaPoolPageOptions,
  ): Promise<MediaPoolSnapshotPage> => {
    const requestedPageSize = pageSize(options.pageSize);
    const response = await runtime.readAtGeneration(generation, {
      operation: "mediaPool.page",
      projectId: wireProjectId,
      offset: 0,
      pageSize: requestedPageSize,
      expectedRevision: null,
      search,
    }, options);
    if (response.operation !== "mediaPool.page") throw invalidResponseFailure("CutAgent runtime did not return the requested Media Pool page.");
    return immutablePage(runtime, generation, projectId, response.data, search, 0, requestedPageSize);
  };
  const mediaPool: MediaPool = {
    snapshot(options = {}) { return readFirstPage(null, options); },
    search(input, options = {}) { return readFirstPage(searchInput(input), options); },
    async assetByName(name, options = {}) {
      const page = await readFirstPage(searchInput({ query: name, match: "exact", fields: ["name"] }), { ...options, pageSize: 2 });
      if (page.total === 0) throw selectionFailure("TARGET_NOT_FOUND", `No Media Pool asset is named ${JSON.stringify(name)}.`);
      if (page.total > 1) throw selectionFailure("AMBIGUOUS_TARGET", `More than one Media Pool asset is named ${JSON.stringify(name)}.`);
      const asset = page.assets[0];
      if (!asset) throw selectionFailure("TARGET_NOT_FOUND", `No Media Pool asset is named ${JSON.stringify(name)}.`);
      return asset;
    },
    asset: durableAsset,
    bin: durableBin,
    createBin(input, options) {
      if (input.parent) {
        if (input.parent.projectId !== projectId) throw new TypeError("The destination bin belongs to another project.");
        assertObservedRevision(input.parent.observedRevision, options.precondition, "The destination bin");
      }
      const resultSchema = bindProjectResult(createBinResultSchema, projectId, (result) => result.folder.name === input.name);
      return runtime.startAction(generation, "cutagent.action.media.folders.create", sdkMediaPoolCreateBinInputSchema.parse({ projectId, precondition: options.precondition, parent: input.parent ? { kind: "folder", id: input.parent.id } : { kind: "root" }, name: input.name }), resultSchema, mutationControl(options));
    },
    importMedia(input, options) {
      if (input.destination) {
        if (input.destination.projectId !== projectId) throw new TypeError("The destination bin belongs to another project.");
        assertObservedRevision(input.destination.observedRevision, options.precondition, "The destination bin");
      }
      return runtime.startAction(generation, "cutagent.action.media.import", sdkMediaPoolImportInputSchema.parse({ projectId, precondition: options.precondition, destination: input.destination ? { kind: "folder", id: input.destination.id } : { kind: "root" }, paths: [...input.paths] }), boundImportResultSchema, mutationControl(options));
    },
    delete(target, options) {
      const targets = Array.isArray(target) ? [...target] : [target as MediaPoolAsset];
      if (targets.length === 0) throw new TypeError("At least one Media Pool asset is required for deletion.");
      const ids = targets.map((asset) => {
        if (asset.projectId !== projectId) throw new TypeError("Every deleted asset must belong to this project.");
        assertObservedRevision(asset.observedRevision, options.precondition, "A deleted Media Pool asset");
        return MediaPoolItemIdSchema.parse(asset.id);
      });
      if (new Set(ids.map(String)).size !== ids.length) throw new TypeError("Deleted Media Pool assets must be unique.");
      const resultSchema = bindProjectResult(deleteResultSchema, projectId, (result) => (
        result.items.length === ids.length
        && result.items.every((item, index) => item.status === "deleted" && String(item.assetId) === String(ids[index]))
      ));
      return runtime.startAction(generation, "cutagent.action.media.delete", sdkMediaPoolDeleteInputSchema.parse({ projectId, precondition: options.precondition, assetIds: ids }), resultSchema, mutationControl(options));
    },
    syncAudio(video, audio, input, options) {
      if (video.kind !== "video") throw new TypeError("The synchronization video target must be a video Media Pool asset.");
      if (audio.some((asset) => asset.kind !== "audio")) throw new TypeError("Every synchronization audio target must be an audio Media Pool asset.");
      const audioIds = audio.map((asset) => String(asset.id));
      if (new Set(audioIds).size !== audioIds.length || audioIds.includes(String(video.id))) {
        throw new TypeError("Synchronization targets must contain one video and unique, distinct audio assets.");
      }
      for (const asset of [video, ...audio]) {
        if (asset.projectId !== projectId) throw new TypeError("Every synchronized asset must belong to this project.");
        assertObservedRevision(asset.observedRevision, options.precondition, "A synchronized Media Pool asset");
      }
      const expectedAudioIds = new Set(audio.map((asset) => String(asset.id)));
      const resultSchema = bindProjectResult(syncAudioResultSchema, projectId, (result) => (
        String(result.videoAssetId) === String(video.id)
        && result.audioAssetIds.length === expectedAudioIds.size
        && new Set(result.audioAssetIds.map(String)).size === expectedAudioIds.size
        && result.audioAssetIds.every((id) => expectedAudioIds.has(String(id)))
      ));
      return runtime.startAction(generation, "cutagent.action.media.sync_audio", sdkMediaPoolSyncAudioInputSchema.parse({ projectId, precondition: options.precondition, videoAssetId: video.id, audioAssetIds: audio.map((asset) => asset.id), method: input.method, appendTracks: input.appendTracks ?? true }), resultSchema, mutationControl(options));
    },
  };
  Object.setPrototypeOf(mediaPool, null);
  return Object.freeze(mediaPool);
}
