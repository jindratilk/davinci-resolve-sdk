from __future__ import annotations

import base64
import json
from importlib import resources
from typing import Any

from ...errors import ValidationError


def _load_reference_multicam_fixture_parts(
    *,
    angle_count: int | None,
    fixture_package: str,
    default_fixture_name: str,
    fixture_name_by_angle_count: dict[int, str],
) -> tuple[str, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    fixture_name = fixture_name_by_angle_count.get(angle_count, default_fixture_name)
    try:
        fixture_text = resources.files(fixture_package).joinpath(fixture_name).read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover - packaging/runtime failure
        raise ValidationError(
            "Native multicam reference fixture is missing.",
            details={"fixture": fixture_name, "angle_count": angle_count},
        ) from exc

    try:
        payload = json.loads(fixture_text)
    except json.JSONDecodeError as exc:  # pragma: no cover - malformed fixture
        raise ValidationError(
            "Native multicam reference fixture is not valid JSON.",
            details={"fixture": fixture_name, "angle_count": angle_count, "error": str(exc)},
        ) from exc

    multicam_media = payload.get("multicam_media") if isinstance(payload, dict) else None
    sequence = payload.get("sequence") if isinstance(payload, dict) else None
    ti_item = payload.get("ti_item") if isinstance(payload, dict) else None
    if not isinstance(multicam_media, dict) or not isinstance(sequence, dict) or not isinstance(ti_item, dict):
        raise ValidationError(
            "Native multicam reference fixture is incomplete.",
            details={"fixture": fixture_name, "angle_count": angle_count},
        )

    return fixture_name, payload, multicam_media, sequence, ti_item


def _build_reference_template_payload(
    *,
    db_type: str,
    track_index: int | None,
    is_placeholder: bool,
    media_file_path: str | None,
    media_timemap_ba: bytes | None,
    preconform_media_extents: bytes | None,
    media_frame_rate: bytes | None,
    virtual_audio_track_ba: bytes | None,
    fields_blob: bytes | None,
    in_value: str | None,
    media_track_idx: int | None,
    current_selector_idx: int | None,
    media_start_time: float | None = None,
) -> dict[str, Any]:
    return {
        "db_type": db_type,
        "track_index": track_index,
        "is_placeholder": bool(is_placeholder),
        "media_file_path": media_file_path,
        "media_timemap_b64": base64.b64encode(media_timemap_ba).decode("ascii") if media_timemap_ba else None,
        "preconform_media_extents_b64": base64.b64encode(preconform_media_extents).decode("ascii")
        if preconform_media_extents
        else None,
        "media_frame_rate_b64": base64.b64encode(media_frame_rate).decode("ascii") if media_frame_rate else None,
        "virtual_audio_track_b64": base64.b64encode(virtual_audio_track_ba).decode("ascii")
        if virtual_audio_track_ba
        else None,
        "fields_blob_b64": base64.b64encode(fields_blob).decode("ascii") if fields_blob else None,
        "in_value": in_value,
        "media_track_idx": media_track_idx,
        "current_selector_idx": current_selector_idx,
        "media_start_time": media_start_time,
    }


def _decoded_template_blob_lengths(reference: Any, decode_optional_bytes_fn) -> dict[str, list[int]]:
    lengths: dict[str, list[int]] = {"track": [], "item": []}
    for template in reference.track_templates:
        blob = decode_optional_bytes_fn(template.get("fields_blob_b64"))
        lengths["track"].append(len(blob) if blob else 0)
    for template in reference.item_templates:
        blob = decode_optional_bytes_fn(template.get("fields_blob_b64"))
        lengths["item"].append(len(blob) if blob else 0)
    return lengths


def _template_selector_values(reference: Any) -> dict[str, list[int | None]]:
    values: dict[str, list[int | None]] = {"video": [], "audio": []}
    for template in reference.item_templates:
        key = "audio" if str(template.get("db_type") or "").strip() == "Sm2TiAudioClip" else "video"
        raw_value = template.get("current_selector_idx")
        values[key].append(int(raw_value) if raw_value not in (None, "") else None)
    return values
