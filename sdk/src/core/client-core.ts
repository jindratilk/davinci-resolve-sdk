import { createProjects, type ReadControlOptions } from "../domain/object-model.js";
import { CompatibilityDescriptorSchema } from "../protocol/compatibility.js";
import { CutAgentSdkError, PUBLIC_ERROR_KIND_BY_CODE } from "../protocol/errors.js";
import { ConnectionIdSchema, idempotencyKey, SdkSessionIdSchema } from "../value-types/identities.js";
import type { EstablishedCarrierSession } from "./carrier-session.js";
import { timeoutValue } from "./carrier-contract.js";
import type {
  ConnectionControlOptions,
  ConnectionSnapshot,
  CutAgentClient,
} from "./public-client-types.js";
import { createOperations, startTypedOperation } from "./operations.js";
import { createVoice } from "../domain/voice.js";
import { createWorkflows } from "./workflows.js";
import { sdkOperationEventSchema } from "../generated/sdk-operations.js";
import type { OperationHandle, PublicActionId } from "../protocol/operations.js";
import { FUSION_GRAPH_APPLY_ACTION_ID } from "../fusion/runtime.js";
import { createActions } from "./actions.js";
import { createArtifacts } from "../domain/artifacts.js";

function snapshot(connection: EstablishedCarrierSession): ConnectionSnapshot {
  return Object.freeze({
    connectionId: ConnectionIdSchema.parse(connection.session.connectionId),
    sessionId: SdkSessionIdSchema.parse(connection.session.sessionId),
    descriptor: Object.freeze(CompatibilityDescriptorSchema.parse(connection.descriptor)),
    issuedAt: connection.session.issuedAt,
    expiresAt: connection.session.expiresAt,
    idleExpiresAt: connection.session.idleExpiresAt,
  });
}

function closedFailure(): CutAgentSdkError {
  return new CutAgentSdkError({
    kind: PUBLIC_ERROR_KIND_BY_CODE.CONNECTION_CLOSED,
    code: "CONNECTION_CLOSED",
    message: "This CutAgent SDK client has no usable runtime session.",
    retrySafe: true,
    retrySafetyProof: { basis: "read_only" },
    possibleMutation: "none",
    usage: "not_reserved",
    recovery: ["reconnect"],
    recoveryGuidance: ["Reconnect the client before inspecting live DaVinci Resolve state."],
    readbackRequired: false,
  });
}

function staleFailure(message: string): CutAgentSdkError {
  return new CutAgentSdkError({
    kind: PUBLIC_ERROR_KIND_BY_CODE.STALE_REVISION,
    code: "STALE_REVISION",
    message,
    retrySafe: true,
    retrySafetyProof: { basis: "read_only" },
    possibleMutation: "none",
    usage: "not_reserved",
    recovery: ["inspect_state"],
    recoveryGuidance: ["Resolve the current project and timeline again from the reconnected client."],
    readbackRequired: false,
  });
}

function fusionCarrierUnavailable(): CutAgentSdkError {
  return new CutAgentSdkError({
    kind: PUBLIC_ERROR_KIND_BY_CODE.RUNTIME_UNAVAILABLE,
    code: "RUNTIME_UNAVAILABLE",
    message: "Typed Fusion graph operations are not activated for plugin-managed connections.",
    retrySafe: true,
    retrySafetyProof: { basis: "pre_execution" },
    possibleMutation: "none",
    usage: "not_reserved",
    recovery: ["reconnect"],
    recoveryGuidance: ["Use an activated desktop-managed CutAgent runtime for typed Fusion graph operations."],
    readbackRequired: false,
  });
}

export interface ClientCoreOptions extends ConnectionControlOptions {
  readonly retainedTimeoutMs?: number;
}

/** Create the one client lifecycle used by every carrier. */
export async function createCarrierClient(
  establish: (options: ConnectionControlOptions) => Promise<EstablishedCarrierSession>,
  options: ClientCoreOptions = {},
): Promise<CutAgentClient> {
  let transport = await establish(options);
  let connection = snapshot(transport);
  let closed = false;
  let closePromise: Promise<void> | null = null;
  let reconnectPromise: Promise<ConnectionSnapshot> | null = null;
  let generation = 0;
  let terminalSubscription: (() => void) | null = null;
  let lifecycleRevision = 0;

  const observe = (observed: EstablishedCarrierSession) => {
    const observationRevision = lifecycleRevision;
    terminalSubscription?.();
    terminalSubscription = observed.onTerminal(() => {
      if (transport !== observed || lifecycleRevision !== observationRevision || closed) return;
      closed = true;
      generation += 1;
    });
  };
  observe(transport);

  const closeCurrent = (control: ConnectionControlOptions): Promise<void> => {
    if (closePromise) return closePromise;
    try {
      timeoutValue(control.timeoutMs);
    } catch (error) {
      return Promise.reject(error);
    }
    if (closed) {
      closePromise = transport.close(control);
      return closePromise;
    }
    closed = true;
    generation += 1;
    lifecycleRevision += 1;
    terminalSubscription?.();
    terminalSubscription = null;
    closePromise = transport.close(control);
    return closePromise;
  };

  const retireCurrent = (control: ConnectionControlOptions): Promise<void> => {
    try {
      timeoutValue(control.timeoutMs);
    } catch (error) {
      return Promise.reject(error);
    }
    if (closed) return closePromise ?? Promise.resolve();
    closed = true;
    generation += 1;
    lifecycleRevision += 1;
    terminalSubscription?.();
    terminalSubscription = null;
    closePromise = transport.retire(control);
    return closePromise;
  };

  const workflows = createWorkflows({ session: () => transport });
  const objectModelRuntime = {
    get generation(): number { return generation; },
    session: () => transport,
    workflows,
    async managedStartAtGeneration(expectedGeneration: number, binding: unknown, cancellationRequested: boolean, control: ReadControlOptions = {}) {
      if (closed || expectedGeneration !== generation) throw staleFailure("This object reference belongs to an earlier CutAgent SDK session.");
      const snapshot = await transport.workflow({ operation: "workflow.managed.start", binding, cancellationRequested } as never, control);
      if (closed || expectedGeneration !== generation) throw staleFailure("The CutAgent SDK session changed during managed application.");
      return { workflowId: snapshot.workflowId, status: snapshot.status } as never;
    },
    async managedWaitAtGeneration(expectedGeneration: number, workflowId: unknown, control: ReadControlOptions = {}) {
      if (closed || expectedGeneration !== generation) throw staleFailure("This object reference belongs to an earlier CutAgent SDK session.");
      const snapshot = await transport.workflow({ operation: "workflow.managed.wait", workflowId } as never, control);
      if (closed || expectedGeneration !== generation) throw staleFailure("The CutAgent SDK session changed during managed application.");
      return Object.freeze({ workflowId: snapshot.workflowId, outcome: snapshot.status, steps: Object.freeze(snapshot.steps.flatMap((entry) => entry.outcome ? [{ name: entry.name, outcome: entry.outcome, ...(entry.operationId ? { operationId: entry.operationId } : {}), ...(entry.actionId ? { actionId: entry.actionId } : {}) }] : [])), journal: snapshot, ...(snapshot.managedState ? { managedState: snapshot.managedState } : {}), manualRecoveryRequired: snapshot.manualRecoveryRequired, cancellationDoesNotRollback: true }) as never;
    },
    async managedInterruptAtGeneration(expectedGeneration: number, workflowId: unknown) {
      if (closed || expectedGeneration !== generation) throw staleFailure("This object reference belongs to an earlier CutAgent SDK session.");
      await transport.workflow({ operation: "workflow.interrupt", workflowId } as never, {});
      if (closed || expectedGeneration !== generation) throw staleFailure("The CutAgent SDK session changed during managed cancellation.");
    },
    sessionAtGeneration(expectedGeneration: number) {
      if (closed || expectedGeneration !== generation) throw staleFailure("This object reference belongs to an earlier CutAgent SDK session.");
      return transport;
    },
    async createOperationAtGeneration(
      expectedGeneration: number,
      request: Parameters<EstablishedCarrierSession["operation"]>[0],
      control: Parameters<EstablishedCarrierSession["operation"]>[1] = {},
    ) {
      if (closed || expectedGeneration !== generation) throw staleFailure("This object reference belongs to an earlier CutAgent SDK session.");
      const activeTransport = transport;
      const event = sdkOperationEventSchema.parse(await activeTransport.operation(request, control));
      if (closed || expectedGeneration !== generation || activeTransport !== transport) {
        throw staleFailure("The CutAgent SDK session changed while starting the marker operation.");
      }
      return event;
    },
    async readAtGeneration(
      expectedGeneration: number,
      request: Parameters<EstablishedCarrierSession["read"]>[0],
      control: ReadControlOptions = {},
    ) {
      if (closed) throw closedFailure();
      if (expectedGeneration !== generation) {
        throw staleFailure("This object reference belongs to an earlier CutAgent SDK session.");
      }
      if (request.operation === "fusion.compositions" && connection.descriptor.distribution === "plugin_managed") {
        throw fusionCarrierUnavailable();
      }
      const activeTransport = transport;
      try {
        const result = await activeTransport.read(request, control);
        if (closed || expectedGeneration !== generation || activeTransport !== transport) {
          throw staleFailure("The CutAgent SDK session changed during the live-state read.");
        }
        return result;
      } catch (error) {
        if (activeTransport !== transport
          || (expectedGeneration !== generation && !activeTransport.closed)) {
          throw staleFailure("The CutAgent SDK session changed during the live-state read.");
        }
        throw error;
      }
    },
    async startAction<TResult, TAction extends PublicActionId>(
      expectedGeneration: number,
      actionId: TAction,
      input: unknown,
      resultSchema: { parse(value: unknown): TResult },
      control: ConnectionControlOptions & { idempotencyKey?: string } = {},
    ): Promise<OperationHandle<TResult, TAction>> {
      if (closed) throw closedFailure();
      if (expectedGeneration !== generation) {
        throw staleFailure("This object reference belongs to an earlier CutAgent SDK session.");
      }
      if (actionId === FUSION_GRAPH_APPLY_ACTION_ID && connection.descriptor.distribution === "plugin_managed") {
        throw fusionCarrierUnavailable();
      }
      return startTypedOperation({ session: () => transport }, actionId, input, resultSchema, control);
    },
    async readAction<TResult, TAction extends PublicActionId>(
      expectedGeneration: number,
      actionId: TAction,
      input: unknown,
      resultSchema: { parse(value: unknown): TResult },
      control: ConnectionControlOptions = {},
    ): Promise<TResult> {
      // Prepared reads use the same durable authority as mutations. Give each
      // read an internal replay identity without burdening callers with a key;
      // mutation keys remain explicitly caller-owned.
      const handle = await this.startAction(expectedGeneration, actionId, input, resultSchema, {
        ...control,
        idempotencyKey: idempotencyKey(),
      });
      const terminal = await handle.wait(control);
      if (terminal.status !== "succeeded") throw new CutAgentSdkError(terminal.failure);
      return terminal.result;
    },
  };
  const projects = createProjects(objectModelRuntime);
  const operations = createOperations({ session: () => transport });
  const actions = createActions({
    read(actionId, input, options) {
      return objectModelRuntime.readAction(generation, actionId, input, {
        parse(value: unknown) { return value; },
      }, options);
    },
    start(actionId, input, resultSchema, control) {
      return objectModelRuntime.startAction(generation, actionId, input, resultSchema, control);
    },
    startLowLevelRead(actionId, input, resultSchema, control) {
      return objectModelRuntime.startAction(generation, actionId, input, resultSchema, {
        ...control,
        idempotencyKey: idempotencyKey(),
      });
    },
  });
  const artifacts = createArtifacts(objectModelRuntime);

  const client: CutAgentClient = {
    get connection(): ConnectionSnapshot { return connection; },
    get closed(): boolean { return closed; },
    projects,
    operations,
    actions,
    artifacts,
    get voice() { return createVoice(objectModelRuntime, generation); },
    workflows,
    close(control = {}) {
      if (reconnectPromise) return reconnectPromise.then(() => closeCurrent(control));
      return closeCurrent(control);
    },
    reconnect(control = {}) {
      if (reconnectPromise) return reconnectPromise;
      reconnectPromise = (async () => {
        if (!closed) {
          const retirement = retireCurrent(control);
          try {
            await retirement;
          } catch (error) {
            // A rejected close reply is historical once the carrier proves
            // termination. Without that proof, activating a replacement could
            // leave two live sessions and must fail closed.
            if (!transport.terminated) throw error;
          }
        } else if (!transport.terminated) {
          // An asynchronous carrier terminal event can close the public client
          // before transport cleanup settles. Re-enter the shared retirement
          // path and require its termination proof before replacing the carrier.
          const retirement = transport.retire(control);
          closePromise ??= retirement;
          try {
            await retirement;
          } catch (error) {
            if (!transport.terminated) throw error;
          }
        }
        const replacement = await establish({
          ...(options.retainedTimeoutMs !== undefined ? { timeoutMs: options.retainedTimeoutMs } : {}),
          ...control,
        });
        lifecycleRevision += 1;
        transport = replacement;
        connection = snapshot(replacement);
        closed = false;
        closePromise = null;
        observe(replacement);
        return connection;
      })().finally(() => {
        reconnectPromise = null;
      });
      return reconnectPromise;
    },
  };
  Object.setPrototypeOf(client, null);
  return Object.freeze(client);
}
