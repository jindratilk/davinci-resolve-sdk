import { z } from "zod";
import { sdkProjectIdSchema, sdkRevisionSchema, sdkTimelineIdSchema, sdkTimelineItemIdSchema, } from "./sdk-identities.js";
const fairlightBindingSchema = z.object({
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    timelineRevision: sdkRevisionSchema,
}).strict();
const fairlightTrackTargetSchema = z.object({
    kind: z.literal("track"),
    trackIndex: z.number().int().min(1).max(4096),
}).strict();
const fairlightClipTargetSchema = z.object({
    kind: z.literal("clip"),
    clipId: sdkTimelineItemIdSchema,
    trackIndex: z.number().int().min(1).max(4096),
}).strict();
const fairlightClipsTargetSchema = z.object({
    kind: z.literal("clips"),
    clips: z.array(fairlightClipTargetSchema.omit({ kind: true })).min(2).max(256).refine((clips) => new Set(clips.map((clip) => clip.clipId)).size === clips.length, "Synchronization clip identities must be unique"),
}).strict();
const fairlightBusTargetSchema = z.object({
    kind: z.literal("bus"),
    busName: z.string().min(1).max(256),
    busKind: z.enum(["main", "bus"]),
}).strict();
const fairlightBoundClipSchema = fairlightBindingSchema.extend({ target: fairlightClipTargetSchema }).strict();
const fairlightBoundTrackSchema = fairlightBindingSchema.extend({ target: fairlightTrackTargetSchema }).strict();
export const sdkFairlightClipGainInputSchema = fairlightBoundClipSchema.extend({ kind: z.literal("clip_gain"), gainDb: z.number().finite().min(-160).max(60) }).strict();
export const sdkFairlightClipPanInputSchema = fairlightBoundClipSchema.extend({ kind: z.literal("clip_pan"), pan: z.number().finite().min(-1).max(1) }).strict();
export const sdkFairlightClipFadeInputSchema = fairlightBoundClipSchema.extend({ kind: z.literal("clip_fade"), direction: z.enum(["in", "out"]), durationFrames: z.number().int().min(0).max(10_000_000) }).strict();
export const sdkFairlightTrackMixInputSchema = fairlightBoundTrackSchema.extend({
    kind: z.literal("track_mix"),
    levelDb: z.number().finite().min(-160).max(60),
    pan: z.number().finite().min(-1).max(1),
}).strict();
export const sdkFairlightRouteInputSchema = fairlightBoundTrackSchema.extend({ kind: z.literal("routing"), destination: fairlightBusTargetSchema }).strict();
const fairlightEqBandSchema = z.object({
    band: z.number().int().min(1).max(32),
    enabled: z.boolean(),
    filterType: z.enum(["low_cut", "low_shelf", "bell", "high_shelf", "high_cut"]),
    frequencyHz: z.number().finite().positive().max(200_000),
    gainDb: z.number().finite().min(-60).max(60),
    q: z.number().finite().positive().max(100),
}).strict();
export const sdkFairlightEqInputSchema = fairlightBoundClipSchema.extend({
    kind: z.literal("eq"),
    enabled: z.boolean(),
    bands: z.array(fairlightEqBandSchema).min(1).max(32).superRefine((bands, context) => {
        const seen = new Set();
        for (const [index, band] of bands.entries()) {
            if (seen.has(band.band))
                context.addIssue({ code: "custom", path: [index, "band"], message: "Fairlight EQ band indexes must be unique" });
            seen.add(band.band);
        }
    }),
}).strict();
const fairlightDynamicsProcessorSchema = z.object({
    enabled: z.boolean(),
    thresholdDb: z.number().finite().min(-160).max(60),
    ratio: z.number().finite().min(1).max(100).nullable(),
}).strict();
export const sdkFairlightDynamicsInputSchema = fairlightBoundTrackSchema.extend({
    kind: z.literal("dynamics"),
    compressor: fairlightDynamicsProcessorSchema,
    gate: fairlightDynamicsProcessorSchema,
    limiter: fairlightDynamicsProcessorSchema,
}).strict();
export const sdkFairlightEffectInputSchema = fairlightBoundClipSchema.extend({
    kind: z.literal("effect"),
    pluginId: z.string().min(1).max(256).regex(/^[A-Za-z0-9][A-Za-z0-9 ._:/()+-]*$/),
    presetId: z.string().min(1).max(256).regex(/^[A-Za-z0-9][A-Za-z0-9 ._:/()+-]*$/).optional(),
}).strict();
export const sdkFairlightSynchronizeInputSchema = fairlightBindingSchema.extend({
    kind: z.literal("synchronization"),
    target: fairlightClipsTargetSchema,
    mode: z.enum(["timecode", "waveform"]),
    preserveLinkedMedia: z.literal(true),
}).strict();
export const sdkFairlightLoudnessInputSchema = fairlightBindingSchema.extend({
    kind: z.literal("loudness"),
    target: z.union([fairlightTrackTargetSchema, fairlightBusTargetSchema]),
    integratedLufs: z.number().finite().min(-70).max(0),
    truePeakDbtp: z.number().finite().min(-20).max(0),
}).strict();
const fairlightPlanChangeSchema = z.discriminatedUnion("kind", [
    sdkFairlightClipGainInputSchema,
    sdkFairlightClipPanInputSchema,
    sdkFairlightClipFadeInputSchema,
    sdkFairlightTrackMixInputSchema,
    sdkFairlightRouteInputSchema,
    sdkFairlightEqInputSchema,
    sdkFairlightDynamicsInputSchema,
    sdkFairlightEffectInputSchema,
    sdkFairlightSynchronizeInputSchema,
    sdkFairlightLoudnessInputSchema,
]);
export const sdkFairlightPlanInputSchema = fairlightBindingSchema.extend({
    changes: z.array(fairlightPlanChangeSchema).min(1).max(128),
    preserveLinkedMedia: z.literal(true),
}).strict().superRefine((plan, context) => {
    for (const [index, change] of plan.changes.entries()) {
        if (change.projectId !== plan.projectId || change.timelineId !== plan.timelineId || change.timelineRevision !== plan.timelineRevision) {
            context.addIssue({ code: "custom", path: ["changes", index], message: "Every Fairlight plan change must share the exact plan binding" });
        }
    }
});
const fairlightBusStateSchema = z.object({ busName: z.string().min(1).max(256), busKind: z.enum(["main", "bus"]) }).strict();
const fairlightMixStateSchema = z.object({ levelDb: z.number().finite().min(-160).max(60), pan: z.number().finite().min(-1).max(1) }).strict();
const fairlightEqStateSchema = z.object({
    enabled: z.boolean(),
    bands: z.array(fairlightEqBandSchema).max(32).refine((bands) => new Set(bands.map((band) => band.band)).size === bands.length, "Fairlight EQ band indexes must be unique"),
}).strict();
const fairlightDynamicsStateSchema = z.object({
    compressor: fairlightDynamicsProcessorSchema,
    gate: fairlightDynamicsProcessorSchema,
    limiter: fairlightDynamicsProcessorSchema,
}).strict();
const fairlightSyncPositionSchema = z.object({ clipId: sdkTimelineItemIdSchema, recordStartFrame: z.number().int().safe() }).strict();
const fairlightSyncPositionsSchema = z.array(fairlightSyncPositionSchema).min(2).max(256).refine((positions) => new Set(positions.map((position) => position.clipId)).size === positions.length, "Synchronization positions must contain unique clip identities");
const fairlightSemanticChangeSchema = z.discriminatedUnion("kind", [
    z.object({ kind: z.literal("clip_gain"), beforeDb: z.number().finite().min(-160).max(60).nullable(), afterDb: z.number().finite().min(-160).max(60).nullable() }).strict(),
    z.object({ kind: z.literal("clip_pan"), before: z.number().finite().min(-1).max(1).nullable(), after: z.number().finite().min(-1).max(1).nullable() }).strict(),
    z.object({ kind: z.literal("clip_fade"), direction: z.enum(["in", "out"]), beforeFrames: z.number().int().min(0).nullable(), afterFrames: z.number().int().min(0).nullable() }).strict(),
    z.object({ kind: z.literal("track_mix"), before: fairlightMixStateSchema.nullable(), after: fairlightMixStateSchema.nullable() }).strict(),
    z.object({ kind: z.literal("routing"), before: fairlightBusStateSchema.nullable(), after: fairlightBusStateSchema.nullable() }).strict(),
    z.object({ kind: z.literal("eq"), before: fairlightEqStateSchema.nullable(), after: fairlightEqStateSchema.nullable() }).strict(),
    z.object({ kind: z.literal("dynamics"), before: fairlightDynamicsStateSchema.nullable(), after: fairlightDynamicsStateSchema.nullable() }).strict(),
    z.object({ kind: z.literal("effect"), pluginId: z.string().min(1).max(256), presetId: z.string().min(1).max(256).nullable(), beforePresent: z.boolean().nullable(), afterPresent: z.boolean().nullable() }).strict(),
    z.object({ kind: z.literal("synchronization"), mode: z.enum(["timecode", "waveform"]), before: fairlightSyncPositionsSchema, after: fairlightSyncPositionsSchema }).strict(),
    z.object({ kind: z.literal("loudness"), before: z.object({ integratedLufs: z.number().finite(), truePeakDbtp: z.number().finite() }).strict().nullable(), after: z.object({ integratedLufs: z.number().finite(), truePeakDbtp: z.number().finite() }).strict().nullable() }).strict(),
]);
const fairlightResultTargetSchema = z.union([
    fairlightClipTargetSchema,
    fairlightTrackTargetSchema,
    fairlightBusTargetSchema,
    fairlightClipsTargetSchema,
]);
const fairlightEvidenceIdSchema = z.string().min(12).max(256).regex(/^evidence_[A-Za-z0-9._~-]+$/);
const fairlightSha256Schema = z.string().regex(/^sha256:[a-f0-9]{64}$/);
const fairlightEvidenceCheckSchema = z.object({
    evidenceId: fairlightEvidenceIdSchema,
    stepIndex: z.number().int().min(0).max(127).nullable(),
    kind: z.enum(["structural_readback", "audio_audition"]),
    status: z.enum(["passed", "failed", "unavailable"]),
    target: fairlightResultTargetSchema.nullable(),
    summary: z.string().min(1).max(1024),
    stateDigest: fairlightSha256Schema.nullable(),
    artifact: z.object({
        artifactId: z.string().min(12).max(256).regex(/^artifact_[A-Za-z0-9._~-]+$/),
        sha256: fairlightSha256Schema,
        mediaType: z.enum(["audio/wav", "audio/flac", "audio/mp4", "audio/mpeg"]),
    }).strict().nullable(),
}).strict().superRefine((check, context) => {
    if (check.kind === "structural_readback" && (check.stepIndex === null || check.target === null)) {
        context.addIssue({ code: "custom", message: "Structural proof must identify its exact submitted-plan step and target" });
    }
    if (check.kind === "audio_audition" && (check.stepIndex !== null || check.target !== null)) {
        context.addIssue({ code: "custom", message: "Aggregate audition proof cannot be attributed to one submitted-plan step or target" });
    }
    if (check.kind === "structural_readback" && check.status !== "unavailable" && check.stateDigest === null) {
        context.addIssue({ code: "custom", path: ["stateDigest"], message: "Observed structural proof requires a state digest" });
    }
    if (check.kind === "structural_readback" && check.artifact !== null) {
        context.addIssue({ code: "custom", path: ["artifact"], message: "Structural proof cannot claim an audition artifact" });
    }
    if (check.kind === "audio_audition" && check.status !== "unavailable" && check.artifact === null) {
        context.addIssue({ code: "custom", path: ["artifact"], message: "Observed audition proof requires a content-addressed audio artifact" });
    }
    if (check.kind === "audio_audition" && check.stateDigest !== null) {
        context.addIssue({ code: "custom", path: ["stateDigest"], message: "Audition proof uses its artifact digest rather than a structural state digest" });
    }
    if (check.status === "unavailable" && (check.stateDigest !== null || check.artifact !== null)) {
        context.addIssue({ code: "custom", message: "Unavailable evidence cannot carry observed proof material" });
    }
});
const fairlightStepResultSchema = z.object({
    stepIndex: z.number().int().min(0).max(127),
    outcome: z.enum(["succeeded", "no_change", "partial"]),
    target: fairlightResultTargetSchema,
    change: fairlightSemanticChangeSchema,
    structuralEvidenceId: fairlightEvidenceIdSchema,
    auditionEvidenceId: fairlightEvidenceIdSchema.nullable(),
}).strict().superRefine((step, context) => {
    const expectedTargets = {
        clip_gain: ["clip"], clip_pan: ["clip"], clip_fade: ["clip"], eq: ["clip"], effect: ["clip"],
        track_mix: ["track"], dynamics: ["track"], routing: ["track"], synchronization: ["clips"], loudness: ["track", "bus"],
    };
    if (!expectedTargets[step.change.kind].includes(step.target.kind)) {
        context.addIssue({ code: "custom", path: ["target"], message: "Fairlight result target and semantic change kinds must agree" });
    }
    if (step.change.kind === "synchronization" && step.target.kind === "clips") {
        const expected = step.target.clips.map((clip) => clip.clipId).sort();
        if (JSON.stringify([...step.change.before.map((position) => position.clipId)].sort()) !== JSON.stringify(expected)
            || JSON.stringify([...step.change.after.map((position) => position.clipId)].sort()) !== JSON.stringify(expected)) {
            context.addIssue({ code: "custom", path: ["change"], message: "Synchronization before and after state must cover the exact target clip identities" });
        }
    }
    if (step.outcome === "succeeded" && !fairlightChanged(step.change)) {
        context.addIssue({ code: "custom", path: ["change"], message: "Successful Fairlight steps require a concrete before/after state change" });
    }
    if (step.outcome === "no_change" && fairlightChanged(step.change)) {
        context.addIssue({ code: "custom", path: ["change"], message: "No-change Fairlight steps cannot contain a before/after state change" });
    }
    if (step.outcome === "no_change" && step.auditionEvidenceId !== null) {
        context.addIssue({ code: "custom", path: ["auditionEvidenceId"], message: "No-change steps cannot claim changed-audio audition proof" });
    }
    if (step.auditionEvidenceId !== null) {
        context.addIssue({ code: "custom", path: ["auditionEvidenceId"], message: "Aggregate Fairlight audition proof cannot be attributed to one step" });
    }
});
function fairlightChanged(change) {
    if (change.kind === "effect")
        return change.beforePresent !== null && change.afterPresent !== null && change.beforePresent !== change.afterPresent;
    if (change.kind === "synchronization") {
        const canonical = (positions) => [...positions].sort((left, right) => left.clipId.localeCompare(right.clipId));
        return JSON.stringify(canonical(change.before)) !== JSON.stringify(canonical(change.after));
    }
    if (change.kind === "eq") {
        const canonical = (state) => state === null ? null : {
            enabled: state.enabled,
            bands: [...state.bands].sort((left, right) => left.band - right.band),
        };
        return change.before !== null && change.after !== null && JSON.stringify(canonical(change.before)) !== JSON.stringify(canonical(change.after));
    }
    if (change.kind === "clip_gain")
        return change.beforeDb !== null && change.afterDb !== null && change.beforeDb !== change.afterDb;
    if (change.kind === "clip_pan")
        return change.before !== null && change.after !== null && change.before !== change.after;
    if (change.kind === "clip_fade")
        return change.beforeFrames !== null && change.afterFrames !== null && change.beforeFrames !== change.afterFrames;
    return change.before !== null && change.after !== null && JSON.stringify(change.before) !== JSON.stringify(change.after);
}
export const sdkFairlightSemanticResultSchema = z.object({
    actionId: z.literal("cutagent.action.sdk.fairlight.plan.apply"),
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    outcome: z.enum(["succeeded", "no_change", "partial"]),
    timelineRevision: sdkRevisionSchema,
    affectedClipIds: z.array(sdkTimelineItemIdSchema).max(4096).refine((ids) => new Set(ids).size === ids.length, "Affected clip identities must be unique"),
    affectedTrackIndexes: z.array(z.number().int().min(1).max(4096)).max(4096).refine((indexes) => new Set(indexes).size === indexes.length, "Affected track indexes must be unique"),
    affectedBuses: z.array(fairlightBusStateSchema).max(4096).refine((buses) => new Set(buses.map((bus) => `${bus.busKind}:${bus.busName}`)).size === buses.length, "Affected bus identities must be unique"),
    steps: z.array(fairlightStepResultSchema).min(1).max(128).refine((steps) => new Set(steps.map((step) => step.stepIndex)).size === steps.length, "Fairlight result step indexes must be unique"),
    evidence: z.object({
        outcome: z.enum(["passed", "partial", "failed", "manual_review_required"]),
        structuralReadback: z.enum(["passed", "failed", "unavailable"]),
        audition: z.object({ required: z.boolean(), status: z.enum(["not_run", "passed", "failed", "unavailable"]) }).strict(),
        checks: z.array(fairlightEvidenceCheckSchema).min(1).max(256).refine((checks) => new Set(checks.map((check) => check.evidenceId)).size === checks.length, "Fairlight evidence identities must be unique"),
        protectedState: z.object({
            evidenceId: fairlightEvidenceIdSchema,
            status: z.enum(["passed", "failed", "unavailable"]),
            linkedMedia: z.enum(["preserved", "changed", "unavailable"]),
            unexpectedChanges: z.boolean().nullable(),
            stateDigest: fairlightSha256Schema.nullable(),
            summary: z.string().min(1).max(1024),
        }).strict(),
    }).strict(),
    recovery: z.discriminatedUnion("state", [
        z.object({ state: z.literal("none"), manualRecoveryRequired: z.literal(false), guidance: z.null() }).strict(),
        z.object({ state: z.literal("readback_required"), manualRecoveryRequired: z.literal(false), guidance: z.string().min(1).max(1024) }).strict(),
        z.object({ state: z.literal("manual_recovery_required"), manualRecoveryRequired: z.literal(true), guidance: z.string().min(1).max(1024) }).strict(),
    ]),
}).strict().superRefine((result, context) => {
    const changedSteps = result.steps.filter((step) => fairlightChanged(step.change));
    const affectedCount = result.affectedClipIds.length + result.affectedTrackIndexes.length + result.affectedBuses.length;
    const checksById = new Map(result.evidence.checks.map((check) => [check.evidenceId, check]));
    const evidenceReferenceCounts = new Map();
    const referenceEvidence = (evidenceId, path) => {
        const count = (evidenceReferenceCounts.get(evidenceId) ?? 0) + 1;
        evidenceReferenceCounts.set(evidenceId, count);
        if (count > 1) {
            context.addIssue({ code: "custom", path, message: "Each Fairlight structural evidence identity must be referenced by exactly one submitted-plan step" });
        }
    };
    for (const [index, step] of result.steps.entries()) {
        const structural = checksById.get(step.structuralEvidenceId);
        referenceEvidence(step.structuralEvidenceId, ["steps", index, "structuralEvidenceId"]);
        if (!structural || structural.stepIndex !== step.stepIndex || structural.kind !== "structural_readback" || JSON.stringify(structural.target) !== JSON.stringify(step.target)) {
            context.addIssue({ code: "custom", path: ["steps", index, "structuralEvidenceId"], message: "Step structural evidence must cover this exact step and target" });
        }
        if (step.outcome === "succeeded" && structural?.status !== "passed") {
            context.addIssue({ code: "custom", path: ["steps", index], message: "Successful steps require passed structural proof" });
        }
        if (step.outcome === "no_change" && structural?.status !== "passed") {
            context.addIssue({ code: "custom", path: ["steps", index], message: "No-change steps require passed structural proof" });
        }
    }
    const structuralCheckCount = result.evidence.checks.filter((check) => check.kind === "structural_readback").length;
    if (evidenceReferenceCounts.size !== structuralCheckCount) {
        context.addIssue({ code: "custom", path: ["evidence", "checks"], message: "Fairlight structural checks must be referenced by exactly one submitted-plan step" });
    }
    const structuralStatuses = result.evidence.checks.filter((check) => check.kind === "structural_readback").map((check) => check.status);
    const expectedStructuralStatus = structuralStatuses.every((status) => status === "passed")
        ? "passed"
        : structuralStatuses.some((status) => status === "failed") ? "failed" : "unavailable";
    if (result.evidence.structuralReadback !== expectedStructuralStatus) {
        context.addIssue({ code: "custom", path: ["evidence", "structuralReadback"], message: "Aggregate structural status must match the submitted step checks" });
    }
    const auditionStatuses = result.evidence.checks.filter((check) => check.kind === "audio_audition").map((check) => check.status);
    const expectedAuditionStatus = auditionStatuses.length === 0
        ? "not_run"
        : auditionStatuses.every((status) => status === "passed")
            ? "passed"
            : auditionStatuses.some((status) => status === "failed") ? "failed" : "unavailable";
    if (result.evidence.audition.status !== expectedAuditionStatus) {
        context.addIssue({ code: "custom", path: ["evidence", "audition", "status"], message: "Aggregate audition status must match the audition checks" });
    }
    if (result.evidence.audition.required !== (auditionStatuses.length > 0)) {
        context.addIssue({ code: "custom", path: ["evidence", "audition", "required"], message: "Aggregate audition requirement must match the audition checks" });
    }
    const protectedState = result.evidence.protectedState;
    if (checksById.has(protectedState.evidenceId)) {
        context.addIssue({ code: "custom", path: ["evidence", "protectedState", "evidenceId"], message: "Protected-state evidence must have an identity distinct from every step check" });
    }
    if (protectedState.status === "passed" && (protectedState.linkedMedia !== "preserved" || protectedState.unexpectedChanges !== false || protectedState.stateDigest === null)) {
        context.addIssue({ code: "custom", path: ["evidence", "protectedState"], message: "Passed protected-state proof requires preserved linked media, zero unexpected changes, and a digest" });
    }
    if (protectedState.status === "unavailable" && (protectedState.linkedMedia !== "unavailable" || protectedState.unexpectedChanges !== null || protectedState.stateDigest !== null)) {
        context.addIssue({ code: "custom", path: ["evidence", "protectedState"], message: "Unavailable protected-state proof cannot claim observations" });
    }
    if (protectedState.status === "failed" && (protectedState.stateDigest === null
        || (protectedState.linkedMedia !== "changed" && protectedState.unexpectedChanges !== true))) {
        context.addIssue({ code: "custom", path: ["evidence", "protectedState"], message: "Failed protected-state proof requires an observed digest and a concrete preservation failure" });
    }
    const hasFailedProof = result.evidence.checks.some((check) => check.status === "failed") || protectedState.status === "failed";
    const hasUnavailableProof = result.evidence.checks.some((check) => check.status === "unavailable") || protectedState.status === "unavailable";
    if (result.evidence.outcome === "passed" && (hasFailedProof || hasUnavailableProof || result.outcome === "partial")) {
        context.addIssue({ code: "custom", path: ["evidence", "outcome"], message: "Passed Fairlight evidence requires complete proof for a completed result" });
    }
    if (result.evidence.outcome === "failed" && !hasFailedProof) {
        context.addIssue({ code: "custom", path: ["evidence", "outcome"], message: "Failed Fairlight evidence requires at least one concrete failed proof" });
    }
    if (result.evidence.outcome === "partial" && (hasFailedProof || !hasUnavailableProof)) {
        context.addIssue({ code: "custom", path: ["evidence", "outcome"], message: "Partial Fairlight evidence requires unavailable proof without a known failed proof" });
    }
    if (result.evidence.outcome === "manual_review_required" && result.recovery.state !== "manual_recovery_required") {
        context.addIssue({ code: "custom", path: ["evidence", "outcome"], message: "Manual-review evidence requires explicit manual recovery" });
    }
    if (hasFailedProof && result.recovery.state !== "manual_recovery_required") {
        context.addIssue({ code: "custom", path: ["recovery"], message: "Known failed Fairlight proof requires manual recovery" });
    }
    if (result.outcome === "succeeded" && (affectedCount === 0 || changedSteps.length !== result.steps.length || result.steps.some((step) => step.outcome !== "succeeded")
        || result.evidence.outcome !== "passed" || result.evidence.structuralReadback !== "passed" || protectedState.status !== "passed")) {
        context.addIssue({ code: "custom", path: ["evidence"], message: "Successful Fairlight results require passed structural verification" });
    }
    if (result.outcome === "partial" && (changedSteps.length === 0 || affectedCount === 0
        || !result.steps.some((step) => step.outcome === "partial")
        || (!hasFailedProof && !hasUnavailableProof))) {
        context.addIssue({ code: "custom", path: ["evidence"], message: "Partial Fairlight results require changed targets and incomplete native evidence" });
    }
    if (result.outcome === "partial" && result.recovery.state === "none") {
        context.addIssue({ code: "custom", path: ["recovery"], message: "Partial Fairlight results require explicit recovery" });
    }
    if (result.outcome !== "partial" && (result.recovery.state !== "none" || result.recovery.manualRecoveryRequired || result.recovery.guidance !== null)) {
        context.addIssue({ code: "custom", path: ["recovery"], message: "Completed and no-change Fairlight results cannot claim recovery" });
    }
    if (result.outcome === "no_change" && (affectedCount !== 0 || changedSteps.length !== 0 || result.steps.some((step) => step.outcome !== "no_change")
        || result.evidence.outcome !== "passed" || result.evidence.structuralReadback !== "passed"
        || protectedState.status !== "passed")) {
        context.addIssue({ code: "custom", path: ["outcome"], message: "No-change Fairlight results require zero affected targets and passed structural no-op proof" });
    }
});
function fairlightRequestedStateMatches(change, requested, outcome) {
    if (change.kind !== requested.kind)
        return false;
    const observed = outcome === "succeeded" ? "after" : "before";
    if (change.kind === "clip_gain" && requested.kind === "clip_gain")
        return (observed === "after" ? change.afterDb : change.beforeDb) === requested.gainDb;
    if (change.kind === "clip_pan" && requested.kind === "clip_pan")
        return (observed === "after" ? change.after : change.before) === requested.pan;
    if (change.kind === "clip_fade" && requested.kind === "clip_fade")
        return change.direction === requested.direction && (observed === "after" ? change.afterFrames : change.beforeFrames) === requested.durationFrames;
    if (change.kind === "track_mix" && requested.kind === "track_mix")
        return JSON.stringify(observed === "after" ? change.after : change.before) === JSON.stringify({ levelDb: requested.levelDb, pan: requested.pan });
    if (change.kind === "routing" && requested.kind === "routing")
        return JSON.stringify(observed === "after" ? change.after : change.before) === JSON.stringify({ busName: requested.destination.busName, busKind: requested.destination.busKind });
    if (change.kind === "eq" && requested.kind === "eq") {
        const state = observed === "after" ? change.after : change.before;
        return state !== null && state.enabled === requested.enabled
            && JSON.stringify([...state.bands].sort((left, right) => left.band - right.band)) === JSON.stringify([...requested.bands].sort((left, right) => left.band - right.band));
    }
    if (change.kind === "dynamics" && requested.kind === "dynamics")
        return JSON.stringify(observed === "after" ? change.after : change.before) === JSON.stringify({ compressor: requested.compressor, gate: requested.gate, limiter: requested.limiter });
    if (change.kind === "effect" && requested.kind === "effect")
        return change.pluginId === requested.pluginId && change.presetId === (requested.presetId ?? null) && (observed === "after" ? change.afterPresent : change.beforePresent) === true;
    if (change.kind === "synchronization" && requested.kind === "synchronization") {
        const state = observed === "after" ? change.after : change.before;
        return change.mode === requested.mode && JSON.stringify([...state.map((position) => position.clipId)].sort()) === JSON.stringify([...requested.target.clips.map((clip) => clip.clipId)].sort());
    }
    if (change.kind === "loudness" && requested.kind === "loudness") {
        const measured = observed === "after" ? change.after : change.before;
        return measured !== null && Math.abs(measured.integratedLufs - requested.integratedLufs) <= 0.3
            && measured.truePeakDbtp <= requested.truePeakDbtp;
    }
    return false;
}
function fairlightSorted(values) {
    return [...values].sort((left, right) => left.localeCompare(right));
}
export const sdkFairlightBoundTerminalSchema = z.object({
    input: sdkFairlightPlanInputSchema,
    result: sdkFairlightSemanticResultSchema,
}).strict().superRefine(({ input, result }, context) => {
    if (result.projectId !== input.projectId || result.timelineId !== input.timelineId) {
        context.addIssue({ code: "custom", path: ["result"], message: "Fairlight result project and timeline identities must match the submitted plan" });
    }
    if ((result.outcome === "no_change") !== (result.timelineRevision === input.timelineRevision)) {
        context.addIssue({ code: "custom", path: ["result", "timelineRevision"], message: "Fairlight terminal revision must match its mutation outcome" });
    }
    if (result.steps.length !== input.changes.length) {
        context.addIssue({ code: "custom", path: ["result", "steps"], message: "Fairlight result step count must match the submitted plan" });
        return;
    }
    const affectedClipIds = new Set();
    const affectedTrackIndexes = new Set();
    const affectedBuses = new Set();
    for (const [index, step] of result.steps.entries()) {
        const requested = input.changes[index];
        if (step.stepIndex !== index || step.change.kind !== requested.kind || JSON.stringify(step.target) !== JSON.stringify(requested.target)) {
            context.addIssue({ code: "custom", path: ["result", "steps", index], message: "Fairlight result step must match the exact submitted change and target" });
            continue;
        }
        const requestedStateMatches = fairlightRequestedStateMatches(step.change, requested, step.outcome === "no_change" ? "no_change" : "succeeded");
        if (step.outcome !== "partial" && !requestedStateMatches) {
            context.addIssue({ code: "custom", path: ["result", "steps", index, "change"], message: "Fairlight result step must prove the exact requested effect" });
        }
        if (step.outcome === "partial" && !requestedStateMatches) {
            const proof = result.evidence.checks.find((check) => check.evidenceId === step.structuralEvidenceId);
            if (proof?.status !== "failed") {
                context.addIssue({ code: "custom", path: ["result", "steps", index, "structuralEvidenceId"], message: "A partial Fairlight mismatch requires failed structural proof" });
            }
        }
        if (!fairlightChanged(step.change))
            continue;
        if (step.target.kind === "clip") {
            affectedClipIds.add(step.target.clipId);
            affectedTrackIndexes.add(String(step.target.trackIndex));
        }
        else if (step.target.kind === "track") {
            affectedTrackIndexes.add(String(step.target.trackIndex));
        }
        else if (step.target.kind === "clips") {
            for (const clip of step.target.clips) {
                affectedClipIds.add(clip.clipId);
                affectedTrackIndexes.add(String(clip.trackIndex));
            }
        }
        else {
            affectedBuses.add(`${step.target.busKind}:${step.target.busName}`);
        }
    }
    if (JSON.stringify(fairlightSorted(result.affectedClipIds)) !== JSON.stringify(fairlightSorted(affectedClipIds))
        || JSON.stringify(fairlightSorted(result.affectedTrackIndexes.map(String))) !== JSON.stringify(fairlightSorted(affectedTrackIndexes))
        || JSON.stringify(fairlightSorted(result.affectedBuses.map((bus) => `${bus.busKind}:${bus.busName}`))) !== JSON.stringify(fairlightSorted(affectedBuses))) {
        context.addIssue({ code: "custom", path: ["result"], message: "Fairlight affected identities must match the changed submitted-plan steps" });
    }
});
