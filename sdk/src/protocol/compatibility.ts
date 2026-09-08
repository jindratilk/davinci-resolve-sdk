import { z } from "zod";
import {
  CUTAGENT_SDK_PROTOCOL_DIGEST,
  sdkCompatibilityDescriptorSchema,
  sdkCompatibilityHandshakeRequestSchema,
  sdkCompatibilityHandshakeResponseSchema,
  sdkRuntimeDistributionSchema,
} from "../generated/sdk-runtime.js";
import {
  assertPublishedCompatible,
  compatibilityManifestPolicy,
  compatibilityManifestPolicySchema,
  evaluatePublishedCompatibility,
} from "./compatibility-policy.js";

/** Digest of the exact reviewed SDK wire schema. @beta */
export const sdkProtocolDigest = CUTAGENT_SDK_PROTOCOL_DIGEST;

/** SDK runtime distribution vocabulary. This preview supports desktop-managed connections only. @beta */
export const RuntimeDistributionSchema = sdkRuntimeDistributionSchema;
/** SDK runtime distribution. @beta */
export type RuntimeDistribution = "standalone_local" | "plugin_managed";

/** Sanitized compatibility policy manifest. It is policy data, not a live handshake. @beta */
export const CompatibilityManifestSchema = compatibilityManifestPolicySchema;
/** Sanitized compatibility policy manifest. @beta */
export type CompatibilityManifest = z.infer<typeof CompatibilityManifestSchema>;

/** Reviewed compatibility policy shipped with this SDK version. @beta */
export const compatibilityManifest: CompatibilityManifest = compatibilityManifestPolicy;

/** Versioned compatibility request validated from the shared wire source of truth. @beta */
export const CompatibilityHandshakeRequestSchema = sdkCompatibilityHandshakeRequestSchema;
/** Versioned compatibility request. @beta */
export type CompatibilityHandshakeRequest = z.infer<typeof CompatibilityHandshakeRequestSchema>;

/** Live compatibility descriptor returned by the desktop-managed runtime. @beta */
export const CompatibilityDescriptorSchema = sdkCompatibilityDescriptorSchema;
/** Live compatibility descriptor returned by the desktop-managed runtime. @beta */
export interface CompatibilityDescriptor {
  readonly sdkApiVersion: string;
  readonly wireProtocol: number;
  readonly runtimeVersion: string;
  readonly distribution: RuntimeDistribution;
  readonly distributionVersion: string;
  readonly cliVersion: string;
  readonly protocolDigest: string;
  readonly runtimeFingerprint: string;
}

/** Versioned compatibility response validated from the shared wire source of truth. @beta */
export const CompatibilityHandshakeResponseSchema = sdkCompatibilityHandshakeResponseSchema;
/** Versioned compatibility response. @beta */
export type CompatibilityHandshakeResponse = z.infer<typeof CompatibilityHandshakeResponseSchema>;

/** Independently evaluated compatibility axis. @beta */
export const CompatibilityAxisSchema = z.enum(["sdk_api", "wire_protocol", "runtime", "distribution", "cli"]);
/** Independently evaluated compatibility axis. @beta */
export type CompatibilityAxis = z.infer<typeof CompatibilityAxisSchema>;

/** Failed compatibility-axis detail. @beta */
export const CompatibilityIssueSchema = z.strictObject({
  axis: CompatibilityAxisSchema,
  received: z.string().min(1),
  supported: z.string().min(1),
});
/** Failed compatibility-axis detail. @beta */
export type CompatibilityIssue = z.infer<typeof CompatibilityIssueSchema>;

/** Fail-closed compatibility negotiation result. @beta */
export const CompatibilityDecisionSchema = z.discriminatedUnion("compatible", [
  z.strictObject({ compatible: z.literal(true), wireProtocol: z.number().int().positive() }),
  z.strictObject({ compatible: z.literal(false), issues: z.array(CompatibilityIssueSchema).min(1) }),
]);
/** Fail-closed compatibility negotiation result. @beta */
export type CompatibilityDecision = z.infer<typeof CompatibilityDecisionSchema>;

/** Evaluate every compatibility axis independently and fail closed on malformed input. @beta */
export function negotiateCompatibility(input: unknown): CompatibilityDecision {
  return CompatibilityDecisionSchema.parse(evaluatePublishedCompatibility(input));
}

/** Assert compatibility and throw a typed public error when any axis is unsupported. @beta */
export function assertCompatible(input: unknown): CompatibilityDescriptor {
  return CompatibilityDescriptorSchema.parse(assertPublishedCompatible(input)) as CompatibilityDescriptor;
}
