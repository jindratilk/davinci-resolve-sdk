import { z } from "zod";
/** Exact public identity of one DaVinci Resolve project library. */
export declare const sdkProjectLibraryReferenceSchema: z.ZodObject<{
    name: z.ZodString;
    kind: z.ZodEnum<{
        disk: "disk";
        postgresql: "postgresql";
    }>;
}, z.core.$strict>;
/** Project identity as observed after a context-changing operation. */
export declare const sdkProjectObservationSchema: z.ZodObject<{
    id: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "ProjectId", "out">>;
    name: z.ZodString;
}, z.core.$strict>;
/** Exact durable project identity required for mutation targeting. */
export declare const sdkProjectReferenceSchema: z.ZodObject<{
    name: z.ZodString;
    id: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
}, z.core.$strict>;
/** Timeline identity as observed after a context-changing operation. */
export declare const sdkTimelineObservationSchema: z.ZodObject<{
    id: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "TimelineId", "out">>;
    name: z.ZodString;
}, z.core.$strict>;
/** Truthful project revision availability after a project-level operation. */
export declare const sdkProjectRevisionObservationSchema: z.ZodDiscriminatedUnion<[z.ZodObject<{
    status: z.ZodLiteral<"available">;
    revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
}, z.core.$strict>, z.ZodObject<{
    status: z.ZodLiteral<"unavailable">;
}, z.core.$strict>], "status">;
export declare const sdkProjectCreateInputSchema: z.ZodObject<{
    precondition: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    name: z.ZodString;
    mediaLocation: z.ZodOptional<z.ZodNullable<z.ZodString>>;
}, z.core.$strict>;
export declare const sdkProjectOpenInputSchema: z.ZodObject<{
    precondition: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    project: z.ZodObject<{
        name: z.ZodString;
        id: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    }, z.core.$strict>;
}, z.core.$strict>;
export declare const sdkProjectBackupInputSchema: z.ZodObject<{
    precondition: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    project: z.ZodObject<{
        name: z.ZodString;
        id: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    }, z.core.$strict>;
    destinationArtifactId: z.core.$ZodBranded<z.ZodString, "ArtifactId", "out">;
    withStills: z.ZodBoolean;
}, z.core.$strict>;
export declare const sdkProjectRestoreInputSchema: z.ZodObject<{
    precondition: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    sourceArtifactId: z.core.$ZodBranded<z.ZodString, "ArtifactId", "out">;
    name: z.ZodString;
}, z.core.$strict>;
export declare const sdkProjectLibraryCreateInputSchema: z.ZodObject<{
    precondition: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    libraryName: z.ZodString;
    directoryPath: z.ZodString;
}, z.core.$strict>;
export declare const sdkProjectLibraryBackupInputSchema: z.ZodObject<{
    precondition: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    library: z.ZodObject<{
        name: z.ZodString;
        kind: z.ZodLiteral<"disk">;
    }, z.core.$strict>;
    destinationArtifactId: z.core.$ZodBranded<z.ZodString, "ArtifactId", "out">;
}, z.core.$strict>;
export declare const sdkProjectLibraryRestoreInputSchema: z.ZodObject<{
    precondition: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    sourceArtifactId: z.core.$ZodBranded<z.ZodString, "ArtifactId", "out">;
    libraryName: z.ZodString;
    directoryPath: z.ZodString;
}, z.core.$strict>;
export declare const sdkProjectLibraryOpenInputSchema: z.ZodObject<{
    precondition: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    library: z.ZodObject<{
        name: z.ZodString;
        kind: z.ZodLiteral<"disk">;
    }, z.core.$strict>;
}, z.core.$strict>;
export declare const sdkProjectContextObservationSchema: z.ZodObject<{
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
export declare const sdkProjectContextMutationResultSchema: z.ZodObject<{
    changed: z.ZodBoolean;
    context: z.ZodObject<{
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
}, z.core.$strict>;
export declare const sdkProjectRestoreResultSchema: z.ZodObject<{
    changed: z.ZodBoolean;
    restoredProject: z.ZodObject<{
        name: z.ZodString;
        id: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    }, z.core.$strict>;
    context: z.ZodObject<{
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
}, z.core.$strict>;
export declare const sdkProjectBackupResultSchema: z.ZodObject<{
    project: z.ZodObject<{
        id: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "ProjectId", "out">>;
        name: z.ZodString;
    }, z.core.$strict>;
    artifact: z.ZodObject<{
        kind: z.ZodLiteral<"project">;
        artifactId: z.core.$ZodBranded<z.ZodString, "ArtifactId", "out">;
    }, z.core.$strict>;
    projectRevision: z.ZodDiscriminatedUnion<[z.ZodObject<{
        status: z.ZodLiteral<"available">;
        revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    }, z.core.$strict>, z.ZodObject<{
        status: z.ZodLiteral<"unavailable">;
    }, z.core.$strict>], "status">;
}, z.core.$strict>;
export declare const sdkProjectLibraryMutationResultSchema: z.ZodObject<{
    changed: z.ZodBoolean;
    library: z.ZodObject<{
        name: z.ZodString;
        kind: z.ZodEnum<{
            disk: "disk";
            postgresql: "postgresql";
        }>;
    }, z.core.$strict>;
    context: z.ZodObject<{
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
}, z.core.$strict>;
export declare const sdkProjectLibraryBackupResultSchema: z.ZodObject<{
    library: z.ZodObject<{
        name: z.ZodString;
        kind: z.ZodEnum<{
            disk: "disk";
            postgresql: "postgresql";
        }>;
    }, z.core.$strict>;
    artifact: z.ZodObject<{
        kind: z.ZodLiteral<"library_backup">;
        artifactId: z.core.$ZodBranded<z.ZodString, "ArtifactId", "out">;
    }, z.core.$strict>;
    context: z.ZodObject<{
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
}, z.core.$strict>;
export declare const sdkMediaPoolBinTargetSchema: z.ZodDiscriminatedUnion<[z.ZodObject<{
    kind: z.ZodLiteral<"root">;
}, z.core.$strict>, z.ZodObject<{
    kind: z.ZodLiteral<"folder">;
    id: z.core.$ZodBranded<z.ZodString, "MediaPoolFolderId", "out">;
}, z.core.$strict>], "kind">;
export declare const sdkMediaPoolCreateBinInputSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    precondition: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    parent: z.ZodDiscriminatedUnion<[z.ZodObject<{
        kind: z.ZodLiteral<"root">;
    }, z.core.$strict>, z.ZodObject<{
        kind: z.ZodLiteral<"folder">;
        id: z.core.$ZodBranded<z.ZodString, "MediaPoolFolderId", "out">;
    }, z.core.$strict>], "kind">;
    name: z.ZodString;
}, z.core.$strict>;
export declare const sdkMediaPoolImportInputSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    precondition: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    destination: z.ZodDiscriminatedUnion<[z.ZodObject<{
        kind: z.ZodLiteral<"root">;
    }, z.core.$strict>, z.ZodObject<{
        kind: z.ZodLiteral<"folder">;
        id: z.core.$ZodBranded<z.ZodString, "MediaPoolFolderId", "out">;
    }, z.core.$strict>], "kind">;
    paths: z.ZodArray<z.ZodString>;
}, z.core.$strict>;
export declare const sdkMediaPoolRelinkInputSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    precondition: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    assetId: z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">;
    path: z.ZodString;
}, z.core.$strict>;
export declare const sdkMediaPoolDeleteInputSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    precondition: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    assetIds: z.ZodArray<z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">>;
}, z.core.$strict>;
export declare const sdkMediaPoolSyncAudioInputSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    precondition: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    videoAssetId: z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">;
    audioAssetIds: z.ZodArray<z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">>;
    method: z.ZodEnum<{
        timecode: "timecode";
        waveform: "waveform";
    }>;
    appendTracks: z.ZodBoolean;
}, z.core.$strict>;
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
export declare const sdkMediaPoolSetMetadataInputSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    precondition: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    assetId: z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">;
    entries: z.ZodArray<z.ZodObject<{
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
export declare const sdkMediaPoolCreateBinResultSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    folder: z.ZodObject<{
        id: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "MediaPoolFolderId", "out">>;
        snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolFolderId", "out">;
        name: z.ZodString;
    }, z.core.$strict>;
    revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
}, z.core.$strict>;
export declare const sdkMediaPoolImportResultSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    assets: z.ZodArray<z.ZodObject<{
        id: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">>;
        snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolItemId", "out">;
        name: z.ZodString;
    }, z.core.$strict>>;
    revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
}, z.core.$strict>;
export declare const sdkMediaPoolRelinkResultSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    asset: z.ZodObject<{
        snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolItemId", "out">;
        name: z.ZodString;
        id: z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">;
    }, z.core.$strict>;
    sourceFileName: z.ZodString;
    revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
}, z.core.$strict>;
export declare const sdkMediaPoolDeleteResultSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    items: z.ZodArray<z.ZodObject<{
        assetId: z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">;
        status: z.ZodLiteral<"deleted">;
    }, z.core.$strict>>;
    revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
}, z.core.$strict>;
export declare const sdkMediaPoolSyncAudioResultSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    videoAssetId: z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">;
    audioAssetIds: z.ZodArray<z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">>;
    syncedAsset: z.ZodNullable<z.ZodObject<{
        id: z.ZodNullable<z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">>;
        snapshotId: z.core.$ZodBranded<z.ZodString, "SnapshotMediaPoolItemId", "out">;
        name: z.ZodString;
    }, z.core.$strict>>;
    revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
}, z.core.$strict>;
export declare const sdkMediaPoolSetMetadataResultSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    assetId: z.core.$ZodBranded<z.ZodString, "MediaPoolItemId", "out">;
    entries: z.ZodArray<z.ZodObject<{
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
    revision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
}, z.core.$strict>;
export type SdkProjectLibraryReference = z.infer<typeof sdkProjectLibraryReferenceSchema>;
export type SdkProjectContextMutationResult = z.infer<typeof sdkProjectContextMutationResultSchema>;
export type SdkProjectRestoreResult = z.infer<typeof sdkProjectRestoreResultSchema>;
export type SdkProjectBackupResult = z.infer<typeof sdkProjectBackupResultSchema>;
export type SdkProjectLibraryMutationResult = z.infer<typeof sdkProjectLibraryMutationResultSchema>;
export type SdkProjectLibraryBackupResult = z.infer<typeof sdkProjectLibraryBackupResultSchema>;
export type SdkMediaPoolBinTarget = z.infer<typeof sdkMediaPoolBinTargetSchema>;
export type SdkMediaPoolCreateBinResult = z.infer<typeof sdkMediaPoolCreateBinResultSchema>;
export type SdkMediaPoolDeleteResult = z.infer<typeof sdkMediaPoolDeleteResultSchema>;
export type SdkMediaPoolImportResult = z.infer<typeof sdkMediaPoolImportResultSchema>;
export type SdkMediaPoolRelinkResult = z.infer<typeof sdkMediaPoolRelinkResultSchema>;
export type SdkMediaPoolSyncAudioResult = z.infer<typeof sdkMediaPoolSyncAudioResultSchema>;
export type SdkMediaPoolSetMetadataResult = z.infer<typeof sdkMediaPoolSetMetadataResultSchema>;
