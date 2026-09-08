import { z } from "zod";
import { TimestampSchema } from "../schemas/time.js";
import { CompatibilityDescriptorSchema, negotiateCompatibility, type CompatibilityDescriptor } from "./compatibility.js";
import { RecoverySchema, type Recovery } from "./errors.js";

/** Sanitized public capability identifier. @beta */
export const CapabilityIdSchema = z.string().regex(/^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)+$/).brand<"CapabilityId">();
/** Sanitized public capability identifier. @beta */
export type CapabilityId = string & { readonly __capabilityId?: never };

/** Public capability availability. @beta */
export const CapabilityAvailabilitySchema = z.enum(["supported", "degraded", "unavailable"]);
/** Public capability availability. @beta */
export type CapabilityAvailability = "supported" | "degraded" | "unavailable";

/** Public platform value for the active live environment. @beta */
export const PlatformSchema = z.enum(["macos", "windows"]);
/** Public platform value for the active live environment. @beta */
export type Platform = "macos" | "windows";

/** Public DaVinci Resolve edition value for the active live environment. @beta */
export const DaVinciResolveEditionSchema = z.enum(["free", "studio"]);
/** Public DaVinci Resolve edition value for the active live environment. @beta */
export type DaVinciResolveEdition = "free" | "studio";

/** Stable reason explaining degraded or unavailable live capability state. @beta */
export const CapabilityReasonCodeSchema = z.enum([
  "EDITION_UNAVAILABLE",
  "PLATFORM_UNAVAILABLE",
  "VERSION_UNSUPPORTED",
  "RUNTIME_INCOMPATIBLE",
  "DEPENDENCY_UNAVAILABLE",
  "AUTHORIZATION_REQUIRED",
  "TEMPORARILY_UNAVAILABLE",
  "DEGRADED_MODE",
  "UNKNOWN",
]);
/** Stable reason explaining degraded or unavailable live capability state. @beta */
export type CapabilityReasonCode =
  | "EDITION_UNAVAILABLE"
  | "PLATFORM_UNAVAILABLE"
  | "VERSION_UNSUPPORTED"
  | "RUNTIME_INCOMPATIBLE"
  | "DEPENDENCY_UNAVAILABLE"
  | "AUTHORIZATION_REQUIRED"
  | "TEMPORARILY_UNAVAILABLE"
  | "DEGRADED_MODE"
  | "UNKNOWN";

const supportedCapability = z.strictObject({
  id: CapabilityIdSchema,
  availability: z.literal("supported"),
});
const nonSupportedCapabilityFields = {
  id: CapabilityIdSchema,
  reasonCode: CapabilityReasonCodeSchema,
  recoveryActions: z.array(RecoverySchema).min(1).max(5),
  recoveryGuidance: z.string().min(1).max(500),
};
const degradedCapability = z.strictObject({
  ...nonSupportedCapabilityFields,
  availability: z.literal("degraded"),
});
const unavailableCapability = z.strictObject({
  ...nonSupportedCapabilityFields,
  availability: z.literal("unavailable"),
});

/** Sanitized capability state for one active environment; it makes no matrix-wide support claim. @beta */
export const PublicCapabilitySchema = z.discriminatedUnion("availability", [
  supportedCapability,
  degradedCapability,
  unavailableCapability,
]);
/** Sanitized capability state for one active environment. @beta */
export type PublicCapability =
  | Readonly<{ id: CapabilityId; availability: "supported" }>
  | Readonly<{
    id: CapabilityId;
    availability: "degraded" | "unavailable";
    reasonCode: CapabilityReasonCode;
    recoveryActions: Recovery[];
    recoveryGuidance: string;
  }>;

/** Identity of the one live environment represented by a capability snapshot. @beta */
export const CapabilityEnvironmentSchema = z.strictObject({
  platform: PlatformSchema,
  edition: DaVinciResolveEditionSchema,
  davinciResolveVersion: z.string().regex(/^\d+\.\d+(?:\.\d+)?$/),
  compatibility: CompatibilityDescriptorSchema,
}).superRefine((environment, context) => {
  const decision = negotiateCompatibility(environment.compatibility);
  if (!decision.compatible) {
    context.addIssue({
      code: "custom",
      path: ["compatibility"],
      message: `Live capability environment is incompatible on: ${decision.issues.map((issue) => issue.axis).join(", ")}`,
    });
  }
});
/** Identity of the one live environment represented by a capability snapshot. @beta */
export interface CapabilityEnvironment {
  readonly platform: Platform;
  readonly edition: DaVinciResolveEdition;
  readonly davinciResolveVersion: string;
  readonly compatibility: CompatibilityDescriptor;
}

/** Sanitized capability snapshot for exactly one compatible live environment. @beta */
export const PublicCapabilitiesSchema = z.strictObject({
  capturedAt: TimestampSchema,
  environment: CapabilityEnvironmentSchema,
  capabilities: z.array(PublicCapabilitySchema).max(2000),
}).superRefine((snapshot, context) => {
  const ids = snapshot.capabilities.map((capability) => capability.id);
  if (new Set(ids).size !== ids.length) {
    context.addIssue({ code: "custom", path: ["capabilities"], message: "Capability IDs must be unique within a live snapshot" });
  }
});
/** Sanitized capability snapshot for exactly one compatible live environment. @beta */
export interface PublicCapabilities {
  readonly environment: CapabilityEnvironment;
  readonly capturedAt: string;
  readonly capabilities: readonly PublicCapability[];
}
