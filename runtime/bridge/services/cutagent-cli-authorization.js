import crypto from "node:crypto";
import {createLocalCapability as createDesktopBridgeCapability} from "../../local/capability.mjs";
import {
  readBundledCutAgentCliCommandCatalog,
  readBundledText,
} from "../../local/resources.mjs";
import { captureAuthenticatedSdkRequest } from "./sdk-authenticated-request.js";
import { sdkPreparedActionAuthorizationBindingSchema } from "../contracts/generated/sdk-prepared-action.js";

const GLOBAL_VALUE_OPTIONS = new Set([
  "--output-mode",
  "--select",
  "--policy-profile",
  "--ffmpeg-path",
  "--ffprobe-path",
]);
const READ_ONLY_CACHEABLE_COMMANDS = new Set([
  "capabilities",
  "project.db.current",
  "project.list",
  "status",
  "version",
  "version.inspect",
  "version.list",
  "version.status",
]);
const CACHE_EXPIRY_SKEW_MS = 10_000;
const MAX_READ_ONLY_CACHE_TTL_MS = 60_000;
const MAX_AUTHORIZATION_CACHE_ENTRIES = 256;
let commandCatalogCache = null;

function normalizeCommandToken(value) {
  return typeof value === "string" ? value.replaceAll("-", "_") : "";
}

function normalizeCommandPath(value) {
  return typeof value === "string"
    ? value.split(/\s+/).filter(Boolean).map(normalizeCommandToken).join(".")
    : "";
}

function canonicalizeCommandPathSegment(commandTokens, token) {
  const canonical = normalizeCommandToken(token);
  if (commandTokens.length === 1 && commandTokens[0] === "timeline" && canonical === "tracks") {
    return "track";
  }
  return canonical;
}

function normalizeArgs(args) {
  return Array.isArray(args) ? args.filter((item) => typeof item === "string") : [];
}

function addCommandPath(index, pathValue, commandIdValue = null) {
  const pathId = normalizeCommandPath(pathValue);
  if (!pathId) {
    return;
  }
  const commandId = typeof commandIdValue === "string" && commandIdValue.trim()
    ? commandIdValue.trim()
    : pathId;
  if (!index.commandByPath.has(pathId) || commandId !== pathId) {
    index.commandByPath.set(pathId, commandId);
  }
  const parts = pathId.split(".");
  for (let indexPart = 1; indexPart < parts.length; indexPart += 1) {
    index.prefixes.add(parts.slice(0, indexPart).join("."));
  }
}

function loadCommandCatalogIndex() {
  if (commandCatalogCache) {
    return commandCatalogCache;
  }

  const index = { commandByPath: new Map(), prefixes: new Set() };
  const agentCatalogRaw = readBundledCutAgentCliCommandCatalog("");
  try {
    const parsed = JSON.parse(agentCatalogRaw);
    const commands = Array.isArray(parsed?.commands) ? parsed.commands : [];
    for (const command of commands) {
      addCommandPath(index, command?.path, command?.command_id);
    }
  } catch {
    // Fall back to the public labels below if the local public reference is unavailable.
  }

  const labelCatalogRaw = readBundledText("cutagent-cli-command-metadata/command-labels.json", "");
  try {
    const parsed = JSON.parse(labelCatalogRaw);
    const commands = parsed && typeof parsed === "object" ? parsed.commands : null;
    for (const pathValue of Object.keys(commands && typeof commands === "object" ? commands : {})) {
      addCommandPath(index, pathValue);
    }
  } catch {
    // Keep a conservative fallback below if bundled command metadata is unavailable.
  }

  commandCatalogCache = index;
  return commandCatalogCache;
}

function inferCommandIdFromCatalog(tokens) {
  const { commandByPath, prefixes } = loadCommandCatalogIndex();
  if (!commandByPath.size) {
    return null;
  }

  const commandTokens = [];
  let bestCommandId = "";
  let timelineTracksAlias = false;

  for (const token of tokens) {
    const normalized = canonicalizeCommandPathSegment(commandTokens, token);
    if (commandTokens.length === 1 && commandTokens[0] === "timeline" && normalizeCommandToken(token) === "tracks") {
      timelineTracksAlias = true;
    }
    const candidate = [...commandTokens, normalized].join(".");
    if (!commandByPath.has(candidate) && !prefixes.has(candidate)) {
      break;
    }
    commandTokens.push(normalized);
    if (commandByPath.has(candidate)) {
      bestCommandId = commandByPath.get(candidate);
    }
  }

  if (!bestCommandId && timelineTracksAlias && commandTokens.join(".") === "timeline.track") {
    return commandByPath.get("timeline.track.list") ?? null;
  }

  return bestCommandId || null;
}

function collectCommandTokens(args) {
  const tokens = [];
  for (let index = 0; index < args.length; index += 1) {
    const token = args[index];
    if (token === "--") {
      break;
    }
    if (GLOBAL_VALUE_OPTIONS.has(token)) {
      index += 1;
      continue;
    }
    if ([...GLOBAL_VALUE_OPTIONS].some((option) => token.startsWith(`${option}=`))) {
      continue;
    }
    if (token.startsWith("-")) {
      continue;
    }
    tokens.push(token);
  }
  return tokens;
}

export function canonicalizeCutAgentCliArgs(args) {
  return JSON.stringify(normalizeArgs(args));
}

export function hashCutAgentCliArgs(args) {
  return crypto
    .createHash("sha256")
    .update(canonicalizeCutAgentCliArgs(args), "utf8")
    .digest("hex");
}

export function inferCutAgentCliCommandId(args) {
  const tokens = normalizeArgs(args);
  if (tokens.includes("sdk-action-read") || tokens.includes("sdk-evaluator-sound-library-observe")) {
    return "sdk.low_level.read";
  }
  const catalogCommandId = inferCommandIdFromCatalog(collectCommandTokens(tokens));
  if (catalogCommandId) {
    return catalogCommandId;
  }

  const commandTokens = [];

  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (token === "--") {
      break;
    }
    if (GLOBAL_VALUE_OPTIONS.has(token)) {
      index += 1;
      continue;
    }
    if ([...GLOBAL_VALUE_OPTIONS].some((option) => token.startsWith(`${option}=`))) {
      continue;
    }
    if (token.startsWith("-")) {
      continue;
    }
    commandTokens.push(canonicalizeCommandPathSegment(commandTokens, token));
    const wantsThirdToken = commandTokens[0] === "project" && commandTokens[1] === "db";
    if (commandTokens.length >= (wantsThirdToken ? 3 : 2)) {
      break;
    }
  }

  if (commandTokens.join(".") === "timeline.track") {
    return "timeline.track.list";
  }

  return commandTokens.length > 0 ? commandTokens.join(".") : "cutagent_cli";
}

export function isCutAgentCliAuthorizationRequired(args) {
  const tokens = normalizeArgs(args);
  if (tokens.length === 0) {
    return false;
  }
  if (isPublicRootFlagProbe(tokens, new Set(["--help", "-h"]))) {
    return false;
  }
  if (isPublicRootFlagProbe(tokens, new Set(["--version"]))) {
    return false;
  }
  if (isLocalStatusProbe(tokens)) {
    return false;
  }

  return true;
}

function isPublicRootFlagProbe(tokens, requestedFlags) {
  const allowedFlags = new Set([
    "--json", "-j", "--agent", "--lean", "--quiet", "-q",
    "--plain", "-p", "--tsv",
  ]);
  let requested = false;
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (requestedFlags.has(token)) {
      if (requested) return false;
      requested = true;
      continue;
    }
    if (allowedFlags.has(token)) continue;
    if (token === "--output-mode") {
      if (index + 1 >= tokens.length) return false;
      index += 1;
      continue;
    }
    if (token.startsWith("--output-mode=")) continue;
    return false;
  }
  return requested;
}

/** Final local execution guard. Every CutAgent CLI spawn site must call this. */
export function assertCutAgentCliPolicyBeforeSpawn(service, args, authorization) {
  if (!isCutAgentCliAuthorizationRequired(args)) return true;
  if (typeof service?.assertReadyForSpawn !== "function") {
    throw createAuthorizationError(args, "AUTH_REQUIRED", "The command execution site has no current authorization authority.");
  }
  return service.assertReadyForSpawn(args, authorization);
}

function isLocalStatusProbe(tokens) {
  const commandTokens = [];
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (token === "--") {
      break;
    }
    if (GLOBAL_VALUE_OPTIONS.has(token)) {
      index += 1;
      continue;
    }
    if ([...GLOBAL_VALUE_OPTIONS].some((option) => token.startsWith(`${option}=`))) {
      continue;
    }
    if (token === "--json" || token === "-j" || token === "--quiet" || token === "-q"
      || token === "--plain" || token === "-p" || token === "--tsv" || token === "--dry-run"
      || token === "-n" || token === "--verbose" || token === "-v") {
      continue;
    }
    if (token.startsWith("-")) {
      return false;
    }
    commandTokens.push(token);
  }
  return commandTokens.length === 1 && normalizeCommandToken(commandTokens[0]) === "status";
}

function createAuthorizationError(args, code, message, extraDetails = {}) {
  const commandId = inferCutAgentCliCommandId(args);
  const error = new Error(message);
  error.name = "CutAgentCliAuthorizationError";
  error.bridge_error_type = "cutagent_cli_error";
  error.code = code;
  error.cli_error_code = code;
  error.cli_error_details = {
    command_id: commandId,
    args_sha256: hashCutAgentCliArgs(args),
    ...extraDetails,
  };
  error.cli_meta = {
    command: commandId,
    policy_profile: "auto_edit",
  };
  error.exit_code = 2;
  return error;
}

function normalizeString(value) {
  return typeof value === "string" && value.trim() ? value.trim() : "";
}

function hashOpaqueValue(value) {
  return crypto
    .createHash("sha256")
    .update(value, "utf8")
    .digest("hex");
}

function normalizeEmbeddedExecuteSha256(value) {
  const normalized = normalizeString(value).toLowerCase();
  return /^[a-f0-9]{64}$/.test(normalized) ? normalized : null;
}

function normalizeExpiresAtMs(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value > 10_000_000_000 ? value : value * 1000;
  }
  if (typeof value === "string" && value.trim()) {
    const numeric = Number(value);
    if (Number.isFinite(numeric)) {
      return normalizeExpiresAtMs(numeric);
    }
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function isReadOnlyCacheableCommand(commandId) {
  return READ_ONLY_CACHEABLE_COMMANDS.has(commandId);
}

function createAuthorizationCacheKey({
  token,
  args,
  commandId,
  session,
  embeddedExecuteSha256,
}) {
  return [
    hashOpaqueValue(token),
    commandId,
    hashCutAgentCliArgs(args),
    normalizeString(session?.id),
    normalizeEmbeddedExecuteSha256(embeddedExecuteSha256) ?? "",
  ].join(":");
}

function buildCutAgentCliAuthorizerEnv(session) {
  const token = normalizeString(process.env.CUTAGENT_CLI_AUTHORIZER_TOKEN);
  if (!token) {
    return {};
  }
  const configuredUrl = normalizeString(process.env.CUTAGENT_CLI_AUTHORIZER_URL);
  const port = normalizeString(process.env.PORT) || "8000";
  const bridgeCapability = createDesktopBridgeCapability({
    method: "POST",
    path: "/internal/cutagent-cli/authorize",
  });
  return {
    CUTAGENT_CLI_AUTHORIZER_URL:
      configuredUrl || `http://127.0.0.1:${port}/internal/cutagent-cli/authorize`,
    CUTAGENT_CLI_AUTHORIZER_TOKEN: token,
    CUTAGENT_CLI_AUTHORIZER_SESSION_ID: normalizeString(session?.id),
    ...(bridgeCapability ? { CUTAGENT_CLI_AUTHORIZER_BRIDGE_CAPABILITY: bridgeCapability } : {}),
  };
}

export function createCutAgentCliAuthorizationService({
  settingsService,
  authService,
  cutagentCloudService,
}) {
  const tokenCache = new Map();
  const inFlightAuthorizations = new Map();
  const trustedCommandAuthorizations = new WeakMap();

  function trustCommandAuthorization(authorization, args, embeddedExecuteSha256 = null, reusable = false) {
    trustedCommandAuthorizations.set(authorization, Object.freeze({
      commandId: inferCutAgentCliCommandId(args),
      argsSha256: hashCutAgentCliArgs(args),
      embeddedExecuteSha256: normalizeEmbeddedExecuteSha256(embeddedExecuteSha256),
      reusable,
    }));
    return authorization;
  }

  async function authorizePreparedAction({
    actionId,
    operationClass,
    authorizationBinding,
    timeoutMs = null,
    signal = null,
  }) {
    if (authService?.isSdkFinalEvaluator === true) {
      if (typeof authService.authorizePreparedActionForEvaluator !== "function") {
        throw createAuthorizationError([], "AUTH_REQUIRED", "Final evaluator prepared-action authorization is unavailable.");
      }
      return authService.authorizePreparedActionForEvaluator({
        actionId,
        operationClass,
        authorizationBinding,
      });
    }
    if (settingsService?.getRuntimeMode?.() !== "cloud_managed") {
      throw createAuthorizationError([], "AUTH_REQUIRED", "Signed prepared-action authorization requires CutAgent Cloud.");
    }
    if (typeof cutagentCloudService?.authorizePreparedSdkAction !== "function") {
      throw createAuthorizationError([], "AUTH_REQUIRED", "Prepared-action authorization is unavailable.");
    }
    const binding = sdkPreparedActionAuthorizationBindingSchema.parse(authorizationBinding);
    if (!/^cutagent\.action\.[a-z0-9_.]+$/.test(String(actionId ?? ""))
      || !["read", "mutation"].includes(operationClass)) {
      throw createAuthorizationError([], "AUTH_TOKEN_INVALID", "Prepared-action authorization binding is invalid.");
    }
    const authenticated = await captureAuthenticatedSdkRequest(authService, { signal });
    let payload;
    try {
      payload = await cutagentCloudService.authorizePreparedSdkAction(authenticated.accessToken, {
        actionId,
        operationClass,
        authorizationBinding: binding,
        desktopSessionId: null,
        platform: process.platform,
        appVersion: "desktop",
      }, { timeoutMs, signal });
    } catch (error) {
      throw createAuthorizationError(
        [],
        typeof error?.cloudErrorCode === "string" ? error.cloudErrorCode : "AUTH_REQUIRED",
        error instanceof Error ? error.message : "Prepared-action authorization failed.",
      );
    }
    authService.assertSessionIdentityCurrent(authenticated.identity);
    const token = typeof payload?.auth_token === "string" ? payload.auth_token.trim() : "";
    if (!token) throw createAuthorizationError([], "AUTH_TOKEN_INVALID", "CutAgent Cloud returned no prepared-action token.");
    return Object.freeze({ token, expiresAt: payload.expires_at ?? null });
  }

  function readCachedAuthorization(cacheKey) {
    const entry = tokenCache.get(cacheKey);
    if (!entry) {
      return null;
    }
    if (entry.cacheExpiresAtMs <= Date.now()) {
      tokenCache.delete(cacheKey);
      return null;
    }
    return entry.authorization;
  }

  function writeCachedAuthorization(cacheKey, authorization, expiresAt) {
    const expiresAtMs = normalizeExpiresAtMs(expiresAt);
    if (!expiresAtMs) {
      return;
    }
    const cacheExpiresAtMs = Math.min(
      expiresAtMs - CACHE_EXPIRY_SKEW_MS,
      Date.now() + MAX_READ_ONLY_CACHE_TTL_MS,
    );
    if (cacheExpiresAtMs <= Date.now()) {
      return;
    }
    tokenCache.set(cacheKey, {
      authorization,
      cacheExpiresAtMs,
    });
    while (tokenCache.size > MAX_AUTHORIZATION_CACHE_ENTRIES) {
      const oldestKey = tokenCache.keys().next().value;
      tokenCache.delete(oldestKey);
    }
  }

  async function authorize(args, {
    accessToken = null,
    session = null,
    embeddedExecuteSha256 = null,
    timeoutMs = null,
    signal = null,
  } = {}) {
    if (!isCutAgentCliAuthorizationRequired(args)) {
      return {};
    }

    const commandId = inferCutAgentCliCommandId(args);
    const cloudManaged = settingsService?.getRuntimeMode?.() === "cloud_managed";
    const token = cloudManaged
      ? (typeof accessToken === "string" && accessToken.trim()
          ? accessToken.trim()
          : authService?.getAccessToken?.() ?? null)
      : null;
    if (cloudManaged && !token) {
      throw createAuthorizationError(
        args,
        "AUTH_REQUIRED",
        "Sign in to CutAgent before running DaVinci Resolve edit commands.",
      );
    }
    const canReuseAuthorization = isReadOnlyCacheableCommand(commandId);

    if (!cloudManaged) {
      return trustCommandAuthorization({}, args, embeddedExecuteSha256, canReuseAuthorization);
    }

    const normalizedArgs = normalizeArgs(args);
    const normalizedEmbeddedExecuteSha256 = normalizeEmbeddedExecuteSha256(embeddedExecuteSha256);
    const cacheKey = createAuthorizationCacheKey({
      token,
      args: normalizedArgs,
      commandId,
      session,
      embeddedExecuteSha256: normalizedEmbeddedExecuteSha256,
    });
    if (canReuseAuthorization) {
      const cachedAuthorization = readCachedAuthorization(cacheKey);
      if (cachedAuthorization) {
        return cachedAuthorization;
      }
    }

    const existingAuthorization = inFlightAuthorizations.get(cacheKey);
    if (existingAuthorization) {
      return existingAuthorization;
    }

    const authorizationPromise = (async () => {
      let payload;
      try {
        payload = await cutagentCloudService.authorizeCutAgentCliCommand(token, {
          args: normalizedArgs,
          command_id: commandId,
          desktop_session_id: session?.id ?? null,
          platform: process.platform,
          app_version: "desktop",
          ...(normalizedEmbeddedExecuteSha256
            ? { embedded_execute_sha256: normalizedEmbeddedExecuteSha256 }
            : {}),
        }, { timeoutMs, signal });
      } catch (error) {
        if (signal?.aborted || error?.name === "AbortError" || error?.name === "TimeoutError") {
          throw signal?.aborted ? (signal.reason ?? error) : error;
        }
        const subscriptionRefused = error?.cloudErrorCode === "cutagent_cli_not_entitled"
          || error?.cloudStatusCode === 402;
        const cloudErrorCode = typeof error?.cloudErrorCode === "string" && error.cloudErrorCode.trim()
          ? error.cloudErrorCode.trim()
          : null;
        const cloudStatusCode = Number.isInteger(error?.cloudStatusCode)
          ? error.cloudStatusCode
          : null;
        throw createAuthorizationError(
          args,
          cloudErrorCode ?? (subscriptionRefused ? "SUBSCRIPTION_REQUIRED" : "AUTH_REQUIRED"),
          error instanceof Error ? error.message : "DaVinci Resolve command authorization is required.",
          {
            ...(cloudStatusCode ? { cloud_status_code: cloudStatusCode } : {}),
            ...(cloudErrorCode ? { cloud_error_code: cloudErrorCode } : {}),
          },
        );
      }
      const commandToken = typeof payload?.auth_token === "string" ? payload.auth_token.trim() : "";
      if (!commandToken) {
        throw createAuthorizationError(
          args,
          "AUTH_TOKEN_INVALID",
          "CutAgent cloud did not return a DaVinci Resolve command authorization token.",
        );
      }
      const expectedArgsSha256 = hashCutAgentCliArgs(normalizedArgs);
      if ((typeof payload?.command_id === "string" && payload.command_id !== commandId)
        || (typeof payload?.args_sha256 === "string" && payload.args_sha256 !== expectedArgsSha256)
        || (normalizedEmbeddedExecuteSha256 && typeof payload?.embedded_execute_sha256 === "string"
          && payload.embedded_execute_sha256 !== normalizedEmbeddedExecuteSha256)) {
        throw createAuthorizationError(
          args,
          "AUTH_TOKEN_INVALID",
          "CutAgent cloud returned a command authorization for different arguments.",
        );
      }

      const authorization = {
        env: {
          CUTAGENT_CLI_AUTH_TOKEN: commandToken,
          CUTAGENT_CLI_AUTH_REQUIRED: "1",
          ...buildCutAgentCliAuthorizerEnv(session),
        },
        commandId: payload.command_id ?? commandId,
        displayLabel: typeof payload.display_label === "string" && payload.display_label.trim()
          ? payload.display_label.trim()
          : null,
        argsSha256: expectedArgsSha256,
        accountSubject: typeof payload.account_subject === "string" && payload.account_subject.trim()
          ? payload.account_subject.trim()
          : null,
        expiresAt: payload.expires_at ?? null,
        embeddedExecuteSha256: payload.embedded_execute_sha256 ?? null,
      };

      trustCommandAuthorization(authorization, args, normalizedEmbeddedExecuteSha256, canReuseAuthorization);

      if (canReuseAuthorization) {
        writeCachedAuthorization(cacheKey, authorization, payload.expires_at);
      }
      return authorization;
    })();

    inFlightAuthorizations.set(cacheKey, authorizationPromise);
    try {
      return await authorizationPromise;
    } catch (error) {
      throw error;
    } finally {
      inFlightAuthorizations.delete(cacheKey);
    }
  }

  function assertReadyForSpawn(args, authorization) {
    const commandId = inferCutAgentCliCommandId(args);
    if (!isCutAgentCliAuthorizationRequired(args)) return true;
    const trusted = authorization && typeof authorization === "object"
      ? trustedCommandAuthorizations.get(authorization)
      : null;
    if (!trusted || trusted.commandId !== commandId || trusted.argsSha256 !== hashCutAgentCliArgs(args)) {
      throw createAuthorizationError(args, "AUTH_REQUIRED", "The command authorization does not match these exact arguments.");
    }
    if (trusted.embeddedExecuteSha256 !== normalizeEmbeddedExecuteSha256(authorization?.embeddedExecuteSha256)) {
      throw createAuthorizationError(args, "AUTH_REQUIRED", "The embedded command authorization binding changed before execution.");
    }
    if (!trusted.reusable) trustedCommandAuthorizations.delete(authorization);
    return true;
  }

  async function getDisplayLabel(args, { accessToken = null } = {}) {
    if (settingsService?.getRuntimeMode?.() !== "cloud_managed") {
      return null;
    }
    const token = typeof accessToken === "string" && accessToken.trim()
      ? accessToken.trim()
      : authService?.getAccessToken?.() ?? null;
    if (!token || typeof cutagentCloudService?.getCutAgentCliCommandMetadata !== "function") {
      return null;
    }
    const normalizedArgs = normalizeArgs(args);
    if (normalizedArgs.length === 0) {
      return null;
    }
    try {
      const payload = await cutagentCloudService.getCutAgentCliCommandMetadata(token, {
        args: normalizedArgs,
        command_id: inferCutAgentCliCommandId(normalizedArgs),
      });
      return typeof payload?.display_label === "string" && payload.display_label.trim()
        ? payload.display_label.trim()
        : null;
    } catch {
      return null;
    }
  }

  return {
    authorize,
    authorizePreparedAction,
    assertReadyForSpawn,
    getDisplayLabel,
    isAuthorizationRequired: isCutAgentCliAuthorizationRequired,
  };
}
