import { z } from "zod";
import { CUTAGENT_PLUGIN_CARRIER_PROTOCOL_DIGEST } from "./sdk-plugin-runtime-protocol.js";
import { CUTAGENT_SDK_WIRE_PROTOCOL, sdkRequestIdSchema, sdkRuntimeCloseRequestSchema, sdkRuntimeCloseSuccessSchema, sdkRuntimeConfirmRequestSchema, sdkRuntimeConfirmSuccessSchema, sdkRuntimeConnectSuccessSchema, sdkRuntimeReadFailureSchema, sdkRuntimeReadRequestSchema, sdkRuntimeReadSuccessSchema, sdkRuntimeSessionBaseSchema, sdkRuntimeSessionConnectRequestSchema, sdkTransportErrorCodeSchema, sdkTransportRecoverySchema, validateSessionLifetime, } from "./sdk-runtime.js";
import { sdkOperationControlFailureSchema, sdkOperationControlRequestSchema, sdkOperationControlSuccessSchema, sdkWorkflowControlRequestSchema, sdkWorkflowControlResponseSchema, } from "./sdk-operations.js";
export { CUTAGENT_PLUGIN_CARRIER_PROTOCOL_DIGEST } from "./sdk-plugin-runtime-protocol.js";
/** Private plugin-carrier wire metadata. Never export this module from the public SDK. */
export const CUTAGENT_SDK_PLUGIN_STDIO_MODE = "--cutagent-sdk-stdio-v1";
export const CUTAGENT_SDK_PLUGIN_FRAME_MAX_BYTES = 16_777_216;
export const CUTAGENT_SDK_PLUGIN_CONNECT_METHOD = "connect";
export const CUTAGENT_SDK_PLUGIN_CONFIRM_METHOD = "confirm";
export const CUTAGENT_SDK_PLUGIN_READ_METHOD = "read";
export const CUTAGENT_SDK_PLUGIN_OPERATION_METHOD = "operation";
export const CUTAGENT_SDK_PLUGIN_WORKFLOW_METHOD = "workflow";
export const CUTAGENT_SDK_PLUGIN_CLOSE_METHOD = "close";
const pairingAttemptIdSchema = z.string()
    .min(8)
    .max(160)
    .regex(/^[A-Za-z0-9][A-Za-z0-9._~-]*$/);
const sdkPluginTransportErrorCodeSchema = z.union([
    sdkTransportErrorCodeSchema,
    z.literal("PAIRING_REQUIRED"),
]);
const sdkPluginRuntimeFailureSchema = z.object({
    ok: z.literal(false),
    requestId: sdkRequestIdSchema.optional(),
    error: z.object({
        code: sdkPluginTransportErrorCodeSchema,
        message: z.string().min(1).max(500),
        recovery: sdkTransportRecoverySchema,
        pairing: z.object({
            attemptId: pairingAttemptIdSchema,
            mcpTool: z.literal("cutagent_connect_local_runtime"),
        }).strict().optional(),
    }).strict(),
}).strict().superRefine((failure, context) => {
    if ((failure.error.code === "PAIRING_REQUIRED") !== (failure.error.pairing !== undefined)) {
        context.addIssue({ code: "custom", path: ["error", "pairing"], message: "Pairing details are required only for PAIRING_REQUIRED" });
    }
});
/** Process-bound metadata; authentication remains inside the owned carrier process. */
export const sdkPluginRuntimeSessionSchema = sdkRuntimeSessionBaseSchema
    .omit({ sessionToken: true })
    .superRefine(validateSessionLifetime);
const sdkPluginFrameBaseSchema = z.object({
    protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
    requestId: sdkRequestIdSchema,
}).strict();
export const sdkPluginStartupRequestSchema = sdkPluginFrameBaseSchema.extend({
    method: z.literal(CUTAGENT_SDK_PLUGIN_CONNECT_METHOD),
    carrierProtocolDigest: z.literal(CUTAGENT_PLUGIN_CARRIER_PROTOCOL_DIGEST),
    payload: sdkRuntimeSessionConnectRequestSchema,
}).strict().superRefine((frame, context) => {
    if (frame.requestId !== frame.payload.handshake.requestId) {
        context.addIssue({ code: "custom", path: ["requestId"], message: "Frame and handshake request IDs must match" });
    }
    if (frame.payload.handshake.requestedDistribution !== "plugin_managed") {
        context.addIssue({ code: "custom", path: ["payload", "handshake", "requestedDistribution"], message: "Plugin startup requires plugin_managed distribution" });
    }
});
export const sdkPluginConfirmRequestFrameSchema = sdkPluginFrameBaseSchema.extend({
    method: z.literal(CUTAGENT_SDK_PLUGIN_CONFIRM_METHOD),
    payload: sdkRuntimeConfirmRequestSchema,
}).strict().superRefine((frame, context) => {
    if (frame.requestId !== frame.payload.requestId) {
        context.addIssue({ code: "custom", path: ["requestId"], message: "Frame and payload request IDs must match" });
    }
});
export const sdkPluginCloseRequestFrameSchema = sdkPluginFrameBaseSchema.extend({
    method: z.literal(CUTAGENT_SDK_PLUGIN_CLOSE_METHOD),
    payload: sdkRuntimeCloseRequestSchema,
}).strict().superRefine((frame, context) => {
    if (frame.requestId !== frame.payload.requestId) {
        context.addIssue({ code: "custom", path: ["requestId"], message: "Frame and payload request IDs must match" });
    }
});
export const sdkPluginReadRequestFrameSchema = sdkPluginFrameBaseSchema.extend({
    method: z.literal(CUTAGENT_SDK_PLUGIN_READ_METHOD),
    payload: sdkRuntimeReadRequestSchema,
}).strict().superRefine((frame, context) => {
    if (frame.requestId !== frame.payload.requestId) {
        context.addIssue({ code: "custom", path: ["requestId"], message: "Frame and payload request IDs must match" });
    }
});
export const sdkPluginOperationRequestFrameSchema = sdkPluginFrameBaseSchema.extend({
    method: z.literal(CUTAGENT_SDK_PLUGIN_OPERATION_METHOD),
    payload: sdkOperationControlRequestSchema,
}).strict().superRefine((frame, context) => {
    if (frame.requestId !== frame.payload.requestId) {
        context.addIssue({ code: "custom", path: ["requestId"], message: "Frame and payload request IDs must match" });
    }
});
export const sdkPluginWorkflowRequestFrameSchema = sdkPluginFrameBaseSchema.extend({
    method: z.literal(CUTAGENT_SDK_PLUGIN_WORKFLOW_METHOD),
    payload: sdkWorkflowControlRequestSchema,
}).strict().superRefine((frame, context) => {
    if (frame.requestId !== frame.payload.requestId) {
        context.addIssue({ code: "custom", path: ["requestId"], message: "Frame and payload request IDs must match" });
    }
});
export const sdkPluginRequestFrameSchema = z.union([
    sdkPluginStartupRequestSchema,
    sdkPluginConfirmRequestFrameSchema,
    sdkPluginReadRequestFrameSchema,
    sdkPluginOperationRequestFrameSchema,
    sdkPluginWorkflowRequestFrameSchema,
    sdkPluginCloseRequestFrameSchema,
]);
export const sdkPluginConnectResponseFrameSchema = sdkPluginFrameBaseSchema.extend({
    method: z.literal(CUTAGENT_SDK_PLUGIN_CONNECT_METHOD),
    payload: z.union([
        sdkRuntimeConnectSuccessSchema.extend({ session: sdkPluginRuntimeSessionSchema }).strict(),
        sdkPluginRuntimeFailureSchema,
    ]),
}).strict().superRefine((frame, context) => {
    if (frame.payload.requestId !== undefined && frame.requestId !== frame.payload.requestId) {
        context.addIssue({ code: "custom", path: ["requestId"], message: "Frame and payload request IDs must match" });
    }
});
export const sdkPluginConfirmResponseFrameSchema = sdkPluginFrameBaseSchema.extend({
    method: z.literal(CUTAGENT_SDK_PLUGIN_CONFIRM_METHOD),
    payload: z.union([sdkRuntimeConfirmSuccessSchema, sdkPluginRuntimeFailureSchema]),
}).strict().superRefine((frame, context) => {
    if (frame.payload.requestId !== undefined && frame.requestId !== frame.payload.requestId) {
        context.addIssue({ code: "custom", path: ["requestId"], message: "Frame and payload request IDs must match" });
    }
});
export const sdkPluginCloseResponseFrameSchema = sdkPluginFrameBaseSchema.extend({
    method: z.literal(CUTAGENT_SDK_PLUGIN_CLOSE_METHOD),
    payload: z.union([sdkRuntimeCloseSuccessSchema, sdkPluginRuntimeFailureSchema]),
}).strict().superRefine((frame, context) => {
    if (frame.payload.requestId !== undefined && frame.requestId !== frame.payload.requestId) {
        context.addIssue({ code: "custom", path: ["requestId"], message: "Frame and payload request IDs must match" });
    }
});
export const sdkPluginReadResponseFrameSchema = sdkPluginFrameBaseSchema.extend({
    method: z.literal(CUTAGENT_SDK_PLUGIN_READ_METHOD),
    payload: z.union([sdkRuntimeReadSuccessSchema, sdkRuntimeReadFailureSchema]),
}).strict().superRefine((frame, context) => {
    if (frame.payload.requestId !== undefined && frame.requestId !== frame.payload.requestId) {
        context.addIssue({ code: "custom", path: ["requestId"], message: "Frame and payload request IDs must match" });
    }
});
export const sdkPluginOperationResponseFrameSchema = sdkPluginFrameBaseSchema.extend({
    method: z.literal(CUTAGENT_SDK_PLUGIN_OPERATION_METHOD),
    payload: z.union([
        sdkOperationControlSuccessSchema,
        sdkOperationControlFailureSchema,
        sdkPluginRuntimeFailureSchema,
    ]),
}).strict().superRefine((frame, context) => {
    if (frame.requestId !== frame.payload.requestId) {
        context.addIssue({ code: "custom", path: ["requestId"], message: "Frame and payload request IDs must match" });
    }
});
export const sdkPluginWorkflowResponseFrameSchema = sdkPluginFrameBaseSchema.extend({
    method: z.literal(CUTAGENT_SDK_PLUGIN_WORKFLOW_METHOD),
    payload: z.union([sdkWorkflowControlResponseSchema, sdkPluginRuntimeFailureSchema]),
}).strict().superRefine((frame, context) => {
    if (frame.requestId !== frame.payload.requestId) {
        context.addIssue({ code: "custom", path: ["requestId"], message: "Frame and payload request IDs must match" });
    }
});
export const sdkPluginResponseFrameSchema = z.union([
    sdkPluginConnectResponseFrameSchema,
    sdkPluginConfirmResponseFrameSchema,
    sdkPluginReadResponseFrameSchema,
    sdkPluginOperationResponseFrameSchema,
    sdkPluginWorkflowResponseFrameSchema,
    sdkPluginCloseResponseFrameSchema,
]);
