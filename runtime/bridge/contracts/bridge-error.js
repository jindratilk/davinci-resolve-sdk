import { parseJsonValueFromText } from "./json-output.js";
import { randomUUID } from "node:crypto";
import { classifyCutAgentFailure } from "./generated/failure-recovery.js";

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function safeJsonParse(value) {
  return parseJsonValueFromText(value);
}

function normalizeMessage(value, fallback) {
  if (typeof value === "string" && value.trim()) {
    return value.trim();
  }
  return fallback;
}

function normalizeExitCode(value) {
  return Number.isInteger(value) ? value : null;
}

function normalizeCustomerErrorCode(value) {
  return value === "insufficient_credits" || value === "usage_limit_exceeded"
    ? value
    : null;
}

export function parseCliPayload(value) {
  if (isPlainObject(value)) {
    return value;
  }

  const parsed = safeJsonParse(value);
  return isPlainObject(parsed) ? parsed : null;
}

export function createBridgeCliError({
  message = "cutagent command failed.",
  cli_error_code = null,
  cli_error_details = null,
  cli_meta = null,
  exit_code = null,
  cause = null,
} = {}) {
  const error = new Error(normalizeMessage(message, "cutagent command failed."));
  error.name = "BridgeCliError";
  error.bridge_error_type = "cutagent_cli_error";
  error.code =
    typeof cli_error_code === "string" && cli_error_code.trim()
      ? cli_error_code.trim()
      : "BRIDGE_CLI_ERROR";
  error.cli_error_code =
    typeof cli_error_code === "string" && cli_error_code.trim()
      ? cli_error_code.trim()
      : null;
  error.cli_error_details = isPlainObject(cli_error_details) ? cli_error_details : null;
  error.cli_meta = isPlainObject(cli_meta) ? cli_meta : null;
  error.exit_code = normalizeExitCode(exit_code);
  if (cause != null) {
    error.cause = cause;
  }
  return error;
}

export function bridgeCliErrorFromPayload(payload, options = {}) {
  const parsed = parseCliPayload(payload);
  if (!parsed || parsed.ok !== false) {
    return null;
  }

  const payloadError = isPlainObject(parsed.error) ? parsed.error : {};
  return createBridgeCliError({
    message: normalizeMessage(payloadError.message, options.fallbackMessage ?? "cutagent command failed."),
    cli_error_code:
      typeof payloadError.code === "string" && payloadError.code.trim()
        ? payloadError.code.trim()
        : null,
    cli_error_details: isPlainObject(payloadError.details) ? payloadError.details : null,
    cli_meta: isPlainObject(parsed.meta) ? parsed.meta : null,
    exit_code:
      normalizeExitCode(options.exit_code)
      ?? normalizeExitCode(parsed.exit_code)
      ?? normalizeExitCode(parsed?.meta?.exit_code),
    cause: options.cause ?? null,
  });
}

export function buildCliProtocolViolationError(details = {}) {
  return createBridgeCliError({
    message: "CutAgent CLI protocol violation.",
    cli_error_code: "CLI_PROTOCOL_VIOLATION",
    cli_error_details: details,
    cli_meta: null,
    exit_code: normalizeExitCode(details?.exit_code),
  });
}

export function buildCliTimeoutError(details = {}) {
  return createBridgeCliError({
    message: "CutAgent CLI did not respond before the timeout.",
    cli_error_code: "CUTAGENT_CLI_TIMEOUT",
    cli_error_details: details,
    cli_meta: null,
    exit_code: null,
  });
}

export function extractBridgeErrorData(error, fallbackMessage = "Operation failed.") {
  const message = normalizeMessage(error?.message, fallbackMessage);
  const cliErrorCode =
    typeof error?.cli_error_code === "string" && error.cli_error_code.trim()
      ? error.cli_error_code.trim()
      : error?.bridge_error_type === "cutagent_cli_error"
        && typeof error?.code === "string"
        && error.code.trim()
        ? error.code.trim()
        : null;

  const cliErrorDetails = isPlainObject(error?.cli_error_details)
    ? error.cli_error_details
    : error?.bridge_error_type === "cutagent_cli_error" && isPlainObject(error?.details)
      ? error.details
      : null;

  const cliMeta = isPlainObject(error?.cli_meta)
    ? error.cli_meta
    : error?.bridge_error_type === "cutagent_cli_error" && isPlainObject(error?.meta)
      ? error.meta
      : null;

  return {
    message,
    cli_error_code: cliErrorCode,
    cli_error_details: cliErrorDetails,
    cli_meta: cliMeta,
    exit_code: normalizeExitCode(error?.exit_code),
  };
}

export function buildBridgeErrorPayload(error, fallbackMessage = "Operation failed.", correlation = {}) {
  const details = extractBridgeErrorData(error, fallbackMessage);
  const payload = {
    message: details.message,
  };

  const customerErrorCode = normalizeCustomerErrorCode(error?.cloudErrorCode ?? error?.error_code);
  const publicFailure = isPlainObject(error?.public_failure) ? error.public_failure : null;
  const readinessDetails = isPlainObject(error?.readiness_details) ? error.readiness_details : null;
  if (publicFailure?.code === "DEPENDENCY_UNAVAILABLE") {
    payload.error_code = "DEPENDENCY_UNAVAILABLE";
    payload.failure_kind = "dependency_unavailable";
    payload.recovery = ["update_required"];
    payload.usage_state = "not_reserved";
    payload.possible_mutation = "none";
    payload.retry_safe = false;
    payload.readback_required = false;
    if (readinessDetails) {
      payload.failure_details = readinessDetails;
    }
  }
  if (customerErrorCode) {
    payload.error_code = customerErrorCode;
  }

  if (details.cli_error_code) {
    payload.cli_error_code = details.cli_error_code;
  }
  if (details.cli_error_details) {
    payload.cli_error_details = details.cli_error_details;
  }
  if (details.cli_meta) {
    payload.cli_meta = details.cli_meta;
  }
  if (details.exit_code !== null) {
    payload.exit_code = details.exit_code;
  }

  const incidentId = typeof error?.incident_id === "string" && error.incident_id.trim()
    ? error.incident_id.trim().slice(0, 256)
    : `incident_${randomUUID().replaceAll("-", "")}`;
  payload.failure = classifyCutAgentFailure({
    raw: error,
    incidentId,
    correlation: {
      requestId: typeof correlation.requestId === "string" ? correlation.requestId : null,
      executionId: typeof correlation.executionId === "string" && correlation.executionId.trim()
        ? correlation.executionId.trim().slice(0, 256) : `execution_${incidentId.slice(0, 246)}`,
      operationId: typeof correlation.operationId === "string" ? correlation.operationId : null,
      runId: typeof correlation.runId === "string" ? correlation.runId : null,
      providerRequestId: null,
    },
    ...(publicFailure?.usage === "not_reserved" ? { usageState: "not_reserved" } : {}),
    ...(typeof correlation.possibleMutation === "string"
      ? { possibleMutation: correlation.possibleMutation }
      : publicFailure?.possibleMutation === "none" ? { possibleMutation: "none" } : {}),
  });

  return payload;
}

export function sanitizePublicAgentErrorEvent(event) {
  if (event?.type !== "agent:error" && event?.type !== "subagent:error") return event;
  return {
    ...event,
    message: event.type === "subagent:error" ? "Subagent failed." : "CutAgent request failed.",
  };
}

export function buildToolErrorEnvelope(error, fallbackMessage = "Tool execution failed.") {
  const details = extractBridgeErrorData(error, fallbackMessage);
  const payload = {
    ok: false,
    data: null,
    error: {
      message: details.message,
    },
  };

  if (details.cli_error_code) {
    payload.error.code = details.cli_error_code;
  }
  if (details.cli_error_details) {
    payload.error.details = details.cli_error_details;
  }
  if (details.cli_meta) {
    payload.meta = details.cli_meta;
  }
  if (details.exit_code !== null) {
    payload.exit_code = details.exit_code;
  }

  return payload;
}
