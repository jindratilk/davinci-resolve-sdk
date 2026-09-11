import { z } from "zod";
export declare const CUTAGENT_MUTATION_POLICY_CONTRACT_VERSION: 1;
export declare const sdkStableTargetIdSchema: z.ZodString;
export declare const sdkStateRevisionSchema: z.ZodString;
export declare const sdkSha256DigestSchema: z.ZodString;
export declare const sdkConstraintBindingLevelSchema: z.ZodEnum<{
    project: "project";
    "account/project-library": "account/project-library";
    "project+timeline": "project+timeline";
}>;
export declare const sdkProtectedTargetKindSchema: z.ZodEnum<{
    project: "project";
    timeline: "timeline";
    marker: "marker";
    fusion_composition: "fusion_composition";
    project_library: "project_library";
    track: "track";
    clip: "clip";
    media: "media";
    runtime_setting: "runtime_setting";
}>;
export declare const sdkTrackTypeSchema: z.ZodEnum<{
    video: "video";
    audio: "audio";
    subtitle: "subtitle";
}>;
export declare const sdkProtectedMediaRoleSchema: z.ZodEnum<{
    music: "music";
    dialogue: "dialogue";
    voiceover: "voiceover";
    ambience: "ambience";
    effects: "effects";
    other: "other";
}>;
export declare const sdkStableMutationTargetSchema: z.ZodObject<{
    kind: z.ZodEnum<{
        project: "project";
        timeline: "timeline";
        marker: "marker";
        fusion_composition: "fusion_composition";
        project_library: "project_library";
        track: "track";
        clip: "clip";
        media: "media";
        runtime_setting: "runtime_setting";
    }>;
    stableId: z.ZodString;
    revision: z.ZodString;
    trackType: z.ZodOptional<z.ZodEnum<{
        video: "video";
        audio: "audio";
        subtitle: "subtitle";
    }>>;
    trackIndex: z.ZodOptional<z.ZodNumber>;
    mediaRole: z.ZodOptional<z.ZodEnum<{
        music: "music";
        dialogue: "dialogue";
        voiceover: "voiceover";
        ambience: "ambience";
        effects: "effects";
        other: "other";
    }>>;
}, z.core.$strict>;
export declare const sdkMutationCarrierSchema: z.ZodEnum<{
    sdk: "sdk";
    desktop: "desktop";
    plugin: "plugin";
    cli: "cli";
    batch: "batch";
    composition: "composition";
}>;
export declare const sdkMutationImpactStatusSchema: z.ZodEnum<{
    unknown: "unknown";
    read: "read";
    mutation: "mutation";
}>;
export declare const sdkMutationEffectSchema: z.ZodObject<{
    operation: z.ZodString;
    kind: z.ZodEnum<{
        unknown: "unknown";
        create: "create";
        update: "update";
        delete: "delete";
        blade: "blade";
    }>;
    trackTypes: z.ZodArray<z.ZodEnum<{
        video: "video";
        audio: "audio";
        subtitle: "subtitle";
    }>>;
    targets: z.ZodArray<z.ZodObject<{
        kind: z.ZodEnum<{
            project: "project";
            timeline: "timeline";
            marker: "marker";
            fusion_composition: "fusion_composition";
            project_library: "project_library";
            track: "track";
            clip: "clip";
            media: "media";
            runtime_setting: "runtime_setting";
        }>;
        stableId: z.ZodString;
        revision: z.ZodString;
        trackType: z.ZodOptional<z.ZodEnum<{
            video: "video";
            audio: "audio";
            subtitle: "subtitle";
        }>>;
        trackIndex: z.ZodOptional<z.ZodNumber>;
        mediaRole: z.ZodOptional<z.ZodEnum<{
            music: "music";
            dialogue: "dialogue";
            voiceover: "voiceover";
            ambience: "ambience";
            effects: "effects";
            other: "other";
        }>>;
    }, z.core.$strict>>;
    placementIntent: z.ZodEnum<{
        unknown: "unknown";
        marker: "marker";
        explicit: "explicit";
    }>;
    broad: z.ZodBoolean;
    ambiguous: z.ZodBoolean;
    complete: z.ZodBoolean;
}, z.core.$strict>;
export declare const sdkMutationVerificationPolicySchema: z.ZodObject<{
    minimumEvidence: z.ZodArray<z.ZodEnum<{
        file: "file";
        readback: "readback";
        structural: "structural";
        rendered: "rendered";
        visual: "visual";
        auditioned: "auditioned";
    }>>;
    requireProtectedStatePreserved: z.ZodBoolean;
    protectedTargetEvidence: z.ZodEnum<{
        none: "none";
        every_declared_target: "every_declared_target";
    }>;
}, z.core.$strict>;
export declare const sdkMutationImpactSchema: z.ZodObject<{
    contractVersion: z.ZodLiteral<1>;
    carrier: z.ZodEnum<{
        sdk: "sdk";
        desktop: "desktop";
        plugin: "plugin";
        cli: "cli";
        batch: "batch";
        composition: "composition";
    }>;
    status: z.ZodEnum<{
        unknown: "unknown";
        read: "read";
        mutation: "mutation";
    }>;
    minimumBinding: z.ZodEnum<{
        project: "project";
        "account/project-library": "account/project-library";
        "project+timeline": "project+timeline";
    }>;
    registryDigest: z.ZodString;
    canonicalRequestDigest: z.ZodString;
    referencedPayloadDigests: z.ZodArray<z.ZodString>;
    requestId: z.core.$ZodBranded<z.ZodString, "RequestId", "out">;
    operationId: z.core.$ZodBranded<z.ZodString, "OperationId", "out">;
    executionId: z.core.$ZodBranded<z.ZodString, "ExecutionId", "out">;
    projectLibraryId: z.ZodString;
    projectId: z.ZodOptional<z.ZodString>;
    timelineId: z.ZodOptional<z.ZodString>;
    projectRevision: z.ZodOptional<z.ZodString>;
    timelineRevision: z.ZodOptional<z.ZodString>;
    effects: z.ZodArray<z.ZodObject<{
        operation: z.ZodString;
        kind: z.ZodEnum<{
            unknown: "unknown";
            create: "create";
            update: "update";
            delete: "delete";
            blade: "blade";
        }>;
        trackTypes: z.ZodArray<z.ZodEnum<{
            video: "video";
            audio: "audio";
            subtitle: "subtitle";
        }>>;
        targets: z.ZodArray<z.ZodObject<{
            kind: z.ZodEnum<{
                project: "project";
                timeline: "timeline";
                marker: "marker";
                fusion_composition: "fusion_composition";
                project_library: "project_library";
                track: "track";
                clip: "clip";
                media: "media";
                runtime_setting: "runtime_setting";
            }>;
            stableId: z.ZodString;
            revision: z.ZodString;
            trackType: z.ZodOptional<z.ZodEnum<{
                video: "video";
                audio: "audio";
                subtitle: "subtitle";
            }>>;
            trackIndex: z.ZodOptional<z.ZodNumber>;
            mediaRole: z.ZodOptional<z.ZodEnum<{
                music: "music";
                dialogue: "dialogue";
                voiceover: "voiceover";
                ambience: "ambience";
                effects: "effects";
                other: "other";
            }>>;
        }, z.core.$strict>>;
        placementIntent: z.ZodEnum<{
            unknown: "unknown";
            marker: "marker";
            explicit: "explicit";
        }>;
        broad: z.ZodBoolean;
        ambiguous: z.ZodBoolean;
        complete: z.ZodBoolean;
    }, z.core.$strict>>;
    closedComposition: z.ZodBoolean;
    complete: z.ZodBoolean;
    ambiguous: z.ZodBoolean;
    broad: z.ZodBoolean;
    executableStableTargetPrecondition: z.ZodBoolean;
    verificationPolicy: z.ZodObject<{
        minimumEvidence: z.ZodArray<z.ZodEnum<{
            file: "file";
            readback: "readback";
            structural: "structural";
            rendered: "rendered";
            visual: "visual";
            auditioned: "auditioned";
        }>>;
        requireProtectedStatePreserved: z.ZodBoolean;
        protectedTargetEvidence: z.ZodEnum<{
            none: "none";
            every_declared_target: "every_declared_target";
        }>;
    }, z.core.$strict>;
}, z.core.$strict>;
export type SdkMutationImpact = z.infer<typeof sdkMutationImpactSchema>;
