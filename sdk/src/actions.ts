/**
 * Typed secondary action namespace generated from CutAgent CLI's public semantic contracts.
 *
 * @packageDocumentation
 */

import type { OperationHandle } from "./protocol/operations.js";
import type { IdempotencyKey } from "./value-types/identities.js";
import type { ConnectionControlOptions } from "./core/public-client-types.js";
import type {
  ActionInput,
  ActionResult,
  OptionalIdempotencyActionId,
  ReadActionId,
  RequiredIdempotencyActionId,
} from "./generated/actions.js";
import type { LowLevelReadActionId } from "./low-level-read-actions.js";

export {
  ACTION_IDS,
  ActionIds,
  CUTAGENT_ACTION_APPLICABILITY_DIGEST,
  CUTAGENT_ACTION_ERROR_REGISTRY_DIGEST,
  CUTAGENT_ACTION_INPUT_SCHEMA_DIGEST,
  CUTAGENT_ACTION_INVENTORY_DIGEST,
  CUTAGENT_ACTION_PROTOCOL_BINDING_DIGEST,
  CUTAGENT_ACTION_RESULT_SCHEMA_DIGEST,
  OPERATION_ACTION_IDS,
  OPTIONAL_IDEMPOTENCY_ACTION_IDS,
  READ_ACTION_IDS,
  REQUIRED_IDEMPOTENCY_ACTION_IDS,
} from "./generated/actions.js";
export type {
  ActionPositiveInteger,
  ActionId,
  ActionInput,
  ActionInputMap,
  ActionResult,
  ActionResultMap,
  OptionalIdempotencyActionId,
  OperationActionId,
  ReadActionId,
  RequiredIdempotencyActionId,
} from "./generated/actions.js";
export type { OperationHandle } from "./protocol/operations.js";
export type { IdempotencyKey } from "./value-types/identities.js";
export type { ConnectionControlOptions } from "./core/public-client-types.js";
export { LOW_LEVEL_READ_ACTION_IDS } from "./low-level-read-actions.js";
export type { LowLevelReadActionId } from "./low-level-read-actions.js";

/** Read action with an exact semantic public result projection. @beta */
export type SemanticReadActionId = Exclude<ReadActionId, LowLevelReadActionId>;

/** Local controls for a typed semantic action request. @beta */
export interface ActionControlOptions extends ConnectionControlOptions {
  /** Stable replay identity for operation actions that permit or require one. */
  idempotencyKey?: IdempotencyKey;
}

/** Operation controls for an action whose contract requires replay identity. @beta */
export interface RequiredActionControlOptions extends ConnectionControlOptions {
  /** Required stable replay identity. */
  idempotencyKey: IdempotencyKey;
}

/** Sanitized result returned by the explicit private CutAgent CLI read carrier. @beta */
export interface LowLevelReadResult<A extends LowLevelReadActionId = LowLevelReadActionId> {
  readonly actionId: A;
  readonly operationClass: "read";
  readonly data: unknown;
  readonly sanitized: true;
}

/**
 * Explicit durable escape hatch for reviewed read-only CLI capabilities that
 * do not yet have a semantic SDK result projection.
 *
 * The caller supplies a public action ID and its generated input type. Command
 * paths and lowering metadata remain private to the authenticated runtime.
 *
 * @beta
 */
export interface LowLevelActions {
  read<A extends LowLevelReadActionId>(
    actionId: A,
    input: ActionInput<A>,
    options?: ConnectionControlOptions,
  ): Promise<OperationHandle<LowLevelReadResult<A>, A>>;
}

/** Typed namespace for the reviewed, result-backed low-level semantic actions. @beta */
export interface Actions {
  /** Explicit durable carrier for activated, typed read-only long-tail actions. */
  readonly lowLevel: LowLevelActions;
  /**
   * Invoke any reviewed low-level semantic action through its declared lifecycle.
   *
   * This is the typed escape hatch for capabilities that do not yet have a
   * high-level domain object. Inputs and results remain action-specific and
   * the request still passes through capability, Mutation Policy, lifecycle,
   * and verification enforcement owned by the authenticated action carrier.
   * Reads return their validated result directly; mutations and long-running
   * actions return durable operation handles.
   */
  invoke<A extends SemanticReadActionId>(
    actionId: A,
    input: ActionInput<A>,
    options?: ConnectionControlOptions,
  ): Promise<ActionResult<A>>;

  invoke<A extends RequiredIdempotencyActionId>(
    actionId: A,
    input: ActionInput<A>,
    options: RequiredActionControlOptions,
  ): Promise<OperationHandle<ActionResult<A>, A>>;

  /** Start a reviewed action whose contract does not require replay identity. */
  invoke<A extends OptionalIdempotencyActionId>(
    actionId: A,
    input: ActionInput<A>,
    options?: ActionControlOptions,
  ): Promise<OperationHandle<ActionResult<A>, A>>;

  /** Execute a read-only semantic action and validate its direct result. */
  read<A extends SemanticReadActionId>(
    actionId: A,
    input: ActionInput<A>,
    options?: ConnectionControlOptions,
  ): Promise<ActionResult<A>>;

  /** Start an operation whose semantic contract requires an idempotency key. */
  start<A extends RequiredIdempotencyActionId>(
    actionId: A,
    input: ActionInput<A>,
    options: RequiredActionControlOptions,
  ): Promise<OperationHandle<ActionResult<A>, A>>;

  /** Start an operation whose semantic contract permits an optional idempotency key. */
  start<A extends OptionalIdempotencyActionId>(
    actionId: A,
    input: ActionInput<A>,
    options?: ActionControlOptions,
  ): Promise<OperationHandle<ActionResult<A>, A>>;
}
