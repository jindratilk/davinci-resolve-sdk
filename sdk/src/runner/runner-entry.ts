/**
 * Managed-runner adapter. Public lifecycle, object, operation, and error
 * semantics stay in the carrier-neutral SDK core; native authorization and
 * process custody remain inside the signed proprietary launcher.
 */
export * from "../index.js";

import { request as nodeHttpRequest, type IncomingMessage } from "node:http";
import type { Socket } from "node:net";
import { z } from "zod";
import { connectDesktop } from "../connection/desktop-transport.js";
import {
  CarrierFault,
  type CarrierChannel,
  type CarrierConnector,
  type CarrierReply,
  type CarrierRequest,
} from "../core/carrier-contract.js";
import { establishCarrierSession } from "../core/carrier-session.js";
import { createCarrierClient } from "../core/client-core.js";
import {
  RuntimeSelectionSchema,
  type CutAgentClient,
  type CutAgentConnectOptions,
} from "../core/public-client-types.js";
import {
  CUTAGENT_SDK_PLUGIN_FRAME_MAX_BYTES,
  sdkPluginResponseFrameSchema,
} from "../generated/sdk-plugin-runtime.js";
import { compatibilityManifest } from "../protocol/compatibility.js";
import { brokerExchangeTimeoutMs } from "./broker-timeout.js";

const ENDPOINT_ENV = "CUTAGENT_SDK_RUNNER_BROKER_ENDPOINT";
const CAPABILITY_ENV = "CUTAGENT_SDK_RUNNER_BROKER_CAPABILITY";
// One broker JSON envelope contains one complete carrier frame. Keep the
// private HTTP hop bounded, but derive its capacity from the generated public
// carrier contract so a valid timeline snapshot cannot be rejected here.
const BROKER_ENVELOPE_MAX_BYTES = 64 * 1024;
const MAX_BROKER_BODY_BYTES = CUTAGENT_SDK_PLUGIN_FRAME_MAX_BYTES + BROKER_ENVELOPE_MAX_BYTES;
const brokerHttpRequest = nodeHttpRequest;
const endpointValue = process.env[ENDPOINT_ENV];
const capabilityValue = process.env[CAPABILITY_ENV];
delete process.env[ENDPOINT_ENV];
delete process.env[CAPABILITY_ENV];

const BrokerFaultSchema = z.enum([
  "unavailable",
  "disconnected",
  "incompatible",
  "invalid_response",
  "authentication_required",
]);
const OpenResponseSchema = z.discriminatedUnion("ok", [
  z.strictObject({ ok: z.literal(true), connectionId: z.string().regex(/^runner_connection_[A-Za-z0-9_-]{32}$/) }),
  z.strictObject({ ok: z.literal(false), fault: BrokerFaultSchema }),
]);
const ExchangeResponseSchema = z.discriminatedUnion("ok", [
  z.strictObject({ ok: z.literal(true), frame: sdkPluginResponseFrameSchema }),
  z.strictObject({ ok: z.literal(false), fault: BrokerFaultSchema }),
]);
const CloseResponseSchema = z.discriminatedUnion("ok", [
  z.strictObject({ ok: z.literal(true), terminated: z.literal(true) }),
  z.strictObject({ ok: z.literal(false), fault: BrokerFaultSchema }),
]);

interface BrokerContext {
  readonly endpoint: URL;
  readonly capability: string;
}

function brokerContext(): BrokerContext {
  if (!endpointValue || !capabilityValue) throw new CarrierFault("unavailable");
  let endpoint: URL;
  try {
    endpoint = new URL(endpointValue);
  } catch {
    throw new CarrierFault("unavailable");
  }
  if (endpoint.protocol !== "http:"
    || endpoint.hostname !== "127.0.0.1"
    || endpoint.port === ""
    || endpoint.pathname !== "/"
    || endpoint.username !== ""
    || endpoint.password !== ""
    || endpoint.search !== ""
    || endpoint.hash !== ""
    || !/^[A-Za-z0-9_-]{43}$/.test(capabilityValue)) {
    throw new CarrierFault("unavailable");
  }
  return { endpoint, capability: capabilityValue };
}

function parseBody<T>(response: IncomingMessage, schema: z.ZodType<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    const declared = Number(response.headers["content-length"]);
    if (response.statusCode !== 200
      || !Number.isSafeInteger(declared)
      || declared < 2
      || declared > MAX_BROKER_BODY_BYTES) {
      response.destroy();
      reject(new CarrierFault("invalid_response"));
      return;
    }
    const chunks: Buffer[] = [];
    let received = 0;
    response.on("data", (chunk: Buffer) => {
      received += chunk.byteLength;
      if (received > declared || received > MAX_BROKER_BODY_BYTES) {
        response.destroy(new Error("oversized"));
      } else {
        chunks.push(chunk);
      }
    });
    response.once("error", () => reject(new CarrierFault("invalid_response")));
    response.once("end", () => {
      if (received !== declared) {
        reject(new CarrierFault("invalid_response"));
        return;
      }
      let raw: unknown;
      try {
        raw = JSON.parse(Buffer.concat(chunks).toString("utf8")) as unknown;
      } catch {
        reject(new CarrierFault("invalid_response"));
        return;
      }
      const parsed = schema.safeParse(raw);
      if (!parsed.success) reject(new CarrierFault("invalid_response"));
      else resolve(parsed.data);
    });
  });
}

function brokerRequest<T>(
  context: BrokerContext,
  route: "open" | "exchange" | "close",
  body: object,
  schema: z.ZodType<T>,
  signal: AbortSignal,
): Promise<T> {
  if (signal.aborted) return Promise.reject(signal.reason ?? new DOMException("Aborted", "AbortError"));
  const bytes = Buffer.from(JSON.stringify(body));
  if (bytes.byteLength > MAX_BROKER_BODY_BYTES) {
    return Promise.reject(new CarrierFault("invalid_response"));
  }
  return new Promise<T>((resolve, reject) => {
    let settled = false;
    let socket: Socket | null = null;
    let response: IncomingMessage | null = null;
    const cleanup = () => {
      signal.removeEventListener("abort", abort);
      response?.destroy();
      socket?.destroy();
      socket?.unref();
    };
    const finish = (action: () => void) => {
      if (settled) return;
      settled = true;
      cleanup();
      action();
    };
    const request = brokerHttpRequest(new URL(route, context.endpoint), {
      method: "POST",
      agent: false,
      headers: {
        "content-type": "application/json",
        "content-length": bytes.byteLength,
        connection: "close",
        "x-cutagent-runner-capability": context.capability,
      },
    });
    const abort = () => {
      cleanup();
      request.destroy(signal.reason instanceof Error ? signal.reason : new Error("aborted"));
      finish(() => reject(signal.reason ?? new DOMException("Aborted", "AbortError")));
    };
    request.once("socket", (value) => {
      socket = value;
      if (settled || signal.aborted) cleanup();
    });
    request.once("response", (value) => {
      response = value;
      void parseBody(value, schema).then(
        (parsed) => finish(() => resolve(parsed)),
        (error: unknown) => finish(() => reject(error)),
      );
    });
    request.once("error", () => finish(() => reject(new CarrierFault("disconnected"))));
    signal.addEventListener("abort", abort, { once: true });
    request.end(bytes);
  });
}

class BrokerChannel implements CarrierChannel {
  readonly distribution = "plugin_managed" as const;
  readonly #context: BrokerContext;
  readonly #connectionId: string;
  #terminated = false;
  #settlement: Promise<void> = Promise.resolve();
  readonly #listeners = new Set<() => void>();

  constructor(context: BrokerContext, connectionId: string) {
    this.#context = context;
    this.#connectionId = connectionId;
  }

  get terminated(): boolean {
    return this.#terminated;
  }

  #terminal(): void {
    if (this.#terminated) return;
    this.#terminated = true;
    for (const listener of this.#listeners) listener();
    this.#listeners.clear();
  }

  exchange(request: CarrierRequest, signal: AbortSignal): Promise<CarrierReply> {
    if (this.#terminated) return Promise.reject(new CarrierFault("disconnected"));
    const pending = brokerRequest(
      this.#context,
      "exchange",
      {
        connectionId: this.#connectionId,
        timeoutMs: brokerExchangeTimeoutMs(request),
        frame: request,
      },
      ExchangeResponseSchema,
      signal,
    ).then((response) => {
      if (!response.ok) throw new CarrierFault(response.fault);
      return { method: response.frame.method, requestId: response.frame.requestId, payload: response.frame.payload };
    }).catch((error: unknown) => {
      if (error instanceof CarrierFault) this.#terminal();
      throw error;
    });
    this.#settlement = pending.then(() => undefined, () => undefined);
    return pending;
  }

  async disconnect(): Promise<void> {
    if (this.#terminated) return;
    const signal = AbortSignal.timeout(10_000);
    try {
      const response = await brokerRequest(
        this.#context,
        "close",
        { connectionId: this.#connectionId, timeoutMs: 10_000 },
        CloseResponseSchema,
        signal,
      );
      if (!response.ok) throw new CarrierFault(response.fault);
    } finally {
      this.#terminal();
    }
  }

  settleInterruptedExchange(): Promise<void> {
    return this.#settlement;
  }

  onDisconnect(listener: () => void): () => void {
    if (this.#terminated) {
      queueMicrotask(listener);
      return () => {};
    }
    this.#listeners.add(listener);
    return () => this.#listeners.delete(listener);
  }
}

class BrokerConnector implements CarrierConnector {
  readonly distribution = "plugin_managed" as const;
  readonly distributionRange = compatibilityManifest.pluginManagedRange;
  readonly #context = brokerContext();

  async open(signal: AbortSignal): Promise<CarrierChannel> {
    const response = await brokerRequest(
      this.#context,
      "open",
      { timeoutMs: 10_000 },
      OpenResponseSchema,
      signal,
    );
    if (!response.ok) throw new CarrierFault(response.fault);
    return new BrokerChannel(this.#context, response.connectionId);
  }
}

async function createClient(options: CutAgentConnectOptions): Promise<CutAgentClient> {
  const runtime = RuntimeSelectionSchema.parse(options.runtime ?? "auto");
  const establish = runtime === "standalone_local"
    ? (control: Parameters<typeof connectDesktop>[0]) => connectDesktop(control)
    : (control: Parameters<typeof establishCarrierSession>[1]) => establishCarrierSession(new BrokerConnector(), control);
  return createCarrierClient(establish, {
    ...(options.timeoutMs !== undefined
      ? { timeoutMs: options.timeoutMs, retainedTimeoutMs: options.timeoutMs }
      : {}),
    ...(options.signal !== undefined ? { signal: options.signal } : {}),
  });
}

/** Runner-private replacement with the exact public `CutAgent` shape. */
const RunnerCutAgent: Readonly<{
  connect(options?: CutAgentConnectOptions): Promise<CutAgentClient>;
}> = Object.freeze({
  connect(options: CutAgentConnectOptions = {}) {
    return createClient(options);
  },
});

export { RunnerCutAgent as CutAgent };
