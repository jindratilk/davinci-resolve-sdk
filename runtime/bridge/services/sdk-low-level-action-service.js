import Ajv2020 from "ajv/dist/2020.js";
import { z } from "zod";
import {CUTAGENT_PREPARED_ACTION_ACTION_METADATA} from "../contracts/sdk-prepared-action-metadata.generated.js";
import { SDK_LOW_LEVEL_RUNTIME_BINDINGS } from "./sdk-low-level-runtime.generated.js";
import { issueCutAgentCliBrokerEnvironment } from "./cutagent-cli-broker-grant.js";

const ajv = new Ajv2020({ allErrors: true, strict: true });
const bindingByAction = new Map(SDK_LOW_LEVEL_RUNTIME_BINDINGS.map((binding) => [binding.actionId, binding]));
const validators = new Map();
const FORBIDDEN_RESULT_KEYS = new Set([
  "argv", "args", "command", "commandargs", "commandargv", "commandid", "commandline",
  "commandpath", "executable", "executablepath", "engine", "route", "db", "dbid", "dbpath",
  "database", "databaseid", "databasepath", "backup", "backuppath", "env", "envvars",
  "environment", "environmentvariables", "sourcefile", "sourcefilepath", "functionname",
  "implementation", "implementationdetail", "implementationdetails", "internal", "internalmetadata",
  "diagnostic", "diagnostics", "diagnosticpath", "buildpath", "runtimepath",
  "workingdirectory", "workingdirectorypath",
]);
const FORBIDDEN_RESULT_LEADING_TOKENS = new Set([
  "argv", "args", "command", "executable", "engine", "route", "db", "database", "backup",
  "env", "environment", "function", "implementation", "internal", "diagnostic", "diagnostics",
  "debug", "build", "runtime",
]);
const PATH_VALUE = /(?:^|\s)(?:\/|~(?:\/|$)|[A-Za-z]:[\\/]|\\\\|file:)/u;
const ARRAY_LOCATION_SEGMENT = Symbol("sdk-low-level-array-location");
const MAX_RESULT_BYTES = 2 * 1024 * 1024;
const PUBLIC_FAILURES = Object.freeze({
  AUTH_REQUIRED: ["AUTHENTICATION_REQUIRED", "authentication_required", ["sign_in"]],
  AUTHENTICATION_REQUIRED: ["AUTHENTICATION_REQUIRED", "authentication_required", ["sign_in"]],
  SUBSCRIPTION_REQUIRED: ["SUBSCRIPTION_REQUIRED", "subscription_required", ["contact_support"]],
  CAPABILITY_UNAVAILABLE: ["CAPABILITY_UNAVAILABLE", "capability_unavailable", ["update_required"]],
  TARGET_NOT_FOUND: ["TARGET_NOT_FOUND", "target_not_found", ["inspect_state"]],
  AMBIGUOUS_TARGET: ["AMBIGUOUS_TARGET", "ambiguous_target", ["inspect_state"]],
  STALE_REVISION: ["STALE_REVISION", "stale_revision", ["inspect_state"]],
  USAGE_EXHAUSTED: ["USAGE_EXHAUSTED", "usage_exhausted", ["contact_support"]],
  REQUEST_TOO_LARGE: ["REQUEST_TOO_LARGE", "request_too_large", ["contact_support"]],
  OUTPUT_LIMIT_REACHED: ["OUTPUT_LIMIT_REACHED", "output_limit_reached", ["contact_support"]],
  RUNTIME_UNAVAILABLE: ["RUNTIME_UNAVAILABLE", "runtime_unavailable", ["restart_runtime"]],
  RUNTIME_TIMEOUT: ["RUNTIME_TIMEOUT", "runtime_timeout", ["retry"]],
  RUNTIME_CRASHED: ["RUNTIME_CRASHED", "runtime_crashed", ["restart_runtime"]],
  DEPENDENCY_UNAVAILABLE: ["DEPENDENCY_UNAVAILABLE", "dependency_unavailable", ["retry"]],
  TEMPORARY_PROVIDER_FAILURE: ["TEMPORARY_PROVIDER_FAILURE", "temporary_provider_failure", ["retry"]],
  CANCELLED: ["CANCELLED", "cancelled", ["continue"]],
});

function validator(binding) {
  let validate = validators.get(binding.actionId);
  if (!validate) { validate = ajv.compile(binding.inputSchema); validators.set(binding.actionId, validate); }
  return validate;
}

function resultKeyTokens(key) {
  return String(key)
    .replace(/([A-Z]+)([A-Z][a-z])/gu, "$1 $2")
    .replace(/([a-z0-9])([A-Z])/gu, "$1 $2")
    .split(/[^A-Za-z0-9]+/gu)
    .filter(Boolean)
    .map((token) => token.toLowerCase());
}

function isForbiddenResultKey(key) {
  const normalized = String(key).replace(/[_-]/gu, "").toLowerCase();
  const tokens = resultKeyTokens(key);
  return FORBIDDEN_RESULT_KEYS.has(normalized)
    || FORBIDDEN_RESULT_LEADING_TOKENS.has(tokens[0])
    || (tokens[0] === "source" && tokens[1] === "file")
    || (tokens[0] === "working" && tokens[1] === "directory");
}

function isStructuralPathLocation(location) {
  const key = [...location].reverse().find((segment) => typeof segment === "string");
  const tokens = resultKeyTokens(key ?? "");
  return ["path", "paths", "file", "files", "directory", "directories"].includes(tokens.at(-1));
}

function matchesRecursivePublicPath(location, rule) {
  if (location.at(-1) !== rule.pathKey) return false;
  const ancestors = location.slice(0, -1);
  if (ancestors.length % 2 !== 0) return false;
  for (let index = 0; index < ancestors.length; index += 2) {
    if (ancestors[index] !== rule.childrenKey || ancestors[index + 1] !== ARRAY_LOCATION_SEGMENT) return false;
  }
  return true;
}

function isPublicPath(location, publicPathProjection) {
  return publicPathProjection.patterns.some((pattern) => pattern.length === location.length
    && pattern.every((segment, index) => segment === "*"
      ? location[index] === ARRAY_LOCATION_SEGMENT
      : segment === location[index]))
    || publicPathProjection.recursiveRules.some((rule) => matchesRecursivePublicPath(location, rule));
}

export function lowerSdkLowLevelAction(actionId, input) {
  const binding = bindingByAction.get(actionId);
  if (!binding) throw Object.assign(new Error("The typed action has no reviewed private CLI lowering."), { code: "CAPABILITY_UNAVAILABLE" });
  const validate = validator(binding);
  if (!validate(input)) throw Object.assign(new TypeError("Typed low-level action input violated its authoritative schema."), { validationErrors: validate.errors });
  return Object.freeze({ actionId, input: Object.freeze({ ...input }) });
}

function sanitize(value, publicPathProjection, location = [], depth = 0) {
  if (depth > 16) throw new Error("CutAgent CLI result nesting exceeded the SDK carrier limit.");
  if (value === null || typeof value === "boolean" || typeof value === "number") return value;
  if (typeof value === "string") {
    const authorizedPath = isPublicPath(location, publicPathProjection);
    if (!authorizedPath && (isStructuralPathLocation(location) || PATH_VALUE.test(value))) return "[redacted]";
    return value.slice(0, 65_536);
  }
  if (Array.isArray(value)) {
    if (value.length > 10_000) throw new Error("CutAgent CLI result collection exceeded the SDK carrier limit.");
    return value.map((entry) => sanitize(entry, publicPathProjection, [...location, ARRAY_LOCATION_SEGMENT], depth + 1));
  }
  if (!value || typeof value !== "object") return String(value);
  const entries = Object.entries(value);
  if (entries.length > 2_000) throw new Error("CutAgent CLI result object exceeded the SDK carrier limit.");
  return Object.fromEntries(entries.filter(([key]) => !isForbiddenResultKey(key)).map(([key, entry]) => [key, sanitize(entry, publicPathProjection, [...location, key], depth + 1)]));
}

export function sanitizeSdkLowLevelReadResult(actionId, value) {
  const binding = bindingByAction.get(actionId);
  const prepared = CUTAGENT_PREPARED_ACTION_ACTION_METADATA[actionId];
  if (binding?.operationClass !== "read" && prepared?.operationClass !== "read") {
    throw new Error("The typed action has no reviewed read-result projection.");
  }
  return sanitize(value, {
    patterns: binding?.publicPathPatterns ?? [],
    recursiveRules: binding?.publicRecursivePathRules ?? [],
  });
}

function readFailure(error) {
  const reported = String(error?.cli_error_code ?? error?.code ?? "");
  const known = PUBLIC_FAILURES[reported];
  if (!known) {
    return {
      kind: "operation_failed", code: "OPERATION_FAILED",
      message: "The typed CutAgent CLI read did not produce a valid terminal result.",
      retrySafe: false, possibleMutation: "none", usage: "unknown", recovery: ["retry"],
      recoveryGuidance: ["Retry the read after confirming that the runtime is available."], readbackRequired: false,
    };
  }
  const [code, kind, recovery] = known;
  const preExecution = new Set(["AUTHENTICATION_REQUIRED", "SUBSCRIPTION_REQUIRED", "CAPABILITY_UNAVAILABLE", "USAGE_EXHAUSTED", "REQUEST_TOO_LARGE"]).has(code);
  return {
    kind, code,
    message: `The typed CutAgent CLI read failed with ${code}.`,
    retrySafe: false,
    possibleMutation: "none",
    usage: preExecution ? "not_reserved" : "unknown",
    recovery,
    recoveryGuidance: [`Follow the ${recovery[0]} recovery action before retrying this read.`],
    readbackRequired: false,
    cause: { code: reported, message: "CutAgent CLI reported this stable public error code." },
  };
}

async function projectTimelineMatteList(payload, input, liveInspectionService) {
  if (typeof liveInspectionService?.readWithMutationGuard !== "function"
    || typeof liveInspectionService?.resolveMediaPoolPrivateFolder !== "function") {
    throw new Error("Timeline matte reads require authoritative Media Pool folder inspection.");
  }
  const nativeId = typeof payload?.folder_native_id === "string" ? payload.folder_native_id.trim() : "";
  const mattes = payload?.mattes;
  if (!nativeId || !Array.isArray(mattes)) throw new Error("CutAgent CLI omitted the timeline matte folder identity or matte list.");
  const inspected = await liveInspectionService.readWithMutationGuard(
    {operation: "project.context"},
    {deadlineAtMs: Date.now() + 60_000},
  );
  const projectId = inspected.value?.project?.id;
  if (typeof projectId !== "string" || !projectId) throw new Error("Timeline matte read lacks a current project identity.");
  const folder = await liveInspectionService.resolveMediaPoolPrivateFolder(
    projectId,
    nativeId,
    null,
    {deadlineAtMs: Date.now() + 60_000},
  );
  const parts = String(input.folder).split("/").map((part) => part.trim()).filter(Boolean);
  const reportedParts = typeof payload.folder === "string"
    ? payload.folder.split("/").map((part) => part.trim()).filter(Boolean)
    : [];
  if (!parts.length || JSON.stringify(reportedParts) !== JSON.stringify(parts) || parts.at(-1) !== folder.name) {
    throw new Error("Timeline matte read resolved a different Media Pool folder.");
  }
  return {
    folder: {
      kind: "media_folder",
      id: folder.stableId,
      addressability: "addressable",
      name: folder.name,
      folderName: parts.length > 1 ? parts.slice(0, -1).join("/") : "Media Pool root",
    },
    matteCount: mattes.length,
  };
}

async function renderJobStatus(input, liveInspectionService) {
  if (typeof liveInspectionService?.read !== "function") {
    throw Object.assign(new Error("Render job status requires authoritative live inspection."), {code: "CAPABILITY_UNAVAILABLE"});
  }
  const options = {deadlineAtMs: Date.now() + 60_000};
  const context = await liveInspectionService.read({operation: "project.context"}, options);
  const projectId = context?.project?.id;
  if (typeof projectId !== "string" || !projectId) {
    throw Object.assign(new Error("Render job status requires a current project."), {code: "TARGET_NOT_FOUND"});
  }
  let cursor = null;
  const matches = [];
  do {
    const page = await liveInspectionService.read({
      operation: "render.queue", projectId, pageSize: 100, cursor,
    }, options);
    if (!page || page.projectId !== projectId || !Array.isArray(page.jobs)) {
      throw new Error("Render job status received a malformed queue snapshot.");
    }
    matches.push(...page.jobs.filter((job) => job?.id === input.jobId));
    cursor = page.nextCursor;
  } while (cursor !== null);
  if (matches.length !== 1) {
    throw Object.assign(new Error("Render job status requires one exact current queue identity."), {
      code: matches.length === 0 ? "TARGET_NOT_FOUND" : "AMBIGUOUS_TARGET",
    });
  }
  const selected = matches[0];
  const snapshot = await liveInspectionService.read({
    operation: "render.job_status",
    projectId,
    queueRevision: selected.queueRevision,
    jobId: selected.id,
  }, options);
  const job = snapshot?.job;
  const status = job?.status?.value;
  if (job?.id !== input.jobId || typeof job.name !== "string" || typeof status !== "string" || !status
    || typeof job.progressPercent !== "number" || !Number.isFinite(job.progressPercent)
    || job.progressPercent < 0 || job.progressPercent > 100) {
    throw new Error("Render job status received malformed exact-job readback.");
  }
  return {
    job: {
      jobId: job.id,
      name: job.name,
      status,
      completionPercent: job.progressPercent,
    },
  };
}

export const sdkLowLevelRawResultSchema = z.object({
  actionId: z.string().regex(/^cutagent\.action\.[a-z0-9_.]+$/),
  operationClass: z.literal("read"),
  data: z.unknown(),
  sanitized: z.literal(true),
}).strict();

export function createSdkLowLevelActions({ resolveService, liveInspectionService, voiceoverBroker = null, excludedActionIds = [], activatedActionIds = SDK_LOW_LEVEL_ACTION_IDS }) {
  if (typeof resolveService?.executeSdkLowLevelAction !== "function") throw new TypeError("Typed low-level actions require the private CutAgent CLI action carrier.");
  const excluded = new Set(excludedActionIds);
  const activated = new Set(activatedActionIds);
  return Object.fromEntries(SDK_LOW_LEVEL_RUNTIME_BINDINGS.filter((binding) => activated.has(binding.actionId) && !excluded.has(binding.actionId)).map((binding) => [binding.actionId, {
    inputSchema: { parse(input) { lowerSdkLowLevelAction(binding.actionId, input); return input; } },
    resultSchema: sdkLowLevelRawResultSchema,
    idempotency: "optional",
    async reconcile() {
      return {
        status: "failed",
        possibleMutation: "none",
        usage: "unknown",
        failure: {
          kind: "operation_failed",
          code: "OPERATION_FAILED",
          message: "The read was interrupted before a terminal result was retained.",
          retrySafe: false,
          possibleMutation: "none",
          usage: "unknown",
          recovery: ["retry"],
          recoveryGuidance: ["Retry the read after reconnecting to the CutAgent runtime."],
          readbackRequired: false,
        },
      };
    },
    async execute(context, normalized) {
      const input = normalized;
      const request = lowerSdkLowLevelAction(binding.actionId, input);
      try {
        const executionOptions = {
          carrier: "sdk",
        };
        if (binding.actionId === "cutagent.action.audio.voice_list") {
          executionOptions.issueBrokerEnvironment = ({ authorization, args }) => issueCutAgentCliBrokerEnvironment({
            broker: voiceoverBroker,
            authorization,
            args,
            commandId: "audio.voice_list",
            authorizationCommandId: "sdk.low_level.read",
            input,
          });
        }
        const rawPayload = binding.actionId === "cutagent.action.render.job_status"
          ? await renderJobStatus(input, liveInspectionService)
          : binding.actionId === "cutagent.action.project.folders.list"
          ? await liveInspectionService?.readProjectFolderInventory(executionOptions)
          : await resolveService.executeSdkLowLevelAction(request, {
              ...executionOptions,
              ...(binding.actionId === "cutagent.action.media.timeline_matte.list" ? {
                extraEnv: {...(executionOptions.extraEnv ?? {}), CUTAGENT_SDK_TIMELINE_MATTE_IDENTITY: "1"},
              } : {}),
            });
        if (binding.actionId === "cutagent.action.project.folders.list" && rawPayload === undefined) {
          throw new Error("Project-folder inventory requires the exact live-inspection producer.");
        }
        const payload = binding.actionId === "cutagent.action.media.timeline_matte.list"
          ? await projectTimelineMatteList(rawPayload, input, liveInspectionService)
          : rawPayload;
        const data = sanitizeSdkLowLevelReadResult(binding.actionId, payload);
        const result = sdkLowLevelRawResultSchema.parse({ actionId: binding.actionId, operationClass: binding.operationClass, data, sanitized: true });
        if (Buffer.byteLength(JSON.stringify(result), "utf8") > MAX_RESULT_BYTES) throw new Error("Sanitized CutAgent CLI result exceeded the SDK carrier limit.");
        return { status: "succeeded", result, possibleMutation: "none", usage: "consumed", verification: { outcome: "not_performed", summary: "Read-only CutAgent CLI action completed.", evidence: [], protectedStatePreserved: null } };
      } catch (error) {
        const failure = readFailure(error);
        return { status: "failed", possibleMutation: "none", usage: failure.usage, failure };
      }
    },
  }]));
}

export const SDK_LOW_LEVEL_ACTION_IDS = Object.freeze(SDK_LOW_LEVEL_RUNTIME_BINDINGS.map((binding) => binding.actionId));
