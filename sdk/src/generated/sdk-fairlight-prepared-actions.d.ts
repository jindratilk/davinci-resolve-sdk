import { z } from "zod";
export declare const CUTAGENT_SDK_FAIRLIGHT_DURABLE_BOUNCE_EXCLUSION_ACTION_IDS: readonly [];
export declare const CUTAGENT_SDK_FAIRLIGHT_PREPARED_READ_ACTION_IDS: readonly ["cutagent.action.fairlight.channel_map.clip", "cutagent.action.fairlight.sound_library.source_list"];
export declare const CUTAGENT_SDK_FAIRLIGHT_REVIEWED_CANDIDATE_ACTION_IDS: readonly ["cutagent.action.fairlight.add", "cutagent.action.fairlight.ai.dialogue_leveler", "cutagent.action.fairlight.ai.music_remixer", "cutagent.action.fairlight.ai.voice_isolation", "cutagent.action.fairlight.automation.write", "cutagent.action.fairlight.bounce.mix_to_track", "cutagent.action.fairlight.bounce.track", "cutagent.action.fairlight.bus.assign", "cutagent.action.fairlight.bus.level", "cutagent.action.fairlight.channel_map.clip", "cutagent.action.fairlight.channel_map.set", "cutagent.action.fairlight.clip.delete", "cutagent.action.fairlight.clip.link", "cutagent.action.fairlight.clip.move", "cutagent.action.fairlight.clip.nudge", "cutagent.action.fairlight.clip.slip", "cutagent.action.fairlight.clip.split", "cutagent.action.fairlight.clip.trim", "cutagent.action.fairlight.clip.unlink", "cutagent.action.fairlight.delete", "cutagent.action.fairlight.dynamics.disable", "cutagent.action.fairlight.dynamics.enable", "cutagent.action.fairlight.dynamics.set", "cutagent.action.fairlight.effect.add", "cutagent.action.fairlight.effect.remove", "cutagent.action.fairlight.effect.set_param", "cutagent.action.fairlight.elastic.enable", "cutagent.action.fairlight.elastic.keyframe", "cutagent.action.fairlight.ensure_stereo_tracks", "cutagent.action.fairlight.ensure_tracks", "cutagent.action.fairlight.eq.set", "cutagent.action.fairlight.export.audio", "cutagent.action.fairlight.insert", "cutagent.action.fairlight.item_source.patch", "cutagent.action.fairlight.lock", "cutagent.action.fairlight.mixer.fader", "cutagent.action.fairlight.mixer.pan", "cutagent.action.fairlight.mute", "cutagent.action.fairlight.preset.apply", "cutagent.action.fairlight.rename", "cutagent.action.fairlight.solo", "cutagent.action.fairlight.solo_restore", "cutagent.action.fairlight.sound_library.delete", "cutagent.action.fairlight.sound_library.index_file", "cutagent.action.fairlight.sound_library.index_folder", "cutagent.action.fairlight.sound_library.insert", "cutagent.action.fairlight.sound_library.source_list", "cutagent.action.fairlight.sound_library.source_rebuild", "cutagent.action.fairlight.sound_library.source_remove", "cutagent.action.fairlight.track.duplicate", "cutagent.action.fairlight.track_color", "cutagent.action.fairlight.track_format.set", "cutagent.action.fairlight.track_order.move", "cutagent.action.fairlight.transition.add", "cutagent.action.fairlight.unlock", "cutagent.action.fairlight.unmute", "cutagent.action.fairlight.voice_isolation.set"];
export declare const CUTAGENT_SDK_FAIRLIGHT_RAW_AUDIO_TRACK_ACTION_BINDINGS: readonly [{
    readonly actionId: "cutagent.action.fairlight.automation.write";
    readonly selectorKey: "track";
}, {
    readonly actionId: "cutagent.action.fairlight.dynamics.disable";
    readonly selectorKey: "track";
    readonly defaultTrackIndex: 1;
}, {
    readonly actionId: "cutagent.action.fairlight.dynamics.enable";
    readonly selectorKey: "track";
    readonly defaultTrackIndex: 1;
}, {
    readonly actionId: "cutagent.action.fairlight.dynamics.set";
    readonly selectorKey: "track";
    readonly defaultTrackIndex: 1;
}, {
    readonly actionId: "cutagent.action.fairlight.lock";
    readonly selectorKey: "index";
}, {
    readonly actionId: "cutagent.action.fairlight.mixer.fader";
    readonly selectorKey: "track";
    readonly alternateSelectorKey: "bus";
}, {
    readonly actionId: "cutagent.action.fairlight.mixer.pan";
    readonly selectorKey: "track";
}, {
    readonly actionId: "cutagent.action.fairlight.mute";
    readonly selectorKey: "index";
}, {
    readonly actionId: "cutagent.action.fairlight.rename";
    readonly selectorKey: "index";
}, {
    readonly actionId: "cutagent.action.fairlight.solo";
    readonly selectorKey: "index";
}, {
    readonly actionId: "cutagent.action.fairlight.track.duplicate";
    readonly selectorKey: "index";
}, {
    readonly actionId: "cutagent.action.fairlight.track_color";
    readonly selectorKey: "index";
}, {
    readonly actionId: "cutagent.action.fairlight.track_format.set";
    readonly selectorKey: "index";
}, {
    readonly actionId: "cutagent.action.fairlight.unlock";
    readonly selectorKey: "index";
}, {
    readonly actionId: "cutagent.action.fairlight.unmute";
    readonly selectorKey: "index";
}, {
    readonly actionId: "cutagent.action.fairlight.voice_isolation.set";
    readonly selectorKey: "track";
}];
export declare const CUTAGENT_SDK_FAIRLIGHT_RAW_AUDIO_TRACK_ACTION_IDS: readonly ("cutagent.action.fairlight.automation.write" | "cutagent.action.fairlight.dynamics.disable" | "cutagent.action.fairlight.dynamics.enable" | "cutagent.action.fairlight.dynamics.set" | "cutagent.action.fairlight.lock" | "cutagent.action.fairlight.mixer.fader" | "cutagent.action.fairlight.mixer.pan" | "cutagent.action.fairlight.mute" | "cutagent.action.fairlight.rename" | "cutagent.action.fairlight.solo" | "cutagent.action.fairlight.track.duplicate" | "cutagent.action.fairlight.track_color" | "cutagent.action.fairlight.track_format.set" | "cutagent.action.fairlight.unlock" | "cutagent.action.fairlight.unmute" | "cutagent.action.fairlight.voice_isolation.set")[];
export declare const CUTAGENT_SDK_FAIRLIGHT_RAW_AUDIO_CLIP_ACTION_BINDINGS: readonly [{
    readonly actionId: "cutagent.action.fairlight.channel_map.set";
    readonly selectorKey: "clipName";
    readonly required: true;
}, {
    readonly actionId: "cutagent.action.fairlight.ai.voice_isolation";
    readonly selectorKey: "clip";
    readonly defaultFirstAudioClip: true;
}, {
    readonly actionId: "cutagent.action.fairlight.eq.set";
    readonly selectorKey: "clip";
    readonly defaultFirstAudioClip: true;
}, {
    readonly actionId: "cutagent.action.fairlight.item_source.patch";
    readonly selectorKey: "itemId";
    readonly required: true;
    readonly idOnly: true;
    readonly exactRecordRangeChecks: true;
}];
export declare const CUTAGENT_SDK_FAIRLIGHT_RAW_AUDIO_CLIP_ACTION_IDS: readonly ("cutagent.action.fairlight.ai.voice_isolation" | "cutagent.action.fairlight.channel_map.set" | "cutagent.action.fairlight.eq.set" | "cutagent.action.fairlight.item_source.patch")[];
export declare const CUTAGENT_SDK_FAIRLIGHT_CARRIER_OWNED_ACTION_IDS: readonly ("cutagent.action.fairlight.ai.voice_isolation" | "cutagent.action.fairlight.automation.write" | "cutagent.action.fairlight.channel_map.set" | "cutagent.action.fairlight.dynamics.disable" | "cutagent.action.fairlight.dynamics.enable" | "cutagent.action.fairlight.dynamics.set" | "cutagent.action.fairlight.eq.set" | "cutagent.action.fairlight.item_source.patch" | "cutagent.action.fairlight.lock" | "cutagent.action.fairlight.mixer.fader" | "cutagent.action.fairlight.mixer.pan" | "cutagent.action.fairlight.mute" | "cutagent.action.fairlight.rename" | "cutagent.action.fairlight.solo" | "cutagent.action.fairlight.track.duplicate" | "cutagent.action.fairlight.track_color" | "cutagent.action.fairlight.track_format.set" | "cutagent.action.fairlight.unlock" | "cutagent.action.fairlight.unmute" | "cutagent.action.fairlight.voice_isolation.set")[];
export declare const CUTAGENT_SDK_FAIRLIGHT_PREPARED_ACTION_IDS: readonly ["cutagent.action.fairlight.add", "cutagent.action.fairlight.ai.dialogue_leveler", "cutagent.action.fairlight.ai.music_remixer", "cutagent.action.fairlight.ai.voice_isolation", "cutagent.action.fairlight.automation.write", "cutagent.action.fairlight.bounce.mix_to_track", "cutagent.action.fairlight.bounce.track", "cutagent.action.fairlight.bus.assign", "cutagent.action.fairlight.bus.level", "cutagent.action.fairlight.channel_map.clip", "cutagent.action.fairlight.channel_map.set", "cutagent.action.fairlight.clip.delete", "cutagent.action.fairlight.clip.link", "cutagent.action.fairlight.clip.move", "cutagent.action.fairlight.clip.nudge", "cutagent.action.fairlight.clip.slip", "cutagent.action.fairlight.clip.split", "cutagent.action.fairlight.clip.trim", "cutagent.action.fairlight.clip.unlink", "cutagent.action.fairlight.delete", "cutagent.action.fairlight.dynamics.disable", "cutagent.action.fairlight.dynamics.enable", "cutagent.action.fairlight.dynamics.set", "cutagent.action.fairlight.effect.add", "cutagent.action.fairlight.effect.remove", "cutagent.action.fairlight.effect.set_param", "cutagent.action.fairlight.elastic.enable", "cutagent.action.fairlight.elastic.keyframe", "cutagent.action.fairlight.ensure_stereo_tracks", "cutagent.action.fairlight.ensure_tracks", "cutagent.action.fairlight.eq.set", "cutagent.action.fairlight.export.audio", "cutagent.action.fairlight.insert", "cutagent.action.fairlight.item_source.patch", "cutagent.action.fairlight.lock", "cutagent.action.fairlight.mixer.fader", "cutagent.action.fairlight.mixer.pan", "cutagent.action.fairlight.mute", "cutagent.action.fairlight.preset.apply", "cutagent.action.fairlight.rename", "cutagent.action.fairlight.solo", "cutagent.action.fairlight.solo_restore", "cutagent.action.fairlight.sound_library.delete", "cutagent.action.fairlight.sound_library.index_file", "cutagent.action.fairlight.sound_library.index_folder", "cutagent.action.fairlight.sound_library.insert", "cutagent.action.fairlight.sound_library.source_list", "cutagent.action.fairlight.sound_library.source_rebuild", "cutagent.action.fairlight.sound_library.source_remove", "cutagent.action.fairlight.track.duplicate", "cutagent.action.fairlight.track_color", "cutagent.action.fairlight.track_format.set", "cutagent.action.fairlight.track_order.move", "cutagent.action.fairlight.transition.add", "cutagent.action.fairlight.unlock", "cutagent.action.fairlight.unmute", "cutagent.action.fairlight.voice_isolation.set"];
export declare const CUTAGENT_SDK_FAIRLIGHT_PREPARED_UNAVAILABLE_ACTION_IDS: readonly [];
export declare const sdkFairlightPreparedCarrierBindingSchema: z.ZodObject<{
    projectLibraryId: z.ZodString;
    projectId: z.ZodString;
    timelineId: z.ZodString;
    projectLibraryRevision: z.ZodString;
    projectRevision: z.ZodString;
    timelineRevision: z.ZodString;
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
    referencedPayloadDigests: z.ZodDefault<z.ZodArray<z.ZodString>>;
}, z.core.$strict>;
export declare const sdkFairlightPreparedOperationInputSchema: z.ZodObject<{
    actionInput: z.ZodRecord<z.ZodString, z.ZodType<unknown, unknown, z.core.$ZodTypeInternals<unknown, unknown>>>;
    carrierBinding: z.ZodObject<{
        projectLibraryId: z.ZodString;
        projectId: z.ZodString;
        timelineId: z.ZodString;
        projectLibraryRevision: z.ZodString;
        projectRevision: z.ZodString;
        timelineRevision: z.ZodString;
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
        referencedPayloadDigests: z.ZodDefault<z.ZodArray<z.ZodString>>;
    }, z.core.$strict>;
}, z.core.$strict>;
export type SdkFairlightPreparedOperationInput = z.infer<typeof sdkFairlightPreparedOperationInputSchema>;
