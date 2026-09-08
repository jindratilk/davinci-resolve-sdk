import { z } from "zod";

/**
 * Schema for a release-gated raw Fusion request description.
 *
 * This public schema does not provide an execution or lowering capability and
 * is never used by the graph builder.
 * @beta
 */
export const AdvancedFusionRawRequestSchema = z.strictObject({
  kind: z.enum(["raw_setting", "fusion_script"]),
  payload: z.string().min(1).max(262_144),
  releaseGate: z.literal("maintainer_authorization_required"),
});
/** Release-gated raw Fusion request description; not an executable capability. @beta */
export interface AdvancedFusionRawRequest {
  /** Raw request kind accepted only by an authorized proprietary lowering boundary. */
  readonly kind: "raw_setting" | "fusion_script";
  /** Sanitized raw payload. */
  readonly payload: string;
  /** Explicit release-gate marker. */
  readonly releaseGate: "maintainer_authorization_required";
}

/** Validate an advanced raw request without lowering, dispatching, or mutating. @beta */
export function validateAdvancedFusionRawRequest(request: AdvancedFusionRawRequest): AdvancedFusionRawRequest {
  return AdvancedFusionRawRequestSchema.parse(request) as AdvancedFusionRawRequest;
}

/**
 * Validate an advanced raw request without lowering, dispatching, or mutating.
 * @deprecated Use `validateAdvancedFusionRawRequest`; this legacy name never executed a request.
 * @beta
 */
export function advancedFusionRaw(request: AdvancedFusionRawRequest): AdvancedFusionRawRequest {
  return validateAdvancedFusionRawRequest(request);
}
