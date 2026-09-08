import {createProfessionalAvPreparedActionBuilderContributions} from "./sdk-professional-av-prepared-action-builders.js";

/**
 * Audio/operations routes whose private signed-runtime descriptors, exact live
 * binding capture, Mutation Policy impact, and independent verification are
 * already production-owned. Central composition decides when to advertise the
 * packet; this domain module never mutates global reachability on its own.
 */
export const AUDIO_OPERATIONS_PRODUCTION_PREPARED_ACTION_IDS = Object.freeze([
  "cutagent.action.audio.beat_detect",
  "cutagent.action.audio.duck",
  "cutagent.action.audio.info",
  "cutagent.action.audio.probe_subframe",
  "cutagent.action.audio.reverb",
  "cutagent.action.audio.waveform_offset",
]);

export function createAudioOperationsPreparedActionBuilderContributions(dependencies = {}) {
  const contributions = createProfessionalAvPreparedActionBuilderContributions({
    ...dependencies,
    enabledActionIds: new Set(AUDIO_OPERATIONS_PRODUCTION_PREPARED_ACTION_IDS),
  });
  const actionIds = Object.keys(contributions).sort();
  if (JSON.stringify(actionIds) !== JSON.stringify([...AUDIO_OPERATIONS_PRODUCTION_PREPARED_ACTION_IDS].sort())) {
    throw new Error("Audio/operations prepared-action contribution drifted from its reviewed production packet.");
  }
  return contributions;
}
