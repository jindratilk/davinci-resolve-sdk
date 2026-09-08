import { z } from "zod";
import {
  ExecutionIdSchema,
  IdempotencyKeySchema,
  OperationIdSchema,
  RequestIdSchema,
  RevisionSchema,
} from "../value-types/identities.js";
import { TimestampSchema } from "../schemas/time.js";
import { PublicFailureSchema } from "./errors.js";

const CorrelatedFailureSchema = PublicFailureSchema.and(z.object({
  requestId: RequestIdSchema,
  executionId: ExecutionIdSchema,
}));

/** Metadata shared by all public wire envelopes. @beta */
export const EnvelopeMetadataSchema = z.strictObject({
  wireProtocol: z.literal(1),
  requestId: RequestIdSchema,
  executionId: ExecutionIdSchema,
  operationId: OperationIdSchema.optional(),
  timestamp: TimestampSchema,
});
/** Metadata shared by all public wire envelopes. @beta */
export type EnvelopeMetadata = z.infer<typeof EnvelopeMetadataSchema>;

/** Metadata for a public request, including replay and stale-state protection. @beta */
export const RequestMetadataSchema = z.strictObject({
  requestId: RequestIdSchema,
  idempotencyKey: IdempotencyKeySchema.optional(),
  precondition: RevisionSchema.optional(),
});
/** Metadata for a public request. @beta */
export type RequestMetadata = z.infer<typeof RequestMetadataSchema>;

/** Public failure envelope. @beta */
export const FailureEnvelopeSchema = z.strictObject({
  ok: z.literal(false),
  meta: EnvelopeMetadataSchema,
  error: CorrelatedFailureSchema,
}).superRefine((envelope, context) => {
  if (envelope.error.requestId !== envelope.meta.requestId) {
    context.addIssue({ code: "custom", path: ["error", "requestId"], message: "Failure request ID must be present and match envelope metadata" });
  }
  if (envelope.error.executionId !== envelope.meta.executionId) {
    context.addIssue({ code: "custom", path: ["error", "executionId"], message: "Failure execution ID must be present and match envelope metadata" });
  }
  if (envelope.error.operationId !== envelope.meta.operationId) {
    context.addIssue({ code: "custom", path: ["error", "operationId"], message: "Failure operation ID presence and value must exactly match envelope metadata" });
  }
});
/** Public failure envelope. @beta */
export type FailureEnvelope = z.infer<typeof FailureEnvelopeSchema>;

/** Create a runtime-validating success-envelope schema for a specific payload schema. @beta */
export function createSuccessEnvelopeSchema<Schema extends z.ZodType>(dataSchema: Schema) {
  return z.strictObject({
    ok: z.literal(true),
    meta: EnvelopeMetadataSchema,
    data: dataSchema,
  });
}

/** Create a runtime-validating success-or-failure wire schema for a specific payload. @beta */
export function createEnvelopeSchema<Schema extends z.ZodType>(dataSchema: Schema) {
  return z.union([createSuccessEnvelopeSchema(dataSchema), FailureEnvelopeSchema]);
}
