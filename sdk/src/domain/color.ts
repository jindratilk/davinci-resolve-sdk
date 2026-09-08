import { z } from "zod";
import {
  sdkColorEffectAddInputSchema,
  sdkColorGradeApplyInputSchema,
  sdkColorMutationResultSchema,
  sdkColorNodeAddInputSchema,
  sdkColorNodeLabelSetInputSchema,
  sdkColorPrimarySetInputSchema,
  type SdkOperationEvent,
} from "../generated/sdk-operations.js";
import { sdkIdempotencyKeySchema } from "../generated/sdk-identities.js";
import { createTypedOperationHandle } from "../core/operations.js";
import type { CarrierOperationRequest } from "../core/carrier-contract.js";
import type { EstablishedCarrierSession } from "../core/carrier-session.js";
import type { ConnectionControlOptions } from "../core/public-client-types.js";
import type { OperationHandle } from "../protocol/operations.js";
import { IdempotencyKeySchema, RevisionSchema, TimelineItemIdSchema, type IdempotencyKey, type Revision, type TimelineItemId } from "../value-types/identities.js";
import type { ColorTargetSnapshot } from "./object-model.js";
import { hydrateTimecode, lowerTimelineRecordPosition } from "../wire/time-adapter.js";

/** Public semantic Color action discriminators. @beta */
export type ColorActionId =
  | "cutagent.action.color.page.primary_set"
  | "cutagent.action.color.page.node_add"
  | "cutagent.action.color.node.label_set"
  | "cutagent.action.color.grade_apply"
  | "cutagent.action.color.page.resolvefx_add";

/** Bounded primary controls with stable semantic meanings. Arbitrary property dictionaries are not accepted. @beta */
export interface ColorPrimaryCorrection {
  readonly contrast?: number;
  readonly pivot?: number;
  readonly temperature?: number;
  readonly tint?: number;
  readonly hue?: number;
  readonly colorBoost?: number;
  readonly midtoneDetail?: number;
  readonly shadows?: number;
  readonly highlights?: number;
}

/** Opaque Color Library identity. Filesystem paths are never accepted by the public SDK. @beta */
export interface ColorAssetReference {
  readonly assetId: string;
  readonly fileId: string;
}

/** Curated ResolveFX families with a stable high-level contract. @beta */
export type ColorEffect = "gaussian_blur" | "sharpen" | "film_grain";
/** Verified node topology choices. @beta */
export type ColorNodeTopology = "serial" | "parallel" | "layer";
/** DRX keyframe-alignment semantics. @beta */
export type ColorGradeAlignment = "none" | "source_timecode" | "start_frame";

/** One closed semantic Color mutation requested by an impact preview. @beta */
export type ColorMutation =
  | Readonly<{ kind: "primary_set"; nodeIndex: number; correction: ColorPrimaryCorrection }>
  | Readonly<{ kind: "node_add"; afterNodeIndex: number; topology: ColorNodeTopology }>
  | Readonly<{ kind: "node_label_set"; nodeIndex: number; label: string }>
  | Readonly<{ kind: "grade_apply"; asset: ColorAssetReference; alignment: ColorGradeAlignment }>
  | Readonly<{ kind: "effect_add"; nodeIndex: number; effect: ColorEffect }>;

/** Immutable inspectable plan required before a Color mutation. @beta */
export interface ColorImpactPreview {
  readonly actionId: ColorActionId;
  readonly target: Readonly<{
    clipId: TimelineItemId;
    colorRevision: Revision;
    timelineRevision: Revision;
    nodeStackLayerIndex: number;
    trackIndex: number;
    recordFrame: number;
  }>;
  readonly mutation: ColorMutation;
  readonly verification: "independent_semantic_readback";
  readonly recovery: "route_specific_checkpoint_or_manual_recovery";
  readonly summary: string;
}

/** Sanitized verified result for one durable Color mutation. @beta */
export interface ColorMutationResult {
  readonly kind: ColorMutation["kind"];
  readonly colorRevision: Revision;
  readonly timelineRevision: Revision;
  readonly nodeStackLayerIndex: number;
  readonly clipId: TimelineItemId;
  readonly nodeCount: number;
  readonly affectedNodeIndex: number | null;
  readonly checkpoint: Readonly<{ availability: "available" | "unavailable"; restored: boolean }>;
}

/** Required replay-safe controls for one Color mutation. @beta */
export interface ColorMutationOptions extends ConnectionControlOptions { readonly idempotencyKey: IdempotencyKey; }

type PreviewInternal = { readonly public: ColorImpactPreview; readonly snapshot: ColorTargetSnapshot; readonly input: Record<string, unknown>; readonly collection: object };
const previewInternals = new WeakMap<object, PreviewInternal>();

export interface ColorRuntime {
  sessionAtGeneration(generation: number): EstablishedCarrierSession;
  createOperationAtGeneration(generation: number, request: Parameters<EstablishedCarrierSession["operation"]>[0], options?: ConnectionControlOptions): Promise<SdkOperationEvent>;
}

/** High-level Color inspection, impact preview, and durable mutation API. @beta */
export interface Color {
  current(options?: ConnectionControlOptions & { readonly nodeStackLayerIndex?: number }): Promise<ColorTargetSnapshot>;
  previewPrimary(snapshot: ColorTargetSnapshot, nodeIndex: number, correction: ColorPrimaryCorrection): ColorImpactPreview;
  previewAddNode(snapshot: ColorTargetSnapshot, input: { readonly afterNodeIndex: number; readonly topology?: ColorNodeTopology }): ColorImpactPreview;
  previewSetNodeLabel(snapshot: ColorTargetSnapshot, nodeIndex: number, label: string): ColorImpactPreview;
  previewApplyGrade(snapshot: ColorTargetSnapshot, asset: ColorAssetReference, options?: { readonly alignment?: ColorGradeAlignment }): ColorImpactPreview;
  previewAddEffect(snapshot: ColorTargetSnapshot, nodeIndex: number, effect: ColorEffect): ColorImpactPreview;
  apply(preview: ColorImpactPreview, options: ColorMutationOptions): Promise<OperationHandle<ColorMutationResult, ColorActionId>>;
}

function freeze<T extends object>(value: T): Readonly<T> { Object.setPrototypeOf(value, null); return Object.freeze(value); }

function targetRecordFrame(snapshot: ColorTargetSnapshot): number {
  const lowered = lowerTimelineRecordPosition(snapshot.clip.recordRange.start, { frameRate: snapshot.frameRate });
  return lowered.value.kind === "frames" ? lowered.value.value : hydrateTimecode(lowered.value).toFrames().value;
}

function targetInput(snapshot: ColorTargetSnapshot) {
  return {
    projectId: String(snapshot.projectId), timelineId: String(snapshot.timelineId), colorRevision: String(snapshot.revision),
    timelineRevision: String(snapshot.timelineRevision), nodeStackLayerIndex: snapshot.nodeStackLayerIndex,
    clipId: String(snapshot.clip.id), trackIndex: snapshot.track.index,
    recordFrame: targetRecordFrame(snapshot),
  };
}

const definitions = {
  primary_set: { actionId: "cutagent.action.color.page.primary_set", schema: sdkColorPrimarySetInputSchema },
  node_add: { actionId: "cutagent.action.color.page.node_add", schema: sdkColorNodeAddInputSchema },
  node_label_set: { actionId: "cutagent.action.color.node.label_set", schema: sdkColorNodeLabelSetInputSchema },
  grade_apply: { actionId: "cutagent.action.color.grade_apply", schema: sdkColorGradeApplyInputSchema },
  effect_add: { actionId: "cutagent.action.color.page.resolvefx_add", schema: sdkColorEffectAddInputSchema },
} as const;

/** Construct the Color facade for one exact timeline generation. @internal */
export function createColor(runtime: ColorRuntime, generation: number, read: (nodeStackLayerIndex: number, options?: ConnectionControlOptions) => Promise<ColorTargetSnapshot>): Color {
  const snapshots = new WeakSet<object>();
  const collection = Object.freeze({});
  const current = async (options: ConnectionControlOptions & { readonly nodeStackLayerIndex?: number } = {}) => {
    const { nodeStackLayerIndex = 1, ...controls } = options;
    if (!Number.isSafeInteger(nodeStackLayerIndex) || nodeStackLayerIndex < 1 || nodeStackLayerIndex > 4096) throw new TypeError("Color node-stack layer index must be from 1 through 4096.");
    const snapshot = await read(nodeStackLayerIndex, controls);
    snapshots.add(snapshot);
    return snapshot;
  };
  const make = (snapshot: ColorTargetSnapshot, mutation: ColorMutation, summary: string): ColorImpactPreview => {
    if (!snapshots.has(snapshot)) throw new TypeError("Color impact previews require a snapshot read by this exact timeline Color facade.");
    const nodeIndex = "nodeIndex" in mutation ? mutation.nodeIndex : "afterNodeIndex" in mutation ? mutation.afterNodeIndex : null;
    if (nodeIndex !== null && !snapshot.nodeGraph.nodes.some((node) => node.index === nodeIndex)) throw new TypeError("Color node reference is stale or outside the inspected graph.");
    const definition = definitions[mutation.kind];
    const semanticInput = mutation.kind === "primary_set" ? { nodeIndex: mutation.nodeIndex, correction: mutation.correction }
      : mutation.kind === "node_add" ? { afterNodeIndex: mutation.afterNodeIndex, topology: mutation.topology }
        : mutation.kind === "node_label_set" ? { nodeIndex: mutation.nodeIndex, label: mutation.label }
          : mutation.kind === "grade_apply" ? { asset: mutation.asset, alignment: mutation.alignment }
            : { nodeIndex: mutation.nodeIndex, effect: mutation.effect };
    let input: Record<string, unknown>;
    try {
      input = definition.schema.parse({ ...targetInput(snapshot), ...semanticInput });
    } catch {
      throw new TypeError("Color mutation values are outside the bounded semantic contract.");
    }
    const value = freeze({
      actionId: definition.actionId, target: freeze({ clipId: snapshot.clip.id, colorRevision: snapshot.revision, timelineRevision: snapshot.timelineRevision, nodeStackLayerIndex: snapshot.nodeStackLayerIndex, trackIndex: snapshot.track.index, recordFrame: targetRecordFrame(snapshot) }),
      mutation: freeze({ ...mutation }), verification: "independent_semantic_readback" as const,
      recovery: "route_specific_checkpoint_or_manual_recovery" as const, summary,
    });
    previewInternals.set(value, { public: value, snapshot, input, collection });
    return value;
  };
  return freeze({
    current,
    previewPrimary: (snapshot, nodeIndex, correction) => make(snapshot, { kind: "primary_set", nodeIndex, correction }, `Set bounded primary controls on Color node ${nodeIndex}.`),
    previewAddNode: (snapshot, input) => {
      const topology = input.topology ?? "serial";
      if (topology !== "serial" && snapshot.nodeGraph.nodeCount !== 1) throw new TypeError("Parallel and layer Color topology can only be added to an inspected single-node graph.");
      if (topology === "serial" && input.afterNodeIndex !== snapshot.nodeGraph.nodeCount) throw new TypeError("Serial Color node add appends after the inspected tail node; arbitrary insertion is not exposed by this SDK slice.");
      return make(snapshot, { kind: "node_add", afterNodeIndex: input.afterNodeIndex, topology }, `Add one ${topology} Color node after node ${input.afterNodeIndex}.`);
    },
    previewSetNodeLabel: (snapshot, nodeIndex, label) => make(snapshot, { kind: "node_label_set", nodeIndex, label }, `Set the label of Color node ${nodeIndex}.`),
    previewApplyGrade: (snapshot, asset, options = {}) => make(snapshot, { kind: "grade_apply", asset, alignment: options.alignment ?? "none" }, "Apply one verified Color Library DRX asset to the exact clip."),
    previewAddEffect: (snapshot, nodeIndex, effect) => make(snapshot, { kind: "effect_add", nodeIndex, effect }, `Add the curated ${effect} effect to Color node ${nodeIndex}.`),
    async apply(preview, options) {
      const internal = previewInternals.get(preview);
      if (!internal || internal.public !== preview || internal.collection !== collection) throw new TypeError("Color mutation requires its matching CutAgent impact preview.");
      IdempotencyKeySchema.parse(options.idempotencyKey);
      const request = { operation: "operation.create", actionId: preview.actionId, input: internal.input, idempotencyKey: sdkIdempotencyKeySchema.parse(options.idempotencyKey) } as CarrierOperationRequest;
      const event = await runtime.createOperationAtGeneration(generation, request, options);
      const schema = z.object({}).passthrough().transform((value) => {
        const result = sdkColorMutationResultSchema.parse(value);
        if (result.nodeStackLayerIndex !== preview.target.nodeStackLayerIndex) {
          throw new TypeError("CutAgent runtime returned a Color mutation result for another node-stack layer.");
        }
        return freeze({ ...result, colorRevision: RevisionSchema.parse(result.colorRevision), timelineRevision: RevisionSchema.parse(result.timelineRevision), clipId: TimelineItemIdSchema.parse(result.clipId), checkpoint: freeze(result.checkpoint) });
      });
      return createTypedOperationHandle({ session: () => runtime.sessionAtGeneration(generation) }, event, preview.actionId, schema);
    },
  });
}
