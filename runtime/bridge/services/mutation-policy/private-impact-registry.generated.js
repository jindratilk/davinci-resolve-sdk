// Generated from the private authoritative CutAgent CLI inventory. Do not edit.
// Selected runtime source distributed under AGPL-3.0-only; see PROVENANCE.md.
export const PRIVATE_IMPACT_REGISTRY_VERSION = 3;
export const PRIVATE_IMPACT_REGISTRY_DIGEST = "sha256:ea97a6eda75096a87b52bfc0520cfb734767e97192f114c58a3c0e1f2fd5fcc2";
export const PRIVATE_COMMAND_IMPACT = Object.freeze(new Map([
  [
    "asset.artifact_index",
    {
      "commandId": "asset.artifact_index",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "asset.resolve",
    {
      "commandId": "asset.resolve",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "audio.beat_detect",
    {
      "commandId": "audio.beat_detect",
      "actionId": "cutagent.action.audio.beat_detect",
      "aliasOf": null,
      "operationClass": "long_running",
      "verificationCategory": "terminal_and_readback"
    }
  ],
  [
    "audio.duck",
    {
      "commandId": "audio.duck",
      "actionId": "cutagent.action.audio.duck",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "audio.info",
    {
      "commandId": "audio.info",
      "actionId": "cutagent.action.audio.info",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "audio.probe_subframe",
    {
      "commandId": "audio.probe_subframe",
      "actionId": "cutagent.action.audio.probe_subframe",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "audio.reverb",
    {
      "commandId": "audio.reverb",
      "actionId": "cutagent.action.audio.reverb",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "audio.voice_generate",
    {
      "commandId": "audio.voice_generate",
      "actionId": "cutagent.action.audio.voice_generate",
      "aliasOf": null,
      "operationClass": "long_running",
      "verificationCategory": "terminal_and_readback"
    }
  ],
  [
    "audio.voice_list",
    {
      "commandId": "audio.voice_list",
      "actionId": "cutagent.action.audio.voice_list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "audio.voice_place",
    {
      "commandId": "audio.voice_place",
      "actionId": "cutagent.action.audio.voice_place",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "audio.waveform_offset",
    {
      "commandId": "audio.waveform_offset",
      "actionId": "cutagent.action.audio.waveform_offset",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "auto_edit.multicam",
    {
      "commandId": "auto_edit.multicam",
      "actionId": "cutagent.action.auto_edit.multicam",
      "aliasOf": null,
      "operationClass": "long_running",
      "verificationCategory": "terminal_and_readback"
    }
  ],
  [
    "auto_edit.podcast_edit",
    {
      "commandId": "auto_edit.podcast_edit",
      "actionId": "cutagent.action.auto_edit.podcast_edit",
      "aliasOf": null,
      "operationClass": "long_running",
      "verificationCategory": "terminal_and_readback"
    }
  ],
  [
    "auto_edit.podcast_multicam",
    {
      "commandId": "auto_edit.podcast_multicam",
      "actionId": "cutagent.action.auto_edit.podcast_multicam",
      "aliasOf": null,
      "operationClass": "long_running",
      "verificationCategory": "terminal_and_readback"
    }
  ],
  [
    "auto_edit.run",
    {
      "commandId": "auto_edit.run",
      "actionId": "cutagent.action.auto_edit.run",
      "aliasOf": null,
      "operationClass": "long_running",
      "verificationCategory": "terminal_and_readback"
    }
  ],
  [
    "auto_edit.silence_cut",
    {
      "commandId": "auto_edit.silence_cut",
      "actionId": "cutagent.action.auto_edit.silence_cut",
      "aliasOf": null,
      "operationClass": "long_running",
      "verificationCategory": "terminal_and_readback"
    }
  ],
  [
    "batch.run",
    {
      "commandId": "batch.run",
      "actionId": "cutagent.action.batch.run",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "batch.validate",
    {
      "commandId": "batch.validate",
      "actionId": "cutagent.action.batch.validate",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "bulk.clip_color_set",
    {
      "commandId": "bulk.clip_color_set",
      "actionId": "cutagent.action.bulk.clip_color_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "bulk.disable",
    {
      "commandId": "bulk.disable",
      "actionId": "cutagent.action.bulk.disable",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "bulk.enable",
    {
      "commandId": "bulk.enable",
      "actionId": "cutagent.action.bulk.enable",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "bulk.lut_set",
    {
      "commandId": "bulk.lut_set",
      "actionId": "cutagent.action.bulk.lut_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "bulk.property_set",
    {
      "commandId": "bulk.property_set",
      "actionId": "cutagent.action.bulk.property_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "bulk.select",
    {
      "commandId": "bulk.select",
      "actionId": "cutagent.action.bulk.select",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "burnin.load",
    {
      "commandId": "burnin.load",
      "actionId": "cutagent.action.burnin.load",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "burnin.preset.export",
    {
      "commandId": "burnin.preset.export",
      "actionId": "cutagent.action.burnin.preset.export",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "burnin.preset.import",
    {
      "commandId": "burnin.preset.import",
      "actionId": "cutagent.action.burnin.preset.import",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "capabilities",
    {
      "commandId": "capabilities",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "clip.audio_eq",
    {
      "commandId": "clip.audio_eq",
      "actionId": "cutagent.action.clip.audio_eq",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.audio_gain",
    {
      "commandId": "clip.audio_gain",
      "actionId": "cutagent.action.clip.audio_gain",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.audio_normalize",
    {
      "commandId": "clip.audio_normalize",
      "actionId": "cutagent.action.clip.audio_normalize",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.audio_pan",
    {
      "commandId": "clip.audio_pan",
      "actionId": "cutagent.action.clip.audio_pan",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.audio_pitch",
    {
      "commandId": "clip.audio_pitch",
      "actionId": "cutagent.action.clip.audio_pitch",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.burnin.load",
    {
      "commandId": "clip.burnin.load",
      "actionId": "cutagent.action.clip.burnin.load",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.cache",
    {
      "commandId": "clip.cache",
      "actionId": "cutagent.action.clip.cache",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.cache_set",
    {
      "commandId": "clip.cache_set",
      "actionId": "cutagent.action.clip.cache_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.cache_state",
    {
      "commandId": "clip.cache_state",
      "actionId": "cutagent.action.clip.cache_state",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "clip.color",
    {
      "commandId": "clip.color",
      "actionId": "cutagent.action.clip.color",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.composite",
    {
      "commandId": "clip.composite",
      "actionId": "cutagent.action.clip.composite",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.current",
    {
      "commandId": "clip.current",
      "actionId": "cutagent.action.clip.current",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "clip.disable",
    {
      "commandId": "clip.disable",
      "actionId": "cutagent.action.clip.disable",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.dynamic_zoom",
    {
      "commandId": "clip.dynamic_zoom",
      "actionId": "cutagent.action.clip.dynamic_zoom",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.enable",
    {
      "commandId": "clip.enable",
      "actionId": "cutagent.action.clip.enable",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.fade_in",
    {
      "commandId": "clip.fade_in",
      "actionId": "cutagent.action.clip.fade_in",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.flag",
    {
      "commandId": "clip.flag",
      "actionId": "cutagent.action.clip.flag",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.freeze",
    {
      "commandId": "clip.freeze",
      "actionId": "cutagent.action.clip.freeze",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.fusion.add",
    {
      "commandId": "clip.fusion.add",
      "actionId": "cutagent.action.clip.fusion.add",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.fusion.by_name",
    {
      "commandId": "clip.fusion.by_name",
      "actionId": "cutagent.action.clip.fusion.by_name",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "clip.fusion.delete",
    {
      "commandId": "clip.fusion.delete",
      "actionId": "cutagent.action.clip.fusion.delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.fusion.export",
    {
      "commandId": "clip.fusion.export",
      "actionId": "cutagent.action.clip.fusion.export",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.fusion.import",
    {
      "commandId": "clip.fusion.import",
      "actionId": "cutagent.action.clip.fusion.import",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.fusion.list",
    {
      "commandId": "clip.fusion.list",
      "actionId": "cutagent.action.clip.fusion.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "clip.fusion.load",
    {
      "commandId": "clip.fusion.load",
      "actionId": "cutagent.action.clip.fusion.load",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.fusion.tool_get",
    {
      "commandId": "clip.fusion.tool_get",
      "actionId": "cutagent.action.clip.fusion.tool_get",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "clip.fusion.tool_set",
    {
      "commandId": "clip.fusion.tool_set",
      "actionId": "cutagent.action.clip.fusion.tool_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.fusion.tools",
    {
      "commandId": "clip.fusion.tools",
      "actionId": "cutagent.action.clip.fusion.tools",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "clip.info",
    {
      "commandId": "clip.info",
      "actionId": "cutagent.action.clip.info",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "clip.keyframe.add",
    {
      "commandId": "clip.keyframe.add",
      "actionId": "cutagent.action.clip.keyframe.add",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.keyframe.delete",
    {
      "commandId": "clip.keyframe.delete",
      "actionId": "cutagent.action.clip.keyframe.delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.keyframe.get",
    {
      "commandId": "clip.keyframe.get",
      "actionId": "cutagent.action.clip.keyframe.get",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "clip.keyframe.set_interpolation",
    {
      "commandId": "clip.keyframe.set_interpolation",
      "actionId": "cutagent.action.clip.keyframe.set_interpolation",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.link",
    {
      "commandId": "clip.link",
      "actionId": "cutagent.action.clip.link",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.linked.list",
    {
      "commandId": "clip.linked.list",
      "actionId": "cutagent.action.clip.linked.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "clip.list",
    {
      "commandId": "clip.list",
      "actionId": "cutagent.action.clip.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "clip.magic_mask",
    {
      "commandId": "clip.magic_mask",
      "actionId": "cutagent.action.clip.magic_mask",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "clip.marker.add",
    {
      "commandId": "clip.marker.add",
      "actionId": "cutagent.action.clip.marker.add",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.marker.custom_data",
    {
      "commandId": "clip.marker.custom_data",
      "actionId": "cutagent.action.clip.marker.custom_data",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.marker.delete",
    {
      "commandId": "clip.marker.delete",
      "actionId": "cutagent.action.clip.marker.delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.marker.delete_custom",
    {
      "commandId": "clip.marker.delete_custom",
      "actionId": "cutagent.action.clip.marker.delete_custom",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.marker.get_custom",
    {
      "commandId": "clip.marker.get_custom",
      "actionId": "cutagent.action.clip.marker.get_custom",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "clip.marker.list",
    {
      "commandId": "clip.marker.list",
      "actionId": "cutagent.action.clip.marker.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "clip.offset",
    {
      "commandId": "clip.offset",
      "actionId": "cutagent.action.clip.offset",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "clip.properties",
    {
      "commandId": "clip.properties",
      "actionId": "cutagent.action.clip.properties",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.rename",
    {
      "commandId": "clip.rename",
      "actionId": "cutagent.action.clip.rename",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.reset_node_colors",
    {
      "commandId": "clip.reset_node_colors",
      "actionId": "cutagent.action.clip.reset_node_colors",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.reverse",
    {
      "commandId": "clip.reverse",
      "actionId": "cutagent.action.clip.reverse",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.smart_reframe",
    {
      "commandId": "clip.smart_reframe",
      "actionId": "cutagent.action.clip.smart_reframe",
      "aliasOf": null,
      "operationClass": "long_running",
      "verificationCategory": "terminal_and_readback"
    }
  ],
  [
    "clip.source_audio_mapping",
    {
      "commandId": "clip.source_audio_mapping",
      "actionId": "cutagent.action.clip.source_audio_mapping",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "clip.source_range",
    {
      "commandId": "clip.source_range",
      "actionId": "cutagent.action.clip.source_range",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "clip.speed",
    {
      "commandId": "clip.speed",
      "actionId": "cutagent.action.clip.speed",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.speed_ramp",
    {
      "commandId": "clip.speed_ramp",
      "actionId": "cutagent.action.clip.speed_ramp",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.stabilize",
    {
      "commandId": "clip.stabilize",
      "actionId": "cutagent.action.clip.stabilize",
      "aliasOf": null,
      "operationClass": "long_running",
      "verificationCategory": "terminal_and_readback"
    }
  ],
  [
    "clip.stereo_values",
    {
      "commandId": "clip.stereo_values",
      "actionId": "cutagent.action.clip.stereo_values",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "clip.take.add",
    {
      "commandId": "clip.take.add",
      "actionId": "cutagent.action.clip.take.add",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.take.delete",
    {
      "commandId": "clip.take.delete",
      "actionId": "cutagent.action.clip.take.delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.take.finalize",
    {
      "commandId": "clip.take.finalize",
      "actionId": "cutagent.action.clip.take.finalize",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.take.list",
    {
      "commandId": "clip.take.list",
      "actionId": "cutagent.action.clip.take.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "clip.take.select",
    {
      "commandId": "clip.take.select",
      "actionId": "cutagent.action.clip.take.select",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.track_info",
    {
      "commandId": "clip.track_info",
      "actionId": "cutagent.action.clip.track_info",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "clip.transform",
    {
      "commandId": "clip.transform",
      "actionId": "cutagent.action.clip.transform",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.unlink",
    {
      "commandId": "clip.unlink",
      "actionId": "cutagent.action.clip.unlink",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.update_sidecar",
    {
      "commandId": "clip.update_sidecar",
      "actionId": "cutagent.action.clip.update_sidecar",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "clip.voice_isolation",
    {
      "commandId": "clip.voice_isolation",
      "actionId": "cutagent.action.clip.voice_isolation",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "codec.build",
    {
      "commandId": "codec.build",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "codec.install",
    {
      "commandId": "codec.install",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "codec.list_installed",
    {
      "commandId": "codec.list_installed",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "codec.package",
    {
      "commandId": "codec.package",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "codec.sample.copy",
    {
      "commandId": "codec.sample.copy",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "codec.scaffold",
    {
      "commandId": "codec.scaffold",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "codec.uninstall",
    {
      "commandId": "codec.uninstall",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "codec.validate",
    {
      "commandId": "codec.validate",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "color.arri_cdl_lut",
    {
      "commandId": "color.arri_cdl_lut",
      "actionId": "cutagent.action.color.arri_cdl_lut",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.auto_color",
    {
      "commandId": "color.auto_color",
      "actionId": "cutagent.action.color.auto_color",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.cdl",
    {
      "commandId": "color.cdl",
      "actionId": "cutagent.action.color.cdl",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.comp.doctor",
    {
      "commandId": "color.comp.doctor",
      "actionId": "cutagent.action.color.comp.doctor",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.comp.export",
    {
      "commandId": "color.comp.export",
      "actionId": "cutagent.action.color.comp.export",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.comp.flatten",
    {
      "commandId": "color.comp.flatten",
      "actionId": "cutagent.action.color.comp.flatten",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.comp.repair",
    {
      "commandId": "color.comp.repair",
      "actionId": "cutagent.action.color.comp.repair",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.curves",
    {
      "commandId": "color.curves",
      "actionId": "cutagent.action.color.curves",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.export_lut",
    {
      "commandId": "color.export_lut",
      "actionId": "cutagent.action.color.export_lut",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.fx.apply",
    {
      "commandId": "color.fx.apply",
      "actionId": "cutagent.action.color.fx.apply",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "terminal_and_readback"
    }
  ],
  [
    "color.fx.list",
    {
      "commandId": "color.fx.list",
      "actionId": "cutagent.action.color.fx.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.gallery.album.create",
    {
      "commandId": "color.gallery.album.create",
      "actionId": "cutagent.action.color.gallery.album.create",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.gallery.album.current",
    {
      "commandId": "color.gallery.album.current",
      "actionId": "cutagent.action.color.gallery.album.current",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.gallery.album.list",
    {
      "commandId": "color.gallery.album.list",
      "actionId": "cutagent.action.color.gallery.album.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.gallery.album.rename",
    {
      "commandId": "color.gallery.album.rename",
      "actionId": "cutagent.action.color.gallery.album.rename",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.gallery.album.switch",
    {
      "commandId": "color.gallery.album.switch",
      "actionId": "cutagent.action.color.gallery.album.switch",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.gallery.still.apply",
    {
      "commandId": "color.gallery.still.apply",
      "actionId": "cutagent.action.color.gallery.still.apply",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.gallery.still.delete",
    {
      "commandId": "color.gallery.still.delete",
      "actionId": "cutagent.action.color.gallery.still.delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.gallery.still.export",
    {
      "commandId": "color.gallery.still.export",
      "actionId": "cutagent.action.color.gallery.still.export",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.gallery.still.grab",
    {
      "commandId": "color.gallery.still.grab",
      "actionId": "cutagent.action.color.gallery.still.grab",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.gallery.still.import",
    {
      "commandId": "color.gallery.still.import",
      "actionId": "cutagent.action.color.gallery.still.import",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.gallery.still.label",
    {
      "commandId": "color.gallery.still.label",
      "actionId": "cutagent.action.color.gallery.still.label",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.gallery.still.list",
    {
      "commandId": "color.gallery.still.list",
      "actionId": "cutagent.action.color.gallery.still.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.grade_apply",
    {
      "commandId": "color.grade_apply",
      "actionId": "cutagent.action.color.grade_apply",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.grade_copy",
    {
      "commandId": "color.grade_copy",
      "actionId": "cutagent.action.color.grade_copy",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.graph.inspect",
    {
      "commandId": "color.graph.inspect",
      "actionId": "cutagent.action.color.graph.inspect",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.graph.normalize",
    {
      "commandId": "color.graph.normalize",
      "actionId": "cutagent.action.color.graph.normalize",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.graph.validate",
    {
      "commandId": "color.graph.validate",
      "actionId": "cutagent.action.color.graph.validate",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.group.add",
    {
      "commandId": "color.group.add",
      "actionId": "cutagent.action.color.group.add",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.group.assign",
    {
      "commandId": "color.group.assign",
      "actionId": "cutagent.action.color.group.assign",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.group.clips",
    {
      "commandId": "color.group.clips",
      "actionId": "cutagent.action.color.group.clips",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.group.delete",
    {
      "commandId": "color.group.delete",
      "actionId": "cutagent.action.color.group.delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.group.graph",
    {
      "commandId": "color.group.graph",
      "actionId": "cutagent.action.color.group.graph",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.group.list",
    {
      "commandId": "color.group.list",
      "actionId": "cutagent.action.color.group.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.group.remove",
    {
      "commandId": "color.group.remove",
      "actionId": "cutagent.action.color.group.remove",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.group.rename",
    {
      "commandId": "color.group.rename",
      "actionId": "cutagent.action.color.group.rename",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.huesat",
    {
      "commandId": "color.huesat",
      "actionId": "cutagent.action.color.huesat",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.inspect",
    {
      "commandId": "color.inspect",
      "actionId": "cutagent.action.color.inspect",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.lut",
    {
      "commandId": "color.lut",
      "actionId": "cutagent.action.color.lut",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.lut_refresh",
    {
      "commandId": "color.lut_refresh",
      "actionId": "cutagent.action.color.lut_refresh",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.mask.inspect",
    {
      "commandId": "color.mask.inspect",
      "actionId": "cutagent.action.color.mask.inspect",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.node.cache",
    {
      "commandId": "color.node.cache",
      "actionId": "cutagent.action.color.node.cache",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.node.disable",
    {
      "commandId": "color.node.disable",
      "actionId": "cutagent.action.color.node.disable",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.node.enable",
    {
      "commandId": "color.node.enable",
      "actionId": "cutagent.action.color.node.enable",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.node.graph",
    {
      "commandId": "color.node.graph",
      "actionId": "cutagent.action.color.node.graph",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.node.label_get",
    {
      "commandId": "color.node.label_get",
      "actionId": "cutagent.action.color.node.label_get",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.node.label_set",
    {
      "commandId": "color.node.label_set",
      "actionId": "cutagent.action.color.node.label_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.node.list",
    {
      "commandId": "color.node.list",
      "actionId": "cutagent.action.color.node.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.node.lut_get",
    {
      "commandId": "color.node.lut_get",
      "actionId": "cutagent.action.color.node.lut_get",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.node.lut_set",
    {
      "commandId": "color.node.lut_set",
      "actionId": "cutagent.action.color.node.lut_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.node.reset",
    {
      "commandId": "color.node.reset",
      "actionId": "cutagent.action.color.node.reset",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.node.tools",
    {
      "commandId": "color.node.tools",
      "actionId": "cutagent.action.color.node.tools",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.nodes",
    {
      "commandId": "color.nodes",
      "actionId": "cutagent.action.color.nodes",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.page.alpha_output_connect",
    {
      "commandId": "color.page.alpha_output_connect",
      "actionId": "cutagent.action.color.page.alpha_output_connect",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.auto_color_ai",
    {
      "commandId": "color.page.auto_color_ai",
      "actionId": "cutagent.action.color.page.auto_color_ai",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.bleach_bypass_intensity_set",
    {
      "commandId": "color.page.bleach_bypass_intensity_set",
      "actionId": "cutagent.action.color.page.bleach_bypass_intensity_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.bleach_bypass_set",
    {
      "commandId": "color.page.bleach_bypass_set",
      "actionId": "cutagent.action.color.page.bleach_bypass_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.cat_set",
    {
      "commandId": "color.page.cat_set",
      "actionId": "cutagent.action.color.page.cat_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.color_slice_set",
    {
      "commandId": "color.page.color_slice_set",
      "actionId": "cutagent.action.color.page.color_slice_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.cst_set",
    {
      "commandId": "color.page.cst_set",
      "actionId": "cutagent.action.color.page.cst_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.curve_points_set",
    {
      "commandId": "color.page.curve_points_set",
      "actionId": "cutagent.action.color.page.curve_points_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.curve_set",
    {
      "commandId": "color.page.curve_set",
      "actionId": "cutagent.action.color.page.curve_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.curve_spline_set",
    {
      "commandId": "color.page.curve_spline_set",
      "actionId": "cutagent.action.color.page.curve_spline_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.dctl_apply",
    {
      "commandId": "color.page.dctl_apply",
      "actionId": "cutagent.action.color.page.dctl_apply",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.dctl_remove",
    {
      "commandId": "color.page.dctl_remove",
      "actionId": "cutagent.action.color.page.dctl_remove",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.false_color_read",
    {
      "commandId": "color.page.false_color_read",
      "actionId": "cutagent.action.color.page.false_color_read",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.hdr_detail_set",
    {
      "commandId": "color.page.hdr_detail_set",
      "actionId": "cutagent.action.color.page.hdr_detail_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.hdr_global_set",
    {
      "commandId": "color.page.hdr_global_set",
      "actionId": "cutagent.action.color.page.hdr_global_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.hdr_zone_set",
    {
      "commandId": "color.page.hdr_zone_set",
      "actionId": "cutagent.action.color.page.hdr_zone_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.hsv_node_set",
    {
      "commandId": "color.page.hsv_node_set",
      "actionId": "cutagent.action.color.page.hsv_node_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.hue_curve_set",
    {
      "commandId": "color.page.hue_curve_set",
      "actionId": "cutagent.action.color.page.hue_curve_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.hue_curve_spline_set",
    {
      "commandId": "color.page.hue_curve_spline_set",
      "actionId": "cutagent.action.color.page.hue_curve_spline_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.key_output_set",
    {
      "commandId": "color.page.key_output_set",
      "actionId": "cutagent.action.color.page.key_output_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.layer_mixer_set",
    {
      "commandId": "color.page.layer_mixer_set",
      "actionId": "cutagent.action.color.page.layer_mixer_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.lut_library_import",
    {
      "commandId": "color.page.lut_library_import",
      "actionId": "cutagent.action.color.page.lut_library_import",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.magic_mask",
    {
      "commandId": "color.page.magic_mask",
      "actionId": "cutagent.action.color.page.magic_mask",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.page.magic_mask_draw_stroke",
    {
      "commandId": "color.page.magic_mask_draw_stroke",
      "actionId": "cutagent.action.color.page.magic_mask_draw_stroke",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.magic_mask_refine",
    {
      "commandId": "color.page.magic_mask_refine",
      "actionId": "cutagent.action.color.page.magic_mask_refine",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.node_add",
    {
      "commandId": "color.page.node_add",
      "actionId": "cutagent.action.color.page.node_add",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.node_add_topology",
    {
      "commandId": "color.page.node_add_topology",
      "actionId": "cutagent.action.color.page.node_add_topology",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.node_cleanup",
    {
      "commandId": "color.page.node_cleanup",
      "actionId": "cutagent.action.color.page.node_cleanup",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.node_cleanup_general",
    {
      "commandId": "color.page.node_cleanup_general",
      "actionId": "cutagent.action.color.page.node_cleanup_general",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.ofx_glow_set",
    {
      "commandId": "color.page.ofx_glow_set",
      "actionId": "cutagent.action.color.page.ofx_glow_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.param_delete",
    {
      "commandId": "color.page.param_delete",
      "actionId": "cutagent.action.color.page.param_delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.power_window_circle",
    {
      "commandId": "color.page.power_window_circle",
      "actionId": "cutagent.action.color.page.power_window_circle",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.power_window_circle_detail",
    {
      "commandId": "color.page.power_window_circle_detail",
      "actionId": "cutagent.action.color.page.power_window_circle_detail",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.power_window_curve",
    {
      "commandId": "color.page.power_window_curve",
      "actionId": "cutagent.action.color.page.power_window_curve",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.power_window_gradient",
    {
      "commandId": "color.page.power_window_gradient",
      "actionId": "cutagent.action.color.page.power_window_gradient",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.power_window_gradient_transform",
    {
      "commandId": "color.page.power_window_gradient_transform",
      "actionId": "cutagent.action.color.page.power_window_gradient_transform",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.power_window_gui_set",
    {
      "commandId": "color.page.power_window_gui_set",
      "actionId": "cutagent.action.color.page.power_window_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.power_window_linear",
    {
      "commandId": "color.page.power_window_linear",
      "actionId": "cutagent.action.color.page.power_window_linear",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.power_window_overlay_transform",
    {
      "commandId": "color.page.power_window_overlay_transform",
      "actionId": "cutagent.action.color.page.power_window_overlay_transform",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.power_window_polygon",
    {
      "commandId": "color.page.power_window_polygon",
      "actionId": "cutagent.action.color.page.power_window_polygon",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.power_window_rectangle",
    {
      "commandId": "color.page.power_window_rectangle",
      "actionId": "cutagent.action.color.page.power_window_rectangle",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.power_window_track",
    {
      "commandId": "color.page.power_window_track",
      "actionId": "cutagent.action.color.page.power_window_track",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.primary_gui_set",
    {
      "commandId": "color.page.primary_gui_set",
      "actionId": "cutagent.action.color.page.primary_extended_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.primary_set",
    {
      "commandId": "color.page.primary_set",
      "actionId": "cutagent.action.color.page.primary_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.qualifier_gui_hsl_set",
    {
      "commandId": "color.page.qualifier_gui_hsl_set",
      "actionId": "cutagent.action.color.page.qualifier_hsl_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.qualifier_gui_matte_set",
    {
      "commandId": "color.page.qualifier_gui_matte_set",
      "actionId": "cutagent.action.color.page.qualifier_matte_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.qualifier_matte_refine",
    {
      "commandId": "color.page.qualifier_matte_refine",
      "actionId": "cutagent.action.color.page.qualifier_matte_refine",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.qualifier_panel_probe",
    {
      "commandId": "color.page.qualifier_panel_probe",
      "actionId": "cutagent.action.color.page.qualifier_panel_probe",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.page.qualifier_sample",
    {
      "commandId": "color.page.qualifier_sample",
      "actionId": "cutagent.action.color.page.qualifier_sample",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.read",
    {
      "commandId": "color.page.read",
      "actionId": "cutagent.action.color.page.read",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.page.resolvefx_add",
    {
      "commandId": "color.page.resolvefx_add",
      "actionId": "cutagent.action.color.page.resolvefx_add",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.resolvefx_list",
    {
      "commandId": "color.page.resolvefx_list",
      "actionId": "cutagent.action.color.page.resolvefx_list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.page.resolvefx_param_discover",
    {
      "commandId": "color.page.resolvefx_param_discover",
      "actionId": "cutagent.action.color.page.resolvefx_param_discover",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.page.resolvefx_param_list",
    {
      "commandId": "color.page.resolvefx_param_list",
      "actionId": "cutagent.action.color.page.resolvefx_param_list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.page.resolvefx_param_set",
    {
      "commandId": "color.page.resolvefx_param_set",
      "actionId": "cutagent.action.color.page.resolvefx_param_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.resolvefx_remove",
    {
      "commandId": "color.page.resolvefx_remove",
      "actionId": "cutagent.action.color.page.resolvefx_remove",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.rgb_mixer_set",
    {
      "commandId": "color.page.rgb_mixer_set",
      "actionId": "cutagent.action.color.page.rgb_mixer_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.sat_curve_set",
    {
      "commandId": "color.page.sat_curve_set",
      "actionId": "cutagent.action.color.page.sat_curve_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.sat_curve_spline_set",
    {
      "commandId": "color.page.sat_curve_spline_set",
      "actionId": "cutagent.action.color.page.sat_curve_spline_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.scope_read",
    {
      "commandId": "color.page.scope_read",
      "actionId": "cutagent.action.color.page.scope_read",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.scope_set",
    {
      "commandId": "color.page.scope_set",
      "actionId": "cutagent.action.color.page.scope_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.sharpen_set",
    {
      "commandId": "color.page.sharpen_set",
      "actionId": "cutagent.action.color.page.sharpen_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.shot_match_analyze",
    {
      "commandId": "color.page.shot_match_analyze",
      "actionId": "cutagent.action.color.page.shot_match_analyze",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.shot_match_apply",
    {
      "commandId": "color.page.shot_match_apply",
      "actionId": "cutagent.action.color.page.shot_match_apply",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.sky_isolation",
    {
      "commandId": "color.page.sky_isolation",
      "actionId": "cutagent.action.color.page.sky_isolation",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.snapshot",
    {
      "commandId": "color.page.snapshot",
      "actionId": "cutagent.action.color.page.snapshot",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.page.softening_set",
    {
      "commandId": "color.page.softening_set",
      "actionId": "cutagent.action.color.page.softening_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.split_tone_set",
    {
      "commandId": "color.page.split_tone_set",
      "actionId": "cutagent.action.color.page.split_tone_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.still_match",
    {
      "commandId": "color.page.still_match",
      "actionId": "cutagent.action.color.page.still_match",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.viewer_before_after",
    {
      "commandId": "color.page.viewer_before_after",
      "actionId": "cutagent.action.color.page.viewer_before_after",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.warper_set",
    {
      "commandId": "color.page.warper_set",
      "actionId": "cutagent.action.color.page.warper_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.wheel_set",
    {
      "commandId": "color.page.wheel_set",
      "actionId": "cutagent.action.color.page.wheel_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.page.white_balance_picker",
    {
      "commandId": "color.page.white_balance_picker",
      "actionId": "cutagent.action.color.page.white_balance_picker",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.power_grade.album.create",
    {
      "commandId": "color.power_grade.album.create",
      "actionId": "cutagent.action.color.power_grade.album.create",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.power_grade.apply",
    {
      "commandId": "color.power_grade.apply",
      "actionId": "cutagent.action.color.power_grade.apply",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.power_grade.list",
    {
      "commandId": "color.power_grade.list",
      "actionId": "cutagent.action.color.power_grade.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.power_grade.template_apply",
    {
      "commandId": "color.power_grade.template_apply",
      "actionId": "cutagent.action.color.power_grade.template_apply",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.primary.get",
    {
      "commandId": "color.primary.get",
      "actionId": "cutagent.action.color.primary.get",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.primary.set",
    {
      "commandId": "color.primary.set",
      "actionId": "cutagent.action.color.primary.set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.qualifier.attach",
    {
      "commandId": "color.qualifier.attach",
      "actionId": "cutagent.action.color.qualifier.attach",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.qualifier.chroma",
    {
      "commandId": "color.qualifier.chroma",
      "actionId": "cutagent.action.color.qualifier.chroma",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.qualifier.detach",
    {
      "commandId": "color.qualifier.detach",
      "actionId": "cutagent.action.color.qualifier.detach",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.qualifier.list",
    {
      "commandId": "color.qualifier.list",
      "actionId": "cutagent.action.color.qualifier.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.reset_fusion",
    {
      "commandId": "color.reset_fusion",
      "actionId": "cutagent.action.color.reset_fusion",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.secondary.create",
    {
      "commandId": "color.secondary.create",
      "actionId": "cutagent.action.color.secondary.create",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.secondary.isolate_green_screen",
    {
      "commandId": "color.secondary.isolate_green_screen",
      "actionId": "cutagent.action.color.secondary.isolate_green_screen",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.secondary.subject_isolation",
    {
      "commandId": "color.secondary.subject_isolation",
      "actionId": "cutagent.action.color.secondary.subject_isolation",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.secondary.tracked_window",
    {
      "commandId": "color.secondary.tracked_window",
      "actionId": "cutagent.action.color.secondary.tracked_window",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.source_grade.apply_cdl",
    {
      "commandId": "color.source_grade.apply_cdl",
      "actionId": "cutagent.action.color.source_grade.apply_cdl",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.source_grade.plan",
    {
      "commandId": "color.source_grade.plan",
      "actionId": "cutagent.action.color.source_grade.plan",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.source_grade.prepare_remote",
    {
      "commandId": "color.source_grade.prepare_remote",
      "actionId": "cutagent.action.color.source_grade.prepare_remote",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.still.grab_all",
    {
      "commandId": "color.still.grab_all",
      "actionId": "cutagent.action.color.still.grab_all",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.thumbnail",
    {
      "commandId": "color.thumbnail",
      "actionId": "cutagent.action.color.thumbnail",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.tracker.add",
    {
      "commandId": "color.tracker.add",
      "actionId": "cutagent.action.color.tracker.add",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.tracker.attach_qualifier",
    {
      "commandId": "color.tracker.attach_qualifier",
      "actionId": "cutagent.action.color.tracker.attach_qualifier",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.tracker.attach_window",
    {
      "commandId": "color.tracker.attach_window",
      "actionId": "cutagent.action.color.tracker.attach_window",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.tracker.list",
    {
      "commandId": "color.tracker.list",
      "actionId": "cutagent.action.color.tracker.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.tracker.set_target",
    {
      "commandId": "color.tracker.set_target",
      "actionId": "cutagent.action.color.tracker.set_target",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.tracker.track_forward",
    {
      "commandId": "color.tracker.track_forward",
      "actionId": "cutagent.action.color.tracker.track_forward",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.tracker.track_reverse",
    {
      "commandId": "color.tracker.track_reverse",
      "actionId": "cutagent.action.color.tracker.track_reverse",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.version.activate",
    {
      "commandId": "color.version.activate",
      "actionId": "cutagent.action.color.version.activate",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.version.add",
    {
      "commandId": "color.version.add",
      "actionId": "cutagent.action.color.version.add",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.version.delete",
    {
      "commandId": "color.version.delete",
      "actionId": "cutagent.action.color.version.delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.version.duplicate",
    {
      "commandId": "color.version.duplicate",
      "actionId": "cutagent.action.color.version.duplicate",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.version.list",
    {
      "commandId": "color.version.list",
      "actionId": "cutagent.action.color.version.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.version.load",
    {
      "commandId": "color.version.load",
      "actionId": "cutagent.action.color.version.load",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.version.rollback",
    {
      "commandId": "color.version.rollback",
      "actionId": "cutagent.action.color.version.rollback",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.wheels.set",
    {
      "commandId": "color.wheels.set",
      "actionId": "cutagent.action.color.wheels.set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.window.attach",
    {
      "commandId": "color.window.attach",
      "actionId": "cutagent.action.color.window.attach",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.window.detach",
    {
      "commandId": "color.window.detach",
      "actionId": "cutagent.action.color.window.detach",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.window.ellipse",
    {
      "commandId": "color.window.ellipse",
      "actionId": "cutagent.action.color.window.ellipse",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.window.list",
    {
      "commandId": "color.window.list",
      "actionId": "cutagent.action.color.window.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "color.window.polygon",
    {
      "commandId": "color.window.polygon",
      "actionId": "cutagent.action.color.window.polygon",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.window.rectangle",
    {
      "commandId": "color.window.rectangle",
      "actionId": "cutagent.action.color.window.rectangle",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "color.window.reorder",
    {
      "commandId": "color.window.reorder",
      "actionId": "cutagent.action.color.window.reorder",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "connect",
    {
      "commandId": "connect",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "context",
    {
      "commandId": "context",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "dctl.apply",
    {
      "commandId": "dctl.apply",
      "actionId": "cutagent.action.dctl.apply",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "dctl.encrypt",
    {
      "commandId": "dctl.encrypt",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "dctl.install",
    {
      "commandId": "dctl.install",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "dctl.list",
    {
      "commandId": "dctl.list",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "dctl.scaffold",
    {
      "commandId": "dctl.scaffold",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "dctl.validate",
    {
      "commandId": "dctl.validate",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "dctl.validate_source",
    {
      "commandId": "dctl.validate_source",
      "actionId": "cutagent.action.dctl.validate_source",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "developer.capability.audit",
    {
      "commandId": "developer.capability.audit",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "developer.capability.diff",
    {
      "commandId": "developer.capability.diff",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "developer.docs.list",
    {
      "commandId": "developer.docs.list",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "developer.docs.open",
    {
      "commandId": "developer.docs.open",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "developer.doctor",
    {
      "commandId": "developer.doctor",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "developer.examples.copy",
    {
      "commandId": "developer.examples.copy",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "developer.examples.list",
    {
      "commandId": "developer.examples.list",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "developer.sdk.doctor",
    {
      "commandId": "developer.sdk.doctor",
      "actionId": null,
      "aliasOf": "developer.doctor",
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "developer.sdk_doctor",
    {
      "commandId": "developer.sdk_doctor",
      "actionId": null,
      "aliasOf": "developer.doctor",
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "doctor",
    {
      "commandId": "doctor",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "edit.auto_subtitle",
    {
      "commandId": "edit.auto_subtitle",
      "actionId": "cutagent.action.edit.auto_subtitle",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "edit.blade",
    {
      "commandId": "edit.blade",
      "actionId": "cutagent.action.edit.blade",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "edit.camera_pip",
    {
      "commandId": "edit.camera_pip",
      "actionId": "cutagent.action.edit.camera_pip",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "edit.delete_through_edit",
    {
      "commandId": "edit.delete_through_edit",
      "actionId": "cutagent.action.edit.delete_through_edit",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "edit.from_edl",
    {
      "commandId": "edit.from_edl",
      "actionId": "cutagent.action.edit.from_edl",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "edit.fx.add",
    {
      "commandId": "edit.fx.add",
      "actionId": "cutagent.action.edit.fx.add",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "terminal_and_readback"
    }
  ],
  [
    "edit.insert",
    {
      "commandId": "edit.insert",
      "actionId": "cutagent.action.edit.insert",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "edit.overwrite",
    {
      "commandId": "edit.overwrite",
      "actionId": "cutagent.action.edit.overwrite",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "edit.remove",
    {
      "commandId": "edit.remove",
      "actionId": "cutagent.action.edit.remove",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "edit.remove_range",
    {
      "commandId": "edit.remove_range",
      "actionId": "cutagent.action.edit.remove_range",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "edit.ripple_delete",
    {
      "commandId": "edit.ripple_delete",
      "actionId": "cutagent.action.edit.ripple_delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "edit.ripple_delete_selected",
    {
      "commandId": "edit.ripple_delete_selected",
      "actionId": "cutagent.action.edit.ripple_delete_selected",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "edit.scene_detect",
    {
      "commandId": "edit.scene_detect",
      "actionId": "cutagent.action.edit.scene_detect",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "edit.slide_selected",
    {
      "commandId": "edit.slide_selected",
      "actionId": "cutagent.action.edit.slide_selected",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "edit.slip_selected",
    {
      "commandId": "edit.slip_selected",
      "actionId": "cutagent.action.edit.slip_selected",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "edit.social_crop",
    {
      "commandId": "edit.social_crop",
      "actionId": "cutagent.action.edit.social_crop",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "edit.split",
    {
      "commandId": "edit.split",
      "actionId": "cutagent.action.edit.split",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "edit.transition.add",
    {
      "commandId": "edit.transition.add",
      "actionId": "cutagent.action.edit.transition.add",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "edit.transition.batch",
    {
      "commandId": "edit.transition.batch",
      "actionId": "cutagent.action.edit.transition.batch",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "edit.trim",
    {
      "commandId": "edit.trim",
      "actionId": "cutagent.action.edit.trim",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "embedded.install",
    {
      "commandId": "embedded.install",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "embedded.ping",
    {
      "commandId": "embedded.ping",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "embedded.start_server",
    {
      "commandId": "embedded.start_server",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "embedded.status",
    {
      "commandId": "embedded.status",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "embedded.uninstall",
    {
      "commandId": "embedded.uninstall",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fairlight.add",
    {
      "commandId": "fairlight.add",
      "actionId": "cutagent.action.fairlight.add",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.adr.cue_list",
    {
      "commandId": "fairlight.adr.cue_list",
      "actionId": "cutagent.action.fairlight.adr.cue_list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fairlight.adr.info",
    {
      "commandId": "fairlight.adr.info",
      "actionId": "cutagent.action.fairlight.adr.info",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.adr.record",
    {
      "commandId": "fairlight.adr.record",
      "actionId": "cutagent.action.fairlight.adr.record",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fairlight.ai.dialogue_leveler",
    {
      "commandId": "fairlight.ai.dialogue_leveler",
      "actionId": "cutagent.action.fairlight.ai.dialogue_leveler",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.ai.music_remixer",
    {
      "commandId": "fairlight.ai.music_remixer",
      "actionId": "cutagent.action.fairlight.ai.music_remixer",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.ai.read",
    {
      "commandId": "fairlight.ai.read",
      "actionId": "cutagent.action.fairlight.ai.read",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.ai.voice_isolation",
    {
      "commandId": "fairlight.ai.voice_isolation",
      "actionId": "cutagent.action.fairlight.ai.voice_isolation",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.api_notes",
    {
      "commandId": "fairlight.api_notes",
      "actionId": "cutagent.action.fairlight.api_notes",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.audio_gain.batch",
    {
      "commandId": "fairlight.audio_gain.batch",
      "actionId": "cutagent.action.fairlight.audio_gain.batch",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.audio_pan.batch",
    {
      "commandId": "fairlight.audio_pan.batch",
      "actionId": "cutagent.action.fairlight.audio_pan.batch",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.automation.list",
    {
      "commandId": "fairlight.automation.list",
      "actionId": "cutagent.action.fairlight.automation.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.automation.write",
    {
      "commandId": "fairlight.automation.write",
      "actionId": "cutagent.action.fairlight.automation.write",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.bounce.mix_to_track",
    {
      "commandId": "fairlight.bounce.mix_to_track",
      "actionId": "cutagent.action.fairlight.bounce.mix_to_track",
      "aliasOf": null,
      "operationClass": "long_running",
      "verificationCategory": "terminal_and_readback"
    }
  ],
  [
    "fairlight.bounce.track",
    {
      "commandId": "fairlight.bounce.track",
      "actionId": "cutagent.action.fairlight.bounce.track",
      "aliasOf": null,
      "operationClass": "long_running",
      "verificationCategory": "terminal_and_readback"
    }
  ],
  [
    "fairlight.bus.assign",
    {
      "commandId": "fairlight.bus.assign",
      "actionId": "cutagent.action.fairlight.bus.assign",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.bus.level",
    {
      "commandId": "fairlight.bus.level",
      "actionId": "cutagent.action.fairlight.bus.level",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.bus.list",
    {
      "commandId": "fairlight.bus.list",
      "actionId": "cutagent.action.fairlight.bus.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.channel_map.clip",
    {
      "commandId": "fairlight.channel_map.clip",
      "actionId": "cutagent.action.fairlight.channel_map.clip",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.channel_map.media",
    {
      "commandId": "fairlight.channel_map.media",
      "actionId": "cutagent.action.fairlight.channel_map.media",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.channel_map.set",
    {
      "commandId": "fairlight.channel_map.set",
      "actionId": "cutagent.action.fairlight.channel_map.set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.clip.delete",
    {
      "commandId": "fairlight.clip.delete",
      "actionId": "cutagent.action.fairlight.clip.delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.clip.info",
    {
      "commandId": "fairlight.clip.info",
      "actionId": "cutagent.action.fairlight.clip.info",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.clip.link",
    {
      "commandId": "fairlight.clip.link",
      "actionId": "cutagent.action.fairlight.clip.link",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.clip.linked.list",
    {
      "commandId": "fairlight.clip.linked.list",
      "actionId": "cutagent.action.fairlight.clip.linked.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.clip.move",
    {
      "commandId": "fairlight.clip.move",
      "actionId": "cutagent.action.fairlight.clip.move",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.clip.nudge",
    {
      "commandId": "fairlight.clip.nudge",
      "actionId": "cutagent.action.fairlight.clip.nudge",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.clip.slip",
    {
      "commandId": "fairlight.clip.slip",
      "actionId": "cutagent.action.fairlight.clip.slip",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.clip.source_range",
    {
      "commandId": "fairlight.clip.source_range",
      "actionId": "cutagent.action.fairlight.clip.source_range",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.clip.split",
    {
      "commandId": "fairlight.clip.split",
      "actionId": "cutagent.action.fairlight.clip.split",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.clip.track_info",
    {
      "commandId": "fairlight.clip.track_info",
      "actionId": "cutagent.action.fairlight.clip.track_info",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.clip.trim",
    {
      "commandId": "fairlight.clip.trim",
      "actionId": "cutagent.action.fairlight.clip.trim",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.clip.unlink",
    {
      "commandId": "fairlight.clip.unlink",
      "actionId": "cutagent.action.fairlight.clip.unlink",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.crossfade.batch",
    {
      "commandId": "fairlight.crossfade.batch",
      "actionId": "cutagent.action.fairlight.crossfade.batch",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.delete",
    {
      "commandId": "fairlight.delete",
      "actionId": "cutagent.action.fairlight.delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.dynamics.disable",
    {
      "commandId": "fairlight.dynamics.disable",
      "actionId": "cutagent.action.fairlight.dynamics.disable",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.dynamics.enable",
    {
      "commandId": "fairlight.dynamics.enable",
      "actionId": "cutagent.action.fairlight.dynamics.enable",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.dynamics.read",
    {
      "commandId": "fairlight.dynamics.read",
      "actionId": "cutagent.action.fairlight.dynamics.read",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.dynamics.set",
    {
      "commandId": "fairlight.dynamics.set",
      "actionId": "cutagent.action.fairlight.dynamics.set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.effect.add",
    {
      "commandId": "fairlight.effect.add",
      "actionId": "cutagent.action.fairlight.effect.add",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.effect.catalog",
    {
      "commandId": "fairlight.effect.catalog",
      "actionId": "cutagent.action.fairlight.effect.catalog",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.effect.list",
    {
      "commandId": "fairlight.effect.list",
      "actionId": "cutagent.action.fairlight.effect.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.effect.params",
    {
      "commandId": "fairlight.effect.params",
      "actionId": "cutagent.action.fairlight.effect.params",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.effect.plugin_catalog",
    {
      "commandId": "fairlight.effect.plugin_catalog",
      "actionId": "cutagent.action.fairlight.effect.plugin_catalog",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.effect.remove",
    {
      "commandId": "fairlight.effect.remove",
      "actionId": "cutagent.action.fairlight.effect.remove",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.effect.set_param",
    {
      "commandId": "fairlight.effect.set_param",
      "actionId": "cutagent.action.fairlight.effect.set_param",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.effect.slot_scan",
    {
      "commandId": "fairlight.effect.slot_scan",
      "actionId": "cutagent.action.fairlight.effect.slot_scan",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.elastic.enable",
    {
      "commandId": "fairlight.elastic.enable",
      "actionId": "cutagent.action.fairlight.elastic.enable",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.elastic.info",
    {
      "commandId": "fairlight.elastic.info",
      "actionId": "cutagent.action.fairlight.elastic.info",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.elastic.keyframe",
    {
      "commandId": "fairlight.elastic.keyframe",
      "actionId": "cutagent.action.fairlight.elastic.keyframe",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.ensure_stereo_tracks",
    {
      "commandId": "fairlight.ensure_stereo_tracks",
      "actionId": "cutagent.action.fairlight.ensure_stereo_tracks",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.ensure_tracks",
    {
      "commandId": "fairlight.ensure_tracks",
      "actionId": "cutagent.action.fairlight.ensure_tracks",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.eq.read",
    {
      "commandId": "fairlight.eq.read",
      "actionId": "cutagent.action.fairlight.eq.read",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.eq.set",
    {
      "commandId": "fairlight.eq.set",
      "actionId": "cutagent.action.fairlight.eq.set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.export.audio",
    {
      "commandId": "fairlight.export.audio",
      "actionId": "cutagent.action.fairlight.export.audio",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.external_process.list",
    {
      "commandId": "fairlight.external_process.list",
      "actionId": "cutagent.action.fairlight.external_process.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.external_process.run",
    {
      "commandId": "fairlight.external_process.run",
      "actionId": "cutagent.action.fairlight.external_process.run",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fairlight.fade_curve",
    {
      "commandId": "fairlight.fade_curve",
      "actionId": "cutagent.action.fairlight.fade_curve",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.fade_in.batch",
    {
      "commandId": "fairlight.fade_in.batch",
      "actionId": "cutagent.action.fairlight.fade_in.batch",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.fade_out.batch",
    {
      "commandId": "fairlight.fade_out.batch",
      "actionId": "cutagent.action.fairlight.fade_out.batch",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.group.assign",
    {
      "commandId": "fairlight.group.assign",
      "actionId": "cutagent.action.fairlight.group.assign",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fairlight.group.list",
    {
      "commandId": "fairlight.group.list",
      "actionId": "cutagent.action.fairlight.group.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.index.clips",
    {
      "commandId": "fairlight.index.clips",
      "actionId": "cutagent.action.fairlight.index.clips",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.index.markers",
    {
      "commandId": "fairlight.index.markers",
      "actionId": "cutagent.action.fairlight.index.markers",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.index.tracks",
    {
      "commandId": "fairlight.index.tracks",
      "actionId": "cutagent.action.fairlight.index.tracks",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.info",
    {
      "commandId": "fairlight.info",
      "actionId": "cutagent.action.fairlight.info",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.insert",
    {
      "commandId": "fairlight.insert",
      "actionId": "cutagent.action.fairlight.insert",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.io.info",
    {
      "commandId": "fairlight.io.info",
      "actionId": "cutagent.action.fairlight.io.info",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.io.patch",
    {
      "commandId": "fairlight.io.patch",
      "actionId": "cutagent.action.fairlight.io.patch",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fairlight.item_source.patch",
    {
      "commandId": "fairlight.item_source.patch",
      "actionId": "cutagent.action.fairlight.item_source.patch",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.items",
    {
      "commandId": "fairlight.items",
      "actionId": "cutagent.action.fairlight.items",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.lock",
    {
      "commandId": "fairlight.lock",
      "actionId": "cutagent.action.fairlight.lock",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.loudness.analyze",
    {
      "commandId": "fairlight.loudness.analyze",
      "actionId": "cutagent.action.fairlight.loudness.analyze",
      "aliasOf": null,
      "operationClass": "long_running",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fairlight.loudness.info",
    {
      "commandId": "fairlight.loudness.info",
      "actionId": "cutagent.action.fairlight.loudness.info",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.loudness.normalize",
    {
      "commandId": "fairlight.loudness.normalize",
      "actionId": "cutagent.action.fairlight.loudness.normalize",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fairlight.mixer.fader",
    {
      "commandId": "fairlight.mixer.fader",
      "actionId": "cutagent.action.fairlight.mixer.fader",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.mixer.meter",
    {
      "commandId": "fairlight.mixer.meter",
      "actionId": "cutagent.action.fairlight.mixer.meter",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fairlight.mixer.meter_settings",
    {
      "commandId": "fairlight.mixer.meter_settings",
      "actionId": "cutagent.action.fairlight.mixer.meter_settings",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.mixer.pan",
    {
      "commandId": "fairlight.mixer.pan",
      "actionId": "cutagent.action.fairlight.mixer.pan",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.mixer.read",
    {
      "commandId": "fairlight.mixer.read",
      "actionId": "cutagent.action.fairlight.mixer.read",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.monitor.info",
    {
      "commandId": "fairlight.monitor.info",
      "actionId": "cutagent.action.fairlight.monitor.info",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.monitor.level",
    {
      "commandId": "fairlight.monitor.level",
      "actionId": "cutagent.action.fairlight.monitor.level",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fairlight.monitor.mute",
    {
      "commandId": "fairlight.monitor.mute",
      "actionId": "cutagent.action.fairlight.monitor.mute",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fairlight.mute",
    {
      "commandId": "fairlight.mute",
      "actionId": "cutagent.action.fairlight.mute",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.preset.apply",
    {
      "commandId": "fairlight.preset.apply",
      "actionId": "cutagent.action.fairlight.preset.apply",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.preset.list",
    {
      "commandId": "fairlight.preset.list",
      "actionId": "cutagent.action.fairlight.preset.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.record.arm",
    {
      "commandId": "fairlight.record.arm",
      "actionId": "cutagent.action.fairlight.record.arm",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fairlight.record.info",
    {
      "commandId": "fairlight.record.info",
      "actionId": "cutagent.action.fairlight.record.info",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.record.start",
    {
      "commandId": "fairlight.record.start",
      "actionId": "cutagent.action.fairlight.record.start",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fairlight.record.stop",
    {
      "commandId": "fairlight.record.stop",
      "actionId": "cutagent.action.fairlight.record.stop",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fairlight.rename",
    {
      "commandId": "fairlight.rename",
      "actionId": "cutagent.action.fairlight.rename",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.send.list",
    {
      "commandId": "fairlight.send.list",
      "actionId": "cutagent.action.fairlight.send.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.send.set",
    {
      "commandId": "fairlight.send.set",
      "actionId": "cutagent.action.fairlight.send.set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fairlight.solo",
    {
      "commandId": "fairlight.solo",
      "actionId": "cutagent.action.fairlight.solo",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.solo_restore",
    {
      "commandId": "fairlight.solo_restore",
      "actionId": "cutagent.action.fairlight.solo_restore",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.sound_library.audition",
    {
      "commandId": "fairlight.sound_library.audition",
      "actionId": "cutagent.action.fairlight.sound_library.audition",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fairlight.sound_library.delete",
    {
      "commandId": "fairlight.sound_library.delete",
      "actionId": "cutagent.action.fairlight.sound_library.delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.sound_library.index_file",
    {
      "commandId": "fairlight.sound_library.index_file",
      "actionId": "cutagent.action.fairlight.sound_library.index_file",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.sound_library.index_folder",
    {
      "commandId": "fairlight.sound_library.index_folder",
      "actionId": "cutagent.action.fairlight.sound_library.index_folder",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.sound_library.insert",
    {
      "commandId": "fairlight.sound_library.insert",
      "actionId": "cutagent.action.fairlight.sound_library.insert",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.sound_library.list",
    {
      "commandId": "fairlight.sound_library.list",
      "actionId": "cutagent.action.fairlight.sound_library.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.sound_library.preview",
    {
      "commandId": "fairlight.sound_library.preview",
      "actionId": null,
      "aliasOf": "fairlight.sound_library.audition",
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fairlight.sound_library.search",
    {
      "commandId": "fairlight.sound_library.search",
      "actionId": "cutagent.action.fairlight.sound_library.search",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.sound_library.source_list",
    {
      "commandId": "fairlight.sound_library.source_list",
      "actionId": "cutagent.action.fairlight.sound_library.source_list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.sound_library.source_rebuild",
    {
      "commandId": "fairlight.sound_library.source_rebuild",
      "actionId": "cutagent.action.fairlight.sound_library.source_rebuild",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.sound_library.source_remove",
    {
      "commandId": "fairlight.sound_library.source_remove",
      "actionId": "cutagent.action.fairlight.sound_library.source_remove",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.track.duplicate",
    {
      "commandId": "fairlight.track.duplicate",
      "actionId": "cutagent.action.fairlight.track.duplicate",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.track.folder",
    {
      "commandId": "fairlight.track.folder",
      "actionId": "cutagent.action.fairlight.track.folder",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fairlight.track.height",
    {
      "commandId": "fairlight.track.height",
      "actionId": "cutagent.action.fairlight.track.height",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.track.hide",
    {
      "commandId": "fairlight.track.hide",
      "actionId": "cutagent.action.fairlight.track.hide",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fairlight.track.input_monitor",
    {
      "commandId": "fairlight.track.input_monitor",
      "actionId": "cutagent.action.fairlight.track.input_monitor",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fairlight.track.show",
    {
      "commandId": "fairlight.track.show",
      "actionId": "cutagent.action.fairlight.track.show",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fairlight.track_color",
    {
      "commandId": "fairlight.track_color",
      "actionId": "cutagent.action.fairlight.track_color",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.track_format.set",
    {
      "commandId": "fairlight.track_format.set",
      "actionId": "cutagent.action.fairlight.track_format.set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.track_order.move",
    {
      "commandId": "fairlight.track_order.move",
      "actionId": "cutagent.action.fairlight.track_order.move",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.tracks",
    {
      "commandId": "fairlight.tracks",
      "actionId": "cutagent.action.fairlight.tracks",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.transition.add",
    {
      "commandId": "fairlight.transition.add",
      "actionId": "cutagent.action.fairlight.transition.add",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.unlock",
    {
      "commandId": "fairlight.unlock",
      "actionId": "cutagent.action.fairlight.unlock",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.unmute",
    {
      "commandId": "fairlight.unmute",
      "actionId": "cutagent.action.fairlight.unmute",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.vca.assign",
    {
      "commandId": "fairlight.vca.assign",
      "actionId": "cutagent.action.fairlight.vca.assign",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fairlight.vca.list",
    {
      "commandId": "fairlight.vca.list",
      "actionId": "cutagent.action.fairlight.vca.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.voice_isolation.get",
    {
      "commandId": "fairlight.voice_isolation.get",
      "actionId": "cutagent.action.fairlight.voice_isolation.get",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.voice_isolation.set",
    {
      "commandId": "fairlight.voice_isolation.set",
      "actionId": "cutagent.action.fairlight.voice_isolation.set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fairlight.waveform.info",
    {
      "commandId": "fairlight.waveform.info",
      "actionId": "cutagent.action.fairlight.waveform.info",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fairlight.waveform.repair_click",
    {
      "commandId": "fairlight.waveform.repair_click",
      "actionId": "cutagent.action.fairlight.waveform.repair_click",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fuse.examples.install",
    {
      "commandId": "fuse.examples.install",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fuse.examples.list",
    {
      "commandId": "fuse.examples.list",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fuse.install",
    {
      "commandId": "fuse.install",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fuse.list",
    {
      "commandId": "fuse.list",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fuse.scaffold",
    {
      "commandId": "fuse.scaffold",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fuse.uninstall",
    {
      "commandId": "fuse.uninstall",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fuse.validate",
    {
      "commandId": "fuse.validate",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fusion.apply",
    {
      "commandId": "fusion.apply",
      "actionId": "cutagent.action.fusion.apply",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.comp.current",
    {
      "commandId": "fusion.comp.current",
      "actionId": "cutagent.action.fusion.comp.current",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fusion.comp.delete",
    {
      "commandId": "fusion.comp.delete",
      "actionId": "cutagent.action.fusion.comp.delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.comp.play",
    {
      "commandId": "fusion.comp.play",
      "actionId": "cutagent.action.fusion.comp.play",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.comp.range",
    {
      "commandId": "fusion.comp.range",
      "actionId": "cutagent.action.fusion.comp.range",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.comp.rename",
    {
      "commandId": "fusion.comp.rename",
      "actionId": "cutagent.action.fusion.comp.rename",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.comp.render",
    {
      "commandId": "fusion.comp.render",
      "actionId": "cutagent.action.fusion.comp.render",
      "aliasOf": null,
      "operationClass": "long_running",
      "verificationCategory": "terminal_and_readback"
    }
  ],
  [
    "fusion.comp.stop",
    {
      "commandId": "fusion.comp.stop",
      "actionId": "cutagent.action.fusion.comp.stop",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.effect.blur",
    {
      "commandId": "fusion.effect.blur",
      "actionId": "cutagent.action.fusion.effect.blur",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.effect.color_correct",
    {
      "commandId": "fusion.effect.color_correct",
      "actionId": "cutagent.action.fusion.effect.color_correct",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.effect.glow",
    {
      "commandId": "fusion.effect.glow",
      "actionId": "cutagent.action.fusion.effect.glow",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.effect.sharpen",
    {
      "commandId": "fusion.effect.sharpen",
      "actionId": "cutagent.action.fusion.effect.sharpen",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.effect.transform",
    {
      "commandId": "fusion.effect.transform",
      "actionId": "cutagent.action.fusion.effect.transform",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.generate",
    {
      "commandId": "fusion.generate",
      "actionId": "cutagent.action.fusion.generate",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.image.batch",
    {
      "commandId": "fusion.image.batch",
      "actionId": "cutagent.action.fusion.image.batch",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.image.set",
    {
      "commandId": "fusion.image.set",
      "actionId": "cutagent.action.fusion.image.set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.insert_setting",
    {
      "commandId": "fusion.insert_setting",
      "actionId": "cutagent.action.fusion.insert_setting",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.insert_settings.batch",
    {
      "commandId": "fusion.insert_settings.batch",
      "actionId": "cutagent.action.fusion.insert_settings.batch",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.keyer.chroma",
    {
      "commandId": "fusion.keyer.chroma",
      "actionId": "cutagent.action.fusion.keyer.chroma",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.keyframe.add",
    {
      "commandId": "fusion.keyframe.add",
      "actionId": "cutagent.action.fusion.keyframe.add",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.keyframe.clear",
    {
      "commandId": "fusion.keyframe.clear",
      "actionId": "cutagent.action.fusion.keyframe.clear",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.keyframe.delete",
    {
      "commandId": "fusion.keyframe.delete",
      "actionId": "cutagent.action.fusion.keyframe.delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.keyframe.list",
    {
      "commandId": "fusion.keyframe.list",
      "actionId": "cutagent.action.fusion.keyframe.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fusion.keyframe.set",
    {
      "commandId": "fusion.keyframe.set",
      "actionId": "cutagent.action.fusion.keyframe.set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.macro.apply",
    {
      "commandId": "fusion.macro.apply",
      "actionId": "cutagent.action.fusion.macro.apply",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.mask.ellipse",
    {
      "commandId": "fusion.mask.ellipse",
      "actionId": "cutagent.action.fusion.mask.ellipse",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.mask.polygon",
    {
      "commandId": "fusion.mask.polygon",
      "actionId": "cutagent.action.fusion.mask.polygon",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.mask.rectangle",
    {
      "commandId": "fusion.mask.rectangle",
      "actionId": "cutagent.action.fusion.mask.rectangle",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.nested_text.batch",
    {
      "commandId": "fusion.nested_text.batch",
      "actionId": "cutagent.action.fusion.nested_text.batch",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.nested_text.update",
    {
      "commandId": "fusion.nested_text.update",
      "actionId": "cutagent.action.fusion.nested_text.update",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.node.add",
    {
      "commandId": "fusion.node.add",
      "actionId": "cutagent.action.fusion.node.add",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.node.connect",
    {
      "commandId": "fusion.node.connect",
      "actionId": "cutagent.action.fusion.node.connect",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.node.delete",
    {
      "commandId": "fusion.node.delete",
      "actionId": "cutagent.action.fusion.node.delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.node.disconnect",
    {
      "commandId": "fusion.node.disconnect",
      "actionId": "cutagent.action.fusion.node.disconnect",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.preview",
    {
      "commandId": "fusion.preview",
      "actionId": "cutagent.action.fusion.preview",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fusion.setting.center_to_polypath",
    {
      "commandId": "fusion.setting.center_to_polypath",
      "actionId": "cutagent.action.fusion.setting.center_to_polypath",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fusion.setting.inspect",
    {
      "commandId": "fusion.setting.inspect",
      "actionId": "cutagent.action.fusion.setting.inspect",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fusion.setting.polypath_to_center",
    {
      "commandId": "fusion.setting.polypath_to_center",
      "actionId": "cutagent.action.fusion.setting.polypath_to_center",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fusion.setting.summary",
    {
      "commandId": "fusion.setting.summary",
      "actionId": "cutagent.action.fusion.setting.summary",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fusion.setting.validate",
    {
      "commandId": "fusion.setting.validate",
      "actionId": "cutagent.action.fusion.setting.validate",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.template.apply",
    {
      "commandId": "fusion.template.apply",
      "actionId": "cutagent.action.fusion.template.apply",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.template.assets.add",
    {
      "commandId": "fusion.template.assets.add",
      "actionId": "cutagent.action.fusion.template.assets.add",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.template.assets.list",
    {
      "commandId": "fusion.template.assets.list",
      "actionId": "cutagent.action.fusion.template.assets.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fusion.template.dir",
    {
      "commandId": "fusion.template.dir",
      "actionId": "cutagent.action.fusion.template.dir",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.template.icon.set",
    {
      "commandId": "fusion.template.icon.set",
      "actionId": "cutagent.action.fusion.template.icon.set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.template.install",
    {
      "commandId": "fusion.template.install",
      "actionId": "cutagent.action.fusion.template.install",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.template.list",
    {
      "commandId": "fusion.template.list",
      "actionId": "cutagent.action.fusion.template.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fusion.template.package_drfx",
    {
      "commandId": "fusion.template.package_drfx",
      "actionId": "cutagent.action.fusion.template.package_drfx",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.template.scaffold",
    {
      "commandId": "fusion.template.scaffold",
      "actionId": "cutagent.action.fusion.template.scaffold",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.template.show",
    {
      "commandId": "fusion.template.show",
      "actionId": "cutagent.action.fusion.template.show",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fusion.template.uninstall",
    {
      "commandId": "fusion.template.uninstall",
      "actionId": "cutagent.action.fusion.template.uninstall",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.template.unpack_drfx",
    {
      "commandId": "fusion.template.unpack_drfx",
      "actionId": "cutagent.action.fusion.template.unpack_drfx",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "fusion.template.validate",
    {
      "commandId": "fusion.template.validate",
      "actionId": "cutagent.action.fusion.template.validate",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fusion.text.batch",
    {
      "commandId": "fusion.text.batch",
      "actionId": "cutagent.action.fusion.text.batch",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.text.set",
    {
      "commandId": "fusion.text.set",
      "actionId": "cutagent.action.fusion.text.set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.tool.active",
    {
      "commandId": "fusion.tool.active",
      "actionId": "cutagent.action.fusion.tool.active",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.tool.add",
    {
      "commandId": "fusion.tool.add",
      "actionId": "cutagent.action.fusion.tool.add",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.tool.attrs",
    {
      "commandId": "fusion.tool.attrs",
      "actionId": "cutagent.action.fusion.tool.attrs",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fusion.tool.connect",
    {
      "commandId": "fusion.tool.connect",
      "actionId": "cutagent.action.fusion.tool.connect",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.tool.copy",
    {
      "commandId": "fusion.tool.copy",
      "actionId": "cutagent.action.fusion.tool.copy",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.tool.delete",
    {
      "commandId": "fusion.tool.delete",
      "actionId": "cutagent.action.fusion.tool.delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.tool.disconnect",
    {
      "commandId": "fusion.tool.disconnect",
      "actionId": "cutagent.action.fusion.tool.disconnect",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.tool.get",
    {
      "commandId": "fusion.tool.get",
      "actionId": "cutagent.action.fusion.tool.get",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fusion.tool.inputs",
    {
      "commandId": "fusion.tool.inputs",
      "actionId": "cutagent.action.fusion.tool.inputs",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fusion.tool.list",
    {
      "commandId": "fusion.tool.list",
      "actionId": "cutagent.action.fusion.tool.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fusion.tool.outputs",
    {
      "commandId": "fusion.tool.outputs",
      "actionId": "cutagent.action.fusion.tool.outputs",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fusion.tool.paste",
    {
      "commandId": "fusion.tool.paste",
      "actionId": "cutagent.action.fusion.tool.paste",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.tool.registry",
    {
      "commandId": "fusion.tool.registry",
      "actionId": "cutagent.action.fusion.tool.registry",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "fusion.tool.set",
    {
      "commandId": "fusion.tool.set",
      "actionId": "cutagent.action.fusion.tool.set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "fusion.tracker.add",
    {
      "commandId": "fusion.tracker.add",
      "actionId": "cutagent.action.fusion.tracker.add",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "info",
    {
      "commandId": "info",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "launch",
    {
      "commandId": "launch",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "layout.delete",
    {
      "commandId": "layout.delete",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "layout.export",
    {
      "commandId": "layout.export",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "layout.import",
    {
      "commandId": "layout.import",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "layout.load",
    {
      "commandId": "layout.load",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "layout.save",
    {
      "commandId": "layout.save",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "layout.update",
    {
      "commandId": "layout.update",
      "actionId": null,
      "aliasOf": "layout.save",
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "lut.convert",
    {
      "commandId": "lut.convert",
      "actionId": "cutagent.action.lut.convert",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "lut.generate.identity",
    {
      "commandId": "lut.generate.identity",
      "actionId": "cutagent.action.lut.generate.identity",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "lut.inspect",
    {
      "commandId": "lut.inspect",
      "actionId": "cutagent.action.lut.inspect",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "lut.install",
    {
      "commandId": "lut.install",
      "actionId": "cutagent.action.lut.install",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "lut.list",
    {
      "commandId": "lut.list",
      "actionId": "cutagent.action.lut.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "lut.remove",
    {
      "commandId": "lut.remove",
      "actionId": "cutagent.action.lut.remove",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "lut.validate",
    {
      "commandId": "lut.validate",
      "actionId": "cutagent.action.lut.validate",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "lut_refresh",
    {
      "commandId": "lut_refresh",
      "actionId": "cutagent.action.lut_refresh",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.append",
    {
      "commandId": "media.append",
      "actionId": "cutagent.action.media.append",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.append.batch",
    {
      "commandId": "media.append.batch",
      "actionId": "cutagent.action.media.append.batch",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.audio_mapping",
    {
      "commandId": "media.audio_mapping",
      "actionId": "cutagent.action.media.audio_mapping",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "media.clear_transcription",
    {
      "commandId": "media.clear_transcription",
      "actionId": "cutagent.action.media.clear_transcription",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.color.clear",
    {
      "commandId": "media.color.clear",
      "actionId": "cutagent.action.media.color.clear",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.color.set",
    {
      "commandId": "media.color.set",
      "actionId": "cutagent.action.media.color.set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.create_timeline",
    {
      "commandId": "media.create_timeline",
      "actionId": "cutagent.action.media.create_timeline",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.delete",
    {
      "commandId": "media.delete",
      "actionId": "cutagent.action.media.delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.duplicate",
    {
      "commandId": "media.duplicate",
      "actionId": "cutagent.action.media.duplicate",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.extract_template",
    {
      "commandId": "media.extract_template",
      "actionId": "cutagent.action.media.extract_template",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.flag.add",
    {
      "commandId": "media.flag.add",
      "actionId": "cutagent.action.media.flag.add",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.flag.clear",
    {
      "commandId": "media.flag.clear",
      "actionId": "cutagent.action.media.flag.clear",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.folder.export_drb",
    {
      "commandId": "media.folder.export_drb",
      "actionId": "cutagent.action.media.folder.export_drb",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.folder.import_drb",
    {
      "commandId": "media.folder.import_drb",
      "actionId": "cutagent.action.media.folder.import_drb",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.folders.create",
    {
      "commandId": "media.folders.create",
      "actionId": "cutagent.action.media.folders.create",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.folders.delete",
    {
      "commandId": "media.folders.delete",
      "actionId": "cutagent.action.media.folders.delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.folders.list",
    {
      "commandId": "media.folders.list",
      "actionId": "cutagent.action.media.folders.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "media.folders.move",
    {
      "commandId": "media.folders.move",
      "actionId": "cutagent.action.media.folders.move",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.folders.open",
    {
      "commandId": "media.folders.open",
      "actionId": "cutagent.action.media.folders.open",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.folders.root",
    {
      "commandId": "media.folders.root",
      "actionId": "cutagent.action.media.folders.root",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.folders.tree",
    {
      "commandId": "media.folders.tree",
      "actionId": "cutagent.action.media.folders.tree",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "media.growing_file.monitor",
    {
      "commandId": "media.growing_file.monitor",
      "actionId": "cutagent.action.media.growing_file.monitor",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.import",
    {
      "commandId": "media.import",
      "actionId": "cutagent.action.media.import",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.info",
    {
      "commandId": "media.info",
      "actionId": "cutagent.action.media.info",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "media.list",
    {
      "commandId": "media.list",
      "actionId": "cutagent.action.media.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "media.mark.clear",
    {
      "commandId": "media.mark.clear",
      "actionId": "cutagent.action.media.mark.clear",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.mark.get",
    {
      "commandId": "media.mark.get",
      "actionId": "cutagent.action.media.mark.get",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "media.mark.set",
    {
      "commandId": "media.mark.set",
      "actionId": "cutagent.action.media.mark.set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.marker.add",
    {
      "commandId": "media.marker.add",
      "actionId": "cutagent.action.media.marker.add",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.marker.delete",
    {
      "commandId": "media.marker.delete",
      "actionId": "cutagent.action.media.marker.delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.marker.list",
    {
      "commandId": "media.marker.list",
      "actionId": "cutagent.action.media.marker.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "media.matte.delete",
    {
      "commandId": "media.matte.delete",
      "actionId": "cutagent.action.media.matte.delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.matte.list",
    {
      "commandId": "media.matte.list",
      "actionId": "cutagent.action.media.matte.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "media.metadata",
    {
      "commandId": "media.metadata",
      "actionId": "cutagent.action.media.metadata",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.metadata.export",
    {
      "commandId": "media.metadata.export",
      "actionId": "cutagent.action.media.metadata.export",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.move",
    {
      "commandId": "media.move",
      "actionId": "cutagent.action.media.move",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.property_set",
    {
      "commandId": "media.property_set",
      "actionId": "cutagent.action.media.property_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.proxy",
    {
      "commandId": "media.proxy",
      "actionId": "cutagent.action.media.proxy",
      "aliasOf": null,
      "operationClass": "long_running",
      "verificationCategory": "terminal_and_readback"
    }
  ],
  [
    "media.proxy.link_fullres",
    {
      "commandId": "media.proxy.link_fullres",
      "actionId": "cutagent.action.media.proxy.link_fullres",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.relink",
    {
      "commandId": "media.relink",
      "actionId": "cutagent.action.media.relink",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.rename",
    {
      "commandId": "media.rename",
      "actionId": "cutagent.action.media.rename",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.replace",
    {
      "commandId": "media.replace",
      "actionId": "cutagent.action.media.replace",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.replace_preserve_subclip",
    {
      "commandId": "media.replace_preserve_subclip",
      "actionId": "cutagent.action.media.replace_preserve_subclip",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.search",
    {
      "commandId": "media.search",
      "actionId": "cutagent.action.media.search",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "media.selected.list",
    {
      "commandId": "media.selected.list",
      "actionId": "cutagent.action.media.selected.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "media.selected.set",
    {
      "commandId": "media.selected.set",
      "actionId": "cutagent.action.media.selected.set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.stereo_create",
    {
      "commandId": "media.stereo_create",
      "actionId": "cutagent.action.media.stereo_create",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.sync_audio",
    {
      "commandId": "media.sync_audio",
      "actionId": "cutagent.action.media.sync_audio",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.third_party_metadata.get",
    {
      "commandId": "media.third_party_metadata.get",
      "actionId": "cutagent.action.media.third_party_metadata.get",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "media.third_party_metadata.set",
    {
      "commandId": "media.third_party_metadata.set",
      "actionId": "cutagent.action.media.third_party_metadata.set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.third_party_metadata.set_json",
    {
      "commandId": "media.third_party_metadata.set_json",
      "actionId": "cutagent.action.media.third_party_metadata.bulk_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.timeline_matte.list",
    {
      "commandId": "media.timeline_matte.list",
      "actionId": "cutagent.action.media.timeline_matte.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "media.transcode",
    {
      "commandId": "media.transcode",
      "actionId": "cutagent.action.media.transcode",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "media.transcribe",
    {
      "commandId": "media.transcribe",
      "actionId": "cutagent.action.media.transcribe",
      "aliasOf": null,
      "operationClass": "long_running",
      "verificationCategory": "terminal_and_readback"
    }
  ],
  [
    "media.transcription",
    {
      "commandId": "media.transcription",
      "actionId": "cutagent.action.media.transcription",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "media.unlink",
    {
      "commandId": "media.unlink",
      "actionId": "cutagent.action.media.unlink",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "multicam.angle.remove",
    {
      "commandId": "multicam.angle.remove",
      "actionId": "cutagent.action.multicam.angle.remove",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "multicam.angle.rename",
    {
      "commandId": "multicam.angle.rename",
      "actionId": "cutagent.action.multicam.angle.rename",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "multicam.angle.set_enabled",
    {
      "commandId": "multicam.angle.set_enabled",
      "actionId": "cutagent.action.multicam.angle.set_enabled",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "multicam.audio_activity.calibrate",
    {
      "commandId": "multicam.audio_activity.calibrate",
      "actionId": "cutagent.action.multicam.audio_activity.calibrate",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "multicam.convert",
    {
      "commandId": "multicam.convert",
      "actionId": "cutagent.action.multicam.convert",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "multicam.create",
    {
      "commandId": "multicam.create",
      "actionId": "cutagent.action.multicam.create",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "multicam.flatten",
    {
      "commandId": "multicam.flatten",
      "actionId": "cutagent.action.multicam.flatten",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "multicam.inspect",
    {
      "commandId": "multicam.inspect",
      "actionId": "cutagent.action.multicam.inspect",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "multicam.match_frame",
    {
      "commandId": "multicam.match_frame",
      "actionId": "cutagent.action.multicam.match_frame",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "multicam.recover_timing",
    {
      "commandId": "multicam.recover_timing",
      "actionId": "cutagent.action.multicam.recover_timing",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "multicam.reorder_angles",
    {
      "commandId": "multicam.reorder_angles",
      "actionId": "cutagent.action.multicam.reorder_angles",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "multicam.replace.audio",
    {
      "commandId": "multicam.replace.audio",
      "actionId": "cutagent.action.multicam.replace.audio",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "multicam.replace.video",
    {
      "commandId": "multicam.replace.video",
      "actionId": "cutagent.action.multicam.replace.video",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "multicam.seed_timeline",
    {
      "commandId": "multicam.seed_timeline",
      "actionId": "cutagent.action.multicam.seed_timeline",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "multicam.set_start_timecode",
    {
      "commandId": "multicam.set_start_timecode",
      "actionId": "cutagent.action.multicam.set_start_timecode",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "multicam.settings",
    {
      "commandId": "multicam.settings",
      "actionId": "cutagent.action.multicam.settings",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "multicam.smart_switch",
    {
      "commandId": "multicam.smart_switch",
      "actionId": "cutagent.action.multicam.smart_switch",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "multicam.source.grade_cdl",
    {
      "commandId": "multicam.source.grade_cdl",
      "actionId": "cutagent.action.multicam.source.grade_cdl",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "multicam.source.move",
    {
      "commandId": "multicam.source.move",
      "actionId": "cutagent.action.multicam.source.move",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "multicam.source.property_set",
    {
      "commandId": "multicam.source.property_set",
      "actionId": "cutagent.action.multicam.source.property_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "multicam.source.raw_braw_set",
    {
      "commandId": "multicam.source.raw_braw_set",
      "actionId": "cutagent.action.multicam.source.raw_braw_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "multicam.source.remove",
    {
      "commandId": "multicam.source.remove",
      "actionId": "cutagent.action.multicam.source.remove",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "multicam.strip_embedded_audio",
    {
      "commandId": "multicam.strip_embedded_audio",
      "actionId": "cutagent.action.multicam.strip_embedded_audio",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "multicam.switch",
    {
      "commandId": "multicam.switch",
      "actionId": "cutagent.action.multicam.switch",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "multicam.timeline_create",
    {
      "commandId": "multicam.timeline_create",
      "actionId": "cutagent.action.multicam.timeline_create",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "multicam.verdict_clear",
    {
      "commandId": "multicam.verdict_clear",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "multicam.verdict_list",
    {
      "commandId": "multicam.verdict_list",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "multicam.verdict_set",
    {
      "commandId": "multicam.verdict_set",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "ofx.build",
    {
      "commandId": "ofx.build",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "ofx.install",
    {
      "commandId": "ofx.install",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "ofx.list_installed",
    {
      "commandId": "ofx.list_installed",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "ofx.package",
    {
      "commandId": "ofx.package",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "ofx.sample.copy",
    {
      "commandId": "ofx.sample.copy",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "ofx.scaffold",
    {
      "commandId": "ofx.scaffold",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "ofx.uninstall",
    {
      "commandId": "ofx.uninstall",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "ofx.validate",
    {
      "commandId": "ofx.validate",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "page.current",
    {
      "commandId": "page.current",
      "actionId": "cutagent.action.page.current",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "page.switch",
    {
      "commandId": "page.switch",
      "actionId": "cutagent.action.page.switch",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "product",
    {
      "commandId": "product",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "project.archive",
    {
      "commandId": "project.archive",
      "actionId": "cutagent.action.project.archive",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.cleanup_scratch",
    {
      "commandId": "project.cleanup_scratch",
      "actionId": "cutagent.action.project.cleanup_scratch",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.close",
    {
      "commandId": "project.close",
      "actionId": "cutagent.action.project.close",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.cloud.create",
    {
      "commandId": "project.cloud.create",
      "actionId": "cutagent.action.project.cloud.create",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.cloud.import",
    {
      "commandId": "project.cloud.import",
      "actionId": "cutagent.action.project.cloud.import",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.cloud.open",
    {
      "commandId": "project.cloud.open",
      "actionId": "cutagent.action.project.cloud.open",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.cloud.restore",
    {
      "commandId": "project.cloud.restore",
      "actionId": "cutagent.action.project.cloud.restore",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.create",
    {
      "commandId": "project.create",
      "actionId": "cutagent.action.project.create",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.db.backup",
    {
      "commandId": "project.db.backup",
      "actionId": "cutagent.action.project.library.backup",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.db.create",
    {
      "commandId": "project.db.create",
      "actionId": "cutagent.action.project.library.create",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.db.current",
    {
      "commandId": "project.db.current",
      "actionId": "cutagent.action.project.library.current",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "project.db.list",
    {
      "commandId": "project.db.list",
      "actionId": "cutagent.action.project.library.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "project.db.restore",
    {
      "commandId": "project.db.restore",
      "actionId": "cutagent.action.project.library.restore",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.db.switch",
    {
      "commandId": "project.db.switch",
      "actionId": "cutagent.action.project.library.switch",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.delete",
    {
      "commandId": "project.delete",
      "actionId": "cutagent.action.project.delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.export",
    {
      "commandId": "project.export",
      "actionId": "cutagent.action.project.export",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.folders.create",
    {
      "commandId": "project.folders.create",
      "actionId": "cutagent.action.project.folders.create",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.folders.delete",
    {
      "commandId": "project.folders.delete",
      "actionId": "cutagent.action.project.folders.delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.folders.list",
    {
      "commandId": "project.folders.list",
      "actionId": "cutagent.action.project.folders.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "project.folders.open",
    {
      "commandId": "project.folders.open",
      "actionId": "cutagent.action.project.folders.open",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.folders.root",
    {
      "commandId": "project.folders.root",
      "actionId": "cutagent.action.project.folders.root",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.folders.up",
    {
      "commandId": "project.folders.up",
      "actionId": "cutagent.action.project.folders.up",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.import",
    {
      "commandId": "project.import",
      "actionId": "cutagent.action.project.import",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.info",
    {
      "commandId": "project.info",
      "actionId": "cutagent.action.project.info",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "project.list",
    {
      "commandId": "project.list",
      "actionId": "cutagent.action.project.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "project.open",
    {
      "commandId": "project.open",
      "actionId": "cutagent.action.project.open",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.preset.delete",
    {
      "commandId": "project.preset.delete",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "project.preset.export",
    {
      "commandId": "project.preset.export",
      "actionId": "cutagent.action.project.preset.export",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.preset.import",
    {
      "commandId": "project.preset.import",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "project.preset.list",
    {
      "commandId": "project.preset.list",
      "actionId": "cutagent.action.project.preset.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "project.preset.load",
    {
      "commandId": "project.preset.load",
      "actionId": "cutagent.action.project.preset.load",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.preset.save",
    {
      "commandId": "project.preset.save",
      "actionId": "cutagent.action.project.preset.save",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.rename",
    {
      "commandId": "project.rename",
      "actionId": "cutagent.action.project.rename",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.restore",
    {
      "commandId": "project.restore",
      "actionId": "cutagent.action.project.restore",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.save",
    {
      "commandId": "project.save",
      "actionId": "cutagent.action.project.save",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "project.settings",
    {
      "commandId": "project.settings",
      "actionId": "cutagent.action.project.settings",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "project.settings_get",
    {
      "commandId": "project.settings_get",
      "actionId": null,
      "aliasOf": "project.settings",
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "project.settings_set",
    {
      "commandId": "project.settings_set",
      "actionId": "cutagent.action.project.settings_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "quit",
    {
      "commandId": "quit",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "render.add",
    {
      "commandId": "render.add",
      "actionId": "cutagent.action.render.add",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "render.alpha",
    {
      "commandId": "render.alpha",
      "actionId": "cutagent.action.render.alpha",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "render.archive_settings",
    {
      "commandId": "render.archive_settings",
      "actionId": "cutagent.action.render.archive_settings",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "render.audio",
    {
      "commandId": "render.audio",
      "actionId": "cutagent.action.render.audio",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "render.burnin.export",
    {
      "commandId": "render.burnin.export",
      "actionId": "cutagent.action.render.burnin.export",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "render.burnin.import",
    {
      "commandId": "render.burnin.import",
      "actionId": "cutagent.action.render.burnin.import",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "render.burnin.load",
    {
      "commandId": "render.burnin.load",
      "actionId": "cutagent.action.render.burnin.load",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "render.cancel",
    {
      "commandId": "render.cancel",
      "actionId": "cutagent.action.render.cancel",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "render.codecs",
    {
      "commandId": "render.codecs",
      "actionId": "cutagent.action.render.codecs",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "render.custom_range",
    {
      "commandId": "render.custom_range",
      "actionId": "cutagent.action.render.custom_range",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "render.delete",
    {
      "commandId": "render.delete",
      "actionId": "cutagent.action.render.delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "render.encoding",
    {
      "commandId": "render.encoding",
      "actionId": "cutagent.action.render.encoding",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "render.export_file",
    {
      "commandId": "render.export_file",
      "actionId": "cutagent.action.render.export_file",
      "aliasOf": null,
      "operationClass": "long_running",
      "verificationCategory": "terminal_and_readback"
    }
  ],
  [
    "render.export_preset",
    {
      "commandId": "render.export_preset",
      "actionId": "cutagent.action.render.export_preset",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "render.formats",
    {
      "commandId": "render.formats",
      "actionId": "cutagent.action.render.formats",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "render.import_preset",
    {
      "commandId": "render.import_preset",
      "actionId": "cutagent.action.render.import_preset",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "render.job_status",
    {
      "commandId": "render.job_status",
      "actionId": "cutagent.action.render.job_status",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "render.jobs",
    {
      "commandId": "render.jobs",
      "actionId": "cutagent.action.render.jobs",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "render.mode.get",
    {
      "commandId": "render.mode.get",
      "actionId": "cutagent.action.render.mode.get",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "render.mode.set",
    {
      "commandId": "render.mode.set",
      "actionId": "cutagent.action.render.mode.set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "render.preset_delete",
    {
      "commandId": "render.preset_delete",
      "actionId": "cutagent.action.render.preset_delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "render.preset_load",
    {
      "commandId": "render.preset_load",
      "actionId": "cutagent.action.render.preset_load",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "render.preset_save",
    {
      "commandId": "render.preset_save",
      "actionId": "cutagent.action.render.preset_save",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "render.preset_update",
    {
      "commandId": "render.preset_update",
      "actionId": "cutagent.action.render.preset_update",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "render.presets",
    {
      "commandId": "render.presets",
      "actionId": "cutagent.action.render.presets",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "render.quick_export",
    {
      "commandId": "render.quick_export",
      "actionId": "cutagent.action.render.quick_export",
      "aliasOf": null,
      "operationClass": "long_running",
      "verificationCategory": "terminal_and_readback"
    }
  ],
  [
    "render.quick_export_presets",
    {
      "commandId": "render.quick_export_presets",
      "actionId": "cutagent.action.render.quick_export_presets",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "render.resolutions",
    {
      "commandId": "render.resolutions",
      "actionId": "cutagent.action.render.resolutions",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "render.settings",
    {
      "commandId": "render.settings",
      "actionId": "cutagent.action.render.settings",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "render.settings_get",
    {
      "commandId": "render.settings_get",
      "actionId": null,
      "aliasOf": "render.settings",
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "render.settings_set",
    {
      "commandId": "render.settings_set",
      "actionId": "cutagent.action.render.settings_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "render.settings_set_json",
    {
      "commandId": "render.settings_set_json",
      "actionId": "cutagent.action.render.settings.replace",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "render.settings_set_key",
    {
      "commandId": "render.settings_set_key",
      "actionId": "cutagent.action.render.settings.update",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "render.start",
    {
      "commandId": "render.start",
      "actionId": "cutagent.action.render.start",
      "aliasOf": null,
      "operationClass": "long_running",
      "verificationCategory": "terminal_and_readback"
    }
  ],
  [
    "render.status",
    {
      "commandId": "render.status",
      "actionId": "cutagent.action.render.status",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "render.stop",
    {
      "commandId": "render.stop",
      "actionId": "cutagent.action.render.stop",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "render.subtitles",
    {
      "commandId": "render.subtitles",
      "actionId": "cutagent.action.render.subtitles",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "render.transcript_audio",
    {
      "commandId": "render.transcript_audio",
      "actionId": "cutagent.action.render.transcript_audio",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "render.wait",
    {
      "commandId": "render.wait",
      "actionId": "cutagent.action.render.wait",
      "aliasOf": null,
      "operationClass": "long_running",
      "verificationCategory": "terminal_and_readback"
    }
  ],
  [
    "script.env.print",
    {
      "commandId": "script.env.print",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "script.install",
    {
      "commandId": "script.install",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "script.list",
    {
      "commandId": "script.list",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "script.run",
    {
      "commandId": "script.run",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "script.uninstall",
    {
      "commandId": "script.uninstall",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "sdk.low_level.read",
    {
      "commandId": "sdk.low_level.read",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "status",
    {
      "commandId": "status",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "storage.files",
    {
      "commandId": "storage.files",
      "actionId": "cutagent.action.storage.files",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "storage.import",
    {
      "commandId": "storage.import",
      "actionId": "cutagent.action.storage.import",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "storage.import_sequence",
    {
      "commandId": "storage.import_sequence",
      "actionId": "cutagent.action.storage.import_sequence",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "storage.import_subclip",
    {
      "commandId": "storage.import_subclip",
      "actionId": "cutagent.action.storage.import_subclip",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "storage.matte.add",
    {
      "commandId": "storage.matte.add",
      "actionId": "cutagent.action.storage.matte.add",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "storage.matte.timeline_add",
    {
      "commandId": "storage.matte.timeline_add",
      "actionId": "cutagent.action.storage.matte.timeline_add",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "storage.reveal",
    {
      "commandId": "storage.reveal",
      "actionId": "cutagent.action.storage.reveal",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "storage.volumes",
    {
      "commandId": "storage.volumes",
      "actionId": "cutagent.action.storage.volumes",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "system.keyboard_preset.current",
    {
      "commandId": "system.keyboard_preset.current",
      "actionId": "cutagent.action.system.keyboard_preset.current",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "system.keyboard_preset.delete",
    {
      "commandId": "system.keyboard_preset.delete",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "system.keyboard_preset.export",
    {
      "commandId": "system.keyboard_preset.export",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "system.keyboard_preset.import",
    {
      "commandId": "system.keyboard_preset.import",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "system.keyboard_preset.list",
    {
      "commandId": "system.keyboard_preset.list",
      "actionId": "cutagent.action.system.keyboard_preset.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "system.keyboard_preset.load",
    {
      "commandId": "system.keyboard_preset.load",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "system.keyframe_mode.get",
    {
      "commandId": "system.keyframe_mode.get",
      "actionId": "cutagent.action.system.keyframe_mode.get",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "system.keyframe_mode.set",
    {
      "commandId": "system.keyframe_mode.set",
      "actionId": "cutagent.action.system.keyframe_mode.set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "text.insert",
    {
      "commandId": "text.insert",
      "actionId": "cutagent.action.text.insert",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "text.insert_captions",
    {
      "commandId": "text.insert_captions",
      "actionId": "cutagent.action.text.insert_captions",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "text.insert_preset",
    {
      "commandId": "text.insert_preset",
      "actionId": "cutagent.action.text.insert_preset",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "text.insert_template",
    {
      "commandId": "text.insert_template",
      "actionId": "cutagent.action.text.insert_template",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "text.insert_template_batch",
    {
      "commandId": "text.insert_template_batch",
      "actionId": "cutagent.action.text.insert_template_batch",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "text.inspect",
    {
      "commandId": "text.inspect",
      "actionId": "cutagent.action.text.inspect",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "text.list_presets",
    {
      "commandId": "text.list_presets",
      "actionId": "cutagent.action.text.list_presets",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "text.update",
    {
      "commandId": "text.update",
      "actionId": "cutagent.action.text.update",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.auto_caption",
    {
      "commandId": "timeline.auto_caption",
      "actionId": "cutagent.action.timeline.auto_caption",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.captions",
    {
      "commandId": "timeline.captions",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "timeline.clip_color.batch",
    {
      "commandId": "timeline.clip_color.batch",
      "actionId": "cutagent.action.timeline.clip_color.batch",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.clip_markers.list",
    {
      "commandId": "timeline.clip_markers.list",
      "actionId": "cutagent.action.timeline.clip_markers.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "timeline.compound_create",
    {
      "commandId": "timeline.compound_create",
      "actionId": "cutagent.action.timeline.compound_create",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.create",
    {
      "commandId": "timeline.create",
      "actionId": "cutagent.action.timeline.create",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.current_item",
    {
      "commandId": "timeline.current_item",
      "actionId": "cutagent.action.timeline.current_item",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "timeline.delete",
    {
      "commandId": "timeline.delete",
      "actionId": "cutagent.action.timeline.delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.dolby.analyze",
    {
      "commandId": "timeline.dolby.analyze",
      "actionId": "cutagent.action.timeline.dolby.analyze",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.duplicate",
    {
      "commandId": "timeline.duplicate",
      "actionId": "cutagent.action.timeline.duplicate",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.duration",
    {
      "commandId": "timeline.duration",
      "actionId": "cutagent.action.timeline.duration",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "timeline.export",
    {
      "commandId": "timeline.export",
      "actionId": "cutagent.action.timeline.export",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.fairlight_preset.apply",
    {
      "commandId": "timeline.fairlight_preset.apply",
      "actionId": "cutagent.action.timeline.fairlight_preset.apply",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.frame_export",
    {
      "commandId": "timeline.frame_export",
      "actionId": "cutagent.action.timeline.frame_export",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.frame_export.batch",
    {
      "commandId": "timeline.frame_export.batch",
      "actionId": "cutagent.action.timeline.frame_export.batch",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.fusion_clip.create",
    {
      "commandId": "timeline.fusion_clip.create",
      "actionId": "cutagent.action.timeline.fusion_clip.create",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.fusion_composition.insert",
    {
      "commandId": "timeline.fusion_composition.insert",
      "actionId": "cutagent.action.timeline.fusion_composition.insert",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.grab_still",
    {
      "commandId": "timeline.grab_still",
      "actionId": "cutagent.action.timeline.grab_still",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.import",
    {
      "commandId": "timeline.import",
      "actionId": "cutagent.action.timeline.import",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.import_into",
    {
      "commandId": "timeline.import_into",
      "actionId": "cutagent.action.timeline.import_into",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.info",
    {
      "commandId": "timeline.info",
      "actionId": "cutagent.action.timeline.info",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "timeline.insert_generator",
    {
      "commandId": "timeline.insert_generator",
      "actionId": "cutagent.action.timeline.insert_generator",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.insert_title",
    {
      "commandId": "timeline.insert_title",
      "actionId": "cutagent.action.timeline.insert_title",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.inspect_export",
    {
      "commandId": "timeline.inspect_export",
      "actionId": "cutagent.action.timeline.inspect_export",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.item_at",
    {
      "commandId": "timeline.item_at",
      "actionId": "cutagent.action.timeline.item_at",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "timeline.items.delete",
    {
      "commandId": "timeline.items.delete",
      "actionId": "cutagent.action.timeline.items.delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.items.move",
    {
      "commandId": "timeline.items.move",
      "actionId": "cutagent.action.timeline.items.move",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "timeline.items.set_duration",
    {
      "commandId": "timeline.items.set_duration",
      "actionId": "cutagent.action.timeline.items.set_duration",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.layer.ensure_media",
    {
      "commandId": "timeline.layer.ensure_media",
      "actionId": "cutagent.action.timeline.layer.ensure_media",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.layout.free_stack",
    {
      "commandId": "timeline.layout.free_stack",
      "actionId": "cutagent.action.timeline.layout.free_stack",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.list",
    {
      "commandId": "timeline.list",
      "actionId": "cutagent.action.timeline.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "timeline.mark.clear",
    {
      "commandId": "timeline.mark.clear",
      "actionId": "cutagent.action.timeline.mark.clear",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.mark.get",
    {
      "commandId": "timeline.mark.get",
      "actionId": "cutagent.action.timeline.mark.get",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "timeline.mark.set",
    {
      "commandId": "timeline.mark.set",
      "actionId": "cutagent.action.timeline.mark.set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.marker.add",
    {
      "commandId": "timeline.marker.add",
      "actionId": "cutagent.action.timeline.marker.add",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.marker.batch",
    {
      "commandId": "timeline.marker.batch",
      "actionId": "cutagent.action.timeline.marker.batch",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.marker.delete",
    {
      "commandId": "timeline.marker.delete",
      "actionId": "cutagent.action.timeline.marker.delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.marker.list",
    {
      "commandId": "timeline.marker.list",
      "actionId": "cutagent.action.timeline.marker.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "timeline.marker.update",
    {
      "commandId": "timeline.marker.update",
      "actionId": "cutagent.action.timeline.marker.update",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.media_pool_item",
    {
      "commandId": "timeline.media_pool_item",
      "actionId": "cutagent.action.timeline.media_pool_item",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "timeline.node_graph.inspect",
    {
      "commandId": "timeline.node_graph.inspect",
      "actionId": "cutagent.action.timeline.node_graph.inspect",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "timeline.output_blanking.get",
    {
      "commandId": "timeline.output_blanking.get",
      "actionId": "cutagent.action.timeline.output_blanking.get",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "timeline.output_blanking.set",
    {
      "commandId": "timeline.output_blanking.set",
      "actionId": "cutagent.action.timeline.output_blanking.set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "timeline.overlay_stack.insert",
    {
      "commandId": "timeline.overlay_stack.insert",
      "actionId": "cutagent.action.timeline.overlay_stack.insert",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.playhead.get",
    {
      "commandId": "timeline.playhead.get",
      "actionId": "cutagent.action.timeline.playhead.get",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "timeline.playhead.set",
    {
      "commandId": "timeline.playhead.set",
      "actionId": "cutagent.action.timeline.playhead.set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.preview_export",
    {
      "commandId": "timeline.preview_export",
      "actionId": "cutagent.action.timeline.preview_export",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.rename",
    {
      "commandId": "timeline.rename",
      "actionId": "cutagent.action.timeline.rename",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.sdk_live_inspect",
    {
      "commandId": "timeline.sdk_live_inspect",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "timeline.set_start_tc",
    {
      "commandId": "timeline.set_start_tc",
      "actionId": "cutagent.action.timeline.set_start_tc",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.settings",
    {
      "commandId": "timeline.settings",
      "actionId": "cutagent.action.timeline.settings",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "timeline.settings_get",
    {
      "commandId": "timeline.settings_get",
      "actionId": null,
      "aliasOf": "timeline.settings",
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "timeline.settings_set",
    {
      "commandId": "timeline.settings_set",
      "actionId": "cutagent.action.timeline.settings_set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.start_tc",
    {
      "commandId": "timeline.start_tc",
      "actionId": "cutagent.action.timeline.start_tc",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.stereo_convert",
    {
      "commandId": "timeline.stereo_convert",
      "actionId": "cutagent.action.timeline.stereo_convert",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "timeline.still.grab_all",
    {
      "commandId": "timeline.still.grab_all",
      "actionId": "cutagent.action.timeline.still.grab_all",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.subtitle.export",
    {
      "commandId": "timeline.subtitle.export",
      "actionId": "cutagent.action.timeline.subtitle.export",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.subtitle.insert",
    {
      "commandId": "timeline.subtitle.insert",
      "actionId": "cutagent.action.timeline.subtitle.insert",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.subtitle.list",
    {
      "commandId": "timeline.subtitle.list",
      "actionId": "cutagent.action.timeline.subtitle.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "timeline.subtitles",
    {
      "commandId": "timeline.subtitles",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "timeline.summarize",
    {
      "commandId": "timeline.summarize",
      "actionId": "cutagent.action.timeline.summarize",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "timeline.switch",
    {
      "commandId": "timeline.switch",
      "actionId": "cutagent.action.timeline.switch",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.sync_clips",
    {
      "commandId": "timeline.sync_clips",
      "actionId": "cutagent.action.timeline.sync_clips",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.thumbnail",
    {
      "commandId": "timeline.thumbnail",
      "actionId": "cutagent.action.timeline.thumbnail",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.track.add",
    {
      "commandId": "timeline.track.add",
      "actionId": "cutagent.action.timeline.track.add",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.track.delete",
    {
      "commandId": "timeline.track.delete",
      "actionId": "cutagent.action.timeline.track.delete",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.track.disable",
    {
      "commandId": "timeline.track.disable",
      "actionId": "cutagent.action.timeline.track.disable",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.track.enable",
    {
      "commandId": "timeline.track.enable",
      "actionId": "cutagent.action.timeline.track.enable",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.track.items",
    {
      "commandId": "timeline.track.items",
      "actionId": "cutagent.action.timeline.track.items",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "timeline.track.list",
    {
      "commandId": "timeline.track.list",
      "actionId": "cutagent.action.timeline.track.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "timeline.track.lock",
    {
      "commandId": "timeline.track.lock",
      "actionId": "cutagent.action.timeline.track.lock",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.track.rename",
    {
      "commandId": "timeline.track.rename",
      "actionId": "cutagent.action.timeline.track.rename",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.track.subtype",
    {
      "commandId": "timeline.track.subtype",
      "actionId": "cutagent.action.timeline.track.subtype",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "timeline.track.unlock",
    {
      "commandId": "timeline.track.unlock",
      "actionId": "cutagent.action.timeline.track.unlock",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "timeline.voice_isolation.get",
    {
      "commandId": "timeline.voice_isolation.get",
      "actionId": "cutagent.action.timeline.voice_isolation.get",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "timeline.voice_isolation.set",
    {
      "commandId": "timeline.voice_isolation.set",
      "actionId": "cutagent.action.timeline.voice_isolation.set",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "transcript.create",
    {
      "commandId": "transcript.create",
      "actionId": "cutagent.action.transcript.create",
      "aliasOf": null,
      "operationClass": "long_running",
      "verificationCategory": "terminal_and_readback"
    }
  ],
  [
    "version",
    {
      "commandId": "version",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "version.create",
    {
      "commandId": "version.create",
      "actionId": "cutagent.action.version.create",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "version.inspect",
    {
      "commandId": "version.inspect",
      "actionId": "cutagent.action.version.inspect",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "version.list",
    {
      "commandId": "version.list",
      "actionId": "cutagent.action.version.list",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "version.prune",
    {
      "commandId": "version.prune",
      "actionId": "cutagent.action.version.prune",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "version.restore",
    {
      "commandId": "version.restore",
      "actionId": "cutagent.action.version.restore",
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "required_unknown"
    }
  ],
  [
    "version.status",
    {
      "commandId": "version.status",
      "actionId": "cutagent.action.version.status",
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "structural_readback"
    }
  ],
  [
    "video.generate",
    {
      "commandId": "video.generate",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "workflow.callback.script.create",
    {
      "commandId": "workflow.callback.script.create",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "workflow.node.check",
    {
      "commandId": "workflow.node.check",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "workflow.plugin.info",
    {
      "commandId": "workflow.plugin.info",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "workflow.plugin.install",
    {
      "commandId": "workflow.plugin.install",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "workflow.plugin.list",
    {
      "commandId": "workflow.plugin.list",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "workflow.plugin.package",
    {
      "commandId": "workflow.plugin.package",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "workflow.plugin.scaffold",
    {
      "commandId": "workflow.plugin.scaffold",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "workflow.plugin.uninstall",
    {
      "commandId": "workflow.plugin.uninstall",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "workflow.plugin.validate",
    {
      "commandId": "workflow.plugin.validate",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "read",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "workflow.script.install",
    {
      "commandId": "workflow.script.install",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ],
  [
    "workflow.ui.scaffold",
    {
      "commandId": "workflow.ui.scaffold",
      "actionId": null,
      "aliasOf": null,
      "operationClass": "mutation",
      "verificationCategory": "not_applicable"
    }
  ]
]));
