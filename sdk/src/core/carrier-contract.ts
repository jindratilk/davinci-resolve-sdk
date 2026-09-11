import { randomUUID } from "node:crypto";
import {
  CUTAGENT_SDK_API_VERSION,
  CUTAGENT_SDK_MAX_CONTROL_TIMEOUT_MS,
  CUTAGENT_SDK_PREVIEW_VERSION,
  CUTAGENT_SDK_PROTOCOL_DIGEST,
  CUTAGENT_SDK_WIRE_PROTOCOL,
  type SdkTimelineEditIntent,
  type SdkRuntimeReadRequest,
  type SdkRuntimeReadResponse,
} from "../generated/sdk-runtime.js";
import type {
  SdkOperationControlRequest,
  SdkOperationEvent,
  SdkOperationResultPage,
  SdkWorkflowControlRequest,
  SdkWorkflowSnapshot,
} from "../generated/sdk-operations.js";
import { RequestIdSchema, type RequestId } from "../value-types/identities.js";

// Desktop-managed reads invoke the release-hardened CutAgent CLI guard, whose
// manifest verification can dominate a healthy first command on cold storage.
// Keep public control bounded at the reviewed protocol maximum while allowing
// callers to opt into a shorter deadline for latency-sensitive work.
export const DEFAULT_CONTROL_TIMEOUT_MS = 60_000;
export const MIN_CONTROL_TIMEOUT_MS = 100;
export const MAX_CONTROL_TIMEOUT_MS = CUTAGENT_SDK_MAX_CONTROL_TIMEOUT_MS;

export type CarrierDistribution = "standalone_local" | "plugin_managed";
export type CarrierMethod = "connect" | "confirm" | "read" | "operation" | "workflow" | "close";
export type CarrierReadRequest =
  | Pick<Extract<SdkRuntimeReadRequest, { operation: "voice.catalog" }>, "operation" | "query">
  | Pick<Extract<SdkRuntimeReadRequest, { operation: "project.context" }>, "operation">
  | Pick<Extract<SdkRuntimeReadRequest, { operation: "project.current" }>, "operation">
  | Pick<Extract<SdkRuntimeReadRequest, { operation: "timeline.current" }>, "operation" | "projectId">
  | Pick<Extract<SdkRuntimeReadRequest, { operation: "timeline.snapshot" }>, "operation" | "projectId" | "timelineId">
  | Pick<Extract<SdkRuntimeReadRequest, { operation: "timeline.retime" }>, "operation" | "projectId" | "timelineId" | "timelineRevision" | "target">
  | Pick<Extract<SdkRuntimeReadRequest, { operation: "timeline.managed.preview" }>, "operation" | "program">
  | Pick<Extract<SdkRuntimeReadRequest, { operation: "timeline.managed.export" }>, "operation" | "request">
  | Pick<Extract<SdkRuntimeReadRequest, { operation: "fusion.compositions" }>, "operation" | "projectId" | "timelineId" | "timelineItemId" | "expectedRevision">
  | Pick<Extract<SdkRuntimeReadRequest, { operation: "mediaPool.page" }>, "operation" | "projectId" | "offset" | "pageSize" | "expectedRevision" | "search">
  | Pick<Extract<SdkRuntimeReadRequest, { operation: "mediaPool.transcription" }>, "operation" | "projectId" | "mediaPoolItemId" | "expectedRevision" | "useNestedClipTranscription">
  | Pick<Extract<SdkRuntimeReadRequest, { operation: "color.current" }>, "operation" | "projectId" | "timelineId" | "nodeStackLayerIndex">
  | { readonly operation: "timeline.edit.preview"; readonly intent: SdkTimelineEditIntent }
  | { readonly operation: "timeline.edit.preview"; readonly intents: readonly SdkTimelineEditIntent[] }
  | Pick<Extract<SdkRuntimeReadRequest, { operation: "multicam.inspect" }>, "operation" | "projectId" | "mediaPoolItemId" | "multicamName" | "expectedRevision">
  | Pick<Extract<SdkRuntimeReadRequest, { operation: "render.discovery" }>, "operation" | "projectId">
  | Pick<Extract<SdkRuntimeReadRequest, { operation: "render.presets" }>, "operation" | "projectId">
  | Pick<Extract<SdkRuntimeReadRequest, { operation: "render.settings" }>, "operation" | "projectId">
  | Pick<Extract<SdkRuntimeReadRequest, { operation: "render.queue" }>, "operation" | "projectId" | "pageSize" | "cursor">
  | Pick<Extract<SdkRuntimeReadRequest, { operation: "render.job_status" }>, "operation" | "projectId" | "queueRevision" | "jobId">
  | Pick<Extract<SdkRuntimeReadRequest, { operation: "artifact.content" }>, "operation" | "artifactId" | "offset" | "length">
  | Pick<Extract<SdkRuntimeReadRequest, { operation: "artifact.fusion_setting.publish" }>, "operation" | "setting">;
export type CarrierReadSuccess = Extract<SdkRuntimeReadResponse, { ok: true }>;
type SelectOperationRequest<T> = T extends {
  operation: "operation.create";
  actionId: infer TAction;
  input: infer TInput;
  idempotencyKey: infer TIdempotency;
}
  ? { operation: "operation.create"; actionId: TAction; input: TInput; idempotencyKey: TIdempotency }
  : never;
export type CarrierOperationRequest =
  | Pick<Extract<SdkOperationControlRequest, { operation: "operation.get" | "operation.cancel" }>, "operation" | "operationId">
  | Pick<Extract<SdkOperationControlRequest, { operation: "operation.result.page" }>, "operation" | "operationId" | "collectionId" | "expectedDigest" | "offset" | "pageSize">
  | SelectOperationRequest<Extract<SdkOperationControlRequest, { operation: "operation.create" }>>;
export type CarrierOperationSuccess = SdkOperationEvent | SdkOperationResultPage;
export type CarrierOperationSuccessFor<TRequest extends CarrierOperationRequest> =
  TRequest extends { operation: "operation.result.page" }
    ? SdkOperationResultPage
    : SdkOperationEvent;
type StripWorkflowEnvelope<T> = T extends unknown ? Omit<T, "protocolVersion" | "requestId" | "sessionId" | "deadlineAtMs"> : never;
export type CarrierWorkflowRequest = StripWorkflowEnvelope<SdkWorkflowControlRequest>;
export type CarrierWorkflowSuccess = SdkWorkflowSnapshot;

export type CarrierRequest =
  | {
    readonly method: "connect";
    readonly requestId: RequestId;
    readonly payload: {
      readonly protocolVersion: typeof CUTAGENT_SDK_WIRE_PROTOCOL;
      readonly handshake: {
        readonly requestId: RequestId;
        readonly sdkVersion: typeof CUTAGENT_SDK_PREVIEW_VERSION;
        readonly sdkApiVersion: typeof CUTAGENT_SDK_API_VERSION;
        readonly supportedWireProtocols: readonly [typeof CUTAGENT_SDK_WIRE_PROTOCOL];
        readonly requestedDistribution: CarrierDistribution;
        readonly protocolDigest: typeof CUTAGENT_SDK_PROTOCOL_DIGEST;
      };
    };
  }
  | {
    readonly method: "confirm" | "close";
    readonly requestId: RequestId;
    readonly payload: {
      readonly protocolVersion: typeof CUTAGENT_SDK_WIRE_PROTOCOL;
      readonly requestId: RequestId;
      readonly sessionId: string;
    };
  }
  | {
    readonly method: "read";
    readonly requestId: RequestId;
    readonly payload: {
      readonly protocolVersion: typeof CUTAGENT_SDK_WIRE_PROTOCOL;
      readonly requestId: RequestId;
      readonly sessionId: string;
      readonly deadlineAtMs: number;
    } & CarrierReadRequest;
  }
  | {
    readonly method: "operation";
    readonly requestId: RequestId;
    readonly payload: {
      readonly protocolVersion: typeof CUTAGENT_SDK_WIRE_PROTOCOL;
      readonly requestId: RequestId;
      readonly sessionId: string;
      readonly deadlineAtMs: number;
    } & CarrierOperationRequest;
  }
  | {
    readonly method: "workflow";
    readonly requestId: RequestId;
    readonly payload: {
      readonly protocolVersion: typeof CUTAGENT_SDK_WIRE_PROTOCOL;
      readonly requestId: RequestId;
      readonly sessionId: string;
      readonly deadlineAtMs: number;
    } & CarrierWorkflowRequest;
  };

/** A carrier reply after carrier-specific framing has been removed. */
export interface CarrierReply {
  readonly method: unknown;
  readonly requestId: unknown;
  readonly payload: unknown;
  /** Sanitized carrier-only failure hint. Correlation is validated before projection. */
  readonly fault?: CarrierFaultKind;
}

/** Carrier-specific transport channel. It owns no public lifecycle or error projection. */
export interface CarrierChannel {
  readonly distribution: CarrierDistribution;
  /** True only after the carrier has proved that its local transport is terminal. */
  readonly terminated: boolean;
  exchange(request: CarrierRequest, signal: AbortSignal): Promise<CarrierReply>;
  disconnect(): Promise<void>;
  /** Await carrier cleanup triggered by aborting its current exchange. */
  settleInterruptedExchange(): Promise<void>;
  /** Observe a carrier-detected terminal loss. Lifecycle projection remains in the shared core. */
  onDisconnect?(listener: () => void): () => void;
  refreshConnectAcquisition?(excludeAcquisition: string, signal: AbortSignal): Promise<boolean>;
  readonly acquisitionId?: string;
}

/** Opens only the carrier-specific transport and acquisition context. */
export interface CarrierConnector {
  readonly distribution: CarrierDistribution;
  /** Reviewed range selected by the carrier's separately authorized distribution path. */
  readonly distributionRange: string | null;
  open(signal: AbortSignal): Promise<CarrierChannel>;
}

export type CarrierFaultKind = "unavailable" | "disconnected" | "incompatible" | "invalid_response" | "authentication_required";

/** Sanitized internal signal from a carrier adapter to the shared session core. */
export class CarrierFault extends Error {
  readonly kind: CarrierFaultKind;

  constructor(kind: CarrierFaultKind) {
    super(kind);
    this.name = "CarrierFault";
    this.kind = kind;
  }
}

export function timeoutValue(value: number | undefined): number {
  if (value === undefined) return DEFAULT_CONTROL_TIMEOUT_MS;
  if (!Number.isInteger(value) || value < MIN_CONTROL_TIMEOUT_MS || value > MAX_CONTROL_TIMEOUT_MS) {
    throw new TypeError(`timeoutMs must be an integer from ${MIN_CONTROL_TIMEOUT_MS} through ${MAX_CONTROL_TIMEOUT_MS}.`);
  }
  return value;
}

export function newRequestId(): RequestId {
  return RequestIdSchema.parse(`request_${randomUUID()}`);
}
