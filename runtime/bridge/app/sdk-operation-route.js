import { CUTAGENT_SDK_OPERATION_PATH, CUTAGENT_SDK_SESSION_HEADER, CUTAGENT_SDK_WIRE_PROTOCOL } from "../contracts/generated/sdk-runtime.js";
import {
  SDK_PUBLIC_ERROR_KIND_BY_CODE,
  sdkOperationControlFailureSchema,
  sdkOperationControlRequestSchema,
  sdkOperationControlSuccessSchema,
} from "../contracts/generated/sdk-operations.js";
import { sdkRequestIdSchema } from "../contracts/generated/sdk-identities.js";
import {
  assertAuthenticatedSdkRequestCurrent,
  captureAuthenticatedSdkRequest,
} from "../services/sdk-authenticated-request.js";
import { SdkOperationAuthorityError } from "../services/sdk-operation-authority.js";

function failure(code, requestId, overrides = {}) {
  return sdkOperationControlFailureSchema.parse({
    ok: false,
    protocolVersion: CUTAGENT_SDK_WIRE_PROTOCOL,
    requestId,
    error: {
      kind: SDK_PUBLIC_ERROR_KIND_BY_CODE[code],
      code,
      message: "CutAgent could not complete the SDK operation control request.",
      retrySafe: false,
      possibleMutation: "none",
      usage: "not_reserved",
      recovery: ["contact_support"],
      recoveryGuidance: ["Reconnect to CutAgent and inspect the original operation before creating replacement work."],
      readbackRequired: false,
      requestId,
      ...overrides,
    },
  });
}

function revoke(sdkRuntimeService, sessionId, sessionToken) {
  try { sdkRuntimeService.closeSession({ sessionId, sessionToken }); } catch { /* sanitized failure remains authoritative */ }
}

function sessionChangedError() {
  const error = new Error("The SDK session changed during operation control.");
  error.code = "SDK_SESSION_CHANGED";
  return error;
}

/** Dedicated authenticated control plane for the durable SDK authority. */
export function registerSdkOperationRoute({
  app,
  sdkRuntimeService,
  authService,
  sdkOperationAuthority,
  sdkOperationReady = Promise.resolve(),
  sessionRepo = null,
}) {
  app.post(CUTAGENT_SDK_OPERATION_PATH, async (req, res) => {
    const parsed = sdkOperationControlRequestSchema.safeParse(req.body);
    if (!parsed.success) {
      const requestId = sdkRequestIdSchema.safeParse(req.body?.requestId);
      if (requestId.success) {
        return res.status(400).json(failure("INVALID_REQUEST", requestId.data, {
          message: "The SDK operation request is invalid.",
          recovery: ["update_required"],
          recoveryGuidance: ["Update the SDK request to the current typed action contract before retrying."],
        }));
      }
      return res.status(400).json({ ok: false, error: { code: "INVALID_REQUEST", message: "The SDK operation request is invalid.", recovery: "update_required" } });
    }
    const { requestId } = parsed.data;
    const readOnlyControl = parsed.data.operation === "operation.get" || parsed.data.operation === "operation.result.page";
    const preEffectRetryBasis = readOnlyControl ? "read_only" : "pre_execution";
    if (parsed.data.deadlineAtMs <= Date.now()) {
      return res.status(504).json(failure("RUNTIME_TIMEOUT", requestId, {
        message: "The SDK operation control deadline expired locally.",
        retrySafe: true,
        retrySafetyProof: { basis: preEffectRetryBasis },
        recovery: ["retry"],
        recoveryGuidance: [readOnlyControl
          ? "Retry the operation lookup; this timeout did not cancel the operation."
          : "Retry the cancellation request; the expired request did not reach the operation authority."],
      }));
    }
    const sessionToken = typeof req.headers[CUTAGENT_SDK_SESSION_HEADER] === "string"
      ? req.headers[CUTAGENT_SDK_SESSION_HEADER].trim()
      : "";
    let authenticated;
    try {
      authenticated = await captureAuthenticatedSdkRequest(authService);
    } catch {
      revoke(sdkRuntimeService, parsed.data.sessionId, sessionToken);
      return res.status(401).json(failure("AUTHENTICATION_REQUIRED", requestId, {
        message: "Sign in to CutAgent before controlling SDK operations.",
        recovery: ["sign_in"],
        recoveryGuidance: ["Sign in and reconnect without creating replacement work."],
      }));
    }
    let validSession;
    try {
      validSession = sdkRuntimeService.validateSession({
        sessionId: parsed.data.sessionId,
        sessionToken,
        accountFingerprint: authenticated.accountFingerprint,
      });
    } catch {
      return res.status(503).json(failure("RUNTIME_UNAVAILABLE", requestId, {
        message: "CutAgent could not verify the SDK runtime identity.",
        recovery: ["restart_runtime"],
        recoveryGuidance: ["Restart CutAgent and reattach to the original operation."],
      }));
    }
    if (!validSession) {
      return res.status(401).json(failure("CONNECTION_CLOSED", requestId, {
        message: "The SDK session is invalid, expired, or closed.",
        retrySafe: true,
        retrySafetyProof: { basis: preEffectRetryBasis },
        recovery: ["reconnect"],
        recoveryGuidance: ["Reconnect and reattach to the original operation."],
      }));
    }
    const ownerSessionId = sdkRuntimeService.resolveOwnerSessionId?.({
      sessionId: parsed.data.sessionId,
      sessionToken,
      accountFingerprint: authenticated.accountFingerprint,
    }) ?? null;
    const ownerSession = ownerSessionId ? sessionRepo?.getSession?.(ownerSessionId) ?? null : null;
    if (ownerSessionId && !ownerSession) {
      revoke(sdkRuntimeService, parsed.data.sessionId, sessionToken);
      return res.status(409).json(failure("CONNECTION_CLOSED", requestId, {
        message: "The CutAgent chat that owns this SDK session is unavailable.",
        recovery: ["reconnect"],
        recoveryGuidance: ["Reconnect from the owning CutAgent chat before creating replacement work."],
      }));
    }
    if (!sdkOperationAuthority) {
      return res.status(503).json(failure("RUNTIME_UNAVAILABLE", requestId, {
        message: "CutAgent durable operation control is unavailable.",
        recovery: ["restart_runtime"],
        recoveryGuidance: ["Restart CutAgent and reattach to the original operation."],
      }));
    }
    try {
      await sdkOperationReady;
      const assertRequestCurrent = () => {
        assertAuthenticatedSdkRequestCurrent(authService, authenticated);
        if (!sdkRuntimeService.validateSession({
          sessionId: parsed.data.sessionId,
          sessionToken,
          accountFingerprint: authenticated.accountFingerprint,
          touch: false,
        })) throw sessionChangedError();
      };
      let snapshot;
      let page;
      if (parsed.data.operation === "operation.create") {
        assertRequestCurrent();
        ({ snapshot } = sdkOperationAuthority.create({
          accountFingerprint: authenticated.accountFingerprint,
          requestId,
          sdkSessionId: parsed.data.sessionId,
          ownerSessionId,
          ownerRuntimeRequired: ownerSession?.resolve_runtime?.mode === "parallel_gui_beta",
          actionId: parsed.data.actionId,
          input: parsed.data.input,
          idempotencyKey: parsed.data.idempotencyKey,
        }));
        try { assertRequestCurrent(); } catch {
          revoke(sdkRuntimeService, parsed.data.sessionId, sessionToken);
        }
      } else if (parsed.data.operation === "operation.cancel") {
        snapshot = await sdkOperationAuthority.cancel({
          accountFingerprint: authenticated.accountFingerprint,
          operationId: parsed.data.operationId,
          ownerSessionId,
          assertRequestCurrent,
        });
        try {
          assertRequestCurrent();
        } catch {
          // The cancellation linearized while the original request was
          // authorized. Revoke the stale session, but return the truthful
          // authority result rather than a contradictory pre-effect denial.
          revoke(sdkRuntimeService, parsed.data.sessionId, sessionToken);
        }
      } else if (parsed.data.operation === "operation.get") {
        snapshot = sdkOperationAuthority.get({
          accountFingerprint: authenticated.accountFingerprint,
          operationId: parsed.data.operationId,
          ownerSessionId,
        });
        assertRequestCurrent();
      } else {
        page = sdkOperationAuthority.getResultPage({
          accountFingerprint: authenticated.accountFingerprint,
          operationId: parsed.data.operationId,
          ownerSessionId,
          collectionId: parsed.data.collectionId,
          expectedDigest: parsed.data.expectedDigest,
          offset: parsed.data.offset,
          pageSize: parsed.data.pageSize,
        });
        assertRequestCurrent();
      }
      return res.json(sdkOperationControlSuccessSchema.parse({
        ok: true,
        protocolVersion: CUTAGENT_SDK_WIRE_PROTOCOL,
        requestId,
        operation: parsed.data.operation,
        ...(page
          ? { page }
          : { event: { operationId: snapshot.operationId, sequence: snapshot.sequence, snapshot } }),
      }));
    } catch (error) {
      if (error instanceof SdkOperationAuthorityError) {
        const response = sdkOperationControlFailureSchema.parse({
          ok: false,
          protocolVersion: CUTAGENT_SDK_WIRE_PROTOCOL,
          requestId,
          error: { ...error.failure, requestId },
        });
        return res.status(["OPERATION_EXPIRED", "TARGET_NOT_FOUND"].includes(error.failure.code) ? 404 : 409).json(response);
      }
      if (error?.code === "AUTH_SESSION_CHANGED" || error?.code === "AUTHENTICATION_REQUIRED") {
        revoke(sdkRuntimeService, parsed.data.sessionId, sessionToken);
        return res.status(401).json(failure("AUTHENTICATION_REQUIRED", requestId, {
          message: "The authenticated CutAgent account changed during operation control.",
          recovery: ["sign_in", "reconnect"],
          recoveryGuidance: ["Sign in, reconnect, and reattach without creating replacement work."],
        }));
      }
      if (error?.code === "SDK_SESSION_CHANGED") {
        return res.status(401).json(failure("CONNECTION_CLOSED", requestId, {
          message: "The SDK session changed before operation control was authorized.",
          retrySafe: true,
          retrySafetyProof: { basis: preEffectRetryBasis },
          recovery: ["reconnect"],
          recoveryGuidance: ["Reconnect and reattach to the original operation."],
        }));
      }
      return res.status(503).json(failure("RUNTIME_UNAVAILABLE", requestId, {
        message: "CutAgent durable operation control is unavailable.",
        recovery: ["restart_runtime"],
        recoveryGuidance: ["Restart CutAgent and reattach to the original operation."],
      }));
    }
  });
}
