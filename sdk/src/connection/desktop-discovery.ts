import { constants as fsConstants } from "node:fs";
import { lstat, open, realpath, stat } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { sdkDesktopDiscoverySchema, type SdkDesktopDiscovery } from "../generated/sdk-runtime.js";
import { CutAgentSdkError } from "../protocol/errors.js";

const DISCOVERY_FILE_NAME = "cutagent-sdk-discovery-v1.json";
const MAX_DISCOVERY_BYTES = 16 * 1024;
const EVALUATOR_OBSERVER_CAPABILITY = /^cutagent-cap\.v1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/;
// The gated native evaluator deliberately publishes a ten-minute bootstrap so
// offline package installation and TypeScript compilation do not race expiry.
// Keep the consumer ceiling aligned with that signed publisher contract.
const MAX_DISCOVERY_TTL_MS = 10 * 60 * 1000;

interface DiscoveryControlOptions {
  timeoutMs?: number;
  signal?: AbortSignal;
  excludeBootstrapToken?: string;
}

function unavailable(message: string): CutAgentSdkError {
  return new CutAgentSdkError({
    kind: "runtime_unavailable",
    code: "RUNTIME_UNAVAILABLE",
    message,
    retrySafe: true,
    retrySafetyProof: { basis: "pre_execution" },
    possibleMutation: "none",
    usage: "not_reserved",
    recovery: ["restart_runtime", "retry"],
    recoveryGuidance: ["Start or restart the compatible CutAgent desktop application, then retry."],
    readbackRequired: false,
  });
}

function cancelled(): CutAgentSdkError {
  return new CutAgentSdkError({
    kind: "cancelled",
    code: "CANCELLED",
    message: "CutAgent SDK discovery was aborted before execution.",
    retrySafe: true,
    retrySafetyProof: { basis: "pre_execution" },
    possibleMutation: "none",
    usage: "not_reserved",
    recovery: ["retry"],
    recoveryGuidance: ["Retry the connection when ready."],
    readbackRequired: false,
  });
}

function discoveryCandidates(): string[] {
  const override = process.env.CUTAGENT_SDK_DISCOVERY_FILE?.trim();
  if (override) return [path.resolve(override)];

  if (process.platform === "darwin") {
    return ["CutAgent", "ai.cutagent.app"].map((owner) => path.join(
      os.homedir(),
      "Library",
      "Application Support",
      owner,
      "data",
      DISCOVERY_FILE_NAME,
    ));
  }
  if (process.platform === "win32") {
    const appData = process.env.APPDATA?.trim();
    if (!appData) return [];
    return ["CutAgent", "ai.cutagent.app"].map((owner) => path.join(
      appData,
      owner,
      "data",
      DISCOVERY_FILE_NAME,
    ));
  }
  const stateHome = process.env.XDG_STATE_HOME?.trim() || path.join(os.homedir(), ".local", "state");
  return [path.join(stateHome, "cutagent", "data", DISCOVERY_FILE_NAME)];
}

async function waitForDiscovery(signal: AbortSignal | undefined): Promise<void> {
  if (signal?.aborted) throw cancelled();
  await new Promise<void>((resolve, reject) => {
    const finish = () => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    };
    const timer = setTimeout(finish, 25);
    const onAbort = () => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
      reject(cancelled());
    };
    signal?.addEventListener("abort", onAbort, { once: true });
    timer.unref?.();
    if (signal?.aborted) onAbort();
  });
}

function assertPrivatePosixMetadata(metadata: Awaited<ReturnType<typeof stat>>, label: string): void {
  if (process.platform === "win32") return;
  const getuid = process.getuid;
  if (typeof getuid === "function" && metadata.uid !== getuid()) {
    throw unavailable(`CutAgent SDK ${label} is not owned by the current user.`);
  }
  if ((Number(metadata.mode) & 0o077) !== 0) {
    throw unavailable(`CutAgent SDK ${label} permissions are not private.`);
  }
}

function isLiveProcess(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === "EPERM";
  }
}

async function securelyReadDiscovery(filePath: string): Promise<SdkDesktopDiscovery> {
  let handle: Awaited<ReturnType<typeof open>> | null = null;
  try {
    const directoryMetadata = await lstat(path.dirname(filePath));
    if (directoryMetadata.isSymbolicLink() || !directoryMetadata.isDirectory()) {
      throw unavailable("CutAgent SDK discovery directory is not a private directory.");
    }
    assertPrivatePosixMetadata(directoryMetadata, "discovery directory");

    const linkMetadata = await lstat(filePath);
    if (linkMetadata.isSymbolicLink() || !linkMetadata.isFile() || linkMetadata.nlink !== 1) {
      throw unavailable("CutAgent SDK discovery is not a regular private file.");
    }
    assertPrivatePosixMetadata(linkMetadata, "discovery file");
    if (linkMetadata.size <= 0 || linkMetadata.size > MAX_DISCOVERY_BYTES) {
      throw unavailable("CutAgent SDK discovery has an invalid size.");
    }

    const resolved = await realpath(filePath);
    const resolvedParent = await realpath(path.dirname(filePath));
    if (resolved !== path.join(resolvedParent, path.basename(filePath))) {
      throw unavailable("CutAgent SDK discovery does not resolve to its expected private path.");
    }

    const noFollow = process.platform === "win32" ? 0 : (fsConstants.O_NOFOLLOW ?? 0);
    handle = await open(filePath, fsConstants.O_RDONLY | noFollow);
    const openedMetadata = await handle.stat();
    if (!openedMetadata.isFile()
      || openedMetadata.nlink !== 1
      || openedMetadata.dev !== linkMetadata.dev
      || openedMetadata.ino !== linkMetadata.ino
      || openedMetadata.size !== linkMetadata.size) {
      throw unavailable("CutAgent SDK discovery changed while it was being opened.");
    }
    assertPrivatePosixMetadata(openedMetadata, "discovery file");
    const contents = await handle.readFile({ encoding: "utf8" });
    if (Buffer.byteLength(contents, "utf8") > MAX_DISCOVERY_BYTES) {
      throw unavailable("CutAgent SDK discovery exceeds its safe size limit.");
    }
    const finalMetadata = await handle.stat();
    if (!finalMetadata.isFile()
      || finalMetadata.nlink !== 1
      || finalMetadata.dev !== openedMetadata.dev
      || finalMetadata.ino !== openedMetadata.ino
      || finalMetadata.size !== openedMetadata.size
      || finalMetadata.mtimeMs !== openedMetadata.mtimeMs) {
      throw unavailable("CutAgent SDK discovery changed while it was being read.");
    }
    assertPrivatePosixMetadata(finalMetadata, "discovery file");
    const decoded = JSON.parse(contents) as unknown;
    // Evaluator mode appends one private observer capability to the otherwise
    // strict public discovery record. The public client never consumes or
    // retains it, but must recognize that exact gated extension.
    let publicDiscovery = decoded;
    if (decoded && typeof decoded === "object" && !Array.isArray(decoded)
      && Object.hasOwn(decoded, "evaluatorObserverCapability")) {
      const { evaluatorObserverCapability, ...candidate } = decoded as Record<string, unknown>;
      if (typeof evaluatorObserverCapability !== "string"
        || !EVALUATOR_OBSERVER_CAPABILITY.test(evaluatorObserverCapability)) {
        throw unavailable("CutAgent SDK evaluator discovery is malformed or incompatible.");
      }
      publicDiscovery = candidate;
    }
    const parsed = sdkDesktopDiscoverySchema.safeParse(publicDiscovery);
    if (!parsed.success) {
      throw unavailable("CutAgent SDK discovery is malformed or incompatible.");
    }
    return parsed.data;
  } catch (error) {
    if (error instanceof CutAgentSdkError) throw error;
    if ((error as NodeJS.ErrnoException).code === "ENOENT") throw error;
    throw unavailable("CutAgent SDK discovery could not be read safely.");
  } finally {
    await handle?.close().catch(() => {});
  }
}

/** Resolve and validate the live desktop runtime discovery record. @internal */
export async function discoverDesktopRuntime(options: DiscoveryControlOptions = {}): Promise<SdkDesktopDiscovery> {
  if (options.signal?.aborted) throw cancelled();
  const candidates = discoveryCandidates();
  const deadline = Date.now() + (options.timeoutMs ?? 10_000);
  do {
    let unavailableCandidate: unknown;
    for (const candidate of candidates) {
      try {
        const discovery = await securelyReadDiscovery(candidate);
        const now = Date.now();
        const issuedAt = Date.parse(discovery.issuedAt);
        const expiresAt = Date.parse(discovery.expiresAt);
        if (!Number.isFinite(issuedAt)
          || !Number.isFinite(expiresAt)
          || issuedAt > now + 30_000
          || expiresAt <= issuedAt
          || expiresAt - issuedAt > MAX_DISCOVERY_TTL_MS) {
          throw unavailable("CutAgent SDK discovery has an invalid lifetime.");
        }
        if (expiresAt <= now) {
          unavailableCandidate ??= unavailable("CutAgent SDK discovery has expired.");
          continue;
        }
        if (!isLiveProcess(discovery.pid)) {
          unavailableCandidate ??= unavailable("CutAgent SDK discovery belongs to a runtime process that is no longer running.");
          continue;
        }
        if (options.excludeBootstrapToken === discovery.bootstrapToken) continue;
        return discovery;
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code === "ENOENT") continue;
        throw error;
      }
    }
    if (unavailableCandidate !== undefined) throw unavailableCandidate;
    if (Date.now() >= deadline) break;
    await waitForDiscovery(options.signal);
  } while (Date.now() < deadline);
  throw unavailable("No compatible CutAgent desktop runtime is available.");
}
