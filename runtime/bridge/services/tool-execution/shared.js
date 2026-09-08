import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { parseJsonValueFromText } from "../../contracts/json-output.js";

export const execFileAsync = promisify(execFile);

export function getTimeoutMs(settingsService) {
  const runtime = settingsService.getAppSettings();
  return Math.max(runtime.non_secret_runtime_preferences.cutagent_cli_timeout_seconds, 5) * 1000;
}

export function formatCliCommand(args) {
  return `cutagent ${args.join(" ")}`;
}

export function ensureJsonArgs(args, expectJson) {
  if (!expectJson) {
    return args;
  }

  if (args.includes("-j") || args.includes("--json")) {
    return args;
  }

  return [...args, "-j"];
}

export function safeJsonParse(text) {
  return parseJsonValueFromText(text);
}

export function isObjectRecord(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function requireSession(options) {
  const session = options?.session ?? null;
  if (!session?.id) {
    throw new Error("This tool requires an active session context.");
  }
  return session;
}
