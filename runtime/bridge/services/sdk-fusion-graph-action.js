import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  CUTAGENT_SDK_FUSION_GRAPH_ACTION_ID,
  sdkFusionGraphApplyInputSchema,
  sdkFusionGraphApplyResultSchema,
} from "../contracts/generated/sdk-fusion.js";
import { MutationPolicyError } from "./mutation-policy/mutation-policy-gate.js";
import {resolveSdkDirectMutationScope, sdkMutationScopeCandidates} from "./sdk-direct-mutation-scope.js";
import { mutationPolicyDigest } from "./mutation-policy/impact-lowering.js";

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
  const errorCode = error?.cli_error_code ?? error?.code;
  const typed = {
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

function selectScope(mutationPolicyGate, accountFingerprint, target, directScope = null) {
  const scopes = sdkMutationScopeCandidates(mutationPolicyGate, accountFingerprint, directScope).filter((scope) => (
    scope.binding.level === "project+timeline"
    && scope.binding.projectId === target.projectId
    && scope.binding.timelineId === target.timelineId
    && scope.binding.timelineRevision === target.timelineRevision
  ));
  if (scopes.length !== 1) {
    throw new MutationPolicyError(
      scopes.length === 0 ? "missing_scope" : "ambiguous_impact",
      scopes.length === 0
        ? "A current project-and-timeline editing-constraint scope is required for Fusion graph apply."
        : "More than one editing-constraint scope matches this exact Fusion target.",
    );
  }
  return scopes[0];
}

function declaredProtectedTargets(scope, inventory) {
  const currentByIdentity = new Map(inventory.map((target) => [`${target.kind}\0${target.stableId}`, target]));
  return scope.constraints.protectedTargets.map((target) => {
    const current = currentByIdentity.get(`${target.kind}\0${target.stableId}`);
    if (!current) {
      const error = new Error("A declared protected target is absent from the live Fusion inspection.");
      error.code = "STALE_REVISION";
      throw error;
    }
    return current;
  });
}

/** Build the sole accepted durable SDK Fusion action definition. */
export function createSdkFusionGraphAction({
  resolveService,
  liveInspectionService,
  mutationPolicyGate,
  tempRoot = os.tmpdir(),
  expectedRegistryDigest,
  directMutationPolicyAuthority = null,
} = {}) {
  if (typeof resolveService?.applySdkFusionGraph !== "function"
    || typeof liveInspectionService?.resolveFusionMutationTarget !== "function"
    || typeof liveInspectionService?.refreshFusionMutationTarget !== "function"
    || !mutationPolicyGate
    || !/^sha256:[0-9a-f]{64}$/.test(expectedRegistryDigest ?? "")) {
    throw new TypeError("SDK Fusion graph action requires live target, policy, and CLI authorities.");
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
      let scope;
      let policyContext;
      let refreshProtectedTargets;
      let liveResolutionOptions;
      try {
        const directScope = await resolveSdkDirectMutationScope({directMutationPolicyAuthority, context, liveInspectionService, level: "project+timeline", projectId: input.target.projectId, timelineId: input.target.timelineId, timelineRevision: input.target.timelineRevision});
        scope = selectScope(mutationPolicyGate, context.accountFingerprint, input.target, directScope);
        liveResolutionOptions = {
          deadlineAtMs: Date.now() + 60_000,
          protectedTargets: scope.constraints.protectedTargets,
          projectLibraryId: scope.binding.projectLibraryId,
        };
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
        const assertExactTargetCurrent = (current) => {
          if (current.reference.revision !== input.precondition
            || current.reference.graphDigest !== input.target.graphDigest) {
            const error = new Error("The exact Fusion composition revision changed before execution.");
            error.code = "STALE_REVISION";
            throw error;
          }
          return current;
        };
        assertExactTargetCurrent(resolved);
        refreshProtectedTargets = async () => {
          const current = assertExactTargetCurrent(await liveInspectionService.resolveFusionMutationTarget({
            operation: "fusion.compositions",
            projectId: input.target.projectId,
            timelineId: input.target.timelineId,
            timelineItemId: input.target.timelineItemId,
            expectedRevision: input.target.timelineRevision,
            fusionCompositionId: input.target.id,
          }, {
            ...liveResolutionOptions,
            deadlineAtMs: Date.now() + 60_000,
          }));
          return declaredProtectedTargets(scope, current.currentProtectedTargets);
        };
        policyContext = {
          requestId: context.requestId,
          operationId: context.operationId,
          executionId: context.executionId,
          scopeId: scope.scopeId,
          scopeRevision: scope.revision,
          projectLibraryId: scope.binding.projectLibraryId,
          projectId: input.target.projectId,
          timelineId: input.target.timelineId,
          projectRevision: scope.binding.projectRevision,
          timelineRevision: input.target.timelineRevision,
          resolvedTargets: [
            { kind: "clip", stableId: input.target.timelineItemId, revision: input.target.timelineRevision },
            { kind: "fusion_composition", stableId: input.target.id, revision: input.target.revision },
          ],
          currentProtectedTargets: declaredProtectedTargets(scope, resolved.currentProtectedTargets),
          placementIntent: "explicit",
          executableStableTargetPrecondition: true,
          closedComposition: true,
        };
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
          policyContext,
          refreshProtectedTargets,
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
            { evidenceId: opaque("evidence_"), modality: "structural", summary: "Native node and connection structure matched the typed graph.", capturedAt: iso(), digest: mutationPolicyDigest(readback) },
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
        const consumedDecision = mutationPolicyGate.inspectDecisions().find((row) => (
          row.operationId === context.operationId && row.executionId === context.executionId && row.state === "consumed"
        ));
        if (!consumedDecision) throw new Error("The consumed Fusion mutation-policy decision is unavailable for verification.");
        mutationPolicyGate.assertProtectedStateEvidence(
          consumedDecision.decisionId,
          verification,
          declaredProtectedTargets(scope, refreshed.currentProtectedTargets),
        );
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
          && (error instanceof MutationPolicyError || error?.failure?.possibleMutation === "none"))
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
