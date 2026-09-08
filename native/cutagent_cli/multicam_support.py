"""Shared multicam support tiers and conservative verification metadata."""

from __future__ import annotations

from typing import Any

REGISTERED_NATIVE_FAMILY_ANGLE_COUNTS = frozenset({2, 3, 4, 5, 6})
PROJECT_LOCAL_REFERENCE_REQUIRED_ANGLE_COUNTS = frozenset()
FULLY_LIVE_SUPPORTED_ANGLE_COUNTS = frozenset({2, 3, 4, 5, 6})
CREATE_VERIFIED_ANGLE_COUNTS = frozenset({2, 3, 4, 5, 6})
TIMELINE_CREATE_LIVE_VERIFIED_ANGLE_COUNTS = frozenset({2, 3, 4, 5, 6})
SWITCH_LIVE_VERIFIED_ANGLE_COUNTS = frozenset({2, 3, 4, 5, 6})
CONTIGUOUS_MULTI_SOURCE_LIVE_VERIFIED_ANGLE_COUNTS = frozenset({2, 3, 4, 5, 6})
SPARSE_MULTI_SOURCE_LIVE_VERIFIED_ANGLE_COUNTS = frozenset({2, 3, 4, 5, 6})
_EXECUTION_CREATE_FAMILY_ANGLE_COUNTS = frozenset({2, 3, 4, 5, 6})
_EXECUTION_SWITCH_FAMILY_ANGLE_COUNTS = frozenset({2, 3, 4, 5, 6})
MIN_SUPPORTED_ANGLE_COUNT = 2
MAX_SUPPORTED_ANGLE_COUNT = 6
SOURCE_ITEM_REPRESENTATION = "distinct_timeline_items"
# The product contract limits logical angles, not the number of source clips
# placed sequentially on any one angle. Practical limits remain the resources
# available to DaVinci Resolve and the host machine.
SOURCE_CLIP_COUNT_PER_ANGLE_LIMIT = None
LATEST_LIVE_VERIFICATION = {
    "date": "2026-08-20",
    "resolve_version": "21.0.1.11",
    "product_name": "DaVinci Resolve Studio",
    "database_type": "Disk",
    "proof": [
        "save_close_reopen_readback",
        "timeline_api_readback",
        "rendered_angle_sequence",
        "gui_inner_timeline_distinct_item_boundaries",
        "twelve_source_items_on_one_of_six_logical_angles",
        "sparse_video_audio_source_items_2_through_6_angles",
        "leading_internal_trailing_gaps",
        "one_two_twelve_and_thirty_two_source_items_per_angle",
        "linked_video_only_audio_only_six_angle_switching",
        "rendered_gap_and_boundary_frames_with_audio_silence_readback",
        "cutagent_waveform_sync_in_out_timecode_marker_and_sound_channel_selection",
        "source_reference_adaptive_and_all_angles_audio_topologies",
        "same_camera_grouping_from_official_media_pool_metadata",
        "split_at_gaps_and_full_clip_extents",
        "rename_reorder_enable_disable_move_remove_source_and_angle",
        "start_timecode_save_close_reopen_readback",
        "timeline_and_compound_conversion",
        "flatten_copy_multicam_and_retain_angle_grade_policies",
        "match_frame_exact_source_item_and_source_frame",
        "persistent_smart_switch_equivalent_with_six_angle_linked_video_audio_switching",
        "remote_source_grade_cdl_readback",
        "braw_sidecar_api_reserialization_and_render_difference",
        "flatten_both_grade_policies_complete_video_audio_renders",
        "converted_timeline_and_compound_multicam_complete_renders",
    ],
}


def _normalized_angle_count(angle_count: int | None) -> int:
    return max(0, int(angle_count or 0))


def create_is_supported(angle_count: int | None) -> bool:
    normalized = _normalized_angle_count(angle_count)
    return MIN_SUPPORTED_ANGLE_COUNT <= normalized <= MAX_SUPPORTED_ANGLE_COUNT


def switch_contract_is_supported(angle_count: int | None) -> bool:
    return create_is_supported(angle_count)


def create_is_live_verified(angle_count: int | None) -> bool:
    return _normalized_angle_count(angle_count) in _EXECUTION_CREATE_FAMILY_ANGLE_COUNTS


def switch_is_live_verified(angle_count: int | None) -> bool:
    return _normalized_angle_count(angle_count) in _EXECUTION_SWITCH_FAMILY_ANGLE_COUNTS


def _operation_verification(normalized: int, *, supported: bool) -> dict[str, dict[str, Any]]:
    return {
        "create": {
            "contract_supported": supported,
            "live_verified": normalized in CREATE_VERIFIED_ANGLE_COUNTS,
        },
        "timeline_create": {
            "contract_supported": supported,
            "live_verified": normalized in TIMELINE_CREATE_LIVE_VERIFIED_ANGLE_COUNTS,
        },
        "switch": {
            "contract_supported": supported,
            "live_verified": normalized in SWITCH_LIVE_VERIFIED_ANGLE_COUNTS,
        },
        "contiguous_multi_source_angle": {
            "contract_supported": supported,
            "live_verified": normalized in CONTIGUOUS_MULTI_SOURCE_LIVE_VERIFIED_ANGLE_COUNTS,
            "source_item_representation": SOURCE_ITEM_REPRESENTATION,
            "source_clip_count_per_angle_limit": SOURCE_CLIP_COUNT_PER_ANGLE_LIMIT,
            "creates_flattened_media": False,
            "sync_modes": ["in"],
            "source_offsets_supported": False,
        },
        "sparse_multi_source_angle": {
            "contract_supported": supported,
            "live_verified": normalized in SPARSE_MULTI_SOURCE_LIVE_VERIFIED_ANGLE_COUNTS,
            "source_item_representation": SOURCE_ITEM_REPRESENTATION,
            "source_clip_count_per_angle_limit": SOURCE_CLIP_COUNT_PER_ANGLE_LIMIT,
            "creates_flattened_media": False,
            "video_audio_timing_linked": True,
            "explicit_fields": ["record_start_frame", "source_in_frame", "duration_frames"],
            "sync_engine": "cutagent",
        },
    }


def support_tier_for_angle_count(
    angle_count: int | None,
    *,
    has_multi_clip_angle: bool = False,
    source_layout: str = "contiguous",
) -> dict[str, Any]:
    normalized = _normalized_angle_count(angle_count)
    supported = MIN_SUPPORTED_ANGLE_COUNT <= normalized <= MAX_SUPPORTED_ANGLE_COUNT
    operation_verification = _operation_verification(normalized, supported=supported)
    normalized_source_layout = str(source_layout or "contiguous").strip().lower().replace("_", "-")
    multi_source_operation = (
        "sparse_multi_source_angle"
        if normalized_source_layout == "sparse"
        else "contiguous_multi_source_angle"
    )
    verification_scope = (
        f"{normalized_source_layout}_multi_source"
        if has_multi_clip_angle
        else "single_source_per_angle"
    )
    if normalized < MIN_SUPPORTED_ANGLE_COUNT:
        return {
            "angle_count": normalized,
            "tier": "unsupported",
            "label": "unsupported",
            "create_supported": False,
            "switch_contract_supported": False,
            "create_shape_verified": False,
            "switch_shape_verified": False,
            "live_verified": False,
            "verification_scope": verification_scope,
            "operation_verification": operation_verification,
            "notes": [
                "Native multicam requires at least 2 source angles.",
            ],
        }

    if normalized > MAX_SUPPORTED_ANGLE_COUNT:
        return {
            "angle_count": normalized,
            "tier": "unsupported",
            "label": "unsupported",
            "create_supported": False,
            "switch_contract_supported": False,
            "create_shape_verified": False,
            "switch_shape_verified": False,
            "live_verified": False,
            "verification_scope": verification_scope,
            "operation_verification": operation_verification,
            "notes": [
                f"Native multicam currently supports at most {MAX_SUPPORTED_ANGLE_COUNT} source angles.",
            ],
        }

    if normalized in FULLY_LIVE_SUPPORTED_ANGLE_COUNTS:
        live_verified = all(
            bool(operation_verification[name]["live_verified"])
            for name in ("create", "timeline_create", "switch")
        ) and (
            not has_multi_clip_angle
            or bool(operation_verification[multi_source_operation]["live_verified"])
        )
        return {
            "angle_count": normalized,
            "tier": "fully_live_supported",
            "label": (
                f"{normalized}-cam {normalized_source_layout} multi-source family live verified"
                if has_multi_clip_angle
                else f"{normalized}-cam native family live verified"
            ),
            "create_supported": True,
            "switch_contract_supported": True,
            "create_shape_verified": normalized in CREATE_VERIFIED_ANGLE_COUNTS,
            "switch_shape_verified": normalized in SWITCH_LIVE_VERIFIED_ANGLE_COUNTS,
            "live_verified": live_verified,
            "verification_scope": verification_scope,
            "operation_verification": operation_verification,
            "latest_live_verification": dict(LATEST_LIVE_VERIFICATION),
            "notes": [
                "A packaged DaVinci Resolve native fixture family is available for create and switch execution.",
                "Create, timeline-create, switch, save/close/reopen, and rendered output are covered by live DaVinci Resolve verification.",
                (
                    "Sparse source items are live-verified with explicit record start, source-in, duration, leading/internal/trailing gaps, and matching video/audio timing."
                    if normalized_source_layout == "sparse"
                    else "Twelve distinct source clips on one of six logical angles are live-verified in sequential input order with sync_mode=in and zero source offsets."
                ),
            ],
        }

    if normalized in REGISTERED_NATIVE_FAMILY_ANGLE_COUNTS:
        return {
            "angle_count": normalized,
            "tier": "registered_native_family_pending_ui_verification",
            "label": f"{normalized}-cam native family registered; pending live UI verification",
            "create_supported": True,
            "switch_contract_supported": True,
            "create_shape_verified": False,
            "switch_shape_verified": normalized in SWITCH_LIVE_VERIFIED_ANGLE_COUNTS,
            "live_verified": False,
            "verification_scope": verification_scope,
            "operation_verification": operation_verification,
            "notes": [
                "A native create/switch family is registered for this angle count.",
                "DaVinci Resolve UI correctness is not assumed verified from angle count alone.",
            ],
        }

    if normalized in PROJECT_LOCAL_REFERENCE_REQUIRED_ANGLE_COUNTS:
        return {
            "angle_count": normalized,
            "tier": "project_local_reference_required",
            "label": f"{normalized}-cam requires a calibrated project-local DaVinci Resolve native reference",
            "create_supported": True,
            "switch_contract_supported": True,
            "create_shape_verified": False,
            "switch_shape_verified": normalized in SWITCH_LIVE_VERIFIED_ANGLE_COUNTS,
            "live_verified": False,
            "verification_scope": verification_scope,
            "operation_verification": operation_verification,
            "notes": [
                "No packaged native family fixture is shipped for this angle count.",
                "Execution requires a healthy DaVinci Resolve-created local reference multicam in the project.",
            ],
        }

    return {
        "angle_count": normalized,
        "tier": "create_supported_switch_pending_ui_verification",
        "label": f"{normalized}-cam create supported, switch pending UI verification",
        "create_supported": True,
        "switch_contract_supported": True,
        "create_shape_verified": False,
        "switch_shape_verified": False,
        "live_verified": False,
        "verification_scope": verification_scope,
        "operation_verification": operation_verification,
        "notes": [
            "Generic N-angle create is supported.",
            "Switch planning/contract is supported, but native switch execution is not yet UI-verified for this angle count.",
        ],
    }


def build_multicam_support_matrix() -> dict[str, Any]:
    return {
        "minimum_supported_angle_count": MIN_SUPPORTED_ANGLE_COUNT,
        "maximum_supported_angle_count": MAX_SUPPORTED_ANGLE_COUNT,
        "registered_native_family_angle_counts": sorted(REGISTERED_NATIVE_FAMILY_ANGLE_COUNTS),
        "project_local_reference_required_angle_counts": sorted(PROJECT_LOCAL_REFERENCE_REQUIRED_ANGLE_COUNTS),
        "fully_live_supported_angle_counts": sorted(FULLY_LIVE_SUPPORTED_ANGLE_COUNTS),
        "create_verified_angle_counts": sorted(CREATE_VERIFIED_ANGLE_COUNTS),
        "timeline_create_live_verified_angle_counts": sorted(TIMELINE_CREATE_LIVE_VERIFIED_ANGLE_COUNTS),
        "switch_live_verified_angle_counts": sorted(SWITCH_LIVE_VERIFIED_ANGLE_COUNTS),
        "contiguous_multi_source_live_verified_angle_counts": sorted(
            CONTIGUOUS_MULTI_SOURCE_LIVE_VERIFIED_ANGLE_COUNTS
        ),
        "contiguous_multi_source_contract": {
            "layout": "contiguous",
            "ordering": "input_order_within_each_angle",
            "source_item_representation": SOURCE_ITEM_REPRESENTATION,
            "source_clip_count_per_angle_limit": SOURCE_CLIP_COUNT_PER_ANGLE_LIMIT,
            "creates_flattened_media": False,
            "sync_modes": ["in"],
            "source_offsets_supported": False,
        },
        "sparse_multi_source_live_verified_angle_counts": sorted(
            SPARSE_MULTI_SOURCE_LIVE_VERIFIED_ANGLE_COUNTS
        ),
        "sparse_multi_source_contract": {
            "layout": "sparse",
            "ordering": "input_order_within_each_angle",
            "source_item_representation": SOURCE_ITEM_REPRESENTATION,
            "source_clip_count_per_angle_limit": SOURCE_CLIP_COUNT_PER_ANGLE_LIMIT,
            "creates_flattened_media": False,
            "explicit_fields": ["record_start_frame", "source_in_frame", "duration_frames"],
            "leading_internal_trailing_gaps_supported": True,
            "same_timing_on_video_and_audio_items": True,
            "overlaps_on_same_angle_supported": False,
            "default_sync_engine": "cutagent",
            "davinci_sound_sync_used": False,
        },
        "persistent_gui_operation_support": {
            "create_2_to_6_angles": "supported",
            "distinct_video_audio_source_items": "supported",
            "explicit_source_item_timing": "supported",
            "leading_internal_trailing_gaps": "supported",
            "same_camera_grouping": "supported",
            "angle_naming_sequential_angle_camera_clip_file": "supported",
            "sync_in": "supported",
            "sync_out": "supported",
            "sync_timecode": "supported",
            "sync_marker": "supported",
            "sync_sound_cutagent_waveform": "supported",
            "audio_source_channels": "supported",
            "audio_source_reference_adaptive_all_angles_modes": "supported",
            "split_multicam_at_gaps": "supported",
            "full_clip_extents": "supported",
            "move_source_clips_to_original_clips": "supported",
            "start_timecode": "supported",
            "reorder_rename_angles": "supported",
            "move_enable_disable_remove_inner_angle_items": "supported",
            "flatten_with_grade_policy": "supported",
            "convert_timeline_or_compound_to_multicam": "supported",
            "match_frame": "supported",
            "smart_switch_persistent_equivalent": "supported",
            "per_angle_grading_and_braw_raw_workflow": "supported",
        },
        "persistent_gui_operation_notes": {
            "sound_sync_engine": "cutagent_waveform_default_and_only; davinci_sound_sync_not_invoked",
            "smart_switch": "persistent_deterministic_audio_activity_and_role_equivalent; viewer_visual_ai_is_not_a_persistent_edit_operation",
            "scope_exclusion": "viewer_layouts_and_keyboard_shortcuts_are_non_persistent_presentation_features",
        },
        "latest_live_verification": dict(LATEST_LIVE_VERIFICATION),
        "tiers": {
            "registered_native_family_pending_ui_verification": (
                "A native family exists for this angle count, but live UI behavior still requires confirmation."
            ),
            "create_supported_switch_pending_ui_verification": (
                "Create is supported generically; switch contract exists but native switch execution is not yet UI-verified."
            ),
            "project_local_reference_required": (
                "The command contract accepts this angle count only when a calibrated project-local native reference is available."
            ),
            "unsupported": "Angle count is outside the supported native multicam range.",
        },
    }
