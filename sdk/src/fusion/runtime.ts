import { createHash } from "node:crypto";
import {
  CUTAGENT_SDK_FUSION_GRAPH_ACTION_ID,
  CUTAGENT_SDK_FUSION_GRAPH_CONTRACT_VERSION,
  sdkFusionGraphApplyInputSchema,
  sdkFusionGraphApplyResultSchema,
  sdkFusionGraphImpactPreviewSchema,
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
import { FusionGraphRequestSchema, serializeFusionGraphRequest, type FusionGraphRequest } from "./graph.js";

/** Public action identifier owned by the typed Fusion graph API. @beta */
export const FUSION_GRAPH_APPLY_ACTION_ID = CUTAGENT_SDK_FUSION_GRAPH_ACTION_ID;

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
