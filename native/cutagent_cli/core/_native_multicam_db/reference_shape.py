from __future__ import annotations

from typing import Any


def _video_selector_mapping_from_item_templates(item_templates: list[dict[str, Any]], *, decode_optional_bytes_fn, selector_signature_fn) -> list[dict[str, Any]]:
    mappings: list[dict[str, Any]] = []
    video_index = 0
    for template in item_templates:
        if str(template.get("db_type") or "").strip() == "Sm2TiAudioClip":
            continue
        selector_blob = decode_optional_bytes_fn(template.get("fields_blob_b64"))
        track_index = template.get("track_index")
        mappings.append(
            {
                "angle_index": int(track_index) if track_index not in (None, "") else video_index,
                "current_selector_idx": (
                    int(template.get("current_selector_idx"))
                    if template.get("current_selector_idx") not in (None, "")
                    else None
                ),
                "selector_signature": selector_signature_fn(selector_blob),
                "selector_blob_size": len(selector_blob) if selector_blob else 0,
                "is_placeholder": bool(template.get("is_placeholder")),
            }
        )
        video_index += 1
    return mappings


def _video_selector_mapping_from_source_templates(
    source_templates_by_index: list[Any],
    *,
    selector_signature_fn,
) -> list[dict[str, Any]]:
    return [
        {
            "angle_index": index,
            "current_selector_idx": templates.video_item.current_selector_idx,
            "selector_signature": selector_signature_fn(templates.video_item.fields_blob),
            "selector_blob_size": len(templates.video_item.fields_blob) if templates.video_item.fields_blob else 0,
            "is_placeholder": templates.video_item.is_placeholder,
        }
        for index, templates in enumerate(source_templates_by_index)
    ]


def _validate_reference_video_selector_shape(
    *,
    resolved_angle_count: int,
    expected_mapping: list[dict[str, Any]],
    actual_mapping: list[dict[str, Any]],
    normalized_selector_idx_fn,
    ordered_selector_values_fn,
) -> dict[str, Any]:
    selector_mismatches: list[dict[str, Any]] = []

    if len(actual_mapping) != resolved_angle_count or len(expected_mapping) != resolved_angle_count:
        selector_mismatches.append(
            {
                "kind": "selector_angle_count_mismatch",
                "expected_angle_count": resolved_angle_count,
                "actual_angle_count": len(actual_mapping),
                "reference_angle_count": len(expected_mapping),
            }
        )

    if any(bool(entry.get("is_placeholder")) for entry in actual_mapping):
        selector_mismatches.append({"kind": "video_selector_placeholder_angle"})

    if any(entry.get("current_selector_idx") in (None,) for entry in actual_mapping):
        selector_mismatches.append({"kind": "missing_video_selector_state"})

    if resolved_angle_count == 2:
        actual_pairs = {
            (normalized_selector_idx_fn(entry.get("current_selector_idx")), entry.get("selector_signature"))
            for entry in actual_mapping
        }
        if not actual_mapping or not all(entry.get("current_selector_idx") not in (None, 0) for entry in actual_mapping):
            selector_mismatches.append(
                {
                    "kind": "missing_nonzero_video_selector",
                    "actual_values": [
                        normalized_selector_idx_fn(entry.get("current_selector_idx"))
                        for entry in actual_mapping
                    ],
                }
            )
        if len(actual_pairs) < 2:
            selector_mismatches.append({"kind": "degenerate_video_selector_shape"})
    elif resolved_angle_count == 3:
        selector_values = ordered_selector_values_fn(actual_mapping)
        if not actual_mapping or not any(value > 0 for value in selector_values):
            selector_mismatches.append(
                {
                    "kind": "missing_nonzero_video_selector",
                    "actual_values": selector_values,
                }
            )
        distinct_selector_values = set(selector_values)
        if len(distinct_selector_values) < 2:
            selector_mismatches.append(
                {
                    "kind": "insufficient_distinct_video_selector_values",
                    "actual_values": sorted(distinct_selector_values),
                }
            )
        if len(selector_values) == 3:
            if selector_values[2] == selector_values[1]:
                selector_mismatches.append(
                    {
                        "kind": "three_cam_selector_family_mismatch",
                        "expected_pattern": "angle_3_uses_distinct_selector_state",
                        "actual_values": selector_values,
                    }
                )
        actual_states = {
            (entry.get("current_selector_idx"), entry.get("selector_signature"))
            for entry in actual_mapping
        }
        if len(actual_states) < 2:
            selector_mismatches.append({"kind": "degenerate_video_selector_shape"})
    elif resolved_angle_count == 4:
        if not any(entry.get("current_selector_idx") not in (None, 0) for entry in actual_mapping):
            selector_mismatches.append({"kind": "missing_nonzero_video_selector"})
        distinct_selector_values = {
            entry.get("current_selector_idx") for entry in actual_mapping if entry.get("current_selector_idx") is not None
        }
        if len(distinct_selector_values) < 2:
            selector_mismatches.append(
                {
                    "kind": "insufficient_distinct_video_selector_values",
                    "actual_values": sorted(distinct_selector_values),
                }
            )
        actual_states = {
            (entry.get("current_selector_idx"), entry.get("selector_signature"))
            for entry in actual_mapping
        }
        if len(actual_states) < 2:
            selector_mismatches.append({"kind": "degenerate_video_selector_shape"})
    elif resolved_angle_count >= 5:
        selector_values = ordered_selector_values_fn(actual_mapping)
        if not any(value > 0 for value in selector_values):
            selector_mismatches.append(
                {
                    "kind": "missing_nonzero_video_selector",
                    "actual_values": selector_values,
                }
            )
        distinct_signatures = {
            entry.get("selector_signature")
            for entry in actual_mapping
            if entry.get("selector_signature")
        }
        if len(distinct_signatures) != resolved_angle_count:
            selector_mismatches.append(
                {
                    "kind": "degenerate_video_selector_shape",
                    "actual_signature_count": len(distinct_signatures),
                    "expected_signature_count": resolved_angle_count,
                }
            )

    return {
        "valid": not selector_mismatches,
        "expected_video_selector_mapping": expected_mapping,
        "actual_video_selector_mapping": actual_mapping,
        "selector_mismatches": selector_mismatches,
    }


def _requires_local_reference(angle_count: int, *, max_supported_angle_count: int) -> bool:
    return 2 <= int(angle_count) <= max_supported_angle_count


def _requires_calibrated_project_reference(angle_count: int, *, project_local_reference_required_angle_counts: tuple[int, ...] | list[int] | set[int]) -> bool:
    return int(angle_count) in project_local_reference_required_angle_counts


def _can_fallback_to_packaged_reference_after_rejections(
    *,
    requested_angle_count: int,
    rejected_candidates: list[dict[str, Any]],
) -> bool:
    if not rejected_candidates:
        return False
    packaged_fallback_safe_reasons = {
        "audio_placeholder_angle",
        "audio_source_set_mismatch",
        "audio_track_count_mismatch",
        "reference_item_start_mismatch",
        "reference_media_start_time_mismatch",
        "video_source_set_mismatch",
        "video_track_count_mismatch",
    }
    if all(
        set(str(reason) for reason in (candidate.get("reasons") or [])).issubset(packaged_fallback_safe_reasons)
        for candidate in rejected_candidates
    ):
        return True
    if all(
        {
            str(reason)
            for reason in (candidate.get("reasons") or [])
        }
        & {"video_track_count_mismatch", "audio_track_count_mismatch"}
        for candidate in rejected_candidates
    ):
        return True
    if int(requested_angle_count) in {5, 6}:
        return True
    if int(requested_angle_count) != 2:
        return False
    return all(
        "reference_template_shape_mismatch" in set(candidate.get("reasons") or [])
        for candidate in rejected_candidates
    )
