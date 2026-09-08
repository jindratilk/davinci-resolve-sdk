import { IdempotencyKeySchema } from "../value-types/identities.js";

type MutationControlInput = {
  readonly timeoutMs?: number;
  readonly signal?: AbortSignal;
  readonly idempotencyKey: unknown;
};

export function freezeRecursively<T>(value: T): T {
  if (value === null || typeof value !== "object" || Object.isFrozen(value)) return value;
  for (const nested of Object.values(value)) freezeRecursively(nested);
  return Object.freeze(value);
}

export function mutationControl(options: MutationControlInput) {
  return {
    ...(options.timeoutMs !== undefined ? { timeoutMs: options.timeoutMs } : {}),
    ...(options.signal !== undefined ? { signal: options.signal } : {}),
    idempotencyKey: IdempotencyKeySchema.parse(options.idempotencyKey),
  };
}
