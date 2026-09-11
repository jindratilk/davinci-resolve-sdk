import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  CUTAGENT_SDK_FUSION_GRAPH_ACTION_ID,
  sdkFusionGraphApplyInputSchema,
  sdkFusionGraphApplyResultSchema,
} from "../contracts/generated/sdk-fusion.js";

function opaque(prefix) { return `${prefix}${crypto.randomUUID()}`; }
function iso() { return new Date().toISOString(); }
function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonicalize(value[key])]));
  }
  return Object.is(value, -0) ? 0 : value;
}

function publicFailure(error, fallback) {
  if (error?.failure) return error.failure;
  return {
    kind: "operation_failed",
    code: "OPERATION_FAILED",
    message: fallback,
    retrySafe: false,
    possibleMutation: "possible",
    usage: "consumed",
    recovery: ["inspect_state", "manual_recovery"],
    recoveryGuidance: ["Inspect the exact Fusion composition and rendered output before creating replacement work."],
    readbackRequired: true,
  };
}

function preEffectFailure(error) {
  const reportedCode = error?.cli_error_code ?? error?.code;
  const errorCode = ["AUTH_REQUIRED", "AUTH_TOKEN_INVALID"].includes(reportedCode) ? "AUTHENTICATION_REQUIRED" : reportedCode;
  const typed = {
    AUTHENTICATION_REQUIRED: "authentication_required",
    STALE_REVISION: "stale_revision",
    TARGET_NOT_FOUND: "target_not_found",
    AMBIGUOUS_TARGET: "ambiguous_target",
    INVALID_RESPONSE: "invalid_response",
  }[errorCode];
  return {
    status: "failed",
    possibleMutation: "none",
    usage: "not_reserved",
    failure: error?.failure ?? {
      kind: typed ?? "operation_failed",
      code: typed ? errorCode : "OPERATION_FAILED",
      message: typed ? error.message : "The exact Fusion graph target could not be authorized before execution.",
      retrySafe: false,
      possibleMutation: "none",
      usage: "not_reserved",
      recovery: ["inspect_state"],
      recoveryGuidance: ["Inspect the current project, timeline, and Fusion composition before creating replacement work."],
      readbackRequired: false,
    },
  };
}

function recoveredEffectFailure(error) {
  const graphDigest = error?.cli_error_details?.recovered_graph_digest;
  const summary = "The Fusion graph apply failed, and exact native readback proved that the pre-mutation graph was restored.";
  const recoveryEvidence = [{
    evidenceId: opaque("evidence_"), modality: "readback", summary,
    capturedAt: iso(), digest: graphDigest,
  }];
  return {
    status: "failed", possibleMutation: "none", usage: "consumed",
    failure: {
      kind: "operation_failed", code: "OPERATION_FAILED", message: "Fusion graph execution failed after authorization.",
      retrySafe: false, possibleMutation: "none", usage: "consumed", recovery: ["continue"],
      recoveryGuidance: ["Create a fresh Fusion impact preview before deciding whether to retry."],
      recoveryOutcome: { status: "succeeded", summary }, readbackRequired: false,
    },
    recovery: { state: "restored", summary, evidence: recoveryEvidence, manualRecoveryRequired: false },
  };
}

function partialEffectFailure(error) {
  const details = error?.cli_error_details ?? {};
  const evidence = [details.expected_graph_digest, details.observed_graph_digest]
    .filter((value) => /^sha256:[0-9a-f]{64}$/.test(value ?? ""))
    .map((digestValue, index) => ({
      evidenceId: opaque("evidence_"), modality: "readback",
      summary: index === 0 ? "Expected pre-mutation Fusion graph digest." : "Observed graph digest after failed recovery.",
      capturedAt: iso(), digest: digestValue,
    }));
  return {
    status: "partially_applied", possibleMutation: "partial", usage: "consumed",
    failure: {
      ...publicFailure(error, "Fusion graph execution failed and left a changed native graph."),
      possibleMutation: "partial", readbackRequired: true,
    },
    verification: {
      outcome: "partial", summary: "Exact native recovery readback found a graph that differed from the authorized pre-state.",
      evidence, protectedStatePreserved: false,
    },
    recovery: { state: "manual_required", summary: "Inspect and recover the exact Fusion composition before any further mutation.", evidence, manualRecoveryRequired: true },
  };
}

/** Build the sole accepted durable SDK Fusion action definition. */
export function createSdkFusionGraphAction({
  resolveService,
  liveInspectionService,
  tempRoot = os.tmpdir(),
  expectedRegistryDigest,
} = {}) {
  if (typeof resolveService?.applySdkFusionGraph !== "function"
    || typeof liveInspectionService?.resolveFusionMutationTarget !== "function"
    || typeof liveInspectionService?.refreshFusionMutationTarget !== "function"
    || !/^sha256:[0-9a-f]{64}$/.test(expectedRegistryDigest ?? "")) {
    throw new TypeError("SDK Fusion graph action requires live target inspection and the CutAgent CLI execution boundary.");
  }
  return Object.freeze({
    inputSchema: sdkFusionGraphApplyInputSchema,
    resultSchema: sdkFusionGraphApplyResultSchema,
    idempotency: "required",
    async execute(context, rawInput) {
      const input = sdkFusionGraphApplyInputSchema.parse(rawInput);
      const authoredGraphDigest = `sha256:${crypto.createHash("sha256")
        .update(JSON.stringify(canonicalize(input.graph)), "utf8").digest("hex")}`;
      if (input.graph.registryDigest !== expectedRegistryDigest) {
        return preEffectFailure(Object.assign(new Error("The Fusion graph registry does not match the activated packaged runtime."), {
          code: "INVALID_RESPONSE",
        }));
      }
      if (input.preview.graphDigest !== authoredGraphDigest
        || JSON.stringify(input.preview.target) !== JSON.stringify(input.target)) {
        return preEffectFailure(Object.assign(new Error("The Fusion graph impact preview does not match the exact authored request."), {
          code: "INVALID_RESPONSE",
        }));
      }
      context.reportProgress({ phase: "authorizing", overallFraction: 0.05, phaseFraction: 0.1 });
      let resolved;
      let liveResolutionOptions;
      try {
        liveResolutionOptions = { deadlineAtMs: Date.now() + 60_000 };
        resolved = await liveInspectionService.resolveFusionMutationTarget({
          operation: "fusion.compositions",
          projectId: input.target.projectId,
          timelineId: input.target.timelineId,
          timelineItemId: input.target.timelineItemId,
          expectedRevision: input.target.timelineRevision,
          fusionCompositionId: input.target.id,
        }, liveResolutionOptions);
        if (resolved.reference.revision !== input.precondition
          || resolved.reference.graphDigest !== input.target.graphDigest) {
          const error = new Error("The exact Fusion composition revision changed before authorization.");
          error.code = "STALE_REVISION";
          throw error;
        }
        if (context.isCancellationRequested()) {
          const requestedAt = context.cancellationRequestedAt() ?? iso();
          return {
            status: "cancelled",
            possibleMutation: "none",
            usage: "not_reserved",
            failure: {
              kind: "cancelled", code: "CANCELLED", message: "Fusion graph apply was cancelled before execution.",
              retrySafe: false, possibleMutation: "none", usage: "not_reserved", recovery: ["continue"],
              recoveryGuidance: ["Inspect current state before deciding whether to create new work."], readbackRequired: false,
            },
            cancellation: { state: "confirmed", requestedAt, confirmedAt: iso() },
          };
        }
      } catch (error) {
        return preEffectFailure(error);
      }

      context.reportProgress({ phase: "applying", overallFraction: 0.3, phaseFraction: 0.1 });
      const workingDirectory = fs.mkdtempSync(path.join(tempRoot, "cutagent-sdk-fusion-"));
      let cliResult;
      let executionMayHaveStarted = false;
      try {
        cliResult = await resolveService.applySdkFusionGraph({
          target: resolved.nativeTarget,
          graph: input.graph,
          expectedGraphDigest: input.target.graphDigest,
        }, {
          workingDirectory,
          onSpawnAttempt() {
            if (typeof context.reportExecutionStarted !== "function") {
              throw new Error("The durable operation authority cannot record Fusion execution start.");
            }
            context.reportExecutionStarted();
            executionMayHaveStarted = true;
          },
        });
        executionMayHaveStarted = true;
        context.reportProgress({ phase: "verifying", overallFraction: 0.75, phaseFraction: 0.2 });
        const refreshed = await liveInspectionService.refreshFusionMutationTarget({
          operation: "fusion.compositions",
          projectId: input.target.projectId,
          timelineId: input.target.timelineId,
          timelineItemId: input.target.timelineItemId,
          expectedRevision: null,
          fusionCompositionId: input.target.id,
        }, {
          ...liveResolutionOptions,
          deadlineAtMs: Date.now() + 60_000,
        });
        const cliEvidence = JSON.stringify(canonicalize(cliResult.nativeGraphEvidence));
        const refreshedEvidence = JSON.stringify(canonicalize(refreshed.nativeTarget.nativeGraphEvidence));
        if (cliEvidence !== refreshedEvidence
          || cliResult.readback.graphDigest !== refreshed.reference.graphDigest) {
          throw new Error("The Fusion graph changed between committed readback and independent live refresh.");
        }
        const readback = { ...cliResult.readback, graphDigest: refreshed.reference.graphDigest };
        const protectedStatePreserved = cliResult.protectedState.projectNativeId === resolved.nativeTarget.projectNativeId
          && cliResult.protectedState.timelineNativeId === resolved.nativeTarget.timelineNativeId
          && cliResult.protectedState.timelineItemNativeId === resolved.nativeTarget.timelineItemNativeId
          && cliResult.protectedState.preserved === true
          && cliResult.protectedState.beforeDigest === cliResult.protectedState.afterDigest;
        const verification = {
          outcome: protectedStatePreserved ? "passed" : "failed",
          summary: protectedStatePreserved
            ? "Exact Fusion graph structural readback and protected-state verification passed."
            : "Fusion graph verification did not prove protected-state preservation.",
          evidence: [
            { evidenceId: opaque("evidence_"), modality: "readback", summary: "Exact native node/input readback matched the requested graph.", capturedAt: iso(), digest: readback.graphDigest },
            { evidenceId: opaque("evidence_"), modality: "structural", summary: "Native node and connection structure matched the typed graph.", capturedAt: iso(), digest: `sha256:${crypto.createHash("sha256").update(JSON.stringify(canonicalize(readback))).digest("hex")}` },
          ],
          protectedStatePreserved,
        };
        if (verification.outcome !== "passed") {
          return {
            status: "verification_failed",
            possibleMutation: "confirmed",
            usage: "consumed",
            failure: {
              ...publicFailure(null, verification.summary),
              kind: "verification_failed",
              code: "VERIFICATION_FAILED",
            },
            verification,
            recovery: { state: "manual_required", summary: "Inspect the exact live Fusion graph and protected state.", evidence: verification.evidence, manualRecoveryRequired: true },
          };
        }
        return {
          status: "succeeded",
          possibleMutation: "confirmed",
          usage: "consumed",
          result: {
            target: refreshed.reference,
            registryDigest: cliResult.registryDigest,
            appliedGraphDigest: cliResult.appliedGraphDigest,
            readback,
            renderedEvidence: [],
            renderedReview: { outcome: "not_run" },
            semanticReview: { outcome: "not_run" },
            temporalReview: {
              required: input.graph.graph.animations.length > 0,
              sampledFrames: [],
              outcome: "not_run",
            },
            protectedStatePreserved: true,
          },
          verification,
        };
      } catch (error) {
        if ((!executionMayHaveStarted
          && (["AUTH_REQUIRED", "AUTH_TOKEN_INVALID"].includes(error?.cli_error_code ?? error?.code) || error?.failure?.possibleMutation === "none"))
          || error?.cli_error_code === "STALE_REVISION") {
          return preEffectFailure(error);
        }
        if (error?.cli_error_details?.recovery === "restored"
          && /^sha256:[0-9a-f]{64}$/.test(error.cli_error_details.recovered_graph_digest ?? "")) {
          return recoveredEffectFailure(error);
        }
        if (error?.cli_error_details?.recovery === "partial") {
          return partialEffectFailure(error);
        }
        return {
          status: "failed",
          possibleMutation: "possible",
          usage: "consumed",
          failure: publicFailure(error, "Fusion graph execution failed after authorization."),
          recovery: { state: "manual_required", summary: "Automatic recovery could not be proved after execution began.", evidence: [], manualRecoveryRequired: true },
        };
      } finally {
        fs.rmSync(workingDirectory, { recursive: true, force: true });
      }
    },
  });
}

export { CUTAGENT_SDK_FUSION_GRAPH_ACTION_ID };
