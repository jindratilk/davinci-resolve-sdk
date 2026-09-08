"""Project.db selector patching for native multicam switch flows."""

from __future__ import annotations

from .row_mutation import (
    _clone_item_row_with_segment,
    _decode_frame_rate_blob,
    _delete_track_items,
    _encode_media_extents,
    _insert_row,
    _quote_identifier,
    _update_row,
)
from .segment_rewrite import (
    _rewrite_multicam_segments_db,
    _use_four_cam_single_item_in_place_patch,
    _use_three_cam_single_item_in_place_patch,
    _use_two_cam_single_item_in_place_patch,
)
from .selector_blobs import (
    _build_compact_angle_selector_fields_blob,
    _build_switch_fields_blob,
    _build_three_cam_whole_clip_selector_fields_blob,
    _build_two_cam_camera_selector_fields_blob,
    _patch_three_angle_selector_fields_blob,
)
from .track_state import (
    _build_fallback_multicam_item_row,
    _load_timeline_multicam_track_state,
    _patch_timeline_multicam_bootstrap_metadata,
)

__all__ = [
    "_clone_item_row_with_segment",
    "_decode_frame_rate_blob",
    "_delete_track_items",
    "_encode_media_extents",
    "_insert_row",
    "_quote_identifier",
    "_update_row",
    "_rewrite_multicam_segments_db",
    "_use_four_cam_single_item_in_place_patch",
    "_use_three_cam_single_item_in_place_patch",
    "_use_two_cam_single_item_in_place_patch",
    "_build_compact_angle_selector_fields_blob",
    "_build_switch_fields_blob",
    "_build_three_cam_whole_clip_selector_fields_blob",
    "_build_two_cam_camera_selector_fields_blob",
    "_patch_three_angle_selector_fields_blob",
    "_build_fallback_multicam_item_row",
    "_load_timeline_multicam_track_state",
    "_patch_timeline_multicam_bootstrap_metadata",
]
