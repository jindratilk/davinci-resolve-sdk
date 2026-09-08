import { z } from "zod";
export declare const CUTAGENT_SDK_FUSION_GRAPH_ACTION_ID: "cutagent.action.fusion.apply";
export declare const CUTAGENT_SDK_FUSION_GRAPH_CONTRACT_VERSION: 1;
export declare const sdkFusionAnimationSchema: z.ZodObject<{
    kind: z.ZodLiteral<"keyframes">;
    keyframes: z.ZodArray<z.ZodObject<{
        time: z.ZodNumber;
        value: z.ZodUnion<readonly [z.ZodNumber, z.ZodString, z.ZodBoolean, z.ZodTuple<[z.ZodNumber, z.ZodNumber], null>, z.ZodTuple<[z.ZodNumber, z.ZodNumber, z.ZodNumber], null>, z.ZodTuple<[z.ZodNumber, z.ZodNumber, z.ZodNumber, z.ZodNumber], null>]>;
    }, z.core.$strict>>;
}, z.core.$strict>;
export declare const sdkFusionGraphRequestSchema: z.ZodObject<{
    graph: z.ZodObject<{
        animations: z.ZodArray<z.ZodObject<{
            node: z.ZodString;
            input: z.ZodString;
            animation: z.ZodObject<{
                kind: z.ZodLiteral<"keyframes">;
                keyframes: z.ZodArray<z.ZodObject<{
                    time: z.ZodNumber;
                    value: z.ZodUnion<readonly [z.ZodNumber, z.ZodString, z.ZodBoolean, z.ZodTuple<[z.ZodNumber, z.ZodNumber], null>, z.ZodTuple<[z.ZodNumber, z.ZodNumber, z.ZodNumber], null>, z.ZodTuple<[z.ZodNumber, z.ZodNumber, z.ZodNumber, z.ZodNumber], null>]>;
                }, z.core.$strict>>;
            }, z.core.$strict>;
        }, z.core.$strict>>;
        connections: z.ZodArray<z.ZodObject<{
            source: z.ZodObject<{
                node: z.ZodString;
                port: z.ZodString;
            }, z.core.$strict>;
            target: z.ZodObject<{
                node: z.ZodString;
                port: z.ZodString;
            }, z.core.$strict>;
        }, z.core.$strict>>;
        nodes: z.ZodArray<z.ZodObject<{
            id: z.ZodString;
            inputs: z.ZodRecord<z.ZodString, z.ZodUnion<readonly [z.ZodNumber, z.ZodString, z.ZodBoolean, z.ZodTuple<[z.ZodNumber, z.ZodNumber], null>, z.ZodTuple<[z.ZodNumber, z.ZodNumber, z.ZodNumber], null>, z.ZodTuple<[z.ZodNumber, z.ZodNumber, z.ZodNumber, z.ZodNumber], null>]>>;
            type: z.ZodString;
        }, z.core.$strict>>;
        outputs: z.ZodArray<z.ZodString>;
    }, z.core.$strict>;
    registryDigest: z.ZodString;
    schema: z.ZodLiteral<"cutagent.fusion.graph-request">;
    schemaVersion: z.ZodLiteral<1>;
}, z.core.$strict>;
export declare const sdkFusionCompositionReferenceSchema: z.ZodObject<{
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
}, z.core.$strict>;
export declare const sdkFusionGraphImpactPreviewSchema: z.ZodObject<{
    kind: z.ZodLiteral<"fusion_graph_replace">;
    target: z.ZodObject<{
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
    }, z.core.$strict>;
    precondition: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    registryDigest: z.ZodString;
    graphDigest: z.ZodString;
    intendedEffects: z.ZodArray<z.ZodEnum<{
        replace_nodes: "replace_nodes";
        replace_connections: "replace_connections";
        replace_inputs: "replace_inputs";
        replace_animation: "replace_animation";
    }>>;
    protectedState: z.ZodArray<z.ZodEnum<{
        project_identity: "project_identity";
        timeline_identity: "timeline_identity";
        timeline_item_identity: "timeline_item_identity";
        other_timeline_items: "other_timeline_items";
        other_fusion_compositions: "other_fusion_compositions";
    }>>;
    minimumEvidence: z.ZodTuple<[z.ZodLiteral<"readback">, z.ZodLiteral<"structural">], null>;
}, z.core.$strict>;
export declare const sdkFusionGraphApplyInputSchema: z.ZodObject<{
    contractVersion: z.ZodLiteral<1>;
    target: z.ZodObject<{
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
    }, z.core.$strict>;
    precondition: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    graph: z.ZodObject<{
        graph: z.ZodObject<{
            animations: z.ZodArray<z.ZodObject<{
                node: z.ZodString;
                input: z.ZodString;
                animation: z.ZodObject<{
                    kind: z.ZodLiteral<"keyframes">;
                    keyframes: z.ZodArray<z.ZodObject<{
                        time: z.ZodNumber;
                        value: z.ZodUnion<readonly [z.ZodNumber, z.ZodString, z.ZodBoolean, z.ZodTuple<[z.ZodNumber, z.ZodNumber], null>, z.ZodTuple<[z.ZodNumber, z.ZodNumber, z.ZodNumber], null>, z.ZodTuple<[z.ZodNumber, z.ZodNumber, z.ZodNumber, z.ZodNumber], null>]>;
                    }, z.core.$strict>>;
                }, z.core.$strict>;
            }, z.core.$strict>>;
            connections: z.ZodArray<z.ZodObject<{
                source: z.ZodObject<{
                    node: z.ZodString;
                    port: z.ZodString;
                }, z.core.$strict>;
                target: z.ZodObject<{
                    node: z.ZodString;
                    port: z.ZodString;
                }, z.core.$strict>;
            }, z.core.$strict>>;
            nodes: z.ZodArray<z.ZodObject<{
                id: z.ZodString;
                inputs: z.ZodRecord<z.ZodString, z.ZodUnion<readonly [z.ZodNumber, z.ZodString, z.ZodBoolean, z.ZodTuple<[z.ZodNumber, z.ZodNumber], null>, z.ZodTuple<[z.ZodNumber, z.ZodNumber, z.ZodNumber], null>, z.ZodTuple<[z.ZodNumber, z.ZodNumber, z.ZodNumber, z.ZodNumber], null>]>>;
                type: z.ZodString;
            }, z.core.$strict>>;
            outputs: z.ZodArray<z.ZodString>;
        }, z.core.$strict>;
        registryDigest: z.ZodString;
        schema: z.ZodLiteral<"cutagent.fusion.graph-request">;
        schemaVersion: z.ZodLiteral<1>;
    }, z.core.$strict>;
    preview: z.ZodObject<{
        kind: z.ZodLiteral<"fusion_graph_replace">;
        target: z.ZodObject<{
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
        }, z.core.$strict>;
        precondition: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        registryDigest: z.ZodString;
        graphDigest: z.ZodString;
        intendedEffects: z.ZodArray<z.ZodEnum<{
            replace_nodes: "replace_nodes";
            replace_connections: "replace_connections";
            replace_inputs: "replace_inputs";
            replace_animation: "replace_animation";
        }>>;
        protectedState: z.ZodArray<z.ZodEnum<{
            project_identity: "project_identity";
            timeline_identity: "timeline_identity";
            timeline_item_identity: "timeline_item_identity";
            other_timeline_items: "other_timeline_items";
            other_fusion_compositions: "other_fusion_compositions";
        }>>;
        minimumEvidence: z.ZodTuple<[z.ZodLiteral<"readback">, z.ZodLiteral<"structural">], null>;
    }, z.core.$strict>;
    idempotencyKey: z.core.$ZodBranded<z.ZodString, "IdempotencyKey", "out">;
}, z.core.$strict>;
export declare const sdkFusionGraphApplyResultSchema: z.ZodObject<{
    target: z.ZodObject<{
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
    }, z.core.$strict>;
    registryDigest: z.ZodString;
    appliedGraphDigest: z.ZodString;
    readback: z.ZodObject<{
        graphDigest: z.ZodString;
        nodes: z.ZodArray<z.ZodObject<{
            id: z.ZodString;
            type: z.ZodString;
            inputsDigest: z.ZodString;
        }, z.core.$strict>>;
        connections: z.ZodArray<z.ZodObject<{
            source: z.ZodObject<{
                node: z.ZodString;
                port: z.ZodString;
            }, z.core.$strict>;
            target: z.ZodObject<{
                node: z.ZodString;
                port: z.ZodString;
            }, z.core.$strict>;
        }, z.core.$strict>>;
        animatedInputs: z.ZodNumber;
    }, z.core.$strict>;
    renderedEvidence: z.ZodArray<z.ZodObject<{
        frame: z.ZodNumber;
        artifactId: z.ZodString;
        digest: z.ZodString;
        mediaType: z.ZodLiteral<"image/jpeg">;
    }, z.core.$strict>>;
    renderedReview: z.ZodObject<{
        outcome: z.ZodLiteral<"not_run">;
    }, z.core.$strict>;
    semanticReview: z.ZodObject<{
        outcome: z.ZodLiteral<"not_run">;
    }, z.core.$strict>;
    temporalReview: z.ZodObject<{
        required: z.ZodBoolean;
        sampledFrames: z.ZodArray<z.ZodNumber>;
        outcome: z.ZodLiteral<"not_run">;
    }, z.core.$strict>;
    protectedStatePreserved: z.ZodLiteral<true>;
}, z.core.$strict>;
export type SdkFusionCompositionReference = z.infer<typeof sdkFusionCompositionReferenceSchema>;
export type SdkFusionGraphImpactPreview = z.infer<typeof sdkFusionGraphImpactPreviewSchema>;
export type SdkFusionGraphApplyInput = z.infer<typeof sdkFusionGraphApplyInputSchema>;
export type SdkFusionGraphApplyResult = z.infer<typeof sdkFusionGraphApplyResultSchema>;
