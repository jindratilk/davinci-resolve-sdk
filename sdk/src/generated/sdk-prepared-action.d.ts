import { z } from "zod";
export declare const CUTAGENT_PREPARED_ACTION_PROTOCOL_VERSION: 2;
export declare const CUTAGENT_PREPARED_ACTION_KERNEL_DIGEST: "sha256:e76c8d3035abb0847eafc519cea1a2125a0d2f9d9c52491f1dd696b5a53a4c90";
export declare const CUTAGENT_PREPARED_ACTION_CONTRACT_DIGEST: "sha256:0de84120b23f26fcd90d8ed327ceb52da731bb512263247c2fd5ff88997134d9";
export declare const CUTAGENT_PREPARED_ACTION_CAPABILITY_DIGEST: "sha256:9094f2a43290856f5be0fa80feab68a21b6d2aaa30aace394601b682e83ff89a";
export declare const CUTAGENT_PREPARED_ACTION_RECEIPT_TTL_MS: 30000;
export declare const CUTAGENT_PREPARED_ACTION_MAX_OUTSTANDING_RECEIPTS: 1024;
export declare const CUTAGENT_PREPARED_ACTION_MAX_RESULT_BYTES: 16777216;
export declare const sdkPreparedActionIdentitiesSchema: z.ZodObject<{
    projectLibraryId: z.ZodString;
    projectId: z.ZodNullable<z.ZodString>;
    timelineId: z.ZodNullable<z.ZodString>;
    targetIds: z.ZodArray<z.ZodString>;
}, z.core.$strict>;
export declare const sdkPreparedActionRevisionsSchema: z.ZodObject<{
    projectLibrary: z.ZodString;
    project: z.ZodNullable<z.ZodString>;
    timeline: z.ZodNullable<z.ZodString>;
    targets: z.ZodRecord<z.ZodString, z.ZodString>;
}, z.core.$strict>;
export declare const sdkPrepareActionRequestSchema: z.ZodObject<{
    protocolVersion: z.ZodLiteral<2>;
    actionId: z.ZodString;
    actionContractVersion: z.ZodNumber;
    input: z.ZodType<unknown, unknown, z.core.$ZodTypeInternals<unknown, unknown>>;
    contractDigest: z.ZodString;
    capabilityDigest: z.ZodString;
    identities: z.ZodObject<{
        projectLibraryId: z.ZodString;
        projectId: z.ZodNullable<z.ZodString>;
        timelineId: z.ZodNullable<z.ZodString>;
        targetIds: z.ZodArray<z.ZodString>;
    }, z.core.$strict>;
    revisions: z.ZodObject<{
        projectLibrary: z.ZodString;
        project: z.ZodNullable<z.ZodString>;
        timeline: z.ZodNullable<z.ZodString>;
        targets: z.ZodRecord<z.ZodString, z.ZodString>;
    }, z.core.$strict>;
    idempotencyKey: z.ZodString;
    requestId: z.ZodString;
    operationId: z.ZodString;
    executionId: z.ZodString;
}, z.core.$strict>;
/** Private carrier-owned base copied verbatim into every prepared mutation impact. */
export declare const sdkPreparedActionMutationBaseSchema: z.ZodObject<{
    contractVersion: z.ZodLiteral<1>;
    carrier: z.ZodLiteral<"sdk">;
    minimumBinding: z.ZodEnum<{
        project: "project";
        "account/project-library": "account/project-library";
        "project+timeline": "project+timeline";
    }>;
    registryDigest: z.ZodString;
    canonicalRequestDigest: z.ZodString;
    referencedPayloadDigests: z.ZodArray<z.ZodString>;
    requestId: z.ZodString;
    operationId: z.ZodString;
    executionId: z.ZodString;
    projectLibraryId: z.ZodString;
    projectId: z.ZodOptional<z.ZodString>;
    timelineId: z.ZodOptional<z.ZodString>;
    projectRevision: z.ZodOptional<z.ZodString>;
    timelineRevision: z.ZodOptional<z.ZodString>;
}, z.core.$strict>;
export declare const sdkPreparedReadImpactSchema: z.ZodObject<{
    contractVersion: z.ZodLiteral<1>;
    status: z.ZodLiteral<"read">;
    complete: z.ZodLiteral<true>;
    targetDigests: z.ZodArray<z.ZodString>;
    resultMaximumBytes: z.ZodNumber;
}, z.core.$strict>;
export declare const sdkPreparedActionImpactSchema: z.ZodUnion<readonly [z.ZodObject<{
    contractVersion: z.ZodLiteral<1>;
    status: z.ZodLiteral<"read">;
    complete: z.ZodLiteral<true>;
    targetDigests: z.ZodArray<z.ZodString>;
    resultMaximumBytes: z.ZodNumber;
}, z.core.$strict>, z.ZodObject<{
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
}, z.core.$strict>]>;
export declare const sdkPreparedActionAuthorizationBindingSchema: z.ZodObject<{
    accountDigest: z.ZodString;
    subscriptionDigest: z.ZodString;
    sessionDigest: z.ZodString;
    actionDigest: z.ZodString;
    inputDigest: z.ZodString;
    contractDigest: z.ZodString;
    capabilityDigest: z.ZodString;
    protocolDigest: z.ZodString;
    projectDigest: z.ZodString;
    timelineDigest: z.ZodString;
    targetsDigest: z.ZodString;
    preStateDigest: z.ZodString;
    impactDigest: z.ZodString;
    receiptDigest: z.ZodString;
    executionDigest: z.ZodString;
    appArtifactDigest: z.ZodString;
    runtimeArtifactDigest: z.ZodString;
    cliArtifactDigest: z.ZodString;
    packagedAncestryDigest: z.ZodString;
    expiresAt: z.ZodNumber;
}, z.core.$strict>;
export declare const sdkPrepareActionResultSchema: z.ZodObject<{
    protocolVersion: z.ZodLiteral<2>;
    receipt: z.ZodString;
    receiptDigest: z.ZodString;
    expiresAt: z.ZodString;
    operationClass: z.ZodEnum<{
        read: "read";
        mutation: "mutation";
    }>;
    impact: z.ZodUnion<readonly [z.ZodObject<{
        contractVersion: z.ZodLiteral<1>;
        status: z.ZodLiteral<"read">;
        complete: z.ZodLiteral<true>;
        targetDigests: z.ZodArray<z.ZodString>;
        resultMaximumBytes: z.ZodNumber;
    }, z.core.$strict>, z.ZodObject<{
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
    }, z.core.$strict>]>;
    authorizationBinding: z.ZodObject<{
        accountDigest: z.ZodString;
        subscriptionDigest: z.ZodString;
        sessionDigest: z.ZodString;
        actionDigest: z.ZodString;
        inputDigest: z.ZodString;
        contractDigest: z.ZodString;
        capabilityDigest: z.ZodString;
        protocolDigest: z.ZodString;
        projectDigest: z.ZodString;
        timelineDigest: z.ZodString;
        targetsDigest: z.ZodString;
        preStateDigest: z.ZodString;
        impactDigest: z.ZodString;
        receiptDigest: z.ZodString;
        executionDigest: z.ZodString;
        appArtifactDigest: z.ZodString;
        runtimeArtifactDigest: z.ZodString;
        cliArtifactDigest: z.ZodString;
        packagedAncestryDigest: z.ZodString;
        expiresAt: z.ZodNumber;
    }, z.core.$strict>;
}, z.core.$strict>;
export declare const sdkAdmitPreparedActionRequestSchema: z.ZodObject<{
    receipt: z.ZodString;
    authorizationToken: z.ZodString;
}, z.core.$strict>;
export declare const sdkExecutePreparedActionRequestSchema: z.ZodObject<{
    receipt: z.ZodString;
}, z.core.$strict>;
export declare const sdkPreparedActionTerminalSchema: z.ZodObject<{
    status: z.ZodEnum<{
        failed: "failed";
        succeeded: "succeeded";
        recovery_failed: "recovery_failed";
        recovered: "recovered";
    }>;
    operationId: z.ZodString;
    executionId: z.ZodString;
    actionId: z.ZodString;
    possibleMutation: z.ZodEnum<{
        unknown: "unknown";
        none: "none";
        possible: "possible";
        confirmed: "confirmed";
        partial: "partial";
    }>;
    usage: z.ZodEnum<{
        unknown: "unknown";
        not_reserved: "not_reserved";
        consumed: "consumed";
        released: "released";
    }>;
    verification: z.ZodObject<{
        outcome: z.ZodEnum<{
            failed: "failed";
            passed: "passed";
            partial: "partial";
            manual_review_required: "manual_review_required";
            not_performed: "not_performed";
        }>;
        evidence: z.ZodArray<z.ZodObject<{
            modality: z.ZodEnum<{
                file: "file";
                readback: "readback";
                structural: "structural";
                rendered: "rendered";
                visual: "visual";
                auditioned: "auditioned";
            }>;
            digest: z.ZodString;
            summary: z.ZodString;
        }, z.core.$strict>>;
        protectedStatePreserved: z.ZodNullable<z.ZodBoolean>;
    }, z.core.$strict>;
    recovery: z.ZodObject<{
        outcome: z.ZodEnum<{
            failed: "failed";
            not_needed: "not_needed";
            succeeded: "succeeded";
            manual_required: "manual_required";
        }>;
        attempted: z.ZodBoolean;
        manualActionRequired: z.ZodBoolean;
        cause: z.ZodOptional<z.ZodObject<{
            code: z.ZodString;
        }, z.core.$strict>>;
    }, z.core.$strict>;
    retrySafe: z.ZodLiteral<false>;
    result: z.ZodOptional<z.ZodObject<{
        actionId: z.ZodType<"cutagent.action.fairlight.channel_map.clip" | "cutagent.action.fairlight.sound_library.source_list" | "cutagent.action.fairlight.add" | "cutagent.action.fairlight.ai.dialogue_leveler" | "cutagent.action.fairlight.ai.music_remixer" | "cutagent.action.fairlight.ai.voice_isolation" | "cutagent.action.fairlight.automation.write" | "cutagent.action.fairlight.bounce.mix_to_track" | "cutagent.action.fairlight.bounce.track" | "cutagent.action.fairlight.bus.assign" | "cutagent.action.fairlight.bus.level" | "cutagent.action.fairlight.channel_map.set" | "cutagent.action.fairlight.clip.delete" | "cutagent.action.fairlight.clip.link" | "cutagent.action.fairlight.clip.move" | "cutagent.action.fairlight.clip.nudge" | "cutagent.action.fairlight.clip.slip" | "cutagent.action.fairlight.clip.split" | "cutagent.action.fairlight.clip.trim" | "cutagent.action.fairlight.clip.unlink" | "cutagent.action.fairlight.delete" | "cutagent.action.fairlight.dynamics.disable" | "cutagent.action.fairlight.dynamics.enable" | "cutagent.action.fairlight.dynamics.set" | "cutagent.action.fairlight.effect.add" | "cutagent.action.fairlight.effect.remove" | "cutagent.action.fairlight.effect.set_param" | "cutagent.action.fairlight.elastic.enable" | "cutagent.action.fairlight.elastic.keyframe" | "cutagent.action.fairlight.ensure_stereo_tracks" | "cutagent.action.fairlight.ensure_tracks" | "cutagent.action.fairlight.eq.set" | "cutagent.action.fairlight.export.audio" | "cutagent.action.fairlight.insert" | "cutagent.action.fairlight.item_source.patch" | "cutagent.action.fairlight.lock" | "cutagent.action.fairlight.mixer.fader" | "cutagent.action.fairlight.mixer.pan" | "cutagent.action.fairlight.mute" | "cutagent.action.fairlight.preset.apply" | "cutagent.action.fairlight.rename" | "cutagent.action.fairlight.solo" | "cutagent.action.fairlight.solo_restore" | "cutagent.action.fairlight.sound_library.delete" | "cutagent.action.fairlight.sound_library.index_file" | "cutagent.action.fairlight.sound_library.index_folder" | "cutagent.action.fairlight.sound_library.insert" | "cutagent.action.fairlight.sound_library.source_rebuild" | "cutagent.action.fairlight.sound_library.source_remove" | "cutagent.action.fairlight.track.duplicate" | "cutagent.action.fairlight.track_color" | "cutagent.action.fairlight.track_format.set" | "cutagent.action.fairlight.track_order.move" | "cutagent.action.fairlight.transition.add" | "cutagent.action.fairlight.unlock" | "cutagent.action.fairlight.unmute" | "cutagent.action.fairlight.voice_isolation.set" | "cutagent.action.sdk.fairlight.plan.apply" | "cutagent.action.fusion.apply" | "cutagent.action.fusion.image.batch" | "cutagent.action.fusion.text.batch" | "cutagent.action.fusion.nested_text.batch" | "cutagent.action.audio.voice_list" | "cutagent.action.clip.cache_state" | "cutagent.action.clip.current" | "cutagent.action.clip.fusion.by_name" | "cutagent.action.clip.fusion.tool_get" | "cutagent.action.clip.fusion.tools" | "cutagent.action.clip.info" | "cutagent.action.clip.list" | "cutagent.action.clip.marker.get_custom" | "cutagent.action.clip.marker.list" | "cutagent.action.clip.source_audio_mapping" | "cutagent.action.clip.stereo_values" | "cutagent.action.dctl.validate_source" | "cutagent.action.fairlight.adr.info" | "cutagent.action.fairlight.ai.read" | "cutagent.action.fairlight.api_notes" | "cutagent.action.fairlight.automation.list" | "cutagent.action.fairlight.bus.list" | "cutagent.action.fairlight.channel_map.media" | "cutagent.action.fairlight.clip.info" | "cutagent.action.fairlight.clip.linked.list" | "cutagent.action.fairlight.clip.source_range" | "cutagent.action.fairlight.clip.track_info" | "cutagent.action.fairlight.dynamics.read" | "cutagent.action.fairlight.effect.catalog" | "cutagent.action.fairlight.effect.list" | "cutagent.action.fairlight.effect.params" | "cutagent.action.fairlight.effect.plugin_catalog" | "cutagent.action.fairlight.effect.slot_scan" | "cutagent.action.fairlight.elastic.info" | "cutagent.action.fairlight.eq.read" | "cutagent.action.fairlight.external_process.list" | "cutagent.action.fairlight.group.list" | "cutagent.action.fairlight.index.clips" | "cutagent.action.fairlight.index.markers" | "cutagent.action.fairlight.index.tracks" | "cutagent.action.fairlight.info" | "cutagent.action.fairlight.io.info" | "cutagent.action.fairlight.items" | "cutagent.action.fairlight.loudness.info" | "cutagent.action.fairlight.mixer.meter_settings" | "cutagent.action.fairlight.mixer.read" | "cutagent.action.fairlight.monitor.info" | "cutagent.action.fairlight.preset.list" | "cutagent.action.fairlight.record.info" | "cutagent.action.fairlight.send.list" | "cutagent.action.fairlight.sound_library.list" | "cutagent.action.fairlight.sound_library.search" | "cutagent.action.fairlight.track.height" | "cutagent.action.fairlight.tracks" | "cutagent.action.fairlight.vca.list" | "cutagent.action.fairlight.voice_isolation.get" | "cutagent.action.fairlight.waveform.info" | "cutagent.action.fusion.preview" | "cutagent.action.fusion.template.list" | "cutagent.action.media.audio_mapping" | "cutagent.action.media.folders.list" | "cutagent.action.media.folders.tree" | "cutagent.action.media.info" | "cutagent.action.media.list" | "cutagent.action.media.mark.get" | "cutagent.action.media.marker.list" | "cutagent.action.media.matte.list" | "cutagent.action.media.search" | "cutagent.action.media.selected.list" | "cutagent.action.media.third_party_metadata.get" | "cutagent.action.media.timeline_matte.list" | "cutagent.action.page.current" | "cutagent.action.project.folders.list" | "cutagent.action.project.info" | "cutagent.action.project.library.current" | "cutagent.action.project.library.list" | "cutagent.action.project.preset.list" | "cutagent.action.project.settings" | "cutagent.action.render.codecs" | "cutagent.action.render.formats" | "cutagent.action.render.job_status" | "cutagent.action.render.jobs" | "cutagent.action.render.mode.get" | "cutagent.action.render.presets" | "cutagent.action.render.quick_export_presets" | "cutagent.action.render.resolutions" | "cutagent.action.render.settings" | "cutagent.action.render.status" | "cutagent.action.system.keyboard_preset.current" | "cutagent.action.system.keyboard_preset.list" | "cutagent.action.system.keyframe_mode.get" | "cutagent.action.text.inspect" | "cutagent.action.text.list_presets" | "cutagent.action.version.inspect" | "cutagent.action.version.list" | "cutagent.action.version.status" | "cutagent.action.audio.beat_detect" | "cutagent.action.audio.duck" | "cutagent.action.audio.info" | "cutagent.action.audio.probe_subframe" | "cutagent.action.audio.reverb" | "cutagent.action.audio.voice_generate" | "cutagent.action.audio.voice_place" | "cutagent.action.audio.waveform_offset" | "cutagent.action.auto_edit.multicam" | "cutagent.action.auto_edit.podcast_edit" | "cutagent.action.auto_edit.podcast_multicam" | "cutagent.action.auto_edit.run" | "cutagent.action.auto_edit.silence_cut" | "cutagent.action.batch.run" | "cutagent.action.batch.validate" | "cutagent.action.bulk.clip_color_set" | "cutagent.action.bulk.disable" | "cutagent.action.bulk.enable" | "cutagent.action.bulk.lut_set" | "cutagent.action.bulk.property_set" | "cutagent.action.bulk.select" | "cutagent.action.burnin.load" | "cutagent.action.burnin.preset.export" | "cutagent.action.burnin.preset.import" | "cutagent.action.clip.audio_eq" | "cutagent.action.clip.audio_gain" | "cutagent.action.clip.audio_normalize" | "cutagent.action.clip.audio_pan" | "cutagent.action.clip.audio_pitch" | "cutagent.action.clip.burnin.load" | "cutagent.action.clip.cache" | "cutagent.action.clip.cache_set" | "cutagent.action.clip.color" | "cutagent.action.clip.composite" | "cutagent.action.clip.disable" | "cutagent.action.clip.dynamic_zoom" | "cutagent.action.clip.enable" | "cutagent.action.clip.fade_in" | "cutagent.action.clip.flag" | "cutagent.action.clip.freeze" | "cutagent.action.clip.fusion.add" | "cutagent.action.clip.fusion.delete" | "cutagent.action.clip.fusion.export" | "cutagent.action.clip.fusion.import" | "cutagent.action.clip.fusion.list" | "cutagent.action.clip.fusion.load" | "cutagent.action.clip.fusion.tool_set" | "cutagent.action.clip.keyframe.add" | "cutagent.action.clip.keyframe.delete" | "cutagent.action.clip.keyframe.get" | "cutagent.action.clip.keyframe.set_interpolation" | "cutagent.action.clip.link" | "cutagent.action.clip.linked.list" | "cutagent.action.clip.magic_mask" | "cutagent.action.clip.marker.add" | "cutagent.action.clip.marker.custom_data" | "cutagent.action.clip.marker.delete" | "cutagent.action.clip.marker.delete_custom" | "cutagent.action.clip.offset" | "cutagent.action.clip.properties" | "cutagent.action.clip.rename" | "cutagent.action.clip.reset_node_colors" | "cutagent.action.clip.reverse" | "cutagent.action.clip.smart_reframe" | "cutagent.action.clip.source_range" | "cutagent.action.clip.speed" | "cutagent.action.clip.speed_ramp" | "cutagent.action.clip.stabilize" | "cutagent.action.clip.take.add" | "cutagent.action.clip.take.delete" | "cutagent.action.clip.take.finalize" | "cutagent.action.clip.take.list" | "cutagent.action.clip.take.select" | "cutagent.action.clip.track_info" | "cutagent.action.clip.transform" | "cutagent.action.clip.unlink" | "cutagent.action.clip.update_sidecar" | "cutagent.action.clip.voice_isolation" | "cutagent.action.color.arri_cdl_lut" | "cutagent.action.color.auto_color" | "cutagent.action.color.cdl" | "cutagent.action.color.comp.doctor" | "cutagent.action.color.comp.export" | "cutagent.action.color.comp.flatten" | "cutagent.action.color.comp.repair" | "cutagent.action.color.curves" | "cutagent.action.color.export_lut" | "cutagent.action.color.fx.apply" | "cutagent.action.color.fx.list" | "cutagent.action.color.gallery.album.create" | "cutagent.action.color.gallery.album.current" | "cutagent.action.color.gallery.album.list" | "cutagent.action.color.gallery.album.rename" | "cutagent.action.color.gallery.album.switch" | "cutagent.action.color.gallery.still.apply" | "cutagent.action.color.gallery.still.delete" | "cutagent.action.color.gallery.still.export" | "cutagent.action.color.gallery.still.grab" | "cutagent.action.color.gallery.still.import" | "cutagent.action.color.gallery.still.label" | "cutagent.action.color.gallery.still.list" | "cutagent.action.color.grade_apply" | "cutagent.action.color.grade_copy" | "cutagent.action.color.graph.inspect" | "cutagent.action.color.graph.normalize" | "cutagent.action.color.graph.validate" | "cutagent.action.color.group.add" | "cutagent.action.color.group.assign" | "cutagent.action.color.group.clips" | "cutagent.action.color.group.delete" | "cutagent.action.color.group.graph" | "cutagent.action.color.group.list" | "cutagent.action.color.group.remove" | "cutagent.action.color.group.rename" | "cutagent.action.color.huesat" | "cutagent.action.color.inspect" | "cutagent.action.color.lut" | "cutagent.action.color.lut_refresh" | "cutagent.action.color.mask.inspect" | "cutagent.action.color.node.cache" | "cutagent.action.color.node.disable" | "cutagent.action.color.node.enable" | "cutagent.action.color.node.graph" | "cutagent.action.color.node.label_get" | "cutagent.action.color.node.label_set" | "cutagent.action.color.node.list" | "cutagent.action.color.node.lut_get" | "cutagent.action.color.node.lut_set" | "cutagent.action.color.node.reset" | "cutagent.action.color.node.tools" | "cutagent.action.color.nodes" | "cutagent.action.color.page.alpha_output_connect" | "cutagent.action.color.page.auto_color_ai" | "cutagent.action.color.page.bleach_bypass_intensity_set" | "cutagent.action.color.page.bleach_bypass_set" | "cutagent.action.color.page.cat_set" | "cutagent.action.color.page.color_slice_set" | "cutagent.action.color.page.cst_set" | "cutagent.action.color.page.curve_points_set" | "cutagent.action.color.page.curve_set" | "cutagent.action.color.page.curve_spline_set" | "cutagent.action.color.page.dctl_apply" | "cutagent.action.color.page.dctl_remove" | "cutagent.action.color.page.false_color_read" | "cutagent.action.color.page.hdr_detail_set" | "cutagent.action.color.page.hdr_global_set" | "cutagent.action.color.page.hdr_zone_set" | "cutagent.action.color.page.hsv_node_set" | "cutagent.action.color.page.hue_curve_set" | "cutagent.action.color.page.hue_curve_spline_set" | "cutagent.action.color.page.key_output_set" | "cutagent.action.color.page.layer_mixer_set" | "cutagent.action.color.page.lut_library_import" | "cutagent.action.color.page.magic_mask" | "cutagent.action.color.page.magic_mask_draw_stroke" | "cutagent.action.color.page.magic_mask_refine" | "cutagent.action.color.page.node_add" | "cutagent.action.color.page.node_add_topology" | "cutagent.action.color.page.node_cleanup" | "cutagent.action.color.page.node_cleanup_general" | "cutagent.action.color.page.ofx_glow_set" | "cutagent.action.color.page.param_delete" | "cutagent.action.color.page.power_window_circle" | "cutagent.action.color.page.power_window_circle_detail" | "cutagent.action.color.page.power_window_curve" | "cutagent.action.color.page.power_window_gradient" | "cutagent.action.color.page.power_window_gradient_transform" | "cutagent.action.color.page.power_window_linear" | "cutagent.action.color.page.power_window_overlay_transform" | "cutagent.action.color.page.power_window_polygon" | "cutagent.action.color.page.power_window_rectangle" | "cutagent.action.color.page.power_window_set" | "cutagent.action.color.page.power_window_track" | "cutagent.action.color.page.primary_extended_set" | "cutagent.action.color.page.primary_set" | "cutagent.action.color.page.qualifier_hsl_set" | "cutagent.action.color.page.qualifier_matte_refine" | "cutagent.action.color.page.qualifier_matte_set" | "cutagent.action.color.page.qualifier_panel_probe" | "cutagent.action.color.page.qualifier_sample" | "cutagent.action.color.page.read" | "cutagent.action.color.page.resolvefx_add" | "cutagent.action.color.page.resolvefx_list" | "cutagent.action.color.page.resolvefx_param_discover" | "cutagent.action.color.page.resolvefx_param_list" | "cutagent.action.color.page.resolvefx_param_set" | "cutagent.action.color.page.resolvefx_remove" | "cutagent.action.color.page.rgb_mixer_set" | "cutagent.action.color.page.sat_curve_set" | "cutagent.action.color.page.sat_curve_spline_set" | "cutagent.action.color.page.scope_read" | "cutagent.action.color.page.scope_set" | "cutagent.action.color.page.sharpen_set" | "cutagent.action.color.page.shot_match_analyze" | "cutagent.action.color.page.shot_match_apply" | "cutagent.action.color.page.sky_isolation" | "cutagent.action.color.page.snapshot" | "cutagent.action.color.page.softening_set" | "cutagent.action.color.page.split_tone_set" | "cutagent.action.color.page.still_match" | "cutagent.action.color.page.viewer_before_after" | "cutagent.action.color.page.warper_set" | "cutagent.action.color.page.wheel_set" | "cutagent.action.color.page.white_balance_picker" | "cutagent.action.color.power_grade.album.create" | "cutagent.action.color.power_grade.apply" | "cutagent.action.color.power_grade.list" | "cutagent.action.color.power_grade.template_apply" | "cutagent.action.color.primary.get" | "cutagent.action.color.primary.set" | "cutagent.action.color.qualifier.attach" | "cutagent.action.color.qualifier.chroma" | "cutagent.action.color.qualifier.detach" | "cutagent.action.color.qualifier.list" | "cutagent.action.color.reset_fusion" | "cutagent.action.color.secondary.create" | "cutagent.action.color.secondary.isolate_green_screen" | "cutagent.action.color.secondary.subject_isolation" | "cutagent.action.color.secondary.tracked_window" | "cutagent.action.color.source_grade.apply_cdl" | "cutagent.action.color.source_grade.plan" | "cutagent.action.color.source_grade.prepare_remote" | "cutagent.action.color.still.grab_all" | "cutagent.action.color.thumbnail" | "cutagent.action.color.tracker.add" | "cutagent.action.color.tracker.attach_qualifier" | "cutagent.action.color.tracker.attach_window" | "cutagent.action.color.tracker.list" | "cutagent.action.color.tracker.set_target" | "cutagent.action.color.tracker.track_forward" | "cutagent.action.color.tracker.track_reverse" | "cutagent.action.color.version.activate" | "cutagent.action.color.version.add" | "cutagent.action.color.version.delete" | "cutagent.action.color.version.duplicate" | "cutagent.action.color.version.list" | "cutagent.action.color.version.load" | "cutagent.action.color.version.rollback" | "cutagent.action.color.wheels.set" | "cutagent.action.color.window.attach" | "cutagent.action.color.window.detach" | "cutagent.action.color.window.ellipse" | "cutagent.action.color.window.list" | "cutagent.action.color.window.polygon" | "cutagent.action.color.window.rectangle" | "cutagent.action.color.window.reorder" | "cutagent.action.dctl.apply" | "cutagent.action.edit.auto_subtitle" | "cutagent.action.edit.blade" | "cutagent.action.edit.camera_pip" | "cutagent.action.edit.delete_through_edit" | "cutagent.action.edit.from_edl" | "cutagent.action.edit.fx.add" | "cutagent.action.edit.insert" | "cutagent.action.edit.overwrite" | "cutagent.action.edit.remove" | "cutagent.action.edit.remove_range" | "cutagent.action.edit.ripple_delete" | "cutagent.action.edit.ripple_delete_selected" | "cutagent.action.edit.scene_detect" | "cutagent.action.edit.slide_selected" | "cutagent.action.edit.slip_selected" | "cutagent.action.edit.social_crop" | "cutagent.action.edit.split" | "cutagent.action.edit.transition.add" | "cutagent.action.edit.transition.batch" | "cutagent.action.edit.trim" | "cutagent.action.fairlight.adr.cue_list" | "cutagent.action.fairlight.adr.record" | "cutagent.action.fairlight.audio_gain.batch" | "cutagent.action.fairlight.audio_pan.batch" | "cutagent.action.fairlight.crossfade.batch" | "cutagent.action.fairlight.external_process.run" | "cutagent.action.fairlight.fade_curve" | "cutagent.action.fairlight.fade_in.batch" | "cutagent.action.fairlight.fade_out.batch" | "cutagent.action.fairlight.group.assign" | "cutagent.action.fairlight.io.patch" | "cutagent.action.fairlight.loudness.analyze" | "cutagent.action.fairlight.loudness.normalize" | "cutagent.action.fairlight.mixer.meter" | "cutagent.action.fairlight.monitor.level" | "cutagent.action.fairlight.monitor.mute" | "cutagent.action.fairlight.record.arm" | "cutagent.action.fairlight.record.start" | "cutagent.action.fairlight.record.stop" | "cutagent.action.fairlight.send.set" | "cutagent.action.fairlight.sound_library.audition" | "cutagent.action.fairlight.track.folder" | "cutagent.action.fairlight.track.hide" | "cutagent.action.fairlight.track.input_monitor" | "cutagent.action.fairlight.track.show" | "cutagent.action.fairlight.vca.assign" | "cutagent.action.fairlight.waveform.repair_click" | "cutagent.action.fusion.comp.current" | "cutagent.action.fusion.comp.delete" | "cutagent.action.fusion.comp.play" | "cutagent.action.fusion.comp.range" | "cutagent.action.fusion.comp.rename" | "cutagent.action.fusion.comp.render" | "cutagent.action.fusion.comp.stop" | "cutagent.action.fusion.effect.blur" | "cutagent.action.fusion.effect.color_correct" | "cutagent.action.fusion.effect.glow" | "cutagent.action.fusion.effect.sharpen" | "cutagent.action.fusion.effect.transform" | "cutagent.action.fusion.generate" | "cutagent.action.fusion.image.set" | "cutagent.action.fusion.insert_setting" | "cutagent.action.fusion.insert_settings.batch" | "cutagent.action.fusion.keyer.chroma" | "cutagent.action.fusion.keyframe.add" | "cutagent.action.fusion.keyframe.clear" | "cutagent.action.fusion.keyframe.delete" | "cutagent.action.fusion.keyframe.list" | "cutagent.action.fusion.keyframe.set" | "cutagent.action.fusion.macro.apply" | "cutagent.action.fusion.mask.ellipse" | "cutagent.action.fusion.mask.polygon" | "cutagent.action.fusion.mask.rectangle" | "cutagent.action.fusion.nested_text.update" | "cutagent.action.fusion.node.add" | "cutagent.action.fusion.node.connect" | "cutagent.action.fusion.node.delete" | "cutagent.action.fusion.node.disconnect" | "cutagent.action.fusion.setting.center_to_polypath" | "cutagent.action.fusion.setting.inspect" | "cutagent.action.fusion.setting.polypath_to_center" | "cutagent.action.fusion.setting.summary" | "cutagent.action.fusion.setting.validate" | "cutagent.action.fusion.template.apply" | "cutagent.action.fusion.template.assets.add" | "cutagent.action.fusion.template.assets.list" | "cutagent.action.fusion.template.dir" | "cutagent.action.fusion.template.icon.set" | "cutagent.action.fusion.template.install" | "cutagent.action.fusion.template.package_drfx" | "cutagent.action.fusion.template.scaffold" | "cutagent.action.fusion.template.show" | "cutagent.action.fusion.template.uninstall" | "cutagent.action.fusion.template.unpack_drfx" | "cutagent.action.fusion.template.validate" | "cutagent.action.fusion.text.set" | "cutagent.action.fusion.tool.active" | "cutagent.action.fusion.tool.add" | "cutagent.action.fusion.tool.attrs" | "cutagent.action.fusion.tool.connect" | "cutagent.action.fusion.tool.copy" | "cutagent.action.fusion.tool.delete" | "cutagent.action.fusion.tool.disconnect" | "cutagent.action.fusion.tool.get" | "cutagent.action.fusion.tool.inputs" | "cutagent.action.fusion.tool.list" | "cutagent.action.fusion.tool.outputs" | "cutagent.action.fusion.tool.paste" | "cutagent.action.fusion.tool.registry" | "cutagent.action.fusion.tool.set" | "cutagent.action.fusion.tracker.add" | "cutagent.action.lut.convert" | "cutagent.action.lut.generate.identity" | "cutagent.action.lut.inspect" | "cutagent.action.lut.install" | "cutagent.action.lut.list" | "cutagent.action.lut.remove" | "cutagent.action.lut.validate" | "cutagent.action.lut_refresh" | "cutagent.action.media.append" | "cutagent.action.media.append.batch" | "cutagent.action.media.clear_transcription" | "cutagent.action.media.color.clear" | "cutagent.action.media.color.set" | "cutagent.action.media.create_timeline" | "cutagent.action.media.delete" | "cutagent.action.media.duplicate" | "cutagent.action.media.extract_template" | "cutagent.action.media.flag.add" | "cutagent.action.media.flag.clear" | "cutagent.action.media.folder.export_drb" | "cutagent.action.media.folder.import_drb" | "cutagent.action.media.folders.create" | "cutagent.action.media.folders.delete" | "cutagent.action.media.folders.move" | "cutagent.action.media.folders.open" | "cutagent.action.media.folders.root" | "cutagent.action.media.growing_file.monitor" | "cutagent.action.media.import" | "cutagent.action.media.mark.clear" | "cutagent.action.media.mark.set" | "cutagent.action.media.marker.add" | "cutagent.action.media.marker.delete" | "cutagent.action.media.matte.delete" | "cutagent.action.media.metadata" | "cutagent.action.media.metadata.export" | "cutagent.action.media.move" | "cutagent.action.media.property_set" | "cutagent.action.media.proxy" | "cutagent.action.media.proxy.link_fullres" | "cutagent.action.media.relink" | "cutagent.action.media.rename" | "cutagent.action.media.replace" | "cutagent.action.media.replace_preserve_subclip" | "cutagent.action.media.selected.set" | "cutagent.action.media.stereo_create" | "cutagent.action.media.sync_audio" | "cutagent.action.media.third_party_metadata.bulk_set" | "cutagent.action.media.third_party_metadata.set" | "cutagent.action.media.transcode" | "cutagent.action.media.transcribe" | "cutagent.action.media.transcription" | "cutagent.action.media.unlink" | "cutagent.action.multicam.angle.remove" | "cutagent.action.multicam.angle.rename" | "cutagent.action.multicam.angle.set_enabled" | "cutagent.action.multicam.audio_activity.calibrate" | "cutagent.action.multicam.convert" | "cutagent.action.multicam.create" | "cutagent.action.multicam.flatten" | "cutagent.action.multicam.inspect" | "cutagent.action.multicam.match_frame" | "cutagent.action.multicam.recover_timing" | "cutagent.action.multicam.reorder_angles" | "cutagent.action.multicam.replace.audio" | "cutagent.action.multicam.replace.video" | "cutagent.action.multicam.seed_timeline" | "cutagent.action.multicam.set_start_timecode" | "cutagent.action.multicam.settings" | "cutagent.action.multicam.smart_switch" | "cutagent.action.multicam.source.grade_cdl" | "cutagent.action.multicam.source.move" | "cutagent.action.multicam.source.property_set" | "cutagent.action.multicam.source.raw_braw_set" | "cutagent.action.multicam.source.remove" | "cutagent.action.multicam.strip_embedded_audio" | "cutagent.action.multicam.switch" | "cutagent.action.multicam.timeline_create" | "cutagent.action.page.switch" | "cutagent.action.project.archive" | "cutagent.action.project.cleanup_scratch" | "cutagent.action.project.close" | "cutagent.action.project.cloud.create" | "cutagent.action.project.cloud.import" | "cutagent.action.project.cloud.open" | "cutagent.action.project.cloud.restore" | "cutagent.action.project.create" | "cutagent.action.project.delete" | "cutagent.action.project.export" | "cutagent.action.project.folders.create" | "cutagent.action.project.folders.delete" | "cutagent.action.project.folders.open" | "cutagent.action.project.folders.root" | "cutagent.action.project.folders.up" | "cutagent.action.project.import" | "cutagent.action.project.library.backup" | "cutagent.action.project.library.create" | "cutagent.action.project.library.restore" | "cutagent.action.project.library.switch" | "cutagent.action.project.list" | "cutagent.action.project.open" | "cutagent.action.project.preset.export" | "cutagent.action.project.preset.load" | "cutagent.action.project.preset.save" | "cutagent.action.project.rename" | "cutagent.action.project.restore" | "cutagent.action.project.save" | "cutagent.action.project.settings_set" | "cutagent.action.render.add" | "cutagent.action.render.alpha" | "cutagent.action.render.archive_settings" | "cutagent.action.render.audio" | "cutagent.action.render.burnin.export" | "cutagent.action.render.burnin.import" | "cutagent.action.render.burnin.load" | "cutagent.action.render.cancel" | "cutagent.action.render.custom_range" | "cutagent.action.render.delete" | "cutagent.action.render.encoding" | "cutagent.action.render.export" | "cutagent.action.render.export_file" | "cutagent.action.render.export_preset" | "cutagent.action.render.import_preset" | "cutagent.action.render.mode.set" | "cutagent.action.render.preset_delete" | "cutagent.action.render.preset_load" | "cutagent.action.render.preset_save" | "cutagent.action.render.preset_update" | "cutagent.action.render.quick_export" | "cutagent.action.render.settings.replace" | "cutagent.action.render.settings.update" | "cutagent.action.render.settings_set" | "cutagent.action.render.start" | "cutagent.action.render.stop" | "cutagent.action.render.subtitles" | "cutagent.action.render.transcript_audio" | "cutagent.action.render.wait" | "cutagent.action.storage.files" | "cutagent.action.storage.import" | "cutagent.action.storage.import_sequence" | "cutagent.action.storage.import_subclip" | "cutagent.action.storage.matte.add" | "cutagent.action.storage.matte.timeline_add" | "cutagent.action.storage.reveal" | "cutagent.action.storage.volumes" | "cutagent.action.system.keyframe_mode.set" | "cutagent.action.text.insert" | "cutagent.action.text.insert_captions" | "cutagent.action.text.insert_preset" | "cutagent.action.text.insert_template" | "cutagent.action.text.insert_template_batch" | "cutagent.action.text.update" | "cutagent.action.timeline.auto_caption" | "cutagent.action.timeline.clip_color.batch" | "cutagent.action.timeline.clip_markers.list" | "cutagent.action.timeline.compound_create" | "cutagent.action.timeline.create" | "cutagent.action.timeline.current_item" | "cutagent.action.timeline.delete" | "cutagent.action.timeline.dolby.analyze" | "cutagent.action.timeline.duplicate" | "cutagent.action.timeline.duration" | "cutagent.action.timeline.export" | "cutagent.action.timeline.fairlight_preset.apply" | "cutagent.action.timeline.frame_export" | "cutagent.action.timeline.frame_export.batch" | "cutagent.action.timeline.fusion_clip.create" | "cutagent.action.timeline.fusion_composition.insert" | "cutagent.action.timeline.grab_still" | "cutagent.action.timeline.import" | "cutagent.action.timeline.import_into" | "cutagent.action.timeline.info" | "cutagent.action.timeline.insert_generator" | "cutagent.action.timeline.insert_title" | "cutagent.action.timeline.inspect_export" | "cutagent.action.timeline.item_at" | "cutagent.action.timeline.items.delete" | "cutagent.action.timeline.items.move" | "cutagent.action.timeline.items.set_duration" | "cutagent.action.timeline.layer.ensure_media" | "cutagent.action.timeline.layout.free_stack" | "cutagent.action.timeline.list" | "cutagent.action.timeline.mark.clear" | "cutagent.action.timeline.mark.get" | "cutagent.action.timeline.mark.set" | "cutagent.action.timeline.marker.add" | "cutagent.action.timeline.marker.batch" | "cutagent.action.timeline.marker.delete" | "cutagent.action.timeline.marker.list" | "cutagent.action.timeline.marker.update" | "cutagent.action.timeline.media_pool_item" | "cutagent.action.timeline.node_graph.inspect" | "cutagent.action.timeline.output_blanking.get" | "cutagent.action.timeline.output_blanking.set" | "cutagent.action.timeline.overlay_stack.insert" | "cutagent.action.timeline.playhead.get" | "cutagent.action.timeline.playhead.set" | "cutagent.action.timeline.preview_export" | "cutagent.action.timeline.rename" | "cutagent.action.timeline.set_start_tc" | "cutagent.action.timeline.settings" | "cutagent.action.timeline.settings_set" | "cutagent.action.timeline.start_tc" | "cutagent.action.timeline.stereo_convert" | "cutagent.action.timeline.still.grab_all" | "cutagent.action.timeline.subtitle.export" | "cutagent.action.timeline.subtitle.insert" | "cutagent.action.timeline.subtitle.list" | "cutagent.action.timeline.summarize" | "cutagent.action.timeline.switch" | "cutagent.action.timeline.sync_clips" | "cutagent.action.timeline.thumbnail" | "cutagent.action.timeline.track.add" | "cutagent.action.timeline.track.delete" | "cutagent.action.timeline.track.disable" | "cutagent.action.timeline.track.enable" | "cutagent.action.timeline.track.items" | "cutagent.action.timeline.track.list" | "cutagent.action.timeline.track.lock" | "cutagent.action.timeline.track.rename" | "cutagent.action.timeline.track.subtype" | "cutagent.action.timeline.track.unlock" | "cutagent.action.timeline.voice_isolation.get" | "cutagent.action.timeline.voice_isolation.set" | "cutagent.action.transcript.create" | "cutagent.action.version.create" | "cutagent.action.version.prune" | "cutagent.action.version.restore", unknown, z.core.$ZodTypeInternals<"cutagent.action.fairlight.channel_map.clip" | "cutagent.action.fairlight.sound_library.source_list" | "cutagent.action.fairlight.add" | "cutagent.action.fairlight.ai.dialogue_leveler" | "cutagent.action.fairlight.ai.music_remixer" | "cutagent.action.fairlight.ai.voice_isolation" | "cutagent.action.fairlight.automation.write" | "cutagent.action.fairlight.bounce.mix_to_track" | "cutagent.action.fairlight.bounce.track" | "cutagent.action.fairlight.bus.assign" | "cutagent.action.fairlight.bus.level" | "cutagent.action.fairlight.channel_map.set" | "cutagent.action.fairlight.clip.delete" | "cutagent.action.fairlight.clip.link" | "cutagent.action.fairlight.clip.move" | "cutagent.action.fairlight.clip.nudge" | "cutagent.action.fairlight.clip.slip" | "cutagent.action.fairlight.clip.split" | "cutagent.action.fairlight.clip.trim" | "cutagent.action.fairlight.clip.unlink" | "cutagent.action.fairlight.delete" | "cutagent.action.fairlight.dynamics.disable" | "cutagent.action.fairlight.dynamics.enable" | "cutagent.action.fairlight.dynamics.set" | "cutagent.action.fairlight.effect.add" | "cutagent.action.fairlight.effect.remove" | "cutagent.action.fairlight.effect.set_param" | "cutagent.action.fairlight.elastic.enable" | "cutagent.action.fairlight.elastic.keyframe" | "cutagent.action.fairlight.ensure_stereo_tracks" | "cutagent.action.fairlight.ensure_tracks" | "cutagent.action.fairlight.eq.set" | "cutagent.action.fairlight.export.audio" | "cutagent.action.fairlight.insert" | "cutagent.action.fairlight.item_source.patch" | "cutagent.action.fairlight.lock" | "cutagent.action.fairlight.mixer.fader" | "cutagent.action.fairlight.mixer.pan" | "cutagent.action.fairlight.mute" | "cutagent.action.fairlight.preset.apply" | "cutagent.action.fairlight.rename" | "cutagent.action.fairlight.solo" | "cutagent.action.fairlight.solo_restore" | "cutagent.action.fairlight.sound_library.delete" | "cutagent.action.fairlight.sound_library.index_file" | "cutagent.action.fairlight.sound_library.index_folder" | "cutagent.action.fairlight.sound_library.insert" | "cutagent.action.fairlight.sound_library.source_rebuild" | "cutagent.action.fairlight.sound_library.source_remove" | "cutagent.action.fairlight.track.duplicate" | "cutagent.action.fairlight.track_color" | "cutagent.action.fairlight.track_format.set" | "cutagent.action.fairlight.track_order.move" | "cutagent.action.fairlight.transition.add" | "cutagent.action.fairlight.unlock" | "cutagent.action.fairlight.unmute" | "cutagent.action.fairlight.voice_isolation.set" | "cutagent.action.sdk.fairlight.plan.apply" | "cutagent.action.fusion.apply" | "cutagent.action.fusion.image.batch" | "cutagent.action.fusion.text.batch" | "cutagent.action.fusion.nested_text.batch" | "cutagent.action.audio.voice_list" | "cutagent.action.clip.cache_state" | "cutagent.action.clip.current" | "cutagent.action.clip.fusion.by_name" | "cutagent.action.clip.fusion.tool_get" | "cutagent.action.clip.fusion.tools" | "cutagent.action.clip.info" | "cutagent.action.clip.list" | "cutagent.action.clip.marker.get_custom" | "cutagent.action.clip.marker.list" | "cutagent.action.clip.source_audio_mapping" | "cutagent.action.clip.stereo_values" | "cutagent.action.dctl.validate_source" | "cutagent.action.fairlight.adr.info" | "cutagent.action.fairlight.ai.read" | "cutagent.action.fairlight.api_notes" | "cutagent.action.fairlight.automation.list" | "cutagent.action.fairlight.bus.list" | "cutagent.action.fairlight.channel_map.media" | "cutagent.action.fairlight.clip.info" | "cutagent.action.fairlight.clip.linked.list" | "cutagent.action.fairlight.clip.source_range" | "cutagent.action.fairlight.clip.track_info" | "cutagent.action.fairlight.dynamics.read" | "cutagent.action.fairlight.effect.catalog" | "cutagent.action.fairlight.effect.list" | "cutagent.action.fairlight.effect.params" | "cutagent.action.fairlight.effect.plugin_catalog" | "cutagent.action.fairlight.effect.slot_scan" | "cutagent.action.fairlight.elastic.info" | "cutagent.action.fairlight.eq.read" | "cutagent.action.fairlight.external_process.list" | "cutagent.action.fairlight.group.list" | "cutagent.action.fairlight.index.clips" | "cutagent.action.fairlight.index.markers" | "cutagent.action.fairlight.index.tracks" | "cutagent.action.fairlight.info" | "cutagent.action.fairlight.io.info" | "cutagent.action.fairlight.items" | "cutagent.action.fairlight.loudness.info" | "cutagent.action.fairlight.mixer.meter_settings" | "cutagent.action.fairlight.mixer.read" | "cutagent.action.fairlight.monitor.info" | "cutagent.action.fairlight.preset.list" | "cutagent.action.fairlight.record.info" | "cutagent.action.fairlight.send.list" | "cutagent.action.fairlight.sound_library.list" | "cutagent.action.fairlight.sound_library.search" | "cutagent.action.fairlight.track.height" | "cutagent.action.fairlight.tracks" | "cutagent.action.fairlight.vca.list" | "cutagent.action.fairlight.voice_isolation.get" | "cutagent.action.fairlight.waveform.info" | "cutagent.action.fusion.preview" | "cutagent.action.fusion.template.list" | "cutagent.action.media.audio_mapping" | "cutagent.action.media.folders.list" | "cutagent.action.media.folders.tree" | "cutagent.action.media.info" | "cutagent.action.media.list" | "cutagent.action.media.mark.get" | "cutagent.action.media.marker.list" | "cutagent.action.media.matte.list" | "cutagent.action.media.search" | "cutagent.action.media.selected.list" | "cutagent.action.media.third_party_metadata.get" | "cutagent.action.media.timeline_matte.list" | "cutagent.action.page.current" | "cutagent.action.project.folders.list" | "cutagent.action.project.info" | "cutagent.action.project.library.current" | "cutagent.action.project.library.list" | "cutagent.action.project.preset.list" | "cutagent.action.project.settings" | "cutagent.action.render.codecs" | "cutagent.action.render.formats" | "cutagent.action.render.job_status" | "cutagent.action.render.jobs" | "cutagent.action.render.mode.get" | "cutagent.action.render.presets" | "cutagent.action.render.quick_export_presets" | "cutagent.action.render.resolutions" | "cutagent.action.render.settings" | "cutagent.action.render.status" | "cutagent.action.system.keyboard_preset.current" | "cutagent.action.system.keyboard_preset.list" | "cutagent.action.system.keyframe_mode.get" | "cutagent.action.text.inspect" | "cutagent.action.text.list_presets" | "cutagent.action.version.inspect" | "cutagent.action.version.list" | "cutagent.action.version.status" | "cutagent.action.audio.beat_detect" | "cutagent.action.audio.duck" | "cutagent.action.audio.info" | "cutagent.action.audio.probe_subframe" | "cutagent.action.audio.reverb" | "cutagent.action.audio.voice_generate" | "cutagent.action.audio.voice_place" | "cutagent.action.audio.waveform_offset" | "cutagent.action.auto_edit.multicam" | "cutagent.action.auto_edit.podcast_edit" | "cutagent.action.auto_edit.podcast_multicam" | "cutagent.action.auto_edit.run" | "cutagent.action.auto_edit.silence_cut" | "cutagent.action.batch.run" | "cutagent.action.batch.validate" | "cutagent.action.bulk.clip_color_set" | "cutagent.action.bulk.disable" | "cutagent.action.bulk.enable" | "cutagent.action.bulk.lut_set" | "cutagent.action.bulk.property_set" | "cutagent.action.bulk.select" | "cutagent.action.burnin.load" | "cutagent.action.burnin.preset.export" | "cutagent.action.burnin.preset.import" | "cutagent.action.clip.audio_eq" | "cutagent.action.clip.audio_gain" | "cutagent.action.clip.audio_normalize" | "cutagent.action.clip.audio_pan" | "cutagent.action.clip.audio_pitch" | "cutagent.action.clip.burnin.load" | "cutagent.action.clip.cache" | "cutagent.action.clip.cache_set" | "cutagent.action.clip.color" | "cutagent.action.clip.composite" | "cutagent.action.clip.disable" | "cutagent.action.clip.dynamic_zoom" | "cutagent.action.clip.enable" | "cutagent.action.clip.fade_in" | "cutagent.action.clip.flag" | "cutagent.action.clip.freeze" | "cutagent.action.clip.fusion.add" | "cutagent.action.clip.fusion.delete" | "cutagent.action.clip.fusion.export" | "cutagent.action.clip.fusion.import" | "cutagent.action.clip.fusion.list" | "cutagent.action.clip.fusion.load" | "cutagent.action.clip.fusion.tool_set" | "cutagent.action.clip.keyframe.add" | "cutagent.action.clip.keyframe.delete" | "cutagent.action.clip.keyframe.get" | "cutagent.action.clip.keyframe.set_interpolation" | "cutagent.action.clip.link" | "cutagent.action.clip.linked.list" | "cutagent.action.clip.magic_mask" | "cutagent.action.clip.marker.add" | "cutagent.action.clip.marker.custom_data" | "cutagent.action.clip.marker.delete" | "cutagent.action.clip.marker.delete_custom" | "cutagent.action.clip.offset" | "cutagent.action.clip.properties" | "cutagent.action.clip.rename" | "cutagent.action.clip.reset_node_colors" | "cutagent.action.clip.reverse" | "cutagent.action.clip.smart_reframe" | "cutagent.action.clip.source_range" | "cutagent.action.clip.speed" | "cutagent.action.clip.speed_ramp" | "cutagent.action.clip.stabilize" | "cutagent.action.clip.take.add" | "cutagent.action.clip.take.delete" | "cutagent.action.clip.take.finalize" | "cutagent.action.clip.take.list" | "cutagent.action.clip.take.select" | "cutagent.action.clip.track_info" | "cutagent.action.clip.transform" | "cutagent.action.clip.unlink" | "cutagent.action.clip.update_sidecar" | "cutagent.action.clip.voice_isolation" | "cutagent.action.color.arri_cdl_lut" | "cutagent.action.color.auto_color" | "cutagent.action.color.cdl" | "cutagent.action.color.comp.doctor" | "cutagent.action.color.comp.export" | "cutagent.action.color.comp.flatten" | "cutagent.action.color.comp.repair" | "cutagent.action.color.curves" | "cutagent.action.color.export_lut" | "cutagent.action.color.fx.apply" | "cutagent.action.color.fx.list" | "cutagent.action.color.gallery.album.create" | "cutagent.action.color.gallery.album.current" | "cutagent.action.color.gallery.album.list" | "cutagent.action.color.gallery.album.rename" | "cutagent.action.color.gallery.album.switch" | "cutagent.action.color.gallery.still.apply" | "cutagent.action.color.gallery.still.delete" | "cutagent.action.color.gallery.still.export" | "cutagent.action.color.gallery.still.grab" | "cutagent.action.color.gallery.still.import" | "cutagent.action.color.gallery.still.label" | "cutagent.action.color.gallery.still.list" | "cutagent.action.color.grade_apply" | "cutagent.action.color.grade_copy" | "cutagent.action.color.graph.inspect" | "cutagent.action.color.graph.normalize" | "cutagent.action.color.graph.validate" | "cutagent.action.color.group.add" | "cutagent.action.color.group.assign" | "cutagent.action.color.group.clips" | "cutagent.action.color.group.delete" | "cutagent.action.color.group.graph" | "cutagent.action.color.group.list" | "cutagent.action.color.group.remove" | "cutagent.action.color.group.rename" | "cutagent.action.color.huesat" | "cutagent.action.color.inspect" | "cutagent.action.color.lut" | "cutagent.action.color.lut_refresh" | "cutagent.action.color.mask.inspect" | "cutagent.action.color.node.cache" | "cutagent.action.color.node.disable" | "cutagent.action.color.node.enable" | "cutagent.action.color.node.graph" | "cutagent.action.color.node.label_get" | "cutagent.action.color.node.label_set" | "cutagent.action.color.node.list" | "cutagent.action.color.node.lut_get" | "cutagent.action.color.node.lut_set" | "cutagent.action.color.node.reset" | "cutagent.action.color.node.tools" | "cutagent.action.color.nodes" | "cutagent.action.color.page.alpha_output_connect" | "cutagent.action.color.page.auto_color_ai" | "cutagent.action.color.page.bleach_bypass_intensity_set" | "cutagent.action.color.page.bleach_bypass_set" | "cutagent.action.color.page.cat_set" | "cutagent.action.color.page.color_slice_set" | "cutagent.action.color.page.cst_set" | "cutagent.action.color.page.curve_points_set" | "cutagent.action.color.page.curve_set" | "cutagent.action.color.page.curve_spline_set" | "cutagent.action.color.page.dctl_apply" | "cutagent.action.color.page.dctl_remove" | "cutagent.action.color.page.false_color_read" | "cutagent.action.color.page.hdr_detail_set" | "cutagent.action.color.page.hdr_global_set" | "cutagent.action.color.page.hdr_zone_set" | "cutagent.action.color.page.hsv_node_set" | "cutagent.action.color.page.hue_curve_set" | "cutagent.action.color.page.hue_curve_spline_set" | "cutagent.action.color.page.key_output_set" | "cutagent.action.color.page.layer_mixer_set" | "cutagent.action.color.page.lut_library_import" | "cutagent.action.color.page.magic_mask" | "cutagent.action.color.page.magic_mask_draw_stroke" | "cutagent.action.color.page.magic_mask_refine" | "cutagent.action.color.page.node_add" | "cutagent.action.color.page.node_add_topology" | "cutagent.action.color.page.node_cleanup" | "cutagent.action.color.page.node_cleanup_general" | "cutagent.action.color.page.ofx_glow_set" | "cutagent.action.color.page.param_delete" | "cutagent.action.color.page.power_window_circle" | "cutagent.action.color.page.power_window_circle_detail" | "cutagent.action.color.page.power_window_curve" | "cutagent.action.color.page.power_window_gradient" | "cutagent.action.color.page.power_window_gradient_transform" | "cutagent.action.color.page.power_window_linear" | "cutagent.action.color.page.power_window_overlay_transform" | "cutagent.action.color.page.power_window_polygon" | "cutagent.action.color.page.power_window_rectangle" | "cutagent.action.color.page.power_window_set" | "cutagent.action.color.page.power_window_track" | "cutagent.action.color.page.primary_extended_set" | "cutagent.action.color.page.primary_set" | "cutagent.action.color.page.qualifier_hsl_set" | "cutagent.action.color.page.qualifier_matte_refine" | "cutagent.action.color.page.qualifier_matte_set" | "cutagent.action.color.page.qualifier_panel_probe" | "cutagent.action.color.page.qualifier_sample" | "cutagent.action.color.page.read" | "cutagent.action.color.page.resolvefx_add" | "cutagent.action.color.page.resolvefx_list" | "cutagent.action.color.page.resolvefx_param_discover" | "cutagent.action.color.page.resolvefx_param_list" | "cutagent.action.color.page.resolvefx_param_set" | "cutagent.action.color.page.resolvefx_remove" | "cutagent.action.color.page.rgb_mixer_set" | "cutagent.action.color.page.sat_curve_set" | "cutagent.action.color.page.sat_curve_spline_set" | "cutagent.action.color.page.scope_read" | "cutagent.action.color.page.scope_set" | "cutagent.action.color.page.sharpen_set" | "cutagent.action.color.page.shot_match_analyze" | "cutagent.action.color.page.shot_match_apply" | "cutagent.action.color.page.sky_isolation" | "cutagent.action.color.page.snapshot" | "cutagent.action.color.page.softening_set" | "cutagent.action.color.page.split_tone_set" | "cutagent.action.color.page.still_match" | "cutagent.action.color.page.viewer_before_after" | "cutagent.action.color.page.warper_set" | "cutagent.action.color.page.wheel_set" | "cutagent.action.color.page.white_balance_picker" | "cutagent.action.color.power_grade.album.create" | "cutagent.action.color.power_grade.apply" | "cutagent.action.color.power_grade.list" | "cutagent.action.color.power_grade.template_apply" | "cutagent.action.color.primary.get" | "cutagent.action.color.primary.set" | "cutagent.action.color.qualifier.attach" | "cutagent.action.color.qualifier.chroma" | "cutagent.action.color.qualifier.detach" | "cutagent.action.color.qualifier.list" | "cutagent.action.color.reset_fusion" | "cutagent.action.color.secondary.create" | "cutagent.action.color.secondary.isolate_green_screen" | "cutagent.action.color.secondary.subject_isolation" | "cutagent.action.color.secondary.tracked_window" | "cutagent.action.color.source_grade.apply_cdl" | "cutagent.action.color.source_grade.plan" | "cutagent.action.color.source_grade.prepare_remote" | "cutagent.action.color.still.grab_all" | "cutagent.action.color.thumbnail" | "cutagent.action.color.tracker.add" | "cutagent.action.color.tracker.attach_qualifier" | "cutagent.action.color.tracker.attach_window" | "cutagent.action.color.tracker.list" | "cutagent.action.color.tracker.set_target" | "cutagent.action.color.tracker.track_forward" | "cutagent.action.color.tracker.track_reverse" | "cutagent.action.color.version.activate" | "cutagent.action.color.version.add" | "cutagent.action.color.version.delete" | "cutagent.action.color.version.duplicate" | "cutagent.action.color.version.list" | "cutagent.action.color.version.load" | "cutagent.action.color.version.rollback" | "cutagent.action.color.wheels.set" | "cutagent.action.color.window.attach" | "cutagent.action.color.window.detach" | "cutagent.action.color.window.ellipse" | "cutagent.action.color.window.list" | "cutagent.action.color.window.polygon" | "cutagent.action.color.window.rectangle" | "cutagent.action.color.window.reorder" | "cutagent.action.dctl.apply" | "cutagent.action.edit.auto_subtitle" | "cutagent.action.edit.blade" | "cutagent.action.edit.camera_pip" | "cutagent.action.edit.delete_through_edit" | "cutagent.action.edit.from_edl" | "cutagent.action.edit.fx.add" | "cutagent.action.edit.insert" | "cutagent.action.edit.overwrite" | "cutagent.action.edit.remove" | "cutagent.action.edit.remove_range" | "cutagent.action.edit.ripple_delete" | "cutagent.action.edit.ripple_delete_selected" | "cutagent.action.edit.scene_detect" | "cutagent.action.edit.slide_selected" | "cutagent.action.edit.slip_selected" | "cutagent.action.edit.social_crop" | "cutagent.action.edit.split" | "cutagent.action.edit.transition.add" | "cutagent.action.edit.transition.batch" | "cutagent.action.edit.trim" | "cutagent.action.fairlight.adr.cue_list" | "cutagent.action.fairlight.adr.record" | "cutagent.action.fairlight.audio_gain.batch" | "cutagent.action.fairlight.audio_pan.batch" | "cutagent.action.fairlight.crossfade.batch" | "cutagent.action.fairlight.external_process.run" | "cutagent.action.fairlight.fade_curve" | "cutagent.action.fairlight.fade_in.batch" | "cutagent.action.fairlight.fade_out.batch" | "cutagent.action.fairlight.group.assign" | "cutagent.action.fairlight.io.patch" | "cutagent.action.fairlight.loudness.analyze" | "cutagent.action.fairlight.loudness.normalize" | "cutagent.action.fairlight.mixer.meter" | "cutagent.action.fairlight.monitor.level" | "cutagent.action.fairlight.monitor.mute" | "cutagent.action.fairlight.record.arm" | "cutagent.action.fairlight.record.start" | "cutagent.action.fairlight.record.stop" | "cutagent.action.fairlight.send.set" | "cutagent.action.fairlight.sound_library.audition" | "cutagent.action.fairlight.track.folder" | "cutagent.action.fairlight.track.hide" | "cutagent.action.fairlight.track.input_monitor" | "cutagent.action.fairlight.track.show" | "cutagent.action.fairlight.vca.assign" | "cutagent.action.fairlight.waveform.repair_click" | "cutagent.action.fusion.comp.current" | "cutagent.action.fusion.comp.delete" | "cutagent.action.fusion.comp.play" | "cutagent.action.fusion.comp.range" | "cutagent.action.fusion.comp.rename" | "cutagent.action.fusion.comp.render" | "cutagent.action.fusion.comp.stop" | "cutagent.action.fusion.effect.blur" | "cutagent.action.fusion.effect.color_correct" | "cutagent.action.fusion.effect.glow" | "cutagent.action.fusion.effect.sharpen" | "cutagent.action.fusion.effect.transform" | "cutagent.action.fusion.generate" | "cutagent.action.fusion.image.set" | "cutagent.action.fusion.insert_setting" | "cutagent.action.fusion.insert_settings.batch" | "cutagent.action.fusion.keyer.chroma" | "cutagent.action.fusion.keyframe.add" | "cutagent.action.fusion.keyframe.clear" | "cutagent.action.fusion.keyframe.delete" | "cutagent.action.fusion.keyframe.list" | "cutagent.action.fusion.keyframe.set" | "cutagent.action.fusion.macro.apply" | "cutagent.action.fusion.mask.ellipse" | "cutagent.action.fusion.mask.polygon" | "cutagent.action.fusion.mask.rectangle" | "cutagent.action.fusion.nested_text.update" | "cutagent.action.fusion.node.add" | "cutagent.action.fusion.node.connect" | "cutagent.action.fusion.node.delete" | "cutagent.action.fusion.node.disconnect" | "cutagent.action.fusion.setting.center_to_polypath" | "cutagent.action.fusion.setting.inspect" | "cutagent.action.fusion.setting.polypath_to_center" | "cutagent.action.fusion.setting.summary" | "cutagent.action.fusion.setting.validate" | "cutagent.action.fusion.template.apply" | "cutagent.action.fusion.template.assets.add" | "cutagent.action.fusion.template.assets.list" | "cutagent.action.fusion.template.dir" | "cutagent.action.fusion.template.icon.set" | "cutagent.action.fusion.template.install" | "cutagent.action.fusion.template.package_drfx" | "cutagent.action.fusion.template.scaffold" | "cutagent.action.fusion.template.show" | "cutagent.action.fusion.template.uninstall" | "cutagent.action.fusion.template.unpack_drfx" | "cutagent.action.fusion.template.validate" | "cutagent.action.fusion.text.set" | "cutagent.action.fusion.tool.active" | "cutagent.action.fusion.tool.add" | "cutagent.action.fusion.tool.attrs" | "cutagent.action.fusion.tool.connect" | "cutagent.action.fusion.tool.copy" | "cutagent.action.fusion.tool.delete" | "cutagent.action.fusion.tool.disconnect" | "cutagent.action.fusion.tool.get" | "cutagent.action.fusion.tool.inputs" | "cutagent.action.fusion.tool.list" | "cutagent.action.fusion.tool.outputs" | "cutagent.action.fusion.tool.paste" | "cutagent.action.fusion.tool.registry" | "cutagent.action.fusion.tool.set" | "cutagent.action.fusion.tracker.add" | "cutagent.action.lut.convert" | "cutagent.action.lut.generate.identity" | "cutagent.action.lut.inspect" | "cutagent.action.lut.install" | "cutagent.action.lut.list" | "cutagent.action.lut.remove" | "cutagent.action.lut.validate" | "cutagent.action.lut_refresh" | "cutagent.action.media.append" | "cutagent.action.media.append.batch" | "cutagent.action.media.clear_transcription" | "cutagent.action.media.color.clear" | "cutagent.action.media.color.set" | "cutagent.action.media.create_timeline" | "cutagent.action.media.delete" | "cutagent.action.media.duplicate" | "cutagent.action.media.extract_template" | "cutagent.action.media.flag.add" | "cutagent.action.media.flag.clear" | "cutagent.action.media.folder.export_drb" | "cutagent.action.media.folder.import_drb" | "cutagent.action.media.folders.create" | "cutagent.action.media.folders.delete" | "cutagent.action.media.folders.move" | "cutagent.action.media.folders.open" | "cutagent.action.media.folders.root" | "cutagent.action.media.growing_file.monitor" | "cutagent.action.media.import" | "cutagent.action.media.mark.clear" | "cutagent.action.media.mark.set" | "cutagent.action.media.marker.add" | "cutagent.action.media.marker.delete" | "cutagent.action.media.matte.delete" | "cutagent.action.media.metadata" | "cutagent.action.media.metadata.export" | "cutagent.action.media.move" | "cutagent.action.media.property_set" | "cutagent.action.media.proxy" | "cutagent.action.media.proxy.link_fullres" | "cutagent.action.media.relink" | "cutagent.action.media.rename" | "cutagent.action.media.replace" | "cutagent.action.media.replace_preserve_subclip" | "cutagent.action.media.selected.set" | "cutagent.action.media.stereo_create" | "cutagent.action.media.sync_audio" | "cutagent.action.media.third_party_metadata.bulk_set" | "cutagent.action.media.third_party_metadata.set" | "cutagent.action.media.transcode" | "cutagent.action.media.transcribe" | "cutagent.action.media.transcription" | "cutagent.action.media.unlink" | "cutagent.action.multicam.angle.remove" | "cutagent.action.multicam.angle.rename" | "cutagent.action.multicam.angle.set_enabled" | "cutagent.action.multicam.audio_activity.calibrate" | "cutagent.action.multicam.convert" | "cutagent.action.multicam.create" | "cutagent.action.multicam.flatten" | "cutagent.action.multicam.inspect" | "cutagent.action.multicam.match_frame" | "cutagent.action.multicam.recover_timing" | "cutagent.action.multicam.reorder_angles" | "cutagent.action.multicam.replace.audio" | "cutagent.action.multicam.replace.video" | "cutagent.action.multicam.seed_timeline" | "cutagent.action.multicam.set_start_timecode" | "cutagent.action.multicam.settings" | "cutagent.action.multicam.smart_switch" | "cutagent.action.multicam.source.grade_cdl" | "cutagent.action.multicam.source.move" | "cutagent.action.multicam.source.property_set" | "cutagent.action.multicam.source.raw_braw_set" | "cutagent.action.multicam.source.remove" | "cutagent.action.multicam.strip_embedded_audio" | "cutagent.action.multicam.switch" | "cutagent.action.multicam.timeline_create" | "cutagent.action.page.switch" | "cutagent.action.project.archive" | "cutagent.action.project.cleanup_scratch" | "cutagent.action.project.close" | "cutagent.action.project.cloud.create" | "cutagent.action.project.cloud.import" | "cutagent.action.project.cloud.open" | "cutagent.action.project.cloud.restore" | "cutagent.action.project.create" | "cutagent.action.project.delete" | "cutagent.action.project.export" | "cutagent.action.project.folders.create" | "cutagent.action.project.folders.delete" | "cutagent.action.project.folders.open" | "cutagent.action.project.folders.root" | "cutagent.action.project.folders.up" | "cutagent.action.project.import" | "cutagent.action.project.library.backup" | "cutagent.action.project.library.create" | "cutagent.action.project.library.restore" | "cutagent.action.project.library.switch" | "cutagent.action.project.list" | "cutagent.action.project.open" | "cutagent.action.project.preset.export" | "cutagent.action.project.preset.load" | "cutagent.action.project.preset.save" | "cutagent.action.project.rename" | "cutagent.action.project.restore" | "cutagent.action.project.save" | "cutagent.action.project.settings_set" | "cutagent.action.render.add" | "cutagent.action.render.alpha" | "cutagent.action.render.archive_settings" | "cutagent.action.render.audio" | "cutagent.action.render.burnin.export" | "cutagent.action.render.burnin.import" | "cutagent.action.render.burnin.load" | "cutagent.action.render.cancel" | "cutagent.action.render.custom_range" | "cutagent.action.render.delete" | "cutagent.action.render.encoding" | "cutagent.action.render.export" | "cutagent.action.render.export_file" | "cutagent.action.render.export_preset" | "cutagent.action.render.import_preset" | "cutagent.action.render.mode.set" | "cutagent.action.render.preset_delete" | "cutagent.action.render.preset_load" | "cutagent.action.render.preset_save" | "cutagent.action.render.preset_update" | "cutagent.action.render.quick_export" | "cutagent.action.render.settings.replace" | "cutagent.action.render.settings.update" | "cutagent.action.render.settings_set" | "cutagent.action.render.start" | "cutagent.action.render.stop" | "cutagent.action.render.subtitles" | "cutagent.action.render.transcript_audio" | "cutagent.action.render.wait" | "cutagent.action.storage.files" | "cutagent.action.storage.import" | "cutagent.action.storage.import_sequence" | "cutagent.action.storage.import_subclip" | "cutagent.action.storage.matte.add" | "cutagent.action.storage.matte.timeline_add" | "cutagent.action.storage.reveal" | "cutagent.action.storage.volumes" | "cutagent.action.system.keyframe_mode.set" | "cutagent.action.text.insert" | "cutagent.action.text.insert_captions" | "cutagent.action.text.insert_preset" | "cutagent.action.text.insert_template" | "cutagent.action.text.insert_template_batch" | "cutagent.action.text.update" | "cutagent.action.timeline.auto_caption" | "cutagent.action.timeline.clip_color.batch" | "cutagent.action.timeline.clip_markers.list" | "cutagent.action.timeline.compound_create" | "cutagent.action.timeline.create" | "cutagent.action.timeline.current_item" | "cutagent.action.timeline.delete" | "cutagent.action.timeline.dolby.analyze" | "cutagent.action.timeline.duplicate" | "cutagent.action.timeline.duration" | "cutagent.action.timeline.export" | "cutagent.action.timeline.fairlight_preset.apply" | "cutagent.action.timeline.frame_export" | "cutagent.action.timeline.frame_export.batch" | "cutagent.action.timeline.fusion_clip.create" | "cutagent.action.timeline.fusion_composition.insert" | "cutagent.action.timeline.grab_still" | "cutagent.action.timeline.import" | "cutagent.action.timeline.import_into" | "cutagent.action.timeline.info" | "cutagent.action.timeline.insert_generator" | "cutagent.action.timeline.insert_title" | "cutagent.action.timeline.inspect_export" | "cutagent.action.timeline.item_at" | "cutagent.action.timeline.items.delete" | "cutagent.action.timeline.items.move" | "cutagent.action.timeline.items.set_duration" | "cutagent.action.timeline.layer.ensure_media" | "cutagent.action.timeline.layout.free_stack" | "cutagent.action.timeline.list" | "cutagent.action.timeline.mark.clear" | "cutagent.action.timeline.mark.get" | "cutagent.action.timeline.mark.set" | "cutagent.action.timeline.marker.add" | "cutagent.action.timeline.marker.batch" | "cutagent.action.timeline.marker.delete" | "cutagent.action.timeline.marker.list" | "cutagent.action.timeline.marker.update" | "cutagent.action.timeline.media_pool_item" | "cutagent.action.timeline.node_graph.inspect" | "cutagent.action.timeline.output_blanking.get" | "cutagent.action.timeline.output_blanking.set" | "cutagent.action.timeline.overlay_stack.insert" | "cutagent.action.timeline.playhead.get" | "cutagent.action.timeline.playhead.set" | "cutagent.action.timeline.preview_export" | "cutagent.action.timeline.rename" | "cutagent.action.timeline.set_start_tc" | "cutagent.action.timeline.settings" | "cutagent.action.timeline.settings_set" | "cutagent.action.timeline.start_tc" | "cutagent.action.timeline.stereo_convert" | "cutagent.action.timeline.still.grab_all" | "cutagent.action.timeline.subtitle.export" | "cutagent.action.timeline.subtitle.insert" | "cutagent.action.timeline.subtitle.list" | "cutagent.action.timeline.summarize" | "cutagent.action.timeline.switch" | "cutagent.action.timeline.sync_clips" | "cutagent.action.timeline.thumbnail" | "cutagent.action.timeline.track.add" | "cutagent.action.timeline.track.delete" | "cutagent.action.timeline.track.disable" | "cutagent.action.timeline.track.enable" | "cutagent.action.timeline.track.items" | "cutagent.action.timeline.track.list" | "cutagent.action.timeline.track.lock" | "cutagent.action.timeline.track.rename" | "cutagent.action.timeline.track.subtype" | "cutagent.action.timeline.track.unlock" | "cutagent.action.timeline.voice_isolation.get" | "cutagent.action.timeline.voice_isolation.set" | "cutagent.action.transcript.create" | "cutagent.action.version.create" | "cutagent.action.version.prune" | "cutagent.action.version.restore", unknown>>;
        actionContractVersion: z.ZodLiteral<1>;
        value: z.ZodJSONSchema;
    }, z.core.$strict>>;
    resultOmitted: z.ZodOptional<z.ZodObject<{
        code: z.ZodLiteral<"OUTPUT_LIMIT_REACHED">;
        digest: z.ZodString;
    }, z.core.$strict>>;
    failure: z.ZodOptional<z.ZodObject<{
        code: z.ZodString;
        kind: z.ZodString;
        message: z.ZodString;
        cause: z.ZodObject<{
            code: z.ZodString;
        }, z.core.$strict>;
        readbackRequired: z.ZodBoolean;
        recoveryGuidance: z.ZodArray<z.ZodString>;
    }, z.core.$strict>>;
    custody: z.ZodOptional<z.ZodLiteral<"terminal_persistence_unavailable">>;
}, z.core.$strict>;
export type SdkPrepareActionRequest = z.infer<typeof sdkPrepareActionRequestSchema>;
export type SdkPreparedActionMutationBase = z.infer<typeof sdkPreparedActionMutationBaseSchema>;
export type SdkPrepareActionResult = z.infer<typeof sdkPrepareActionResultSchema>;
export type SdkPreparedActionAuthorizationBinding = z.infer<typeof sdkPreparedActionAuthorizationBindingSchema>;
export type SdkAdmitPreparedActionRequest = z.infer<typeof sdkAdmitPreparedActionRequestSchema>;
export type SdkExecutePreparedActionRequest = z.infer<typeof sdkExecutePreparedActionRequestSchema>;
export type SdkPreparedActionTerminal = z.infer<typeof sdkPreparedActionTerminalSchema>;
