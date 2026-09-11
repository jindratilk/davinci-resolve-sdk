import { createHash } from "node:crypto";
import {
  CUTAGENT_SDK_FUSION_GRAPH_ACTION_ID,
  CUTAGENT_SDK_FUSION_GRAPH_CONTRACT_VERSION,
  CUTAGENT_SDK_FUSION_IMAGE_REPLACE_ACTION_ID,
  CUTAGENT_SDK_FUSION_IMAGE_REPLACE_CONTRACT_VERSION,
  sdkFusionImageReplaceInputSchema,
  sdkFusionImageReplaceResultSchema,
  CUTAGENT_SDK_FUSION_TEXT_ACTION_ID,
  sdkFusionGraphApplyInputSchema,
  sdkFusionGraphApplyResultSchema,
  sdkFusionGraphImpactPreviewSchema,
  sdkFusionTextActionInputSchema,
  sdkFusionTextActionResultSchema,
  sdkFusionTextUpdateSchema,
  CUTAGENT_SDK_FUSION_NESTED_TEXT_ACTION_ID,
  sdkFusionNestedTextInputSchema,
  sdkFusionNestedTextResultSchema,
  type SdkFusionCompositionReference,
} from "../generated/sdk-fusion.js";
import {
  sdkProjectIdSchema,
  sdkRevisionSchema,
  sdkTimelineIdSchema,
  sdkTimelineItemIdSchema,
} from "../generated/sdk-identities.js";
import type { CarrierReadRequest, CarrierReadSuccess } from "../core/carrier-session.js";
import type { ConnectionControlOptions } from "../core/public-client-types.js";
import { parseClosedActionSchema } from "../core/action-schema.js";
import {
  ACTION_RUNTIME_CONTRACTS,
  ACTION_SCHEMA_DEFINITIONS,
  type ActionInput,
  type ActionResult,
} from "../generated/actions.js";
import type { OperationHandle, PublicActionId } from "../protocol/operations.js";
import {
  FusionCompositionIdSchema,
  ArtifactIdSchema,
  IdempotencyKeySchema,
  ProjectIdSchema,
  RevisionSchema,
  TimelineIdSchema,
  TimelineItemIdSchema,
  type FusionCompositionId,
  type ArtifactId,
  type IdempotencyKey,
  type ProjectId,
  type Revision,
  type TimelineId,
  type TimelineItemId,
} from "../value-types/identities.js";
import type {
  BoundFrames,
  FrameDuration,
  Frames,
  TimelineRecordPositionOf,
} from "../value-types/time.js";
import { lowerDuration, lowerTimelineRecordPosition } from "../wire/time-adapter.js";
import { FusionGraphRequestSchema, serializeFusionGraphRequest, type FusionGraphRequest } from "./graph.js";

/** Public action identifier owned by the typed Fusion graph API. @beta */
export const FUSION_GRAPH_APPLY_ACTION_ID = CUTAGENT_SDK_FUSION_GRAPH_ACTION_ID;
/** Public action identifier used internally by the plural Fusion image API. @beta */
export const FUSION_IMAGE_REPLACE_ACTION_ID = CUTAGENT_SDK_FUSION_IMAGE_REPLACE_ACTION_ID;

/** Existing plural native action used by the domain insertion method. @beta */
export const FUSION_SETTINGS_INSERT_ACTION_ID = "cutagent.action.fusion.insert_settings.batch" as const;

/** One Fusion setting/template placement in a multi-item insertion. @beta */
export interface FusionSettingInsertion {
  readonly settingArtifactId: ArtifactId;
  readonly clipName?: string;
  readonly recordPosition: TimelineRecordPositionOf<Frames | BoundFrames>;
  readonly clipDuration: FrameDuration;
  readonly videoTrackIndex?: number;
  readonly position?: Readonly<{ readonly x: number; readonly y: number }>;
  readonly text?: string;
  readonly imageArtifactId?: ArtifactId;
  readonly styleMarkdown?: boolean;
  readonly boldStyle?: string;
}

/** Required controls for one ordered Fusion setting insertion request. @beta */
export interface FusionSettingsInsertOptions extends ConnectionControlOptions {
  readonly precondition: Revision;
  readonly idempotencyKey: IdempotencyKey;
}

/** Exact inserted timeline items plus their single coherent revision transition. @beta */
export type FusionSettingsInsertResult = ActionResult<typeof FUSION_SETTINGS_INSERT_ACTION_ID>["insertedItems"];
/** Public action identifier behind `timeline.fusion.setText`. @beta */
export const FUSION_TEXT_ACTION_ID = CUTAGENT_SDK_FUSION_TEXT_ACTION_ID;
/** Public action identifier used internally by the plural nested-text carrier. @beta */
export const FUSION_NESTED_TEXT_ACTION_ID = CUTAGENT_SDK_FUSION_NESTED_TEXT_ACTION_ID;

/** Immutable exact live reference to one Fusion composition. @beta */
export interface FusionCompositionReference {
  /** Opaque durable identity for this exact composition slot. */
  readonly id: FusionCompositionId;
  /** Opaque durable parent project identity. */
  readonly projectId: ProjectId;
  /** Opaque durable parent timeline identity. */
  readonly timelineId: TimelineId;
  /** Opaque durable timeline-item identity. */
  readonly timelineItemId: TimelineItemId;
  /** One-based native composition index on the timeline item. */
  readonly index: number;
  /** Current human-readable composition name. */
  readonly name: string;
  /** Coherent project snapshot revision observed with this reference. */
  readonly projectRevision: Revision;
  /** Coherent timeline snapshot revision observed with this reference. */
  readonly timelineRevision: Revision;
  /** Exact composition revision, including its live graph evidence. */
  readonly revision: Revision;
  /** SHA-256 digest of the bounded native graph evidence. */
  readonly graphDigest: string;
}

/** Typed, side-effect-free impact preview for replacing one exact composition graph. @beta */
export interface FusionGraphImpactPreview {
  readonly kind: "fusion_graph_replace";
  readonly target: FusionCompositionReference;
  readonly precondition: Revision;
  readonly registryDigest: string;
  readonly graphDigest: string;
  readonly intendedEffects: readonly ("replace_nodes" | "replace_connections" | "replace_inputs" | "replace_animation")[];
  readonly protectedState: readonly ("project_identity" | "timeline_identity" | "timeline_item_identity" | "other_timeline_items" | "other_fusion_compositions")[];
  readonly minimumEvidence: readonly ["readback", "structural"];
}

/** Verified result returned after exact structural readback and protected-state verification. @beta */
export interface FusionGraphApplyResult {
  readonly target: FusionCompositionReference;
  readonly registryDigest: string;
  readonly appliedGraphDigest: string;
  readonly readback: {
    readonly graphDigest: string;
    readonly nodes: readonly { readonly id: string; readonly type: string; readonly inputsDigest: string }[];
    readonly connections: readonly {
      readonly source: { readonly node: string; readonly port: string };
      readonly target: { readonly node: string; readonly port: string };
    }[];
    readonly animatedInputs: number;
  };
  readonly renderedEvidence: readonly {
    readonly frame: number;
    readonly artifactId: ArtifactId;
    readonly digest: string;
    readonly mediaType: "image/jpeg";
  }[];
  readonly renderedReview: { readonly outcome: "not_run" };
  readonly semanticReview: { readonly outcome: "not_run" };
  readonly temporalReview: {
    readonly required: boolean;
    readonly sampledFrames: readonly number[];
    readonly outcome: "not_run";
  };
  readonly protectedStatePreserved: true;
}

/** Required controls for one non-retrying Fusion graph mutation. @beta */
export interface FusionGraphApplyOptions extends ConnectionControlOptions {
  /** Exact live revision observed on the target composition. */
  readonly precondition: Revision;
  /** Caller-owned replay key. Reuse only for the identical semantic request. */
  readonly idempotencyKey: IdempotencyKey;
}

/** One exact image replacement in one observed Fusion composition. @beta */
export interface FusionImageReplacement {
  readonly target: FusionCompositionReference;
  readonly imageArtifactId: ArtifactId;
  readonly groupToolName?: string;
  readonly groupInputName?: string;
  readonly importMedia?: boolean;
  readonly zoom?: Readonly<{ x: number; y: number }>;
  readonly position?: Readonly<{ x: number; y: number }>;
}

/** Required controls for one plural Fusion image operation. @beta */
export interface FusionImageReplaceOptions extends ConnectionControlOptions {
  readonly idempotencyKey: IdempotencyKey;
}

/** Ordered per-composition readback from one plural Fusion image operation. @beta */
export interface FusionImageReplaceResult {
  readonly actionId: typeof FUSION_IMAGE_REPLACE_ACTION_ID;
  readonly results: readonly (
    | Readonly<{ index: number; ok: true; timelineItemId: TimelineItemId; compositionIndex: number; imageArtifactId: ArtifactId; durationMs: number; toolName: string; inputName: string; verified: true; revisionBefore: Revision; revisionAfter: Revision }>
    | Readonly<{ index: number; ok: false; timelineItemId: TimelineItemId; compositionIndex: number; imageArtifactId: ArtifactId; durationMs: number; error: Readonly<{ code: string; message: string }> }>
  )[];
  readonly successCount: number;
  readonly failureCount: number;
  readonly durationMs: number;
  readonly protectedStatePreserved: true;
}

/** One exact text input mutation in an observed Fusion composition. @beta */
export interface FusionTextUpdate {
  readonly target: FusionCompositionReference;
  readonly toolName: string;
  readonly inputName: string;
  readonly text: string;
}

/** Required controls for one non-retrying Fusion text operation. @beta */
export interface FusionTextOptions extends ConnectionControlOptions {
  readonly precondition: Revision;
  readonly idempotencyKey: IdempotencyKey;
}

/** Verified result for one or more exact Fusion text mutations. @beta */
export interface FusionTextResult {
  readonly actionId: typeof FUSION_TEXT_ACTION_ID;
  readonly textUpdates: {
    readonly updates: readonly {
      readonly timelineItemId: TimelineItemId;
      readonly compositionIndex: number;
      readonly toolName: string;
      readonly inputName: string;
      readonly text: string;
      readonly verified: true;
    }[];
    readonly revision: {
      readonly revisionBefore: Revision;
      readonly revisionAfter: Revision;
      readonly changed: boolean;
    };
  };
}
/** One nested Fusion template text change. @beta */
export interface FusionNestedTextUpdate {
  /** Exact outer timeline item that owns the nested template. */
  readonly timelineItemId: TimelineItemId;
  /** One-based Fusion composition index associated with the template item. */
  readonly compositionIndex: number;
  readonly header?: string;
  readonly body?: string;
  readonly headerClipName?: string;
  readonly bodyClipName?: string;
  readonly headerUppercase?: boolean;
  readonly headerDoubleSpaces?: boolean;
  readonly boldStyle?: string;
}

/** Required controls for one plural nested-text operation. @beta */
export interface FusionNestedTextMutationOptions extends ConnectionControlOptions {
  /** Exact timeline revision observed before the plural mutation. */
  readonly precondition: Revision;
  /** Caller-owned replay identity for the complete ordered update list. */
  readonly idempotencyKey: IdempotencyKey;
}

/** Per-item readback from a plural nested-text operation. @beta */
export type FusionNestedTextItemResult =
  | Readonly<{
    index: number;
    status: "succeeded";
    timelineItemId: TimelineItemId;
    headerUpdated: boolean;
    bodyUpdated: boolean;
    revisionBefore: Revision;
    revisionAfter: Revision;
  }>
  | Readonly<{
    index: number;
    status: "failed";
    timelineItemId: TimelineItemId;
    code: string;
    message: string;
  }>;

/** Ordered, verified result of changing one or more nested Fusion templates. @beta */
export interface FusionNestedTextMutationResult {
  readonly actionId: typeof FUSION_NESTED_TEXT_ACTION_ID;
  readonly projectId: ProjectId;
  readonly timelineId: TimelineId;
  readonly revisionBefore: Revision;
  readonly revisionAfter: Revision;
  readonly changed: boolean;
  readonly successCount: number;
  readonly failureCount: number;
  readonly results: readonly FusionNestedTextItemResult[];
  readonly protectedStatePreserved: true;
}
/** One exact live Fusion composition with typed preview and apply methods. @beta */
export interface FusionComposition extends FusionCompositionReference {
  /** Compute the complete public-safe impact before dispatch. This never mutates. */
  previewApply(graph: FusionGraphRequest): FusionGraphImpactPreview;
  /** Create one durable graph replacement operation. The SDK never retries this dispatch. */
  applyGraph(
    graph: FusionGraphRequest,
    options: FusionGraphApplyOptions,
  ): Promise<OperationHandle<FusionGraphApplyResult, typeof FUSION_GRAPH_APPLY_ACTION_ID>>;
}

/** Fusion compositions scoped to one exact timeline. @beta */
export interface FusionCompositions {
  /** Inspect all exact compositions on a durable item from one coherent snapshot revision. */
  forTimelineItem(
    timelineItemId: TimelineItemId,
    expectedRevision: Revision,
    options?: ConnectionControlOptions,
  ): Promise<readonly FusionComposition[]>;
  /** Replace images in one or many exact compositions through one native plural operation. */
  replaceImages(
    replacements: FusionImageReplacement | readonly FusionImageReplacement[],
    options: FusionImageReplaceOptions,
  ): Promise<OperationHandle<FusionImageReplaceResult, typeof FUSION_IMAGE_REPLACE_ACTION_ID>>;
  /** Insert one setting or an ordered list through one native request and one verification boundary. */
  insertSettings(
    insertionOrInsertions: FusionSettingInsertion | readonly FusionSettingInsertion[],
    options: FusionSettingsInsertOptions,
  ): Promise<OperationHandle<FusionSettingsInsertResult, typeof FUSION_SETTINGS_INSERT_ACTION_ID>>;
  /** Set one exact text node or several exact text nodes in one native operation. */
  setText(
    updates: FusionTextUpdate | readonly FusionTextUpdate[],
    options: FusionTextOptions,
  ): Promise<OperationHandle<FusionTextResult, typeof FUSION_TEXT_ACTION_ID>>;
  /**
   * Change nested header/body text on one template or an ordered non-empty list.
   * All targets share one native setup and one durable operation.
   */
  updateNestedText(
    updates: FusionNestedTextUpdate | readonly FusionNestedTextUpdate[],
    options: FusionNestedTextMutationOptions,
  ): Promise<OperationHandle<FusionNestedTextMutationResult, typeof FUSION_NESTED_TEXT_ACTION_ID>>;
}

/** @internal */
export interface FusionObjectRuntime {
  readonly generation: number;
  readAtGeneration(
    generation: number,
    request: CarrierReadRequest,
    options?: ConnectionControlOptions,
  ): Promise<CarrierReadSuccess>;
  startAction<TResult, TAction extends PublicActionId>(
    generation: number,
    actionId: TAction,
    input: unknown,
    resultSchema: { parse(value: unknown): TResult },
    options?: ConnectionControlOptions & { idempotencyKey?: string },
  ): Promise<OperationHandle<TResult, TAction>>;
}

function digestGraph(graph: FusionGraphRequest): string {
  return `sha256:${createHash("sha256").update(serializeFusionGraphRequest(graph), "utf8").digest("hex")}`;
}

function immutableReference(raw: SdkFusionCompositionReference): FusionCompositionReference {
  return Object.freeze({
    id: FusionCompositionIdSchema.parse(raw.id),
    projectId: ProjectIdSchema.parse(raw.projectId),
    timelineId: TimelineIdSchema.parse(raw.timelineId),
    timelineItemId: TimelineItemIdSchema.parse(raw.timelineItemId),
    index: raw.index,
    name: raw.name,
    projectRevision: RevisionSchema.parse(raw.projectRevision),
    timelineRevision: RevisionSchema.parse(raw.timelineRevision),
    revision: RevisionSchema.parse(raw.revision),
    graphDigest: raw.graphDigest,
  });
}

const fusionSettingsInsertResultSchema = Object.freeze({
  parse(value: unknown): FusionSettingsInsertResult {
    const result = parseClosedActionSchema<ActionResult<typeof FUSION_SETTINGS_INSERT_ACTION_ID>>(
      ACTION_RUNTIME_CONTRACTS[FUSION_SETTINGS_INSERT_ACTION_ID].result,
      ACTION_SCHEMA_DEFINITIONS,
      value,
      `${FUSION_SETTINGS_INSERT_ACTION_ID}.result`,
    );
    return Object.freeze({
      ...result.insertedItems,
      items: Object.freeze(result.insertedItems.items.map((item) => Object.freeze({ ...item }))),
      revision: Object.freeze({ ...result.insertedItems.revision }),
    });
  },
});

function createComposition(
  runtime: FusionObjectRuntime,
  generation: number,
  raw: SdkFusionCompositionReference,
): FusionComposition {
  const reference = immutableReference(raw);
  const previewApply = (graphInput: FusionGraphRequest): FusionGraphImpactPreview => {
    const graph = FusionGraphRequestSchema.parse(graphInput) as unknown as FusionGraphRequest;
    const parsed = sdkFusionGraphImpactPreviewSchema.parse({
      kind: "fusion_graph_replace",
      target: raw,
      precondition: reference.revision,
      registryDigest: graph.registryDigest,
      graphDigest: digestGraph(graph),
      intendedEffects: ["replace_nodes", "replace_connections", "replace_inputs", "replace_animation"],
      protectedState: ["project_identity", "timeline_identity", "timeline_item_identity", "other_timeline_items", "other_fusion_compositions"],
      minimumEvidence: ["readback", "structural"],
    });
    return Object.freeze({ ...parsed, target: reference, precondition: reference.revision });
  };
  const composition: FusionComposition = {
    ...reference,
    previewApply,
    async applyGraph(graphInput, options) {
      const graph = FusionGraphRequestSchema.parse(graphInput) as unknown as FusionGraphRequest;
      const precondition = RevisionSchema.parse(options.precondition);
      if (precondition !== reference.revision) {
        throw new TypeError("Fusion graph precondition must equal the exact observed composition revision.");
      }
      const idempotencyKey = IdempotencyKeySchema.parse(options.idempotencyKey);
      const input = sdkFusionGraphApplyInputSchema.parse({
        contractVersion: CUTAGENT_SDK_FUSION_GRAPH_CONTRACT_VERSION,
        target: raw,
        precondition,
        graph,
        preview: previewApply(graph),
        idempotencyKey,
      });
      return runtime.startAction(
        generation,
        FUSION_GRAPH_APPLY_ACTION_ID,
        input,
        FusionGraphApplyResultSchema,
        options,
      );
    },
  };
  Object.setPrototypeOf(composition, null);
  return Object.freeze(composition);
}

/** Bind the semantic Fusion collection to one exact project/timeline generation. @internal */
export function createFusionCompositions(
  runtime: FusionObjectRuntime,
  generation: number,
  projectId: ProjectId,
  timelineId: TimelineId,
): FusionCompositions {
  const collection: FusionCompositions = {
    async forTimelineItem(timelineItemIdInput, expectedRevisionInput, options = {}) {
      const timelineItemId = TimelineItemIdSchema.parse(timelineItemIdInput);
      const expectedRevision = RevisionSchema.parse(expectedRevisionInput);
      const response = await runtime.readAtGeneration(generation, {
        operation: "fusion.compositions",
        projectId: sdkProjectIdSchema.parse(projectId),
        timelineId: sdkTimelineIdSchema.parse(timelineId),
        timelineItemId: sdkTimelineItemIdSchema.parse(timelineItemId),
        expectedRevision: sdkRevisionSchema.parse(expectedRevision),
      }, options);
      if (response.operation !== "fusion.compositions") {
        throw new TypeError("CutAgent runtime returned the wrong semantic Fusion read result.");
      }
      if (response.data.some((raw) => (
        String(raw.projectId) !== String(projectId)
        || String(raw.timelineId) !== String(timelineId)
        || String(raw.timelineItemId) !== String(timelineItemId)
      ))) {
        throw new TypeError("CutAgent runtime returned an uncorrelated Fusion composition result.");
      }
      return Object.freeze(response.data.map((raw) => createComposition(runtime, generation, raw)));
    },
    async replaceImages(replacementsInput, options) {
      const replacements = Array.isArray(replacementsInput) ? replacementsInput : [replacementsInput];
      if (replacements.length === 0) throw new TypeError("Fusion image replacement requires at least one target.");
      const idempotencyKey = IdempotencyKeySchema.parse(options.idempotencyKey);
      const targets = replacements.map((replacement) => immutableReference(replacement.target as unknown as SdkFusionCompositionReference));
      const firstTarget = targets[0]!;
      if (targets.some((target) => target.projectId !== projectId || target.timelineId !== timelineId)) {
        throw new TypeError("Fusion image targets must belong to the bound project and timeline.");
      }
      if (targets.some((target) => target.timelineRevision !== firstTarget.timelineRevision)) {
        throw new TypeError("Fusion image targets must share one observed timeline revision.");
      }
      const items = replacements.map((replacement, index) => ({
        timelineItemId: targets[index]!.timelineItemId,
        compositionIndex: targets[index]!.index,
        compositionRevision: targets[index]!.revision,
        imageArtifactId: ArtifactIdSchema.parse(replacement.imageArtifactId),
        ...(replacement.groupToolName === undefined ? {} : { groupToolName: replacement.groupToolName }),
        ...(replacement.groupInputName === undefined ? {} : { groupInputName: replacement.groupInputName }),
        ...(replacement.importMedia === undefined ? {} : { importMedia: replacement.importMedia }),
        ...(replacement.zoom === undefined ? {} : { zoom: replacement.zoom }),
        ...(replacement.position === undefined ? {} : { position: replacement.position }),
      }));
      const input = sdkFusionImageReplaceInputSchema.parse({
        contractVersion: CUTAGENT_SDK_FUSION_IMAGE_REPLACE_CONTRACT_VERSION,
        projectId,
        timelineId,
        revision: firstTarget.timelineRevision,
        items,
      });
      return runtime.startAction(
        generation,
        FUSION_IMAGE_REPLACE_ACTION_ID,
        input,
        FusionImageReplaceResultSchema,
        { ...options, idempotencyKey },
      );
    },
    async insertSettings(insertionOrInsertions, options) {
      const insertions = Array.isArray(insertionOrInsertions)
        ? [...insertionOrInsertions]
        : [insertionOrInsertions];
      if (insertions.length === 0 || insertions.length > 100) {
        throw new TypeError("Fusion setting insertion requires 1 through 100 items.");
      }
      const revision = RevisionSchema.parse(options.precondition);
      const idempotencyKey = IdempotencyKeySchema.parse(options.idempotencyKey);
      const items = insertions.map((item) => ({
        ...item,
        settingArtifactId: ArtifactIdSchema.parse(item.settingArtifactId),
        imageArtifactId: item.imageArtifactId === undefined
          ? undefined
          : ArtifactIdSchema.parse(item.imageArtifactId),
        recordPosition: lowerTimelineRecordPosition(item.recordPosition),
        clipDuration: lowerDuration(item.clipDuration),
      }));
      const input = parseClosedActionSchema<ActionInput<typeof FUSION_SETTINGS_INSERT_ACTION_ID>>(
        ACTION_RUNTIME_CONTRACTS[FUSION_SETTINGS_INSERT_ACTION_ID].input,
        ACTION_SCHEMA_DEFINITIONS,
        { projectId, timelineId, revision, items },
        `${FUSION_SETTINGS_INSERT_ACTION_ID}.input`,
      );
      return runtime.startAction(
        generation,
        FUSION_SETTINGS_INSERT_ACTION_ID,
        input,
        fusionSettingsInsertResultSchema,
        { ...options, idempotencyKey },
      );
    },
    async setText(updatesInput, options) {
      const updates = Array.isArray(updatesInput) ? updatesInput : [updatesInput];
      if (updates.length === 0) throw new TypeError("Fusion text updates must not be empty.");
      const precondition = RevisionSchema.parse(options.precondition);
      const idempotencyKey = IdempotencyKeySchema.parse(options.idempotencyKey);
      const input = sdkFusionTextActionInputSchema.parse({
        projectId: sdkProjectIdSchema.parse(projectId),
        timelineId: sdkTimelineIdSchema.parse(timelineId),
        revision: sdkRevisionSchema.parse(precondition),
        updates: updates.map((updateInput) => {
          const target = updateInput.target;
          const update = sdkFusionTextUpdateSchema.parse({
            target: {
              id: target.id,
              projectId: target.projectId,
              timelineId: target.timelineId,
              timelineItemId: target.timelineItemId,
              index: target.index,
              name: target.name,
              projectRevision: target.projectRevision,
              timelineRevision: target.timelineRevision,
              revision: target.revision,
              graphDigest: target.graphDigest,
            },
            toolName: updateInput.toolName,
            inputName: updateInput.inputName,
            text: updateInput.text,
          });
          if (String(update.target.projectId) !== String(projectId)
            || String(update.target.timelineId) !== String(timelineId)) {
            throw new TypeError("Every Fusion text target must belong to this exact timeline.");
          }
          if (update.target.timelineRevision !== precondition) {
            throw new TypeError("Every Fusion text target must share the requested timeline revision.");
          }
          return {
            timelineItemId: update.target.timelineItemId,
            compositionIndex: update.target.index,
            compositionRevision: update.target.revision,
            toolName: update.toolName,
            inputName: update.inputName,
            text: update.text,
          };
        }),
      });
      return runtime.startAction(
        generation,
        FUSION_TEXT_ACTION_ID,
        input,
        FusionTextResultSchema,
        { ...options, idempotencyKey },
      );
    },
    async updateNestedText(updateInput, options) {
      const precondition = RevisionSchema.parse(options.precondition);
      const idempotencyKey = IdempotencyKeySchema.parse(options.idempotencyKey);
      const updates = Array.isArray(updateInput) ? [...updateInput] : [updateInput];
      const input = sdkFusionNestedTextInputSchema.parse({
        projectId: sdkProjectIdSchema.parse(projectId),
        timelineId: sdkTimelineIdSchema.parse(timelineId),
        revision: sdkRevisionSchema.parse(precondition),
        updates,
      });
      const resultSchema = Object.freeze({
        parse(value: unknown): FusionNestedTextMutationResult {
          const parsed = sdkFusionNestedTextResultSchema.parse(value);
          if (parsed.projectId !== projectId || parsed.timelineId !== timelineId
            || parsed.revisionBefore !== precondition || parsed.results.length !== input.updates.length
            || parsed.results.some((row, index) => row.timelineItemId !== input.updates[index]?.timelineItemId)) {
            throw new TypeError("CutAgent runtime returned an uncorrelated nested Fusion text result.");
          }
          const results = parsed.results.map((row) => Object.freeze({
            ...row,
            timelineItemId: TimelineItemIdSchema.parse(row.timelineItemId),
            ...(row.status === "succeeded" ? {
              revisionBefore: RevisionSchema.parse(row.revisionBefore),
              revisionAfter: RevisionSchema.parse(row.revisionAfter),
            } : {}),
          })) as readonly FusionNestedTextItemResult[];
          return Object.freeze({
            ...parsed,
            projectId: ProjectIdSchema.parse(parsed.projectId),
            timelineId: TimelineIdSchema.parse(parsed.timelineId),
            revisionBefore: RevisionSchema.parse(parsed.revisionBefore),
            revisionAfter: RevisionSchema.parse(parsed.revisionAfter),
            results: Object.freeze(results),
          });
        },
      });
      return runtime.startAction(
        generation,
        FUSION_NESTED_TEXT_ACTION_ID,
        input,
        resultSchema,
        { ...options, idempotencyKey },
      );
    },
  };
  Object.setPrototypeOf(collection, null);
  return Object.freeze(collection);
}

/** Runtime validator used by the trusted action seam. @internal */
export const FusionGraphApplyResultSchema = Object.freeze({
  parse(value: unknown): FusionGraphApplyResult {
    const parsed = sdkFusionGraphApplyResultSchema.parse(value);
    return Object.freeze({
      ...parsed,
      target: immutableReference(parsed.target),
      renderedEvidence: Object.freeze(parsed.renderedEvidence.map((row) => Object.freeze({
        ...row,
        artifactId: ArtifactIdSchema.parse(row.artifactId),
      }))),
    });
  },
});

/** Runtime validator for ordered plural Fusion image readback. @internal */
export const FusionImageReplaceResultSchema = Object.freeze({
  parse(value: unknown): FusionImageReplaceResult {
    const parsed = sdkFusionImageReplaceResultSchema.parse(value);
    return Object.freeze({
      ...parsed,
      results: Object.freeze(parsed.results.map((row) => Object.freeze({
        ...row,
        timelineItemId: TimelineItemIdSchema.parse(row.timelineItemId),
        imageArtifactId: ArtifactIdSchema.parse(row.imageArtifactId),
        ...(row.ok ? {
          revisionBefore: RevisionSchema.parse(row.revisionBefore),
          revisionAfter: RevisionSchema.parse(row.revisionAfter),
        } : {}),
      }))),
    }) as FusionImageReplaceResult;
  },
});

/** @internal */
export const FusionTextResultSchema = Object.freeze({
  parse(value: unknown): FusionTextResult {
    return sdkFusionTextActionResultSchema.parse(value) as FusionTextResult;
  },
});
