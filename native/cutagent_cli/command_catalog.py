"""Source-derived command catalog for internal docs and contract sync."""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .capabilities import get_capabilities

ROOT = Path(__file__).resolve().parents[1]
MAIN_FILE = ROOT / "cutagent_cli" / "main.py"
COMMANDS_DIR = ROOT / "cutagent_cli" / "commands"
# Build-time catalog snapshot, consulted only when the package ships compiled
# (Nuitka) and the original ``.py`` sources are no longer on disk to parse.
SNAPSHOT_FILE = ROOT / "cutagent_cli" / "command_catalog_snapshot.json"
SNAPSHOT_VERSION = 1
SNAPSHOT_KIND_FULL = "full"
SNAPSHOT_KIND_PUBLIC_RUNTIME = "public_runtime"
_PUBLIC_RUNTIME_TEXT_REPLACEMENTS = {
    "Project.db": "project database",
    "Sm2TiItem_id": "item id",
    "Sm2TiItem": "timeline item",
    "EffectFiltersBA": "effect settings",
    "LmVersion": "timeline data",
    "db_workaround": "native persistence",
    "compressed protobuf": "encoded data",
    "parameters": "settings",
    "Parameters": "Settings",
    "params": "settings",
    "Params": "Settings",
    "defaults": "standard settings",
    "Defaults": "Standard settings",
    "default": "standard",
    "Default": "Standard",
}
PUBLIC_COMMAND_LABELS_FILE = ROOT.parent / "cutagent-cli-command-metadata" / "command-labels.json"


def _facade_shard_source(path: Path) -> str | None:
    """Return reconstructed source for command facades split into shards."""
    shard_dirs = [
        path.with_name(f"_{path.stem}"),
        path.with_name(f"_{path.stem}_command"),
    ]
    shard_dir = next((candidate for candidate in shard_dirs if candidate.is_dir()), None)
    if shard_dir is None:
        return None
    parts = sorted(shard_dir.glob("part_*.py"))
    if not parts:
        return None

    source_parts: list[str] = []
    for index, part in enumerate(parts):
        text = part.read_text(encoding="utf-8")
        if index > 0 and text.startswith("from __future__ import annotations\n\n"):
            text = text.removeprefix("from __future__ import annotations\n\n")
        source_parts.append(text)
    return "".join(source_parts)

_DOCS_TOPIC_BY_ROOT = {
    "asset": "asset",
    "audio": "audio",
    "auto-edit": "timeline",
    "batch": "timeline",
    "burnin": "render",
    "capabilities": "orchestration",
    "clip": "clip",
    "codec": "developer-sdk",
    "color": "color",
    "connect": "orchestration",
    "dctl": "developer-sdk",
    "developer": "developer-sdk",
    "doctor": "orchestration",
    "edit": "timeline",
    "fairlight": "audio",
    "fuse": "developer-sdk",
    "fusion": "fusion",
    "info": "orchestration",
    "launch": "orchestration",
    "layout": "orchestration",
    "lut": "developer-sdk",
    "media": "media",
    "multicam": "timeline",
    "ofx": "developer-sdk",
    "page": "orchestration",
    "product": "orchestration",
    "project": "project",
    "quit": "orchestration",
    "render": "render",
    "script": "developer-sdk",
    "status": "orchestration",
    "storage": "media",
    "system": "orchestration",
    "text": "text",
    "timeline": "timeline",
    "transcript": "audio",
    "version": "orchestration",
    "workflow": "developer-sdk",
}

_GROUP_CAPABILITY_HINTS = {
    ("burnin", "load"): "render.burnin_preset_import_export",
    ("burnin", "preset"): "render.burnin_preset_import_export",
    ("clip", "burnin"): "render.burnin_preset_import_export",
    ("clip", "cache_set"): "clip.cache_control",
    ("clip", "cache_state"): "clip.cache_control",
    ("clip", "fusion"): "clip.fusion_comp",
    ("clip", "keyframe"): "clip.keyframe_crud",
    ("clip", "linked"): "clip.linked_items",
    ("clip", "marker"): "clip.marker",
    ("clip", "offset"): "clip.track_info",
    ("clip", "reset_node_colors"): "color.node_graph_ops",
    ("clip", "source_audio_mapping"): "clip.audio_channel_mapping",
    ("clip", "source_range"): "clip.track_info",
    ("clip", "stereo_values"): "clip.stereo_values",
    ("clip", "take"): "clip.take",
    ("clip", "track_info"): "clip.track_info",
    ("clip", "update_sidecar"): "clip.properties_write",
    ("color", "arri_cdl_lut"): "color.arri_cdl_lut_helper",
    ("color", "gallery"): "color.gallery_stills",
    ("color", "graph"): "color.node_graph_ops",
    ("color", "group"): "color.color_group_management",
    ("color", "node"): "color.node_graph_ops",
    ("color", "power_grade"): "color.gallery_power_grade_list_album",
    ("color", "qualifier"): "fusion.mutation",
    ("color", "secondary"): "fusion.mutation",
    ("color", "still"): "timeline.grab_still",
    ("color", "tracker"): "fusion.mutation",
    ("fairlight", "automation"): "fairlight.automation",
    ("fairlight", "adr", "info"): "fairlight.adr_read",
    ("fairlight", "adr"): "fairlight.adr",
    ("fairlight", "bounce"): "fairlight.bounce",
    ("fairlight", "bus"): "fairlight.bus_routing",
    ("fairlight", "channel_map", "clip"): "fairlight.channel_mapping_read",
    ("fairlight", "channel_map", "media"): "fairlight.channel_mapping_read",
    ("fairlight", "channel_map", "set"): "fairlight.channel_mapping_write",
    ("fairlight", "clip", "delete"): "fairlight.clip_delete",
    ("fairlight", "clip", "info"): "clip.track_info",
    ("fairlight", "clip", "link"): "clip.link_unlink",
    ("fairlight", "clip", "linked"): "clip.linked_items",
    ("fairlight", "clip", "source_range"): "clip.track_info",
    ("fairlight", "clip", "track_info"): "clip.track_info",
    ("fairlight", "clip", "unlink"): "clip.link_unlink",
    ("fairlight", "clip", "move"): "fairlight.clip_move",
    ("fairlight", "clip", "nudge"): "fairlight.clip_move",
    ("fairlight", "clip", "slip"): "fairlight.clip_slip",
    ("fairlight", "clip", "split"): "fairlight.clip_split",
    ("fairlight", "clip", "trim"): "fairlight.clip_trim",
    ("fairlight", "crossfade"): "fairlight.crossfade_batch",
    ("fairlight", "elastic", "enable"): "fairlight.elastic_wave_enable",
    ("fairlight", "elastic", "info"): "fairlight.elastic_wave_read",
    ("fairlight", "elastic"): "fairlight.elastic_wave",
    ("fairlight", "effect", "catalog"): "fairlight.track_effect_catalog",
    ("fairlight", "effect", "list"): "fairlight.clip_effect_list",
    ("fairlight", "effect", "params"): "fairlight.clip_effect_params",
    ("fairlight", "effect", "plugin_catalog"): "fairlight.plugin_catalog_read",
    ("fairlight", "effect", "slot_scan"): "fairlight.plugin_slot_probe",
    ("fairlight", "effect", "set_param"): "fairlight.clip_effect_param_write",
    ("fairlight", "effect"): "fairlight.plugin_routing",
    ("fairlight", "export"): "fairlight.audio_export",
    ("fairlight", "external_process", "list"): "fairlight.external_process_read",
    ("fairlight", "external_process"): "fairlight.external_process",
    ("fairlight", "fade-out"): "fairlight.fade_out_batch",
    ("fairlight", "group", "list"): "fairlight.group_read",
    ("fairlight", "group"): "fairlight.groups",
    ("fairlight", "info"): "fairlight.track_info",
    ("fairlight", "index"): "fairlight.index_read",
    ("fairlight", "io", "info"): "fairlight.patch_io_read",
    ("fairlight", "io"): "fairlight.patch_io",
    ("fairlight", "item-source"): "fairlight.item_source_patch",
    ("fairlight", "loudness", "info"): "fairlight.loudness_read",
    ("fairlight", "loudness"): "fairlight.loudness",
    ("fairlight", "mixer", "fader"): "fairlight.fader",
    ("fairlight", "mixer", "meter"): "fairlight.metering",
    ("fairlight", "mixer", "meter_settings"): "fairlight.metering_read",
    ("fairlight", "mixer", "pan"): "fairlight.pan",
    ("fairlight", "monitor", "info"): "fairlight.monitoring_read",
    ("fairlight", "monitor"): "fairlight.monitoring",
    ("fairlight", "preset"): "fairlight.preset",
    ("fairlight", "record", "info"): "fairlight.recording_read",
    ("fairlight", "record"): "fairlight.recording",
    ("fairlight", "send"): "fairlight.sends",
    ("fairlight", "sound_library", "delete"): "fairlight.sound_library_delete",
    ("fairlight", "sound_library", "list"): "fairlight.sound_library_read",
    ("fairlight", "sound_library", "search"): "fairlight.sound_library_read",
    ("fairlight", "sound_library", "source_list"): "fairlight.sound_library_read",
    ("fairlight", "sound_library", "index_file"): "fairlight.sound_library_index",
    ("fairlight", "sound_library", "index_folder"): "fairlight.sound_library_index",
    ("fairlight", "sound_library", "source_rebuild"): "fairlight.sound_library_index",
    ("fairlight", "sound_library", "source_remove"): "fairlight.sound_library_delete",
    ("fairlight", "sound_library", "audition"): "fairlight.sound_library_audition",
    ("fairlight", "sound_library", "preview"): "fairlight.sound_library_audition",
    ("fairlight", "sound_library"): "fairlight.sound_library",
    ("fairlight", "track", "folder"): "fairlight.track_folder",
    ("fairlight", "track_format"): "fairlight.track_format_write",
    ("fairlight", "track_order"): "fairlight.track_reorder",
    ("fairlight", "tracks"): "fairlight.track_management",
    ("fairlight", "transition", "add"): "fairlight.transition",
    ("fairlight", "vca", "list"): "fairlight.vca_read",
    ("fairlight", "vca"): "fairlight.vca",
    ("fairlight", "waveform", "info"): "fairlight.waveform_view_read",
    ("fairlight", "waveform"): "fairlight.waveform_editing",
    ("fairlight", "voice_isolation", "get"): "fairlight.timeline_voice_isolation",
    ("fairlight", "voice_isolation", "set"): "fairlight.timeline_voice_isolation",
    ("fairlight", "voice_isolation"): "fairlight.timeline_voice_isolation",
    ("fusion", "comp", "delete"): "clip.fusion_comp",
    ("fusion", "comp", "rename"): "clip.fusion_comp",
    ("fusion", "image"): "fusion.mutation",
    ("fusion", "keyframe"): "fusion.mutation",
    ("fusion", "macro"): "fusion.mutation",
    ("fusion", "nested-text"): "fusion.mutation",
    ("fusion", "nested_text"): "fusion.mutation",
    ("fusion", "node"): "fusion.mutation",
    ("fusion", "template", "apply"): "fusion.mutation",
    ("fusion", "text"): "fusion.mutation",
    ("fusion", "tool"): "fusion.mutation",
    ("layout", "update"): "system.layout_preset",
    ("media", "audio_mapping"): "media.audio_mapping",
    ("media", "folder", "export_drb"): "media.import",
    ("media", "folder", "import_drb"): "media.import",
    ("media", "folders"): "media.folder_management",
    ("media", "flag"): "media.flag_color",
    ("media", "growing_file"): "media.clip_management",
    ("media", "mark"): "media.mark_in_out",
    ("media", "marker"): "media.marker_crud",
    ("media", "matte"): "media.clip_management",
    ("media", "proxy"): "media.proxy_transcode",
    ("media", "rename"): "media.clip_management",
    ("media", "replace"): "media.clip_management",
    ("media", "replace_preserve_subclip"): "media.clip_management",
    ("media", "selected", "list"): "media.list",
    ("media", "selected", "set"): "media.clip_management",
    ("media", "stereo_create"): "media.stereo_clip",
    ("media", "third_party_metadata"): "media.metadata_write",
    ("media", "timeline_matte"): "media.clip_management",
    ("auto_edit", "podcast_edit"): "edit.multicam_podcast_auto",
    ("auto_edit", "podcast_multicam"): "edit.multicam_podcast_auto",
    ("edit", "camera_pip"): "clip.transform",
    ("edit", "social_crop"): "clip.transform",
    ("timeline", "clip_markers"): "clip.marker",
    ("timeline", "clip-color"): "timeline.clip_color_batch",
    ("multicam", "audio_activity", "calibrate"): "multicam.audio_activity_calibrate",
    ("multicam", "create"): "multicam.create",
    ("multicam", "convert"): "multicam.convert",
    ("multicam", "flatten"): "multicam.flatten",
    ("multicam", "inspect"): "multicam.inspect",
    ("multicam", "match_frame"): "multicam.match_frame",
    ("multicam", "angle", "remove"): "multicam.angle.remove",
    ("multicam", "angle", "rename"): "multicam.angle.rename",
    ("multicam", "angle", "set_enabled"): "multicam.angle.set_enabled",
    ("multicam", "recover_timing"): "multicam.recover_timing",
    ("multicam", "replace", "audio"): "multicam.replace_audio",
    ("multicam", "replace", "video"): "multicam.replace_video",
    ("multicam", "replace_audio"): "multicam.replace_audio",
    ("multicam", "reorder_angles"): "multicam.reorder_angles",
    ("multicam", "seed_timeline"): "multicam.seed_timeline",
    ("multicam", "settings"): "multicam.settings",
    ("multicam", "set_start_timecode"): "multicam.set_start_timecode",
    ("multicam", "smart_switch"): "multicam.smart_switch",
    ("multicam", "source", "grade_cdl"): "multicam.source.grade_cdl",
    ("multicam", "source", "move"): "multicam.source.move",
    ("multicam", "source", "property_set"): "multicam.source.property_set",
    ("multicam", "source", "raw_braw_set"): "multicam.source.raw_braw_set",
    ("multicam", "source", "remove"): "multicam.source.remove",
    ("multicam", "strip_embedded_audio"): "multicam.strip_embedded_audio",
    ("multicam", "switch"): "multicam.switch",
    ("multicam", "timeline_create"): "multicam.timeline_create",
    ("page", "current"): "page.navigation",
    ("page", "switch"): "page.navigation",
    ("project", "db"): "project.db_switch",
    ("project", "folders"): "project.folder_management",
    ("project", "cleanup_scratch"): "project.cleanup_scratch",
    ("project", "cloud", "create"): "project.cloud.create",
    ("project", "cloud", "import"): "project.cloud.import",
    ("project", "cloud", "open"): "project.cloud.open",
    ("project", "cloud", "restore"): "project.cloud.restore",
    ("project", "preset"): "project.preset_list",
    ("project", "preset", "load"): "project.preset_load",
    ("project", "preset", "save"): "project.preset_save",
    ("project", "settings"): "project.settings_read",
    ("project", "settings_get"): "project.settings_read",
    ("project", "settings_set"): "project.settings_write",
    ("project", "rename"): "project.settings_write",
    ("project", "save"): "project.settings_write",
    ("render", "alpha"): "render.settings_write",
    ("render", "audio"): "render.audio_only",
    ("render", "burnin"): "render.burnin_preset_import_export",
    ("render", "encoding"): "render.settings_write",
    ("render", "export_file"): "render.export_file",
    ("render", "export_preset"): "render.preset_import_export",
    ("render", "import_preset"): "render.preset_import_export",
    ("render", "job_status"): "render.status",
    ("render", "mode"): "render.mode_set",
    ("render", "preset_delete"): "render.preset_save",
    ("render", "preset_save"): "render.preset_save",
    ("render", "resolutions"): "render.resolutions",
    ("render", "settings"): "render.settings_read",
    ("render", "settings_get"): "render.settings_read",
    ("render", "settings_set_json"): "render.settings_write",
    ("render", "settings_set_key"): "render.settings_write",
    ("render", "subtitles"): "render.settings_write",
    ("storage", "import_sequence"): "media.import",
    ("storage", "import_subclip"): "media.import",
    ("storage", "matte"): "media.clip_management",
    ("storage", "reveal"): "media.import",
    ("system", "keyframe_mode"): "system.keyframe_mode",
    ("timeline", "dolby"): "timeline.dolby_vision",
    ("timeline", "fairlight_preset"): "fairlight.preset",
    ("timeline", "fusion_clip"): "fusion.comp_add_delete_import_export",
    ("timeline", "fusion_composition"): "fusion.comp_add_delete_import_export",
    ("timeline", "import_into"): "timeline.import_export",
    ("timeline", "marker"): "timeline.marker_crud",
    ("timeline", "items"): "timeline.items_delete",
    ("timeline", "mark"): "timeline.marker_crud",
    ("timeline", "media_pool_item"): "timeline.item_at",
    ("timeline", "node_graph"): "color.node_graph_ops",
    ("timeline", "playhead"): "timeline.playhead_set",
    ("timeline", "still"): "timeline.grab_still",
    ("timeline", "subtitle", "insert"): "timeline.subtitle_arbitrary_insert",
    ("timeline", "stereo_convert"): "timeline.stereo_convert",
    ("timeline", "subtitle"): "timeline.subtitle_list_add_export",
    ("timeline", "track"): "timeline.track_management",
    ("timeline", "voice_isolation", "get"): "fairlight.timeline_voice_isolation",
    ("timeline", "voice_isolation", "set"): "fairlight.timeline_voice_isolation",
    ("timeline", "voice_isolation"): "fairlight.timeline_voice_isolation",
    ("text", "insert"): "text.insert",
    ("text", "insert-preset"): "text.insert_preset",
    ("text", "insert-template"): "text.insert_template",
    ("text", "insert-template-batch"): "text.insert_template_batch",
    ("text", "insert-captions"): "text.insert_captions",
    ("text", "update"): "text.update",
    ("text", "inspect"): "text.inspect",
    ("text", "list-presets"): "text.list_presets",
}

_COMMAND_CAPABILITY_HINTS = {
    "audio.beat_detect": "audio.beat_detection",
    "audio.voice_generate": "audio.voiceover",
    "audio.voice_list": "audio.voiceover",
    "audio.voice_place": "audio.voiceover",
    "audio.duck": "edit.audio_duck_sidechain",
    "clip.disable": "clip.enable_disable",
    "clip.enable": "clip.enable_disable",
    "clip.flag": "clip.flag",
    "clip.link": "clip.link_unlink",
    "clip.list": "clip.list_read",
    "clip.properties": "clip.properties_write",
    "clip.speed_ramp": "edit.speed_ramp_workaround",
    "clip.unlink": "clip.link_unlink",
    "edit.ripple_delete_selected": "edit.ripple_roll_trim_native",
    "edit.slide_selected": "edit.slip_slide",
    "edit.slip_selected": "edit.slip_slide",
    "fairlight.ai.read": "fairlight.ai_read",
    "fusion.setting.inspect": "fusion.setting_inspect",
    "fusion.setting.summary": "fusion.setting_summary",
    "fusion.setting.validate": "fusion.setting_validate",
    "fusion.generate": "fusion.setting_generation",
    "fusion.comp.current": "fusion.comp_add_delete_import_export",
    "fusion.keyframe.list": "fusion.keyframes",
    "fusion.template.show": "fusion.template_management",
    "fusion.template.assets.add": "fusion.template_management",
    "fusion.template.assets.list": "fusion.template_management",
    "fusion.template.dir": "fusion.template_management",
    "fusion.template.icon.set": "fusion.template_management",
    "fusion.template.install": "fusion.template_management",
    "fusion.template.list": "fusion.template_management",
    "fusion.template.package_drfx": "fusion.template_management",
    "fusion.template.scaffold": "fusion.template_management",
    "fusion.template.uninstall": "fusion.template_management",
    "fusion.template.unpack_drfx": "fusion.template_management",
    "fusion.template.validate": "fusion.template_management",
    "fusion.tool.attrs": "fusion.tool_list_get_set",
    "fusion.tool.get": "fusion.tool_list_get_set",
    "fusion.tool.inputs": "fusion.tool_list_get_set",
    "fusion.tool.list": "fusion.tool_list_get_set",
    "fusion.tool.outputs": "fusion.tool_list_get_set",
    "lut.convert": "system.lut_management",
    "lut.generate.identity": "system.lut_management",
    "lut.install": "system.lut_management",
    "lut.inspect": "system.lut_management",
    "lut.list": "system.lut_management",
    "lut.remove": "system.lut_management",
    "lut.validate": "system.lut_management",
    "project.db.backup": "project.db_backup",
    "project.db.create": "project.db_create",
    "project.db.restore": "project.db_restore",
    "fairlight.effect.add": "fairlight.builtin_effect_route",
    "fairlight.effect.remove": "fairlight.builtin_effect_route",
    "fairlight.preset.list": "fairlight.preset_list",
    "color.curves": "color.curves_lut",
    "color.inspect": "color.node_graph_ops",
    "color.lut": "color.lut_set_clear",
    "color.lut_refresh": "system.lut_refresh",
    "color.mask.inspect": "color.node_graph_ops",
    "color.nodes": "color.node_graph_ops",
    "color.reset_fusion": "fusion.mutation",
    "fusion.insert_setting": "fusion.setting_insert",
    "color.page.hdr_detail_set": "color.page_hdr_detail_set",
    "color.page.hdr_zone_set": "color.page_hdr_zone_set",
    "color.page.read": "color.page_wheel_set",
    "color.page.snapshot": "color.page_wheel_set",
    "color.page.wheel_set": "color.page_wheel_set",
    "color.page.primary_set": "color.page_primary_set",
    "color.page.primary_gui_set": "color.page_primary_gui_set",
    "color.page.curve_set": "color.page_curve_set",
    "color.page.curve_points_set": "color.page_curve_points_set",
    "color.page.split_tone_set": "color.page_split_tone_set",
    "color.page.hsv_node_set": "color.page_hsv_node_set",
    "color.page.hue_curve_set": "color.page_hue_curve_set",
    "color.page.sat_curve_set": "color.page_sat_curve_set",
    "color.page.hdr_global_set": "color.page_hdr_global_set",
    "color.page.key_output_set": "color.page_key_output_set",
    "color.page.alpha_output_connect": "color.page_alpha_output_connect",
    "color.page.bleach_bypass_set": "color.page_bleach_bypass",
    "color.page.rgb_mixer_set": "color.page_rgb_mixer_monochrome",
    "color.page.layer_mixer_set": "color.page_layer_mixer_composite",
    "color.page.sky_isolation": "color.page_sky_isolation_gui",
    "color.page.node_add": "color.page_node_add_serial",
    "color.page.node_cleanup": "color.page_node_cleanup_empty_serial",
    "color.page.bleach_bypass_intensity_set": "color.page_bleach_bypass_intensity",
    "color.page.cst_set": "color.page_cst_set",
    "color.page.power_window_circle": "color.page_power_window_circle",
    "color.page.power_window_gradient": "color.page_power_window_gradient",
    "color.page.power_window_linear": "color.page_power_window_linear",
    "color.page.power_window_rectangle": "color.page_power_window_rectangle",
    "color.page.power_window_gui_set": "color.page_power_window_gui_set",
    "color.page.power_window_polygon": "color.page_power_window_polygon",
    "color.page.power_window_curve": "color.page_power_window_curve",
    "color.page.param_delete": "color.page_param_delete",
    "color.page.scope_read": "color.page_scope_read",
    "color.page.false_color_read": "color.page_false_color_read",
    "color.page.viewer_before_after": "color.page_viewer_before_after",
    "color.page.shot_match_analyze": "color.page_shot_match_analyze",
    "color.page.shot_match_apply": "color.page_shot_match_apply",
    "color.page.qualifier_sample": "color.page_qualifier_sample",
    "color.page.white_balance_picker": "color.page_white_balance_picker",
    "color.page.lut_library_import": "color.page_lut_library_import",
    "color.page.dctl_apply": "color.page_dctl_apply",
    "color.page.dctl_remove": "color.page_dctl_remove",
    "color.page.resolvefx_add": "color.page_resolvefx_add",
    "color.page.resolvefx_list": "color.page_resolvefx_list",
    "color.page.resolvefx_param_discover": "color.page_resolvefx_param_discover",
    "color.page.resolvefx_param_list": "color.page_resolvefx_param_list",
    "color.page.resolvefx_param_set": "color.page_resolvefx_param_set",
    "color.page.resolvefx_remove": "color.page_resolvefx_remove",
    "color.page.ofx_glow_set": "color.page_ofx_glow_set",
    "color.page.sharpen_set": "color.page_sharpen_set",
    "color.page.softening_set": "color.page_softening_set",
    "color.page.magic_mask": "color.page_magic_mask",
    "color.page.magic_mask_draw_stroke": "color.page_magic_mask",
    "color.page.auto_color_ai": "ai_neural.auto_color_ai",
    "color.page.qualifier_panel_probe": "color.page_qualifier_panel_probe",
    "color.page.qualifier_gui_hsl_set": "color.page_qualifier_gui_hsl_set",
    "color.page.qualifier_gui_matte_set": "color.page_qualifier_gui_matte_set",
    "color.page.cat_set": "color.page_cat_set",
    "color.page.scope_set": "color.page_scope_set_gui",
    "color.page.color_slice_set": "color.page_color_slice",
    "color.page.warper_set": "color.page_color_warper",
    "color.page.curve_spline_set": "color.page_curve_spline_freeform",
    "color.page.hue_curve_spline_set": "color.page_hue_curve_gui_spline",
    "color.page.sat_curve_spline_set": "color.page_sat_curve_gui_spline",
    "color.page.power_window_gradient_transform": "color.page_power_window_gradient_transform",
    "color.page.power_window_circle_detail": "color.page_power_window_circle_detail",
    "color.page.power_window_overlay_transform": "color.page_power_window_overlay_transform",
    "color.page.power_window_track": "color.page_power_window_track",
    "color.page.still_match": "color.page_still_match",
    "color.page.node_add_topology": "color.page_node_add_arbitrary_topology",
    "color.page.node_cleanup_general": "color.page_node_cleanup_general",
    "color.page.qualifier_matte_refine": "color.page_qualifier_matte_refinement",
    "color.page.magic_mask_refine": "color.page_magic_mask_refinement",
    "color.node.cache": "color.node_graph_ops",
    "color.node.disable": "color.node_graph_ops",
    "color.node.enable": "color.node_graph_ops",
    "color.node.label_get": "color.node_graph_ops",
    "color.node.label_set": "color.node_graph_ops",
    "color.node.lut_get": "color.node_graph_ops",
    "color.node.tools": "color.node_graph_ops",
    "color.grade_copy": "color.grade_copy_apply",
    "color.source_grade.plan": "color.source_remote_grade",
    "color.source_grade.prepare_remote": "color.source_remote_grade",
    "color.source_grade.apply_cdl": "color.source_remote_grade",
    "color.grade_apply": "color.grade_apply_drx",
    "color.power_grade.apply": "color.power_grade_apply",
    "color.power_grade.template_apply": "color.power_grade_template_apply",
    "color.power_grade.list": "color.gallery_power_grade_list_album",
    "color.power_grade.album.create": "color.gallery_power_grade_list_album",
    "color.version.load": "color.grade_copy_apply",
    "color.version.activate": "color.grade_copy_apply",
    "color.version.rollback": "color.grade_copy_apply",
    "color.version.duplicate": "color.grade_copy_apply",
    "color.cdl": "color.cdl_set",
    "color.wheels.set": "color.wheels_emulation",
    "edit.auto_subtitle": "timeline.subtitle_list_add_export",
    "edit.blade": "edit.blade_native",
    "edit.split": "edit.blade_native",
    "auto_edit.silence_cut": "auto_edit.silence_cut",
    "edit.from_edl": "timeline.import_export",
    "fairlight.ai.dialogue_leveler": "fairlight.dialogue_leveler",
    "fairlight.ai.music_remixer": "fairlight.music_remixer",
    "fairlight.ai.voice_isolation": "clip.voice_isolation",
    "fairlight.add": "fairlight.track_management",
    "fairlight.adr.info": "fairlight.adr_read",
    "fairlight.api_notes": "fairlight.track_info",
    "fairlight.audio_gain.batch": "fairlight.audio_gain_batch",
    "fairlight.audio_pan.batch": "fairlight.audio_pan_batch",
    "fairlight.automation.list": "fairlight.automation_read",
    "fairlight.bus.level": "fairlight.bus_read",
    "fairlight.bus.list": "fairlight.bus_read",
    "fairlight.clip.delete": "fairlight.clip_delete",
    "fairlight.clip.info": "clip.track_info",
    "fairlight.clip.link": "clip.link_unlink",
    "fairlight.clip.linked.list": "clip.linked_items",
    "fairlight.clip.source_range": "clip.track_info",
    "fairlight.clip.track_info": "clip.track_info",
    "fairlight.clip.unlink": "clip.link_unlink",
    "fairlight.clip.move": "fairlight.clip_move",
    "fairlight.clip.nudge": "fairlight.clip_move",
    "fairlight.clip.slip": "fairlight.clip_slip",
    "fairlight.clip.split": "fairlight.clip_split",
    "fairlight.clip.trim": "fairlight.clip_trim",
    "fairlight.crossfade.batch": "fairlight.crossfade_batch",
    "fairlight.delete": "fairlight.track_management",
    "fairlight.ensure_tracks": "fairlight.track_management",
    "fairlight.ensure_stereo_tracks": "fairlight.stereo_track_management",
    "fairlight.elastic.enable": "fairlight.elastic_wave_enable",
    "fairlight.elastic.info": "fairlight.elastic_wave_read",
    "fairlight.effect.plugin_catalog": "fairlight.plugin_catalog_read",
    "fairlight.effect.slot_scan": "fairlight.plugin_slot_probe",
    "fairlight.external_process.list": "fairlight.external_process_read",
    "fairlight.export.audio": "fairlight.audio_export",
    "fairlight.fade_in.batch": "fairlight.fade_in_batch",
    "fairlight.fade_out.batch": "fairlight.fade_out_batch",
    "fairlight.group.list": "fairlight.group_read",
    "fairlight.info": "fairlight.track_info",
    "fairlight.items": "clip.track_info",
    "fairlight.item_source.patch": "fairlight.item_source_patch",
    "fairlight.lock": "fairlight.track_state",
    "fairlight.loudness.info": "fairlight.loudness_read",
    "fairlight.mixer.read": "fairlight.mixer_read",
    "fairlight.mute": "fairlight.track_state",
    "fairlight.record.info": "fairlight.recording_read",
    "fairlight.rename": "fairlight.track_management",
    "fairlight.send.list": "fairlight.sends_read",
    "fairlight.transition.add": "fairlight.transition",
    "fairlight.track.duplicate": "fairlight.track_duplicate",
    "fairlight.track.folder": "fairlight.track_folder",
    "fairlight.track.height": "fairlight.track_height",
    "fairlight.track.hide": "fairlight.track_visibility",
    "fairlight.track.input_monitor": "fairlight.input_monitoring",
    "fairlight.track.show": "fairlight.track_visibility",
    "fairlight.unlock": "fairlight.track_state",
    "fairlight.unmute": "fairlight.track_state",
    "fairlight.vca.list": "fairlight.vca_read",
    "timeline.clip-color.batch": "timeline.clip_color_batch",
    "timeline.clip_color.batch": "timeline.clip_color_batch",
    "timeline.marker.batch": "timeline.marker_crud",
    "timeline.items.delete": "timeline.items_delete",
    "timeline.items.set_duration": "timeline.item_duration_set",
    "timeline.items.move": "timeline.item_move",
    "fairlight.solo_restore": "fairlight.solo",
    "timeline.auto_caption": "timeline.subtitle_list_add_export",
    "timeline.subtitle.insert": "timeline.subtitle_arbitrary_insert",
    "version.create": "version.checkpoint",
    "version.inspect": "version.checkpoint",
    "version.list": "version.checkpoint",
    "version.prune": "version.checkpoint",
    "version.restore": "version.checkpoint",
    "version.status": "version.checkpoint",
    "color.window.attach": "fusion.mutation",
    "color.window.detach": "fusion.mutation",
    "color.window.ellipse": "fusion.mutation",
    "color.window.polygon": "fusion.mutation",
    "color.window.rectangle": "fusion.mutation",
    "color.window.reorder": "fusion.mutation",
    "text.insert": "text.insert",
    "text.insert_preset": "text.insert_preset",
    "text.insert_template": "text.insert_template",
    "text.insert_template_batch": "text.insert_template_batch",
    "text.insert_captions": "text.insert_captions",
    "text.update": "text.update",
    "text.inspect": "text.inspect",
    "text.list_presets": "text.list_presets",
}

_SOURCE_HANDLER_CONTRACTS: dict[str, dict[str, Any]] = {}

_COMMAND_ENGINE_OVERRIDES = {
    "audio.voice_place": "api_native",
    "color.node.label_set": "db_workaround",
    "fusion.insert_setting": "workaround_setting",
    "color.version.load": "workaround_setting",
}

_COMMAND_CAVEAT_OVERRIDES = {
    "color.node.label_set": {
        "primary_route": "native SetNodeLabel when available",
        "verified_fallback": "db_workaround_color_page_node_label_set",
        "route_truth": (
            "This command first attempts the native Color Page node graph API, then uses the verified Project.db "
            "mutation/readback route when DaVinci Resolve does not expose SetNodeLabel. Catalog engine metadata uses "
            "db_workaround so agents do not treat label writes as guaranteed pure api_native behavior."
        ),
        "verified_route": True,
    },
    "fusion.insert_setting": {
        "primary_route": "holder insertion plus timeline_item.ImportFusionComp",
        "verified_fallback": "isolated scratch holder plus Project.db transplant for precise track/frame placement",
        "route_truth": (
            "This command is a deterministic .setting workflow. It can use native holder insertion and "
            "ImportFusionComp, but precise placement may use Media Pool holder append or an isolated scratch "
            "timeline plus Project.db transplant with exact post-reopen enumeration. Catalog engine metadata uses "
            "workaround_setting so agents treat it as an orchestrated setting route, not a pure Fusion API mutation."
        ),
        "verified_route": True,
    },
}

_KEYWORD_HINTS = {
    "asset.resolve": (
        "resolve asset",
        "fallback asset",
        "fallback template",
        "find template or media",
        "find custom media",
        "custom database media",
        "resolve fusion template",
    ),
    "media.import": (
        "import media",
        "import footage",
        "import files",
        "import folder",
        "import mov",
        "import b-roll",
        "ingest footage",
        "bring media into project",
        "bring footage into project",
        "bring a folder of footage into the current project",
    ),
    "media.transcode": (
        "transcode media",
        "generate proxy",
        "proxy workflow",
        "make lightweight editing copy",
        "convert media",
        "create h264 proxy file",
    ),
    "media.proxy.link_fullres": (
        "link full resolution media",
        "reconnect fullres",
        "proxy relink",
        "replace proxy with fullres",
        "link proxy to original media",
    ),
    "media.extract_template": (
        "extract template",
        "read media pool template text",
        "read lower third template",
        "inspect fusion template metadata",
        "extract text image from template",
    ),
    "media.delete": ("delete clip", "remove clip"),
    "page.switch": (
        "switch page",
        "open page",
        "go to page",
        "go to color page",
        "go to edit page",
        "open color page",
        "switch to color page",
        "switch to edit page",
    ),
    "timeline.delete": ("delete timeline", "delete current timeline", "remove timeline"),
    "timeline.rename": ("rename timeline", "rename current timeline", "change timeline name"),
    "timeline.items.delete": (
        "delete timeline items",
        "delete clips but keep tracks",
        "delete timeline clips",
        "clear timeline items",
        "remove timeline items",
        "remove clips but keep tracks",
    ),
    "timeline.items.set_duration": (
        "set timeline item duration",
        "set timeline item end",
        "extend timeline item",
        "extend background",
        "extend holder",
        "fix overlay duration",
        "prodluž holder",
        "nastav délku itemu",
    ),
    "timeline.clip_color.batch": (
        "batch timeline clip color",
        "set clip colors by frame range",
        "color timeline clips",
        "bulk clip color",
    ),
    "timeline.marker.add": ("add timeline marker", "add marker to timeline", "create timeline marker"),
    "timeline.marker.batch": ("batch timeline markers", "add range markers", "add timeline markers from json", "highlight markers"),
    "timeline.marker.delete": (
        "delete timeline marker",
        "delete timeline markers",
        "remove timeline marker",
        "clear timeline markers",
        "delete markers safely",
        "delete timeline markers safely",
        "safely delete markers",
        "safe marker cleanup",
    ),
    "timeline.marker.list": ("list timeline markers", "show timeline markers", "inspect timeline markers"),
    "timeline.clip_markers.list": (
        "list timeline clip markers",
        "list clip markers in timeline",
        "find clip markers in timeline",
        "find blue clip markers",
        "all blue clip markers",
        "modré markery v klipech",
        "clip markers directly in clips",
    ),
    "clip.flag": ("flag clip", "add flag to clip", "clear flag from clip", "clip flag"),
    "clip.dynamic_zoom": ("zoom in", "punch in", "dynamic zoom"),
    "clip.transform": ("zoom in", "punch in", "reframe"),
    "clip.freeze": ("freeze frame",),
    "clip.reverse": ("reverse clip", "reverse a clip", "play clip backwards", "make clip play backwards"),
    "clip.speed": ("clip speed", "change clip speed", "retime clip", "slow down clip", "speed up clip"),
    "clip.audio_eq": ("voice eq",),
    "clip.fusion.import": ("import fusion comp", "import fusion composition", "import setting file"),
    "layout.import": ("import layout", "import workspace layout"),
    "project.import": ("import project", "import project archive"),
    "color.gallery.still.import": ("import gallery still", "import still", "import drx still"),
    "auto_edit.silence_cut": (
        "cut silence",
        "remove pauses",
        "silence cut",
        "jump cut",
        "remove long pauses",
        "cut out parts where i dont talk",
        "remove non-speech segments",
        "cut silence remove gaps",
    ),
    "edit.auto_subtitle": ("auto subtitle", "auto subtitles", "auto caption", "generate captions from audio"),
    "auto_edit.podcast_edit": ("podcast edit", "podcast multicam", "active speaker podcast edit"),
    "auto_edit.podcast_multicam": ("podcast edit", "podcast multicam", "active speaker podcast edit"),
    "edit.blade": ("blade", "razor", "cut at playhead", "split clip at playhead", "strih na playheadu"),
    "edit.split": (
        "split clip",
        "legacy split",
        "edit split",
        "split clip at playhead",
        "stary split",
        "strih na playheadu",
    ),
    "edit.camera_pip": (
        "camera pip",
        "picture in picture",
        "webcam overlay",
        "rounded camera",
        "screen recording facecam",
    ),
    "edit.social_crop": ("social crop", "vertical crop", "crop for tiktok", "crop for reels", "crop for shorts"),
    "timeline.sync_clips": (
        "sync clips without multicam",
        "sync videos without multicam",
        "waveform sync timeline clips",
        "screen camera sync",
        "screen recording facecam sync",
    ),
    "text.insert": (
        "text overlay",
        "on-screen text",
        "add text overlay",
        "text on video",
        "popisek do videa",
        "styled captions",
        "pretty captions",
        "prettier captions",
        "make captions prettier",
        "italic captions",
        "caption background",
        "lower third",
        "lower third captions",
        "lower-third caption",
        "animated lower third",
        "text+ lower third",
        "visible captions",
        "caption styling",
        "not native subtitles",
    ),
    "text.insert_preset": ("insert title preset", "multitext", "text+", "fusion title", "lower third preset"),
    "text.insert_template": ("insert text template", "lower third setting", "custom title setting", "render text template"),
    "text.insert_template_batch": (
        "batch text templates",
        "bulk text+ templates",
        "insert many text templates",
        "timed text+ templates",
        "text+ labels batch",
        "text+ callouts batch",
        "batch captions",
        "caption batch",
        "text+ captions batch",
        "transcript captions",
        "empty upper text track",
    ),
    "text.insert_captions": (
        "designed transcript captions",
        "segment transcript captions",
        "timed text+ captions",
        "explicit caption segmentation",
        "caption reading speed",
        "one-line captions",
    ),
    "text.update": ("update text", "set textplus text", "change title text", "edit lower third fields"),
    "text.inspect": ("inspect text", "inspect title fields", "read text template", "text field discovery"),
    "text.list_presets": ("list text presets", "title presets", "fusion title presets", "available text titles"),
    "multicam.reorder_angles": (
        "reorder multicam angles",
        "reorder native multicam",
        "change multicam angle order",
        "reorder multicam tracks",
    ),
    "multicam.replace_audio": (
        "replace multicam audio",
        "isolated mic inside multicam",
        "native multicam internal audio",
        "swap camera audio for wav microphones",
    ),
    "multicam.replace.audio": (
        "replace multicam audio by angle number",
        "isolated mic inside multicam",
        "native multicam internal audio",
        "clear multicam angle audio",
    ),
    "multicam.replace.video": (
        "replace multicam video by angle number",
        "native multicam internal video",
        "swap multicam angle media",
        "replace angle video",
    ),
    "multicam.seed_timeline": (
        "seed multicam timeline",
        "append multicam clip to timeline",
        "place native multicam on v1",
        "insert multicam media item",
    ),
    "multicam.switch": (
        "switch multicam angle",
        "explicit multicam angle switches",
        "switch native multicam at record frames",
        "linked multicam switch",
        "video multicam switch",
        "audio multicam switch",
    ),
    "fairlight.automation.list": ("fairlight automation list", "read fairlight automation", "AutoMix tokens", "MixLevel controls"),
    "multicam.audio_activity.calibrate": (
        "calibrate podcast multicam audio activity",
        "recommend audio activity thresholds",
        "podcast multicam calibration",
        "speaker separation diagnostics",
        "transcript assisted multicam calibration",
    ),
    "fairlight.automation.write": ("fairlight automation write", "write fairlight automation", "audio automation", "api call failed"),
    "fairlight.audio_gain.batch": ("fairlight audio gain batch", "batch audio gain", "bulk audio gain", "audio item gain"),
    "fusion.node.add": ("fusion node add", "add fusion node", "create fusion node", "node creation"),
    "fusion.image.set": ("fusion image set", "inject image into fusion", "set fusion image path", "fusion image injection"),
    "fusion.image.batch": ("fusion image batch", "batch fusion image injection", "bulk fusion image set"),
    "fusion.node.delete": ("fusion node delete", "delete fusion node", "remove fusion node", "node not found"),
    "fusion.node.connect": ("fusion node connect", "connect fusion nodes", "connect fusion node", "node not found"),
    "fusion.node.disconnect": ("fusion node disconnect", "disconnect fusion node", "disconnect fusion nodes", "node not found"),
    "fusion.keyframe.add": (
        "fusion keyframe add",
        "add fusion keyframe",
        "create fusion keyframe",
        "animated fusion lower third",
        "text+ keyframes",
        "lower third keyframes",
        "no active comp",
    ),
    "fusion.keyframe.delete": ("fusion keyframe delete", "delete fusion keyframe", "remove fusion keyframe", "no active comp"),
    "fusion.text.set": ("fusion text set", "set textplus text", "update fusion text", "set styledtext"),
    "fusion.text.batch": ("fusion text batch", "batch textplus update", "bulk fusion text set"),
    "fusion.nested_text.update": ("fusion nested text update", "update compound text", "nested text update", "open compound and set header body"),
    "fusion.nested_text.batch": ("fusion nested text batch", "batch compound text update", "bulk nested text update"),
    "fusion.macro.apply": ("fusion macro apply", "apply fusion macro", "apply fusion template", "macro not found"),
    "fusion.template.apply": ("fusion template apply", "apply fusion template", "apply fusion macro", "template not found"),
    "fairlight.add": ("fairlight add", "add audio track", "insert audio track", "Timeline.AddTrack", "adaptive36", "7.1film"),
    "fairlight.adr.info": ("fairlight adr info", "adr schema probe", "AutoCue settings", "adr storage readback"),
    "fairlight.adr.cue_list": ("fairlight adr cue-list", "adr cues", "adr cue sheet", "adr take list"),
    "fairlight.adr.record": ("fairlight adr record", "record adr cue", "adr beeps streamers prompts", "adr takes"),
    "fairlight.bounce.mix_to_track": ("fairlight bounce mix-to-track", "bounce mix to track", "fairlight stems", "bounce bus"),
    "fairlight.bounce.track": ("fairlight bounce track", "bounce track effects", "bounce audio track", "fairlight bounce"),
    "fairlight.bus.assign": ("fairlight bus assign", "assign audio track to bus", "route track to bus", "bus not found"),
    "fairlight.bus.list": ("fairlight bus list", "list fairlight buses", "bus readback", "FLStudioModelBA bus labels"),
    "fairlight.bus.level": (
        "fairlight bus level",
        "read main output gain context",
        "set bus level",
        "bus fader",
        "OutputAudioGain",
        "bus not found",
    ),
    "fairlight.channel_map.clip": ("fairlight channel-map clip", "timeline item audio mapping", "source audio channel mapping", "GetSourceAudioChannelMapping"),
    "fairlight.channel_map.media": ("fairlight channel-map media", "media pool audio mapping", "clip attributes audio mapping", "GetAudioMapping"),
    "fairlight.channel_map.set": ("fairlight channel-map set", "set audio channel mapping", "clip attributes channel map", "write channel mapping"),
    "fairlight.clip.delete": ("fairlight clip delete", "delete audio clip", "remove fairlight clip", "non ripple audio delete"),
    "fairlight.clip.info": ("fairlight clip info", "audio clip inspector", "TimelineItem metadata", "GetProperty"),
    "fairlight.clip.link": ("fairlight clip link", "link audio clips", "SetClipsLinked", "fairlight linked clips"),
    "fairlight.clip.linked.list": ("fairlight clip linked list", "linked audio clips", "GetLinkedItems", "fairlight linked item readback"),
    "fairlight.clip.source_range": ("fairlight clip source-range", "audio clip source range", "left offset", "right offset"),
    "fairlight.clip.track_info": ("fairlight clip track-info", "audio clip track index", "GetTrackTypeAndIndex", "clip track info"),
    "fairlight.clip.unlink": ("fairlight clip unlink", "unlink audio clip", "SetClipsLinked false", "fairlight unlink clip"),
    "fairlight.clip.move": (
        "fairlight clip move",
        "nudge audio clip",
        "move fairlight clip",
        "audio clip start",
        "move audio clip to track",
        "fairlight clip to another audio track",
    ),
    "fairlight.clip.nudge": (
        "fairlight clip nudge",
        "nudge audio clip",
        "move audio clip by frames",
        "fairlight audio nudge",
        "timeline audio nudge",
    ),
    "fairlight.clip.slip": (
        "fairlight clip slip",
        "slip audio clip",
        "source in audio clip",
        "change audio clip source offset",
        "fairlight source slip",
    ),
    "fairlight.clip.split": ("fairlight clip split", "split audio clip", "razor audio item", "Fairlight razor"),
    "fairlight.clip.trim": (
        "fairlight clip trim",
        "trim audio clip",
        "set audio clip duration",
        "right edge audio trim",
        "left edge audio trim",
        "head trim audio clip",
    ),
    "fairlight.elastic.info": ("fairlight elastic info", "Elastic Wave storage readback", "speed profile readback", "retime profile signals"),
    "fairlight.elastic.enable": ("fairlight elastic enable", "elastic wave", "enable elastic wave", "pitch preserving stretch"),
    "fairlight.elastic.keyframe": ("fairlight elastic keyframe", "elastic wave keyframe", "stretch keyframe", "time stretch audio"),
    "fairlight.effect.add": ("fairlight effect add", "add fairlight effect", "insert audio effect", "effect not found"),
    "fairlight.effect.catalog": ("fairlight effect catalog", "Fairlight Track FX catalog", "Macro FX catalog", "FLStudioModelBA effect catalog"),
    "fairlight.effect.params": ("fairlight effect params", "fairlight effect parameters", "audio effect params", "effect not found"),
    "fairlight.effect.plugin_catalog": (
        "fairlight effect plugin-catalog",
        "AUConfiguration.xml",
        "VST3Configuration.xml",
        "Fairlight plugin availability catalog",
        "FXScan paths",
        "libBMDAudioPlugins.dylib",
        "BMD Fairlight FX catalog",
    ),
    "fairlight.effect.slot_scan": ("fairlight effect slot-scan", "Fairlight plugin slot DB scan", "plugin slot candidates", "FLStudioModelBA BMD tokens", "clip FL::ClipFX payloads"),
    "fairlight.effect.set_param": ("fairlight effect set-param", "set Fairlight clip FX parameter", "write audio effect parameter", "clip effect param write"),
    "fairlight.effect.remove": ("fairlight effect remove", "remove fairlight effect", "delete audio effect", "effect not found"),
    "fairlight.external_process.list": ("fairlight external-process list", "ExternalFXConfiguration.xml", "configured external audio process", "external process readback"),
    "fairlight.external_process.run": ("fairlight external-process run", "external audio process", "roundtrip rx", "audio editor round trip"),
    "fairlight.export.audio": ("fairlight export audio", "export fairlight audio", "audio mixdown file", "render fairlight mix"),
    "fairlight.audio_pan.batch": ("fairlight audio-pan batch", "batch audio pan", "bulk audio pan", "audio item pan"),
    "fairlight.crossfade.batch": ("fairlight crossfade batch", "batch audio crossfade", "audio edit point crossfade", "adjacent audio clips"),
    "fairlight.group.assign": ("fairlight group assign", "track group", "link group", "fairlight groups"),
    "fairlight.group.list": ("fairlight group list", "Fairlight group labels", "track group list", "FLStudioModelBA groups", "SM_Group stored groups"),
    "fairlight.io.info": ("fairlight io info", "patch input output readback", "stored audio settings", "VTR input output settings"),
    "fairlight.io.patch": ("fairlight io patch", "patch input output", "record input patch", "hardware output route"),
    "fairlight.dynamics.set": ("fairlight dynamics set", "set compressor", "set limiter", "set gate", "dynamics api failed"),
    "fairlight.delete": ("fairlight delete", "delete audio track", "remove audio track", "Timeline.DeleteTrack"),
    "fairlight.ensure_tracks": ("fairlight ensure-tracks", "ensure audio tracks", "add lcr audio tracks", "adaptive36 audio tracks"),
    "fairlight.ensure_stereo_tracks": ("fairlight ensure stereo tracks", "stereo audio tracks", "add stereo audio tracks", "podcast stereo tracks"),
    "fairlight.fade_in.batch": ("fairlight fade-in batch", "batch audio fade in", "bulk audio fade in", "audio item fades"),
    "fairlight.fade_out.batch": ("fairlight fade-out batch", "batch audio fade out", "bulk audio fade out", "audio item fades"),
    "fairlight.fader": (
        "fairlight mixer fader",
        "audio track fader",
        "main output gain context",
        "OutputAudioGain",
        "bus main fader",
    ),
    "fairlight.mixer.fader": (
        "fairlight mixer fader",
        "audio track fader",
        "main output gain context",
        "OutputAudioGain",
        "bus main fader",
    ),
    "fairlight.index.clips": ("fairlight index clips", "Fairlight Index clips", "audio clip index", "timeline audio clips"),
    "fairlight.index.markers": ("fairlight index markers", "Fairlight Index markers", "timeline marker index", "spotting markers"),
    "fairlight.index.tracks": ("fairlight index tracks", "Fairlight Index tracks", "audio track index", "track clip counts"),
    "fairlight.info": ("fairlight info", "audio track info", "track mixer readback", "track routing readback"),
    "fairlight.item_source.patch": ("fairlight item source patch", "audio source offset", "patch Sm2TiItem In Duration", "external microphone layout"),
    "fairlight.loudness.info": ("fairlight loudness info", "loudness storage readback", "meter setup signals", "LUFS schema probe"),
    "fairlight.loudness.analyze": ("fairlight loudness analyze", "loudness meter", "integrated lufs", "true peak"),
    "fairlight.loudness.normalize": ("fairlight loudness normalize", "normalize lufs", "loudness normalization", "true peak"),
    "fairlight.mixer.meter_settings": ("fairlight mixer meter-settings", "audio meter setup", "AudioMeterDBUEnable", "AudioMeterAlignmentLevel"),
    "fairlight.mixer.read": (
        "fairlight mixer read",
        "mixer strip readback",
        "track fader pan read",
        "main output gain context",
        "OutputAudioGain",
        "FLStudioModelBA mixer lanes",
    ),
    "fairlight.monitor.info": ("fairlight monitor info", "control room setup readback", "MuteAudio", "TargetMonitor"),
    "fairlight.monitor.level": ("fairlight monitor level", "control room level", "monitor dim", "speaker set"),
    "fairlight.monitor.mute": ("fairlight monitor mute", "control room mute", "monitor mute", "fairlight monitoring"),
    "fairlight.record.arm": ("fairlight record arm", "arm audio track", "record enable", "input monitor"),
    "fairlight.record.info": ("fairlight record info", "record setup readback", "SyRecordInfo", "record status"),
    "fairlight.record.start": ("fairlight record start", "start audio recording", "voiceover record", "fairlight recording"),
    "fairlight.record.stop": ("fairlight record stop", "stop audio recording", "recording take", "voiceover stop"),
    "fairlight.send.list": ("fairlight send list", "send token probe", "FLStudioModelBA sends", "aux bus destinations"),
    "fairlight.send.set": ("fairlight send set", "audio send level", "pre fader post fader", "send to bus"),
    "fairlight.solo": ("fairlight solo", "solo audio track", "mute all other tracks"),
    "fairlight.sound_library.delete": ("fairlight sound-library delete", "remove sound library index", "unindex sound effect", "FLAssetBaseClip DB delete"),
    "fairlight.sound_library.index_folder": ("fairlight sound-library index-folder", "index sound library folder", "scan sound effects folder", "FLAssetBase folder DB index"),
    "fairlight.sound_library.index_file": ("fairlight sound-library index-file", "index sound library file", "register sound effect", "FLAssetBaseFile DB index"),
    "fairlight.sound_library.insert": ("fairlight sound-library insert", "sound library insert", "insert sound effect", "sound library result"),
    "fairlight.sound_library.audition": ("fairlight sound-library audition", "audition sound effect", "preview sound library result", "Sound Library audition blocker"),
    "fairlight.sound_library.list": ("fairlight sound-library list", "list sound library", "sound library index", "FLAssetBaseClip ed metadata"),
    "fairlight.sound_library.preview": ("fairlight sound-library preview", "preview sound effect", "audition sound library result", "Sound Library preview blocker"),
    "fairlight.sound_library.search": ("fairlight sound-library search", "search sound library", "sound metadata tags", "ed_level_db fade pan eq metadata"),
    "fairlight.sound_library.source_list": ("fairlight sound-library source-list", "sound library source folders", "FLAssetBaseContainer paths", "indexed source list"),
    "fairlight.sound_library.source_rebuild": ("fairlight sound-library source-rebuild", "rebuild sound library source", "delete rescan sound effects folder", "FLAssetBase source rebuild"),
    "fairlight.sound_library.source_remove": ("fairlight sound-library source-remove", "remove sound library source", "unindex source folder", "delete FLAssetBaseContainer source rows"),
    "fairlight.track_format.set": ("fairlight track-format set", "set audio track format", "SetTrackSubType", "convert track format"),
    "fairlight.track.duplicate": ("fairlight track duplicate", "duplicate audio track", "copy fairlight track", "duplicate clips", "duplicate mixer processing"),
    "fairlight.track.folder": ("fairlight track folder", "Fairlight folder track", "DaVinci Resolve 21 folder tracks", "collapse Fairlight tracks"),
    "fairlight.track.height": ("fairlight track height", "audio track height", "track display size", "resize fairlight track"),
    "fairlight.track.hide": ("fairlight track hide", "hide audio track", "track visibility", "fairlight track display"),
    "fairlight.track.input_monitor": ("fairlight track input-monitor", "input monitoring", "monitor audio input", "track input monitor"),
    "fairlight.track.show": ("fairlight track show", "show audio track", "track visibility", "fairlight track display"),
    "fairlight.track_order.move": ("fairlight track-order move", "reorder audio tracks", "move audio track", "duplicate audio track"),
    "fairlight.track_color": ("fairlight track color", "audio track color", "set track color"),
    "fairlight.transition.add": ("fairlight transition add", "audio transition object", "cross fade 0db", "Fairlight crossfade transition"),
    "fairlight.vca.assign": ("fairlight vca assign", "vca group", "vca fader", "assign vca"),
    "fairlight.vca.list": ("fairlight vca list", "Fairlight VCA labels", "vca label list", "FLStudioModelBA vcas"),
    "fairlight.waveform.info": ("fairlight waveform info", "audio waveform view state", "UIElementsState waveform", "waveform display readback"),
    "fairlight.waveform.repair_click": ("fairlight waveform repair-click", "click pop repair", "sample repair", "waveform edit"),
    "timeline.subtitles": ("add subtitles", "subtitles", "subtitle please", "subtitles please"),
    "timeline.captions": ("add captions", "captions", "caption please", "captions please"),
    "render.export_preset": ("export render preset", "render preset template", "edit render preset xml"),
    "render.import_preset": ("import render preset", "import render preset xml", "import preset bundle"),
    "render.archive_settings": ("archive render", "render archive", "separate embedded audio tracks", "all timeline tracks audio"),
    "render.preset_load": ("youtube export", "export for youtube"),
    "render.preset_save": ("save render preset", "create custom render preset", "custom render preset"),
    "render.settings_set": ("set render settings", "h264 mp4 export", "youtube h264", "mp4 delivery", "deliver h264"),
    "render.start": ("start render", "begin export", "render queue start", "export video"),
    "render.export_file": ("render and validate file", "export timeline file", "verified file delivery"),
    "color.cdl": ("black and white", "desaturate", "desaturation", "monochrome", "set saturation", "remove color"),
    "color.primary.set": ("black and white", "desaturate clip", "monochrome grade", "set saturation", "remove saturation"),
    "color.lut": ("apply lut", "rec709 lut", "set lut", "apply rec709", "look up table"),
    "color.page.lut_library_import": ("import lut library", "refresh lut folder", "lut folder import", "power grade lut workflow"),
    "color.node.lut_set": ("apply lut to node", "set node lut", "rec709 lut", "apply look"),
    "color.page.auto_color_ai": ("native auto color", "DaVinci Resolve Auto Color", "Color > Auto Color", "AI auto color"),
}

_LEGACY_ALIAS_COMMAND_IDS = {
    # Keep the compatibility route callable, but do not present it as a
    # standalone documented command in generated agent references.
    "multicam.replace_audio",
}


@dataclass(frozen=True)
class ParameterDef:
    python_name: str
    kind: str
    cli_names: tuple[str, ...] = ()
    help_text: str | None = None
    default: str | None = None
    annotation: str | None = None


@dataclass(frozen=True)
class CommandDef:
    path: str
    command_id: str
    source_file: str
    function_name: str
    docs_topic: str
    help_text: str | None = None
    doc: str | None = None
    parameters: tuple[ParameterDef, ...] = ()
    capability_id: str | None = None
    capability_status: str | None = None
    engine: str | None = None
    capability_caveats: dict[str, Any] | None = None
    legacy: bool = False
    keywords: tuple[str, ...] = ()


def _literal(node: ast.AST | None) -> Any:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def _expr_text(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


def _call_keyword(node: ast.Call, name: str) -> ast.AST | None:
    for kw in node.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _command_name_from_decorator(decorator: ast.AST) -> str | None:
    if not isinstance(decorator, ast.Call):
        return None
    func = decorator.func
    if not isinstance(func, ast.Attribute) or func.attr != "command":
        return None
    if not decorator.args:
        return ""
    value = _literal(decorator.args[0])
    return value if isinstance(value, str) else ""


def _typer_target_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _expr_text(node)
    return None


def _is_hidden_call(node: ast.Call) -> bool:
    return _literal(_call_keyword(node, "hidden")) is True


def _extract_add_typer_call(node: ast.Call) -> tuple[str | None, str | None, str | None, bool]:
    if not isinstance(node.func, ast.Attribute) or node.func.attr != "add_typer" or not node.args:
        return (None, None, None, False)
    parent = _typer_target_name(node.func.value)
    target = _typer_target_name(node.args[0])
    value = _literal(_call_keyword(node, "name"))
    return (parent, target, value if isinstance(value, str) else None, _is_hidden_call(node))


def _annotation_text(arg: ast.arg) -> str | None:
    return _expr_text(arg.annotation)


def _extract_parameter(arg: ast.arg, default_node: ast.AST | None) -> ParameterDef | None:
    kind = "argument"
    cli_names: list[str] = []
    help_text = None
    if isinstance(default_node, ast.Call):
        func_name = _expr_text(default_node.func) or ""
        help_value = _literal(_call_keyword(default_node, "help"))
        help_text = help_value if isinstance(help_value, str) else None
        if func_name.endswith("Option"):
            if _is_hidden_call(default_node):
                return None
            kind = "option"
            for raw_arg in default_node.args:
                value = _literal(raw_arg)
                if isinstance(value, str) and value.startswith("-"):
                    cli_names.append(value)
            if not cli_names and arg.arg:
                cli_names.append(f"--{arg.arg.replace('_', '-')}")
    return ParameterDef(
        python_name=arg.arg,
        kind=kind,
        cli_names=tuple(cli_names),
        help_text=help_text,
        default=_expr_text(default_node),
        annotation=_annotation_text(arg),
    )


def _build_module_context(tree: ast.Module, source_file: str) -> dict[str, str]:
    app_to_prefix: dict[str, str] = {}
    pending_targets: dict[str, str | None] = {}
    source_file = source_file.replace("\\", "/")

    if source_file in {"cutagent_cli/main.py", "cutagent_cli/commands/utility.py"}:
        app_to_prefix["app"] = ""
    else:
        app_to_prefix["app"] = Path(source_file).stem.replace("_", "-")

    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
            value = node.value
            if isinstance(value, ast.Call):
                func_name = _expr_text(value.func) or ""
                if func_name.endswith("Typer"):
                    pending_targets[target] = None
                else:
                    parent_app, target_app, child_name, hidden = _extract_add_typer_call(value)
                    if target_app and child_name and target and not hidden:
                        parent_prefix = app_to_prefix.get(parent_app, pending_targets.get(parent_app))
                        if parent_prefix is not None:
                            app_to_prefix[target] = " ".join(part for part in [parent_prefix, child_name] if part)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            parent_app, target_app, child_name, hidden = _extract_add_typer_call(node.value)
            if parent_app and target_app and child_name and not hidden:
                parent_prefix = app_to_prefix.get(parent_app, pending_targets.get(parent_app))
                if parent_prefix is not None:
                    app_to_prefix[target_app] = " ".join(part for part in [parent_prefix, child_name] if part)
    return app_to_prefix


def _docs_topic_for_path(path: str) -> str:
    root = path.split()[0]
    return _DOCS_TOPIC_BY_ROOT.get(root, "orchestration")


def _command_id_for_path(path: str) -> str:
    return ".".join(segment.replace("-", "_") for segment in path.split())


def _capability_id_for(
    command_id: str,
    feature_graph: dict[str, dict[str, object]],
) -> tuple[str | None, str | None, str | None]:
    direct_candidate = _COMMAND_CAPABILITY_HINTS.get(command_id)
    if direct_candidate and direct_candidate in feature_graph:
        feature = feature_graph[direct_candidate]
        return direct_candidate, str(feature.get("status")), str(feature.get("engine"))

    if command_id in feature_graph:
        feature = feature_graph[command_id]
        return command_id, str(feature.get("status")), str(feature.get("engine"))

    tokens = command_id.split(".")
    if len(tokens) >= 3:
        candidate = _GROUP_CAPABILITY_HINTS.get(tuple(tokens[:3]))
        if candidate and candidate in feature_graph:
            feature = feature_graph[candidate]
            return candidate, str(feature.get("status")), str(feature.get("engine"))

    candidate = _GROUP_CAPABILITY_HINTS.get(tuple(tokens[:2]))
    if candidate and candidate in feature_graph:
        feature = feature_graph[candidate]
        return candidate, str(feature.get("status")), str(feature.get("engine"))

    if len(tokens) >= 2:
        candidate = ".".join(tokens[:2])
        if candidate in feature_graph:
            feature = feature_graph[candidate]
            return candidate, str(feature.get("status")), str(feature.get("engine"))
    return (None, None, None)


def _capability_caveats_for(
    capability_id: str | None,
    feature_graph: dict[str, dict[str, object]],
) -> dict[str, Any] | None:
    if not capability_id:
        return None
    feature = feature_graph.get(capability_id)
    if not isinstance(feature, dict):
        return None
    caveats = feature.get("caveats")
    return dict(caveats) if isinstance(caveats, dict) and caveats else None


def _command_keywords(command_id: str) -> tuple[str, ...]:
    return _KEYWORD_HINTS.get(command_id, ())


def _command_defs_from_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    app_to_prefix: dict[str, str],
    source_file: str,
    feature_graph: dict[str, dict[str, object]],
) -> list[CommandDef]:
    commands: list[CommandDef] = []
    args = list(node.args.args)
    defaults = list(node.args.defaults)
    aligned_defaults: list[ast.AST | None] = [None] * (len(args) - len(defaults)) + defaults

    for decorator in node.decorator_list:
        command_name = _command_name_from_decorator(decorator)
        if command_name is None or not isinstance(decorator, ast.Call):
            continue
        if _is_hidden_call(decorator):
            continue
        func = decorator.func
        if not isinstance(func, ast.Attribute):
            continue
        app_name = _typer_target_name(func.value)
        if app_name is None or app_name not in app_to_prefix:
            continue
        prefix = app_to_prefix[app_name]
        resolved_name = command_name or node.name.replace("_", "-")
        path = " ".join(part for part in [prefix, resolved_name] if part).strip()
        help_value = _literal(_call_keyword(decorator, "help"))
        help_text = help_value if isinstance(help_value, str) else None
        parameters = tuple(
            parameter
            for arg, default_node in zip(args, aligned_defaults)
            if arg.arg != "self"
            for parameter in [_extract_parameter(arg, default_node)]
            if parameter is not None
        )
        command_id = _command_id_for_path(path)
        declared_capabilities: set[str] = set()
        mutation_capable = False
        for call in (item for item in ast.walk(node) if isinstance(item, ast.Call)):
            call_name = _expr_text(call.func) or ""
            if call_name.endswith(("set_capability_context", "enforce_mutation_policy")) and call.args:
                declared = _literal(call.args[0])
                if isinstance(declared, str):
                    declared_capabilities.add(declared)
            if call_name.endswith("enforce_mutation_policy"):
                mutating = _call_keyword(call, "mutating")
                if not (isinstance(mutating, ast.Constant) and mutating.value is False):
                    mutation_capable = True
        capability_id, status, engine = _capability_id_for(command_id, feature_graph)
        if len(declared_capabilities) == 1:
            declared_capability = next(iter(declared_capabilities))
            feature = feature_graph.get(declared_capability)
            if isinstance(feature, dict):
                capability_id = declared_capability
                status = str(feature.get("status"))
                engine = str(feature.get("engine"))
        _SOURCE_HANDLER_CONTRACTS[command_id] = {
            "capability_ids": tuple(sorted(declared_capabilities)),
            "mutation_capable": mutation_capable,
        }
        engine = _COMMAND_ENGINE_OVERRIDES.get(command_id, engine)
        capability_caveats = _capability_caveats_for(capability_id, feature_graph)
        if command_id in _COMMAND_CAVEAT_OVERRIDES:
            capability_caveats = {
                **(capability_caveats or {}),
                **_COMMAND_CAVEAT_OVERRIDES[command_id],
            }
        commands.append(
            CommandDef(
                path=path,
                command_id=command_id,
                source_file=source_file,
                function_name=node.name,
                docs_topic=_docs_topic_for_path(path),
                help_text=help_text,
                doc=ast.get_docstring(node),
                parameters=parameters,
                capability_id=capability_id,
                capability_status=status,
                engine=engine,
                capability_caveats=capability_caveats,
                legacy=command_id in _LEGACY_ALIAS_COMMAND_IDS,
                keywords=_command_keywords(command_id),
            )
        )
    return commands


def _collect_source_catalog() -> list[CommandDef]:
    _SOURCE_HANDLER_CONTRACTS.clear()
    # A catalog is one transport-neutral metadata snapshot. Build the dynamic
    # capability graph once for this source parse rather than rebuilding it for
    # every command, declared capability, caveat, and synthetic compatibility
    # path. The next catalog construction still obtains a fresh graph.
    feature_graph = get_capabilities().get("feature_graph", {})
    commands: list[CommandDef] = []
    for path in [MAIN_FILE] + sorted(COMMANDS_DIR.glob("*.py")):
        source_file = path.relative_to(ROOT).as_posix()
        source_text = _facade_shard_source(path) or path.read_text(encoding="utf-8")
        tree = ast.parse(source_text, filename=str(path))
        app_to_prefix = _build_module_context(tree, source_file)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                commands.extend(
                    _command_defs_from_function(
                        node,
                        app_to_prefix,
                        source_file,
                        feature_graph,
                    )
                )
    deduped: dict[str, CommandDef] = {}
    for command in commands:
        current = deduped.get(command.path)
        if current is None or (len(command.parameters), bool(command.help_text), bool(command.doc)) > (
            len(current.parameters),
            bool(current.help_text),
            bool(current.doc),
        ):
            deduped[command.path] = command
    for command in _synthetic_command_defs(feature_graph):
        deduped.setdefault(command.path, command)
    return sorted(deduped.values(), key=lambda item: item.path)


def source_handler_contracts() -> dict[str, dict[str, Any]]:
    """Return literal capability and mutation-policy declarations from command handlers."""
    get_command_catalog()
    return {
        command_id: {
            "capability_ids": tuple(contract["capability_ids"]),
            "mutation_capable": bool(contract["mutation_capable"]),
        }
        for command_id, contract in _SOURCE_HANDLER_CONTRACTS.items()
    }


def _synthetic_command_defs(
    feature_graph: dict[str, dict[str, object]],
) -> tuple[CommandDef, ...]:
    """Command paths dispatched by compatibility callbacks rather than Typer subcommands."""
    feature = feature_graph.get("media.metadata_write", {})
    media_append_feature = feature_graph.get("media.append", {})
    media_proxy_feature = feature_graph.get("media.proxy_transcode", {})
    timeline_frame_export_feature = feature_graph.get("timeline.frame_export_batch", {})
    fusion_mutation_feature = feature_graph.get("fusion.mutation", {})
    return (
        CommandDef(
            path="media append batch",
            command_id="media.append.batch",
            source_file="cutagent_cli/commands/media.py",
            function_name="append_batch",
            docs_topic="media",
            help_text="Append multiple Media Pool items with all-entry preflight.",
            doc="Compatibility-dispatched public path accepted by `media append batch`.",
            parameters=(
                ParameterDef("batch", "option", cli_names=("--batch",), help_text="JSON batch file"),
                ParameterDef("input_file", "option", cli_names=("--input",), help_text="JSON batch file alias"),
                ParameterDef("batch_json", "option", cli_names=("--batch-json",), help_text="Inline JSON batch payload"),
                ParameterDef("allow_partial", "option", cli_names=("--allow-partial",), help_text="Apply valid entries even when some entries fail preflight"),
            ),
            capability_id="media.append",
            capability_status=str(media_append_feature.get("status")) if media_append_feature else None,
            engine=str(media_append_feature.get("engine")) if media_append_feature else None,
        ),
        CommandDef(
            path="media proxy",
            command_id="media.proxy",
            source_file="cutagent_cli/commands/media.py",
            function_name="proxy_clip",
            docs_topic="media",
            help_text="Generate, link, or unlink Media Pool proxy media for a clip.",
            doc="Callback-dispatched public path accepted by `media proxy --name CLIP --generate|--link PATH|--unlink` and legacy `media proxy CLIP --generate|--link PATH|--unlink`.",
            parameters=(
                ParameterDef("name", "argument", help_text="Media Pool clip name for legacy positional form", default="None", annotation="Optional[str]"),
                ParameterDef("name", "option", cli_names=("--name",), help_text="Media Pool clip name", default="None", annotation="Optional[str]"),
                ParameterDef("generate", "option", cli_names=("--generate",), help_text="Generate proxy/optimized media", default="False", annotation="bool"),
                ParameterDef("link", "option", cli_names=("--link",), help_text="Link proxy media path", default="None", annotation="Optional[str]"),
                ParameterDef("unlink", "option", cli_names=("--unlink",), help_text="Unlink proxy media", default="False", annotation="bool"),
                ParameterDef("dry_run", "option", cli_names=("--dry-run", "-n"), help_text="Show what would happen without making changes"),
                ParameterDef("json_output", "option", cli_names=("--json", "-j"), help_text="JSON output"),
            ),
            capability_id="media.proxy_transcode",
            capability_status=str(media_proxy_feature.get("status")) if media_proxy_feature else None,
            engine=str(media_proxy_feature.get("engine")) if media_proxy_feature else None,
            keywords=_command_keywords("media.transcode"),
        ),
        CommandDef(
            path="media metadata export",
            command_id="media.metadata.export",
            source_file="cutagent_cli/commands/media.py",
            function_name="metadata",
            docs_topic="media",
            help_text="Export Media Pool metadata to a file.",
            doc="Compatibility-dispatched public path accepted by `media metadata export FILE [CLIP...]`.",
            parameters=(
                ParameterDef("file", "argument", help_text="Output metadata file", annotation="str"),
                ParameterDef("clips", "argument", help_text="Optional Media Pool clip names", default="None", annotation="Optional[list[str]]"),
            ),
            capability_id="media.metadata_write",
            capability_status=str(feature.get("status")) if feature else None,
            engine=str(feature.get("engine")) if feature else None,
        ),
        CommandDef(
            path="timeline frame-export batch",
            command_id="timeline.frame_export.batch",
            source_file="cutagent_cli/commands/timeline.py",
            function_name="frame_export_batch",
            docs_topic="timeline",
            help_text="Export multiple timeline frames sequentially and restore the playhead once.",
            doc="Compatibility-dispatched public path accepted by `timeline frame-export batch`.",
            parameters=(
                ParameterDef("frames", "option", cli_names=("--frames",), help_text="Comma-separated timeline positions to sample"),
                ParameterDef("out_dir", "option", cli_names=("--out-dir",), help_text="Directory for exported stills"),
                ParameterDef("prefix", "option", cli_names=("--prefix",), help_text="Output filename prefix"),
                ParameterDef("extension", "option", cli_names=("--extension",), help_text="Output extension: png|jpg|jpeg"),
                ParameterDef("contact_sheet", "option", cli_names=("--contact-sheet",), help_text="Optional contact sheet image path"),
                ParameterDef("contact_columns", "option", cli_names=("--contact-columns",), help_text="Contact sheet columns"),
                ParameterDef("contact_tile_width", "option", cli_names=("--contact-tile-width",), help_text="Contact sheet tile width"),
            ),
            capability_id="timeline.frame_export_batch",
            capability_status=str(timeline_frame_export_feature.get("status")) if timeline_frame_export_feature else None,
            engine=str(timeline_frame_export_feature.get("engine")) if timeline_frame_export_feature else None,
        ),
        CommandDef(
            path="fusion insert-settings batch",
            command_id="fusion.insert_settings.batch",
            source_file="cutagent_cli/commands/fusion.py",
            function_name="insert_settings_batch",
            docs_topic="fusion",
            help_text="Insert multiple Fusion/Text+ clips from .setting template specs.",
            doc="Compatibility-dispatched public path accepted by `fusion insert-settings batch`.",
            parameters=(
                ParameterDef("spec_path", "option", cli_names=("--spec",), help_text="Path to JSON spec file"),
                ParameterDef("spec_json", "option", cli_names=("--spec-json",), help_text="Inline JSON spec"),
            ),
            capability_id="fusion.mutation",
            capability_status=str(fusion_mutation_feature.get("status")) if fusion_mutation_feature else None,
            engine=str(fusion_mutation_feature.get("engine")) if fusion_mutation_feature else None,
        ),
    )


def _parameter_to_snapshot(parameter: ParameterDef) -> dict[str, Any]:
    return {
        "python_name": parameter.python_name,
        "kind": parameter.kind,
        "cli_names": list(parameter.cli_names),
        "help_text": parameter.help_text,
        "default": parameter.default,
        "annotation": parameter.annotation,
    }


def _command_to_snapshot(command: CommandDef) -> dict[str, Any]:
    return {
        "path": command.path,
        "command_id": command.command_id,
        "source_file": command.source_file,
        "function_name": command.function_name,
        "docs_topic": command.docs_topic,
        "help_text": command.help_text,
        "doc": command.doc,
        "parameters": [_parameter_to_snapshot(parameter) for parameter in command.parameters],
        "capability_id": command.capability_id,
        "capability_status": command.capability_status,
        "engine": command.engine,
        "capability_caveats": dict(command.capability_caveats) if command.capability_caveats else None,
        "legacy": command.legacy,
        "keywords": list(command.keywords),
    }


def _command_to_public_runtime_snapshot(command: CommandDef) -> dict[str, Any]:
    public_label = _public_command_label(command.path)
    return {
        "path": command.path,
        "command_id": command.command_id,
        "docs_topic": command.docs_topic,
        "public_label": _sanitize_public_runtime_text(public_label),
        "parameters": [
            {
                "name": parameter.python_name,
                "kind": parameter.kind,
                "cli_names": list(parameter.cli_names),
                "variadic": (
                    parameter.kind == "argument"
                    and isinstance(parameter.annotation, str)
                    and (
                        "list[" in parameter.annotation.lower()
                        or "tuple[" in parameter.annotation.lower()
                    )
                ),
            }
            for parameter in command.parameters
        ],
        "capability_id": command.capability_id,
        "capability_status": command.capability_status,
        "legacy": command.legacy,
    }


def _sanitize_public_runtime_text(value: str | None) -> str | None:
    if not isinstance(value, str):
        return value
    sanitized = value
    for needle, replacement in _PUBLIC_RUNTIME_TEXT_REPLACEMENTS.items():
        sanitized = sanitized.replace(needle, replacement)
    return sanitized


@lru_cache(maxsize=1)
def _load_public_command_labels() -> dict[str, Any]:
    try:
        payload = json.loads(PUBLIC_COMMAND_LABELS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    commands = payload.get("commands")
    return commands if isinstance(commands, dict) else {}


def _public_command_label(command_path: str) -> str | None:
    entry = _load_public_command_labels().get(command_path)
    if not isinstance(entry, dict):
        return _fallback_public_command_label(command_path)
    label = entry.get("label")
    return (
        label.strip()
        if isinstance(label, str) and label.strip()
        else _fallback_public_command_label(command_path)
    )


def _fallback_public_command_label(command_path: str) -> str:
    public_path = command_path.replace("_", " ").replace("-", " ")
    return f"Runs the public CutAgent {public_path} action"


def _parameter_from_snapshot(payload: dict[str, Any]) -> ParameterDef:
    return ParameterDef(
        python_name=str(payload.get("python_name") or payload["name"]),
        kind=str(payload["kind"]),
        cli_names=tuple(payload.get("cli_names") or ()),
        help_text=payload.get("help_text"),
        default=payload.get("default"),
        annotation=payload.get("annotation"),
    )


def _command_from_snapshot(payload: dict[str, Any]) -> CommandDef:
    caveats = payload.get("capability_caveats")
    return CommandDef(
        path=str(payload["path"]),
        command_id=str(payload["command_id"]),
        source_file=str(payload.get("source_file") or ""),
        function_name=str(payload.get("function_name") or ""),
        docs_topic=str(payload["docs_topic"]),
        help_text=payload.get("help_text"),
        doc=payload.get("doc"),
        parameters=tuple(_parameter_from_snapshot(item) for item in payload.get("parameters") or ()),
        capability_id=payload.get("capability_id"),
        capability_status=payload.get("capability_status"),
        engine=payload.get("engine"),
        capability_caveats=dict(caveats) if isinstance(caveats, dict) and caveats else None,
        legacy=bool(payload.get("legacy", False)),
        keywords=tuple(payload.get("keywords") or ()),
    )


def build_command_catalog_snapshot(*, public_runtime: bool = False) -> dict[str, Any]:
    """Serialize the source-parsed catalog for shipping with compiled builds."""
    commands = _collect_source_catalog()
    kind = SNAPSHOT_KIND_PUBLIC_RUNTIME if public_runtime else SNAPSHOT_KIND_FULL
    command_serializer = (
        _command_to_public_runtime_snapshot
        if public_runtime
        else _command_to_snapshot
    )
    return {
        "version": SNAPSHOT_VERSION,
        "kind": kind,
        "commands": [command_serializer(command) for command in commands],
    }


def write_command_catalog_snapshot(
    path: Path | None = None,
    *,
    public_runtime: bool = False,
) -> Path:
    """Write the catalog snapshot JSON (build-time helper, parses source)."""
    target = path or SNAPSHOT_FILE
    target.write_text(
        json.dumps(
            build_command_catalog_snapshot(public_runtime=public_runtime),
            indent=2,
            ensure_ascii=False,
            sort_keys=False,
        ) + "\n",
        encoding="utf-8",
    )
    return target


def _command_source_available() -> bool:
    return MAIN_FILE.is_file() and COMMANDS_DIR.is_dir()


def _load_catalog_snapshot_payload() -> dict[str, Any] | None:
    try:
        raw = SNAPSHOT_FILE.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("version") != SNAPSHOT_VERSION:
        return None
    return payload


def _load_catalog_snapshot() -> tuple[CommandDef, ...] | None:
    payload = _load_catalog_snapshot_payload()
    if payload is None:
        return None
    commands = payload.get("commands")
    if not isinstance(commands, list):
        return None
    return tuple(_command_from_snapshot(item) for item in commands if isinstance(item, dict))


def catalog_metadata_redacted() -> bool:
    if _command_source_available():
        return False
    payload = _load_catalog_snapshot_payload()
    return payload is not None and payload.get("kind") == SNAPSHOT_KIND_PUBLIC_RUNTIME


@lru_cache(maxsize=1)
def get_command_catalog() -> tuple[CommandDef, ...]:
    # Source parsing stays authoritative whenever the ``.py`` files exist
    # (dev + the standard source runtime); the baked snapshot is a fallback for
    # compiled builds where the sources were replaced by an extension module.
    if _command_source_available():
        return tuple(_collect_source_catalog())
    snapshot = _load_catalog_snapshot()
    if snapshot is not None:
        return snapshot
    return tuple(_collect_source_catalog())


def command_catalog_rows(*, include_parameters: bool = False) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for command in get_command_catalog():
        row: dict[str, object] = {
            "command_id": command.command_id,
            "path": command.path,
            "summary": command.help_text or command.doc or "",
            "docs_topic": command.docs_topic,
            "capability_id": command.capability_id,
            "status": command.capability_status,
            "engine": command.engine,
            "legacy": command.legacy,
        }
        if command.capability_caveats:
            row["capability_caveats"] = dict(command.capability_caveats)
        if include_parameters:
            row["parameters"] = [
                {
                    "name": parameter.python_name,
                    "kind": parameter.kind,
                    "cli_names": list(parameter.cli_names),
                    "help": parameter.help_text,
                }
                for parameter in command.parameters
            ]
            row["source_file"] = command.source_file
            row["function_name"] = command.function_name
            row["keywords"] = list(command.keywords)
        rows.append(row)
    return rows
