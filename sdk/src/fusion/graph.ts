import { z } from "zod";
import { FUSION_REGISTRY, type GeneratedFusionRegistry } from "./generated/public-registry.js";
import { FusionRegistrySchema, type FusionRegistryDefinition } from "./registry.js";

/** Integer time in a Fusion composition's frame domain. @beta */
export const FusionFrameSchema = z.number().int().safe().brand<"FusionFrame">();
declare const fusionFrameBrand: unique symbol;
/** Integer time in a Fusion composition's frame domain. @beta */
export type FusionFrame = number & { readonly [fusionFrameBrand]: "FusionFrame" };

/** Construct a validated Fusion composition frame. @beta */
export function fusionFrame(value: number): FusionFrame {
  return FusionFrameSchema.parse(value) as unknown as FusionFrame;
}

/** Public values accepted by the graph IR. @beta */
export type FusionInputValue = number | string | boolean | [number, number] | [number, number, number] | [number, number, number, number];

/** Node identifier present in a registry literal. @beta */
export type FusionNodeType<R extends FusionRegistryDefinition> = R["nodes"][number]["id"];
/** Registry node selected by identifier. @beta */
export type FusionNodeByType<R extends FusionRegistryDefinition, T extends FusionNodeType<R>> = Extract<R["nodes"][number], { id: T }>;
/** Input port selected from a node type. @beta */
export type FusionInputPort<R extends FusionRegistryDefinition, T extends FusionNodeType<R>> = FusionNodeByType<R, T>["inputs"][number];
/** Output port selected from a node type. @beta */
export type FusionOutputPort<R extends FusionRegistryDefinition, T extends FusionNodeType<R>> = FusionNodeByType<R, T>["outputs"][number];
/** Input identifier for a node type. @beta */
export type FusionInputId<R extends FusionRegistryDefinition, T extends FusionNodeType<R>> = FusionInputPort<R, T>["id"];
/** Output identifier for a node type. @beta */
export type FusionOutputId<R extends FusionRegistryDefinition, T extends FusionNodeType<R>> = FusionOutputPort<R, T>["id"];
/** Port selected by identifier. @beta */
export type FusionPortById<P, I> = Extract<P, { id: I }>;
/** Literal value corresponding to a captured Fusion data type. @beta */
export type FusionValueForDataType<T> = T extends "Number" ? number
  : T extends "Text" | "String" ? string
    : T extends "Boolean" ? boolean
      : T extends "Point" | "Point2D" ? [number, number]
        : T extends "Point3D" ? [number, number, number]
          : T extends "Color" ? [number, number, number, number]
            : never;
/** Literal input value for a selected node input. @beta */
export type FusionInputValueFor<R extends FusionRegistryDefinition, T extends FusionNodeType<R>, I extends FusionInputId<R, T>> = FusionValueForDataType<FusionPortById<FusionInputPort<R, T>, I>["dataType"]>;
/** Inputs whose observed data type has a public literal representation. @beta */
export type FusionSettableInputId<R extends FusionRegistryDefinition, T extends FusionNodeType<R>> = {
  [I in FusionInputId<R, T>]: FusionInputValueFor<R, T, I> extends never ? never : I
}[FusionInputId<R, T>];
/** Inputs whose live registry evidence explicitly proves keyframe animation support. @beta */
export type FusionAnimatableInputId<R extends FusionRegistryDefinition, T extends FusionNodeType<R>> = {
  [I in FusionSettableInputId<R, T>]: FusionPortById<FusionInputPort<R, T>, I> extends {
    observed: { animatable: true };
  } ? I : never
}[FusionSettableInputId<R, T>];
/** Typed literal inputs accepted while adding a node. @beta */
export type FusionInitialInputs<R extends FusionRegistryDefinition, T extends FusionNodeType<R>> = Partial<{
  [I in FusionSettableInputId<R, T>]: FusionInputValueFor<R, T, I>
}>;
/** Instance name to registry node-type mapping accumulated by the builder. @beta */
export type FusionGraphNodeMap<R extends FusionRegistryDefinition> = Record<string, FusionNodeType<R>>;
/** Target port when the exact registry connection has verified evidence. @beta */
export type FusionCompatibleTargetPort<
  R extends FusionRegistryDefinition,
  S extends FusionNodeType<R>,
  SO extends FusionOutputId<R, S>,
  T extends FusionNodeType<R>,
  TI extends FusionInputId<R, T>,
> = Extract<R["connections"][number], { source: { node: S; port: SO }; target: { node: T; port: TI } }> extends never ? never : TI;

/** Relationship between captured source and target data-type labels. @beta */
export type FusionConnectionTypeLabelRelation = "same" | "different" | "unknown";

/** Catalog evidence for one endpoint used by a connection diagnostic. @beta */
export interface FusionConnectionEndpointDiagnostic {
  /** Captured data-type label, when the registry supplied one. */
  readonly dataType: string | null;
  /** Whether the exact node and port occur in the generated registry. */
  readonly registered: boolean;
}

/**
 * Diagnostic that keeps catalog presence, captured type labels, and exact
 * connection evidence separate. Only `verified_pair` is accepted by the typed
 * graph builder; matching type labels alone are never native compatibility proof.
 * @beta
 */
export interface FusionConnectionDiagnostic {
  /** Whether the typed graph builder accepts this exact registry pair. */
  readonly acceptedByGraphBuilder: boolean;
  /** Source endpoint catalog evidence. */
  readonly source: FusionConnectionEndpointDiagnostic;
  /** Exact evidence status for the requested pair. */
  readonly status: "verified_pair" | "unverified_pair" | "unknown_endpoint";
  /** Target endpoint catalog evidence. */
  readonly target: FusionConnectionEndpointDiagnostic;
  /** Relationship between labels only; this never asserts native compatibility. */
  readonly typeLabelRelation: FusionConnectionTypeLabelRelation;
}

const FusionValueSchema = z.union([
  z.number().finite(),
  z.string().max(65_536),
  z.boolean(),
  z.tuple([z.number().finite(), z.number().finite()]),
  z.tuple([z.number().finite(), z.number().finite(), z.number().finite()]),
  z.tuple([z.number().finite(), z.number().finite(), z.number().finite(), z.number().finite()]),
]);

const FusionKeyframeSchema = z.strictObject({ time: FusionFrameSchema, value: FusionValueSchema });

/** Sanitized animation track attached to an input. @beta */
export const FusionAnimationSchema = z.strictObject({
  kind: z.literal("keyframes"),
  keyframes: z.array(FusionKeyframeSchema).min(1).max(10_000),
});
/** Sanitized Fusion animation or modifier. @beta */
export type FusionAnimation = FusionAnimationFor<FusionInputValue>;
/** Input-specific animation accepted by the typed graph builder. @beta */
export type FusionAnimationFor<Value extends FusionInputValue> = {
  kind: "keyframes";
  keyframes: Array<{ time: FusionFrame; value: Value }>;
};

const FusionGraphNodeSchema = z.strictObject({
  id: z.string().regex(/^[A-Za-z][A-Za-z0-9_]{0,127}$/),
  inputs: z.record(z.string(), FusionValueSchema),
  type: z.string().regex(/^[A-Za-z][A-Za-z0-9_.:-]{0,127}$/),
});
const FusionGraphConnectionSchema = z.strictObject({
  source: z.strictObject({ node: z.string(), port: z.string() }),
  target: z.strictObject({ node: z.string(), port: z.string() }),
});
const FusionGraphAnimationSchema = z.strictObject({ node: z.string(), input: z.string(), animation: FusionAnimationSchema });

/** Pure graph IR accepted by the proprietary lowering boundary. @beta */
export const FusionGraphRequestSchema = z.strictObject({
  graph: z.strictObject({
    animations: z.array(FusionGraphAnimationSchema),
    connections: z.array(FusionGraphConnectionSchema),
    nodes: z.array(FusionGraphNodeSchema),
    outputs: z.array(z.string()).min(1),
  }),
  registryDigest: z.string().regex(/^sha256:[0-9a-f]{64}$/),
  schema: z.literal("cutagent.fusion.graph-request"),
  schemaVersion: z.literal(1),
});
/** Pure, sanitized Fusion graph request. @beta */
export interface FusionGraphRequest {
  /** Authored graph IR. */
  readonly graph: {
    readonly animations: readonly { readonly node: string; readonly input: string; readonly animation: FusionAnimation }[];
    readonly connections: readonly {
      readonly source: { readonly node: string; readonly port: string };
      readonly target: { readonly node: string; readonly port: string };
    }[];
    readonly nodes: readonly { readonly id: string; readonly inputs: Readonly<Record<string, FusionInputValue>>; readonly type: string }[];
    readonly outputs: readonly string[];
  };
  /** Digest of the registry used while authoring. */
  readonly registryDigest: string;
  /** Graph request schema identifier. */
  readonly schema: "cutagent.fusion.graph-request";
  /** Graph request schema version. */
  readonly schemaVersion: 1;
}

/** Runtime validation failure before any transport or mutation. @beta */
export class FusionGraphValidationError extends TypeError {
  override readonly name = "FusionGraphValidationError";
}

interface GraphNodeDraft { id: string; inputs: Record<string, FusionInputValue>; type: string }
interface GraphConnectionDraft { source: { node: string; port: string }; target: { node: string; port: string } }
interface GraphAnimationDraft { node: string; input: string; animation: FusionAnimation }

function fail(message: string): never {
  throw new FusionGraphValidationError(message);
}

function validateValue(port: FusionRegistryDefinition["nodes"][number]["inputs"][number], value: FusionInputValue): void {
  const expected = port.dataType;
  const valid = expected === "Number" ? typeof value === "number"
    : expected === "Text" || expected === "String" ? typeof value === "string"
      : expected === "Boolean" ? typeof value === "boolean"
        : expected === "Point" || expected === "Point2D" ? Array.isArray(value) && value.length === 2
          : expected === "Point3D" ? Array.isArray(value) && value.length === 3
            : expected === "Color" ? Array.isArray(value) && value.length === 4
              : false;
  if (!valid) fail(`Input ${port.id} does not accept a literal ${expected ?? "unknown"} value`);
  if (typeof value === "number") {
    const minimum = port.observed["minAllowed"];
    const maximum = port.observed["maxAllowed"];
    if (typeof minimum === "number" && value < minimum) fail(`Input ${port.id} is below its observed minimum`);
    if (typeof maximum === "number" && value > maximum) fail(`Input ${port.id} is above its observed maximum`);
    const enumRecord = Object.entries(port.observed).find(([key, item]) =>
      key.startsWith("INPST_ComboControl_ID") && item !== null && typeof item === "object" && !Array.isArray(item)
    )?.[1];
    if (enumRecord !== undefined && enumRecord !== null && typeof enumRecord === "object" && !Object.hasOwn(enumRecord, String(value))) {
      fail(`Input ${port.id} is not one of its observed enum values`);
    }
  }
}

function validateGraph(registry: FusionRegistryDefinition, graph: FusionGraphRequest["graph"]): void {
  const definitions = new Map(registry.nodes.map((node) => [node.id, node]));
  const nodes = new Map<string, GraphNodeDraft>();
  for (const node of graph.nodes) {
    if (nodes.has(node.id)) fail(`Duplicate node id: ${node.id}`);
    const definition = definitions.get(node.type);
    if (definition === undefined) fail(`Unknown node type: ${node.type}`);
    nodes.set(node.id, node);
    for (const [inputId, value] of Object.entries(node.inputs)) {
      const input = definition.inputs.find((candidate) => candidate.id === inputId);
      if (input === undefined) fail(`Unknown input ${node.type}.${inputId}`);
      validateValue(input, value);
    }
  }
  const outgoing = new Map<string, Set<string>>();
  const occupiedInputs = new Set<string>();
  for (const connection of graph.connections) {
    const source = nodes.get(connection.source.node) ?? fail(`Unknown source node: ${connection.source.node}`);
    const target = nodes.get(connection.target.node) ?? fail(`Unknown target node: ${connection.target.node}`);
    const verified = registry.connections.some((candidate) =>
      candidate.source.node === source.type && candidate.source.port === connection.source.port
      && candidate.target.node === target.type && candidate.target.port === connection.target.port
    );
    if (!verified) fail(`Connection is not verified: ${source.type}.${connection.source.port} -> ${target.type}.${connection.target.port}`);
    const targetKey = `${target.id}:${connection.target.port}`;
    if (occupiedInputs.has(targetKey)) fail(`Input already has a source: ${targetKey}`);
    occupiedInputs.add(targetKey);
    (outgoing.get(source.id) ?? outgoing.set(source.id, new Set()).get(source.id))?.add(target.id);
  }
  for (const node of nodes.values()) {
    const definition = definitions.get(node.type) ?? fail(`Unknown node type: ${node.type}`);
    for (const input of definition.inputs) {
      if (input.required && node.inputs[input.id] === undefined && !occupiedInputs.has(`${node.id}:${input.id}`)) {
        fail(`Required input is not supplied: ${node.id}.${input.id}`);
      }
    }
  }
  const animationKeys = new Set<string>();
  for (const row of graph.animations) {
    const node = nodes.get(row.node) ?? fail(`Unknown animation node: ${row.node}`);
    const definition = definitions.get(node.type) ?? fail(`Unknown node type: ${node.type}`);
    const input = definition.inputs.find((candidate) => candidate.id === row.input);
    if (input === undefined) fail(`Unknown animated input: ${node.type}.${row.input}`);
    if (input.observed["animatable"] !== true) fail(`Input is not observed as animatable: ${node.type}.${row.input}`);
    const key = `${row.node}:${row.input}`;
    if (animationKeys.has(key)) fail(`Input has multiple animations: ${key}`);
    animationKeys.add(key);
    let previous: number | undefined;
    for (const keyframe of row.animation.keyframes) {
      validateValue(input, keyframe.value);
      if (previous !== undefined && keyframe.time <= previous) fail(`Keyframes must have unique ascending times: ${key}`);
      previous = keyframe.time;
    }
  }
  const outputs = new Set(graph.outputs);
  for (const output of outputs) {
    const node = nodes.get(output) ?? fail(`Unknown output node: ${output}`);
    if (node.type !== "MediaOut") fail(`Graph output must be a MediaOut node: ${output}`);
  }
  const reachesOutput = (start: string, visiting: Set<string>): boolean => {
    if (outputs.has(start)) return true;
    if (visiting.has(start)) fail(`Graph contains a cycle at ${start}`);
    const next = outgoing.get(start);
    if (next === undefined || next.size === 0) return false;
    const active = new Set(visiting).add(start);
    return [...next].some((node) => reachesOutput(node, active));
  };
  const visited = new Set<string>();
  const detectCycle = (start: string, active: Set<string>): void => {
    if (active.has(start)) fail(`Graph contains a cycle at ${start}`);
    if (visited.has(start)) return;
    const nextActive = new Set(active).add(start);
    for (const next of outgoing.get(start) ?? []) detectCycle(next, nextActive);
    visited.add(start);
  };
  for (const node of nodes.keys()) detectCycle(node, new Set());
  for (const node of nodes.keys()) {
    if (!reachesOutput(node, new Set())) fail(`Node has no path to an output: ${node}`);
  }
}

/** Immutable, type-checkable Fusion graph builder. @beta */
export class FusionGraphBuilder<
  R extends FusionRegistryDefinition,
  N extends FusionGraphNodeMap<R> = Record<never, never>,
  HasOutput extends boolean = false,
> {
  declare private readonly outputState: HasOutput;

  private constructor(
    private readonly registry: R,
    private readonly nodes: readonly GraphNodeDraft[] = [],
    private readonly connections: readonly GraphConnectionDraft[] = [],
    private readonly animations: readonly GraphAnimationDraft[] = [],
    private readonly outputs: readonly string[] = [],
  ) {}

  /** @internal */
  static create<R extends FusionRegistryDefinition>(registry: R): FusionGraphBuilder<R> {
    return new FusionGraphBuilder(registry);
  }

  /** Add a uniquely named node with typed literal inputs. @beta */
  node<Name extends string, T extends FusionNodeType<R>>(
    name: Name extends keyof N ? never : Name,
    type: T,
    inputs: FusionInitialInputs<R, T> = {},
  ): FusionGraphBuilder<R, N & Record<Name, T>, HasOutput> {
    const materializedInputs: Record<string, FusionInputValue> = {};
    for (const [input, value] of Object.entries(inputs)) {
      if (value !== undefined) materializedInputs[input] = FusionValueSchema.parse(value);
    }
    return new FusionGraphBuilder<R, N & Record<Name, T>, HasOutput>(
      this.registry,
      [...this.nodes, { id: name, inputs: materializedInputs, type }],
      this.connections,
      this.animations,
      this.outputs,
    );
  }

  /** Set one typed literal input. @beta */
  set<Name extends keyof N & string, I extends FusionSettableInputId<R, N[Name]>>(
    node: Name,
    input: I,
    value: FusionInputValueFor<R, N[Name], I>,
  ): FusionGraphBuilder<R, N, HasOutput> {
    const next = this.nodes.map((candidate) => {
      if (candidate.id !== node) return candidate;
      const inputs: Record<string, FusionInputValue> = { ...candidate.inputs };
      inputs[String(input)] = FusionValueSchema.parse(value);
      return { ...candidate, inputs };
    });
    return new FusionGraphBuilder(this.registry, next, this.connections, this.animations, this.outputs);
  }

  /** Attach an exact set of keyframe values to a typed input. Interpolation is not asserted. @beta */
  animate<Name extends keyof N & string, I extends FusionAnimatableInputId<R, N[Name]>>(
    node: Name,
    input: I,
    animation: FusionAnimationFor<FusionInputValueFor<R, N[Name], I>>,
  ): FusionGraphBuilder<R, N, HasOutput> {
    return new FusionGraphBuilder(this.registry, this.nodes, this.connections, [...this.animations, { node, input, animation }], this.outputs);
  }

  /** Connect only a registry-verified output/input pair. @beta */
  connect<
    SName extends keyof N & string,
    SPort extends FusionOutputId<R, N[SName]>,
    TName extends keyof N & string,
    TPort extends FusionInputId<R, N[TName]>,
  >(
    sourceNode: SName,
    sourcePort: SPort,
    targetNode: TName,
    targetPort: FusionCompatibleTargetPort<R, N[SName], SPort, N[TName], TPort>,
  ): FusionGraphBuilder<R, N, HasOutput> {
    const connection = { source: { node: sourceNode, port: sourcePort }, target: { node: targetNode, port: targetPort } };
    return new FusionGraphBuilder(this.registry, this.nodes, [...this.connections, connection], this.animations, this.outputs);
  }

  /** Declare a MediaOut node as a required graph output. @beta */
  output<Name extends keyof N & string>(name: N[Name] extends "MediaOut" ? Name : never): FusionGraphBuilder<R, N, true> {
    return new FusionGraphBuilder<R, N, true>(this.registry, this.nodes, this.connections, this.animations, [...this.outputs, name]);
  }

  /** Validate and compile one sanitized request; this does not dispatch or mutate. @beta */
  compile(this: FusionGraphBuilder<R, N, true>): FusionGraphRequest {
    const graph = {
      animations: [...this.animations],
      connections: [...this.connections],
      nodes: [...this.nodes],
      outputs: [...new Set(this.outputs)].sort(),
    };
    validateGraph(this.registry, graph);
    return FusionGraphRequestSchema.parse({
      graph,
      registryDigest: this.registry.registryDigest,
      schema: "cutagent.fusion.graph-request",
      schemaVersion: 1,
    }) as unknown as FusionGraphRequest;
  }
}

/** Registry activation options; fixture access exists only for tests and maintainers. @beta */
export interface FusionRegistryGateOptions {
  /** Allow the explicit contract fixture; this never permits a release-gated live registry. */
  readonly allowFixtureRegistry?: boolean;
}

function assertRegistryUsable(options: FusionRegistryGateOptions): void {
  const releaseStatus = FUSION_REGISTRY.releaseStatus as FusionRegistryDefinition["releaseStatus"];
  if (releaseStatus === "verified") return;
  if (releaseStatus === "fixture_only" && options.allowFixtureRegistry === true) return;
  fail(`The generated Fusion registry is ${releaseStatus}; reviewed activation evidence is required`);
}

function findConnectionEndpoint(
  registry: FusionRegistryDefinition,
  direction: "input" | "output",
  nodeId: string,
  portId: string,
): FusionConnectionEndpointDiagnostic {
  const node = registry.nodes.find((candidate) => candidate.id === nodeId);
  const ports = direction === "input" ? node?.inputs : node?.outputs;
  const port = ports?.find((candidate) => candidate.id === portId);
  return Object.freeze({ dataType: port?.dataType ?? null, registered: port !== undefined });
}

/**
 * Inspect catalog, type-label, and exact readback evidence for a possible
 * connection without compiling, dispatching, or mutating a graph.
 *
 * A result with `typeLabelRelation: "same"` remains unverified unless `status`
 * is `verified_pair`. Conversely, a verified native exception may have
 * `typeLabelRelation: "different"`.
 * @beta
 */
export function diagnoseFusionConnection(
  source: { readonly node: string; readonly port: string },
  target: { readonly node: string; readonly port: string },
  options: FusionRegistryGateOptions = {},
): FusionConnectionDiagnostic {
  FusionRegistrySchema.parse(FUSION_REGISTRY);
  assertRegistryUsable(options);
  const sourceEvidence = findConnectionEndpoint(FUSION_REGISTRY, "output", source.node, source.port);
  const targetEvidence = findConnectionEndpoint(FUSION_REGISTRY, "input", target.node, target.port);
  const endpointsRegistered = sourceEvidence.registered && targetEvidence.registered;
  const verified = endpointsRegistered && FUSION_REGISTRY.connections.some((candidate) =>
    candidate.source.node === source.node && candidate.source.port === source.port
    && candidate.target.node === target.node && candidate.target.port === target.port
  );
  const typeLabelRelation: FusionConnectionTypeLabelRelation = sourceEvidence.dataType === null || targetEvidence.dataType === null
    ? "unknown"
    : sourceEvidence.dataType === targetEvidence.dataType ? "same" : "different";
  return Object.freeze({
    acceptedByGraphBuilder: verified,
    source: sourceEvidence,
    status: verified ? "verified_pair" : endpointsRegistered ? "unverified_pair" : "unknown_endpoint",
    target: targetEvidence,
    typeLabelRelation,
  });
}

/** Create a graph builder over the generated reviewed registry. @beta */
export function fusionGraph(options: FusionRegistryGateOptions = {}): FusionGraphBuilder<GeneratedFusionRegistry> {
  FusionRegistrySchema.parse(FUSION_REGISTRY);
  assertRegistryUsable(options);
  return FusionGraphBuilder.create(FUSION_REGISTRY);
}

/** Proprietary runtimes implement this seam after mutation policy and authorization. @beta */
export interface FusionGraphLoweringTarget<T> {
  /** Exact versioned lowering protocol. */
  readonly protocol: "cutagent.fusion.graph-request/1";
  /** Lower a validated request without changing its public meaning. */
  lower(request: FusionGraphRequest): T;
}

/** Validate registry binding and graph semantics, then invoke an injected lowering target. @beta */
export function lowerFusionGraph<T>(
  request: FusionGraphRequest,
  target: FusionGraphLoweringTarget<T>,
  options: FusionRegistryGateOptions = {},
): T {
  if (target.protocol !== "cutagent.fusion.graph-request/1") fail("Fusion graph lowering protocol is incompatible");
  FusionRegistrySchema.parse(FUSION_REGISTRY);
  assertRegistryUsable(options);
  const parsed = FusionGraphRequestSchema.parse(request) as unknown as FusionGraphRequest;
  if (parsed.registryDigest !== FUSION_REGISTRY.registryDigest) fail("Fusion graph registry digest does not match the generated registry");
  validateGraph(FUSION_REGISTRY, parsed.graph);
  return target.lower(parsed);
}

function canonicalValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalValue);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0).map(([key, item]) => [key, canonicalValue(item)]));
  }
  return value;
}

/** Serialize a graph request deterministically without paths or implementation metadata. @beta */
export function serializeFusionGraphRequest(request: FusionGraphRequest): string {
  return JSON.stringify(canonicalValue(FusionGraphRequestSchema.parse(request)));
}
