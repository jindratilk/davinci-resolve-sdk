import {
  CUTAGENT_SDK_CAPABILITY_HEADER,
  CUTAGENT_SDK_CLOSE_PATH,
  CUTAGENT_SDK_CONFIRM_PATH,
  CUTAGENT_SDK_READ_PATH,
  CUTAGENT_SDK_OPERATION_PATH,
  CUTAGENT_SDK_WORKFLOW_PATH,
  CUTAGENT_SDK_SESSION_HEADER,
  sdkRuntimeCloseResponseSchema,
  sdkRuntimeConfirmResponseSchema,
  sdkRuntimeConnectResponseSchema,
  sdkRuntimeReadResponseSchema,
} from "../generated/sdk-runtime.js";
import { CUTAGENT_SDK_OPERATION_REQUEST_MAX_BYTES, sdkOperationControlResponseSchema } from "../generated/sdk-operations.js";
import { sdkWorkflowControlResponseSchema } from "../generated/sdk-operations.js";
import {
  CarrierFault,
  establishCarrierSession,
  type CarrierChannel,
  type CarrierConnector,
  type CarrierReply,
  type CarrierRequest,
  type EstablishedCarrierSession,
} from "../core/carrier-session.js";
import type { ConnectionControlOptions } from "../core/public-client-types.js";
import { compatibilityManifest } from "../protocol/compatibility.js";
import { discoverDesktopRuntime } from "./desktop-discovery.js";

const MAX_CONTROL_RESPONSE_BYTES = 64 * 1024;
const MAX_READ_RESPONSE_BYTES = 16 * 1024 * 1024;
const MAX_REQUEST_BYTES = 32 * 1024;

type DesktopDiscovery = Awaited<ReturnType<typeof discoverDesktopRuntime>>;

async function readBoundedJson(response: Response, maxBytes: number): Promise<unknown> {
  const contentLength = Number(response.headers.get("content-length"));
  if (Number.isFinite(contentLength) && contentLength > maxBytes) {
    await response.body?.cancel().catch(() => {});
    throw new CarrierFault("invalid_response");
  }
  if (!response.body) throw new CarrierFault("invalid_response");
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const item = await reader.read();
      if (item.done) break;
      total += item.value.byteLength;
      if (total > maxBytes) {
        await reader.cancel();
        throw new CarrierFault("invalid_response");
      }
      chunks.push(item.value);
    }
  } finally {
    reader.releaseLock();
  }
  try {
    return JSON.parse(Buffer.concat(chunks.map((chunk) => Buffer.from(chunk))).toString("utf8")) as unknown;
  } catch {
    throw new CarrierFault("invalid_response");
  }
}

class DesktopChannel implements CarrierChannel {
  readonly distribution = "standalone_local" as const;
  #discovery: DesktopDiscovery;
  #sessionToken: string | null = null;
  #sessionId: string | null = null;
  #acceptingExchanges = true;
  #terminationProven = false;
  #exchangeSettlement: Promise<void> | null = null;
  #disconnectPromise: Promise<void> | null = null;

  get terminated(): boolean {
    return this.#terminationProven;
  }

  constructor(discovery: DesktopDiscovery) {
    this.#discovery = discovery;
  }

  get acquisitionId(): string {
    return this.#discovery.bootstrapToken;
  }

  async refreshConnectAcquisition(excludeAcquisition: string, signal: AbortSignal): Promise<boolean> {
    const replacement = await discoverDesktopRuntime({
      signal,
      excludeBootstrapToken: excludeAcquisition,
    });
    if (!this.#acceptingExchanges) throw new CarrierFault("disconnected");
    this.#discovery = replacement;
    return true;
  }

  exchange(request: CarrierRequest, signal: AbortSignal): Promise<CarrierReply> {
    if (!this.#acceptingExchanges) return Promise.reject(new CarrierFault("disconnected"));
    if (this.#exchangeSettlement) return Promise.reject(new CarrierFault("invalid_response"));
    const operation = this.#performExchange(request, signal);
    const settlement = operation.then(() => undefined, () => undefined);
    this.#exchangeSettlement = settlement;
    return operation.finally(() => {
      if (this.#exchangeSettlement === settlement) this.#exchangeSettlement = null;
    });
  }

  async #performExchange(request: CarrierRequest, signal: AbortSignal): Promise<CarrierReply> {
    const endpoint = request.method === "connect"
      ? this.#discovery.endpoint
      : new URL(
        request.method === "confirm"
          ? CUTAGENT_SDK_CONFIRM_PATH
          : request.method === "read"
            ? CUTAGENT_SDK_READ_PATH
            : request.method === "operation"
              ? CUTAGENT_SDK_OPERATION_PATH
            : request.method === "workflow"
              ? CUTAGENT_SDK_WORKFLOW_PATH
            : CUTAGENT_SDK_CLOSE_PATH,
        this.#discovery.endpoint,
      ).toString();
    const headers: Record<string, string> = request.method === "connect"
      ? { [CUTAGENT_SDK_CAPABILITY_HEADER]: this.#discovery.bridgeCapability }
      : this.#sessionToken
        ? { [CUTAGENT_SDK_SESSION_HEADER]: this.#sessionToken }
        : {};
    if (request.method !== "connect" && (!this.#sessionToken || !this.#sessionId)) {
      throw new CarrierFault("disconnected");
    }
    const body = request.method === "connect"
      ? {
        ...request.payload,
        runtimeInstanceId: this.#discovery.runtimeInstanceId,
        bootstrapToken: this.#discovery.bootstrapToken,
      }
      : request.payload;
    const serialized = JSON.stringify(body);
    const maximumRequestBytes = request.method === "operation" || request.method === "read"
      ? CUTAGENT_SDK_OPERATION_REQUEST_MAX_BYTES
      : MAX_REQUEST_BYTES;
    if (Buffer.byteLength(serialized, "utf8") > maximumRequestBytes) {
      throw new CarrierFault("invalid_response");
    }
    let response: Response;
    try {
      response = await fetch(endpoint, {
        method: "POST",
        headers: { "content-type": "application/json", connection: "close", ...headers },
        body: serialized,
        redirect: "error",
        signal,
      });
    } catch (error) {
      if (signal.aborted) throw error;
      throw new CarrierFault("unavailable");
    }
    const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
    if (!/^application\/json(?:\s*;|$)/.test(contentType)) {
      await response.body?.cancel().catch(() => {});
      throw new CarrierFault("invalid_response");
    }
    const raw = await readBoundedJson(
      response,
      request.method === "read" || request.method === "operation" || request.method === "workflow" ? MAX_READ_RESPONSE_BYTES : MAX_CONTROL_RESPONSE_BYTES,
    );
    const schema = request.method === "connect"
      ? sdkRuntimeConnectResponseSchema
      : request.method === "confirm"
        ? sdkRuntimeConfirmResponseSchema
        : request.method === "read"
          ? sdkRuntimeReadResponseSchema
          : request.method === "operation"
            ? sdkOperationControlResponseSchema
          : request.method === "workflow"
            ? sdkWorkflowControlResponseSchema
          : sdkRuntimeCloseResponseSchema;
    const parsed = schema.safeParse(raw);
    if (!parsed.success || response.ok !== parsed.data.ok) throw new CarrierFault("invalid_response");
    if (request.method === "connect" && parsed.data.ok && "session" in parsed.data) {
      this.#sessionToken = parsed.data.session.sessionToken;
      this.#sessionId = parsed.data.session.sessionId;
      const { sessionToken: _sessionToken, ...session } = parsed.data.session;
      return {
        method: request.method,
        requestId: parsed.data.requestId,
        payload: { ...parsed.data, session },
      };
    }
    return {
      method: request.method,
      requestId: parsed.data.requestId,
      payload: parsed.data,
    };
  }

  settleInterruptedExchange(): Promise<void> {
    return this.#exchangeSettlement ?? Promise.resolve();
  }

  disconnect(): Promise<void> {
    if (this.#disconnectPromise) return this.#disconnectPromise;
    this.#acceptingExchanges = false;
    this.#disconnectPromise = (async () => {
      await this.settleInterruptedExchange();
      this.#sessionToken = null;
      this.#sessionId = null;
      this.#terminationProven = true;
    })();
    return this.#disconnectPromise;
  }
}

const DesktopConnector: CarrierConnector = Object.freeze({
  distribution: "standalone_local",
  distributionRange: compatibilityManifest.desktopManagedRange,
  async open(signal: AbortSignal) {
    try {
      return new DesktopChannel(await discoverDesktopRuntime({ signal }));
    } catch (error) {
      if (signal.aborted) throw error;
      throw new CarrierFault("unavailable");
    }
  },
});

/** Establish one authenticated, non-billable desktop-managed SDK session. @internal */
export function connectDesktop(options: ConnectionControlOptions = {}): Promise<EstablishedCarrierSession> {
  return establishCarrierSession(DesktopConnector, options);
}
