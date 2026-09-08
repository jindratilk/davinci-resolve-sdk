import path from "node:path";
import { bridgeCliErrorFromPayload } from "../contracts/bridge-error.js";
import { buildCutAgentCliEnv, resolveCutAgentCliCommand } from "../../local/cli-runtime.mjs";
import { getSessionRuntimeEnv } from "./session-runtime-paths.js";
import { assertCutAgentCliPolicyBeforeSpawn } from "./cutagent-cli-authorization.js";
import {
  ensureJsonArgs,
  execFileAsync,
  getTimeoutMs,
  safeJsonParse,
} from "./tool-execution/shared.js";

const PROMPT_LABEL_MAX = 72;

function normalizePromptLabel(prompt) {
  const text = typeof prompt === "string" ? prompt.replace(/\s+/g, " ").trim() : "";
  if (!text) {
    return "prompt";
  }
  if (text.length <= PROMPT_LABEL_MAX) {
    return text;
  }
  return `${text.slice(0, PROMPT_LABEL_MAX - 1).trim()}...`;
}

function createError(message, details = {}) {
  const error = new Error(message);
  error.details = details;
  return error;
}

function requireCliSuccess(payload, fallbackMessage) {
  const cliError = bridgeCliErrorFromPayload(payload, { fallbackMessage });
  if (cliError) {
    throw cliError;
  }
  if (!payload || payload.ok !== true) {
    throw createError(fallbackMessage, { payload });
  }
  return payload.data;
}

function normalizeCheckpoint(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : null;
}

export function createVersionCheckpointService({
  settingsService,
  checkpointDir,
  cutAgentCliAuthorizationService = null,
  incidentReporterService = null,
} = {}) {
  const resolvedCheckpointDir = path.resolve(
    checkpointDir || path.join(process.cwd(), ".cutagent-config", "checkpoints"),
  );

  async function runCutAgentCli(args, {
    session = null,
    accessToken = null,
    cutAgentCliCommand = null,
    skipAuthorization = false,
    policyContext = null,
  } = {}) {
    const jsonArgs = ensureJsonArgs(args, true);
    const authorization = skipAuthorization
      ? null
      : await cutAgentCliAuthorizationService?.authorize?.(jsonArgs, {
        session,
        accessToken,
        cutAgentCliCommand,
        policyContext,
      });
    let stdout = "";
    try {
      assertCutAgentCliPolicyBeforeSpawn(cutAgentCliAuthorizationService, jsonArgs, authorization);
      const result = await execFileAsync(cutAgentCliCommand || resolveCutAgentCliCommand(), jsonArgs, {
        cwd:
          settingsService.getAppSettings().non_secret_runtime_preferences.managed_workspace_root
          || process.cwd(),
        encoding: "utf8",
        timeout: getTimeoutMs(settingsService),
        maxBuffer: 10 * 1024 * 1024,
        shell: false,
        env: buildCutAgentCliEnv({args: jsonArgs,
          sessionEnv: {
            ...getSessionRuntimeEnv(session),
            CUTAGENT_CHECKPOINT_DIR: resolvedCheckpointDir,
          },
          extraEnv: authorization?.env ?? null,
        }),
      });
      stdout = typeof result.stdout === "string" ? result.stdout : "";
    } catch (error) {
      stdout = typeof error?.stdout === "string" ? error.stdout : "";
      const parsedError = safeJsonParse(stdout);
      if (parsedError) {
        try {
          requireCliSuccess(parsedError, "DaVinci Resolve checkpoint command failed.");
        } catch (cliError) {
          incidentReporterService?.record?.({
            category: "cutagent_cli_failure",
            source: "bridge",
            severity: "warning",
            local_session_id: session?.id ?? null,
            error_code: cliError?.cli_error_code ?? cliError?.code ?? "version_checkpoint_failed",
            message: cliError instanceof Error ? cliError.message : "DaVinci Resolve checkpoint command failed.",
            fingerprint: [
              "version_checkpoint",
              args.join(" "),
              cliError?.cli_error_code ?? cliError?.code ?? "unknown",
            ].join(":"),
            metadata: {
              command_path: args.join(" "),
              cli_error_code: cliError?.cli_error_code ?? null,
              cli_error_details: cliError?.cli_error_details ?? null,
              cli_meta: cliError?.cli_meta ?? null,
              output_tail: stdout.slice(-1200),
            },
          });
          throw cliError;
        }
      }
      incidentReporterService?.record?.({
        category: "cutagent_cli_failure",
        source: "bridge",
        severity: "warning",
        local_session_id: session?.id ?? null,
        error_code: error?.code ?? "version_checkpoint_failed",
        message: error instanceof Error ? error.message : "DaVinci Resolve checkpoint command failed.",
        fingerprint: ["version_checkpoint", args.join(" "), error?.code ?? "exec_failed"].join(":"),
        metadata: {
          command_path: args.join(" "),
          stdout_tail: stdout.slice(-1200),
          stderr_tail: typeof error?.stderr === "string" ? error.stderr.slice(-1200) : "",
        },
      });
      throw error;
    }

    const parsed = safeJsonParse(stdout);
    if (!parsed) {
      throw createError("The CutAgent CLI version command did not return valid JSON.", {
        stdout: stdout.trim(),
        args: jsonArgs,
      });
    }
    return requireCliSuccess(parsed, "DaVinci Resolve checkpoint command failed.");
  }

  async function createCheckpoint({
    session,
    prompt = "",
    kind,
    label = "",
    promptEventId = null,
    parentCheckpointId = null,
    accessToken = null,
    cutAgentCliCommand = null,
    policyContext = null,
  }) {
    const args = [
      "version",
      "create",
      "--kind",
      kind,
      "--label",
      label || `${kind === "after_prompt" ? "After" : "Before"} prompt: ${normalizePromptLabel(prompt)}`,
    ];
    if (session?.id) {
      args.push("--session-id", session.id);
    }
    if (promptEventId) {
      args.push("--prompt-event-id", promptEventId);
    }
    if (parentCheckpointId) {
      args.push("--parent-id", parentCheckpointId);
    }

    const checkpoint = normalizeCheckpoint(await runCutAgentCli(args, {
      session, accessToken, cutAgentCliCommand, policyContext,
    }));
    if (!checkpoint?.id) {
      throw createError("CutAgent CLI returned an invalid checkpoint payload.", { checkpoint });
    }
    return checkpoint;
  }

  async function inspectCheckpoint({
    session,
    checkpointId,
    accessToken = null,
  }) {
    const id = typeof checkpointId === "string" ? checkpointId.trim() : "";
    if (!id) {
      throw new Error("Checkpoint id is required.");
    }
    const checkpoint = normalizeCheckpoint(await runCutAgentCli(["version", "inspect", id], { session, accessToken }));
    if (!checkpoint?.id) {
      throw createError("CutAgent CLI returned an invalid checkpoint payload.", { checkpoint });
    }
    return checkpoint;
  }

  return {
    checkpointDir: resolvedCheckpointDir,
    createBeforePromptCheckpoint({
      session,
      prompt,
      promptEventId,
      accessToken = null,
      cutAgentCliCommand = null,
      policyContext = null,
    }) {
      return createCheckpoint({
        session,
        prompt,
        kind: "before_prompt",
        promptEventId,
        accessToken,
        cutAgentCliCommand,
        policyContext,
      });
    },
    createAfterPromptCheckpoint({
      session,
      prompt,
      promptEventId,
      parentCheckpointId,
      accessToken = null,
      cutAgentCliCommand = null,
      policyContext = null,
    }) {
      return createCheckpoint({
        session,
        prompt,
        kind: "after_prompt",
        promptEventId,
        parentCheckpointId,
        accessToken,
        cutAgentCliCommand,
        policyContext,
      });
    },
    async restoreCheckpoint({ session, checkpointId, accessToken = null, policyContext = null }) {
      const id = typeof checkpointId === "string" ? checkpointId.trim() : "";
      if (!id) {
        throw new Error("Checkpoint id is required.");
      }
      if (!session?.id) {
        throw new Error("Session id is required to restore a checkpoint.");
      }
      const checkpoint = await inspectCheckpoint({ session, checkpointId: id, accessToken });
      if (checkpoint.session_id !== session.id) {
        throw createError("Checkpoint belongs to a different CutAgent chat.", {
          reason: "session_mismatch",
          checkpoint_id: id,
          expected_session_id: session.id,
          checkpoint_session_id: checkpoint.session_id ?? null,
        });
      }
      return runCutAgentCli(["version", "restore", id, "--session-id", session.id], {
        session, accessToken, policyContext,
      });
    },
    inspectCheckpoint,
    async getStatus({ session, accessToken = null } = {}) {
      const args = ["version", "status"];
      if (session?.id) {
        args.push("--session-id", session.id);
      }
      return runCutAgentCli(args, { session, accessToken });
    },
    async listCheckpoints({ session, accessToken = null } = {}) {
      const args = ["version", "list"];
      if (session?.id) {
        args.push("--session-id", session.id);
      }
      return runCutAgentCli(args, { session, accessToken });
    },
    async pruneSessionCheckpoints({ session, accessToken = null } = {}) {
      if (!session?.id) {
        return null;
      }
      return runCutAgentCli(["version", "prune", "--session-id", session.id], {
        session,
        accessToken,
        skipAuthorization: true,
      });
    },
  };
}
