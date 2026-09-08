import { z } from "zod";
export declare const sdkFairlightClipGainInputSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
    timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    target: z.ZodObject<{
        kind: z.ZodLiteral<"clip">;
        clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
        trackIndex: z.ZodNumber;
    }, z.core.$strict>;
    kind: z.ZodLiteral<"clip_gain">;
    gainDb: z.ZodNumber;
}, z.core.$strict>;
export declare const sdkFairlightClipPanInputSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
    timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    target: z.ZodObject<{
        kind: z.ZodLiteral<"clip">;
        clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
        trackIndex: z.ZodNumber;
    }, z.core.$strict>;
    kind: z.ZodLiteral<"clip_pan">;
    pan: z.ZodNumber;
}, z.core.$strict>;
export declare const sdkFairlightClipFadeInputSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
    timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    target: z.ZodObject<{
        kind: z.ZodLiteral<"clip">;
        clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
        trackIndex: z.ZodNumber;
    }, z.core.$strict>;
    kind: z.ZodLiteral<"clip_fade">;
    direction: z.ZodEnum<{
        out: "out";
        in: "in";
    }>;
    durationFrames: z.ZodNumber;
}, z.core.$strict>;
export declare const sdkFairlightTrackMixInputSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
    timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    target: z.ZodObject<{
        kind: z.ZodLiteral<"track">;
        trackIndex: z.ZodNumber;
    }, z.core.$strict>;
    kind: z.ZodLiteral<"track_mix">;
    levelDb: z.ZodNumber;
    pan: z.ZodNumber;
}, z.core.$strict>;
export declare const sdkFairlightRouteInputSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
    timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    target: z.ZodObject<{
        kind: z.ZodLiteral<"track">;
        trackIndex: z.ZodNumber;
    }, z.core.$strict>;
    kind: z.ZodLiteral<"routing">;
    destination: z.ZodObject<{
        kind: z.ZodLiteral<"bus">;
        busName: z.ZodString;
        busKind: z.ZodEnum<{
            bus: "bus";
            main: "main";
        }>;
    }, z.core.$strict>;
}, z.core.$strict>;
export declare const sdkFairlightEqInputSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
    timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    target: z.ZodObject<{
        kind: z.ZodLiteral<"clip">;
        clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
        trackIndex: z.ZodNumber;
    }, z.core.$strict>;
    kind: z.ZodLiteral<"eq">;
    enabled: z.ZodBoolean;
    bands: z.ZodArray<z.ZodObject<{
        band: z.ZodNumber;
        enabled: z.ZodBoolean;
        filterType: z.ZodEnum<{
            low_cut: "low_cut";
            low_shelf: "low_shelf";
            bell: "bell";
            high_shelf: "high_shelf";
            high_cut: "high_cut";
        }>;
        frequencyHz: z.ZodNumber;
        gainDb: z.ZodNumber;
        q: z.ZodNumber;
    }, z.core.$strict>>;
}, z.core.$strict>;
export declare const sdkFairlightDynamicsInputSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
    timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    target: z.ZodObject<{
        kind: z.ZodLiteral<"track">;
        trackIndex: z.ZodNumber;
    }, z.core.$strict>;
    kind: z.ZodLiteral<"dynamics">;
    compressor: z.ZodObject<{
        enabled: z.ZodBoolean;
        thresholdDb: z.ZodNumber;
        ratio: z.ZodNullable<z.ZodNumber>;
    }, z.core.$strict>;
    gate: z.ZodObject<{
        enabled: z.ZodBoolean;
        thresholdDb: z.ZodNumber;
        ratio: z.ZodNullable<z.ZodNumber>;
    }, z.core.$strict>;
    limiter: z.ZodObject<{
        enabled: z.ZodBoolean;
        thresholdDb: z.ZodNumber;
        ratio: z.ZodNullable<z.ZodNumber>;
    }, z.core.$strict>;
}, z.core.$strict>;
export declare const sdkFairlightEffectInputSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
    timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    target: z.ZodObject<{
        kind: z.ZodLiteral<"clip">;
        clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
        trackIndex: z.ZodNumber;
    }, z.core.$strict>;
    kind: z.ZodLiteral<"effect">;
    pluginId: z.ZodString;
    presetId: z.ZodOptional<z.ZodString>;
}, z.core.$strict>;
export declare const sdkFairlightSynchronizeInputSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
    timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    kind: z.ZodLiteral<"synchronization">;
    target: z.ZodObject<{
        kind: z.ZodLiteral<"clips">;
        clips: z.ZodArray<z.ZodObject<{
            trackIndex: z.ZodNumber;
            clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
        }, z.core.$strict>>;
    }, z.core.$strict>;
    mode: z.ZodEnum<{
        timecode: "timecode";
        waveform: "waveform";
    }>;
    preserveLinkedMedia: z.ZodLiteral<true>;
}, z.core.$strict>;
export declare const sdkFairlightLoudnessInputSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
    timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    kind: z.ZodLiteral<"loudness">;
    target: z.ZodUnion<readonly [z.ZodObject<{
        kind: z.ZodLiteral<"track">;
        trackIndex: z.ZodNumber;
    }, z.core.$strict>, z.ZodObject<{
        kind: z.ZodLiteral<"bus">;
        busName: z.ZodString;
        busKind: z.ZodEnum<{
            bus: "bus";
            main: "main";
        }>;
    }, z.core.$strict>]>;
    integratedLufs: z.ZodNumber;
    truePeakDbtp: z.ZodNumber;
}, z.core.$strict>;
export declare const sdkFairlightPlanInputSchema: z.ZodObject<{
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
    timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    changes: z.ZodArray<z.ZodDiscriminatedUnion<[z.ZodObject<{
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        target: z.ZodObject<{
            kind: z.ZodLiteral<"clip">;
            clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
            trackIndex: z.ZodNumber;
        }, z.core.$strict>;
        kind: z.ZodLiteral<"clip_gain">;
        gainDb: z.ZodNumber;
    }, z.core.$strict>, z.ZodObject<{
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        target: z.ZodObject<{
            kind: z.ZodLiteral<"clip">;
            clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
            trackIndex: z.ZodNumber;
        }, z.core.$strict>;
        kind: z.ZodLiteral<"clip_pan">;
        pan: z.ZodNumber;
    }, z.core.$strict>, z.ZodObject<{
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        target: z.ZodObject<{
            kind: z.ZodLiteral<"clip">;
            clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
            trackIndex: z.ZodNumber;
        }, z.core.$strict>;
        kind: z.ZodLiteral<"clip_fade">;
        direction: z.ZodEnum<{
            out: "out";
            in: "in";
        }>;
        durationFrames: z.ZodNumber;
    }, z.core.$strict>, z.ZodObject<{
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        target: z.ZodObject<{
            kind: z.ZodLiteral<"track">;
            trackIndex: z.ZodNumber;
        }, z.core.$strict>;
        kind: z.ZodLiteral<"track_mix">;
        levelDb: z.ZodNumber;
        pan: z.ZodNumber;
    }, z.core.$strict>, z.ZodObject<{
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        target: z.ZodObject<{
            kind: z.ZodLiteral<"track">;
            trackIndex: z.ZodNumber;
        }, z.core.$strict>;
        kind: z.ZodLiteral<"routing">;
        destination: z.ZodObject<{
            kind: z.ZodLiteral<"bus">;
            busName: z.ZodString;
            busKind: z.ZodEnum<{
                bus: "bus";
                main: "main";
            }>;
        }, z.core.$strict>;
    }, z.core.$strict>, z.ZodObject<{
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        target: z.ZodObject<{
            kind: z.ZodLiteral<"clip">;
            clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
            trackIndex: z.ZodNumber;
        }, z.core.$strict>;
        kind: z.ZodLiteral<"eq">;
        enabled: z.ZodBoolean;
        bands: z.ZodArray<z.ZodObject<{
            band: z.ZodNumber;
            enabled: z.ZodBoolean;
            filterType: z.ZodEnum<{
                low_cut: "low_cut";
                low_shelf: "low_shelf";
                bell: "bell";
                high_shelf: "high_shelf";
                high_cut: "high_cut";
            }>;
            frequencyHz: z.ZodNumber;
            gainDb: z.ZodNumber;
            q: z.ZodNumber;
        }, z.core.$strict>>;
    }, z.core.$strict>, z.ZodObject<{
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        target: z.ZodObject<{
            kind: z.ZodLiteral<"track">;
            trackIndex: z.ZodNumber;
        }, z.core.$strict>;
        kind: z.ZodLiteral<"dynamics">;
        compressor: z.ZodObject<{
            enabled: z.ZodBoolean;
            thresholdDb: z.ZodNumber;
            ratio: z.ZodNullable<z.ZodNumber>;
        }, z.core.$strict>;
        gate: z.ZodObject<{
            enabled: z.ZodBoolean;
            thresholdDb: z.ZodNumber;
            ratio: z.ZodNullable<z.ZodNumber>;
        }, z.core.$strict>;
        limiter: z.ZodObject<{
            enabled: z.ZodBoolean;
            thresholdDb: z.ZodNumber;
            ratio: z.ZodNullable<z.ZodNumber>;
        }, z.core.$strict>;
    }, z.core.$strict>, z.ZodObject<{
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        target: z.ZodObject<{
            kind: z.ZodLiteral<"clip">;
            clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
            trackIndex: z.ZodNumber;
        }, z.core.$strict>;
        kind: z.ZodLiteral<"effect">;
        pluginId: z.ZodString;
        presetId: z.ZodOptional<z.ZodString>;
    }, z.core.$strict>, z.ZodObject<{
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        kind: z.ZodLiteral<"synchronization">;
        target: z.ZodObject<{
            kind: z.ZodLiteral<"clips">;
            clips: z.ZodArray<z.ZodObject<{
                trackIndex: z.ZodNumber;
                clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
            }, z.core.$strict>>;
        }, z.core.$strict>;
        mode: z.ZodEnum<{
            timecode: "timecode";
            waveform: "waveform";
        }>;
        preserveLinkedMedia: z.ZodLiteral<true>;
    }, z.core.$strict>, z.ZodObject<{
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        kind: z.ZodLiteral<"loudness">;
        target: z.ZodUnion<readonly [z.ZodObject<{
            kind: z.ZodLiteral<"track">;
            trackIndex: z.ZodNumber;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"bus">;
            busName: z.ZodString;
            busKind: z.ZodEnum<{
                bus: "bus";
                main: "main";
            }>;
        }, z.core.$strict>]>;
        integratedLufs: z.ZodNumber;
        truePeakDbtp: z.ZodNumber;
    }, z.core.$strict>], "kind">>;
    preserveLinkedMedia: z.ZodLiteral<true>;
}, z.core.$strict>;
export declare const sdkFairlightSemanticResultSchema: z.ZodObject<{
    actionId: z.ZodLiteral<"cutagent.action.sdk.fairlight.plan.apply">;
    projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
    timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
    outcome: z.ZodEnum<{
        succeeded: "succeeded";
        no_change: "no_change";
        partial: "partial";
    }>;
    timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
    affectedClipIds: z.ZodArray<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>;
    affectedTrackIndexes: z.ZodArray<z.ZodNumber>;
    affectedBuses: z.ZodArray<z.ZodObject<{
        busName: z.ZodString;
        busKind: z.ZodEnum<{
            bus: "bus";
            main: "main";
        }>;
    }, z.core.$strict>>;
    steps: z.ZodArray<z.ZodObject<{
        stepIndex: z.ZodNumber;
        outcome: z.ZodEnum<{
            succeeded: "succeeded";
            no_change: "no_change";
            partial: "partial";
        }>;
        target: z.ZodUnion<readonly [z.ZodObject<{
            kind: z.ZodLiteral<"clip">;
            clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
            trackIndex: z.ZodNumber;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"track">;
            trackIndex: z.ZodNumber;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"bus">;
            busName: z.ZodString;
            busKind: z.ZodEnum<{
                bus: "bus";
                main: "main";
            }>;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"clips">;
            clips: z.ZodArray<z.ZodObject<{
                trackIndex: z.ZodNumber;
                clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
            }, z.core.$strict>>;
        }, z.core.$strict>]>;
        change: z.ZodDiscriminatedUnion<[z.ZodObject<{
            kind: z.ZodLiteral<"clip_gain">;
            beforeDb: z.ZodNullable<z.ZodNumber>;
            afterDb: z.ZodNullable<z.ZodNumber>;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"clip_pan">;
            before: z.ZodNullable<z.ZodNumber>;
            after: z.ZodNullable<z.ZodNumber>;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"clip_fade">;
            direction: z.ZodEnum<{
                out: "out";
                in: "in";
            }>;
            beforeFrames: z.ZodNullable<z.ZodNumber>;
            afterFrames: z.ZodNullable<z.ZodNumber>;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"track_mix">;
            before: z.ZodNullable<z.ZodObject<{
                levelDb: z.ZodNumber;
                pan: z.ZodNumber;
            }, z.core.$strict>>;
            after: z.ZodNullable<z.ZodObject<{
                levelDb: z.ZodNumber;
                pan: z.ZodNumber;
            }, z.core.$strict>>;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"routing">;
            before: z.ZodNullable<z.ZodObject<{
                busName: z.ZodString;
                busKind: z.ZodEnum<{
                    bus: "bus";
                    main: "main";
                }>;
            }, z.core.$strict>>;
            after: z.ZodNullable<z.ZodObject<{
                busName: z.ZodString;
                busKind: z.ZodEnum<{
                    bus: "bus";
                    main: "main";
                }>;
            }, z.core.$strict>>;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"eq">;
            before: z.ZodNullable<z.ZodObject<{
                enabled: z.ZodBoolean;
                bands: z.ZodArray<z.ZodObject<{
                    band: z.ZodNumber;
                    enabled: z.ZodBoolean;
                    filterType: z.ZodEnum<{
                        low_cut: "low_cut";
                        low_shelf: "low_shelf";
                        bell: "bell";
                        high_shelf: "high_shelf";
                        high_cut: "high_cut";
                    }>;
                    frequencyHz: z.ZodNumber;
                    gainDb: z.ZodNumber;
                    q: z.ZodNumber;
                }, z.core.$strict>>;
            }, z.core.$strict>>;
            after: z.ZodNullable<z.ZodObject<{
                enabled: z.ZodBoolean;
                bands: z.ZodArray<z.ZodObject<{
                    band: z.ZodNumber;
                    enabled: z.ZodBoolean;
                    filterType: z.ZodEnum<{
                        low_cut: "low_cut";
                        low_shelf: "low_shelf";
                        bell: "bell";
                        high_shelf: "high_shelf";
                        high_cut: "high_cut";
                    }>;
                    frequencyHz: z.ZodNumber;
                    gainDb: z.ZodNumber;
                    q: z.ZodNumber;
                }, z.core.$strict>>;
            }, z.core.$strict>>;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"dynamics">;
            before: z.ZodNullable<z.ZodObject<{
                compressor: z.ZodObject<{
                    enabled: z.ZodBoolean;
                    thresholdDb: z.ZodNumber;
                    ratio: z.ZodNullable<z.ZodNumber>;
                }, z.core.$strict>;
                gate: z.ZodObject<{
                    enabled: z.ZodBoolean;
                    thresholdDb: z.ZodNumber;
                    ratio: z.ZodNullable<z.ZodNumber>;
                }, z.core.$strict>;
                limiter: z.ZodObject<{
                    enabled: z.ZodBoolean;
                    thresholdDb: z.ZodNumber;
                    ratio: z.ZodNullable<z.ZodNumber>;
                }, z.core.$strict>;
            }, z.core.$strict>>;
            after: z.ZodNullable<z.ZodObject<{
                compressor: z.ZodObject<{
                    enabled: z.ZodBoolean;
                    thresholdDb: z.ZodNumber;
                    ratio: z.ZodNullable<z.ZodNumber>;
                }, z.core.$strict>;
                gate: z.ZodObject<{
                    enabled: z.ZodBoolean;
                    thresholdDb: z.ZodNumber;
                    ratio: z.ZodNullable<z.ZodNumber>;
                }, z.core.$strict>;
                limiter: z.ZodObject<{
                    enabled: z.ZodBoolean;
                    thresholdDb: z.ZodNumber;
                    ratio: z.ZodNullable<z.ZodNumber>;
                }, z.core.$strict>;
            }, z.core.$strict>>;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"effect">;
            pluginId: z.ZodString;
            presetId: z.ZodNullable<z.ZodString>;
            beforePresent: z.ZodNullable<z.ZodBoolean>;
            afterPresent: z.ZodNullable<z.ZodBoolean>;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"synchronization">;
            mode: z.ZodEnum<{
                timecode: "timecode";
                waveform: "waveform";
            }>;
            before: z.ZodArray<z.ZodObject<{
                clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
                recordStartFrame: z.ZodNumber;
            }, z.core.$strict>>;
            after: z.ZodArray<z.ZodObject<{
                clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
                recordStartFrame: z.ZodNumber;
            }, z.core.$strict>>;
        }, z.core.$strict>, z.ZodObject<{
            kind: z.ZodLiteral<"loudness">;
            before: z.ZodNullable<z.ZodObject<{
                integratedLufs: z.ZodNumber;
                truePeakDbtp: z.ZodNumber;
            }, z.core.$strict>>;
            after: z.ZodNullable<z.ZodObject<{
                integratedLufs: z.ZodNumber;
                truePeakDbtp: z.ZodNumber;
            }, z.core.$strict>>;
        }, z.core.$strict>], "kind">;
        structuralEvidenceId: z.ZodString;
        auditionEvidenceId: z.ZodNullable<z.ZodString>;
    }, z.core.$strict>>;
    evidence: z.ZodObject<{
        outcome: z.ZodEnum<{
            failed: "failed";
            passed: "passed";
            partial: "partial";
            manual_review_required: "manual_review_required";
        }>;
        structuralReadback: z.ZodEnum<{
            failed: "failed";
            passed: "passed";
            unavailable: "unavailable";
        }>;
        audition: z.ZodObject<{
            required: z.ZodBoolean;
            status: z.ZodEnum<{
                failed: "failed";
                passed: "passed";
                unavailable: "unavailable";
                not_run: "not_run";
            }>;
        }, z.core.$strict>;
        checks: z.ZodArray<z.ZodObject<{
            evidenceId: z.ZodString;
            stepIndex: z.ZodNullable<z.ZodNumber>;
            kind: z.ZodEnum<{
                structural_readback: "structural_readback";
                audio_audition: "audio_audition";
            }>;
            status: z.ZodEnum<{
                failed: "failed";
                passed: "passed";
                unavailable: "unavailable";
            }>;
            target: z.ZodNullable<z.ZodUnion<readonly [z.ZodObject<{
                kind: z.ZodLiteral<"clip">;
                clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
                trackIndex: z.ZodNumber;
            }, z.core.$strict>, z.ZodObject<{
                kind: z.ZodLiteral<"track">;
                trackIndex: z.ZodNumber;
            }, z.core.$strict>, z.ZodObject<{
                kind: z.ZodLiteral<"bus">;
                busName: z.ZodString;
                busKind: z.ZodEnum<{
                    bus: "bus";
                    main: "main";
                }>;
            }, z.core.$strict>, z.ZodObject<{
                kind: z.ZodLiteral<"clips">;
                clips: z.ZodArray<z.ZodObject<{
                    trackIndex: z.ZodNumber;
                    clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
                }, z.core.$strict>>;
            }, z.core.$strict>]>>;
            summary: z.ZodString;
            stateDigest: z.ZodNullable<z.ZodString>;
            artifact: z.ZodNullable<z.ZodObject<{
                artifactId: z.ZodString;
                sha256: z.ZodString;
                mediaType: z.ZodEnum<{
                    "audio/wav": "audio/wav";
                    "audio/flac": "audio/flac";
                    "audio/mp4": "audio/mp4";
                    "audio/mpeg": "audio/mpeg";
                }>;
            }, z.core.$strict>>;
        }, z.core.$strict>>;
        protectedState: z.ZodObject<{
            evidenceId: z.ZodString;
            status: z.ZodEnum<{
                failed: "failed";
                passed: "passed";
                unavailable: "unavailable";
            }>;
            linkedMedia: z.ZodEnum<{
                unavailable: "unavailable";
                preserved: "preserved";
                changed: "changed";
            }>;
            unexpectedChanges: z.ZodNullable<z.ZodBoolean>;
            stateDigest: z.ZodNullable<z.ZodString>;
            summary: z.ZodString;
        }, z.core.$strict>;
    }, z.core.$strict>;
    recovery: z.ZodDiscriminatedUnion<[z.ZodObject<{
        state: z.ZodLiteral<"none">;
        manualRecoveryRequired: z.ZodLiteral<false>;
        guidance: z.ZodNull;
    }, z.core.$strict>, z.ZodObject<{
        state: z.ZodLiteral<"readback_required">;
        manualRecoveryRequired: z.ZodLiteral<false>;
        guidance: z.ZodString;
    }, z.core.$strict>, z.ZodObject<{
        state: z.ZodLiteral<"manual_recovery_required">;
        manualRecoveryRequired: z.ZodLiteral<true>;
        guidance: z.ZodString;
    }, z.core.$strict>], "state">;
}, z.core.$strict>;
export declare const sdkFairlightBoundTerminalSchema: z.ZodObject<{
    input: z.ZodObject<{
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        changes: z.ZodArray<z.ZodDiscriminatedUnion<[z.ZodObject<{
            projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
            timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            target: z.ZodObject<{
                kind: z.ZodLiteral<"clip">;
                clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
                trackIndex: z.ZodNumber;
            }, z.core.$strict>;
            kind: z.ZodLiteral<"clip_gain">;
            gainDb: z.ZodNumber;
        }, z.core.$strict>, z.ZodObject<{
            projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
            timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            target: z.ZodObject<{
                kind: z.ZodLiteral<"clip">;
                clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
                trackIndex: z.ZodNumber;
            }, z.core.$strict>;
            kind: z.ZodLiteral<"clip_pan">;
            pan: z.ZodNumber;
        }, z.core.$strict>, z.ZodObject<{
            projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
            timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            target: z.ZodObject<{
                kind: z.ZodLiteral<"clip">;
                clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
                trackIndex: z.ZodNumber;
            }, z.core.$strict>;
            kind: z.ZodLiteral<"clip_fade">;
            direction: z.ZodEnum<{
                out: "out";
                in: "in";
            }>;
            durationFrames: z.ZodNumber;
        }, z.core.$strict>, z.ZodObject<{
            projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
            timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            target: z.ZodObject<{
                kind: z.ZodLiteral<"track">;
                trackIndex: z.ZodNumber;
            }, z.core.$strict>;
            kind: z.ZodLiteral<"track_mix">;
            levelDb: z.ZodNumber;
            pan: z.ZodNumber;
        }, z.core.$strict>, z.ZodObject<{
            projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
            timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            target: z.ZodObject<{
                kind: z.ZodLiteral<"track">;
                trackIndex: z.ZodNumber;
            }, z.core.$strict>;
            kind: z.ZodLiteral<"routing">;
            destination: z.ZodObject<{
                kind: z.ZodLiteral<"bus">;
                busName: z.ZodString;
                busKind: z.ZodEnum<{
                    bus: "bus";
                    main: "main";
                }>;
            }, z.core.$strict>;
        }, z.core.$strict>, z.ZodObject<{
            projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
            timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            target: z.ZodObject<{
                kind: z.ZodLiteral<"clip">;
                clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
                trackIndex: z.ZodNumber;
            }, z.core.$strict>;
            kind: z.ZodLiteral<"eq">;
            enabled: z.ZodBoolean;
            bands: z.ZodArray<z.ZodObject<{
                band: z.ZodNumber;
                enabled: z.ZodBoolean;
                filterType: z.ZodEnum<{
                    low_cut: "low_cut";
                    low_shelf: "low_shelf";
                    bell: "bell";
                    high_shelf: "high_shelf";
                    high_cut: "high_cut";
                }>;
                frequencyHz: z.ZodNumber;
                gainDb: z.ZodNumber;
                q: z.ZodNumber;
            }, z.core.$strict>>;
        }, z.core.$strict>, z.ZodObject<{
            projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
            timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            target: z.ZodObject<{
                kind: z.ZodLiteral<"track">;
                trackIndex: z.ZodNumber;
            }, z.core.$strict>;
            kind: z.ZodLiteral<"dynamics">;
            compressor: z.ZodObject<{
                enabled: z.ZodBoolean;
                thresholdDb: z.ZodNumber;
                ratio: z.ZodNullable<z.ZodNumber>;
            }, z.core.$strict>;
            gate: z.ZodObject<{
                enabled: z.ZodBoolean;
                thresholdDb: z.ZodNumber;
                ratio: z.ZodNullable<z.ZodNumber>;
            }, z.core.$strict>;
            limiter: z.ZodObject<{
                enabled: z.ZodBoolean;
                thresholdDb: z.ZodNumber;
                ratio: z.ZodNullable<z.ZodNumber>;
            }, z.core.$strict>;
        }, z.core.$strict>, z.ZodObject<{
            projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
            timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            target: z.ZodObject<{
                kind: z.ZodLiteral<"clip">;
                clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
                trackIndex: z.ZodNumber;
            }, z.core.$strict>;
            kind: z.ZodLiteral<"effect">;
            pluginId: z.ZodString;
            presetId: z.ZodOptional<z.ZodString>;
        }, z.core.$strict>, z.ZodObject<{
            projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
            timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            kind: z.ZodLiteral<"synchronization">;
            target: z.ZodObject<{
                kind: z.ZodLiteral<"clips">;
                clips: z.ZodArray<z.ZodObject<{
                    trackIndex: z.ZodNumber;
                    clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
                }, z.core.$strict>>;
            }, z.core.$strict>;
            mode: z.ZodEnum<{
                timecode: "timecode";
                waveform: "waveform";
            }>;
            preserveLinkedMedia: z.ZodLiteral<true>;
        }, z.core.$strict>, z.ZodObject<{
            projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
            timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
            timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
            kind: z.ZodLiteral<"loudness">;
            target: z.ZodUnion<readonly [z.ZodObject<{
                kind: z.ZodLiteral<"track">;
                trackIndex: z.ZodNumber;
            }, z.core.$strict>, z.ZodObject<{
                kind: z.ZodLiteral<"bus">;
                busName: z.ZodString;
                busKind: z.ZodEnum<{
                    bus: "bus";
                    main: "main";
                }>;
            }, z.core.$strict>]>;
            integratedLufs: z.ZodNumber;
            truePeakDbtp: z.ZodNumber;
        }, z.core.$strict>], "kind">>;
        preserveLinkedMedia: z.ZodLiteral<true>;
    }, z.core.$strict>;
    result: z.ZodObject<{
        actionId: z.ZodLiteral<"cutagent.action.sdk.fairlight.plan.apply">;
        projectId: z.core.$ZodBranded<z.ZodString, "ProjectId", "out">;
        timelineId: z.core.$ZodBranded<z.ZodString, "TimelineId", "out">;
        outcome: z.ZodEnum<{
            succeeded: "succeeded";
            no_change: "no_change";
            partial: "partial";
        }>;
        timelineRevision: z.core.$ZodBranded<z.ZodString, "Revision", "out">;
        affectedClipIds: z.ZodArray<z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">>;
        affectedTrackIndexes: z.ZodArray<z.ZodNumber>;
        affectedBuses: z.ZodArray<z.ZodObject<{
            busName: z.ZodString;
            busKind: z.ZodEnum<{
                bus: "bus";
                main: "main";
            }>;
        }, z.core.$strict>>;
        steps: z.ZodArray<z.ZodObject<{
            stepIndex: z.ZodNumber;
            outcome: z.ZodEnum<{
                succeeded: "succeeded";
                no_change: "no_change";
                partial: "partial";
            }>;
            target: z.ZodUnion<readonly [z.ZodObject<{
                kind: z.ZodLiteral<"clip">;
                clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
                trackIndex: z.ZodNumber;
            }, z.core.$strict>, z.ZodObject<{
                kind: z.ZodLiteral<"track">;
                trackIndex: z.ZodNumber;
            }, z.core.$strict>, z.ZodObject<{
                kind: z.ZodLiteral<"bus">;
                busName: z.ZodString;
                busKind: z.ZodEnum<{
                    bus: "bus";
                    main: "main";
                }>;
            }, z.core.$strict>, z.ZodObject<{
                kind: z.ZodLiteral<"clips">;
                clips: z.ZodArray<z.ZodObject<{
                    trackIndex: z.ZodNumber;
                    clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
                }, z.core.$strict>>;
            }, z.core.$strict>]>;
            change: z.ZodDiscriminatedUnion<[z.ZodObject<{
                kind: z.ZodLiteral<"clip_gain">;
                beforeDb: z.ZodNullable<z.ZodNumber>;
                afterDb: z.ZodNullable<z.ZodNumber>;
            }, z.core.$strict>, z.ZodObject<{
                kind: z.ZodLiteral<"clip_pan">;
                before: z.ZodNullable<z.ZodNumber>;
                after: z.ZodNullable<z.ZodNumber>;
            }, z.core.$strict>, z.ZodObject<{
                kind: z.ZodLiteral<"clip_fade">;
                direction: z.ZodEnum<{
                    out: "out";
                    in: "in";
                }>;
                beforeFrames: z.ZodNullable<z.ZodNumber>;
                afterFrames: z.ZodNullable<z.ZodNumber>;
            }, z.core.$strict>, z.ZodObject<{
                kind: z.ZodLiteral<"track_mix">;
                before: z.ZodNullable<z.ZodObject<{
                    levelDb: z.ZodNumber;
                    pan: z.ZodNumber;
                }, z.core.$strict>>;
                after: z.ZodNullable<z.ZodObject<{
                    levelDb: z.ZodNumber;
                    pan: z.ZodNumber;
                }, z.core.$strict>>;
            }, z.core.$strict>, z.ZodObject<{
                kind: z.ZodLiteral<"routing">;
                before: z.ZodNullable<z.ZodObject<{
                    busName: z.ZodString;
                    busKind: z.ZodEnum<{
                        bus: "bus";
                        main: "main";
                    }>;
                }, z.core.$strict>>;
                after: z.ZodNullable<z.ZodObject<{
                    busName: z.ZodString;
                    busKind: z.ZodEnum<{
                        bus: "bus";
                        main: "main";
                    }>;
                }, z.core.$strict>>;
            }, z.core.$strict>, z.ZodObject<{
                kind: z.ZodLiteral<"eq">;
                before: z.ZodNullable<z.ZodObject<{
                    enabled: z.ZodBoolean;
                    bands: z.ZodArray<z.ZodObject<{
                        band: z.ZodNumber;
                        enabled: z.ZodBoolean;
                        filterType: z.ZodEnum<{
                            low_cut: "low_cut";
                            low_shelf: "low_shelf";
                            bell: "bell";
                            high_shelf: "high_shelf";
                            high_cut: "high_cut";
                        }>;
                        frequencyHz: z.ZodNumber;
                        gainDb: z.ZodNumber;
                        q: z.ZodNumber;
                    }, z.core.$strict>>;
                }, z.core.$strict>>;
                after: z.ZodNullable<z.ZodObject<{
                    enabled: z.ZodBoolean;
                    bands: z.ZodArray<z.ZodObject<{
                        band: z.ZodNumber;
                        enabled: z.ZodBoolean;
                        filterType: z.ZodEnum<{
                            low_cut: "low_cut";
                            low_shelf: "low_shelf";
                            bell: "bell";
                            high_shelf: "high_shelf";
                            high_cut: "high_cut";
                        }>;
                        frequencyHz: z.ZodNumber;
                        gainDb: z.ZodNumber;
                        q: z.ZodNumber;
                    }, z.core.$strict>>;
                }, z.core.$strict>>;
            }, z.core.$strict>, z.ZodObject<{
                kind: z.ZodLiteral<"dynamics">;
                before: z.ZodNullable<z.ZodObject<{
                    compressor: z.ZodObject<{
                        enabled: z.ZodBoolean;
                        thresholdDb: z.ZodNumber;
                        ratio: z.ZodNullable<z.ZodNumber>;
                    }, z.core.$strict>;
                    gate: z.ZodObject<{
                        enabled: z.ZodBoolean;
                        thresholdDb: z.ZodNumber;
                        ratio: z.ZodNullable<z.ZodNumber>;
                    }, z.core.$strict>;
                    limiter: z.ZodObject<{
                        enabled: z.ZodBoolean;
                        thresholdDb: z.ZodNumber;
                        ratio: z.ZodNullable<z.ZodNumber>;
                    }, z.core.$strict>;
                }, z.core.$strict>>;
                after: z.ZodNullable<z.ZodObject<{
                    compressor: z.ZodObject<{
                        enabled: z.ZodBoolean;
                        thresholdDb: z.ZodNumber;
                        ratio: z.ZodNullable<z.ZodNumber>;
                    }, z.core.$strict>;
                    gate: z.ZodObject<{
                        enabled: z.ZodBoolean;
                        thresholdDb: z.ZodNumber;
                        ratio: z.ZodNullable<z.ZodNumber>;
                    }, z.core.$strict>;
                    limiter: z.ZodObject<{
                        enabled: z.ZodBoolean;
                        thresholdDb: z.ZodNumber;
                        ratio: z.ZodNullable<z.ZodNumber>;
                    }, z.core.$strict>;
                }, z.core.$strict>>;
            }, z.core.$strict>, z.ZodObject<{
                kind: z.ZodLiteral<"effect">;
                pluginId: z.ZodString;
                presetId: z.ZodNullable<z.ZodString>;
                beforePresent: z.ZodNullable<z.ZodBoolean>;
                afterPresent: z.ZodNullable<z.ZodBoolean>;
            }, z.core.$strict>, z.ZodObject<{
                kind: z.ZodLiteral<"synchronization">;
                mode: z.ZodEnum<{
                    timecode: "timecode";
                    waveform: "waveform";
                }>;
                before: z.ZodArray<z.ZodObject<{
                    clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
                    recordStartFrame: z.ZodNumber;
                }, z.core.$strict>>;
                after: z.ZodArray<z.ZodObject<{
                    clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
                    recordStartFrame: z.ZodNumber;
                }, z.core.$strict>>;
            }, z.core.$strict>, z.ZodObject<{
                kind: z.ZodLiteral<"loudness">;
                before: z.ZodNullable<z.ZodObject<{
                    integratedLufs: z.ZodNumber;
                    truePeakDbtp: z.ZodNumber;
                }, z.core.$strict>>;
                after: z.ZodNullable<z.ZodObject<{
                    integratedLufs: z.ZodNumber;
                    truePeakDbtp: z.ZodNumber;
                }, z.core.$strict>>;
            }, z.core.$strict>], "kind">;
            structuralEvidenceId: z.ZodString;
            auditionEvidenceId: z.ZodNullable<z.ZodString>;
        }, z.core.$strict>>;
        evidence: z.ZodObject<{
            outcome: z.ZodEnum<{
                failed: "failed";
                passed: "passed";
                partial: "partial";
                manual_review_required: "manual_review_required";
            }>;
            structuralReadback: z.ZodEnum<{
                failed: "failed";
                passed: "passed";
                unavailable: "unavailable";
            }>;
            audition: z.ZodObject<{
                required: z.ZodBoolean;
                status: z.ZodEnum<{
                    failed: "failed";
                    passed: "passed";
                    unavailable: "unavailable";
                    not_run: "not_run";
                }>;
            }, z.core.$strict>;
            checks: z.ZodArray<z.ZodObject<{
                evidenceId: z.ZodString;
                stepIndex: z.ZodNullable<z.ZodNumber>;
                kind: z.ZodEnum<{
                    structural_readback: "structural_readback";
                    audio_audition: "audio_audition";
                }>;
                status: z.ZodEnum<{
                    failed: "failed";
                    passed: "passed";
                    unavailable: "unavailable";
                }>;
                target: z.ZodNullable<z.ZodUnion<readonly [z.ZodObject<{
                    kind: z.ZodLiteral<"clip">;
                    clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
                    trackIndex: z.ZodNumber;
                }, z.core.$strict>, z.ZodObject<{
                    kind: z.ZodLiteral<"track">;
                    trackIndex: z.ZodNumber;
                }, z.core.$strict>, z.ZodObject<{
                    kind: z.ZodLiteral<"bus">;
                    busName: z.ZodString;
                    busKind: z.ZodEnum<{
                        bus: "bus";
                        main: "main";
                    }>;
                }, z.core.$strict>, z.ZodObject<{
                    kind: z.ZodLiteral<"clips">;
                    clips: z.ZodArray<z.ZodObject<{
                        trackIndex: z.ZodNumber;
                        clipId: z.core.$ZodBranded<z.ZodString, "TimelineItemId", "out">;
                    }, z.core.$strict>>;
                }, z.core.$strict>]>>;
                summary: z.ZodString;
                stateDigest: z.ZodNullable<z.ZodString>;
                artifact: z.ZodNullable<z.ZodObject<{
                    artifactId: z.ZodString;
                    sha256: z.ZodString;
                    mediaType: z.ZodEnum<{
                        "audio/wav": "audio/wav";
                        "audio/flac": "audio/flac";
                        "audio/mp4": "audio/mp4";
                        "audio/mpeg": "audio/mpeg";
                    }>;
                }, z.core.$strict>>;
            }, z.core.$strict>>;
            protectedState: z.ZodObject<{
                evidenceId: z.ZodString;
                status: z.ZodEnum<{
                    failed: "failed";
                    passed: "passed";
                    unavailable: "unavailable";
                }>;
                linkedMedia: z.ZodEnum<{
                    unavailable: "unavailable";
                    preserved: "preserved";
                    changed: "changed";
                }>;
                unexpectedChanges: z.ZodNullable<z.ZodBoolean>;
                stateDigest: z.ZodNullable<z.ZodString>;
                summary: z.ZodString;
            }, z.core.$strict>;
        }, z.core.$strict>;
        recovery: z.ZodDiscriminatedUnion<[z.ZodObject<{
            state: z.ZodLiteral<"none">;
            manualRecoveryRequired: z.ZodLiteral<false>;
            guidance: z.ZodNull;
        }, z.core.$strict>, z.ZodObject<{
            state: z.ZodLiteral<"readback_required">;
            manualRecoveryRequired: z.ZodLiteral<false>;
            guidance: z.ZodString;
        }, z.core.$strict>, z.ZodObject<{
            state: z.ZodLiteral<"manual_recovery_required">;
            manualRecoveryRequired: z.ZodLiteral<true>;
            guidance: z.ZodString;
        }, z.core.$strict>], "state">;
    }, z.core.$strict>;
}, z.core.$strict>;
