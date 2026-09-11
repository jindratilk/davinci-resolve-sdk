import test from 'node:test';
import assert from 'node:assert/strict';
import {createSdkOperationRetentionLifecycle} from '../runtime/bridge/services/sdk-operation-retention-lifecycle.js';

test('retention cleanup follows readiness, repeats on schedule, and stops durably', async () => {
  let cleanupCalls = 0;
  let scheduled = null;
  let cleared = null;
  let releaseReadiness;
  const readiness = new Promise(resolve => { releaseReadiness = resolve; });
  const lifecycle = createSdkOperationRetentionLifecycle({
    operationAuthority: {cleanup() { cleanupCalls += 1; }},
    sweepIntervalMs: 2_345,
    scheduleInterval(callback, interval) {
      scheduled = {callback, interval, unref() {}};
      return scheduled;
    },
    clearScheduledInterval(timer) { cleared = timer; },
  });

  const starting = lifecycle.startAfter(readiness);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(cleanupCalls, 0);
  assert.equal(scheduled, null);
  releaseReadiness();
  await starting;
  assert.equal(cleanupCalls, 1);
  assert.equal(scheduled.interval, 2_345);
  scheduled.callback();
  assert.equal(cleanupCalls, 2);

  lifecycle.stop();
  assert.equal(cleared, scheduled);
  scheduled.callback();
  assert.equal(cleanupCalls, 2);
});

test('shutdown before readiness prevents startup cleanup and scheduling', async () => {
  let cleanupCalls = 0;
  let scheduleCalls = 0;
  let releaseReadiness;
  const readiness = new Promise(resolve => { releaseReadiness = resolve; });
  const lifecycle = createSdkOperationRetentionLifecycle({
    operationAuthority: {cleanup() { cleanupCalls += 1; }},
    scheduleInterval() { scheduleCalls += 1; return {unref() {}}; },
    clearScheduledInterval() {},
  });

  const starting = lifecycle.startAfter(readiness);
  lifecycle.stop();
  releaseReadiness();
  await starting;
  assert.equal(cleanupCalls, 0);
  assert.equal(scheduleCalls, 0);
});

test('startup cleanup failure is reported and remains a startup failure', async () => {
  const cause = Object.assign(new Error('durable retention store rejected cleanup'), {
    code: 'SDK_OPERATION_AUTHORITY_UNAVAILABLE',
  });
  const reported = [];
  let scheduleCalls = 0;
  const lifecycle = createSdkOperationRetentionLifecycle({
    operationAuthority: {cleanup() { throw cause; }},
    scheduleInterval() { scheduleCalls += 1; return {unref() {}}; },
    clearScheduledInterval() {},
    onCleanupError(error) { reported.push(error); },
  });

  await assert.rejects(lifecycle.startAfter(Promise.resolve()), error => error === cause);
  assert.deepEqual(reported, [cause]);
  assert.equal(scheduleCalls, 0);
  lifecycle.stop();
});
