import type { ConnectionControlOptions } from "../core/public-client-types.js";
import { parseClosedActionSchema } from "../core/action-schema.js";
import {
  ACTION_RUNTIME_CONTRACTS,
  ACTION_SCHEMA_DEFINITIONS,
  type ActionResult,
} from "../generated/actions.js";
import type { OperationHandle, PublicActionId } from "../protocol/operations.js";
import {
  sdkProjectBackupInputSchema,
  sdkProjectBackupResultSchema,
  sdkProjectContextMutationResultSchema,
  sdkProjectCreateInputSchema,
  sdkProjectLibraryBackupInputSchema,
  sdkProjectLibraryBackupResultSchema,
  sdkProjectLibraryCreateInputSchema,
  sdkProjectLibraryMutationResultSchema,
  sdkProjectLibraryOpenInputSchema,
  sdkProjectLibraryReferenceSchema,
  sdkProjectLibraryRestoreInputSchema,
  sdkProjectOpenInputSchema,
  sdkProjectRestoreInputSchema,
  sdkProjectRestoreResultSchema,
} from "../generated/sdk-project-media.js";
import { CutAgentSdkError, PUBLIC_ERROR_KIND_BY_CODE } from "../protocol/errors.js";
import { ArtifactIdSchema, ProjectIdSchema, RevisionSchema, TimelineIdSchema, type ArtifactId, type IdempotencyKey, type ProjectId, type Revision, type TimelineId } from "../value-types/identities.js";
import { mutationControl as control } from "./internal-utilities.js";

/** Stable caller controls for a project or project-library mutation. @beta */
export interface ProjectMutationOptions extends ConnectionControlOptions {
  /** Exact live-state revision that the runtime must still observe before mutation. */
  readonly precondition: Revision;
  /** Reuse this exact key after an uncertain response. Never replace it to retry. */
  readonly idempotencyKey: IdempotencyKey;
}

/** Exact project-library identity exposed by the current CutAgent contracts. @beta */
export interface ProjectLibraryReference {
  readonly name: string;
  readonly kind: "disk" | "postgresql";
}
/** Exact durable project identity required for mutation targeting. @beta */
export interface ProjectReference { readonly id: ProjectId; readonly name: string; }
/** Project identity observed by authoritative readback; some transports cannot expose a durable ID. @beta */
export interface ProjectObservation { readonly id: ProjectId | null; readonly name: string; }
/** Timeline identity observed by authoritative readback; some transports cannot expose a durable ID. @beta */
export interface TimelineObservation { readonly id: TimelineId | null; readonly name: string; }
/** Explicit revision availability after a context-changing project operation. @beta */
export type ProjectRevisionObservation = Readonly<{ status: "available"; revision: Revision }> | Readonly<{ status: "unavailable" }>;
/** Exact active context independently observed after a project or library operation. @beta */
export interface ProjectContextObservation {
  readonly library: ProjectLibraryReference | null;
  readonly project: ProjectObservation | null;
  readonly timeline: TimelineObservation | null;
  readonly projectRevision: ProjectRevisionObservation;
}
/** Verified result of creating, opening, or restoring project context. @beta */
export interface ProjectContextMutationResult { readonly changed: boolean; readonly context: ProjectContextObservation; }
/** Verified restore result retaining the exact restored project identity. @beta */
export interface ProjectRestoreResult extends ProjectContextMutationResult { readonly restoredProject: ProjectReference; }
/** Verified project backup artifact and revision truth. @beta */
export interface ProjectBackupResult {
  readonly project: ProjectObservation;
  readonly artifact: Readonly<{ kind: "project"; artifactId: ArtifactId }>;
  readonly projectRevision: ProjectRevisionObservation;
}
/** Verified project-library context mutation result. @beta */
export interface ProjectLibraryMutationResult { readonly changed: boolean; readonly library: ProjectLibraryReference; readonly context: ProjectContextObservation; }
/** Verified project-library backup artifact and restored active-context truth. @beta */
export interface ProjectLibraryBackupResult {
  readonly library: ProjectLibraryReference;
  readonly artifact: Readonly<{ kind: "library_backup"; artifactId: ArtifactId }>;
  readonly context: ProjectContextObservation;
}

/** Project-library operations. PostgreSQL libraries are inspectable identities but local create/restore remains Disk-only. @beta */
export interface ProjectLibraries {
  create(input: { readonly name: string; readonly directoryPath: string }, options: ProjectMutationOptions): Promise<OperationHandle<ProjectLibraryMutationResult, "cutagent.action.project.library.create">>;
  open(library: ProjectLibraryReference, options: ProjectMutationOptions): Promise<OperationHandle<ProjectLibraryMutationResult, "cutagent.action.project.library.switch">>;
  backup(library: ProjectLibraryReference, input: { readonly destinationArtifactId: ArtifactId }, options: ProjectMutationOptions): Promise<OperationHandle<ProjectLibraryBackupResult, "cutagent.action.project.library.backup">>;
  restore(input: { readonly sourceArtifactId: ArtifactId; readonly name: string; readonly directoryPath: string }, options: ProjectMutationOptions): Promise<OperationHandle<ProjectLibraryMutationResult, "cutagent.action.project.library.restore">>;
}

/** Project collection mutations independent of one current project handle. @beta */
export interface ProjectCollectionMutations {
  readonly libraries: ProjectLibraries;
  create(input: { readonly name: string; readonly mediaLocation?: string | null }, options: ProjectMutationOptions): Promise<OperationHandle<ProjectContextMutationResult, "cutagent.action.project.create">>;
  open(project: ProjectReference, options: ProjectMutationOptions): Promise<OperationHandle<ProjectContextMutationResult, "cutagent.action.project.open">>;
  restore(input: { readonly sourceArtifactId: ArtifactId; readonly name: string }, options: ProjectMutationOptions): Promise<OperationHandle<ProjectRestoreResult, "cutagent.action.project.restore">>;
}

/** Mutations bound to one exact current project handle. @beta */
export interface ProjectBoundMutations {
  backup(input: { readonly destinationArtifactId: ArtifactId; readonly withStills?: boolean }, options: ProjectMutationOptions): Promise<OperationHandle<ProjectBackupResult, "cutagent.action.project.export">>;
  /** Rename this exact current project after revalidating its caller-owned revision. */
  rename(name: string, options: ProjectMutationOptions): Promise<OperationHandle<ProjectRenameResult, "cutagent.action.project.rename">>;
  /** Set one project setting after revalidating this exact current project and revision. */
  setSetting(key: string, value: string, options: ProjectMutationOptions): Promise<OperationHandle<ProjectSettingMutationResult, "cutagent.action.project.settings_set">>;
}

/** Verified project rename result projected from the signed prepared-action carrier. @beta */
export interface ProjectRenameResult {
  readonly changed: boolean;
  readonly project: ProjectReference;
  readonly previousName: string;
  readonly currentName: string;
}

/** Verified project-setting mutation result projected from the signed prepared-action carrier. @beta */
export interface ProjectSettingMutationResult {
  readonly changed: boolean;
  readonly key: string;
  readonly previousValue: string | null;
  readonly requestedValue: string;
  readonly appliedValue: string;
}

/** Carrier-neutral semantic project action seam. @internal */
export interface ProjectManagementRuntime {
  startAction<TResult, TAction extends PublicActionId>(
    generation: number,
    actionId: TAction,
    input: unknown,
    schema: { parse(value: unknown): TResult },
    options?: ConnectionControlOptions & { idempotencyKey?: string },
  ): Promise<OperationHandle<TResult, TAction>>;
}

function adaptSchema<TWire, TResult>(schema: { parse(value: unknown): TWire }, adapt: (wire: TWire) => TResult) {
  return { parse(value: unknown): TResult { return adapt(schema.parse(value)); } };
}

function invalidResponseFailure(message: string): CutAgentSdkError {
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
  });
}

function sameProject(observed: ProjectObservation | null, expected: { readonly id?: ProjectId; readonly name: string }): boolean {
  return observed !== null
    && observed.name === expected.name
    && (expected.id === undefined || String(observed.id) === String(expected.id));
}

function sameLibrary(observed: ProjectLibraryReference | null, expected: ProjectLibraryReference): boolean {
  return observed !== null && observed.name === expected.name && observed.kind === expected.kind;
}

function bindResult<TResult>(
  schema: { parse(value: unknown): TResult },
  validate: (result: TResult) => boolean,
  message: string,
) {
  return {
    parse(value: unknown): TResult {
      const result = schema.parse(value);
      if (!validate(result)) throw invalidResponseFailure(message);
      return result;
    },
  };
}

function revisionObservation(value: { status: "available"; revision: string } | { status: "unavailable" }): ProjectRevisionObservation {
  return value.status === "available"
    ? Object.freeze({ status: "available", revision: RevisionSchema.parse(value.revision) })
    : Object.freeze({ status: "unavailable" });
}

function authoritativeActionResult<A extends "cutagent.action.project.rename" | "cutagent.action.project.settings_set">(
  actionId: A,
  value: unknown,
): ActionResult<A> {
  return parseClosedActionSchema<ActionResult<A>>(
    ACTION_RUNTIME_CONTRACTS[actionId].result,
    ACTION_SCHEMA_DEFINITIONS,
    value,
    `${actionId}.result`,
  );
}

function projectRenameResultSchema(project: ProjectReference, expectedName: string) {
  return { parse(value: unknown): ProjectRenameResult {
    const root = authoritativeActionResult("cutagent.action.project.rename", value);
    const { payload } = root;
    if (payload.status !== "completed"
      || payload.target.id !== project.id || payload.target.name !== expectedName
      || payload.data.previousName !== project.name || payload.data.currentName !== expectedName
      || payload.changed !== (payload.data.previousName !== payload.data.currentName)) {
      throw invalidResponseFailure("CutAgent runtime returned a project rename result for another target or without matching verification.");
    }
    return Object.freeze({
      changed: payload.changed,
      project: Object.freeze({ id: project.id, name: payload.data.currentName }),
      previousName: payload.data.previousName,
      currentName: payload.data.currentName,
    });
  } };
}

function projectSettingResultSchema(expectedKey: string, expectedValue: string) {
  return { parse(value: unknown): ProjectSettingMutationResult {
    const root = authoritativeActionResult("cutagent.action.project.settings_set", value);
    const { payload } = root;
    if (payload.status !== "completed" || payload.target.key !== expectedKey
      || payload.data.requestedValue !== expectedValue || payload.data.appliedValue !== expectedValue
      || payload.changed !== (payload.data.previousValue !== payload.data.appliedValue)) {
      throw invalidResponseFailure("CutAgent runtime returned a project-setting result for another target or without matching verification.");
    }
    return Object.freeze({
      changed: payload.changed,
      key: expectedKey,
      previousValue: payload.data.previousValue,
      requestedValue: payload.data.requestedValue,
      appliedValue: payload.data.appliedValue,
    });
  } };
}

export function contextObservation(value: ReturnType<typeof sdkProjectContextMutationResultSchema.parse>["context"]): ProjectContextObservation {
  return Object.freeze({
    library: value.library === null ? null : Object.freeze({ ...value.library }),
    project: value.project === null ? null : Object.freeze({ id: value.project.id === null ? null : ProjectIdSchema.parse(value.project.id), name: value.project.name }),
    timeline: value.timeline === null ? null : Object.freeze({ id: value.timeline.id === null ? null : TimelineIdSchema.parse(value.timeline.id), name: value.timeline.name }),
    projectRevision: revisionObservation(value.projectRevision),
  });
}

const projectContextResultSchema = adaptSchema(sdkProjectContextMutationResultSchema, (value): ProjectContextMutationResult => Object.freeze({ changed: value.changed, context: contextObservation(value.context) }));
const projectRestoreResultSchema = adaptSchema(sdkProjectRestoreResultSchema, (value): ProjectRestoreResult => Object.freeze({
  changed: value.changed,
  restoredProject: Object.freeze({id: ProjectIdSchema.parse(value.restoredProject.id), name: value.restoredProject.name}),
  context: contextObservation(value.context),
}));
const projectLibraryResultSchema = adaptSchema(sdkProjectLibraryMutationResultSchema, (value): ProjectLibraryMutationResult => Object.freeze({ changed: value.changed, library: Object.freeze({ ...value.library }), context: contextObservation(value.context) }));
const projectLibraryBackupSchema = adaptSchema(sdkProjectLibraryBackupResultSchema, (value): ProjectLibraryBackupResult => Object.freeze({ library: Object.freeze({ ...value.library }), artifact: Object.freeze({ kind: value.artifact.kind, artifactId: ArtifactIdSchema.parse(value.artifact.artifactId) }), context: contextObservation(value.context) }));
const projectBackupSchema = adaptSchema(sdkProjectBackupResultSchema, (value): ProjectBackupResult => Object.freeze({ project: Object.freeze({ id: value.project.id === null ? null : ProjectIdSchema.parse(value.project.id), name: value.project.name }), artifact: Object.freeze({ kind: value.artifact.kind, artifactId: ArtifactIdSchema.parse(value.artifact.artifactId) }), projectRevision: revisionObservation(value.projectRevision) }));

/** Construct project-collection mutations bound to one client generation. @internal */
export function createProjectCollectionMutations(runtime: ProjectManagementRuntime, currentGeneration: () => number): ProjectCollectionMutations {
  const libraries: ProjectLibraries = {
    create(input, options) {
      const target = Object.freeze({ name: input.name, kind: "disk" as const });
      const resultSchema = bindResult(projectLibraryResultSchema, (result) => sameLibrary(result.library, target), "CutAgent runtime returned a project-library creation result for another library.");
      return runtime.startAction(currentGeneration(), "cutagent.action.project.library.create", sdkProjectLibraryCreateInputSchema.parse({ precondition: options.precondition, libraryName: input.name, directoryPath: input.directoryPath }), resultSchema, control(options));
    },
    open(library, options) {
      const target = sdkProjectLibraryReferenceSchema.parse(library);
      if (target.kind !== "disk") throw new TypeError("Only Disk project libraries can be opened through the current semantic SDK contract.");
      const resultSchema = bindResult(projectLibraryResultSchema, (result) => sameLibrary(result.library, target) && sameLibrary(result.context.library, target), "CutAgent runtime returned a project-library switch result for another library.");
      return runtime.startAction(currentGeneration(), "cutagent.action.project.library.switch", sdkProjectLibraryOpenInputSchema.parse({ precondition: options.precondition, library: target }), resultSchema, control(options));
    },
    backup(library, input, options) {
      const target = sdkProjectLibraryReferenceSchema.parse(library);
      if (target.kind !== "disk") throw new TypeError("Only Disk project libraries can be backed up through the current semantic SDK contract.");
      const destinationArtifactId = ArtifactIdSchema.parse(input.destinationArtifactId);
      const resultSchema = bindResult(projectLibraryBackupSchema, (result) => sameLibrary(result.library, target) && result.artifact.artifactId === destinationArtifactId, "CutAgent runtime returned a project-library backup result for another target or artifact.");
      return runtime.startAction(currentGeneration(), "cutagent.action.project.library.backup", sdkProjectLibraryBackupInputSchema.parse({ precondition: options.precondition, library: target, destinationArtifactId }), resultSchema, control(options));
    },
    restore(input, options) {
      const target = Object.freeze({ name: input.name, kind: "disk" as const });
      const resultSchema = bindResult(projectLibraryResultSchema, (result) => sameLibrary(result.library, target), "CutAgent runtime returned a project-library restore result for another library.");
      return runtime.startAction(currentGeneration(), "cutagent.action.project.library.restore", sdkProjectLibraryRestoreInputSchema.parse({ precondition: options.precondition, sourceArtifactId: ArtifactIdSchema.parse(input.sourceArtifactId), libraryName: input.name, directoryPath: input.directoryPath }), resultSchema, control(options));
    },
  };
  Object.setPrototypeOf(libraries, null);
  const collection: ProjectCollectionMutations = {
    libraries: Object.freeze(libraries),
    create(input, options) {
      const resultSchema = bindResult(projectContextResultSchema, (result) => sameProject(result.context.project, { name: input.name }), "CutAgent runtime returned a project creation result for another project.");
      return runtime.startAction(currentGeneration(), "cutagent.action.project.create", sdkProjectCreateInputSchema.parse({ ...input, precondition: options.precondition }), resultSchema, control(options));
    },
    open(project, options) {
      const target = Object.freeze({ id: ProjectIdSchema.parse(project.id), name: project.name });
      const resultSchema = bindResult(projectContextResultSchema, (result) => sameProject(result.context.project, target), "CutAgent runtime returned a project-open result for another project.");
      return runtime.startAction(currentGeneration(), "cutagent.action.project.open", sdkProjectOpenInputSchema.parse({ project: target, precondition: options.precondition }), resultSchema, control(options));
    },
    restore(input, options) {
      const name = input.name;
      const resultSchema = bindResult(projectRestoreResultSchema, (result) => result.restoredProject.name === name, "CutAgent runtime returned a restored project with another identity.");
      return runtime.startAction(currentGeneration(), "cutagent.action.project.restore", sdkProjectRestoreInputSchema.parse({ sourceArtifactId: ArtifactIdSchema.parse(input.sourceArtifactId), name, precondition: options.precondition }), resultSchema, control(options));
    },
  };
  Object.setPrototypeOf(collection, null);
  return Object.freeze(collection);
}

/** Construct project-bound mutations for one exact current project observation. @internal */
export function createProjectBoundMutations(
  runtime: ProjectManagementRuntime,
  generation: number,
  project: ProjectReference,
  readCurrentContext?: (options?: ConnectionControlOptions) => Promise<ProjectContextObservation>,
): ProjectBoundMutations {
  async function assertCurrent(options: ProjectMutationOptions): Promise<void> {
    if (!readCurrentContext) throw invalidResponseFailure("CutAgent runtime cannot revalidate the current project before mutation.");
    const context = await readCurrentContext(options);
    if (!sameProject(context.project, project) || context.projectRevision.status !== "available"
      || String(context.projectRevision.revision) !== String(options.precondition)) {
      throw new CutAgentSdkError({
        kind: PUBLIC_ERROR_KIND_BY_CODE.STALE_REVISION,
        code: "STALE_REVISION",
        message: "The exact current project or its revision changed before mutation.",
        retrySafe: false,
        possibleMutation: "none",
        usage: "not_reserved",
        recovery: ["inspect_state"],
        recoveryGuidance: ["Inspect the current project context and retry with its new revision and the same intent."],
        readbackRequired: false,
      });
    }
  }
  const mutations: ProjectBoundMutations = {
    backup(input, options) {
      const destinationArtifactId = ArtifactIdSchema.parse(input.destinationArtifactId);
      const resultSchema = bindResult(projectBackupSchema, (result) => sameProject(result.project, project) && result.artifact.artifactId === destinationArtifactId, "CutAgent runtime returned a project backup result for another project or artifact.");
      return runtime.startAction(generation, "cutagent.action.project.export", sdkProjectBackupInputSchema.parse({ project, precondition: options.precondition, destinationArtifactId, withStills: input.withStills ?? true }), resultSchema, control(options));
    },
    async rename(name, options) {
      if (typeof name !== "string" || name.trim().length === 0 || name.trim().length > 1024) throw new TypeError("Project name must contain between 1 and 1024 characters.");
      const normalized = name.trim();
      await assertCurrent(options);
      return runtime.startAction(generation, "cutagent.action.project.rename", { name: normalized }, projectRenameResultSchema(project, normalized), control(options));
    },
    async setSetting(key, value, options) {
      if (typeof key !== "string" || key.length === 0 || key.length > 1024) throw new TypeError("Project setting key must contain between 1 and 1024 characters.");
      if (typeof value !== "string" || value.length === 0 || value.length > 4096) throw new TypeError("Project setting value must contain between 1 and 4096 characters.");
      await assertCurrent(options);
      return runtime.startAction(generation, "cutagent.action.project.settings_set", { key, value }, projectSettingResultSchema(key, value), control(options));
    },
  };
  Object.setPrototypeOf(mutations, null);
  return Object.freeze(mutations);
}
