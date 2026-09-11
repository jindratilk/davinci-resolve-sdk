"""Capability registry and schema metadata."""

from __future__ import annotations

from copy import deepcopy

from .multicam_support import build_multicam_support_matrix

CAPABILITIES_SCHEMA_VERSION = "1.14.35"

_BASE_CAPABILITIES: dict[str, dict[str, list[str]]] = {
    "supported": {
        "dctl": ["encrypt"],
        "video": ["generation"],
        "transcript": [
            "create",
        ],
        "audio": [
            "beat_detection",
            "voiceover",
        ],
        "asset": [
            "resolve",
            "artifact_index",
        ],
        "project": [
            "create",
            "delete",
            "open",
            "close",
            "list",
            "settings_read",
            "import_drp",
            "settings_write",
            "export_drp",
            "preset_list",
            "preset_load",
            "folder_management",
            "archive_restore",
            "db_switch",
            "cleanup_scratch",
            "preset_save",
            "preset_delete",
            "preset_import_export",
            "cloud.create",
            "cloud.open",
            "cloud.import",
            "cloud.restore",
        ],
        "timeline": [
            "create",
            "delete",
            "rename",
            "switch",
            "list",
            "marker_crud",
            "track_management",
            "import_export",
            "inspection_export",
            "settings_write",
            "output_blanking",
            "playhead_set",
            "compound_clip",
            "grab_still",
            "set_start_tc",
            "item_at",
            "transcription",
            "scene_cuts_native",
            "stereo_convert",
            "clip_thumbnail",
            "items_delete",
            "item_duration_set",
            "item_move",
            "layer.ensure_media",
            "layout_planning",
            "overlay_stack",
            "insert_generator",
            "insert_title",
            "dolby_vision",
            "frame_export",
            "frame_export_batch",
            "preview_export",
            "sync_clips",
            "subtitle_list_add_export",
            "subtitle_arbitrary_insert",
            "clip_color_batch",
            "duplicate",
            "thumbnail",
        ],
        "media": [
            "import",
            "list",
            "search",
            "append",
            "folder_management",
            "clip_management",
            "metadata_write",
            "marker_crud",
            "flag_color",
            "folder_move_delete",
            "duplicate",
            "unlink_relink",
            "proxy_transcode",
            "create_timeline",
            "stereo_clip",
            "audio_sync",
            "audio_mapping",
            "mark_in_out",
            "extract_template",
        ],
        "clip": [
            "list_read",
            "properties_write",
            "color_flag",
            "flag",
            "transform",
            "composite",
            "speed",
            "enable_disable",
            "rename",
            "fusion_comp",
            "marker",
            "take",
            "link_unlink",
            "stabilize",
            "voice_isolation",
            "export_lut",
            "linked_items",
            "track_info",
            "cache_control",
            "audio_channel_mapping",
            "stereo_values",
            "freeze",
            "reverse",
            "audio_eq",
            "audio_normalize",
            "audio_gain",
            "audio_pan",
            "audio_pitch",
            "fade_in",
            "dynamic_zoom",
            "keyframes",
            "keyframe_crud",
        ],
        "render": [
            "formats",
            "codecs",
            "resolutions",
            "presets",
            "settings_read",
            "settings_write",
            "add",
            "start",
            "status",
            "wait",
            "cancel",
            "custom_range",
            "queue_delete",
            "mode_set",
            "preset_load",
            "preset_save",
            "audio_only",
            "quick_export",
            "burnin_preset_import_export",
            "archive_settings",
            "preset_import_export",
        ],
        "fusion": [
            "comp_add_delete_import_export",
            "tool_list_get_set",
            "keyframes",
            "effects_primitives",
            "mutation",
            "setting_insert",
            "setting_inspect",
            "setting_validate",
            "setting_summary",
            "setting_coords",
            "setting_generation",
            "template_management",
        ],
        "color": [
            "lut_set_clear",
            "grade_copy_apply",
            "source_remote_grade",
            "gallery_stills",
            "gallery_power_grade_list_album",
            "color_group_management",
            "node_graph_ops",
            "gallery_stills_crud",
            "grade_apply_drx",
            "cdl_set",
            "page_wheel_set",
            "wheels_emulation",
            "page_primary_set",
            "power_grade_template_apply",
            "page_still_match",
            "page_sky_isolation_gui",
            "page_scope_set_gui",
            "page_sat_curve_gui_spline",
            "page_resolvefx_param_set",
            "page_resolvefx_param_list",
            "page_resolvefx_param_discover",
            "page_qualifier_panel_probe",
            "page_qualifier_matte_refinement",
            "page_qualifier_gui_matte_set",
            "page_qualifier_gui_hsl_set",
            "page_primary_gui_set",
            "page_power_window_track",
            "page_power_window_gui_set",
            "page_node_cleanup_general",
            "page_node_add_arbitrary_topology",
            "page_hue_curve_gui_spline",
            "page_hdr_detail_controls",
            "page_curve_spline_freeform",
            "page_color_warper",
            "page_color_slice",
            "page_cat_set",
            "hdr_palette",
            "page_curve_set",
            "page_curve_points_set",
            "page_split_tone_set",
            "page_hsv_node_set",
            "page_hue_curve_set",
            "page_sat_curve_set",
            "page_hdr_global_set",
            "page_hdr_zone_set",
            "page_hdr_detail_set",
            "page_key_output_set",
            "page_alpha_output_connect",
            "page_rgb_mixer_monochrome",
            "page_layer_mixer_composite",
            "page_layer_mixer_opacity",
            "page_bleach_bypass",
            "page_bleach_bypass_intensity",
            "page_node_add_serial",
            "page_node_add_parallel",
            "page_node_add_layer",
            "page_node_cleanup_empty_serial",
            "page_cst_set",
            "page_power_window_circle",
            "page_power_window_gradient",
            "page_power_window_gradient_transform",
            "page_power_window_circle_detail",
            "page_power_window_overlay_transform",
            "page_power_window_linear",
            "page_power_window_rectangle",
            "page_power_window_polygon",
            "page_power_window_curve",
            "page_param_delete",
            "page_scope_read",
            "page_false_color_read",
            "page_viewer_before_after",
            "page_shot_match_analyze",
            "page_shot_match_apply",
            "page_qualifier_sample",
            "page_white_balance_picker",
            "page_lut_library_import",
            "page_dctl_apply",
            "page_dctl_remove",
            "page_ofx_glow_set",
            "page_sharpen_set",
            "page_softening_set",
            "page_resolvefx_list",
            "page_resolvefx_add",
            "page_resolvefx_remove",
            "page_magic_mask",
            "power_grade_apply",
            "thumbnail",
            "arri_cdl_lut_helper",
            "curves_lut",
        ],
        "page": [
            "navigation",
        ],
        "fairlight": [
            "adr_read",
            "ai_read",
            "bus_read",
            "channel_mapping_read",
            "clip_effect_list",
            "clip_effect_params",
            "track_effect_catalog",
            "recording_read",
            "patch_io_read",
            "audio_export",
            "audio_gain_batch",
            "audio_pan_batch",
            "automation_read",
            "bounce",
            "bus_routing",
            "clip_delete",
            "clip_split",
            "crossfade_batch",
            "dialogue_leveler",
            "dynamics",
            "eq",
            "elastic_wave",
            "elastic_wave_enable",
            "elastic_wave_read",
            "external_process_read",
            "fade_in_batch",
            "fade_out_batch",
            "fader",
            "group_read",
            "index_read",
            "insert",
            "loudness_read",
            "metering_read",
            "mixer_read",
            "monitoring_read",
            "music_remixer",
            "plugin_catalog_read",
            "plugin_slot_probe",
            "preset_list",
            "item_source_patch",
            "stereo_track_management",
            "sends_read",
            "sound_library_delete",
            "sound_library_index",
            "sound_library_read",
            "sound_library",
            "solo",
            "timeline_voice_isolation",
            "track_management",
            "track_color",
            "track_state",
            "track_format_write",
            "track_info",
            "track_reorder",
            "transition",
            "vca_read",
            "waveform_view_read",
        ],
        "storage": [
            "import",
            "list",
        ],
        "system": [
            "launch_headless",
            "resolve_quit",
            "layout_preset",
            "lut_refresh",
            "lut_management",
            "keyframe_mode",
            "keyboard_preset_read",
            "keyboard_preset_management",
            "export_frame_still",
            # insert_audio_fairlight removed: redundant with fairlight.insert
        ],
        "version": [
            "checkpoint",
        ],
        "edit": [
            "insert_overwrite",
            "blade_native",
            "razor_native",
            "transitions_native",
            "multicam_native_create",
            "multicam_native_switch",
            "multicam_podcast_auto",
            "audio_duck_sidechain",
            "speed_ramp_workaround",
            "delete_through_edit",
            "trim_workaround",
        ],
        "auto_edit": [
            "silence_cut",
        ],
        "text": [
            "insert",
            "insert_preset",
            "insert_template",
            "insert_template_batch",
            "insert_captions",
            "update",
            "inspect",
            "list_presets",
        ],
        "multicam": [
            "audio_activity_calibrate",
            "angle.remove",
            "angle.rename",
            "angle.set_enabled",
            "convert",
            "create",
            "flatten",
            "match_frame",
            "recover_timing",
            "replace_audio",
            "replace_video",
            "reorder_angles",
            "seed_timeline",
            "timeline_create",
            "switch",
            "strip_embedded_audio",
            "job_execute",
            "inspect",
            "settings",
            "set_start_timecode",
            "smart_switch",
            "source.move",
            "source.property_set",
            "source.raw_braw_set",
            "source.remove",
            "verdict_set",
            "verdict_clear",
        ],
        "ai_neural": [
            "auto_color_ai",
        ],
    },
    "partial": {
        "color": [
            "tracker",
            "qualifier",
            "power_windows",
            "page_rgb_mixer_coefficients",
            "page_magic_mask_refinement",
            "page_hsv_node_target",
            "page_bleach_bypass_parametric",
            "curves",
        ],
        "edit": [
            "remove_remove_range",
            "slip_slide",
            "ripple_roll_trim_native",
            "ofx_resolvefx_native",
            "multicam_orchestration",
            "batch_recipe_pipeline",
        ],
        "fairlight": [
            "automation",
            "builtin_effect_route",
            "channel_mapping_write",
            "clip_effect_param_write",
            "clip_move",
            "clip_slip",
            "clip_trim",
            "pan",
            "preset",
            "track_duplicate",
            "track_height",
        ],
        "timeline": [
        ],
        "clip": [
            "smart_reframe",
        ],
        "multicam": [
        ],
        "project": [
            "db_create",
            "db_backup",
            "db_restore",
        ],
        "render": [
        ],
        "ai_neural": [
            "face_refinement",
        ],
    },
    "unsupported": {
        "color": [
            "page_sky_isolation_layer",
        ],
        "edit": [
        ],
        "fairlight": [
            "adr",
            "external_process",
            "groups",
            "loudness",
            "metering",
            "monitoring",
            "plugin_routing",
            "patch_io",
            "input_monitoring",
            "recording",
            "sends",
            "sound_library_audition",
            "track_folder",
            "track_visibility",
            "vca",
            "waveform_editing",
        ],
        "timeline": [
        ],
        "ai_neural": [
        ],
        "clip": [
            "magic_mask",
        ],
        "multicam": [
            "source.grade_cdl",
        ],
    },
}

_ENGINE_CONFIDENCE = {
    "api_native": 1.0,
    "fusion_native": 1.0,
    "hosted_api": 1.0,
    "db_direct": 0.85,
    "db_workaround": 0.9,
    "workaround_setting": 0.75,
    "resolve_gui": 0.65,
    "not_available": 0.0,
}

_FEATURE_TRANSPORT_OVERRIDES = {
    "dctl.encrypt": ["studio_external"],
    "system.resolve_quit": ["studio_external", "embedded_free"],
    "edit.trim_workaround": ["studio_external"],
}

_FEATURE_ENGINE_OVERRIDES = {
    "dctl.encrypt": "api_native",
    "audio.beat_detection": "workaround_setting",
    "audio.voiceover": "hosted_api",
    "video.generation": "hosted_api",
    "timeline.scene_cuts_native": "api_native",
    "timeline.thumbnail": "workaround_setting",
    "timeline.frame_export": "api_native",
    "timeline.frame_export_batch": "api_native",
    "timeline.preview_export": "api_native",
    "timeline.clip_color_batch": "api_native",
    "timeline.layout_planning": "api_native",
    "timeline.layer.ensure_media": "api_native",
    "timeline.overlay_stack": "workaround_setting",
    "fusion.setting_insert": "workaround_setting",
    "media.extract_template": "api_native",
    "edit.insert_overwrite": "api_native",
    "edit.blade_native": "db_workaround",
    "auto_edit.silence_cut": "workaround_setting",
    "edit.transitions_native": "api_native",
    "edit.audio_duck_sidechain": "workaround_setting",
    "edit.delete_through_edit": "db_workaround",
    "edit.trim_workaround": "db_workaround",
    "edit.ofx_resolvefx_native": "fusion_native",
    "edit.speed_ramp_workaround": "db_workaround",
    "text.insert": "workaround_setting",
    "text.insert_template": "workaround_setting",
    "text.insert_template_batch": "workaround_setting",
    "text.insert_captions": "workaround_setting",
    "text.update": "api_native",
    "text.inspect": "api_native",
    "text.list_presets": "api_native",
    "edit.multicam_native_create": "db_workaround",
    "edit.multicam_native_switch": "db_workaround",
    "edit.multicam_podcast_auto": "db_workaround",
    "multicam.create": "db_workaround",
    "multicam.convert": "db_workaround",
    "multicam.flatten": "db_workaround",
    "multicam.match_frame": "db_direct",
    "multicam.angle.remove": "db_workaround",
    "multicam.angle.rename": "db_workaround",
    "multicam.angle.set_enabled": "db_workaround",
    "multicam.audio_activity_calibrate": "api_native",
    "multicam.inspect": "db_direct",
    "multicam.recover_timing": "db_workaround",
    "multicam.replace_audio": "db_workaround",
    "multicam.replace_video": "db_workaround",
    "multicam.reorder_angles": "db_workaround",
    "multicam.seed_timeline": "db_workaround",
    "multicam.timeline_create": "db_workaround",
    "multicam.switch": "db_workaround",
    "multicam.strip_embedded_audio": "db_workaround",
    "multicam.settings": "api_native",
    "multicam.set_start_timecode": "db_workaround",
    "multicam.smart_switch": "db_workaround",
    "multicam.source.move": "db_workaround",
    "multicam.source.property_set": "api_native",
    "multicam.source.raw_braw_set": "api_native",
    "multicam.source.remove": "db_workaround",
    "multicam.verdict_set": "api_native",
    "multicam.verdict_clear": "api_native",
    "multicam.job_execute": "db_workaround",
    "clip.speed": "db_workaround",
    "clip.dynamic_zoom": "workaround_setting",
    "clip.keyframe_crud": "db_workaround",
    "clip.keyframes": "db_workaround",
    "clip.freeze": "db_workaround",
    "clip.reverse": "db_workaround",
    "clip.audio_eq": "db_workaround",
    "clip.audio_normalize": "api_native",
    "clip.audio_gain": "api_native",
    "clip.audio_pan": "api_native",
    "clip.audio_pitch": "api_native",
    "clip.fade_in": "api_native",
    "fairlight.dialogue_leveler": "db_workaround",
    "fairlight.music_remixer": "db_workaround",
    "fairlight.ai_read": "db_workaround",
    "fairlight.adr_read": "db_workaround",
    "fairlight.audio_gain_batch": "db_workaround",
    "fairlight.audio_pan_batch": "db_workaround",
    "fairlight.automation": "db_workaround",
    "fairlight.automation_read": "db_workaround",
    "fairlight.bounce": "api_native",
    "fairlight.bus_read": "db_workaround",
    "fairlight.bus_routing": "db_workaround",
    "fairlight.clip_effect_list": "db_workaround",
    "fairlight.clip_effect_param_write": "db_workaround",
    "fairlight.clip_effect_params": "db_workaround",
    "fairlight.track_effect_catalog": "db_workaround",
    "fairlight.clip_delete": "api_native",
    "fairlight.clip_move": "db_workaround",
    "fairlight.clip_slip": "db_workaround",
    "fairlight.clip_split": "db_workaround",
    "fairlight.clip_trim": "db_workaround",
    "fairlight.crossfade_batch": "db_workaround",
    "fairlight.channel_mapping_read": "api_native",
    "fairlight.channel_mapping_write": "api_native",
    "fairlight.builtin_effect_route": "db_workaround",
    "fairlight.dynamics": "db_workaround",
    "fairlight.eq": "db_workaround",
    "fairlight.elastic_wave_enable": "db_workaround",
    "fairlight.elastic_wave_read": "db_workaround",
    "fairlight.elastic_wave": "db_workaround",
    "fairlight.external_process_read": "workaround_setting",
    "fairlight.fade_in_batch": "db_workaround",
    "fairlight.fade_out_batch": "db_workaround",
    "fairlight.fader": "db_workaround",
    "fairlight.group_read": "db_workaround",
    "fairlight.index_read": "db_workaround",
    "fairlight.loudness_read": "db_workaround",
    "fairlight.metering_read": "db_workaround",
    "fairlight.mixer_read": "db_workaround",
    "fairlight.monitoring_read": "db_workaround",
    "fairlight.pan": "db_workaround",
    "fairlight.plugin_catalog_read": "workaround_setting",
    "fairlight.plugin_slot_probe": "db_workaround",
    "fairlight.preset_list": "api_native",
    "fairlight.item_source_patch": "db_workaround",
    "fairlight.patch_io_read": "db_workaround",
    "fairlight.recording_read": "db_workaround",
    "fairlight.sends_read": "db_workaround",
    "fairlight.solo": "api_native",
    "fairlight.sound_library_delete": "db_workaround",
    "fairlight.sound_library_index": "db_workaround",
    "fairlight.sound_library_read": "db_workaround",
    "fairlight.stereo_track_management": "db_workaround",
    "fairlight.timeline_voice_isolation": "api_native",
    "fairlight.track_management": "api_native",
    "fairlight.track_color": "db_workaround",
    "fairlight.track_duplicate": "api_native",
    "fairlight.track_folder": "not_available",
    "fairlight.track_format_write": "db_workaround",
    "fairlight.track_height": "db_workaround",
    "fairlight.track_info": "db_workaround",
    "fairlight.track_reorder": "db_workaround",
    "fairlight.transition": "db_workaround",
    "fairlight.vca_read": "db_workaround",
    "fairlight.waveform_view_read": "db_workaround",
    "render.archive_settings": "api_native",
    "color.grade_copy_apply": "db_workaround",
    "color.source_remote_grade": "api_native",
    "color.lut_set_clear": "workaround_setting",
    "color.cdl_set": "db_workaround",
    "color.wheels_emulation": "db_workaround",
    "color.page_wheel_set": "db_workaround",
    "color.page_primary_set": "db_workaround",
    "color.page_curve_set": "db_workaround",
    "color.page_curve_points_set": "db_workaround",
    "color.page_split_tone_set": "db_workaround",
    "color.page_hsv_node_set": "db_workaround",
    "color.page_hue_curve_set": "db_workaround",
    "color.page_sat_curve_set": "db_workaround",
    "color.page_hdr_global_set": "db_workaround",
    "color.page_hdr_zone_set": "db_workaround",
    "color.page_hdr_detail_set": "db_workaround",
    "color.page_key_output_set": "db_workaround",
    "color.page_alpha_output_connect": "db_workaround",
    "color.page_rgb_mixer_monochrome": "db_workaround",
    "color.page_layer_mixer_composite": "db_workaround",
    "color.page_layer_mixer_opacity": "db_workaround",
    "color.page_bleach_bypass": "db_workaround",
    "color.page_bleach_bypass_intensity": "db_workaround",
    "color.page_node_add_serial": "db_workaround",
    "color.page_node_add_parallel": "db_workaround",
    "color.page_node_add_layer": "db_workaround",
    "color.page_node_cleanup_empty_serial": "db_workaround",
    "color.page_cst_set": "db_workaround",
    "color.page_power_window_circle": "db_workaround",
    "color.page_power_window_gradient": "db_workaround",
    "color.page_power_window_gradient_transform": "db_workaround",
    "color.page_power_window_circle_detail": "db_workaround",
    "color.page_power_window_overlay_transform": "db_workaround",
    "color.page_power_window_linear": "db_workaround",
    "color.page_power_window_rectangle": "db_workaround",
    "color.page_power_window_polygon": "db_workaround",
    "color.page_power_window_curve": "db_workaround",
    "color.page_param_delete": "db_workaround",
    "color.page_scope_read": "api_native",
    "color.page_false_color_read": "api_native",
    "color.page_viewer_before_after": "api_native",
    "color.page_shot_match_analyze": "api_native",
    "color.page_shot_match_apply": "db_workaround",
    "color.page_qualifier_sample": "api_native",
    "color.page_white_balance_picker": "db_workaround",
    "color.page_lut_library_import": "workaround_setting",
    "color.page_dctl_apply": "workaround_setting",
    "color.page_dctl_remove": "workaround_setting",
    "color.page_ofx_glow_set": "workaround_setting",
    "color.page_sharpen_set": "workaround_setting",
    "color.page_softening_set": "workaround_setting",
    "color.page_resolvefx_list": "api_native",
    "color.page_resolvefx_add": "db_workaround",
    "color.page_resolvefx_remove": "db_workaround",
    "color.page_magic_mask": "resolve_gui",
    "color.power_grade_apply": "db_workaround",
    "color.thumbnail": "workaround_setting",
    "color.curves_lut": "workaround_setting",
    "timeline.item_duration_set": "db_workaround",
    "timeline.item_move": "db_workaround",
    "timeline.duplicate": "api_native",
    "timeline.subtitle_list_add_export": "api_native",
    "version.checkpoint": "db_workaround",
    "ai_neural.auto_color_ai": "resolve_gui",
    "ai_neural.face_refinement": "db_workaround",
    "color.curves": "db_workaround",
    "color.hdr_palette": "db_workaround",
    "color.page_bleach_bypass_parametric": "db_workaround",
    "color.page_cat_set": "fusion_native",
    "color.page_color_slice": "resolve_gui",
    "color.page_color_warper": "db_workaround",
    "color.page_curve_spline_freeform": "db_workaround",
    "color.page_hdr_detail_controls": "db_workaround",
    "color.page_hsv_node_target": "db_workaround",
    "color.page_hue_curve_gui_spline": "db_workaround",
    "color.page_magic_mask_refinement": "resolve_gui",
    "color.page_node_add_arbitrary_topology": "db_workaround",
    "color.page_node_cleanup_general": "db_workaround",
    "color.page_power_window_gui_set": "resolve_gui",
    "color.page_power_window_track": "resolve_gui",
    "color.page_primary_gui_set": "resolve_gui",
    "color.page_qualifier_gui_hsl_set": "resolve_gui",
    "color.page_qualifier_gui_matte_set": "resolve_gui",
    "color.page_qualifier_matte_refinement": "db_workaround",
    "color.page_qualifier_panel_probe": "resolve_gui",
    "color.page_resolvefx_param_discover": "api_native",
    "color.page_resolvefx_param_list": "db_direct",
    "color.page_resolvefx_param_set": "db_workaround",
    "color.page_rgb_mixer_coefficients": "db_workaround",
    "color.page_sat_curve_gui_spline": "db_workaround",
    "color.page_scope_set_gui": "resolve_gui",
    "color.page_sky_isolation_gui": "resolve_gui",
    "color.page_sky_isolation_layer": "not_available",
    "color.page_still_match": "resolve_gui",
    "color.power_grade_template_apply": "db_workaround",
    "color.power_windows": "db_workaround",
    "color.qualifier": "db_workaround",
    "color.tracker": "fusion_native",
    "edit.razor_native": "db_workaround",
    "edit.remove_remove_range": "api_native",
    "edit.ripple_roll_trim_native": "api_native",
    "edit.slip_slide": "resolve_gui",
    "timeline.subtitle_arbitrary_insert": "api_native",
    "project.db_create": "db_workaround",
    "project.db_backup": "db_workaround",
    "project.db_restore": "db_workaround",
}

# Alternate mutation engines that a command may select only after the primary
# route fails safely. These are part of the advertised capability contract so
# policy admission can cover the strongest possible route before execution.
_FEATURE_FALLBACK_ENGINE_OVERRIDES = {
    "fairlight.channel_mapping_write": ["db_workaround"],
    "edit.transitions_native": ["db_workaround"],
    "clip.audio_normalize": ["db_workaround"],
    "clip.audio_gain": ["db_workaround"],
    "clip.audio_pan": ["db_workaround"],
    "clip.audio_pitch": ["db_workaround"],
    "clip.fade_in": ["db_workaround"],
    "clip.fusion_comp": ["db_workaround"],
}

_FEATURE_VERIFICATION_OVERRIDES = {
    "dctl.encrypt": True,
    "project.preset_delete": True,
    "project.preset_import_export": True,
    "edit.insert_overwrite": True,
    "edit.blade_native": True,
    "edit.trim_workaround": True,
    "auto_edit.silence_cut": True,
    "edit.transitions_native": True,
    "edit.delete_through_edit": True,
    "fairlight.adr_read": False,
    "fairlight.audio_export": True,
    "fairlight.audio_gain_batch": True,
    "fairlight.audio_pan_batch": True,
    "fairlight.automation_read": False,
    "fairlight.bounce": True,
    "fairlight.bus_read": True,
    "fairlight.clip_effect_list": False,
    "fairlight.clip_effect_param_write": False,
    "fairlight.clip_effect_params": False,
    "fairlight.track_effect_catalog": False,
    "fairlight.clip_delete": True,
    "fairlight.clip_move": False,
    "fairlight.clip_slip": False,
    "fairlight.clip_split": True,
    "fairlight.clip_trim": False,
    "fairlight.crossfade_batch": True,
    "fairlight.dialogue_leveler": True,
    "fairlight.music_remixer": True,
    "fairlight.ai_read": False,
    "fairlight.automation": True,
    "fairlight.bus_routing": True,
    "fairlight.builtin_effect_route": True,
    "fairlight.dynamics": True,
    "fairlight.eq": True,
    "fairlight.elastic_wave_enable": True,
    "fairlight.elastic_wave_read": False,
    "fairlight.elastic_wave": True,
    "fairlight.external_process_read": False,
    "fairlight.fade_in_batch": True,
    "fairlight.fade_out_batch": True,
    "fairlight.fader": True,
    "fairlight.group_read": False,
    "fairlight.index_read": False,
    "fairlight.loudness_read": False,
    "fairlight.metering_read": False,
    "fairlight.mixer_read": True,
    "fairlight.monitoring_read": False,
    "fairlight.pan": False,
    "fairlight.plugin_catalog_read": False,
    "fairlight.plugin_slot_probe": False,
    "fairlight.preset_list": False,
    "fairlight.item_source_patch": True,
    "fairlight.patch_io_read": False,
    "fairlight.plugin_routing": True,
    "fairlight.recording_read": False,
    "fairlight.sends_read": False,
    "fairlight.solo": False,
    "fairlight.sound_library": True,
    "fairlight.sound_library_delete": True,
    "fairlight.sound_library_index": True,
    "fairlight.sound_library_read": False,
    "fairlight.stereo_track_management": True,
    "fairlight.timeline_voice_isolation": True,
    "fairlight.track_management": False,
    "fairlight.track_state": False,
    "fairlight.track_color": True,
    "fairlight.track_duplicate": True,
    "fairlight.track_height": False,
    "fairlight.track_folder": False,
    "fairlight.track_format_write": True,
    "fairlight.track_info": True,
    "fairlight.track_reorder": True,
    "fairlight.transition": True,
    "fairlight.vca_read": False,
    "fairlight.waveform_view_read": False,
    "color.page_wheel_set": True,
    "color.page_primary_set": True,
    "color.page_curve_set": True,
    "color.page_curve_points_set": True,
    "color.page_split_tone_set": True,
    "color.page_hsv_node_set": True,
    "color.page_hue_curve_set": True,
    "color.page_sat_curve_set": True,
    "color.page_hdr_global_set": True,
    "color.page_hdr_zone_set": True,
    "color.page_hdr_detail_set": True,
    "color.page_key_output_set": True,
    "color.page_alpha_output_connect": True,
    "color.page_rgb_mixer_monochrome": True,
    "color.page_node_add_serial": True,
    "color.page_node_add_parallel": True,
    "color.page_node_add_layer": True,
    "color.page_node_cleanup_empty_serial": True,
    "color.page_cst_set": True,
    "color.page_power_window_circle": True,
    "color.page_power_window_gradient": True,
    "color.page_power_window_gradient_transform": True,
    "color.page_power_window_circle_detail": True,
    "color.page_power_window_overlay_transform": True,
    "color.page_power_window_linear": True,
    "color.page_power_window_rectangle": True,
    "color.page_power_window_polygon": True,
    "color.page_power_window_curve": True,
    "color.page_param_delete": True,
    "color.page_scope_read": True,
    "color.page_false_color_read": True,
    "color.page_viewer_before_after": True,
    "color.page_shot_match_analyze": True,
    "color.page_shot_match_apply": True,
    "color.page_qualifier_sample": True,
    "color.page_white_balance_picker": True,
    "color.page_lut_library_import": True,
    "color.page_dctl_apply": True,
    "color.page_dctl_remove": True,
    "color.page_ofx_glow_set": True,
    "color.page_sharpen_set": True,
    "color.page_softening_set": True,
    "color.page_resolvefx_add": True,
    "color.page_resolvefx_remove": True,
    "color.page_magic_mask": True,
    "color.power_grade_apply": True,
    "clip.fade_in": True,
    "timeline.clip_color_batch": True,
    "timeline.item_duration_set": True,
    "timeline.item_move": True,
    "timeline.layout_planning": True,
    "timeline.layer.ensure_media": True,
    "timeline.overlay_stack": True,
    "fusion.setting_insert": True,
    "media.extract_template": True,
    "timeline.duplicate": True,
    "timeline.subtitle_list_add_export": True,
    "version.checkpoint": True,
    "project.db_create": True,
    "project.db_backup": True,
    "project.db_restore": True,
    "project.preset_save": True,
    "project.preset_delete": True,
    "project.preset_import_export": True,
    "text.insert": True,
    "text.insert_preset": True,
    "text.insert_template": True,
    "text.insert_template_batch": True,
    "text.insert_captions": True,
    "text.update": True,
    "ai_neural.auto_color_ai": True,
    "ai_neural.face_refinement": True,
    "color.curves": True,
    "color.hdr_palette": True,
    "color.page_bleach_bypass_parametric": True,
    "color.page_cat_set": True,
    "color.page_color_slice": True,
    "color.page_curve_spline_freeform": True,
    "color.page_hdr_detail_controls": True,
    "color.page_hsv_node_target": True,
    "color.page_hue_curve_gui_spline": True,
    "color.page_magic_mask_refinement": True,
    "color.page_node_add_arbitrary_topology": True,
    "color.page_node_cleanup_general": True,
    "color.page_power_window_gui_set": True,
    "color.page_power_window_track": True,
    "color.page_primary_gui_set": True,
    "color.page_qualifier_gui_hsl_set": True,
    "color.page_qualifier_gui_matte_set": True,
    "color.page_qualifier_panel_probe": True,
    "color.page_resolvefx_param_discover": True,
    "color.page_resolvefx_param_list": True,
    "color.page_resolvefx_param_set": True,
    "color.page_rgb_mixer_coefficients": True,
    "color.page_sat_curve_gui_spline": True,
    "color.page_scope_set_gui": True,
    "color.page_sky_isolation_gui": True,
    "color.page_sky_isolation_layer": False,
    "color.page_still_match": True,
    "color.power_grade_template_apply": True,
    "color.power_windows": True,
    "color.qualifier": True,
    "color.tracker": True,
    "edit.razor_native": True,
    "edit.remove_remove_range": True,
    "edit.ripple_roll_trim_native": True,
    "edit.slip_slide": True,
    "project.cleanup_scratch": True,
    "timeline.subtitle_arbitrary_insert": True,
}

_FEATURE_RECOVERABILITY_OVERRIDES = {
    "dctl.encrypt": "manual",
    "edit.insert_overwrite": "manual",
    "edit.blade_native": "manual",
    "edit.remove_remove_range": "manual",
    "auto_edit.silence_cut": "manual",
    "timeline.duplicate": "manual",
    "timeline.item_duration_set": "manual",
    "timeline.item_move": "manual",
    "timeline.clip_color_batch": "manual",
    "timeline.layer.ensure_media": "manual",
    "media.extract_template": "manual",
    "timeline.subtitle_list_add_export": "manual",
    "fairlight.item_source_patch": "manual",
    "fairlight.dialogue_leveler": "manual",
    "fairlight.music_remixer": "manual",
    "fairlight.automation": "manual",
    "fairlight.bus_routing": "manual",
    "fairlight.builtin_effect_route": "manual",
    "fairlight.dynamics": "manual",
    "fairlight.eq": "manual",
    "fairlight.fader": "manual",
    "fairlight.pan": "manual",
    "fairlight.plugin_routing": "manual",
    "fairlight.sound_library_delete": "manual",
    "fairlight.sound_library_index": "manual",
    "fairlight.timeline_voice_isolation": "manual",
    "version.checkpoint": "manual",
    "project.preset_save": "manual",
    "project.preset_delete": "manual",
    "project.preset_import_export": "manual",
    "render.archive_settings": "manual",
    "render.preset_import_export": "manual",
    "project.cloud.create": "manual",
    "project.cloud.open": "manual",
    "project.cloud.import": "manual",
    "project.cloud.restore": "manual",
    "color.page_magic_mask": "manual",
    "color.page_magic_mask_refinement": "manual",
    "color.page_primary_gui_set": "manual",
    "color.page_qualifier_gui_hsl_set": "manual",
    "color.page_qualifier_gui_matte_set": "manual",
    "color.page_qualifier_panel_probe": "manual",
    "edit.razor_native": "manual",
    "project.cleanup_scratch": "manual",
    "timeline.subtitle_arbitrary_insert": "manual",
}

_FEATURE_RENDER_PROOF_STATUS_OVERRIDES = {
    "dctl.encrypt": "readback_only",
    "multicam.convert": "render_proof_verified",
    "multicam.flatten": "render_proof_verified",
    "multicam.smart_switch": "render_proof_verified",
    "multicam.source.raw_braw_set": "render_proof_verified",
    "color.lut_set_clear": "readback_only",
    "color.grade_copy_apply": "readback_only",
    "color.source_remote_grade": "readback_only",
    "color.grade_apply_drx": "readback_only",
    "color.node_graph_ops": "readback_only",
    "color.cdl_set": "readback_only",
    "color.wheels_emulation": "readback_only",
    "color.page_wheel_set": "readback_only",
    "color.page_primary_set": "readback_only",
    "color.page_curve_set": "readback_only",
    "color.page_curve_points_set": "readback_only",
    "color.page_split_tone_set": "readback_only",
    "color.page_hsv_node_set": "readback_only",
    "color.page_hue_curve_set": "readback_only",
    "color.page_sat_curve_set": "readback_only",
    "color.page_hdr_global_set": "readback_only",
    "color.page_hdr_zone_set": "readback_only",
    "color.page_hdr_detail_set": "readback_only",
    "color.page_key_output_set": "readback_only",
    "color.page_alpha_output_connect": "readback_only",
    "color.page_rgb_mixer_monochrome": "readback_only",
    "color.page_layer_mixer_composite": "readback_only",
    "color.page_layer_mixer_opacity": "readback_only",
    "color.page_bleach_bypass": "readback_only",
    "color.page_bleach_bypass_intensity": "readback_only",
    "color.page_node_add_serial": "readback_only",
    "color.page_node_add_parallel": "readback_only",
    "color.page_node_add_layer": "readback_only",
    "color.page_node_cleanup_empty_serial": "readback_only",
    "color.page_cst_set": "readback_only",
    "color.page_power_window_circle": "readback_only",
    "color.page_power_window_gradient": "readback_only",
    "color.page_power_window_gradient_transform": "readback_only",
    "color.page_power_window_circle_detail": "readback_only",
    "color.page_power_window_overlay_transform": "readback_only",
    "color.page_power_window_linear": "readback_only",
    "color.page_power_window_rectangle": "readback_only",
    "color.page_power_window_polygon": "readback_only",
    "color.page_power_window_curve": "readback_only",
    "color.page_param_delete": "readback_only",
    "color.page_shot_match_apply": "readback_only",
    "color.page_white_balance_picker": "readback_only",
    "color.page_lut_library_import": "readback_only",
    "color.page_dctl_apply": "render_proof_verified",
    "color.page_dctl_remove": "readback_only",
    "color.page_ofx_glow_set": "readback_only",
    "color.page_sharpen_set": "readback_only",
    "color.page_softening_set": "readback_only",
    "color.page_resolvefx_add": "readback_only",
    "color.page_resolvefx_remove": "readback_only",
    "color.power_grade_apply": "readback_only",
    "color.thumbnail": "readback_only",
    "color.curves_lut": "readback_only",
    "color.page_scope_read": "render_proof_verified",
    "color.page_false_color_read": "render_proof_verified",
    "color.page_viewer_before_after": "render_proof_verified",
    "color.page_shot_match_analyze": "render_proof_verified",
    "color.page_qualifier_sample": "render_proof_verified",
    "ai_neural.auto_color_ai": "render_proof_verified",
    "ai_neural.face_refinement": "readback_only",
    "color.hdr_palette": "readback_only",
    "color.page_color_slice": "gui_proof_verified",
    "color.page_curve_spline_freeform": "readback_only",
    "color.page_hdr_detail_controls": "readback_only",
    "color.page_hue_curve_gui_spline": "readback_only",
    "color.page_node_add_arbitrary_topology": "readback_only",
    "color.page_node_cleanup_general": "readback_only",
    "color.page_power_window_gui_set": "readback_only",
    "color.page_primary_gui_set": "render_proof_verified",
    "color.page_qualifier_gui_hsl_set": "render_proof_verified",
    "color.page_qualifier_gui_matte_set": "setup_only",
    "color.page_qualifier_matte_refinement": "readback_only",
    "color.page_resolvefx_param_discover": "readback_only",
    "color.page_resolvefx_param_list": "readback_only",
    "color.page_resolvefx_param_set": "render_proof_verified",
    "color.page_rgb_mixer_coefficients": "readback_only",
    "color.page_sat_curve_gui_spline": "readback_only",
    "color.page_scope_set_gui": "gui_proof_verified",
    "color.page_sky_isolation_gui": "render_proof_verified",
    "color.page_sky_isolation_layer": "unsupported",
    "color.power_grade_template_apply": "readback_only",
}

_BLACKMAGIC_CLOUD_CAVEATS = {
    "requires_cloud_account": True,
    "may_open_resolve_cloud_ui": True,
    "manual_prerequisite": "Sign in to Blackmagic Cloud in DaVinci Resolve before unattended automation.",
}

_FAIRLIGHT_AUTOMATION_CAVEATS = {
    "db_scope": "verified_audio_clip_volume_envelope_point",
    "supported_lanes": ["volume", "level", "gain"],
    "target_route": "exact_audio_clip_at_track_and_record_frame",
    "storage": "Sm2TiItem.EffectFiltersBA audio_gain group 124 parameter 95",
    "readback_route": "exact post-reopen clip-local keyframe decode projected to record frames",
    "unsupported": [
        "track_mixer_automation_lanes",
        "bus_automation_lanes",
        "pan",
        "mute",
        "clip_name_selector",
    ],
}

_FAIRLIGHT_BUS_ROUTING_CAVEATS = {
    "db_scope": "verified_default_output_bus",
    "supported_buses": ["Bus 1"],
    "level_route": "Sm2Sequence.OutputAudioGain",
    "assignment_route": "default_output_verification_noop",
    "unsupported": ["bus_creation", "arbitrary_track_to_bus_routing", "sends", "non_default_buses"],
}

_FAIRLIGHT_DIALOGUE_LEVELER_CAVEATS = {
    "db_scope": "verified_default_clip_fx_seed_and_param_write",
    "supported_subset": ["default_payload_seed", "lifter", "cleaner", "output_gain"],
    "readback_route": "Sm2TiItem.FieldsBlob FL::ClipFX Dialogue Leveler params",
    "render_proof": "/tmp/cutagent_fairlight_ai_payload_probe_20260619/20_public_dialogue_leveler_vs_clean_diff.json",
    "unsupported": [
        "track_or_bus_dialogue_leveler_slots",
        "unmapped_advanced_dialogue_leveler_params",
        "multiple_clip_fx_plugins_on_same_clip",
    ],
}

_FAIRLIGHT_MUSIC_REMIXER_CAVEATS = {
    "db_scope": "verified_default_clip_fx_seed_and_stem_level_write",
    "supported_subset": ["default_payload_seed", "voice", "drums", "bass", "other", "guitar"],
    "readback_route": "Sm2TiItem.FieldsBlob FL::ClipFX Music Remixer params",
    "render_proof": "/tmp/cutagent_music_remixer_probe_20260619/29_public_music_remixer_seed_vs_clean_diff.json",
    "primary_source_boundary": "Blackmagic describes Music Remixer as a Track FX plugin, but this DaVinci Resolve Free runtime also accepts the verified clip-level FL::ClipFX payload subset.",
    "unsupported": [
        "track_or_bus_music_remixer_slots",
        "mute_toggles",
        "multiple_clip_fx_plugins_on_same_clip",
        "studio_only_ai_model_variation",
    ],
    "native_voice_isolation_route": "fairlight.ai.voice_isolation uses TimelineItem.SetVoiceIsolationState/GetVoiceIsolationState via clip.voice_isolation.",
}

_FAIRLIGHT_TIMELINE_VOICE_ISOLATION_CAVEATS = {
    "native_api": [
        "Timeline.GetVoiceIsolationState(trackIndex)",
        "Timeline.SetVoiceIsolationState(trackIndex, state)",
        "TimelineItem.GetVoiceIsolationState()",
    ],
    "verified_runtime": "DaVinci Resolve 21.0.0.48 Free embedded_free",
    "readback_route": "Timeline.GetVoiceIsolationState(trackIndex)",
    "verified_write_scope": "track voice isolation enable/amount with post-write getter readback",
    "related_clip_route": "fairlight.ai.voice_isolation uses TimelineItem.SetVoiceIsolationState/GetVoiceIsolationState through clip.voice_isolation",
}

_FAIRLIGHT_CLIP_MOVE_CAVEATS = {
    "db_scope": "verified_record_position_patch",
    "supported_subset": [
        "absolute_record_move",
        "relative_record_nudge",
        "explicit_audio_only_linked_av_move",
        "native_link_identity_video_companion_move",
    ],
    "readback_route": "live timeline range + Sm2TiItem.Start + protected Project.db structural state",
    "linked_video_scope": "--include-linked-video updates only TimelineItem.GetLinkedItems video companions mapped to exact Project.db item ids; coincident unlinked items are excluded",
    "failure_semantics": "stale/ambiguous native identity, collision, unsupported link membership, or failed mandatory verification aborts or restores the pre-edit Project.db backup",
    "unsupported": [
        "ripple_move_semantics",
        "cross_track_collision_resolution",
        "non_simple_linked_group_move",
        "linked_non_video_companion_groups",
        "layer_or_selection_range_move",
    ],
}

_FAIRLIGHT_CLIP_SLIP_CAVEATS = {
    "db_scope": "verified_source_offset_patch",
    "supported_subset": [
        "single_audio_item_source_slip",
        "explicit_audio_only_linked_av_slip",
        "native_link_identity_video_companion_source_slip",
    ],
    "readback_route": "live timeline range + Sm2TiItem.In + protected Project.db structural state",
    "linked_video_scope": "--include-linked-video applies one exact source-frame delta to native-linked video ids and fails closed when positive-delta source bounds cannot be proved",
    "failure_semantics": "stale/ambiguous native identity, invalid source offset, unsupported link membership, or failed mandatory verification aborts or restores the pre-edit Project.db backup",
    "unsupported": [
        "multi_channel_source_edge_semantics",
        "non_simple_linked_group_slip",
        "linked_non_video_companion_groups",
        "transition_reflow",
        "layer_or_selection_range_slip",
    ],
}

_FAIRLIGHT_CLIP_TRIM_CAVEATS = {
    "db_scope": "verified_item_duration_patch",
    "supported_subset": [
        "single_audio_item_tail_trim",
        "single_audio_item_head_trim",
        "explicit_audio_only_linked_av_trim",
        "native_link_identity_video_companion_tail_trim",
        "native_link_identity_video_companion_head_trim",
    ],
    "readback_route": "live timeline range + Sm2TiItem.Start/Duration/In + protected Project.db structural state",
    "linked_video_scope": "--include-linked-video applies the same edge delta to exact native-linked video ids, preserves differing linked durations, and fails closed on unproved expansion bounds",
    "failure_semantics": "stale/ambiguous native identity, invalid edge/duration, collision, unsupported link membership, or failed mandatory verification aborts or restores the pre-edit Project.db backup",
    "unsupported": [
        "ripple_trim_semantics",
        "crossfade_trim_interaction",
        "non_simple_linked_group_trim",
        "linked_non_video_companion_groups",
        "layer_or_selection_range_trim",
        "source_bound_restore_after_db_shrink_without_no_source_bounds",
    ],
}

_EDIT_TRIM_CAVEATS = {
    "activation_gates": ["windows", "embedded_free"],
    "release_gates": {
        "linked_audio_preserve": "inactive until real DaVinci Resolve mutation, project-reopen, exact-topology, protected-state, and checkpoint-recovery proof passes",
    },
    "preconditions": "saved named local Disk project, active timeline, and authoritative DaVinci Resolve project/timeline unique identity available before mutation and immediately before project close",
    "mutation_scope": "one existing video item plus every exact directly linked reciprocal audio occurrence when preserve mode is selected",
    "semantics": "non_ripple_head_and_or_tail_trim; adjacent items and track counts remain unchanged",
    "selector": "unique video track/name/start/end selector revalidated immediately before project close; no implicit current-selection route",
    "time_domain": "--head and --tail are non-negative duration seconds converted once at the active timeline frame rate",
    "linked_audio_modes": {
        "preserve": "default safety mode; unlinked clips are supported, while clips with direct links fail closed with edit_trim_linked_audio_preservation_release_gated until the implemented atomic linked-video/audio path passes its release proof gate",
        "exclude": "explicit intentional video-only trim; audio rows are protected and verified unchanged, but the DB edge update may sever or change link topology and must not be described as preserving linked media",
    },
    "verification": "after project reopen, every changed video/audio target record/source and authoritative identity must match, preserve mode must prove exact reciprocal link topology from the same authoritative proxies used for target readback, and unrelated video/audio/subtitle items, track counts, and available track name/enabled/locked structure remain unchanged",
    "recovery": "checkpoint-backed recovery attempts to restore the pre-edit project state after reopen or verification failure; if restoration also fails, the error reports manual recovery as required and preserves the backup/recovery-failure truth",
    "unsupported": [
        "ripple_trim_semantics",
        "transition_adjacent_trim",
        "multicam_timeline_items",
        "non_reciprocal_or_record_range_diverged_linked_groups",
        "ambiguous_or_stale_selectors",
        "linked_audio_preservation_until_release_proof",
    ],
}

_FAIRLIGHT_CLIP_EFFECT_PARAM_WRITE_CAVEATS = {
    "native_subset": {
        "effect": "Voice Isolation",
        "param": "DRY_MIX",
        "write": "TimelineItem.SetVoiceIsolationState",
        "readback": "TimelineItem.GetVoiceIsolationState",
        "value_mapping": "DRY_MIX 0.0-1.0 -> amount 0-100",
    },
    "db_scope": "verified_existing_or_create_if_missing_clip_fx_param_write_for_known_clip_fx",
    "create_if_missing_scope": "opt-in insertion of a verified default Sm2TiItem.FieldsBlob FL::ClipFX payload before writing a render-verified parameter",
    "readback_route": "TimelineItem voice-isolation state for native subset; Sm2TiItem.FieldsBlob existing or opt-in inserted clip FX payload for DB subset",
    "unsupported": ["arbitrary_fairlight_plugin_slot_params", "track_or_bus_effect_params", "multi_plugin_clip_fx_param_surgery"],
}

_FAIRLIGHT_PLUGIN_ROUTING_CAVEATS = {
    "db_scope": "negative_track_bus_plugin_slot_model",
    "available_read_routes": ["effect catalog", "effect plugin-catalog", "effect slot-scan"],
    "unsupported": ["third_party_plugins", "plugin_slot_insertion", "plugin_slot_removal", "clip_targeting", "bus_targeting"],
}

_FAIRLIGHT_BUILTIN_EFFECT_ROUTE_CAVEATS = {
    "db_scope": "verified_builtin_current_timeline_processing_and_clip_level_fl_clipfx",
    "supported_effects": {
        "timeline_builtin": ["Dialogue Processor", "Dynamics", "EQ"],
        "clip_level_fl_clipfx": [
            "Voice Isolation",
            "Dialogue Leveler",
            "Dialogue Processor",
            "Music Remixer",
            "Chorus",
            "De-Esser",
            "De-Hummer",
            "Reverb",
            "Distortion",
            "Multiband Compressor",
            "Noise Reduction",
            "Flanger",
            "Echo",
            "Delay",
            "Gain",
            "Vocal Channel",
            "Limiter",
            "Fairlight EQ",
            "Stereo Width",
            "Stereo Fixer",
            "Soft Clipper",
            "Pitch",
            "Modulation",
        ],
    },
    "mutation_route": "Sm2Sequence.FieldsBlob dynamics params; Sm2TiItem.FieldsBlob FL::ClipFX for verified clip-level payloads",
    "unsupported": [
        "third_party_plugins",
        "track_or_bus_plugin_slot_insertion",
        "track_or_bus_plugin_slot_removal",
        "unsupported_clip_fx_payloads",
        "bus_targeting",
    ],
}

_FAIRLIGHT_ELASTIC_WAVE_CAVEATS = {
    "db_scope": "verified_audio_timemap_stretch_and_algorithm_payloads",
    "supported_subset": [
        "voice_algorithm_enable",
        "general_purpose_algorithm_enable",
        "varispeed_algorithm_enable",
        "whole_clip_ratio_stretch",
        "explicit_segment_timemap_points",
    ],
    "readback_route": "Sm2TiItem.MediaTimemapBA + Sm2TiItem.FieldsBlob.FL::Retimer",
    "proof_status": "real_audio_db_readback_render_pitch_click_timing_gui_timing_point_and_gui_algorithm_payload_verified",
    "unsupported": ["pitch_preservation_storage_flag"],
}

_FAIRLIGHT_PAN_CAVEATS = {
    "db_scope": "verified_mono_and_stereo_track_2d_pan",
    "storage": [
        "channel_lane_pan_int32_x10",
        "fairlight_mixer_record_table_pan_int32_x10",
        "fairlight_mixer_compact_param_records_pan_int32_x10",
    ],
    "read_scope": "mono/stereo/multichannel lane readback when the decoded lane model is in-range",
    "write_scope": "mono_track_pan_and_stereo_track_left_right_balance",
    "unsupported": ["surround_track_pan_write", "adaptive_track_pan_write", "3d_panner_angle_spread_divergence", "bus_pan_write"],
}

_FAIRLIGHT_PRESET_CAVEATS = {
    "native_readback": "Resolve.GetFairlightPresets()",
    "native_apply_candidates": [
        "Project.ApplyFairlightPresetToCurrentTimeline(name)",
        "Timeline.ApplyFairlightPreset(name)",
    ],
    "apply_guard": "mutating apply is attempted only after catalog readback reports the requested preset",
    "local_fixture_status": "no user Fairlight preset catalog fixture; local store only contains AUTOmix Default.dat/internal payloads",
    "gui_equalizer_apply_boundary": (
        "GUI Equalizer Presets can mutate opaque Sm2Sequence.FieldsBlob.FLStudioModelBA bytes, but Resolve.GetFairlightPresets() "
        "still returns an empty catalog and no safe DB apply/readback model is mapped."
    ),
    "unsupported": ["creating_or_importing_fairlight_presets", "positive_apply_without_available_catalog_preset"],
}

_FAIRLIGHT_TRACK_DUPLICATE_CAVEATS = {
    "native_scope": "verified_empty_or_clips_duplicate_plus_explicit_volume_mono_pan_clip_eq_clip_fx_and_color_subsets",
    "supported_subset": [
        "empty_no_processing",
        "clips_no_processing",
        "empty_with_volume_no_other_processing",
        "clips_with_volume_no_other_processing",
        "empty_with_pan_no_other_processing",
        "clips_with_pan_no_other_processing",
        "empty_with_color_no_other_processing",
        "clips_with_color_no_other_processing",
        "clips_with_clip_eq_no_other_processing",
        "clips_with_clip_fx_no_other_processing",
        "clips_with_volume_clip_eq_no_other_processing",
        "clips_with_volume_clip_fx_no_other_processing",
        "clips_with_pan_clip_eq_no_other_processing",
        "clips_with_pan_clip_fx_no_other_processing",
        "clips_with_clip_eq_clip_fx_no_other_processing",
        "clips_with_clip_eq_color_no_other_processing",
        "clips_with_clip_fx_color_no_other_processing",
        "empty_with_volume_color_no_other_processing",
        "clips_with_volume_color_no_other_processing",
        "empty_with_pan_color_no_other_processing",
        "clips_with_pan_color_no_other_processing",
        "empty_with_volume_pan_no_other_processing",
        "clips_with_volume_pan_no_other_processing",
        "empty_with_volume_pan_color_no_other_processing",
        "clips_with_volume_pan_color_no_other_processing",
        "clips_with_volume_clip_eq_color_no_other_processing",
        "clips_with_volume_clip_eq_clip_fx_no_other_processing",
        "clips_with_volume_clip_fx_color_no_other_processing",
        "clips_with_pan_clip_eq_color_no_other_processing",
        "clips_with_pan_clip_eq_clip_fx_no_other_processing",
        "clips_with_pan_clip_fx_color_no_other_processing",
        "clips_with_clip_eq_clip_fx_color_no_other_processing",
        "clips_with_volume_pan_clip_eq_no_other_processing",
        "clips_with_volume_pan_clip_fx_no_other_processing",
        "clips_with_volume_pan_clip_eq_color_no_other_processing",
        "clips_with_volume_pan_clip_eq_clip_fx_no_other_processing",
        "clips_with_volume_pan_clip_fx_color_no_other_processing",
        "clips_with_volume_clip_eq_clip_fx_color_no_other_processing",
        "clips_with_pan_clip_eq_clip_fx_color_no_other_processing",
        "clips_with_volume_pan_clip_eq_clip_fx_color_no_other_processing",
    ],
    "volume_copy_scope": "common source fader level across mapped track channel lanes via verified mixer fader DB route",
    "mono_pan_copy_scope": "mono source pan value with set_supported=true via verified mixer pan DB route",
    "clip_eq_copy_scope": "clip-level Sm2TiItem.EffectFiltersBA payloads on media-pool backed timeline items duplicated with --include-clips",
    "clip_fx_copy_scope": "clip-level Sm2TiItem.FieldsBlob FL::ClipFX payloads on media-pool backed timeline items duplicated with --include-clips",
    "color_copy_scope": "track-level Sm2TiTrack.FieldsBlob.Color copied through the verified track-color DB route",
    "gui_volume_copy_boundary": (
        "DaVinci Resolve 21 Fairlight track-header Copy/Paste Attributes can copy the Volume/fader slice with "
        "Sm2Sequence.FieldsBlob.FLStudioModelBA and target Sm2TiTrack.FieldsBlob readback, but this does "
        "not cover full Duplicate Track EQ/dynamics/stereo-pan/plugins/routing/sends/automation parity."
    ),
    "unsupported": [
        "track_eq_copy",
        "dynamics_copy",
        "stereo_or_multichannel_pan_copy",
        "routing_copy",
        "send_copy",
        "plugin_slot_copy",
        "automation_copy",
    ],
}

_FAIRLIGHT_TRACK_HEIGHT_CAVEATS = {
    "db_scope": "read_only_stored_display_height",
    "readback_route": "Sm2Sequence.UIElementsState",
    "gui_resize_boundary": (
        "DaVinci Resolve 21 GUI resize can visibly expand a Fairlight audio track while leaving UIElementsState height "
        "readback unchanged; the visible resize diff landed in opaque Sm2Sequence.FieldsBlob.FLStudioModelBA bytes."
    ),
    "unsupported": ["gui_resize_write", "live_panel_height_verification"],
}

_FAIRLIGHT_TRACK_COLOR_CAVEATS = {
    "native_candidate": "Timeline.SetTrackColor('audio', index, color)",
    "db_scope": "verified_sm2_titrack_fieldsblob_color",
    "db_write_route": "Sm2TiTrack.FieldsBlob.Color",
    "db_readback_route": "Sm2TiTrack.FieldsBlob.Color after project reopen",
    "verified_gui_value_map": {
        "Green": 0,
        "Teal": 1,
        "Blue": 2,
        "Purple": 3,
        "Pink": 4,
        "Tan": 5,
        "Brown": 6,
        "Apricot": 7,
        "Beige": 8,
        "Chocolate": 9,
        "Lime": 10,
        "Navy": 11,
        "Olive": 12,
        "Orange": 13,
        "Violet": 14,
        "Yellow": 15,
    },
    "proof_status": "resolve_21_gui_value_map_db_write_reopen_readback",
    "unsupported": [],
}

_FAIRLIGHT_UNSUPPORTED_WRITE_CAVEATS = {
    "fairlight.adr": {
        "native_scope": "negative_adr_recording_api_probe",
        "available_read_route": "fairlight adr info",
        "unsupported": ["adr_cue_list_read", "adr_record_start_stop", "adr_take_capture"],
    },
    "fairlight.channel_mapping_write": {
        "native_scope": "timeline_item_stereo_source_channel_mapping",
        "native_since": "21.1",
        "fallback": "Disk DB on older runtimes only; no retry after a native mutation attempt.",
        "available_read_route": "fairlight channel-map clip|media",
        "supported_subset": [
            "timeline_item_track_1_stereo_channel_idx_restore_[1,2]",
            "timeline_item_track_1_single_source_channel_idx_[1]",
            "timeline_item_track_1_single_source_channel_idx_[2]",
        ],
        "unsupported": [
            "media_pool_item_mapping_write",
            "multi_track_mapping_write",
            "mute_channel_mapping",
            "non_stereo_track_types",
            "four_channel_mono_marker_readback_without_rendered_audio",
            "arbitrary_channel_patch_matrix",
        ],
    },
    "fairlight.external_process": {
        "native_scope": "read_only_external_process_config_boundary",
        "available_read_route": "fairlight external-process list",
        "unsupported": ["launch_external_audio_editor", "round_trip_external_process", "verified_reimport"],
    },
    "fairlight.groups": {
        "native_scope": "read_only_group_membership_boundary",
        "available_read_route": "fairlight group list",
        "unsupported": ["assign_tracks_to_group", "remove_tracks_from_group", "group_parameter_linking"],
    },
    "fairlight.patch_io": {
        "native_scope": "read_only_io_patch_boundary",
        "available_read_route": "fairlight io info",
        "unsupported": ["write_input_patch", "write_output_patch", "hardware_io_route_verification"],
    },
    "fairlight.loudness": {
        "native_scope": "read_only_loudness_metadata_boundary",
        "available_read_route": "fairlight loudness info",
        "unsupported": [
            "native_loudness_analysis_job",
            "native_loudness_normalize_write",
            "render_loudness_normalization_is_export_time_only",
            "rendered_lufs_proof",
        ],
    },
    "fairlight.metering": {
        "native_scope": "read_only_meter_settings_boundary",
        "available_read_route": "fairlight mixer meter-settings",
        "unsupported": ["live_meter_stream", "peak_meter_readback", "loudness_meter_readback"],
    },
    "fairlight.monitoring": {
        "native_scope": "read_only_monitor_setup_boundary",
        "available_read_route": "fairlight monitor info",
        "unsupported": ["control_room_level_write", "control_room_mute_write", "live_monitor_state_readback"],
    },
    "fairlight.recording": {
        "native_scope": "read_only_record_setup_boundary",
        "available_read_route": "fairlight record info",
        "unsupported": ["record_arm_write", "record_start", "record_stop", "take_file_verification"],
    },
    "fairlight.sends": {
        "native_scope": "read_only_send_model_boundary",
        "available_read_route": "fairlight send list",
        "unsupported": ["send_level_write", "send_pan_write", "pre_post_toggle", "send_mute_write"],
    },
    "fairlight.sound_library_audition": {
        "native_scope": "sound_library_db_read_insert_only",
        "available_read_route": "fairlight sound-library list/search",
        "unsupported": ["panel_audition_playback", "preview_without_insert", "audition_route_readback"],
    },
    "fairlight.track_folder": {
        "native_scope": "resolve_21_gui_only_folder_tracks",
        "available_read_route": None,
        "unsupported": ["create_folder_track", "read_folder_membership", "set_folder_collapsed", "remove_folder_track"],
    },
    "fairlight.track_visibility": {
        "native_scope": "track_visibility_is_not_audio_enable_state",
        "available_read_route": None,
        "unsupported": ["hide_audio_track", "show_audio_track", "persist_visibility_without_mute"],
    },
    "fairlight.input_monitoring": {
        "native_scope": "read_only_record_input_boundary",
        "available_read_route": "fairlight record info",
        "unsupported": ["input_monitor_toggle", "track_input_monitor_readback"],
    },
    "fairlight.vca": {
        "native_scope": "read_only_vca_membership_boundary",
        "available_read_route": "fairlight vca list",
        "unsupported": ["assign_tracks_to_vca", "remove_tracks_from_vca", "vca_gain_write"],
    },
    "fairlight.waveform_editing": {
        "native_scope": "read_only_waveform_view_boundary",
        "available_read_route": "fairlight waveform info",
        "unsupported": ["repair_click_write", "destructive_waveform_edit", "rendered_waveform_repair_proof"],
    },
}

_FEATURE_CAVEATS = {
    "dctl.encrypt": {
        "native_since": "21.1",
        "edition": "Studio",
        "scope": "explicit source .dctl path to exact output .dctle path",
        "overwrite": "existing output is rejected unless --overwrite is explicit",
        "verification": "non-empty output artifact size and SHA-256 readback",
    },
    "multicam.source.grade_cdl": {
        "reason": "multicam_source_grade_target_not_addressable",
        "required_target": "exact_nested_multicam_timeline_item",
        "rejected_route": "temporary_timeline_remote_version",
        "verification": "A setter and readback on a disposable timeline instance do not prove mutation of the nested multicam source item.",
    },
    "system.keyboard_preset_read": {
        "native_since": "21.1",
        "scope": "keyboard preset catalog and current preset name only",
        "methods": ["GetKeyboardPresetList", "GetCurrentKeyboardPreset"],
    },
    "system.keyboard_preset_management": {
        "native_since": "21.1",
        "scope": "exact keyboard preset load, inactive delete, import and no-overwrite export",
        "methods": ["LoadKeyboardPreset", "DeleteKeyboardPreset", "ImportKeyboardPreset", "ExportKeyboardPreset"],
        "sdk_activation": "pending_reviewed_managed_artifact_and_global_state_custody",
    },
    "edit.transitions_native": {"native_since": "21.1", "native_scope": "single_command_item_edge_transitions", "fallback": "Disk DB for older runtimes, interior seam splitting, Smooth Cut preparation and transition batches."},
    "clip.audio_normalize": {"native_since": "21.1", "native_scope": "Sample Peak Program via NormalizeAudioLevel with clip gain readback", "fallback": "Render analysis and Disk DB on older runtimes only; native readback does not claim a separately measured output peak."},
    "clip.audio_gain": {"native_since": "21.1", "native_range_db": [-100, 30], "fallback": "Disk DB for older runtimes or gain above +30 dB; no fallback after a native mutation attempt."},
    "clip.audio_pan": {"native_since": "21.1", "fallback": "Disk DB on older runtimes only."},
    "clip.audio_pitch": {"native_since": "21.1", "fallback": "Disk DB on older runtimes only."},
    "clip.fade_in": {"native_since": "21.1", "fallback": "Disk DB on older runtimes only; native duration must fit each exact item."},
    "project.db_create": {
        "scope": "explicit new Disk project library",
        "overwrite_supported": False,
        "verification": "registration readback, two DaVinci Resolve reopen readbacks, and original project/timeline restoration",
        "activation_gate": "macOS and Windows, DaVinci Resolve Free and Studio live proof",
    },
    "project.db_backup": {
        "scope": "explicit registered Disk project library to a new CutAgent backup directory",
        "overwrite_supported": False,
        "verification": "SQLite integrity, complete per-file SHA-256 inventory, backup identity, and original context restoration",
        "activation_gate": "macOS and Windows, DaVinci Resolve Free and Studio live proof",
    },
    "project.db_restore": {
        "scope": "verified CutAgent backup to an explicit new Disk project library",
        "overwrite_supported": False,
        "verification": "pre-mutation compatibility/integrity, registration readback, two DaVinci Resolve reopen readbacks, and original project/timeline restoration",
        "activation_gate": "macOS and Windows, DaVinci Resolve Free and Studio live proof",
    },
    "edit.insert_overwrite": {
        "verified_routes": ["edit insert", "edit overwrite"],
        "time_contract": "half-open source and record ranges with explicit source-to-timeline frame-rate conversion",
        "fractional_rate_contract": "frame references use the f suffix at fractional rates; ambiguous colon/semicolon timecode fails closed",
        "insert_semantics": "non-ripple placement into a preflight-confirmed empty target range",
        "overwrite_recovery": "private checkpoint before destructive mutation with verified restore on post-mutation failure",
        "live_evidence": {
            "date": "2026-08-30",
            "davinci_resolve": "Studio 21.0.0.47",
            "corpus": "cutagent-real-media-corpus-v1.0.0",
            "media": [
                "nasa-marcos-berrios-spanish-small.mp4",
                "camera-a-timecode-01000000.mov",
                "camera-b-golden-trout-135.webm",
            ],
            "proof": "fresh structural readback passed for non-ripple insert and checkpoint-backed partial-edge linked A/V overwrite, including exact 29.97 fps source boundaries; disposable project deletion verified",
        },
        "caveat": (
            "The route requires authoritative project, timeline, Media Pool, timeline-item, track-state, link-state, "
            "transition, and partial-edge Project.db clip-state readback. It fails before mutation when those signals "
            "are unavailable or when an affected transition, protected linked item, retime, transform, audio effect, "
            "or other clip-local state cannot be reconstructed exactly."
        ),
    },
    "color.lut_set_clear": {
        "render_proof_required": True,
        "readback_scope": "node LUT metadata only",
        "caveat": (
            "Set/clear can read back node LUT metadata, but live render testing found this can be a false positive. "
            "Mutating commands return verification.status=render_unverified until a rendered-frame proof route "
            "confirms DaVinci Resolve applies the LUT in output pixels."
        ),
    },
    "color.cdl_set": {
        "render_proof_required": True,
        "readback_scope": "Project.db Color Page params only",
        "caveat": (
            "CDL writes can read back Project.db grade params, but that does not prove DaVinci Resolve used the "
            "grade for Deliver/render output. Mutating commands return verification.status=render_unverified "
            "until a rendered-frame proof confirms changed output pixels."
        ),
    },
    "color.page_wheel_set": {
        "render_proof_required": True,
        "readback_scope": "Project.db Color Page params only",
        "caveat": (
            "Wheel writes can read back Project.db params after reopen, but live testing found rendered frames can "
            "remain unchanged. Treat DB readback as partial evidence only; mutating commands return "
            "verification.status=render_unverified unless rendered-frame proof is added."
        ),
    },
    "color.page_primary_set": {
        "render_proof_required": True,
        "readback_scope": "Project.db Color Page params only",
        "caveat": (
            "Primary writes can read back Project.db params after reopen, but that is not visual proof. Mutating "
            "commands return verification.status=render_unverified unless rendered-frame proof confirms changed output pixels."
        ),
    },
    "color.page_curve_set": {
        "render_proof_required": True,
        "readback_scope": "Project.db Custom Curves endpoint params only",
        "caveat": (
            "Custom Curves endpoint writes can read back Project.db params, but they are not accepted as visual proof. "
            "Mutating commands return verification.status=render_unverified until rendered-frame proof exists."
        ),
    },
    "color.page_curve_points_set": {
        "render_proof_required": True,
        "readback_scope": "Project.db Custom Curves point payload only",
        "caveat": (
            "Custom Curves point writes can read back the DB payload, but they are not accepted as visual proof. "
            "Mutating commands return verification.status=render_unverified until rendered-frame proof exists."
        ),
    },
    "color.gallery_power_grade_list_album": {
        "verified_routes": ["list", "album_create"],
        "residual": (
            "PowerGrade list and album creation are supported through DaVinci Resolve's Gallery API. "
            "PowerGrade library apply is split to color.power_grade_apply and requires its own rendered-frame proof."
        ),
    },
    "color.power_grade_apply": {
        "verified_route": True,
        "verified_routes": ["apply_user_gallery_db_render_proof"],
        "caveat": (
            "PowerGrade apply goes through the per-user gallery database (User.db): the selected still's "
            "ListMgt::LmVersion grade body is written onto the target clip's grade version through the Disk Project.db "
            "close/write/reopen route, then the command exports before/after Color Page frames and requires a nonzero "
            "pixel diff. DB signature readback alone is not accepted as success. Native PowerGrade ExportStills/DRX "
            "export remains unavailable in DaVinci Resolve Studio 21 (live probe 2026-06-10 returned false for every "
            "format), so DRX-based application still requires a concrete DRX file via color grade-apply PATH."
        ),
    },
    "color.page_resolvefx_add": {
        "verified_route": True,
        "verified_routes": ["resolvefx-add", "resolvefx-remove", "resolvefx-list"],
        "caveat": (
            "ResolveFX add/remove writes the native OFX tool params (plugin id, OFX filter context, enables, and the "
            "generic options payload) on the primary Color Page grade node through the verified Disk Project.db "
            "close/write/reopen route. Live DaVinci Resolve Studio 21 proof on real footage rendered a CLI-inserted "
            "Box Blur pixel-identical to the GUI-authored fixture and a never-GUI-touched Vignette with default "
            "parameters. Effects run at plugin defaults; per-effect parameter control is not yet command-backed. "
            "One ResolveFX instance per primary node is managed by this route."
        ),
    },
    "color.page_scope_read": {
        "gui_scope_set_verified": False,
        "verified_routes": ["scope-read"],
        "residual": (
            "Color Page scope-read is a production-verified frame analyzer for waveform, RGB parade, and vectorscope-style metrics. "
            "Native GUI scope toggles such as Parade/Waveform/Vectorscope layout, Y/RGB, colorize, skin-tone indicator, 2x zoom, "
            "qualify focus, and percentage scale are not command-backed until a live scriptable UI, API, or verified preference route "
            "has readback proof."
        ),
    },
    "color.page_false_color_read": {
        "gui_false_color_verified": False,
        "verified_routes": ["false-color-read"],
        "residual": (
            "Color Page false-color-read is a production-verified frame analyzer that exports the current Color Page frame and "
            "computes tutorial-style luma/IRE false-color bands for exposure, skin/proper range, shadow crush, and highlight clipping. "
            "It does not enable DaVinci Resolve's native false-color viewer overlay or monitor LUT; keep GUI false-color state manual until "
            "a scriptable UI/API/preference route has readback proof."
        ),
    },
    "color.page_viewer_before_after": {
        "verified_route": True,
        "viewer_compare_state_verified": False,
        "verified_routes": ["viewer-before-after"],
        "residual": (
            "Color Page viewer-before-after is a production-supported proof route: it exports before/after Color Page frames, "
            "decodes them through ffmpeg RGB24, returns pixel-diff metrics, and can generate a side-by-side proof image. "
            "It does not control DaVinci Resolve's native Gallery split-screen, wipe, or viewer comparison UI state."
        ),
    },
    "color.page_shot_match_analyze": {
        "verified_route": True,
        "viewer_compare_verified": False,
        "verified_routes": ["shot-match-analyze"],
        "residual": (
            "Color Page shot-match-analyze is a production-supported programmatic frame analyzer: it exports reference and target "
            "Color Page frames, compares full-frame or shared-anchor luma/RGB metrics, and returns conservative primary-gain "
            "recommendations. It is not DaVinci Resolve's Gallery split-screen, wipe, or side-by-side viewer comparison UI."
        ),
    },
    "color.page_shot_match_apply": {
        "verified_route": True,
        "viewer_compare_verified": False,
        "verified_routes": ["shot-match-analyze", "shot-match-apply"],
        "residual": (
            "Color Page shot-match-apply applies the shot-match analyzer's conservative RGB Gain recommendation through the verified "
            "Project.db primary-parameter route and returns DB readback. It does not copy creative grades, control Gallery still "
            "wipe state, or claim visual shot matching without exported before/after frame proof."
        ),
    },
    "color.page_power_window_gradient_transform": {
        "verified_route": True,
        "verified_slices": [
            "x/pan",
            "y/tilt",
            "softness/Soft 1",
        ],
        "residual": (
            "Gradient Power Window transform has verified DB slices for Pan, Tilt, and Soft 1. GUI rotate fixtures changed "
            "viewer state but did not map to a safe scalar DB route. Angle/Rotate, Transform Size, Aspect, Opacity, viewer "
            "drag placement, and the remaining opaque overlay payload are not yet full GUI parity."
        ),
    },
    "color.page_power_window_circle_detail": {
        "verified_route": True,
        "verified_slices": ["opacity", "invert/outside selection"],
        "residual": (
            "Circle detail now supports verified Opacity and outside/invert selection through the same DB route as "
            "color.page_power_window_circle. The DaVinci Resolve GUI fixture disables Circle Soft 2/3/4 and Inside/Outside "
            "softness in this panel state, so those flags intentionally fail validation instead of pretending to be writable."
        ),
    },
    "color.page_power_window_overlay_transform": {
        "verified_route": True,
        "verified_slices": [
            "linear/rectangle x",
            "linear/rectangle y",
            "linear/rectangle width",
            "linear/rectangle height",
            "linear/rectangle Soft 1-4",
            "linear/rectangle opacity",
        ],
        "residual": (
            "Power Window overlay-transform is production-supported only as explicit normalized Linear/Rectangle values, "
            "not as raw viewer drags. A 2026-06-10 overlay fixture verified x/y and Soft 2 persistence through the existing "
            "linear DB route, while manual Rotate 25 changed an opaque overlay payload that is not safely writable yet. "
            "Rotate and feather-drag flags intentionally fail validation until they have parser/replay/render proof."
        ),
    },
    "color.page_dctl_apply": {
        "verified_route": True,
        "verified_slices": ["apply DCTL/LUT as node LUT", "node LUT readback", "Color Page and Deliver render proof"],
        "residual": (
            "DCTL apply is implemented through DaVinci Resolve's node LUT route and succeeds only after Color Page and "
            "Deliver renders prove changed pixels. Compile failures or unchanged renders fail closed. It does not expose native DCTL "
            "OFX parameter panels, pivot helper UI, or DCTL-specific parameter editing beyond applying the installed/nameable "
            "DCTL/LUT to a Color Page node."
        ),
    },
    "color.page_dctl_remove": {
        "verified_route": True,
        "verified_slices": ["clear node LUT", "node LUT readback"],
        "residual": (
            "DCTL remove clears the Color Page node LUT through the verified LUT clear route. It does not remove DCTL files "
            "from disk or manage DCTL-specific OFX parameter state."
        ),
    },
    "color.page_split_tone_set": {
        "verified_route": True,
        "verified_slices": ["Custom Curves RGB/Y control points", "optional Key Output Gain"],
        "residual": (
            "Split tone is implemented as a deterministic Custom Curves recipe with optional verified Key Output Gain. "
            "It supports pivot, rolloff, shadow/highlight RGB offsets, and Y mood through sampled control points, but "
            "does not expose arbitrary GUI spline handles or unlimited curve point counts."
        ),
    },
    "color.page_hsv_node_set": {
        "verified_route": True,
        "verified_slices": ["HSV color space/channel 2 fixture", "Gamma/Gain saturation params", "optional Key Output Gain"],
        "residual": (
            "HSV node set grafts the verified DaVinci Resolve Studio 21 HSV/channel-2 Primary Balance fixture and optional "
            "Key Output Gain. It verifies the HSV mode blocks and Gamma/Gain param readback, but arbitrary node targeting "
            "beyond the fixture-backed node-1 route is not promoted."
        ),
    },
    "color.page_layer_mixer_opacity": {
        "verified_route": True,
        "verified_slices": [
            "branch node native Key Output Gain payload inside the Layer Mixer topology",
            "node-index targeted DB readback",
            "rendered-frame proof",
        ],
        "residual": (
            "Layer Mixer branch opacity is supported only for the verified Layer Mixer topology by writing the selected "
            "branch node's native Key Output Gain payload in that branch container. It is not a generic arbitrary-node "
            "Key Output alias and does not imply GUI support for other Layer Mixer overlay states."
        ),
    },
    "color.page_ofx_glow_set": {
        "verified_route": True,
        "verified_slices": ["Fusion SoftGlow inline tool", "Fusion graph validation", "tool list readback"],
        "residual": (
            "Color Page ofx-glow-set is supported as a clip-attached Fusion SoftGlow finishing workaround with Gain parameter "
            "readback through Fusion tool inspection. It is not native DaVinci Resolve ResolveFX/OpenFX Glow panel control and "
            "does not claim Bloom/Halation/Film Grain parameter parity."
        ),
    },
    "color.page_sharpen_set": {
        "verified_route": True,
        "verified_slices": ["Fusion UnsharpMask inline tool", "Fusion graph validation", "tool list readback"],
        "residual": (
            "Color Page sharpen-set is supported as a clip-attached Fusion UnsharpMask finishing workaround with Amount parameter "
            "readback through Fusion tool inspection. It is not native DaVinci Resolve ResolveFX/OpenFX sharpening panel control."
        ),
    },
    "color.page_softening_set": {
        "verified_route": True,
        "verified_slices": ["Fusion Blur inline tool", "Fusion graph validation", "tool list readback"],
        "residual": (
            "Color Page softening-set is supported as a clip-attached Fusion Blur finishing workaround that writes XBlurSize/YBlurSize "
            "equally and verifies the Blur tool in the main Fusion pipe. It is not native DaVinci Resolve beauty/softening OFX panel control."
        ),
    },
    "clip.magic_mask": {
        "verified_route": False,
        "residual": (
            "DaVinci Resolve Studio 21 exposes TimelineItem.CreateMagicMask/RegenerateMagicMask in the scripting API, "
            "but live production proof on a disposable timeline with real footage returned False for CreateMagicMask "
            "in F, B, and BI modes. Use the verified public `color page magic-mask-draw-stroke` route instead: it drives "
            "the native Color-page Magic Mask without activating DaVinci Resolve and returns screenshot/export proof. "
            "Keep the separate Edit-page `clip magic-mask` API route blocked until CreateMagicMask itself has reliable "
            "native readback or rendered proof."
        ),
    },
    "clip.smart_reframe": {
        "verified_route": False,
        "residual": (
            "TimelineItem.SmartReframe is exposed by the embedded scripting API, but live DaVinci Resolve Free 21.0.1 "
            "testing on real footage in a vertical timeline returned False. The command now exposes stable operation identity, "
            "phase-only progress, truthful non-cancellable native-call semantics, exact target revalidation, and terminal rendered "
            "before/after evidence when the API succeeds. Treat edition/platform applicability as partial until successful Studio "
            "proof exists on macOS and Windows; a cancellation request during the native call is never reported as confirmed."
        ),
    },
    "edit.ofx_resolvefx_native": {
        "verified_route": False,
        "residual": (
            "The public edit/color FX actions are restricted to stable reviewed effect IDs and typed/ranged Fusion parameters, "
            "exact timeline-item targets, structural readback, retained rendered before/after evidence, and verified rollback on "
            "failure. Those public built-ins use the direct fusion_native route. Custom .setting templates use the separate "
            "workaround_setting route and require a versioned manifest with an exact template hash and tool identities. Keep the "
            "capability partial until the reviewed built-ins have real-media proof on macOS and Windows across DaVinci Resolve "
            "Free and Studio; this route does not claim native ResolveFX/OpenFX panel parity."
        ),
    },
    "color.page_magic_mask": {
        "verified_route": True,
        "engine_scope": "workflow_owned_resolve_gui",
        "required_proof": ["screenshot_path", "export_path", "viewer_rect"],
        "verified_routes": ["color page magic-mask-draw-stroke"],
        "caveat": (
            "Color Page Magic Mask is supported only through the workflow-owned GUI-assisted command "
            "`color page magic-mask-draw-stroke`. The internal macOS driver is scoped to DaVinci Resolve Magic Mask: "
            "it performs Screen Recording/Accessibility preflight, DaVinci Resolve window and Color page readiness checks, "
            "binds input to the verified DaVinci Resolve PID and window ID without changing the Workspace-frontmost app, "
            "selects Magic Mask's positive input mode (including the initial Add Click fallback in Magic Mask 2), maps "
            "viewer strokes, optionally tracks the full range, waits for native completion, and captures proof artifacts. "
            "This does not expose generic see/click/type/screen automation and must not be reused as a broad GUI fallback."
        ),
    },
    "color.page_alpha_output_connect": {
        "verified_route": True,
        "verified_slices": [
            "exact timeline item owner selection",
            "single-node GUI-authored RGB/Alpha graph topology",
            "Project.db backup/transaction/reopen/rollback",
            "post-reopen exact item and grade-body readback",
        ],
        "residual": (
            "The command connects an existing single Color node key output to DaVinci Resolve Alpha Output. "
            "It does not create or judge a matte. Magic Mask and text-behind-object workflows must still export "
            "target-only early/middle/late frames and prove the complete intended foreground subject."
        ),
    },
    "project.cloud.create": _BLACKMAGIC_CLOUD_CAVEATS,
    "project.cloud.open": _BLACKMAGIC_CLOUD_CAVEATS,
    "project.cloud.import": _BLACKMAGIC_CLOUD_CAVEATS,
    "project.cloud.restore": _BLACKMAGIC_CLOUD_CAVEATS,
    "fairlight.dialogue_leveler": _FAIRLIGHT_DIALOGUE_LEVELER_CAVEATS,
    "fairlight.music_remixer": _FAIRLIGHT_MUSIC_REMIXER_CAVEATS,
    "fairlight.timeline_voice_isolation": _FAIRLIGHT_TIMELINE_VOICE_ISOLATION_CAVEATS,
    "fairlight.automation": _FAIRLIGHT_AUTOMATION_CAVEATS,
    "fairlight.bus_routing": _FAIRLIGHT_BUS_ROUTING_CAVEATS,
    "fairlight.builtin_effect_route": _FAIRLIGHT_BUILTIN_EFFECT_ROUTE_CAVEATS,
    "fairlight.clip_effect_param_write": _FAIRLIGHT_CLIP_EFFECT_PARAM_WRITE_CAVEATS,
    "fairlight.clip_move": _FAIRLIGHT_CLIP_MOVE_CAVEATS,
    "fairlight.clip_slip": _FAIRLIGHT_CLIP_SLIP_CAVEATS,
    "fairlight.clip_trim": _FAIRLIGHT_CLIP_TRIM_CAVEATS,
    "edit.trim_workaround": _EDIT_TRIM_CAVEATS,
    "fairlight.elastic_wave": _FAIRLIGHT_ELASTIC_WAVE_CAVEATS,
    "fairlight.pan": _FAIRLIGHT_PAN_CAVEATS,
    "fairlight.plugin_routing": _FAIRLIGHT_PLUGIN_ROUTING_CAVEATS,
    "fairlight.preset": _FAIRLIGHT_PRESET_CAVEATS,
    "fairlight.track_color": _FAIRLIGHT_TRACK_COLOR_CAVEATS,
    "fairlight.track_duplicate": _FAIRLIGHT_TRACK_DUPLICATE_CAVEATS,
    "fairlight.track_height": _FAIRLIGHT_TRACK_HEIGHT_CAVEATS,
    **_FAIRLIGHT_UNSUPPORTED_WRITE_CAVEATS,
    "ai_neural.auto_color_ai": {
        "verified_route": True,
        "verified_routes": ["native_color_page_auto_color_menu_frame_diff"],
        "engine_scope": "workflow_owned_resolve_gui",
        "required_proof": ["before_frame", "after_frame", "pixel_diff"],
        "caveat": (
            "Auto Color AI is supported through the workflow-owned `color page auto-color-ai` GUI route. "
            "The command invokes DaVinci Resolve's native Color > Auto Color menu item, exports before/after "
            "Color Page frames through Project.ExportCurrentFrameAsStill, and requires a nonzero pixel diff. "
            "Use --undo-after-proof when a live proof should verify native behavior without leaving the Auto Color "
            "grade applied."
        ),
    },
    "ai_neural.face_refinement": {
        "verified_route": True,
        "verified_routes": ["color page resolvefx-add --fx Face Refinement"],
        "engine_scope": "native_resolvefx_default_insert",
        "plugin_ids": [
            "com.blackmagicdesign.resolvefx.facerefinement2",
            "com.blackmagicdesign.resolvefx.facerefinement",
        ],
        "live_probe": {
            "runtime": "local DaVinci Resolve Free registry probe via `color page resolvefx-list --category Refine`",
            "listed_refine_plugins": ["Beauty", "Blemish Removal", "Depth Map", "Relight"],
            "face_refinement_listed_in_free_registry": False,
            "app_binary_symbols_found": [
                "com.blackmagicdesign.resolvefx.facerefinement2",
                "com.blackmagicdesign.resolvefx.facerefinement",
                "AI Face Refinement",
                "AI Face Refinement (Legacy)",
            ],
        },
        "residual": (
            "AI Face Refinement is partial, not full parameter parity. The verified native route is the existing "
            "Color Page ResolveFX DB-backed default OFX insertion/removal path, with explicit aliases for the "
            "Face Refinement v2 and legacy plugin ids found in the DaVinci Resolve app binary. This does not claim "
            "control over Face Refinement analysis data, face mask size/softness, GUI overlay handles, Studio-only "
            "licensing behavior, or per-parameter UI parity; agents should use `color page resolvefx-list --category Refine` "
            "when live registry confirmation is required and then apply `color page resolvefx-add CLIP --fx \"Face Refinement\"`."
        ),
    },
    "color.curves": {
        "verified_slices": [
            "page_curve_set",
            "page_curve_points_set",
            "page_curve_spline_set",
            "page_hue_curve_set",
            "page_hue_curve_spline_set",
            "page_sat_curve_set",
            "page_sat_curve_spline_set",
        ],
        "engine_scope": "verified_db_backed_curve_slices",
        "residual": (
            "Verified Color Page curve routes cover endpoint values, GUI-sampled custom curve points, point-list Custom Curve "
            "spline writes, Hue curves, Hue spline points, and Sat/Lum spline points. The broad curves capability is partial "
            "and still excludes exact GUI Bezier-handle sculpting, pivot pins, and unlimited GUI point/handle parity until those "
            "workflows have native/API/verified DB readback and render proof. A live Apple Log reprobe found no Bezier/Pivot "
            "edit API methods on DaVinci Resolve, project, timeline, current item, or node graph, and active Project.db strings were "
            "media/timeline handle or RED camera curve schema rather than Color Page GUI curve-handle fixtures."
        ),
    },
    "color.hdr_palette": {
        "verified_route": True,
        "verified_slices": [
            "color.page_hdr_global_set",
            "color.page_hdr_zone_set",
            "color.page_hdr_detail_set",
        ],
        "caveat": (
            "The broad HDR palette capability is covered by the verified DB-backed HDR command family: Global "
            "Exposure/Saturation, Dark/Shadow/Light x/y/z vectors, and Highlight/Specular x/y/sat/range/falloff. "
            "These routes verify decoded Project.db readback. Arbitrary GUI-only HDR palette gestures and raw adjacent-key "
            "experiments are not exposed as hidden fallbacks."
        ),
    },
    "color.page_bleach_bypass_parametric": {
        "verified_route": False,
        "verified_slices": ["color.page_bleach_bypass", "color.page_bleach_bypass_intensity"],
        "engine_scope": "verified_bleach_bypass_recipe_slice",
        "residual": (
            "Fully parametric bleach-bypass controls such as separate contrast, desaturation, and topology-policy knobs are "
            "still unsupported. The broad bleach-bypass parametric capability is partial because the verified command covers "
            "the native RGB Mixer Monochrome + Preserve Luminance branch, Layer Mixer Overlay, and optional Key Output Gain "
            "intensity. Do not add hidden primary/curve/desaturation fallback steps under the bleach-bypass-set name without "
            "separate GUI-authored fixture, DB/API readback, and rendered-frame proof."
        ),
    },
    "color.page_cat_set": {
        "verified_route": True,
        "verified_routes": ["color page cat-set"],
        "native_tool": "Fusion ChromaticAdaptation",
        "caveat": (
            "CAT is implemented through DaVinci Resolve's native Fusion ChromaticAdaptation tool attached to the target "
            "timeline clip. The command sets CATMethod, standard Source/Target illuminant inputs, and fixed "
            "REC709_COLORSPACE/LINEAR_GAMMA processing, then verifies readback with Fusion GetInput. This replaces the "
            "rejected Color Space Transform doCAT/DB experiment; it does not expose custom Kelvin, tint, CIE1931 xy, mask, "
            "or arbitrary color-space/gamma options under the cat-set command."
        ),
    },
    "color.page_color_slice": {
        "verified_route": True,
        "verified_routes": ["native_color_page_colorslice_gui_readback"],
        "engine_scope": "workflow_owned_resolve_gui",
        "supported_controls": ["per-vector Hue", "per-vector Saturation", "per-vector Density"],
        "caveat": (
            "color-slice-set drives DaVinci Resolve's native Color Page ColorSlice panel through a workflow-owned macOS GUI route. "
            "It supports the seven native vectors Red, Skin, Yellow, Green, Cyan, Blue, and Magenta. Saturation and Density use "
            "native vertical slider drags with per-step numeric readback; Hue uses the native ColorSlice Hue strip and verifies the per-vector numeric readback. "
            "The public --luma option maps to the native per-vector Density control. The route targets the current Color Page "
            "clip and rejects a non-current clip name instead of silently changing another clip. Input and proof are scoped "
            "to the verified DaVinci Resolve PID/window without activating DaVinci Resolve at the macOS Workspace level. "
            "ColorSlice selects a color-family vector across the frame; it is not a spatial/object mask."
        ),
    },
    "color.page_color_warper": {
        "verified_route": True,
        "verified_routes": ["native_color_page_warper_single_pin_db_readback"],
        "engine_scope": "single_pin_chroma_warp_db_payload",
        "supported_controls": ["single Chroma Warp pin source/target normalized map coordinates"],
        "caveat": (
            "warper-set writes DaVinci Resolve's native Color Page Color Warper single-pin Chroma Warp payload in Project.db. "
            "The payload shape was derived from GUI-authored Pin Point moves in DaVinci Resolve Studio 21.0.0b.20 and verified "
            "by post-reopen DB readback plus Peekaboo GUI evidence. It intentionally supports the verified single-pin source/target "
            "payload only; freehand strokes, multiple pins, Hue-Saturation mode, Chroma-Luma mode, and radius editing remain outside this route."
        ),
    },
    "color.page_curve_spline_freeform": {
        "verified_route": True,
        "verified_slices": ["color.page_curve_set", "color.page_curve_points_set"],
        "caveat": (
            "Custom Curves spline set is supported for normalized channel point lists by writing the same DB-native control "
            "point payload as color.page_curve_points_set. Pivot pins and explicit Bezier handle placement are not accepted "
            "as hidden fallbacks; the public command exposes point-list spline state only."
        ),
    },
    "color.page_hdr_detail_controls": {
        "verified_route": True,
        "verified_routes": ["color.page_hdr_detail_set", "color.page_hdr_zone_set"],
        "caveat": (
            "HDR detail controls are supported through verified Disk Project.db payload routes. "
            "`color page hdr-detail-set` writes the native HDR detail container for Highlight/Specular "
            "x/y/sat/range/falloff and verifies decoded post-write readback. `color page hdr-zone-set` remains "
            "the main HDR palette route for Dark/Shadow/Light x/y/z and Highlight/Specular x/y/sat. Zone color "
            "pickers and arbitrary GUI-only HDR palette operations are not hidden behind these commands."
        ),
    },
    "color.page_hsv_node_target": {
        "verified_route": False,
        "verified_slices": ["color.page_hsv_node_set"],
        "engine_scope": "verified_fixture_backed_node_1_slice",
        "residual": (
            "HSV node targeting is partial. The verified HSV workflow grafts the GUI-authored HSV/channel-2 "
            "fixture into the fixture-backed node-1 route; other node indices still return explicit unsupported "
            "diagnostics and need separate GUI fixtures, DB readback, and rendered-frame proof before public support."
        ),
    },
    "color.page_hue_curve_gui_spline": {
        "verified_route": True,
        "verified_slices": ["color.page_hue_curve_set"],
        "caveat": (
            "Hue curve spline set is supported for the native fixture-backed multi-point Hue vs Hue/Hue vs Sat/Hue vs Lum "
            "payloads already used by color.page_hue_curve_set. The command writes DB-native curve points and verifies "
            "Project.db readback; separate Bezier handle sculpting remains outside the public option surface."
        ),
    },
    "color.page_magic_mask_refinement": {
        "verified_route": True,
        "engine_scope": "workflow_owned_resolve_gui",
        "required_proof": ["screenshot_path", "export_path", "viewer_rect"],
        "verified_routes": ["color page magic-mask-refine"],
        "supported_controls": ["native Magic Mask refinement stroke", "native Magic Mask Track button"],
        "unsupported": ["matte_finesse_controls", "automatic_object_selection_without_stroke", "tracked_mask_keyframe_readback"],
        "caveat": (
            "Magic Mask refinement is partial: `color page magic-mask-refine` uses the same workflow-owned native "
            "DaVinci Resolve Magic Mask GUI driver as `magic-mask-draw-stroke`, but requires an explicit normalized "
            "`--stroke` so the refinement action is proofable. The route switches to the Color page, validates the "
            "Magic Mask panel, draws the refinement stroke in the viewer, optionally clicks the native Track button, "
            "and records screenshot plus exported-frame proof. It does not claim matte finesse sliders, automatic "
            "object selection without a stroke, or tracked-mask keyframe readback."
        ),
    },
    "color.page_node_add_arbitrary_topology": {
        "verified_route": True,
        "verified_slices": [
            "color.page_node_add_serial",
            "color.page_node_add_parallel",
            "color.page_node_add_layer",
        ],
        "caveat": (
            "Node-add-topology is supported for the verified native serial, parallel, layer, and mixer-alias routes. It "
            "validates position constraints for parallel/layer insertion and does not claim arbitrary rewiring, labels, "
            "bypass state, or complex topology surgery beyond those DB-backed layouts."
        ),
    },
    "color.page_node_cleanup_general": {
        "verified_route": True,
        "verified_slices": ["color.page_node_cleanup_empty_serial"],
        "caveat": (
            "General cleanup is command-backed for the verified empty-serial graph cleanup route. The command validates "
            "unsupported modes instead of silently deleting mixers, resetting grades, or performing arbitrary topology rewrites."
        ),
    },
    "color.page_power_window_gui_set": {
        "render_proof_required": False,
        "readback_scope": "DaVinci Resolve Color Page node graph plus GUI screenshot proof",
        "caveat": (
            "`color page power-window-gui-set` is setup-only: creating or moving a Power Window may not change pixels by itself. "
            "Use it only on a controlled selected node, then apply a visible node-local correction and require render/locality proof. "
            "Verified controls cover Linear/Circle/Polygon/Curve/Gradient shape button creation plus Size, Aspect, Pan, Tilt, "
            "Rotate, Opacity, Soft 1-4, Inside, and Outside numeric GUI fields. Invert remains fail-fast until a verified "
            "native GUI control is located; DaVinci Resolve Studio 21.0.0.47 AX runtime probes expose Inside/Outside numeric "
            "fields but no stable Invert toggle in the Window panel."
        ),
    },
    "color.page_power_window_track": {
        "verified_route": True,
        "verified_routes": ["native_color_page_tracker_gui_readback"],
        "engine_scope": "workflow_owned_resolve_gui",
        "supported_directions": [
            "forward",
            "reverse",
            "one-frame-forward",
            "one-frame-reverse",
            "forward-reverse",
        ],
        "caveat": (
            "`color page power-window-track` uses a narrow macOS resolve_gui route to run DaVinci Resolve's native "
            "Color Page Tracker - Window buttons for the current selected Power Window. The route requires Accessibility "
            "and Screen Recording, an open Color Page Tracker panel, saves the project before/after the native click, and "
            "verifies that the target clip's grade `LmVersion.Body` fingerprint changed. It was derived from Peekaboo "
            "fixtures on DaVinci Resolve Studio 21.0.0b.20 where Track One Frame Forward inserted a native tracking payload "
            "under the Power Window node. The command does not parse or author arbitrary tracker keyframes, auto-select "
            "Power Window shapes, or claim generic Color Page tracker/Magic Mask tracking parity. macOS input and screenshot "
            "proof target the exact verified DaVinci Resolve PID/window without activating it in the Workspace."
        ),
    },
    "color.page_primary_gui_set": {
        "verified_route": True,
        "engine_scope": "workflow_owned_resolve_gui",
        "verified_routes": ["color page primary-gui-set"],
        "required_panel": "Color page Primaries - Color Wheels",
        "required_proof": ["render_proof.status=verified", "comparison.changed_pixel_count>0"],
        "verified_controls": [
            "temperature",
            "tint",
            "contrast",
            "pivot",
            "mid_detail",
            "color_boost",
            "shadows",
            "highlights",
            "saturation",
            "hue",
            "lum_mix",
        ],
        "caveat": (
            "Native Color Page Primaries GUI mutation is scoped to the currently selected Color Page node. The command "
            "opens the Primaries - Color Wheels panel, writes verified numeric fields through PID/window-targeted mouse and "
            "keyboard events with numeric readback, captures the exact DaVinci Resolve window, and by default requires "
            "rendered-frame pixel proof without activating DaVinci Resolve at the macOS Workspace level. It does not select "
            "an arbitrary node index; workflows must create/select the target node first and must fail if render proof "
            "or locality checks do not match the intended correction."
        ),
    },
    "color.page_qualifier_gui_hsl_set": {
        "verified_route": True,
        "engine_scope": "workflow_owned_resolve_gui",
        "required_probe": "color page qualifier-panel-probe",
        "required_probe_decision": "ready_for_proof_gated_write",
        "required_proof": ["render_proof.status=verified", "comparison.changed_pixel_count>0"],
        "caveat": (
            "Native Color Page Qualifier GUI HSL mutation is a workflow-owned route. It first probes the visible "
            "Qualifier panel and refuses to mutate unless HSL numeric GUI fields are exposed. It then writes the "
            "specific HSL numeric fields through exact PID/window-targeted background input, exports before/after rendered "
            "frames, and fails if pixels are unchanged. It does not require DaVinci Resolve to become the frontmost app."
        ),
    },
    "color.page_qualifier_gui_matte_set": {
        "verified_route": True,
        "engine_scope": "workflow_owned_resolve_gui",
        "required_probe": "color page qualifier-panel-probe",
        "required_probe_flag": "matte_refinement_gui_write_supported",
        "required_setup_proof": ["probe.summary.matte_refinement_gui_write_supported=true", "apply_result.results[].set=true"],
        "required_final_proof": ["render_proof.status=verified", "comparison.changed_pixel_count>0"],
        "verified_controls": ["clean_black", "clean_white", "blur"],
        "probe_gated_controls": ["softness", "denoise", "grow_shrink"],
        "latest_live_validation": {
            "date": "2026-06-19",
            "resolve_version": "DaVinci Resolve Studio 21.0.0.47",
            "project": "CA CLI Color Proof 20260618 180430",
            "clip": "A001_05261747_C004.mov",
            "setup_only": "ok",
            "standalone_render_proof": "COLOR_RENDER_PROOF_FAILED when matte refinement produced no visible pixel change",
        },
        "caveat": (
            "Native Color Page Qualifier GUI matte/refinement mutation is a workflow-owned route. It first "
            "probes the visible Qualifier panel and refuses to mutate unless matte/refinement settable controls are "
            "exposed. It writes the verified Clean Black, Clean White, and Blur Radius numeric GUI fields through exact "
            "PID/window-targeted background input. Softness, Denoise, and Grow/Shrink are supported only when the live panel probe "
            "exposes a settable control for that semantic family; the route does not guess DB keys for them. Treat the "
            "command as setup-only unless a same-node visible correction supplies final rendered-frame proof; matte-only "
            "changes can legitimately be pixel-identical. Do not treat this as arbitrary Key palette matte parity."
        ),
    },
    "color.page_qualifier_matte_refinement": {
        "verified_route": True,
        "verified_routes": ["native_color_page_hsl_qualifier_db_readback"],
        "engine_scope": "hsl_qualifier_range_and_matte_finesse_db_payload",
        "render_proof_required": True,
        "supported_controls": [
            "HSL Hue center/width/soft/symmetry",
            "Saturation low/high/low-soft/high-soft",
            "Luminance low/high/low-soft/high-soft",
            "Matte Finesse Blur Radius",
        ],
        "caveat": (
            "qualifier-matte-refine writes DaVinci Resolve's native Color Page HSL Qualifier scaffold and Matte Finesse "
            "Blur Radius in Project.db. The route was derived from Peekaboo-driven GUI fixtures in DaVinci Resolve Studio "
            "21.0.0b.20: native picker + blur survived project close/open, Hue Center DB deltas mapped to 0x0830000e, "
            "and live DB replay verifies post-reopen readback. It does not automate eyedropper sampling gestures, RGB/LUM/3D "
            "qualifier modes, Clean Black/White or Black/White Clip controls, or rendered matte proof."
        ),
    },
    "color.page_qualifier_panel_probe": {
        "verified_route": True,
        "engine_scope": "workflow_owned_resolve_gui",
        "required_proof": ["screenshot_path", "panel_rect", "onscreen_window_rect"],
        "verified_routes": ["color page qualifier-panel-probe"],
        "caveat": (
            "Native Color Page Qualifier panel inspection is supported only through the workflow-owned GUI-assisted "
            "diagnostic command `color page qualifier-panel-probe`. The command performs Screen Recording/"
            "Accessibility preflight, Color page readiness, an on-screen/current-Space DaVinci Resolve window guard, "
            "Qualifier panel selection, AX control enumeration, and a panel screenshot proof. It does not mutate HSL "
            "ranges, does not create a matte, and must not be treated as a render-visible qualifier correction."
        ),
    },
    "color.page_resolvefx_param_discover": {
        "verified_route": True,
        "verified_routes": ["resolvefx-param-discover"],
        "caveat": (
            "resolvefx-param-discover is read-only descriptor introspection. It creates a temporary Fusion composition, "
            "adds the requested installed ResolveFX OFX tool, and reads GetInputList() attrs to return parameter ids, UI names, "
            "control classes, defaults, ranges, choices, and suggested DB value types. It does not mutate the Color Page and "
            "does not prove that a DB option write is render-visible; pair discovered params with resolvefx-param-set render proof."
        ),
    },
    "color.page_resolvefx_param_list": {
        "verified_route": True,
        "verified_routes": ["resolvefx-param-list"],
        "caveat": (
            "resolvefx-param-list is a read-only Project.db introspection command for the active Color Page "
            "grade version and requested --node. It decodes the current ResolveFX OFX options payload, reports exact option names/types/"
            "values, marks each option as render_proof_verified_param or raw_unverified_param_name, and reports whether "
            "that decoded option can be rewritten with resolvefx-param-set --type auto. It is readback-only by design; "
            "use resolvefx-param-set with render proof before treating a parameter change as visually applied."
        ),
    },
    "color.page_resolvefx_param_set": {
        "verified_route": True,
        "verified_routes": ["resolvefx-param-set boxblur strength/HStrength"],
        "caveat": (
            "resolvefx-param-set defaults to render proof and should fail with COLOR_RENDER_PROOF_FAILED when an OFX "
            "option write is only DB-visible. The route is node-scoped with --node, but the only production verified "
            "effect-specific parameter today is Box Blur Strength/HStrength, backed by a GUI-authored payload fixture and live DaVinci Resolve Studio 21.0.0.47 "
            "proof on real project media. Raw names such as Glow Spread/ShineThreshold/Saturation wrote DB entries but "
            "changed 0 pixels in live render proof before descriptor discovery existed. --type auto is supported for options already decoded by "
            "resolvefx-param-list as double/int/string and for new parameters whose ids are present in live resolvefx-param-discover "
            "output with a supported suggested type. A discovered descriptor is still not visual proof; unlisted/non-changing "
            "parameters must fail render proof rather than be treated as artist-safe controls."
        ),
    },
    "color.page_rgb_mixer_coefficients": {
        "verified_route": False,
        "verified_slices": ["color.page_rgb_mixer_monochrome"],
        "engine_scope": "verified_rgb_mixer_monochrome_slice",
        "residual": (
            "RGB Mixer coefficient coverage is partial. The verified DB-backed route covers the native RGB Mixer "
            "Monochrome + Preserve Luminance mode through `color page rgb-mixer-set` without coefficient flags. "
            "Coefficient controls outside that verified slice remain unsupported. "
            "A 2026-06-10 live probe wrote candidate red/green/blue keys 0x86000052-0x86000054 and read them back from "
            "Project.db after reopen, but rendered frame proof on the active Apple Log clip changed 0 pixels, including "
            "a monochrome-plus-coefficients reprobe. Keep coefficient flags as residual diagnostics until a GUI-authored "
            "fixture produces readback and rendered-frame proof."
        ),
    },
    "color.page_sat_curve_gui_spline": {
        "verified_route": True,
        "verified_slices": ["color.page_sat_curve_set"],
        "caveat": (
            "Sat/Lum curve spline set is supported for native fixture-backed multi-point Sat vs Sat/Sat vs Lum/Lum vs Sat "
            "payloads already used by color.page_sat_curve_set. The command writes DB-native curve points and verifies "
            "Project.db readback; separate Bezier handle sculpting remains outside the public option surface."
        ),
    },
    "color.page_scope_set_gui": {
        "verified_route": True,
        "verified_routes": ["native_color_page_scopes_gui_readback"],
        "route": "resolve_gui",
        "proof": "macOS Accessibility header readback plus native Scopes settings screenshot pixel readback",
        "caveat": (
            "scope-set drives DaVinci Resolve's native Color Page Scopes panel through a workflow-owned macOS GUI route. "
            "Mode is verified through Accessibility readback of the Scopes header. Y/CbCr/RGB, Colorize, Vectorscope "
            "Show Skin Tone Indicator, and Vectorscope Show 2x Zoom are verified from a captured native settings popover. "
            "The command intentionally does not expose unrelated Scopes controls such as extents/combine/reference levels, "
            "range sliders, graticule intensity, or panel expansion."
        ),
    },
    "color.page_sky_isolation_gui": {
        "render_proof_required": True,
        "readback_scope": (
            "new DB serial node, GUI Power Window/HSL/matte setup, optional GUI Power Window tracking, "
            "GUI Primaries correction, rendered-frame locality proof"
        ),
        "caveat": (
            "`color page sky-isolation` uses the production-safe GUI route, not the disabled DB Layer Mixer payload. It succeeds only "
            "after DaVinci Resolve adds a new serial node, the node graph reads back Power Windows/HSL/Primary tools, rendered before/after "
            "frames differ, and the changed bounds stay inside the configured sky locality guard. When `--track` is set, it also runs the "
            "workflow-owned `color page power-window-track` route before final correction and requires the final node graph to read back "
            "Tracking. Legacy `--slope`, `--offset`, and `--power` DB CDL options intentionally fail."
        ),
    },
    "color.page_sky_isolation_layer": {
        "render_proof_required": True,
        "readback_scope": "unsupported; live DaVinci Resolve 21 proof found the generated DB Layer Mixer topology can fail reopen",
        "caveat": (
            "`color page sky-isolation` is disabled because live DaVinci Resolve 21 verification found the DB-backed "
            "Layer Mixer topology can make the project fail to reopen after mutation. Do not use it for professional "
            "local sky recovery until the topology has post-reopen GUI and Deliver-render proof. Prefer render-proofed "
            "`color cdl`, `color page primary-set --require-render-proof`, and future native GUI/API local correction routes."
        ),
    },
    "color.page_still_match": {
        "verified_route": True,
        "verified_routes": ["native_gallery_still_match_gui_proof"],
        "engine_scope": "workflow_owned_resolve_gui",
        "supported_modes": ["image-wipe", "split-screen"],
        "verified_gallery_routes": ["color gallery still grab", "color gallery still export", "color gallery still apply"],
        "caveat": (
            "`color page still-match` uses a narrow macOS resolve_gui route for DaVinci Resolve's native Color Page Gallery "
            "viewer comparison controls. It resolves the still selector through native Gallery still APIs, selects the matching "
            "thumbnail in the visible Gallery grid, clicks the native Image Wipe or Split Screen control, and captures a proof "
            "screenshot covering the Gallery selection and viewer. This is viewer/session state: prior DB fixture work found no "
            "Project.db rows for wipe position changes, so the route verifies native GUI controls and screenshot proof instead "
            "of claiming a persisted DB payload."
        ),
    },
    "color.power_grade_template_apply": {
        "verified_route": True,
        "verified_routes": ["apply_user_gallery_db_render_proof"],
        "caveat": (
            "PowerGrade template-apply now resolves the template argument as a PowerGrade still selector in the per-user "
            "gallery database and applies that native grade body through the same verified Project.db close/write/reopen "
            "route as color.power_grade_apply. It supports full-grade mode 0 only; selective grade modes 1/2 remain rejected "
            "by validation until they have their own verified native DB/API route and render proof."
        ),
    },
    "color.power_windows": {
        "verified_slices": [
            "page_power_window_circle",
            "page_power_window_gradient",
            "page_power_window_linear",
            "page_power_window_rectangle",
            "page_power_window_polygon",
            "page_power_window_curve",
            "page_power_window_track",
        ],
        "engine_scope": "verified_db_backed_power_window_slices_plus_tracker_gui",
        "residual": (
            "Verified Power Window routes cover named shape creation and selected fixture-backed params. The broad Power Windows "
            "capability is partial and still excludes viewer overlay drag/rotate/feather workflows, Circle extra softness, "
            "Gradient transforms beyond size, Bezier-handle sculpting, and arbitrary tracked/animated mask keyframe editing. "
            "`color page power-window-track` runs DaVinci Resolve's native Color Page Tracker panel buttons through a "
            "workflow-owned resolve_gui route and verifies persisted grade-body tracking state after save. Native Magic Mask "
            "creation/regeneration is not promoted because live DaVinci Resolve Studio 21.0.0b.20 testing returned False "
            "from TimelineItem.CreateMagicMask on real footage even though the method exists. A live Apple Log reprobe "
            "found no scriptable Color Page Power Window transform/tracker methods; only stereo floating-window getters "
            "and timeline track APIs surfaced."
        ),
    },
    "color.qualifier": {
        "verified_slices": [
            "page_qualifier_matte_refinement",
            "page_qualifier_sample",
            "page_white_balance_picker",
        ],
        "engine_scope": "verified_hsl_qualifier_db_slice",
        "residual": (
            "Color qualifier coverage is partial but no longer empty: `color page qualifier-matte-refine` writes the native "
            "Color Page HSL Qualifier range and Matte Finesse Blur Radius DB payload and verifies post-reopen readback. "
            "Verified adjacent routes also export/sample Color Page frames and compute neutral-patch white balance. "
            "RGB/LUM/3D qualifier modes, eyedropper gesture automation, and rendered matte proof remain residual work."
        ),
    },
    "color.tracker": {
        "verified_slices": [
            "color tracker add",
            "color tracker set-target",
            "color tracker track-forward",
            "color tracker track-reverse",
            "color tracker attach-window",
            "color tracker attach-qualifier",
            "color tracker list",
        ],
        "engine_scope": "verified_fusion_native_tracker_command_family",
        "residual": (
            "Color tracker coverage is partial. The supported `color tracker ...` command family uses native Fusion "
            "tracker tools attached to clip Fusion comps and can add/list/retarget/track/attach trackers through "
            "Fusion-native APIs. `color page power-window-track` now covers native Color Page Power Window tracker buttons "
            "through a workflow-owned resolve_gui route with persisted grade-body readback. This does not claim broad native "
            "Color Page tracker parity for generic tracked effects, Magic Mask tracking state, or manually refined Color Page "
            "mask tracking until those states can be run and read back with rendered-frame proof. DaVinci Resolve "
            "Studio exposes TimelineItem.CreateMagicMask/RegenerateMagicMask, but live testing on real footage returned "
            "False for F/B/BI modes from both the disposable Magic Mask proof timeline and the current Apple Log Color "
            "Page clip."
        ),
    },
    "edit.remove_remove_range": {
        "implemented_routes": ["edit remove", "edit remove-range"],
        "native_api": ["Timeline.DeleteClips([timelineItems], False)"],
        "selection_semantics": {
            "edit remove": "one uniquely resolved item at a record-domain position",
            "edit remove-range": "all whole items overlapping a half-open record-domain range",
        },
        "protected_state": [
            "non-target A/V item record and source ranges",
            "linked A/V counterparts outside the requested track scope",
            "active timeline identity",
        ],
        "verified_routes": ["edit remove", "edit remove-range"],
        "verification": "Real-media DaVinci Resolve proof verified stable target identity, non-ripple deletion, protected A/V state, and active-timeline identity.",
        "caveat": (
            "`edit remove` and `edit remove-range` use explicit non-ripple native deletion with stable item identity, "
            "stale-target rejection, one batched write, and protected A/V readback. `edit remove-range` deletes whole "
            "items that overlap the requested half-open range; it does not split partially overlapping edge clips."
        ),
    },
    "edit.razor_native": {
        "verified_route": True,
        "verified_routes": ["edit blade", "edit split"],
        "caveat": (
            "Razor is treated as the DaVinci Resolve/Edit-page naming alias for the verified native blade route. "
            "The public commands are `edit blade` and the compatibility `edit split`; both use the Disk Project.db "
            "blade mutation with preflight/readback verification and preserve timeline item DB properties."
        ),
    },
    "edit.ripple_roll_trim_native": {
        "implemented_routes": ["edit ripple-delete-selected"],
        "native_api": ["Timeline.DeleteClips([timelineItems], True)"],
        "supported_slice": "ripple-delete a stable, uniquely resolved current/named/at-addressed item or its native GetLinkedItems group with gap-closure and protected-track readback",
        "verified_routes": ["edit ripple-delete-selected"],
        "verification": "Real-media DaVinci Resolve proof verified linked A/V deletion, native gap closure, protected-track state, and active-timeline identity.",
        "residual_blockers": [
            "native roll edit point mutation",
            "native arbitrary range ripple delete without pre-splitting",
            "native slip/slide setter parity",
        ],
        "caveat": (
            "`edit ripple-delete-selected` implements the native item-level ripple-delete contract with guarded "
            "readback and has real-media proof for its supported slice. Broader roll-trim, "
            "range-ripple, and slip/slide parity remains explicit residual work and must not be inferred from this slice."
        ),
    },
    "edit.slip_slide": {
        "implemented_routes": ["edit slip-selected", "edit slide-selected"],
        "engine_scope": "workflow_owned_resolve_gui",
        "native_ui": [
            "Trim > Select All Clips Under Playhead",
            "Trim > Select Nearest Clip To > Slip/Slide",
            "Trim > Nudge > One Frame Left/Right",
        ],
        "supported_slice": (
            "video-led linked A/V one-frame Slip/Slide nudges selected through the Edit page, verified against "
            "the complete A/V timeline snapshot; failed multi-step edits receive inverse-nudge compensation"
        ),
        "verified_routes": ["edit slip-selected", "edit slide-selected"],
        "verification": "Real-media DaVinci Resolve proof verified two-step linked A/V Slip and mixed-rate Slide in both directions with protected-state and UI-state readback.",
        "residual_blockers": [
            "multi-frame GUI drag parity",
            "audio-only Slip Audio/Subframe parity",
            "arbitrary slide without adjacent clip reflow readback",
            "range-selection Slip/Slide workflows",
        ],
        "caveat": (
            "`edit slip-selected` and `edit slide-selected` implement guarded one-frame Edit-page nudge workflows "
            "with timeline readback and compensation and have real-media proof for the supported linked A/V slice. "
            "They do not claim full Trim Editor, subframe audio, or arbitrary drag parity."
        ),
    },
}

_MULTICAM_SUPPORT_FEATURES = {
    "edit.multicam_native_create": "create",
    "edit.multicam_native_switch": "switch",
    "edit.multicam_podcast_auto": "job_execute",
    "multicam.create": "create",
    "multicam.convert": "convert",
    "multicam.flatten": "flatten",
    "multicam.match_frame": "match_frame",
    "multicam.angle.remove": "angle_remove",
    "multicam.angle.rename": "angle_rename",
    "multicam.angle.set_enabled": "angle_set_enabled",
    "multicam.audio_activity_calibrate": "audio_activity_calibrate",
    "multicam.inspect": "inspect",
    "multicam.recover_timing": "recover_timing",
    "multicam.replace_audio": "replace_audio",
    "multicam.replace_video": "replace_video",
    "multicam.reorder_angles": "reorder_angles",
    "multicam.seed_timeline": "seed_timeline",
    "multicam.timeline_create": "timeline_create",
    "multicam.switch": "switch",
    "multicam.strip_embedded_audio": "strip_embedded_audio",
    "multicam.settings": "settings",
    "multicam.set_start_timecode": "set_start_timecode",
    "multicam.smart_switch": "smart_switch",
    "multicam.source.grade_cdl": "source_grade_cdl",
    "multicam.source.move": "source_move",
    "multicam.source.property_set": "source_property_set",
    "multicam.source.raw_braw_set": "source_raw_braw_set",
    "multicam.source.remove": "source_remove",
    "multicam.job_execute": "job_execute",
}


def _engine_for(status: str, domain: str) -> str:
    if status == "supported":
        return "fusion_native" if domain == "fusion" else "api_native"
    if status == "partial" and domain in {"color", "edit"}:
        return "workaround_setting"
    if status == "partial":
        return "api_native"
    return "not_available"


def _recoverability_for(status: str, engine: str) -> str:
    if status == "supported" and engine in {"api_native", "fusion_native", "hosted_api"}:
        return "retryable"
    return "manual"


def _verification_required(status: str, engine: str) -> bool:
    if status == "unsupported":
        return True
    return engine in {"db_direct", "db_workaround", "workaround_setting"}


def _render_proof_status(feature_id: str, status: str) -> str:
    if status == "unsupported":
        return "unsupported"
    return _FEATURE_RENDER_PROOF_STATUS_OVERRIDES.get(feature_id, "not_required")


def _build_feature_graph(base: dict[str, dict[str, list[str]]]) -> dict[str, dict[str, object]]:
    graph: dict[str, dict[str, object]] = {}
    multicam_support = build_multicam_support_matrix()
    for status in ("supported", "partial", "unsupported"):
        domains = base.get(status, {})
        for domain, features in domains.items():
            for feature in features:
                feature_id = f"{domain}.{feature}"
                engine = _FEATURE_ENGINE_OVERRIDES.get(feature_id, _engine_for(status, domain))
                graph[feature_id] = {
                    "status": status,
                    "engine": engine,
                    "engine_confidence": _ENGINE_CONFIDENCE.get(engine, 0.5),
                    "verification_required": _FEATURE_VERIFICATION_OVERRIDES.get(
                        feature_id,
                        _verification_required(status, engine),
                    ),
                    "recoverability": _FEATURE_RECOVERABILITY_OVERRIDES.get(
                        feature_id,
                        _recoverability_for(status, engine),
                    ),
                    "render_proof_status": _render_proof_status(feature_id, status),
                }
                fallback_engines = _FEATURE_FALLBACK_ENGINE_OVERRIDES.get(feature_id)
                if fallback_engines:
                    graph[feature_id]["fallback_engines"] = list(fallback_engines)
                caveats = _FEATURE_CAVEATS.get(feature_id)
                if caveats:
                    graph[feature_id]["caveats"] = dict(caveats)
                multicam_operation = _MULTICAM_SUPPORT_FEATURES.get(feature_id)
                if multicam_operation:
                    graph[feature_id]["multicam_support"] = {
                        **multicam_support,
                        "operation": multicam_operation,
                    }
    return graph


def _feature_available_for_transport(
    feature_id: str,
    feature: dict[str, object],
    transport: str | None,
) -> dict[str, object]:
    enriched = dict(feature)
    engine = str(enriched.get("engine") or "")
    transport_override = _FEATURE_TRANSPORT_OVERRIDES.get(feature_id)
    supported_transports = list(transport_override or ["studio_external"])
    unavailable_reason = None

    if transport_override is None:
        if engine in {"api_native", "fusion_native", "hosted_api"}:
            supported_transports.append("embedded_free")
        elif engine in {"db_direct", "db_workaround"}:
            supported_transports.append("embedded_free")
            if enriched.get("verification_required") is not False:
                enriched["verification_required"] = True
        elif engine in {"workaround_setting", "resolve_gui"}:
            supported_transports.append("embedded_free")

    if transport == "embedded_free" and engine == "not_available":
        unavailable_reason = "not_available"
    elif transport == "embedded_free" and "embedded_free" not in supported_transports:
        unavailable_reason = "transport_not_supported"

    enriched["transports"] = supported_transports
    if unavailable_reason:
        enriched["status"] = "unsupported"
        enriched["engine"] = "not_available"
        enriched["engine_confidence"] = 0.0
        enriched["verification_required"] = True
        enriched["recoverability"] = "manual"
        enriched["render_proof_status"] = "unsupported"
        enriched["unavailable_reason"] = unavailable_reason
        enriched["transport_available"] = False
    elif transport:
        enriched["transport_available"] = transport in supported_transports
    return enriched


def _transport_adjust_feature_graph(feature_graph: dict[str, dict[str, object]], transport: str | None) -> dict[str, dict[str, object]]:
    return {
        feature_id: _feature_available_for_transport(feature_id, feature, transport)
        for feature_id, feature in feature_graph.items()
    }


def _group_feature_graph_by_status(
    feature_graph: dict[str, dict[str, object]],
    template: dict[str, dict[str, list[str]]],
) -> dict[str, dict[str, list[str]]]:
    statuses = ("supported", "partial", "unsupported")
    domains = list(
        dict.fromkeys(
            domain
            for status in statuses
            for domain in template.get(status, {})
        )
    )
    grouped = {status: {domain: [] for domain in domains} for status in statuses}
    for feature_id, feature in feature_graph.items():
        status = str(feature.get("status") or "")
        domain, separator, name = feature_id.partition(".")
        if status not in grouped or not separator:
            continue
        grouped[status].setdefault(domain, []).append(name)
    return grouped


def get_capabilities(*, transport: str | None = None, transport_status: dict | None = None) -> dict:
    """Return machine-readable capability map."""
    grouped = deepcopy(_BASE_CAPABILITIES)
    feature_graph = _build_feature_graph(grouped)
    feature_graph = _transport_adjust_feature_graph(feature_graph, transport)
    grouped = _group_feature_graph_by_status(feature_graph, grouped)
    return {
        "capabilities_schema_version": CAPABILITIES_SCHEMA_VERSION,
        "transport": transport,
        "transport_status": transport_status,
        "multicam_support": build_multicam_support_matrix(),
        "supported": grouped["supported"],
        "partial": grouped["partial"],
        "unsupported": grouped["unsupported"],
        "feature_graph": feature_graph,
    }
