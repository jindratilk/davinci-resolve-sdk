from __future__ import annotations

import json
import os
import re
from typing import Any

from ...errors import ValidationError
from ...utils.timecode import seconds_to_frames, timecode_to_seconds
from .. import media_pool


def _is_temp_bin_folder_path(folder_path: str | None, *, temp_bin_prefix: str) -> bool:
    normalized = str(folder_path or "")
    return f"/{temp_bin_prefix}" in normalized or normalized.startswith(temp_bin_prefix)


def _normalize_folder_path_for_match(value: str | None) -> str:
    return re.sub(r"/+", "/", str(value or "").strip().replace("\\", "/")).strip("/")


def _folder_path_matches(candidate: str | None, requested: str | None) -> bool:
    candidate_normalized = _normalize_folder_path_for_match(candidate)
    requested_normalized = _normalize_folder_path_for_match(requested)
    if not requested_normalized:
        return True
    if candidate_normalized == requested_normalized:
        return True
    return candidate_normalized.endswith(f"/{requested_normalized}")


def _normalize_source_path_for_match(value: str | None) -> str:
    expanded = os.path.expanduser(str(value or "").strip())
    return os.path.normcase(os.path.normpath(expanded))


def _stable_clip_matches(conn, clip_name: str, *, temp_bin_prefix: str) -> list[dict[str, Any]]:
    root = conn.media_pool.GetRootFolder()
    matches: list[dict[str, Any]] = []
    media_pool._collect_clip_matches(root, clip_name, "", matches)
    return [
        match
        for match in matches
        if not _is_temp_bin_folder_path(str(match.get("folder") or ""), temp_bin_prefix=temp_bin_prefix)
    ]


def _find_resolved_angle_clip_match(conn, clip_name: str, *, temp_bin_prefix: str) -> dict[str, Any] | None:
    try:
        return media_pool.find_clip_match(conn, clip_name)
    except ValidationError as exc:
        candidates = exc.details.get("candidates") if isinstance(exc.details, dict) else None
        if not isinstance(candidates, list):
            raise

        stable_matches = _stable_clip_matches(conn, clip_name, temp_bin_prefix=temp_bin_prefix)
        if len(stable_matches) == 1:
            return stable_matches[0]
        if not stable_matches:
            raise

        raise ValidationError(
            "Clip name is ambiguous in Media Pool.",
            details={
                "clip": clip_name,
                "candidates": [{"name": match["name"], "folder": match["folder"]} for match in stable_matches],
            },
        ) from exc


def _normalize_angle_source_specs(
    source_specs: list[dict[str, Any]] | None,
    angle_map: dict[str, str],
    *,
    angle_source_spec_cls: type,
) -> list[Any]:
    if not source_specs:
        return [angle_source_spec_cls(label=label, clip_name=clip_name) for label, clip_name in angle_map.items()]

    normalized: list[Any] = []
    item_counts_by_angle: dict[str, int] = {}
    for raw in source_specs:
        if not isinstance(raw, dict):
            continue
        label = str(raw.get("angle") or raw.get("label") or "").strip()
        clip_name = str(raw.get("clip_name") or raw.get("clip") or raw.get("name") or "").strip()
        folder = str(raw.get("folder") or raw.get("folder_path") or raw.get("bin") or "").strip() or None
        source_path = str(raw.get("source_path") or raw.get("path") or raw.get("media_path") or "").strip() or None
        record_start_frame = raw.get("record_start_frame")
        source_in_frame = raw.get("source_in_frame")
        duration_frames = raw.get("duration_frames")
        try:
            record_start_frame = int(record_start_frame) if record_start_frame is not None else None
            source_in_frame = int(source_in_frame) if source_in_frame is not None else None
            duration_frames = int(duration_frames) if duration_frames is not None else None
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "Native multicam source timing fields must be integers when provided.",
                details={"source": raw},
            ) from exc
        if not label or not clip_name:
            raise ValidationError(
                "Each native multicam source spec must define both angle and clip_name.",
                details={"source": raw},
            )
        item_index = item_counts_by_angle.get(label, 0)
        item_counts_by_angle[label] = item_index + 1
        normalized.append(
            angle_source_spec_cls(
                label=label,
                clip_name=clip_name,
                folder=folder,
                source_path=source_path,
                item_index=item_index,
                record_start_frame=record_start_frame,
                source_in_frame=source_in_frame,
                duration_frames=duration_frames,
            )
        )

    if not normalized:
        raise ValidationError("At least one multicam angle source spec is required.")
    source_labels = list(dict.fromkeys(source.label for source in normalized))
    if sorted(source_labels) != sorted(angle_map.keys()):
        raise ValidationError(
            "Native multicam source specs must contain exactly the requested angle labels.",
            details={
                "source_spec_angles": source_labels,
                "angle_spec_angles": list(angle_map.keys()),
            },
        )
    return normalized


def _find_resolved_angle_source_spec_match(conn, source_spec: Any, *, temp_bin_prefix: str) -> dict[str, Any] | None:
    if not source_spec.folder and not source_spec.source_path:
        return _find_resolved_angle_clip_match(conn, source_spec.clip_name, temp_bin_prefix=temp_bin_prefix)

    stable_matches = _stable_clip_matches(conn, source_spec.clip_name, temp_bin_prefix=temp_bin_prefix)
    if source_spec.folder:
        stable_matches = [
            match
            for match in stable_matches
            if _folder_path_matches(str(match.get("folder") or ""), source_spec.folder)
        ]
    if source_spec.source_path:
        requested_path = _normalize_source_path_for_match(source_spec.source_path)
        filtered: list[dict[str, Any]] = []
        for match in stable_matches:
            clip = match["clip"]
            source_path = media_pool._canonical_source_path(media_pool._clip_properties(clip), clip)
            if source_path and _normalize_source_path_for_match(source_path) == requested_path:
                filtered.append({**match, "_resolved_source_path": source_path})
        stable_matches = filtered

    if len(stable_matches) == 1:
        return stable_matches[0]
    if not stable_matches:
        return None
    raise ValidationError(
        "Clip name is ambiguous in Media Pool after applying the source spec.",
        details={
            "clip": source_spec.clip_name,
            "folder": source_spec.folder,
            "source_path": source_spec.source_path,
            "candidates": [{"name": match["name"], "folder": match["folder"]} for match in stable_matches],
        },
    )


def _resolved_angle_media_start_time(props: dict[str, Any], clip_fps: float) -> float | None:
    for key in ("Start TC", "Start Timecode", "Source Start TC", "Source Timecode", "TC"):
        raw_value = props.get(key)
        if raw_value in (None, ""):
            continue
        try:
            return timecode_to_seconds(str(raw_value).strip(), clip_fps)
        except Exception:
            continue
    return None


def _resolved_source_markers(clip: Any) -> tuple[dict[str, Any], ...]:
    getter = getattr(clip, "GetMarkers", None)
    if not callable(getter):
        return ()
    try:
        raw_markers = getter() or {}
    except Exception:
        return ()
    if not isinstance(raw_markers, dict):
        return ()
    normalized: list[dict[str, Any]] = []
    for raw_frame, raw_marker in raw_markers.items():
        if not isinstance(raw_marker, dict):
            continue
        try:
            frame = int(round(float(raw_frame)))
        except (TypeError, ValueError):
            continue
        normalized.append(
            {
                "frame": frame,
                "name": str(raw_marker.get("name") or "").strip(),
                "color": str(raw_marker.get("color") or "").strip(),
                "note": str(raw_marker.get("note") or "").strip(),
            }
        )
    return tuple(sorted(normalized, key=lambda marker: (int(marker["frame"]), str(marker["name"]))))


def _resolved_source_audio_mapping(clip: Any) -> dict[str, Any] | None:
    getter = getattr(clip, "GetAudioMapping", None)
    if not callable(getter):
        return None
    try:
        payload = json.loads(str(getter() or "{}"))
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("track_mapping"), dict):
        return None
    return payload


def _resolve_angle_source_specs(
    conn,
    source_specs: list[dict[str, Any]] | None,
    *,
    angle_map: dict[str, str],
    angle_source_spec_cls: type,
    resolved_angle_clip_cls: type,
    temp_bin_prefix: str,
) -> list[Any]:
    normalized_specs = _normalize_angle_source_specs(
        source_specs,
        angle_map,
        angle_source_spec_cls=angle_source_spec_cls,
    )
    resolved: list[Any] = []
    missing_clips: list[dict[str, str]] = []
    missing_source_paths: list[dict[str, str]] = []
    source_to_angle: dict[str, str] = {}
    duplicates: list[dict[str, str]] = []

    for source_spec in normalized_specs:
        label = source_spec.label
        clip_name = source_spec.clip_name
        match = _find_resolved_angle_source_spec_match(conn, source_spec, temp_bin_prefix=temp_bin_prefix)
        if not match:
            missing_clips.append(
                {
                    "label": label,
                    "clip_name": clip_name,
                    "folder": source_spec.folder or "",
                    "source_path": source_spec.source_path or "",
                }
            )
            continue

        clip = match["clip"]
        props = media_pool._clip_properties(clip)
        source_path = str(match.get("_resolved_source_path") or media_pool._canonical_source_path(props, clip) or "")
        if not source_path:
            missing_source_paths.append(
                {
                    "label": label,
                    "clip_name": clip_name,
                    "folder": str(match.get("folder") or ""),
                }
            )
            continue

        previous_label = source_to_angle.get(source_path)
        if previous_label:
            duplicates.append(
                {
                    "source_path": source_path,
                    "first_label": previous_label,
                    "duplicate_label": label,
                    "clip_name": clip_name,
                }
            )
            continue

        source_to_angle[source_path] = label
        clip_fps = float(getattr(conn, "fps", 24.0) or 24.0)
        duration_frames: int | None = None
        duration_raw = str(props.get("Duration") or "").strip()
        if duration_raw:
            try:
                duration_frames = seconds_to_frames(timecode_to_seconds(duration_raw, clip_fps), clip_fps)
            except Exception:
                duration_frames = None
        resolved.append(
            resolved_angle_clip_cls(
                label=label,
                clip_name=clip_name,
                source_path=source_path,
                folder=str(match.get("folder") or ""),
                duration_frames=duration_frames,
                fps=clip_fps,
                media_start_time=_resolved_angle_media_start_time(props, clip_fps),
                item_index=int(source_spec.item_index),
                record_start_frame=source_spec.record_start_frame,
                source_in_frame=source_spec.source_in_frame,
                item_duration_frames=source_spec.duration_frames,
                markers=_resolved_source_markers(clip),
                audio_mapping=_resolved_source_audio_mapping(clip),
            )
        )

    if missing_clips:
        raise ValidationError(
            "One or more angle clips were not found in the Media Pool.",
            details={"missing_clips": missing_clips, "angles": angle_map},
        )
    if missing_source_paths:
        raise ValidationError(
            "One or more angle clips do not expose a usable source_path.",
            details={"missing_source_paths": missing_source_paths, "angles": angle_map},
        )
    if duplicates:
        raise ValidationError(
            "Native multicam angles must resolve to distinct source files.",
            details={"duplicate_source_paths": duplicates, "angles": angle_map},
        )
    resolved_angle_count = len({source.label for source in resolved})
    if resolved_angle_count < 2:
        raise ValidationError(
            "Native multicam requires at least 2 logical angles.",
            details={
                "resolved_count": len(resolved),
                "resolved_angle_count": resolved_angle_count,
                "angles": angle_map,
            },
        )
    return resolved


def _resolve_angle_sources(
    conn,
    angle_map: dict[str, str],
    *,
    angle_source_spec_cls: type,
    resolved_angle_clip_cls: type,
    temp_bin_prefix: str,
) -> list[Any]:
    return _resolve_angle_source_specs(
        conn,
        None,
        angle_map=angle_map,
        angle_source_spec_cls=angle_source_spec_cls,
        resolved_angle_clip_cls=resolved_angle_clip_cls,
        temp_bin_prefix=temp_bin_prefix,
    )
