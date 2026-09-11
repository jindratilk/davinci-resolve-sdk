import { CUTAGENT_SDK_SESSION_HEADER, CUTAGENT_SDK_WIRE_PROTOCOL, CUTAGENT_SDK_WORKFLOW_PATH } from "../contracts/generated/sdk-runtime.js";
import {
  SDK_PUBLIC_ERROR_KIND_BY_CODE,
  sdkWorkflowControlFailureSchema,
  sdkWorkflowControlRequestSchema,
  sdkWorkflowControlResponseSchema,
} from "../contracts/generated/sdk-operations.js";
import { captureAuthenticatedSdkRequest, assertAuthenticatedSdkRequestCurrent } from "../services/sdk-authenticated-request.js";
import { runWithSdkOwnerSession } from "../services/sdk-owner-session-context.js";

function failure(code, requestId, overrides = {}) {
  const workflowId = overrides.workflowId;
  return sdkWorkflowControlFailureSchema.parse({
    ok: false,
    protocolVersion: CUTAGENT_SDK_WIRE_PROTOCOL,
    requestId,
    ...(workflowId ? { workflowId } : {}),
    error: {
      kind: SDK_PUBLIC_ERROR_KIND_BY_CODE[code],
      code,
      message: "CutAgent could not complete the workflow control request.",
      retrySafe: false,
      possibleMutation: "none",
      usage: "not_reserved",
      recovery: ["restart_runtime"],
      recoveryGuidance: ["Reattach the workflow before continuing."],
      readbackRequired: false,
      requestId,
      ...(workflowId ? { workflowId } : {}),
      ...overrides,
    },
  });
}

export function registerSdkWorkflowRoute({ app, sdkRuntimeService, authService, sdkWorkflowAuthority, sessionRepo = null }) {
  app.post(CUTAGENT_SDK_WORKFLOW_PATH, async (req, res) => {
    const parsed = sdkWorkflowControlRequestSchema.safeParse(req.body);
    if (!parsed.success) return res.status(400).json({ ok: false, error: { code: "INVALID_REQUEST", message: "Invalid workflow request." } });
    const request = parsed.data;
    if (request.deadlineAtMs <= Date.now()) return res.status(504).json(failure("RUNTIME_TIMEOUT", request.requestId, {
      message: "The workflow control deadline expired before reaching the authority.",
      retrySafe: true,
      retrySafetyProof: { basis: request.operation === "workflow.get" ? "read_only" : "pre_execution" },
      recovery: ["retry"],
      recoveryGuidance: ["Retry with the same workflow or idempotency identity."],
      ...("workflowId" in request ? { workflowId: request.workflowId } : {}),
    }));
    const token = typeof req.headers[CUTAGENT_SDK_SESSION_HEADER] === "string" ? req.headers[CUTAGENT_SDK_SESSION_HEADER].trim() : "";
    let snapshot = null;
    try {
      const authenticated = await captureAuthenticatedSdkRequest(authService);
      if (!sdkRuntimeService.validateSession({ sessionId: request.sessionId, sessionToken: token, accountFingerprint: authenticated.accountFingerprint })) throw new Error("session");
      const ownerSessionId = sdkRuntimeService.resolveOwnerSessionId?.({ sessionId: request.sessionId, sessionToken: token, accountFingerprint: authenticated.accountFingerprint }) ?? null;
      const ownerSession = ownerSessionId ? sessionRepo?.getSession?.(ownerSessionId) ?? null : null;
      if (ownerSessionId && !ownerSession) throw Object.assign(new Error("The owning CutAgent chat is unavailable."), { code: "SDK_OWNER_SESSION_UNAVAILABLE" });
      const assertRequestCurrent = () => {
        assertAuthenticatedSdkRequestCurrent(authService, authenticated);
        if (!sdkRuntimeService.validateSession({ sessionId: request.sessionId, sessionToken: token, accountFingerprint: authenticated.accountFingerprint, touch: false })) throw new Error("session");
      };
      const execute = async () => {
        assertRequestCurrent();
        if (request.operation === "workflow.managed.start") snapshot = await sdkWorkflowAuthority.beginManaged({ accountFingerprint: authenticated.accountFingerprint, accessToken: authenticated.accessToken, sdkSessionId: request.sessionId, binding: request.binding, cancellationRequested: request.cancellationRequested, assertRequestCurrent, deadlineAtMs: request.deadlineAtMs });
        else if (request.operation === "workflow.managed.wait") snapshot = await sdkWorkflowAuthority.waitManaged({ accountFingerprint: authenticated.accountFingerprint, accessToken: authenticated.accessToken, sdkSessionId: request.sessionId, workflowId: request.workflowId, assertRequestCurrent });
        else if (request.operation === "workflow.create") snapshot = await sdkWorkflowAuthority.create({ accountFingerprint: authenticated.accountFingerprint, accessToken: authenticated.accessToken, sdkSessionId: request.sessionId, binding: request.binding, deadlineAtMs: request.deadlineAtMs });
        else if (request.operation === "workflow.get") snapshot = await sdkWorkflowAuthority.get({ accountFingerprint: authenticated.accountFingerprint, workflowId: request.workflowId, assertRequestCurrent });
        else if (request.operation === "workflow.step.reserve") snapshot = sdkWorkflowAuthority.reserve({ accountFingerprint: authenticated.accountFingerprint, workflowId: request.workflowId, name: request.name });
        else if (request.operation === "workflow.step.attach") snapshot = await sdkWorkflowAuthority.attach({ accountFingerprint: authenticated.accountFingerprint, workflowId: request.workflowId, name: request.name, operationId: request.operationId, assertRequestCurrent });
        else if (request.operation === "workflow.step.observe") snapshot = await sdkWorkflowAuthority.observe({ accountFingerprint: authenticated.accountFingerprint, accessToken: authenticated.accessToken, workflowId: request.workflowId, name: request.name, assertRequestCurrent });
        else if (request.operation === "workflow.step.fail_before_mutation") snapshot = await sdkWorkflowAuthority.failBeforeMutation({ accountFingerprint: authenticated.accountFingerprint, accessToken: authenticated.accessToken, workflowId: request.workflowId, name: request.name });
        else if (request.operation === "workflow.fail") snapshot = await sdkWorkflowAuthority.fail({ accountFingerprint: authenticated.accountFingerprint, accessToken: authenticated.accessToken, workflowId: request.workflowId });
        else if (request.operation === "workflow.complete") snapshot = sdkWorkflowAuthority.complete({ accountFingerprint: authenticated.accountFingerprint, workflowId: request.workflowId });
        else snapshot = await sdkWorkflowAuthority.interrupt({ accountFingerprint: authenticated.accountFingerprint, workflowId: request.workflowId, assertRequestCurrent });
        assertRequestCurrent();
      };
      if (ownerSession) await runWithSdkOwnerSession(ownerSession, execute); else await execute();
      return res.json(sdkWorkflowControlResponseSchema.parse({ ok: true, protocolVersion: CUTAGENT_SDK_WIRE_PROTOCOL, requestId: request.requestId, operation: request.operation, snapshot }));
    } catch (error) {
      if (error?.code === "SDK_OWNER_SESSION_UNAVAILABLE") {
        try { sdkRuntimeService.closeSession({ sessionId: request.sessionId, sessionToken: token }); } catch { /* public failure stays sanitized */ }
        return res.status(409).json(failure("CONNECTION_CLOSED", request.requestId, {
          message: "The CutAgent chat that owns this SDK session is unavailable.",
          recovery: ["reconnect"],
          recoveryGuidance: ["Reconnect from the owning CutAgent chat before continuing the workflow."],
        }));
      }
      const admissionTimedOut = error?.name === "TimeoutError"
        && (request.operation === "workflow.create" || request.operation === "workflow.managed.start")
        && !error?.workflowId
        && !snapshot?.workflowId;
      if (admissionTimedOut) {
        return res.status(504).json(failure("RUNTIME_TIMEOUT", request.requestId, {
          message: "The workflow admission deadline expired before execution.",
          retrySafe: true,
          retrySafetyProof: { basis: "pre_execution" },
          possibleMutation: "none",
          usage: "not_reserved",
          recovery: ["retry"],
          recoveryGuidance: ["Retry with the same idempotency identity."],
          readbackRequired: false,
          ...(request.binding?.idempotencyKey ? { idempotencyKey: request.binding.idempotencyKey } : {}),
        }));
      }
      const code = ({
        OPERATION_EXPIRED: "OPERATION_EXPIRED",
        IDEMPOTENCY_CONFLICT: "IDEMPOTENCY_CONFLICT",
        WORKFLOW_RECOVERY_LINEAGE_UNPROVEN: "RECOVERY_FAILED",
        WORKFLOW_RESTORE_VERIFICATION_FAILED: "VERIFICATION_FAILED",
      })[error?.code] ?? "RUNTIME_UNAVAILABLE";
      const uncertain = new Set([
        "workflow.get",
        "workflow.create",
        "workflow.managed.start",
        "workflow.managed.wait",
        "workflow.step.attach",
        "workflow.step.observe",
        "workflow.step.fail_before_mutation",
        "workflow.fail",
        "workflow.interrupt",
      ]).has(request.operation);
      const workflowId = error?.workflowId ?? snapshot?.workflowId ?? request.workflowId;
      const managedControl = request.operation === "workflow.managed.start" || request.operation === "workflow.managed.wait";
      const preEffectConflict = code === "IDEMPOTENCY_CONFLICT"
        && (!managedControl || (!workflowId && (error?.admissionState === "not_admitted" || request.operation === "workflow.managed.start")));
      return res.status(code === "IDEMPOTENCY_CONFLICT" ? 409 : code === "OPERATION_EXPIRED" ? 410 : 503).json(failure(code, request.requestId, {
        message: error?.message || "The workflow authority is unavailable.",
        possibleMutation: preEffectConflict ? "none" : uncertain ? "unknown" : "none",
        usage: preEffectConflict ? "not_reserved" : uncertain ? "unknown" : "not_reserved",
        recovery: preEffectConflict ? ["inspect_state"]
          : uncertain ? ["inspect_state", "manual_recovery"] : ["restart_runtime"],
        ...(managedControl ? { recoveryGuidance: ["Reattach with the same WorkflowId or idempotency key and inspect authoritative workflow and timeline state before retrying."] } : {}),
        readbackRequired: preEffectConflict ? false : uncertain,
        ...(workflowId ? { workflowId } : {}),
        ...(error?.idempotencyKey || request.binding?.idempotencyKey ? { idempotencyKey: error?.idempotencyKey ?? request.binding.idempotencyKey } : {}),
        ...(code === "RECOVERY_FAILED" ? { recoveryOutcome: { status: "failed", summary: "Automatic workflow recovery could not be proven.", manualRecoveryRequired: true } } : {}),
      }));
    }
  });
}
