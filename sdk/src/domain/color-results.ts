import { z } from "zod";
import {
  CUTAGENT_SDK_NORMALIZED_COLOR_ARTIFACT_ACTION_IDS,
  CUTAGENT_SDK_NORMALIZED_COLOR_OBSERVATION_ACTION_IDS,
  CUTAGENT_SDK_NORMALIZED_COLOR_RESULT_KIND_BY_ACTION_ID,
} from "../generated/sdk-operation-actions.js";

const resultKindByActionId = CUTAGENT_SDK_NORMALIZED_COLOR_RESULT_KIND_BY_ACTION_ID as Record<string, string>;
const colorActionIds = new Set(Object.keys(resultKindByActionId));
const observationActionIds = new Set<string>(CUTAGENT_SDK_NORMALIZED_COLOR_OBSERVATION_ACTION_IDS);
const artifactActionIds = new Set<string>(CUTAGENT_SDK_NORMALIZED_COLOR_ARTIFACT_ACTION_IDS);
const entityKindsByResultKind: Record<string, ReadonlySet<string>> = Object.fromEntries(Object.entries({
  gallery_album: ["album"], gallery_still: ["still", "album"], group: ["group", "clip"],
  tracker: ["tracker", "window", "qualifier"], mask: ["window", "tracker"],
  match: ["clip", "still", "parameter"], grade_asset: ["lut", "still", "version"],
  node_graph: ["node", "effect", "parameter"], qualifier: ["qualifier", "parameter"],
  version: ["version"], composition: ["node", "effect", "parameter"],
  effect: ["effect", "node", "parameter"], inspection: ["other", "clip", "node", "parameter"],
  grade: ["node", "parameter", "lut", "clip"],
}).map(([kind, kinds]) => [kind, new Set(kinds)]));
const privatePathText = /(?:^|[^A-Za-z0-9._~-])\/(?!\/)[A-Za-z0-9._~-]+(?:\/|$|[^A-Za-z0-9._~-])|file:\/{2,3}|[A-Za-z]:\\|\\\\|~\/|argv|sqlite|project\.db|workaround|executionroute|[a-z]+_(?:native|gui)/i;
const privateRouteText = /\b[a-z]+(?:[./-][a-z_]+)+\b/;
const revision = z.string().regex(/^revision_[A-Za-z0-9][A-Za-z0-9._~-]*$/);
const nullableRevision = revision.nullable();
const publicText = z.string().max(4096).refine(
  (value) => !privatePathText.test(value) && !privateRouteText.test(value),
  "Private execution or local-path text is forbidden",
);

const namedValue = z.object({
  name: publicText.min(1).max(256),
  value: z.union([z.null(), z.boolean(), z.number().finite(), publicText, z.array(z.number().finite()).max(64)]),
}).strict();
const artifact = z.object({
  artifactId: z.string().regex(/^artifact_[A-Za-z0-9][A-Za-z0-9._~-]*$/),
  kind: z.enum(["drx", "lut", "still", "frame", "thumbnail", "analysis", "graph", "other"]),
  mediaType: z.string().min(3).max(255).regex(/^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,126}\/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,126}$/),
  sha256: z.string().regex(/^[a-f0-9]{64}$/),
  byteLength: z.number().int().nonnegative().safe(),
}).strict();
const entity = z.object({
  id: z.string().regex(/^color_entity_[A-Za-z0-9][A-Za-z0-9._~-]*$/),
  kind: z.enum(["node", "group", "clip", "album", "still", "lut", "effect", "qualifier", "window", "tracker", "version", "parameter", "other"]),
  name: publicText.max(1024).nullable(),
  index: z.number().int().positive().safe().nullable(),
  enabled: z.boolean().nullable(),
  values: z.array(namedValue).max(256),
}).strict();
const state = z.object({
  kind: z.enum(["gallery_album", "gallery_still", "group", "tracker", "mask", "match", "grade_asset", "node_graph", "qualifier", "version", "composition", "effect", "inspection", "grade"]),
  entities: z.array(entity).max(4096),
  values: z.array(namedValue).max(512),
  artifacts: z.array(artifact).max(32),
}).strict();
const target = z.object({
  projectId: z.string().regex(/^project_[A-Za-z0-9][A-Za-z0-9._~-]*$/),
  projectRevision: revision,
  timelineId: z.string().regex(/^timeline_(?!item_)[A-Za-z0-9][A-Za-z0-9._~-]*$/).nullable(),
  timelineRevision: nullableRevision,
  timelineItemId: z.string().regex(/^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$/).nullable(),
  snapshotTimelineItemId: z.string().regex(/^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$/).nullable(),
  colorRevision: nullableRevision,
  trackIndex: z.number().int().positive().safe().nullable(),
  recordFrame: z.number().int().safe().nullable(),
  nodeIndex: z.number().int().positive().safe().nullable(),
  groupId: z.string().regex(/^group_[A-Za-z0-9][A-Za-z0-9._~-]*$/).nullable(),
  albumId: z.string().regex(/^album_[A-Za-z0-9][A-Za-z0-9._~-]*$/).nullable(),
  stillId: z.string().regex(/^still_[A-Za-z0-9][A-Za-z0-9._~-]*$/).nullable(),
  windowId: z.string().regex(/^color_window_[A-Za-z0-9][A-Za-z0-9._~-]*$/).nullable(),
  trackerId: z.string().regex(/^color_tracker_[A-Za-z0-9][A-Za-z0-9._~-]*$/).nullable(),
}).strict();
const evidence = z.object({
  kind: z.enum(["structural_readback", "rendered_frame", "visual_review", "artifact_readback", "manual_review"]),
  summary: publicText.min(1).max(500),
  artifactId: z.string().regex(/^artifact_[A-Za-z0-9][A-Za-z0-9._~-]*$/).nullable(),
}).strict();
const verification = z.object({
  outcome: z.enum(["passed", "partial", "failed", "not_performed", "manual_review_required"]),
  evidence: z.array(evidence).max(32),
  protectedState: z.enum(["preserved", "not_applicable", "not_proven", "partial"]),
}).strict();
const recovery = z.object({
  state: z.enum(["not_needed", "available", "manual_required", "unknown"]),
  retry: z.enum(["safe", "same_idempotency_key_required", "inspect_state_first", "manual_only"]),
  guidance: publicText.min(1).max(500),
}).strict();
const revisionRelationship = z.union([
  z.object({ relationship: z.literal("advanced"), before: revision, after: revision }).strict(),
  z.object({ relationship: z.literal("unchanged"), current: revision }).strict(),
  z.object({ relationship: z.literal("partial"), before: revision, observedAfter: nullableRevision }).strict(),
  z.object({ relationship: z.literal("unknown"), lastKnown: nullableRevision }).strict(),
]);
const readPayload = z.object({
  status: z.literal("completed"), targets: z.array(target).min(1).max(128), data: state, verification,
}).strict();
const mutationPayload = z.object({
  status: z.enum(["completed", "no_change", "partial", "manual_recovery_required"]),
  changed: z.boolean(), revision: revisionRelationship, targets: z.array(target).min(1).max(128),
  change: z.object({ kind: state.shape.kind, before: state.nullable(), after: state.nullable() }).strict(),
  verification, recovery,
}).strict();
const artifactPayload = z.object({
  status: z.enum(["completed", "no_change", "partial", "manual_recovery_required"]),
  changed: z.boolean(), targets: z.array(target).min(1).max(128), data: state,
  verification, recovery,
}).strict();

/** Runtime validator for the 134 normalized Color results not owned by exact contracts. @beta */
export const NormalizedColorActionResultSchema = z.object({
  actionId: z.string().refine((value) => colorActionIds.has(value), "Unknown normalized Color action ID"),
  payload: z.union([readPayload, mutationPayload, artifactPayload]),
}).strict().superRefine((result, context) => {
  const observation = observationActionIds.has(result.actionId);
  const artifactResult = artifactActionIds.has(result.actionId);
  const expectedKind = resultKindByActionId[result.actionId];
  if ("change" in result.payload) {
    if (observation || artifactResult) {
      context.addIssue({ code: "custom", path: ["payload"], message: "Color action returned a result from another lifecycle family" });
      return;
    }
    const payload = result.payload;
    const states = [payload.change.before, payload.change.after].filter((item) => item !== null);
    if (payload.change.kind !== expectedKind || states.some((item) => item.kind !== expectedKind || item.entities.some((entry) => !entityKindsByResultKind[item.kind]?.has(entry.kind)))) {
      context.addIssue({ code: "custom", path: ["payload"], message: "Color result contains state or entity truth incompatible with its action family" });
    }
    const before = "before" in payload.revision ? payload.revision.before : "current" in payload.revision ? payload.revision.current : payload.revision.lastKnown;
    if (payload.targets.some((item) => item.colorRevision !== null && item.colorRevision !== before)) context.addIssue({ code: "custom", path: ["payload", "targets"], message: "Color revision does not belong to the exact target" });
    if (payload.status === "completed" && (!payload.changed || payload.revision.relationship !== "advanced" || payload.revision.before === payload.revision.after || payload.change.before === null || payload.change.after === null || JSON.stringify(payload.change.before) === JSON.stringify(payload.change.after) || payload.verification.outcome !== "passed" || payload.verification.protectedState !== "preserved" || payload.verification.evidence.length === 0 || payload.recovery.state !== "not_needed")) context.addIssue({ code: "custom", path: ["payload"], message: "Completed Color mutation lacks exact advanced, verified truth" });
    if (payload.status === "completed" && payload.change.before !== null && payload.change.after !== null) {
      const beforeIds = new Set(payload.change.before.entities.map((item) => item.id));
      const afterIds = new Set(payload.change.after.entities.map((item) => item.id));
      const preserved = afterIds.size >= beforeIds.size ? [...beforeIds].every((id) => afterIds.has(id)) : [...afterIds].every((id) => beforeIds.has(id));
      if (beforeIds.size > 0 && !preserved) context.addIssue({ code: "custom", path: ["payload", "change"], message: "Completed Color mutation replaced exact entity identities" });
    }
    if (payload.status === "no_change" && (payload.changed || payload.revision.relationship !== "unchanged" || JSON.stringify(payload.change.before) !== JSON.stringify(payload.change.after) || payload.verification.outcome !== "passed" || payload.verification.protectedState !== "preserved" || payload.verification.evidence.length === 0 || payload.recovery.state !== "not_needed")) context.addIssue({ code: "custom", path: ["payload"], message: "No-change Color result is contradictory" });
    if (payload.status === "partial" && (payload.revision.relationship !== "partial" || payload.verification.outcome !== "partial" || payload.verification.evidence.length === 0 || !["available", "manual_required", "unknown"].includes(payload.recovery.state) || !["inspect_state_first", "manual_only"].includes(payload.recovery.retry))) context.addIssue({ code: "custom", path: ["payload"], message: "Partial Color result is contradictory" });
    if (payload.status === "manual_recovery_required" && (!["partial", "unknown"].includes(payload.revision.relationship) || !["failed", "manual_review_required"].includes(payload.verification.outcome) || payload.verification.evidence.length === 0 || payload.recovery.state !== "manual_required" || payload.recovery.retry !== "manual_only")) context.addIssue({ code: "custom", path: ["payload"], message: "Manual-recovery Color result is contradictory" });
    return;
  }
  if (!("data" in result.payload)) {
    context.addIssue({ code: "custom", path: ["payload"], message: "Color action returned a result from another lifecycle family" });
    return;
  }
  const payload = result.payload;
  if (payload.data.kind !== expectedKind || payload.data.entities.some((entry) => !entityKindsByResultKind[payload.data.kind]?.has(entry.kind))) {
    context.addIssue({ code: "custom", path: ["payload"], message: "Color result contains state or entity truth incompatible with its action family" });
  }
  if (!("changed" in payload)) {
    if (!observation || artifactResult) context.addIssue({ code: "custom", path: ["payload"], message: "Color action returned a result from another lifecycle family" });
    if (payload.verification.outcome !== "passed" || payload.verification.evidence.length === 0) context.addIssue({ code: "custom", path: ["payload", "verification"], message: "Completed Color observations require passed evidence" });
    return;
  }
  if (!artifactResult || observation) {
    context.addIssue({ code: "custom", path: ["payload"], message: "Color action returned a result from another lifecycle family" });
    return;
  }
  const nonempty = new Set(payload.data.artifacts.filter((item) => item.byteLength > 0).map((item) => item.artifactId));
  const proven = payload.verification.evidence.some((item) => item.kind === "artifact_readback" && item.artifactId !== null && nonempty.has(item.artifactId));
  if (["completed", "no_change"].includes(payload.status) && ((payload.status === "completed") !== payload.changed || !proven || payload.verification.outcome !== "passed" || payload.recovery.state !== "not_needed")) context.addIssue({ code: "custom", path: ["payload"], message: "Completed Color artifact result lacks matching nonempty artifact proof" });
  if (payload.status === "partial" && (payload.verification.outcome !== "partial" || payload.verification.evidence.length === 0 || !["available", "manual_required", "unknown"].includes(payload.recovery.state) || !["inspect_state_first", "manual_only"].includes(payload.recovery.retry))) context.addIssue({ code: "custom", path: ["payload"], message: "Partial Color artifact result is contradictory" });
  if (payload.status === "manual_recovery_required" && (!["failed", "manual_review_required"].includes(payload.verification.outcome) || payload.verification.evidence.length === 0 || payload.recovery.state !== "manual_required" || payload.recovery.retry !== "manual_only")) context.addIssue({ code: "custom", path: ["payload"], message: "Manual-recovery Color artifact result is contradictory" });
});

/** One normalized public result for a residual Color action. @beta */
export type NormalizedColorActionResult = z.infer<typeof NormalizedColorActionResultSchema>;

/** Parse one untrusted normalized Color action result. @beta */
export function parseNormalizedColorActionResult(value: unknown): NormalizedColorActionResult {
  return NormalizedColorActionResultSchema.parse(value);
}
