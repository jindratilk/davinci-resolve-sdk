import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, chmod, rm, readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {z} from 'zod';
import * as sdk from '../sdk/dist/index.js';
import {startLocalRuntime} from '../runtime/index.mjs';
import {createLocalPrincipalAuthority} from '../runtime/local/principal.mjs';

async function fixture(t, overrides = {}) {
  const stateDirectory = await mkdtemp(join(tmpdir(), 'standalone-sdk-'));
  await chmod(stateDirectory, 0o700);
  const originalDiscovery = process.env.CUTAGENT_SDK_DISCOVERY_FILE;
  const runtime = await startLocalRuntime({stateDirectory,
    // An explicit simulated native owner; this test proves the real SDK/HTTP
    // admission chain, not native DaVinci Resolve connectivity or mutation.
    nativeIdentityProbe: () => ({version: '3.0.0', executableDigest: createHash('sha256').update('test-native-owner').digest('hex')}),
    nativeIdentityCurrent: () => true,
    liveInspectionService: {async read(request, context) {
      assert.equal(request.operation, 'project.current');
      assert.equal(context.accessToken, undefined);
      return {id: 'project_standalone_source_smoke', name: 'Local project'};
    }}, ...overrides});
  process.env.CUTAGENT_SDK_DISCOVERY_FILE = runtime.discoveryFile;
  t.after(async () => {
    await runtime.close();
    if (originalDiscovery === undefined) delete process.env.CUTAGENT_SDK_DISCOVERY_FILE;
    else process.env.CUTAGENT_SDK_DISCOVERY_FILE = originalDiscovery;
    await rm(stateDirectory, {recursive: true, force: true});
  });
  return runtime;
}

test('original full SDK connects and routes project inspection without commercial credentials', async t => {
  await fixture(t);
  const client = await sdk.CutAgent.connect();

  assert.equal(client.connection.descriptor.distribution, 'standalone_local');
  const project = await client.projects.current();
  assert.equal(project.name, 'Local project');
  // Original SDK facades survive extraction; no replacement small API.
  assert.equal(typeof project.mediaPool.importMedia, 'function');
  assert.equal(typeof project.render.export, 'function');
  assert.equal(typeof client.operations.reattach, 'function');
  assert.equal(typeof client.actions.start, 'function');
  await client.close();
});

test('local runtime starts retention only after readiness and stops its scheduler on shutdown', async t => {
  let scheduled = null;
  let cleared = null;
  let unrefCount = 0;
  let releaseReadiness;
  const readiness = new Promise(resolve => { releaseReadiness = resolve; });
  const starting = fixture(t, {
    sdkOperationReady: readiness,
    operationRetentionLifecycleOptions: {
      sweepIntervalMs: 1_234,
      scheduleInterval(callback, interval) {
        scheduled = {callback, interval, unref() { unrefCount += 1; }};
        return scheduled;
      },
      clearScheduledInterval(timer) { cleared = timer; },
    },
  });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(scheduled, null);
  releaseReadiness();
  const runtime = await starting;
  assert.equal(scheduled.interval, 1_234);
  assert.equal(unrefCount, 1);

  await runtime.close();
  assert.equal(cleared, scheduled);
});

test('default retention reporting excludes cleanup secrets and raw paths', async t => {
  const privateMessage = 'cleanup failed for /private/editor/project bearer-secret-value';
  let cleanupCalls = 0;
  let scheduled = null;
  const runtime = await fixture(t, {
    sdkOperationAuthority: {
      installationAuthority: 'sdk_installation_retention_reporting_test',
      cleanup() {
        cleanupCalls += 1;
        if (cleanupCalls > 1) throw Object.assign(new Error(privateMessage), {code: 'SDK_OPERATION_AUTHORITY_UNAVAILABLE'});
      },
    },
    operationRetentionLifecycleOptions: {
      scheduleInterval(callback) {
        scheduled = {callback, unref() {}};
        return scheduled;
      },
      clearScheduledInterval() {},
    },
  });
  assert.equal(cleanupCalls, 1);
  const output = [];
  const original = console.error;
  console.error = value => output.push(String(value));
  try {
    scheduled.callback();
  } finally {
    console.error = original;
  }
  assert.equal(cleanupCalls, 2);
  assert.deepEqual(output, [
    '[cutagent-sdk-runtime] Durable SDK operation retention cleanup failed. (SDK_OPERATION_AUTHORITY_UNAVAILABLE)',
  ]);
  assert.equal(JSON.stringify(output).includes(privateMessage), false);
  assert.equal(JSON.stringify(output).includes('/private/editor/project'), false);
  await runtime.close();
});

test('retention failure reaches the existing private diagnostic callback in bounded form', async t => {
  let cleanupCalls = 0;
  let scheduled = null;
  const diagnostics = [];
  const runtime = await fixture(t, {
    sdkOperationAuthority: {
      installationAuthority: 'sdk_installation_retention_callback_test',
      cleanup() {
        cleanupCalls += 1;
        if (cleanupCalls > 1) throw Object.assign(new Error('secret /private/runtime/state'), {code: 'BAD code with spaces'});
      },
    },
    onExecutorError(diagnostic) {
      diagnostics.push(diagnostic);
      throw new Error('diagnostic consumer failure');
    },
    operationRetentionLifecycleOptions: {
      scheduleInterval(callback) {
        scheduled = {callback, unref() {}};
        return scheduled;
      },
      clearScheduledInterval() {},
    },
  });
  assert.doesNotThrow(() => scheduled.callback());
  assert.deepEqual(diagnostics, [{
    phase: 'retention.cleanup',
    errorClass: 'Error',
    errorCode: null,
    message: 'Durable SDK operation retention cleanup failed.',
  }]);
  assert.equal(JSON.stringify(diagnostics).includes('/private/runtime/state'), false);
  await runtime.close();
});

test('full SDK export names match the original public package', async () => {
  const baseline = JSON.parse(await readFile(new URL('./public-export-names.json', import.meta.url), 'utf8'));
  assert.deepEqual(Object.keys(sdk).sort(), baseline);
});

test('missing bootstrap capability and browser-origin callers fail before admission', async t => {
  const runtime = await fixture(t);
  const url = `http://127.0.0.1:${runtime.port}/internal/sdk/v1/connect`;
  assert.equal((await fetch(url, {method: 'POST', headers: {'content-type':'application/json'}, body:'{}'})).status, 401);
  assert.equal((await fetch(url, {method:'POST', headers:{origin:'https://untrusted.example'}, body:'{}'})).status, 403);
});

test('replaying the already consumed discovery bootstrap is rejected', async t => {
  const runtime = await fixture(t);
  const discovery = await readFile(runtime.discoveryFile, 'utf8');
  const client = await sdk.CutAgent.connect();

  assert.equal(await readFile(runtime.discoveryFile, 'utf8'), discovery);
  await assert.rejects(sdk.CutAgent.connect({timeoutMs:1000}));
  await client.close();
});

test('local principal rotation invalidates in-flight project inspection', async t => {
  let runtime;
  runtime = await fixture(t, {liveInspectionService: {async read() {
    runtime.rotatePrincipal();
    return {id:'project_standalone_source_smoke', name:'Local project'};
  }}});
  const client = await sdk.CutAgent.connect();

  await assert.rejects(client.projects.current(), error => ['AUTHENTICATION_REQUIRED','CONNECTION_CLOSED'].includes(error.failure?.code));
  await client.close();
});

test('local principal snapshots reject forgery, stale generations and closed authority', () => {
  const authority = createLocalPrincipalAuthority();
  const first = authority.capture();
  authority.assertCurrent(first);
  assert.equal('accessToken' in first, false);
  assert.equal('subscription' in first, false);
  assert.throws(() => authority.assertCurrent(structuredClone(first)));
  authority.rotate();
  assert.throws(() => authority.assertCurrent(first));
  authority.assertCurrent(authority.capture());
  authority.close();
  assert.throws(() => authority.capture());
});

test('no implicit fake native implementation and no unsafe shared state directory', async t => {
  const directory = await mkdtemp(join(tmpdir(), 'standalone-sdk-reject-'));
  t.after(() => rm(directory, {recursive:true, force:true}));
  await chmod(directory, 0o700);
  await assert.rejects(startLocalRuntime({stateDirectory:directory}), /native-host identity owner/);
  await chmod(directory, 0o755);
  await assert.rejects(startLocalRuntime({stateDirectory:directory}), /mode 0700/);
});

test('executor diagnostics require an internal callback', async () => {
  await assert.rejects(
    startLocalRuntime({onExecutorError: {}}),
    error => error instanceof TypeError && error.message === 'Executor diagnostics must be a callback.',
  );
});

test('executor failures reach private diagnostics without leaking into the public terminal', async t => {
  const actionId = 'cutagent.action.audio.duck';
  const privateMessage = 'native failure at /private/editor/source.wav bearer-secret-value';
  const privateReason = 'native stderr contained private fixture identity';
  const diagnostics = [];
  await fixture(t, {
    sdkActions: {[actionId]: {
      inputSchema: z.object({
        inputPath: z.string(),
        speechTrackIndex: z.number().int(),
        musicTrackIndex: z.number().int(),
      }).strict(),
      resultSchema: z.object({changed: z.boolean()}).strict(),
      idempotency: 'required',
      async execute() {
        throw Object.assign(new Error(privateMessage), {
          code: 'NATIVE_PRIVATE_FAILURE',
          hostPhase: 'after_native_dispatch',
          privateReason,
        });
      },
    }},
    onExecutorError(diagnostic) {
      diagnostics.push(diagnostic);
      throw new Error('diagnostic sink failure must not alter operation truth');
    },
  });
  const client = await sdk.CutAgent.connect();

  const operation = await client.actions.start(actionId, {
    inputPath: '/session/audio/source.wav',
    speechTrackIndex: 1,
    musicTrackIndex: 2,
  }, {idempotencyKey: 'idempotency_executor_error_1234'});
  const terminal = await operation.wait();

  assert.equal(terminal.status, 'failed');
  const publicTerminal = JSON.stringify(terminal);
  for (const privateValue of [privateMessage, privateReason, 'NATIVE_PRIVATE_FAILURE', 'after_native_dispatch']) {
    assert.equal(publicTerminal.includes(privateValue), false);
  }
  assert.equal(diagnostics.length, 1);
  assert.deepEqual(
    {
      phase: diagnostics[0].phase,
      actionId: diagnostics[0].actionId,
      errorClass: diagnostics[0].errorClass,
      message: diagnostics[0].message,
      errorCode: diagnostics[0].errorCode,
      hostPhase: diagnostics[0].hostPhase,
      reason: diagnostics[0].reason,
    },
    {
      phase: 'definition.execute',
      actionId,
      errorClass: 'Error',
      message: privateMessage,
      errorCode: 'NATIVE_PRIVATE_FAILURE',
      hostPhase: 'after_native_dispatch',
      reason: privateReason,
    },
  );
  assert.match(diagnostics[0].operationId, /^operation_/);
  assert.match(diagnostics[0].executionId, /^execution_/);
  await client.close();
});

test('existing native-to-public projector rejects changed project identity', async t => {
  await fixture(t, {liveInspectionService:null, identityNamespace:'standalone-local-test',
    resolveService:{async readSdkLiveInspection() {
      const project={project_open:true,context:'project',project_id:'native-1',name:'Source smoke',current_timeline:null};
      return {before:{project},after:{project:{...project,project_id:'native-2'}}};
    }}});
  const client=await sdk.CutAgent.connect();
  await assert.rejects(client.projects.current(), error => error.failure?.code === 'STALE_REVISION');
  await client.close();
});

test('native owner exposes existing inspection seam and rejects mutations before spawn', async () => {
  const {createNativeInspectionOwner,resolveNativeInspectionPython}=await import('../runtime/local/native-inspection.mjs');
  assert.equal(resolveNativeInspectionPython(), join(process.cwd(), '.venv/bin/python'));
  const owner=createNativeInspectionOwner({python:'/not-a-python-executable',transport:'studio_external'});
  const identity=owner.nativeIdentityProbe();
  assert.match(identity.executableDigest,/^[a-f0-9]{64}$/);
  assert.equal(owner.nativeIdentityCurrent(identity),true);
  await assert.rejects(owner.resolveService.readSdkLiveInspection('marker.create',{}),error=>error.code==='CAPABILITY_UNAVAILABLE');
  await assert.rejects(owner.resolveService.readSdkLiveInspection('project.current',{deadlineAtMs:Date.now()-1}),error=>error.name==='TimeoutError');
});
