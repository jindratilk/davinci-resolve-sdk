const BROKER_ENV_KEYS = Object.freeze({
  url: "CUTAGENT_CLI_BROKER_URL",
  token: "CUTAGENT_CLI_BROKER_TOKEN",
  capability: "CUTAGENT_CLI_BROKER_CAPABILITY",
});
const BROKER_PATH_BY_COMMAND = Object.freeze({
  "transcript.create": "/internal/cutagent-cli/transcript",
  "audio.voice_list": "/internal/cutagent-cli/voiceover",
});

function authorizationError(message) {
  return Object.assign(new Error(message), { code: "AUTH_REQUIRED", cli_error_code: "AUTH_REQUIRED" });
}

function loopbackBrokerOrigin(authorizerUrl) {
  let base;
  try { base = new URL(authorizerUrl); } catch { throw authorizationError("CutAgent broker authorization endpoint is unavailable."); }
  const host = base.hostname.replace(/^\[|\]$/gu, "").toLowerCase();
  if (base.protocol !== "http:" || !["127.0.0.1", "::1", "localhost"].includes(host)
    || base.username || base.password || base.search || base.hash) {
    throw authorizationError("CutAgent broker authorization endpoint is invalid.");
  }
  return base.origin;
}

/** Issue fresh, invocation-bound broker credentials after command authorization. */
export function issueCutAgentCliBrokerEnvironment({
  broker,
  authorization,
  args,
  commandId,
  authorizationCommandId = commandId,
  input = null,
} = {}) {
  if (authorization?.commandId !== authorizationCommandId
    || !/^[a-f0-9]{64}$/iu.test(authorization?.argsSha256 ?? "")
    || typeof authorization?.accountSubject !== "string" || !authorization.accountSubject.trim()) {
    throw authorizationError("CutAgent broker grant requires exact account-bound command authorization.");
  }
  const brokerOrigin = loopbackBrokerOrigin(authorization?.env?.CUTAGENT_CLI_AUTHORIZER_URL);
  const issuer = input === null ? broker?.issueGrant : broker?.issueSdkGrant;
  if (typeof issuer !== "function") throw authorizationError("CutAgent broker grant authority is unavailable.");
  const grant = issuer.call(broker, {
    commandId,
    argsSha256: authorization.argsSha256,
    args,
    accountSubject: authorization.accountSubject,
    ...(input === null ? {} : { input }),
  });
  if (!grant || typeof grant.path !== "string"
    || grant.path !== BROKER_PATH_BY_COMMAND[commandId]
    || typeof grant.token !== "string" || !grant.token
    || typeof grant.bridge_capability !== "string" || !grant.bridge_capability) {
    throw authorizationError("CutAgent broker rejected the authorized command grant.");
  }
  return Object.freeze({
    [BROKER_ENV_KEYS.url]: new URL(grant.path, brokerOrigin).toString(),
    [BROKER_ENV_KEYS.token]: grant.token,
    [BROKER_ENV_KEYS.capability]: grant.bridge_capability,
  });
}
