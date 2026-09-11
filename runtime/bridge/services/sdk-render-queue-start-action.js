import crypto from "node:crypto";
import {
  sdkRenderQueueStartInputSchema,
  sdkRenderQueueStartResultSchema,
} from "../contracts/generated/sdk-operations.js";

const ACTION_ID = "cutagent.action.render.start";
const COMPLETE = new Set(["completed"]);
const FAILED = new Set(["failed", "cancelled"]);

const deferred = () => {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
};

const digest = (value) => `sha256:${crypto.createHash("sha256").update(JSON.stringify(value), "utf8").digest("hex")}`;
const evidence = (summary, value) => ({
  evidenceId: `evidence_${crypto.randomUUID()}`,
  modality: "readback",
  summary,
  capturedAt: new Date().toISOString(),
  digest: digest(value),
});

function publicResult(input, selections) {
  return sdkRenderQueueStartResultSchema.parse({
    projectId: input.projectId,
    queueRevision: input.queueRevision,
    jobs: selections.map(({ job }) => ({
      id: job.id,
      statusSupport: job.statusSupport,
      status: job.status,
      progressPercent: job.progressPercent,
    })),
  });
}

function failure(code, message, context, possibleMutation = "none", usage = possibleMutation === "none" ? "released" : "consumed") {
  return {
    kind: code === "STALE_REVISION" ? "stale_revision"
      : code === "VERIFICATION_FAILED" ? "verification_failed"
        : code === "CANCELLED" ? "cancelled" : "operation_failed",
    code,
    message,
    retrySafe: false,
    possibleMutation,
    usage,
    recovery: possibleMutation === "none" ? ["inspect_state"] : ["inspect_state", "manual_recovery"],
    recoveryGuidance: [possibleMutation === "none"
      ? "Refresh the render queue and select current job snapshots."
      : "Refresh every selected render job before starting replacement work."],
    readbackRequired: possibleMutation !== "none",
    requestId: context.requestId,
    operationId: context.operationId,
    executionId: context.executionId,
  };
}

function knownStatus(selection) {
  return selection.job.statusSupport?.availability === "supported" && selection.job.status?.kind === "known"
    ? selection.job.status.value
    : null;
}

function exactStartAcknowledgement(response, nativeJobIds) {
  const data = response?.data;
  return data?.action === "render.start"
    && data.changed === true
    && data.started === true
    && data.wait === false
    && data.jobs === nativeJobIds.join(",");
}

function report(selections, outcome = "passed") {
  const statuses = selections.map(({ job }) => ({ id: job.id, status: job.status, progressPercent: job.progressPercent }));
  return {
    outcome,
    summary: outcome === "passed"
      ? "Every selected native render job reached independently readable completed status."
      : "At least one selected native render job did not reach completed status.",
    evidence: [evidence("Read back every selected render job after the shared native dispatch.", statuses)],
    protectedStatePreserved: null,
  };
}

export function createSdkRenderQueueStartAction({ liveInspectionService, run, acquireOwnership, wait }) {
  if (typeof liveInspectionService?.resolveRenderJobSelections !== "function"
    || typeof run !== "function" || typeof acquireOwnership !== "function" || typeof wait !== "function") {
    throw new TypeError("Render queue start requires exact job resolution, native execution, and shared render ownership.");
  }
  const states = new Map();

  const resolve = (input) => liveInspectionService.resolveRenderJobSelections(input, { deadlineAtMs: Date.now() + 30_000 });

  const terminal = async (state, baseline, { requireTransition }) => {
    const transitioned = new Set();
    for (;;) {
      if (state.stopRequested) {
        if (state.cancellationProof) await state.cancellationProof.promise;
        if (state.cancellationConfirmed) throw Object.assign(new Error("Render queue start cancelled."), { cancelled: true });
        throw new Error("Render queue cancellation could not be confirmed.");
      }
      const selections = await resolve(state.input);
      selections.forEach((selection, index) => {
        const status = knownStatus(selection);
        if (status !== baseline[index] || status === "rendering") transitioned.add(selection.job.id);
      });
      const statuses = selections.map(knownStatus);
      const progress = selections.map(({ job }) => job.progressPercent ?? 0);
      state.context.reportProgress?.({
        phase: "rendering",
        overallFraction: Math.min(0.99, progress.reduce((sum, value) => sum + value, 0) / (100 * progress.length)),
        phaseFraction: Math.min(1, progress.reduce((sum, value) => sum + value, 0) / (100 * progress.length)),
      });
      if (statuses.some((status) => status === null)) {
        throw Object.assign(new Error("A selected render job has no trustworthy status readback."), { selections });
      }
      if (statuses.some((status) => FAILED.has(status))) {
        throw Object.assign(new Error("A selected render job ended without completing."), { selections });
      }
      if (statuses.every((status) => COMPLETE.has(status))
        && (!requireTransition || state.startAcknowledged || transitioned.size === selections.length)) return selections;
      await wait(500);
    }
  };

  const success = (state, selections) => ({
    status: "succeeded",
    possibleMutation: "confirmed",
    usage: "consumed",
    verification: report(selections),
    result: publicResult(state.input, selections),
  });

  const executeState = async (state, { dispatch }) => {
    let releaseOwnership;
    try {
      releaseOwnership = await acquireOwnership();
      state.phase = "resolving";
      const initial = await resolve(state.input);
      const baseline = initial.map(knownStatus);
      if (baseline.some((status) => status === null)) {
        return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("VERIFICATION_FAILED", "A selected render job has no trustworthy initial status.", state.context) };
      }
      if (state.stopRequested) throw Object.assign(new Error("Render queue start cancelled."), { cancelled: true });
      if (dispatch) {
        state.phase = "starting";
        state.startAttempted = true;
        const nativeJobIds = initial.map(({ nativeJobId }) => nativeJobId);
        try {
          const response = await run(["render", "start", "--jobs", nativeJobIds.join(","), "--no-wait"], {
            onAuthorization: () => state.context.reportExecutionStarted?.(),
          });
          if (!exactStartAcknowledgement(response, nativeJobIds)) {
            throw Object.assign(new Error("CutAgent CLI did not acknowledge the exact plural native render start."), { code: "VERIFICATION_FAILED" });
          }
          state.startAcknowledged = true;
          state.started = true;
        } finally {
          state.startSettled.resolve();
        }
      }
      state.phase = "rendering";
      return success(state, await terminal(state, baseline, { requireTransition: dispatch }));
    } catch (error) {
      if (state.stopRequested && state.cancellationProof) {
        state.cancellationConfirmed = await state.cancellationProof.promise;
      }
      if (error?.cancelled === true || state.cancellationConfirmed) {
        return {
          status: "cancelled",
          possibleMutation: state.startAttempted ? "partial" : "none",
          usage: state.startAttempted ? "consumed" : "released",
          cancellation: { state: "confirmed", requestedAt: state.cancelRequestedAt, confirmedAt: new Date().toISOString() },
          failure: failure("CANCELLED", "The selected render run stopped after a confirmed cancellation request.", state.context, state.startAttempted ? "partial" : "none", state.startAttempted ? "consumed" : "released"),
        };
      }
      const selections = error?.selections;
      if (state.started && Array.isArray(selections)) {
        const verification = report(selections, "failed");
        return {
          status: "verification_failed",
          possibleMutation: "confirmed",
          usage: "consumed",
          result: publicResult(state.input, selections),
          failure: failure("VERIFICATION_FAILED", "A selected render job did not complete successfully.", state.context, "confirmed", "consumed"),
          verification,
          recovery: { state: "manual_required", summary: "Inspect each selected render job before retrying.", evidence: verification.evidence, manualRecoveryRequired: true },
        };
      }
      const code = error?.code === "STALE_REVISION" ? "STALE_REVISION" : "OPERATION_FAILED";
      return {
        status: "failed",
        possibleMutation: state.startAttempted ? "possible" : "none",
        usage: state.startAttempted ? "consumed" : "released",
        failure: failure(code, state.startAttempted ? "The shared native render dispatch could not be reconciled." : "The selected render jobs could not be started safely.", state.context, state.startAttempted ? "possible" : "none", state.startAttempted ? "consumed" : "released"),
      };
    } finally {
      releaseOwnership?.();
    }
  };

  const execute = async (context, rawInput) => {
    const state = {
      context,
      input: sdkRenderQueueStartInputSchema.parse(rawInput),
      phase: "waiting_for_ownership",
      started: false,
      startAttempted: false,
      startAcknowledged: false,
      stopRequested: false,
      cancelRequestedAt: null,
      cancellationProof: null,
      cancellationConfirmed: false,
      startSettled: deferred(),
      settled: deferred(),
    };
    states.set(context.operationId, state);
    try { return await executeState(state, { dispatch: true }); }
    finally { state.settled.resolve(); states.delete(context.operationId); }
  };

  const cancel = async (context) => {
    const state = states.get(context.operationId);
    if (!state) return { confirmed: false, reason: "The selected render run no longer has active executor custody." };
    state.cancelRequestedAt = new Date().toISOString();
    state.stopRequested = true;
    state.cancellationProof ??= deferred();
    if (state.phase === "starting") await state.startSettled.promise;
    if (!state.startAttempted) {
      state.cancellationConfirmed = true;
      state.cancellationProof.resolve(true);
      return { confirmed: true, possibleMutation: "none", usage: "released", readbackRequired: false };
    }
    try {
      await run(["render", "stop"], { onAuthorization: () => {} });
      const selected = await resolve(state.input);
      const stopped = selected.every((selection) => knownStatus(selection) !== "rendering");
      state.cancellationConfirmed = stopped;
      state.cancellationProof.resolve(stopped);
      await state.settled.promise;
      return stopped
        ? { confirmed: true, possibleMutation: "partial", usage: "consumed", readbackRequired: true }
        : { confirmed: false, reason: "At least one selected native render job remained active after stop." };
    } catch {
      state.cancellationProof.resolve(false);
      return { confirmed: false, reason: "The shared native render stop could not be confirmed." };
    }
  };

  const reconcile = async (context, rawInput) => {
    const state = {
      context: { ...context, reportProgress() {} }, input: sdkRenderQueueStartInputSchema.parse(rawInput),
      phase: "reconciling", started: true, startAttempted: true, startAcknowledged: false, stopRequested: false, cancelRequestedAt: null,
      cancellationProof: null, cancellationConfirmed: false, startSettled: deferred(), settled: deferred(),
    };
    states.set(context.operationId, state);
    try { return await executeState(state, { dispatch: false }); }
    finally { state.settled.resolve(); states.delete(context.operationId); }
  };

  return Object.freeze({
    inputSchema: sdkRenderQueueStartInputSchema,
    resultSchema: sdkRenderQueueStartResultSchema,
    idempotency: "required",
    execute,
    cancel,
    reconcile,
  });
}
