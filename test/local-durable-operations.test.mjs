import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, rm} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {z} from 'zod';
import {createSdkOperationRepo} from '../runtime/bridge/repos/sdk-operation-repo.js';
import {createSdkOperationAuthority} from '../runtime/bridge/services/sdk-operation-authority.js';
import {createLocalPrincipalAuthority} from '../runtime/local/principal.mjs';

test('existing durable owner preserves local identity and idempotency across restart', async t => {
  const storageDir = await mkdtemp(join(tmpdir(), 'standalone-operations-'));
  t.after(() => rm(storageDir, {recursive: true, force: true}));
  let calls = 0;
  const actionId = 'cutagent.action.audio.duck';
  // Explicit test executor exercises the existing durable protocol, no native mutation.
  const actions = {[actionId]: {
    inputSchema: z.object({amount: z.number()}).strict(),
    resultSchema: z.object({changed: z.boolean()}).strict(),
    idempotency: 'required',
    async execute() {
      calls++;
      return {status: 'succeeded', result: {changed: false}, possibleMutation: 'none', usage: 'not_reserved',
        verification: {outcome: 'not_performed', summary: 'Non-mutating test executor.', evidence: [], protectedStatePreserved: null}};
    },
  }};
  function start() {
    const repo = createSdkOperationRepo({storageDir});
    const principal = createLocalPrincipalAuthority({installationAuthority: repo.installationAuthority});
    return {repo, principal, authority: createSdkOperationAuthority({repo, actions})};
  }
  const first = start();
  const accountFingerprint = first.principal.capture().accountFingerprint;
  const request = {accountFingerprint, actionId, requestId: 'request_standalone_1234', input: {amount: 2}, idempotencyKey: 'idempotency_standalone_1234'};
  const created = first.authority.create(request);
  assert.throws(start, /ownership|owner|already/i);
  await first.authority.waitForIdle();
  assert.equal(first.authority.get({accountFingerprint, operationId: created.snapshot.operationId}).status, 'succeeded');
  first.principal.close();
  first.repo.releaseOwnership();
  const second = start();
  try {
    await second.authority.reconcileOrphans();
    assert.equal(second.principal.capture().accountFingerprint, accountFingerprint);
    const replay = second.authority.create(request);
    assert.equal(replay.replayed, true);
    assert.equal(replay.snapshot.operationId, created.snapshot.operationId);
    assert.equal(calls, 1);
    assert.throws(() => second.authority.create({...request, input: {amount: 3}}), e => e.failure?.code === 'IDEMPOTENCY_CONFLICT');
    const other = createLocalPrincipalAuthority({installationAuthority: 'sdk_installation_another'});
    assert.throws(() => second.authority.get({accountFingerprint: other.capture().accountFingerprint, operationId: created.snapshot.operationId}));
    assert.equal(calls, 1);
    other.close();
  } finally {second.principal.close(); second.repo.releaseOwnership();}
});
