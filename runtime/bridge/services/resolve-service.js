import { execFile, spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import {
  areResolveProjectsEqual,
  normalizeDatabaseDetails,
  normalizeResolveProject,
} from "../contracts/resolve-project.js";
import { parseJsonValueFromText } from "../contracts/json-output.js";
import {
  bridgeCliErrorFromPayload,
  buildBridgeErrorPayload,
  buildCliProtocolViolationError,
  buildCliTimeoutError,
} from "../contracts/bridge-error.js";
import { buildCutAgentCliEnv, resolveCutAgentCliCommand } from "../../local/cli-runtime.mjs";
import { getSessionRuntimeEnv } from "./session-runtime-paths.js";
import { getSdkOwnerSession } from "./sdk-owner-session-context.js";
import { assertCutAgentCliPolicyBeforeSpawn } from "./cutagent-cli-authorization.js";
import {
  listeningPidsForPort,
  terminateManagedEmbeddedRuntimeForPort,
  terminateWindowsProcessTree,
  waitForPortRelease,
} from "./embedded-runtime-process.js";

const execFileAsync = promisify(execFile);
const SOFT_DATABASE_ERROR_CODES = new Set([
  "EMBEDDED_BRIDGE_NOT_RUNNING",
  "RESOLVE_NOT_RUNNING",
  "RESOLVE_SCRIPTING_UNAVAILABLE",
  "NO_PROJECT_OPEN",
]);
const RESOLVE_ACTIVATION_ATTEMPTS = process.platform === "darwin"
  ? [
      ["/usr/bin/open", ["-b", "com.blackmagic-design.DaVinciResolve"]],
      ["/usr/bin/open", ["-a", "DaVinci Resolve"]],
    ]
  : [];
const EMBEDDED_AUTH_FILE_NAME = "embedded-bridge-auth.json";
const EMBEDDED_AUTH_TOKEN_WAIT_MS = embeddedAuthTokenWaitMs();
const EMBEDDED_DEFAULT_PORT = 18764;
const EMBEDDED_FALLBACK_PORTS = [18765, 18766, 18767, 18768, 18769];
const EMBEDDED_TIME_WAIT_FALLBACK_THRESHOLD = 1000;
const RELEASE_BRIDGE_BUNDLE = process.env.CUTAGENT_RELEASE_BRIDGE_BUNDLE === "1";
const CUTAGENT_AUTH_BYPASS_ENV_PATTERN = /^CUTAGENT_.*AUTH.*BYPASS$/;
const EMBEDDED_RESTART_ERROR_CODES = new Set([
  "EMBEDDED_BRIDGE_AUTH_FAILED",
  "EMBEDDED_BRIDGE_OUTDATED",
]);
const STUDIO_EXTERNAL_TRANSPORT = "studio_external";
const EMBEDDED_FREE_TRANSPORT = "embedded_free";
const TRANSIENT_STATUS_FAILURE_LIMIT = 12;
const TRANSIENT_STATUS_FAILURE_TTL_MS = 120_000;
const STATUS_TRANSITION_TELEMETRY_WINDOW_MS = 60_000;
const STATUS_TRANSITION_INFO_LIMIT = 2;
const STATUS_TRANSITION_WARNING_LIMIT = 1;

function embeddedAuthTokenWaitMs(platform = process.platform) {
  // A cold Windows Python runtime can take several seconds to import the
  // embedded bridge before it publishes the auth file. Keep the shorter wait
  // on platforms where startup is already fast, but do not kill a healthy
  // Windows bridge while it is still booting.
  return platform === "win32" ? 20000 : 3000;
}

export async function probeResolveProcessRunning({
  platform = process.platform,
  env = process.env,
  execFileFn = execFileAsync,
} = {}) {
  if (platform === "win32") {
    const systemRoot = typeof env.SystemRoot === "string" && env.SystemRoot.trim()
      ? env.SystemRoot.trim()
      : typeof env.WINDIR === "string" && env.WINDIR.trim()
        ? env.WINDIR.trim()
        : "";
    if (!systemRoot || !path.win32.isAbsolute(systemRoot)) {
      return null;
    }
    try {
      const result = await execFileFn(path.win32.join(systemRoot, "System32", "tasklist.exe"), [
        "/FI",
        "IMAGENAME eq Resolve.exe",
        "/FO",
        "CSV",
        "/NH",
      ], {
        encoding: "utf8",
        timeout: 2000,
        windowsHide: true,
        shell: false,
      });
      return /(?:^|\r?\n)\s*"Resolve\.exe"\s*,/i.test(String(result?.stdout ?? ""));
    } catch {
      return null;
    }
  }

  const command = ["/usr/bin/pgrep", "/bin/pgrep"].find((candidate) => fs.existsSync(candidate));
  if (!command) {
    return null;
  }
  try {
    await execFileFn(command, ["-x", platform === "darwin" ? "Resolve" : "resolve"], {
      encoding: "utf8",
      timeout: 2000,
      shell: false,
    });
    return true;
  } catch (error) {
    return Number(error?.code) === 1 ? false : null;
  }
}

function normalizeResolveEdition(value) {
  const text = typeof value === "string" ? value.trim().toLowerCase() : "";
  if (text === "studio" || text === "free") {
    return text;
  }
  return null;
}

function inferEditionFromProductName(productName) {
  const text = typeof productName === "string" ? productName.trim().toLowerCase() : "";
  if (!text) {
    return null;
  }
  return text.includes("studio") ? "studio" : "free";
}

function normalizeLastKnownResolveRoute(route) {
  if (!route || typeof route !== "object") {
    return {
      active_transport: null,
      edition: null,
      product_name: null,
    };
  }
  const activeTransport = typeof route.active_transport === "string" ? route.active_transport : null;
  const productName = typeof route.product_name === "string" && route.product_name.trim()
    ? route.product_name.trim()
    : null;
  return {
    active_transport: activeTransport,
    edition: normalizeResolveEdition(route.edition) ?? inferEditionFromProductName(productName),
    product_name: productName,
  };
}

function classifyResolveTransport(status, lastKnownRoute = null) {
  const transports = status?.transports && typeof status.transports === "object" ? status.transports : {};
  const studio = transports.studio_external && typeof transports.studio_external === "object"
    ? transports.studio_external
    : {};
  const embedded = transports.embedded_free && typeof transports.embedded_free === "object"
    ? transports.embedded_free
    : {};
  const activeTransport = typeof status?.active_transport === "string" ? status.active_transport : null;
  const productName = typeof status?.product_name === "string" && status.product_name.trim()
    ? status.product_name.trim()
    : null;
  const directEdition = normalizeResolveEdition(status?.edition) ?? inferEditionFromProductName(productName);
  const lastKnown = normalizeLastKnownResolveRoute(lastKnownRoute);
  const embeddedExplicitlyConfigured = studio.reason === "embedded_free_configured";
  const studioExplicitlyConfigured = embedded.reason === "studio_external_configured";
  const connectionError = status?.data?.connection_error && typeof status.data.connection_error === "object"
    ? status.data.connection_error
    : {};
  const scriptingUnavailable = studio.error_code === "RESOLVE_SCRIPTING_UNAVAILABLE"
    || connectionError.code === "RESOLVE_SCRIPTING_UNAVAILABLE";

  let embeddedRelevance = "unknown";
  let effectiveTransport = activeTransport;
  let effectiveEdition = directEdition;

  if (!effectiveTransport && studio.connected === true) {
    effectiveTransport = STUDIO_EXTERNAL_TRANSPORT;
  } else if (!effectiveTransport && embedded.connected === true) {
    effectiveTransport = EMBEDDED_FREE_TRANSPORT;
  }

  if (!effectiveEdition && effectiveTransport === STUDIO_EXTERNAL_TRANSPORT) {
    effectiveEdition = "studio";
  } else if (!effectiveEdition && effectiveTransport === EMBEDDED_FREE_TRANSPORT) {
    effectiveEdition = "free";
  }

  if (embeddedExplicitlyConfigured || activeTransport === EMBEDDED_FREE_TRANSPORT || embedded.connected === true) {
    embeddedRelevance = "required";
    effectiveTransport = effectiveTransport ?? EMBEDDED_FREE_TRANSPORT;
    effectiveEdition = effectiveEdition ?? "free";
  } else if (
    studioExplicitlyConfigured
    || activeTransport === STUDIO_EXTERNAL_TRANSPORT
    || studio.connected === true
    || directEdition === "studio"
  ) {
    embeddedRelevance = "irrelevant";
    effectiveTransport = effectiveTransport ?? STUDIO_EXTERNAL_TRANSPORT;
    effectiveEdition = effectiveEdition ?? "studio";
  } else if (directEdition === "free") {
    embeddedRelevance = "required";
    effectiveEdition = "free";
  } else if (
    status?.connected !== true
    && (lastKnown.active_transport === EMBEDDED_FREE_TRANSPORT || lastKnown.edition === "free")
  ) {
    embeddedRelevance = "required";
    effectiveTransport = effectiveTransport ?? EMBEDDED_FREE_TRANSPORT;
    effectiveEdition = effectiveEdition ?? "free";
  }

  let primaryDisconnectReason = null;
  if (status?.connected !== true) {
    if (scriptingUnavailable) {
      primaryDisconnectReason = "davinci_resolve_scripting_unavailable";
    } else if (embeddedRelevance === "irrelevant" || effectiveEdition === "studio") {
      primaryDisconnectReason = "davinci_resolve_studio_unavailable";
    } else if (embeddedRelevance === "required" || effectiveEdition === "free") {
      primaryDisconnectReason = "davinci_resolve_free_embedded_bridge_unavailable";
    } else {
      primaryDisconnectReason = "davinci_resolve_unavailable";
    }
  }

  return {
    effective_transport: effectiveTransport,
    effective_edition: effectiveEdition,
    embedded_relevance: embeddedRelevance,
    primary_disconnect_reason: primaryDisconnectReason,
    last_known_active_transport: lastKnown.active_transport,
    last_known_edition: lastKnown.edition,
    last_known_product_name: lastKnown.product_name,
  };
}

function safeJsonParse(text) {
  return parseJsonValueFromText(text);
}

function hasCutAgentAuthBypassEnv(env = {}) {
  return Object.entries(env).some(([name, value]) => (
    CUTAGENT_AUTH_BYPASS_ENV_PATTERN.test(name)
    && value === "1"
  ));
}

async function parseResolveJson(
  args,
  timeoutMs,
  {
    cutAgentCliAuthorizationService = null,
    accessToken = null,
    session = null,
    extraEnv = null,
    skipCutAgentCliAuthorization = false,
    cutAgentCliCommand = null,
    cwd = null,
    carrier = "cli",
    policyContext = null,
    refreshProtectedTargets = null,
    signal = null,
    deadlineAtMs = null,
    onAuthorization = null,
    issueBrokerEnvironment = null,
    onSpawnAttempt = null,
  } = {},
) {
  const effectiveSession = session ?? getSdkOwnerSession();
  const jsonArgs = ["-j", ...args];
  let childTimeoutOwnedByDeadline = false;
  let spawnAttempted = false;
  const abortReason = () => signal?.reason ?? new DOMException("The SDK inspection was aborted.", "AbortError");
  const remainingTimeoutMs = () => {
    if (signal?.aborted) throw abortReason();
    if (deadlineAtMs !== null && deadlineAtMs !== undefined && Number.isFinite(Number(deadlineAtMs))) {
      const remaining = Math.floor(Number(deadlineAtMs) - Date.now());
      if (remaining < 1) throw new DOMException("The SDK inspection deadline expired.", "TimeoutError");
      childTimeoutOwnedByDeadline = remaining <= timeoutMs;
      return Math.max(1, Math.min(timeoutMs, remaining));
    }
    return timeoutMs;
  };
  try {
    let effectiveTimeoutMs = remainingTimeoutMs();
    const authorization = skipCutAgentCliAuthorization
      ? null
      : await cutAgentCliAuthorizationService?.authorize?.(jsonArgs, {
        accessToken,
        session: effectiveSession,
        timeoutMs: effectiveTimeoutMs,
        cutAgentCliCommand,
        cwd,
        carrier,
        policyContext,
        refreshProtectedTargets,
        signal,
      });
    if (authorization && typeof onAuthorization === "function") onAuthorization(authorization);
    effectiveTimeoutMs = remainingTimeoutMs();
    await assertCutAgentCliPolicyBeforeSpawn(cutAgentCliAuthorizationService, jsonArgs, authorization);
    const brokerEnv = typeof issueBrokerEnvironment === "function"
      ? await issueBrokerEnvironment({ authorization, args: [...jsonArgs] })
      : null;
    effectiveTimeoutMs = remainingTimeoutMs();
    if (typeof onSpawnAttempt === "function") onSpawnAttempt();
    spawnAttempted = true;
    const result = await execFileAsync(cutAgentCliCommand || resolveCutAgentCliCommand(), jsonArgs, {
      encoding: "utf8",
      timeout: effectiveTimeoutMs,
      maxBuffer: 10 * 1024 * 1024,
      shell: false,
      ...(cwd ? { cwd } : {}),
      ...(signal ? { signal } : {}),
      env: buildCutAgentCliEnv({args: jsonArgs,
        sessionEnv: getSessionRuntimeEnv(effectiveSession),
        extraEnv: {
          ...(extraEnv ?? {}),
          ...(authorization?.env ?? {}),
          ...(brokerEnv ?? {}),
        },
      }),
    });
    const output = typeof result.stdout === "string" ? result.stdout : "";
    const parsed = safeJsonParse(output);
    if (parsed) {
      return parsed;
    }
    throw buildCliProtocolViolationError({
      args,
      stdout: typeof output === "string" ? output.trim() : "",
    });
  } catch (error) {
    if (signal?.aborted || error?.name === "AbortError" || error?.name === "TimeoutError") {
      throw signal?.aborted ? abortReason() : error;
    }
    if (!spawnAttempted) throw error;
    const stdout = typeof error?.stdout === "string" ? error.stdout : "";
    const parsed = safeJsonParse(stdout);
    if (parsed) {
      const exitCode = Number.isInteger(error?.code)
        ? error.code
        : Number.isInteger(error?.status)
          ? error.status
          : null;
      if (exitCode !== null && !Number.isInteger(parsed?.exit_code)) {
        return {
          ...parsed,
          exit_code: exitCode,
        };
      }
      return parsed;
    }
    if (error?.code === "CLI_PROTOCOL_VIOLATION") {
      throw error;
    }
    if (error?.killed === true) {
      if (childTimeoutOwnedByDeadline) {
        throw new DOMException("The SDK inspection deadline expired.", "TimeoutError");
      }
      // execFile killed the child because it exceeded `timeout` (a busy
      // DaVinci Resolve routinely does this); that is not a protocol violation.
      throw buildCliTimeoutError({
        args,
        timeout_ms: Number.isFinite(Number(timeoutMs)) ? Number(timeoutMs) : null,
        signal: typeof error?.signal === "string" ? error.signal : null,
        stdout: stdout.trim(),
        stderr: typeof error?.stderr === "string" ? error.stderr.trim() : "",
      });
    }
    throw buildCliProtocolViolationError({
      args,
      stdout: stdout.trim(),
      stderr: typeof error?.stderr === "string" ? error.stderr.trim() : "",
      cause: error instanceof Error ? error.message : String(error ?? ""),
      exit_code: Number.isInteger(error?.code)
        ? error.code
        : Number.isInteger(error?.status)
          ? error.status
          : null,
    });
  }
}

function requireCutAgentCliSuccess(payload, fallbackMessage) {
  const cliError = bridgeCliErrorFromPayload(payload, { fallbackMessage });
  if (cliError) {
    throw cliError;
  }
  return payload;
}

async function activateResolveAppBestEffort() {
  for (const [command, args] of RESOLVE_ACTIVATION_ATTEMPTS) {
    try {
      await execFileAsync(command, args, {
        timeout: 10_000,
        shell: false,
      });
      return true;
    } catch {
      // Best-effort only. Project switching should still succeed even if activation fails.
    }
  }

  return false;
}

function buildProjectIdentity(projectName, currentDatabase, status = "inactive") {
  const name = typeof projectName === "string" ? projectName.trim() : "";
  if (!name) {
    return null;
  }

  return normalizeResolveProject({
    name,
    ...normalizeDatabaseDetails(currentDatabase),
    status,
  }, status);
}

function extractProjectRows(payload) {
  const data = payload?.data ?? payload;
  if (Array.isArray(data)) {
    return data;
  }
  if (Array.isArray(data?.projects)) {
    return data.projects;
  }
  return [];
}

function normalizeProjectListRows(rows, currentDatabase, { strict = false } = {}) {
  return rows
    .map((project, offset) => {
      const name = typeof project === "string" ? project : project?.name;
      const current = typeof project === "object" && project !== null
        ? project.current === "✓" || project.current === true
        : false;
      const identity = buildProjectIdentity(name, currentDatabase, current ? "active" : "inactive");
      if (!identity && strict) throw new Error(`DaVinci Resolve returned an invalid project inventory row at index ${offset + 1}.`);
      const index = Number.isSafeInteger(project?.index) && project.index >= 1 ? project.index : offset + 1;
      return identity ? { ...identity, current, index } : null;
    })
    .filter(Boolean);
}

function normalizeResolveStatusPayload(payload, currentDatabase = null, lastKnownRoute = null) {
  const info = payload?.data ?? payload;

  let connected = false;
  if (typeof info?.resolve === "boolean") {
    connected = info.resolve;
  } else if (info?.status === "connected") {
    connected = true;
  } else if (info?.status === "disconnected") {
    connected = false;
  }

  const hasActiveProject = connected && info?.project_open !== false && info?.context !== "project_manager";
  const activeProject = hasActiveProject
    ? buildProjectIdentity(info?.project ?? null, currentDatabase, "active")
    : null;

  const status = {
    status: connected ? "connected" : "disconnected",
    connected,
    active_transport: typeof info?.active_transport === "string" ? info.active_transport : null,
    transports: info?.transports ?? null,
    resolve_version: info?.resolve_version ?? null,
    product_name: info?.product_name ?? null,
    edition: info?.edition ?? null,
    project_name: activeProject?.name ?? null,
    current_database: normalizeDatabaseDetails(currentDatabase),
    active_project: activeProject,
    data: payload ?? {},
  };
  return {
    ...status,
    ...classifyResolveTransport(status, lastKnownRoute),
  };
}

function normalizeResolveStatusError(
  error,
  currentDatabase = null,
  fallbackMessage = "Failed to query DaVinci Resolve status.",
  lastKnownRoute = null,
) {
  const payload = buildBridgeErrorPayload(error, fallbackMessage);
  const code = payload.cli_error_code ?? error?.code ?? "RESOLVE_STATUS_UNAVAILABLE";
  const message = payload.message ?? fallbackMessage;
  const details = payload.cli_error_details ?? {};
  const meta = payload.cli_meta ?? {};

  const status = {
    status: "disconnected",
    connected: false,
    active_transport: null,
    transports: null,
    resolve_version: null,
    product_name: null,
    edition: null,
    project_name: null,
    current_database: normalizeDatabaseDetails(currentDatabase),
    active_project: null,
    error: {
      code,
      message,
      details,
      recoverability: meta.recoverability ?? error?.recoverability ?? null,
      exit_code: payload.exit_code ?? null,
    },
    data: {
      ok: false,
      data: null,
      error: {
        code,
        message,
        details,
      },
      meta,
    },
  };
  return {
    ...status,
    ...classifyResolveTransport(status, lastKnownRoute),
  };
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function getEmbeddedAuthPath(env = process.env, platform = process.platform) {
  const override = typeof env.DAVINCI_RESOLVE_SDK_EMBEDDED_AUTH_PATH === "string"
    ? env.DAVINCI_RESOLVE_SDK_EMBEDDED_AUTH_PATH.trim()
    : "";
  if (override) {
    return path.resolve(override.replace(/^~(?=$|\/)/, env.HOME || os.homedir()));
  }
  const home = typeof env.HOME === "string" && env.HOME.trim() ? env.HOME.trim() : os.homedir();
  const scope = getEmbeddedAuthScope(env);
  const scopedFileName = EMBEDDED_AUTH_FILE_NAME.replace(/\.json$/, `.${scope}.json`);
  if (platform === "win32") {
    const pathApi = path.win32;
    const appData = typeof env.APPDATA === "string" && env.APPDATA.trim()
      ? env.APPDATA.trim()
      : pathApi.join(
        typeof env.USERPROFILE === "string" && env.USERPROFILE.trim() ? env.USERPROFILE.trim() : home,
        "AppData",
        "Roaming",
      );
    return pathApi.join(appData, "DaVinciResolveSDK", scopedFileName);
  }
  return path.join(home, "Library", "Application Support", "DaVinciResolveSDK", scopedFileName);
}

function sanitizeEmbeddedAuthScope(value) {
  const raw = typeof value === "string" ? value.trim().toLowerCase() : "";
  if (!raw) {
    return "";
  }
  const normalized = raw
    .replace(/[^a-z0-9_.-]+/g, "-")
    .replace(/^[._-]+|[._-]+$/g, "");
  return normalized || "local";
}

function getEmbeddedAuthScope() { return "standalone"; }

function readEmbeddedAuthTokenStatus({ env = process.env, startedAtMs = null } = {}) {
  const authPath = getEmbeddedAuthPath(env);
  const status = {
    auth_path: authPath,
    auth_token_present: false,
    auth_token_valid: false,
    fresh: false,
    error: null,
  };
  try {
    const stat = fs.statSync(authPath);
    const raw = fs.readFileSync(authPath, "utf8");
    const payload = JSON.parse(raw);
    const token = payload && typeof payload === "object" && !Array.isArray(payload)
      ? payload.auth_token
      : null;
    status.auth_token_present = typeof token === "string" && token.length > 0;
    status.auth_token_valid = status.auth_token_present;
    status.host = typeof payload.host === "string" ? payload.host : null;
    status.port = normalizePort(payload.port);
    status.fresh = startedAtMs === null || stat.mtimeMs >= startedAtMs - 1000;
    if (!status.auth_token_valid) {
      status.error = "missing_auth_token";
    } else if (!status.fresh) {
      status.error = "stale_auth_token";
    }
  } catch (error) {
    status.error = error instanceof Error ? error.message : "auth_token_unavailable";
  }
  return status;
}

async function waitForEmbeddedAuthToken({ child, env, startedAtMs, timeoutMs = EMBEDDED_AUTH_TOKEN_WAIT_MS }) {
  const deadline = Date.now() + timeoutMs;
  let lastStatus = readEmbeddedAuthTokenStatus({ env, startedAtMs });
  while (Date.now() < deadline) {
    if (lastStatus.auth_token_valid && lastStatus.fresh) {
      return lastStatus;
    }
    if (child.exitCode !== null || child.signalCode !== null || child.killed) {
      break;
    }
    await delay(100);
    lastStatus = readEmbeddedAuthTokenStatus({ env, startedAtMs });
  }
  return lastStatus;
}

function normalizeEmbeddedStatusPayload(payload) {
  const data = payload?.data ?? payload;
  return data && typeof data === "object" && !Array.isArray(data) ? data : null;
}

function normalizeEmbeddedServer(status) {
  const server = status?.server;
  return server && typeof server === "object" && !Array.isArray(server) ? server : null;
}

function embeddedStatusErrorCode(status) {
  const server = normalizeEmbeddedServer(status);
  const candidates = [
    status?.server_error_code,
    status?.error_code,
    server?.error_code,
    status?.server_error_details?.embedded_error_code,
    status?.error_details?.embedded_error_code,
    server?.error_details?.embedded_error_code,
  ];
  for (const candidate of candidates) {
    if (typeof candidate === "string" && candidate.trim()) {
      return candidate.trim();
    }
  }
  return null;
}

function normalizePort(value) {
  const port = Number(value);
  if (!Number.isInteger(port) || port <= 0 || port > 65535) {
    return null;
  }
  return port;
}

function embeddedServerCanBeReused(status) {
  const server = normalizeEmbeddedServer(status);
  if (!server?.running) {
    return false;
  }
  if (server.error) {
    return false;
  }
  const expectedProtocol = Number(status?.protocol_version);
  const actualProtocol = Number(server?.protocol_version);
  const protocolMatches = Number.isFinite(expectedProtocol)
    && Number.isFinite(actualProtocol)
    && expectedProtocol === actualProtocol;
  return protocolMatches && Boolean(status?.auth_token_valid);
}

function embeddedServerLooksStale(status) {
  const server = normalizeEmbeddedServer(status);
  if (!server?.running) {
    return false;
  }
  const expectedProtocol = Number(status?.protocol_version);
  const actualProtocol = Number(server?.protocol_version);
  const protocolKnown = Number.isFinite(expectedProtocol) && Number.isFinite(actualProtocol);
  const protocolMismatch = protocolKnown && expectedProtocol !== actualProtocol;
  const authInvalid = status?.auth_token_valid === false;
  const restartableError = EMBEDDED_RESTART_ERROR_CODES.has(embeddedStatusErrorCode(status));
  return protocolMismatch || authInvalid || restartableError;
}

function embeddedServerSummary(status) {
  const server = normalizeEmbeddedServer(status) ?? {};
  return [
    `host=${server.host ?? "unknown"}`,
    `port=${server.port ?? "unknown"}`,
    `server_protocol=${server.protocol_version ?? "unknown"}`,
    `script_protocol=${status?.protocol_version ?? "unknown"}`,
    `auth_valid=${Boolean(status?.auth_token_valid)}`,
    `server_error_code=${embeddedStatusErrorCode(status) ?? "none"}`,
    `server_error=${server.error ?? "none"}`,
  ].join(" ");
}

function embeddedRuntimeEnvForServer({ host = null, port = null } = {}) {
  const env = {};
  const normalizedPort = normalizePort(port);
  if (normalizedPort) {
    env.DAVINCI_RESOLVE_SDK_EMBEDDED_PORT = String(normalizedPort);
  }
  if (typeof host === "string" && host.trim()) {
    env.DAVINCI_RESOLVE_SDK_EMBEDDED_HOST = host.trim();
  }
  return env;
}

async function timeWaitCountForPort(port) {
  if (process.platform !== "darwin") {
    return 0;
  }
  try {
    const { stdout } = await execFileAsync("netstat", ["-anp", "tcp"], {
      encoding: "utf8",
      timeout: 2500,
      shell: false,
      maxBuffer: 4 * 1024 * 1024,
    });
    const portPattern = new RegExp(`(^|\\s)127\\.0\\.0\\.1\\.${port}(\\s|$)`);
    return stdout
      .split("\n")
      .filter((line) => line.includes("TIME_WAIT") && portPattern.test(line))
      .length;
  } catch {
    return 0;
  }
}

async function selectEmbeddedServerEnv(currentEnv = process.env) {
  const configuredPort = normalizePort(currentEnv.DAVINCI_RESOLVE_SDK_EMBEDDED_PORT);
  if (configuredPort) {
    return {
      env: { DAVINCI_RESOLVE_SDK_EMBEDDED_PORT: String(configuredPort) },
      port: configuredPort,
      fallback: false,
      reason: "configured",
    };
  }
  const defaultTimeWaitCount = await timeWaitCountForPort(EMBEDDED_DEFAULT_PORT);
  if (defaultTimeWaitCount < EMBEDDED_TIME_WAIT_FALLBACK_THRESHOLD) {
    return {
      env: {},
      port: EMBEDDED_DEFAULT_PORT,
      fallback: false,
      reason: "default",
      time_wait_count: defaultTimeWaitCount,
    };
  }
  for (const port of EMBEDDED_FALLBACK_PORTS) {
    const [owners, timeWaitCount] = await Promise.all([
      listeningPidsForPort(port),
      timeWaitCountForPort(port),
    ]);
    if (owners.length === 0 && timeWaitCount < EMBEDDED_TIME_WAIT_FALLBACK_THRESHOLD) {
      return {
        env: { DAVINCI_RESOLVE_SDK_EMBEDDED_PORT: String(port) },
        port,
        fallback: true,
        reason: "default_port_time_wait_saturated",
        time_wait_count: defaultTimeWaitCount,
      };
    }
  }
  return {
    env: {},
    port: EMBEDDED_DEFAULT_PORT,
    fallback: false,
    reason: "fallback_unavailable",
    time_wait_count: defaultTimeWaitCount,
  };
}

async function reclaimStaleEmbeddedServer(status) {
  const server = normalizeEmbeddedServer(status);
  const port = normalizePort(server?.port);
  if (!port || !embeddedServerLooksStale(status)) {
    return { reclaimed: false, reason: "not_stale" };
  }
  if (process.platform !== "darwin") {
    return { reclaimed: false, reason: "unsupported_platform" };
  }

  const pids = await listeningPidsForPort(port);
  if (pids.length === 0) {
    return { reclaimed: true, pids: [] };
  }
  for (const pid of pids) {
    try {
      process.kill(pid, "SIGTERM");
    } catch {
      // Continue trying the remaining owners; the release wait below decides success.
    }
  }
  const released = await waitForPortRelease(port);
  return {
    reclaimed: released,
    pids,
    reason: released ? null : "port_still_in_use",
  };
}

export function buildSdkTimelineEditArgs(intent, { dryRun, timelineName, projectNativeId, timelineNativeId, sourceNativeId = null, executionRevision = null, frameRate = null, timelineStartFrame = 0 }) {
  if (intent.action === "trim") {
    const fps = Number(frameRate?.numerator) / Number(frameRate?.denominator);
    if (!Number.isFinite(fps) || fps <= 0) throw new TypeError("Trim lowering requires the exact timeline frame rate.");
    const args = [
      "edit", "trim", "--name", intent.clipName,
      "--head", String(intent.headFrames / fps),
      "--tail", String(intent.tailFrames / fps),
      "--timeline", timelineName,
      "--track", String(intent.trackIndex),
      "--start-frame", `${intent.currentRecordRange.start}f`,
      "--current-end-frame", `${intent.currentRecordRange.endExclusive}f`,
      "--linked-audio", intent.linkedAudio,
    ];
    if (dryRun) args.push("--dry-run");
    return args;
  }
  if (intent.at.value.value < timelineStartFrame) throw new TypeError("Timeline edit placement cannot precede the timeline start frame.");
  const placement = intent.placement ?? "video";
  const args = [
    "edit", intent.action, intent.source.name,
    "--at", `${intent.at.value.value - timelineStartFrame}f`,
    "--in", `${intent.sourceRange.start}f`,
    "--out", `${intent.sourceRange.endExclusive}f`,
    "--track", String(placement === "audio" ? intent.audioTrackIndex : intent.videoTrackIndex),
    "--project-id", projectNativeId,
    "--timeline-id", timelineNativeId,
  ];
  if (placement === "audio") args.push("--audio-only");
  if (sourceNativeId) args.push("--media-id", sourceNativeId);
  if (placement === "video" && intent.audioTrackIndex !== null) args.push("--audio-track", String(intent.audioTrackIndex));
  if (placement === "video") args.push(intent.linkedAudio === "include" ? "--include-linked-audio" : "--video-only");
  if (executionRevision) args.push("--revision", executionRevision);
  if (dryRun) args.push("--dry-run");
  return args;
}

export function createResolveService({
  settingsService,
  cutAgentCliAuthorizationService = null,
  incidentReporterService = null,
  resolveProcessProbe = probeResolveProcessRunning,
  resolveActivator = activateResolveAppBestEffort,
  now = Date.now,
}) {
  let statusCache = {
    value: null,
    expiresAt: 0,
  };
  const statusInFlightByCommand = new Map();
  const lightweightStatusInFlightByCommand = new Map();
  let embeddedServerProcess = null;
  let embeddedServerStarting = null;
  let embeddedRuntimeEnv = {};
  let lastKnownResolveRoute = {
    active_transport: null,
    edition: null,
    product_name: null,
  };
  let lastConfirmedConnectedStatus = null;
  let lastConfirmedConnectedAtMs = null;
  let consecutiveTransientStatusFailures = 0;
  let transientStatusFailureStartedAtMs = null;
  let lastStatusProbeState = null;
  let statusStateGeneration = 0;
  const transitionTelemetryTimestamps = {
    info: [],
    warning: [],
  };

  function statusProbeFailureDetails(status, error = null) {
    const data = status?.data?.data ?? status?.data ?? {};
    const connectionError = data?.connection_error && typeof data.connection_error === "object"
      ? data.connection_error
      : {};
    const connectionDetails = connectionError.details && typeof connectionError.details === "object"
      ? connectionError.details
      : {};
    const transports = data?.transports && typeof data.transports === "object" ? data.transports : {};
    const studio = transports.studio_external && typeof transports.studio_external === "object"
      ? transports.studio_external
      : {};
    const embedded = transports.embedded_free && typeof transports.embedded_free === "object"
      ? transports.embedded_free
      : {};
    const studioDetails = studio.error_details && typeof studio.error_details === "object"
      ? studio.error_details
      : {};
    const processRunning = connectionDetails.process_running === true || studioDetails.process_running === true
      ? true
      : connectionDetails.process_running === false || studioDetails.process_running === false
        ? false
        : null;
    return {
      errorCode: connectionError.code
        ?? studio.error_code
        ?? embedded.server_error_code
        ?? error?.cli_error_code
        ?? error?.code
        ?? null,
      processRunning,
      transportConnected: studio.connected === true || embedded.connected === true,
    };
  }

  function reportStatusProbeTransition(nextState, {
    status = null,
    error = null,
    probe,
    processRunning = null,
    generation = statusStateGeneration,
  }) {
    if (generation !== statusStateGeneration) {
      return;
    }
    const previousState = lastStatusProbeState;
    if (previousState === nextState) {
      return;
    }
    lastStatusProbeState = nextState;
    if (previousState === null) {
      return;
    }
    const details = statusProbeFailureDetails(status, error);
    const reason = details.errorCode ?? (nextState === "connected" ? "probe_recovered" : "status_disconnected");
    const severity = nextState === "disconnected" ? "warning" : "info";
    const timestamp = now();
    const cutoff = timestamp - STATUS_TRANSITION_TELEMETRY_WINDOW_MS;
    const timestamps = transitionTelemetryTimestamps[severity].filter((value) => value > cutoff);
    transitionTelemetryTimestamps[severity] = timestamps;
    const limit = severity === "warning" ? STATUS_TRANSITION_WARNING_LIMIT : STATUS_TRANSITION_INFO_LIMIT;
    if (timestamps.length >= limit) {
      return;
    }
    timestamps.push(timestamp);
    incidentReporterService?.record?.({
      category: "cutagent_cli_failure",
      source: "bridge",
      severity,
      error_code: String(reason),
      message: nextState === "connected"
        ? "DaVinci Resolve status probe recovered."
        : nextState === "degraded_connected"
          ? "DaVinci Resolve status probe degraded while the last confirmed connection was preserved."
          : "DaVinci Resolve status changed to disconnected.",
      fingerprint: ["resolve_status_transition", previousState, nextState, String(reason)].join(":"),
      metadata: {
        probe,
        previous_state: previousState,
        next_state: nextState,
        reason,
        process_running: processRunning ?? details.processRunning,
        transport_connected: details.transportConnected,
        active_transport: status?.effective_transport ?? status?.active_transport ?? lastKnownResolveRoute.active_transport,
        edition: status?.effective_edition ?? status?.edition ?? lastKnownResolveRoute.edition,
        consecutive_failures: consecutiveTransientStatusFailures,
        last_confirmed_connected_age_ms: lastConfirmedConnectedAtMs === null
          ? null
          : Math.max(0, now() - lastConfirmedConnectedAtMs),
      },
    });
  }

  function connectedStatusToPreserve() {
    return statusCache.value?.connected ? statusCache.value : lastConfirmedConnectedStatus;
  }

  function sanitizeConnectedLivenessStatus(status) {
    if (!status?.connected) {
      return null;
    }
    const transports = status.transports && typeof status.transports === "object"
      ? status.transports
      : {};
    const studio = transports.studio_external && typeof transports.studio_external === "object"
      ? transports.studio_external
      : {};
    const embedded = transports.embedded_free && typeof transports.embedded_free === "object"
      ? transports.embedded_free
      : {};
    return {
      status: "connected",
      connected: true,
      active_transport: status.active_transport ?? status.effective_transport ?? null,
      effective_transport: status.effective_transport ?? status.active_transport ?? null,
      transports: {
        studio_external: {
          available: studio.available === true,
          connected: studio.connected === true,
        },
        embedded_free: {
          installed: embedded.installed === true,
          current: embedded.current === true,
          running: embedded.running === true,
          connected: embedded.connected === true,
        },
      },
      resolve_version: status.resolve_version ?? null,
      product_name: status.product_name ?? null,
      edition: status.edition ?? status.effective_edition ?? null,
      effective_edition: status.effective_edition ?? status.edition ?? null,
      embedded_relevance: status.embedded_relevance ?? "unknown",
      primary_disconnect_reason: null,
      last_known_active_transport: status.last_known_active_transport ?? lastKnownResolveRoute.active_transport,
      last_known_edition: status.last_known_edition ?? lastKnownResolveRoute.edition,
      last_known_product_name: status.last_known_product_name ?? lastKnownResolveRoute.product_name,
      project_name: null,
      current_database: null,
      active_project: null,
      data: {},
    };
  }

  function resetTransientStatusFailures() {
    consecutiveTransientStatusFailures = 0;
    transientStatusFailureStartedAtMs = null;
  }

  function recordTransientStatusFailure() {
    const timestamp = now();
    transientStatusFailureStartedAtMs ??= timestamp;
    consecutiveTransientStatusFailures += 1;
    return {
      count: consecutiveTransientStatusFailures,
      ageMs: Math.max(0, timestamp - transientStatusFailureStartedAtMs),
    };
  }

  function transientFailureCanRemainConnected(processRunning) {
    const failure = recordTransientStatusFailure();
    const lastConfirmedConnectedAgeMs = lastConfirmedConnectedAtMs === null
      ? Number.POSITIVE_INFINITY
      : Math.max(0, now() - lastConfirmedConnectedAtMs);
    return processRunning === true
      && failure.count <= TRANSIENT_STATUS_FAILURE_LIMIT
      && failure.ageMs <= TRANSIENT_STATUS_FAILURE_TTL_MS
      && lastConfirmedConnectedAgeMs <= TRANSIENT_STATUS_FAILURE_TTL_MS;
  }

  async function readPositiveResolveLiveness(status = null) {
    const details = statusProbeFailureDetails(status);
    if (details.processRunning !== null) {
      return details.processRunning;
    }
    if (details.transportConnected) {
      return true;
    }
    try {
      return await resolveProcessProbe();
    } catch {
      return null;
    }
  }

  async function preserveConnectedStatusAcrossTransientProbe(
    error,
    currentDatabase,
    fallbackMessage,
    probe,
    generation,
  ) {
    const cached = connectedStatusToPreserve();
    const transient = error?.code === "CLI_PROTOCOL_VIOLATION"
      || error?.code === "CUTAGENT_CLI_TIMEOUT"
      || !error?.cli_error_code;
    const processRunning = transient && cached?.connected
      ? await readPositiveResolveLiveness()
      : null;
    if (generation !== statusStateGeneration) {
      return connectedStatusToPreserve()
        ?? normalizeResolveStatusError(error, currentDatabase, fallbackMessage, lastKnownResolveRoute);
    }
    if (transient && cached?.connected && transientFailureCanRemainConnected(processRunning)) {
      reportStatusProbeTransition("degraded_connected", { error, probe, processRunning, generation });
      return cached;
    }
    if (!transient) {
      resetTransientStatusFailures();
    }
    const disconnected = normalizeResolveStatusError(error, currentDatabase, fallbackMessage, lastKnownResolveRoute);
    reportStatusProbeTransition("disconnected", { status: disconnected, error, probe, processRunning, generation });
    resetTransientStatusFailures();
    lastConfirmedConnectedStatus = null;
    lastConfirmedConnectedAtMs = null;
    return disconnected;
  }

  function markStatusProbeHealthy(status, probe, generation) {
    if (generation !== statusStateGeneration) {
      return;
    }
    resetTransientStatusFailures();
    lastConfirmedConnectedStatus = status;
    lastConfirmedConnectedAtMs = now();
    reportStatusProbeTransition("connected", { status, probe, generation });
  }

  async function preserveConnectedStatusAcrossRetryableDisconnect(status, probe, generation) {
    const cached = connectedStatusToPreserve();
    if (!cached?.connected || status?.connected) {
      return undefined;
    }
    const details = statusProbeFailureDetails(status);
    const retryable = details.processRunning === true
      || details.transportConnected
      || details.errorCode === "RESOLVE_SCRIPTING_UNAVAILABLE";
    if (!retryable) {
      return undefined;
    }
    const processRunning = await readPositiveResolveLiveness(status);
    if (generation !== statusStateGeneration) {
      return connectedStatusToPreserve();
    }
    if (!transientFailureCanRemainConnected(processRunning)) {
      return null;
    }
    reportStatusProbeTransition("degraded_connected", { status, probe, processRunning, generation });
    return cached;
  }

  async function acceptStatusProbeCandidate(
    status,
    probe,
    generation,
    { retryablePreservationChecked = false } = {},
  ) {
    if (generation !== statusStateGeneration) {
      return connectedStatusToPreserve() ?? sanitizeConnectedLivenessStatus(status) ?? status;
    }
    if (status?.connected) {
      markStatusProbeHealthy(status, probe, generation);
      return status;
    }
    if (!retryablePreservationChecked) {
      const preserved = await preserveConnectedStatusAcrossRetryableDisconnect(status, probe, generation);
      if (preserved) {
        return preserved;
      }
    }
    resetTransientStatusFailures();
    reportStatusProbeTransition("disconnected", { status, probe, generation });
    lastConfirmedConnectedStatus = null;
    lastConfirmedConnectedAtMs = null;
    return status;
  }

  function embeddedServerIsAlive() {
    return Boolean(
      embeddedServerProcess
      && embeddedServerProcess.exitCode === null
      && embeddedServerProcess.signalCode === null
      && !embeddedServerProcess.killed,
    );
  }

  function appendLimited(buffer, chunk) {
    const next = `${buffer}${chunk?.toString?.() ?? ""}`;
    return next.length > 4000 ? next.slice(-4000) : next;
  }

  function invalidateStatusCache() {
    const livenessStatus = sanitizeConnectedLivenessStatus(connectedStatusToPreserve());
    lastConfirmedConnectedStatus = livenessStatus;
    resetTransientStatusFailures();
    statusStateGeneration += 1;
    statusCache = {
      value: null,
      expiresAt: 0,
    };
  }

  function rememberResolveRoute(status) {
    if (!status?.connected) {
      return;
    }
    const next = normalizeLastKnownResolveRoute({
      active_transport: status.effective_transport ?? status.active_transport,
      edition: status.effective_edition ?? status.edition,
      product_name: status.product_name,
    });
    if (next.active_transport || next.edition || next.product_name) {
      lastKnownResolveRoute = next;
    }
  }

  function cacheResolveStatus(status, generation) {
    if (generation !== statusStateGeneration) {
      return statusCache.value
        ?? connectedStatusToPreserve()
        ?? sanitizeConnectedLivenessStatus(status)
        ?? status;
    }
    rememberResolveRoute(status);
    const cachedStatus = {
      ...status,
      last_known_active_transport: lastKnownResolveRoute.active_transport,
      last_known_edition: lastKnownResolveRoute.edition,
      last_known_product_name: lastKnownResolveRoute.product_name,
    };
    statusCache = {
      value: cachedStatus,
      expiresAt: Date.now() + getStatusCacheMs(),
    };
    return cachedStatus;
  }

  function getRuntimePreferences() {
    return settingsService.getAppSettings().non_secret_runtime_preferences;
  }

  function getTimeoutMs() {
    return Math.max(getRuntimePreferences().cutagent_cli_timeout_seconds, 5) * 1000;
  }

  function getStatusProbeTimeoutMs() {
    const timeoutMs = getTimeoutMs();
    if (process.platform === "win32") {
      // Windows Python console launchers spawn a child python.exe, and DaVinci Resolve
      // Free status may also probe the embedded socket route. The old 8s cap
      // routinely timed out the parent before the real probe completed.
      return Math.max(timeoutMs, 20000);
    }
    return Math.min(timeoutMs, 8000);
  }

  function statusProbeKey(options = {}) {
    return typeof options.cutAgentCliCommand === "string" && options.cutAgentCliCommand
      ? `attested:${options.cutAgentCliCommand}`
      : "ambient";
  }

  function parseJson(args, timeoutMs, options = {}) {
    return parseResolveJson(args, timeoutMs, {
      cutAgentCliAuthorizationService,
      accessToken: options.accessToken ?? null,
      session: options.session ?? null,
      skipCutAgentCliAuthorization: options.skipCutAgentCliAuthorization === true,
      cutAgentCliCommand: options.cutAgentCliCommand ?? null,
      cwd: options.cwd ?? null,
      carrier: options.carrier ?? "cli",
      policyContext: options.policyContext ?? null,
      refreshProtectedTargets: options.refreshProtectedTargets ?? null,
      signal: options.signal ?? null,
      deadlineAtMs: options.deadlineAtMs ?? null,
      onAuthorization: options.onAuthorization ?? null,
      issueBrokerEnvironment: options.issueBrokerEnvironment ?? null,
      onSpawnAttempt: options.onSpawnAttempt ?? null,
      extraEnv: {
        DAVINCI_RESOLVE_SDK_EMBEDDED_AUTH_PATH: getEmbeddedAuthPath(),
        ...embeddedRuntimeEnv,
        ...(options.extraEnv ?? {}),
      },
    });
  }

  function reportCutAgentCliProbeFailure(args, error, context = {}, generation = statusStateGeneration) {
    if (generation !== statusStateGeneration) {
      return;
    }
    const errorCode = error?.cli_error_code || error?.code || "cutagent_cli_probe_failed";
    if (errorCode === "CUTAGENT_CLI_TIMEOUT" || errorCode === "CLI_PROTOCOL_VIOLATION") {
      // Timeout/non-JSON status failures are reported by the bounded transition
      // telemetry above. Avoid one incident per watcher poll while DaVinci
      // Resolve is busy.
      return;
    }
    if (lastStatusProbeState !== null) {
      // Once a baseline exists, the transition reporter owns status-probe
      // telemetry. This keeps repeated failures bounded to state changes.
      return;
    }
    if (
      errorCode === "EMBEDDED_BRIDGE_NOT_RUNNING"
      && lastKnownResolveRoute.active_transport === STUDIO_EXTERNAL_TRANSPORT
    ) {
      return;
    }
    const message = error instanceof Error && error.message.trim()
      ? error.message.trim()
      : "CutAgent CLI probe failed.";
    incidentReporterService?.record?.({
      category: "cutagent_cli_failure",
      source: "bridge",
      severity: "warning",
      error_code: String(errorCode),
      message,
      fingerprint: ["cutagent_cli_probe", args.join(" "), String(errorCode), message.toLowerCase().slice(0, 100)].join(":"),
      metadata: {
        command_path: args.join(" "),
        context,
        cli_error_code: error?.cli_error_code ?? null,
        cli_error_details: error?.cli_error_details ?? null,
        cli_meta: error?.cli_meta ?? null,
        exit_code: error?.exit_code ?? null,
      },
    });
  }

  function getStatusCacheMs() {
    const pollMs = Number(getRuntimePreferences().status_poll_interval_seconds) * 1000;
    if (!Number.isFinite(pollMs) || pollMs <= 0) {
      return 5000;
    }
    return Math.max(2000, Math.min(pollMs, 60_000));
  }

  async function readCurrentDatabase(options = {}) {
    try {
      const parsed = requireCutAgentCliSuccess(
        await parseJson(["project", "db", "current"], Math.min(getTimeoutMs(), 8000), options),
        "Failed to read the current DaVinci Resolve database.",
      );
      return normalizeDatabaseDetails(parsed?.data ?? parsed);
    } catch (error) {
      if (error?.code === "CLI_PROTOCOL_VIOLATION") {
        throw error;
      }
      if (SOFT_DATABASE_ERROR_CODES.has(error?.cli_error_code)) {
        return {
          database_type: null,
          database_name: null,
        };
      }
      if (error?.cli_error_code) {
        throw error;
      }
      return {
        database_type: null,
        database_name: null,
      };
    }
  }

  async function getCurrentDatabase(options = {}) {
    if (options.session?.resolve_runtime?.mode === "parallel_gui_beta") {
      return readCurrentDatabase(options);
    }
    if (!options.forceRefresh && statusCache.value && Date.now() < statusCache.expiresAt) {
      return statusCache.value.current_database;
    }
    return readCurrentDatabase(options);
  }

  async function loadResolveStatus(options = {}, generation) {
    let currentDatabase = {
      database_type: null,
      database_name: null,
    };
    const normalizeWithConnectedDatabase = async (data) => {
      const lightweight = normalizeResolveStatusPayload(data, null, lastKnownResolveRoute);
      if (!lightweight.connected) {
        return lightweight;
      }
      try {
        currentDatabase = await readCurrentDatabase(options);
      } catch (error) {
        if (error?.code !== "CLI_PROTOCOL_VIOLATION" && !error?.cli_error_code) {
          throw error;
        }
      }
      return normalizeResolveStatusPayload(data, currentDatabase, lastKnownResolveRoute);
    };

    try {
      const data = requireCutAgentCliSuccess(
        await parseJson(["status"], getStatusProbeTimeoutMs(), options),
        "Failed to query DaVinci Resolve status.",
      );
      const normalized = await normalizeWithConnectedDatabase(data);
      const preserved = await preserveConnectedStatusAcrossRetryableDisconnect(
        normalized,
        "resolve_status",
        generation,
      );
      if (preserved !== undefined) {
        return preserved ?? await acceptStatusProbeCandidate(normalized, "resolve_status", generation, {
          retryablePreservationChecked: true,
        });
      }
      if (generation !== statusStateGeneration) {
        return connectedStatusToPreserve() ?? sanitizeConnectedLivenessStatus(normalized) ?? normalized;
      }
      if (shouldStartEmbeddedServer(normalized) && !options.cutAgentCliCommand) {
        await api.startEmbeddedServer(options);
        const refreshed = requireCutAgentCliSuccess(
          await parseJson(["status"], getStatusProbeTimeoutMs(), options),
          "Failed to query DaVinci Resolve status.",
        );
        const refreshedStatus = await normalizeWithConnectedDatabase(refreshed);
        return await acceptStatusProbeCandidate(refreshedStatus, "resolve_status", generation);
      }
      return await acceptStatusProbeCandidate(normalized, "resolve_status", generation);
    } catch (error) {
      reportCutAgentCliProbeFailure(["status"], error, { probe: "resolve_status" }, generation);
      return await preserveConnectedStatusAcrossTransientProbe(
        error,
        currentDatabase,
        error?.code === "CLI_PROTOCOL_VIOLATION"
          ? "DaVinci Resolve status response was invalid."
          : "Failed to query DaVinci Resolve status.",
        "resolve_status",
        generation,
      );
    }
  }

  async function loadLightweightResolveStatus(options = {}, generation) {
    const currentDatabase = statusCache.value?.current_database ?? null;
    try {
      const data = requireCutAgentCliSuccess(
        await parseJson(["status"], getStatusProbeTimeoutMs(), options),
        "Failed to query DaVinci Resolve status.",
      );
      const normalized = normalizeResolveStatusPayload(data, currentDatabase, lastKnownResolveRoute);
      const preserved = await preserveConnectedStatusAcrossRetryableDisconnect(
        normalized,
        "lightweight_resolve_status",
        generation,
      );
      if (preserved !== undefined) {
        return preserved ?? await acceptStatusProbeCandidate(normalized, "lightweight_resolve_status", generation, {
          retryablePreservationChecked: true,
        });
      }
      if (generation !== statusStateGeneration) {
        return connectedStatusToPreserve() ?? sanitizeConnectedLivenessStatus(normalized) ?? normalized;
      }
      if (shouldStartEmbeddedServer(normalized) && !options.cutAgentCliCommand) {
        await api.startEmbeddedServer(options);
        const refreshed = requireCutAgentCliSuccess(
          await parseJson(["status"], getStatusProbeTimeoutMs(), options),
          "Failed to query DaVinci Resolve status.",
        );
        const refreshedStatus = normalizeResolveStatusPayload(refreshed, currentDatabase, lastKnownResolveRoute);
        return await acceptStatusProbeCandidate(refreshedStatus, "lightweight_resolve_status", generation);
      }
      return await acceptStatusProbeCandidate(normalized, "lightweight_resolve_status", generation);
    } catch (error) {
      reportCutAgentCliProbeFailure(["status"], error, { probe: "lightweight_resolve_status" }, generation);
      return await preserveConnectedStatusAcrossTransientProbe(
        error,
        currentDatabase,
        "Failed to query DaVinci Resolve status.",
        "lightweight_resolve_status",
        generation,
      );
    }
  }

  function shouldStartEmbeddedServer(status) {
    if (!status || status.connected) {
      return false;
    }
    const transports = status.transports ?? {};
    const studio = transports.studio_external ?? {};
    const embedded = transports.embedded_free ?? {};
    const embeddedNeedsRestart = embedded.running === true
      && embedded.connected !== true
      && embeddedServerLooksStale(embedded);
    const embeddedAutoStartAllowed = status.embedded_relevance === "required"
      || (
        status.embedded_relevance === "unknown"
        && status.effective_transport !== STUDIO_EXTERNAL_TRANSPORT
        && status.effective_edition !== "studio"
      );
    return Boolean(
      embeddedAutoStartAllowed
      && studio.connected !== true
      && embedded.installed === true
      && (embedded.running !== true || embeddedNeedsRestart),
    );
  }

  async function getActiveProject(options = {}) {
    const status = await api.getStatus(options);
    return status.active_project ?? null;
  }

  async function getTargetedSessionStatus(options = {}, { lightweight = false } = {}) {
    let currentDatabase = null;
    if (!lightweight) {
      currentDatabase = await readCurrentDatabase(options).catch(() => null);
    }
    const data = requireCutAgentCliSuccess(
      await parseJson(["status"], getStatusProbeTimeoutMs(), options),
      "Failed to query the isolated DaVinci Resolve status.",
    );
    return normalizeResolveStatusPayload(data, currentDatabase, {});
  }

  async function listProjects(options = {}) {
    let currentDatabase;
    try {
      currentDatabase = await getCurrentDatabase(options);
    } catch {
      currentDatabase = {
        database_type: null,
        database_name: null,
      };
    }
    const listPayload = requireCutAgentCliSuccess(
      await parseJson(["project", "list"], getTimeoutMs(), options),
      "Failed to list DaVinci Resolve projects.",
    );
    return normalizeProjectListRows(extractProjectRows(listPayload), currentDatabase, { strict: options.strictSdkInventory === true });
  }

  async function readSdkLiveInspection(operation, options = {}) {
    if (!new Set([
      "project.context",
      "project.folder_context",
      "project.library_context",
      "project.current",
      "timeline.current",
      "timeline.list",
      "timeline.retime",
      "timeline.snapshot",
      "fusion.compositions",
      "mediaPool.page",
      "color.current",
      "multicam.inspect",
      "managed.protected",
      "storage.mattes",
      "render.discovery",
      "render.presets",
      "render.settings",
      "render.queue",
      "render.job_status",
    ]).has(operation)) {
      throw new TypeError("Unsupported SDK read-only inspection operation.");
    }
    const deadlineAtMs = Number(options.deadlineAtMs);
    if (!Number.isSafeInteger(deadlineAtMs) || deadlineAtMs <= Date.now()) {
      throw new DOMException("The SDK inspection deadline expired.", "TimeoutError");
    }
    const args = ["timeline", "sdk-live-inspect", operation, "--deadline-at-ms", String(deadlineAtMs)];
    if (operation === "color.current") {
      const layerIndex = options.readRequest?.nodeStackLayerIndex;
      if (!Number.isSafeInteger(layerIndex) || layerIndex < 1 || layerIndex > 4096) {
        throw new TypeError("Color inspection requires an explicit bounded node-stack layer index.");
      }
      args.push("--node-stack-layer", String(layerIndex));
    }
    if (operation === "timeline.retime") {
      const privateTargets = options.privateTargets;
      if (!Array.isArray(privateTargets) || privateTargets.length < 1 || privateTargets.length > 514
        || privateTargets.some((target) => !target || typeof target !== "object" || typeof target.id !== "string" || !target.id)) {
        throw new TypeError("SDK retime inspection requires exact private timeline-item targets.");
      }
      args.push("--retime-targets-json", JSON.stringify(privateTargets));
    } else if (operation === "mediaPool.page") {
      const request = options.readRequest;
      if (!request || request.operation !== "mediaPool.page") {
        throw new TypeError("Media Pool inspection requires a validated semantic read request.");
      }
      args.push("--offset", String(request.offset), "--page-size", String(request.pageSize));
      if (request.search) args.push("--search-json", JSON.stringify(request.search));
    } else if (operation === "multicam.inspect") {
      const request = options.readRequest;
      if (!request || request.operation !== "multicam.inspect") {
        throw new TypeError("Multicam inspection requires a validated semantic read request.");
      }
      args.push("--multicam-name", request.multicamName);
    } else if (operation === "storage.mattes") {
      const nativeIds = options.readRequest?.nativeIds ?? [];
      if (!Array.isArray(nativeIds) || nativeIds.some((value) => typeof value !== "string" || !value)) {
        throw new TypeError("Storage matte inspection requires exact native Media Pool identities.");
      }
      args.push("--managed-affected-json", JSON.stringify(nativeIds));
    } else if (operation === "managed.protected") {
      const request = options.readRequest;
      if (!request || request.operation !== "managed.protected" || !Array.isArray(request.affectedNativeItemIds)) {
        throw new TypeError("Managed protected-state inspection requires exact native affected identities.");
      }
      args.push("--managed-affected-json", JSON.stringify(request.affectedNativeItemIds));
      args.push("--managed-retained-database-json", JSON.stringify(request.retainedDatabaseNativeItemIds ?? request.affectedNativeItemIds));
    }
    let inspectionOptions = operation === "mediaPool.page"
      ? { ...options, extraEnv: { ...(options.extraEnv ?? {}), CUTAGENT_SDK_MEDIA_POOL_PRIVATE_PATHS: "1" } }
      : options;
    if (operation === "fusion.compositions") {
      const request = options.readRequest;
      if (request?.operation !== operation
        || !/^timeline_f[A-Za-z0-9_-]{43}$/.test(request.timelineId ?? "")
        || !/^timeline_item_f[A-Za-z0-9_-]{43}$/.test(request.timelineItemId ?? "")) {
        throw new TypeError("Fusion inspection requires exact public timeline and timeline-item identities.");
      }
      inspectionOptions = { ...options, extraEnv: { ...(options.extraEnv ?? {}),
        CUTAGENT_SDK_FUSION_INSPECTION_TARGET: JSON.stringify({ timelineId: request.timelineId, timelineItemId: request.timelineItemId }),
      } };
    }
    const inspectionPayload = await parseJson(
      args,
      getTimeoutMs(),
      inspectionOptions,
    );
    const inspectionError = bridgeCliErrorFromPayload(inspectionPayload, {
      fallbackMessage: "Failed to inspect the current DaVinci Resolve live state.",
    });
    if (inspectionError?.cli_error_code === "SDK_LIVE_INSPECTION_TIMEOUT") {
      throw new DOMException("The SDK inspection deadline expired.", "TimeoutError");
    }
    if (inspectionError) throw inspectionError;
    return inspectionPayload?.data ?? inspectionPayload;
  }

  async function executeSdkMarkerMutation(action, input, options = {}) {
    const command = action === "create" ? "add" : action;
    const args = ["timeline", "marker", command];
    if (action === "create") args.push(`${input.recordFrame}f`);
    else args.push("--frame", String(input.targetFrame));
    if (action !== "delete") {
      if (action === "update" && input.recordFrame !== input.targetFrame) args.push("--position", `${input.recordFrame}f`);
      args.push("--color", input.color, "--name", input.name, "--note", input.note, "--duration", String(input.durationFrames));
    }
    const payload = await parseJson(args, getTimeoutMs(), {
      ...options,
      carrier: "sdk",
      extraEnv: { ...(options.extraEnv ?? {}), CUTAGENT_SDK_MARKER_GUARD: options.mutationGuard },
    });
    const markerError = bridgeCliErrorFromPayload(payload, { fallbackMessage: "The semantic marker mutation failed." });
    if (markerError) throw markerError;
    return payload?.data ?? payload;
  }

  async function executeSdkProjectCreate(input, options = {}) {
    const args = ["project", "create", input.name];
    if (input.mediaLocation !== undefined && input.mediaLocation !== null) {
      args.push("--media-location", input.mediaLocation);
    }
    const payload = await parseJson(args, getTimeoutMs(), {
      ...options,
      carrier: "sdk",
      extraEnv: { ...(options.extraEnv ?? {}), CUTAGENT_SDK_PROJECT_GUARD: options.mutationGuard },
    });
    const projectError = bridgeCliErrorFromPayload(payload, { fallbackMessage: "The semantic project creation failed." });
    if (projectError) throw projectError;
    return payload?.data ?? payload;
  }

  async function readSdkProjectSettings(options = {}) {
    const payload = await parseJson(["project", "settings"], getTimeoutMs(), {
      ...options,
      carrier: "sdk",
    });
    const projectError = bridgeCliErrorFromPayload(payload, { fallbackMessage: "Project settings readback failed." });
    if (projectError) throw projectError;
    return payload?.data ?? payload;
  }

  async function executeSdkMediaImport(pathValue, options = {}) {
    const payload = await parseJson(["media", "import", pathValue], getTimeoutMs(), {
      ...options,
      carrier: "sdk",
      extraEnv: {
        ...(options.extraEnv ?? {}),
        CUTAGENT_SDK_MEDIA_POOL_GUARD: options.mutationGuard,
        CUTAGENT_SDK_MEDIA_IMPORT_ROOT: "1",
      },
    });
    const mediaError = bridgeCliErrorFromPayload(payload, { fallbackMessage: "The semantic Media Pool import failed." });
    if (mediaError) throw mediaError;
    return payload?.data ?? payload;
  }

  async function executeSdkColorMutation(kind, input, options = {}) {
    const nodeStackLayerIndex = input.nodeStackLayerIndex ?? 1;
    if (!Number.isSafeInteger(nodeStackLayerIndex) || nodeStackLayerIndex < 1 || nodeStackLayerIndex > 4096) {
      throw new TypeError("Color mutation requires a bounded node-stack layer index.");
    }
    const args = ["color"];
    if (kind === "primary_set") {
      const timelineStartFrame = options.timelineStartFrame;
      if (!Number.isSafeInteger(timelineStartFrame) || timelineStartFrame < 0) {
        throw new TypeError("Color primary mutation requires a non-negative integer timeline start frame.");
      }
      if (!Number.isSafeInteger(input.recordFrame) || input.recordFrame < timelineStartFrame) {
        throw new TypeError("Color primary mutation record frame must be an absolute frame at or after the timeline start.");
      }
      const relativeRecordFrame = input.recordFrame - timelineStartFrame;
      args.push("page", "primary-set", "--track", String(input.trackIndex), "--at", `${relativeRecordFrame}f`, "--node", String(input.nodeIndex));
      const flags = { contrast: "--contrast", pivot: "--pivot", temperature: "--temperature", tint: "--tint", hue: "--hue", colorBoost: "--color-boost", midtoneDetail: "--mid-detail", shadows: "--shadows", highlights: "--highlights" };
      for (const [key, flag] of Object.entries(flags)) if (input.correction[key] !== undefined) args.push(flag, String(input.correction[key]));
    } else if (kind === "node_add") {
      args.push("page", "node-add", "--kind", input.topology, "--position", "after", "--node", String(input.afterNodeIndex));
    } else if (kind === "node_label_set") {
      args.push("node", "label-set", String(input.nodeIndex), input.label);
      if (nodeStackLayerIndex !== 1) args.push("--node-stack-layer", String(nodeStackLayerIndex));
    } else if (kind === "grade_apply") {
      if (!options.assetPath) throw new TypeError("Color grade apply requires a privately resolved Color Library asset.");
      const mode = { none: "0", source_timecode: "1", start_frame: "2" }[input.alignment];
      args.push("grade-apply", options.assetPath, "--mode", mode, "--setup-only");
    } else if (kind === "effect_add") {
      const effect = { gaussian_blur: "box-blur", sharpen: "sharpen", film_grain: "film-grain" }[input.effect];
      args.push("page", "resolvefx-add", "--node", String(input.nodeIndex), "--fx", effect);
    } else {
      throw new TypeError("Unsupported semantic Color mutation.");
    }
    const payload = await parseJson(args, getTimeoutMs(), {
      ...options,
      carrier: "sdk",
      extraEnv: {
        ...(options.extraEnv ?? {}),
        CUTAGENT_SDK_COLOR_GUARD: options.mutationGuard,
        CUTAGENT_SDK_COLOR_NODE_STACK_LAYER_INDEX: String(nodeStackLayerIndex),
      },
    });
    const colorError = bridgeCliErrorFromPayload(payload, { fallbackMessage: "The semantic Color mutation failed." });
    if (colorError) throw colorError;
    return payload?.data ?? payload;
  }

  async function readSdkCapability(capabilityId, options = {}) {
    const payload = await parseJson(["capabilities", capabilityId], getTimeoutMs(), options);
    const capabilityError = bridgeCliErrorFromPayload(payload, { fallbackMessage: "Failed to inspect the required CutAgent capability." });
    if (capabilityError) throw capabilityError;
    const data = payload?.data ?? payload;
    const rows = Array.isArray(data?.capabilities) ? data.capabilities : Array.isArray(data) ? data : [];
    const capability = (data?.feature_id === capabilityId ? data : null)
      ?? data?.feature_graph?.[capabilityId]
      ?? rows.find((row) => row?.id === capabilityId)
      ?? (data?.capabilities && !Array.isArray(data.capabilities) ? data.capabilities[capabilityId] : null)
      ?? data?.[capabilityId]
      ?? null;
    const status = capability?.status ?? capability?.availability ?? capability?.supported;
    return {
      id: capabilityId,
      supported: status === "supported" || status === "available" || status === true,
      reason: capability?.reason_code ?? capability?.reason ?? null,
    };
  }

  async function previewSdkTimelineEdit(intent, context, options = {}) {
    const payload = await parseJson(buildSdkTimelineEditArgs(intent, { ...context, dryRun: true }), getTimeoutMs(), {
      ...options,
      carrier: "sdk",
      policyContext: { semanticReadOnlyPreview: "timeline.edit.v1" },
    });
    const editError = bridgeCliErrorFromPayload(payload, { fallbackMessage: "The semantic timeline edit preview failed." });
    if (editError) throw editError;
    return payload?.data ?? payload;
  }

  async function executeSdkTimelineEdit(intent, context, options = {}) {
    const payload = await parseJson(buildSdkTimelineEditArgs(intent, { ...context, dryRun: false }), getTimeoutMs(), {
      ...options,
      carrier: "sdk",
      extraEnv: { ...(options.extraEnv ?? {}), CUTAGENT_SDK_MARKER_GUARD: options.mutationGuard },
    });
    const editError = bridgeCliErrorFromPayload(payload, { fallbackMessage: "The semantic timeline edit failed." });
    if (editError) throw editError;
    return payload?.data ?? payload;
  }

  async function executeSdkMulticamMutation(action, input, prepared, options = {}) {
    const sourceRows = prepared.sources?.map((source) => ({
      angle: source.angleLabel,
      clip_name: source.name,
      source_path: source.sourcePath,
    })) ?? [];
    let args;
    if (action === "create") {
      const timelineName = input.timelineName ?? `${input.name} Timeline`;
      const angleOrder = [...new Set(sourceRows.map((source) => source.angle))];
      const job = {
        sources: sourceRows,
        timeline_settings: { timeline_name: timelineName, replace_active_timeline: false },
        multicam_settings: {
          timeline_name: timelineName, multicam_name: input.name, sync_mode: input.syncMode,
          sync_engine: "cutagent", source_layout: "contiguous", source_item_representation: "distinct_timeline_items",
          angle_order: angleOrder, angle_names: Object.fromEntries(angleOrder.map((angle) => [angle, angle])),
          default_video_angle: angleOrder[0], default_audio_angle: angleOrder[0],
        },
      };
      args = ["multicam", input.createTimeline ? "timeline-create" : "create", "--job-json", JSON.stringify(job)];
    } else if (action === "switch") {
      const rate = prepared.timeline.frameRate.numerator / prepared.timeline.frameRate.denominator;
      const startFrame = prepared.timeline.start.value.value;
      const byId = new Map(prepared.multicam.value.angles.map((angle) => [angle.id, angle.label]));
      if (input.switches[0]?.atRecordFrame !== startFrame) {
        const error = new Error("The first multicam switch point must equal the exact timeline start so preceding program material is never silently replaced.");
        error.cli_error_code = "CAPABILITY_UNAVAILABLE";
        throw error;
      }
      const segments = input.switches.map((point, index) => {
        const end = input.switches[index + 1]?.atRecordFrame ?? prepared.endFrame;
        const angle = byId.get(point.angleId);
        if (!angle || end <= point.atRecordFrame || end > prepared.endFrame) {
          const error = new Error("The multicam switch plan no longer fits the exact inspected timeline and angle revision.");
          error.cli_error_code = "STALE_REVISION";
          throw error;
        }
        const startMs = Math.round((point.atRecordFrame - startFrame) * 1000 / rate);
        const endMs = Math.round((end - startFrame) * 1000 / rate);
        return { angle, start_ms: startMs, end_ms: endMs, output_start_ms: startMs, output_end_ms: endMs };
      });
      const angleOrder = [...new Set(sourceRows.map((source) => source.angle))];
      const job = {
        sources: sourceRows,
        timeline_settings: { timeline_name: prepared.timelineName, replace_active_timeline: true },
        multicam_settings: { timeline_name: prepared.timelineName, multicam_name: prepared.multicam.name,
          angle_order: angleOrder, default_video_angle: angleOrder[0], default_audio_angle: angleOrder[0] },
        segments,
      };
      args = ["multicam", "switch", "--multicam-name", prepared.multicam.name,
        "--job-json", JSON.stringify(job), "--replace-active-timeline"];
      const scope = input.switches[0]?.scope;
      if (scope === "video") args.push("--video-only");
      if (scope === "audio") args.push("--audio-only");
    } else if (action === "flatten") {
      args = ["multicam", "flatten", "--timeline", prepared.timelineName, "--scope", input.scope,
        "--grade-policy", input.gradePolicy, "--force"];
    } else {
      throw new TypeError("Unsupported semantic multicam mutation.");
    }
    const payload = await parseJson(args, getTimeoutMs(), {
      ...options,
      carrier: "sdk",
      extraEnv: {
        ...(options.extraEnv ?? {}),
        ...(prepared.timelineMutationGuard ? { CUTAGENT_SDK_TIMELINE_GUARD: prepared.timelineMutationGuard } : {}),
        ...(prepared.timelineNativeId ? { CUTAGENT_SDK_EXPECTED_TIMELINE_NATIVE_ID: prepared.timelineNativeId } : {}),
        ...(prepared.multicam?.nativeId ? { CUTAGENT_SDK_EXPECTED_MULTICAM_NATIVE_ID: prepared.multicam.nativeId } : {}),
        ...(action === "create" && prepared.sources?.[0]?.poolDigest
          ? { CUTAGENT_SDK_MULTICAM_CREATE_GUARD: prepared.sources[0].poolDigest }
          : {}),
      },
    });
    const operationError = bridgeCliErrorFromPayload(payload, { fallbackMessage: "The semantic multicam mutation failed." });
    if (operationError) throw operationError;
    return payload?.data ?? payload;
  }

  async function executeSdkMulticamMatchFrame(input, prepared, options = {}) {
    if (!prepared?.multicam?.nativeId || !prepared?.multicam?.name
      || !Number.isSafeInteger(prepared.angleNumber) || prepared.angleNumber < 1) {
      throw new TypeError("Multicam match-frame requires one exact private multicam and angle binding.");
    }
    const payload = await parseJson([
      "multicam", "match-frame",
      "--multicam-name", prepared.multicam.name,
      "--media-id", prepared.multicam.nativeId,
      "--angle", String(prepared.angleNumber),
      "--record-frame", String(input.recordFrame),
      "--media-type", "video",
    ], getTimeoutMs(), { ...options, carrier: "sdk" });
    const readError = bridgeCliErrorFromPayload(payload, { fallbackMessage: "The exact multicam frame read failed." });
    if (readError) throw readError;
    return payload?.data ?? payload;
  }

  async function executeSdkMulticamResidual(action, input, prepared, options = {}) {
    const target = prepared?.multicam;
    const targetArgs = target ? ["--multicam-name", target.name, "--media-id", target.nativeId] : [];
    const scope = (value) => value === "both" ? "both" : value;
    const triplet = (value) => value?.join(" ");
    let args;
    if (action === "settings") args = ["multicam", "settings", "--job-json", JSON.stringify({
      sources: prepared.sources.map((source) => ({ angle: source.angleLabel, clip_name: source.name, source_path: source.sourcePath })),
      timeline_settings: { timeline_name: input.timelineName },
      multicam_settings: { multicam_name: input.name, sync_mode: input.syncMode, source_layout: input.sourceLayout,
        audio_mode: input.audioMode, full_clip_extents: input.fullClipExtents },
    })];
    else if (action === "angle.remove") args = ["multicam", "angle", "remove", ...targetArgs, "--angle", String(prepared.angleNumber), "--force"];
    else if (action === "angle.rename") args = ["multicam", "angle", "rename", ...targetArgs, "--angle", String(prepared.angleNumber), "--name", input.name, "--media-type", scope(input.scope)];
    else if (action === "angle.set_enabled") args = ["multicam", "angle", "set-enabled", ...targetArgs, "--angle", String(prepared.angleNumber), input.enabled ? "--enabled" : "--disabled", "--media-type", scope(input.scope)];
    else if (action === "source.move") args = ["multicam", "source", "move", ...targetArgs, "--angle", String(prepared.angleNumber), "--item-index", String(prepared.itemIndex), "--record-start-frame", String(input.recordStartFrame), "--media-type", scope(input.scope)];
    else if (action === "source.remove") args = ["multicam", "source", "remove", ...targetArgs, "--angle", String(prepared.angleNumber), "--item-index", String(prepared.itemIndex), "--media-type", scope(input.scope), "--force"];
    else if (action === "source.property_set") args = ["multicam", "source", "property-set", input.property, input.value, ...targetArgs, "--angle", String(prepared.angleNumber), "--record-frame", String(input.recordFrame), "--media-type", input.mediaType];
    else if (action === "source.grade_cdl") {
      args = ["multicam", "source", "grade-cdl", ...targetArgs, "--angle", String(prepared.angleNumber), "--record-frame", String(input.recordFrame)];
      if (input.versionName) args.push("--version-name", input.versionName);
      if (input.slope) args.push("--slope", triplet(input.slope));
      if (input.offset) args.push("--offset", triplet(input.offset));
      if (input.power) args.push("--power", triplet(input.power));
      if (input.saturation !== undefined) args.push("--sat", String(input.saturation));
    } else if (action === "source.raw_braw_set") args = ["multicam", "source", "raw-braw-set", ...targetArgs, "--angle", String(prepared.angleNumber), "--record-frame", String(input.recordFrame), "--settings-json", JSON.stringify({
      ...(input.adjustments.iso === undefined ? {} : { iso: input.adjustments.iso }),
      ...(input.adjustments.exposure === undefined ? {} : { exposure: input.adjustments.exposure }),
      ...(input.adjustments.whiteBalanceKelvin === undefined ? {} : { white_balance_kelvin: input.adjustments.whiteBalanceKelvin }),
      ...(input.adjustments.whiteBalanceTint === undefined ? {} : { white_balance_tint: input.adjustments.whiteBalanceTint }),
    })];
    else if (action === "reorder_angles") {
      const labels = new Map(target.value.angles.map((angle) => [angle.id, angle.label]));
      args = ["multicam", "reorder-angles", ...targetArgs];
      for (const angleId of input.angleIds) args.push("--angle-order", labels.get(angleId));
      args.push(input.renameTracks ? "--rename-tracks" : "--no-rename-tracks", input.includeAudio ? "--include-audio" : "--video-only", input.strict ? "--strict" : "--partial");
    } else if (action === "set_start_timecode") args = ["multicam", "set-start-timecode", ...targetArgs, "--start-timecode", input.startTimecode];
    else if (action === "strip_embedded_audio") args = ["multicam", "strip-embedded-audio", ...targetArgs, ...(input.allowMissingAudio ? ["--allow-missing-audio"] : []), "--force"];
    else if (action === "recover_timing") args = ["multicam", "recover-timing", ...targetArgs, "--source-specs-json", JSON.stringify(prepared.timingSources.map((source) => ({
      media_id: source.nativeId, path: source.sourcePath, source_start_frame: source.sourceStartFrame, duration_frames: source.durationFrames,
    }))), ...(input.applyTimeMap ? ["--apply-timemap"] : []), ...(input.applySourceStartTimecode ? ["--apply-source-start-tc"] : []), ...(input.applyMediaExtents ? ["--apply-media-extents"] : []), ...(input.verifyReopen ? ["--verify-reopen"] : [])];
    else if (action === "replace.audio" || action === "replace.video") {
      const kind = action === "replace.audio" ? "audio" : "video";
      args = ["multicam", "replace", kind, ...targetArgs];
      for (const replacement of prepared.replacementSources) {
        args.push("--angle", `${replacement.angleNumber}=${replacement.sourcePath}`);
        if (kind === "audio") args.push("--offset", `${replacement.angleNumber}=${replacement.offsetFrames}`);
        else args.push("--source-in", `${replacement.angleNumber}=${replacement.sourceStartFrame}`, "--start", `${replacement.angleNumber}=${replacement.recordStartFrame}`, "--duration", `${replacement.angleNumber}=${replacement.durationFrames}`);
      }
      if (kind === "audio") args.push("--unmapped", input.unmappedPolicy);
      if (kind === "video" && input.allowShortSource) args.push("--allow-short-source");
      args.push("--force");
    } else if (action === "convert") args = ["multicam", "convert", "--timeline", prepared.timelineName, "--media-id", prepared.timelineNativeId, "--multicam-name", input.name, "--force"];
    else if (action === "seed_timeline") args = ["multicam", "seed-timeline", ...targetArgs, "--timeline", prepared.timelineName, "--absolute-record-frame", String(input.atRecordFrame), ...(input.requireEmpty ? ["--require-empty"] : [])];
    else if (action === "smart_switch") {
      const labels = new Map(target.value.angles.map((angle) => [angle.id, angle.label]));
      args = ["multicam", "smart-switch", "--multicam-name", target.name, "--timeline", prepared.timelineName,
        "--audio-sync", input.audioSync, "--minimum-edit-duration-ms", String(input.minimumEditDurationMs),
        "--edit-change-delay-ms", String(input.editChangeDelayMs), "--wide-angle-mode", input.wideAngleMode,
        "--wide-angle-frequency", input.wideAngleFrequency, "--switch", input.scope === "linked" ? "video-and-audio" : "video-only",
        "--analysis-window-ms", String(input.analysisWindowMs), "--activity-floor-db", String(input.activityFloorDb),
        "--activity-margin-db", String(input.activityMarginDb), "--dominance-margin-db", String(input.dominanceMarginDb),
        "--max-silence-hold-ms", String(input.maxSilenceHoldMs), "--replace-active-timeline",
        input.useWideAngleForIntroOutro ? "--wide-intro-outro" : "--no-wide-intro-outro",
        input.useWideAngleForSilence ? "--wide-silence" : "--no-wide-silence",
        input.useAudioOnlyFastAnalysis ? "--audio-only-fast-analysis" : "--audio-plus-angle-metadata"];
      if (input.wideAngleId) args.push("--wide-angle", labels.get(input.wideAngleId));
      for (const source of prepared.smartVideoSources) args.push("--angle", `${source.angleLabel}=${source.sourcePath}`);
      prepared.smartAudioSources.forEach((source, index) => args.push("--audio-source", `sdk_audio_${index}=${source.sourcePath}`));
      args.push("--audio-angle-map", prepared.smartAudioSources.map((source, index) => `sdk_audio_${index}=${source.angleLabel}`).join(","));
      for (const offset of input.videoSourceOffsets) args.push("--video-source-offset", `${labels.get(offset.angleId)}=${offset.offsetFrames}`);
    } else if (action === "audio_activity.calibrate") {
      args = ["multicam", "audio-activity", "calibrate", "--audio-sync", input.audioSync, "--style", input.style, "--ranked-candidates", String(input.rankedCandidates)];
      for (const source of prepared.videoSources) args.push("--angle", `${source.angleLabel}=${source.sourcePath}`);
      for (const source of prepared.audioSources) args.push("--audio-source", `${source.mediaPoolItemId}=${source.sourcePath}`);
      args.push("--audio-angle-map", prepared.audioSources.map((source) => `${source.mediaPoolItemId}=${source.angleLabel}`).join(","));
    } else throw new TypeError(`Unsupported exact multicam action: ${action}`);
    if (args.some((value) => value === undefined || value === null)) throw new TypeError("Exact multicam lowering lost a required private target binding.");
    const payload = await parseJson(args, getTimeoutMs(), {
      ...options, carrier: "sdk", extraEnv: {
        ...(options.extraEnv ?? {}),
        ...(prepared.timelineMutationGuard ? { CUTAGENT_SDK_TIMELINE_GUARD: prepared.timelineMutationGuard } : {}),
        ...(prepared.timelineNativeId ? { CUTAGENT_SDK_EXPECTED_TIMELINE_NATIVE_ID: prepared.timelineNativeId } : {}),
        ...(target?.nativeId ? { CUTAGENT_SDK_EXPECTED_MULTICAM_NATIVE_ID: target.nativeId } : {}),
        ...(prepared.sourceNativeId ? { CUTAGENT_SDK_EXPECTED_MULTICAM_SOURCE_NATIVE_ID: prepared.sourceNativeId } : {}),
        ...(prepared.itemIndex !== null && prepared.itemIndex !== undefined ? { CUTAGENT_SDK_EXPECTED_MULTICAM_SOURCE_ITEM_INDEX: String(prepared.itemIndex) } : {}),
      },
    });
    const operationError = bridgeCliErrorFromPayload(payload, { fallbackMessage: "The exact multicam action failed." });
    if (operationError) throw operationError;
    return payload?.data ?? payload;
  }

  async function executeSdkTimelineStructure(input, before, options = {}) {
    if (input.operation !== "clip_remove") throw new TypeError("This runtime activates only the existing exact managed clip-removal composition.");
    if (input.affectedTracks.length !== 1 || input.affectedTracks[0].type !== input.track.type
      || input.affectedTracks[0].index !== input.track.index) throw new TypeError("Managed clip removal requires one exact executable track coordinate.");
    const args = ["timeline", "items", "delete", "--track-type", input.track.type, "--track", String(input.track.index)];
    args.push("--start-frame", `${input.range.start}f`, "--end-frame", `${input.range.endExclusive}f`, "--match", "contained");
    const payload = await parseJson(args, getTimeoutMs(), { ...options, carrier: "sdk", extraEnv: { ...(options.extraEnv ?? {}), CUTAGENT_SDK_TIMELINE_GUARD: options.mutationGuard } });
    const structureError = bridgeCliErrorFromPayload(payload, { fallbackMessage: "The semantic timeline structure mutation failed." });
    if (structureError) throw structureError;
    return payload?.data ?? payload;
  }

  async function executeSdkVoicePlacement(input, assetPath, options = {}) {
    const payload = await parseJson([
      "audio", "voice-place", assetPath,
      "--track", String(input.trackIndex),
      "--absolute-record-frame", String(input.recordFrame),
    ], getTimeoutMs(), {
      ...options,
      carrier: "sdk",
      extraEnv: { ...(options.extraEnv ?? {}), CUTAGENT_SDK_MARKER_GUARD: options.mutationGuard },
    });
    const placementError = bridgeCliErrorFromPayload(payload, { fallbackMessage: "Generated voice placement failed." });
    if (placementError) throw placementError;
    return payload?.data ?? payload;
  }

  async function applySdkFusionGraph(privatePayload, options = {}) {
    const workingDirectory = typeof options.workingDirectory === "string"
      ? path.resolve(options.workingDirectory)
      : "";
    if (!workingDirectory || workingDirectory === path.parse(workingDirectory).root) {
      throw new TypeError("SDK Fusion graph apply requires a private bounded working directory.");
    }
    fs.mkdirSync(workingDirectory, { recursive: true, mode: 0o700 });
    const requestPath = path.join(workingDirectory, "request.json");
    fs.writeFileSync(requestPath, JSON.stringify(privatePayload), { encoding: "utf8", mode: 0o600, flag: "wx" });
    const payload = await parseJson(
      ["fusion", "apply", requestPath, "--sdk-graph-runtime"],
      getTimeoutMs(),
      { ...options, cwd: workingDirectory, carrier: "sdk" },
    );
    const inspectionError = bridgeCliErrorFromPayload(payload, {
      fallbackMessage: "Failed to apply the exact Fusion composition graph.",
    });
    if (inspectionError) throw inspectionError;
    return payload?.data ?? payload;
  }

  async function executeSdkTimelineItemMove(input, options = {}) {
    const privateTarget = options.privateTarget;
    const privateLinkedAudioTargets = options.privateLinkedAudioTargets;
    if (!privateTarget || typeof privateTarget !== "object" || typeof privateTarget.id !== "string" || !privateTarget.id) {
      throw new TypeError("Timeline-item moves require an exact private video-item execution target.");
    }
    if (!Array.isArray(privateLinkedAudioTargets) || privateLinkedAudioTargets.length !== input.linkedAudioTargets.length) {
      throw new TypeError("Timeline-item moves require exact private linked-audio execution targets.");
    }
    const executionOptions = { ...options };
    delete executionOptions.privateTarget;
    delete executionOptions.privateLinkedAudioTargets;
    const args = [
      "timeline", "items", "move",
      "--track", String(input.target.trackIndex),
      "--start-frame", `${input.target.recordStartFrame}f`,
      "--current-end-frame", `${input.target.recordEndFrame}f`,
      "--name", input.target.name,
      "--to-track", String(input.destination.trackIndex),
      "--to-start-frame", `${input.destination.recordStartFrame}f`,
    ];
    if (input.collisionPolicy === "allow") args.push("--allow-overlap");
    if (input.linkedAudio === "preserve" && input.linkedAudioTargets.length > 0) args.push("--include-linked-audio");
    if (input.linkedAudio === "exclude") args.push("--allow-linked-video-only");
    const payload = await parseJson(args, getTimeoutMs(), {
      ...executionOptions,
      carrier: "sdk",
      extraEnv: {
        ...(executionOptions.extraEnv ?? {}),
        CUTAGENT_SDK_MARKER_GUARD: executionOptions.mutationGuard,
        CUTAGENT_SDK_EXPECTED_TIMELINE_ITEM_TARGET: JSON.stringify(privateTarget),
        CUTAGENT_SDK_EXPECTED_LINKED_AUDIO_COUNT: String(input.linkedAudioTargets.length),
        CUTAGENT_SDK_EXPECTED_LINKED_AUDIO_TARGETS: JSON.stringify(privateLinkedAudioTargets),
      },
    });
    const moveError = bridgeCliErrorFromPayload(payload, { fallbackMessage: "The semantic timeline-item move failed." });
    if (moveError) throw moveError;
    return payload?.data ?? payload;
  }

  function clipMotionEnvironment(options) {
    const privateTarget = options.privateTarget;
    if (!privateTarget || typeof privateTarget !== "object" || typeof privateTarget.id !== "string" || !privateTarget.id) {
      throw new TypeError("Clip motion execution requires an exact private timeline-item target.");
    }
    const executionOptions = { ...options };
    delete executionOptions.privateTarget;
    return {
      executionOptions,
      extraEnv: {
        ...(executionOptions.extraEnv ?? {}),
        CUTAGENT_SDK_TIMELINE_GUARD: executionOptions.mutationGuard,
        CUTAGENT_SDK_EXPECTED_CLIP_MOTION_TARGET: JSON.stringify(privateTarget),
      },
    };
  }

  async function readSdkClipMotion(kind, input, options = {}) {
    const { executionOptions, extraEnv } = clipMotionEnvironment(options);
    const args = kind === "transform"
      ? ["clip", "transform", input.target.name]
      : kind === "keyframe_get"
        ? ["clip", "keyframe", "get", input.property, "--clip", input.target.name]
        : ["clip", "keyframe", "get", "--clip", input.target.name];
    const payload = await parseJson(args, getTimeoutMs(), { ...executionOptions, carrier: "sdk", extraEnv });
    const readError = bridgeCliErrorFromPayload(payload, { fallbackMessage: "Exact clip motion readback failed." });
    if (readError) throw readError;
    return payload?.data ?? payload;
  }

  async function executeSdkClipMotion(kind, input, options = {}) {
    const { executionOptions, extraEnv } = clipMotionEnvironment(options);
    let args;
    if (kind === "keyframe_add") {
      args = ["clip", "keyframe", "add", input.property, String(input.recordFrame), String(input.value), "--clip", input.target.name];
      extraEnv.CUTAGENT_SDK_KEYFRAME_INTERPOLATION = input.interpolation.replace("_", "-");
    } else if (kind === "keyframe_delete") {
      args = ["clip", "keyframe", "delete", input.property, String(input.recordFrame), "--clip", input.target.name];
    } else if (kind === "keyframe_interpolation") {
      args = ["clip", "keyframe", "set-interpolation", input.property, String(input.recordFrame), input.interpolation.replace("_", "-"), "--clip", input.target.name];
    } else if (kind === "transform") {
      args = ["clip", "transform", input.target.name];
      const flags = {
        zoomX: "--zoom-x", zoomY: "--zoom-y", positionX: "--position-x", positionY: "--position-y",
        rotation: "--rotation", anchorX: "--anchor-x", anchorY: "--anchor-y", pitch: "--pitch", yaw: "--yaw",
        opacity: "--opacity", cropLeft: "--crop-left", cropRight: "--crop-right", cropTop: "--crop-top",
        cropBottom: "--crop-bottom", distortion: "--distortion", dynamicZoomEase: "--dynamic-zoom-ease",
      };
      for (const [key, value] of Object.entries(input.transform)) {
        if (key === "flipX") args.push(value ? "--flip-x" : "--no-flip-x");
        else if (key === "flipY") args.push(value ? "--flip-y" : "--no-flip-y");
        else args.push(flags[key], String(value));
      }
    } else {
      throw new TypeError("Unsupported clip motion mutation.");
    }
    const payload = await parseJson(args, getTimeoutMs(), { ...executionOptions, carrier: "sdk", extraEnv });
    const mutationError = bridgeCliErrorFromPayload(payload, { fallbackMessage: "Exact clip motion mutation failed." });
    if (mutationError) throw mutationError;
    return payload?.data ?? payload;
  }

  async function executeSdkTimelineBlade(input, targets, options = {}) {
    const privateTargets = options.privateTargets;
    if (!Array.isArray(privateTargets) || privateTargets.length !== targets.length
      || privateTargets.some((target) => !target || typeof target !== "object" || typeof target.id !== "string" || !target.id)) {
      throw new TypeError("Timeline splits require exact private execution targets.");
    }
    const executionOptions = { ...options };
    delete executionOptions.privateTargets;
    const cuts = targets.map((target) => ({
      at: `${input.recordFrame}f`,
      track_type: target.track.type,
      track: target.track.index,
    }));
    const payload = await parseJson([
      "edit", "blade",
      "--batch-json", JSON.stringify({ cuts }),
      "--respect-locks",
    ], getTimeoutMs(), {
      ...executionOptions,
      carrier: "sdk",
      extraEnv: {
        ...(executionOptions.extraEnv ?? {}),
        CUTAGENT_SDK_MARKER_GUARD: executionOptions.mutationGuard,
        CUTAGENT_SDK_EXPECTED_BLADE_TARGETS: JSON.stringify(privateTargets),
      },
    });
    const bladeError = bridgeCliErrorFromPayload(payload, { fallbackMessage: "The semantic timeline split failed." });
    if (bladeError) throw bladeError;
    return payload?.data ?? payload;
  }

  async function executeSdkLowLevelAction(request, options = {}) {
    if (!request || typeof request !== "object"
      || !/^cutagent\.action\.[a-z0-9_.]+$/u.test(request.actionId)
      || !request.input || typeof request.input !== "object" || Array.isArray(request.input)) {
      throw new TypeError("The typed-action descriptor request is invalid.");
    }
    const payload = await parseJson([
      "sdk-action-read",
      request.actionId,
      "--input-json",
      JSON.stringify(request.input),
    ], getTimeoutMs(), {
      ...options,
      carrier: "sdk",
    });
    const cliError = bridgeCliErrorFromPayload(payload, { fallbackMessage: "The authenticated SDK read failed." });
    if (cliError) throw cliError;
    return payload?.data ?? payload;
  }

  async function observeSdkEvaluatorSoundLibrary({ scope, sourceRoot, phase } = {}, options = {}) {
    if (!new Set(["project", "user"]).has(scope)
      || typeof sourceRoot !== "string" || !path.isAbsolute(sourceRoot)
      || !new Set(["before", "mutated", "restored"]).has(phase)) {
      throw new TypeError("The evaluator Sound Library observation request is invalid.");
    }
    const payload = await parseJson([
      "sdk-evaluator-sound-library-observe",
      "--scope", scope,
      "--source-root", sourceRoot,
      "--phase", phase,
    ], getTimeoutMs(), {...options, carrier: "sdk"});
    const cliError = bridgeCliErrorFromPayload(payload, {fallbackMessage: "The evaluator Sound Library observation failed."});
    if (cliError) throw cliError;
    return payload?.data ?? payload;
  }

  async function readSdkColorSelectorInventory({ kind, album = null, clip = null, compIndex = 1 } = {}, options = {}) {
    const inventoryLabel = (row) => ["label", "name", "version_name", "versionName", "album", "still"]
      .map((key) => row?.[key]).find((value) => typeof value === "string" && value.trim())?.trim() ?? null;
    const inventoryOrdinal = (row, fallback) => ["index", "order", "position"]
      .map((key) => row?.[key]).find((value) => Number.isSafeInteger(value) && value > 0) ?? fallback;
    const clipArgs = typeof clip === "string" && clip.trim() ? ["--clip", clip.trim()] : [];
    const compArgs = Number.isSafeInteger(compIndex) && compIndex > 0 ? ["--comp", String(compIndex)] : null;
    const args = kind === "groups"
      ? ["color", "group", "list"]
      : kind === "albums"
        ? ["color", "gallery", "album", "list"]
        : kind === "stills" && typeof album === "string" && album.trim()
          ? ["color", "gallery", "still", "list", "--album", album.trim()]
          : kind === "powerGrades"
            ? ["color", "power-grade", "list"]
            : kind === "versions"
                ? ["color", "version", "list", ...clipArgs]
                : ["qualifiers", "trackers", "windows"].includes(kind) && compArgs
                  ? ["color", kind.slice(0, -1), "list", ...clipArgs, ...compArgs]
                  : null;
    if (!args) throw new TypeError("Color selector inventory request is invalid.");
    const readRows = async (commandArgs) => {
      const payload = await parseJson(commandArgs, getTimeoutMs(), {...options, carrier: "sdk"});
      const cliError = bridgeCliErrorFromPayload(payload, {fallbackMessage: "Failed to inspect exact Color selector identities."});
      if (cliError) throw cliError;
      const data = payload?.data ?? payload;
      const rows = Array.isArray(data) ? data : data?.items ?? data?.groups ?? data?.albums ?? data?.stills ?? data?.versions;
      return Array.isArray(rows) ? rows : [data];
    };
    let rows = await readRows(args);
    if (kind === "albums") {
      const currentRows = await readRows(["color", "gallery", "album", "current"]);
      const current = currentRows[0];
      const currentLabel = inventoryLabel(current);
      const currentIndex = inventoryOrdinal(current, 0);
      const matches = rows.filter((row, index) => (
        (currentIndex > 0 && inventoryOrdinal(row, index + 1) === currentIndex)
        || (currentLabel !== null && inventoryLabel(row) === currentLabel)
      ));
      if (matches.length !== 1) throw new Error("Current Color album cannot be bound exactly.");
      rows = rows.map((row) => ({...row, ...(row === matches[0] ? {current: true} : {})}));
    }
    if (!Array.isArray(rows) || rows.some((row) => !row || typeof row !== "object" || Array.isArray(row))) {
      throw new Error("CutAgent CLI returned malformed Color selector inventory.");
    }
    return rows;
  }

  async function executeSdkStorageAction(kind, input, options = {}) {
    const executionOptions = { ...options };
    delete executionOptions.mutationGuard;
    delete executionOptions.nativeMediaId;
    delete executionOptions.artifactGuardPath;
    delete executionOptions.artifactDigests;
    delete executionOptions.artifactGuardDigest;
    delete executionOptions.nativeFolderId;
    delete executionOptions.receiptPath;
    delete executionOptions.receiptNonce;
    let args;
    if (kind === "volumes") args = ["storage", "volumes"];
    else if (kind === "reveal") args = ["storage", "reveal", input.path];
    else if (kind === "import") args = ["storage", "import", input.path];
    else if (kind === "import_sequence") {
      args = ["storage", "import-sequence", input.pattern];
      if (input.startIndex !== undefined) args.push("--start-index", String(input.startIndex));
      if (input.endIndex !== undefined) args.push("--end-index", String(input.endIndex));
    } else if (kind === "import_subclip") {
      args = ["storage", "import-subclip", input.path, "--start-frame", String(input.startFrame), "--end-frame", String(input.endFrame)];
    } else if (kind === "matte.add") {
      args = ["storage", "matte", "add", input.clip, ...input.paths];
      if (input.eye) args.push("--eye", input.eye);
    } else if (kind === "matte.timeline_add") args = ["storage", "matte", "timeline-add", ...input.paths];
    else throw new TypeError("Unsupported SDK Storage action.");
    const payload = await parseJson(args, getTimeoutMs(), {
      ...executionOptions,
      carrier: "sdk",
      extraEnv: {
        ...(executionOptions.extraEnv ?? {}),
        ...(options.mutationGuard ? { CUTAGENT_SDK_MEDIA_POOL_GUARD: options.mutationGuard } : {}),
        ...(input.nativeMediaId ? { CUTAGENT_SDK_EXPECTED_STORAGE_MEDIA_TARGET: JSON.stringify({ nativeId: input.nativeMediaId, name: input.clip }) } : {}),
        ...(input.nativeFolderId ? { CUTAGENT_SDK_EXPECTED_STORAGE_FOLDER_TARGET: input.nativeFolderId } : {}),
        ...(options.receiptPath ? { CUTAGENT_SDK_STORAGE_RECEIPT_PATH: options.receiptPath, CUTAGENT_SDK_STORAGE_RECEIPT_NONCE: options.receiptNonce } : {}),
        ...(options.artifactGuardPath ? { CUTAGENT_SDK_STORAGE_ARTIFACT_GUARD: options.artifactGuardPath } : {}),
        ...(options.artifactDigests ? { CUTAGENT_SDK_STORAGE_ARTIFACT_DIGESTS: JSON.stringify(options.artifactDigests) } : {}),
        ...(options.artifactGuardDigest ? { CUTAGENT_SDK_STORAGE_ARTIFACT_GUARD_DIGEST: options.artifactGuardDigest } : {}),
      },
    });
    const storageError = bridgeCliErrorFromPayload(payload, { fallbackMessage: "The managed Storage action failed." });
    if (storageError) throw storageError;
    return payload?.data ?? payload;
  }

  async function executeSdkClipRetime(actionId, input, options = {}) {
    const privateTargets = options.privateTargets;
    if (!Array.isArray(privateTargets) || privateTargets.length < 1
      || privateTargets.some((target) => !target || typeof target !== "object" || typeof target.id !== "string" || !target.id)) {
      throw new TypeError("SDK retime actions require a complete set of exact private execution targets.");
    }
    const executionOptions = { ...options };
    delete executionOptions.privateTargets;
    const primary = actionId === "cutagent.action.clip.speed_ramp" ? input.outgoing : input.target;
    let args;
    if (actionId === "cutagent.action.clip.speed") {
      args = ["clip", "speed", primary.name, "--at", `${primary.recordRange.start}f`];
      if (input.control.kind === "multiplier") args.push("--set", String(input.control.multiplier));
      else args.push("--duration", `${input.control.duration.value.value}f`);
      if (input.rippleTimeline) args.push("--ripple-timeline");
      if (input.pitchCorrection === true) args.push("--pitch-correction");
      if (input.pitchCorrection === false) args.push("--no-pitch-correction");
      args.push("--keyframes", input.keyframes.replaceAll("_", "-"));
    } else if (actionId === "cutagent.action.clip.freeze" || actionId === "cutagent.action.clip.reverse") {
      args = ["clip", actionId.endsWith(".freeze") ? "freeze" : "reverse", primary.name, "--at", `${primary.recordRange.start}f`];
    } else if (actionId === "cutagent.action.clip.speed_ramp") {
      args = [
        "clip", "speed-ramp",
        "--cut-at", `${input.cut.value.value}f`,
        "--track", String(input.outgoing.trackIndex),
        "--out-frames", String(input.outDuration.value.value),
        "--in-frames", String(input.inDuration.value.value),
        "--peak-speed", String(Math.max(input.outStartSpeed, input.outEndSpeed, input.inStartSpeed, input.inEndSpeed)),
        "--out-start-speed", String(input.outStartSpeed),
        "--out-end-speed", String(input.outEndSpeed),
        "--in-start-speed", String(input.inStartSpeed),
        "--in-end-speed", String(input.inEndSpeed),
        "--curve", input.curve.replaceAll("_", "-"),
      ];
      if (input.reverseIncoming) args.push("--reverse-incoming");
    } else {
      throw new TypeError(`Unsupported SDK retime action: ${actionId}`);
    }
    const payload = await parseJson(args, getTimeoutMs(), {
      ...executionOptions,
      carrier: "sdk",
      extraEnv: {
        ...(executionOptions.extraEnv ?? {}),
        CUTAGENT_SDK_MARKER_GUARD: executionOptions.mutationGuard,
        CUTAGENT_SDK_TIMELINE_GUARD: executionOptions.mutationGuard,
        CUTAGENT_SDK_EXPECTED_RETIME_TARGETS: JSON.stringify(privateTargets),
        ...(executionOptions.nativeTimelineId
          ? { CUTAGENT_SDK_EXPECTED_TIMELINE_NATIVE_ID: executionOptions.nativeTimelineId }
          : {}),
      },
    });
    const retimeError = bridgeCliErrorFromPayload(payload, { fallbackMessage: "The exact SDK retime mutation failed." });
    if (retimeError) throw retimeError;
    return payload?.data ?? payload;
  }

  function switchDatabase(databaseName, databaseType = "Disk", options = {}) {
    return parseJson(
      ["project", "db", "switch", databaseName, "--type", databaseType],
      Math.min(getTimeoutMs(), 15000),
      options,
    );
  }

  async function ensureProjectLoaded(project, options = {}) {
    const normalized = normalizeResolveProject(project);
    if (!normalized) {
      throw new Error("Project identity is required.");
    }

    const current = await getActiveProject(options);
    if (current && areResolveProjectsEqual(current, normalized)) {
      return current;
    }

    const currentDatabase = await getCurrentDatabase({ ...options, forceRefresh: true });
    if (
      normalized.database_name
      && normalized.database_type
      && (
        currentDatabase.database_name !== normalized.database_name
        || currentDatabase.database_type !== normalized.database_type
      )
    ) {
      requireCutAgentCliSuccess(
        await switchDatabase(normalized.database_name, normalized.database_type, options),
        `Failed to switch DaVinci Resolve database to "${normalized.database_name}".`,
      );
    }

    requireCutAgentCliSuccess(
      await api.openProject(normalized.name, options),
      `Failed to open project "${normalized.name}".`,
    );

    const reopened = await getActiveProject(options);
    if (!reopened || reopened.name !== normalized.name) {
      throw new Error(`DaVinci Resolve did not activate project "${normalized.name}".`);
    }

    return reopened;
  }

  const api = {
    getCutAgentCliRuntimeEnv() {
      return {
        DAVINCI_RESOLVE_SDK_EMBEDDED_AUTH_PATH: getEmbeddedAuthPath(),
        ...embeddedRuntimeEnv,
      };
    },
    getCachedStatus() {
      return statusCache.value;
    },
    async getStatus(options = {}) {
      const sdkOwnerSession = getSdkOwnerSession();
      if (!options.session && sdkOwnerSession) options = { ...options, session: sdkOwnerSession };
      if (options.session?.resolve_runtime?.mode === "parallel_gui_beta") {
        return getTargetedSessionStatus(options);
      }
      const probeKey = statusProbeKey(options);
      const lightweightStatusInFlight = lightweightStatusInFlightByCommand.get(probeKey);
      if (lightweightStatusInFlight) {
        try {
          await lightweightStatusInFlight;
        } catch {
          // The full probe below remains authoritative.
        }
      }
      if (!options.forceRefresh && statusCache.value && Date.now() < statusCache.expiresAt) {
        return statusCache.value;
      }

      const statusInFlight = statusInFlightByCommand.get(probeKey);
      if (statusInFlight) {
        return statusInFlight;
      }

      const generation = statusStateGeneration;
      const nextStatusInFlight = loadResolveStatus(options, generation)
        .then((nextStatus) => {
          return cacheResolveStatus(nextStatus, generation);
        })
        .finally(() => {
          if (statusInFlightByCommand.get(probeKey) === nextStatusInFlight) {
            statusInFlightByCommand.delete(probeKey);
          }
        });
      statusInFlightByCommand.set(probeKey, nextStatusInFlight);

      return nextStatusInFlight;
    },
    async getLightweightStatus(options = {}) {
      const sdkOwnerSession = getSdkOwnerSession();
      if (!options.session && sdkOwnerSession) options = { ...options, session: sdkOwnerSession };
      if (options.session?.resolve_runtime?.mode === "parallel_gui_beta") {
        return getTargetedSessionStatus(options, { lightweight: true });
      }
      if (!options.forceRefresh && statusCache.value && Date.now() < statusCache.expiresAt) {
        return statusCache.value;
      }

      const probeKey = statusProbeKey(options);
      const statusInFlight = statusInFlightByCommand.get(probeKey);
      if (statusInFlight) {
        return statusInFlight;
      }

      const lightweightStatusInFlight = lightweightStatusInFlightByCommand.get(probeKey);
      if (lightweightStatusInFlight) {
        return lightweightStatusInFlight;
      }

      const generation = statusStateGeneration;
      const nextLightweightStatusInFlight = loadLightweightResolveStatus(options, generation)
        .then((nextStatus) => {
          return cacheResolveStatus(nextStatus, generation);
        })
        .finally(() => {
          if (lightweightStatusInFlightByCommand.get(probeKey) === nextLightweightStatusInFlight) {
            lightweightStatusInFlightByCommand.delete(probeKey);
          }
        });
      lightweightStatusInFlightByCommand.set(probeKey, nextLightweightStatusInFlight);

      return nextLightweightStatusInFlight;
    },
    getCurrentDatabase,
    getActiveProject,
    listProjects,
    executeLocalSdkCommand: (args, options) => parseJson(args, getTimeoutMs(), options),
    readSdkLiveInspection,
    executeSdkMarkerMutation,
    executeSdkProjectCreate,
    readSdkProjectSettings,
    executeSdkMediaImport,
    executeSdkColorMutation,
    executeSdkTimelineEdit,
    executeSdkMulticamMutation,
    executeSdkMulticamMatchFrame,
    executeSdkMulticamResidual,
    executeSdkTimelineStructure,
    previewSdkTimelineEdit,
    readSdkCapability,
    executeSdkVoicePlacement,
    applySdkFusionGraph,
    executeSdkTimelineItemMove,
    readSdkClipMotion,
    executeSdkClipMotion,
    executeSdkTimelineBlade,
    executeSdkClipRetime,
    executeSdkLowLevelAction,
    observeSdkEvaluatorSoundLibrary,
    readSdkColorSelectorInventory,
    executeSdkStorageAction,
    ensureProjectLoaded,
    async createProject(name, options = {}) {
      invalidateStatusCache();
      const payload = await parseJson(["project", "create", name], Math.min(getTimeoutMs(), 15000), options);
      if (payload?.ok) {
        void resolveActivator();
      }
      return payload;
    },
    async openProject(name, options = {}) {
      invalidateStatusCache();
      const payload = await parseJson(["project", "open", name], Math.min(getTimeoutMs(), 15000), options);
      if (payload?.ok) {
        void resolveActivator();
      }
      return payload;
    },
    closeProject(options = {}) {
      invalidateStatusCache();
      return parseJson(["project", "close"], Math.min(getTimeoutMs(), 15000), options);
    },
    saveProject(options = {}) {
      invalidateStatusCache();
      return parseJson(["project", "save"], Math.min(getTimeoutMs(), 15000), options);
    },
    exportProject(name, exportPath, options = {}) {
      const args = ["project", "export", name, exportPath, options.withStills === false ? "--no-stills" : "--with-stills"];
      return parseJson(args, getTimeoutMs(), options);
    },
    importProject(importPath, options = {}) {
      invalidateStatusCache();
      return parseJson(["project", "import", importPath], getTimeoutMs(), options);
    },
    async inspectCurrentProjectDatabase(options = {}) {
      const payload = requireCutAgentCliSuccess(
        await parseJson(["project", "db", "current"], Math.min(getTimeoutMs(), 8000), options),
        "Failed to inspect the active DaVinci Resolve Project.db.",
      );
      return payload?.data ?? payload;
    },
    async quitResolve(options = {}) {
      invalidateStatusCache();
      return requireCutAgentCliSuccess(
        await parseJson(["quit", "--force"], Math.min(getTimeoutMs(), 30000), options),
        "Failed to stop the isolated DaVinci Resolve instance.",
      );
    },
    async installEmbeddedScript(options = {}) {
      invalidateStatusCache();
      const server = await api.startEmbeddedServer(options);
      const args = ["embedded", "install"];
      if (options.sandbox) {
        args.push("--sandbox");
      }
      const payload = requireCutAgentCliSuccess(
        await parseJson(args, Math.min(getTimeoutMs(), 15000), options),
        "Failed to install CutAgent.lua.",
      );
      return {
        ...(payload?.data ?? payload),
        server,
      };
    },
    async startEmbeddedServer(options = {}) {
      if (options.cutAgentCliCommand) {
        const error = new Error(
          "An attested per-run CutAgent CLI snapshot cannot own the persistent embedded bridge server.",
        );
        error.code = "ATTESTED_RUNTIME_PERSISTENT_SERVER_FORBIDDEN";
        throw error;
      }
      if (embeddedServerIsAlive()) {
        const authStatus = readEmbeddedAuthTokenStatus();
        if (authStatus.auth_token_valid) {
          embeddedRuntimeEnv = {
            ...embeddedRuntimeEnv,
            ...embeddedRuntimeEnvForServer({
              host: authStatus.host,
              port: authStatus.port,
            }),
          };
          return {
            running: true,
            started: false,
            pid: embeddedServerProcess.pid ?? null,
            auth_path: authStatus.auth_path,
            auth_token_present: authStatus.auth_token_present,
            auth_token_valid: authStatus.auth_token_valid,
            host: authStatus.host ?? "127.0.0.1",
            port: authStatus.port ?? null,
          };
        }
        embeddedServerProcess.kill();
        embeddedServerProcess = null;
      }

      try {
        const statusPayload = await parseJson(["embedded", "status"], Math.min(getTimeoutMs(), 5000), options);
        const embeddedStatus = normalizeEmbeddedStatusPayload(statusPayload);
        if (embeddedServerCanBeReused(embeddedStatus)) {
          const server = normalizeEmbeddedServer(embeddedStatus) ?? {};
          const serverPort = normalizePort(server.port);
          const orphanCleanup = serverPort
            ? await terminateManagedEmbeddedRuntimeForPort(serverPort)
            : { matched: false, terminated: false };
          if (orphanCleanup.matched && !orphanCleanup.terminated) {
            throw new Error(
              "A previous CutAgent embedded bridge could not be stopped safely. Quit CutAgent and try again.",
            );
          }
          if (orphanCleanup.matched) {
            embeddedRuntimeEnv = {};
          } else {
            embeddedRuntimeEnv = {
              ...embeddedRuntimeEnv,
              ...embeddedRuntimeEnvForServer({
                host: server.host,
                port: server.port,
              }),
            };
            return {
              running: true,
              started: false,
              external: true,
              pid: null,
              auth_path: embeddedStatus.auth_path ?? server.auth_path ?? getEmbeddedAuthPath(),
              auth_token_present: Boolean(embeddedStatus.auth_token_present),
              auth_token_valid: Boolean(embeddedStatus.auth_token_valid),
              host: server.host ?? "127.0.0.1",
              port: serverPort,
            };
          }
        }
        if (embeddedServerLooksStale(embeddedStatus)) {
          const reclaim = await reclaimStaleEmbeddedServer(embeddedStatus);
          if (!reclaim.reclaimed) {
            throw new Error(
              `A stale CutAgent embedded bridge is already using the DaVinci Resolve Free port (${embeddedServerSummary(embeddedStatus)}).`
              + " Quit older CutAgent helper processes or restart the Mac, then try again.",
            );
          }
        }
      } catch (error) {
        if (
          error?.cli_error_code === "AUTH_REQUIRED"
          || error?.cli_error_code === "AUTH_TOKEN_INVALID"
          || error?.cli_error_code === "AUTH_TOKEN_EXPIRED"
          || error?.cli_error_code === "AUTH_TOKEN_COMMAND_MISMATCH"
        ) {
          throw error;
        }
        if (
          error instanceof Error
          && (
            error.message.includes("stale CutAgent embedded bridge")
            || error.message.includes("previous CutAgent embedded bridge")
          )
        ) {
          throw error;
        }
        // If status probing fails for a non-contract reason, fall through to the normal start path.
      }

      if (embeddedServerStarting) {
        return embeddedServerStarting;
      }

      embeddedServerStarting = (async () => {
        let stdout = "";
        let stderr = "";
        let startError = null;
        const args = ["embedded", "start-server", "-j"];
        const authorization = await cutAgentCliAuthorizationService?.authorize?.(args, {
          accessToken: options.accessToken ?? null,
          session: options.session ?? null,
          cutAgentCliCommand: options.cutAgentCliCommand ?? null,
        });
        const previousEmbeddedRuntimeEnv = embeddedRuntimeEnv;
        const selectedServerEnv = await selectEmbeddedServerEnv({
          ...process.env,
          ...previousEmbeddedRuntimeEnv,
        });
        embeddedRuntimeEnv = {
          ...previousEmbeddedRuntimeEnv,
          ...selectedServerEnv.env,
        };
        const cliEnv = buildCutAgentCliEnv({
          extraEnv: {
            DAVINCI_RESOLVE_SDK_EMBEDDED_AUTH_PATH: getEmbeddedAuthPath(),
            ...embeddedRuntimeEnv,
            ...(authorization?.env ?? {}),
          },
        });
        assertCutAgentCliPolicyBeforeSpawn(cutAgentCliAuthorizationService, args, authorization);
        const startedAtMs = Date.now();
        const child = spawn(
          options.cutAgentCliCommand || resolveCutAgentCliCommand(),
          ["embedded", "start-server", "-j"],
          {
            shell: false,
            stdio: ["ignore", "pipe", "pipe"],
            env: cliEnv,
          },
        );
        embeddedServerProcess = child;
        child.stdout?.on("data", (chunk) => {
          stdout = appendLimited(stdout, chunk);
        });
        child.stderr?.on("data", (chunk) => {
          stderr = appendLimited(stderr, chunk);
        });
        child.once("error", (error) => {
          startError = error;
        });
        child.once("exit", () => {
          if (embeddedServerProcess === child) {
            embeddedServerProcess = null;
          }
        });

        await delay(250);
        if (startError) {
          throw startError;
        }
        if (!embeddedServerIsAlive()) {
          embeddedRuntimeEnv = previousEmbeddedRuntimeEnv;
          throw new Error(
            stderr.trim()
            || stdout.trim()
            || "Failed to start CutAgent embedded bridge server.",
          );
        }
        const authStatus = await waitForEmbeddedAuthToken({
          child,
          env: cliEnv,
          startedAtMs,
        });
        if (!authStatus.auth_token_valid || !authStatus.fresh) {
          child.kill();
          embeddedServerProcess = null;
          embeddedRuntimeEnv = previousEmbeddedRuntimeEnv;
          const reason = authStatus.error ? ` (${authStatus.error})` : "";
          throw new Error(
            `CutAgent embedded bridge server started but did not publish its auth token at ${authStatus.auth_path}${reason}.`,
          );
        }

        return {
          running: true,
          started: true,
          pid: child.pid ?? null,
          auth_path: authStatus.auth_path,
          auth_token_present: authStatus.auth_token_present,
          auth_token_valid: authStatus.auth_token_valid,
          host: authStatus.host ?? "127.0.0.1",
          port: authStatus.port ?? selectedServerEnv.port,
          fallback_port: selectedServerEnv.fallback === true,
          fallback_reason: selectedServerEnv.fallback ? selectedServerEnv.reason : null,
        };
      })().finally(() => {
        embeddedServerStarting = null;
      });

      return embeddedServerStarting;
    },
    async stopEmbeddedServer() {
      const child = embeddedServerProcess;
      embeddedServerProcess = null;
      const runtimePort = normalizePort(embeddedRuntimeEnv.DAVINCI_RESOLVE_SDK_EMBEDDED_PORT)
        ?? normalizePort(readEmbeddedAuthTokenStatus().port)
        ?? EMBEDDED_DEFAULT_PORT;
      embeddedRuntimeEnv = {};
      const managedCleanup = await terminateManagedEmbeddedRuntimeForPort(runtimePort, {
        allowedParentPids: [1, process.pid, child?.pid].filter(Number.isInteger),
      });
      const childWasAlive = Boolean(
        child && child.exitCode === null && child.signalCode === null,
      );
      if (childWasAlive) {
        const windowsTreeStopped = await terminateWindowsProcessTree(child.pid);
        if (!windowsTreeStopped) {
          child.kill("SIGTERM");
        }
        await Promise.race([
          new Promise((resolve) => child.once("exit", resolve)),
          delay(1500).then(() => {
            if (child.exitCode === null && child.signalCode === null) {
              child.kill("SIGKILL");
            }
          }),
        ]);
      }
      return {
        stopped: childWasAlive || managedCleanup.terminated,
        orphan_reclaimed: managedCleanup.terminated,
      };
    },
    deleteProject(name, options = {}) {
      invalidateStatusCache();
      return parseJson(["project", "delete", name, "--force"], Math.min(getTimeoutMs(), 15000), options);
    },
    switchDatabase(databaseName, databaseType = "Disk", options = {}) {
      invalidateStatusCache();
      return switchDatabase(databaseName, databaseType, options);
    },
  };

  return api;
}

export {
  embeddedAuthTokenWaitMs,
  getEmbeddedAuthPath,
  normalizeResolveStatusPayload,
  waitForEmbeddedAuthToken,
};
