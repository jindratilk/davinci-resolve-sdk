import { z } from "zod";

/** Observed metadata is data-only and may not contain implementation details. @beta */
const FusionObservedValueSchema: z.ZodType<unknown> = z.lazy(() =>
  z.union([
    z.null(),
    z.boolean(),
    z.number().finite(),
    z.string().max(512),
    z.array(FusionObservedValueSchema).max(256),
    z.record(z.string().max(128), FusionObservedValueSchema),
  ]),
);

/** One introspected Fusion port. @beta */
export const FusionPortDefinitionSchema = z.strictObject({
  dataType: z.string().min(1).max(128).nullable(),
  direction: z.enum(["input", "output"]),
  id: z.string().regex(/^[A-Za-z][A-Za-z0-9_.:-]{0,127}$/),
  name: z.string().min(1).max(512),
  observed: z.record(z.string().max(128), FusionObservedValueSchema),
  required: z.boolean(),
});
/** One introspected Fusion port. @beta */
export interface FusionPortDefinition {
  /** Captured Fusion data type, when present. */
  readonly dataType: string | null;
  /** Port direction. */
  readonly direction: "input" | "output";
  /** Stable public port identifier. */
  readonly id: string;
  /** Human-readable captured port name. */
  readonly name: string;
  /** Public-safe observed metadata. */
  readonly observed: Readonly<Record<string, unknown>>;
  /** Whether the port must be supplied. */
  readonly required: boolean;
}

/** One introspected Fusion node descriptor. @beta */
export const FusionNodeDefinitionSchema = z.strictObject({
  category: z.string().min(1).max(512).nullable(),
  id: z.string().regex(/^[A-Za-z][A-Za-z0-9_.:-]{0,127}$/),
  inputs: z.array(FusionPortDefinitionSchema.extend({ direction: z.literal("input") })).max(1_024),
  name: z.string().min(1).max(512).nullable(),
  observedIn: z.array(z.string().regex(/^sha256:[0-9a-f]{64}$/)).min(1),
  outputs: z.array(FusionPortDefinitionSchema.extend({ direction: z.literal("output") })).max(1_024),
  rawKind: z.string().min(1).max(512).nullable(),
});
/** One introspected Fusion node descriptor. @beta */
export interface FusionNodeDefinition {
  /** Captured category, when present. */
  readonly category: string | null;
  /** Stable public node identifier. */
  readonly id: string;
  /** Captured input ports. */
  readonly inputs: readonly (FusionPortDefinition & { readonly direction: "input" })[];
  /** Human-readable captured node name. */
  readonly name: string | null;
  /** Digests of captures supporting this descriptor. */
  readonly observedIn: readonly string[];
  /** Captured output ports. */
  readonly outputs: readonly (FusionPortDefinition & { readonly direction: "output" })[];
  /** Native kind retained as public evidence, when present. */
  readonly rawKind: string | null;
}

const FusionEndpointSchema = z.strictObject({
  node: z.string().regex(/^[A-Za-z][A-Za-z0-9_.:-]{0,127}$/),
  port: z.string().regex(/^[A-Za-z][A-Za-z0-9_.:-]{0,127}$/),
});

/**
 * One connection proven by FusionScript connection readback.
 *
 * This is evidence for one exact pair, not a data-type compatibility matrix.
 * Native Fusion may accept pairs with different captured type labels and reject
 * pairs whose labels match, so callers must not infer additional connections.
 * @beta
 */
export const FusionConnectionDefinitionSchema = z.strictObject({
  observedIn: z.array(z.string().regex(/^sha256:[0-9a-f]{64}$/)).min(1),
  source: FusionEndpointSchema,
  target: FusionEndpointSchema,
});
/** One verified Fusion connection definition. @beta */
export interface FusionConnectionDefinition {
  /** Digests of captures proving this connection. */
  readonly observedIn: readonly string[];
  /** Source node and port. */
  readonly source: { readonly node: string; readonly port: string };
  /** Target node and port. */
  readonly target: { readonly node: string; readonly port: string };
}

const FusionRegistryEnvironmentSchema = z.strictObject({
  architecture: z.string().min(1).max(512),
  edition: z.enum(["free", "studio", "unverified"]),
  platform: z.enum(["macos", "windows", "fixture"]),
  productName: z.string().min(1).max(512),
  resolveVersion: z.array(z.union([z.number().int(), z.string().max(512)])).min(1).max(8),
  transport: z.enum(["embedded_free", "studio_external", "unverified"]),
  versionString: z.string().min(1).max(512),
});

/** Generated, public-safe Fusion registry contract. @beta */
export const FusionRegistrySchema = z.strictObject({
  allowlistRevision: z.string().min(1).max(128),
  captures: z.array(z.strictObject({
    captureDigest: z.string().regex(/^sha256:[0-9a-f]{64}$/),
    environment: FusionRegistryEnvironmentSchema,
    evidenceKind: z.enum(["contract_fixture", "live"]),
  })),
  connections: z.array(FusionConnectionDefinitionSchema),
  nodes: z.array(FusionNodeDefinitionSchema),
  registryDigest: z.string().regex(/^sha256:[0-9a-f]{64}$/),
  releaseStatus: z.enum(["fixture_only", "release_gated", "verified"]),
  schema: z.literal("cutagent.fusion.public-registry"),
  schemaVersion: z.literal(1),
});
/** Generated public-safe Fusion registry. @beta */
export interface FusionRegistry {
  /** Revision of the public allowlist used to produce the registry. */
  readonly allowlistRevision: string;
  /** Public-safe capture provenance. */
  readonly captures: readonly {
    readonly captureDigest: string;
    readonly environment: {
      readonly architecture: string;
      readonly edition: "free" | "studio" | "unverified";
      readonly platform: "macos" | "windows" | "fixture";
      readonly productName: string;
      readonly resolveVersion: readonly (number | string)[];
      readonly transport: "embedded_free" | "studio_external" | "unverified";
      readonly versionString: string;
    };
    readonly evidenceKind: "contract_fixture" | "live";
  }[];
  /** Exact connection pairs verified by readback; never inferred from type labels. */
  readonly connections: readonly FusionConnectionDefinition[];
  /** Captured node descriptors. */
  readonly nodes: readonly FusionNodeDefinition[];
  /** Digest binding this registry to authored graph requests. */
  readonly registryDigest: string;
  /** Registry activation state. */
  readonly releaseStatus: "fixture_only" | "release_gated" | "verified";
  /** Registry schema identifier. */
  readonly schema: "cutagent.fusion.public-registry";
  /** Registry schema version. */
  readonly schemaVersion: 1;
}

/** Structural registry type retained as a literal for compile-time graph checks. @beta */
export interface FusionRegistryDefinition {
  /** Canonical registry digest bound into every graph request. */
  readonly registryDigest: string;
  /** Registry activation state. */
  readonly releaseStatus: "fixture_only" | "release_gated" | "verified";
  /** Captured node descriptors. */
  readonly nodes: readonly {
    readonly id: string;
    readonly inputs: readonly {
      readonly dataType: string | null;
      readonly id: string;
      readonly observed: Readonly<Record<string, unknown>>;
      readonly required: boolean;
    }[];
    readonly outputs: readonly { readonly dataType: string | null; readonly id: string }[];
  }[];
  /** Exact connection pairs proven by readback; this is not a type-compatibility table. */
  readonly connections: readonly {
    readonly source: { readonly node: string; readonly port: string };
    readonly target: { readonly node: string; readonly port: string };
  }[];
}
