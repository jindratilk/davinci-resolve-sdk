import { z } from "zod";
import rawCompatibilityManifest from "../../compatibility.json" with { type: "json" };
import {
  sdkCompatibilityDescriptorSchema,
  sdkRuntimeDistributionSchema,
} from "../generated/sdk-runtime.js";
import { evaluateCutAgentSdkRuntimeCompatibility } from "../generated/sdk-runtime-policy.js";
import { CutAgentSdkError } from "./errors.js";

export const compatibilityManifestPolicySchema = z.strictObject({
  $schema: z.literal("./compatibility.schema.json"),
  manifestVersion: z.literal(1),
  packageName: z.literal("cutagent"),
  sdkVersion: z.literal("0.2.0"),
  sdkApiVersion: z.literal("0.2"),
  wireProtocol: z.literal(1),
  moduleFormat: z.literal("esm"),
  browserSupported: z.literal(false),
  nodeRange: z.literal(">=22.12.0 <23 || >=24.0.0 <25"),
  typescriptRange: z.literal(">=5.7.0 <5.10.0"),
  runtimeRange: z.literal(">=3.0.0 <3.1.0"),
  desktopManagedRange: z.literal(">=3.0.0 <3.1.0"),
  pluginManagedRange: z.null(),
  cliRange: z.literal(">=3.0.0 <3.1.0"),
});

export const compatibilityManifestPolicy = compatibilityManifestPolicySchema.parse(rawCompatibilityManifest);

type RuntimeDistribution = z.infer<typeof sdkRuntimeDistributionSchema>;
type CompatibilityDescriptor = z.infer<typeof sdkCompatibilityDescriptorSchema>;
type CompatibilityAxis = "sdk_api" | "wire_protocol" | "runtime" | "distribution" | "cli";
interface CompatibilityIssue {
  readonly axis: CompatibilityAxis;
  readonly received: string;
  readonly supported: string;
}
type CompatibilityDecision =
  | Readonly<{ compatible: true; wireProtocol: number }>
  | Readonly<{ compatible: false; issues: readonly CompatibilityIssue[] }>;
type DistributionRangePolicy = Readonly<Record<RuntimeDistribution, string | null>>;

const publishedDistributionRanges: DistributionRangePolicy = Object.freeze({
  standalone_local: compatibilityManifestPolicy.desktopManagedRange,
  plugin_managed: compatibilityManifestPolicy.pluginManagedRange,
});

function evaluateCompatibility(
  input: unknown,
  distributionRanges: DistributionRangePolicy,
  expectedDistribution?: RuntimeDistribution,
): CompatibilityDecision {
  const descriptorResult = sdkCompatibilityDescriptorSchema.safeParse(input);
  if (!descriptorResult.success) {
    return { compatible: false, issues: [{ axis: "wire_protocol", received: "invalid_descriptor", supported: "valid compatibility descriptor" }] };
  }
  const descriptor = descriptorResult.data;
  const issues: CompatibilityIssue[] = [];
  if (descriptor.sdkApiVersion !== compatibilityManifestPolicy.sdkApiVersion) {
    issues.push({ axis: "sdk_api", received: descriptor.sdkApiVersion, supported: compatibilityManifestPolicy.sdkApiVersion });
  }
  if (descriptor.wireProtocol !== compatibilityManifestPolicy.wireProtocol) {
    issues.push({ axis: "wire_protocol", received: String(descriptor.wireProtocol), supported: String(compatibilityManifestPolicy.wireProtocol) });
  }
  const runtimeDecision = evaluateCutAgentSdkRuntimeCompatibility(descriptor, {
    runtimeRange: compatibilityManifestPolicy.runtimeRange,
    desktopManagedRange: distributionRanges.standalone_local,
    pluginManagedRange: distributionRanges.plugin_managed,
    cliRange: compatibilityManifestPolicy.cliRange,
    ...(expectedDistribution === undefined ? {} : { expectedDistribution }),
  });
  if (!runtimeDecision.compatible) {
    issues.push(...runtimeDecision.issues);
  }
  return issues.length === 0
    ? { compatible: true, wireProtocol: descriptor.wireProtocol }
    : { compatible: false, issues };
}

function assertCompatibility(
  input: unknown,
  distributionRanges: DistributionRangePolicy,
  expectedDistribution?: RuntimeDistribution,
): CompatibilityDescriptor {
  const decision = evaluateCompatibility(input, distributionRanges, expectedDistribution);
  if (!decision.compatible) {
    throw new CutAgentSdkError({
      kind: "runtime_incompatible",
      code: "SDK_INCOMPATIBLE",
      message: `Incompatible CutAgent contract: ${decision.issues.map((issue) => issue.axis).join(", ")}`,
      retrySafe: false,
      possibleMutation: "none",
      usage: "not_reserved",
      recovery: ["update_required"],
      recoveryGuidance: ["Install a reviewed compatible SDK and CutAgent distribution."],
      readbackRequired: false,
    });
  }
  return sdkCompatibilityDescriptorSchema.parse(input);
}

export function evaluatePublishedCompatibility(input: unknown): CompatibilityDecision {
  return evaluateCompatibility(input, publishedDistributionRanges);
}

export function assertPublishedCompatible(input: unknown): CompatibilityDescriptor {
  return assertCompatibility(input, publishedDistributionRanges);
}

export function assertCarrierPolicyCompatible(
  input: unknown,
  expectedDistribution: RuntimeDistribution,
  distributionRange: string | null,
): CompatibilityDescriptor {
  return assertCompatibility(
    input,
    {
      standalone_local: expectedDistribution === "standalone_local" ? distributionRange : null,
      plugin_managed: expectedDistribution === "plugin_managed" ? distributionRange : null,
    },
    expectedDistribution,
  );
}
