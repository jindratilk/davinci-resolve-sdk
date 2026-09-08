import crypto from "node:crypto";
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import {createLocalCapability as createDesktopBridgeCapability} from "../../local/capability.mjs";
import {
  readBundledCutAgentCliCommandCatalog,
  readBundledText,
} from "../../local/resources.mjs";
import { captureAuthenticatedSdkRequest } from "./sdk-authenticated-request.js";
import {
  isReviewedSdkEditPreview,
  lowerCutAgentCliMutationImpact,
  mutationPolicyDigest,
  privateCommandImpact,
  PRIVATE_IMPACT_REGISTRY_DIGEST,
} from "./mutation-policy/impact-lowering.js";
import { MutationPolicyError } from "./mutation-policy/mutation-policy-gate.js";
import { resolveCutAgentCliCommand } from "../../local/cli-runtime.mjs";
import { sdkMutationImpactSchema } from "../contracts/generated/sdk-mutation-policy.js";
import { sdkPreparedActionAuthorizationBindingSchema } from "../contracts/generated/sdk-prepared-action.js";

const RELEASE_BRIDGE_BUNDLE = process.env.CUTAGENT_RELEASE_BRIDGE_BUNDLE === "1";
const MUTATION_IMPACT_ARG = "--cutagent-internal-mutation-impact";
const MUTATION_IMPACT_PROOF_CONTEXT = "cutagent-mutation-impact-v1";
const MUTATION_AUTHORITY_SECRET = crypto.randomBytes(32).toString("base64url");

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
const NON_EDITING_LOCAL_UTILITY_COMMANDS = new Set([
  "embedded.install",
  "embedded.start_server",
]);

const CACHE_EXPIRY_SKEW_MS = 10_000;
const MAX_READ_ONLY_CACHE_TTL_MS = 60_000;
const MAX_AUTHORIZATION_CACHE_ENTRIES = 256;
const MAX_NATIVE_IMPACT_OUTPUT_BYTES = 256 * 1024;

let commandCatalogCache = null;

function requestNativeImpactArtifact(requestBytes, nonce, cutAgentCliCommand = null) {
  return new Promise((resolve, reject) => {
    // This authenticated metadata request never executes a public CLI command;
    // mutation execution still passes through assertCutAgentCliPolicyBeforeSpawn.
    const authorityCommand = cutAgentCliCommand || resolveCutAgentCliCommand();
    const child = spawn(authorityCommand, [MUTATION_IMPACT_ARG, nonce], {
      shell: false,
      stdio: ["pipe", "pipe", "pipe"],
      env: {
        ...process.env,
        CUTAGENT_MUTATION_AUTHORITY_SECRET: MUTATION_AUTHORITY_SECRET,
        CUTAGENT_MUTATION_AUTHORITY_BRIDGE_PID: String(process.pid),
      },
    });
    let stdout = Buffer.alloc(0);
    let stderr = Buffer.alloc(0);
    let settled = false;
    let timer = null;
    const finish = (error, value = null) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      if (error) reject(error); else resolve(value);
    };
    const append = (current, chunk) => {
      const next = Buffer.concat([current, chunk]);
      if (next.length > MAX_NATIVE_IMPACT_OUTPUT_BYTES) {
        child.kill("SIGKILL");
        throw new Error("Native mutation authority output exceeded its bound.");
      }
      return next;
    };
    child.stdout.on("data", (chunk) => {
      try { stdout = append(stdout, chunk); } catch (error) { finish(error); }
    });
    child.stderr.on("data", (chunk) => {
      try { stderr = append(stderr, chunk); } catch (error) { finish(error); }
    });
    child.once("error", (error) => finish(error));
    child.once("close", (code) => {
      if (code !== 0) {
        finish(new Error(stderr.toString("utf8").trim() || "Native mutation authority failed."));
      } else {
        finish(null, stdout.toString("utf8"));
      }
    });
    timer = setTimeout(() => {
      child.kill("SIGKILL");
      finish(new Error("Native mutation authority timed out."));
    }, 2_000);
    timer.unref?.();
    child.stdin.end(requestBytes);
  });
}

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

function commandOption(args, name) {
  const exactIndex = args.lastIndexOf(name);
  if (exactIndex >= 0) return args[exactIndex + 1] ?? null;
  const inline = [...args].reverse().find((item) => item.startsWith(`${name}=`));
  return inline ? inline.slice(name.length + 1) : null;
}

export function currentReferencedPayloadDigests(args, cwd) {
  const inline = commandOption(args, "--batch-json");
  if (inline) return [mutationPolicyDigest(inline)];
  const fusionIndex = args.indexOf("fusion");
  const requested = commandOption(args, "--batch")
    ?? commandOption(args, "--input")
    ?? commandOption(args, "--input-file")
    ?? (args.includes("--sdk-graph-runtime")
      && fusionIndex >= 0
      && args[fusionIndex + 1] === "apply"
      ? args[fusionIndex + 2]
      : null);
  if (!requested) return [];
  if (typeof cwd !== "string" || !cwd) {
    throw new MutationPolicyError(
      "decision_binding_mismatch",
      "The referenced mutation payload has no execution directory at launch.",
    );
  }
  try {
    const bytes = fs.readFileSync(path.resolve(cwd, requested));
    return [`sha256:${crypto.createHash("sha256").update(bytes).digest("hex")}`];
  } catch {
    throw new MutationPolicyError(
      "decision_binding_mismatch",
      "The referenced mutation payload is unavailable at launch.",
    );
  }
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
  if (tokens.includes("--help") || tokens.includes("-h") || tokens.includes("--version")) {
    return false;
  }
  if (isLocalStatusProbe(tokens)) {
    return false;
  }

  return true;
}

/** Final local execution guard. Every CutAgent CLI spawn site must call this. */
export function assertCutAgentCliPolicyBeforeSpawn(service, args, authorization) {
  if (!isCutAgentCliAuthorizationRequired(args)) return true;
  const commandId = inferCutAgentCliCommandId(args);
  if (!RELEASE_BRIDGE_BUNDLE && privateCommandImpact(commandId)?.operationClass === "read") return true;
  if (typeof service?.assertReadyForSpawn !== "function") {
    throw new MutationPolicyError(
      "missing_scope",
      "The mutation execution site has no current policy authority.",
    );
  }
  return service.assertReadyForSpawn(args, authorization);
}

function canonicalNativeArtifact(value) {
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number" && Number.isFinite(value)) return Object.is(value, -0) ? 0 : value;
  if (Array.isArray(value)) return value.map(canonicalNativeArtifact);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonicalNativeArtifact(value[key])]));
  }
  throw new TypeError("Native mutation impact must be JSON-compatible.");
}

function parseNativeMutationImpact(stdout, expectedNonce, expectedCommandId, expectedArgs) {
  let parsed;
  try {
    parsed = JSON.parse(typeof stdout === "string" ? stdout.trim() : "");
  } catch {
    parsed = null;
  }
  const artifact = parsed?.artifact;
  const signature = typeof parsed?.signature === "string" ? parsed.signature : "";
  const expectedSignature = crypto.createHmac("sha256", MUTATION_AUTHORITY_SECRET)
    .update(`${MUTATION_IMPACT_PROOF_CONTEXT}\0${JSON.stringify(canonicalNativeArtifact(artifact))}`, "utf8")
    .digest("hex");
  const impact = artifact?.impact === null ? null : sdkMutationImpactSchema.safeParse(artifact?.impact);
  if (parsed && Object.keys(parsed).sort().join("\0") !== ["artifact", "signature"].sort().join("\0")
    || artifact?.schemaVersion !== 1
    || artifact?.nonce !== expectedNonce
    || artifact?.registryDigest !== PRIVATE_IMPACT_REGISTRY_DIGEST
    || !["read", "mutation"].includes(artifact?.classification)
    || !/^[a-f0-9]{64}$/.test(signature)
    || !crypto.timingSafeEqual(Buffer.from(signature, "hex"), Buffer.from(expectedSignature, "hex"))
    || (artifact.classification === "read" ? artifact.impact !== null : !impact?.success)
    || (impact?.success && impact.data.canonicalRequestDigest !== mutationPolicyDigest({ commandId: expectedCommandId, args: expectedArgs }))) {
    throw new MutationPolicyError(
      "unknown_impact",
      "The private native mutation authority returned an incompatible result.",
    );
  }
  return Object.freeze({
    commandId: expectedCommandId,
    operationClass: artifact.classification,
    registryDigest: artifact.registryDigest,
    impact: impact?.success ? impact.data : null,
  });
}

export async function resolveCutAgentCliCommandImpact({
  args,
  commandId,
  carrier,
  cwd,
  policyContext,
  cutAgentCliCommand = null,
}) {
  if (isReviewedSdkEditPreview({ args, commandId, carrier, policyContext })) {
    return Object.freeze({
      commandId,
      operationClass: "read",
      registryDigest: PRIVATE_IMPACT_REGISTRY_DIGEST,
      impact: null,
    });
  }
  if (!RELEASE_BRIDGE_BUNDLE) {
    const impact = privateCommandImpact(commandId);
    return Object.freeze({
      commandId,
      operationClass: impact?.operationClass ?? "mutation",
      registryDigest: PRIVATE_IMPACT_REGISTRY_DIGEST,
      impact: impact?.operationClass === "read" ? null : lowerCutAgentCliMutationImpact({
        args, commandId, carrier, cwd, policyContext,
      }),
    });
  }
  try {
    const nonce = crypto.randomBytes(32).toString("base64url");
    const request = { args: normalizeArgs(args), commandId, carrier, cwd, policyContext, nonce };
    const stdout = await requestNativeImpactArtifact(
      Buffer.from(JSON.stringify(request), "utf8"),
      nonce,
      cutAgentCliCommand,
    );
    return parseNativeMutationImpact(stdout, nonce, commandId, normalizeArgs(args));
  } catch (error) {
    if (error instanceof MutationPolicyError) throw error;
    throw new MutationPolicyError(
      "unknown_impact",
      "The private native mutation authority is unavailable.",
    );
  }
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
  mutationPolicyGate = null,
}) {
  const tokenCache = new Map();
  const inFlightAuthorizations = new Map();
  const trustedReadAuthorizations = new WeakSet();
  const trustedLocalUtilityAuthorizations = new WeakMap();

  function trustLocalUtilityAuthorization(authorization, args) {
    trustedLocalUtilityAuthorizations.set(authorization, hashCutAgentCliArgs(args));
    return authorization;
  }

  async function authorizePreparedAction({
    actionId,
    operationClass,
    authorizationBinding,
    policyDecisionDigest = null,
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
        policyDecisionDigest,
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
      || !["read", "mutation"].includes(operationClass)
      || ((operationClass === "mutation") !== (typeof policyDecisionDigest === "string" && /^sha256:[a-f0-9]{64}$/.test(policyDecisionDigest)))) {
      throw createAuthorizationError([], "AUTH_TOKEN_INVALID", "Prepared-action authorization binding is invalid.");
    }
    const authenticated = await captureAuthenticatedSdkRequest(authService, { signal });
    let payload;
    try {
      payload = await cutagentCloudService.authorizePreparedSdkAction(authenticated.accessToken, {
        actionId,
        operationClass,
        authorizationBinding: binding,
        ...(policyDecisionDigest ? { policyDecisionDigest } : {}),
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
    cwd = null,
    carrier = "cli",
    policyContext = null,
    refreshProtectedTargets = null,
    cutAgentCliCommand = null,
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
    const localUtility = NON_EDITING_LOCAL_UTILITY_COMMANDS.has(commandId);
    const commandImpact = localUtility
      ? Object.freeze({
          commandId,
          operationClass: "mutation",
          registryDigest: PRIVATE_IMPACT_REGISTRY_DIGEST,
          impact: null,
        })
      : await resolveCutAgentCliCommandImpact({
          args: normalizeArgs(args), commandId, carrier, cwd, policyContext, cutAgentCliCommand,
        });
    let policyDecision = null;
    let policyDecisionBinding = null;
    let policyImpact = null;
    if (commandImpact?.operationClass !== "read" && !localUtility) {
      if (!mutationPolicyGate) {
        throw new MutationPolicyError(
          "missing_scope",
          "A durable editing-constraint authority is required before this mutation can be authorized.",
        );
      }
      const authenticated = await captureAuthenticatedSdkRequest(authService);
      const impact = commandImpact.impact;
      policyImpact = impact;
      const preflightProtectedTargets = typeof refreshProtectedTargets === "function"
        ? await refreshProtectedTargets()
        : policyContext?.currentProtectedTargets ?? null;
      policyDecision = mutationPolicyGate.preflight({
        accountFingerprint: authenticated.accountFingerprint,
        impact,
        currentProtectedTargets: preflightProtectedTargets,
      });
      policyDecisionBinding = {
        registryDigest: policyDecision.registryDigest,
        canonicalRequestDigest: policyDecision.canonicalRequestDigest,
        referencedPayloadDigests: policyDecision.referencedPayloadDigests,
        resolvedTargetsDigest: policyDecision.resolvedTargetsDigest,
        projectLibraryId: policyDecision.projectLibraryId,
        projectId: policyDecision.projectId,
        timelineId: policyDecision.timelineId,
        projectRevision: policyDecision.projectRevision,
        timelineRevision: policyDecision.timelineRevision,
        requestId: policyDecision.requestId,
        operationId: policyDecision.operationId,
        executionId: policyDecision.executionId,
      };
      mutationPolicyGate.revalidateBeforeAuthorization(
        policyDecision.decisionId,
        policyDecisionBinding,
        typeof refreshProtectedTargets === "function"
          ? await refreshProtectedTargets()
          : policyContext?.currentProtectedTargets ?? null,
      );
    }

    const policyAuthorization = policyDecision
      ? {
          policyDecision,
          policyDecisionBinding,
          policyRevalidation: { cwd, carrier, policyContext: structuredClone(policyContext) },
          refreshProtectedTargets,
          policyImpact,
        }
      : {
          policyClassification: commandImpact,
        };

    if (!cloudManaged) {
      if (commandImpact.operationClass === "read") trustedReadAuthorizations.add(policyAuthorization);
      return localUtility
        ? trustLocalUtilityAuthorization(policyAuthorization, args)
        : policyAuthorization;
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
    const canReuseAuthorization = isReadOnlyCacheableCommand(commandId);
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
        argsSha256: payload.args_sha256 ?? hashCutAgentCliArgs(args),
        accountSubject: typeof payload.account_subject === "string" && payload.account_subject.trim()
          ? payload.account_subject.trim()
          : null,
        expiresAt: payload.expires_at ?? null,
        embeddedExecuteSha256: payload.embedded_execute_sha256 ?? null,
        ...policyAuthorization,
      };

      if (commandImpact.operationClass === "read") trustedReadAuthorizations.add(authorization);
      if (localUtility) trustLocalUtilityAuthorization(authorization, args);

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
    if (trustedReadAuthorizations.has(authorization)
      && authorization.policyClassification?.commandId === commandId
      && authorization.policyClassification?.operationClass === "read") return true;
    if (NON_EDITING_LOCAL_UTILITY_COMMANDS.has(commandId)
      && authorization?.policyClassification?.commandId === commandId
      && authorization.policyClassification.operationClass === "mutation"
      && trustedLocalUtilityAuthorizations.get(authorization) === hashCutAgentCliArgs(args)) return true;
    if (!RELEASE_BRIDGE_BUNDLE && privateCommandImpact(commandId)?.operationClass === "read") return true;
    if (!authorization?.policyDecision || !authorization?.policyDecisionBinding || !mutationPolicyGate) {
      throw new MutationPolicyError(
        "missing_scope",
        "The mutation has no current one-use policy decision.",
      );
    }
    const revalidation = authorization.policyRevalidation ?? {};
    const currentImpact = RELEASE_BRIDGE_BUNDLE
      ? authorization.policyImpact
      : lowerCutAgentCliMutationImpact({
          args: normalizeArgs(args),
          commandId,
          cwd: revalidation.cwd ?? null,
          carrier: revalidation.carrier ?? "cli",
          policyContext: revalidation.policyContext ?? null,
        });
    if (currentImpact?.status !== "mutation") {
      throw new MutationPolicyError("decision_binding_mismatch", "The mutation impact could not be reproduced at launch.");
    }
    const currentBinding = {
      ...authorization.policyDecisionBinding,
      registryDigest: currentImpact.registryDigest,
      canonicalRequestDigest: RELEASE_BRIDGE_BUNDLE
        ? mutationPolicyDigest({ commandId, args: normalizeArgs(args) })
        : currentImpact.canonicalRequestDigest,
      referencedPayloadDigests: RELEASE_BRIDGE_BUNDLE
        ? currentReferencedPayloadDigests(normalizeArgs(args), revalidation.cwd ?? null)
        : currentImpact.referencedPayloadDigests,
      resolvedTargetsDigest: mutationPolicyDigest(currentImpact.effects.map((effect) => effect.targets)),
      projectLibraryId: currentImpact.projectLibraryId,
      projectId: currentImpact.projectId ?? null,
      timelineId: currentImpact.timelineId ?? null,
      projectRevision: currentImpact.projectRevision ?? null,
      timelineRevision: currentImpact.timelineRevision ?? null,
    };
    const consume = (currentProtectedTargets) => {
      const consumed = mutationPolicyGate.consumeBeforeSpawn(
        authorization.policyDecision.decisionId,
        currentBinding,
        currentProtectedTargets,
      );
      authorization.env = {
        ...(authorization.env ?? {}),
        CUTAGENT_MUTATION_POLICY_ARGS_SHA256: hashCutAgentCliArgs(args),
        ...(currentBinding.referencedPayloadDigests.length === 1
          ? { CUTAGENT_MUTATION_POLICY_PAYLOAD_SHA256: currentBinding.referencedPayloadDigests[0] }
          : {}),
        ...(currentImpact.commandId === "version.restore"
          && typeof revalidation.policyContext?.expectedCurrentStateHash === "string"
          ? { CUTAGENT_WORKFLOW_EXPECTED_STATE_HASH: revalidation.policyContext.expectedCurrentStateHash }
          : {}),
      };
      return consumed;
    };
    return typeof authorization.refreshProtectedTargets === "function"
      ? Promise.resolve(authorization.refreshProtectedTargets()).then(consume)
      : consume(revalidation.policyContext?.currentProtectedTargets ?? null);
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
