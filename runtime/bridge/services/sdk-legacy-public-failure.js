/** Preserve historical outcomes while retiring the former edit-policy error contract. */
export function readLegacySdkPublicFailure(failure) {
  if (failure?.code !== "EDIT_CONSTRAINT_VIOLATION" || failure.kind !== "edit_constraint_violation") return failure;
  return { ...failure, code: "OPERATION_FAILED", kind: "operation_failed" };
}
