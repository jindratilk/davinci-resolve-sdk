import { z } from "zod";
export declare const CUTAGENT_SDK_FUSION_GRAPH_ACTION_ID: "cutagent.action.fusion.apply";
export declare const CUTAGENT_SDK_FUSION_GRAPH_CONTRACT_VERSION: 1;
export declare const CUTAGENT_SDK_FUSION_IMAGE_REPLACE_ACTION_ID: "cutagent.action.fusion.image.batch";
export declare const CUTAGENT_SDK_FUSION_IMAGE_REPLACE_CONTRACT_VERSION: 1;
export declare const CUTAGENT_SDK_FUSION_TEXT_ACTION_ID: "cutagent.action.fusion.text.batch";
export declare const CUTAGENT_SDK_FUSION_NESTED_TEXT_ACTION_ID: "cutagent.action.fusion.nested_text.batch";
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
export declare const sdkFusionTextUpdateSchema: z.ZodObject<{
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
    toolName: z.ZodString;
    inputName: z.ZodString;
    text: z.ZodString;
}, z.core.$strict>;
export declare const sdkFusionTextActionInputSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
    revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    updates: z.ZodArray<z.ZodObject<{
        timelineItemId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
        compositionIndex: z.ZodNumber;
        compositionRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        toolName: z.ZodString;
        inputName: z.ZodString;
        text: z.ZodString;
    }, z.core.$strict>>;
}, z.core.$strict>;
export declare const sdkFusionTextActionResultSchema: z.ZodObject<{
    actionId: z.ZodLiteral<"cutagent.action.fusion.text.batch">;
    textUpdates: z.ZodObject<{
        updates: z.ZodArray<z.ZodObject<{
            timelineItemId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
            compositionIndex: z.ZodNumber;
            toolName: z.ZodString;
            inputName: z.ZodString;
            text: z.ZodString;
            verified: z.ZodLiteral<true>;
        }, z.core.$strict>>;
        revision: z.ZodObject<{
            revisionBefore: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            revisionAfter: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            changed: z.ZodBoolean;
        }, z.core.$strict>;
    }, z.core.$strict>;
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
export declare const sdkFusionImageReplaceInputSchema: z.ZodObject<{
    contractVersion: z.ZodLiteral<1>;
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
    revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    items: z.ZodArray<z.ZodObject<{
        timelineItemId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
        compositionIndex: z.ZodNumber;
        compositionRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        imageArtifactId: z.ZodString;
        groupToolName: z.ZodOptional<z.ZodString>;
        groupInputName: z.ZodOptional<z.ZodString>;
        importMedia: z.ZodOptional<z.ZodBoolean>;
        zoom: z.ZodOptional<z.ZodObject<{
            x: z.ZodNumber;
            y: z.ZodNumber;
        }, z.core.$strict>>;
        position: z.ZodOptional<z.ZodObject<{
            x: z.ZodNumber;
            y: z.ZodNumber;
        }, z.core.$strict>>;
    }, z.core.$strict>>;
}, z.core.$strict>;
export declare const sdkFusionImageReplaceResultSchema: z.ZodObject<{
    actionId: z.ZodLiteral<"cutagent.action.fusion.image.batch">;
    results: z.ZodArray<z.ZodDiscriminatedUnion<[z.ZodObject<{
        index: z.ZodNumber;
        ok: z.ZodLiteral<true>;
        timelineItemId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
        compositionIndex: z.ZodNumber;
        imageArtifactId: z.ZodString;
        durationMs: z.ZodNumber;
        toolName: z.ZodString;
        inputName: z.ZodString;
        verified: z.ZodLiteral<true>;
        revisionBefore: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        revisionAfter: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    }, z.core.$strict>, z.ZodObject<{
        index: z.ZodNumber;
        ok: z.ZodLiteral<false>;
        timelineItemId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
        compositionIndex: z.ZodNumber;
        imageArtifactId: z.ZodString;
        durationMs: z.ZodNumber;
        error: z.ZodObject<{
            code: z.ZodString;
            message: z.ZodString;
        }, z.core.$strict>;
    }, z.core.$strict>], "ok">>;
    successCount: z.ZodNumber;
    failureCount: z.ZodNumber;
    durationMs: z.ZodNumber;
    protectedStatePreserved: z.ZodLiteral<true>;
}, z.core.$strict>;
export declare const sdkFusionNestedTextInputSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
    revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    updates: z.ZodArray<z.ZodObject<{
        timelineItemId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
        compositionIndex: z.ZodNumber;
        header: z.ZodOptional<z.ZodString>;
        body: z.ZodOptional<z.ZodString>;
        headerClipName: z.ZodOptional<z.ZodString>;
        bodyClipName: z.ZodOptional<z.ZodString>;
        headerUppercase: z.ZodOptional<z.ZodBoolean>;
        headerDoubleSpaces: z.ZodOptional<z.ZodBoolean>;
        boldStyle: z.ZodOptional<z.ZodString>;
    }, z.core.$strict>>;
}, z.core.$strict>;
export declare const sdkFusionNestedTextResultSchema: z.ZodObject<{
    actionId: z.ZodLiteral<"cutagent.action.fusion.nested_text.batch">;
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
    revisionBefore: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    revisionAfter: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    changed: z.ZodBoolean;
    successCount: z.ZodNumber;
    failureCount: z.ZodNumber;
    results: z.ZodArray<z.ZodDiscriminatedUnion<[z.ZodObject<{
        index: z.ZodNumber;
        status: z.ZodLiteral<"succeeded">;
        timelineItemId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
        headerUpdated: z.ZodBoolean;
        bodyUpdated: z.ZodBoolean;
        revisionBefore: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        revisionAfter: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    }, z.core.$strict>, z.ZodObject<{
        index: z.ZodNumber;
        status: z.ZodLiteral<"failed">;
        timelineItemId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
        code: z.ZodString;
        message: z.ZodString;
    }, z.core.$strict>], "status">>;
    protectedStatePreserved: z.ZodLiteral<true>;
}, z.core.$strict>;
export type SdkFusionCompositionReference = z.infer<typeof sdkFusionCompositionReferenceSchema>;
export type SdkFusionTextUpdate = z.infer<typeof sdkFusionTextUpdateSchema>;
export type SdkFusionTextActionInput = z.infer<typeof sdkFusionTextActionInputSchema>;
export type SdkFusionTextActionResult = z.infer<typeof sdkFusionTextActionResultSchema>;
export type SdkFusionGraphImpactPreview = z.infer<typeof sdkFusionGraphImpactPreviewSchema>;
export type SdkFusionGraphApplyInput = z.infer<typeof sdkFusionGraphApplyInputSchema>;
export type SdkFusionGraphApplyResult = z.infer<typeof sdkFusionGraphApplyResultSchema>;
export type SdkFusionImageReplaceInput = z.infer<typeof sdkFusionImageReplaceInputSchema>;
export type SdkFusionImageReplaceResult = z.infer<typeof sdkFusionImageReplaceResultSchema>;
export type SdkFusionNestedTextInput = z.infer<typeof sdkFusionNestedTextInputSchema>;
export type SdkFusionNestedTextResult = z.infer<typeof sdkFusionNestedTextResultSchema>;
