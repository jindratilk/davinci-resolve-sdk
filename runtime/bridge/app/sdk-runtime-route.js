import {
  CUTAGENT_SDK_API_VERSION,
  CUTAGENT_SDK_CLOSE_PATH,
  CUTAGENT_SDK_CONFIRM_PATH,
  CUTAGENT_SDK_CONNECT_PATH,
  CUTAGENT_SDK_PROTOCOL_DIGEST,
  CUTAGENT_SDK_READ_PATH,
  CUTAGENT_SDK_OPERATION_PATH,
  CUTAGENT_SDK_WORKFLOW_PATH,
  CUTAGENT_SDK_SESSION_HEADER,
  CUTAGENT_SDK_SUPPORTED_PACKAGE_MAJOR,
  CUTAGENT_SDK_SUPPORTED_PACKAGE_MINOR,
  CUTAGENT_SDK_WIRE_PROTOCOL,
  sdkRuntimeCloseRequestSchema,
  sdkRuntimeConfirmRequestSchema,
  sdkRuntimeConnectRequestSchema,
  sdkRuntimeReadFailureSchema,
  sdkRuntimeReadRequestSchema,
  sdkRuntimeReadSuccessSchema,
} from "../contracts/generated/sdk-runtime.js";
import { evaluateCutAgentSdkRuntimeCompatibility } from "../contracts/generated/sdk-runtime-policy.js";
import { requireDesktopBridgeSecret } from "./desktop-bridge-secret.js";
import {
  assertAuthenticatedSdkRequestCurrent,
  captureAuthenticatedSdkRequest,
} from "../services/sdk-authenticated-request.js";
import { sdkAccountFingerprint } from "../services/sdk-runtime-service.js";
import { createSdkLiveInspectionService, SdkLiveInspectionError } from "../services/sdk-live-inspection-service.js";
import { registerSdkOperationRoute } from "./sdk-operation-route.js";
const SDK_VOICE_CATALOG_ACTIVATED = false;
import { registerSdkWorkflowRoute } from "./sdk-workflow-route.js";
import { runWithSdkOwnerSession } from "../services/sdk-owner-session-context.js";

const AUTHENTICATION_REQUIRED_CODES = new Set([
  "AUTHENTICATION_REQUIRED",
  "AUTH_REQUIRED",
  "AUTH_TOKEN_EXPIRED",
  "AUTH_TOKEN_INVALID",
]);
const MAX_CONCURRENT_SDK_LIVE_INSPECTIONS = 1;
export const CUTAGENT_SDK_READINESS_PATH = "/api/sdk/runtime/readiness";

function awaitSdkAbortable(value, signal) {
  if (signal.aborted) return Promise.reject(signal.reason ?? new DOMException("The SDK request was aborted.", "AbortError"));
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (callback, result) => {
      if (settled) return;
      settled = true;
      signal.removeEventListener("abort", onAbort);
      callback(result);
    };
    const onAbort = () => finish(reject, signal.reason ?? new DOMException("The SDK request was aborted.", "AbortError"));
    signal.addEventListener("abort", onAbort, { once: true });
    Promise.resolve(value).then(
      (result) => finish(resolve, result),
      (error) => finish(reject, error),
    );
  });
}

function respondFailure(res, status, code, message, recovery, requestId = undefined) {
  return res.status(status).json({
    ok: false,
    ...(requestId ? { requestId } : {}),
    error: { code, message, recovery },
  });
}

function respondReadFailure(res, status, code, message, recovery, requestId = undefined) {
  const response = sdkRuntimeReadFailureSchema.parse({
    ok: false,
    ...(requestId ? { requestId } : {}),
    error: { code, message, recovery },
  });
  return res.status(status).json(response);
}

function respondAuthenticationRequired(res, requestId, read = false) {
  const respond = read ? respondReadFailure : respondFailure;
  return respond(res, 401, "AUTHENTICATION_REQUIRED", "Sign in to CutAgent before using the SDK.", "sign_in", requestId);
}

function respondSessionRejected(res, requestId, read = false) {
  const respond = read ? respondReadFailure : respondFailure;
  return respond(res, 401, "SESSION_REJECTED", "The SDK session is invalid, expired, or closed.", "reconnect", requestId);
}

function sdkIdentityFailureKind(error) {
  const codes = [error?.code, error?.cli_error_code, error?.cloudErrorCode]
    .filter((value) => typeof value === "string")
    .map((value) => value.trim());
  if (codes.includes("AUTH_SESSION_CHANGED")) return "session_changed";
  if (
    codes.some((code) => AUTHENTICATION_REQUIRED_CODES.has(code))
    || Number(error?.cloudStatusCode ?? error?.statusCode) === 401
  ) {
    return "authentication_required";
  }
  return null;
}

function respondSdkIdentityFailure(res, error, requestId, read = false) {
  const kind = sdkIdentityFailureKind(error);
  if (kind === "session_changed") {
    return respondSessionRejected(res, requestId, read);
  }
  if (kind === "authentication_required") {
    return respondAuthenticationRequired(res, requestId, read);
  }
  const respond = read ? respondReadFailure : respondFailure;
  return respond(res, 503, "RUNTIME_UNAVAILABLE", "CutAgent could not verify the authenticated SDK session.", "restart_runtime", requestId);
}

function revokeSdkSession(sdkRuntimeService, sessionId, sessionToken) {
  try {
    sdkRuntimeService.closeSession({ sessionId, sessionToken });
  } catch {
    // The sanitized route failure remains authoritative if the runtime is stopping.
  }
}

function respondRuntimeIdentityFailure(res, error, requestId, { read = false } = {}) {
  const incompatible = error?.code === "SDK_INCOMPATIBLE";
  const responder = read ? respondReadFailure : respondFailure;
  return responder(
    res,
    incompatible ? 409 : 503,
    incompatible ? "SDK_INCOMPATIBLE" : "RUNTIME_UNAVAILABLE",
    incompatible
      ? "The CutAgent runtime identity is incompatible with this SDK."
      : "The CutAgent runtime identity is unavailable.",
    incompatible ? "update_required" : "restart_runtime",
    requestId,
  );
}

function runtimeDescriptorCompatible(descriptor) {
  return descriptor.sdkApiVersion === CUTAGENT_SDK_API_VERSION
    && descriptor.wireProtocol === CUTAGENT_SDK_WIRE_PROTOCOL
    && descriptor.protocolDigest === CUTAGENT_SDK_PROTOCOL_DIGEST
    && evaluateCutAgentSdkRuntimeCompatibility(descriptor).compatible;
}

function compatible(handshake, descriptor) {
  const sdkVersion = handshake.sdkVersion.split(".").map((value) => Number(value));
  return sdkVersion[0] === CUTAGENT_SDK_SUPPORTED_PACKAGE_MAJOR
    && sdkVersion[1] === CUTAGENT_SDK_SUPPORTED_PACKAGE_MINOR
    && handshake.sdkApiVersion === CUTAGENT_SDK_API_VERSION
    && handshake.supportedWireProtocols.includes(CUTAGENT_SDK_WIRE_PROTOCOL)
    && handshake.requestedDistribution === "standalone_local"
    && handshake.protocolDigest === CUTAGENT_SDK_PROTOCOL_DIGEST
    && runtimeDescriptorCompatible(descriptor);
}

async function requireLocalPrincipal(authService) {
  const authenticated = await captureAuthenticatedSdkRequest(authService);
  assertAuthenticatedSdkRequestCurrent(authService, authenticated);
  return authenticated;
}

export function getSdkRuntimeRoutePaths() {
  return {
    connect: CUTAGENT_SDK_CONNECT_PATH,
    confirm: CUTAGENT_SDK_CONFIRM_PATH,
    close: CUTAGENT_SDK_CLOSE_PATH,
    read: CUTAGENT_SDK_READ_PATH,
    operation: CUTAGENT_SDK_OPERATION_PATH,
    readiness: CUTAGENT_SDK_READINESS_PATH,
    workflow: CUTAGENT_SDK_WORKFLOW_PATH,
  };
}

export function registerSdkRuntimeRoutes({
  app,
  sdkRuntimeService,
  authService,
  desktopAuthBroker,
  resolveService = null,
  identityNamespace = null,
  liveInspectionService: suppliedLiveInspectionService = null,
  cutagentCloudService = null,
  voiceCatalogActivated = SDK_VOICE_CATALOG_ACTIVATED,
  sdkOperationAuthority = null,
  sdkOperationReady = Promise.resolve(),
  sdkArtifactService = null,
  sdkWorkflowAuthority = null,
  sessionRepo = null,
}) {
  const activeInspectionSessions = new Set();
  let activeInspectionCount = 0;
  const liveInspectionService = suppliedLiveInspectionService ?? (resolveService
    ? createSdkLiveInspectionService({ resolveService, identityNamespace })
    : null);
  registerSdkOperationRoute({ app, sdkRuntimeService, authService, sdkOperationAuthority, sdkOperationReady, sessionRepo });
  const resolveOwnerSession = (sessionId, sessionToken, accountFingerprint) => {
    const ownerSessionId = sdkRuntimeService.resolveOwnerSessionId({ sessionId, sessionToken, accountFingerprint });
    if (!ownerSessionId) return null;
    const ownerSession = sessionRepo?.getSession?.(ownerSessionId) ?? null;
    if (!ownerSession) {
      const error = new Error("The CutAgent chat that owns this SDK session is no longer available.");
      error.code = "SDK_OWNER_SESSION_UNAVAILABLE";
      throw error;
    }
    return ownerSession;
  };
  const withOwnerSession = (ownerSession, operation) => (
    ownerSession ? runWithSdkOwnerSession(ownerSession, operation) : operation()
  );
  app.get(CUTAGENT_SDK_READINESS_PATH, requireDesktopBridgeSecret, async (_req, res) => {
    await sdkRuntimeService.waitForReadiness();
    const readiness = sdkRuntimeService.readinessState();
    if (readiness.state === "ready") {
      return res.json({ ok: true, readiness });
    }
    return res.status(readiness.category === "incompatible" ? 409 : 503).json({
      ok: false,
      readiness,
    });
  });
  registerSdkWorkflowRoute({ app, sdkRuntimeService, authService, sdkWorkflowAuthority, sessionRepo });
  app.post(CUTAGENT_SDK_CONNECT_PATH, requireDesktopBridgeSecret, async (req, res) => {
    let disconnected = req.aborted === true || res.destroyed === true;
    let responseFinished = false;
    let openedSession = null;
    req.once("aborted", () => {
      disconnected = true;
    });
    res.once("finish", () => {
      responseFinished = true;
    });
    res.once("close", () => {
      if (!responseFinished) {
        disconnected = true;
        if (openedSession) {
          try {
            sdkRuntimeService.closeSession({
              sessionId: openedSession.sessionId,
              sessionToken: openedSession.sessionToken,
            });
          } catch {
            // Runtime identity loss already revoked every session credential.
          }
        }
      }
    });
    const isDisconnected = () => disconnected
      || req.aborted === true
      || req.socket?.destroyed === true
      || res.destroyed === true;
    const parsed = sdkRuntimeConnectRequestSchema.safeParse(req.body);
    const requestId = parsed.success ? parsed.data.handshake.requestId : undefined;
    if (!parsed.success) {
      return respondFailure(res, 400, "INVALID_REQUEST", "The SDK connection request is invalid.", "update_required", requestId);
    }
    const request = parsed.data;
    let bootstrapBinding;
    try {
      bootstrapBinding = sdkRuntimeService.consumeBootstrapBinding(request.bootstrapToken, request.runtimeInstanceId);
    } catch (error) {
      return respondRuntimeIdentityFailure(res, error, requestId);
    }
    if (!bootstrapBinding) {
      return respondFailure(res, 401, "BOOTSTRAP_REJECTED", "The SDK bootstrap is invalid, expired, or already consumed.", "reconnect", requestId);
    }
    if (!sdkRuntimeService.descriptor || !compatible(request.handshake, sdkRuntimeService.descriptor)) {
      return respondFailure(res, 409, "SDK_INCOMPATIBLE", "The SDK and CutAgent runtime contracts are incompatible.", "update_required", requestId);
    }
    try {
      if (isDisconnected()) return;
      const authorized = await requireLocalPrincipal(authService);
      if (isDisconnected()) return;
      openedSession = sdkRuntimeService.prepareSession({
        accountFingerprint: authorized.accountFingerprint,
        ownerSessionId: bootstrapBinding.ownerSessionId,
      });
      if (isDisconnected()) {
        sdkRuntimeService.closeSession({
          sessionId: openedSession.sessionId,
          sessionToken: openedSession.sessionToken,
        });
        return;
      }
      return res.json({
        ok: true,
        protocolVersion: CUTAGENT_SDK_WIRE_PROTOCOL,
        requestId,
        descriptor: sdkRuntimeService.descriptor,
        session: openedSession,
      });
    } catch (error) {
      if (sdkIdentityFailureKind(error)) {
        return respondFailure(res, 401, "AUTHENTICATION_REQUIRED", "Sign in to CutAgent before connecting the SDK.", "sign_in", requestId);
      }
      if (error?.code === "SUBSCRIPTION_REQUIRED") {
        return respondFailure(res, 402, "SUBSCRIPTION_REQUIRED", "An active CutAgent subscription is required.", "upgrade_or_wait", requestId);
      }
      if (error?.code === "SESSION_LIMIT_REACHED") {
        return respondFailure(res, 429, "SESSION_LIMIT_REACHED", "The CutAgent SDK session limit was reached.", "reconnect", requestId);
      }
      if (error?.code === "SDK_INCOMPATIBLE" || error?.code === "RUNTIME_UNAVAILABLE") {
        return respondRuntimeIdentityFailure(res, error, requestId);
      }
      return respondFailure(res, 503, "RUNTIME_UNAVAILABLE", "CutAgent could not establish the SDK session.", "restart_runtime", requestId);
    }
  });

  app.post(CUTAGENT_SDK_CONFIRM_PATH, async (req, res) => {
    const parsed = sdkRuntimeConfirmRequestSchema.safeParse(req.body);
    const requestId = parsed.success ? parsed.data.requestId : undefined;
    if (!parsed.success) {
      return respondFailure(res, 400, "INVALID_REQUEST", "The SDK confirmation request is invalid.", "reconnect", requestId);
    }
    const sessionToken = typeof req.headers[CUTAGENT_SDK_SESSION_HEADER] === "string"
      ? req.headers[CUTAGENT_SDK_SESSION_HEADER].trim()
      : "";
    let authenticated;
    try {
      authenticated = await captureAuthenticatedSdkRequest(authService);
    } catch (error) {
      revokeSdkSession(sdkRuntimeService, parsed.data.sessionId, sessionToken);
      return respondSdkIdentityFailure(res, error, requestId);
    }
    let confirmed;
    try {
      confirmed = sdkRuntimeService.confirmSession({
        sessionId: parsed.data.sessionId,
        sessionToken,
        accountFingerprint: authenticated.accountFingerprint,
      });
    } catch (error) {
      return respondRuntimeIdentityFailure(res, error, requestId);
    }
    if (!confirmed) {
      return respondSessionRejected(res, requestId);
    }
    return res.json({
      ok: true,
      protocolVersion: CUTAGENT_SDK_WIRE_PROTOCOL,
      requestId,
      confirmed: true,
    });
  });

  app.post(CUTAGENT_SDK_CLOSE_PATH, async (req, res) => {
    const parsed = sdkRuntimeCloseRequestSchema.safeParse(req.body);
    const requestId = parsed.success ? parsed.data.requestId : undefined;
    if (!parsed.success) {
      return respondFailure(res, 400, "INVALID_REQUEST", "The SDK close request is invalid.", "reconnect", requestId);
    }
    const sessionToken = typeof req.headers[CUTAGENT_SDK_SESSION_HEADER] === "string"
      ? req.headers[CUTAGENT_SDK_SESSION_HEADER].trim()
      : "";
    let closed;
    try {
      closed = sdkRuntimeService.closeSession({ sessionId: parsed.data.sessionId, sessionToken });
    } catch (error) {
      return respondRuntimeIdentityFailure(res, error, requestId);
    }
    if (!closed) {
      return respondFailure(res, 401, "SESSION_REJECTED", "The SDK session is invalid, expired, or already closed.", "reconnect", requestId);
    }
    return res.json({
      ok: true,
      protocolVersion: CUTAGENT_SDK_WIRE_PROTOCOL,
      requestId,
      closed: true,
    });
  });

  app.post(CUTAGENT_SDK_READ_PATH, async (req, res) => {
    const parsed = sdkRuntimeReadRequestSchema.safeParse(req.body);
    const requestId = parsed.success ? parsed.data.requestId : undefined;
    if (!parsed.success) {
      return respondReadFailure(res, 400, "INVALID_REQUEST", "The SDK read request is invalid.", "update_required", requestId);
    }
    const sessionToken = typeof req.headers[CUTAGENT_SDK_SESSION_HEADER] === "string"
      ? req.headers[CUTAGENT_SDK_SESSION_HEADER].trim()
      : "";
    let authenticated;
    try {
      authenticated = await captureAuthenticatedSdkRequest(authService);
    } catch (error) {
      revokeSdkSession(sdkRuntimeService, parsed.data.sessionId, sessionToken);
      return respondSdkIdentityFailure(res, error, requestId, true);
    }
    let validSession;
    try {
      validSession = sdkRuntimeService.validateSession({
        sessionId: parsed.data.sessionId,
        sessionToken,
        accountFingerprint: authenticated.accountFingerprint,
      });
    } catch (error) {
      return respondRuntimeIdentityFailure(res, error, requestId, { read: true });
    }
    if (!validSession) {
      return respondSessionRejected(res, requestId, true);
    }
    let ownerSession;
    try {
      ownerSession = resolveOwnerSession(parsed.data.sessionId, sessionToken, authenticated.accountFingerprint);
    } catch {
      revokeSdkSession(sdkRuntimeService, parsed.data.sessionId, sessionToken);
      return respondReadFailure(res, 409, "CONNECTION_CLOSED", "The CutAgent chat that owns this SDK session is unavailable.", "reconnect", requestId);
    }
    if (parsed.data.operation === "voice.catalog") {
      if (!voiceCatalogActivated || !cutagentCloudService?.listTextToSpeechVoices) {
        return respondReadFailure(res, 503, "CAPABILITY_UNAVAILABLE", "The hosted voice catalog awaits reviewed production activation evidence.", "contact_support", requestId);
      }
      try {
        const result = await cutagentCloudService.listTextToSpeechVoices(authenticated.accessToken, {
          source: "account",
          search: parsed.data.query.search,
          page_token: parsed.data.query.pageToken,
          limit: parsed.data.query.limit,
        }, { signal: req.signal ?? null, timeoutMs: Math.max(1, parsed.data.deadlineAtMs - Date.now()) });
        const data = {
          voices: (Array.isArray(result?.voices) ? result.voices : []).map((voice) => ({
            voiceId: String(voice?.voice_id ?? ""),
            name: String(voice?.name ?? ""),
            description: typeof voice?.description === "string" ? voice.description : null,
            language: typeof voice?.language === "string" ? voice.language : null,
            accent: typeof voice?.accent === "string" ? voice.accent : null,
          })),
          hasMore: result?.has_more === true,
          nextPageToken: typeof result?.next_page_token === "string" && result.next_page_token ? result.next_page_token : null,
        };
        assertAuthenticatedSdkRequestCurrent(authService, authenticated);
        if (!sdkRuntimeService.validateSession({
          sessionId: parsed.data.sessionId,
          sessionToken,
          accountFingerprint: authenticated.accountFingerprint,
          touch: false,
        })) {
          return respondSessionRejected(res, requestId, true);
        }
        const response = sdkRuntimeReadSuccessSchema.safeParse({ ok: true, protocolVersion: CUTAGENT_SDK_WIRE_PROTOCOL, requestId, operation: "voice.catalog", data });
        if (!response.success) return respondReadFailure(res, 502, "INVALID_RESPONSE", "CutAgent could not validate the hosted voice catalog.", "contact_support", requestId);
        return res.json(response.data);
      } catch (error) {
        if (sdkIdentityFailureKind(error)) {
          revokeSdkSession(sdkRuntimeService, parsed.data.sessionId, sessionToken);
          return respondSdkIdentityFailure(res, error, requestId, true);
        }
        const code = error?.cloudErrorCode === "text_to_speech_not_entitled" || error?.cloudErrorCode === "subscription_past_due"
          ? "SUBSCRIPTION_REQUIRED" : error?.cloudErrorCode === "usage_limit_exceeded" ? "USAGE_EXHAUSTED" : "TEMPORARY_PROVIDER_FAILURE";
        return respondReadFailure(res, Number(error?.cloudStatusCode) || 503, code, "The hosted voice catalog is unavailable.", code === "SUBSCRIPTION_REQUIRED" || code === "USAGE_EXHAUSTED" ? "upgrade_or_wait" : "retry", requestId);
      }
    }

    if (parsed.data.operation === "artifact.fusion_setting.publish") {
      if (!sdkArtifactService?.publishFusionSetting) {
        return respondReadFailure(res, 503, "RUNTIME_UNAVAILABLE", "CutAgent Fusion setting ingress is unavailable.", "restart_runtime", requestId);
      }
      if (parsed.data.deadlineAtMs <= Date.now()) {
        return respondReadFailure(res, 504, "RUNTIME_TIMEOUT", "The Fusion setting publication deadline expired.", "retry", requestId);
      }
      try {
        const data = sdkArtifactService.publishFusionSetting({
          bytes: Buffer.from(parsed.data.setting.bytesBase64, "base64"),
          accountFingerprint: authenticated.accountFingerprint,
        });
        assertAuthenticatedSdkRequestCurrent(authService, authenticated);
        if (!sdkRuntimeService.validateSession({sessionId: parsed.data.sessionId, sessionToken, accountFingerprint: authenticated.accountFingerprint, touch: false})) {
          return respondSessionRejected(res, requestId, true);
        }
        return res.json(sdkRuntimeReadSuccessSchema.parse({ok: true, protocolVersion: CUTAGENT_SDK_WIRE_PROTOCOL, requestId, operation: parsed.data.operation, data}));
      } catch (error) {
        if (sdkIdentityFailureKind(error)) {
          revokeSdkSession(sdkRuntimeService, parsed.data.sessionId, sessionToken);
          return respondSdkIdentityFailure(res, error, requestId, true);
        }
        if (error?.code === "INVALID_REQUEST" || error instanceof TypeError) {
          return respondReadFailure(res, 400, "INVALID_REQUEST", "The Fusion setting input is invalid.", "update_required", requestId);
        }
        return respondReadFailure(res, 503, "RUNTIME_UNAVAILABLE", "CutAgent could not publish the Fusion setting artifact.", "retry", requestId);
      }
    }

    if (parsed.data.operation === "artifact.content") {
      if (!sdkArtifactService) {
        return respondReadFailure(res, 503, "RUNTIME_UNAVAILABLE", "CutAgent artifact delivery is unavailable.", "restart_runtime", requestId);
      }
      if (parsed.data.deadlineAtMs <= Date.now()) {
        return respondReadFailure(res, 504, "RUNTIME_TIMEOUT", "The SDK artifact read deadline expired.", "retry", requestId);
      }
      try {
        const data = sdkArtifactService.read({
          artifactId: parsed.data.artifactId,
          accountFingerprint: authenticated.accountFingerprint,
          offset: parsed.data.offset,
          length: parsed.data.length,
        });
        assertAuthenticatedSdkRequestCurrent(authService, authenticated);
        if (!sdkRuntimeService.validateSession({
          sessionId: parsed.data.sessionId,
          sessionToken,
          accountFingerprint: authenticated.accountFingerprint,
          touch: false,
        })) {
          return respondSessionRejected(res, requestId, true);
        }
        const response = sdkRuntimeReadSuccessSchema.parse({
          ok: true,
          protocolVersion: CUTAGENT_SDK_WIRE_PROTOCOL,
          requestId,
          operation: parsed.data.operation,
          data,
        });
        return res.json(response);
      } catch (error) {
        if (sdkIdentityFailureKind(error)) {
          revokeSdkSession(sdkRuntimeService, parsed.data.sessionId, sessionToken);
          return respondSdkIdentityFailure(res, error, requestId, true);
        }
        if (error?.code === "TARGET_NOT_FOUND") {
          return respondReadFailure(res, 404, "TARGET_NOT_FOUND", "The managed render artifact is unavailable.", "inspect_state", requestId);
        }
        if (error?.code === "INVALID_REQUEST" || error instanceof TypeError) {
          return respondReadFailure(res, 400, "INVALID_REQUEST", "The SDK artifact read request is invalid.", "update_required", requestId);
        }
        return respondReadFailure(res, 503, "RUNTIME_UNAVAILABLE", "CutAgent could not read the managed render artifact.", "restart_runtime", requestId);
      }
    }
    if (["timeline.managed.preview", "timeline.managed.export"].includes(parsed.data.operation)) {
      const exporting = parsed.data.operation === "timeline.managed.export";
      const operationLabel = exporting ? "export" : "preview";
      const method = exporting ? sdkWorkflowAuthority?.exportManaged : sdkWorkflowAuthority?.previewManaged;
      if (!method) {
        return respondReadFailure(res, 503, "RUNTIME_UNAVAILABLE", `Managed timeline ${operationLabel} is unavailable.`, "restart_runtime", requestId);
      }
      const deadlineRemainingMs = parsed.data.deadlineAtMs - Date.now();
      if (deadlineRemainingMs < 1) {
        return respondReadFailure(res, 504, "RUNTIME_TIMEOUT", `The managed timeline ${operationLabel} deadline expired.`, "retry", requestId);
      }
      const controller = new AbortController();
      let responseFinished = false;
      const abortDisconnected = () => controller.abort(new DOMException("The SDK client disconnected.", "AbortError"));
      const onAborted = () => abortDisconnected();
      const onFinish = () => { responseFinished = true; };
      const onClose = () => {
        if (!responseFinished) abortDisconnected();
      };
      req.once("aborted", onAborted);
      res.once("finish", onFinish);
      res.once("close", onClose);
      const deadlineTimer = setTimeout(
        () => controller.abort(new DOMException(`The managed timeline ${operationLabel} deadline expired.`, "TimeoutError")),
        deadlineRemainingMs,
      );
      deadlineTimer.unref?.();
      try {
        const data = await awaitSdkAbortable(withOwnerSession(ownerSession, () => method({
          accountFingerprint: authenticated.accountFingerprint,
          accessToken: authenticated.accessToken,
          sdkSessionId: parsed.data.sessionId,
          ...(exporting ? {request: parsed.data.request} : {program: parsed.data.program}),
          deadlineAtMs: parsed.data.deadlineAtMs,
          signal: controller.signal,
        })), controller.signal);
        if (req.aborted || res.destroyed) return;
        if (controller.signal.aborted) throw controller.signal.reason;
        assertAuthenticatedSdkRequestCurrent(authService, authenticated);
        if (!sdkRuntimeService.validateSession({ sessionId: parsed.data.sessionId, sessionToken, accountFingerprint: authenticated.accountFingerprint, touch: false })) {
          return respondSessionRejected(res, requestId, true);
        }
        return res.json(sdkRuntimeReadSuccessSchema.parse({ ok: true, protocolVersion: CUTAGENT_SDK_WIRE_PROTOCOL, requestId, operation: parsed.data.operation, data }));
      } catch (error) {
        const abortReason = controller.signal.reason;
        if (req.aborted || res.destroyed || abortReason?.name === "AbortError") return;
        if (abortReason?.name === "TimeoutError" || error?.name === "TimeoutError") {
          return respondReadFailure(res, 504, "RUNTIME_TIMEOUT", `The managed timeline ${operationLabel} deadline expired.`, "retry", requestId);
        }
        if (sdkIdentityFailureKind(error)) {
          revokeSdkSession(sdkRuntimeService, parsed.data.sessionId, sessionToken);
          return respondSdkIdentityFailure(res, error, requestId, true);
        }
        return respondReadFailure(res, 503, "RUNTIME_UNAVAILABLE", `CutAgent could not complete managed timeline ${operationLabel}.`, "restart_runtime", requestId);
      } finally {
        clearTimeout(deadlineTimer);
        req.off("aborted", onAborted);
        res.off("finish", onFinish);
        res.off("close", onClose);
      }
    }
    if (!liveInspectionService) {
      return respondReadFailure(res, 503, "RUNTIME_UNAVAILABLE", "CutAgent live inspection is unavailable.", "restart_runtime", requestId);
    }
    if (
      activeInspectionSessions.has(parsed.data.sessionId)
      || activeInspectionCount >= MAX_CONCURRENT_SDK_LIVE_INSPECTIONS
    ) {
      return respondReadFailure(res, 429, "RUNTIME_UNAVAILABLE", "A CutAgent SDK live inspection is already in progress.", "retry", requestId);
    }
    const deadlineRemainingMs = parsed.data.deadlineAtMs - Date.now();
    if (deadlineRemainingMs < 1) {
      return respondReadFailure(res, 504, "RUNTIME_TIMEOUT", "The SDK live inspection deadline expired.", "retry", requestId);
    }
    activeInspectionSessions.add(parsed.data.sessionId);
    activeInspectionCount += 1;
    const controller = new AbortController();
    let responseFinished = false;
    const abortDisconnected = () => controller.abort(new DOMException("The SDK client disconnected.", "AbortError"));
    const onAborted = () => abortDisconnected();
    const onFinish = () => { responseFinished = true; };
    const onClose = () => {
      if (!responseFinished) abortDisconnected();
    };
    req.once("aborted", onAborted);
    res.once("finish", onFinish);
    res.once("close", onClose);
    const deadlineTimer = setTimeout(
      () => controller.abort(new DOMException("The SDK live inspection deadline expired.", "TimeoutError")),
      deadlineRemainingMs,
    );
    deadlineTimer.unref?.();
    try {
      if (controller.signal.aborted || req.aborted || res.destroyed) return;
      const data = await withOwnerSession(ownerSession, () => liveInspectionService.read(parsed.data, {
        accessToken: authenticated.accessToken,
        deadlineAtMs: parsed.data.deadlineAtMs,
        signal: controller.signal,
      }));
      if (controller.signal.aborted || req.aborted || res.destroyed) return;
      assertAuthenticatedSdkRequestCurrent(authService, authenticated);
      if (!sdkRuntimeService.validateSession({
        sessionId: parsed.data.sessionId,
        sessionToken,
        accountFingerprint: authenticated.accountFingerprint,
        touch: false,
      })) {
        return respondSessionRejected(res, requestId, true);
      }
      const response = sdkRuntimeReadSuccessSchema.safeParse({
        ok: true,
        protocolVersion: CUTAGENT_SDK_WIRE_PROTOCOL,
        requestId,
        operation: parsed.data.operation,
        data,
      });
      if (!response.success) {
        return respondReadFailure(res, 502, "INVALID_RESPONSE", "CutAgent could not validate the DaVinci Resolve inspection result.", "contact_support", requestId);
      }
      return res.json(response.data);
    } catch (error) {
      if (req.aborted || res.destroyed || (controller.signal.aborted && controller.signal.reason?.name === "AbortError")) {
        return;
      }
      if (controller.signal.aborted || error?.name === "TimeoutError") {
        return respondReadFailure(res, 504, "RUNTIME_TIMEOUT", "The SDK live inspection deadline expired.", "retry", requestId);
      }
      if (sdkIdentityFailureKind(error)) {
        revokeSdkSession(sdkRuntimeService, parsed.data.sessionId, sessionToken);
        return respondSdkIdentityFailure(res, error, requestId, true);
      }
      if (error?.code === "SDK_INCOMPATIBLE" || error?.code === "RUNTIME_UNAVAILABLE") {
        return respondRuntimeIdentityFailure(res, error, requestId, { read: true });
      }
      if (error instanceof SdkLiveInspectionError) {
        const details = {
          TARGET_NOT_FOUND: [404, "TARGET_NOT_FOUND", "The requested DaVinci Resolve object was not found.", "inspect_state"],
          AMBIGUOUS_TARGET: [409, "AMBIGUOUS_TARGET", "The requested DaVinci Resolve object is ambiguous.", "inspect_state"],
          STALE_REVISION: [409, "STALE_REVISION", "The referenced DaVinci Resolve state is stale.", "inspect_state"],
          CAPABILITY_UNAVAILABLE: [409, "CAPABILITY_UNAVAILABLE", error.message, "upgrade_or_wait"],
          INVALID_REQUEST: [400, "INVALID_REQUEST", error.message, "inspect_state"],
          INVALID_RESPONSE: [502, "INVALID_RESPONSE", "CutAgent could not validate the DaVinci Resolve inspection result.", "contact_support"],
        }[error.code];
        if (details) return respondReadFailure(res, ...details, requestId);
      }
      return respondReadFailure(res, 503, "RUNTIME_UNAVAILABLE", "CutAgent could not inspect the current DaVinci Resolve state.", "restart_runtime", requestId);
    } finally {
      clearTimeout(deadlineTimer);
      req.off("aborted", onAborted);
      res.off("finish", onFinish);
      res.off("close", onClose);
      activeInspectionSessions.delete(parsed.data.sessionId);
      activeInspectionCount -= 1;
    }
  });
}
