"""Local transport/admission substitutions; domain factories remain original source."""
def transform(path, text):
    if path == 'bridge/services/sdk-prepared-action-runtime-client.js':
        text = 'import {buildCutAgentCliEnv} from "../../local/cli-runtime.mjs";\n'+text
        start = text.index('  if (runtimeEnv === null')
        end = text.index('  let hostDiagnostic',start)
        text = text[:start]+'''  const child = spawnProcess(executablePath, [], {
    stdio: ["pipe", "pipe", "pipe"], windowsHide: true, detached: process.platform !== "win32",
    env: buildCutAgentCliEnv({args: [], extraEnv: runtimeEnv}),
  });
  const productionMacBroker = false;
  const productionWindowsBroker = false;
  let ownerWatchdog = null;
  const cleanup = () => {};
'''+text[end:]
        start = text.index('  try {\n    const accepted = await bounded')
        end = text.index('  let requestSequence', start)
        text = text[:start]+text[end:]
    if path == 'bridge/services/sdk-prepared-action-coordinator.js':
        start = text.index('  if (typeof authorizationService?.authorizePreparedAction')
        end = text.index('\n\n  async function execute', start)
        text=text[:start]+text[end:]
        start=text.index('    const authorization = await authorizationService.authorizePreparedAction(')
        end=text.index('    await admitOperation',start)
        text=text[:start]+'''    authService.assertCurrent(authenticated);
'''+text[end:]
        text=text.replace('      authorizationToken: authorization.token,\n','')
    if path == 'bridge/services/sdk-prepared-action-production-composition.js':
        start=text.index('export async function resolvePreparedActionAccount(')
        end=text.index('\nfunction sha256',start)
        text=text[:start]+text[end:]
        start=text.index('  if (typeof resourcesDir !== "string"')
        end=text.index('  const capturedRuntimeBindings',start)
        text=text[:start]+'''  if (typeof resourcesDir !== "string" || !path.isAbsolute(resourcesDir) || typeof secretDir !== "string" || !path.isAbsolute(secretDir)) throw new TypeError("Local prepared runtime roots are required.");
  const runtimeRoot = resourcesDir;
  const executablePath = path.join(runtimeRoot, "framed_prepared_host");
  const manifestBytes = fs.readFileSync(path.join(runtimeRoot, "SOURCE_INVENTORY.json"));
  const manifestDigest = sha256(manifestBytes);
  const manifest = {version: appVersion};
  const hostEntry = {sha256: sha256(fs.readFileSync(executablePath))};
  const runtimeEntry = {sha256: sha256(fs.readFileSync(path.join(runtimeRoot, "cutagent")))};
  const desktopArtifactDigest = manifestDigest;
'''+text[end:]
        start=text.index('      if (!authenticated?.accessToken')
        end=text.index('      const issuedAt',start)
        text=text[:start]+'''      if (!sdkSessionId) throw new Error("Local prepared session is unavailable.");
      authService.assertCurrent(authenticated);
'''+text[end:]
        text=text.replace('account: {accountId: authenticated.accountSubject, accountSubject: authenticated.accountSubject},','localPrincipal: {fingerprint: authenticated.accountFingerprint},')
        text=text.replace('        subscription: {plan: account.planCode ?? "unknown", state: account.subscriptionStatus ?? "unknown"},\n','')
        text=text.replace('          accountId: authenticated.accountSubject,\n','')
        start=text.index('        bootstrap: {',text.index('runtime = await createPreparedActionRuntimeClient'))
        end=text.index('        initialization:', start)
        text=text[:start]+text[end:]
        start=text.index('        async redeemAuthorization(payload)')
        end=text.index('        async inspectPreparedActionTimeline',start)
        text=text[:start]+'''        async redeemAuthorization() { throw new Error("Commercial redemption is unavailable in the local host."); },
'''+text[end:]
    return text
