import type { ActionControlOptions, Actions, LowLevelReadActionId, LowLevelReadResult, SemanticReadActionId } from "../actions.js";
import {
  ACTION_RUNTIME_CONTRACTS,
  ACTION_SCHEMA_DEFINITIONS,
  type ActionId,
  type ActionInput,
  type ActionResult,
  type OperationActionId,
  type ReadActionId,
} from "../generated/actions.js";
import type { OperationHandle } from "../protocol/operations.js";
import { sdkIdempotencyKeySchema } from "../generated/sdk-identities.js";
import { LOW_LEVEL_READ_ACTION_IDS } from "../low-level-read-actions.js";
import type { ConnectionControlOptions } from "./public-client-types.js";
import { parseClosedActionSchema } from "./action-schema.js";
import { authoringTimeInternals } from "../value-types/time.js";
import {
  lowerDuration,
  lowerSourcePosition,
  lowerSourceRange,
  lowerTimelineRecordPosition,
  lowerTimelineRecordRange,
} from "../wire/time-adapter.js";

export interface ActionRuntime {
  read(actionId: ReadActionId, input: object, options: ConnectionControlOptions): Promise<unknown>;
  start(
    actionId: OperationActionId,
    input: object,
    resultSchema: { parse(value: unknown): unknown },
    options: ActionControlOptions,
  ): Promise<OperationHandle<unknown>>;
  startLowLevelRead(
    actionId: LowLevelReadActionId,
    input: object,
    resultSchema: { parse(value: unknown): unknown },
    options: ConnectionControlOptions,
  ): Promise<OperationHandle<unknown>>;
}

const lowLevelReadActionIds = new Set<string>(LOW_LEVEL_READ_ACTION_IDS);

function rejectIncompatibleDirectRead(actionId: ActionId): void {
  if (lowLevelReadActionIds.has(actionId)) {
    throw new TypeError(`${actionId} is owned by the sanitized low-level read carrier; use actions.lowLevel.read().`);
  }
}

function lowLevelReadResultParser<A extends LowLevelReadActionId>(actionId: A): { parse(value: unknown): LowLevelReadResult<A> } {
  return Object.freeze({
    parse(value: unknown): LowLevelReadResult<A> {
      if (value === null || typeof value !== "object" || Array.isArray(value)) {
        throw new TypeError(`${actionId}.lowLevelResult must be an object.`);
      }
      const result = value as Record<string, unknown>;
      if (Object.keys(result).some((key) => !["actionId", "operationClass", "data", "sanitized"].includes(key))
        || result.actionId !== actionId || result.operationClass !== "read" || result.sanitized !== true
        || !("data" in result)) {
        throw new TypeError(`${actionId}.lowLevelResult violated the sanitized read carrier contract.`);
      }
      return result as unknown as LowLevelReadResult<A>;
    },
  });
}

function contract<A extends ActionId>(actionId: A) {
  const value = ACTION_RUNTIME_CONTRACTS[actionId];
  if (!value) throw new TypeError(`Unknown CutAgent action ID: ${String(actionId)}`);
  return value;
}

function lowerInputValue(value: unknown): unknown {
  if (authoringTimeInternals.isDuration(value)) return lowerDuration(value);
  if (authoringTimeInternals.isTimelineRecordPosition(value)) {
    const lowered = lowerTimelineRecordPosition(value);
    return {
      domain: lowered.domain,
      value: lowered.value.kind === "timecode"
        ? { kind: lowered.value.kind, value: lowered.value.value }
        : lowered.value,
    };
  }
  if (authoringTimeInternals.isSourcePosition(value)) {
    const lowered = lowerSourcePosition(value);
    return {
      domain: lowered.domain,
      value: lowered.value.kind === "timecode"
        ? { kind: lowered.value.kind, value: lowered.value.value }
        : lowered.value,
    };
  }
  if (authoringTimeInternals.isTimelineRecordRange(value)) return lowerTimelineRecordRange(value);
  if (authoringTimeInternals.isSourceRange(value)) return lowerSourceRange(value);
  if (Array.isArray(value)) return value.map(lowerInputValue);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, entry]) => [key, lowerInputValue(entry)]));
  }
  return value;
}

function parseInput<A extends ActionId>(actionId: A, input: ActionInput<A>): object {
  return parseClosedActionSchema<object>(
    contract(actionId).input,
    ACTION_SCHEMA_DEFINITIONS,
    lowerInputValue(input),
    `${actionId}.input`,
  );
}

const semanticPayloadActionIds = new Set<ActionId>([
  "cutagent.action.timeline.subtitle.list",
  "cutagent.action.timeline.subtitle.export",
]);

function adaptSemanticResult(actionId: ActionId, value: unknown): unknown {
  if (!semanticPayloadActionIds.has(actionId) || value === null || typeof value !== "object" || Array.isArray(value) || "actionId" in value) return value;
  return { actionId, payload: value };
}

function resultParser<A extends ActionId>(actionId: A): { parse(value: unknown): ActionResult<A> } {
  return Object.freeze({
    parse(value: unknown): ActionResult<A> {
      return parseClosedActionSchema<ActionResult<A>>(
        contract(actionId).result,
        ACTION_SCHEMA_DEFINITIONS,
        adaptSemanticResult(actionId, value),
        `${actionId}.result`,
      );
    },
  });
}

function validateIdempotencyKey(
  actionId: ActionId,
  idempotencyCategory: string,
  options: ActionControlOptions,
): void {
  if (idempotencyCategory === "requires_idempotency_key" && options.idempotencyKey === undefined) {
    throw new TypeError(`${actionId} requires an idempotencyKey.`);
  }
  if (options.idempotencyKey !== undefined) sdkIdempotencyKeySchema.parse(options.idempotencyKey);
}

export function createActions(runtime: ActionRuntime): Actions {
  const lowLevel = Object.freeze(Object.assign(Object.create(null), {
    async read<A extends LowLevelReadActionId>(
      actionId: A,
      input: ActionInput<A>,
      options: ConnectionControlOptions = {},
    ): Promise<OperationHandle<LowLevelReadResult<A>, A>> {
      if (!lowLevelReadActionIds.has(actionId)) throw new TypeError(`${actionId} has no activated low-level read carrier.`);
      const actionContract = contract(actionId);
      if (actionContract.operationClass !== "read") throw new TypeError(`${actionId} is not a read action.`);
      const validatedInput = parseInput(actionId, input);
      return runtime.startLowLevelRead(actionId, validatedInput, lowLevelReadResultParser(actionId), options) as Promise<OperationHandle<LowLevelReadResult<A>, A>>;
    },
  }));
  function invoke<A extends SemanticReadActionId>(
    actionId: A,
    input: ActionInput<A>,
    options?: ConnectionControlOptions,
  ): Promise<ActionResult<A>>;
  function invoke<A extends OperationActionId>(
    actionId: A,
    input: ActionInput<A>,
    options?: ActionControlOptions,
  ): Promise<OperationHandle<ActionResult<A>, A>>;
  async function invoke(
    actionId: ActionId,
    input: ActionInput<ActionId>,
    options: ActionControlOptions = {},
  ): Promise<ActionResult<ActionId> | OperationHandle<ActionResult<ActionId>, OperationActionId>> {
    const actionContract = contract(actionId);
    rejectIncompatibleDirectRead(actionId);
    const validatedInput = parseInput(actionId, input);
    if (actionContract.operationClass === "read") {
      return resultParser(actionId).parse(await runtime.read(actionId as ReadActionId, validatedInput, options));
    }
    validateIdempotencyKey(actionId, actionContract.idempotencyCategory, options);
    return runtime.start(
      actionId as OperationActionId,
      validatedInput,
      resultParser(actionId),
      options,
    ) as Promise<OperationHandle<ActionResult<ActionId>, OperationActionId>>;
  }

  async function read<A extends SemanticReadActionId>(
    actionId: A,
    input: ActionInput<A>,
    options: ConnectionControlOptions = {},
  ): Promise<ActionResult<A>> {
    const actionContract = contract(actionId);
    if (actionContract.operationClass !== "read") throw new TypeError(`${actionId} is not a read action.`);
    rejectIncompatibleDirectRead(actionId);
    const validatedInput = parseInput(actionId, input);
    return resultParser(actionId).parse(await runtime.read(actionId, validatedInput, options));
  }

  async function start(
    actionId: OperationActionId,
    input: ActionInput<OperationActionId>,
    options: ActionControlOptions = {},
  ): Promise<OperationHandle<ActionResult<OperationActionId>>> {
    const actionContract = contract(actionId);
    if (actionContract.operationClass === "read") throw new TypeError(`${actionId} is not an operation action.`);
    validateIdempotencyKey(actionId, actionContract.idempotencyCategory, options);
    const validatedInput = parseInput(actionId, input);
    return runtime.start(actionId, validatedInput, resultParser(actionId), options) as Promise<OperationHandle<ActionResult<OperationActionId>>>;
  }

  const actions: Actions = { invoke, read, start, lowLevel };
  Object.setPrototypeOf(actions, null);
  return Object.freeze(actions);
}
