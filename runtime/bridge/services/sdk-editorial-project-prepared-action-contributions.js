import {createFusionTimelinePreparedActionBuilderContributions} from "./sdk-fusion-timeline-prepared-action-contributions.js";
import {createProfessionalAvPreparedActionBuilderContributions} from "./sdk-professional-av-prepared-action-builders.js";
import {
  PROJECT_PRODUCTION_PREPARED_ACTION_IDS,
  createProjectPreparedActionBuilderContributions,
} from "./sdk-project-render-storage-media-prepared-action-builders.js";

const CLIP_TEXT_PRODUCTION_ACTION_IDS = Object.freeze([
  "cutagent.action.clip.audio_eq", "cutagent.action.clip.audio_gain",
  "cutagent.action.clip.audio_normalize", "cutagent.action.clip.audio_pan",
  "cutagent.action.clip.audio_pitch", "cutagent.action.clip.burnin.load",
  "cutagent.action.clip.cache", "cutagent.action.clip.cache_set",
  "cutagent.action.clip.color", "cutagent.action.clip.composite",
  "cutagent.action.clip.disable", "cutagent.action.clip.dynamic_zoom",
  "cutagent.action.clip.enable", "cutagent.action.clip.fade_in",
  "cutagent.action.clip.flag", "cutagent.action.clip.freeze",
  "cutagent.action.clip.fusion.add", "cutagent.action.clip.fusion.delete",
  "cutagent.action.clip.fusion.export", "cutagent.action.clip.fusion.import",
  "cutagent.action.clip.fusion.list", "cutagent.action.clip.fusion.load",
  "cutagent.action.clip.fusion.tool_set", "cutagent.action.clip.keyframe.delete",
  "cutagent.action.clip.keyframe.get", "cutagent.action.clip.keyframe.set_interpolation",
  "cutagent.action.clip.link", "cutagent.action.clip.linked.list",
  "cutagent.action.clip.offset",
  "cutagent.action.clip.marker.add", "cutagent.action.clip.marker.custom_data",
  "cutagent.action.clip.marker.delete", "cutagent.action.clip.marker.delete_custom",
  "cutagent.action.clip.properties", "cutagent.action.clip.rename",
  "cutagent.action.clip.reset_node_colors", "cutagent.action.clip.reverse",
  "cutagent.action.clip.smart_reframe", "cutagent.action.clip.source_range",
  "cutagent.action.clip.speed", "cutagent.action.clip.stabilize",
  "cutagent.action.clip.take.add", "cutagent.action.clip.take.delete",
  "cutagent.action.clip.take.finalize", "cutagent.action.clip.take.list",
  "cutagent.action.clip.take.select", "cutagent.action.clip.track_info",
  "cutagent.action.clip.unlink", "cutagent.action.clip.update_sidecar",
  "cutagent.action.clip.voice_isolation", "cutagent.action.text.insert",
  "cutagent.action.edit.auto_subtitle", "cutagent.action.edit.camera_pip",
  "cutagent.action.edit.delete_through_edit", "cutagent.action.edit.from_edl",
  "cutagent.action.edit.remove", "cutagent.action.edit.remove_range",
  "cutagent.action.edit.ripple_delete", "cutagent.action.edit.ripple_delete_selected",
  "cutagent.action.edit.scene_detect", "cutagent.action.edit.slide_selected",
  "cutagent.action.edit.slip_selected", "cutagent.action.edit.social_crop",
  "cutagent.action.edit.split", "cutagent.action.edit.transition.add",
  "cutagent.action.text.insert_preset", "cutagent.action.text.insert_template",
  "cutagent.action.text.insert_template_batch", "cutagent.action.text.update",
]);

const TIMELINE_READ_PRODUCTION_ACTION_IDS = Object.freeze([
  "cutagent.action.timeline.clip_markers.list", "cutagent.action.timeline.item_at",
  "cutagent.action.timeline.current_item", "cutagent.action.timeline.duration",
  "cutagent.action.timeline.info",
  "cutagent.action.timeline.mark.get",
  "cutagent.action.timeline.marker.list", "cutagent.action.timeline.media_pool_item",
  "cutagent.action.timeline.node_graph.inspect", "cutagent.action.timeline.playhead.get",
  "cutagent.action.timeline.settings", "cutagent.action.timeline.summarize",
  "cutagent.action.timeline.track.items", "cutagent.action.timeline.track.list",
  "cutagent.action.timeline.track.subtype", "cutagent.action.timeline.voice_isolation.get",
]);

const TIMELINE_ORDINARY_PRODUCTION_ACTION_IDS = Object.freeze([
  "cutagent.action.timeline.create", "cutagent.action.timeline.delete",
  "cutagent.action.timeline.dolby.analyze", "cutagent.action.timeline.duplicate",
  "cutagent.action.timeline.fairlight_preset.apply", "cutagent.action.timeline.import",
  "cutagent.action.timeline.mark.clear", "cutagent.action.timeline.mark.set",
  "cutagent.action.timeline.playhead.set", "cutagent.action.timeline.rename",
  "cutagent.action.timeline.set_start_tc", "cutagent.action.timeline.settings_set",
  "cutagent.action.timeline.start_tc", "cutagent.action.timeline.switch",
]);

/**
 * Editorial routes whose exact schemas, private lowering, stable live binding,
 * Mutation Policy impact, durable terminal, and verification are already owned
 * by the signed prepared-action production packets. Central composition owns
 * advertisement; this module contributes no command or lowering metadata.
 */
export const EDITORIAL_PROJECT_PRODUCTION_PREPARED_ACTION_IDS = Object.freeze([
  ...CLIP_TEXT_PRODUCTION_ACTION_IDS,
  ...TIMELINE_READ_PRODUCTION_ACTION_IDS,
  ...TIMELINE_ORDINARY_PRODUCTION_ACTION_IDS,
  ...PROJECT_PRODUCTION_PREPARED_ACTION_IDS,
]);

if (EDITORIAL_PROJECT_PRODUCTION_PREPARED_ACTION_IDS.length !== 164
  || new Set(EDITORIAL_PROJECT_PRODUCTION_PREPARED_ACTION_IDS).size !== 164) {
  throw new Error("Editorial/project production action selection is not exact and unique.");
}

export function createEditorialProjectPreparedActionBuilderContributions(dependencies = {}) {
  const clipText = createProfessionalAvPreparedActionBuilderContributions({
    ...dependencies,
    enabledActionIds: new Set(CLIP_TEXT_PRODUCTION_ACTION_IDS),
  });
  const timeline = createFusionTimelinePreparedActionBuilderContributions({
    ...dependencies,
    enabledActionIds: new Set([...TIMELINE_READ_PRODUCTION_ACTION_IDS, ...TIMELINE_ORDINARY_PRODUCTION_ACTION_IDS]),
  });
  const project = createProjectPreparedActionBuilderContributions(dependencies);
  const contributions = Object.freeze({...clipText, ...timeline, ...project});
  const actual = Object.keys(contributions).sort();
  const expected = [...EDITORIAL_PROJECT_PRODUCTION_PREPARED_ACTION_IDS].sort();
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error("Editorial/project prepared-action contribution drifted from its reviewed production packet.");
  }
  return contributions;
}
