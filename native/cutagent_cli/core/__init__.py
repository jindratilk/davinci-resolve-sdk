"""Core business logic layer for cutagent-cli.

This package contains all the core business logic extracted from commands.
Each module provides functions that take ResolveConnection as a parameter
and return data or perform operations.

Modules:
    - timeline_ops: Timeline CRUD, playhead, markers, tracks, items
    - media_pool: Import, folders, search, metadata
    - clip_ops: Properties, color, flags, markers, takes, transform, composite, speed
    - render_engine: Render pipeline with retry, progress, cleanup
    - color_ops: LUT, CDL, grade operations, versions
    - fairlight_ops: Audio tracks, volume, mute/solo
    - fairlight_record_gui_route: GUI-assisted Fairlight transport record/stop
    - fairlight_group_gui_route: GUI-assisted Fairlight group assignment
    - fairlight_track_folder_gui_route: GUI-assisted Fairlight folder tracks
    - fusion_api: Fusion scripting API (direct comp manipulation)
    - text_ops: Agent-facing text/title helpers
    - fx_template_ops: Fusion-template effect helpers for workaround routes
    - blade_db: DB-backed timeline blade mutations
    - multicam_ops: Timeline-based multicam orchestration
    - podcast_multicam: Native multicam podcast orchestration
    - multicam_engine: Structured generic native multicam jobs/primitives
    - recipe_ops: Deterministic YAML recipe parser/runner
"""


from . import timeline_ops
from . import timeline_sync
from . import timeline_clip_color
from . import timeline_markers
from . import timeline_item_move_db
from . import edit_trim_db
from . import media_pool
from . import clip_ops
from . import keyframe_ops
from . import render_engine
from . import color_ops
from . import color_source_grade
from . import gallery_ops
from . import fairlight_ops
from . import fairlight_channel_map_db
from . import fairlight_adr_record_gui_route
from . import fairlight_external_process_gui_route
from . import fairlight_group_gui_route
from . import fairlight_loudness_gui_route
from . import fairlight_record_gui_route
from . import fairlight_track_folder_gui_route
from . import fusion_api
from . import fusion_common
from . import fusion_image_ops
from . import fusion_text_ops
from . import text_ops
from . import launch_ops
from . import fx_template_ops
from . import db_session
from . import db_timeline_rows
from . import db_timeline_selection
from . import retime_db
from . import clip_speed_db
from . import speed_ramp_db
from . import clip_effects_db
from . import blade_db
from . import transition_db
from . import multicam_ops
from . import multicam_engine
from . import podcast_multicam
from . import recipe_ops
from . import version_ops

__all__ = [
    "timeline_ops",
    "timeline_sync",
    "timeline_clip_color",
    "timeline_markers",
    "timeline_item_move_db",
    "edit_trim_db",
    "media_pool",
    "clip_ops",
    "keyframe_ops",
    "render_engine",
    "color_ops",
    "color_source_grade",
    "gallery_ops",
    "fairlight_ops",
    "fairlight_channel_map_db",
    "fairlight_adr_record_gui_route",
    "fairlight_external_process_gui_route",
    "fairlight_group_gui_route",
    "fairlight_loudness_gui_route",
    "fairlight_record_gui_route",
    "fairlight_track_folder_gui_route",
    "fusion_api",
    "fusion_common",
    "fusion_image_ops",
    "fusion_text_ops",
    "text_ops",
    "launch_ops",
    "fx_template_ops",
    "db_session",
    "db_timeline_rows",
    "db_timeline_selection",
    "retime_db",
    "clip_speed_db",
    "speed_ramp_db",
    "clip_effects_db",
    "blade_db",
    "transition_db",
    "multicam_ops",
    "multicam_engine",
    "podcast_multicam",
    "recipe_ops",
    "version_ops",
]
