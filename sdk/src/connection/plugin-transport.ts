import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { constants as fsConstants } from "node:fs";
import { access, lstat, realpath } from "node:fs/promises";
import path from "node:path";
import { TextDecoder } from "node:util";
import {
  CUTAGENT_SDK_PLUGIN_FRAME_MAX_BYTES,
  CUTAGENT_SDK_PLUGIN_STDIO_MODE,
  CUTAGENT_PLUGIN_CARRIER_PROTOCOL_DIGEST,
  sdkPluginResponseFrameSchema,
  type SdkPluginResponseFrame,
} from "../generated/sdk-plugin-runtime.js";
import { CUTAGENT_SDK_WIRE_PROTOCOL } from "../generated/sdk-runtime.js";
import {
  CarrierFault,
  establishCarrierSession,
  type CarrierChannel,
  type CarrierConnector,
  type CarrierReply,
  type CarrierRequest,
  type EstablishCarrierOptions,
  type EstablishedCarrierSession,
} from "../core/carrier-session.js";
import { createCarrierClient } from "../core/client-core.js";
import type { ConnectionControlOptions, CutAgentClient } from "../core/public-client-types.js";
import { compatibilityManifest } from "../protocol/compatibility.js";

const MAX_STDERR_BYTES = 8 * 1024;

/** Private carrier input. It is not exported by the public npm entry point. */
export interface InternalPluginCarrierOptions extends ConnectionControlOptions {
  launcherRoot: string;
  /** Deterministic deadline clock injection used only by carrier contract tests. */
  deadlineClock?: () => number;
}

function platformLauncher(root: string): string {
  if (process.platform === "darwin" && process.arch === "arm64") {
    return path.join(root, "bin", "macos-arm64", "cutagent");
  }
  throw new CarrierFault("incompatible");
}

async function resolveLauncher(configuredRoot: string): Promise<string> {
  if (!configuredRoot || !path.isAbsolute(configuredRoot)) throw new CarrierFault("unavailable");
  const assertTrustedDirectory = async (directory: string): Promise<string> => {
    const metadata = await lstat(directory).catch(() => null);
    if (!metadata?.isDirectory() || metadata.isSymbolicLink()) throw new CarrierFault("unavailable");
    const canonical = await realpath(directory);
    if (canonical !== path.resolve(directory)) throw new CarrierFault("unavailable");
    if (process.platform !== "win32") {
      if (typeof process.getuid === "function" && metadata.uid !== process.getuid()) {
        throw new CarrierFault("unavailable");
      }
      if ((metadata.mode & 0o022) !== 0) throw new CarrierFault("unavailable");
    }
    return canonical;
  };
  const resolvedRoot = await assertTrustedDirectory(configuredRoot);
  const launcher = platformLauncher(resolvedRoot);
  await assertTrustedDirectory(path.join(resolvedRoot, "bin"));
  await assertTrustedDirectory(path.dirname(launcher));
  const metadata = await lstat(launcher).catch(() => null);
  if (!metadata?.isFile() || metadata.isSymbolicLink() || metadata.nlink !== 1) {
    throw new CarrierFault("unavailable");
  }
  if (process.platform !== "win32") {
    if (typeof process.getuid === "function" && metadata.uid !== process.getuid()) {
      throw new CarrierFault("unavailable");
    }
    if ((metadata.mode & 0o022) !== 0) throw new CarrierFault("unavailable");
    await access(launcher, fsConstants.X_OK).catch(() => {
      throw new CarrierFault("unavailable");
    });
  }
  if (await realpath(launcher) !== launcher) throw new CarrierFault("unavailable");
  return launcher;
}

function childEnvironment(): NodeJS.ProcessEnv {
  const allowed = [
    "HOME",
    "USER",
    "LOGNAME",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "APPDATA",
    "LOCALAPPDATA",
    "USERPROFILE",
    "SystemRoot",
    "WINDIR",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
  ];
  return Object.fromEntries(
    allowed.flatMap((name) => process.env[name] === undefined ? [] : [[name, process.env[name]]]),
  ) as NodeJS.ProcessEnv;
}

class FramedPluginProcess {
  readonly #child: ChildProcessWithoutNullStreams;
  #buffer = Buffer.alloc(0);
  #stderr = Buffer.alloc(0);
  #pending: null | {
    resolve(value: SdkPluginResponseFrame): void;
    reject(reason: unknown): void;
  } = null;
  #fatal: CarrierFault | null = null;
  #successfulConnectAccepted = false;
  #requestWritten = false;
  #stopped = false;
  #terminationProven = false;
  #stopPromise: Promise<void> | null = null;
  readonly #terminalListeners = new Set<() => void>();

  constructor(launcher: string) {
    this.#child = spawn(launcher, [CUTAGENT_SDK_PLUGIN_STDIO_MODE], {
      stdio: ["pipe", "pipe", "pipe"],
      detached: true,
      windowsHide: true,
      env: childEnvironment(),
    });
    this.#child.stdout.on("data", (chunk: Buffer) => this.#accept(chunk));
    this.#child.stderr.on("data", (chunk: Buffer) => {
      if (this.#stderr.byteLength < MAX_STDERR_BYTES) {
        this.#stderr = Buffer.concat([
          this.#stderr,
          chunk.subarray(0, MAX_STDERR_BYTES - this.#stderr.byteLength),
        ]);
      }
    });
    this.#child.once("error", () => this.#fail(new CarrierFault("unavailable")));
    this.#child.once("exit", () => {
      if (this.#stopped) return;
      if (this.#buffer.byteLength > 0) {
        this.#fail(new CarrierFault("invalid_response"));
        return;
      }
      this.#fail(new CarrierFault(this.#successfulConnectAccepted || this.#requestWritten ? "disconnected" : "unavailable"));
    });
  }

  get terminated(): boolean {
    return this.#terminationProven;
  }

  #fail(error: CarrierFault): void {
    if (this.#fatal) return;
    this.#fatal = error;
    this.#pending?.reject(error);
    this.#pending = null;
    for (const listener of this.#terminalListeners) listener();
    this.#terminalListeners.clear();
    void this.stop().catch(() => {});
  }

  onTerminal(listener: () => void): () => void {
    if (this.#fatal) {
      queueMicrotask(listener);
      return () => {};
    }
    this.#terminalListeners.add(listener);
    return () => this.#terminalListeners.delete(listener);
  }

  #accept(chunk: Buffer): void {
    if (this.#fatal || this.#stopped) return;
    if (this.#buffer.byteLength + chunk.byteLength > CUTAGENT_SDK_PLUGIN_FRAME_MAX_BYTES + 4) {
      this.#fail(new CarrierFault("invalid_response"));
      return;
    }
    this.#buffer = Buffer.concat([this.#buffer, chunk]);
    while (this.#buffer.byteLength >= 4) {
      const length = this.#buffer.readUInt32BE(0);
      if (length < 2 || length > CUTAGENT_SDK_PLUGIN_FRAME_MAX_BYTES) {
        this.#fail(new CarrierFault("invalid_response"));
        return;
      }
      if (this.#buffer.byteLength < length + 4) return;
      const payload = this.#buffer.subarray(4, length + 4);
      this.#buffer = this.#buffer.subarray(length + 4);
      let raw: unknown;
      try {
        raw = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(payload)) as unknown;
      } catch {
        this.#fail(new CarrierFault("invalid_response"));
        return;
      }
      const parsed = sdkPluginResponseFrameSchema.safeParse(raw);
      if (!parsed.success || !this.#pending) {
        this.#fail(new CarrierFault("invalid_response"));
        return;
      }
      const pending = this.#pending;
      if (parsed.data.method === "connect" && parsed.data.payload.ok) {
        this.#successfulConnectAccepted = true;
      }
      this.#pending = null;
      pending.resolve(parsed.data);
    }
  }

  request(frame: object, signal: AbortSignal): Promise<SdkPluginResponseFrame> {
    if (this.#fatal) return Promise.reject(this.#fatal);
    if (this.#stopped) return Promise.reject(new CarrierFault("disconnected"));
    if (this.#pending) return Promise.reject(new CarrierFault("invalid_response"));
    const serialized = Buffer.from(JSON.stringify(frame), "utf8");
    if (serialized.byteLength > CUTAGENT_SDK_PLUGIN_FRAME_MAX_BYTES) {
      return Promise.reject(new CarrierFault("invalid_response"));
    }
    const header = Buffer.allocUnsafe(4);
    header.writeUInt32BE(serialized.byteLength, 0);
    return new Promise((resolve, reject) => {
      let settled = false;
      const cleanup = () => signal.removeEventListener("abort", onAbort);
      const finishReject = (error: unknown) => {
        if (settled) return;
        settled = true;
        cleanup();
        this.#pending = null;
        void this.stop().then(() => reject(error), reject);
      };
      const onAbort = () => finishReject(signal.reason ?? new CarrierFault("disconnected"));
      this.#pending = {
        resolve: (value) => {
          if (settled) return;
          settled = true;
          cleanup();
          resolve(value);
        },
        reject: finishReject,
      };
      signal.addEventListener("abort", onAbort, { once: true });
      if (signal.aborted) {
        onAbort();
        return;
      }
      this.#child.stdin.write(Buffer.concat([header, serialized]), (error) => {
        if (!error) {
          this.#requestWritten = true;
          return;
        }
        finishReject(new CarrierFault(this.#successfulConnectAccepted ? "disconnected" : "unavailable"));
      });
    });
  }

  stop(): Promise<void> {
    if (this.#stopPromise) return this.#stopPromise;
    this.#stopped = true;
    this.#child.stdin.destroy();
    this.#child.stdout.destroy();
    this.#child.stderr.destroy();
    this.#stopPromise = new Promise((resolve, reject) => {
      let completed = false;
      let forceTimer: NodeJS.Timeout | undefined;
      let proofTimer: NodeJS.Timeout | undefined;
      let pollTimer: NodeJS.Timeout | undefined;
      const finish = () => {
        if (completed) return;
        completed = true;
        this.#terminationProven = true;
        if (forceTimer) clearTimeout(forceTimer);
        if (proofTimer) clearTimeout(proofTimer);
        if (pollTimer) clearInterval(pollTimer);
        resolve();
      };
      const processGroupExists = () => {
        const pid = this.#child.pid;
        if (!pid) return false;
        if (process.platform === "win32") {
          return this.#child.exitCode === null && this.#child.signalCode === null;
        }
        try {
          process.kill(-pid, 0);
          return true;
        } catch (error) {
          return (error as NodeJS.ErrnoException).code !== "ESRCH";
        }
      };
      const signalTree = (signal: NodeJS.Signals) => {
        if (!this.#child.pid) return;
        if (process.platform === "win32") {
          this.#child.kill(signal);
          return;
        }
        try {
          process.kill(-this.#child.pid, signal);
        } catch (error) {
          if ((error as NodeJS.ErrnoException).code !== "ESRCH") this.#child.kill(signal);
        }
      };
      signalTree("SIGTERM");
      forceTimer = setTimeout(() => signalTree("SIGKILL"), 250);
      pollTimer = setInterval(() => {
        if (!processGroupExists()) finish();
      }, 20);
      proofTimer = setTimeout(() => {
        if (completed) return;
        completed = true;
        signalTree("SIGKILL");
        if (forceTimer) clearTimeout(forceTimer);
        if (pollTimer) clearInterval(pollTimer);
        reject(new CarrierFault("disconnected"));
      }, 2_000);
      if (!processGroupExists()) finish();
    });
    return this.#stopPromise;
  }

  settleInterruptedRequest(): Promise<void> {
    return this.#stopPromise ?? Promise.resolve();
  }
}

class PluginChannel implements CarrierChannel {
  readonly distribution = "plugin_managed" as const;
  readonly #process: FramedPluginProcess;

  constructor(process: FramedPluginProcess) {
    this.#process = process;
  }

  get terminated(): boolean {
    return this.#process.terminated;
  }

  async exchange(request: CarrierRequest, signal: AbortSignal): Promise<CarrierReply> {
    const frame = await this.#process.request({
      protocolVersion: CUTAGENT_SDK_WIRE_PROTOCOL,
      requestId: request.requestId,
      method: request.method,
      ...(request.method === "connect"
        ? { carrierProtocolDigest: CUTAGENT_PLUGIN_CARRIER_PROTOCOL_DIGEST }
        : {}),
      payload: request.payload,
    }, signal);
    return {
      method: frame.method,
      requestId: frame.requestId,
      payload: frame.payload,
      ...(!frame.payload.ok && frame.payload.error.code === "PAIRING_REQUIRED"
        ? { fault: "authentication_required" as const }
        : request.method === "operation" && !frame.payload.ok && frame.payload.error.code === "RUNTIME_UNAVAILABLE"
          ? { fault: "unavailable" as const }
        : {}),
    };
  }

  disconnect(): Promise<void> {
    return this.#process.stop();
  }

  settleInterruptedExchange(): Promise<void> {
    return this.#process.settleInterruptedRequest();
  }

  onDisconnect(listener: () => void): () => void {
    return this.#process.onTerminal(listener);
  }
}

function pluginConnector(launcherRoot: string): CarrierConnector {
  return {
    distribution: "plugin_managed",
    distributionRange: compatibilityManifest.runtimeRange,
    async open(signal) {
      if (signal.aborted) throw signal.reason;
      const launcher = await resolveLauncher(launcherRoot);
      if (signal.aborted) throw signal.reason;
      return new PluginChannel(new FramedPluginProcess(launcher));
    },
  };
}

/** Establish the private plugin-managed session through the shared session core. @internal */
export function connectPluginCarrier(options: InternalPluginCarrierOptions): Promise<EstablishedCarrierSession> {
  const establishOptions: EstablishCarrierOptions = {
    ...(options.timeoutMs !== undefined ? { timeoutMs: options.timeoutMs } : {}),
    ...(options.signal !== undefined ? { signal: options.signal } : {}),
    ...(options.deadlineClock !== undefined ? { deadlineClock: options.deadlineClock } : {}),
  };
  return establishCarrierSession(pluginConnector(options.launcherRoot), establishOptions);
}

/** Construct the same client/object model used by desktop from the private plugin carrier. @internal */
export function connectPluginClient(options: InternalPluginCarrierOptions): Promise<CutAgentClient> {
  const retained = {
    launcherRoot: options.launcherRoot,
    ...(options.timeoutMs !== undefined ? { timeoutMs: options.timeoutMs } : {}),
    ...(options.deadlineClock !== undefined ? { deadlineClock: options.deadlineClock } : {}),
  };
  return createCarrierClient(
    (control) => connectPluginCarrier({ ...retained, ...control }),
    {
      ...(options.timeoutMs !== undefined
        ? { timeoutMs: options.timeoutMs, retainedTimeoutMs: options.timeoutMs }
        : {}),
      ...(options.signal !== undefined ? { signal: options.signal } : {}),
    },
  );
}
