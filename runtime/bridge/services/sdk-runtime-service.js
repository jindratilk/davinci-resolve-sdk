import crypto from "node:crypto";
import {
  CUTAGENT_SDK_API_VERSION,
  CUTAGENT_SDK_PROTOCOL_DIGEST,
  CUTAGENT_SDK_WIRE_PROTOCOL,
  sdkCompatibilityDescriptorSchema,
} from "../contracts/generated/sdk-runtime.js";
import {
  CutAgentCliIdentityError,
  isCutAgentCliIdentityCurrent,
  probeCutAgentCliIdentity,
} from "../../local/cli-runtime.mjs";
import { evaluateCutAgentSdkRuntimeCompatibility } from "../contracts/generated/sdk-runtime-policy.js";

const DEFAULT_BOOTSTRAP_TTL_MS = 2 * 60 * 1000;
const DEFAULT_SESSION_TTL_MS = 30 * 60 * 1000;
const DEFAULT_SESSION_IDLE_TTL_MS = 10 * 60 * 1000;
const DEFAULT_MAX_SESSIONS = 32;
const DEFAULT_PENDING_SESSION_TTL_MS = 30 * 1000;
const DEFAULT_CLOSE_TOMBSTONE_TTL_MS = 5 * 60 * 1000;
const DEFAULT_MAX_CLOSE_TOMBSTONES = 64;
const DEFAULT_CLI_IDENTITY_REFRESH_INTERVAL_MS = 5 * 60 * 1000;
const SEMVER_PATTERN = /^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/;
const EXECUTABLE_DIGEST_PATTERN = /^[a-f0-9]{64}$/;

function opaque(prefix) {
  return `${prefix}${crypto.randomUUID()}`;
}

function token() {
  return crypto.randomBytes(32).toString("base64url");
}

function digest(value) {
  return crypto.createHash("sha256").update(String(value), "utf8").digest("base64url");
}

function tokenMatches(expectedDigest, candidate) {
  if (typeof candidate !== "string" || !candidate) return false;
  const actual = Buffer.from(digest(candidate), "utf8");
  const expected = Buffer.from(expectedDigest, "utf8");
  return actual.length === expected.length && crypto.timingSafeEqual(actual, expected);
}

function iso(milliseconds) {
  return new Date(milliseconds).toISOString();
}

function assertDuration(value, label) {
  if (!Number.isInteger(value) || value < 1_000 || value > 24 * 60 * 60 * 1000) {
    throw new Error(`${label} must be a bounded positive duration.`);
  }
}

export function createSdkRuntimeService({
  appVersion,
  runtimeVersion = appVersion,
  distributionVersion = appVersion,
  cliIdentityProbe = probeCutAgentCliIdentity,
  cliIdentityCurrent = isCutAgentCliIdentityCurrent,
  cliProbeOptions = undefined,
  cliIdentityRefreshIntervalMs = DEFAULT_CLI_IDENTITY_REFRESH_INTERVAL_MS,
  now = () => Date.now(),
  bootstrapTtlMs = DEFAULT_BOOTSTRAP_TTL_MS,
  sessionTtlMs = DEFAULT_SESSION_TTL_MS,
  sessionIdleTtlMs = DEFAULT_SESSION_IDLE_TTL_MS,
  maxSessions = DEFAULT_MAX_SESSIONS,
  pendingSessionTtlMs = DEFAULT_PENDING_SESSION_TTL_MS,
  closeTombstoneTtlMs = DEFAULT_CLOSE_TOMBSTONE_TTL_MS,
  maxCloseTombstones = DEFAULT_MAX_CLOSE_TOMBSTONES,
} = {}) {
  assertDuration(bootstrapTtlMs, "bootstrapTtlMs");
  assertDuration(sessionTtlMs, "sessionTtlMs");
  assertDuration(sessionIdleTtlMs, "sessionIdleTtlMs");
  if (!Number.isInteger(maxSessions) || maxSessions < 1 || maxSessions > 256) {
    throw new Error("maxSessions must be between 1 and 256.");
  }
  assertDuration(closeTombstoneTtlMs, "closeTombstoneTtlMs");
  assertDuration(pendingSessionTtlMs, "pendingSessionTtlMs");
  assertDuration(cliIdentityRefreshIntervalMs, "cliIdentityRefreshIntervalMs");
  if (!Number.isInteger(maxCloseTombstones) || maxCloseTombstones < 1 || maxCloseTombstones > 256) {
    throw new Error("maxCloseTombstones must be between 1 and 256.");
  }

  const normalizedAppVersion = typeof appVersion === "string" ? appVersion.trim() : "";
  const normalizedRuntimeVersion = typeof runtimeVersion === "string" ? runtimeVersion.trim() : "";
  const normalizedDistributionVersion = typeof distributionVersion === "string"
    ? distributionVersion.trim()
    : "";
  const runtimeInstanceId = opaque("runtime_instance_");
  const bootstraps = new Map();
  const sessions = new Map();
  const pendingSessions = new Map();
  const closedSessions = new Map();
  let stopped = false;
  let onBootstrapConsumed = null;
  let onReadinessChanged = null;
  let descriptor = null;
  let readinessFailure = null;
  let cliIdentity = null;
  let cliIdentityKey = null;
  let probeInFlight = null;
  let probeAbortController = null;
  let stopPromise = null;

  function clearRuntimeCredentials() {
    bootstraps.clear();
    sessions.clear();
    pendingSessions.clear();
    closedSessions.clear();
  }

  function notifyReadinessChanged() {
    queueMicrotask(() => onReadinessChanged?.());
  }

  function failReadiness(code, message, category, cliVersion = null) {
    const changed = Boolean(descriptor)
      || readinessFailure?.code !== code
      || readinessFailure?.cliVersion !== cliVersion;
    descriptor = null;
    readinessFailure = Object.freeze({ code, message, category, cliVersion });
    clearRuntimeCredentials();
    if (changed) notifyReadinessChanged();
    return false;
  }

  function applyCliIdentity(identity) {
    if (stopped) return false;
    const cliVersion = typeof identity?.version === "string" ? identity.version : "";
    const executableDigest = typeof identity?.executableDigest === "string"
      ? identity.executableDigest
      : "";
    if (!cliVersion || !EXECUTABLE_DIGEST_PATTERN.test(executableDigest)) {
      cliIdentity = null;
      return failReadiness(
        "CUTAGENT_CLI_IDENTITY_MALFORMED",
        "CutAgent CLI identity is malformed.",
        "incompatible",
        cliVersion || null,
      );
    }
    cliIdentity = identity;
    const compatibility = evaluateCutAgentSdkRuntimeCompatibility({
      runtimeVersion: normalizedRuntimeVersion,
      distribution: "standalone_local",
      distributionVersion: normalizedDistributionVersion,
      cliVersion,
    });
    if (!compatibility.compatible) {
      const issue = compatibility.issues[0];
      const code = issue.axis === "runtime"
        ? "SDK_RUNTIME_VERSION_UNSUPPORTED"
        : issue.axis === "distribution"
          ? "SDK_DISTRIBUTION_VERSION_UNSUPPORTED"
          : "CUTAGENT_CLI_VERSION_UNSUPPORTED";
      return failReadiness(
        code,
        `The ${issue.axis} version axis (${issue.received}) is outside the reviewed SDK policy (${issue.supported}).`,
        "incompatible",
        cliVersion,
      );
    }

    const nextIdentityKey = `${cliVersion}:${executableDigest}`;
    if (cliIdentityKey && cliIdentityKey !== nextIdentityKey) {
      clearRuntimeCredentials();
    }
    cliIdentityKey = nextIdentityKey;
    // This is an observed executable binding, not a replacement trust store.
    // In packaged builds the selected CutAgent CLI guard remains responsible
    // for verifying its signed runtime manifest before it starts the CLI.
    const runtimeFingerprint = `runtime_fingerprint_f${digest([
      normalizedAppVersion,
      normalizedRuntimeVersion,
      normalizedDistributionVersion,
      cliVersion,
      executableDigest,
      runtimeInstanceId,
    ].join(":")).slice(0, 42)}`;
    const parsedDescriptor = sdkCompatibilityDescriptorSchema.safeParse({
      sdkApiVersion: CUTAGENT_SDK_API_VERSION,
      wireProtocol: CUTAGENT_SDK_WIRE_PROTOCOL,
      runtimeVersion: normalizedRuntimeVersion,
      distribution: "standalone_local",
      distributionVersion: normalizedDistributionVersion,
      cliVersion,
      protocolDigest: CUTAGENT_SDK_PROTOCOL_DIGEST,
      runtimeFingerprint,
    });
    if (!parsedDescriptor.success) {
      return failReadiness(
        "SDK_COMPATIBILITY_DESCRIPTOR_INVALID",
        "The CutAgent SDK compatibility descriptor is invalid.",
        "incompatible",
        cliVersion,
      );
    }
    const changed = descriptor?.runtimeFingerprint !== parsedDescriptor.data.runtimeFingerprint
      || readinessFailure !== null;
    descriptor = parsedDescriptor.data;
    readinessFailure = null;
    if (changed) notifyReadinessChanged();
    return true;
  }

  function applyCliProbeFailure(error) {
    if (stopped) return false;
    cliIdentity = null;
    const code = error instanceof CutAgentCliIdentityError
      ? error.code
      : "CUTAGENT_CLI_PROBE_FAILED";
    const category = code === "CUTAGENT_CLI_IDENTITY_MALFORMED"
      || code === "CUTAGENT_CLI_IDENTITY_DRIFT"
      ? "incompatible"
      : "unavailable";
    return failReadiness(
      code,
      error instanceof CutAgentCliIdentityError
        ? error.message
        : "CutAgent CLI identity could not be established.",
      category,
    );
  }

  function startCliIdentityProbe() {
    if (stopped || probeInFlight) return false;
    probeAbortController = new AbortController();
    let result;
    try {
      result = cliIdentityProbe({
        ...(cliProbeOptions ?? {}),
        signal: probeAbortController.signal,
      });
    } catch (error) {
      probeAbortController = null;
      return applyCliProbeFailure(error);
    }
    if (!result || typeof result.then !== "function") {
      probeAbortController = null;
      return applyCliIdentity(result);
    }
    const pending = Promise.resolve(result)
      .then(applyCliIdentity, applyCliProbeFailure)
      .finally(() => {
        if (probeInFlight === pending) probeInFlight = null;
        probeAbortController = null;
      });
    probeInFlight = pending;
    return false;
  }

  function refreshReadiness({ forceProbe = false } = {}) {
    if (stopped) {
      return failReadiness(
        "SDK_RUNTIME_STOPPED",
        "The CutAgent SDK runtime has stopped.",
        "unavailable",
      );
    }
    if (!SEMVER_PATTERN.test(normalizedAppVersion)) {
      return failReadiness(
        "SDK_APP_VERSION_MALFORMED",
        "The CutAgent desktop app version is missing or malformed.",
        "incompatible",
      );
    }
    if (forceProbe) {
      startCliIdentityProbe();
      return Boolean(descriptor);
    }
    if (cliIdentity) {
      try {
        if (cliIdentityCurrent(cliIdentity, cliProbeOptions)) {
          return Boolean(descriptor);
        }
      } catch {
        // Treat any fast identity-check failure as drift and re-establish it asynchronously.
      }
      cliIdentity = null;
      failReadiness(
        "CUTAGENT_CLI_IDENTITY_DRIFT",
        "CutAgent CLI identity could not be revalidated.",
        "incompatible",
      );
      return startCliIdentityProbe();
    }
    if (!probeInFlight && !readinessFailure) {
      failReadiness(
        "CUTAGENT_CLI_PROBE_PENDING",
        "CutAgent CLI identity is being established.",
        "unavailable",
      );
      return startCliIdentityProbe();
    }
    return Boolean(descriptor);
  }

  function rememberClosed(sessionId, entry, at = now()) {
    while (closedSessions.size >= maxCloseTombstones) {
      closedSessions.delete(closedSessions.keys().next().value);
    }
    closedSessions.set(sessionId, {
      tokenDigest: entry.tokenDigest,
      expiresAt: at + closeTombstoneTtlMs,
    });
  }

  function cleanup(at = now()) {
    for (const [key, entry] of bootstraps) {
      if (entry.expiresAt <= at) bootstraps.delete(key);
    }
    for (const [sessionId, entry] of sessions) {
      if (entry.expiresAt <= at || entry.idleExpiresAt <= at) {
        sessions.delete(sessionId);
        rememberClosed(sessionId, entry, at);
      }
    }
    for (const [sessionId, entry] of pendingSessions) {
      if (entry.pendingExpiresAt <= at || entry.expiresAt <= at) {
        pendingSessions.delete(sessionId);
        rememberClosed(sessionId, entry, at);
      }
    }
    for (const [sessionId, entry] of closedSessions) {
      if (entry.expiresAt <= at) closedSessions.delete(sessionId);
    }
  }

  function requireReady({ refresh = true } = {}) {
    if (refresh) refreshReadiness();
    if (stopped || !descriptor) {
      const error = new Error("CutAgent SDK runtime is not version-ready.");
      error.code = readinessFailure?.category === "incompatible"
        ? "SDK_INCOMPATIBLE"
        : "RUNTIME_UNAVAILABLE";
      error.readiness = readinessFailure;
      throw error;
    }
  }

  function issueBootstrap({ ownerSessionId = null } = {}) {
    requireReady({ refresh: true });
    cleanup();
    if (ownerSessionId !== null && (typeof ownerSessionId !== "string" || !ownerSessionId.trim() || ownerSessionId.length > 256)) {
      throw new TypeError("SDK bootstrap owner session ID is invalid.");
    }
    // The public discovery file names exactly one unowned bootstrap. Private
    // app-agent bootstraps coexist briefly so concurrent chats cannot revoke
    // one another before connecting.
    if (ownerSessionId === null) {
      for (const [key, entry] of bootstraps) {
        if (entry.ownerSessionId === null) bootstraps.delete(key);
      }
    }
    const bootstrapToken = token();
    const issuedAt = now();
    const expiresAt = issuedAt + bootstrapTtlMs;
    bootstraps.set(digest(bootstrapToken), { issuedAt, expiresAt, ownerSessionId });
    return { bootstrapToken, issuedAt, expiresAt };
  }

  function consumeBootstrapBinding(bootstrapToken, requestedRuntimeInstanceId) {
    requireReady({ refresh: true });
    cleanup();
    if (requestedRuntimeInstanceId !== runtimeInstanceId || typeof bootstrapToken !== "string") {
      return null;
    }
    const key = digest(bootstrapToken);
    const entry = bootstraps.get(key);
    if (!entry) return null;
    bootstraps.delete(key);
    if (entry.expiresAt <= now()) return null;
    if (entry.ownerSessionId === null) queueMicrotask(() => onBootstrapConsumed?.());
    return Object.freeze({ ownerSessionId: entry.ownerSessionId });
  }

  function consumeBootstrap(bootstrapToken, requestedRuntimeInstanceId) {
    return consumeBootstrapBinding(bootstrapToken, requestedRuntimeInstanceId) !== null;
  }

  function createSessionRecord({ accountFingerprint, ownerSessionId = null }) {
    requireReady();
    cleanup();
    if (sessions.size + pendingSessions.size >= maxSessions) {
      const error = new Error("CutAgent SDK session limit reached.");
      error.code = "SESSION_LIMIT_REACHED";
      throw error;
    }
    if (typeof accountFingerprint !== "string" || !accountFingerprint) {
      throw new Error("SDK session requires an account fingerprint.");
    }
    if (ownerSessionId !== null && (typeof ownerSessionId !== "string" || !ownerSessionId.trim() || ownerSessionId.length > 256)) {
      throw new TypeError("SDK owner session ID is invalid.");
    }
    const issuedAt = now();
    const expiresAt = issuedAt + sessionTtlMs;
    const idleExpiresAt = Math.min(expiresAt, issuedAt + sessionIdleTtlMs);
    const sessionId = opaque("sdk_session_");
    const connectionId = opaque("connection_");
    const sessionToken = token();
    const entry = {
      tokenDigest: digest(sessionToken),
      accountFingerprint,
      ownerSessionId,
      issuedAt,
      expiresAt,
      idleExpiresAt,
    };
    return { entry, session: {
      connectionId,
      sessionId,
      sessionToken,
      issuedAt: iso(issuedAt),
      expiresAt: iso(expiresAt),
      idleExpiresAt: iso(idleExpiresAt),
    } };
  }

  function openSession(input) {
    const created = createSessionRecord(input);
    sessions.set(created.session.sessionId, created.entry);
    return created.session;
  }

  function prepareSession(input) {
    const created = createSessionRecord(input);
    pendingSessions.set(created.session.sessionId, {
      ...created.entry,
      pendingExpiresAt: now() + pendingSessionTtlMs,
    });
    return created.session;
  }

  function confirmSession({ sessionId, sessionToken, accountFingerprint } = {}) {
    requireReady();
    cleanup();
    const entry = pendingSessions.get(sessionId);
    if (!entry || !tokenMatches(entry.tokenDigest, sessionToken)) return false;
    if (typeof accountFingerprint !== "string" || !accountFingerprint || entry.accountFingerprint !== accountFingerprint) {
      pendingSessions.delete(sessionId);
      rememberClosed(sessionId, entry);
      return false;
    }
    pendingSessions.delete(sessionId);
    const { pendingExpiresAt: _pendingExpiresAt, ...activeEntry } = entry;
    sessions.set(sessionId, activeEntry);
    return true;
  }

  function validateSession({ sessionId, sessionToken, accountFingerprint, touch = true } = {}) {
    requireReady();
    cleanup();
    const entry = sessions.get(sessionId);
    if (!entry || !tokenMatches(entry.tokenDigest, sessionToken)) return false;
    if (typeof accountFingerprint !== "string" || !accountFingerprint || entry.accountFingerprint !== accountFingerprint) {
      sessions.delete(sessionId);
      rememberClosed(sessionId, entry);
      return false;
    }
    if (touch) {
      entry.idleExpiresAt = Math.min(entry.expiresAt, now() + sessionIdleTtlMs);
    }
    return true;
  }

  function resolveOwnerSessionId({ sessionId, sessionToken, accountFingerprint } = {}) {
    if (!validateSession({ sessionId, sessionToken, accountFingerprint, touch: false })) return null;
    return sessions.get(sessionId)?.ownerSessionId ?? null;
  }

  function ownsActiveSession({ sessionId, accountFingerprint } = {}) {
    requireReady();
    cleanup();
    const entry = sessions.get(sessionId);
    return Boolean(entry && typeof accountFingerprint === "string" && entry.accountFingerprint === accountFingerprint);
  }

  function closeSessionsForAccount(accountFingerprint) {
    cleanup();
    let closed = 0;
    for (const store of [sessions, pendingSessions]) {
      for (const [sessionId, entry] of store) {
        if (entry.accountFingerprint !== accountFingerprint) continue;
        store.delete(sessionId);
        rememberClosed(sessionId, entry);
        closed += 1;
      }
    }
    return closed;
  }

  function closeSession({ sessionId, sessionToken } = {}) {
    requireReady();
    cleanup();
    const tombstone = closedSessions.get(sessionId);
    if (tombstone) return tokenMatches(tombstone.tokenDigest, sessionToken);
    const entry = sessions.get(sessionId) ?? pendingSessions.get(sessionId);
    if (!entry || !tokenMatches(entry.tokenDigest, sessionToken)) return false;
    sessions.delete(sessionId);
    pendingSessions.delete(sessionId);
    rememberClosed(sessionId, entry);
    return true;
  }

  async function waitForReadiness() {
    if (probeInFlight) await probeInFlight;
    return Boolean(descriptor) && !stopped;
  }

  function readinessState() {
    if (descriptor && !stopped) {
      return Object.freeze({
        state: "ready",
        appVersion: normalizedAppVersion,
        runtimeVersion: descriptor.runtimeVersion,
        distributionVersion: descriptor.distributionVersion,
        cliVersion: descriptor.cliVersion,
        sdkApiVersion: descriptor.sdkApiVersion,
        wireProtocol: descriptor.wireProtocol,
        protocolDigest: descriptor.protocolDigest,
      });
    }
    if (probeInFlight) {
      return Object.freeze({
        state: "pending",
        code: "CUTAGENT_CLI_PROBE_PENDING",
        category: "unavailable",
      });
    }
    return Object.freeze({
      state: stopped ? "stopped" : "failed",
      code: readinessFailure?.code ?? "CUTAGENT_CLI_UNAVAILABLE",
      category: readinessFailure?.category ?? "unavailable",
      cliVersion: readinessFailure?.cliVersion ?? null,
    });
  }

  const sweepInterval = Math.min(60_000, bootstrapTtlMs, sessionIdleTtlMs);
  const timer = setInterval(cleanup, sweepInterval);
  timer.unref?.();
  refreshReadiness();
  const identityTimer = setInterval(
    () => refreshReadiness({ forceProbe: true }),
    cliIdentityRefreshIntervalMs,
  );
  identityTimer.unref?.();

  return {
    runtimeInstanceId,
    get descriptor() {
      return descriptor;
    },
    refreshReadiness,
    waitForReadiness,
    readinessState,
    issueBootstrap,
    consumeBootstrapBinding,
    consumeBootstrap,
    openSession,
    prepareSession,
    confirmSession,
    validateSession,
    resolveOwnerSessionId,
    ownsActiveSession,
    closeSessionsForAccount,
    closeSession,
    setBootstrapConsumedHandler(handler) {
      onBootstrapConsumed = typeof handler === "function" ? handler : null;
    },
    setReadinessChangedHandler(handler) {
      onReadinessChanged = typeof handler === "function" ? handler : null;
    },
    inspect() {
      cleanup();
      return {
        ready: Boolean(descriptor) && !stopped,
        readinessFailure,
        bootstrapCount: bootstraps.size,
        sessionCount: sessions.size,
        pendingSessionCount: pendingSessions.size,
        closeTombstoneCount: closedSessions.size,
        cliIdentityProbeInFlight: Boolean(probeInFlight),
        runtimeInstanceId,
      };
    },
    stop() {
      if (stopped) return stopPromise ?? Promise.resolve();
      stopped = true;
      clearInterval(timer);
      clearInterval(identityTimer);
      const pendingProbe = probeInFlight;
      probeAbortController?.abort();
      probeAbortController = null;
      onBootstrapConsumed = null;
      onReadinessChanged = null;
      clearRuntimeCredentials();
      descriptor = null;
      readinessFailure = Object.freeze({
        code: "SDK_RUNTIME_STOPPED",
        message: "The CutAgent SDK runtime has stopped.",
        category: "unavailable",
        cliVersion: null,
      });
      stopPromise = pendingProbe
        ? pendingProbe.then(() => undefined, () => undefined)
        : Promise.resolve();
      return stopPromise;
    },
  };
}

export function sdkAccountFingerprint(account) {
  const identity = typeof account?.userId === "string" ? account.userId.trim() : "";
  if (!identity) {
    const error = new Error("CutAgent account identity is unavailable.");
    error.code = "AUTHENTICATION_REQUIRED";
    throw error;
  }
  return digest(identity);
}
