import { z } from "zod";
export declare const sdkTimelineEditIntentSchema: z.ZodDiscriminatedUnion<[z.ZodObject<{
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
export declare const sdkTimelineEditImpactSchema: z.ZodObject<{
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
export type SdkTimelineEditIntent = z.infer<typeof sdkTimelineEditIntentSchema>;
export type SdkTimelineEditImpact = z.infer<typeof sdkTimelineEditImpactSchema>;
