"""Structured multicam job planning/execution over the native DB-backed engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
import os
from typing import Any

from ..errors import ValidationError
from . import media_pool, multicam_smart_switch, multicam_ui_verdicts, native_multicam_db, podcast_audio_activity, podcast_multicam
from .audio_ops import _run_ffprobe
from ..multicam_support import (
    MAX_SUPPORTED_ANGLE_COUNT,
    SOURCE_CLIP_COUNT_PER_ANGLE_LIMIT,
    SOURCE_ITEM_REPRESENTATION,
    support_tier_for_angle_count,
)

_DEFAULT_SYNC_MODE = native_multicam_db.DEFAULT_NATIVE_ANGLE_SYNC_MODE
_DEFAULT_AUDIO_MODE = "source_audio_channels"
_AUDIO_MODE_ALIASES = {
    "source": "source_audio_channels",
    "source-audio": "source_audio_channels",
    "source-audio-channels": "source_audio_channels",
    "source_audio_channels": "source_audio_channels",
    "reference": "reference_audio",
    "reference-audio": "reference_audio",
    "reference_audio": "reference_audio",
    "adaptive": "adaptive_tracks",
    "adaptive-tracks": "adaptive_tracks",
    "adaptive_tracks": "adaptive_tracks",
    "all": "all_angles",
    "all-angles": "all_angles",
    "all_angles": "all_angles",
}
_DEFAULT_MIN_SHOT_MS = 1200
_DEFAULT_MERGE_GAP_MS = 250
_SAME_CAMERA_PROPERTY_KEYS = {
    "camera_number": ("Camera #", "Camera Number", "Camera"),
    "angle": ("Angle",),
    "reel_number": ("Reel Number", "Reel #"),
    "reel_name": ("Reel Name",),
    "roll_card": ("Roll/Card #", "Roll/Card", "Roll", "Card"),
}


@dataclass(frozen=True)
class MulticamSource:
    angle: str
    clip_name: str
    role: str | None = None
    label: str | None = None
    folder: str | None = None
    source_path: str | None = None
    source_duration_frames: int | None = None
    record_start_frame: int | None = None
    source_in_frame: int | None = None
    duration_frames: int | None = None


def _normalize_same_camera_grouping(value: Any) -> str:
    if value in (None, "", False, "none", "off", "manual"):
        return "manual"
    if value is True:
        return "camera_number"
    if isinstance(value, dict):
        if value.get("enabled") is False:
            return "manual"
        value = value.get("metadata") or value.get("property") or value.get("mode") or "camera_number"
    normalized = str(value).strip().lower().replace("#", "number").replace("/", "_").replace("-", "_").replace(" ", "_")
    aliases = {
        "camera": "camera_number",
        "camera_number": "camera_number",
        "angle": "angle",
        "reel": "reel_number",
        "reel_number": "reel_number",
        "reel_name": "reel_name",
        "roll_card": "roll_card",
        "roll_card_number": "roll_card",
    }
    if normalized not in aliases:
        raise ValidationError(
            "Unsupported same-camera grouping metadata property.",
            details={
                "same_camera_grouping": value,
                "supported_same_camera_grouping": ["manual", *_SAME_CAMERA_PROPERTY_KEYS],
            },
        )
    return aliases[normalized]


def _clip_property_and_metadata_values(clip: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read both API surfaces used by DaVinci Resolve's clip metadata UI.

    Camera, reel, and roll/card fields written with MediaPoolItem.SetMetadata()
    are not guaranteed to be mirrored by GetClipProperty().  Treating the two
    dictionaries as interchangeable made same-camera detection fail for clips
    whose metadata was populated through the official scripting API.
    """

    properties = media_pool._clip_properties(clip)
    metadata: dict[str, Any] = {}
    getter = getattr(clip, "GetMetadata", None)
    if callable(getter):
        try:
            raw_metadata = getter()
        except Exception:
            raw_metadata = None
        if isinstance(raw_metadata, dict):
            metadata = dict(raw_metadata)
    return properties, metadata


def _first_clip_field_value(
    properties: dict[str, Any],
    metadata: dict[str, Any],
    keys: tuple[str, ...],
) -> tuple[str, str, str] | None:
    for source_name, values in (("clip_property", properties), ("metadata", metadata)):
        for key in keys:
            value = str(values.get(key) or "").strip()
            if value:
                return key, value, source_name
    return None


def _job_with_resolved_same_camera_groups(conn, job: dict[str, Any]) -> dict[str, Any]:
    settings = job.get("multicam_settings") if isinstance(job.get("multicam_settings"), dict) else {}
    grouping_mode = _normalize_same_camera_grouping(settings.get("same_camera_grouping"))
    if grouping_mode == "manual":
        return job

    raw_sources = list(job.get("sources") or [])
    grouped_sources: list[dict[str, Any]] = []
    grouping_evidence: list[dict[str, Any]] = []
    property_keys = _SAME_CAMERA_PROPERTY_KEYS[grouping_mode]
    for source_index, raw_source in enumerate(raw_sources):
        if not isinstance(raw_source, dict):
            raise ValidationError(
                "Each multicam source must be an object before same-camera grouping.",
                details={"source_index": source_index, "source": raw_source},
            )
        source = dict(raw_source)
        clip_name = str(source.get("clip_name") or source.get("clip") or source.get("name") or "").strip()
        if not clip_name:
            raise ValidationError(
                "Same-camera grouping requires clip_name on every source.",
                details={"source_index": source_index, "source": source},
            )
        spec = podcast_multicam.AngleSourceSpec(
            label="__metadata_probe__",
            clip_name=clip_name,
            folder=str(source.get("folder") or source.get("folder_path") or source.get("bin") or "").strip() or None,
            source_path=str(source.get("source_path") or source.get("path") or source.get("media_path") or "").strip() or None,
        )
        match = podcast_multicam._find_resolved_angle_source_spec_match(conn, spec)
        if match is None:
            raise ValidationError(
                "A source clip required for same-camera grouping was not found in the Media Pool.",
                details={"source_index": source_index, "clip_name": clip_name},
            )
        properties, metadata = _clip_property_and_metadata_values(match["clip"])
        field = _first_clip_field_value(properties, metadata, property_keys)
        if field is None:
            raise ValidationError(
                "Same-camera grouping metadata is missing on a source clip.",
                details={
                    "reason": "same_camera_metadata_required",
                    "source_index": source_index,
                    "clip_name": clip_name,
                    "grouping_mode": grouping_mode,
                    "property_keys": list(property_keys),
                },
            )
        property_key, group_value, metadata_source = field
        source["angle"] = group_value
        grouped_sources.append(source)
        grouping_evidence.append(
            {
                "source_index": source_index,
                "clip_name": clip_name,
                "property": property_key,
                "metadata_source": metadata_source,
                "value": group_value,
                "angle": group_value,
            }
        )

    resolved_job = dict(job)
    resolved_settings = dict(settings)
    resolved_settings["same_camera_grouping"] = grouping_mode
    resolved_settings["same_camera_grouping_evidence"] = grouping_evidence
    resolved_job["multicam_settings"] = resolved_settings
    resolved_job["sources"] = grouped_sources
    return resolved_job


def _job_with_resolved_angle_names(conn, job: dict[str, Any]) -> dict[str, Any]:
    settings = job.get("multicam_settings") if isinstance(job.get("multicam_settings"), dict) else {}
    if isinstance(settings.get("angle_names"), dict) and settings["angle_names"]:
        return job
    raw_mode = str(settings.get("angle_name") or settings.get("angle_name_mode") or "sequential").strip().lower()
    mode = raw_mode.replace("-", "_").replace(" ", "_")
    aliases = {
        "sequential": "sequential",
        "angle": "angle",
        "camera": "camera_number",
        "camera_number": "camera_number",
        "clip": "clip_name",
        "clip_name": "clip_name",
        "file": "file_name",
        "file_name": "file_name",
    }
    if mode not in aliases:
        raise ValidationError(
            "Unsupported multicam angle-name mode.",
            details={
                "angle_name_mode": raw_mode,
                "supported_angle_name_modes": ["sequential", "angle", "camera", "clip_name", "file_name"],
            },
        )
    mode = aliases[mode]
    raw_sources = [dict(source) for source in list(job.get("sources") or []) if isinstance(source, dict)]
    angle_order = list(dict.fromkeys(str(source.get("angle") or "").strip() for source in raw_sources))
    if any(not angle for angle in angle_order):
        return job
    names: dict[str, str] = {}
    evidence: list[dict[str, Any]] = []
    for index, angle in enumerate(angle_order):
        source = next(source for source in raw_sources if str(source.get("angle") or "").strip() == angle)
        if mode == "sequential":
            value = f"Angle {index + 1}"
            property_key = "sequential"
        elif mode == "clip_name":
            value = str(source.get("clip_name") or source.get("clip") or source.get("name") or "").strip()
            property_key = "Clip Name"
        elif mode == "file_name":
            source_path = str(source.get("source_path") or source.get("path") or source.get("media_path") or "").strip()
            if not source_path:
                clip_name = str(source.get("clip_name") or source.get("clip") or source.get("name") or "").strip()
                spec = podcast_multicam.AngleSourceSpec(
                    label=angle,
                    clip_name=clip_name,
                    folder=str(source.get("folder") or source.get("folder_path") or source.get("bin") or "").strip() or None,
                )
                match = podcast_multicam._find_resolved_angle_source_spec_match(conn, spec)
                if match is not None:
                    properties, _metadata = _clip_property_and_metadata_values(match["clip"])
                    source_path = str(
                        properties.get("File Path")
                        or properties.get("Path")
                        or properties.get("Source Path")
                        or ""
                    ).strip()
            value = os.path.basename(source_path) if source_path else ""
            property_key = "File Name"
        else:
            clip_name = str(source.get("clip_name") or source.get("clip") or source.get("name") or "").strip()
            spec = podcast_multicam.AngleSourceSpec(
                label=angle,
                clip_name=clip_name,
                folder=str(source.get("folder") or source.get("folder_path") or source.get("bin") or "").strip() or None,
                source_path=str(source.get("source_path") or source.get("path") or source.get("media_path") or "").strip() or None,
            )
            match = podcast_multicam._find_resolved_angle_source_spec_match(conn, spec)
            properties, metadata = (
                _clip_property_and_metadata_values(match["clip"])
                if match is not None
                else ({}, {})
            )
            keys = _SAME_CAMERA_PROPERTY_KEYS[mode]
            field = _first_clip_field_value(properties, metadata, keys)
            property_key, value, _metadata_source = field if field is not None else ("", "", "")
        if not value:
            raise ValidationError(
                "Multicam angle-name metadata is missing for a source angle.",
                details={"reason": "angle_name_metadata_required", "mode": mode, "angle": angle, "source": source},
            )
        names[angle] = value
        evidence.append({"angle": angle, "name": value, "mode": mode, "property": property_key})
    resolved = dict(job)
    resolved_settings = dict(settings)
    resolved_settings["angle_name_mode"] = mode
    resolved_settings["angle_names"] = names
    resolved_settings["angle_name_evidence"] = evidence
    resolved["multicam_settings"] = resolved_settings
    return resolved


def _job_with_resolved_creation_metadata(conn, job: dict[str, Any]) -> dict[str, Any]:
    return _job_with_resolved_angle_names(conn, _job_with_resolved_same_camera_groups(conn, job))


def _load_job_payload(*, job_path: str | None = None, job_json: str | None = None) -> dict[str, Any]:
    if bool(job_path) == bool(job_json):
        raise ValidationError(
            "Provide exactly one of --job or --job-json.",
            details={
                "job_path": job_path,
                "has_job_json": bool(job_json),
                "example_usage": [
                    "multicam settings --job /absolute/path/job.json",
                    "multicam settings --job-json '{\"sources\": [...], \"segments\": [...], \"multicam_settings\": {\"multicam_name\": \"Interview MC\"}, \"timeline_settings\": {\"timeline_name\": \"Interview Cut\"}}'",
                ],
                "example_job": {
                    "sources": [
                        {"angle": "A", "clip_name": "Cam A"},
                        {"angle": "B", "clip_name": "Cam B"},
                    ],
                    "segments": [
                        {"start_ms": 0, "end_ms": 3000, "angle": "A"},
                        {"start_ms": 3000, "end_ms": 6000, "angle": "B"},
                    ],
                    "multicam_settings": {"multicam_name": "Interview MC"},
                    "timeline_settings": {"timeline_name": "Interview Cut"},
                },
            },
        )

    if job_path:
        expanded = os.path.abspath(os.path.expanduser(job_path))
        if not os.path.isfile(expanded):
            raise ValidationError("Multicam job file not found.", details={"job": expanded})
        try:
            with open(expanded, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                "Multicam job file is not valid JSON.",
                details={"job": expanded, "error": str(exc)},
            ) from exc
    else:
        try:
            payload = json.loads(str(job_json))
        except json.JSONDecodeError as exc:
            raise ValidationError(
                "Multicam job JSON is not valid.",
                details={"error": str(exc)},
            ) from exc

    if not isinstance(payload, dict):
        raise ValidationError("Multicam job must be a JSON object.")
    return payload


def _parse_sources(raw_sources: Any, *, allow_missing_angles: bool = False) -> list[MulticamSource]:
    sources: list[MulticamSource] = []
    for source_index, raw in enumerate(list(raw_sources or [])):
        if not isinstance(raw, dict):
            continue
        angle = str(raw.get("angle") or "").strip()
        if not angle and allow_missing_angles:
            angle = f"__metadata_group_{source_index + 1}__"
        clip_name = str(raw.get("clip_name") or raw.get("clip") or raw.get("name") or "").strip()
        role = str(raw.get("role") or "").strip() or None
        label = str(raw.get("label") or "").strip() or None
        folder = str(raw.get("folder") or raw.get("folder_path") or raw.get("bin") or "").strip() or None
        source_path = str(raw.get("source_path") or raw.get("path") or raw.get("media_path") or "").strip() or None
        source_duration_frames = raw.get("source_duration_frames")
        record_start_frame = raw.get("record_start_frame")
        source_in_frame = raw.get("source_in_frame")
        duration_frames = raw.get("duration_frames")
        try:
            source_duration_frames = int(source_duration_frames) if source_duration_frames is not None else None
            record_start_frame = int(record_start_frame) if record_start_frame is not None else None
            source_in_frame = int(source_in_frame) if source_in_frame is not None else None
            duration_frames = int(duration_frames) if duration_frames is not None else None
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "Multicam source frame fields must be integers when provided.",
                details={
                    "source": raw,
                    "record_start_frame": record_start_frame,
                    "source_in_frame": source_in_frame,
                    "duration_frames": duration_frames,
                    "source_duration_frames": source_duration_frames,
                },
            ) from exc
        if source_duration_frames is not None and source_duration_frames <= 0:
            raise ValidationError(
                "Multicam source source_duration_frames must be positive when provided.",
                details={"source": raw, "source_duration_frames": source_duration_frames},
            )
        if record_start_frame is not None and record_start_frame < 0:
            raise ValidationError(
                "Multicam source record_start_frame must be zero or greater when provided.",
                details={"source": raw, "record_start_frame": record_start_frame},
            )
        if source_in_frame is not None and source_in_frame < 0:
            raise ValidationError(
                "Multicam source source_in_frame must be zero or greater when provided.",
                details={"source": raw, "source_in_frame": source_in_frame},
            )
        if duration_frames is not None and duration_frames <= 0:
            raise ValidationError(
                "Multicam source duration_frames must be positive when provided.",
                details={"source": raw, "duration_frames": duration_frames},
            )
        if (
            source_duration_frames is not None
            and source_in_frame is not None
            and duration_frames is not None
            and source_in_frame + duration_frames > source_duration_frames
        ):
            raise ValidationError(
                "Multicam source range exceeds source_duration_frames.",
                details={
                    "source": raw,
                    "source_in_frame": source_in_frame,
                    "duration_frames": duration_frames,
                    "source_duration_frames": source_duration_frames,
                },
            )
        if not angle or not clip_name:
            raise ValidationError(
                "Each multicam source must define both angle and clip_name.",
                details={"source": raw},
            )
        sources.append(
            MulticamSource(
                angle=angle,
                clip_name=clip_name,
                role=role,
                label=label,
                folder=folder,
                source_path=source_path,
                source_duration_frames=source_duration_frames,
                record_start_frame=record_start_frame,
                source_in_frame=source_in_frame,
                duration_frames=duration_frames,
            )
        )

    source_angles = list(dict.fromkeys(source.angle for source in sources))
    if len(source_angles) < 2:
        raise ValidationError(
            "Multicam requires at least 2 logical angles.",
            details={"source_count": len(sources), "angle_count": len(source_angles)},
        )
    if len(source_angles) > MAX_SUPPORTED_ANGLE_COUNT and not allow_missing_angles:
        raise ValidationError(
            f"Multicam currently supports at most {MAX_SUPPORTED_ANGLE_COUNT} logical angles.",
            details={
                "source_count": len(sources),
                "angle_count": len(source_angles),
                "max_supported_angle_count": MAX_SUPPORTED_ANGLE_COUNT,
                "reason": "unsupported_angle_count",
            },
        )

    seen_source_identities: set[str] = set()
    for source in sources:
        if source.source_path:
            source_identity = f"source_path:{os.path.normcase(os.path.normpath(os.path.expanduser(source.source_path)))}"
        elif source.folder:
            normalized_folder = str(source.folder).strip().strip("/")
            source_identity = f"folder:{normalized_folder}/{source.clip_name}"
        else:
            source_identity = f"clip_name:{source.clip_name}"
        if source_identity in seen_source_identities:
            raise ValidationError(
                "Each multicam source may only appear once in the source set.",
                details={
                    "clip_name": source.clip_name,
                    "folder": source.folder,
                    "source_path": source.source_path,
                },
            )
        seen_source_identities.add(source_identity)
    return sources


def _normalize_effective_settings(job: dict[str, Any], *, sources: list[MulticamSource]) -> dict[str, Any]:
    multicam_settings = job.get("multicam_settings")
    if multicam_settings is None:
        multicam_settings = {}
    if not isinstance(multicam_settings, dict):
        raise ValidationError("multicam_settings must be an object.", details={"multicam_settings": multicam_settings})

    timeline_settings = job.get("timeline_settings")
    if timeline_settings is None:
        timeline_settings = {}
    if not isinstance(timeline_settings, dict):
        raise ValidationError("timeline_settings must be an object.", details={"timeline_settings": timeline_settings})

    source_angles = list(dict.fromkeys(source.angle for source in sources))
    requested_order = multicam_settings.get("angle_order") or source_angles
    if not isinstance(requested_order, list) or not requested_order:
        raise ValidationError(
            "multicam_settings.angle_order must be a non-empty list.",
            details={"angle_order": requested_order},
        )
    angle_order = [str(item).strip() for item in requested_order if str(item).strip()]
    if sorted(angle_order) != sorted(source_angles):
        raise ValidationError(
            "multicam_settings.angle_order must contain exactly the source angles.",
            details={"angle_order": angle_order, "source_angles": source_angles},
        )

    angle_names = multicam_settings.get("angle_names") or {}
    if not isinstance(angle_names, dict):
        raise ValidationError("multicam_settings.angle_names must be an object.", details={"angle_names": angle_names})
    normalized_angle_names = {
        angle: str(angle_names.get(angle) or f"Angle {index + 1}").strip()
        for index, angle in enumerate(angle_order)
    }

    timeline_name = str(
        timeline_settings.get("timeline_name")
        or multicam_settings.get("timeline_name")
        or job.get("timeline_name")
        or ""
    ).strip()
    if not timeline_name:
        raise ValidationError("A target timeline_name is required for multicam jobs.")

    multicam_name = str(
        multicam_settings.get("multicam_name")
        or job.get("multicam_name")
        or f"{timeline_name} Multicam"
    ).strip()
    if not multicam_name:
        raise ValidationError("A multicam_name is required for multicam jobs.")

    default_video_angle = str(multicam_settings.get("default_video_angle") or angle_order[0]).strip()
    default_audio_angle = str(multicam_settings.get("default_audio_angle") or default_video_angle).strip()
    if default_video_angle not in angle_order:
        raise ValidationError(
            "default_video_angle must be one of the source angles.",
            details={"default_video_angle": default_video_angle, "angle_order": angle_order},
        )
    if default_audio_angle not in angle_order:
        raise ValidationError(
            "default_audio_angle must be one of the source angles.",
            details={"default_audio_angle": default_audio_angle, "angle_order": angle_order},
        )

    sync_mode = native_multicam_db.normalize_native_angle_sync_mode(
        multicam_settings.get("sync_mode") or _DEFAULT_SYNC_MODE,
        details_key="sync_mode",
        supported_key="supported_sync_modes",
    )
    reference_source = native_multicam_db.normalize_multicam_reference_source_policy(
        multicam_settings.get("reference_source") or multicam_settings.get("reference_source_policy"),
        details_key="reference_source",
        supported_key="supported_reference_sources",
    )

    sync_engine = str(multicam_settings.get("sync_engine") or "cutagent").strip().lower().replace("_", "-")
    if sync_engine != "cutagent":
        raise ValidationError(
            "Unsupported multicam sync_engine.",
            details={
                "sync_engine": sync_engine,
                "supported_sync_engines": ["cutagent"],
                "reason": "davinci_sound_sync_not_used",
            },
        )

    raw_audio_mode = str(multicam_settings.get("audio_mode") or _DEFAULT_AUDIO_MODE).strip().lower()
    audio_mode = _AUDIO_MODE_ALIASES.get(raw_audio_mode.replace(" ", "-").replace("_", "-"))
    if audio_mode is None:
        audio_mode = _AUDIO_MODE_ALIASES.get(raw_audio_mode)
    if audio_mode is None:
        raise ValidationError(
            "Unsupported multicam audio_mode.",
            details={
                "audio_mode": multicam_settings.get("audio_mode"),
                "supported_audio_modes": [
                    "source_audio_channels",
                    "reference_audio",
                    "adaptive_tracks",
                    "all_angles",
                ],
            },
        )
    sync_channel = podcast_multicam._sync_planner.normalize_sync_channel(
        multicam_settings.get("sync_channel", "auto")
    )
    marker_name = str(multicam_settings.get("marker_name") or "").strip() or None
    if sync_mode == "marker" and marker_name is None:
        # An omitted name intentionally means "the one marker on each clip".
        marker_name = None
    full_clip_extents = bool(multicam_settings.get("full_clip_extents", True))
    split_at_gaps = bool(multicam_settings.get("split_at_gaps", False))
    same_camera_grouping = _normalize_same_camera_grouping(multicam_settings.get("same_camera_grouping"))
    same_camera_grouping_evidence = list(multicam_settings.get("same_camera_grouping_evidence") or [])
    start_timecode = str(
        multicam_settings.get("start_timecode")
        or multicam_settings.get("multicam_start_timecode")
        or ""
    ).strip() or None
    if split_at_gaps and sync_mode != "sound":
        raise ValidationError(
            "split_at_gaps is available only with multicam sound sync.",
            details={"sync_mode": sync_mode, "reason": "split_at_gaps_requires_sound_sync"},
        )
    has_explicit_item_timing = any(
        source.record_start_frame is not None
        or source.source_in_frame is not None
        or source.duration_frames is not None
        for source in sources
    )
    source_layout = str(
        multicam_settings.get("source_layout") or ("sparse" if has_explicit_item_timing else "contiguous")
    ).strip().lower().replace("_", "-")
    if source_layout not in {"contiguous", "sparse"}:
        raise ValidationError(
            "Unsupported multicam source_layout.",
            details={"source_layout": source_layout, "supported_source_layouts": ["contiguous", "sparse"]},
        )
    source_counts_by_angle = {
        angle: sum(1 for source in sources if source.angle == angle)
        for angle in source_angles
    }
    video_source_offsets = _normalize_video_source_offsets(
        multicam_settings.get("video_source_offsets_frames"),
        angle_map={angle: angle for angle in angle_order},
    )
    return {
        "sync_mode": sync_mode,
        "sync_engine": sync_engine,
        "reference_source": reference_source,
        "angle_order": angle_order,
        "angle_names": normalized_angle_names,
        "angle_name_mode": str(multicam_settings.get("angle_name_mode") or "explicit").strip(),
        "angle_name_evidence": list(multicam_settings.get("angle_name_evidence") or []),
        "audio_mode": audio_mode,
        "sync_channel": sync_channel,
        "marker_name": marker_name,
        "full_clip_extents": full_clip_extents,
        "split_at_gaps": split_at_gaps,
        "move_source_clips_to_original_bin": bool(
            multicam_settings.get("move_source_clips_to_original_bin")
            or multicam_settings.get("move_original_clips")
        ),
        "start_timecode": start_timecode,
        "same_camera_grouping": same_camera_grouping,
        "same_camera_grouping_evidence": same_camera_grouping_evidence,
        "source_layout": source_layout,
        "source_item_representation": SOURCE_ITEM_REPRESENTATION,
        "source_clip_count_per_angle_limit": SOURCE_CLIP_COUNT_PER_ANGLE_LIMIT,
        "creates_flattened_media": False,
        "source_counts_by_angle": source_counts_by_angle,
        "default_video_angle": default_video_angle,
        "default_audio_angle": default_audio_angle,
        "min_shot_ms": int(multicam_settings.get("min_shot_ms") or _DEFAULT_MIN_SHOT_MS),
        "merge_gap_ms": int(multicam_settings.get("merge_gap_ms") or _DEFAULT_MERGE_GAP_MS),
        "hold_short_utterances": bool(multicam_settings.get("hold_short_utterances", False)),
        "reaction_hold_ms": int(multicam_settings.get("reaction_hold_ms") or 0),
        "switch_on": list(multicam_settings.get("switch_on") or []),
        "switch_exceptions": list(multicam_settings.get("switch_exceptions") or []),
        "timeline_name": timeline_name,
        "multicam_name": multicam_name,
        "timeline_duration_frames": _normalize_timeline_duration_frames(
            timeline_settings.get("duration_frames") or timeline_settings.get("timeline_duration_frames")
        ),
        "video_source_offsets_frames": video_source_offsets,
        "video_source_offset_fallback_angle": multicam_settings.get("video_source_offset_fallback_angle"),
    }


def _sources_to_angle_map(sources: list[MulticamSource], angle_order: list[str]) -> dict[str, str]:
    by_angle: dict[str, str] = {}
    for source in sources:
        by_angle.setdefault(source.angle, source.clip_name)
    return {angle: by_angle[angle] for angle in angle_order}


def _move_sources_to_original_clips_bin(conn: Any, sources: list[MulticamSource]) -> dict[str, Any]:
    media_pool_api = getattr(conn, "media_pool", None)
    if media_pool_api is None:
        raise ValidationError("Moving multicam ISO sources requires the DaVinci Resolve Media Pool API.")
    current_folder = media_pool_api.GetCurrentFolder()
    if current_folder is None:
        raise ValidationError("The current Media Pool folder could not be resolved.")
    target_folder = next(
        (
            folder
            for folder in list(current_folder.GetSubFolderList() or [])
            if str(folder.GetName() or "").strip() == "Original Clips"
        ),
        None,
    )
    created = False
    if target_folder is None:
        target_folder = media_pool_api.AddSubFolder(current_folder, "Original Clips")
        created = True
    if target_folder is None:
        raise ValidationError("DaVinci Resolve did not create the Original Clips Media Pool bin.")

    matches = media_pool.collect_append_media_matches(conn)
    selected: list[Any] = []
    evidence: list[dict[str, Any]] = []
    seen: set[int] = set()
    for source in sources:
        candidates = list(matches)
        if source.source_path:
            candidates = [
                match
                for match in candidates
                if media_pool._source_path_matches(match.get("source_path"), source.source_path)
            ]
        if source.folder:
            candidates = [match for match in candidates if str(match.get("folder") or "") == source.folder]
        if not source.source_path:
            candidates = [match for match in candidates if str(match.get("name") or "") == source.clip_name]
        if len(candidates) != 1:
            raise ValidationError(
                "A multicam ISO source could not be resolved uniquely before moving it to Original Clips.",
                details={
                    "reason": "original_clip_source_match_not_unique",
                    "clip_name": source.clip_name,
                    "source_path": source.source_path,
                    "match_count": len(candidates),
                },
            )
        clip = candidates[0]["clip"]
        if id(clip) not in seen:
            seen.add(id(clip))
            selected.append(clip)
            evidence.append(
                {
                    "clip_name": candidates[0].get("name"),
                    "source_path": candidates[0].get("source_path"),
                    "from_folder": candidates[0].get("folder"),
                }
            )
    move_result = media_pool_api.MoveClips(selected, target_folder)
    if move_result is False:
        raise ValidationError("DaVinci Resolve rejected moving multicam ISO sources to Original Clips.")
    expected_media_ids = {
        str(clip.GetMediaId() or "").strip()
        for clip in selected
        if callable(getattr(clip, "GetMediaId", None))
    }
    expected_paths = {
        os.path.realpath(str(entry.get("source_path") or ""))
        for entry in evidence
        if str(entry.get("source_path") or "").strip()
    }
    target_clips = list(target_folder.GetClipList() or [])
    target_media_ids = {
        str(clip.GetMediaId() or "").strip()
        for clip in target_clips
        if callable(getattr(clip, "GetMediaId", None))
    }
    target_paths = {
        os.path.realpath(str(clip.GetClipProperty("File Path") or ""))
        for clip in target_clips
        if callable(getattr(clip, "GetClipProperty", None))
        and str(clip.GetClipProperty("File Path") or "").strip()
    }
    media_ids_verified = bool(expected_media_ids) and expected_media_ids.issubset(target_media_ids)
    paths_verified = bool(expected_paths) and expected_paths.issubset(target_paths)
    if not (media_ids_verified or paths_verified):
        raise ValidationError(
            "Original Clips move did not survive Media Pool API readback.",
            details={
                "reason": "original_clips_move_readback_failed",
                "clip_count": len(selected),
                "expected_media_ids": sorted(expected_media_ids),
                "target_media_ids": sorted(target_media_ids),
                "expected_paths": sorted(expected_paths),
                "target_paths": sorted(target_paths),
            },
        )
    return {
        "status": "verified",
        "bin_name": "Original Clips",
        "bin_created": created,
        "moved_clip_count": len(selected),
        "clips": evidence,
        "readback_key": "media_id" if media_ids_verified else "file_path",
        "route": "MediaPool.AddSubFolder/MoveClips/GetClipList",
    }


def _split_sources_at_global_gaps(sources: list[MulticamSource]) -> list[list[MulticamSource]]:
    """Partition source recordings into multicam events separated by a global gap.

    Explicit sparse timing wins. Without it, repeated per-angle source occurrence
    indexes represent separate synchronized recording groups, matching the
    create-dialog meaning of splitting discontinuous camera files at gaps.
    """
    if all(source.record_start_frame is not None and source.duration_frames is not None for source in sources):
        indexed = sorted(
            enumerate(sources),
            key=lambda entry: (int(entry[1].record_start_frame or 0), entry[0]),
        )
        groups: list[list[MulticamSource]] = []
        current: list[MulticamSource] = []
        current_end: int | None = None
        for _index, source in indexed:
            start = int(source.record_start_frame or 0)
            end = start + int(source.duration_frames or 0)
            if current and current_end is not None and start > current_end:
                groups.append(current)
                current = []
                current_end = None
            current.append(source)
            current_end = max(current_end or end, end)
        if current:
            groups.append(current)
        groups = [
            [
                replace(source, record_start_frame=int(source.record_start_frame or 0) - group_start)
                for source in group
            ]
            for group in groups
            for group_start in [min(int(source.record_start_frame or 0) for source in group)]
        ]
    else:
        occurrence_by_angle: dict[str, int] = {}
        grouped: dict[int, list[MulticamSource]] = {}
        for source in sources:
            occurrence = occurrence_by_angle.get(source.angle, 0)
            occurrence_by_angle[source.angle] = occurrence + 1
            grouped.setdefault(occurrence, []).append(source)
        groups = [grouped[index] for index in sorted(grouped)]
    for index, group in enumerate(groups, start=1):
        angles = list(dict.fromkeys(source.angle for source in group))
        if len(angles) < 2:
            raise ValidationError(
                "Split Multicam at gaps produced a recording group with fewer than two camera angles.",
                details={
                    "reason": "split_gap_group_requires_two_angles",
                    "split_group": index,
                    "angles": angles,
                    "clip_names": [source.clip_name for source in group],
                },
            )
    return groups


def _normalize_video_source_offsets(raw: Any, *, angle_map: dict[str, str]) -> dict[str, int]:
    if raw in (None, ""):
        return {}
    if not isinstance(raw, dict):
        raise ValidationError(
            "multicam_settings.video_source_offsets_frames must be an object keyed by angle.",
            details={"video_source_offsets_frames": raw},
        )
    offsets: dict[str, int] = {}
    for angle, value in raw.items():
        angle_key = str(angle or "").strip()
        if angle_key not in angle_map:
            raise ValidationError(
                "Video source offset references an unknown multicam angle.",
                details={
                    "angle": angle_key,
                    "known_angles": sorted(angle_map.keys()),
                    "video_source_offsets_frames": raw,
                },
            )
        try:
            offsets[angle_key] = int(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "Video source offset frames must be integers.",
                details={"angle": angle_key, "value": value},
            ) from exc
    return offsets


def _normalize_timeline_duration_frames(raw: Any) -> int | None:
    if raw in (None, ""):
        return None
    try:
        duration_frames = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "timeline_settings.duration_frames must be an integer when provided.",
            details={"duration_frames": raw},
        ) from exc
    if duration_frames <= 0:
        raise ValidationError(
            "timeline_settings.duration_frames must be positive when provided.",
            details={"duration_frames": duration_frames},
        )
    return duration_frames


def _apply_video_source_offsets_to_plan(
    plan: dict[str, Any],
    *,
    angle_map: dict[str, str],
    effective_settings: dict[str, Any],
    sources: list[MulticamSource],
    planning_fps: float,
    timeline_start_frame: int,
) -> None:
    offsets = _normalize_video_source_offsets(
        effective_settings.get("video_source_offsets_frames"),
        angle_map=angle_map,
    )
    if not offsets:
        return
    fallback_angle = _select_video_source_offset_fallback_angle(
        angle_map=angle_map,
        offsets=offsets,
        effective_settings=effective_settings,
    )
    source_duration_frames_by_angle = _video_source_duration_frames_by_angle(sources, planning_fps=planning_fps)
    adjusted_segments: list[dict[str, Any]] = []
    adjustments: list[dict[str, Any]] = []
    for row in list(plan.get("segments") or []):
        if not isinstance(row, dict):
            adjusted_segments.append(row)
            continue
        angle = str(row.get("angle") or "").strip()
        record_start = row.get("record_start_frame")
        if record_start is None:
            record_start = row.get("start_frame")
        record_end = row.get("record_end_frame")
        if record_end is None:
            record_end = row.get("end_frame")
        if angle not in offsets or record_start is None:
            adjusted_segments.append(row)
            continue
        if record_end is None:
            raise ValidationError(
                "Video source offset requires each segment to have an end frame.",
                details={"angle": angle, "segment": row},
            )
        source_start = _video_source_start_frame(
            record_start_frame=int(record_start),
            offset_frames=int(offsets[angle]),
            timeline_start_frame=int(timeline_start_frame),
        )
        duration = int(record_end) - int(record_start)
        if duration <= 0:
            adjusted_segments.append(row)
            continue
        if source_start >= 0:
            _validate_video_source_range(
                angle=angle,
                source_start_frame=source_start,
                duration_frames=duration,
                source_duration_frames_by_angle=source_duration_frames_by_angle,
            )
            row["source_start_frame"] = source_start
            adjusted_segments.append(row)
            continue
        trim_frames = -source_start
        if fallback_angle is None:
            raise ValidationError(
                "Video source offset would create a negative source frame before any fallback angle can cover it.",
                details={
                    "angle": angle,
                    "offset_frames": offsets[angle],
                    "record_start_frame": int(record_start),
                    "source_start_frame": source_start,
                    "known_offsets": offsets,
                },
            )
        fallback_end = min(int(record_end), int(record_start) + trim_frames)
        fallback_row = dict(row)
        fallback_row["angle"] = fallback_angle
        fallback_row["clip_name"] = angle_map[fallback_angle]
        fallback_row["record_start_frame"] = int(record_start)
        fallback_row["record_end_frame"] = fallback_end
        fallback_row["start_frame"] = int(record_start)
        fallback_row["end_frame"] = fallback_end
        fallback_row["source_start_frame"] = _video_source_start_frame(
            record_start_frame=int(record_start),
            offset_frames=int(offsets.get(fallback_angle, 0)),
            timeline_start_frame=int(timeline_start_frame),
        )
        _validate_video_source_range(
            angle=fallback_angle,
            source_start_frame=int(fallback_row["source_start_frame"]),
            duration_frames=fallback_end - int(record_start),
            source_duration_frames_by_angle=source_duration_frames_by_angle,
        )
        fallback_row["text"] = str(row.get("text") or "video_source_offset_preroll_fallback")
        if "video_source_offset_preroll_fallback" not in fallback_row["text"]:
            fallback_row["text"] = f"{fallback_row['text']}|video_source_offset_preroll_fallback"
        adjusted_segments.append(fallback_row)
        adjustments.append(
            {
                "angle": angle,
                "fallback_angle": fallback_angle,
                "record_start_frame": int(record_start),
                "record_end_frame": fallback_end,
                "reason": "negative_source_start",
            }
        )
        if duration > trim_frames:
            trimmed_row = dict(row)
            trimmed_row["record_start_frame"] = int(record_start) + trim_frames
            trimmed_row["start_frame"] = int(record_start) + trim_frames
            trimmed_row["source_start_frame"] = 0
            _validate_video_source_range(
                angle=angle,
                source_start_frame=0,
                duration_frames=int(record_end) - int(trimmed_row["record_start_frame"]),
                source_duration_frames_by_angle=source_duration_frames_by_angle,
            )
            adjusted_segments.append(trimmed_row)
            adjustments.append(
                {
                    "angle": angle,
                    "record_start_frame": int(record_start) + trim_frames,
                    "record_end_frame": int(record_end),
                    "trimmed_start_frames": trim_frames,
                    "reason": "negative_source_start_trimmed",
                }
            )
    plan["segments"] = adjusted_segments
    plan["segment_count"] = len(adjusted_segments)
    plan["video_source_offsets_frames"] = dict(offsets)
    if fallback_angle is not None:
        plan["video_source_offset_fallback_angle"] = fallback_angle
    if adjustments:
        plan["video_source_offset_adjustments"] = adjustments


def _apply_video_source_container_offsets_to_plan(
    plan: dict[str, Any],
    *,
    angle_map: dict[str, str],
    effective_settings: dict[str, Any],
    sources: list[MulticamSource],
    planning_fps: float,
    timeline_start_frame: int,
) -> None:
    offsets = _normalize_video_source_offsets(
        effective_settings.get("video_source_offsets_frames"),
        angle_map=angle_map,
    )
    if not offsets:
        return
    fallback_angle = _select_video_source_offset_fallback_angle(
        angle_map=angle_map,
        offsets=offsets,
        effective_settings=effective_settings,
    )
    source_duration_frames_by_angle = _video_source_duration_frames_by_angle(sources, planning_fps=planning_fps)
    adjusted_segments: list[dict[str, Any]] = []
    adjustments: list[dict[str, Any]] = []
    for row in list(plan.get("segments") or []):
        if not isinstance(row, dict):
            adjusted_segments.append(row)
            continue
        angle = str(row.get("angle") or "").strip()
        record_start = row.get("record_start_frame")
        if record_start is None:
            record_start = row.get("start_frame")
        record_end = row.get("record_end_frame")
        if record_end is None:
            record_end = row.get("end_frame")
        if angle not in offsets or record_start is None:
            row["source_start_frame"] = None
            adjusted_segments.append(row)
            continue
        if record_end is None:
            raise ValidationError(
                "Video source offset requires each segment to have an end frame.",
                details={"angle": angle, "segment": row},
            )
        record_start_int = int(record_start)
        record_end_int = int(record_end)
        duration = record_end_int - record_start_int
        if duration <= 0:
            row["source_start_frame"] = None
            adjusted_segments.append(row)
            continue
        offset = int(offsets.get(angle, 0))
        source_start = _video_source_start_frame(
            record_start_frame=record_start_int,
            offset_frames=offset,
            timeline_start_frame=int(timeline_start_frame),
        )
        if source_start >= 0:
            _validate_video_source_range(
                angle=angle,
                source_start_frame=source_start,
                duration_frames=duration,
                source_duration_frames_by_angle=source_duration_frames_by_angle,
            )
            row["source_start_frame"] = None
            adjusted_segments.append(row)
            continue
        trim_frames = -source_start
        if fallback_angle is None:
            raise ValidationError(
                "Video source offset would select an angle before it exists in the synced multicam container.",
                details={
                    "angle": angle,
                    "offset_frames": offset,
                    "record_start_frame": record_start_int,
                    "source_start_frame": source_start,
                    "known_offsets": offsets,
                },
            )
        fallback_end = min(record_end_int, record_start_int + trim_frames)
        fallback_row = dict(row)
        fallback_row["angle"] = fallback_angle
        fallback_row["clip_name"] = angle_map[fallback_angle]
        fallback_row["record_start_frame"] = record_start_int
        fallback_row["record_end_frame"] = fallback_end
        fallback_row["start_frame"] = record_start_int
        fallback_row["end_frame"] = fallback_end
        fallback_row["source_start_frame"] = None
        fallback_source_start = _video_source_start_frame(
            record_start_frame=record_start_int,
            offset_frames=int(offsets.get(fallback_angle, 0)),
            timeline_start_frame=int(timeline_start_frame),
        )
        _validate_video_source_range(
            angle=fallback_angle,
            source_start_frame=fallback_source_start,
            duration_frames=fallback_end - record_start_int,
            source_duration_frames_by_angle=source_duration_frames_by_angle,
        )
        fallback_row["text"] = str(row.get("text") or "video_source_offset_preroll_fallback")
        if "video_source_offset_preroll_fallback" not in fallback_row["text"]:
            fallback_row["text"] = f"{fallback_row['text']}|video_source_offset_preroll_fallback"
        adjusted_segments.append(fallback_row)
        adjustments.append(
            {
                "angle": angle,
                "fallback_angle": fallback_angle,
                "record_start_frame": record_start_int,
                "record_end_frame": fallback_end,
                "reason": "container_angle_unavailable_before_synced_start",
            }
        )
        if record_end_int > fallback_end:
            trimmed_row = dict(row)
            trimmed_row["record_start_frame"] = fallback_end
            trimmed_row["start_frame"] = fallback_end
            trimmed_row["source_start_frame"] = None
            _validate_video_source_range(
                angle=angle,
                source_start_frame=0,
                duration_frames=record_end_int - fallback_end,
                source_duration_frames_by_angle=source_duration_frames_by_angle,
            )
            adjusted_segments.append(trimmed_row)
            adjustments.append(
                {
                    "angle": angle,
                    "record_start_frame": fallback_end,
                    "record_end_frame": record_end_int,
                    "trimmed_start_frames": trim_frames,
                    "reason": "container_angle_trimmed_to_synced_start",
                }
            )
    plan["segments"] = adjusted_segments
    plan["segment_count"] = len(adjusted_segments)
    plan["video_source_offsets_frames"] = dict(offsets)
    plan["video_source_offsets_applied_in"] = "multicam_container"
    if fallback_angle is not None:
        plan["video_source_offset_fallback_angle"] = fallback_angle
    if adjustments:
        plan["video_source_offset_adjustments"] = adjustments


def _video_source_duration_frames_by_angle(
    sources: list[MulticamSource],
    *,
    planning_fps: float,
) -> dict[str, int]:
    durations: dict[str, int] = {}
    fps = float(planning_fps or 0.0)
    for source in sources:
        if source.source_duration_frames is not None:
            durations[source.angle] = int(source.source_duration_frames)
            continue
        if fps <= 0:
            continue
        duration_ms = _probe_video_duration_ms(source.source_path)
        if duration_ms is not None and duration_ms > 0:
            durations[source.angle] = int(round(float(duration_ms) * fps / 1000.0))
    return durations


def _video_source_start_frame(
    *,
    record_start_frame: int,
    offset_frames: int,
    timeline_start_frame: int,
) -> int:
    return int(record_start_frame) - int(timeline_start_frame) + int(offset_frames)


def _validate_video_source_range(
    *,
    angle: str,
    source_start_frame: int,
    duration_frames: int,
    source_duration_frames_by_angle: dict[str, int],
) -> None:
    if duration_frames <= 0:
        return
    if source_start_frame < 0:
        raise ValidationError(
            "Video source offset would create a negative source frame.",
            details={"angle": angle, "source_start_frame": source_start_frame},
        )
    source_duration = source_duration_frames_by_angle.get(angle)
    if source_duration is None:
        return
    source_end = int(source_start_frame) + int(duration_frames)
    if source_end > int(source_duration):
        raise ValidationError(
            "Video source offset would exceed the selected angle's source duration.",
            details={
                "angle": angle,
                "source_start_frame": int(source_start_frame),
                "duration_frames": int(duration_frames),
                "source_end_frame": source_end,
                "source_duration_frames": int(source_duration),
            },
        )


def _shifted_container_duration_frames(
    resolved_angles: list[dict[str, Any]],
    *,
    angle_order: list[str],
    video_source_offsets_frames: dict[str, int],
) -> int | None:
    durations: list[int] = []
    for index, item in enumerate(resolved_angles):
        duration_frames = item.get("duration_frames")
        if duration_frames is None:
            continue
        angle = str(item.get("label") or item.get("angle") or "").strip()
        if not angle and index < len(angle_order):
            angle = str(angle_order[index] or "").strip()
        if not angle:
            continue
        offset_frames = int(video_source_offsets_frames.get(angle, 0))
        available_duration = int(duration_frames) - offset_frames
        if available_duration <= 0:
            raise ValidationError(
                "Video source offset leaves no available media in the synced multicam container.",
                details={
                    "angle": angle,
                    "duration_frames": int(duration_frames),
                    "offset_frames": offset_frames,
                    "available_duration_frames": available_duration,
                },
            )
        durations.append(available_duration)
    return min(durations) if durations else None


def _shifted_source_duration_frames(
    sources: list[MulticamSource],
    *,
    planning_fps: float,
    video_source_offsets_frames: dict[str, int],
) -> int | None:
    source_duration_frames_by_angle = _video_source_duration_frames_by_angle(sources, planning_fps=planning_fps)
    durations: list[int] = []
    for source in sources:
        source_duration = source_duration_frames_by_angle.get(source.angle)
        if source_duration is None:
            continue
        offset_frames = int(video_source_offsets_frames.get(source.angle, 0))
        available_duration = int(source_duration) - offset_frames
        if available_duration <= 0:
            raise ValidationError(
                "Video source offset leaves no available media in the source clip.",
                details={
                    "angle": source.angle,
                    "source_duration_frames": int(source_duration),
                    "offset_frames": offset_frames,
                    "available_duration_frames": available_duration,
                },
            )
        durations.append(available_duration)
    return min(durations) if durations else None


def _select_video_source_offset_fallback_angle(
    *,
    angle_map: dict[str, str],
    offsets: dict[str, int],
    effective_settings: dict[str, Any],
) -> str | None:
    explicit = str(
        effective_settings.get("video_source_offset_fallback_angle")
        or effective_settings.get("default_preroll_angle")
        or ""
    ).strip()
    if explicit:
        if explicit not in angle_map:
            raise ValidationError(
                "video_source_offset_fallback_angle must reference a known multicam angle.",
                details={"angle": explicit, "known_angles": sorted(angle_map.keys())},
            )
        if int(offsets.get(explicit, 0)) < 0:
            raise ValidationError(
                "video_source_offset_fallback_angle cannot itself have a negative source offset.",
                details={"angle": explicit, "offset_frames": offsets.get(explicit, 0)},
            )
        return explicit
    zero_or_positive = [angle for angle in angle_map if int(offsets.get(angle, 0)) >= 0]
    if not zero_or_positive:
        return None
    default_angle = str(effective_settings.get("default_video_angle") or "").strip()
    if default_angle in zero_or_positive:
        return default_angle
    for preferred in ("W", "wide", "Wide"):
        if preferred in zero_or_positive:
            return preferred
    return zero_or_positive[0]


def _sources_to_reference_audio_map(sources: list[MulticamSource], angle_order: list[str]) -> dict[str, str]:
    by_angle = {
        source.angle: str(source.source_path or source.clip_name)
        for source in sources
    }
    return {angle: by_angle[angle] for angle in angle_order}


def _sources_to_angle_spec(sources: list[MulticamSource], angle_order: list[str]) -> str:
    angle_map = _sources_to_angle_map(sources, angle_order)
    return ",".join(f"{angle}={angle_map[angle]}" for angle in angle_order)


def _sources_to_source_specs(sources: list[MulticamSource], angle_order: list[str]) -> list[dict[str, Any]]:
    return [
        asdict(source)
        for angle in angle_order
        for source in sources
        if source.angle == angle
    ]


def _source_start_offsets_for_angle_order(
    effective_settings: dict[str, Any],
    sources: list[MulticamSource],
) -> list[int] | None:
    offsets = effective_settings.get("video_source_offsets_frames")
    if not isinstance(offsets, dict) or not offsets:
        return None
    return [
        int(offsets.get(source.angle, 0))
        for angle in list(effective_settings["angle_order"])
        for source in sources
        if source.angle == angle
    ]


def _support_tier_for_sources(
    sources: list[MulticamSource],
    *,
    source_layout: str | None = None,
) -> dict[str, Any]:
    unique_angle_count = len({source.angle for source in sources})
    inferred_source_layout = source_layout or (
        "sparse"
        if any(source.record_start_frame is not None for source in sources)
        else "contiguous"
    )
    return support_tier_for_angle_count(
        unique_angle_count,
        has_multi_clip_angle=len(sources) > unique_angle_count,
        source_layout=inferred_source_layout,
    )


def _support_tier_for_plan(plan: dict[str, Any]) -> dict[str, Any]:
    raw_sources = plan.get("sources")
    if isinstance(raw_sources, list) and raw_sources:
        try:
            return _support_tier_for_sources(_parse_sources(raw_sources))
        except ValidationError:
            pass

    multicam_settings = plan.get("multicam_settings")
    if isinstance(multicam_settings, dict):
        angle_order = multicam_settings.get("angle_order")
        if isinstance(angle_order, list) and angle_order:
            return support_tier_for_angle_count(len(angle_order))

    angle_order = plan.get("angle_order")
    if isinstance(angle_order, list) and angle_order:
        return support_tier_for_angle_count(len(angle_order))

    unique_angles = {
        str(segment.get("angle") or "").strip()
        for segment in list(plan.get("segments") or [])
        if isinstance(segment, dict) and str(segment.get("angle") or "").strip()
    }
    return support_tier_for_angle_count(len(unique_angles))


def _normalize_program_audio_settings(raw: Any) -> dict[str, Any] | None:
    return native_multicam_db.normalize_multicam_audio_replacement_settings(raw)


def _parse_ffprobe_rate(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text or text in {"0/0", "N/A"}:
        return None
    if "/" in text:
        numerator, denominator = text.split("/", 1)
        try:
            denominator_value = float(denominator)
            if denominator_value == 0:
                return None
            return float(numerator) / denominator_value
        except (TypeError, ValueError, ZeroDivisionError):
            return None
    try:
        parsed = float(text)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _probe_video_duration_ms(source_path: str | None) -> int | None:
    if not source_path:
        return None
    expanded = os.path.abspath(os.path.expanduser(str(source_path)))
    if not os.path.isfile(expanded):
        return None
    try:
        result = _run_ffprobe(
            [
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                "-select_streams",
                "v:0",
                expanded,
            ],
            check=True,
        )
        payload = json.loads(result.stdout or "{}")
    except Exception:
        return None

    streams = list(payload.get("streams") or [])
    stream = streams[0] if streams and isinstance(streams[0], dict) else {}
    for raw_duration in (stream.get("duration"),):
        try:
            seconds = float(raw_duration)
        except (TypeError, ValueError):
            continue
        if seconds > 0:
            return int(round(seconds * 1000.0))

    try:
        frame_count = int(stream.get("nb_frames") or 0)
    except (TypeError, ValueError):
        frame_count = 0
    rate = _parse_ffprobe_rate(stream.get("avg_frame_rate")) or _parse_ffprobe_rate(stream.get("r_frame_rate"))
    if frame_count > 0 and rate and rate > 0:
        return int(round((frame_count / rate) * 1000.0))

    format_info = payload.get("format") if isinstance(payload.get("format"), dict) else {}
    try:
        seconds = float(format_info.get("duration"))
    except (TypeError, ValueError):
        seconds = 0.0
    if seconds > 0:
        return int(round(seconds * 1000.0))
    return None


def _positive_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _settings_frame_rate(settings: Any) -> float | None:
    if not isinstance(settings, dict):
        return None
    for key in ("timelineFrameRate", "timelinePlaybackFrameRate"):
        number = _positive_float(settings.get(key))
        if number is not None:
            return number
    return None


def _resolve_planning_fps(conn) -> float:
    timeline = getattr(conn, "timeline", None)
    get_timeline_setting = getattr(timeline, "GetSetting", None)
    if callable(get_timeline_setting):
        try:
            fps = _settings_frame_rate(get_timeline_setting())
        except Exception:
            fps = None
        if fps is not None:
            return fps
        try:
            fps = _positive_float(get_timeline_setting("timelineFrameRate"))
        except Exception:
            fps = None
        if fps is not None:
            return fps

    project = getattr(conn, "project", None)
    get_project_setting = getattr(project, "GetSetting", None)
    if callable(get_project_setting):
        try:
            fps = _settings_frame_rate(get_project_setting())
        except Exception:
            fps = None
        if fps is not None:
            return fps
        try:
            fps = _positive_float(get_project_setting("timelineFrameRate"))
        except Exception:
            fps = None
        if fps is not None:
            return fps

    return _positive_float(getattr(conn, "fps", None)) or 24.0


def normalize_switch_scope(value: Any = "linked") -> str:
    normalized = str(value or "linked").strip().lower().replace("_", "-")
    aliases = {
        "both": "linked",
        "all": "linked",
        "video-only": "video",
        "audio-only": "audio",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"linked", "video", "audio"}:
        raise ValidationError(
            "Multicam switch scope must be linked, video, or audio.",
            details={"switch_scope": value, "supported": ["linked", "video", "audio"]},
        )
    return normalized


def _program_audio_offsets(plan: dict[str, Any], program_audio: dict[str, Any]) -> dict[str, int]:
    offsets: dict[str, int] = {}
    audio_activity = plan.get("audio_activity") if isinstance(plan, dict) else None
    if isinstance(audio_activity, dict):
        for source in list(audio_activity.get("audio_sources") or []):
            if isinstance(source, dict) and source.get("id") is not None:
                offsets[str(source["id"])] = int(source.get("offset_frames") or 0)
    offsets.update({str(key): int(value) for key, value in dict(program_audio.get("offsets") or {}).items()})
    return offsets


def _replace_program_audio_inside_multicam(conn, *, multicam_name: str, plan: dict[str, Any]) -> dict[str, Any] | None:
    program_audio = plan.get("program_audio")
    if not isinstance(program_audio, dict):
        return None
    return native_multicam_db.replace_multicam_audio(
        conn,
        multicam_name=multicam_name,
        audio_sources=list(program_audio.get("sources") or []),
        audio_angle_map=dict(program_audio.get("audio_angle_map") or {}),
        angle_order=list(program_audio.get("angle_order") or plan.get("angle_order") or []),
        offsets=_program_audio_offsets(plan, program_audio),
        unmapped_audio=str(program_audio.get("unmapped_audio") or "remove"),
        empty_angle_indices=list(program_audio.get("empty_angle_indices") or []),
    )


def _infer_min_source_duration_ms(
    conn,
    *,
    sources: list[MulticamSource],
    angle_map: dict[str, str],
    angle_order: list[str],
    video_source_offsets_frames: dict[str, int] | None = None,
    planning_fps: float | None = None,
) -> int | None:
    durations_ms: list[int] = []
    offset_fps = float(planning_fps or _resolve_planning_fps(conn) or 24.0)
    for source in sources:
        angle_label = str(source.angle or "").strip()
        if not angle_label:
            continue
        offset_frames = int((video_source_offsets_frames or {}).get(angle_label, 0))
        offset_ms = int(round(offset_frames * 1000.0 / offset_fps)) if offset_fps > 0 else 0
        probed_duration_ms = _probe_video_duration_ms(source.source_path)
        if probed_duration_ms is not None and probed_duration_ms > 0:
            durations_ms.append(max(0, int(probed_duration_ms) - offset_ms))
            continue
        if source.source_duration_frames is not None and offset_fps > 0:
            duration_ms = int(round(int(source.source_duration_frames) * 1000.0 / offset_fps))
            durations_ms.append(max(0, duration_ms - offset_ms))

    try:
        resolved_angles = podcast_multicam._resolve_angle_source_specs(
            conn,
            _sources_to_source_specs(sources, angle_order),
            angle_map=angle_map,
        )
    except Exception:
        return min(durations_ms) if durations_ms else None
    for angle in resolved_angles:
        angle_label = str(getattr(angle, "label", "") or "").strip()
        fps = float(getattr(angle, "fps", None) or getattr(conn, "fps", 24.0) or 24.0)
        offset_frames = int((video_source_offsets_frames or {}).get(angle_label, 0))
        offset_ms = int(round(offset_frames * 1000.0 / offset_fps)) if offset_fps > 0 else 0
        probed_duration_ms = _probe_video_duration_ms(getattr(angle, "source_path", None))
        if probed_duration_ms is not None and probed_duration_ms > 0:
            durations_ms.append(max(0, int(probed_duration_ms) - offset_ms))
            continue
        duration_frames = getattr(angle, "duration_frames", None)
        if duration_frames is None or fps <= 0:
            continue
        duration_ms = int(round(int(duration_frames) * 1000.0 / fps))
        durations_ms.append(max(0, duration_ms - offset_ms))
    return min(durations_ms) if durations_ms else None


def _normalize_explicit_segments(
    conn,
    *,
    raw_segments: Any,
    angle_map: dict[str, str],
) -> dict[str, Any]:
    segments: list[dict[str, Any]] = []
    for index, raw in enumerate(list(raw_segments or [])):
        if not isinstance(raw, dict):
            raise ValidationError("segments entries must be objects.", details={"segment_index": index})
        angle = str(raw.get("angle") or "").strip()
        if angle not in angle_map:
            raise ValidationError(
                "Segment angle is not present in the multicam source set.",
                details={"segment_index": index, "angle": angle, "angles": sorted(angle_map.keys())},
            )
        start_ms = raw.get("start_ms")
        end_ms = raw.get("end_ms")
        if start_ms is None or end_ms is None:
            raise ValidationError(
                "Explicit multicam segments currently require start_ms and end_ms.",
                details={"segment_index": index, "segment": raw},
            )
        start_ms_int = int(start_ms)
        end_ms_int = int(end_ms)
        if end_ms_int <= start_ms_int:
            raise ValidationError(
                "Segment end_ms must be greater than start_ms.",
                details={"segment_index": index, "start_ms": start_ms_int, "end_ms": end_ms_int},
            )
        start_frame = conn.start_frame + int(round(start_ms_int * conn.fps / 1000.0))
        end_frame = conn.start_frame + int(round(end_ms_int * conn.fps / 1000.0))
        if end_frame <= start_frame:
            raise ValidationError(
                "Explicit segment collapsed to zero duration after frame rounding.",
                details={"segment_index": index, "start_frame": start_frame, "end_frame": end_frame},
            )
        output_start_ms = raw.get("output_start_ms", raw.get("record_start_ms", start_ms_int))
        output_end_ms = raw.get("output_end_ms", raw.get("record_end_ms", end_ms_int))
        output_start_frame = conn.start_frame + int(round(int(output_start_ms) * conn.fps / 1000.0))
        output_end_frame = conn.start_frame + int(round(int(output_end_ms) * conn.fps / 1000.0))
        if output_end_frame <= output_start_frame:
            raise ValidationError(
                "Explicit segment output window collapsed to zero duration after frame rounding.",
                details={
                    "segment_index": index,
                    "output_start_frame": output_start_frame,
                    "output_end_frame": output_end_frame,
                },
            )
        text = str(raw.get("text") or raw.get("reason") or "").strip()
        segment = podcast_multicam.SwitchSegment(
            speaker_id=str(raw.get("speaker_id") or f"segment_{index}"),
            angle=angle,
            clip_name=angle_map[angle],
            start_frame=start_frame,
            end_frame=end_frame,
            start_tc=podcast_multicam.frames_to_timecode(start_frame, conn.fps),
            end_tc=podcast_multicam.frames_to_timecode(end_frame, conn.fps),
            text=text,
            record_start_frame=output_start_frame,
            record_end_frame=output_end_frame,
        )
        segments.append(asdict(segment))
    if not segments:
        raise ValidationError("Explicit multicam job must include at least one segment.")
    return {
        "segment_count": len(segments),
        "segments": segments,
        "angle_order": list(angle_map.keys()),
    }


def _apply_speaker_rule_exceptions(
    transcript_segments: list[dict[str, Any]],
    *,
    filler_tokens: set[str],
    reaction_hold_ms: int,
) -> list[dict[str, Any]]:
    if not filler_tokens and reaction_hold_ms <= 0:
        return transcript_segments

    normalized: list[dict[str, Any]] = []
    previous_speaker_id: str | None = None
    for raw in transcript_segments:
        row = dict(raw)
        text = str(row.get("text") or "").strip().lower()
        duration_ms = int(row.get("end_ms") or 0) - int(row.get("start_ms") or 0)
        if previous_speaker_id and (
            (text and text in filler_tokens)
            or (reaction_hold_ms > 0 and duration_ms <= reaction_hold_ms)
        ):
            row["speaker_id"] = previous_speaker_id
        previous_speaker_id = str(row.get("speaker_id") or previous_speaker_id or "")
        normalized.append(row)
    return normalized


def _apply_force_segments(
    plan: dict[str, Any],
    *,
    conn,
    angle_map: dict[str, str],
    force_segments: list[dict[str, Any]],
) -> dict[str, Any]:
    if not force_segments:
        return plan

    existing = [
        podcast_multicam.SwitchSegment(**segment)
        for segment in list(plan.get("segments") or [])
    ]
    if not existing:
        return plan

    boundaries: set[int] = set()
    for segment in existing:
        boundaries.add(int(segment.start_frame))
        boundaries.add(int(segment.end_frame))
    normalized_forces: list[dict[str, Any]] = []
    for raw in force_segments:
        if not isinstance(raw, dict):
            continue
        angle = str(raw.get("angle") or "").strip()
        if angle not in angle_map:
            raise ValidationError(
                "force_segments angle is not present in the multicam source set.",
                details={"force_segment": raw, "angles": sorted(angle_map.keys())},
            )
        start_ms = int(raw.get("start_ms") or 0)
        end_ms = int(raw.get("end_ms") or 0)
        if end_ms <= start_ms:
            raise ValidationError("force_segments require end_ms > start_ms.", details={"force_segment": raw})
        start_frame = conn.start_frame + int(round(start_ms * conn.fps / 1000.0))
        end_frame = conn.start_frame + int(round(end_ms * conn.fps / 1000.0))
        boundaries.add(start_frame)
        boundaries.add(end_frame)
        normalized_forces.append(
            {
                "angle": angle,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "text": str(raw.get("text") or raw.get("reason") or "").strip(),
            }
        )

    ordered = sorted(boundaries)
    rebuilt: list[podcast_multicam.SwitchSegment] = []
    for start_frame, end_frame in zip(ordered, ordered[1:]):
        if end_frame <= start_frame:
            continue
        source = next(
            (segment for segment in existing if int(segment.start_frame) <= start_frame and int(segment.end_frame) >= end_frame),
            None,
        )
        if source is None:
            continue
        forced = next(
            (item for item in normalized_forces if int(item["start_frame"]) <= start_frame and int(item["end_frame"]) >= end_frame),
            None,
        )
        angle = forced["angle"] if forced else source.angle
        text = forced["text"] if forced and forced["text"] else source.text
        rebuilt.append(
            podcast_multicam.SwitchSegment(
                speaker_id=source.speaker_id,
                angle=angle,
                clip_name=angle_map[angle],
                start_frame=start_frame,
                end_frame=end_frame,
                start_tc=podcast_multicam.frames_to_timecode(start_frame, conn.fps),
                end_tc=podcast_multicam.frames_to_timecode(end_frame, conn.fps),
                text=text,
            )
        )

    collapsed: list[podcast_multicam.SwitchSegment] = []
    for segment in rebuilt:
        if (
            collapsed
            and collapsed[-1].angle == segment.angle
            and int(collapsed[-1].end_frame) == int(segment.start_frame)
        ):
            previous = collapsed[-1]
            collapsed[-1] = podcast_multicam.SwitchSegment(
                speaker_id=previous.speaker_id,
                angle=previous.angle,
                clip_name=previous.clip_name,
                start_frame=previous.start_frame,
                end_frame=segment.end_frame,
                start_tc=previous.start_tc,
                end_tc=segment.end_tc,
                text=" ".join(part for part in (previous.text, segment.text) if part).strip(),
            )
            continue
        collapsed.append(segment)

    if not collapsed:
        raise ValidationError("Rule program overrides produced no valid multicam segments.")
    return {
        **plan,
        "segment_count": len(collapsed),
        "segments": [asdict(item) for item in collapsed],
    }


def _compile_speaker_transcript_rule_program(
    conn,
    *,
    job: dict[str, Any],
    angle_map: dict[str, str],
    effective_settings: dict[str, Any],
    rule_program: dict[str, Any],
    kind: str,
) -> dict[str, Any]:
    transcript_path = str(rule_program.get("transcript_path") or job.get("transcript_path") or "").strip()
    if not transcript_path:
        raise ValidationError("speaker_transcript_v1 requires transcript_path.")

    transcript = podcast_multicam.normalize_scribe_v2_transcript(transcript_path)
    speaker_map_raw = rule_program.get("speaker_map") or job.get("speaker_map") or {}
    if isinstance(speaker_map_raw, str):
        speaker_map = podcast_multicam.parse_speaker_mapping(speaker_map_raw)
    elif isinstance(speaker_map_raw, dict):
        speaker_map = {str(key): str(value) for key, value in speaker_map_raw.items()}
    else:
        raise ValidationError("speaker_map must be an object or speaker=angle string.", details={"speaker_map": speaker_map_raw})

    if not speaker_map:
        inference = podcast_multicam.infer_speaker_camera_mapping(
            segments=transcript["segments"],
            angle_map=angle_map,
        )
        if inference.get("needs_clarification"):
            raise ValidationError(
                "Speaker-to-camera mapping is ambiguous. Ask a clarification before running the multicam job.",
                details={
                    "candidate_mappings": inference.get("candidate_mappings", []),
                    "speakers": transcript.get("speakers", []),
                    "angles": angle_map,
                },
            )
        speaker_map = dict(inference["mapping"])

    filler_tokens = {
        str(token).strip().lower()
        for token in list(rule_program.get("filler_tokens") or [])
        if str(token).strip()
    }
    transcript_segments = _apply_speaker_rule_exceptions(
        list(transcript["segments"]),
        filler_tokens=filler_tokens,
        reaction_hold_ms=int(effective_settings["reaction_hold_ms"]),
    )

    plan = podcast_multicam.build_switch_plan(
        conn=conn,
        transcript_segments=transcript_segments,
        angle_map=angle_map,
        speaker_map=speaker_map,
        min_shot_ms=int(effective_settings["min_shot_ms"]),
        merge_gap_ms=int(effective_settings["merge_gap_ms"]),
    )
    force_segments = list(rule_program.get("force_segments") or [])
    plan = _apply_force_segments(plan, conn=conn, angle_map=angle_map, force_segments=force_segments)
    plan["rule_program"] = {
        "kind": kind,
        "speaker_map": speaker_map,
        "transcript_path": transcript_path,
        "filler_tokens": sorted(filler_tokens),
        "force_segments": force_segments,
    }
    plan["transcript"] = transcript
    return plan


def _compile_audio_activity_rule_program(
    conn,
    *,
    job: dict[str, Any],
    sources: list[MulticamSource],
    angle_map: dict[str, str],
    effective_settings: dict[str, Any],
    rule_program: dict[str, Any],
    kind: str,
) -> dict[str, Any]:
    audio_sources = rule_program.get("audio_sources") or job.get("audio_sources")
    audio_angle_map = rule_program.get("audio_angle_map") or job.get("audio_angle_map") or {}
    audio_targets = rule_program.get("audio_targets") or job.get("audio_targets") or {}
    audio_sync = rule_program.get("audio_sync") or job.get("audio_sync") or {"mode": "prealigned"}
    switching = rule_program.get("switching") or job.get("switching") or {}
    overlap = rule_program.get("overlap") or job.get("overlap") or {}
    if kind == "smart_switch_v1":
        smart_settings = dict(rule_program.get("smart_switch") or job.get("smart_switch") or {})
        if str(smart_settings.get("wide_angle_mode") or "automatic").strip().lower().replace("-", "_") == "automatic":
            smart_audio_angle_map = (
                podcast_audio_activity.parse_audio_angle_map(audio_angle_map)
                if isinstance(audio_angle_map, str)
                else {str(key): str(value) for key, value in dict(audio_angle_map or {}).items()}
            )
            detection = multicam_smart_switch._automatic_wide_angle(
                angle_map=angle_map,
                angle_order=list(effective_settings["angle_order"]),
                angle_names=dict(effective_settings.get("angle_names") or {}),
                sources=[asdict(source) for source in sources],
                audio_angle_map=smart_audio_angle_map,
            )
            smart_settings["wide_angle"] = detection["angle"]
        wide_angle = str(smart_settings.get("wide_angle") or "").strip()
        overlap = {**dict(overlap or {}), "policy": "wide", **({"angle": wide_angle} if wide_angle else {})}
        rule_program = {**rule_program, "smart_switch": smart_settings}
    allow_unresolved = bool(rule_program.get("allow_unresolved_targets") or job.get("allow_unresolved_targets"))
    planning_fps = _resolve_planning_fps(conn)
    max_timeline_ms = _infer_min_source_duration_ms(
        conn,
        sources=sources,
        angle_map=angle_map,
        angle_order=effective_settings["angle_order"],
        video_source_offsets_frames=effective_settings.get("video_source_offsets_frames"),
        planning_fps=planning_fps,
    )
    analysis = podcast_audio_activity.build_audio_activity_plan(
        audio_sources=list(audio_sources or []),
        audio_angle_map=audio_angle_map or {},
        audio_targets=audio_targets or {},
        audio_sync=audio_sync or {},
        switching=dict(switching or {}),
        overlap=dict(overlap or {}),
        angle_map=angle_map,
        reference_audio_by_angle=_sources_to_reference_audio_map(sources, effective_settings["angle_order"]),
        max_timeline_ms=max_timeline_ms,
        fps=planning_fps,
    )
    if kind == "smart_switch_v1":
        smart_switch_settings = dict(rule_program.get("smart_switch") or job.get("smart_switch") or {})
        analysis = multicam_smart_switch.apply_smart_switch_policy(
            analysis,
            smart_switch=smart_switch_settings,
            angle_map=angle_map,
            angle_order=list(effective_settings["angle_order"]),
            angle_names=dict(effective_settings.get("angle_names") or {}),
            sources=[asdict(source) for source in sources],
            audio_angle_map=dict(analysis.get("audio_angle_map") or {}),
        )
    unresolved = list(analysis.get("unresolved_segments") or [])
    if unresolved and not allow_unresolved:
        raise ValidationError(
            "Audio activity plan contains segments that require an agent-selected angle.",
            details={
                "reason": "unresolved_audio_activity_targets",
                "unresolved_segments": unresolved,
                "next_steps": [
                    "Run multicam switch with --plan-only to inspect candidate angles.",
                    "Provide audio_angle_map for direct audio-source to angle mapping.",
                    "Rewrite the plan as explicit segments after choosing angles from audio_targets.",
                ],
            },
        )

    segments: list[dict[str, Any]] = []
    for index, raw in enumerate(list(analysis.get("segments") or [])):
        angle = str(raw.get("angle") or "").strip()
        if angle not in angle_map:
            raise ValidationError(
                "Audio activity segment points to an unknown multicam angle.",
                details={"segment_index": index, "angle": angle, "angles": sorted(angle_map.keys())},
            )
        start_ms = int(raw.get("start_ms") or 0)
        end_ms = int(raw.get("end_ms") or 0)
        if end_ms <= start_ms:
            continue
        start_frame = conn.start_frame + int(round(start_ms * planning_fps / 1000.0))
        end_frame = conn.start_frame + int(round(end_ms * planning_fps / 1000.0))
        if end_frame <= start_frame:
            continue
        segment = podcast_multicam.SwitchSegment(
            speaker_id="+".join(str(item) for item in list(raw.get("audio_source_ids") or [])) or f"audio_activity_{index}",
            angle=angle,
            clip_name=angle_map[angle],
            start_frame=start_frame,
            end_frame=end_frame,
            start_tc=podcast_multicam.frames_to_timecode(start_frame, planning_fps),
            end_tc=podcast_multicam.frames_to_timecode(end_frame, planning_fps),
            text=str(raw.get("reason") or ""),
            record_start_frame=start_frame,
            record_end_frame=end_frame,
        )
        row = asdict(segment)
        row["audio_activity"] = {
            key: value
            for key, value in raw.items()
            if key not in {"start_ms", "end_ms", "angle"}
        }
        row["start_ms"] = start_ms
        row["end_ms"] = end_ms
        segments.append(row)

    if not segments and not allow_unresolved:
        raise ValidationError(
            "Audio activity analysis did not produce any resolved multicam switch segments.",
            details={"analysis": analysis},
        )
    result = {
        "segment_count": len(segments),
        "segments": segments,
        "angle_order": list(angle_map.keys()),
        "rule_program": {
            "kind": kind,
            "audio_source_count": len(analysis.get("audio_sources") or []),
            "allow_unresolved_targets": allow_unresolved,
            **({"smart_switch": dict(analysis.get("smart_switch") or {})} if kind == "smart_switch_v1" else {}),
        },
        "audio_activity": analysis,
    }
    for key in ("audio_instructions", "audio_ranges", "audio_batch_plan"):
        if key in analysis:
            result[key] = analysis[key]
    return result


def _compile_rule_program(
    conn,
    *,
    job: dict[str, Any],
    sources: list[MulticamSource],
    angle_map: dict[str, str],
    effective_settings: dict[str, Any],
) -> dict[str, Any]:
    rule_program = job.get("rule_program")
    if not isinstance(rule_program, dict):
        raise ValidationError("Multicam job must provide either segments or rule_program.")
    kind = str(rule_program.get("kind") or "").strip()
    if kind == "speaker_transcript_v1":
        return _compile_speaker_transcript_rule_program(
            conn,
            job=job,
            angle_map=angle_map,
            effective_settings=effective_settings,
            rule_program=rule_program,
            kind=kind,
        )
    if kind in {"audio_activity_v1", "smart_switch_v1"}:
        return _compile_audio_activity_rule_program(
            conn,
            job=job,
            sources=sources,
            angle_map=angle_map,
            effective_settings=effective_settings,
            rule_program=rule_program,
            kind=kind,
        )
    raise ValidationError(
        "Unsupported multicam rule_program kind.",
        details={"kind": kind, "supported_kinds": ["speaker_transcript_v1", "audio_activity_v1", "smart_switch_v1"]},
    )


def build_multicam_job_plan(conn, job: dict[str, Any]) -> dict[str, Any]:
    job = _job_with_resolved_creation_metadata(conn, job)
    sources = _parse_sources(job.get("sources"))
    effective_settings = _normalize_effective_settings(job, sources=sources)
    angle_map = _sources_to_angle_map(sources, effective_settings["angle_order"])
    planning_fps = _resolve_planning_fps(conn)
    if job.get("segments") is not None:
        plan = _normalize_explicit_segments(conn, raw_segments=job.get("segments"), angle_map=angle_map)
    else:
        plan = _compile_rule_program(conn, job=job, sources=sources, angle_map=angle_map, effective_settings=effective_settings)
    _apply_video_source_container_offsets_to_plan(
        plan,
        angle_map=angle_map,
        effective_settings=effective_settings,
        sources=sources,
        planning_fps=planning_fps,
        timeline_start_frame=int(getattr(conn, "start_frame", 0) or 0),
    )
    plan["sources"] = [asdict(source) for source in sources]
    plan["selection_policy_result"] = job.get("selection_policy_result") or {}
    plan_multicam_settings = dict(effective_settings)
    if effective_settings["audio_mode"] == "reference_audio":
        plan_multicam_settings["reference_audio_clip_name"] = angle_map[
            effective_settings["default_audio_angle"]
        ]
    plan["multicam_settings"] = plan_multicam_settings
    plan["timeline_settings"] = {
        "timeline_name": effective_settings["timeline_name"],
        "replace_active_timeline": bool(job.get("timeline_settings", {}).get("replace_active_timeline", False))
        if isinstance(job.get("timeline_settings"), dict)
        else False,
    }
    plan["verification_requirements"] = job.get("verification_requirements") or {}
    plan["support_tier"] = _support_tier_for_sources(
        sources,
        source_layout=effective_settings["source_layout"],
    )
    program_audio = _normalize_program_audio_settings(job.get("program_audio"))
    if program_audio is not None:
        plan["program_audio"] = program_audio
    return plan


def multicam_create(conn, *, job: dict[str, Any], cleanup_stale_targets: bool = False) -> dict[str, Any]:
    job = _job_with_resolved_creation_metadata(conn, job)
    sources = _parse_sources(job.get("sources"))
    effective_settings = _normalize_effective_settings(job, sources=sources)
    support_tier = _support_tier_for_sources(sources, source_layout=effective_settings["source_layout"])
    source_groups = _split_sources_at_global_gaps(sources) if effective_settings["split_at_gaps"] else [sources]
    split_results: list[dict[str, Any]] = []
    for group_index, group_sources in enumerate(source_groups, start=1):
        group_angle_order = [angle for angle in effective_settings["angle_order"] if any(source.angle == angle for source in group_sources)]
        group_name = (
            f"{effective_settings['multicam_name']} {group_index}"
            if len(source_groups) > 1
            else effective_settings["multicam_name"]
        )
        group_result = podcast_multicam.native_multicam_create(
            conn,
            timeline_name=effective_settings["timeline_name"],
            multicam_name=group_name,
            angles=_sources_to_angle_spec(group_sources, group_angle_order),
            source_specs=_sources_to_source_specs(group_sources, group_angle_order),
            angle_names={angle: effective_settings["angle_names"][angle] for angle in group_angle_order},
            source_layout=effective_settings["source_layout"],
            sync=effective_settings["sync_mode"],
            sync_channel=effective_settings["sync_channel"],
            marker_name=effective_settings["marker_name"],
            full_clip_extents=effective_settings["full_clip_extents"],
            audio_mode=effective_settings["audio_mode"],
            reference_audio_angle=(
                effective_settings["default_audio_angle"]
                if effective_settings["default_audio_angle"] in group_angle_order
                else group_angle_order[0]
            ),
            start_timecode=effective_settings["start_timecode"],
            reference_source=effective_settings["reference_source"],
            source_start_offsets_frames=_source_start_offsets_for_angle_order(
                {**effective_settings, "angle_order": group_angle_order},
                group_sources,
            ),
            source_start_offsets_mode="timeline_offsets",
            materialize_timeline=False,
            cleanup_stale_targets=cleanup_stale_targets,
            preferred_duration_frames=(
                None if len(source_groups) > 1 else effective_settings.get("timeline_duration_frames")
            ),
        )
        group_result["split_group"] = group_index
        split_results.append(group_result)
    result = dict(split_results[0])
    if effective_settings["split_at_gaps"]:
        result["split_at_gaps"] = {
            "status": "verified",
            "multicam_clip_count": len(split_results),
            "multicam_clips": [
                {
                    "name": item.get("multicam_name"),
                    "media_id": item.get("multicam_media_id"),
                    "sequence_id": item.get("multicam_sequence_id"),
                    "source_clip_count": item.get("source_clip_count"),
                    "verification": item.get("verification"),
                }
                for item in split_results
            ],
            "route": "CutAgent sound-sync recording groups -> independent native Project.db multicam sequences",
        }
    if effective_settings["move_source_clips_to_original_bin"]:
        result["original_clips_move"] = _move_sources_to_original_clips_bin(conn, sources)
    result["effective_settings"] = effective_settings
    result["sources"] = [asdict(source) for source in sources]
    result["selection_policy_result"] = job.get("selection_policy_result") or {}
    result["support_tier"] = support_tier
    return result


def _multicam_create_and_materialize_timeline(
    conn,
    *,
    job: dict[str, Any],
    cleanup_stale_targets: bool = False,
) -> dict[str, Any]:
    job = _job_with_resolved_creation_metadata(conn, job)
    sources = _parse_sources(job.get("sources"))
    effective_settings = _normalize_effective_settings(job, sources=sources)
    support_tier = _support_tier_for_sources(sources, source_layout=effective_settings["source_layout"])
    angle_spec = _sources_to_angle_spec(sources, effective_settings["angle_order"])
    result = podcast_multicam.native_multicam_create(
        conn,
        timeline_name=effective_settings["timeline_name"],
        multicam_name=effective_settings["multicam_name"],
        angles=angle_spec,
        source_specs=_sources_to_source_specs(sources, effective_settings["angle_order"]),
        angle_names=effective_settings["angle_names"],
        source_layout=effective_settings["source_layout"],
        sync=effective_settings["sync_mode"],
        sync_channel=effective_settings["sync_channel"],
        marker_name=effective_settings["marker_name"],
        full_clip_extents=effective_settings["full_clip_extents"],
        audio_mode=effective_settings["audio_mode"],
        reference_audio_angle=effective_settings["default_audio_angle"],
        start_timecode=effective_settings["start_timecode"],
        reference_source=effective_settings["reference_source"],
        source_start_offsets_frames=_source_start_offsets_for_angle_order(effective_settings, sources),
        source_start_offsets_mode="timeline_offsets",
        materialize_timeline=True,
        cleanup_stale_targets=cleanup_stale_targets,
        preferred_duration_frames=effective_settings.get("timeline_duration_frames"),
    )
    if effective_settings["move_source_clips_to_original_bin"]:
        result["original_clips_move"] = _move_sources_to_original_clips_bin(conn, sources)
    result["effective_settings"] = effective_settings
    result["sources"] = [asdict(source) for source in sources]
    result["selection_policy_result"] = job.get("selection_policy_result") or {}
    result["support_tier"] = support_tier
    return result


def multicam_switch(
    conn,
    *,
    multicam_name: str,
    plan: dict[str, Any],
    timeline_name: str | None = None,
    replace_active_timeline: bool = True,
    switch_scope: str = "linked",
    multicam_media_id: str | None = None,
    timeline_native_id: str | None = None,
) -> dict[str, Any]:
    switch_scope = normalize_switch_scope(switch_scope)
    support_tier = _support_tier_for_plan(plan)
    timeline_target = timeline_name or (getattr(conn.timeline, "GetName", lambda: None)() or "")
    timeline_step, verification_checks = podcast_multicam._materialize_timeline_from_switch_plan(
        conn,
        timeline_name=timeline_target,
        multicam_name=multicam_name,
        plan=plan,
        replace_active_timeline=replace_active_timeline,
        switch_scope=switch_scope,
        multicam_media_id=multicam_media_id,
        timeline_native_id=timeline_native_id,
    )
    result = {
        "multicam_name": multicam_name,
        "timeline_name": timeline_step["timeline_name"],
        "engine": "db_workaround",
        "switch_scope": switch_scope,
        "video_changed": bool(timeline_step.get("video_changed", switch_scope in {"linked", "video"})),
        "audio_changed": bool(timeline_step.get("audio_changed", switch_scope in {"linked", "audio"})),
        "segments_applied": timeline_step["segment_count"],
        "segment_write": timeline_step["segment_write"],
        "selector_patch": timeline_step["selector_patch"],
        "timeline_start_restore": timeline_step.get("timeline_start_restore"),
        "support_tier": support_tier,
        "verification": {
            "status": "verified" if all(check.get("ok") for check in verification_checks) else "pending_manual",
            "checks": verification_checks,
        },
    }
    if switch_scope != "video":
        program_audio_result = _replace_program_audio_inside_multicam(
            conn,
            multicam_name=multicam_name,
            plan=plan,
        )
        if program_audio_result is not None:
            result["program_audio"] = program_audio_result
    return result


def timeline_create(conn, *, job: dict[str, Any], cleanup_stale_targets: bool = False) -> dict[str, Any]:
    job = _job_with_resolved_creation_metadata(conn, job)
    sources = _parse_sources(job.get("sources"))
    angle_count = len({source.angle for source in sources})
    if angle_count > 4:
        create_result = _multicam_create_and_materialize_timeline(
            conn,
            job=job,
            cleanup_stale_targets=cleanup_stale_targets,
        )
        effective_settings = create_result["effective_settings"]
        verification = create_result.get("verification") or {"status": "pending_manual", "checks": []}
        return {
            "multicam_name": effective_settings["multicam_name"],
            "timeline_name": effective_settings["timeline_name"],
            "create": create_result,
            "timeline_create": {
                "multicam_name": effective_settings["multicam_name"],
                "timeline_name": effective_settings["timeline_name"],
                "engine": "db_workaround",
                "route": "db_native_materialized_timeline",
                "segments_applied": 1,
                "selector_patch": {
                    "status": "not_required",
                    "reason": "single native multicam item materialized without DB selector rewrite",
                },
            },
            "support_tier": create_result["support_tier"],
            "verification": verification,
        }

    create_result = multicam_create(conn, job=job, cleanup_stale_targets=cleanup_stale_targets)
    effective_settings = create_result["effective_settings"]
    angle_map = _sources_to_angle_map(sources, effective_settings["angle_order"])
    default_angle = effective_settings["default_video_angle"]
    planning_fps = _resolve_planning_fps(conn)
    source_counts_by_angle = dict(effective_settings.get("source_counts_by_angle") or {})
    has_multi_clip_angle = any(int(count) > 1 for count in source_counts_by_angle.values())
    if has_multi_clip_angle:
        shifted_container_duration = create_result.get("multicam_duration_frames")
        if shifted_container_duration is not None:
            shifted_container_duration = int(shifted_container_duration)
        shifted_source_duration = None
    else:
        shifted_container_duration = _shifted_container_duration_frames(
            list(create_result.get("resolved_angles", []) or []),
            angle_order=effective_settings["angle_order"],
            video_source_offsets_frames=dict(effective_settings.get("video_source_offsets_frames") or {}),
        )
        shifted_source_duration = _shifted_source_duration_frames(
            sources,
            planning_fps=planning_fps,
            video_source_offsets_frames=dict(effective_settings.get("video_source_offsets_frames") or {}),
        )
    available_durations = [
        duration
        for duration in (
            shifted_container_duration,
            shifted_source_duration,
            effective_settings.get("timeline_duration_frames"),
        )
        if duration is not None
    ]
    if not available_durations:
        raise ValidationError(
            "Could not infer multicam duration for timeline_create.",
            details={
                "reason": "multicam_duration_unavailable",
                "source_counts_by_angle": source_counts_by_angle,
            },
        )
    shifted_container_duration = min(available_durations)
    end_frame = int(conn.start_frame) + shifted_container_duration
    default_segment = podcast_multicam.SwitchSegment(
        speaker_id="default",
        angle=default_angle,
        clip_name=angle_map[default_angle],
        start_frame=int(conn.start_frame),
        end_frame=end_frame,
        start_tc=podcast_multicam.frames_to_timecode(int(conn.start_frame), conn.fps),
        end_tc=podcast_multicam.frames_to_timecode(end_frame, conn.fps),
        text="default multicam placement",
    )
    plan = {
        "segment_count": 1,
        "segments": [asdict(default_segment)],
        "angle_order": effective_settings["angle_order"],
    }
    _apply_video_source_container_offsets_to_plan(
        plan,
        angle_map=angle_map,
        effective_settings=effective_settings,
        sources=sources,
        planning_fps=planning_fps,
        timeline_start_frame=int(getattr(conn, "start_frame", 0) or 0),
    )
    switch_result = multicam_switch(
        conn,
        multicam_name=effective_settings["multicam_name"],
        plan=plan,
        timeline_name=effective_settings["timeline_name"],
        replace_active_timeline=False,
    )
    return {
        "multicam_name": effective_settings["multicam_name"],
        "timeline_name": effective_settings["timeline_name"],
        "create": create_result,
        "timeline_create": switch_result,
        "support_tier": create_result["support_tier"],
        "verification": switch_result["verification"],
    }


def inspect_multicam(conn, *, multicam_name: str, timeline_name: str | None = None) -> dict[str, Any]:
    clip = media_pool.find_clip(conn, multicam_name)
    project_db_path = podcast_multicam._resolve_current_project_db_path(conn)
    try:
        binding_state = native_multicam_db.inspect_multicam_bindings(
            project_db_path,
            multicam_name=multicam_name,
        )
    except ValidationError as exc:
        if exc.details.get("reason") != "multicam_not_found":
            raise
        available_multicam_clips = native_multicam_db.list_multicam_binding_summaries(project_db_path)
        raise ValidationError(
            "Multicam clip not found.",
            details={
                "reason": "multicam_not_found",
                "multicam_name": multicam_name,
                "project_db_path": project_db_path,
                "available_multicam_clips": available_multicam_clips,
                "next_steps": [
                    "Run multicam inspect without --multicam-name to list inspectable multicam clips.",
                    "Create a native multicam clip with multicam create before inspecting it.",
                ],
            },
        ) from exc
    support_tier = support_tier_for_angle_count(int(binding_state["angle_count"] or 0))
    ui_manual_verdict = multicam_ui_verdicts.resolve_manual_multicam_ui_verdict(
        multicam_name=multicam_name,
        angle_count=int(binding_state["angle_count"] or 0),
    )
    if ui_manual_verdict["status"] == "ui_confirmed":
        runtime_scope = {
            "angle_count": int(binding_state["angle_count"] or 0),
            "tier": "manual_ui_confirmed",
            "label": "Manually confirmed in DaVinci Resolve UI",
            "create_supported": bool(support_tier["create_supported"]),
            "switch_contract_supported": bool(support_tier["switch_contract_supported"]),
            "create_shape_verified": True,
            "switch_shape_verified": True,
            "live_verified": True,
            "notes": list(ui_manual_verdict["notes"]),
        }
    elif ui_manual_verdict["status"] == "ui_rejected":
        runtime_scope = {
            "angle_count": int(binding_state["angle_count"] or 0),
            "tier": "manual_ui_rejected",
            "label": "Manually rejected in DaVinci Resolve UI",
            "create_supported": bool(support_tier["create_supported"]),
            "switch_contract_supported": bool(support_tier["switch_contract_supported"]),
            "create_shape_verified": False,
            "switch_shape_verified": False,
            "live_verified": False,
            "notes": list(ui_manual_verdict["notes"]),
        }
    elif bool(binding_state["binding_consistent"]):
        runtime_scope = {
            "angle_count": int(binding_state["angle_count"] or 0),
            "tier": "db_readback_consistent_pending_ui_confirmation",
            "label": "DB readback consistent; pending UI confirmation",
            "create_supported": bool(support_tier["create_supported"]),
            "switch_contract_supported": bool(support_tier["switch_contract_supported"]),
            "create_shape_verified": False,
            "switch_shape_verified": False,
            "live_verified": False,
            "notes": [
                "Project.db binding looks internally consistent for this multicam clip.",
                "DaVinci Resolve UI switching/selection is not assumed verified from DB readback alone.",
            ],
        }
    elif binding_state.get("audio_binding_mode") == "separate_audio_sources":
        runtime_scope = {
            "angle_count": int(binding_state["angle_count"] or 0),
            "tier": "db_readback_separate_audio_sources",
            "label": "DB readback shows separate internal multicam audio sources",
            "create_supported": bool(support_tier["create_supported"]),
            "switch_contract_supported": bool(support_tier["switch_contract_supported"]),
            "create_shape_verified": False,
            "switch_shape_verified": False,
            "live_verified": False,
            "notes": [
                "Internal audio items intentionally reference different media than the video angles.",
                "Use audio_source_mapping to verify isolated microphone replacement inside the multicam.",
            ],
        }
    else:
        runtime_scope = {
            "angle_count": int(binding_state["angle_count"] or 0),
            "tier": "db_readback_binding_mismatch_detected",
            "label": "DB readback mismatch detected",
            "create_supported": bool(support_tier["create_supported"]),
            "switch_contract_supported": bool(support_tier["switch_contract_supported"]),
            "create_shape_verified": False,
            "switch_shape_verified": False,
            "live_verified": False,
            "notes": [
                "Project.db readback shows binding mismatches for this multicam clip.",
            ],
        }
    active_timeline_name = timeline_name or (getattr(conn.timeline, "GetName", lambda: None)() or "")
    timeline_db = None
    if active_timeline_name:
        try:
            timeline_db = podcast_multicam._snapshot_timeline_multicam_segments_db(
                project_db_path,
                timeline_name=active_timeline_name,
                multicam_name=multicam_name,
            )
        except Exception:
            timeline_db = None
    video_items_by_angle: dict[int, list[dict[str, Any]]] = {}
    for item in binding_state["video_source_mapping"]:
        if item.get("clip_name"):
            video_items_by_angle.setdefault(int(item["angle_index"]), []).append(item)
    angle_order = []
    for angle_index, items in sorted(video_items_by_angle.items()):
        ordered_items = sorted(
            items,
            key=lambda item: (
                int(item.get("item_index") or 0),
                int(item.get("start_frame") or 0),
            ),
        )
        angle_order.append(
            {
                "clip_name": ordered_items[0]["clip_name"],
                "clip_names": [item["clip_name"] for item in ordered_items],
                "source_clip_count": len(ordered_items),
                "angle_index": angle_index,
                "ui_label": f"Angle {angle_index + 1}",
            }
        )
    source_mapping = {
        chr(65 + index): {
            "clip_name": item["clip_name"],
            "clip_names": item["clip_names"],
            "source_clip_count": item["source_clip_count"],
            "angle_index": item["angle_index"],
            "ui_label": item["ui_label"],
        }
        for index, item in enumerate(angle_order)
    }
    return {
        "multicam_name": multicam_name,
        "clip_name": clip.GetName() if hasattr(clip, "GetName") else multicam_name,
        "media_pool_clip_found": clip is not None,
        "project_db_path": project_db_path,
        "angle_count": int(binding_state["angle_count"] or 0),
        "source_clip_count": int(binding_state.get("source_clip_count") or len(binding_state["video_source_mapping"])),
        "source_item_representation": binding_state.get("source_item_representation", SOURCE_ITEM_REPRESENTATION),
        "source_clip_count_per_angle_limit": binding_state.get(
            "source_clip_count_per_angle_limit", SOURCE_CLIP_COUNT_PER_ANGLE_LIMIT
        ),
        "creates_flattened_media": bool(binding_state.get("creates_flattened_media", False)),
        "source_items_are_distinct": bool(binding_state.get("source_items_are_distinct", False)),
        "source_items_contiguous_by_angle": bool(binding_state.get("source_items_contiguous_by_angle", False)),
        "angles": list(binding_state.get("angles") or []),
        "angle_order": angle_order,
        "angle_labels": [item["ui_label"] for item in angle_order],
        "source_mapping": source_mapping,
        "video_source_mapping": binding_state["video_source_mapping"],
        "audio_source_mapping": binding_state["audio_source_mapping"],
        "audio_binding_mode": binding_state.get("audio_binding_mode"),
        "separate_audio_angle_count": binding_state.get("separate_audio_angle_count"),
        "empty_audio_angle_count": binding_state.get("empty_audio_angle_count"),
        "binding_consistent": bool(binding_state["binding_consistent"]),
        "binding_mismatches": list(binding_state["mismatches"]),
        "ui_manual_verdict": ui_manual_verdict,
        "create_shape_verified": bool(runtime_scope["create_shape_verified"]),
        "switch_shape_verified": bool(runtime_scope["switch_shape_verified"]),
        "live_verified_scope": runtime_scope,
        "support_tier": support_tier,
        "timeline_name": active_timeline_name or None,
        "timeline_db": timeline_db,
    }


def list_multicam_inspection_context(conn, *, timeline_name: str | None = None) -> dict[str, Any]:
    project_db_path = podcast_multicam._resolve_current_project_db_path(conn)
    available_multicam_clips = native_multicam_db.list_multicam_binding_summaries(project_db_path)
    active_timeline_name = timeline_name or (getattr(conn.timeline, "GetName", lambda: None)() or "")
    if available_multicam_clips:
        next_steps = [
            "Pass one candidate name with --multicam-name to inspect angle bindings.",
            "Use multicam create if you need to create a new native multicam clip.",
        ]
    else:
        next_steps = [
            "No native multicam clips were found in the current project database.",
            "Create one with multicam create, then rerun multicam inspect --multicam-name NAME.",
        ]
    return {
        "requires_multicam_name": bool(available_multicam_clips),
        "status": "candidates_available" if available_multicam_clips else "no_multicam_clips_found",
        "project_db_path": project_db_path,
        "timeline_name": active_timeline_name or None,
        "available_multicam_clips": available_multicam_clips,
        "candidate_count": len(available_multicam_clips),
        "example_commands": [
            "cutagent multicam inspect --json",
            'cutagent multicam inspect --multicam-name "Podcast Edit Multicam" --json',
            'cutagent multicam create --angle "A=camA.mov" --angle "B=camB.mov" --timeline-name "Podcast Edit" --multicam-name "Podcast Edit Multicam" --sync-mode in --json',
        ],
        "next_steps": next_steps,
    }


def resolve_effective_settings(job: dict[str, Any]) -> dict[str, Any]:
    settings = job.get("multicam_settings") if isinstance(job.get("multicam_settings"), dict) else {}
    allow_missing_angles = _normalize_same_camera_grouping(settings.get("same_camera_grouping")) != "manual"
    sources = _parse_sources(job.get("sources"), allow_missing_angles=allow_missing_angles)
    return _normalize_effective_settings(job, sources=sources)


def auto_edit_multicam(conn, *, job: dict[str, Any]) -> dict[str, Any]:
    job = _job_with_resolved_creation_metadata(conn, job)
    plan = build_multicam_job_plan(conn, job)
    effective_settings = dict(plan["multicam_settings"])
    sources = _parse_sources(job.get("sources"))
    angle_spec = _sources_to_angle_spec(sources, effective_settings["angle_order"])
    create_result = podcast_multicam.native_multicam_create(
        conn,
        timeline_name=effective_settings["timeline_name"],
        multicam_name=effective_settings["multicam_name"],
        angles=angle_spec,
        source_specs=_sources_to_source_specs(sources, effective_settings["angle_order"]),
        source_layout=effective_settings["source_layout"],
        sync=effective_settings["sync_mode"],
        sync_channel=effective_settings["sync_channel"],
        marker_name=effective_settings["marker_name"],
        full_clip_extents=effective_settings["full_clip_extents"],
        audio_mode=effective_settings["audio_mode"],
        reference_audio_angle=effective_settings["default_audio_angle"],
        start_timecode=effective_settings["start_timecode"],
        reference_source=effective_settings["reference_source"],
        source_start_offsets_frames=_source_start_offsets_for_angle_order(effective_settings, sources),
        source_start_offsets_mode="timeline_offsets",
        materialize_timeline=False,
        preferred_duration_frames=effective_settings.get("timeline_duration_frames"),
    )
    switch_result = multicam_switch(
        conn,
        multicam_name=effective_settings["multicam_name"],
        plan=plan,
        timeline_name=effective_settings["timeline_name"],
        replace_active_timeline=False,
    )
    return {
        "timeline_name": effective_settings["timeline_name"],
        "multicam_name": effective_settings["multicam_name"],
        "sources": plan["sources"],
        "selection_policy_result": plan["selection_policy_result"],
        "multicam_settings": effective_settings,
        "timeline_settings": plan["timeline_settings"],
        "switch_rules": list(job.get("switch_rules") or []),
        "plan": plan,
        "create": create_result,
        "switch": switch_result,
        "support_tier": plan["support_tier"],
        "verification": switch_result["verification"],
    }


def load_multicam_job(*, job_path: str | None = None, job_json: str | None = None) -> dict[str, Any]:
    return _load_job_payload(job_path=job_path, job_json=job_json)
