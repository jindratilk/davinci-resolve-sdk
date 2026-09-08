/** Resolve the one Mutation Policy scope owned by this direct SDK session and target. */
export async function resolveSdkDirectMutationScope({
  directMutationPolicyAuthority,
  context,
  liveInspectionService,
  level,
  projectId = null,
  timelineId = null,
  timelineRevision = null,
  inspectedProjectContext = null,
}) {
  if (directMutationPolicyAuthority === null) return null;
  if (typeof directMutationPolicyAuthority?.resolveScope !== "function") {
    throw new TypeError("Direct SDK mutation scope authority is invalid.");
  }
  const inspected = inspectedProjectContext ?? await liveInspectionService.readWithMutationGuard(
    {operation: "project.context"},
    {deadlineAtMs: Date.now() + 60_000},
  );
  const projectLibraryId = inspected?.privateExecutionIdentity?.projectLibraryId;
  const currentProject = inspected?.value?.project;
  const currentTimeline = inspected?.value?.timeline;
  const projectRevision = inspected?.value?.projectRevision;
  if (typeof projectLibraryId !== "string" || !projectLibraryId) {
    throw Object.assign(new Error("The direct SDK policy scope lost its exact project-library binding."), {code: "STALE_REVISION"});
  }
  const binding = {level, projectLibraryId};
  if (level === "project" || level === "project+timeline") {
    if (currentProject?.id !== projectId || projectRevision?.status !== "available" || typeof projectRevision.revision !== "string") {
      throw Object.assign(new Error("The direct SDK policy scope lost its exact project binding."), {code: "STALE_REVISION"});
    }
    Object.assign(binding, {projectId, projectRevision: projectRevision.revision});
  }
  if (level === "project+timeline") {
    if (currentTimeline?.id !== timelineId || typeof timelineRevision !== "string") {
      throw Object.assign(new Error("The direct SDK policy scope lost its exact timeline binding."), {code: "STALE_REVISION"});
    }
    Object.assign(binding, {timelineId, timelineRevision});
  }
  return directMutationPolicyAuthority.resolveScope({
    sdkSessionId: context.sdkSessionId,
    accountFingerprint: context.accountFingerprint,
    ...(context.idempotencyKey ? {idempotencyKey: context.idempotencyKey} : {}),
    binding,
  });
}

/** Account scans remain only as an injectable legacy/test fallback. */
export function sdkMutationScopeCandidates(mutationPolicyGate, accountFingerprint, directScope) {
  return directScope === null
    ? mutationPolicyGate.listScopes({accountFingerprint})
    : [directScope];
}

/** Bind an already-captured prepared-action identity to its session-owned scope. */
export async function resolveSdkPreparedMutationScope({directMutationPolicyAuthority, mutationPolicyGate = null, context, minimumBinding, binding}) {
  const requested = {
    level: minimumBinding,
    projectLibraryId: binding.projectLibraryId,
    ...(minimumBinding === "account/project-library" ? {} : {
      projectId: binding.projectId,
      projectRevision: binding.projectRevision,
    }),
    ...(minimumBinding === "project+timeline" ? {
      timelineId: binding.timelineId,
      timelineRevision: binding.timelineRevision,
    } : {}),
  };
  if (typeof directMutationPolicyAuthority?.resolveScope === "function") {
    return directMutationPolicyAuthority.resolveScope({
      sdkSessionId: context.sdkSessionId,
      accountFingerprint: context.accountFingerprint,
      ...(context.idempotencyKey ? {idempotencyKey: context.idempotencyKey} : {}),
      binding: requested,
    });
  }
  const matches = mutationPolicyGate?.listScopes?.({accountFingerprint: context.accountFingerprint})?.filter((scope) => (
    Object.entries(requested).every(([key, value]) => scope?.binding?.[key] === value)
  )) ?? [];
  if (matches.length !== 1) throw new TypeError("Prepared SDK mutation requires direct session scope authority.");
  return matches[0];
}
