import { z } from "zod";
export const cutAgentFailureKindSchema = z.enum([
    "usage_exhausted",
    "request_too_large",
    "output_limit_reached",
    "runtime_unavailable",
    "runtime_timeout",
    "runtime_crashed",
    "runtime_incompatible",
    "dependency_unavailable",
    "temporary_provider_failure",
    "edit_constraint_violation",
    "unknown",
]);
export const cutAgentRecoverySchema = z.enum([
    "upgrade_or_wait",
    "continue",
    "start_continuation",
    "restart_runtime",
    "update_required",
    "retry",
    "contact_support",
]);
export const cutAgentFailureUsageStateSchema = z.enum([
    "not_reserved",
    "reserved",
    "consumed",
    "released",
    "unknown",
]);
export const cutAgentPossibleMutationSchema = z.enum([
    "none",
    "possible",
    "confirmed",
    "unknown",
]);
export const cutAgentFailureCorrelationSchema = z.object({
    requestId: z.string().trim().min(1).max(256).nullable(),
    executionId: z.string().trim().min(1).max(256),
    operationId: z.string().trim().min(1).max(256).nullable(),
    runId: z.string().trim().min(1).max(256).nullable(),
    providerRequestId: z.string().trim().min(1).max(256).nullable(),
}).strict();
export const cutAgentPublicFailureFields = {
    contractVersion: z.literal(1),
    kind: cutAgentFailureKindSchema,
    code: z.string().trim().min(1).max(128),
    causeCode: z.string().trim().min(1).max(128).nullable(),
    recovery: cutAgentRecoverySchema,
    retrySafe: z.boolean(),
    usageState: cutAgentFailureUsageStateSchema,
    possibleMutation: cutAgentPossibleMutationSchema,
    readbackRequired: z.boolean(),
    manualRecoveryRequired: z.boolean(),
    incidentId: z.string().trim().min(1).max(256),
    correlation: cutAgentFailureCorrelationSchema,
};
export function validateCutAgentPublicFailure(failure, context) {
    const allowedRecovery = {
        usage_exhausted: [["upgrade_or_wait", false]],
        request_too_large: [["start_continuation", false]],
        output_limit_reached: [["continue", false]],
        runtime_unavailable: [["retry", true], ["start_continuation", false], ["contact_support", false]],
        runtime_timeout: [["restart_runtime", false]],
        runtime_crashed: [["restart_runtime", false]],
        runtime_incompatible: [["update_required", false]],
        dependency_unavailable: [["update_required", false]],
        temporary_provider_failure: [["retry", true], ["start_continuation", false], ["contact_support", false]],
        edit_constraint_violation: [["continue", false]],
        unknown: [["contact_support", false]],
    };
    if (!allowedRecovery[failure.kind]?.some(([recovery, retrySafe]) => recovery === failure.recovery && retrySafe === failure.retrySafe)) {
        context.addIssue({ code: "custom", path: ["recovery"], message: "Failure kind, recovery, and retry safety are contradictory" });
    }
    if ((failure.recovery === "retry") !== failure.retrySafe) {
        context.addIssue({ code: "custom", path: ["recovery"], message: "Retry guidance is valid only for a proven retry-safe failure" });
    }
    if (["possible", "confirmed", "unknown"].includes(failure.possibleMutation) && !failure.readbackRequired) {
        context.addIssue({ code: "custom", path: ["readbackRequired"], message: "Mutation uncertainty requires project readback" });
    }
    if (failure.manualRecoveryRequired && !failure.readbackRequired) {
        context.addIssue({ code: "custom", path: ["manualRecoveryRequired"], message: "Manual recovery requires project readback" });
    }
    if (failure.kind === "usage_exhausted" && (failure.recovery !== "upgrade_or_wait" || failure.retrySafe)) {
        context.addIssue({ code: "custom", path: ["kind"], message: "Usage exhaustion is an upgrade-or-wait failure and is never an immediate retry" });
    }
    if (failure.kind === "request_too_large" && (failure.recovery !== "start_continuation" || failure.retrySafe)) {
        context.addIssue({ code: "custom", path: ["kind"], message: "Request-too-large requires a continuation and is never an immediate retry" });
    }
    if (failure.kind === "runtime_incompatible" && (failure.recovery !== "update_required" || failure.retrySafe)) {
        context.addIssue({ code: "custom", path: ["kind"], message: "Runtime incompatibility requires an update before continuing" });
    }
    if (failure.kind === "edit_constraint_violation" && failure.retrySafe) {
        context.addIssue({ code: "custom", path: ["kind"], message: "Editing-constraint denial is never an immediate retry" });
    }
}
export const cutAgentPublicFailureSchema = z.object(cutAgentPublicFailureFields)
    .strict()
    .superRefine(validateCutAgentPublicFailure);
const CODE_KEYS = ["error_code", "cloudErrorCode", "code", "type", "cli_error_code", "cause_code", "reason"];
function records(value, depth = 0) {
    if (typeof value === "string" && depth <= 4) {
        const start = value.indexOf("{");
        if (start < 0 || value.length - start > 4_096)
            return [];
        try {
            return records(JSON.parse(value.slice(start)), depth + 1);
        }
        catch {
            return [];
        }
    }
    if (!value || typeof value !== "object" || Array.isArray(value) || depth > 4)
        return [];
    const record = value;
    const nested = [record.error, record.cause, record.additionalDetails, record.details, record.incomplete_details,
        record.response, record.failure, record.public_failure]
        .flatMap((child) => records(child, depth + 1));
    return [record, ...nested];
}
function boundedText(value) {
    const parts = [];
    const visit = (candidate, depth) => {
        if (parts.join(" ").length >= 16_384 || depth > 4 || candidate === null || candidate === undefined)
            return;
        if (typeof candidate === "string") {
            parts.push(candidate.slice(0, 4_096));
            const start = candidate.indexOf("{");
            if (start >= 0 && candidate.length - start <= 4_096) {
                try {
                    visit(JSON.parse(candidate.slice(start)), depth + 1);
                }
                catch { /* diagnostic text only */ }
            }
            return;
        }
        if (typeof candidate !== "object" || Array.isArray(candidate))
            return;
        const record = candidate;
        for (const key of ["message", "detail", "error", "additionalDetails", "cause"])
            visit(record[key], depth + 1);
    };
    visit(value, 0);
    return parts.join(" ").toLowerCase();
}
function normalizedCodes(value) {
    return records(value).flatMap((record) => CODE_KEYS.flatMap((key) => {
        const candidate = record[key];
        return typeof candidate === "string" && candidate.trim() ? [candidate.trim().slice(0, 128)] : [];
    }));
}
function statusFrom(input) {
    if (Number.isInteger(input.status))
        return input.status ?? null;
    for (const record of records(input.raw)) {
        for (const key of ["status", "statusCode", "status_code"]) {
            const value = record[key];
            if (Number.isInteger(value))
                return value;
        }
    }
    return null;
}
function authoritativeUsageState(value) {
    for (const record of records(value)) {
        if (record.usage_charged === false)
            return "not_reserved";
        if (record.usage_charged === true)
            return "consumed";
    }
    return null;
}
function explicitFailure(value) {
    for (const record of records(value)) {
        if (record.public_failure && typeof record.public_failure === "object"
            && record.public_failure.contractVersion !== undefined)
            return record.public_failure;
        if (record.failure && typeof record.failure === "object"
            && record.failure.contractVersion !== undefined)
            return record.failure;
    }
    return null;
}
function stableCauseCode(codes) {
    return codes.find((code) => /^[A-Z][A-Z0-9_]{2,127}$/.test(code))
        ?? codes.find((code) => /^[a-z][a-z0-9_.-]{2,127}$/.test(code))
        ?? null;
}
function make(input, fields) {
    return cutAgentPublicFailureSchema.parse({
        contractVersion: 1,
        incidentId: input.incidentId,
        correlation: input.correlation,
        causeCode: fields.causeCode ?? null,
        ...fields,
    });
}
function unknownFailure(input, code = null, causeCode = null) {
    const mutation = input.possibleMutation ?? "unknown";
    return make(input, {
        kind: "unknown",
        code: code ?? causeCode ?? "FAILURE_UNKNOWN",
        causeCode,
        recovery: "contact_support",
        retrySafe: false,
        usageState: input.usageState ?? "unknown",
        possibleMutation: mutation,
        readbackRequired: mutation !== "none",
        manualRecoveryRequired: mutation !== "none",
    });
}
export function classifyCutAgentFailure(input) {
    const explicit = explicitFailure(input.raw);
    if (explicit !== null) {
        const candidate = explicit && typeof explicit === "object" ? {
            ...explicit,
            ...(input.usageState ? { usageState: input.usageState } : {}),
            ...(input.possibleMutation ? {
                possibleMutation: input.possibleMutation,
                readbackRequired: input.possibleMutation !== "none",
                manualRecoveryRequired: input.possibleMutation !== "none"
                    && explicit.manualRecoveryRequired === true,
            } : {}),
        } : explicit;
        const parsed = cutAgentPublicFailureSchema.safeParse(candidate);
        if (parsed.success)
            return parsed.data;
        return unknownFailure(input, "FAILURE_CONTRACT_INVALID", stableCauseCode(normalizedCodes(input.raw)));
    }
    const codes = normalizedCodes(input.raw);
    const normalized = new Set(codes.map((code) => code.toLowerCase()));
    const text = boundedText(input.raw);
    const status = statusFrom(input);
    const usageState = input.usageState ?? authoritativeUsageState(input.raw) ?? undefined;
    const causeCode = stableCauseCode(codes);
    const code = causeCode ?? "RUN_FAILED";
    const has = (...candidates) => candidates.some((candidate) => normalized.has(candidate.toLowerCase()));
    const hasOpenAiFailedTerminal = codes.some((candidate) => candidate.toLowerCase().startsWith("openai_response_failed_"));
    if (has("insufficient_credits", "usage_limit_exceeded", "usage_exhausted", "USAGE_EXHAUSTED")
        || (/\b402\b/.test(text) && /usage|credit|quota/.test(text))) {
        const mutation = input.possibleMutation ?? "unknown";
        return make(input, { kind: "usage_exhausted", code, causeCode, recovery: "upgrade_or_wait", retrySafe: false,
            usageState: usageState ?? "unknown", possibleMutation: mutation,
            readbackRequired: mutation !== "none", manualRecoveryRequired: false });
    }
    if (status === 413 || has("request_too_large", "request_body_too_large", "function_payload_too_large", "payload_too_large")
        || (/\b413\b/.test(text) && /payload|request|body|entity/.test(text))) {
        const mutation = input.possibleMutation ?? "unknown";
        return make(input, { kind: "request_too_large", code, causeCode, recovery: "start_continuation", retrySafe: false,
            usageState: usageState ?? "unknown", possibleMutation: mutation,
            readbackRequired: mutation !== "none", manualRecoveryRequired: false });
    }
    if (has("output_limit_reached", "max_output_tokens", "length", "incomplete_output", "openai_response_incomplete_max_output_tokens")
        || /max[_ -]?output[_ -]?tokens|output limit|incomplete.*length/.test(text)) {
        const mutation = input.possibleMutation ?? "unknown";
        return make(input, { kind: "output_limit_reached", code, causeCode, recovery: "continue", retrySafe: false,
            usageState: usageState ?? "consumed", possibleMutation: mutation, readbackRequired: mutation !== "none", manualRecoveryRequired: false });
    }
    if (has("edit_constraint_violation", "EDIT_CONSTRAINT_VIOLATION")) {
        const mutation = input.possibleMutation ?? "unknown";
        return make(input, { kind: "edit_constraint_violation", code, causeCode, recovery: "continue", retrySafe: false,
            usageState: usageState ?? "unknown", possibleMutation: mutation,
            readbackRequired: mutation !== "none", manualRecoveryRequired: false });
    }
    if (has("runtime_incompatible", "sdk_incompatible", "protocol_incompatible", "codex_protocol_incompatible", "protocol_digest_mismatch")) {
        const mutation = input.possibleMutation ?? "none";
        return make(input, { kind: "runtime_incompatible", code, causeCode, recovery: "update_required", retrySafe: false,
            usageState: usageState ?? "not_reserved", possibleMutation: mutation,
            readbackRequired: mutation !== "none", manualRecoveryRequired: false });
    }
    if (has("dependency_unavailable", "DEPENDENCY_UNAVAILABLE", "runtime_dependency_missing")) {
        return make(input, { kind: "dependency_unavailable", code, causeCode, recovery: "update_required", retrySafe: false,
            usageState: usageState ?? "not_reserved", possibleMutation: "none", readbackRequired: false, manualRecoveryRequired: false });
    }
    if (has("runtime_timeout", "CUTAGENT_CLI_TIMEOUT", "ETIMEDOUT", "UND_ERR_CONNECT_TIMEOUT") || /runtime[^.]{0,40}timed? out/.test(text)) {
        const mutation = input.possibleMutation ?? "unknown";
        return make(input, { kind: "runtime_timeout", code, causeCode, recovery: "restart_runtime", retrySafe: false,
            usageState: usageState ?? "unknown", possibleMutation: mutation, readbackRequired: mutation !== "none", manualRecoveryRequired: mutation !== "none" });
    }
    if (has("runtime_crashed", "RUNTIME_CRASHED", "EPIPE", "ECONNRESET", "PROCESS_EXITED")) {
        const mutation = input.possibleMutation ?? "unknown";
        return make(input, { kind: "runtime_crashed", code, causeCode, recovery: "restart_runtime", retrySafe: false,
            usageState: usageState ?? "unknown", possibleMutation: mutation, readbackRequired: mutation !== "none", manualRecoveryRequired: mutation !== "none" });
    }
    if (has("runtime_unavailable", "RUNTIME_UNAVAILABLE", "runtime_not_ready")) {
        const mutation = input.possibleMutation ?? "unknown";
        const safe = mutation === "none" && ["not_reserved", "released"].includes(usageState ?? "not_reserved");
        return make(input, { kind: "runtime_unavailable", code, causeCode, recovery: safe ? "retry" : "contact_support", retrySafe: safe,
            usageState: usageState ?? "not_reserved", possibleMutation: mutation, readbackRequired: mutation !== "none", manualRecoveryRequired: mutation !== "none" });
    }
    if (has("provider_outcome_unknown")) {
        const mutation = input.possibleMutation ?? "unknown";
        return make(input, { kind: "temporary_provider_failure", code, causeCode,
            recovery: "start_continuation", retrySafe: false,
            usageState: usageState ?? "unknown", possibleMutation: mutation,
            readbackRequired: mutation !== "none", manualRecoveryRequired: false });
    }
    if (has("temporary_provider_failure", "openai_proxy_fetch_failed", "openai_proxy_request_failed", "rate_limit_exceeded")
        || hasOpenAiFailedTerminal
        || status === 429 || (status !== null && status >= 500 && status <= 599)) {
        const mutation = input.possibleMutation ?? "unknown";
        const usage = usageState ?? (status === 429 ? "not_reserved" : "unknown");
        const safe = mutation === "none" && ["not_reserved", "released"].includes(usage);
        return make(input, { kind: "temporary_provider_failure", code, causeCode, recovery: safe ? "retry" : "contact_support", retrySafe: safe,
            usageState: usage, possibleMutation: mutation, readbackRequired: mutation !== "none", manualRecoveryRequired: mutation !== "none" });
    }
    return unknownFailure(input, null, causeCode);
}
