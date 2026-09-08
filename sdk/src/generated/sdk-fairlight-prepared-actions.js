import { z } from "zod";
import { sdkSha256DigestSchema, sdkStableMutationTargetSchema, sdkStableTargetIdSchema, sdkStateRevisionSchema, } from "./sdk-mutation-policy.js";
export const CUTAGENT_SDK_FAIRLIGHT_DURABLE_BOUNCE_EXCLUSION_ACTION_IDS = [];
export const CUTAGENT_SDK_FAIRLIGHT_PREPARED_READ_ACTION_IDS = [
    "cutagent.action.fairlight.channel_map.clip",
    "cutagent.action.fairlight.sound_library.source_list",
];
export const CUTAGENT_SDK_FAIRLIGHT_REVIEWED_CANDIDATE_ACTION_IDS = [
    "cutagent.action.fairlight.add",
    "cutagent.action.fairlight.ai.dialogue_leveler",
    "cutagent.action.fairlight.ai.music_remixer",
    "cutagent.action.fairlight.ai.voice_isolation",
    "cutagent.action.fairlight.automation.write",
    "cutagent.action.fairlight.bounce.mix_to_track",
    "cutagent.action.fairlight.bounce.track",
    "cutagent.action.fairlight.bus.assign",
    "cutagent.action.fairlight.bus.level",
    "cutagent.action.fairlight.channel_map.clip",
    "cutagent.action.fairlight.channel_map.set",
    "cutagent.action.fairlight.clip.delete",
    "cutagent.action.fairlight.clip.link",
    "cutagent.action.fairlight.clip.move",
    "cutagent.action.fairlight.clip.nudge",
    "cutagent.action.fairlight.clip.slip",
    "cutagent.action.fairlight.clip.split",
    "cutagent.action.fairlight.clip.trim",
    "cutagent.action.fairlight.clip.unlink",
    "cutagent.action.fairlight.delete",
    "cutagent.action.fairlight.dynamics.disable",
    "cutagent.action.fairlight.dynamics.enable",
    "cutagent.action.fairlight.dynamics.set",
    "cutagent.action.fairlight.effect.add",
    "cutagent.action.fairlight.effect.remove",
    "cutagent.action.fairlight.effect.set_param",
    "cutagent.action.fairlight.elastic.enable",
    "cutagent.action.fairlight.elastic.keyframe",
    "cutagent.action.fairlight.ensure_stereo_tracks",
    "cutagent.action.fairlight.ensure_tracks",
    "cutagent.action.fairlight.eq.set",
    "cutagent.action.fairlight.export.audio",
    "cutagent.action.fairlight.insert",
    "cutagent.action.fairlight.item_source.patch",
    "cutagent.action.fairlight.lock",
    "cutagent.action.fairlight.mixer.fader",
    "cutagent.action.fairlight.mixer.pan",
    "cutagent.action.fairlight.mute",
    "cutagent.action.fairlight.preset.apply",
    "cutagent.action.fairlight.rename",
    "cutagent.action.fairlight.solo",
    "cutagent.action.fairlight.solo_restore",
    "cutagent.action.fairlight.sound_library.delete",
    "cutagent.action.fairlight.sound_library.index_file",
    "cutagent.action.fairlight.sound_library.index_folder",
    "cutagent.action.fairlight.sound_library.insert",
    "cutagent.action.fairlight.sound_library.source_list",
    "cutagent.action.fairlight.sound_library.source_rebuild",
    "cutagent.action.fairlight.sound_library.source_remove",
    "cutagent.action.fairlight.track.duplicate",
    "cutagent.action.fairlight.track_color",
    "cutagent.action.fairlight.track_format.set",
    "cutagent.action.fairlight.track_order.move",
    "cutagent.action.fairlight.transition.add",
    "cutagent.action.fairlight.unlock",
    "cutagent.action.fairlight.unmute",
    "cutagent.action.fairlight.voice_isolation.set",
];
// Public inputs for these actions identify one audio track by a one-based
// selector. The desktop carrier resolves that
// selector to a fresh stable identity and never accepts a caller-authored
// carrier binding.
// Deliberately excluded routes need different custody: solo_restore and link
// operations are multi-target; clip and media routes need stable item
// resolution; and bounce, import/export, and Sound Library mutations require
// managed-file or durable-output custody.
export const CUTAGENT_SDK_FAIRLIGHT_RAW_AUDIO_TRACK_ACTION_BINDINGS = [
    { actionId: "cutagent.action.fairlight.automation.write", selectorKey: "track" },
    { actionId: "cutagent.action.fairlight.dynamics.disable", selectorKey: "track", defaultTrackIndex: 1 },
    { actionId: "cutagent.action.fairlight.dynamics.enable", selectorKey: "track", defaultTrackIndex: 1 },
    { actionId: "cutagent.action.fairlight.dynamics.set", selectorKey: "track", defaultTrackIndex: 1 },
    { actionId: "cutagent.action.fairlight.lock", selectorKey: "index" },
    { actionId: "cutagent.action.fairlight.mixer.fader", selectorKey: "track", alternateSelectorKey: "bus" },
    { actionId: "cutagent.action.fairlight.mixer.pan", selectorKey: "track" },
    { actionId: "cutagent.action.fairlight.mute", selectorKey: "index" },
    { actionId: "cutagent.action.fairlight.rename", selectorKey: "index" },
    { actionId: "cutagent.action.fairlight.solo", selectorKey: "index" },
    { actionId: "cutagent.action.fairlight.track.duplicate", selectorKey: "index" },
    { actionId: "cutagent.action.fairlight.track_color", selectorKey: "index" },
    { actionId: "cutagent.action.fairlight.track_format.set", selectorKey: "index" },
    { actionId: "cutagent.action.fairlight.unlock", selectorKey: "index" },
    { actionId: "cutagent.action.fairlight.unmute", selectorKey: "index" },
    { actionId: "cutagent.action.fairlight.voice_isolation.set", selectorKey: "track" },
];
export const CUTAGENT_SDK_FAIRLIGHT_RAW_AUDIO_TRACK_ACTION_IDS = Object.freeze(CUTAGENT_SDK_FAIRLIGHT_RAW_AUDIO_TRACK_ACTION_BINDINGS.map((binding) => binding.actionId));
// Public inputs for these actions identify one audio clip by public snapshot
// identity or exact name. When omitted, the desktop carrier binds the first
// current-timeline audio clip, matching the public command contract, while the
// native timeline-item identity remains private.
export const CUTAGENT_SDK_FAIRLIGHT_RAW_AUDIO_CLIP_ACTION_BINDINGS = [
    { actionId: "cutagent.action.fairlight.ai.voice_isolation", selectorKey: "clip", defaultFirstAudioClip: true },
    { actionId: "cutagent.action.fairlight.eq.set", selectorKey: "clip", defaultFirstAudioClip: true },
    { actionId: "cutagent.action.fairlight.item_source.patch", selectorKey: "itemId", required: true, idOnly: true, exactRecordRangeChecks: true },
];
export const CUTAGENT_SDK_FAIRLIGHT_RAW_AUDIO_CLIP_ACTION_IDS = Object.freeze(CUTAGENT_SDK_FAIRLIGHT_RAW_AUDIO_CLIP_ACTION_BINDINGS.map((binding) => binding.actionId));
export const CUTAGENT_SDK_FAIRLIGHT_CARRIER_OWNED_ACTION_IDS = Object.freeze([
    ...CUTAGENT_SDK_FAIRLIGHT_RAW_AUDIO_TRACK_ACTION_IDS,
    ...CUTAGENT_SDK_FAIRLIGHT_RAW_AUDIO_CLIP_ACTION_IDS,
]);
// These routes have complete carrier-relative implementation seams for
// evaluation. Signed-host advertisement remains a separate release gate and
// must stay closed until the route's required live evidence has been proven.
export const CUTAGENT_SDK_FAIRLIGHT_PREPARED_ACTION_IDS = CUTAGENT_SDK_FAIRLIGHT_REVIEWED_CANDIDATE_ACTION_IDS;
export const CUTAGENT_SDK_FAIRLIGHT_PREPARED_UNAVAILABLE_ACTION_IDS = CUTAGENT_SDK_FAIRLIGHT_DURABLE_BOUNCE_EXCLUSION_ACTION_IDS;
const jsonValueSchema = z.lazy(() => z.union([
    z.null(), z.boolean(), z.number().finite(), z.string().max(1_048_576),
    z.array(jsonValueSchema).max(10_000), z.record(z.string().max(256), jsonValueSchema),
]));
export const sdkFairlightPreparedCarrierBindingSchema = z.object({
    projectLibraryId: sdkStableTargetIdSchema,
    projectId: sdkStableTargetIdSchema,
    timelineId: sdkStableTargetIdSchema,
    projectLibraryRevision: sdkStateRevisionSchema,
    projectRevision: sdkStateRevisionSchema,
    timelineRevision: sdkStateRevisionSchema,
    targets: z.array(sdkStableMutationTargetSchema).max(10_000),
    referencedPayloadDigests: z.array(sdkSha256DigestSchema).max(1_000).default([]),
}).strict().superRefine((binding, context) => {
    const ids = binding.targets.map((target) => target.stableId);
    if (new Set(ids).size !== ids.length) {
        context.addIssue({ code: "custom", path: ["targets"], message: "Prepared Fairlight target identities must be unique" });
    }
});
export const sdkFairlightPreparedOperationInputSchema = z.object({
    actionInput: z.record(z.string().max(256), jsonValueSchema),
    carrierBinding: sdkFairlightPreparedCarrierBindingSchema,
}).strict().superRefine((value, context) => {
    if (new TextEncoder().encode(JSON.stringify(value.actionInput)).byteLength > 1024 * 1024) {
        context.addIssue({ code: "custom", path: ["actionInput"], message: "Prepared Fairlight input exceeds its public bound" });
    }
});
