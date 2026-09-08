import type { EstablishedCarrierSession } from "./carrier-session.js";
import type { ConnectionControlOptions } from "./public-client-types.js";
import type { PublicActionId } from "../protocol/operations.js";
import type { IdempotencyKey, OperationId, ProjectId, Revision, SdkSessionId, TimelineId, TimelineItemId, WorkflowId } from "../value-types/identities.js";

/** Truthful terminal state of one workflow step. @beta */
export type WorkflowStepOutcome = "completed" | "failed_before_mutation" | "partially_applied" | "checkpoint_restored" | "compensated" | "restore_failed" | "manual_recovery_required" | "cancellation_requested";
/** Truthful aggregate workflow state. @beta */
export type WorkflowOutcome = WorkflowStepOutcome;
/** Durable authoritative identity assigned to a stable managed element key. @beta */
export interface ManagedElementMapping { readonly key: string; readonly timelineItemId: TimelineItemId }
/** Durable managed ownership truth returned after verified completion or restoration. @beta */
export interface ManagedWorkflowVerification { readonly outcome: "passed"; readonly finalRevision: Revision; readonly protectedStateDigest: string; readonly expectedManagedStateDigest: string; readonly evidence: readonly Readonly<{ readonly modality: "readback" | "structural"; readonly summary: string; readonly digest: string }>[] }
/** Verified final managed ownership truth. @beta */
export interface ManagedWorkflowState { readonly ownershipId: string; readonly generation: number; readonly revision: Revision; readonly desiredStateDigest: string; readonly elements: readonly ManagedElementMapping[]; readonly verification: ManagedWorkflowVerification }
/** Exact project/timeline/revision binding for one checkpoint workflow. @beta */
export interface WorkflowBinding { readonly sessionId: SdkSessionId; readonly projectId: ProjectId; readonly timelineId: TimelineId; readonly revision: Revision; readonly idempotencyKey: IdempotencyKey }
/** Binding returned after the runtime captures the exact Mutation Policy revision. @beta */
export interface AuthoritativeWorkflowBinding extends Omit<WorkflowBinding, "sessionId"> { readonly policyRevision: string }
/** Runtime-owned durable step correlation. @beta */
export interface WorkflowStepJournalEntry { readonly name: string; readonly idempotencyKey: IdempotencyKey; readonly operationId?: OperationId; readonly actionId?: PublicActionId; readonly outcome?: WorkflowStepOutcome }
/** Sanitized projection of proprietary durable workflow authority. @beta */
export interface WorkflowJournal { readonly workflowId: WorkflowId; readonly binding: AuthoritativeWorkflowBinding; readonly sequence: number; readonly status: "checkpoint_pending" | "active" | WorkflowOutcome; readonly steps: readonly WorkflowStepJournalEntry[]; readonly createdAt: string; readonly updatedAt: string; readonly retentionExpiresAt: string; readonly manualRecoveryRequired: boolean; readonly cancellationDoesNotRollback: true; readonly managedState?: ManagedWorkflowState }
/** One observed terminal step. @beta */
export interface WorkflowStepResult { readonly name: string; readonly outcome: WorkflowStepOutcome; readonly operationId?: OperationId; readonly actionId?: PublicActionId }
/** Aggregate checkpoint-backed workflow truth. This is never an atomic transaction. @beta */
export interface WorkflowResult {
  readonly workflowId: WorkflowId;
  readonly outcome: WorkflowOutcome;
  readonly steps: readonly WorkflowStepResult[];
  readonly journal: WorkflowJournal;
  readonly managedState?: ManagedWorkflowState;
  readonly manualRecoveryRequired: boolean;
  readonly cancellationDoesNotRollback: true;
  /** Original local callback errors retained alongside the runtime-authoritative outcome. */
  readonly authoringErrors?: readonly Readonly<{ readonly phase: "step_start" | "workflow_body"; readonly cause: unknown; readonly stepName?: string }>[];
}
/** Start or resume options. @beta */
export type CheckpointWorkflowOptions = ConnectionControlOptions & { readonly pollIntervalMs?: number; readonly cancellationSignal?: AbortSignal } & ({ readonly binding: Omit<WorkflowBinding, "sessionId">; readonly resume?: never } | { readonly resume: WorkflowId; readonly binding?: never });
/** Serial workflow body with ordinary TypeScript control flow. @beta */
export interface WorkflowOperationHandle { readonly operationId: OperationId; wait(options?: ConnectionControlOptions): Promise<unknown> }
/** Serial workflow body with ordinary TypeScript control flow. @beta */
export interface CheckpointWorkflowContext { readonly workflowId: WorkflowId; readonly binding: AuthoritativeWorkflowBinding; step(name: string, start: (idempotencyKey: IdempotencyKey) => Promise<WorkflowOperationHandle>): Promise<WorkflowStepResult> }
/** Runtime-authoritative checkpoint workflow composition. @beta */
export interface Workflows { checkpointed(options: CheckpointWorkflowOptions, run: (workflow: CheckpointWorkflowContext) => Promise<void>): Promise<WorkflowResult> }

const workflowPollInterval = (value: number | undefined): number => {
  if (value === undefined) return 250;
  if (!Number.isInteger(value) || value < 100 || value > 10_000) throw new TypeError("pollIntervalMs must be an integer from 100 through 10,000.");
  return value;
};

const waitForWorkflowPoll = (milliseconds: number, signal?: AbortSignal): Promise<"poll" | "cancel"> => {
  if (signal?.aborted) return Promise.resolve("cancel");
  return new Promise((resolve) => {
    const timer = setTimeout(finish, milliseconds);
    const abort = () => { clearTimeout(timer); signal?.removeEventListener("abort", abort); resolve("cancel"); };
    function finish() { signal?.removeEventListener("abort", abort); resolve("poll"); }
    signal?.addEventListener("abort", abort, { once: true });
  });
};

const waitForOperationOrCancellation = async (operation: Promise<unknown>, signal: AbortSignal): Promise<"operation" | "cancel"> => {
  let abort = () => {};
  const cancellation = new Promise<"cancel">((resolve) => {
    abort = () => resolve("cancel");
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
  });
  try {
    return await Promise.race([operation.then(() => "operation" as const), cancellation]);
  } finally {
    signal.removeEventListener("abort", abort);
  }
};

type WorkflowAuthoringError = Readonly<{ readonly phase: "step_start" | "workflow_body"; readonly cause: unknown; readonly stepName?: string }>;

const result = (snapshot: any, authoringErrors: readonly WorkflowAuthoringError[]): WorkflowResult => Object.freeze({
  workflowId: snapshot.workflowId, outcome: snapshot.status,
  steps: Object.freeze(snapshot.steps.flatMap((entry: any) => entry.outcome ? [{ name: entry.name, outcome: entry.outcome, ...(entry.operationId ? { operationId: entry.operationId } : {}), ...(entry.actionId ? { actionId: entry.actionId } : {}) }] : [])),
  journal: snapshot, ...(snapshot.managedState ? { managedState: snapshot.managedState } : {}), manualRecoveryRequired: snapshot.manualRecoveryRequired, cancellationDoesNotRollback: true,
  ...(authoringErrors.length > 0 ? { authoringErrors: Object.freeze([...authoringErrors]) } : {}),
}) as WorkflowResult;

/** Thin typed composition adapter. Recovery, replay reconciliation, and verification remain runtime-owned. @internal */
export function createWorkflows(runtime: { session(): EstablishedCarrierSession }): Workflows {
  let active = false;
  return Object.freeze({
    async checkpointed(options: CheckpointWorkflowOptions, run: (workflow: CheckpointWorkflowContext) => Promise<void>) {
      if (active) throw new Error("Nested or concurrent mutating workflows are not allowed on one client.");
      const pollIntervalMs = workflowPollInterval(options.pollIntervalMs);
      active = true;
      let detach = () => {};
      const authoringErrors: WorkflowAuthoringError[] = [];
      try {
        const resuming = "resume" in options && options.resume !== undefined;
        let snapshot = await runtime.session().workflow((resuming ? { operation: "workflow.get", workflowId: options.resume } : { operation: "workflow.create", binding: options.binding }) as never, options);
        if (snapshot.authorityKind === "managed") throw new TypeError("Managed WorkflowIds must be observed through their managed application handle.");
        if (snapshot.status === "checkpoint_pending") throw new Error("Workflow checkpoint admission is still pending; retry the same idempotency identity.");
        const interrupt = () => runtime.session().workflow({ operation: "workflow.interrupt", workflowId: snapshot.workflowId }, {});
        let cancellationNotice: Promise<typeof snapshot> | undefined;
        if (options.cancellationSignal) {
          const cancel = () => { cancellationNotice ??= interrupt(); };
          options.cancellationSignal.addEventListener("abort", cancel, { once: true });
          detach = () => options.cancellationSignal?.removeEventListener("abort", cancel);
          if (options.cancellationSignal.aborted) snapshot = await interrupt();
        }
        if (snapshot.status === "active") {
          const context: CheckpointWorkflowContext = Object.freeze({
            workflowId: snapshot.workflowId as unknown as WorkflowId, binding: snapshot.binding as unknown as AuthoritativeWorkflowBinding,
            async step(name: string, start: (idempotencyKey: IdempotencyKey) => Promise<WorkflowOperationHandle>) {
              if (snapshot.status !== "active") throw new Error("Workflow is halted; no later step can start.");
              snapshot = await runtime.session().workflow({ operation: "workflow.step.reserve", workflowId: snapshot.workflowId, name }, options);
              let entry = snapshot.steps.find((candidate) => candidate.name === name)!;
              if (!entry.outcome) {
                snapshot = await runtime.session().workflow({ operation: "workflow.step.observe", workflowId: snapshot.workflowId, name }, options);
                entry = snapshot.steps.find((candidate) => candidate.name === name)!;
              }
              if (!entry.outcome && !entry.operationId) {
                let handle: WorkflowOperationHandle | undefined;
                try { handle = await start(entry.idempotencyKey as unknown as IdempotencyKey); }
                catch (error) {
                  authoringErrors.push(Object.freeze({ phase: "step_start", stepName: name, cause: error }));
                  snapshot = await runtime.session().workflow({ operation: "workflow.step.observe", workflowId: snapshot.workflowId, name }, {});
                  entry = snapshot.steps.find((candidate) => candidate.name === name)!;
                  if (!entry.outcome && !entry.operationId) {
                    snapshot = await runtime.session().workflow({ operation: "workflow.step.fail_before_mutation", workflowId: snapshot.workflowId, name }, {});
                  }
                }
                if (handle) {
                  snapshot = await runtime.session().workflow({ operation: "workflow.step.attach", workflowId: snapshot.workflowId, name, operationId: handle.operationId } as never, options);
                  if (options.cancellationSignal?.aborted) snapshot = await interrupt();
                  else if (cancellationNotice) snapshot = await cancellationNotice;
                  else if (options.cancellationSignal) {
                    const waited = await waitForOperationOrCancellation(handle.wait(options), options.cancellationSignal);
                    if (waited === "cancel" || options.cancellationSignal.aborted || cancellationNotice) snapshot = await (cancellationNotice ?? interrupt());
                  } else await handle.wait(options);
                }
              }
              if (snapshot.status !== "active") {
                entry = snapshot.steps.find((candidate) => candidate.name === name)!;
                return Object.freeze({ name, outcome: (entry.outcome ?? snapshot.status) as WorkflowStepOutcome, ...(entry.operationId ? { operationId: entry.operationId as unknown as OperationId } : {}), ...(entry.actionId ? { actionId: entry.actionId as PublicActionId } : {}) });
              }
              while (snapshot.status === "active") {
                snapshot = await runtime.session().workflow({ operation: "workflow.step.observe", workflowId: snapshot.workflowId, name }, options);
                entry = snapshot.steps.find((candidate) => candidate.name === name)!;
                if (entry.outcome) break;
                if (!entry.operationId) throw new Error("Workflow step remains unattached; reattach by WorkflowId.");
                const waited = await waitForWorkflowPoll(pollIntervalMs, options.cancellationSignal);
                if (waited === "cancel") snapshot = await (cancellationNotice ?? interrupt());
              }
              if (snapshot.status !== "active") {
                entry = snapshot.steps.find((candidate) => candidate.name === name)!;
                return Object.freeze({ name, outcome: (entry.outcome ?? snapshot.status) as WorkflowStepOutcome, ...(entry.operationId ? { operationId: entry.operationId as unknown as OperationId } : {}), ...(entry.actionId ? { actionId: entry.actionId as PublicActionId } : {}) });
              }
              if (!entry.outcome) throw new Error("Workflow step remains non-terminal; reattach by WorkflowId.");
              return Object.freeze({ name, outcome: entry.outcome, ...(entry.operationId ? { operationId: entry.operationId as unknown as OperationId } : {}), ...(entry.actionId ? { actionId: entry.actionId as PublicActionId } : {}) });
            },
          });
          try { await run(context); }
          catch (error) {
            authoringErrors.push(Object.freeze({ phase: "workflow_body", cause: error }));
            if (snapshot.status === "active" && snapshot.steps.some((step) => !step.outcome && step.operationId)) throw error;
            if (snapshot.status === "active") snapshot = await runtime.session().workflow({ operation: "workflow.fail", workflowId: snapshot.workflowId }, {});
          }
          if (options.cancellationSignal?.aborted && snapshot.status === "active") snapshot = await (cancellationNotice ?? interrupt());
          if (snapshot.status === "active") {
            try { snapshot = await runtime.session().workflow({ operation: "workflow.complete", workflowId: snapshot.workflowId }, {}); }
            catch (error) {
              if (options.cancellationSignal?.aborted) snapshot = await interrupt();
              else throw error;
            }
          }
        }
        return result(snapshot, authoringErrors);
      } finally { detach(); active = false; }
    },
  });
}
