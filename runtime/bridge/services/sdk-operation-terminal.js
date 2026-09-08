import {
  CUTAGENT_SDK_ACTION_CONTRACT_VERSION,
  sdkFairlightBoundTerminalSchema,
  sdkOperationSnapshotSchema,
  sdkPublicFailureSchema,
  sdkVerificationReportSchema,
} from "../contracts/generated/sdk-operations.js";
import { sdkRevisionSchema } from "../contracts/generated/sdk-identities.js";
import { canonicalSdkOperationInput } from "./sdk-operation-input.js";
import {
  editResultCollectionSpecs,
  projectSdkOperationResultCollections,
} from "./sdk-operation-result-collections.js";

function iso(value) {
  return new Date(value).toISOString();
}

function operationCommon(snapshot) {
  return {
    operationId: snapshot.operationId,
    requestId: snapshot.requestId,
    executionId: snapshot.executionId,
    actionId: snapshot.actionId,
    actionContractVersion: snapshot.actionContractVersion,
    createdAt: snapshot.createdAt,
    idempotency: snapshot.idempotency,
  };
}

function correlatedFailure(record, failure) {
  return sdkPublicFailureSchema.parse({
    ...failure,
    requestId: record.public.requestId,
    operationId: record.public.operationId,
    executionId: record.public.executionId,
    possibleMutation: failure.possibleMutation,
    usage: failure.usage,
  });
}

function rejectedCancellation(record, now, reason) {
  return record.public.status === "cancellation_requested"
    ? { cancellation: {
      state: "rejected",
      requestedAt: record.public.cancellation.requestedAt,
      resolvedAt: iso(now()),
      reason,
    } }
    : {};
}

function semanticResultStatus(result, normalizedInput) {
  if (result?.actionId === "cutagent.action.sdk.fairlight.plan.apply"
    && ["succeeded", "no_change", "partial"].includes(result.outcome)) {
    return result.outcome === "succeeded" ? "completed" : result.outcome;
  }
  const payload = result?.payload;
  if (result?.actionId?.startsWith("cutagent.action.media.")
    && typeof payload?.changed === "boolean"
    && ["completed", "no_op", "partial", "manual_review_required"].includes(payload?.status)) {
    return payload.status === "no_op" ? "no_change" : payload.status;
  }
  if (result?.actionId === "cutagent.action.color.gallery.still.export") {
    const destinationArtifactId = normalizedInput?.destinationArtifactId;
    const exactExport = result?.exportedStill;
    const normalizedArtifact = payload?.data?.artifacts?.find(
      (artifact) => artifact?.artifactId === destinationArtifactId && artifact?.byteLength > 0,
    );
    const normalizedEvidence = payload?.verification?.evidence?.some(
      (item) => item?.kind === "artifact_readback" && item?.artifactId === destinationArtifactId,
    );
    const exactProof = exactExport?.artifactId === destinationArtifactId
      && exactExport?.exists === true
      && exactExport?.byteCount > 0;
    if (!exactProof && (!normalizedArtifact || !normalizedEvidence)) {
      throw new Error("Gallery export result must prove the requested nonempty artifact.");
    }
  }
  if (payload?.data?.artifacts && normalizedInput?.destinationArtifactId) {
    const artifactId = normalizedInput.destinationArtifactId;
    const nonemptyArtifact = payload.data.artifacts.some(
      (artifact) => artifact?.artifactId === artifactId && artifact?.byteLength > 0,
    );
    const artifactEvidence = payload.verification?.evidence?.some(
      (item) => item?.kind === "artifact_readback" && item?.artifactId === artifactId,
    );
    if (["completed", "no_change"].includes(payload.status) && (!nonemptyArtifact || !artifactEvidence)) {
      throw new Error("Color artifact result must prove the requested nonempty artifact.");
    }
    if (["partial", "manual_recovery_required"].includes(payload.status)
      && (!Array.isArray(payload.verification?.evidence) || payload.verification.evidence.length === 0)) {
      throw new Error("Non-success Color artifact results require verification evidence.");
    }
    return payload.status;
  }
  if (!payload || typeof payload !== "object" || !Object.hasOwn(payload, "revision")) return null;
  const { status, revision, change, verification, targets } = payload;
  if (!["completed", "no_change", "partial", "manual_recovery_required"].includes(status)) return null;
  if ((status === "partial" || status === "manual_recovery_required")
    && (!Array.isArray(verification?.evidence) || verification.evidence.length === 0)) {
    throw new Error("Non-success semantic results require verification evidence.");
  }
  const expectedRevision = revision?.before ?? revision?.current ?? revision?.lastKnown ?? null;
  if (Array.isArray(targets) && targets.some(
    (target) => target?.colorRevision != null && target.colorRevision !== expectedRevision,
  )) {
    throw new Error("Semantic result revision must belong to every exact Color target.");
  }
  if (status === "completed") {
    if (revision?.relationship !== "advanced" || revision.before === revision.after) {
      throw new Error("Completed semantic results must prove a revision advance.");
    }
    if (Object.hasOwn(change ?? {}, "before")
      && JSON.stringify(change.before) === JSON.stringify(change.after)) {
      throw new Error("Completed semantic results must prove a state change.");
    }
    const beforeIds = new Set(change?.before?.entities?.map((entity) => entity.id) ?? []);
    const afterIds = new Set(change?.after?.entities?.map((entity) => entity.id) ?? []);
    const preserved = afterIds.size >= beforeIds.size
      ? [...beforeIds].every((id) => afterIds.has(id))
      : [...afterIds].every((id) => beforeIds.has(id));
    if (beforeIds.size > 0 && !preserved) {
      throw new Error("Completed semantic results cannot replace stable entity identities.");
    }
  }
  if (status === "no_change") {
    if (revision?.relationship !== "unchanged") {
      throw new Error("No-change semantic results must preserve one revision.");
    }
    if (Object.hasOwn(change ?? {}, "before")
      && JSON.stringify(change.before) !== JSON.stringify(change.after)) {
      throw new Error("No-change semantic results cannot report changed state.");
    }
  }
  if (["fusion_export", "sidecar"].includes(change?.kind)) {
    if (change.before?.artifactId !== change.after?.artifactId) {
      throw new Error("Artifact semantic results must preserve artifact identity.");
    }
    if (["completed", "no_change"].includes(status) && change.after?.exists !== true) {
      throw new Error("Artifact semantic results must prove post-write existence.");
    }
  }
  return status;
}

function postTimelineRevision(result) {
  const candidate = result?.timelineRevision
    ?? result?.payload?.revision?.after
    ?? result?.payload?.revision?.observedAfter
    ?? result?.verification?.revision
    ?? result?.payload?.verification?.revision;
  const parsed = sdkRevisionSchema.safeParse(candidate);
  return parsed.success ? parsed.data : null;
}

function explicitPostTimelineRevision(value) {
  if (value === undefined || value === null) return null;
  return sdkRevisionSchema.parse(value);
}

export function createSdkOperationTerminal({
  repo,
  now,
  resultRetentionMs,
  idempotencyTombstoneMs,
  terminalStatuses,
  onNormalizationError = null,
}) {
  function reportNormalizationError(record, error) {
    try {
      onNormalizationError?.(record, error);
    } catch {
      // Private diagnostics must never alter durable terminal truth.
    }
  }

  function genericExecutionFailure(record) {
    const usage = record.public.usage === "not_reserved" ? "unknown" : record.public.usage;
    return {
      status: "failed",
      possibleMutation: "possible",
      usage,
      failure: {
        kind: "operation_failed",
        code: "OPERATION_FAILED",
        message: "The operation executor failed after execution began.",
        retrySafe: false,
        possibleMutation: "possible",
        usage,
        recovery: ["inspect_state", "manual_recovery"],
        recoveryGuidance: ["Inspect current project state before attempting another mutation."],
        readbackRequired: true,
      },
      recovery: {
        state: "manual_required",
        summary: "Automatic recovery was not claimed.",
        evidence: [],
        manualRecoveryRequired: true,
      },
      ...rejectedCancellation(
        record,
        now,
        "Execution failed before cancellation could be confirmed.",
      ),
    };
  }

  function normalizeTerminalOutcome(record, definition, outcome) {
    if (!outcome || typeof outcome !== "object" || !terminalStatuses.has(outcome.status)) {
      reportNormalizationError(
        record,
        new TypeError("Operation executor returned an invalid terminal outcome."),
      );
      return genericExecutionFailure(record);
    }
    if (outcome.status !== "succeeded") {
      let terminalRevision;
      let result;
      let resultCollections;
      try {
        terminalRevision = explicitPostTimelineRevision(outcome.postTimelineRevision)
          ?? postTimelineRevision(outcome.result);
        if (Object.hasOwn(outcome, "result")) {
          const internalResult = canonicalSdkOperationInput(definition.resultSchema.parse(outcome.result));
          const projected = projectSdkOperationResultCollections(
            internalResult,
            definition.resultCollections ?? editResultCollectionSpecs(record.public.actionId),
          );
          result = projected.result;
          resultCollections = projected.collections;
          if (result?.actionId === "cutagent.action.sdk.fairlight.plan.apply") {
            sdkFairlightBoundTerminalSchema.parse({
              input: record.private.normalizedInput,
              result,
            });
          }
        }
      } catch (error) {
        reportNormalizationError(record, error);
        return genericExecutionFailure(record);
      }
      const normalized = {
        ...outcome,
        ...(result !== undefined ? { result } : {}),
        ...(terminalRevision ? { postTimelineRevision: terminalRevision } : {}),
        ...(resultCollections !== undefined ? { resultCollections } : {}),
      };
      // The frozen public failed-terminal schema intentionally has no
      // verification member. Executors may still return diagnostic readback
      // alongside a conservative failure; keep that detail private to the
      // executor and persist only the closed public failure shape.
      if (outcome.status === "failed") delete normalized.verification;
      if (outcome.status !== "cancelled" && !outcome.cancellation) {
        Object.assign(normalized, rejectedCancellation(
          record,
          now,
          "Execution reached a terminal state before cancellation was confirmed.",
        ));
      }
      return normalized;
    }

    const cancellation = rejectedCancellation(
      record,
      now,
      "Execution completed before cancellation was confirmed.",
    );
    let result;
    let resultCollections;
    let verification;
    try {
      const internalResult = canonicalSdkOperationInput(definition.resultSchema.parse(outcome.result));
      const projected = projectSdkOperationResultCollections(
        internalResult,
        definition.resultCollections ?? editResultCollectionSpecs(record.public.actionId),
      );
      result = projected.result;
      resultCollections = projected.collections;
      const isFairlight = result?.actionId === "cutagent.action.sdk.fairlight.plan.apply";
      if (isFairlight) {
        sdkFairlightBoundTerminalSchema.parse({
          input: record.private.normalizedInput,
          result,
        });
      }
      verification = sdkVerificationReportSchema.parse(outcome.verification);
      const semanticStatus = semanticResultStatus(result, record.private.normalizedInput);
      const timelineRevision = postTimelineRevision(result);
      if (isFairlight) {
        const expectedProtectedState = result.evidence.protectedState.status === "passed"
          ? true
          : result.evidence.protectedState.status === "failed" ? false : null;
        if (verification.protectedStatePreserved !== expectedProtectedState) {
          throw new Error("Fairlight protected-state verification mismatch.");
        }
      }
      if (semanticStatus === "partial") {
        if (isFairlight ? verification.outcome !== result.evidence?.outcome : verification.outcome !== "partial") {
          throw new Error("Partial result verification mismatch.");
        }
        const recovery = isFairlight && result.recovery?.state === "readback_required"
          ? {
              state: "not_attempted",
              summary: result.recovery.guidance,
              manualRecoveryRequired: false,
            }
          : {
              state: "manual_required",
              summary: result.recovery?.guidance ?? "The partial change requires explicit state inspection.",
              evidence: verification.evidence,
              manualRecoveryRequired: true,
            };
        return {
          status: "partially_applied",
          result,
          possibleMutation: "partial",
          usage: outcome.usage,
          verification,
          failure: {
            kind: "operation_failed",
            code: "OPERATION_FAILED",
            message: "The semantic operation applied only part of the requested change.",
            retrySafe: false,
            possibleMutation: "partial",
            usage: outcome.usage,
            recovery: recovery.manualRecoveryRequired ? ["inspect_state", "manual_recovery"] : ["inspect_state"],
            recoveryGuidance: [recovery.summary],
            readbackRequired: true,
          },
          recovery,
          ...(timelineRevision ? { postTimelineRevision: timelineRevision } : {}),
          resultCollections,
          ...cancellation,
        };
      }
      if (semanticStatus === "manual_review_required") {
        if (verification.outcome !== "manual_review_required") {
          throw new Error("Manual-review result verification mismatch.");
        }
        const possibleMutation = "unknown";
        const summary = "The Media mutation requires explicit state inspection.";
        return {
          status: "verification_failed",
          result,
          possibleMutation,
          usage: outcome.usage,
          verification,
          failure: {
            kind: "verification_failed",
            code: "VERIFICATION_FAILED",
            message: "The Media mutation could not be verified conclusively.",
            retrySafe: false,
            possibleMutation,
            usage: outcome.usage,
            recovery: ["inspect_state", "manual_recovery"],
            recoveryGuidance: [summary],
            readbackRequired: true,
          },
          recovery: {
            state: "manual_required",
            summary,
            evidence: verification.evidence,
            manualRecoveryRequired: true,
          },
          ...(timelineRevision ? { postTimelineRevision: timelineRevision } : {}),
          resultCollections,
          ...cancellation,
        };
      }
      if (semanticStatus === "manual_recovery_required") {
        if (!["failed", "manual_review_required"].includes(verification.outcome)) {
          throw new Error("Manual-recovery result verification mismatch.");
        }
        const possibleMutation = outcome.possibleMutation === "none" ? "unknown" : outcome.possibleMutation;
        return {
          status: "recovery_failed",
          possibleMutation,
          usage: outcome.usage,
          verification,
          failure: {
            kind: "recovery_failed",
            code: "RECOVERY_FAILED",
            message: "The semantic operation requires manual recovery.",
            retrySafe: false,
            possibleMutation,
            usage: outcome.usage,
            recovery: ["inspect_state", "manual_recovery"],
            recoveryGuidance: ["Inspect and recover the affected targets before any retry."],
            recoveryOutcome: {
              status: "failed",
              summary: "Automatic recovery was not proven.",
              manualRecoveryRequired: true,
            },
            readbackRequired: true,
          },
          recovery: {
            state: "failed",
            summary: "Automatic recovery was not proven.",
            evidence: verification.evidence,
            manualRecoveryRequired: true,
          },
          result,
          ...(timelineRevision ? { postTimelineRevision: timelineRevision } : {}),
          resultCollections,
          ...cancellation,
        };
      }
      if (result?.actionId === "cutagent.action.sdk.fairlight.plan.apply") {
        const expectedMutation = semanticStatus === "completed" ? "confirmed" : semanticStatus === "no_change" ? "none" : null;
        if (expectedMutation === null || outcome.possibleMutation !== expectedMutation || verification.outcome !== "passed") {
          throw new Error("Fairlight semantic success truth mismatch.");
        }
      }
    } catch (error) {
      reportNormalizationError(record, error);
      return genericExecutionFailure(record);
    }
    const timelineRevision = postTimelineRevision(result);
    const mediaMutationStatus = result?.actionId?.startsWith("cutagent.action.media.")
      && typeof result?.payload?.changed === "boolean"
      ? result?.payload?.status
      : null;
    const possibleMutation = mediaMutationStatus === "no_op"
      ? "none"
      : mediaMutationStatus === "completed" ? "confirmed" : outcome.possibleMutation;
    return {
      status: "succeeded",
      result,
      ...(timelineRevision ? { postTimelineRevision: timelineRevision } : {}),
      resultCollections,
      verification,
      possibleMutation,
      usage: outcome.usage,
      ...(outcome.preparedActionTerminal ? {preparedActionTerminal: outcome.preparedActionTerminal} : {}),
      ...cancellation,
    };
  }

  function terminalSnapshot(record, outcome) {
    const at = now();
    const result = Object.hasOwn(outcome, "result")
      && outcome.status !== "cancelled"
      ? {
          result: {
            actionId: record.public.actionId,
            actionContractVersion: CUTAGENT_SDK_ACTION_CONTRACT_VERSION,
            value: outcome.result,
          },
        }
      : {};
    const common = {
      ...operationCommon(record.public),
      status: outcome.status,
      sequence: record.public.sequence + 1,
      updatedAt: iso(at),
      retentionExpiresAt: iso(at + resultRetentionMs),
      possibleMutation: outcome.possibleMutation,
      usage: outcome.usage,
      ...(outcome.cancellation ? { cancellation: outcome.cancellation } : {}),
      ...(outcome.verification ? { verification: outcome.verification } : {}),
      ...(outcome.recovery ? { recovery: outcome.recovery } : {}),
      ...result,
      ...(record.public.idempotency ? {
        idempotency: {
          key: record.public.idempotency.key,
          tombstoneExpiresAt: iso(at + idempotencyTombstoneMs),
        },
      } : {}),
    };
    if (outcome.status === "succeeded") {
      return sdkOperationSnapshotSchema.parse({
        ...common,
      });
    }
    return sdkOperationSnapshotSchema.parse({
      ...common,
      failure: correlatedFailure(record, outcome.failure),
    });
  }

  function transitionTerminal(record, outcome) {
    const snapshot = terminalSnapshot(record, outcome);
    const transitioned = repo.transition(
      record.public.operationId,
      record.public.sequence,
      (current) => ({
        ...current,
        public: snapshot,
        private: {
          ...current.private,
          cancellationResume: undefined,
          ...(typeof outcome.postTimelineRevision === "string"
            ? { postTimelineRevision: outcome.postTimelineRevision }
            : {}),
          ...(Object.keys(outcome.resultCollections ?? {}).length > 0
            ? { resultCollections: outcome.resultCollections }
            : {}),
          ...(outcome.preparedActionTerminal
            ? { preparedActionTerminal: outcome.preparedActionTerminal }
            : {}),
        },
      }),
    );
    return transitioned && transitioned !== false
      ? transitioned
      : repo.getOperation(record.public.operationId);
  }

  return Object.freeze({ genericExecutionFailure, normalizeTerminalOutcome, transitionTerminal });
}
