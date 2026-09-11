import type { z } from "zod";
import {
  CUTAGENT_SDK_ACTION_CONTRACT_VERSION as GENERATED_ACTION_CONTRACT_VERSION,
  CUTAGENT_SDK_ACTION_INVENTORY_DIGEST as GENERATED_ACTION_INVENTORY_DIGEST,
  CUTAGENT_SDK_PUBLIC_ACTION_IDS as GENERATED_PUBLIC_ACTION_IDS,
  sdkOperationEventSchema,
  sdkOperationResultCollectionReferenceSchema,
  sdkOperationResultPageSchema,
  sdkOperationProgressSchema,
  sdkOperationRecoverySchema,
  sdkOperationSnapshotSchema,
  sdkOperationStatusSchema,
  sdkMediaActionResultValueSchema,
  sdkPublicActionIdSchema,
  sdkPublicActionResultSchema,
} from "../generated/sdk-operations.js";
import type { ConnectionControlOptions } from "../core/public-client-types.js";
import type { ExecutionId, IdempotencyKey, OperationId, RequestId } from "../value-types/identities.js";
import type { PossibleMutationState, PublicFailure, UsageState } from "./errors.js";
import type { VerificationEvidence, VerificationReport } from "./verification.js";
import type { ActionId, ActionResult } from "../generated/actions.js";

/** Current version of every operation action discriminator in this preview. @beta */
export const CUTAGENT_SDK_ACTION_CONTRACT_VERSION = GENERATED_ACTION_CONTRACT_VERSION;
/** Digest of the accepted operation action inventory. @beta */
export const CUTAGENT_SDK_ACTION_INVENTORY_DIGEST = GENERATED_ACTION_INVENTORY_DIGEST;
/** Accepted public-safe action discriminators. @beta */
export const PUBLIC_ACTION_IDS = GENERATED_PUBLIC_ACTION_IDS;
/** Accepted public-safe action discriminator. @beta */
export type PublicActionId = (typeof PUBLIC_ACTION_IDS)[number];
/** Version discriminator carried by every public action and operation. @beta */
export type PublicActionContractVersion = 1;
/** JSON value accepted for public action results without a generated action contract. @beta */
export type JsonValue = null | boolean | number | string | JsonValue[] | { readonly [key: string]: JsonValue };
/** Accepted public-safe action discriminator. @beta */
export const PublicActionIdSchema = sdkPublicActionIdSchema as unknown as z.ZodType<PublicActionId>;
/** Durable operation status. @beta */
export type OperationStatus =
  | "queued" | "running" | "waiting" | "cancellation_requested"
  | "succeeded" | "failed" | "cancelled" | "partially_applied"
  | "verification_failed" | "recovery_failed";
/** Durable operation status with truthful terminal states. @beta */
export const OperationStatusSchema: z.ZodType<OperationStatus> = sdkOperationStatusSchema;
/** Sanitized long-running operation progress. @beta */
export interface OperationProgress {
  phase: string;
  overallFraction?: number;
  phaseFraction?: number;
  completedUnits?: number;
  totalUnits?: number;
  message?: string;
}
/** Sanitized monotonic long-running operation progress. @beta */
export const OperationProgressSchema = sdkOperationProgressSchema as unknown as z.ZodType<OperationProgress>;
/** Typed operation recovery state. @beta */
export type OperationRecovery =
  | { state: "not_attempted"; summary: string; manualRecoveryRequired: boolean }
  | { state: "restored"; summary: string; evidence: VerificationEvidence[]; manualRecoveryRequired: false }
  | { state: "compensated"; summary: string; evidence: VerificationEvidence[] }
  | { state: "failed"; summary: string; evidence: VerificationEvidence[]; manualRecoveryRequired: true }
  | { state: "manual_required"; summary: string; evidence: VerificationEvidence[]; manualRecoveryRequired: true };
/** Typed recovery state attached only to applicable terminal branches. @beta */
export const OperationRecoverySchema = sdkOperationRecoverySchema as unknown as z.ZodType<OperationRecovery>;
/** Pinned Media inventory with typed supported or explicit unsupported terminals. @beta */
export type MediaActionId = Exclude<
  Extract<PublicActionId, `cutagent.action.media.${string}`>,
  "cutagent.action.media.append.batch" | "cutagent.action.media.third_party_metadata.bulk_set"
>;
/** Media-prefixed batch aliases intentionally outside the public semantic result surface. @beta */
export type MediaExcludedActionId =
  | "cutagent.action.media.append.batch"
  | "cutagent.action.media.third_party_metadata.bulk_set";
/** Twelve Media actions with reviewed typed read results. @beta */
export type MediaReadActionId =
  | "cutagent.action.media.audio_mapping"
  | "cutagent.action.media.folders.list"
  | "cutagent.action.media.folders.tree"
  | "cutagent.action.media.info"
  | "cutagent.action.media.list"
  | "cutagent.action.media.mark.get"
  | "cutagent.action.media.marker.list"
  | "cutagent.action.media.matte.list"
  | "cutagent.action.media.search"
  | "cutagent.action.media.selected.list"
  | "cutagent.action.media.third_party_metadata.get"
  | "cutagent.action.media.timeline_matte.list";
/** Ten Media actions whose typed mutation results require independent readback. @beta */
export type MediaMutationActionId =
  | "cutagent.action.media.import"
  | "cutagent.action.media.create_timeline"
  | "cutagent.action.media.folders.create"
  | "cutagent.action.media.folders.delete"
  | "cutagent.action.media.folders.open"
  | "cutagent.action.media.folders.root"
  | "cutagent.action.media.metadata"
  | "cutagent.action.media.property_set"
  | "cutagent.action.media.proxy"
  | "cutagent.action.media.third_party_metadata.set";
/** Thirty-one Media actions that fail closed with an explicit unsupported result. @beta */
export type MediaUnsupportedActionId = Exclude<MediaActionId, MediaReadActionId | MediaMutationActionId>;
/** Public-safe Media result applicability. @beta */
export interface MediaResultApplicability {
  overall: "unknown";
  operatingSystem: { macos: "unknown"; windows: "unknown" };
  architecture: { arm64: "unknown"; x86_64: "unknown" };
  edition: { free: "unknown" | "declared_unverified"; studio: "unknown" | "declared_unverified" };
  transport: { embeddedFree: "unknown" | "declared_unverified"; studioExternal: "unknown" | "declared_unverified" };
}
/** Opaque or scoped public Media identity. @beta */
export interface MediaResultEntity {
  kind: "media_asset" | "media_folder" | "timeline" | "marker" | "matte" | "artifact";
  id: string | null;
  addressability: "addressable" | "not_addressable";
  name: string | null;
  folderName: string | null;
}
/** Sanitized scalar Media property. @beta */
export interface MediaResultProperty { key: string; value: string | number | boolean | null }
/** Verification embedded in one reviewed Media result. @beta */
export interface MediaResultVerification {
  outcome: "passed" | "partial" | "manual_review_required";
  evidence: Array<{ kind: "command_read" | "structural_readback" | "manual_review"; summary: string }>;
  protectedState: "preserved" | "not_applicable" | "not_proven" | "partial";
}
/** Exact read data keyed by its public Media action. @beta */
export interface MediaReadResultDataByAction {
  "cutagent.action.media.audio_mapping": { outcome: "audio_mapping"; item: MediaResultEntity; mapping: MediaResultProperty[] };
  "cutagent.action.media.folders.list": { outcome: "folders.list"; scope: MediaResultEntity; folders: MediaResultEntity[] };
  "cutagent.action.media.folders.tree": { outcome: "folders.tree"; root: MediaResultEntity; folders: MediaResultEntity[] };
  "cutagent.action.media.info": { outcome: "info"; item: MediaResultEntity; properties: MediaResultProperty[] };
  "cutagent.action.media.list": { outcome: "list"; scope: MediaResultEntity; items: MediaResultEntity[] };
  "cutagent.action.media.mark.get": { outcome: "mark.get"; item: MediaResultEntity; marks: Array<{ kind: string; inFrame: number | null; outFrame: number | null }> };
  "cutagent.action.media.marker.list": { outcome: "marker.list"; item: MediaResultEntity; markers: Array<{ frame: number; color: string | null; name: string | null; note: string | null; durationFrames: number | null }> };
  "cutagent.action.media.matte.list": { outcome: "matte.list"; item: MediaResultEntity; matteCount: number };
  "cutagent.action.media.search": { outcome: "search"; scope: MediaResultEntity; items: MediaResultEntity[] };
  "cutagent.action.media.selected.list": { outcome: "selected.list"; scope: MediaResultEntity; items: MediaResultEntity[] };
  "cutagent.action.media.third_party_metadata.get": { outcome: "third_party_metadata.get"; item: MediaResultEntity; metadata: MediaResultProperty[] };
  "cutagent.action.media.timeline_matte.list": { outcome: "timeline_matte.list"; folder: MediaResultEntity; matteCount: number };
}
/** Typed data returned by the twelve reviewed Media reads. @beta */
export type MediaReadResultData = MediaReadResultDataByAction[MediaReadActionId];
/** Exact mutation data keyed by its public Media action. @beta */
export interface MediaMutationResultDataByAction {
  "cutagent.action.media.import": { outcome: "import"; importedItems: MediaResultEntity[] };
  "cutagent.action.media.create_timeline": { outcome: "create_timeline"; targetIds: string[] };
  "cutagent.action.media.folders.create": { outcome: "folders.create"; folder: MediaResultEntity };
  "cutagent.action.media.folders.delete": { outcome: "folders.delete"; folder: MediaResultEntity };
  "cutagent.action.media.folders.open": { outcome: "folders.open"; targetIds: string[] };
  "cutagent.action.media.folders.root": { outcome: "folders.root"; targetIds: string[] };
  "cutagent.action.media.metadata": { outcome: "metadata"; item: MediaResultEntity; metadata: MediaResultProperty[] };
  "cutagent.action.media.property_set": { outcome: "property_set"; item: MediaResultEntity; metadata: MediaResultProperty[] };
  "cutagent.action.media.proxy": { outcome: "proxy"; targetIds: string[] };
  "cutagent.action.media.third_party_metadata.set": { outcome: "third_party_metadata.set"; item: MediaResultEntity; metadata: MediaResultProperty[] };
}
/** Typed data returned by the ten readback-backed Media mutations. @beta */
export type MediaMutationResultData = MediaMutationResultDataByAction[MediaMutationActionId];
/** Typed semantic value available from raw Media operation reattachment. @beta */
export type MediaActionResultValue =
  | { [A in MediaReadActionId]: { actionId: A; applicability: MediaResultApplicability; payload: { status: "completed"; data: MediaReadResultDataByAction[A]; verification: MediaResultVerification } } }[MediaReadActionId]
  | { [A in MediaMutationActionId]: { actionId: A; applicability: MediaResultApplicability; payload: { status: "completed" | "no_op" | "partial" | "manual_review_required"; changed: boolean; data: MediaMutationResultDataByAction[A]; verification: MediaResultVerification } } }[MediaMutationActionId]
  | { [A in MediaUnsupportedActionId]: { actionId: A; applicability: MediaResultApplicability; payload: { status: "unsupported"; reason: "action_not_available"; message: "This action is not available through the public SDK." } } }[MediaUnsupportedActionId];
/** Runtime schema for the pinned Media supported/unsupported result union. @beta */
export const MediaActionResultValueSchema = sdkMediaActionResultValueSchema as unknown as z.ZodType<MediaActionResultValue>;
/** Runtime-validated public action result envelope. @beta */
export type PublicActionResult =
  | { [A in MediaActionId]: { actionId: A; actionContractVersion: PublicActionContractVersion; value: Extract<MediaActionResultValue, { actionId: A }> } }[MediaActionId]
  | { [A in Exclude<PublicActionId, MediaActionId | MediaExcludedActionId>]: {
    actionId: A;
    actionContractVersion: PublicActionContractVersion;
    value: A extends ActionId ? ActionResult<A> : JsonValue;
  } }[Exclude<PublicActionId, MediaActionId | MediaExcludedActionId>];
/** Runtime-validated public action result envelope used by raw-ID reattachment. @beta */
export const PublicActionResultSchema = sdkPublicActionResultSchema as unknown as z.ZodType<PublicActionResult>;

/** Runtime-validated discriminated operation snapshot. @beta */
export const OperationSnapshotSchema = sdkOperationSnapshotSchema as unknown as z.ZodType<OperationSnapshot<PublicActionResult>>;
/** Runtime-validated operation event. @beta */
export const OperationEventSchema = sdkOperationEventSchema as unknown as z.ZodType<OperationEvent>;

/** Digest-bound locator for one complete retained operation-result collection. @beta */
export interface OperationResultCollectionReference {
  collectionId: string;
  kind: "identity_map" | "array";
  totalItems: number;
  digest: string;
  defaultPageSize: number;
}
/** Runtime validator for retained operation-result collection locators. @beta */
export const OperationResultCollectionReferenceSchema = sdkOperationResultCollectionReferenceSchema as unknown as z.ZodType<OperationResultCollectionReference>;
/** One authority-owned page from a retained operation result. @beta */
export type OperationResultPage = {
  operationId: OperationId;
  actionId: PublicActionId;
  actionContractVersion: PublicActionContractVersion;
  collectionId: string;
  digest: string;
  totalItems: number;
  offset: number;
  nextOffset: number | null;
  retentionExpiresAt: string;
} & (
  | { kind: "identity_map"; entries: Array<{ key: string; value: unknown }> }
  | { kind: "array"; entries: Array<{ index: number; value: unknown }> }
);
/** Runtime validator for retained operation-result pages. @beta */
export const OperationResultPageSchema = sdkOperationResultPageSchema as unknown as z.ZodType<OperationResultPage>;

/** Options for retrieving one retained result page. @beta */
export interface OperationResultPageOptions extends ConnectionControlOptions {
  offset?: number;
  pageSize?: number;
}

/** Identity, sequencing, and custody fields shared by every operation state. @beta */
export interface OperationSnapshotBase<TAction extends PublicActionId = PublicActionId> {
  operationId: OperationId;
  requestId: RequestId;
  executionId: ExecutionId;
  actionId: TAction;
  actionContractVersion: PublicActionContractVersion;
  sequence: number;
  createdAt: string;
  updatedAt: string;
  possibleMutation: PossibleMutationState;
  usage: UsageState;
  idempotency?: { key: IdempotencyKey; tombstoneExpiresAt: string };
}

/** Retention metadata shared by every terminal operation state. @beta */
export interface TerminalOperationSnapshotBase<TAction extends PublicActionId = PublicActionId> extends OperationSnapshotBase<TAction> {
  retentionExpiresAt: string;
}

/** Authority rejection of a cancellation request after it was evaluated. @beta */
export interface OperationCancellationRejected {
  state: "rejected";
  requestedAt: string;
  resolvedAt: string;
  reason: string;
}

/** Terminal public failure with exact operation correlation. @beta */
export type TerminalOperationFailure = PublicFailure & Required<
  Pick<PublicFailure, "requestId" | "operationId" | "executionId">
>;

/** One monotonic event published by the durable operation authority. @beta */
export interface OperationEvent {
  operationId: OperationId;
  sequence: number;
  snapshot: OperationSnapshot<PublicActionResult, PublicActionId>;
}

/**
 * One discriminated operation snapshot. Typed semantic results are required on
 * success and may also preserve partial, manual-review, or unsupported truth on
 * the matching non-success terminal.
 * @beta
 */
export type OperationSnapshot<TResult = PublicActionResult, TAction extends PublicActionId = PublicActionId> =
  | (OperationSnapshotBase<TAction> & { status: "queued" })
  | (OperationSnapshotBase<TAction> & { status: "running"; progress: OperationProgress; cancellation?: OperationCancellationRejected })
  | (OperationSnapshotBase<TAction> & {
    status: "waiting";
    progress: OperationProgress;
    waitingFor: "runtime" | "external_service" | "user" | "resource";
    cancellation?: OperationCancellationRejected;
  })
  | (OperationSnapshotBase<TAction> & {
    status: "cancellation_requested";
    cancellation: { state: "requested"; requestedAt: string };
    progress?: OperationProgress;
  })
  | (TerminalOperationSnapshotBase<TAction> & {
    status: "succeeded";
    possibleMutation: "none" | "confirmed";
    result: TResult;
    verification: VerificationReport;
    cancellation?: OperationCancellationRejected;
  })
  | (TerminalOperationSnapshotBase<TAction> & { result?: TResult } & {
    status: "failed";
    failure: TerminalOperationFailure;
    recovery?: OperationRecovery;
    cancellation?: OperationCancellationRejected;
  })
  | (TerminalOperationSnapshotBase<TAction> & {
    status: "cancelled";
    failure: TerminalOperationFailure;
    cancellation: { state: "confirmed"; requestedAt: string; confirmedAt: string };
    verification?: VerificationReport;
    recovery?: OperationRecovery;
  })
  | (TerminalOperationSnapshotBase<TAction> & { result?: TResult } & {
    status: "partially_applied";
    possibleMutation: "partial";
    failure: TerminalOperationFailure;
    verification?: VerificationReport;
    recovery: OperationRecovery;
    cancellation?: OperationCancellationRejected;
  })
  | (TerminalOperationSnapshotBase<TAction> & { result?: TResult } & {
    status: "verification_failed";
    failure: TerminalOperationFailure;
    verification: VerificationReport;
    recovery?: OperationRecovery;
    cancellation?: OperationCancellationRejected;
  })
  | (TerminalOperationSnapshotBase<TAction> & {
    status: "recovery_failed";
    result?: TResult;
    failure: TerminalOperationFailure;
    recovery: Extract<OperationRecovery, { state: "failed" }>;
    verification?: VerificationReport;
    cancellation?: OperationCancellationRejected;
  });

/** Terminal operation result returned by `wait()`. @beta */
export type TerminalOperationSnapshot<TResult = PublicActionResult, TAction extends PublicActionId = PublicActionId> = Exclude<
  OperationSnapshot<TResult, TAction>,
  { status: "queued" | "running" | "waiting" | "cancellation_requested" }
>;

declare const operationRefBrand: unique symbol;

/**
 * Action-specific durable reference produced by a trusted SDK action. It is
 * intentionally not constructible from an unchecked result generic.
 * @beta
 */
export interface OperationRef<TAction extends PublicActionId, TResult> {
  readonly operationId: OperationId;
  readonly actionId: TAction;
  readonly actionContractVersion: PublicActionContractVersion;
  readonly [operationRefBrand]: (result: TResult) => TResult;
}

/** Options for polling an operation without implying server cancellation. @beta */
export interface OperationWaitOptions extends ConnectionControlOptions {
  /** Bounded polling cadence. Defaults to 250 milliseconds. */
  pollIntervalMs?: number;
}

/** Options for a progress subscription. @beta */
export interface OperationSubscribeOptions {
  /** Bounded polling cadence. Defaults to 250 milliseconds. */
  pollIntervalMs?: number;
  /** Stops only this local subscription. */
  signal?: AbortSignal;
}

/** Public durable operation handle independent of live object-model generations. @beta */
export interface OperationHandle<TResult, TAction extends PublicActionId = PublicActionId> {
  readonly operationId: OperationId;
  readonly actionId: TAction;
  readonly ref: OperationRef<TAction, TResult>;
  /**
   * Latest accepted snapshot. Sequence orders updates while one authority process
   * remains active. After an authority restart, a correlated immutable terminal
   * snapshot may have a lower sequence and supersede a nonterminal snapshot.
   */
  readonly current: OperationSnapshot<TResult, TAction>;
  /** Fetch and validate the current authority state. */
  refresh(options?: ConnectionControlOptions): Promise<OperationSnapshot<TResult, TAction>>;
  /** Wait locally for a terminal state. Abort and timeout stop only this wait. */
  wait(options?: OperationWaitOptions): Promise<TerminalOperationSnapshot<TResult, TAction>>;
  /**
   * Deliver current state immediately, then validated lifecycle updates until
   * unsubscribe. A correlated immutable terminal recovered after an authority
   * restart may have a lower sequence than progress observed before the restart.
   */
  subscribe(
    listener: (snapshot: OperationSnapshot<TResult, TAction>) => void,
    options?: OperationSubscribeOptions,
  ): () => void;
  /** Request cancellation. Confirmation remains a distinct authority transition. */
  requestCancellation(options?: ConnectionControlOptions): Promise<OperationSnapshot<TResult, TAction>>;
  /** Retrieve a digest-bound page from a collection declared by this operation result. */
  getResultPage(reference: OperationResultCollectionReference, options?: OperationResultPageOptions): Promise<OperationResultPage>;
}

/** Runtime-discriminated handle returned by raw-ID reattachment. @beta */
export type AnyOperationHandle = OperationHandle<PublicActionResult, PublicActionId>;

/** Mandatory operation reattachment surface on every CutAgent client. @beta */
export interface Operations {
  /** Reattach by raw ID without permitting an unchecked caller-selected result generic. */
  reattach(operationId: OperationId, options?: ConnectionControlOptions): Promise<AnyOperationHandle>;
  /** Reattach through an action-specific reference produced by a trusted SDK action. */
  reattach<TAction extends PublicActionId, TResult>(
    operation: OperationRef<TAction, TResult>,
    options?: ConnectionControlOptions,
  ): Promise<OperationHandle<TResult, TAction>>;
}
