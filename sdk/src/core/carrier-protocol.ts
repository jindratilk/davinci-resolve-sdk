import { z } from "zod";
import {
  CUTAGENT_SDK_API_VERSION,
  CUTAGENT_SDK_PREVIEW_VERSION,
  CUTAGENT_SDK_PROTOCOL_DIGEST,
  CUTAGENT_SDK_WIRE_PROTOCOL,
  sdkCompatibilityDescriptorSchema,
  sdkRuntimeCloseResponseSchema,
  sdkRuntimeConfirmResponseSchema,
  sdkRuntimeFailureSchema,
  sdkRuntimeSessionBaseSchema,
  validateSessionLifetime,
} from "../generated/sdk-runtime.js";
import { assertCarrierPolicyCompatible } from "../protocol/compatibility-policy.js";
import type { CompatibilityDescriptor } from "../protocol/compatibility.js";
import { RequestIdSchema, type RequestId } from "../value-types/identities.js";
import {
  CarrierFault,
  type CarrierDistribution,
  type CarrierMethod,
  type CarrierReply,
  type CarrierRequest,
} from "./carrier-contract.js";
import { mapTransportFailure, publicFailure } from "./carrier-errors.js";

export const SanitizedSessionSchema = sdkRuntimeSessionBaseSchema
  .omit({ sessionToken: true })
  .strict()
  .superRefine(validateSessionLifetime);

export const SanitizedConnectSuccessSchema = z.object({
  ok: z.literal(true),
  protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
  requestId: RequestIdSchema,
  descriptor: sdkCompatibilityDescriptorSchema,
  session: SanitizedSessionSchema,
}).strict();

export const SanitizedConnectResponseSchema = z.union([SanitizedConnectSuccessSchema, sdkRuntimeFailureSchema]);
export type SanitizedCarrierSession = z.infer<typeof SanitizedSessionSchema>;

export function assertCarrierCompatible(
  descriptor: CompatibilityDescriptor,
  distribution: CarrierDistribution,
  distributionRange: string | null,
): CompatibilityDescriptor {
  return assertCarrierPolicyCompatible(descriptor, distribution, distributionRange);
}

export function assertReply(reply: CarrierReply, method: CarrierMethod, requestId: RequestId): unknown {
  if (reply.method !== method || reply.requestId !== requestId) {
    throw publicFailure({
      code: "INVALID_RESPONSE",
      message: "CutAgent runtime returned an uncorrelated response.",
      recovery: ["contact_support"],
      requestId,
    });
  }
  if (reply.fault !== undefined) throw new CarrierFault(reply.fault);
  return reply.payload;
}

export function request(method: "connect", requestId: RequestId, distribution: CarrierDistribution): CarrierRequest;
export function request(method: "confirm" | "close", requestId: RequestId, distribution: CarrierDistribution, sessionId: string): CarrierRequest;
export function request(
  method: "connect" | "confirm" | "close",
  requestId: RequestId,
  distribution: CarrierDistribution,
  sessionId?: string,
): CarrierRequest {
  if (method === "connect") {
    return {
      method,
      requestId,
      payload: {
        protocolVersion: CUTAGENT_SDK_WIRE_PROTOCOL,
        handshake: {
          requestId,
          sdkVersion: CUTAGENT_SDK_PREVIEW_VERSION,
          sdkApiVersion: CUTAGENT_SDK_API_VERSION,
          supportedWireProtocols: [CUTAGENT_SDK_WIRE_PROTOCOL],
          requestedDistribution: distribution,
          protocolDigest: CUTAGENT_SDK_PROTOCOL_DIGEST,
        },
      },
    };
  }
  if (sessionId === undefined) throw new TypeError("A session ID is required for session control requests.");
  return {
    method,
    requestId,
    payload: { protocolVersion: CUTAGENT_SDK_WIRE_PROTOCOL, requestId, sessionId },
  };
}

export function parseControlResponse(method: "confirm" | "close", payload: unknown, requestId: RequestId): void {
  const schema = method === "confirm" ? sdkRuntimeConfirmResponseSchema : sdkRuntimeCloseResponseSchema;
  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    throw publicFailure({ code: "INVALID_RESPONSE", message: "CutAgent runtime response failed SDK validation.", recovery: ["contact_support"], requestId });
  }
  if (!parsed.data.ok) throw mapTransportFailure(parsed.data, requestId, "pre_execution");
  if (String(parsed.data.requestId) !== String(requestId)) {
    throw publicFailure({ code: "INVALID_RESPONSE", message: "CutAgent runtime returned an uncorrelated response.", recovery: ["contact_support"], requestId });
  }
}
