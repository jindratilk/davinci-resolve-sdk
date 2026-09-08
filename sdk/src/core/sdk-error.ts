import { sdkPublicFailureSchema } from "../generated/sdk-operations.js";
import type { PublicFailure } from "../protocol/errors.js";

/** Error thrown after a public failure payload has passed runtime validation. @beta */
export class CutAgentSdkError extends Error {
  /** Validated public failure details. */
  readonly failure: PublicFailure;

  /** Create an SDK error from a public failure payload. */
  constructor(failure: PublicFailure, options?: ErrorOptions) {
    const validated = sdkPublicFailureSchema.parse(failure) as unknown as PublicFailure;
    super(validated.message, options);
    this.name = "CutAgentSdkError";
    this.failure = validated;
  }
}
