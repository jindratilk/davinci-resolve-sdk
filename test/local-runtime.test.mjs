import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, chmod, rm, readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
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
  const {createNativeInspectionOwner}=await import('../runtime/local/native-inspection.mjs');
  const owner=createNativeInspectionOwner({python:'/not-a-python-executable',transport:'studio_external'});
  const identity=owner.nativeIdentityProbe();
  assert.match(identity.executableDigest,/^[a-f0-9]{64}$/);
  assert.equal(owner.nativeIdentityCurrent(identity),true);
  await assert.rejects(owner.resolveService.readSdkLiveInspection('marker.create',{}),error=>error.code==='CAPABILITY_UNAVAILABLE');
  await assert.rejects(owner.resolveService.readSdkLiveInspection('project.current',{deadlineAtMs:Date.now()-1}),error=>error.name==='TimeoutError');
});
