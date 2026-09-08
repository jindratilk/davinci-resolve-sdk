import { z } from "zod";
export * from "./sdk-operations.js";
export * from "./sdk-fairlight.js";
export * from "./sdk-timeline-editing.js";
import { sdkTimelineEditImpactSchema, sdkTimelineEditIntentSchema } from "./sdk-timeline-editing.js";
export * from "./sdk-fusion.js";
export { CUTAGENT_SDK_PROTOCOL_DIGEST } from "./sdk-runtime-protocol.js";
export { CUTAGENT_SDK_PREVIEW_VERSION, CUTAGENT_SDK_RUNTIME_MAX_EXCLUSIVE_VERSION, CUTAGENT_SDK_RUNTIME_MIN_VERSION, CUTAGENT_SDK_SUPPORTED_PACKAGE_MAJOR, CUTAGENT_SDK_SUPPORTED_PACKAGE_MINOR, } from "./sdk-runtime-policy.js";
export { sdkConnectionIdSchema, sdkMediaPoolFolderIdSchema, sdkMediaPoolItemIdSchema, sdkMarkerIdSchema, sdkProjectIdSchema, sdkRequestIdSchema, sdkRevisionSchema, sdkRenderQueueCursorSchema, sdkRuntimeFingerprintSchema, sdkRuntimeInstanceIdSchema, sdkSessionIdSchema, sdkSnapshotRenderJobIdSchema, sdkSnapshotTimelineItemIdSchema, sdkSnapshotMediaPoolFolderIdSchema, sdkSnapshotMediaPoolItemIdSchema, sdkSnapshotTrackIdSchema, sdkTimelineIdSchema, sdkTimelineItemIdSchema, } from "./sdk-identities.js";
export declare const CUTAGENT_SDK_WIRE_PROTOCOL: 1;
export declare const CUTAGENT_SDK_API_VERSION: "0.2";
export declare const CUTAGENT_SDK_CONNECT_PATH: "/internal/sdk/v1/connect";
export declare const CUTAGENT_SDK_CONFIRM_PATH: "/internal/sdk/v1/session/confirm";
export declare const CUTAGENT_SDK_CLOSE_PATH: "/internal/sdk/v1/session/close";
export declare const CUTAGENT_SDK_READ_PATH: "/internal/sdk/v1/read";
export declare const CUTAGENT_SDK_OPERATION_PATH: "/internal/sdk/v1/operation";
export declare const CUTAGENT_SDK_WORKFLOW_PATH: "/internal/sdk/v1/workflow";
export declare const CUTAGENT_SDK_SESSION_HEADER: "x-cutagent-sdk-session";
export declare const CUTAGENT_SDK_CAPABILITY_HEADER: "x-cutagent-bridge-capability";
export declare const CUTAGENT_SDK_MAX_CONTROL_TIMEOUT_MS: 180000;
export declare const sdkRuntimeDistributionSchema: z.ZodEnum<{
    standalone_local: "standalone_local";
    plugin_managed: "plugin_managed";
}>;
export declare const sdkCompatibilityHandshakeRequestSchema: z.ZodObject<{
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    sdkVersion: z.ZodString;
    sdkApiVersion: z.ZodString;
    supportedWireProtocols: z.ZodArray<z.ZodNumber>;
    requestedDistribution: z.ZodEnum<{
        standalone_local: "standalone_local";
        plugin_managed: "plugin_managed";
    }>;
    protocolDigest: z.ZodLiteral<"sha256:7c591bff196489464626d07d0acf139ce1e9529ca114cd4dbb1d31c9253e9ee5">;
}, z.core.$strict>;
export declare const sdkCompatibilityDescriptorSchema: z.ZodObject<{
    sdkApiVersion: z.ZodString;
    wireProtocol: z.ZodNumber;
    runtimeVersion: z.ZodString;
    distribution: z.ZodEnum<{
        standalone_local: "standalone_local";
        plugin_managed: "plugin_managed";
    }>;
    distributionVersion: z.ZodString;
    cliVersion: z.ZodString;
    protocolDigest: z.ZodLiteral<"sha256:7c591bff196489464626d07d0acf139ce1e9529ca114cd4dbb1d31c9253e9ee5">;
    runtimeFingerprint: z.core.$ZodBranded<z.ZodString, "SdkRuntimeFingerprint", "out">;
}, z.core.$strict>;
export declare const sdkCompatibilityHandshakeResponseSchema: z.ZodObject<{
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    descriptor: z.ZodObject<{
        sdkApiVersion: z.ZodString;
        wireProtocol: z.ZodNumber;
        runtimeVersion: z.ZodString;
        distribution: z.ZodEnum<{
            standalone_local: "standalone_local";
            plugin_managed: "plugin_managed";
        }>;
        distributionVersion: z.ZodString;
        cliVersion: z.ZodString;
        protocolDigest: z.ZodLiteral<"sha256:7c591bff196489464626d07d0acf139ce1e9529ca114cd4dbb1d31c9253e9ee5">;
        runtimeFingerprint: z.core.$ZodBranded<z.ZodString, "SdkRuntimeFingerprint", "out">;
    }, z.core.$strict>;
}, z.core.$strict>;
export declare const sdkDesktopDiscoverySchema: z.ZodObject<{
    version: z.ZodLiteral<1>;
    distribution: z.ZodLiteral<"standalone_local">;
    endpoint: z.ZodString;
    bridgeCapability: z.ZodString;
    bootstrapToken: z.ZodString;
    runtimeInstanceId: z.core.$ZodBranded<z.ZodString, "SdkRuntimeInstanceId", "out">;
    pid: z.ZodNumber;
    issuedAt: z.ZodString;
    expiresAt: z.ZodString;
}, z.core.$strict>;
/** Transport-independent request that opens one pending SDK session. */
export declare const sdkRuntimeSessionConnectRequestSchema: z.ZodObject<{
    protocolVersion: z.ZodLiteral<1>;
    handshake: z.ZodObject<{
        requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
        sdkVersion: z.ZodString;
        sdkApiVersion: z.ZodString;
        supportedWireProtocols: z.ZodArray<z.ZodNumber>;
        requestedDistribution: z.ZodEnum<{
            standalone_local: "standalone_local";
            plugin_managed: "plugin_managed";
        }>;
        protocolDigest: z.ZodLiteral<"sha256:7c591bff196489464626d07d0acf139ce1e9529ca114cd4dbb1d31c9253e9ee5">;
    }, z.core.$strict>;
}, z.core.$strict>;
/** Desktop carrier envelope around the transport-independent connect request. */
export declare const sdkRuntimeConnectRequestSchema: z.ZodObject<{
    protocolVersion: z.ZodLiteral<1>;
    handshake: z.ZodObject<{
        requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
        sdkVersion: z.ZodString;
        sdkApiVersion: z.ZodString;
        supportedWireProtocols: z.ZodArray<z.ZodNumber>;
        requestedDistribution: z.ZodEnum<{
            standalone_local: "standalone_local";
            plugin_managed: "plugin_managed";
        }>;
        protocolDigest: z.ZodLiteral<"sha256:7c591bff196489464626d07d0acf139ce1e9529ca114cd4dbb1d31c9253e9ee5">;
    }, z.core.$strict>;
    runtimeInstanceId: z.core.$ZodBranded<z.ZodString, "SdkRuntimeInstanceId", "out">;
    bootstrapToken: z.ZodString;
}, z.core.$strict>;
export declare const sdkRuntimeSessionBaseSchema: z.ZodObject<{
    connectionId: z.core.$ZodBranded<z.ZodString, "ConnectionId", "out">;
    sessionId: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
    sessionToken: z.ZodString;
    issuedAt: z.ZodString;
    expiresAt: z.ZodString;
    idleExpiresAt: z.ZodString;
}, z.core.$strict>;
export declare const validateSessionLifetime: (session: {
    issuedAt: string;
    expiresAt: string;
    idleExpiresAt: string;
}, context: z.RefinementCtx) => void;
export declare const sdkRuntimeSessionSchema: z.ZodObject<{
    connectionId: z.core.$ZodBranded<z.ZodString, "ConnectionId", "out">;
    sessionId: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
    sessionToken: z.ZodString;
    issuedAt: z.ZodString;
    expiresAt: z.ZodString;
    idleExpiresAt: z.ZodString;
}, z.core.$strict>;
export declare const sdkRuntimeConnectSuccessSchema: z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    descriptor: z.ZodObject<{
        sdkApiVersion: z.ZodString;
        wireProtocol: z.ZodNumber;
        runtimeVersion: z.ZodString;
        distribution: z.ZodEnum<{
            standalone_local: "standalone_local";
            plugin_managed: "plugin_managed";
        }>;
        distributionVersion: z.ZodString;
        cliVersion: z.ZodString;
        protocolDigest: z.ZodLiteral<"sha256:7c591bff196489464626d07d0acf139ce1e9529ca114cd4dbb1d31c9253e9ee5">;
        runtimeFingerprint: z.core.$ZodBranded<z.ZodString, "SdkRuntimeFingerprint", "out">;
    }, z.core.$strict>;
    session: z.ZodObject<{
        connectionId: z.core.$ZodBranded<z.ZodString, "ConnectionId", "out">;
        sessionId: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
        sessionToken: z.ZodString;
        issuedAt: z.ZodString;
        expiresAt: z.ZodString;
        idleExpiresAt: z.ZodString;
    }, z.core.$strict>;
}, z.core.$strict>;
export declare const sdkTransportErrorCodeSchema: z.ZodEnum<{
    RUNTIME_UNAVAILABLE: "RUNTIME_UNAVAILABLE";
    SDK_INCOMPATIBLE: "SDK_INCOMPATIBLE";
    AUTHENTICATION_REQUIRED: "AUTHENTICATION_REQUIRED";
    SUBSCRIPTION_REQUIRED: "SUBSCRIPTION_REQUIRED";
    INVALID_REQUEST: "INVALID_REQUEST";
    BOOTSTRAP_REJECTED: "BOOTSTRAP_REJECTED";
    SESSION_REJECTED: "SESSION_REJECTED";
    SESSION_LIMIT_REACHED: "SESSION_LIMIT_REACHED";
    INTERNAL_ERROR: "INTERNAL_ERROR";
}>;
export declare const sdkTransportRecoverySchema: z.ZodEnum<{
    upgrade_or_wait: "upgrade_or_wait";
    restart_runtime: "restart_runtime";
    update_required: "update_required";
    contact_support: "contact_support";
    sign_in: "sign_in";
    reconnect: "reconnect";
}>;
export declare const sdkRuntimeFailureSchema: z.ZodObject<{
    ok: z.ZodLiteral<false>;
    requestId: z.ZodOptional<z.core.$ZodBranded<z.ZodString, "RequestId", "out">>;
    error: z.ZodObject<{
        code: z.ZodEnum<{
            RUNTIME_UNAVAILABLE: "RUNTIME_UNAVAILABLE";
            SDK_INCOMPATIBLE: "SDK_INCOMPATIBLE";
            AUTHENTICATION_REQUIRED: "AUTHENTICATION_REQUIRED";
            SUBSCRIPTION_REQUIRED: "SUBSCRIPTION_REQUIRED";
            INVALID_REQUEST: "INVALID_REQUEST";
            BOOTSTRAP_REJECTED: "BOOTSTRAP_REJECTED";
            SESSION_REJECTED: "SESSION_REJECTED";
            SESSION_LIMIT_REACHED: "SESSION_LIMIT_REACHED";
            INTERNAL_ERROR: "INTERNAL_ERROR";
        }>;
        message: z.ZodString;
        recovery: z.ZodEnum<{
            upgrade_or_wait: "upgrade_or_wait";
            restart_runtime: "restart_runtime";
            update_required: "update_required";
            contact_support: "contact_support";
            sign_in: "sign_in";
            reconnect: "reconnect";
        }>;
    }, z.core.$strict>;
}, z.core.$strict>;
export declare const sdkReadErrorCodeSchema: z.ZodUnion<readonly [z.ZodEnum<{
    RUNTIME_UNAVAILABLE: "RUNTIME_UNAVAILABLE";
    SDK_INCOMPATIBLE: "SDK_INCOMPATIBLE";
    AUTHENTICATION_REQUIRED: "AUTHENTICATION_REQUIRED";
    SUBSCRIPTION_REQUIRED: "SUBSCRIPTION_REQUIRED";
    INVALID_REQUEST: "INVALID_REQUEST";
    BOOTSTRAP_REJECTED: "BOOTSTRAP_REJECTED";
    SESSION_REJECTED: "SESSION_REJECTED";
    SESSION_LIMIT_REACHED: "SESSION_LIMIT_REACHED";
    INTERNAL_ERROR: "INTERNAL_ERROR";
}>, z.ZodEnum<{
    USAGE_EXHAUSTED: "USAGE_EXHAUSTED";
    INVALID_RESPONSE: "INVALID_RESPONSE";
    CAPABILITY_UNAVAILABLE: "CAPABILITY_UNAVAILABLE";
    TARGET_NOT_FOUND: "TARGET_NOT_FOUND";
    AMBIGUOUS_TARGET: "AMBIGUOUS_TARGET";
    STALE_REVISION: "STALE_REVISION";
    RUNTIME_TIMEOUT: "RUNTIME_TIMEOUT";
    TEMPORARY_PROVIDER_FAILURE: "TEMPORARY_PROVIDER_FAILURE";
}>]>;
export declare const sdkReadRecoverySchema: z.ZodUnion<readonly [z.ZodEnum<{
    upgrade_or_wait: "upgrade_or_wait";
    restart_runtime: "restart_runtime";
    update_required: "update_required";
    contact_support: "contact_support";
    sign_in: "sign_in";
    reconnect: "reconnect";
}>, z.ZodEnum<{
    retry: "retry";
    inspect_state: "inspect_state";
}>]>;
export declare const sdkRuntimeReadFailureSchema: z.ZodObject<{
    ok: z.ZodLiteral<false>;
    requestId: z.ZodOptional<z.core.$ZodBranded<z.ZodString, "RequestId", "out">>;
    error: z.ZodObject<{
        code: z.ZodUnion<readonly [z.ZodEnum<{
            RUNTIME_UNAVAILABLE: "RUNTIME_UNAVAILABLE";
            SDK_INCOMPATIBLE: "SDK_INCOMPATIBLE";
            AUTHENTICATION_REQUIRED: "AUTHENTICATION_REQUIRED";
            SUBSCRIPTION_REQUIRED: "SUBSCRIPTION_REQUIRED";
            INVALID_REQUEST: "INVALID_REQUEST";
            BOOTSTRAP_REJECTED: "BOOTSTRAP_REJECTED";
            SESSION_REJECTED: "SESSION_REJECTED";
            SESSION_LIMIT_REACHED: "SESSION_LIMIT_REACHED";
            INTERNAL_ERROR: "INTERNAL_ERROR";
        }>, z.ZodEnum<{
            USAGE_EXHAUSTED: "USAGE_EXHAUSTED";
            INVALID_RESPONSE: "INVALID_RESPONSE";
            CAPABILITY_UNAVAILABLE: "CAPABILITY_UNAVAILABLE";
            TARGET_NOT_FOUND: "TARGET_NOT_FOUND";
            AMBIGUOUS_TARGET: "AMBIGUOUS_TARGET";
            STALE_REVISION: "STALE_REVISION";
            RUNTIME_TIMEOUT: "RUNTIME_TIMEOUT";
            TEMPORARY_PROVIDER_FAILURE: "TEMPORARY_PROVIDER_FAILURE";
        }>]>;
        message: z.ZodString;
        recovery: z.ZodUnion<readonly [z.ZodEnum<{
            upgrade_or_wait: "upgrade_or_wait";
            restart_runtime: "restart_runtime";
            update_required: "update_required";
            contact_support: "contact_support";
            sign_in: "sign_in";
            reconnect: "reconnect";
        }>, z.ZodEnum<{
            retry: "retry";
            inspect_state: "inspect_state";
        }>]>;
    }, z.core.$strict>;
}, z.core.$strict>;
export declare const sdkRuntimeConnectResponseSchema: z.ZodUnion<readonly [z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    descriptor: z.ZodObject<{
        sdkApiVersion: z.ZodString;
        wireProtocol: z.ZodNumber;
        runtimeVersion: z.ZodString;
        distribution: z.ZodEnum<{
            standalone_local: "standalone_local";
            plugin_managed: "plugin_managed";
        }>;
        distributionVersion: z.ZodString;
        cliVersion: z.ZodString;
        protocolDigest: z.ZodLiteral<"sha256:7c591bff196489464626d07d0acf139ce1e9529ca114cd4dbb1d31c9253e9ee5">;
        runtimeFingerprint: z.core.$ZodBranded<z.ZodString, "SdkRuntimeFingerprint", "out">;
    }, z.core.$strict>;
    session: z.ZodObject<{
        connectionId: z.core.$ZodBranded<z.ZodString, "ConnectionId", "out">;
        sessionId: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
        sessionToken: z.ZodString;
        issuedAt: z.ZodString;
        expiresAt: z.ZodString;
        idleExpiresAt: z.ZodString;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<false>;
    requestId: z.ZodOptional<z.core.$ZodBranded<z.ZodString, "RequestId", "out">>;
    error: z.ZodObject<{
        code: z.ZodEnum<{
            RUNTIME_UNAVAILABLE: "RUNTIME_UNAVAILABLE";
            SDK_INCOMPATIBLE: "SDK_INCOMPATIBLE";
            AUTHENTICATION_REQUIRED: "AUTHENTICATION_REQUIRED";
            SUBSCRIPTION_REQUIRED: "SUBSCRIPTION_REQUIRED";
            INVALID_REQUEST: "INVALID_REQUEST";
            BOOTSTRAP_REJECTED: "BOOTSTRAP_REJECTED";
            SESSION_REJECTED: "SESSION_REJECTED";
            SESSION_LIMIT_REACHED: "SESSION_LIMIT_REACHED";
            INTERNAL_ERROR: "INTERNAL_ERROR";
        }>;
        message: z.ZodString;
        recovery: z.ZodEnum<{
            upgrade_or_wait: "upgrade_or_wait";
            restart_runtime: "restart_runtime";
            update_required: "update_required";
            contact_support: "contact_support";
            sign_in: "sign_in";
            reconnect: "reconnect";
        }>;
    }, z.core.$strict>;
}, z.core.$strict>]>;
export declare const sdkRuntimeCloseRequestSchema: z.ZodObject<{
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    sessionId: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
}, z.core.$strict>;
export declare const sdkRuntimeConfirmRequestSchema: z.ZodObject<{
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    sessionId: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
}, z.core.$strict>;
export declare const sdkRuntimeConfirmSuccessSchema: z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    confirmed: z.ZodLiteral<true>;
}, z.core.$strict>;
export declare const sdkRuntimeConfirmResponseSchema: z.ZodUnion<readonly [z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    confirmed: z.ZodLiteral<true>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<false>;
    requestId: z.ZodOptional<z.core.$ZodBranded<z.ZodString, "RequestId", "out">>;
    error: z.ZodObject<{
        code: z.ZodEnum<{
            RUNTIME_UNAVAILABLE: "RUNTIME_UNAVAILABLE";
            SDK_INCOMPATIBLE: "SDK_INCOMPATIBLE";
            AUTHENTICATION_REQUIRED: "AUTHENTICATION_REQUIRED";
            SUBSCRIPTION_REQUIRED: "SUBSCRIPTION_REQUIRED";
            INVALID_REQUEST: "INVALID_REQUEST";
            BOOTSTRAP_REJECTED: "BOOTSTRAP_REJECTED";
            SESSION_REJECTED: "SESSION_REJECTED";
            SESSION_LIMIT_REACHED: "SESSION_LIMIT_REACHED";
            INTERNAL_ERROR: "INTERNAL_ERROR";
        }>;
        message: z.ZodString;
        recovery: z.ZodEnum<{
            upgrade_or_wait: "upgrade_or_wait";
            restart_runtime: "restart_runtime";
            update_required: "update_required";
            contact_support: "contact_support";
            sign_in: "sign_in";
            reconnect: "reconnect";
        }>;
    }, z.core.$strict>;
}, z.core.$strict>]>;
export declare const sdkRuntimeCloseSuccessSchema: z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    closed: z.ZodLiteral<true>;
}, z.core.$strict>;
export declare const sdkRuntimeCloseResponseSchema: z.ZodUnion<readonly [z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    closed: z.ZodLiteral<true>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<false>;
    requestId: z.ZodOptional<z.core.$ZodBranded<z.ZodString, "RequestId", "out">>;
    error: z.ZodObject<{
        code: z.ZodEnum<{
            RUNTIME_UNAVAILABLE: "RUNTIME_UNAVAILABLE";
            SDK_INCOMPATIBLE: "SDK_INCOMPATIBLE";
            AUTHENTICATION_REQUIRED: "AUTHENTICATION_REQUIRED";
            SUBSCRIPTION_REQUIRED: "SUBSCRIPTION_REQUIRED";
            INVALID_REQUEST: "INVALID_REQUEST";
            BOOTSTRAP_REJECTED: "BOOTSTRAP_REJECTED";
            SESSION_REJECTED: "SESSION_REJECTED";
            SESSION_LIMIT_REACHED: "SESSION_LIMIT_REACHED";
            INTERNAL_ERROR: "INTERNAL_ERROR";
        }>;
        message: z.ZodString;
        recovery: z.ZodEnum<{
            upgrade_or_wait: "upgrade_or_wait";
            restart_runtime: "restart_runtime";
            update_required: "update_required";
            contact_support: "contact_support";
            sign_in: "sign_in";
            reconnect: "reconnect";
        }>;
    }, z.core.$strict>;
}, z.core.$strict>]>;
export declare const sdkTrackTypeSchema: z.ZodEnum<{
    video: "video";
    audio: "audio";
    subtitle: "subtitle";
}>;
export declare const sdkProjectReferenceSchema: z.ZodObject<{
    id: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    name: z.ZodString;
}, z.core.$strict>;
export declare const sdkTimelineReferenceSchema: z.ZodObject<{
    id: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    name: z.ZodString;
}, z.core.$strict>;
export declare const sdkTimelineClipSnapshotSchema: z.ZodObject<{
    id: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>;
    snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotTimelineItemId", "out">;
    snapshotTrackId: z.core.$ZodBranded<z.ZodString, "SnapshotTrackId", "out">;
    snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    name: z.ZodString;
    recordRange: z.ZodObject<{
        domain: z.ZodLiteral<"timeline_record_range">;
        unit: z.ZodLiteral<"frames">;
        start: z.ZodNumber;
        endExclusive: z.ZodNumber;
    }, z.core.$strict>;
    duration: z.ZodObject<{
        domain: z.ZodLiteral<"duration">;
        value: z.ZodObject<{
            kind: z.ZodLiteral<"frames">;
            value: z.ZodNumber;
        }, z.core.$strict>;
    }, z.core.$strict>;
    sourceRange: z.ZodNullable<z.ZodObject<{
        domain: z.ZodLiteral<"source_range">;
        unit: z.ZodLiteral<"frames">;
        start: z.ZodNumber;
        endExclusive: z.ZodNumber;
    }, z.core.$strict>>;
    retimeSource: z.ZodOptional<z.ZodNullable<z.ZodObject<{
        availableRange: z.ZodObject<{
            domain: z.ZodLiteral<"source_range">;
            unit: z.ZodLiteral<"frames">;
            start: z.ZodNumber;
            endExclusive: z.ZodNumber;
        }, z.core.$strict>;
        originFrame: z.ZodNumber;
    }, z.core.$strict>>>;
    sourceFrameRate: z.ZodNullable<z.ZodObject<{
        numerator: z.ZodNumber;
        denominator: z.ZodNumber;
        nominalTimebase: z.ZodNumber;
    }, z.core.$strict>>;
    mediaPoolItemId: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">>;
    linkedItemIds: z.ZodNullable<z.ZodArray<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>>;
}, z.core.$strict>;
export declare const sdkRetimeReadbackSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
    timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    timelineItemId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
    durationFrames: z.ZodNumber;
    speedMultiplier: z.ZodNumber;
    reversed: z.ZodBoolean;
    frozen: z.ZodBoolean;
    points: z.ZodArray<z.ZodObject<{
        recordFrame: z.ZodNumber;
        recordPositionFrames: z.ZodNumber;
        sourceFrame: z.ZodNumber;
        incomingControl: z.ZodObject<{
            recordPositionFrames: z.ZodNumber;
            sourceFrame: z.ZodNumber;
        }, z.core.$strict>;
        outgoingControl: z.ZodObject<{
            recordPositionFrames: z.ZodNumber;
            sourceFrame: z.ZodNumber;
        }, z.core.$strict>;
        speed: z.ZodNumber;
        interpolation: z.ZodEnum<{
            linear: "linear";
            bezier: "bezier";
            hold: "hold";
        }>;
    }, z.core.$strict>>;
}, z.core.$strict>;
export declare const sdkTimelineTrackSnapshotSchema: z.ZodObject<{
    snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotTrackId", "out">;
    timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
    snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    type: z.ZodEnum<{
        video: "video";
        audio: "audio";
        subtitle: "subtitle";
    }>;
    index: z.ZodNumber;
    name: z.ZodString;
    enabled: z.ZodNullable<z.ZodBoolean>;
    locked: z.ZodNullable<z.ZodBoolean>;
    clips: z.ZodArray<z.ZodObject<{
        id: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>;
        snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotTimelineItemId", "out">;
        snapshotTrackId: z.core.$ZodBranded<z.ZodString, "SnapshotTrackId", "out">;
        snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        name: z.ZodString;
        recordRange: z.ZodObject<{
            domain: z.ZodLiteral<"timeline_record_range">;
            unit: z.ZodLiteral<"frames">;
            start: z.ZodNumber;
            endExclusive: z.ZodNumber;
        }, z.core.$strict>;
        duration: z.ZodObject<{
            domain: z.ZodLiteral<"duration">;
            value: z.ZodObject<{
                kind: z.ZodLiteral<"frames">;
                value: z.ZodNumber;
            }, z.core.$strict>;
        }, z.core.$strict>;
        sourceRange: z.ZodNullable<z.ZodObject<{
            domain: z.ZodLiteral<"source_range">;
            unit: z.ZodLiteral<"frames">;
            start: z.ZodNumber;
            endExclusive: z.ZodNumber;
        }, z.core.$strict>>;
        retimeSource: z.ZodOptional<z.ZodNullable<z.ZodObject<{
            availableRange: z.ZodObject<{
                domain: z.ZodLiteral<"source_range">;
                unit: z.ZodLiteral<"frames">;
                start: z.ZodNumber;
                endExclusive: z.ZodNumber;
            }, z.core.$strict>;
            originFrame: z.ZodNumber;
        }, z.core.$strict>>>;
        sourceFrameRate: z.ZodNullable<z.ZodObject<{
            numerator: z.ZodNumber;
            denominator: z.ZodNumber;
            nominalTimebase: z.ZodNumber;
        }, z.core.$strict>>;
        mediaPoolItemId: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">>;
        linkedItemIds: z.ZodNullable<z.ZodArray<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>>;
    }, z.core.$strict>>;
}, z.core.$strict>;
export declare const sdkTimelineMarkerSnapshotSchema: z.ZodObject<{
    id: z.core.$ZodBranded<z.ZodString, "MarkerId", "out">;
    snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    position: z.ZodObject<{
        domain: z.ZodLiteral<"timeline_record">;
        value: z.ZodObject<{
            kind: z.ZodLiteral<"frames">;
            value: z.ZodNumber;
        }, z.core.$strict>;
    }, z.core.$strict>;
    color: z.ZodString;
    name: z.ZodString;
    note: z.ZodString;
    duration: z.ZodObject<{
        domain: z.ZodLiteral<"duration">;
        value: z.ZodObject<{
            kind: z.ZodLiteral<"frames">;
            value: z.ZodNumber;
        }, z.core.$strict>;
    }, z.core.$strict>;
}, z.core.$strict>;
export declare const sdkTimelineSnapshotSchema: z.ZodObject<{
    project: z.ZodObject<{
        id: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        name: z.ZodString;
    }, z.core.$strict>;
    timeline: z.ZodObject<{
        id: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        name: z.ZodString;
    }, z.core.$strict>;
    revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    frameRate: z.ZodObject<{
        numerator: z.ZodNumber;
        denominator: z.ZodNumber;
        nominalTimebase: z.ZodNumber;
    }, z.core.$strict>;
    start: z.ZodObject<{
        domain: z.ZodLiteral<"timeline_record">;
        value: z.ZodObject<{
            kind: z.ZodLiteral<"frames">;
            value: z.ZodNumber;
        }, z.core.$strict>;
    }, z.core.$strict>;
    tracks: z.ZodArray<z.ZodObject<{
        snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotTrackId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        type: z.ZodEnum<{
            video: "video";
            audio: "audio";
            subtitle: "subtitle";
        }>;
        index: z.ZodNumber;
        name: z.ZodString;
        enabled: z.ZodNullable<z.ZodBoolean>;
        locked: z.ZodNullable<z.ZodBoolean>;
        clips: z.ZodArray<z.ZodObject<{
            id: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>;
            snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotTimelineItemId", "out">;
            snapshotTrackId: z.core.$ZodBranded<z.ZodString, "SnapshotTrackId", "out">;
            snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            name: z.ZodString;
            recordRange: z.ZodObject<{
                domain: z.ZodLiteral<"timeline_record_range">;
                unit: z.ZodLiteral<"frames">;
                start: z.ZodNumber;
                endExclusive: z.ZodNumber;
            }, z.core.$strict>;
            duration: z.ZodObject<{
                domain: z.ZodLiteral<"duration">;
                value: z.ZodObject<{
                    kind: z.ZodLiteral<"frames">;
                    value: z.ZodNumber;
                }, z.core.$strict>;
            }, z.core.$strict>;
            sourceRange: z.ZodNullable<z.ZodObject<{
                domain: z.ZodLiteral<"source_range">;
                unit: z.ZodLiteral<"frames">;
                start: z.ZodNumber;
                endExclusive: z.ZodNumber;
            }, z.core.$strict>>;
            retimeSource: z.ZodOptional<z.ZodNullable<z.ZodObject<{
                availableRange: z.ZodObject<{
                    domain: z.ZodLiteral<"source_range">;
                    unit: z.ZodLiteral<"frames">;
                    start: z.ZodNumber;
                    endExclusive: z.ZodNumber;
                }, z.core.$strict>;
                originFrame: z.ZodNumber;
            }, z.core.$strict>>>;
            sourceFrameRate: z.ZodNullable<z.ZodObject<{
                numerator: z.ZodNumber;
                denominator: z.ZodNumber;
                nominalTimebase: z.ZodNumber;
            }, z.core.$strict>>;
            mediaPoolItemId: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">>;
            linkedItemIds: z.ZodNullable<z.ZodArray<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>>;
        }, z.core.$strict>>;
    }, z.core.$strict>>;
    markers: z.ZodArray<z.ZodObject<{
        id: z.core.$ZodBranded<z.ZodString, "MarkerId", "out">;
        snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        position: z.ZodObject<{
            domain: z.ZodLiteral<"timeline_record">;
            value: z.ZodObject<{
                kind: z.ZodLiteral<"frames">;
                value: z.ZodNumber;
            }, z.core.$strict>;
        }, z.core.$strict>;
        color: z.ZodString;
        name: z.ZodString;
        note: z.ZodString;
        duration: z.ZodObject<{
            domain: z.ZodLiteral<"duration">;
            value: z.ZodObject<{
                kind: z.ZodLiteral<"frames">;
                value: z.ZodNumber;
            }, z.core.$strict>;
        }, z.core.$strict>;
    }, z.core.$strict>>;
    fairlight: z.ZodDefault<z.ZodDiscriminatedUnion<[z.ZodObject<{
        status: z.ZodLiteral<"available">;
        tracks: z.ZodArray<z.ZodObject<{
            trackIndex: z.ZodNumber;
            levelDb: z.ZodDiscriminatedUnion<[z.ZodObject<{
                status: z.ZodLiteral<"available">;
                value: z.ZodNumber;
            }, z.core.$strict>, z.ZodObject<{
                status: z.ZodLiteral<"unavailable">;
                reason: z.ZodEnum<{
                    readback_unavailable: "readback_unavailable";
                    not_exposed_by_runtime: "not_exposed_by_runtime";
                }>;
            }, z.core.$strict>], "status">;
            pan: z.ZodDiscriminatedUnion<[z.ZodObject<{
                status: z.ZodLiteral<"available">;
                value: z.ZodNumber;
            }, z.core.$strict>, z.ZodObject<{
                status: z.ZodLiteral<"unavailable">;
                reason: z.ZodEnum<{
                    readback_unavailable: "readback_unavailable";
                    not_exposed_by_runtime: "not_exposed_by_runtime";
                }>;
            }, z.core.$strict>], "status">;
        }, z.core.$strict>>;
        clips: z.ZodDefault<z.ZodArray<z.ZodObject<{
            clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
            trackIndex: z.ZodNumber;
            gainDb: z.ZodDiscriminatedUnion<[z.ZodObject<{
                status: z.ZodLiteral<"available">;
                value: z.ZodNumber;
            }, z.core.$strict>, z.ZodObject<{
                status: z.ZodLiteral<"unavailable">;
                reason: z.ZodEnum<{
                    readback_unavailable: "readback_unavailable";
                    not_exposed_by_runtime: "not_exposed_by_runtime";
                }>;
            }, z.core.$strict>], "status">;
            pan: z.ZodDiscriminatedUnion<[z.ZodObject<{
                status: z.ZodLiteral<"available">;
                value: z.ZodNumber;
            }, z.core.$strict>, z.ZodObject<{
                status: z.ZodLiteral<"unavailable">;
                reason: z.ZodEnum<{
                    readback_unavailable: "readback_unavailable";
                    not_exposed_by_runtime: "not_exposed_by_runtime";
                }>;
            }, z.core.$strict>], "status">;
            fadeInFrames: z.ZodDiscriminatedUnion<[z.ZodObject<{
                status: z.ZodLiteral<"available">;
                value: z.ZodNumber;
            }, z.core.$strict>, z.ZodObject<{
                status: z.ZodLiteral<"unavailable">;
                reason: z.ZodEnum<{
                    readback_unavailable: "readback_unavailable";
                    not_exposed_by_runtime: "not_exposed_by_runtime";
                }>;
            }, z.core.$strict>], "status">;
            fadeOutFrames: z.ZodDiscriminatedUnion<[z.ZodObject<{
                status: z.ZodLiteral<"available">;
                value: z.ZodNumber;
            }, z.core.$strict>, z.ZodObject<{
                status: z.ZodLiteral<"unavailable">;
                reason: z.ZodEnum<{
                    readback_unavailable: "readback_unavailable";
                    not_exposed_by_runtime: "not_exposed_by_runtime";
                }>;
            }, z.core.$strict>], "status">;
        }, z.core.$strict>>>;
        buses: z.ZodDiscriminatedUnion<[z.ZodObject<{
            status: z.ZodLiteral<"available">;
            buses: z.ZodArray<z.ZodObject<{
                name: z.ZodString;
                kind: z.ZodEnum<{
                    bus: "bus";
                    main: "main";
                }>;
            }, z.core.$strict>>;
        }, z.core.$strict>, z.ZodObject<{
            status: z.ZodLiteral<"unavailable">;
            reason: z.ZodEnum<{
                readback_unavailable: "readback_unavailable";
                not_exposed_by_runtime: "not_exposed_by_runtime";
            }>;
            buses: z.ZodTuple<[], null>;
        }, z.core.$strict>], "status">;
    }, z.core.$strict>, z.ZodObject<{
        status: z.ZodLiteral<"unavailable">;
        reason: z.ZodEnum<{
            readback_unavailable: "readback_unavailable";
            not_exposed_by_runtime: "not_exposed_by_runtime";
        }>;
        tracks: z.ZodTuple<[], null>;
        buses: z.ZodObject<{
            status: z.ZodLiteral<"unavailable">;
            reason: z.ZodEnum<{
                readback_unavailable: "readback_unavailable";
                not_exposed_by_runtime: "not_exposed_by_runtime";
            }>;
            buses: z.ZodTuple<[], null>;
        }, z.core.$strict>;
    }, z.core.$strict>], "status">>;
}, z.core.$strict>;
export declare const sdkMediaPoolAssetKindSchema: z.ZodEnum<{
    unknown: "unknown";
    timeline: "timeline";
    multicam: "multicam";
    fusion_composition: "fusion_composition";
    video: "video";
    audio: "audio";
    still: "still";
    compound: "compound";
    generator: "generator";
}>;
export declare const sdkMediaPoolMetadataKeySchema: z.ZodEnum<{
    description: "description";
    comments: "comments";
    keywords: "keywords";
    shot: "shot";
    scene: "scene";
    take: "take";
    angle: "angle";
    camera: "camera";
    reel: "reel";
    dateRecorded: "dateRecorded";
    goodTake: "goodTake";
    clipColor: "clipColor";
}>;
export declare const sdkMediaPoolMetadataEntrySchema: z.ZodObject<{
    key: z.ZodEnum<{
        description: "description";
        comments: "comments";
        keywords: "keywords";
        shot: "shot";
        scene: "scene";
        take: "take";
        angle: "angle";
        camera: "camera";
        reel: "reel";
        dateRecorded: "dateRecorded";
        goodTake: "goodTake";
        clipColor: "clipColor";
    }>;
    value: z.ZodString;
}, z.core.$strict>;
export declare const sdkMediaPoolFolderSnapshotSchema: z.ZodObject<{
    id: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "MediaPoolFolderId", "out">>;
    snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolFolderId", "out">;
    parentSnapshotId: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolFolderId", "out">>;
    snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    name: z.ZodString;
    depth: z.ZodNumber;
}, z.core.$strict>;
export declare const sdkMediaPoolAssetSnapshotSchema: z.ZodObject<{
    id: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">>;
    snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolItemId", "out">;
    folderSnapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolFolderId", "out">;
    snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    name: z.ZodString;
    kind: z.ZodEnum<{
        unknown: "unknown";
        timeline: "timeline";
        multicam: "multicam";
        fusion_composition: "fusion_composition";
        video: "video";
        audio: "audio";
        still: "still";
        compound: "compound";
        generator: "generator";
    }>;
    selected: z.ZodBoolean;
    sourceFileName: z.ZodNullable<z.ZodString>;
    duration: z.ZodNullable<z.ZodString>;
    resolution: z.ZodNullable<z.ZodString>;
    frameRate: z.ZodNullable<z.ZodString>;
    startTimecode: z.ZodNullable<z.ZodString>;
    metadata: z.ZodArray<z.ZodObject<{
        key: z.ZodEnum<{
            description: "description";
            comments: "comments";
            keywords: "keywords";
            shot: "shot";
            scene: "scene";
            take: "take";
            angle: "angle";
            camera: "camera";
            reel: "reel";
            dateRecorded: "dateRecorded";
            goodTake: "goodTake";
            clipColor: "clipColor";
        }>;
        value: z.ZodString;
    }, z.core.$strict>>;
}, z.core.$strict>;
export declare const sdkMediaPoolSearchSchema: z.ZodObject<{
    query: z.ZodString;
    match: z.ZodEnum<{
        exact: "exact";
        contains: "contains";
    }>;
    fields: z.ZodArray<z.ZodEnum<{
        name: "name";
        metadata: "metadata";
        sourceFileName: "sourceFileName";
    }>>;
}, z.core.$strict>;
export declare const sdkMediaPoolPageSchema: z.ZodObject<{
    project: z.ZodObject<{
        id: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        name: z.ZodString;
    }, z.core.$strict>;
    revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    offset: z.ZodNumber;
    pageSize: z.ZodNumber;
    total: z.ZodNumber;
    nextOffset: z.ZodNullable<z.ZodNumber>;
    search: z.ZodNullable<z.ZodObject<{
        query: z.ZodString;
        match: z.ZodEnum<{
            exact: "exact";
            contains: "contains";
        }>;
        fields: z.ZodArray<z.ZodEnum<{
            name: "name";
            metadata: "metadata";
            sourceFileName: "sourceFileName";
        }>>;
    }, z.core.$strict>>;
    folders: z.ZodArray<z.ZodObject<{
        id: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "MediaPoolFolderId", "out">>;
        snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolFolderId", "out">;
        parentSnapshotId: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolFolderId", "out">>;
        snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        name: z.ZodString;
        depth: z.ZodNumber;
    }, z.core.$strict>>;
    assets: z.ZodArray<z.ZodObject<{
        id: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">>;
        snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolItemId", "out">;
        folderSnapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolFolderId", "out">;
        snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        name: z.ZodString;
        kind: z.ZodEnum<{
            unknown: "unknown";
            timeline: "timeline";
            multicam: "multicam";
            fusion_composition: "fusion_composition";
            video: "video";
            audio: "audio";
            still: "still";
            compound: "compound";
            generator: "generator";
        }>;
        selected: z.ZodBoolean;
        sourceFileName: z.ZodNullable<z.ZodString>;
        duration: z.ZodNullable<z.ZodString>;
        resolution: z.ZodNullable<z.ZodString>;
        frameRate: z.ZodNullable<z.ZodString>;
        startTimecode: z.ZodNullable<z.ZodString>;
        metadata: z.ZodArray<z.ZodObject<{
            key: z.ZodEnum<{
                description: "description";
                comments: "comments";
                keywords: "keywords";
                shot: "shot";
                scene: "scene";
                take: "take";
                angle: "angle";
                camera: "camera";
                reel: "reel";
                dateRecorded: "dateRecorded";
                goodTake: "goodTake";
                clipColor: "clipColor";
            }>;
            value: z.ZodString;
        }, z.core.$strict>>;
    }, z.core.$strict>>;
}, z.core.$strict>;
/** Sanitized immutable Color readback for the exact current video target. */
export declare const sdkColorTargetSnapshotSchema: z.ZodObject<{
    project: z.ZodObject<{
        id: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        name: z.ZodString;
    }, z.core.$strict>;
    timeline: z.ZodObject<{
        id: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        name: z.ZodString;
    }, z.core.$strict>;
    revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    nodeStackLayerIndex: z.ZodNumber;
    frameRate: z.ZodObject<{
        numerator: z.ZodNumber;
        denominator: z.ZodNumber;
        nominalTimebase: z.ZodNumber;
    }, z.core.$strict>;
    track: z.ZodObject<{
        snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotTrackId", "out">;
        index: z.ZodNumber;
        name: z.ZodString;
    }, z.core.$strict>;
    clip: z.ZodObject<{
        snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotTimelineItemId", "out">;
        snapshotTrackId: z.core.$ZodBranded<z.ZodString, "SnapshotTrackId", "out">;
        snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        name: z.ZodString;
        recordRange: z.ZodObject<{
            domain: z.ZodLiteral<"timeline_record_range">;
            unit: z.ZodLiteral<"frames">;
            start: z.ZodNumber;
            endExclusive: z.ZodNumber;
        }, z.core.$strict>;
        duration: z.ZodObject<{
            domain: z.ZodLiteral<"duration">;
            value: z.ZodObject<{
                kind: z.ZodLiteral<"frames">;
                value: z.ZodNumber;
            }, z.core.$strict>;
        }, z.core.$strict>;
        sourceRange: z.ZodNullable<z.ZodObject<{
            domain: z.ZodLiteral<"source_range">;
            unit: z.ZodLiteral<"frames">;
            start: z.ZodNumber;
            endExclusive: z.ZodNumber;
        }, z.core.$strict>>;
        retimeSource: z.ZodOptional<z.ZodNullable<z.ZodObject<{
            availableRange: z.ZodObject<{
                domain: z.ZodLiteral<"source_range">;
                unit: z.ZodLiteral<"frames">;
                start: z.ZodNumber;
                endExclusive: z.ZodNumber;
            }, z.core.$strict>;
            originFrame: z.ZodNumber;
        }, z.core.$strict>>>;
        sourceFrameRate: z.ZodNullable<z.ZodObject<{
            numerator: z.ZodNumber;
            denominator: z.ZodNumber;
            nominalTimebase: z.ZodNumber;
        }, z.core.$strict>>;
        mediaPoolItemId: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">>;
        linkedItemIds: z.ZodNullable<z.ZodArray<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>>;
        id: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
    }, z.core.$strict>;
    capabilities: z.ZodObject<{
        nodeGraph: z.ZodDiscriminatedUnion<[z.ZodObject<{
            status: z.ZodLiteral<"supported">;
        }, z.core.$strict>, z.ZodObject<{
            status: z.ZodLiteral<"unavailable">;
            reason: z.ZodLiteral<"not_exposed_by_runtime">;
        }, z.core.$strict>], "status">;
        labels: z.ZodDiscriminatedUnion<[z.ZodObject<{
            status: z.ZodLiteral<"supported">;
        }, z.core.$strict>, z.ZodObject<{
            status: z.ZodLiteral<"unavailable">;
            reason: z.ZodLiteral<"not_exposed_by_runtime">;
        }, z.core.$strict>], "status">;
        enabledState: z.ZodDiscriminatedUnion<[z.ZodObject<{
            status: z.ZodLiteral<"supported">;
        }, z.core.$strict>, z.ZodObject<{
            status: z.ZodLiteral<"unavailable">;
            reason: z.ZodLiteral<"not_exposed_by_runtime">;
        }, z.core.$strict>], "status">;
        luts: z.ZodDiscriminatedUnion<[z.ZodObject<{
            status: z.ZodLiteral<"supported">;
        }, z.core.$strict>, z.ZodObject<{
            status: z.ZodLiteral<"unavailable">;
            reason: z.ZodLiteral<"not_exposed_by_runtime">;
        }, z.core.$strict>], "status">;
        effects: z.ZodDiscriminatedUnion<[z.ZodObject<{
            status: z.ZodLiteral<"supported">;
        }, z.core.$strict>, z.ZodObject<{
            status: z.ZodLiteral<"unavailable">;
            reason: z.ZodLiteral<"not_exposed_by_runtime">;
        }, z.core.$strict>], "status">;
        versions: z.ZodDiscriminatedUnion<[z.ZodObject<{
            status: z.ZodLiteral<"supported">;
        }, z.core.$strict>, z.ZodObject<{
            status: z.ZodLiteral<"unavailable">;
            reason: z.ZodLiteral<"not_exposed_by_runtime">;
        }, z.core.$strict>], "status">;
        colorGroup: z.ZodDiscriminatedUnion<[z.ZodObject<{
            status: z.ZodLiteral<"supported">;
        }, z.core.$strict>, z.ZodObject<{
            status: z.ZodLiteral<"unavailable">;
            reason: z.ZodLiteral<"not_exposed_by_runtime">;
        }, z.core.$strict>], "status">;
    }, z.core.$strict>;
    mutationCapabilities: z.ZodDefault<z.ZodObject<{
        primary: z.ZodObject<{
            status: z.ZodLiteral<"runtime_check_required">;
            edition: z.ZodEnum<{
                studio_or_free: "studio_or_free";
                studio_required: "studio_required";
            }>;
            projectStorage: z.ZodEnum<{
                any: "any";
                disk_required: "disk_required";
            }>;
            plugin: z.ZodEnum<{
                not_required: "not_required";
                installed_effect_required: "installed_effect_required";
            }>;
        }, z.core.$strict>;
        nodes: z.ZodObject<{
            status: z.ZodLiteral<"runtime_check_required">;
            edition: z.ZodEnum<{
                studio_or_free: "studio_or_free";
                studio_required: "studio_required";
            }>;
            projectStorage: z.ZodEnum<{
                any: "any";
                disk_required: "disk_required";
            }>;
            plugin: z.ZodEnum<{
                not_required: "not_required";
                installed_effect_required: "installed_effect_required";
            }>;
        }, z.core.$strict>;
        lutAssets: z.ZodObject<{
            status: z.ZodLiteral<"runtime_check_required">;
            edition: z.ZodEnum<{
                studio_or_free: "studio_or_free";
                studio_required: "studio_required";
            }>;
            projectStorage: z.ZodEnum<{
                any: "any";
                disk_required: "disk_required";
            }>;
            plugin: z.ZodEnum<{
                not_required: "not_required";
                installed_effect_required: "installed_effect_required";
            }>;
        }, z.core.$strict>;
        drxAssets: z.ZodObject<{
            status: z.ZodLiteral<"runtime_check_required">;
            edition: z.ZodEnum<{
                studio_or_free: "studio_or_free";
                studio_required: "studio_required";
            }>;
            projectStorage: z.ZodEnum<{
                any: "any";
                disk_required: "disk_required";
            }>;
            plugin: z.ZodEnum<{
                not_required: "not_required";
                installed_effect_required: "installed_effect_required";
            }>;
        }, z.core.$strict>;
        effects: z.ZodObject<{
            status: z.ZodLiteral<"runtime_check_required">;
            edition: z.ZodEnum<{
                studio_or_free: "studio_or_free";
                studio_required: "studio_required";
            }>;
            projectStorage: z.ZodEnum<{
                any: "any";
                disk_required: "disk_required";
            }>;
            plugin: z.ZodEnum<{
                not_required: "not_required";
                installed_effect_required: "installed_effect_required";
            }>;
        }, z.core.$strict>;
    }, z.core.$strict>>;
    nodeGraph: z.ZodObject<{
        nodeCount: z.ZodNumber;
        nodes: z.ZodArray<z.ZodObject<{
            index: z.ZodNumber;
            label: z.ZodNullable<z.ZodString>;
            enabled: z.ZodNullable<z.ZodBoolean>;
            lut: z.ZodObject<{
                applied: z.ZodBoolean;
                displayName: z.ZodNullable<z.ZodString>;
            }, z.core.$strict>;
            effects: z.ZodArray<z.ZodString>;
        }, z.core.$strict>>;
    }, z.core.$strict>;
    versions: z.ZodObject<{
        current: z.ZodNullable<z.ZodString>;
        local: z.ZodArray<z.ZodString>;
        remote: z.ZodArray<z.ZodString>;
    }, z.core.$strict>;
    colorGroup: z.ZodNullable<z.ZodString>;
}, z.core.$strict>;
export declare const sdkRenderDiscoverySchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    formatSupport: z.ZodDiscriminatedUnion<[z.ZodObject<{
        availability: z.ZodLiteral<"supported">;
    }, z.core.$strict>, z.ZodObject<{
        availability: z.ZodLiteral<"unavailable">;
        reason: z.ZodEnum<{
            api_unavailable: "api_unavailable";
            edition_unavailable: "edition_unavailable";
            temporarily_unavailable: "temporarily_unavailable";
        }>;
    }, z.core.$strict>, z.ZodObject<{
        availability: z.ZodLiteral<"unknown_version">;
        reason: z.ZodLiteral<"unrecognized_response">;
    }, z.core.$strict>], "availability">;
    formats: z.ZodArray<z.ZodObject<{
        format: z.ZodDiscriminatedUnion<[z.ZodObject<{
            kind: z.ZodLiteral<"known">;
            value: z.ZodEnum<{
                quicktime: "quicktime";
                mp4: "mp4";
                mxf: "mxf";
                wave: "wave";
                aiff: "aiff";
                dcp: "dcp";
                image_sequence: "image_sequence";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"unknown_version">;
            label: z.ZodString;
        }, z.core.$strict>], "kind">;
        label: z.ZodString;
        extension: z.ZodNullable<z.ZodString>;
        codecs: z.ZodArray<z.ZodObject<{
            codec: z.ZodDiscriminatedUnion<[z.ZodObject<{
                kind: z.ZodLiteral<"known">;
                value: z.ZodEnum<{
                    h264: "h264";
                    h265: "h265";
                    prores: "prores";
                    dnxhr: "dnxhr";
                    av1: "av1";
                    linear_pcm: "linear_pcm";
                    aac: "aac";
                    flac: "flac";
                    exr: "exr";
                    dpx: "dpx";
                    tiff: "tiff";
                    jpeg: "jpeg";
                }>;
            }, z.core.$strict>, z.ZodObject<{
                kind: z.ZodLiteral<"unknown_version">;
                label: z.ZodString;
            }, z.core.$strict>], "kind">;
            label: z.ZodString;
            resolutions: z.ZodArray<z.ZodObject<{
                width: z.ZodNumber;
                height: z.ZodNumber;
            }, z.core.$strict>>;
            resolutionSupport: z.ZodDiscriminatedUnion<[z.ZodObject<{
                availability: z.ZodLiteral<"supported">;
            }, z.core.$strict>, z.ZodObject<{
                availability: z.ZodLiteral<"unavailable">;
                reason: z.ZodEnum<{
                    api_unavailable: "api_unavailable";
                    edition_unavailable: "edition_unavailable";
                    temporarily_unavailable: "temporarily_unavailable";
                }>;
            }, z.core.$strict>, z.ZodObject<{
                availability: z.ZodLiteral<"unknown_version">;
                reason: z.ZodLiteral<"unrecognized_response">;
            }, z.core.$strict>], "availability">;
        }, z.core.$strict>>;
        codecSupport: z.ZodDiscriminatedUnion<[z.ZodObject<{
            availability: z.ZodLiteral<"supported">;
        }, z.core.$strict>, z.ZodObject<{
            availability: z.ZodLiteral<"unavailable">;
            reason: z.ZodEnum<{
                api_unavailable: "api_unavailable";
                edition_unavailable: "edition_unavailable";
                temporarily_unavailable: "temporarily_unavailable";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            availability: z.ZodLiteral<"unknown_version">;
            reason: z.ZodLiteral<"unrecognized_response">;
        }, z.core.$strict>], "availability">;
    }, z.core.$strict>>;
}, z.core.$strict>;
export declare const sdkRenderPresetsSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    support: z.ZodDiscriminatedUnion<[z.ZodObject<{
        availability: z.ZodLiteral<"supported">;
    }, z.core.$strict>, z.ZodObject<{
        availability: z.ZodLiteral<"unavailable">;
        reason: z.ZodEnum<{
            api_unavailable: "api_unavailable";
            edition_unavailable: "edition_unavailable";
            temporarily_unavailable: "temporarily_unavailable";
        }>;
    }, z.core.$strict>, z.ZodObject<{
        availability: z.ZodLiteral<"unknown_version">;
        reason: z.ZodLiteral<"unrecognized_response">;
    }, z.core.$strict>], "availability">;
    presets: z.ZodArray<z.ZodObject<{
        name: z.ZodString;
    }, z.core.$strict>>;
}, z.core.$strict>;
export declare const sdkRenderSettingsSnapshotSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    support: z.ZodDiscriminatedUnion<[z.ZodObject<{
        availability: z.ZodLiteral<"supported">;
    }, z.core.$strict>, z.ZodObject<{
        availability: z.ZodLiteral<"unavailable">;
        reason: z.ZodEnum<{
            api_unavailable: "api_unavailable";
            edition_unavailable: "edition_unavailable";
            temporarily_unavailable: "temporarily_unavailable";
        }>;
    }, z.core.$strict>, z.ZodObject<{
        availability: z.ZodLiteral<"unknown_version">;
        reason: z.ZodLiteral<"unrecognized_response">;
    }, z.core.$strict>], "availability">;
    format: z.ZodNullable<z.ZodDiscriminatedUnion<[z.ZodObject<{
        kind: z.ZodLiteral<"known">;
        value: z.ZodEnum<{
            quicktime: "quicktime";
            mp4: "mp4";
            mxf: "mxf";
            wave: "wave";
            aiff: "aiff";
            dcp: "dcp";
            image_sequence: "image_sequence";
        }>;
    }, z.core.$strict>, z.ZodObject<{
        kind: z.ZodLiteral<"unknown_version">;
        label: z.ZodString;
    }, z.core.$strict>], "kind">>;
    codec: z.ZodNullable<z.ZodDiscriminatedUnion<[z.ZodObject<{
        kind: z.ZodLiteral<"known">;
        value: z.ZodEnum<{
            h264: "h264";
            h265: "h265";
            prores: "prores";
            dnxhr: "dnxhr";
            av1: "av1";
            linear_pcm: "linear_pcm";
            aac: "aac";
            flac: "flac";
            exr: "exr";
            dpx: "dpx";
            tiff: "tiff";
            jpeg: "jpeg";
        }>;
    }, z.core.$strict>, z.ZodObject<{
        kind: z.ZodLiteral<"unknown_version">;
        label: z.ZodString;
    }, z.core.$strict>], "kind">>;
    resolution: z.ZodNullable<z.ZodObject<{
        width: z.ZodNumber;
        height: z.ZodNumber;
    }, z.core.$strict>>;
    frameRate: z.ZodNullable<z.ZodNumber>;
    mode: z.ZodNullable<z.ZodDiscriminatedUnion<[z.ZodObject<{
        kind: z.ZodLiteral<"known">;
        value: z.ZodEnum<{
            individual_clips: "individual_clips";
            single_clip: "single_clip";
        }>;
    }, z.core.$strict>, z.ZodObject<{
        kind: z.ZodLiteral<"unknown_version">;
        value: z.ZodString;
    }, z.core.$strict>], "kind">>;
    range: z.ZodDiscriminatedUnion<[z.ZodObject<{
        kind: z.ZodLiteral<"full_timeline">;
    }, z.core.$strict>, z.ZodObject<{
        kind: z.ZodLiteral<"custom">;
        markInFrame: z.ZodNumber;
        markOutFrame: z.ZodNumber;
    }, z.core.$strict>, z.ZodObject<{
        kind: z.ZodLiteral<"unknown">;
    }, z.core.$strict>], "kind">;
    exportVideo: z.ZodNullable<z.ZodBoolean>;
    exportAudio: z.ZodNullable<z.ZodBoolean>;
    exportSubtitles: z.ZodNullable<z.ZodBoolean>;
    customName: z.ZodNullable<z.ZodString>;
    queueCount: z.ZodNumber;
}, z.core.$strict>;
export declare const sdkArtifactContentChunkSchema: z.ZodObject<{
    artifactId: z.core.$ZodBranded<z.ZodString, "ArtifactId", "out">;
    offset: z.ZodNumber;
    totalSize: z.ZodNumber;
    bytesBase64: z.ZodString;
    eof: z.ZodBoolean;
    sha256: z.ZodString;
    availableUntil: z.ZodString;
}, z.core.$strict>;
export declare const sdkFusionSettingIngressSchema: z.ZodObject<{
    bytesBase64: z.ZodString;
}, z.core.$strict>;
export declare const sdkFusionSettingArtifactReceiptSchema: z.ZodObject<{
    artifactId: z.core.$ZodBranded<z.ZodString, "ArtifactId", "out">;
    mediaType: z.ZodLiteral<"application/x-fusion-setting">;
    byteCount: z.ZodNumber;
    sha256: z.ZodString;
}, z.core.$strict>;
export declare const sdkRenderJobSnapshotSchema: z.ZodObject<{
    id: z.core.$ZodBranded<z.ZodString, "SnapshotRenderJobId", "out">;
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    queueRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    index: z.ZodNumber;
    name: z.ZodString;
    statusSupport: z.ZodDiscriminatedUnion<[z.ZodObject<{
        availability: z.ZodLiteral<"supported">;
    }, z.core.$strict>, z.ZodObject<{
        availability: z.ZodLiteral<"unavailable">;
        reason: z.ZodEnum<{
            api_unavailable: "api_unavailable";
            edition_unavailable: "edition_unavailable";
            temporarily_unavailable: "temporarily_unavailable";
        }>;
    }, z.core.$strict>, z.ZodObject<{
        availability: z.ZodLiteral<"unknown_version">;
        reason: z.ZodLiteral<"unrecognized_response">;
    }, z.core.$strict>], "availability">;
    status: z.ZodDiscriminatedUnion<[z.ZodObject<{
        kind: z.ZodLiteral<"known">;
        value: z.ZodEnum<{
            completed: "completed";
            failed: "failed";
            queued: "queued";
            cancelled: "cancelled";
            rendering: "rendering";
        }>;
    }, z.core.$strict>, z.ZodObject<{
        kind: z.ZodLiteral<"unknown_version">;
        value: z.ZodString;
    }, z.core.$strict>], "kind">;
    progressPercent: z.ZodNullable<z.ZodNumber>;
}, z.core.$strict>;
export declare const sdkRenderQueuePageSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    queueRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    support: z.ZodDiscriminatedUnion<[z.ZodObject<{
        availability: z.ZodLiteral<"supported">;
    }, z.core.$strict>, z.ZodObject<{
        availability: z.ZodLiteral<"unavailable">;
        reason: z.ZodEnum<{
            api_unavailable: "api_unavailable";
            edition_unavailable: "edition_unavailable";
            temporarily_unavailable: "temporarily_unavailable";
        }>;
    }, z.core.$strict>, z.ZodObject<{
        availability: z.ZodLiteral<"unknown_version">;
        reason: z.ZodLiteral<"unrecognized_response">;
    }, z.core.$strict>], "availability">;
    cursor: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "RenderQueueCursor", "out">>;
    offset: z.ZodNumber;
    pageSize: z.ZodNumber;
    jobs: z.ZodArray<z.ZodObject<{
        id: z.core.$ZodBranded<z.ZodString, "SnapshotRenderJobId", "out">;
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        queueRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        index: z.ZodNumber;
        name: z.ZodString;
        statusSupport: z.ZodDiscriminatedUnion<[z.ZodObject<{
            availability: z.ZodLiteral<"supported">;
        }, z.core.$strict>, z.ZodObject<{
            availability: z.ZodLiteral<"unavailable">;
            reason: z.ZodEnum<{
                api_unavailable: "api_unavailable";
                edition_unavailable: "edition_unavailable";
                temporarily_unavailable: "temporarily_unavailable";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            availability: z.ZodLiteral<"unknown_version">;
            reason: z.ZodLiteral<"unrecognized_response">;
        }, z.core.$strict>], "availability">;
        status: z.ZodDiscriminatedUnion<[z.ZodObject<{
            kind: z.ZodLiteral<"known">;
            value: z.ZodEnum<{
                completed: "completed";
                failed: "failed";
                queued: "queued";
                cancelled: "cancelled";
                rendering: "rendering";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"unknown_version">;
            value: z.ZodString;
        }, z.core.$strict>], "kind">;
        progressPercent: z.ZodNullable<z.ZodNumber>;
    }, z.core.$strict>>;
    nextCursor: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "RenderQueueCursor", "out">>;
    total: z.ZodNumber;
}, z.core.$strict>;
export declare const sdkRenderJobStatusSnapshotSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    queueRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    support: z.ZodDiscriminatedUnion<[z.ZodObject<{
        availability: z.ZodLiteral<"supported">;
    }, z.core.$strict>, z.ZodObject<{
        availability: z.ZodLiteral<"unavailable">;
        reason: z.ZodEnum<{
            api_unavailable: "api_unavailable";
            edition_unavailable: "edition_unavailable";
            temporarily_unavailable: "temporarily_unavailable";
        }>;
    }, z.core.$strict>, z.ZodObject<{
        availability: z.ZodLiteral<"unknown_version">;
        reason: z.ZodLiteral<"unrecognized_response">;
    }, z.core.$strict>], "availability">;
    job: z.ZodObject<{
        id: z.core.$ZodBranded<z.ZodString, "SnapshotRenderJobId", "out">;
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        queueRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        index: z.ZodNumber;
        name: z.ZodString;
        statusSupport: z.ZodDiscriminatedUnion<[z.ZodObject<{
            availability: z.ZodLiteral<"supported">;
        }, z.core.$strict>, z.ZodObject<{
            availability: z.ZodLiteral<"unavailable">;
            reason: z.ZodEnum<{
                api_unavailable: "api_unavailable";
                edition_unavailable: "edition_unavailable";
                temporarily_unavailable: "temporarily_unavailable";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            availability: z.ZodLiteral<"unknown_version">;
            reason: z.ZodLiteral<"unrecognized_response">;
        }, z.core.$strict>], "availability">;
        status: z.ZodDiscriminatedUnion<[z.ZodObject<{
            kind: z.ZodLiteral<"known">;
            value: z.ZodEnum<{
                completed: "completed";
                failed: "failed";
                queued: "queued";
                cancelled: "cancelled";
                rendering: "rendering";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"unknown_version">;
            value: z.ZodString;
        }, z.core.$strict>], "kind">;
        progressPercent: z.ZodNullable<z.ZodNumber>;
    }, z.core.$strict>;
}, z.core.$strict>;
export declare const sdkVoiceCatalogRequestSchema: z.ZodObject<{
    search: z.ZodNullable<z.ZodString>;
    pageToken: z.ZodNullable<z.ZodString>;
    limit: z.ZodNumber;
}, z.core.$strict>;
export declare const sdkVoiceCatalogPageSchema: z.ZodObject<{
    voices: z.ZodArray<z.ZodObject<{
        voiceId: z.ZodString;
        name: z.ZodString;
        description: z.ZodNullable<z.ZodString>;
        language: z.ZodNullable<z.ZodString>;
        accent: z.ZodNullable<z.ZodString>;
    }, z.core.$strict>>;
    hasMore: z.ZodBoolean;
    nextPageToken: z.ZodNullable<z.ZodString>;
}, z.core.$strict>;
export declare const sdkManagedTimelinePreviewRequestSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
    revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    ownershipId: z.ZodString;
    scope: z.ZodDiscriminatedUnion<[z.ZodObject<{
        kind: z.ZodLiteral<"whole_timeline">;
    }, z.core.$strict>, z.ZodObject<{
        kind: z.ZodLiteral<"region">;
        startFrame: z.ZodNumber;
        endExclusiveFrame: z.ZodNumber;
    }, z.core.$strict>], "kind">;
    timelineFrameRate: z.ZodObject<{
        numerator: z.ZodNumber;
        denominator: z.ZodNumber;
        nominalTimebase: z.ZodNumber;
    }, z.core.$strict>;
    elements: z.ZodArray<z.ZodObject<{
        key: z.ZodString;
        assetId: z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">;
        assetName: z.ZodString;
        assetRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        videoTrack: z.ZodNumber;
        audioTrack: z.ZodNullable<z.ZodNumber>;
        atFrame: z.ZodNumber;
        sourceStartFrame: z.ZodNumber;
        sourceEndExclusiveFrame: z.ZodNumber;
        sourceFrameRate: z.ZodObject<{
            numerator: z.ZodNumber;
            denominator: z.ZodNumber;
            nominalTimebase: z.ZodNumber;
        }, z.core.$strict>;
        linkedAudio: z.ZodEnum<{
            include: "include";
            exclude: "exclude";
        }>;
        adoptTimelineItemId: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>;
    }, z.core.$strict>>;
}, z.core.$strict>;
export declare const sdkManagedTimelineExportSelectionSchema: z.ZodDiscriminatedUnion<[z.ZodObject<{
    kind: z.ZodLiteral<"existing_ownership">;
}, z.core.$strict>, z.ZodObject<{
    kind: z.ZodLiteral<"adopt">;
    clips: z.ZodArray<z.ZodObject<{
        key: z.ZodString;
        timelineItemId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
    }, z.core.$strict>>;
}, z.core.$strict>], "kind">;
export declare const sdkManagedTimelineExportRequestSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
    revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    ownershipId: z.ZodString;
    scope: z.ZodDiscriminatedUnion<[z.ZodObject<{
        kind: z.ZodLiteral<"whole_timeline">;
    }, z.core.$strict>, z.ZodObject<{
        kind: z.ZodLiteral<"region">;
        startFrame: z.ZodNumber;
        endExclusiveFrame: z.ZodNumber;
    }, z.core.$strict>], "kind">;
    selection: z.ZodDiscriminatedUnion<[z.ZodObject<{
        kind: z.ZodLiteral<"existing_ownership">;
    }, z.core.$strict>, z.ZodObject<{
        kind: z.ZodLiteral<"adopt">;
        clips: z.ZodArray<z.ZodObject<{
            key: z.ZodString;
            timelineItemId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
        }, z.core.$strict>>;
    }, z.core.$strict>], "kind">;
}, z.core.$strict>;
export declare const sdkManagedTimelineDriftSchema: z.ZodObject<{
    kind: z.ZodEnum<{
        create: "create";
        update: "update";
        preserve: "preserve";
        remove: "remove";
    }>;
    key: z.ZodString;
    timelineItemId: z.ZodOptional<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>;
    summary: z.ZodString;
}, z.core.$strict>;
export declare const sdkManagedTimelineBlockerSchema: z.ZodObject<{
    code: z.ZodEnum<{
        stale_revision: "stale_revision";
        ambiguous_identity: "ambiguous_identity";
        scope_crossing: "scope_crossing";
        unsupported_change: "unsupported_change";
        protected_state_unproven: "protected_state_unproven";
        ownership_overlap: "ownership_overlap";
    }>;
    key: z.ZodOptional<z.ZodString>;
    message: z.ZodString;
}, z.core.$strict>;
export declare const sdkManagedTimelinePreviewSchema: z.ZodObject<{
    status: z.ZodEnum<{
        blocked: "blocked";
        no_change: "no_change";
        ready: "ready";
    }>;
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
    revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    ownershipId: z.ZodString;
    scope: z.ZodDiscriminatedUnion<[z.ZodObject<{
        kind: z.ZodLiteral<"whole_timeline">;
    }, z.core.$strict>, z.ZodObject<{
        kind: z.ZodLiteral<"region">;
        startFrame: z.ZodNumber;
        endExclusiveFrame: z.ZodNumber;
    }, z.core.$strict>], "kind">;
    desiredStateDigest: z.ZodString;
    contextDigest: z.ZodString;
    protectedStateDigest: z.ZodString;
    previewDigest: z.ZodString;
    ownershipGeneration: z.ZodNumber;
    policyRevision: z.ZodString;
    capabilityDigest: z.ZodString;
    drift: z.ZodArray<z.ZodObject<{
        kind: z.ZodEnum<{
            create: "create";
            update: "update";
            preserve: "preserve";
            remove: "remove";
        }>;
        key: z.ZodString;
        timelineItemId: z.ZodOptional<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>;
        summary: z.ZodString;
    }, z.core.$strict>>;
    blockers: z.ZodArray<z.ZodObject<{
        code: z.ZodEnum<{
            stale_revision: "stale_revision";
            ambiguous_identity: "ambiguous_identity";
            scope_crossing: "scope_crossing";
            unsupported_change: "unsupported_change";
            protected_state_unproven: "protected_state_unproven";
            ownership_overlap: "ownership_overlap";
        }>;
        key: z.ZodOptional<z.ZodString>;
        message: z.ZodString;
    }, z.core.$strict>>;
}, z.core.$strict>;
export declare const sdkManagedTimelineExportSchema: z.ZodDiscriminatedUnion<[z.ZodObject<{
    status: z.ZodLiteral<"ready">;
    dialect: z.ZodLiteral<"cutagent.managed-timeline">;
    version: z.ZodLiteral<1>;
    program: z.ZodObject<{
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        ownershipId: z.ZodString;
        scope: z.ZodDiscriminatedUnion<[z.ZodObject<{
            kind: z.ZodLiteral<"whole_timeline">;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"region">;
            startFrame: z.ZodNumber;
            endExclusiveFrame: z.ZodNumber;
        }, z.core.$strict>], "kind">;
        timelineFrameRate: z.ZodObject<{
            numerator: z.ZodNumber;
            denominator: z.ZodNumber;
            nominalTimebase: z.ZodNumber;
        }, z.core.$strict>;
        elements: z.ZodArray<z.ZodObject<{
            key: z.ZodString;
            assetId: z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">;
            assetName: z.ZodString;
            assetRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            videoTrack: z.ZodNumber;
            audioTrack: z.ZodNullable<z.ZodNumber>;
            atFrame: z.ZodNumber;
            sourceStartFrame: z.ZodNumber;
            sourceEndExclusiveFrame: z.ZodNumber;
            sourceFrameRate: z.ZodObject<{
                numerator: z.ZodNumber;
                denominator: z.ZodNumber;
                nominalTimebase: z.ZodNumber;
            }, z.core.$strict>;
            linkedAudio: z.ZodEnum<{
                include: "include";
                exclude: "exclude";
            }>;
            adoptTimelineItemId: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>;
        }, z.core.$strict>>;
    }, z.core.$strict>;
    assets: z.ZodArray<z.ZodObject<{
        id: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">>;
        snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolItemId", "out">;
        folderSnapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolFolderId", "out">;
        snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        name: z.ZodString;
        kind: z.ZodEnum<{
            unknown: "unknown";
            timeline: "timeline";
            multicam: "multicam";
            fusion_composition: "fusion_composition";
            video: "video";
            audio: "audio";
            still: "still";
            compound: "compound";
            generator: "generator";
        }>;
        selected: z.ZodBoolean;
        sourceFileName: z.ZodNullable<z.ZodString>;
        duration: z.ZodNullable<z.ZodString>;
        resolution: z.ZodNullable<z.ZodString>;
        frameRate: z.ZodNullable<z.ZodString>;
        startTimecode: z.ZodNullable<z.ZodString>;
        metadata: z.ZodArray<z.ZodObject<{
            key: z.ZodEnum<{
                description: "description";
                comments: "comments";
                keywords: "keywords";
                shot: "shot";
                scene: "scene";
                take: "take";
                angle: "angle";
                camera: "camera";
                reel: "reel";
                dateRecorded: "dateRecorded";
                goodTake: "goodTake";
                clipColor: "clipColor";
            }>;
            value: z.ZodString;
        }, z.core.$strict>>;
    }, z.core.$strict>>;
    coverage: z.ZodObject<{
        represented: z.ZodTuple<[z.ZodLiteral<"clip_placement/v1">], null>;
        preservedButNotRepresented: z.ZodTuple<[z.ZodLiteral<"unmanaged_clips">, z.ZodLiteral<"track_properties">, z.ZodLiteral<"markers">, z.ZodLiteral<"fusion">, z.ZodLiteral<"color">, z.ZodLiteral<"fairlight">, z.ZodLiteral<"retime">, z.ZodLiteral<"transitions">, z.ZodLiteral<"effects">, z.ZodLiteral<"captions">], null>;
        protectedStateDigest: z.ZodString;
    }, z.core.$strict>;
    blockers: z.ZodTuple<[], null>;
}, z.core.$strict>, z.ZodObject<{
    status: z.ZodLiteral<"blocked">;
    dialect: z.ZodLiteral<"cutagent.managed-timeline">;
    version: z.ZodLiteral<1>;
    document: z.ZodNull;
    blockers: z.ZodArray<z.ZodObject<{
        code: z.ZodEnum<{
            stale_revision: "stale_revision";
            ambiguous_identity: "ambiguous_identity";
            scope_crossing: "scope_crossing";
            unsupported_change: "unsupported_change";
            protected_state_unproven: "protected_state_unproven";
            ownership_overlap: "ownership_overlap";
        }>;
        key: z.ZodOptional<z.ZodString>;
        message: z.ZodString;
    }, z.core.$strict>>;
}, z.core.$strict>], "status">;
export declare const sdkRuntimeReadRequestSchema: z.ZodDiscriminatedUnion<[z.ZodObject<{
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    sessionId: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
    deadlineAtMs: z.ZodNumber;
    operation: z.ZodLiteral<"voice.catalog">;
    query: z.ZodObject<{
        search: z.ZodNullable<z.ZodString>;
        pageToken: z.ZodNullable<z.ZodString>;
        limit: z.ZodNumber;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    sessionId: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
    deadlineAtMs: z.ZodNumber;
    operation: z.ZodLiteral<"project.context">;
}, z.core.$strict>, z.ZodObject<{
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    sessionId: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
    deadlineAtMs: z.ZodNumber;
    operation: z.ZodLiteral<"project.current">;
}, z.core.$strict>, z.ZodObject<{
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    sessionId: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
    deadlineAtMs: z.ZodNumber;
    operation: z.ZodLiteral<"timeline.current">;
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
}, z.core.$strict>, z.ZodObject<{
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    sessionId: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
    deadlineAtMs: z.ZodNumber;
    operation: z.ZodLiteral<"timeline.snapshot">;
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
}, z.core.$strict>, z.ZodObject<{
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    sessionId: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
    deadlineAtMs: z.ZodNumber;
    operation: z.ZodLiteral<"timeline.retime">;
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
    timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    target: z.ZodObject<{
        snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotTimelineItemId", "out">;
        snapshotTrackId: z.core.$ZodBranded<z.ZodString, "SnapshotTrackId", "out">;
        snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        name: z.ZodString;
        recordRange: z.ZodObject<{
            domain: z.ZodLiteral<"timeline_record_range">;
            unit: z.ZodLiteral<"frames">;
            start: z.ZodNumber;
            endExclusive: z.ZodNumber;
        }, z.core.$strict>;
        duration: z.ZodObject<{
            domain: z.ZodLiteral<"duration">;
            value: z.ZodObject<{
                kind: z.ZodLiteral<"frames">;
                value: z.ZodNumber;
            }, z.core.$strict>;
        }, z.core.$strict>;
        retimeSource: z.ZodOptional<z.ZodNullable<z.ZodObject<{
            availableRange: z.ZodObject<{
                domain: z.ZodLiteral<"source_range">;
                unit: z.ZodLiteral<"frames">;
                start: z.ZodNumber;
                endExclusive: z.ZodNumber;
            }, z.core.$strict>;
            originFrame: z.ZodNumber;
        }, z.core.$strict>>>;
        sourceFrameRate: z.ZodNullable<z.ZodObject<{
            numerator: z.ZodNumber;
            denominator: z.ZodNumber;
            nominalTimebase: z.ZodNumber;
        }, z.core.$strict>>;
        mediaPoolItemId: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">>;
        id: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
        sourceRange: z.ZodObject<{
            domain: z.ZodLiteral<"source_range">;
            unit: z.ZodLiteral<"frames">;
            start: z.ZodNumber;
            endExclusive: z.ZodNumber;
        }, z.core.$strict>;
        linkedItemIds: z.ZodArray<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>;
        trackType: z.ZodEnum<{
            video: "video";
            audio: "audio";
        }>;
        trackIndex: z.ZodNumber;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    sessionId: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
    deadlineAtMs: z.ZodNumber;
    operation: z.ZodLiteral<"timeline.managed.preview">;
    program: z.ZodObject<{
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        ownershipId: z.ZodString;
        scope: z.ZodDiscriminatedUnion<[z.ZodObject<{
            kind: z.ZodLiteral<"whole_timeline">;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"region">;
            startFrame: z.ZodNumber;
            endExclusiveFrame: z.ZodNumber;
        }, z.core.$strict>], "kind">;
        timelineFrameRate: z.ZodObject<{
            numerator: z.ZodNumber;
            denominator: z.ZodNumber;
            nominalTimebase: z.ZodNumber;
        }, z.core.$strict>;
        elements: z.ZodArray<z.ZodObject<{
            key: z.ZodString;
            assetId: z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">;
            assetName: z.ZodString;
            assetRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            videoTrack: z.ZodNumber;
            audioTrack: z.ZodNullable<z.ZodNumber>;
            atFrame: z.ZodNumber;
            sourceStartFrame: z.ZodNumber;
            sourceEndExclusiveFrame: z.ZodNumber;
            sourceFrameRate: z.ZodObject<{
                numerator: z.ZodNumber;
                denominator: z.ZodNumber;
                nominalTimebase: z.ZodNumber;
            }, z.core.$strict>;
            linkedAudio: z.ZodEnum<{
                include: "include";
                exclude: "exclude";
            }>;
            adoptTimelineItemId: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>;
        }, z.core.$strict>>;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    sessionId: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
    deadlineAtMs: z.ZodNumber;
    operation: z.ZodLiteral<"timeline.managed.export">;
    request: z.ZodObject<{
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        ownershipId: z.ZodString;
        scope: z.ZodDiscriminatedUnion<[z.ZodObject<{
            kind: z.ZodLiteral<"whole_timeline">;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"region">;
            startFrame: z.ZodNumber;
            endExclusiveFrame: z.ZodNumber;
        }, z.core.$strict>], "kind">;
        selection: z.ZodDiscriminatedUnion<[z.ZodObject<{
            kind: z.ZodLiteral<"existing_ownership">;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"adopt">;
            clips: z.ZodArray<z.ZodObject<{
                key: z.ZodString;
                timelineItemId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
            }, z.core.$strict>>;
        }, z.core.$strict>], "kind">;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    sessionId: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
    deadlineAtMs: z.ZodNumber;
    operation: z.ZodLiteral<"fusion.compositions">;
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
    timelineItemId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
    expectedRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
}, z.core.$strict>, z.ZodObject<{
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    sessionId: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
    deadlineAtMs: z.ZodNumber;
    operation: z.ZodLiteral<"mediaPool.page">;
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    offset: z.ZodNumber;
    pageSize: z.ZodNumber;
    expectedRevision: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "Revision", "out">>;
    search: z.ZodNullable<z.ZodObject<{
        query: z.ZodString;
        match: z.ZodEnum<{
            exact: "exact";
            contains: "contains";
        }>;
        fields: z.ZodArray<z.ZodEnum<{
            name: "name";
            metadata: "metadata";
            sourceFileName: "sourceFileName";
        }>>;
    }, z.core.$strict>>;
}, z.core.$strict>, z.ZodObject<{
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    sessionId: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
    deadlineAtMs: z.ZodNumber;
    operation: z.ZodLiteral<"color.current">;
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
    nodeStackLayerIndex: z.ZodNumber;
}, z.core.$strict>, z.ZodObject<{
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    sessionId: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
    deadlineAtMs: z.ZodNumber;
    operation: z.ZodLiteral<"render.discovery">;
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
}, z.core.$strict>, z.ZodObject<{
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    sessionId: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
    deadlineAtMs: z.ZodNumber;
    operation: z.ZodLiteral<"render.presets">;
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
}, z.core.$strict>, z.ZodObject<{
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    sessionId: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
    deadlineAtMs: z.ZodNumber;
    operation: z.ZodLiteral<"render.settings">;
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
}, z.core.$strict>, z.ZodObject<{
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    sessionId: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
    deadlineAtMs: z.ZodNumber;
    operation: z.ZodLiteral<"render.queue">;
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    pageSize: z.ZodNumber;
    cursor: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "RenderQueueCursor", "out">>;
}, z.core.$strict>, z.ZodObject<{
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    sessionId: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
    deadlineAtMs: z.ZodNumber;
    operation: z.ZodLiteral<"render.job_status">;
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    queueRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    jobId: z.core.$ZodBranded<z.ZodString, "SnapshotRenderJobId", "out">;
}, z.core.$strict>, z.ZodObject<{
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    sessionId: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
    deadlineAtMs: z.ZodNumber;
    operation: z.ZodLiteral<"artifact.content">;
    artifactId: z.core.$ZodBranded<z.ZodString, "ArtifactId", "out">;
    offset: z.ZodNumber;
    length: z.ZodNumber;
}, z.core.$strict>, z.ZodObject<{
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    sessionId: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
    deadlineAtMs: z.ZodNumber;
    operation: z.ZodLiteral<"artifact.fusion_setting.publish">;
    setting: z.ZodObject<{
        bytesBase64: z.ZodString;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    sessionId: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
    deadlineAtMs: z.ZodNumber;
    operation: z.ZodLiteral<"timeline.edit.preview">;
    intent: z.ZodDiscriminatedUnion<[z.ZodObject<{
        action: z.ZodEnum<{
            insert: "insert";
            overwrite: "overwrite";
        }>;
        placement: z.ZodDefault<z.ZodEnum<{
            video: "video";
            audio: "audio";
        }>>;
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        source: z.ZodObject<{
            id: z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">;
            name: z.ZodString;
            snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        }, z.core.$strict>;
        sourceRange: z.ZodObject<{
            domain: z.ZodLiteral<"source_range" | "timeline_record_range">;
            unit: z.ZodLiteral<"frames">;
            start: z.ZodNumber;
            endExclusive: z.ZodNumber;
        }, z.core.$strict>;
        at: z.ZodObject<{
            domain: z.ZodLiteral<"timeline_record">;
            value: z.ZodObject<{
                kind: z.ZodLiteral<"frames">;
                value: z.ZodNumber;
            }, z.core.$strict>;
        }, z.core.$strict>;
        videoTrackIndex: z.ZodNullable<z.ZodNumber>;
        audioTrackIndex: z.ZodNullable<z.ZodNumber>;
        linkedAudio: z.ZodEnum<{
            include: "include";
            exclude: "exclude";
        }>;
    }, z.core.$strict>, z.ZodObject<{
        action: z.ZodLiteral<"trim">;
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
        clipName: z.ZodString;
        trackIndex: z.ZodNumber;
        currentRecordRange: z.ZodObject<{
            domain: z.ZodLiteral<"source_range" | "timeline_record_range">;
            unit: z.ZodLiteral<"frames">;
            start: z.ZodNumber;
            endExclusive: z.ZodNumber;
        }, z.core.$strict>;
        headFrames: z.ZodNumber;
        tailFrames: z.ZodNumber;
        linkedAudio: z.ZodEnum<{
            exclude: "exclude";
            preserve: "preserve";
        }>;
    }, z.core.$strict>, z.ZodObject<{
        action: z.ZodLiteral<"remove">;
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
        clipName: z.ZodString;
        trackType: z.ZodEnum<{
            video: "video";
            audio: "audio";
            subtitle: "subtitle";
        }>;
        trackIndex: z.ZodNumber;
        currentRecordRange: z.ZodObject<{
            domain: z.ZodLiteral<"source_range" | "timeline_record_range">;
            unit: z.ZodLiteral<"frames">;
            start: z.ZodNumber;
            endExclusive: z.ZodNumber;
        }, z.core.$strict>;
        linkedItems: z.ZodLiteral<"exclude">;
    }, z.core.$strict>], "action">;
}, z.core.$strict>, z.ZodObject<{
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    sessionId: z.core.$ZodBranded<z.ZodString, "SdkSessionId", "out">;
    deadlineAtMs: z.ZodNumber;
    operation: z.ZodLiteral<"multicam.inspect">;
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    mediaPoolItemId: z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">;
    multicamName: z.ZodString;
    expectedRevision: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "Revision", "out">>;
}, z.core.$strict>], "operation">;
export declare const sdkRuntimeReadSuccessSchema: z.ZodDiscriminatedUnion<[z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"voice.catalog">;
    data: z.ZodObject<{
        voices: z.ZodArray<z.ZodObject<{
            voiceId: z.ZodString;
            name: z.ZodString;
            description: z.ZodNullable<z.ZodString>;
            language: z.ZodNullable<z.ZodString>;
            accent: z.ZodNullable<z.ZodString>;
        }, z.core.$strict>>;
        hasMore: z.ZodBoolean;
        nextPageToken: z.ZodNullable<z.ZodString>;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"project.context">;
    data: z.ZodObject<{
        library: z.ZodNullable<z.ZodObject<{
            name: z.ZodString;
            kind: z.ZodEnum<{
                disk: "disk";
                postgresql: "postgresql";
            }>;
        }, z.core.$strict>>;
        project: z.ZodNullable<z.ZodObject<{
            id: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "ProjectId", "out">>;
            name: z.ZodString;
        }, z.core.$strict>>;
        timeline: z.ZodNullable<z.ZodObject<{
            id: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "TimelineId", "out">>;
            name: z.ZodString;
        }, z.core.$strict>>;
        projectRevision: z.ZodDiscriminatedUnion<[z.ZodObject<{
            status: z.ZodLiteral<"available">;
            revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        }, z.core.$strict>, z.ZodObject<{
            status: z.ZodLiteral<"unavailable">;
        }, z.core.$strict>], "status">;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"project.current">;
    data: z.ZodObject<{
        id: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        name: z.ZodString;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"timeline.current">;
    data: z.ZodObject<{
        id: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        name: z.ZodString;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"timeline.snapshot">;
    data: z.ZodObject<{
        project: z.ZodObject<{
            id: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            name: z.ZodString;
        }, z.core.$strict>;
        timeline: z.ZodObject<{
            id: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
            projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            name: z.ZodString;
        }, z.core.$strict>;
        revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        frameRate: z.ZodObject<{
            numerator: z.ZodNumber;
            denominator: z.ZodNumber;
            nominalTimebase: z.ZodNumber;
        }, z.core.$strict>;
        start: z.ZodObject<{
            domain: z.ZodLiteral<"timeline_record">;
            value: z.ZodObject<{
                kind: z.ZodLiteral<"frames">;
                value: z.ZodNumber;
            }, z.core.$strict>;
        }, z.core.$strict>;
        tracks: z.ZodArray<z.ZodObject<{
            snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotTrackId", "out">;
            timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
            snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            type: z.ZodEnum<{
                video: "video";
                audio: "audio";
                subtitle: "subtitle";
            }>;
            index: z.ZodNumber;
            name: z.ZodString;
            enabled: z.ZodNullable<z.ZodBoolean>;
            locked: z.ZodNullable<z.ZodBoolean>;
            clips: z.ZodArray<z.ZodObject<{
                id: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>;
                snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotTimelineItemId", "out">;
                snapshotTrackId: z.core.$ZodBranded<z.ZodString, "SnapshotTrackId", "out">;
                snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
                name: z.ZodString;
                recordRange: z.ZodObject<{
                    domain: z.ZodLiteral<"timeline_record_range">;
                    unit: z.ZodLiteral<"frames">;
                    start: z.ZodNumber;
                    endExclusive: z.ZodNumber;
                }, z.core.$strict>;
                duration: z.ZodObject<{
                    domain: z.ZodLiteral<"duration">;
                    value: z.ZodObject<{
                        kind: z.ZodLiteral<"frames">;
                        value: z.ZodNumber;
                    }, z.core.$strict>;
                }, z.core.$strict>;
                sourceRange: z.ZodNullable<z.ZodObject<{
                    domain: z.ZodLiteral<"source_range">;
                    unit: z.ZodLiteral<"frames">;
                    start: z.ZodNumber;
                    endExclusive: z.ZodNumber;
                }, z.core.$strict>>;
                retimeSource: z.ZodOptional<z.ZodNullable<z.ZodObject<{
                    availableRange: z.ZodObject<{
                        domain: z.ZodLiteral<"source_range">;
                        unit: z.ZodLiteral<"frames">;
                        start: z.ZodNumber;
                        endExclusive: z.ZodNumber;
                    }, z.core.$strict>;
                    originFrame: z.ZodNumber;
                }, z.core.$strict>>>;
                sourceFrameRate: z.ZodNullable<z.ZodObject<{
                    numerator: z.ZodNumber;
                    denominator: z.ZodNumber;
                    nominalTimebase: z.ZodNumber;
                }, z.core.$strict>>;
                mediaPoolItemId: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">>;
                linkedItemIds: z.ZodNullable<z.ZodArray<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>>;
            }, z.core.$strict>>;
        }, z.core.$strict>>;
        markers: z.ZodArray<z.ZodObject<{
            id: z.core.$ZodBranded<z.ZodString, "MarkerId", "out">;
            snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            position: z.ZodObject<{
                domain: z.ZodLiteral<"timeline_record">;
                value: z.ZodObject<{
                    kind: z.ZodLiteral<"frames">;
                    value: z.ZodNumber;
                }, z.core.$strict>;
            }, z.core.$strict>;
            color: z.ZodString;
            name: z.ZodString;
            note: z.ZodString;
            duration: z.ZodObject<{
                domain: z.ZodLiteral<"duration">;
                value: z.ZodObject<{
                    kind: z.ZodLiteral<"frames">;
                    value: z.ZodNumber;
                }, z.core.$strict>;
            }, z.core.$strict>;
        }, z.core.$strict>>;
        fairlight: z.ZodDefault<z.ZodDiscriminatedUnion<[z.ZodObject<{
            status: z.ZodLiteral<"available">;
            tracks: z.ZodArray<z.ZodObject<{
                trackIndex: z.ZodNumber;
                levelDb: z.ZodDiscriminatedUnion<[z.ZodObject<{
                    status: z.ZodLiteral<"available">;
                    value: z.ZodNumber;
                }, z.core.$strict>, z.ZodObject<{
                    status: z.ZodLiteral<"unavailable">;
                    reason: z.ZodEnum<{
                        readback_unavailable: "readback_unavailable";
                        not_exposed_by_runtime: "not_exposed_by_runtime";
                    }>;
                }, z.core.$strict>], "status">;
                pan: z.ZodDiscriminatedUnion<[z.ZodObject<{
                    status: z.ZodLiteral<"available">;
                    value: z.ZodNumber;
                }, z.core.$strict>, z.ZodObject<{
                    status: z.ZodLiteral<"unavailable">;
                    reason: z.ZodEnum<{
                        readback_unavailable: "readback_unavailable";
                        not_exposed_by_runtime: "not_exposed_by_runtime";
                    }>;
                }, z.core.$strict>], "status">;
            }, z.core.$strict>>;
            clips: z.ZodDefault<z.ZodArray<z.ZodObject<{
                clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
                trackIndex: z.ZodNumber;
                gainDb: z.ZodDiscriminatedUnion<[z.ZodObject<{
                    status: z.ZodLiteral<"available">;
                    value: z.ZodNumber;
                }, z.core.$strict>, z.ZodObject<{
                    status: z.ZodLiteral<"unavailable">;
                    reason: z.ZodEnum<{
                        readback_unavailable: "readback_unavailable";
                        not_exposed_by_runtime: "not_exposed_by_runtime";
                    }>;
                }, z.core.$strict>], "status">;
                pan: z.ZodDiscriminatedUnion<[z.ZodObject<{
                    status: z.ZodLiteral<"available">;
                    value: z.ZodNumber;
                }, z.core.$strict>, z.ZodObject<{
                    status: z.ZodLiteral<"unavailable">;
                    reason: z.ZodEnum<{
                        readback_unavailable: "readback_unavailable";
                        not_exposed_by_runtime: "not_exposed_by_runtime";
                    }>;
                }, z.core.$strict>], "status">;
                fadeInFrames: z.ZodDiscriminatedUnion<[z.ZodObject<{
                    status: z.ZodLiteral<"available">;
                    value: z.ZodNumber;
                }, z.core.$strict>, z.ZodObject<{
                    status: z.ZodLiteral<"unavailable">;
                    reason: z.ZodEnum<{
                        readback_unavailable: "readback_unavailable";
                        not_exposed_by_runtime: "not_exposed_by_runtime";
                    }>;
                }, z.core.$strict>], "status">;
                fadeOutFrames: z.ZodDiscriminatedUnion<[z.ZodObject<{
                    status: z.ZodLiteral<"available">;
                    value: z.ZodNumber;
                }, z.core.$strict>, z.ZodObject<{
                    status: z.ZodLiteral<"unavailable">;
                    reason: z.ZodEnum<{
                        readback_unavailable: "readback_unavailable";
                        not_exposed_by_runtime: "not_exposed_by_runtime";
                    }>;
                }, z.core.$strict>], "status">;
            }, z.core.$strict>>>;
            buses: z.ZodDiscriminatedUnion<[z.ZodObject<{
                status: z.ZodLiteral<"available">;
                buses: z.ZodArray<z.ZodObject<{
                    name: z.ZodString;
                    kind: z.ZodEnum<{
                        bus: "bus";
                        main: "main";
                    }>;
                }, z.core.$strict>>;
            }, z.core.$strict>, z.ZodObject<{
                status: z.ZodLiteral<"unavailable">;
                reason: z.ZodEnum<{
                    readback_unavailable: "readback_unavailable";
                    not_exposed_by_runtime: "not_exposed_by_runtime";
                }>;
                buses: z.ZodTuple<[], null>;
            }, z.core.$strict>], "status">;
        }, z.core.$strict>, z.ZodObject<{
            status: z.ZodLiteral<"unavailable">;
            reason: z.ZodEnum<{
                readback_unavailable: "readback_unavailable";
                not_exposed_by_runtime: "not_exposed_by_runtime";
            }>;
            tracks: z.ZodTuple<[], null>;
            buses: z.ZodObject<{
                status: z.ZodLiteral<"unavailable">;
                reason: z.ZodEnum<{
                    readback_unavailable: "readback_unavailable";
                    not_exposed_by_runtime: "not_exposed_by_runtime";
                }>;
                buses: z.ZodTuple<[], null>;
            }, z.core.$strict>;
        }, z.core.$strict>], "status">>;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"timeline.retime">;
    data: z.ZodObject<{
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        timelineItemId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
        durationFrames: z.ZodNumber;
        speedMultiplier: z.ZodNumber;
        reversed: z.ZodBoolean;
        frozen: z.ZodBoolean;
        points: z.ZodArray<z.ZodObject<{
            recordFrame: z.ZodNumber;
            recordPositionFrames: z.ZodNumber;
            sourceFrame: z.ZodNumber;
            incomingControl: z.ZodObject<{
                recordPositionFrames: z.ZodNumber;
                sourceFrame: z.ZodNumber;
            }, z.core.$strict>;
            outgoingControl: z.ZodObject<{
                recordPositionFrames: z.ZodNumber;
                sourceFrame: z.ZodNumber;
            }, z.core.$strict>;
            speed: z.ZodNumber;
            interpolation: z.ZodEnum<{
                linear: "linear";
                bezier: "bezier";
                hold: "hold";
            }>;
        }, z.core.$strict>>;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"fusion.compositions">;
    data: z.ZodArray<z.ZodObject<{
        id: z.core.$ZodBranded<z.ZodString, "FusionCompositionId", "out">;
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        timelineItemId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
        index: z.ZodNumber;
        name: z.ZodString;
        projectRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        graphDigest: z.ZodString;
    }, z.core.$strict>>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"mediaPool.page">;
    data: z.ZodObject<{
        project: z.ZodObject<{
            id: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            name: z.ZodString;
        }, z.core.$strict>;
        revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        offset: z.ZodNumber;
        pageSize: z.ZodNumber;
        total: z.ZodNumber;
        nextOffset: z.ZodNullable<z.ZodNumber>;
        search: z.ZodNullable<z.ZodObject<{
            query: z.ZodString;
            match: z.ZodEnum<{
                exact: "exact";
                contains: "contains";
            }>;
            fields: z.ZodArray<z.ZodEnum<{
                name: "name";
                metadata: "metadata";
                sourceFileName: "sourceFileName";
            }>>;
        }, z.core.$strict>>;
        folders: z.ZodArray<z.ZodObject<{
            id: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "MediaPoolFolderId", "out">>;
            snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolFolderId", "out">;
            parentSnapshotId: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolFolderId", "out">>;
            snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            name: z.ZodString;
            depth: z.ZodNumber;
        }, z.core.$strict>>;
        assets: z.ZodArray<z.ZodObject<{
            id: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">>;
            snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolItemId", "out">;
            folderSnapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolFolderId", "out">;
            snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            name: z.ZodString;
            kind: z.ZodEnum<{
                unknown: "unknown";
                timeline: "timeline";
                multicam: "multicam";
                fusion_composition: "fusion_composition";
                video: "video";
                audio: "audio";
                still: "still";
                compound: "compound";
                generator: "generator";
            }>;
            selected: z.ZodBoolean;
            sourceFileName: z.ZodNullable<z.ZodString>;
            duration: z.ZodNullable<z.ZodString>;
            resolution: z.ZodNullable<z.ZodString>;
            frameRate: z.ZodNullable<z.ZodString>;
            startTimecode: z.ZodNullable<z.ZodString>;
            metadata: z.ZodArray<z.ZodObject<{
                key: z.ZodEnum<{
                    description: "description";
                    comments: "comments";
                    keywords: "keywords";
                    shot: "shot";
                    scene: "scene";
                    take: "take";
                    angle: "angle";
                    camera: "camera";
                    reel: "reel";
                    dateRecorded: "dateRecorded";
                    goodTake: "goodTake";
                    clipColor: "clipColor";
                }>;
                value: z.ZodString;
            }, z.core.$strict>>;
        }, z.core.$strict>>;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"color.current">;
    data: z.ZodObject<{
        project: z.ZodObject<{
            id: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            name: z.ZodString;
        }, z.core.$strict>;
        timeline: z.ZodObject<{
            id: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
            projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            name: z.ZodString;
        }, z.core.$strict>;
        revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        nodeStackLayerIndex: z.ZodNumber;
        frameRate: z.ZodObject<{
            numerator: z.ZodNumber;
            denominator: z.ZodNumber;
            nominalTimebase: z.ZodNumber;
        }, z.core.$strict>;
        track: z.ZodObject<{
            snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotTrackId", "out">;
            index: z.ZodNumber;
            name: z.ZodString;
        }, z.core.$strict>;
        clip: z.ZodObject<{
            snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotTimelineItemId", "out">;
            snapshotTrackId: z.core.$ZodBranded<z.ZodString, "SnapshotTrackId", "out">;
            snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            name: z.ZodString;
            recordRange: z.ZodObject<{
                domain: z.ZodLiteral<"timeline_record_range">;
                unit: z.ZodLiteral<"frames">;
                start: z.ZodNumber;
                endExclusive: z.ZodNumber;
            }, z.core.$strict>;
            duration: z.ZodObject<{
                domain: z.ZodLiteral<"duration">;
                value: z.ZodObject<{
                    kind: z.ZodLiteral<"frames">;
                    value: z.ZodNumber;
                }, z.core.$strict>;
            }, z.core.$strict>;
            sourceRange: z.ZodNullable<z.ZodObject<{
                domain: z.ZodLiteral<"source_range">;
                unit: z.ZodLiteral<"frames">;
                start: z.ZodNumber;
                endExclusive: z.ZodNumber;
            }, z.core.$strict>>;
            retimeSource: z.ZodOptional<z.ZodNullable<z.ZodObject<{
                availableRange: z.ZodObject<{
                    domain: z.ZodLiteral<"source_range">;
                    unit: z.ZodLiteral<"frames">;
                    start: z.ZodNumber;
                    endExclusive: z.ZodNumber;
                }, z.core.$strict>;
                originFrame: z.ZodNumber;
            }, z.core.$strict>>>;
            sourceFrameRate: z.ZodNullable<z.ZodObject<{
                numerator: z.ZodNumber;
                denominator: z.ZodNumber;
                nominalTimebase: z.ZodNumber;
            }, z.core.$strict>>;
            mediaPoolItemId: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">>;
            linkedItemIds: z.ZodNullable<z.ZodArray<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>>;
            id: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
        }, z.core.$strict>;
        capabilities: z.ZodObject<{
            nodeGraph: z.ZodDiscriminatedUnion<[z.ZodObject<{
                status: z.ZodLiteral<"supported">;
            }, z.core.$strict>, z.ZodObject<{
                status: z.ZodLiteral<"unavailable">;
                reason: z.ZodLiteral<"not_exposed_by_runtime">;
            }, z.core.$strict>], "status">;
            labels: z.ZodDiscriminatedUnion<[z.ZodObject<{
                status: z.ZodLiteral<"supported">;
            }, z.core.$strict>, z.ZodObject<{
                status: z.ZodLiteral<"unavailable">;
                reason: z.ZodLiteral<"not_exposed_by_runtime">;
            }, z.core.$strict>], "status">;
            enabledState: z.ZodDiscriminatedUnion<[z.ZodObject<{
                status: z.ZodLiteral<"supported">;
            }, z.core.$strict>, z.ZodObject<{
                status: z.ZodLiteral<"unavailable">;
                reason: z.ZodLiteral<"not_exposed_by_runtime">;
            }, z.core.$strict>], "status">;
            luts: z.ZodDiscriminatedUnion<[z.ZodObject<{
                status: z.ZodLiteral<"supported">;
            }, z.core.$strict>, z.ZodObject<{
                status: z.ZodLiteral<"unavailable">;
                reason: z.ZodLiteral<"not_exposed_by_runtime">;
            }, z.core.$strict>], "status">;
            effects: z.ZodDiscriminatedUnion<[z.ZodObject<{
                status: z.ZodLiteral<"supported">;
            }, z.core.$strict>, z.ZodObject<{
                status: z.ZodLiteral<"unavailable">;
                reason: z.ZodLiteral<"not_exposed_by_runtime">;
            }, z.core.$strict>], "status">;
            versions: z.ZodDiscriminatedUnion<[z.ZodObject<{
                status: z.ZodLiteral<"supported">;
            }, z.core.$strict>, z.ZodObject<{
                status: z.ZodLiteral<"unavailable">;
                reason: z.ZodLiteral<"not_exposed_by_runtime">;
            }, z.core.$strict>], "status">;
            colorGroup: z.ZodDiscriminatedUnion<[z.ZodObject<{
                status: z.ZodLiteral<"supported">;
            }, z.core.$strict>, z.ZodObject<{
                status: z.ZodLiteral<"unavailable">;
                reason: z.ZodLiteral<"not_exposed_by_runtime">;
            }, z.core.$strict>], "status">;
        }, z.core.$strict>;
        mutationCapabilities: z.ZodDefault<z.ZodObject<{
            primary: z.ZodObject<{
                status: z.ZodLiteral<"runtime_check_required">;
                edition: z.ZodEnum<{
                    studio_or_free: "studio_or_free";
                    studio_required: "studio_required";
                }>;
                projectStorage: z.ZodEnum<{
                    any: "any";
                    disk_required: "disk_required";
                }>;
                plugin: z.ZodEnum<{
                    not_required: "not_required";
                    installed_effect_required: "installed_effect_required";
                }>;
            }, z.core.$strict>;
            nodes: z.ZodObject<{
                status: z.ZodLiteral<"runtime_check_required">;
                edition: z.ZodEnum<{
                    studio_or_free: "studio_or_free";
                    studio_required: "studio_required";
                }>;
                projectStorage: z.ZodEnum<{
                    any: "any";
                    disk_required: "disk_required";
                }>;
                plugin: z.ZodEnum<{
                    not_required: "not_required";
                    installed_effect_required: "installed_effect_required";
                }>;
            }, z.core.$strict>;
            lutAssets: z.ZodObject<{
                status: z.ZodLiteral<"runtime_check_required">;
                edition: z.ZodEnum<{
                    studio_or_free: "studio_or_free";
                    studio_required: "studio_required";
                }>;
                projectStorage: z.ZodEnum<{
                    any: "any";
                    disk_required: "disk_required";
                }>;
                plugin: z.ZodEnum<{
                    not_required: "not_required";
                    installed_effect_required: "installed_effect_required";
                }>;
            }, z.core.$strict>;
            drxAssets: z.ZodObject<{
                status: z.ZodLiteral<"runtime_check_required">;
                edition: z.ZodEnum<{
                    studio_or_free: "studio_or_free";
                    studio_required: "studio_required";
                }>;
                projectStorage: z.ZodEnum<{
                    any: "any";
                    disk_required: "disk_required";
                }>;
                plugin: z.ZodEnum<{
                    not_required: "not_required";
                    installed_effect_required: "installed_effect_required";
                }>;
            }, z.core.$strict>;
            effects: z.ZodObject<{
                status: z.ZodLiteral<"runtime_check_required">;
                edition: z.ZodEnum<{
                    studio_or_free: "studio_or_free";
                    studio_required: "studio_required";
                }>;
                projectStorage: z.ZodEnum<{
                    any: "any";
                    disk_required: "disk_required";
                }>;
                plugin: z.ZodEnum<{
                    not_required: "not_required";
                    installed_effect_required: "installed_effect_required";
                }>;
            }, z.core.$strict>;
        }, z.core.$strict>>;
        nodeGraph: z.ZodObject<{
            nodeCount: z.ZodNumber;
            nodes: z.ZodArray<z.ZodObject<{
                index: z.ZodNumber;
                label: z.ZodNullable<z.ZodString>;
                enabled: z.ZodNullable<z.ZodBoolean>;
                lut: z.ZodObject<{
                    applied: z.ZodBoolean;
                    displayName: z.ZodNullable<z.ZodString>;
                }, z.core.$strict>;
                effects: z.ZodArray<z.ZodString>;
            }, z.core.$strict>>;
        }, z.core.$strict>;
        versions: z.ZodObject<{
            current: z.ZodNullable<z.ZodString>;
            local: z.ZodArray<z.ZodString>;
            remote: z.ZodArray<z.ZodString>;
        }, z.core.$strict>;
        colorGroup: z.ZodNullable<z.ZodString>;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"render.discovery">;
    data: z.ZodObject<{
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        formatSupport: z.ZodDiscriminatedUnion<[z.ZodObject<{
            availability: z.ZodLiteral<"supported">;
        }, z.core.$strict>, z.ZodObject<{
            availability: z.ZodLiteral<"unavailable">;
            reason: z.ZodEnum<{
                api_unavailable: "api_unavailable";
                edition_unavailable: "edition_unavailable";
                temporarily_unavailable: "temporarily_unavailable";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            availability: z.ZodLiteral<"unknown_version">;
            reason: z.ZodLiteral<"unrecognized_response">;
        }, z.core.$strict>], "availability">;
        formats: z.ZodArray<z.ZodObject<{
            format: z.ZodDiscriminatedUnion<[z.ZodObject<{
                kind: z.ZodLiteral<"known">;
                value: z.ZodEnum<{
                    quicktime: "quicktime";
                    mp4: "mp4";
                    mxf: "mxf";
                    wave: "wave";
                    aiff: "aiff";
                    dcp: "dcp";
                    image_sequence: "image_sequence";
                }>;
            }, z.core.$strict>, z.ZodObject<{
                kind: z.ZodLiteral<"unknown_version">;
                label: z.ZodString;
            }, z.core.$strict>], "kind">;
            label: z.ZodString;
            extension: z.ZodNullable<z.ZodString>;
            codecs: z.ZodArray<z.ZodObject<{
                codec: z.ZodDiscriminatedUnion<[z.ZodObject<{
                    kind: z.ZodLiteral<"known">;
                    value: z.ZodEnum<{
                        h264: "h264";
                        h265: "h265";
                        prores: "prores";
                        dnxhr: "dnxhr";
                        av1: "av1";
                        linear_pcm: "linear_pcm";
                        aac: "aac";
                        flac: "flac";
                        exr: "exr";
                        dpx: "dpx";
                        tiff: "tiff";
                        jpeg: "jpeg";
                    }>;
                }, z.core.$strict>, z.ZodObject<{
                    kind: z.ZodLiteral<"unknown_version">;
                    label: z.ZodString;
                }, z.core.$strict>], "kind">;
                label: z.ZodString;
                resolutions: z.ZodArray<z.ZodObject<{
                    width: z.ZodNumber;
                    height: z.ZodNumber;
                }, z.core.$strict>>;
                resolutionSupport: z.ZodDiscriminatedUnion<[z.ZodObject<{
                    availability: z.ZodLiteral<"supported">;
                }, z.core.$strict>, z.ZodObject<{
                    availability: z.ZodLiteral<"unavailable">;
                    reason: z.ZodEnum<{
                        api_unavailable: "api_unavailable";
                        edition_unavailable: "edition_unavailable";
                        temporarily_unavailable: "temporarily_unavailable";
                    }>;
                }, z.core.$strict>, z.ZodObject<{
                    availability: z.ZodLiteral<"unknown_version">;
                    reason: z.ZodLiteral<"unrecognized_response">;
                }, z.core.$strict>], "availability">;
            }, z.core.$strict>>;
            codecSupport: z.ZodDiscriminatedUnion<[z.ZodObject<{
                availability: z.ZodLiteral<"supported">;
            }, z.core.$strict>, z.ZodObject<{
                availability: z.ZodLiteral<"unavailable">;
                reason: z.ZodEnum<{
                    api_unavailable: "api_unavailable";
                    edition_unavailable: "edition_unavailable";
                    temporarily_unavailable: "temporarily_unavailable";
                }>;
            }, z.core.$strict>, z.ZodObject<{
                availability: z.ZodLiteral<"unknown_version">;
                reason: z.ZodLiteral<"unrecognized_response">;
            }, z.core.$strict>], "availability">;
        }, z.core.$strict>>;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"render.presets">;
    data: z.ZodObject<{
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        support: z.ZodDiscriminatedUnion<[z.ZodObject<{
            availability: z.ZodLiteral<"supported">;
        }, z.core.$strict>, z.ZodObject<{
            availability: z.ZodLiteral<"unavailable">;
            reason: z.ZodEnum<{
                api_unavailable: "api_unavailable";
                edition_unavailable: "edition_unavailable";
                temporarily_unavailable: "temporarily_unavailable";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            availability: z.ZodLiteral<"unknown_version">;
            reason: z.ZodLiteral<"unrecognized_response">;
        }, z.core.$strict>], "availability">;
        presets: z.ZodArray<z.ZodObject<{
            name: z.ZodString;
        }, z.core.$strict>>;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"render.settings">;
    data: z.ZodObject<{
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        support: z.ZodDiscriminatedUnion<[z.ZodObject<{
            availability: z.ZodLiteral<"supported">;
        }, z.core.$strict>, z.ZodObject<{
            availability: z.ZodLiteral<"unavailable">;
            reason: z.ZodEnum<{
                api_unavailable: "api_unavailable";
                edition_unavailable: "edition_unavailable";
                temporarily_unavailable: "temporarily_unavailable";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            availability: z.ZodLiteral<"unknown_version">;
            reason: z.ZodLiteral<"unrecognized_response">;
        }, z.core.$strict>], "availability">;
        format: z.ZodNullable<z.ZodDiscriminatedUnion<[z.ZodObject<{
            kind: z.ZodLiteral<"known">;
            value: z.ZodEnum<{
                quicktime: "quicktime";
                mp4: "mp4";
                mxf: "mxf";
                wave: "wave";
                aiff: "aiff";
                dcp: "dcp";
                image_sequence: "image_sequence";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"unknown_version">;
            label: z.ZodString;
        }, z.core.$strict>], "kind">>;
        codec: z.ZodNullable<z.ZodDiscriminatedUnion<[z.ZodObject<{
            kind: z.ZodLiteral<"known">;
            value: z.ZodEnum<{
                h264: "h264";
                h265: "h265";
                prores: "prores";
                dnxhr: "dnxhr";
                av1: "av1";
                linear_pcm: "linear_pcm";
                aac: "aac";
                flac: "flac";
                exr: "exr";
                dpx: "dpx";
                tiff: "tiff";
                jpeg: "jpeg";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"unknown_version">;
            label: z.ZodString;
        }, z.core.$strict>], "kind">>;
        resolution: z.ZodNullable<z.ZodObject<{
            width: z.ZodNumber;
            height: z.ZodNumber;
        }, z.core.$strict>>;
        frameRate: z.ZodNullable<z.ZodNumber>;
        mode: z.ZodNullable<z.ZodDiscriminatedUnion<[z.ZodObject<{
            kind: z.ZodLiteral<"known">;
            value: z.ZodEnum<{
                individual_clips: "individual_clips";
                single_clip: "single_clip";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"unknown_version">;
            value: z.ZodString;
        }, z.core.$strict>], "kind">>;
        range: z.ZodDiscriminatedUnion<[z.ZodObject<{
            kind: z.ZodLiteral<"full_timeline">;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"custom">;
            markInFrame: z.ZodNumber;
            markOutFrame: z.ZodNumber;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"unknown">;
        }, z.core.$strict>], "kind">;
        exportVideo: z.ZodNullable<z.ZodBoolean>;
        exportAudio: z.ZodNullable<z.ZodBoolean>;
        exportSubtitles: z.ZodNullable<z.ZodBoolean>;
        customName: z.ZodNullable<z.ZodString>;
        queueCount: z.ZodNumber;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"render.queue">;
    data: z.ZodObject<{
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        queueRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        support: z.ZodDiscriminatedUnion<[z.ZodObject<{
            availability: z.ZodLiteral<"supported">;
        }, z.core.$strict>, z.ZodObject<{
            availability: z.ZodLiteral<"unavailable">;
            reason: z.ZodEnum<{
                api_unavailable: "api_unavailable";
                edition_unavailable: "edition_unavailable";
                temporarily_unavailable: "temporarily_unavailable";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            availability: z.ZodLiteral<"unknown_version">;
            reason: z.ZodLiteral<"unrecognized_response">;
        }, z.core.$strict>], "availability">;
        cursor: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "RenderQueueCursor", "out">>;
        offset: z.ZodNumber;
        pageSize: z.ZodNumber;
        jobs: z.ZodArray<z.ZodObject<{
            id: z.core.$ZodBranded<z.ZodString, "SnapshotRenderJobId", "out">;
            projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            queueRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            index: z.ZodNumber;
            name: z.ZodString;
            statusSupport: z.ZodDiscriminatedUnion<[z.ZodObject<{
                availability: z.ZodLiteral<"supported">;
            }, z.core.$strict>, z.ZodObject<{
                availability: z.ZodLiteral<"unavailable">;
                reason: z.ZodEnum<{
                    api_unavailable: "api_unavailable";
                    edition_unavailable: "edition_unavailable";
                    temporarily_unavailable: "temporarily_unavailable";
                }>;
            }, z.core.$strict>, z.ZodObject<{
                availability: z.ZodLiteral<"unknown_version">;
                reason: z.ZodLiteral<"unrecognized_response">;
            }, z.core.$strict>], "availability">;
            status: z.ZodDiscriminatedUnion<[z.ZodObject<{
                kind: z.ZodLiteral<"known">;
                value: z.ZodEnum<{
                    completed: "completed";
                    failed: "failed";
                    queued: "queued";
                    cancelled: "cancelled";
                    rendering: "rendering";
                }>;
            }, z.core.$strict>, z.ZodObject<{
                kind: z.ZodLiteral<"unknown_version">;
                value: z.ZodString;
            }, z.core.$strict>], "kind">;
            progressPercent: z.ZodNullable<z.ZodNumber>;
        }, z.core.$strict>>;
        nextCursor: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "RenderQueueCursor", "out">>;
        total: z.ZodNumber;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"render.job_status">;
    data: z.ZodObject<{
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        queueRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        support: z.ZodDiscriminatedUnion<[z.ZodObject<{
            availability: z.ZodLiteral<"supported">;
        }, z.core.$strict>, z.ZodObject<{
            availability: z.ZodLiteral<"unavailable">;
            reason: z.ZodEnum<{
                api_unavailable: "api_unavailable";
                edition_unavailable: "edition_unavailable";
                temporarily_unavailable: "temporarily_unavailable";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            availability: z.ZodLiteral<"unknown_version">;
            reason: z.ZodLiteral<"unrecognized_response">;
        }, z.core.$strict>], "availability">;
        job: z.ZodObject<{
            id: z.core.$ZodBranded<z.ZodString, "SnapshotRenderJobId", "out">;
            projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            queueRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            index: z.ZodNumber;
            name: z.ZodString;
            statusSupport: z.ZodDiscriminatedUnion<[z.ZodObject<{
                availability: z.ZodLiteral<"supported">;
            }, z.core.$strict>, z.ZodObject<{
                availability: z.ZodLiteral<"unavailable">;
                reason: z.ZodEnum<{
                    api_unavailable: "api_unavailable";
                    edition_unavailable: "edition_unavailable";
                    temporarily_unavailable: "temporarily_unavailable";
                }>;
            }, z.core.$strict>, z.ZodObject<{
                availability: z.ZodLiteral<"unknown_version">;
                reason: z.ZodLiteral<"unrecognized_response">;
            }, z.core.$strict>], "availability">;
            status: z.ZodDiscriminatedUnion<[z.ZodObject<{
                kind: z.ZodLiteral<"known">;
                value: z.ZodEnum<{
                    completed: "completed";
                    failed: "failed";
                    queued: "queued";
                    cancelled: "cancelled";
                    rendering: "rendering";
                }>;
            }, z.core.$strict>, z.ZodObject<{
                kind: z.ZodLiteral<"unknown_version">;
                value: z.ZodString;
            }, z.core.$strict>], "kind">;
            progressPercent: z.ZodNullable<z.ZodNumber>;
        }, z.core.$strict>;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"artifact.content">;
    data: z.ZodObject<{
        artifactId: z.core.$ZodBranded<z.ZodString, "ArtifactId", "out">;
        offset: z.ZodNumber;
        totalSize: z.ZodNumber;
        bytesBase64: z.ZodString;
        eof: z.ZodBoolean;
        sha256: z.ZodString;
        availableUntil: z.ZodString;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"artifact.fusion_setting.publish">;
    data: z.ZodObject<{
        artifactId: z.core.$ZodBranded<z.ZodString, "ArtifactId", "out">;
        mediaType: z.ZodLiteral<"application/x-fusion-setting">;
        byteCount: z.ZodNumber;
        sha256: z.ZodString;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"timeline.edit.preview">;
    data: z.ZodObject<{
        impactId: z.ZodString;
        action: z.ZodEnum<{
            trim: "trim";
            insert: "insert";
            overwrite: "overwrite";
            remove: "remove";
        }>;
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        intent: z.ZodDiscriminatedUnion<[z.ZodObject<{
            action: z.ZodEnum<{
                insert: "insert";
                overwrite: "overwrite";
            }>;
            placement: z.ZodDefault<z.ZodEnum<{
                video: "video";
                audio: "audio";
            }>>;
            projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
            timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            source: z.ZodObject<{
                id: z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">;
                name: z.ZodString;
                snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            }, z.core.$strict>;
            sourceRange: z.ZodObject<{
                domain: z.ZodLiteral<"source_range" | "timeline_record_range">;
                unit: z.ZodLiteral<"frames">;
                start: z.ZodNumber;
                endExclusive: z.ZodNumber;
            }, z.core.$strict>;
            at: z.ZodObject<{
                domain: z.ZodLiteral<"timeline_record">;
                value: z.ZodObject<{
                    kind: z.ZodLiteral<"frames">;
                    value: z.ZodNumber;
                }, z.core.$strict>;
            }, z.core.$strict>;
            videoTrackIndex: z.ZodNullable<z.ZodNumber>;
            audioTrackIndex: z.ZodNullable<z.ZodNumber>;
            linkedAudio: z.ZodEnum<{
                include: "include";
                exclude: "exclude";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            action: z.ZodLiteral<"trim">;
            projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
            timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
            clipName: z.ZodString;
            trackIndex: z.ZodNumber;
            currentRecordRange: z.ZodObject<{
                domain: z.ZodLiteral<"source_range" | "timeline_record_range">;
                unit: z.ZodLiteral<"frames">;
                start: z.ZodNumber;
                endExclusive: z.ZodNumber;
            }, z.core.$strict>;
            headFrames: z.ZodNumber;
            tailFrames: z.ZodNumber;
            linkedAudio: z.ZodEnum<{
                exclude: "exclude";
                preserve: "preserve";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            action: z.ZodLiteral<"remove">;
            projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
            timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
            clipName: z.ZodString;
            trackType: z.ZodEnum<{
                video: "video";
                audio: "audio";
                subtitle: "subtitle";
            }>;
            trackIndex: z.ZodNumber;
            currentRecordRange: z.ZodObject<{
                domain: z.ZodLiteral<"source_range" | "timeline_record_range">;
                unit: z.ZodLiteral<"frames">;
                start: z.ZodNumber;
                endExclusive: z.ZodNumber;
            }, z.core.$strict>;
            linkedItems: z.ZodLiteral<"exclude">;
        }, z.core.$strict>], "action">;
        recordRange: z.ZodObject<{
            domain: z.ZodLiteral<"source_range" | "timeline_record_range">;
            unit: z.ZodLiteral<"frames">;
            start: z.ZodNumber;
            endExclusive: z.ZodNumber;
        }, z.core.$strict>;
        affectedTracks: z.ZodArray<z.ZodObject<{
            type: z.ZodEnum<{
                video: "video";
                audio: "audio";
                subtitle: "subtitle";
            }>;
            index: z.ZodNumber;
            snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotTrackId", "out">;
        }, z.core.$strict>>;
        affectedItems: z.ZodArray<z.ZodObject<{
            id: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
            track: z.ZodObject<{
                type: z.ZodEnum<{
                    video: "video";
                    audio: "audio";
                    subtitle: "subtitle";
                }>;
                index: z.ZodNumber;
                snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotTrackId", "out">;
            }, z.core.$strict>;
            recordRange: z.ZodObject<{
                domain: z.ZodLiteral<"source_range" | "timeline_record_range">;
                unit: z.ZodLiteral<"frames">;
                start: z.ZodNumber;
                endExclusive: z.ZodNumber;
            }, z.core.$strict>;
            role: z.ZodEnum<{
                replace: "replace";
                trim: "trim";
                remove: "remove";
                linked: "linked";
                protected_overlap: "protected_overlap";
                protected_neighbor: "protected_neighbor";
            }>;
        }, z.core.$strict>>;
        protectedItems: z.ZodArray<z.ZodObject<{
            id: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
            track: z.ZodObject<{
                type: z.ZodEnum<{
                    video: "video";
                    audio: "audio";
                    subtitle: "subtitle";
                }>;
                index: z.ZodNumber;
                snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotTrackId", "out">;
            }, z.core.$strict>;
            recordRange: z.ZodObject<{
                domain: z.ZodLiteral<"source_range" | "timeline_record_range">;
                unit: z.ZodLiteral<"frames">;
                start: z.ZodNumber;
                endExclusive: z.ZodNumber;
            }, z.core.$strict>;
            role: z.ZodEnum<{
                replace: "replace";
                trim: "trim";
                remove: "remove";
                linked: "linked";
                protected_overlap: "protected_overlap";
                protected_neighbor: "protected_neighbor";
            }>;
        }, z.core.$strict>>;
        expectedItems: z.ZodArray<z.ZodObject<{
            role: z.ZodEnum<{
                replacement: "replacement";
                preserved_edge: "preserved_edge";
                trimmed: "trimmed";
                unlinked: "unlinked";
            }>;
            beforeItemId: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>;
            track: z.ZodObject<{
                type: z.ZodEnum<{
                    video: "video";
                    audio: "audio";
                    subtitle: "subtitle";
                }>;
                index: z.ZodNumber;
                snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotTrackId", "out">;
            }, z.core.$strict>;
            recordRange: z.ZodObject<{
                domain: z.ZodLiteral<"source_range" | "timeline_record_range">;
                unit: z.ZodLiteral<"frames">;
                start: z.ZodNumber;
                endExclusive: z.ZodNumber;
            }, z.core.$strict>;
            sourceRange: z.ZodObject<{
                domain: z.ZodLiteral<"source_range" | "timeline_record_range">;
                unit: z.ZodLiteral<"frames">;
                start: z.ZodNumber;
                endExclusive: z.ZodNumber;
            }, z.core.$strict>;
            sourceEndToleranceFrames: z.ZodNumber;
            mediaPoolItemId: z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">;
            name: z.ZodString;
            linkedExpectedItemIndexes: z.ZodArray<z.ZodNumber>;
            linkedExistingItemIds: z.ZodArray<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>;
        }, z.core.$strict>>;
        expectedLinkTransitions: z.ZodDefault<z.ZodArray<z.ZodObject<{
            itemId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
            beforeLinkedItemIds: z.ZodArray<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>;
            afterLinkedItemIds: z.ZodArray<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>;
        }, z.core.$strict>>>;
        linkedAudio: z.ZodObject<{
            behavior: z.ZodEnum<{
                include: "include";
                exclude: "exclude";
                preserve: "preserve";
            }>;
            topologyProven: z.ZodBoolean;
        }, z.core.$strict>;
        capabilityId: z.ZodEnum<{
            "edit.insert_overwrite": "edit.insert_overwrite";
            "edit.trim_workaround": "edit.trim_workaround";
            "timeline.items_delete": "timeline.items_delete";
        }>;
        summary: z.ZodString;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"timeline.managed.preview">;
    data: z.ZodObject<{
        status: z.ZodEnum<{
            blocked: "blocked";
            no_change: "no_change";
            ready: "ready";
        }>;
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        ownershipId: z.ZodString;
        scope: z.ZodDiscriminatedUnion<[z.ZodObject<{
            kind: z.ZodLiteral<"whole_timeline">;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"region">;
            startFrame: z.ZodNumber;
            endExclusiveFrame: z.ZodNumber;
        }, z.core.$strict>], "kind">;
        desiredStateDigest: z.ZodString;
        contextDigest: z.ZodString;
        protectedStateDigest: z.ZodString;
        previewDigest: z.ZodString;
        ownershipGeneration: z.ZodNumber;
        policyRevision: z.ZodString;
        capabilityDigest: z.ZodString;
        drift: z.ZodArray<z.ZodObject<{
            kind: z.ZodEnum<{
                create: "create";
                update: "update";
                preserve: "preserve";
                remove: "remove";
            }>;
            key: z.ZodString;
            timelineItemId: z.ZodOptional<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>;
            summary: z.ZodString;
        }, z.core.$strict>>;
        blockers: z.ZodArray<z.ZodObject<{
            code: z.ZodEnum<{
                stale_revision: "stale_revision";
                ambiguous_identity: "ambiguous_identity";
                scope_crossing: "scope_crossing";
                unsupported_change: "unsupported_change";
                protected_state_unproven: "protected_state_unproven";
                ownership_overlap: "ownership_overlap";
            }>;
            key: z.ZodOptional<z.ZodString>;
            message: z.ZodString;
        }, z.core.$strict>>;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"timeline.managed.export">;
    data: z.ZodDiscriminatedUnion<[z.ZodObject<{
        status: z.ZodLiteral<"ready">;
        dialect: z.ZodLiteral<"cutagent.managed-timeline">;
        version: z.ZodLiteral<1>;
        program: z.ZodObject<{
            projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
            revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            ownershipId: z.ZodString;
            scope: z.ZodDiscriminatedUnion<[z.ZodObject<{
                kind: z.ZodLiteral<"whole_timeline">;
            }, z.core.$strict>, z.ZodObject<{
                kind: z.ZodLiteral<"region">;
                startFrame: z.ZodNumber;
                endExclusiveFrame: z.ZodNumber;
            }, z.core.$strict>], "kind">;
            timelineFrameRate: z.ZodObject<{
                numerator: z.ZodNumber;
                denominator: z.ZodNumber;
                nominalTimebase: z.ZodNumber;
            }, z.core.$strict>;
            elements: z.ZodArray<z.ZodObject<{
                key: z.ZodString;
                assetId: z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">;
                assetName: z.ZodString;
                assetRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
                videoTrack: z.ZodNumber;
                audioTrack: z.ZodNullable<z.ZodNumber>;
                atFrame: z.ZodNumber;
                sourceStartFrame: z.ZodNumber;
                sourceEndExclusiveFrame: z.ZodNumber;
                sourceFrameRate: z.ZodObject<{
                    numerator: z.ZodNumber;
                    denominator: z.ZodNumber;
                    nominalTimebase: z.ZodNumber;
                }, z.core.$strict>;
                linkedAudio: z.ZodEnum<{
                    include: "include";
                    exclude: "exclude";
                }>;
                adoptTimelineItemId: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>;
            }, z.core.$strict>>;
        }, z.core.$strict>;
        assets: z.ZodArray<z.ZodObject<{
            id: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">>;
            snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolItemId", "out">;
            folderSnapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolFolderId", "out">;
            snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            name: z.ZodString;
            kind: z.ZodEnum<{
                unknown: "unknown";
                timeline: "timeline";
                multicam: "multicam";
                fusion_composition: "fusion_composition";
                video: "video";
                audio: "audio";
                still: "still";
                compound: "compound";
                generator: "generator";
            }>;
            selected: z.ZodBoolean;
            sourceFileName: z.ZodNullable<z.ZodString>;
            duration: z.ZodNullable<z.ZodString>;
            resolution: z.ZodNullable<z.ZodString>;
            frameRate: z.ZodNullable<z.ZodString>;
            startTimecode: z.ZodNullable<z.ZodString>;
            metadata: z.ZodArray<z.ZodObject<{
                key: z.ZodEnum<{
                    description: "description";
                    comments: "comments";
                    keywords: "keywords";
                    shot: "shot";
                    scene: "scene";
                    take: "take";
                    angle: "angle";
                    camera: "camera";
                    reel: "reel";
                    dateRecorded: "dateRecorded";
                    goodTake: "goodTake";
                    clipColor: "clipColor";
                }>;
                value: z.ZodString;
            }, z.core.$strict>>;
        }, z.core.$strict>>;
        coverage: z.ZodObject<{
            represented: z.ZodTuple<[z.ZodLiteral<"clip_placement/v1">], null>;
            preservedButNotRepresented: z.ZodTuple<[z.ZodLiteral<"unmanaged_clips">, z.ZodLiteral<"track_properties">, z.ZodLiteral<"markers">, z.ZodLiteral<"fusion">, z.ZodLiteral<"color">, z.ZodLiteral<"fairlight">, z.ZodLiteral<"retime">, z.ZodLiteral<"transitions">, z.ZodLiteral<"effects">, z.ZodLiteral<"captions">], null>;
            protectedStateDigest: z.ZodString;
        }, z.core.$strict>;
        blockers: z.ZodTuple<[], null>;
    }, z.core.$strict>, z.ZodObject<{
        status: z.ZodLiteral<"blocked">;
        dialect: z.ZodLiteral<"cutagent.managed-timeline">;
        version: z.ZodLiteral<1>;
        document: z.ZodNull;
        blockers: z.ZodArray<z.ZodObject<{
            code: z.ZodEnum<{
                stale_revision: "stale_revision";
                ambiguous_identity: "ambiguous_identity";
                scope_crossing: "scope_crossing";
                unsupported_change: "unsupported_change";
                protected_state_unproven: "protected_state_unproven";
                ownership_overlap: "ownership_overlap";
            }>;
            key: z.ZodOptional<z.ZodString>;
            message: z.ZodString;
        }, z.core.$strict>>;
    }, z.core.$strict>], "status">;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"multicam.inspect">;
    data: z.ZodObject<{
        id: z.core.$ZodBranded<z.ZodString, "MulticamId", "out">;
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        name: z.ZodString;
        angles: z.ZodArray<z.ZodObject<{
            id: z.core.$ZodBranded<z.ZodString, "MulticamAngleId", "out">;
            label: z.ZodString;
            enabled: z.ZodNullable<z.ZodBoolean>;
            sources: z.ZodArray<z.ZodObject<{
                mediaPoolItemId: z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">;
                name: z.ZodString;
            }, z.core.$strict>>;
        }, z.core.$strict>>;
    }, z.core.$strict>;
}, z.core.$strict>], "operation">;
export declare const sdkRuntimeReadResponseSchema: z.ZodUnion<readonly [z.ZodDiscriminatedUnion<[z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"voice.catalog">;
    data: z.ZodObject<{
        voices: z.ZodArray<z.ZodObject<{
            voiceId: z.ZodString;
            name: z.ZodString;
            description: z.ZodNullable<z.ZodString>;
            language: z.ZodNullable<z.ZodString>;
            accent: z.ZodNullable<z.ZodString>;
        }, z.core.$strict>>;
        hasMore: z.ZodBoolean;
        nextPageToken: z.ZodNullable<z.ZodString>;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"project.context">;
    data: z.ZodObject<{
        library: z.ZodNullable<z.ZodObject<{
            name: z.ZodString;
            kind: z.ZodEnum<{
                disk: "disk";
                postgresql: "postgresql";
            }>;
        }, z.core.$strict>>;
        project: z.ZodNullable<z.ZodObject<{
            id: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "ProjectId", "out">>;
            name: z.ZodString;
        }, z.core.$strict>>;
        timeline: z.ZodNullable<z.ZodObject<{
            id: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "TimelineId", "out">>;
            name: z.ZodString;
        }, z.core.$strict>>;
        projectRevision: z.ZodDiscriminatedUnion<[z.ZodObject<{
            status: z.ZodLiteral<"available">;
            revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        }, z.core.$strict>, z.ZodObject<{
            status: z.ZodLiteral<"unavailable">;
        }, z.core.$strict>], "status">;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"project.current">;
    data: z.ZodObject<{
        id: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        name: z.ZodString;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"timeline.current">;
    data: z.ZodObject<{
        id: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        name: z.ZodString;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"timeline.snapshot">;
    data: z.ZodObject<{
        project: z.ZodObject<{
            id: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            name: z.ZodString;
        }, z.core.$strict>;
        timeline: z.ZodObject<{
            id: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
            projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            name: z.ZodString;
        }, z.core.$strict>;
        revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        frameRate: z.ZodObject<{
            numerator: z.ZodNumber;
            denominator: z.ZodNumber;
            nominalTimebase: z.ZodNumber;
        }, z.core.$strict>;
        start: z.ZodObject<{
            domain: z.ZodLiteral<"timeline_record">;
            value: z.ZodObject<{
                kind: z.ZodLiteral<"frames">;
                value: z.ZodNumber;
            }, z.core.$strict>;
        }, z.core.$strict>;
        tracks: z.ZodArray<z.ZodObject<{
            snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotTrackId", "out">;
            timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
            snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            type: z.ZodEnum<{
                video: "video";
                audio: "audio";
                subtitle: "subtitle";
            }>;
            index: z.ZodNumber;
            name: z.ZodString;
            enabled: z.ZodNullable<z.ZodBoolean>;
            locked: z.ZodNullable<z.ZodBoolean>;
            clips: z.ZodArray<z.ZodObject<{
                id: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>;
                snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotTimelineItemId", "out">;
                snapshotTrackId: z.core.$ZodBranded<z.ZodString, "SnapshotTrackId", "out">;
                snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
                name: z.ZodString;
                recordRange: z.ZodObject<{
                    domain: z.ZodLiteral<"timeline_record_range">;
                    unit: z.ZodLiteral<"frames">;
                    start: z.ZodNumber;
                    endExclusive: z.ZodNumber;
                }, z.core.$strict>;
                duration: z.ZodObject<{
                    domain: z.ZodLiteral<"duration">;
                    value: z.ZodObject<{
                        kind: z.ZodLiteral<"frames">;
                        value: z.ZodNumber;
                    }, z.core.$strict>;
                }, z.core.$strict>;
                sourceRange: z.ZodNullable<z.ZodObject<{
                    domain: z.ZodLiteral<"source_range">;
                    unit: z.ZodLiteral<"frames">;
                    start: z.ZodNumber;
                    endExclusive: z.ZodNumber;
                }, z.core.$strict>>;
                retimeSource: z.ZodOptional<z.ZodNullable<z.ZodObject<{
                    availableRange: z.ZodObject<{
                        domain: z.ZodLiteral<"source_range">;
                        unit: z.ZodLiteral<"frames">;
                        start: z.ZodNumber;
                        endExclusive: z.ZodNumber;
                    }, z.core.$strict>;
                    originFrame: z.ZodNumber;
                }, z.core.$strict>>>;
                sourceFrameRate: z.ZodNullable<z.ZodObject<{
                    numerator: z.ZodNumber;
                    denominator: z.ZodNumber;
                    nominalTimebase: z.ZodNumber;
                }, z.core.$strict>>;
                mediaPoolItemId: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">>;
                linkedItemIds: z.ZodNullable<z.ZodArray<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>>;
            }, z.core.$strict>>;
        }, z.core.$strict>>;
        markers: z.ZodArray<z.ZodObject<{
            id: z.core.$ZodBranded<z.ZodString, "MarkerId", "out">;
            snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            position: z.ZodObject<{
                domain: z.ZodLiteral<"timeline_record">;
                value: z.ZodObject<{
                    kind: z.ZodLiteral<"frames">;
                    value: z.ZodNumber;
                }, z.core.$strict>;
            }, z.core.$strict>;
            color: z.ZodString;
            name: z.ZodString;
            note: z.ZodString;
            duration: z.ZodObject<{
                domain: z.ZodLiteral<"duration">;
                value: z.ZodObject<{
                    kind: z.ZodLiteral<"frames">;
                    value: z.ZodNumber;
                }, z.core.$strict>;
            }, z.core.$strict>;
        }, z.core.$strict>>;
        fairlight: z.ZodDefault<z.ZodDiscriminatedUnion<[z.ZodObject<{
            status: z.ZodLiteral<"available">;
            tracks: z.ZodArray<z.ZodObject<{
                trackIndex: z.ZodNumber;
                levelDb: z.ZodDiscriminatedUnion<[z.ZodObject<{
                    status: z.ZodLiteral<"available">;
                    value: z.ZodNumber;
                }, z.core.$strict>, z.ZodObject<{
                    status: z.ZodLiteral<"unavailable">;
                    reason: z.ZodEnum<{
                        readback_unavailable: "readback_unavailable";
                        not_exposed_by_runtime: "not_exposed_by_runtime";
                    }>;
                }, z.core.$strict>], "status">;
                pan: z.ZodDiscriminatedUnion<[z.ZodObject<{
                    status: z.ZodLiteral<"available">;
                    value: z.ZodNumber;
                }, z.core.$strict>, z.ZodObject<{
                    status: z.ZodLiteral<"unavailable">;
                    reason: z.ZodEnum<{
                        readback_unavailable: "readback_unavailable";
                        not_exposed_by_runtime: "not_exposed_by_runtime";
                    }>;
                }, z.core.$strict>], "status">;
            }, z.core.$strict>>;
            clips: z.ZodDefault<z.ZodArray<z.ZodObject<{
                clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
                trackIndex: z.ZodNumber;
                gainDb: z.ZodDiscriminatedUnion<[z.ZodObject<{
                    status: z.ZodLiteral<"available">;
                    value: z.ZodNumber;
                }, z.core.$strict>, z.ZodObject<{
                    status: z.ZodLiteral<"unavailable">;
                    reason: z.ZodEnum<{
                        readback_unavailable: "readback_unavailable";
                        not_exposed_by_runtime: "not_exposed_by_runtime";
                    }>;
                }, z.core.$strict>], "status">;
                pan: z.ZodDiscriminatedUnion<[z.ZodObject<{
                    status: z.ZodLiteral<"available">;
                    value: z.ZodNumber;
                }, z.core.$strict>, z.ZodObject<{
                    status: z.ZodLiteral<"unavailable">;
                    reason: z.ZodEnum<{
                        readback_unavailable: "readback_unavailable";
                        not_exposed_by_runtime: "not_exposed_by_runtime";
                    }>;
                }, z.core.$strict>], "status">;
                fadeInFrames: z.ZodDiscriminatedUnion<[z.ZodObject<{
                    status: z.ZodLiteral<"available">;
                    value: z.ZodNumber;
                }, z.core.$strict>, z.ZodObject<{
                    status: z.ZodLiteral<"unavailable">;
                    reason: z.ZodEnum<{
                        readback_unavailable: "readback_unavailable";
                        not_exposed_by_runtime: "not_exposed_by_runtime";
                    }>;
                }, z.core.$strict>], "status">;
                fadeOutFrames: z.ZodDiscriminatedUnion<[z.ZodObject<{
                    status: z.ZodLiteral<"available">;
                    value: z.ZodNumber;
                }, z.core.$strict>, z.ZodObject<{
                    status: z.ZodLiteral<"unavailable">;
                    reason: z.ZodEnum<{
                        readback_unavailable: "readback_unavailable";
                        not_exposed_by_runtime: "not_exposed_by_runtime";
                    }>;
                }, z.core.$strict>], "status">;
            }, z.core.$strict>>>;
            buses: z.ZodDiscriminatedUnion<[z.ZodObject<{
                status: z.ZodLiteral<"available">;
                buses: z.ZodArray<z.ZodObject<{
                    name: z.ZodString;
                    kind: z.ZodEnum<{
                        bus: "bus";
                        main: "main";
                    }>;
                }, z.core.$strict>>;
            }, z.core.$strict>, z.ZodObject<{
                status: z.ZodLiteral<"unavailable">;
                reason: z.ZodEnum<{
                    readback_unavailable: "readback_unavailable";
                    not_exposed_by_runtime: "not_exposed_by_runtime";
                }>;
                buses: z.ZodTuple<[], null>;
            }, z.core.$strict>], "status">;
        }, z.core.$strict>, z.ZodObject<{
            status: z.ZodLiteral<"unavailable">;
            reason: z.ZodEnum<{
                readback_unavailable: "readback_unavailable";
                not_exposed_by_runtime: "not_exposed_by_runtime";
            }>;
            tracks: z.ZodTuple<[], null>;
            buses: z.ZodObject<{
                status: z.ZodLiteral<"unavailable">;
                reason: z.ZodEnum<{
                    readback_unavailable: "readback_unavailable";
                    not_exposed_by_runtime: "not_exposed_by_runtime";
                }>;
                buses: z.ZodTuple<[], null>;
            }, z.core.$strict>;
        }, z.core.$strict>], "status">>;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"timeline.retime">;
    data: z.ZodObject<{
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        timelineItemId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
        durationFrames: z.ZodNumber;
        speedMultiplier: z.ZodNumber;
        reversed: z.ZodBoolean;
        frozen: z.ZodBoolean;
        points: z.ZodArray<z.ZodObject<{
            recordFrame: z.ZodNumber;
            recordPositionFrames: z.ZodNumber;
            sourceFrame: z.ZodNumber;
            incomingControl: z.ZodObject<{
                recordPositionFrames: z.ZodNumber;
                sourceFrame: z.ZodNumber;
            }, z.core.$strict>;
            outgoingControl: z.ZodObject<{
                recordPositionFrames: z.ZodNumber;
                sourceFrame: z.ZodNumber;
            }, z.core.$strict>;
            speed: z.ZodNumber;
            interpolation: z.ZodEnum<{
                linear: "linear";
                bezier: "bezier";
                hold: "hold";
            }>;
        }, z.core.$strict>>;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"fusion.compositions">;
    data: z.ZodArray<z.ZodObject<{
        id: z.core.$ZodBranded<z.ZodString, "FusionCompositionId", "out">;
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        timelineItemId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
        index: z.ZodNumber;
        name: z.ZodString;
        projectRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        graphDigest: z.ZodString;
    }, z.core.$strict>>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"mediaPool.page">;
    data: z.ZodObject<{
        project: z.ZodObject<{
            id: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            name: z.ZodString;
        }, z.core.$strict>;
        revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        offset: z.ZodNumber;
        pageSize: z.ZodNumber;
        total: z.ZodNumber;
        nextOffset: z.ZodNullable<z.ZodNumber>;
        search: z.ZodNullable<z.ZodObject<{
            query: z.ZodString;
            match: z.ZodEnum<{
                exact: "exact";
                contains: "contains";
            }>;
            fields: z.ZodArray<z.ZodEnum<{
                name: "name";
                metadata: "metadata";
                sourceFileName: "sourceFileName";
            }>>;
        }, z.core.$strict>>;
        folders: z.ZodArray<z.ZodObject<{
            id: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "MediaPoolFolderId", "out">>;
            snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolFolderId", "out">;
            parentSnapshotId: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolFolderId", "out">>;
            snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            name: z.ZodString;
            depth: z.ZodNumber;
        }, z.core.$strict>>;
        assets: z.ZodArray<z.ZodObject<{
            id: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">>;
            snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolItemId", "out">;
            folderSnapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolFolderId", "out">;
            snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            name: z.ZodString;
            kind: z.ZodEnum<{
                unknown: "unknown";
                timeline: "timeline";
                multicam: "multicam";
                fusion_composition: "fusion_composition";
                video: "video";
                audio: "audio";
                still: "still";
                compound: "compound";
                generator: "generator";
            }>;
            selected: z.ZodBoolean;
            sourceFileName: z.ZodNullable<z.ZodString>;
            duration: z.ZodNullable<z.ZodString>;
            resolution: z.ZodNullable<z.ZodString>;
            frameRate: z.ZodNullable<z.ZodString>;
            startTimecode: z.ZodNullable<z.ZodString>;
            metadata: z.ZodArray<z.ZodObject<{
                key: z.ZodEnum<{
                    description: "description";
                    comments: "comments";
                    keywords: "keywords";
                    shot: "shot";
                    scene: "scene";
                    take: "take";
                    angle: "angle";
                    camera: "camera";
                    reel: "reel";
                    dateRecorded: "dateRecorded";
                    goodTake: "goodTake";
                    clipColor: "clipColor";
                }>;
                value: z.ZodString;
            }, z.core.$strict>>;
        }, z.core.$strict>>;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"color.current">;
    data: z.ZodObject<{
        project: z.ZodObject<{
            id: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            name: z.ZodString;
        }, z.core.$strict>;
        timeline: z.ZodObject<{
            id: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
            projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            name: z.ZodString;
        }, z.core.$strict>;
        revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        nodeStackLayerIndex: z.ZodNumber;
        frameRate: z.ZodObject<{
            numerator: z.ZodNumber;
            denominator: z.ZodNumber;
            nominalTimebase: z.ZodNumber;
        }, z.core.$strict>;
        track: z.ZodObject<{
            snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotTrackId", "out">;
            index: z.ZodNumber;
            name: z.ZodString;
        }, z.core.$strict>;
        clip: z.ZodObject<{
            snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotTimelineItemId", "out">;
            snapshotTrackId: z.core.$ZodBranded<z.ZodString, "SnapshotTrackId", "out">;
            snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            name: z.ZodString;
            recordRange: z.ZodObject<{
                domain: z.ZodLiteral<"timeline_record_range">;
                unit: z.ZodLiteral<"frames">;
                start: z.ZodNumber;
                endExclusive: z.ZodNumber;
            }, z.core.$strict>;
            duration: z.ZodObject<{
                domain: z.ZodLiteral<"duration">;
                value: z.ZodObject<{
                    kind: z.ZodLiteral<"frames">;
                    value: z.ZodNumber;
                }, z.core.$strict>;
            }, z.core.$strict>;
            sourceRange: z.ZodNullable<z.ZodObject<{
                domain: z.ZodLiteral<"source_range">;
                unit: z.ZodLiteral<"frames">;
                start: z.ZodNumber;
                endExclusive: z.ZodNumber;
            }, z.core.$strict>>;
            retimeSource: z.ZodOptional<z.ZodNullable<z.ZodObject<{
                availableRange: z.ZodObject<{
                    domain: z.ZodLiteral<"source_range">;
                    unit: z.ZodLiteral<"frames">;
                    start: z.ZodNumber;
                    endExclusive: z.ZodNumber;
                }, z.core.$strict>;
                originFrame: z.ZodNumber;
            }, z.core.$strict>>>;
            sourceFrameRate: z.ZodNullable<z.ZodObject<{
                numerator: z.ZodNumber;
                denominator: z.ZodNumber;
                nominalTimebase: z.ZodNumber;
            }, z.core.$strict>>;
            mediaPoolItemId: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">>;
            linkedItemIds: z.ZodNullable<z.ZodArray<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>>;
            id: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
        }, z.core.$strict>;
        capabilities: z.ZodObject<{
            nodeGraph: z.ZodDiscriminatedUnion<[z.ZodObject<{
                status: z.ZodLiteral<"supported">;
            }, z.core.$strict>, z.ZodObject<{
                status: z.ZodLiteral<"unavailable">;
                reason: z.ZodLiteral<"not_exposed_by_runtime">;
            }, z.core.$strict>], "status">;
            labels: z.ZodDiscriminatedUnion<[z.ZodObject<{
                status: z.ZodLiteral<"supported">;
            }, z.core.$strict>, z.ZodObject<{
                status: z.ZodLiteral<"unavailable">;
                reason: z.ZodLiteral<"not_exposed_by_runtime">;
            }, z.core.$strict>], "status">;
            enabledState: z.ZodDiscriminatedUnion<[z.ZodObject<{
                status: z.ZodLiteral<"supported">;
            }, z.core.$strict>, z.ZodObject<{
                status: z.ZodLiteral<"unavailable">;
                reason: z.ZodLiteral<"not_exposed_by_runtime">;
            }, z.core.$strict>], "status">;
            luts: z.ZodDiscriminatedUnion<[z.ZodObject<{
                status: z.ZodLiteral<"supported">;
            }, z.core.$strict>, z.ZodObject<{
                status: z.ZodLiteral<"unavailable">;
                reason: z.ZodLiteral<"not_exposed_by_runtime">;
            }, z.core.$strict>], "status">;
            effects: z.ZodDiscriminatedUnion<[z.ZodObject<{
                status: z.ZodLiteral<"supported">;
            }, z.core.$strict>, z.ZodObject<{
                status: z.ZodLiteral<"unavailable">;
                reason: z.ZodLiteral<"not_exposed_by_runtime">;
            }, z.core.$strict>], "status">;
            versions: z.ZodDiscriminatedUnion<[z.ZodObject<{
                status: z.ZodLiteral<"supported">;
            }, z.core.$strict>, z.ZodObject<{
                status: z.ZodLiteral<"unavailable">;
                reason: z.ZodLiteral<"not_exposed_by_runtime">;
            }, z.core.$strict>], "status">;
            colorGroup: z.ZodDiscriminatedUnion<[z.ZodObject<{
                status: z.ZodLiteral<"supported">;
            }, z.core.$strict>, z.ZodObject<{
                status: z.ZodLiteral<"unavailable">;
                reason: z.ZodLiteral<"not_exposed_by_runtime">;
            }, z.core.$strict>], "status">;
        }, z.core.$strict>;
        mutationCapabilities: z.ZodDefault<z.ZodObject<{
            primary: z.ZodObject<{
                status: z.ZodLiteral<"runtime_check_required">;
                edition: z.ZodEnum<{
                    studio_or_free: "studio_or_free";
                    studio_required: "studio_required";
                }>;
                projectStorage: z.ZodEnum<{
                    any: "any";
                    disk_required: "disk_required";
                }>;
                plugin: z.ZodEnum<{
                    not_required: "not_required";
                    installed_effect_required: "installed_effect_required";
                }>;
            }, z.core.$strict>;
            nodes: z.ZodObject<{
                status: z.ZodLiteral<"runtime_check_required">;
                edition: z.ZodEnum<{
                    studio_or_free: "studio_or_free";
                    studio_required: "studio_required";
                }>;
                projectStorage: z.ZodEnum<{
                    any: "any";
                    disk_required: "disk_required";
                }>;
                plugin: z.ZodEnum<{
                    not_required: "not_required";
                    installed_effect_required: "installed_effect_required";
                }>;
            }, z.core.$strict>;
            lutAssets: z.ZodObject<{
                status: z.ZodLiteral<"runtime_check_required">;
                edition: z.ZodEnum<{
                    studio_or_free: "studio_or_free";
                    studio_required: "studio_required";
                }>;
                projectStorage: z.ZodEnum<{
                    any: "any";
                    disk_required: "disk_required";
                }>;
                plugin: z.ZodEnum<{
                    not_required: "not_required";
                    installed_effect_required: "installed_effect_required";
                }>;
            }, z.core.$strict>;
            drxAssets: z.ZodObject<{
                status: z.ZodLiteral<"runtime_check_required">;
                edition: z.ZodEnum<{
                    studio_or_free: "studio_or_free";
                    studio_required: "studio_required";
                }>;
                projectStorage: z.ZodEnum<{
                    any: "any";
                    disk_required: "disk_required";
                }>;
                plugin: z.ZodEnum<{
                    not_required: "not_required";
                    installed_effect_required: "installed_effect_required";
                }>;
            }, z.core.$strict>;
            effects: z.ZodObject<{
                status: z.ZodLiteral<"runtime_check_required">;
                edition: z.ZodEnum<{
                    studio_or_free: "studio_or_free";
                    studio_required: "studio_required";
                }>;
                projectStorage: z.ZodEnum<{
                    any: "any";
                    disk_required: "disk_required";
                }>;
                plugin: z.ZodEnum<{
                    not_required: "not_required";
                    installed_effect_required: "installed_effect_required";
                }>;
            }, z.core.$strict>;
        }, z.core.$strict>>;
        nodeGraph: z.ZodObject<{
            nodeCount: z.ZodNumber;
            nodes: z.ZodArray<z.ZodObject<{
                index: z.ZodNumber;
                label: z.ZodNullable<z.ZodString>;
                enabled: z.ZodNullable<z.ZodBoolean>;
                lut: z.ZodObject<{
                    applied: z.ZodBoolean;
                    displayName: z.ZodNullable<z.ZodString>;
                }, z.core.$strict>;
                effects: z.ZodArray<z.ZodString>;
            }, z.core.$strict>>;
        }, z.core.$strict>;
        versions: z.ZodObject<{
            current: z.ZodNullable<z.ZodString>;
            local: z.ZodArray<z.ZodString>;
            remote: z.ZodArray<z.ZodString>;
        }, z.core.$strict>;
        colorGroup: z.ZodNullable<z.ZodString>;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"render.discovery">;
    data: z.ZodObject<{
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        formatSupport: z.ZodDiscriminatedUnion<[z.ZodObject<{
            availability: z.ZodLiteral<"supported">;
        }, z.core.$strict>, z.ZodObject<{
            availability: z.ZodLiteral<"unavailable">;
            reason: z.ZodEnum<{
                api_unavailable: "api_unavailable";
                edition_unavailable: "edition_unavailable";
                temporarily_unavailable: "temporarily_unavailable";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            availability: z.ZodLiteral<"unknown_version">;
            reason: z.ZodLiteral<"unrecognized_response">;
        }, z.core.$strict>], "availability">;
        formats: z.ZodArray<z.ZodObject<{
            format: z.ZodDiscriminatedUnion<[z.ZodObject<{
                kind: z.ZodLiteral<"known">;
                value: z.ZodEnum<{
                    quicktime: "quicktime";
                    mp4: "mp4";
                    mxf: "mxf";
                    wave: "wave";
                    aiff: "aiff";
                    dcp: "dcp";
                    image_sequence: "image_sequence";
                }>;
            }, z.core.$strict>, z.ZodObject<{
                kind: z.ZodLiteral<"unknown_version">;
                label: z.ZodString;
            }, z.core.$strict>], "kind">;
            label: z.ZodString;
            extension: z.ZodNullable<z.ZodString>;
            codecs: z.ZodArray<z.ZodObject<{
                codec: z.ZodDiscriminatedUnion<[z.ZodObject<{
                    kind: z.ZodLiteral<"known">;
                    value: z.ZodEnum<{
                        h264: "h264";
                        h265: "h265";
                        prores: "prores";
                        dnxhr: "dnxhr";
                        av1: "av1";
                        linear_pcm: "linear_pcm";
                        aac: "aac";
                        flac: "flac";
                        exr: "exr";
                        dpx: "dpx";
                        tiff: "tiff";
                        jpeg: "jpeg";
                    }>;
                }, z.core.$strict>, z.ZodObject<{
                    kind: z.ZodLiteral<"unknown_version">;
                    label: z.ZodString;
                }, z.core.$strict>], "kind">;
                label: z.ZodString;
                resolutions: z.ZodArray<z.ZodObject<{
                    width: z.ZodNumber;
                    height: z.ZodNumber;
                }, z.core.$strict>>;
                resolutionSupport: z.ZodDiscriminatedUnion<[z.ZodObject<{
                    availability: z.ZodLiteral<"supported">;
                }, z.core.$strict>, z.ZodObject<{
                    availability: z.ZodLiteral<"unavailable">;
                    reason: z.ZodEnum<{
                        api_unavailable: "api_unavailable";
                        edition_unavailable: "edition_unavailable";
                        temporarily_unavailable: "temporarily_unavailable";
                    }>;
                }, z.core.$strict>, z.ZodObject<{
                    availability: z.ZodLiteral<"unknown_version">;
                    reason: z.ZodLiteral<"unrecognized_response">;
                }, z.core.$strict>], "availability">;
            }, z.core.$strict>>;
            codecSupport: z.ZodDiscriminatedUnion<[z.ZodObject<{
                availability: z.ZodLiteral<"supported">;
            }, z.core.$strict>, z.ZodObject<{
                availability: z.ZodLiteral<"unavailable">;
                reason: z.ZodEnum<{
                    api_unavailable: "api_unavailable";
                    edition_unavailable: "edition_unavailable";
                    temporarily_unavailable: "temporarily_unavailable";
                }>;
            }, z.core.$strict>, z.ZodObject<{
                availability: z.ZodLiteral<"unknown_version">;
                reason: z.ZodLiteral<"unrecognized_response">;
            }, z.core.$strict>], "availability">;
        }, z.core.$strict>>;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"render.presets">;
    data: z.ZodObject<{
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        support: z.ZodDiscriminatedUnion<[z.ZodObject<{
            availability: z.ZodLiteral<"supported">;
        }, z.core.$strict>, z.ZodObject<{
            availability: z.ZodLiteral<"unavailable">;
            reason: z.ZodEnum<{
                api_unavailable: "api_unavailable";
                edition_unavailable: "edition_unavailable";
                temporarily_unavailable: "temporarily_unavailable";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            availability: z.ZodLiteral<"unknown_version">;
            reason: z.ZodLiteral<"unrecognized_response">;
        }, z.core.$strict>], "availability">;
        presets: z.ZodArray<z.ZodObject<{
            name: z.ZodString;
        }, z.core.$strict>>;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"render.settings">;
    data: z.ZodObject<{
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        support: z.ZodDiscriminatedUnion<[z.ZodObject<{
            availability: z.ZodLiteral<"supported">;
        }, z.core.$strict>, z.ZodObject<{
            availability: z.ZodLiteral<"unavailable">;
            reason: z.ZodEnum<{
                api_unavailable: "api_unavailable";
                edition_unavailable: "edition_unavailable";
                temporarily_unavailable: "temporarily_unavailable";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            availability: z.ZodLiteral<"unknown_version">;
            reason: z.ZodLiteral<"unrecognized_response">;
        }, z.core.$strict>], "availability">;
        format: z.ZodNullable<z.ZodDiscriminatedUnion<[z.ZodObject<{
            kind: z.ZodLiteral<"known">;
            value: z.ZodEnum<{
                quicktime: "quicktime";
                mp4: "mp4";
                mxf: "mxf";
                wave: "wave";
                aiff: "aiff";
                dcp: "dcp";
                image_sequence: "image_sequence";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"unknown_version">;
            label: z.ZodString;
        }, z.core.$strict>], "kind">>;
        codec: z.ZodNullable<z.ZodDiscriminatedUnion<[z.ZodObject<{
            kind: z.ZodLiteral<"known">;
            value: z.ZodEnum<{
                h264: "h264";
                h265: "h265";
                prores: "prores";
                dnxhr: "dnxhr";
                av1: "av1";
                linear_pcm: "linear_pcm";
                aac: "aac";
                flac: "flac";
                exr: "exr";
                dpx: "dpx";
                tiff: "tiff";
                jpeg: "jpeg";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"unknown_version">;
            label: z.ZodString;
        }, z.core.$strict>], "kind">>;
        resolution: z.ZodNullable<z.ZodObject<{
            width: z.ZodNumber;
            height: z.ZodNumber;
        }, z.core.$strict>>;
        frameRate: z.ZodNullable<z.ZodNumber>;
        mode: z.ZodNullable<z.ZodDiscriminatedUnion<[z.ZodObject<{
            kind: z.ZodLiteral<"known">;
            value: z.ZodEnum<{
                individual_clips: "individual_clips";
                single_clip: "single_clip";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"unknown_version">;
            value: z.ZodString;
        }, z.core.$strict>], "kind">>;
        range: z.ZodDiscriminatedUnion<[z.ZodObject<{
            kind: z.ZodLiteral<"full_timeline">;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"custom">;
            markInFrame: z.ZodNumber;
            markOutFrame: z.ZodNumber;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"unknown">;
        }, z.core.$strict>], "kind">;
        exportVideo: z.ZodNullable<z.ZodBoolean>;
        exportAudio: z.ZodNullable<z.ZodBoolean>;
        exportSubtitles: z.ZodNullable<z.ZodBoolean>;
        customName: z.ZodNullable<z.ZodString>;
        queueCount: z.ZodNumber;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"render.queue">;
    data: z.ZodObject<{
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        queueRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        support: z.ZodDiscriminatedUnion<[z.ZodObject<{
            availability: z.ZodLiteral<"supported">;
        }, z.core.$strict>, z.ZodObject<{
            availability: z.ZodLiteral<"unavailable">;
            reason: z.ZodEnum<{
                api_unavailable: "api_unavailable";
                edition_unavailable: "edition_unavailable";
                temporarily_unavailable: "temporarily_unavailable";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            availability: z.ZodLiteral<"unknown_version">;
            reason: z.ZodLiteral<"unrecognized_response">;
        }, z.core.$strict>], "availability">;
        cursor: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "RenderQueueCursor", "out">>;
        offset: z.ZodNumber;
        pageSize: z.ZodNumber;
        jobs: z.ZodArray<z.ZodObject<{
            id: z.core.$ZodBranded<z.ZodString, "SnapshotRenderJobId", "out">;
            projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            queueRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            index: z.ZodNumber;
            name: z.ZodString;
            statusSupport: z.ZodDiscriminatedUnion<[z.ZodObject<{
                availability: z.ZodLiteral<"supported">;
            }, z.core.$strict>, z.ZodObject<{
                availability: z.ZodLiteral<"unavailable">;
                reason: z.ZodEnum<{
                    api_unavailable: "api_unavailable";
                    edition_unavailable: "edition_unavailable";
                    temporarily_unavailable: "temporarily_unavailable";
                }>;
            }, z.core.$strict>, z.ZodObject<{
                availability: z.ZodLiteral<"unknown_version">;
                reason: z.ZodLiteral<"unrecognized_response">;
            }, z.core.$strict>], "availability">;
            status: z.ZodDiscriminatedUnion<[z.ZodObject<{
                kind: z.ZodLiteral<"known">;
                value: z.ZodEnum<{
                    completed: "completed";
                    failed: "failed";
                    queued: "queued";
                    cancelled: "cancelled";
                    rendering: "rendering";
                }>;
            }, z.core.$strict>, z.ZodObject<{
                kind: z.ZodLiteral<"unknown_version">;
                value: z.ZodString;
            }, z.core.$strict>], "kind">;
            progressPercent: z.ZodNullable<z.ZodNumber>;
        }, z.core.$strict>>;
        nextCursor: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "RenderQueueCursor", "out">>;
        total: z.ZodNumber;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"render.job_status">;
    data: z.ZodObject<{
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        queueRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        support: z.ZodDiscriminatedUnion<[z.ZodObject<{
            availability: z.ZodLiteral<"supported">;
        }, z.core.$strict>, z.ZodObject<{
            availability: z.ZodLiteral<"unavailable">;
            reason: z.ZodEnum<{
                api_unavailable: "api_unavailable";
                edition_unavailable: "edition_unavailable";
                temporarily_unavailable: "temporarily_unavailable";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            availability: z.ZodLiteral<"unknown_version">;
            reason: z.ZodLiteral<"unrecognized_response">;
        }, z.core.$strict>], "availability">;
        job: z.ZodObject<{
            id: z.core.$ZodBranded<z.ZodString, "SnapshotRenderJobId", "out">;
            projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            queueRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            index: z.ZodNumber;
            name: z.ZodString;
            statusSupport: z.ZodDiscriminatedUnion<[z.ZodObject<{
                availability: z.ZodLiteral<"supported">;
            }, z.core.$strict>, z.ZodObject<{
                availability: z.ZodLiteral<"unavailable">;
                reason: z.ZodEnum<{
                    api_unavailable: "api_unavailable";
                    edition_unavailable: "edition_unavailable";
                    temporarily_unavailable: "temporarily_unavailable";
                }>;
            }, z.core.$strict>, z.ZodObject<{
                availability: z.ZodLiteral<"unknown_version">;
                reason: z.ZodLiteral<"unrecognized_response">;
            }, z.core.$strict>], "availability">;
            status: z.ZodDiscriminatedUnion<[z.ZodObject<{
                kind: z.ZodLiteral<"known">;
                value: z.ZodEnum<{
                    completed: "completed";
                    failed: "failed";
                    queued: "queued";
                    cancelled: "cancelled";
                    rendering: "rendering";
                }>;
            }, z.core.$strict>, z.ZodObject<{
                kind: z.ZodLiteral<"unknown_version">;
                value: z.ZodString;
            }, z.core.$strict>], "kind">;
            progressPercent: z.ZodNullable<z.ZodNumber>;
        }, z.core.$strict>;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"artifact.content">;
    data: z.ZodObject<{
        artifactId: z.core.$ZodBranded<z.ZodString, "ArtifactId", "out">;
        offset: z.ZodNumber;
        totalSize: z.ZodNumber;
        bytesBase64: z.ZodString;
        eof: z.ZodBoolean;
        sha256: z.ZodString;
        availableUntil: z.ZodString;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"artifact.fusion_setting.publish">;
    data: z.ZodObject<{
        artifactId: z.core.$ZodBranded<z.ZodString, "ArtifactId", "out">;
        mediaType: z.ZodLiteral<"application/x-fusion-setting">;
        byteCount: z.ZodNumber;
        sha256: z.ZodString;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"timeline.edit.preview">;
    data: z.ZodObject<{
        impactId: z.ZodString;
        action: z.ZodEnum<{
            trim: "trim";
            insert: "insert";
            overwrite: "overwrite";
            remove: "remove";
        }>;
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        intent: z.ZodDiscriminatedUnion<[z.ZodObject<{
            action: z.ZodEnum<{
                insert: "insert";
                overwrite: "overwrite";
            }>;
            placement: z.ZodDefault<z.ZodEnum<{
                video: "video";
                audio: "audio";
            }>>;
            projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
            timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            source: z.ZodObject<{
                id: z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">;
                name: z.ZodString;
                snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            }, z.core.$strict>;
            sourceRange: z.ZodObject<{
                domain: z.ZodLiteral<"source_range" | "timeline_record_range">;
                unit: z.ZodLiteral<"frames">;
                start: z.ZodNumber;
                endExclusive: z.ZodNumber;
            }, z.core.$strict>;
            at: z.ZodObject<{
                domain: z.ZodLiteral<"timeline_record">;
                value: z.ZodObject<{
                    kind: z.ZodLiteral<"frames">;
                    value: z.ZodNumber;
                }, z.core.$strict>;
            }, z.core.$strict>;
            videoTrackIndex: z.ZodNullable<z.ZodNumber>;
            audioTrackIndex: z.ZodNullable<z.ZodNumber>;
            linkedAudio: z.ZodEnum<{
                include: "include";
                exclude: "exclude";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            action: z.ZodLiteral<"trim">;
            projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
            timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
            clipName: z.ZodString;
            trackIndex: z.ZodNumber;
            currentRecordRange: z.ZodObject<{
                domain: z.ZodLiteral<"source_range" | "timeline_record_range">;
                unit: z.ZodLiteral<"frames">;
                start: z.ZodNumber;
                endExclusive: z.ZodNumber;
            }, z.core.$strict>;
            headFrames: z.ZodNumber;
            tailFrames: z.ZodNumber;
            linkedAudio: z.ZodEnum<{
                exclude: "exclude";
                preserve: "preserve";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            action: z.ZodLiteral<"remove">;
            projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
            timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
            clipName: z.ZodString;
            trackType: z.ZodEnum<{
                video: "video";
                audio: "audio";
                subtitle: "subtitle";
            }>;
            trackIndex: z.ZodNumber;
            currentRecordRange: z.ZodObject<{
                domain: z.ZodLiteral<"source_range" | "timeline_record_range">;
                unit: z.ZodLiteral<"frames">;
                start: z.ZodNumber;
                endExclusive: z.ZodNumber;
            }, z.core.$strict>;
            linkedItems: z.ZodLiteral<"exclude">;
        }, z.core.$strict>], "action">;
        recordRange: z.ZodObject<{
            domain: z.ZodLiteral<"source_range" | "timeline_record_range">;
            unit: z.ZodLiteral<"frames">;
            start: z.ZodNumber;
            endExclusive: z.ZodNumber;
        }, z.core.$strict>;
        affectedTracks: z.ZodArray<z.ZodObject<{
            type: z.ZodEnum<{
                video: "video";
                audio: "audio";
                subtitle: "subtitle";
            }>;
            index: z.ZodNumber;
            snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotTrackId", "out">;
        }, z.core.$strict>>;
        affectedItems: z.ZodArray<z.ZodObject<{
            id: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
            track: z.ZodObject<{
                type: z.ZodEnum<{
                    video: "video";
                    audio: "audio";
                    subtitle: "subtitle";
                }>;
                index: z.ZodNumber;
                snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotTrackId", "out">;
            }, z.core.$strict>;
            recordRange: z.ZodObject<{
                domain: z.ZodLiteral<"source_range" | "timeline_record_range">;
                unit: z.ZodLiteral<"frames">;
                start: z.ZodNumber;
                endExclusive: z.ZodNumber;
            }, z.core.$strict>;
            role: z.ZodEnum<{
                replace: "replace";
                trim: "trim";
                remove: "remove";
                linked: "linked";
                protected_overlap: "protected_overlap";
                protected_neighbor: "protected_neighbor";
            }>;
        }, z.core.$strict>>;
        protectedItems: z.ZodArray<z.ZodObject<{
            id: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
            track: z.ZodObject<{
                type: z.ZodEnum<{
                    video: "video";
                    audio: "audio";
                    subtitle: "subtitle";
                }>;
                index: z.ZodNumber;
                snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotTrackId", "out">;
            }, z.core.$strict>;
            recordRange: z.ZodObject<{
                domain: z.ZodLiteral<"source_range" | "timeline_record_range">;
                unit: z.ZodLiteral<"frames">;
                start: z.ZodNumber;
                endExclusive: z.ZodNumber;
            }, z.core.$strict>;
            role: z.ZodEnum<{
                replace: "replace";
                trim: "trim";
                remove: "remove";
                linked: "linked";
                protected_overlap: "protected_overlap";
                protected_neighbor: "protected_neighbor";
            }>;
        }, z.core.$strict>>;
        expectedItems: z.ZodArray<z.ZodObject<{
            role: z.ZodEnum<{
                replacement: "replacement";
                preserved_edge: "preserved_edge";
                trimmed: "trimmed";
                unlinked: "unlinked";
            }>;
            beforeItemId: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>;
            track: z.ZodObject<{
                type: z.ZodEnum<{
                    video: "video";
                    audio: "audio";
                    subtitle: "subtitle";
                }>;
                index: z.ZodNumber;
                snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotTrackId", "out">;
            }, z.core.$strict>;
            recordRange: z.ZodObject<{
                domain: z.ZodLiteral<"source_range" | "timeline_record_range">;
                unit: z.ZodLiteral<"frames">;
                start: z.ZodNumber;
                endExclusive: z.ZodNumber;
            }, z.core.$strict>;
            sourceRange: z.ZodObject<{
                domain: z.ZodLiteral<"source_range" | "timeline_record_range">;
                unit: z.ZodLiteral<"frames">;
                start: z.ZodNumber;
                endExclusive: z.ZodNumber;
            }, z.core.$strict>;
            sourceEndToleranceFrames: z.ZodNumber;
            mediaPoolItemId: z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">;
            name: z.ZodString;
            linkedExpectedItemIndexes: z.ZodArray<z.ZodNumber>;
            linkedExistingItemIds: z.ZodArray<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>;
        }, z.core.$strict>>;
        expectedLinkTransitions: z.ZodDefault<z.ZodArray<z.ZodObject<{
            itemId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
            beforeLinkedItemIds: z.ZodArray<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>;
            afterLinkedItemIds: z.ZodArray<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>;
        }, z.core.$strict>>>;
        linkedAudio: z.ZodObject<{
            behavior: z.ZodEnum<{
                include: "include";
                exclude: "exclude";
                preserve: "preserve";
            }>;
            topologyProven: z.ZodBoolean;
        }, z.core.$strict>;
        capabilityId: z.ZodEnum<{
            "edit.insert_overwrite": "edit.insert_overwrite";
            "edit.trim_workaround": "edit.trim_workaround";
            "timeline.items_delete": "timeline.items_delete";
        }>;
        summary: z.ZodString;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"timeline.managed.preview">;
    data: z.ZodObject<{
        status: z.ZodEnum<{
            blocked: "blocked";
            no_change: "no_change";
            ready: "ready";
        }>;
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        ownershipId: z.ZodString;
        scope: z.ZodDiscriminatedUnion<[z.ZodObject<{
            kind: z.ZodLiteral<"whole_timeline">;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"region">;
            startFrame: z.ZodNumber;
            endExclusiveFrame: z.ZodNumber;
        }, z.core.$strict>], "kind">;
        desiredStateDigest: z.ZodString;
        contextDigest: z.ZodString;
        protectedStateDigest: z.ZodString;
        previewDigest: z.ZodString;
        ownershipGeneration: z.ZodNumber;
        policyRevision: z.ZodString;
        capabilityDigest: z.ZodString;
        drift: z.ZodArray<z.ZodObject<{
            kind: z.ZodEnum<{
                create: "create";
                update: "update";
                preserve: "preserve";
                remove: "remove";
            }>;
            key: z.ZodString;
            timelineItemId: z.ZodOptional<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>;
            summary: z.ZodString;
        }, z.core.$strict>>;
        blockers: z.ZodArray<z.ZodObject<{
            code: z.ZodEnum<{
                stale_revision: "stale_revision";
                ambiguous_identity: "ambiguous_identity";
                scope_crossing: "scope_crossing";
                unsupported_change: "unsupported_change";
                protected_state_unproven: "protected_state_unproven";
                ownership_overlap: "ownership_overlap";
            }>;
            key: z.ZodOptional<z.ZodString>;
            message: z.ZodString;
        }, z.core.$strict>>;
    }, z.core.$strict>;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"timeline.managed.export">;
    data: z.ZodDiscriminatedUnion<[z.ZodObject<{
        status: z.ZodLiteral<"ready">;
        dialect: z.ZodLiteral<"cutagent.managed-timeline">;
        version: z.ZodLiteral<1>;
        program: z.ZodObject<{
            projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
            revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            ownershipId: z.ZodString;
            scope: z.ZodDiscriminatedUnion<[z.ZodObject<{
                kind: z.ZodLiteral<"whole_timeline">;
            }, z.core.$strict>, z.ZodObject<{
                kind: z.ZodLiteral<"region">;
                startFrame: z.ZodNumber;
                endExclusiveFrame: z.ZodNumber;
            }, z.core.$strict>], "kind">;
            timelineFrameRate: z.ZodObject<{
                numerator: z.ZodNumber;
                denominator: z.ZodNumber;
                nominalTimebase: z.ZodNumber;
            }, z.core.$strict>;
            elements: z.ZodArray<z.ZodObject<{
                key: z.ZodString;
                assetId: z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">;
                assetName: z.ZodString;
                assetRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
                videoTrack: z.ZodNumber;
                audioTrack: z.ZodNullable<z.ZodNumber>;
                atFrame: z.ZodNumber;
                sourceStartFrame: z.ZodNumber;
                sourceEndExclusiveFrame: z.ZodNumber;
                sourceFrameRate: z.ZodObject<{
                    numerator: z.ZodNumber;
                    denominator: z.ZodNumber;
                    nominalTimebase: z.ZodNumber;
                }, z.core.$strict>;
                linkedAudio: z.ZodEnum<{
                    include: "include";
                    exclude: "exclude";
                }>;
                adoptTimelineItemId: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>;
            }, z.core.$strict>>;
        }, z.core.$strict>;
        assets: z.ZodArray<z.ZodObject<{
            id: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">>;
            snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolItemId", "out">;
            folderSnapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolFolderId", "out">;
            snapshotRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            name: z.ZodString;
            kind: z.ZodEnum<{
                unknown: "unknown";
                timeline: "timeline";
                multicam: "multicam";
                fusion_composition: "fusion_composition";
                video: "video";
                audio: "audio";
                still: "still";
                compound: "compound";
                generator: "generator";
            }>;
            selected: z.ZodBoolean;
            sourceFileName: z.ZodNullable<z.ZodString>;
            duration: z.ZodNullable<z.ZodString>;
            resolution: z.ZodNullable<z.ZodString>;
            frameRate: z.ZodNullable<z.ZodString>;
            startTimecode: z.ZodNullable<z.ZodString>;
            metadata: z.ZodArray<z.ZodObject<{
                key: z.ZodEnum<{
                    description: "description";
                    comments: "comments";
                    keywords: "keywords";
                    shot: "shot";
                    scene: "scene";
                    take: "take";
                    angle: "angle";
                    camera: "camera";
                    reel: "reel";
                    dateRecorded: "dateRecorded";
                    goodTake: "goodTake";
                    clipColor: "clipColor";
                }>;
                value: z.ZodString;
            }, z.core.$strict>>;
        }, z.core.$strict>>;
        coverage: z.ZodObject<{
            represented: z.ZodTuple<[z.ZodLiteral<"clip_placement/v1">], null>;
            preservedButNotRepresented: z.ZodTuple<[z.ZodLiteral<"unmanaged_clips">, z.ZodLiteral<"track_properties">, z.ZodLiteral<"markers">, z.ZodLiteral<"fusion">, z.ZodLiteral<"color">, z.ZodLiteral<"fairlight">, z.ZodLiteral<"retime">, z.ZodLiteral<"transitions">, z.ZodLiteral<"effects">, z.ZodLiteral<"captions">], null>;
            protectedStateDigest: z.ZodString;
        }, z.core.$strict>;
        blockers: z.ZodTuple<[], null>;
    }, z.core.$strict>, z.ZodObject<{
        status: z.ZodLiteral<"blocked">;
        dialect: z.ZodLiteral<"cutagent.managed-timeline">;
        version: z.ZodLiteral<1>;
        document: z.ZodNull;
        blockers: z.ZodArray<z.ZodObject<{
            code: z.ZodEnum<{
                stale_revision: "stale_revision";
                ambiguous_identity: "ambiguous_identity";
                scope_crossing: "scope_crossing";
                unsupported_change: "unsupported_change";
                protected_state_unproven: "protected_state_unproven";
                ownership_overlap: "ownership_overlap";
            }>;
            key: z.ZodOptional<z.ZodString>;
            message: z.ZodString;
        }, z.core.$strict>>;
    }, z.core.$strict>], "status">;
}, z.core.$strict>, z.ZodObject<{
    ok: z.ZodLiteral<true>;
    protocolVersion: z.ZodLiteral<1>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operation: z.ZodLiteral<"multicam.inspect">;
    data: z.ZodObject<{
        id: z.core.$ZodBranded<z.ZodString, "MulticamId", "out">;
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        name: z.ZodString;
        angles: z.ZodArray<z.ZodObject<{
            id: z.core.$ZodBranded<z.ZodString, "MulticamAngleId", "out">;
            label: z.ZodString;
            enabled: z.ZodNullable<z.ZodBoolean>;
            sources: z.ZodArray<z.ZodObject<{
                mediaPoolItemId: z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">;
                name: z.ZodString;
            }, z.core.$strict>>;
        }, z.core.$strict>>;
    }, z.core.$strict>;
}, z.core.$strict>], "operation">, z.ZodObject<{
    ok: z.ZodLiteral<false>;
    requestId: z.ZodOptional<z.core.$ZodBranded<z.ZodString, "RequestId", "out">>;
    error: z.ZodObject<{
        code: z.ZodUnion<readonly [z.ZodEnum<{
            RUNTIME_UNAVAILABLE: "RUNTIME_UNAVAILABLE";
            SDK_INCOMPATIBLE: "SDK_INCOMPATIBLE";
            AUTHENTICATION_REQUIRED: "AUTHENTICATION_REQUIRED";
            SUBSCRIPTION_REQUIRED: "SUBSCRIPTION_REQUIRED";
            INVALID_REQUEST: "INVALID_REQUEST";
            BOOTSTRAP_REJECTED: "BOOTSTRAP_REJECTED";
            SESSION_REJECTED: "SESSION_REJECTED";
            SESSION_LIMIT_REACHED: "SESSION_LIMIT_REACHED";
            INTERNAL_ERROR: "INTERNAL_ERROR";
        }>, z.ZodEnum<{
            USAGE_EXHAUSTED: "USAGE_EXHAUSTED";
            INVALID_RESPONSE: "INVALID_RESPONSE";
            CAPABILITY_UNAVAILABLE: "CAPABILITY_UNAVAILABLE";
            TARGET_NOT_FOUND: "TARGET_NOT_FOUND";
            AMBIGUOUS_TARGET: "AMBIGUOUS_TARGET";
            STALE_REVISION: "STALE_REVISION";
            RUNTIME_TIMEOUT: "RUNTIME_TIMEOUT";
            TEMPORARY_PROVIDER_FAILURE: "TEMPORARY_PROVIDER_FAILURE";
        }>]>;
        message: z.ZodString;
        recovery: z.ZodUnion<readonly [z.ZodEnum<{
            upgrade_or_wait: "upgrade_or_wait";
            restart_runtime: "restart_runtime";
            update_required: "update_required";
            contact_support: "contact_support";
            sign_in: "sign_in";
            reconnect: "reconnect";
        }>, z.ZodEnum<{
            retry: "retry";
            inspect_state: "inspect_state";
        }>]>;
    }, z.core.$strict>;
}, z.core.$strict>]>;
export type SdkRuntimeDistribution = z.infer<typeof sdkRuntimeDistributionSchema>;
export type SdkCompatibilityHandshakeRequest = z.infer<typeof sdkCompatibilityHandshakeRequestSchema>;
export type SdkCompatibilityDescriptor = z.infer<typeof sdkCompatibilityDescriptorSchema>;
export type SdkCompatibilityHandshakeResponse = z.infer<typeof sdkCompatibilityHandshakeResponseSchema>;
export type SdkDesktopDiscovery = z.infer<typeof sdkDesktopDiscoverySchema>;
export type SdkRuntimeConnectRequest = z.infer<typeof sdkRuntimeConnectRequestSchema>;
export type SdkRuntimeSessionConnectRequest = z.infer<typeof sdkRuntimeSessionConnectRequestSchema>;
export type SdkRuntimeConnectResponse = z.infer<typeof sdkRuntimeConnectResponseSchema>;
export type SdkRuntimeConnectSuccess = z.infer<typeof sdkRuntimeConnectSuccessSchema>;
export type SdkRuntimeCloseRequest = z.infer<typeof sdkRuntimeCloseRequestSchema>;
export type SdkRuntimeCloseResponse = z.infer<typeof sdkRuntimeCloseResponseSchema>;
export type SdkRuntimeConfirmRequest = z.infer<typeof sdkRuntimeConfirmRequestSchema>;
export type SdkRuntimeConfirmResponse = z.infer<typeof sdkRuntimeConfirmResponseSchema>;
export type SdkProjectReference = z.infer<typeof sdkProjectReferenceSchema>;
export type SdkTimelineReference = z.infer<typeof sdkTimelineReferenceSchema>;
export type SdkTimelineSnapshot = z.infer<typeof sdkTimelineSnapshotSchema>;
export type SdkMediaPoolPage = z.infer<typeof sdkMediaPoolPageSchema>;
export type SdkMediaPoolSearch = z.infer<typeof sdkMediaPoolSearchSchema>;
export type SdkColorTargetSnapshot = z.infer<typeof sdkColorTargetSnapshotSchema>;
export type SdkRenderDiscovery = z.infer<typeof sdkRenderDiscoverySchema>;
export type SdkRenderPresets = z.infer<typeof sdkRenderPresetsSchema>;
export type SdkRenderSettingsSnapshot = z.infer<typeof sdkRenderSettingsSnapshotSchema>;
export type SdkRenderQueuePage = z.infer<typeof sdkRenderQueuePageSchema>;
export type SdkRenderJobStatusSnapshot = z.infer<typeof sdkRenderJobStatusSnapshotSchema>;
export type SdkArtifactContentChunk = z.infer<typeof sdkArtifactContentChunkSchema>;
export type SdkTimelineEditIntent = z.infer<typeof sdkTimelineEditIntentSchema>;
export type SdkTimelineEditImpact = z.infer<typeof sdkTimelineEditImpactSchema>;
export type SdkRuntimeReadRequest = z.infer<typeof sdkRuntimeReadRequestSchema>;
export type SdkRuntimeReadResponse = z.infer<typeof sdkRuntimeReadResponseSchema>;
