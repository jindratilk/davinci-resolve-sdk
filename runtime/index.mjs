import {createServer} from 'node:http';
import {constants} from 'node:fs';
import {lstat, open, rename, unlink} from 'node:fs/promises';
import {join, isAbsolute} from 'node:path';
import {randomUUID} from 'node:crypto';
import express from 'express';
import {createSdkRuntimeService} from './bridge/services/sdk-runtime-service.js';
import {registerSdkRuntimeRoutes} from './bridge/app/sdk-runtime-route.js';
import {sdkDesktopDiscoverySchema} from './bridge/contracts/generated/sdk-runtime.js';
import {composeLocalNativeActions} from './local/native-actions.mjs';
import {createLocalPrincipalAuthority} from './local/principal.mjs';
import {createSdkOperationRepo} from './bridge/repos/sdk-operation-repo.js';
import {createSdkOperationAuthority} from './bridge/services/sdk-operation-authority.js';
import {createLocalCapability} from './local/capability.mjs';

/** Compose the existing complete SDK route table against local native owners.
 * No production native owner is fabricated when one has not been configured.
 */
export async function startLocalRuntime({stateDirectory, nativeIdentityProbe, nativeIdentityCurrent,
  resolveService, liveInspectionService, sdkOperationAuthority, sdkOperationReady,
  sdkArtifactService, sdkWorkflowAuthority, identityNamespace, sdkActions = {}, nativeTransport = null} = {}) {
  if (!isAbsolute(stateDirectory ?? '')) throw new TypeError('An absolute private state directory is required.');
  const state = await lstat(stateDirectory);
  if (process.platform === 'win32') throw new Error('Windows private-directory ACL validation is not integrated yet.');
  if (!state.isDirectory() || state.isSymbolicLink() || state.uid !== process.getuid() || (state.mode & 0o077)) {
    throw new Error('The local SDK state directory must be owned by the current user with mode 0700.');
  }
  if (typeof nativeIdentityProbe !== 'function' || typeof nativeIdentityCurrent !== 'function') {
    throw new TypeError('A real native-host identity owner is required.');
  }
  // Reuse the existing durable authority and its exclusive private-directory lock.
  // Native action factories are supplied through the same registry used upstream.
  const operationRepo = sdkOperationAuthority ? null : createSdkOperationRepo({storageDir: join(stateDirectory, 'operations')});
  const authority = createLocalPrincipalAuthority({installationAuthority: operationRepo?.installationAuthority ?? sdkOperationAuthority.installationAuthority});
  const capability = createLocalCapability();
  const runtime = createSdkRuntimeService({appVersion: '3.0.0',
    cliIdentityProbe: nativeIdentityProbe, cliIdentityCurrent: nativeIdentityCurrent});
  let nativeComposition = null;
  if (nativeTransport !== null) {
    if (!operationRepo || Object.keys(sdkActions).length || resolveService || liveInspectionService) {
      operationRepo?.releaseOwnership();
      throw new TypeError('Native composition owns its action registry and native services.');
    }
    try {
      identityNamespace ??= operationRepo.installationAuthority;
      nativeComposition = composeLocalNativeActions({stateDirectory, transport: nativeTransport,
        authService: authority, sdkRuntimeService: runtime, identityNamespace});
      ({actions: sdkActions, resolveService, liveInspectionService, sdkArtifactService} = nativeComposition);
    } catch (error) {operationRepo.releaseOwnership(); authority.close(); capability.revoke(); await runtime.stop(); throw error;}
  }
  sdkOperationAuthority ??= createSdkOperationAuthority({repo: operationRepo, actions: sdkActions});
  if (nativeComposition) {
    sdkWorkflowAuthority = nativeComposition.composeWorkflowAuthority(sdkOperationAuthority);
    sdkOperationReady = sdkWorkflowAuthority.reconcileStartup();
  }
  const app = express();
  app.locals.localCapability = capability.token;
  app.use((req, res, next) => {
    if (req.headers.origin || !/^127\.0\.0\.1:\d+$/.test(req.headers.host ?? '')) {
      return res.status(403).json({ok: false, error: 'LOCAL_ACCESS_REQUIRED'});
    }
    next();
  });
  app.use(express.json({limit: '32mb'}));
  registerSdkRuntimeRoutes({app, sdkRuntimeService: runtime, authService: authority,
    desktopAuthBroker: null, cutagentCloudService: null, voiceCatalogActivated: false,
    resolveService, liveInspectionService, sdkOperationAuthority, sdkOperationReady,
    sdkArtifactService, sdkWorkflowAuthority, identityNamespace});
  const server = createServer(app);
  const file = join(stateDirectory, 'cutagent-sdk-discovery-v1.json');
  let refresh;
  let stopped = false;
  async function close() {
    if (stopped) return;
    stopped = true; clearInterval(refresh); authority.close(); capability.revoke();
    await runtime.stop();
    server.closeAllConnections();
    if (server.listening) await new Promise(resolve => server.close(resolve));
    if (operationRepo) {
      await sdkOperationAuthority.waitForIdle();
      operationRepo.releaseOwnership();
    }
    await nativeComposition?.close();
    try {
      const handle = await open(file, constants.O_RDONLY | constants.O_NOFOLLOW);
      let value; try { value = JSON.parse(await handle.readFile('utf8')); } finally { await handle.close(); }
      if (value.runtimeInstanceId === runtime.runtimeInstanceId) await unlink(file);
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  try {
    await sdkOperationReady;
    if (operationRepo) await sdkOperationAuthority.reconcileOrphans();
    await runtime.waitForReadiness();
    if (!runtime.descriptor) throw new Error('The native host has no compatible runtime identity.');
    await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
    const port = server.address().port;
    async function publishDiscovery() {
      if (stopped) return;
      const bootstrap = runtime.issueBootstrap();
      const payload = sdkDesktopDiscoverySchema.parse({version: 1, distribution: 'standalone_local',
        endpoint: `http://127.0.0.1:${port}/internal/sdk/v1/connect`, bridgeCapability: capability.token,
        bootstrapToken: bootstrap.bootstrapToken, runtimeInstanceId: runtime.runtimeInstanceId, pid: process.pid,
        issuedAt: new Date(bootstrap.issuedAt).toISOString(), expiresAt: new Date(bootstrap.expiresAt).toISOString()});
      const temporary = join(stateDirectory, `.discovery-${randomUUID()}.json`);
      const handle = await open(temporary, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
      try { await handle.writeFile(JSON.stringify(payload)); } finally { await handle.close(); }
      try { await rename(temporary, file); } catch (error) { await unlink(temporary); throw error; }
    }
    await publishDiscovery();
    refresh = setInterval(() => { publishDiscovery().catch(() => close().catch(() => {})); }, 60_000);
    refresh.unref();
    return Object.freeze({discoveryFile: file, port, close, publishDiscovery,
      rotatePrincipal() { authority.rotate(); }});
  } catch (error) { await close(); throw error; }
}

/** Start the complete local native registry using its actual extracted source identity. */
export async function startNativeLocalRuntime({stateDirectory, transport}) {
  const {createNativeInspectionOwner} = await import('./local/native-inspection.mjs');
  const {nativeIdentityProbe, nativeIdentityCurrent} = createNativeInspectionOwner({transport});
  return startLocalRuntime({stateDirectory, nativeTransport: transport, nativeIdentityProbe, nativeIdentityCurrent});
}
