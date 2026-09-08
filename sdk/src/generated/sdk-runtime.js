import { z } from "zod";
import { sdkArtifactIdSchema, sdkConnectionIdSchema, sdkMediaPoolFolderIdSchema, sdkMediaPoolItemIdSchema, sdkMarkerIdSchema, sdkProjectIdSchema, sdkRequestIdSchema, sdkRevisionSchema, sdkRenderQueueCursorSchema, sdkRuntimeFingerprintSchema, sdkRuntimeInstanceIdSchema, sdkSessionIdSchema, sdkSnapshotRenderJobIdSchema, sdkSnapshotTimelineItemIdSchema, sdkSnapshotMediaPoolFolderIdSchema, sdkSnapshotMediaPoolItemIdSchema, sdkSnapshotTrackIdSchema, sdkTimelineIdSchema, sdkTimelineItemIdSchema, } from "./sdk-identities.js";
import { sdkProjectContextObservationSchema } from "./sdk-project-media.js";
import { CUTAGENT_SDK_PROTOCOL_DIGEST } from "./sdk-runtime-protocol.js";
import { CUTAGENT_SDK_PREVIEW_VERSION, CUTAGENT_SDK_RUNTIME_MAX_EXCLUSIVE_VERSION, CUTAGENT_SDK_RUNTIME_MIN_VERSION, CUTAGENT_SDK_SUPPORTED_PACKAGE_MAJOR, CUTAGENT_SDK_SUPPORTED_PACKAGE_MINOR, } from "./sdk-runtime-policy.js";
import { sdkFusionCompositionReferenceSchema } from "./sdk-fusion.js";
export * from "./sdk-operations.js";
export * from "./sdk-fairlight.js";
export * from "./sdk-timeline-editing.js";
import { sdkTimelineEditImpactSchema, sdkTimelineEditIntentSchema } from "./sdk-timeline-editing.js";
import { sdkManagedWorkflowClaimSchema, sdkMulticamSnapshotSchema } from "./sdk-operations.js";
export * from "./sdk-fusion.js";
export { CUTAGENT_SDK_PROTOCOL_DIGEST } from "./sdk-runtime-protocol.js";
export { CUTAGENT_SDK_PREVIEW_VERSION, CUTAGENT_SDK_RUNTIME_MAX_EXCLUSIVE_VERSION, CUTAGENT_SDK_RUNTIME_MIN_VERSION, CUTAGENT_SDK_SUPPORTED_PACKAGE_MAJOR, CUTAGENT_SDK_SUPPORTED_PACKAGE_MINOR, } from "./sdk-runtime-policy.js";
export { sdkConnectionIdSchema, sdkMediaPoolFolderIdSchema, sdkMediaPoolItemIdSchema, sdkMarkerIdSchema, sdkProjectIdSchema, sdkRequestIdSchema, sdkRevisionSchema, sdkRenderQueueCursorSchema, sdkRuntimeFingerprintSchema, sdkRuntimeInstanceIdSchema, sdkSessionIdSchema, sdkSnapshotRenderJobIdSchema, sdkSnapshotTimelineItemIdSchema, sdkSnapshotMediaPoolFolderIdSchema, sdkSnapshotMediaPoolItemIdSchema, sdkSnapshotTrackIdSchema, sdkTimelineIdSchema, sdkTimelineItemIdSchema, } from "./sdk-identities.js";
export const CUTAGENT_SDK_WIRE_PROTOCOL = 1;
export const CUTAGENT_SDK_API_VERSION = "0.2";
export const CUTAGENT_SDK_CONNECT_PATH = "/internal/sdk/v1/connect";
export const CUTAGENT_SDK_CONFIRM_PATH = "/internal/sdk/v1/session/confirm";
export const CUTAGENT_SDK_CLOSE_PATH = "/internal/sdk/v1/session/close";
export const CUTAGENT_SDK_READ_PATH = "/internal/sdk/v1/read";
export const CUTAGENT_SDK_OPERATION_PATH = "/internal/sdk/v1/operation";
export const CUTAGENT_SDK_WORKFLOW_PATH = "/internal/sdk/v1/workflow";
export const CUTAGENT_SDK_SESSION_HEADER = "x-cutagent-sdk-session";
export const CUTAGENT_SDK_CAPABILITY_HEADER = "x-cutagent-bridge-capability";
export const CUTAGENT_SDK_MAX_CONTROL_TIMEOUT_MS = 180_000;
const desktopLoopbackEndpointSchema = z.string().url().max(256).refine((value) => {
    try {
        const parsed = new URL(value);
        return parsed.protocol === "http:"
            && parsed.hostname === "127.0.0.1"
            && parsed.port !== ""
            && parsed.username === ""
            && parsed.password === ""
            && parsed.search === ""
            && parsed.hash === ""
            && parsed.pathname === CUTAGENT_SDK_CONNECT_PATH;
    }
    catch {
        return false;
    }
}, "SDK desktop endpoint must be the exact loopback connect route");
const versionSchema = z.string().regex(/^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$/);
const apiVersionSchema = z.string().regex(/^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$/);
const secretSchema = z.string().min(32).max(256).regex(/^[A-Za-z0-9_-]+$/);
const bridgeCapabilitySchema = z.string()
    .min(64)
    .max(1024)
    .regex(/^cutagent-cap\.v1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/);
export const sdkRuntimeDistributionSchema = z.enum(["standalone_local", "plugin_managed"]);
export const sdkCompatibilityHandshakeRequestSchema = z.object({
    requestId: sdkRequestIdSchema,
    sdkVersion: versionSchema,
    sdkApiVersion: apiVersionSchema,
    supportedWireProtocols: z.array(z.number().int().positive()).min(1).max(8),
    requestedDistribution: sdkRuntimeDistributionSchema,
    protocolDigest: z.literal(CUTAGENT_SDK_PROTOCOL_DIGEST),
}).strict();
export const sdkCompatibilityDescriptorSchema = z.object({
    sdkApiVersion: apiVersionSchema,
    wireProtocol: z.number().int().positive(),
    runtimeVersion: versionSchema,
    distribution: sdkRuntimeDistributionSchema,
    distributionVersion: versionSchema,
    cliVersion: versionSchema,
    protocolDigest: z.literal(CUTAGENT_SDK_PROTOCOL_DIGEST),
    runtimeFingerprint: sdkRuntimeFingerprintSchema,
}).strict();
export const sdkCompatibilityHandshakeResponseSchema = z.object({
    requestId: sdkRequestIdSchema,
    descriptor: sdkCompatibilityDescriptorSchema,
}).strict();
export const sdkDesktopDiscoverySchema = z.object({
    version: z.literal(1),
    distribution: z.literal("standalone_local"),
    endpoint: desktopLoopbackEndpointSchema,
    bridgeCapability: bridgeCapabilitySchema,
    bootstrapToken: secretSchema,
    runtimeInstanceId: sdkRuntimeInstanceIdSchema,
    pid: z.number().int().positive(),
    issuedAt: z.string().datetime({ offset: true }),
    expiresAt: z.string().datetime({ offset: true }),
}).strict();
/** Transport-independent request that opens one pending SDK session. */
export const sdkRuntimeSessionConnectRequestSchema = z.object({
    protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
    handshake: sdkCompatibilityHandshakeRequestSchema,
}).strict();
/** Desktop carrier envelope around the transport-independent connect request. */
export const sdkRuntimeConnectRequestSchema = sdkRuntimeSessionConnectRequestSchema.extend({
    runtimeInstanceId: sdkRuntimeInstanceIdSchema,
    bootstrapToken: secretSchema,
}).strict();
export const sdkRuntimeSessionBaseSchema = z.object({
    connectionId: sdkConnectionIdSchema,
    sessionId: sdkSessionIdSchema,
    sessionToken: secretSchema,
    issuedAt: z.string().datetime({ offset: true }),
    expiresAt: z.string().datetime({ offset: true }),
    idleExpiresAt: z.string().datetime({ offset: true }),
}).strict();
export const validateSessionLifetime = (session, context) => {
    const issuedAt = Date.parse(session.issuedAt);
    const expiresAt = Date.parse(session.expiresAt);
    const idleExpiresAt = Date.parse(session.idleExpiresAt);
    if (expiresAt <= issuedAt || expiresAt - issuedAt > 24 * 60 * 60 * 1000) {
        context.addIssue({ code: "custom", path: ["expiresAt"], message: "Session expiry must be after issuance and bounded to 24 hours" });
    }
    if (idleExpiresAt < issuedAt || idleExpiresAt > expiresAt) {
        context.addIssue({ code: "custom", path: ["idleExpiresAt"], message: "Idle expiry must be within the session lifetime" });
    }
};
export const sdkRuntimeSessionSchema = sdkRuntimeSessionBaseSchema.superRefine(validateSessionLifetime);
export const sdkRuntimeConnectSuccessSchema = z.object({
    ok: z.literal(true),
    protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
    requestId: sdkRequestIdSchema,
    descriptor: sdkCompatibilityDescriptorSchema,
    session: sdkRuntimeSessionSchema,
}).strict();
export const sdkTransportErrorCodeSchema = z.enum([
    "INVALID_REQUEST",
    "BOOTSTRAP_REJECTED",
    "AUTHENTICATION_REQUIRED",
    "SUBSCRIPTION_REQUIRED",
    "SDK_INCOMPATIBLE",
    "SESSION_REJECTED",
    "SESSION_LIMIT_REACHED",
    "RUNTIME_UNAVAILABLE",
    "INTERNAL_ERROR",
]);
export const sdkTransportRecoverySchema = z.enum([
    "sign_in",
    "upgrade_or_wait",
    "update_required",
    "reconnect",
    "restart_runtime",
    "contact_support",
]);
export const sdkRuntimeFailureSchema = z.object({
    ok: z.literal(false),
    requestId: sdkRequestIdSchema.optional(),
    error: z.object({
        code: sdkTransportErrorCodeSchema,
        message: z.string().min(1).max(500),
        recovery: sdkTransportRecoverySchema,
    }).strict(),
}).strict();
export const sdkReadErrorCodeSchema = z.union([
    sdkTransportErrorCodeSchema,
    z.enum([
        "RUNTIME_TIMEOUT", "TARGET_NOT_FOUND", "AMBIGUOUS_TARGET", "STALE_REVISION", "INVALID_RESPONSE",
        "CAPABILITY_UNAVAILABLE", "USAGE_EXHAUSTED", "TEMPORARY_PROVIDER_FAILURE",
    ]),
]);
export const sdkReadRecoverySchema = z.union([
    sdkTransportRecoverySchema,
    z.enum(["retry", "inspect_state"]),
]);
export const sdkRuntimeReadFailureSchema = z.object({
    ok: z.literal(false),
    requestId: sdkRequestIdSchema.optional(),
    error: z.object({
        code: sdkReadErrorCodeSchema,
        message: z.string().min(1).max(500),
        recovery: sdkReadRecoverySchema,
    }).strict(),
}).strict();
export const sdkRuntimeConnectResponseSchema = z.union([
    sdkRuntimeConnectSuccessSchema,
    sdkRuntimeFailureSchema,
]);
export const sdkRuntimeCloseRequestSchema = z.object({
    protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
    requestId: sdkRequestIdSchema,
    sessionId: sdkSessionIdSchema,
}).strict();
export const sdkRuntimeConfirmRequestSchema = sdkRuntimeCloseRequestSchema;
export const sdkRuntimeConfirmSuccessSchema = z.object({
    ok: z.literal(true),
    protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
    requestId: sdkRequestIdSchema,
    confirmed: z.literal(true),
}).strict();
export const sdkRuntimeConfirmResponseSchema = z.union([
    sdkRuntimeConfirmSuccessSchema,
    sdkRuntimeFailureSchema,
]);
export const sdkRuntimeCloseSuccessSchema = z.object({
    ok: z.literal(true),
    protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
    requestId: sdkRequestIdSchema,
    closed: z.literal(true),
}).strict();
export const sdkRuntimeCloseResponseSchema = z.union([
    sdkRuntimeCloseSuccessSchema,
    sdkRuntimeFailureSchema,
]);
export const sdkTrackTypeSchema = z.enum(["video", "audio", "subtitle"]);
export const sdkProjectReferenceSchema = z.object({
    id: sdkProjectIdSchema,
    name: z.string().min(1).max(1024),
}).strict();
export const sdkTimelineReferenceSchema = z.object({
    id: sdkTimelineIdSchema,
    projectId: sdkProjectIdSchema,
    name: z.string().min(1).max(1024),
}).strict();
function greatestCommonDivisor(left, right) {
    let a = left;
    let b = right;
    while (b !== 0) {
        const remainder = a % b;
        a = b;
        b = remainder;
    }
    return a;
}
const sdkFrameRateSchema = z.object({
    numerator: z.number().int().positive().max(1_000_000),
    denominator: z.number().int().positive().max(1_000_000),
    nominalTimebase: z.number().int().positive().max(1000),
}).strict().superRefine((rate, context) => {
    if (greatestCommonDivisor(rate.numerator, rate.denominator) !== 1) {
        context.addIssue({ code: "custom", message: "Frame rate rational must be reduced" });
    }
    const calculatedNominalTimebase = Math.floor((rate.numerator + rate.denominator - 1) / rate.denominator);
    if (calculatedNominalTimebase !== rate.nominalTimebase) {
        context.addIssue({ code: "custom", message: "Nominal timebase must equal the ceiling of the actual rate" });
    }
});
const sdkFramesSchema = z.object({ kind: z.literal("frames"), value: z.number().int() }).strict();
const sdkTimelineRecordTimeSchema = z.object({
    domain: z.literal("timeline_record"),
    value: sdkFramesSchema,
}).strict();
const sdkTimelineRecordRangeSchema = z.object({
    domain: z.literal("timeline_record_range"),
    unit: z.literal("frames"),
    start: z.number().int(),
    endExclusive: z.number().int(),
}).strict().refine((range) => range.endExclusive > range.start, {
    message: "Timeline record range end must be greater than start",
    path: ["endExclusive"],
});
const sdkSourceRangeSchema = z.object({
    domain: z.literal("source_range"),
    unit: z.literal("frames"),
    start: z.number().int(),
    endExclusive: z.number().int(),
}).strict().refine((range) => range.endExclusive > range.start, {
    message: "Source range end must be greater than start",
    path: ["endExclusive"],
});
const sdkFrameDurationSchema = z.object({
    domain: z.literal("duration"),
    value: z.object({ kind: z.literal("frames"), value: z.number().int().nonnegative() }).strict(),
}).strict();
const sdkTimelineClipSnapshotObjectSchema = z.object({
    id: sdkTimelineItemIdSchema.nullable(),
    snapshotId: sdkSnapshotTimelineItemIdSchema,
    snapshotTrackId: sdkSnapshotTrackIdSchema,
    snapshotRevision: sdkRevisionSchema,
    name: z.string().min(1).max(4096),
    recordRange: sdkTimelineRecordRangeSchema,
    duration: sdkFrameDurationSchema,
    sourceRange: sdkSourceRangeSchema.nullable(),
    retimeSource: z.object({
        availableRange: sdkSourceRangeSchema,
        originFrame: z.number().finite().nonnegative().max(Number.MAX_SAFE_INTEGER),
    }).strict().nullable().optional(),
    sourceFrameRate: sdkFrameRateSchema.nullable(),
    mediaPoolItemId: sdkMediaPoolItemIdSchema.nullable(),
    linkedItemIds: z.array(sdkTimelineItemIdSchema).max(256).nullable(),
}).strict();
export const sdkTimelineClipSnapshotSchema = sdkTimelineClipSnapshotObjectSchema.superRefine((clip, context) => {
    if (clip.retimeSource && (clip.sourceFrameRate === null
        || clip.retimeSource.availableRange.start !== 0
        || clip.retimeSource.originFrame >= clip.retimeSource.availableRange.endExclusive)) {
        context.addIssue({ code: "custom", message: "Retime source authority requires an available origin and known media rate", path: ["retimeSource"] });
    }
    if (clip.duration.value.value !== clip.recordRange.endExclusive - clip.recordRange.start) {
        context.addIssue({ code: "custom", message: "Clip duration must equal its record range length", path: ["duration"] });
    }
});
const sdkRetimeReadTargetSchema = sdkTimelineClipSnapshotObjectSchema.extend({
    id: sdkTimelineItemIdSchema,
    sourceRange: sdkSourceRangeSchema,
    linkedItemIds: z.array(sdkTimelineItemIdSchema).max(256),
    trackType: z.enum(["video", "audio"]),
    trackIndex: z.number().int().min(1).max(4096),
}).strict();
const sdkRetimeReadPointSchema = z.object({
    recordFrame: z.number().int().safe(),
    recordPositionFrames: z.number().finite().min(-1e15).max(1e15),
    sourceFrame: z.number().finite().nonnegative().max(1e15),
    incomingControl: z.object({
        recordPositionFrames: z.number().finite().min(-1e15).max(1e15),
        sourceFrame: z.number().finite().nonnegative().max(1e15),
    }).strict(),
    outgoingControl: z.object({
        recordPositionFrames: z.number().finite().min(-1e15).max(1e15),
        sourceFrame: z.number().finite().nonnegative().max(1e15),
    }).strict(),
    speed: z.number().finite().min(-1000).max(1000),
    interpolation: z.enum(["linear", "bezier", "hold"]),
}).strict();
export const sdkRetimeReadbackSchema = z.object({
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    timelineRevision: sdkRevisionSchema,
    timelineItemId: sdkTimelineItemIdSchema,
    durationFrames: z.number().int().safe().positive(),
    speedMultiplier: z.number().finite().nonnegative().max(1000),
    reversed: z.boolean(),
    frozen: z.boolean(),
    points: z.array(sdkRetimeReadPointSchema).min(1).max(4096),
}).strict();
export const sdkTimelineTrackSnapshotSchema = z.object({
    snapshotId: sdkSnapshotTrackIdSchema,
    timelineId: sdkTimelineIdSchema,
    snapshotRevision: sdkRevisionSchema,
    type: sdkTrackTypeSchema,
    index: z.number().int().min(1).max(4096),
    name: z.string().max(4096),
    enabled: z.boolean().nullable(),
    locked: z.boolean().nullable(),
    clips: z.array(sdkTimelineClipSnapshotSchema).max(100_000),
}).strict();
export const sdkTimelineMarkerSnapshotSchema = z.object({
    id: sdkMarkerIdSchema,
    snapshotRevision: sdkRevisionSchema,
    position: sdkTimelineRecordTimeSchema,
    color: z.string().min(1).max(64),
    name: z.string().max(4096),
    note: z.string().max(65_536),
    duration: sdkFrameDurationSchema.refine((value) => value.value.value > 0, "Marker duration must be positive"),
}).strict();
const sdkFairlightNumericReadbackSchema = z.discriminatedUnion("status", [
    z.object({ status: z.literal("available"), value: z.number().finite() }).strict(),
    z.object({ status: z.literal("unavailable"), reason: z.enum(["readback_unavailable", "not_exposed_by_runtime"]) }).strict(),
]);
const sdkFairlightSnapshotStateSchema = z.discriminatedUnion("status", [
    z.object({
        status: z.literal("available"),
        tracks: z.array(z.object({
            trackIndex: z.number().int().min(1).max(4096),
            levelDb: sdkFairlightNumericReadbackSchema,
            pan: sdkFairlightNumericReadbackSchema,
        }).strict()).max(4096).refine((tracks) => new Set(tracks.map((track) => track.trackIndex)).size === tracks.length, "Fairlight track readback indexes must be unique"),
        clips: z.array(z.object({
            clipId: sdkTimelineItemIdSchema,
            trackIndex: z.number().int().min(1).max(4096),
            gainDb: sdkFairlightNumericReadbackSchema,
            pan: sdkFairlightNumericReadbackSchema,
            fadeInFrames: sdkFairlightNumericReadbackSchema,
            fadeOutFrames: sdkFairlightNumericReadbackSchema,
        }).strict()).max(100_000).refine((clips) => new Set(clips.map((clip) => clip.clipId)).size === clips.length, "Fairlight clip readback identities must be unique").default([]),
        buses: z.discriminatedUnion("status", [
            z.object({
                status: z.literal("available"),
                buses: z.array(z.object({ name: z.string().min(1).max(256), kind: z.enum(["main", "bus"]) }).strict()).max(4096).refine((buses) => new Set(buses.map((bus) => `${bus.kind}:${bus.name}`)).size === buses.length, "Fairlight bus identities must be unique"),
            }).strict(),
            z.object({ status: z.literal("unavailable"), reason: z.enum(["readback_unavailable", "not_exposed_by_runtime"]), buses: z.tuple([]) }).strict(),
        ]),
    }).strict(),
    z.object({
        status: z.literal("unavailable"),
        reason: z.enum(["readback_unavailable", "not_exposed_by_runtime"]),
        tracks: z.tuple([]),
        buses: z.object({ status: z.literal("unavailable"), reason: z.enum(["readback_unavailable", "not_exposed_by_runtime"]), buses: z.tuple([]) }).strict(),
    }).strict(),
]);
export const sdkTimelineSnapshotSchema = z.object({
    project: sdkProjectReferenceSchema,
    timeline: sdkTimelineReferenceSchema,
    revision: sdkRevisionSchema,
    frameRate: sdkFrameRateSchema,
    start: sdkTimelineRecordTimeSchema,
    tracks: z.array(sdkTimelineTrackSnapshotSchema).max(12_288),
    markers: z.array(sdkTimelineMarkerSnapshotSchema).max(100_000),
    fairlight: sdkFairlightSnapshotStateSchema.default({
        status: "unavailable",
        reason: "not_exposed_by_runtime",
        tracks: [],
        buses: { status: "unavailable", reason: "not_exposed_by_runtime", buses: [] },
    }),
}).strict().superRefine((snapshot, context) => {
    if (snapshot.timeline.projectId !== snapshot.project.id) {
        context.addIssue({ code: "custom", path: ["timeline", "projectId"], message: "Timeline project identity does not match snapshot project" });
    }
    const trackIds = new Set();
    const trackCoordinates = new Set();
    const clipIds = new Set();
    const snapshotClipIds = new Set();
    const markerIds = new Set();
    const markerFrames = new Set();
    if (snapshot.fairlight.status === "available") {
        const audioTrackIndexes = snapshot.tracks.filter((track) => track.type === "audio").map((track) => track.index).sort((left, right) => left - right);
        const fairlightTrackIndexes = snapshot.fairlight.tracks.map((track) => track.trackIndex).sort((left, right) => left - right);
        if (JSON.stringify(audioTrackIndexes) !== JSON.stringify(fairlightTrackIndexes)) {
            context.addIssue({ code: "custom", path: ["fairlight", "tracks"], message: "Fairlight readback must cover the exact audio tracks in this snapshot" });
        }
        const audioClipTracks = new Map(snapshot.tracks.filter((track) => track.type === "audio")
            .flatMap((track) => track.clips.flatMap((clip) => clip.id === null ? [] : [[clip.id, track.index]])));
        for (let offset = 0; offset < snapshot.fairlight.clips.length; offset += 1) {
            const clip = snapshot.fairlight.clips[offset];
            if (!clip || audioClipTracks.get(clip.clipId) !== clip.trackIndex) {
                context.addIssue({ code: "custom", path: ["fairlight", "clips", offset], message: "Fairlight clip readback must bind one exact audio clip and track in this snapshot" });
            }
        }
    }
    for (let markerOffset = 0; markerOffset < snapshot.markers.length; markerOffset += 1) {
        const marker = snapshot.markers[markerOffset];
        if (!marker)
            continue;
        if (marker.snapshotRevision !== snapshot.revision) {
            context.addIssue({ code: "custom", path: ["markers", markerOffset, "snapshotRevision"], message: "Marker reference is not bound to this snapshot" });
        }
        if (markerIds.has(marker.id) || markerFrames.has(marker.position.value.value)) {
            context.addIssue({ code: "custom", path: ["markers", markerOffset], message: "Marker identity and record position must be unique" });
        }
        markerIds.add(marker.id);
        markerFrames.add(marker.position.value.value);
    }
    for (let trackOffset = 0; trackOffset < snapshot.tracks.length; trackOffset += 1) {
        const track = snapshot.tracks[trackOffset];
        if (!track)
            continue;
        if (track.timelineId !== snapshot.timeline.id || track.snapshotRevision !== snapshot.revision) {
            context.addIssue({ code: "custom", path: ["tracks", trackOffset], message: "Track reference is not bound to this snapshot" });
        }
        if (trackIds.has(track.snapshotId)) {
            context.addIssue({ code: "custom", path: ["tracks", trackOffset, "snapshotId"], message: "Snapshot track identity must be unique" });
        }
        trackIds.add(track.snapshotId);
        const coordinate = `${track.type}:${track.index}`;
        if (trackCoordinates.has(coordinate)) {
            context.addIssue({ code: "custom", path: ["tracks", trackOffset, "index"], message: "Track type and index must be unique" });
        }
        trackCoordinates.add(coordinate);
        for (let clipOffset = 0; clipOffset < track.clips.length; clipOffset += 1) {
            const clip = track.clips[clipOffset];
            if (!clip)
                continue;
            if (clip.snapshotTrackId !== track.snapshotId || clip.snapshotRevision !== snapshot.revision) {
                context.addIssue({ code: "custom", path: ["tracks", trackOffset, "clips", clipOffset], message: "Clip reference is not bound to this track and snapshot" });
            }
            if (clip.id !== null && clipIds.has(clip.id)) {
                context.addIssue({ code: "custom", path: ["tracks", trackOffset, "clips", clipOffset, "id"], message: "Durable clip identity must be unique within its timeline" });
            }
            if (clip.id !== null)
                clipIds.add(clip.id);
            if (clip.id !== null && clip.linkedItemIds?.includes(clip.id)) {
                context.addIssue({ code: "custom", path: ["tracks", trackOffset, "clips", clipOffset, "linkedItemIds"], message: "A clip cannot link to itself" });
            }
            if (clip.linkedItemIds !== null && new Set(clip.linkedItemIds).size !== clip.linkedItemIds.length) {
                context.addIssue({ code: "custom", path: ["tracks", trackOffset, "clips", clipOffset, "linkedItemIds"], message: "Linked clip identities must be unique" });
            }
            if (snapshotClipIds.has(clip.snapshotId)) {
                context.addIssue({ code: "custom", path: ["tracks", trackOffset, "clips", clipOffset, "snapshotId"], message: "Snapshot clip identity must be unique within its snapshot" });
            }
            snapshotClipIds.add(clip.snapshotId);
        }
    }
    for (let trackOffset = 0; trackOffset < snapshot.tracks.length; trackOffset += 1) {
        const track = snapshot.tracks[trackOffset];
        if (!track)
            continue;
        for (let clipOffset = 0; clipOffset < track.clips.length; clipOffset += 1) {
            const clip = track.clips[clipOffset];
            if (!clip || clip.linkedItemIds === null)
                continue;
            if (clip.id === null && clip.linkedItemIds.length > 0) {
                context.addIssue({ code: "custom", path: ["tracks", trackOffset, "clips", clipOffset, "linkedItemIds"], message: "Linked topology requires an authoritative timeline-item identity" });
            }
            for (const linkedId of clip.linkedItemIds) {
                if (!clipIds.has(linkedId)) {
                    context.addIssue({ code: "custom", path: ["tracks", trackOffset, "clips", clipOffset, "linkedItemIds"], message: "Linked clip identity is absent from this snapshot" });
                    continue;
                }
                const linkedClip = snapshot.tracks.flatMap((candidateTrack) => candidateTrack.clips).find((candidate) => candidate.id === linkedId);
                if (linkedClip?.linkedItemIds === null) {
                    context.addIssue({ code: "custom", path: ["tracks", trackOffset, "clips", clipOffset, "linkedItemIds"], message: "Linked clip topology must be readable on both sides" });
                }
                else if (!linkedClip?.linkedItemIds.includes(clip.id)) {
                    context.addIssue({ code: "custom", path: ["tracks", trackOffset, "clips", clipOffset, "linkedItemIds"], message: "Linked clip topology must be reciprocal" });
                }
            }
        }
    }
});
export const sdkMediaPoolAssetKindSchema = z.enum([
    "video",
    "audio",
    "still",
    "timeline",
    "multicam",
    "compound",
    "fusion_composition",
    "generator",
    "unknown",
]);
export const sdkMediaPoolMetadataKeySchema = z.enum([
    "description",
    "comments",
    "keywords",
    "shot",
    "scene",
    "take",
    "angle",
    "camera",
    "reel",
    "dateRecorded",
    "goodTake",
    "clipColor",
]);
export const sdkMediaPoolMetadataEntrySchema = z.object({
    key: sdkMediaPoolMetadataKeySchema,
    value: z.string().max(16_384),
}).strict();
export const sdkMediaPoolFolderSnapshotSchema = z.object({
    id: sdkMediaPoolFolderIdSchema.nullable(),
    snapshotId: sdkSnapshotMediaPoolFolderIdSchema,
    parentSnapshotId: sdkSnapshotMediaPoolFolderIdSchema.nullable(),
    snapshotRevision: sdkRevisionSchema,
    name: z.string().min(1).max(4096),
    depth: z.number().int().min(0).max(256),
}).strict();
export const sdkMediaPoolAssetSnapshotSchema = z.object({
    id: sdkMediaPoolItemIdSchema.nullable(),
    snapshotId: sdkSnapshotMediaPoolItemIdSchema,
    folderSnapshotId: sdkSnapshotMediaPoolFolderIdSchema,
    snapshotRevision: sdkRevisionSchema,
    name: z.string().min(1).max(4096),
    kind: sdkMediaPoolAssetKindSchema,
    selected: z.boolean(),
    sourceFileName: z.string().min(1).max(4096).refine((value) => value !== "." && value !== ".." && !value.includes("/") && !value.includes("\\"), "Media Pool source file name must be a basename").nullable(),
    duration: z.string().max(4096).nullable(),
    resolution: z.string().max(4096).nullable(),
    frameRate: z.string().max(256).nullable(),
    startTimecode: z.string().max(256).nullable(),
    metadata: z.array(sdkMediaPoolMetadataEntrySchema).max(12),
}).strict().superRefine((asset, context) => {
    const metadataKeys = new Set();
    for (let offset = 0; offset < asset.metadata.length; offset += 1) {
        const entry = asset.metadata[offset];
        if (!entry)
            continue;
        if (metadataKeys.has(entry.key)) {
            context.addIssue({ code: "custom", path: ["metadata", offset, "key"], message: "Media Pool metadata keys must be unique" });
        }
        metadataKeys.add(entry.key);
    }
});
function isWellFormedUnicode(value) {
    for (let offset = 0; offset < value.length; offset += 1) {
        const codeUnit = value.charCodeAt(offset);
        if (codeUnit >= 0xd800 && codeUnit <= 0xdbff) {
            const next = value.charCodeAt(offset + 1);
            if (!(next >= 0xdc00 && next <= 0xdfff))
                return false;
            offset += 1;
        }
        else if (codeUnit >= 0xdc00 && codeUnit <= 0xdfff) {
            return false;
        }
    }
    return true;
}
const utf16BoundedTextSchema = (maximumCodeUnits, field) => z.string().min(1).refine((value) => value.length <= maximumCodeUnits, `${field} must contain at most ${maximumCodeUnits} UTF-16 code units`);
export const sdkMediaPoolSearchSchema = z.object({
    query: z.string().min(1).refine(isWellFormedUnicode, "Media Pool search query must be well-formed Unicode").refine((query) => new TextEncoder().encode(query).byteLength <= 1024, "Media Pool search query must contain at most 1024 UTF-8 bytes").refine((query) => query.trim().length > 0, "Media Pool search query must contain visible text"),
    match: z.enum(["contains", "exact"]),
    fields: z.array(z.enum(["name", "metadata", "sourceFileName"])).min(1).max(3),
}).strict().refine((search) => new Set(search.fields).size === search.fields.length, {
    message: "Media Pool search fields must be unique",
    path: ["fields"],
});
export const sdkMediaPoolPageSchema = z.object({
    project: sdkProjectReferenceSchema,
    revision: sdkRevisionSchema,
    offset: z.number().int().min(0).max(1_000_000),
    pageSize: z.number().int().min(1).max(32),
    total: z.number().int().min(0).max(1_000_000),
    nextOffset: z.number().int().min(1).max(1_000_000).nullable(),
    search: sdkMediaPoolSearchSchema.nullable(),
    folders: z.array(sdkMediaPoolFolderSnapshotSchema).max(32),
    assets: z.array(sdkMediaPoolAssetSnapshotSchema).max(32),
}).strict().superRefine((page, context) => {
    if (new TextEncoder().encode(JSON.stringify(page)).byteLength > 7 * 1024 * 1024) {
        context.addIssue({ code: "custom", message: "Media Pool page exceeds the transport-safe byte limit" });
    }
    if (page.folders.length + page.assets.length > page.pageSize) {
        context.addIssue({ code: "custom", message: "Media Pool page exceeds its declared page size" });
    }
    if (page.offset + page.folders.length + page.assets.length > page.total) {
        context.addIssue({ code: "custom", message: "Media Pool page entries exceed the declared total" });
    }
    if (page.offset > page.total || (page.nextOffset !== null && (page.nextOffset <= page.offset || page.nextOffset > page.total))) {
        context.addIssue({ code: "custom", path: ["nextOffset"], message: "Media Pool pagination bounds are invalid" });
    }
    const endOffset = page.offset + page.folders.length + page.assets.length;
    if (page.nextOffset !== null && page.nextOffset !== endOffset) {
        context.addIssue({ code: "custom", path: ["nextOffset"], message: "Media Pool next offset must follow the final page entry" });
    }
    if (page.nextOffset !== null && endOffset >= page.total) {
        context.addIssue({ code: "custom", path: ["nextOffset"], message: "A complete Media Pool page cannot declare a continuation" });
    }
    if (page.nextOffset === null && endOffset !== page.total) {
        context.addIssue({ code: "custom", path: ["nextOffset"], message: "A final Media Pool page must reach the declared total" });
    }
    const identities = new Set();
    const durableIdentities = new Set();
    if (page.search !== null && page.folders.length > 0) {
        context.addIssue({ code: "custom", path: ["folders"], message: "Media Pool search pages cannot contain folders" });
    }
    for (const entry of [...page.folders, ...page.assets]) {
        if (entry.snapshotRevision !== page.revision) {
            context.addIssue({ code: "custom", message: "Media Pool entry is not bound to this snapshot revision" });
        }
        if (identities.has(entry.snapshotId)) {
            context.addIssue({ code: "custom", message: "Media Pool snapshot identities must be unique within a page" });
        }
        identities.add(entry.snapshotId);
        if (entry.id !== null && durableIdentities.has(entry.id)) {
            context.addIssue({ code: "custom", message: "Media Pool durable identities must be unique within a page" });
        }
        if (entry.id !== null)
            durableIdentities.add(entry.id);
    }
    if (page.search !== null) {
        const foldedQuery = page.search.query.toLowerCase();
        for (let offset = 0; offset < page.assets.length; offset += 1) {
            const asset = page.assets[offset];
            if (!asset)
                continue;
            const candidates = page.search.fields.flatMap((field) => {
                if (field === "name")
                    return [asset.name];
                if (field === "sourceFileName")
                    return [asset.sourceFileName ?? ""];
                return asset.metadata.map((entry) => entry.value);
            });
            const matches = candidates.some((candidate) => page.search?.match === "exact"
                ? candidate.toLowerCase() === foldedQuery
                : candidate.toLowerCase().includes(foldedQuery));
            if (!matches) {
                context.addIssue({ code: "custom", path: ["assets", offset], message: "Media Pool asset does not match the declared search" });
            }
        }
    }
});
const sdkColorReadCapabilitySchema = z.discriminatedUnion("status", [
    z.object({ status: z.literal("supported") }).strict(),
    z.object({
        status: z.literal("unavailable"),
        reason: z.literal("not_exposed_by_runtime"),
    }).strict(),
]);
const sdkColorMutationCapabilitySchema = z.object({
    status: z.literal("runtime_check_required"),
    edition: z.enum(["studio_or_free", "studio_required"]),
    projectStorage: z.enum(["disk_required", "any"]),
    plugin: z.enum(["not_required", "installed_effect_required"]),
}).strict();
const sdkColorNodeSnapshotSchema = z.object({
    index: z.number().int().min(1).max(4096),
    label: z.string().max(4096).nullable(),
    enabled: z.boolean().nullable(),
    lut: z.object({
        applied: z.boolean(),
        displayName: z.string().min(1).max(1024).nullable(),
    }).strict(),
    effects: z.array(z.string().min(1).max(512)).max(256),
}).strict();
const sdkColorTargetClipSnapshotSchema = sdkTimelineClipSnapshotObjectSchema.extend({
    id: sdkTimelineItemIdSchema,
}).refine((clip) => clip.duration.value.value === clip.recordRange.endExclusive - clip.recordRange.start, {
    message: "Clip duration must equal its record range length",
    path: ["duration"],
});
/** Sanitized immutable Color readback for the exact current video target. */
export const sdkColorTargetSnapshotSchema = z.object({
    project: sdkProjectReferenceSchema,
    timeline: sdkTimelineReferenceSchema,
    revision: sdkRevisionSchema,
    timelineRevision: sdkRevisionSchema,
    nodeStackLayerIndex: z.number().int().min(1).max(4096),
    frameRate: sdkFrameRateSchema,
    track: z.object({
        snapshotId: sdkSnapshotTrackIdSchema,
        index: z.number().int().min(1).max(4096),
        name: z.string().max(4096),
    }).strict(),
    clip: sdkColorTargetClipSnapshotSchema,
    capabilities: z.object({
        nodeGraph: sdkColorReadCapabilitySchema,
        labels: sdkColorReadCapabilitySchema,
        enabledState: sdkColorReadCapabilitySchema,
        luts: sdkColorReadCapabilitySchema,
        effects: sdkColorReadCapabilitySchema,
        versions: sdkColorReadCapabilitySchema,
        colorGroup: sdkColorReadCapabilitySchema,
    }).strict(),
    mutationCapabilities: z.object({
        primary: sdkColorMutationCapabilitySchema,
        nodes: sdkColorMutationCapabilitySchema,
        lutAssets: sdkColorMutationCapabilitySchema,
        drxAssets: sdkColorMutationCapabilitySchema,
        effects: sdkColorMutationCapabilitySchema,
    }).strict().default({
        primary: { status: "runtime_check_required", edition: "studio_or_free", projectStorage: "disk_required", plugin: "not_required" },
        nodes: { status: "runtime_check_required", edition: "studio_or_free", projectStorage: "disk_required", plugin: "not_required" },
        lutAssets: { status: "runtime_check_required", edition: "studio_or_free", projectStorage: "any", plugin: "not_required" },
        drxAssets: { status: "runtime_check_required", edition: "studio_or_free", projectStorage: "disk_required", plugin: "not_required" },
        effects: { status: "runtime_check_required", edition: "studio_or_free", projectStorage: "disk_required", plugin: "installed_effect_required" },
    }),
    nodeGraph: z.object({
        nodeCount: z.number().int().min(0).max(4096),
        nodes: z.array(sdkColorNodeSnapshotSchema).max(4096),
    }).strict().refine((graph) => graph.nodeCount === graph.nodes.length, {
        message: "Color node count must equal the ordered node snapshot length",
    }),
    versions: z.object({
        current: z.string().min(1).max(1024).nullable(),
        local: z.array(z.string().min(1).max(1024)).max(4096),
        remote: z.array(z.string().min(1).max(1024)).max(4096),
    }).strict(),
    colorGroup: z.string().min(1).max(1024).nullable(),
}).strict().superRefine((snapshot, context) => {
    if (snapshot.timeline.projectId !== snapshot.project.id) {
        context.addIssue({ code: "custom", path: ["timeline", "projectId"], message: "Color target project identity does not match" });
    }
    if (snapshot.clip.snapshotRevision !== snapshot.timelineRevision
        || snapshot.clip.snapshotTrackId !== snapshot.track.snapshotId) {
        context.addIssue({ code: "custom", path: ["clip"], message: "Color target is not bound to its timeline revision and track" });
    }
    for (let offset = 0; offset < snapshot.nodeGraph.nodes.length; offset += 1) {
        if (snapshot.nodeGraph.nodes[offset]?.index !== offset + 1) {
            context.addIssue({ code: "custom", path: ["nodeGraph", "nodes", offset, "index"], message: "Color nodes must preserve one-based graph order" });
        }
    }
    const unavailable = (capability) => capability.status === "unavailable";
    if (unavailable(snapshot.capabilities.nodeGraph) && snapshot.nodeGraph.nodeCount !== 0) {
        context.addIssue({ code: "custom", path: ["nodeGraph"], message: "Unavailable Color node graph must not contain node metadata" });
    }
    for (let offset = 0; offset < snapshot.nodeGraph.nodes.length; offset += 1) {
        const node = snapshot.nodeGraph.nodes[offset];
        if (!node)
            continue;
        if (unavailable(snapshot.capabilities.labels) && node.label !== null) {
            context.addIssue({ code: "custom", path: ["nodeGraph", "nodes", offset, "label"], message: "Unavailable Color labels must remain null" });
        }
        if (unavailable(snapshot.capabilities.enabledState) && node.enabled !== null) {
            context.addIssue({ code: "custom", path: ["nodeGraph", "nodes", offset, "enabled"], message: "Unavailable Color enabled state must remain null" });
        }
        if ((node.lut.applied && node.lut.displayName === null) || (!node.lut.applied && node.lut.displayName !== null)) {
            context.addIssue({ code: "custom", path: ["nodeGraph", "nodes", offset, "lut"], message: "Color LUT application and display name must agree" });
        }
        if (unavailable(snapshot.capabilities.luts) && (node.lut.applied || node.lut.displayName !== null)) {
            context.addIssue({ code: "custom", path: ["nodeGraph", "nodes", offset, "lut"], message: "Unavailable Color LUT metadata must remain empty" });
        }
        if (unavailable(snapshot.capabilities.effects) && node.effects.length !== 0) {
            context.addIssue({ code: "custom", path: ["nodeGraph", "nodes", offset, "effects"], message: "Unavailable Color effect metadata must remain empty" });
        }
    }
    if (unavailable(snapshot.capabilities.versions) && (snapshot.versions.current !== null || snapshot.versions.local.length !== 0 || snapshot.versions.remote.length !== 0)) {
        context.addIssue({ code: "custom", path: ["versions"], message: "Unavailable Color version metadata must remain empty" });
    }
    if (unavailable(snapshot.capabilities.colorGroup) && snapshot.colorGroup !== null) {
        context.addIssue({ code: "custom", path: ["colorGroup"], message: "Unavailable Color group metadata must remain null" });
    }
});
const sdkRenderKnownFormatSchema = z.enum(["quicktime", "mp4", "mxf", "wave", "aiff", "dcp", "image_sequence"]);
const sdkRenderKnownCodecSchema = z.enum([
    "h264", "h265", "prores", "dnxhr", "av1", "linear_pcm", "aac", "flac", "exr", "dpx", "tiff", "jpeg",
]);
const sdkRenderVersionedFormatSchema = z.discriminatedUnion("kind", [
    z.object({ kind: z.literal("known"), value: sdkRenderKnownFormatSchema }).strict(),
    z.object({ kind: z.literal("unknown_version"), label: z.string().min(1).max(256) }).strict(),
]);
const sdkRenderVersionedCodecSchema = z.discriminatedUnion("kind", [
    z.object({ kind: z.literal("known"), value: sdkRenderKnownCodecSchema }).strict(),
    z.object({ kind: z.literal("unknown_version"), label: z.string().min(1).max(256) }).strict(),
]);
const sdkRenderSupportSchema = z.discriminatedUnion("availability", [
    z.object({ availability: z.literal("supported") }).strict(),
    z.object({
        availability: z.literal("unavailable"),
        reason: z.enum(["api_unavailable", "edition_unavailable", "temporarily_unavailable"]),
    }).strict(),
    z.object({ availability: z.literal("unknown_version"), reason: z.literal("unrecognized_response") }).strict(),
]);
const sdkRenderResolutionSchema = z.object({
    width: z.number().int().positive().max(65_536),
    height: z.number().int().positive().max(65_536),
}).strict();
const sdkRenderCodecSchema = z.object({
    codec: sdkRenderVersionedCodecSchema,
    label: z.string().min(1).max(256),
    resolutions: z.array(sdkRenderResolutionSchema).max(512),
    resolutionSupport: sdkRenderSupportSchema,
}).strict();
const sdkRenderFormatSchema = z.object({
    format: sdkRenderVersionedFormatSchema,
    label: z.string().min(1).max(256),
    extension: z.string().min(1).max(32).regex(/^[A-Za-z0-9._-]+$/).nullable(),
    codecs: z.array(sdkRenderCodecSchema).max(256),
    codecSupport: sdkRenderSupportSchema,
}).strict();
export const sdkRenderDiscoverySchema = z.object({
    projectId: sdkProjectIdSchema,
    formatSupport: sdkRenderSupportSchema,
    formats: z.array(sdkRenderFormatSchema).max(256),
}).strict();
export const sdkRenderPresetsSchema = z.object({
    projectId: sdkProjectIdSchema,
    support: sdkRenderSupportSchema,
    presets: z.array(z.object({ name: z.string().min(1).max(1024) }).strict()).max(2048),
}).strict();
const sdkRenderModeSchema = z.discriminatedUnion("kind", [
    z.object({ kind: z.literal("known"), value: z.enum(["individual_clips", "single_clip"]) }).strict(),
    z.object({ kind: z.literal("unknown_version"), value: z.string().min(1).max(128) }).strict(),
]);
const sdkRenderRangeSchema = z.discriminatedUnion("kind", [
    z.object({ kind: z.literal("full_timeline") }).strict(),
    z.object({
        kind: z.literal("custom"),
        markInFrame: z.number().int(),
        markOutFrame: z.number().int(),
    }).strict().refine((value) => value.markOutFrame >= value.markInFrame, "Render range end must not precede its start"),
    z.object({ kind: z.literal("unknown") }).strict(),
]);
export const sdkRenderSettingsSnapshotSchema = z.object({
    projectId: sdkProjectIdSchema,
    revision: sdkRevisionSchema,
    support: sdkRenderSupportSchema,
    format: sdkRenderVersionedFormatSchema.nullable(),
    codec: sdkRenderVersionedCodecSchema.nullable(),
    resolution: sdkRenderResolutionSchema.nullable(),
    frameRate: z.number().positive().max(1000).nullable(),
    mode: sdkRenderModeSchema.nullable(),
    range: sdkRenderRangeSchema,
    exportVideo: z.boolean().nullable(),
    exportAudio: z.boolean().nullable(),
    exportSubtitles: z.boolean().nullable(),
    customName: z.string().min(1).max(1024).nullable(),
    queueCount: z.number().int().nonnegative().max(10_000),
}).strict();
export const sdkArtifactContentChunkSchema = z.object({
    artifactId: sdkArtifactIdSchema,
    offset: z.number().int().safe().nonnegative(),
    totalSize: z.number().int().safe().positive(),
    bytesBase64: z.string().max(1_398_104).regex(/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/),
    eof: z.boolean(),
    sha256: z.string().regex(/^sha256:[a-f0-9]{64}$/),
    availableUntil: z.string().datetime({ offset: true }),
}).strict().superRefine((chunk, context) => {
    const padding = chunk.bytesBase64.endsWith("==") ? 2 : chunk.bytesBase64.endsWith("=") ? 1 : 0;
    const byteLength = (chunk.bytesBase64.length / 4) * 3 - padding;
    if (chunk.offset + byteLength > chunk.totalSize || chunk.eof !== (chunk.offset + byteLength === chunk.totalSize)) {
        context.addIssue({ code: "custom", path: ["bytesBase64"], message: "Artifact chunk coordinates are inconsistent" });
    }
});
export const sdkFusionSettingIngressSchema = z.object({
    bytesBase64: z.string().min(4).max(5_592_408).regex(/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/),
}).strict().superRefine((value, context) => {
    const padding = value.bytesBase64.endsWith("==") ? 2 : value.bytesBase64.endsWith("=") ? 1 : 0;
    const byteLength = (value.bytesBase64.length / 4) * 3 - padding;
    if (byteLength < 1 || byteLength > 4 * 1024 * 1024) {
        context.addIssue({ code: "custom", path: ["bytesBase64"], message: "Fusion setting input must contain 1 through 4194304 bytes" });
    }
});
export const sdkFusionSettingArtifactReceiptSchema = z.object({
    artifactId: sdkArtifactIdSchema,
    mediaType: z.literal("application/x-fusion-setting"),
    byteCount: z.number().int().safe().positive().max(4 * 1024 * 1024),
    sha256: z.string().regex(/^sha256:[a-f0-9]{64}$/),
}).strict();
const sdkRenderJobStatusSchema = z.discriminatedUnion("kind", [
    z.object({ kind: z.literal("known"), value: z.enum(["queued", "rendering", "completed", "failed", "cancelled"]) }).strict(),
    z.object({ kind: z.literal("unknown_version"), value: z.string().min(1).max(128) }).strict(),
]);
export const sdkRenderJobSnapshotSchema = z.object({
    id: sdkSnapshotRenderJobIdSchema,
    projectId: sdkProjectIdSchema,
    queueRevision: sdkRevisionSchema,
    index: z.number().int().min(1).max(10_000),
    name: z.string().min(1).max(1024).refine((value) => !/[\\/]/.test(value) && !/^[A-Za-z]:/.test(value) && !/^file:/i.test(value), "Render job name must not contain a filesystem path"),
    statusSupport: sdkRenderSupportSchema,
    status: sdkRenderJobStatusSchema,
    progressPercent: z.number().min(0).max(100).nullable(),
}).strict();
export const sdkRenderQueuePageSchema = z.object({
    projectId: sdkProjectIdSchema,
    queueRevision: sdkRevisionSchema,
    support: sdkRenderSupportSchema,
    cursor: sdkRenderQueueCursorSchema.nullable(),
    offset: z.number().int().min(0).max(10_000),
    pageSize: z.number().int().min(1).max(100),
    jobs: z.array(sdkRenderJobSnapshotSchema).max(100),
    nextCursor: sdkRenderQueueCursorSchema.nullable(),
    total: z.number().int().nonnegative().max(10_000),
}).strict().superRefine((page, context) => {
    if (page.jobs.length > page.pageSize || page.offset > page.total || page.offset + page.jobs.length > page.total) {
        context.addIssue({ code: "custom", path: ["jobs"], message: "Render queue page coordinates are invalid" });
    }
    if (page.cursor === null && page.offset !== 0) {
        context.addIssue({ code: "custom", path: ["offset"], message: "The initial Render queue page must start at offset zero" });
    }
    if (page.support.availability !== "supported" && (page.jobs.length > 0 || page.total > 0 || page.nextCursor !== null)) {
        context.addIssue({ code: "custom", path: ["support"], message: "An unavailable Render queue cannot expose jobs" });
    }
    const identities = new Set();
    for (let index = 0; index < page.jobs.length; index += 1) {
        const job = page.jobs[index];
        if (job && (job.projectId !== page.projectId || job.queueRevision !== page.queueRevision)) {
            context.addIssue({ code: "custom", path: ["jobs", index], message: "Render job is not bound to this queue page" });
        }
        if (job && job.index !== page.offset + index + 1) {
            context.addIssue({ code: "custom", path: ["jobs", index, "index"], message: "Render job index does not match its queue page coordinate" });
        }
        if (job && identities.has(job.id)) {
            context.addIssue({ code: "custom", path: ["jobs", index, "id"], message: "Render job identities must be unique within a page" });
        }
        if (job)
            identities.add(job.id);
    }
    const endOffset = page.offset + page.jobs.length;
    if (endOffset < page.total && page.jobs.length === 0) {
        context.addIssue({ code: "custom", path: ["jobs"], message: "An incomplete Render queue page must make progress" });
    }
    if (page.nextCursor !== null && page.nextCursor === page.cursor) {
        context.addIssue({ code: "custom", path: ["nextCursor"], message: "A Render queue continuation must advance the cursor" });
    }
    if ((endOffset < page.total) !== (page.nextCursor !== null)) {
        context.addIssue({ code: "custom", path: ["nextCursor"], message: "Render queue continuation does not match the page boundary" });
    }
});
export const sdkRenderJobStatusSnapshotSchema = z.object({
    projectId: sdkProjectIdSchema,
    queueRevision: sdkRevisionSchema,
    support: sdkRenderSupportSchema,
    job: sdkRenderJobSnapshotSchema,
}).strict().superRefine((snapshot, context) => {
    if (snapshot.job.projectId !== snapshot.projectId || snapshot.job.queueRevision !== snapshot.queueRevision) {
        context.addIssue({ code: "custom", path: ["job"], message: "Render job status is not bound to this queue snapshot" });
    }
});
const sdkRuntimeReadDeadlineSchema = z.number().int().safe().positive()
    .refine((value) => value > Date.now(), "SDK read deadline has already elapsed")
    .refine((value) => value <= Date.now() + CUTAGENT_SDK_MAX_CONTROL_TIMEOUT_MS, "SDK read deadline exceeds the maximum control timeout window");
export const sdkVoiceCatalogRequestSchema = z.object({
    search: z.string().min(1).max(200).nullable(),
    pageToken: z.string().min(1).max(1000).nullable(),
    limit: z.number().int().min(1).max(100),
}).strict();
export const sdkVoiceCatalogPageSchema = z.object({
    voices: z.array(z.object({
        voiceId: z.string().min(1).max(256),
        name: z.string().min(1).max(500),
        description: z.string().max(1000).nullable(),
        language: z.string().max(100).nullable(),
        accent: z.string().max(100).nullable(),
    }).strict()).max(100),
    hasMore: z.boolean(),
    nextPageToken: z.string().min(1).max(1000).nullable(),
}).strict();
export const sdkManagedTimelinePreviewRequestSchema = z.object({
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    revision: sdkRevisionSchema,
    ownershipId: sdkManagedWorkflowClaimSchema.shape.ownershipId,
    scope: sdkManagedWorkflowClaimSchema.shape.scope,
    timelineFrameRate: sdkManagedWorkflowClaimSchema.shape.timelineFrameRate,
    elements: sdkManagedWorkflowClaimSchema.shape.elements,
}).strict();
export const sdkManagedTimelineExportSelectionSchema = z.discriminatedUnion("kind", [
    z.object({ kind: z.literal("existing_ownership") }).strict(),
    z.object({
        kind: z.literal("adopt"),
        clips: z.array(z.object({
            key: z.string().regex(/^[a-z][a-z0-9_-]{0,63}$/),
            timelineItemId: sdkTimelineItemIdSchema,
        }).strict()).min(1).max(32),
    }).strict(),
]);
export const sdkManagedTimelineExportRequestSchema = z.object({
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    revision: sdkRevisionSchema,
    ownershipId: sdkManagedWorkflowClaimSchema.shape.ownershipId,
    scope: sdkManagedWorkflowClaimSchema.shape.scope,
    selection: sdkManagedTimelineExportSelectionSchema,
}).strict();
const sdkManagedTimelineExportProgramSchema = sdkManagedTimelinePreviewRequestSchema.extend({
    elements: sdkManagedWorkflowClaimSchema.shape.elements.max(32),
}).strict();
export const sdkManagedTimelineDriftSchema = z.object({
    kind: z.enum(["create", "update", "remove", "preserve"]),
    key: z.string().min(1).max(200),
    timelineItemId: sdkTimelineItemIdSchema.optional(),
    summary: z.string().min(1).max(500),
}).strict();
export const sdkManagedTimelineBlockerSchema = z.object({
    code: z.enum(["stale_revision", "ambiguous_identity", "scope_crossing", "unsupported_change", "protected_state_unproven", "ownership_overlap"]),
    key: z.string().min(1).max(200).optional(),
    message: z.string().min(1).max(500),
}).strict();
export const sdkManagedTimelinePreviewSchema = z.object({
    status: z.enum(["no_change", "ready", "blocked"]),
    projectId: sdkProjectIdSchema,
    timelineId: sdkTimelineIdSchema,
    revision: sdkRevisionSchema,
    ownershipId: sdkManagedWorkflowClaimSchema.shape.ownershipId,
    scope: sdkManagedWorkflowClaimSchema.shape.scope,
    desiredStateDigest: z.string().regex(/^sha256:[a-f0-9]{64}$/),
    contextDigest: z.string().regex(/^sha256:[a-f0-9]{64}$/),
    protectedStateDigest: z.string().regex(/^sha256:[a-f0-9]{64}$/),
    previewDigest: z.string().regex(/^sha256:[a-f0-9]{64}$/),
    ownershipGeneration: z.number().int().nonnegative(),
    policyRevision: z.string().regex(/^policy_revision_[1-9][0-9]*$/),
    capabilityDigest: z.string().regex(/^sha256:[a-f0-9]{64}$/),
    drift: z.array(sdkManagedTimelineDriftSchema).max(100_000),
    blockers: z.array(sdkManagedTimelineBlockerSchema).max(100_000),
}).strict();
export const sdkManagedTimelineExportSchema = z.discriminatedUnion("status", [
    z.object({
        status: z.literal("ready"),
        dialect: z.literal("cutagent.managed-timeline"),
        version: z.literal(1),
        program: sdkManagedTimelineExportProgramSchema,
        assets: z.array(sdkMediaPoolAssetSnapshotSchema).max(32),
        coverage: z.object({
            represented: z.tuple([z.literal("clip_placement/v1")]),
            preservedButNotRepresented: z.tuple([
                z.literal("unmanaged_clips"), z.literal("track_properties"), z.literal("markers"),
                z.literal("fusion"), z.literal("color"), z.literal("fairlight"),
                z.literal("retime"), z.literal("transitions"), z.literal("effects"), z.literal("captions"),
            ]),
            protectedStateDigest: z.string().regex(/^sha256:[a-f0-9]{64}$/),
        }).strict(),
        blockers: z.tuple([]),
    }).strict(),
    z.object({
        status: z.literal("blocked"),
        dialect: z.literal("cutagent.managed-timeline"),
        version: z.literal(1),
        document: z.null(),
        blockers: z.array(sdkManagedTimelineBlockerSchema).min(1).max(100_000),
    }).strict(),
]);
export const sdkRuntimeReadRequestSchema = z.discriminatedUnion("operation", [
    z.object({
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
        requestId: sdkRequestIdSchema,
        sessionId: sdkSessionIdSchema,
        deadlineAtMs: sdkRuntimeReadDeadlineSchema,
        operation: z.literal("voice.catalog"),
        query: sdkVoiceCatalogRequestSchema,
    }).strict(),
    z.object({
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
        requestId: sdkRequestIdSchema,
        sessionId: sdkSessionIdSchema,
        deadlineAtMs: sdkRuntimeReadDeadlineSchema,
        operation: z.literal("project.context"),
    }).strict(),
    z.object({
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
        requestId: sdkRequestIdSchema,
        sessionId: sdkSessionIdSchema,
        deadlineAtMs: sdkRuntimeReadDeadlineSchema,
        operation: z.literal("project.current"),
    }).strict(),
    z.object({
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
        requestId: sdkRequestIdSchema,
        sessionId: sdkSessionIdSchema,
        deadlineAtMs: sdkRuntimeReadDeadlineSchema,
        operation: z.literal("timeline.current"),
        projectId: sdkProjectIdSchema,
    }).strict(),
    z.object({
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
        requestId: sdkRequestIdSchema,
        sessionId: sdkSessionIdSchema,
        deadlineAtMs: sdkRuntimeReadDeadlineSchema,
        operation: z.literal("timeline.snapshot"),
        projectId: sdkProjectIdSchema,
        timelineId: sdkTimelineIdSchema,
    }).strict(),
    z.object({
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
        requestId: sdkRequestIdSchema,
        sessionId: sdkSessionIdSchema,
        deadlineAtMs: sdkRuntimeReadDeadlineSchema,
        operation: z.literal("timeline.retime"),
        projectId: sdkProjectIdSchema,
        timelineId: sdkTimelineIdSchema,
        timelineRevision: sdkRevisionSchema,
        target: sdkRetimeReadTargetSchema,
    }).strict(),
    z.object({
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
        requestId: sdkRequestIdSchema,
        sessionId: sdkSessionIdSchema,
        deadlineAtMs: sdkRuntimeReadDeadlineSchema,
        operation: z.literal("timeline.managed.preview"),
        program: sdkManagedTimelinePreviewRequestSchema,
    }).strict(),
    z.object({
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
        requestId: sdkRequestIdSchema,
        sessionId: sdkSessionIdSchema,
        deadlineAtMs: sdkRuntimeReadDeadlineSchema,
        operation: z.literal("timeline.managed.export"),
        request: sdkManagedTimelineExportRequestSchema,
    }).strict(),
    z.object({
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
        requestId: sdkRequestIdSchema,
        sessionId: sdkSessionIdSchema,
        deadlineAtMs: sdkRuntimeReadDeadlineSchema,
        operation: z.literal("fusion.compositions"),
        projectId: sdkProjectIdSchema,
        timelineId: sdkTimelineIdSchema,
        timelineItemId: sdkTimelineItemIdSchema,
        expectedRevision: sdkRevisionSchema,
    }).strict(),
    z.object({
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
        requestId: sdkRequestIdSchema,
        sessionId: sdkSessionIdSchema,
        deadlineAtMs: sdkRuntimeReadDeadlineSchema,
        operation: z.literal("mediaPool.page"),
        projectId: sdkProjectIdSchema,
        offset: z.number().int().min(0).max(1_000_000),
        pageSize: z.number().int().min(1).max(32),
        expectedRevision: sdkRevisionSchema.nullable(),
        search: sdkMediaPoolSearchSchema.nullable(),
    }).strict(),
    z.object({
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
        requestId: sdkRequestIdSchema,
        sessionId: sdkSessionIdSchema,
        deadlineAtMs: sdkRuntimeReadDeadlineSchema,
        operation: z.literal("color.current"),
        projectId: sdkProjectIdSchema,
        timelineId: sdkTimelineIdSchema,
        nodeStackLayerIndex: z.number().int().min(1).max(4096),
    }).strict(),
    z.object({
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL), requestId: sdkRequestIdSchema, sessionId: sdkSessionIdSchema,
        deadlineAtMs: sdkRuntimeReadDeadlineSchema, operation: z.literal("render.discovery"), projectId: sdkProjectIdSchema,
    }).strict(),
    z.object({
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL), requestId: sdkRequestIdSchema, sessionId: sdkSessionIdSchema,
        deadlineAtMs: sdkRuntimeReadDeadlineSchema, operation: z.literal("render.presets"), projectId: sdkProjectIdSchema,
    }).strict(),
    z.object({
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL), requestId: sdkRequestIdSchema, sessionId: sdkSessionIdSchema,
        deadlineAtMs: sdkRuntimeReadDeadlineSchema, operation: z.literal("render.settings"), projectId: sdkProjectIdSchema,
    }).strict(),
    z.object({
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL), requestId: sdkRequestIdSchema, sessionId: sdkSessionIdSchema,
        deadlineAtMs: sdkRuntimeReadDeadlineSchema, operation: z.literal("render.queue"), projectId: sdkProjectIdSchema,
        pageSize: z.number().int().min(1).max(100), cursor: sdkRenderQueueCursorSchema.nullable(),
    }).strict(),
    z.object({
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL), requestId: sdkRequestIdSchema, sessionId: sdkSessionIdSchema,
        deadlineAtMs: sdkRuntimeReadDeadlineSchema, operation: z.literal("render.job_status"), projectId: sdkProjectIdSchema,
        queueRevision: sdkRevisionSchema, jobId: sdkSnapshotRenderJobIdSchema,
    }).strict(),
    z.object({
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL), requestId: sdkRequestIdSchema, sessionId: sdkSessionIdSchema,
        deadlineAtMs: sdkRuntimeReadDeadlineSchema, operation: z.literal("artifact.content"), artifactId: sdkArtifactIdSchema,
        offset: z.number().int().safe().nonnegative(), length: z.number().int().min(1).max(1024 * 1024),
    }).strict(),
    z.object({
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL), requestId: sdkRequestIdSchema, sessionId: sdkSessionIdSchema,
        deadlineAtMs: sdkRuntimeReadDeadlineSchema, operation: z.literal("artifact.fusion_setting.publish"),
        setting: sdkFusionSettingIngressSchema,
    }).strict(),
    z.object({
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
        requestId: sdkRequestIdSchema,
        sessionId: sdkSessionIdSchema,
        deadlineAtMs: sdkRuntimeReadDeadlineSchema,
        operation: z.literal("timeline.edit.preview"),
        intent: sdkTimelineEditIntentSchema,
    }).strict(),
    z.object({
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
        requestId: sdkRequestIdSchema,
        sessionId: sdkSessionIdSchema,
        deadlineAtMs: sdkRuntimeReadDeadlineSchema,
        operation: z.literal("multicam.inspect"),
        projectId: sdkProjectIdSchema,
        mediaPoolItemId: sdkMediaPoolItemIdSchema,
        multicamName: utf16BoundedTextSchema(1024, "Multicam name"),
        expectedRevision: sdkRevisionSchema.nullable(),
    }).strict(),
]);
export const sdkRuntimeReadSuccessSchema = z.discriminatedUnion("operation", [
    z.object({
        ok: z.literal(true),
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
        requestId: sdkRequestIdSchema,
        operation: z.literal("voice.catalog"),
        data: sdkVoiceCatalogPageSchema,
    }).strict(),
    z.object({
        ok: z.literal(true),
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
        requestId: sdkRequestIdSchema,
        operation: z.literal("project.context"),
        data: sdkProjectContextObservationSchema,
    }).strict(),
    z.object({
        ok: z.literal(true),
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
        requestId: sdkRequestIdSchema,
        operation: z.literal("project.current"),
        data: sdkProjectReferenceSchema,
    }).strict(),
    z.object({
        ok: z.literal(true),
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
        requestId: sdkRequestIdSchema,
        operation: z.literal("timeline.current"),
        data: sdkTimelineReferenceSchema,
    }).strict(),
    z.object({
        ok: z.literal(true),
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
        requestId: sdkRequestIdSchema,
        operation: z.literal("timeline.snapshot"),
        data: sdkTimelineSnapshotSchema,
    }).strict(),
    z.object({
        ok: z.literal(true),
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
        requestId: sdkRequestIdSchema,
        operation: z.literal("timeline.retime"),
        data: sdkRetimeReadbackSchema,
    }).strict(),
    z.object({
        ok: z.literal(true),
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
        requestId: sdkRequestIdSchema,
        operation: z.literal("fusion.compositions"),
        data: z.array(sdkFusionCompositionReferenceSchema).max(128),
    }).strict(),
    z.object({
        ok: z.literal(true),
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
        requestId: sdkRequestIdSchema,
        operation: z.literal("mediaPool.page"),
        data: sdkMediaPoolPageSchema,
    }).strict(),
    z.object({
        ok: z.literal(true),
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
        requestId: sdkRequestIdSchema,
        operation: z.literal("color.current"),
        data: sdkColorTargetSnapshotSchema,
    }).strict(),
    z.object({ ok: z.literal(true), protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL), requestId: sdkRequestIdSchema, operation: z.literal("render.discovery"), data: sdkRenderDiscoverySchema }).strict(),
    z.object({ ok: z.literal(true), protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL), requestId: sdkRequestIdSchema, operation: z.literal("render.presets"), data: sdkRenderPresetsSchema }).strict(),
    z.object({ ok: z.literal(true), protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL), requestId: sdkRequestIdSchema, operation: z.literal("render.settings"), data: sdkRenderSettingsSnapshotSchema }).strict(),
    z.object({ ok: z.literal(true), protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL), requestId: sdkRequestIdSchema, operation: z.literal("render.queue"), data: sdkRenderQueuePageSchema }).strict(),
    z.object({ ok: z.literal(true), protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL), requestId: sdkRequestIdSchema, operation: z.literal("render.job_status"), data: sdkRenderJobStatusSnapshotSchema }).strict(),
    z.object({ ok: z.literal(true), protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL), requestId: sdkRequestIdSchema, operation: z.literal("artifact.content"), data: sdkArtifactContentChunkSchema }).strict(),
    z.object({ ok: z.literal(true), protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL), requestId: sdkRequestIdSchema, operation: z.literal("artifact.fusion_setting.publish"), data: sdkFusionSettingArtifactReceiptSchema }).strict(),
    z.object({
        ok: z.literal(true),
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
        requestId: sdkRequestIdSchema,
        operation: z.literal("timeline.edit.preview"),
        data: sdkTimelineEditImpactSchema,
    }).strict(),
    z.object({
        ok: z.literal(true), protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL), requestId: sdkRequestIdSchema,
        operation: z.literal("timeline.managed.preview"), data: sdkManagedTimelinePreviewSchema,
    }).strict(),
    z.object({
        ok: z.literal(true), protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL), requestId: sdkRequestIdSchema,
        operation: z.literal("timeline.managed.export"), data: sdkManagedTimelineExportSchema,
    }).strict(),
    z.object({
        ok: z.literal(true),
        protocolVersion: z.literal(CUTAGENT_SDK_WIRE_PROTOCOL),
        requestId: sdkRequestIdSchema,
        operation: z.literal("multicam.inspect"),
        data: sdkMulticamSnapshotSchema,
    }).strict(),
]);
export const sdkRuntimeReadResponseSchema = z.union([
    sdkRuntimeReadSuccessSchema,
    sdkRuntimeReadFailureSchema,
]);
