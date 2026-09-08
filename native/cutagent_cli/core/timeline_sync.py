"""Timeline clip sync without native multicam creation."""

from __future__ import annotations

import json
from pathlib import Path
import shlex
from typing import Any

from ..errors import APICallFailed, ValidationError
from ..utils.time_ref import parse_record_frame
from . import audio_conform, media_pool, subframe_probe, sync_metadata, timeline_ops, waveform_sync
from .audio_ops import _run_ffprobe

SYNC_MODES = {"waveform", "timecode", "manual"}
AUDIO_MODES = {"none", "reference", "all"}
SUBFRAME_MODES = {"auto", "fractional", "round", "conform"}
SYNC_SCHEMA_VERSION = 1
DEFAULT_MULTICAM_AUDIO_ACTIVITY_SWITCHING = {
    "analysis_window_ms": 250,
    "activity_floor_db": -50.0,
    "activity_margin_db": 6.0,
    "dominance_margin_db": 4.0,
    "min_switch_ms": 1500,
    "switch_delay_ms": 500,
    "max_silence_hold_ms": 8000,
}

# Pairwise shared-clock verification is only attempted when two targets land
# within this window of each other (cheap prescreen before the pair estimate).
_GROUP_PRESCREEN_SECONDS = 1.0


def _parse_repeated_key_values(specs: list[str] | None, *, option_name: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for spec in list(specs or []):
        label, value = _split_label_value(spec, option_name=option_name)
        if label in values:
            raise ValidationError(
                f"{option_name} labels must be unique.",
                details={"label": label, "value": spec},
                recoverability="not_applicable",
            )
        values[label] = value
    return values


def _parse_multicam_angle_specs(specs: list[str] | None, *, video_labels: list[str]) -> dict[str, str]:
    if not specs:
        return {label: label for label in video_labels}
    known = set(video_labels)
    angles: dict[str, str] = {}
    seen_labels: set[str] = set()
    for raw in list(specs or []):
        text = str(raw or "").strip()
        if not text:
            continue
        if "=" in text:
            label, angle = _split_label_value(text, option_name="--multicam-angle")
        else:
            label, angle = text, text
        if label not in known:
            raise ValidationError(
                "--multicam-angle references an unknown video sync source.",
                details={"label": label, "video_labels": video_labels},
                recoverability="not_applicable",
            )
        if label in seen_labels or angle in angles:
            raise ValidationError(
                "--multicam-angle entries must have unique source labels and angles.",
                details={"label": label, "angle": angle},
                recoverability="not_applicable",
            )
        seen_labels.add(label)
        angles[angle] = label
    if len(angles) < 2:
        raise ValidationError(
            "Multicam artifact export requires at least two video angles.",
            details={"angle_count": len(angles), "video_labels": video_labels},
            recoverability="not_applicable",
        )
    return angles


def _split_label_value(raw: str, *, option_name: str) -> tuple[str, str]:
    text = str(raw or "").strip()
    if "=" not in text:
        raise ValidationError(
            f"{option_name} must use LABEL=VALUE syntax.",
            details={"value": raw, "option": option_name},
            recoverability="not_applicable",
        )
    label, value = text.split("=", 1)
    label = label.strip()
    value = value.strip()
    if not label:
        raise ValidationError(
            f"{option_name} label must not be empty.",
            details={"value": raw, "option": option_name},
            recoverability="not_applicable",
        )
    if not value:
        raise ValidationError(
            f"{option_name} value must not be empty.",
            details={"label": label, "option": option_name},
            recoverability="not_applicable",
        )
    return label, value


def _source_entry_from_value(value: str) -> dict[str, Any]:
    text = str(value or "").strip()
    if "|" in text:
        entry: dict[str, Any] = {}
        for raw_part in text.split("|"):
            part = raw_part.strip()
            lowered_part = part.lower()
            for prefix, key in (
                ("name:", "name"),
                ("path:", "path"),
                ("media_id:", "media_id"),
                ("media-id:", "media_id"),
                ("folder:", "folder"),
            ):
                if lowered_part.startswith(prefix):
                    entry[key] = part[len(prefix):].strip()
                    break
            else:
                raise ValidationError(
                    "Compound --source parts must use name:, path:, media_id:, or folder:.",
                    details={"source": value, "part": raw_part},
                    recoverability="not_applicable",
                )
        if not any(entry.get(key) for key in ("name", "path", "media_id")):
            raise ValidationError(
                "Compound --source requires name:, path:, or media_id:.",
                details={"source": value},
                recoverability="not_applicable",
            )
        return entry
    lowered = text.lower()
    for prefix, key in (
        ("name:", "name"),
        ("path:", "path"),
        ("media_id:", "media_id"),
        ("media-id:", "media_id"),
    ):
        if lowered.startswith(prefix):
            return {key: text[len(prefix):].strip()}
    if text.startswith(("/", "~")) or "/" in text or "\\" in text:
        return {"path": str(Path(text).expanduser())}
    return {"name": text}


def parse_source_specs(source_specs: list[str]) -> list[dict[str, Any]]:
    if len(source_specs) < 2:
        raise ValidationError(
            "timeline sync-clips requires at least two --source entries.",
            details={"source_count": len(source_specs)},
            recoverability="not_applicable",
        )
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, spec in enumerate(source_specs):
        label, value = _split_label_value(spec, option_name="--source")
        if label in seen:
            raise ValidationError(
                "Duplicate sync source label.",
                details={"label": label, "source": spec},
                recoverability="not_applicable",
            )
        seen.add(label)
        entry = _source_entry_from_value(value)
        sources.append({"index": index, "label": label, "input": value, "entry": entry})
    return sources


def parse_track_specs(track_specs: list[str], *, option_name: str) -> dict[str, int]:
    tracks: dict[str, int] = {}
    for spec in track_specs:
        label, value = _split_label_value(spec, option_name=option_name)
        try:
            track = int(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                f"{option_name} track index must be an integer.",
                details={"label": label, "track": value},
                recoverability="not_applicable",
            ) from exc
        if track < 1:
            raise ValidationError(
                f"{option_name} track index must be 1 or greater.",
                details={"label": label, "track": track},
                recoverability="not_applicable",
            )
        tracks[label] = track
    return tracks


def parse_offset_specs(offset_specs: list[str]) -> dict[str, int]:
    offsets: dict[str, int] = {}
    for spec in offset_specs:
        label, value = _split_label_value(spec, option_name="--offset")
        try:
            offsets[label] = int(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "--offset value must be an integer frame count.",
                details={"label": label, "offset": value},
                recoverability="not_applicable",
            ) from exc
    return offsets


def _timeline_start_frame(conn: Any) -> int:
    timeline = getattr(conn, "timeline", None)
    getter = getattr(timeline, "GetStartFrame", None)
    if callable(getter):
        try:
            return int(getter())
        except Exception:
            pass
    try:
        return int(getattr(conn, "start_frame", 0) or 0)
    except Exception:
        return 0


def _timeline_name(conn: Any) -> str | None:
    timeline = getattr(conn, "timeline", None)
    getter = getattr(timeline, "GetName", None)
    if callable(getter):
        try:
            return str(getter())
        except Exception:
            return None
    return None


def _find_timeline(conn: Any, name: str) -> object | None:
    project = getattr(conn, "project", None)
    if not project:
        return None
    try:
        count = int(project.GetTimelineCount() or 0)
    except Exception:
        count = 0
    for index in range(1, count + 1):
        timeline = project.GetTimelineByIndex(index)
        if timeline and hasattr(timeline, "GetName") and timeline.GetName() == name:
            return timeline
    return None


def prepare_target_timeline(
    conn: Any,
    *,
    timeline_name: str | None,
    create_timeline: bool,
) -> dict[str, Any]:
    if create_timeline and not timeline_name:
        raise ValidationError(
            "--create-timeline requires --timeline.",
            details={"timeline": timeline_name, "create_timeline": create_timeline},
            recoverability="not_applicable",
        )
    if not timeline_name:
        if getattr(conn, "timeline", None) is None:
            raise ValidationError(
                "No active timeline is available; pass --timeline or --create-timeline.",
                details={},
            )
        return {
            "mode": "current",
            "timeline": _timeline_name(conn),
            "changed": False,
            "created": False,
        }

    existing = _find_timeline(conn, timeline_name)
    if create_timeline:
        if existing is not None:
            raise ValidationError(
                "Target timeline already exists.",
                details={"timeline": timeline_name, "create_timeline": True},
                recoverability="manual",
            )
        timeline_ops.create_timeline(conn, timeline_name)
        refresh = getattr(conn, "refresh", None)
        if callable(refresh):
            refresh()
        return {
            "mode": "created",
            "timeline": timeline_name,
            "changed": True,
            "created": True,
        }

    switch = timeline_ops.switch_timeline(conn, name=timeline_name, return_details=True)
    refresh = getattr(conn, "refresh", None)
    if callable(refresh):
        refresh()
    return {
        "mode": "switched",
        "timeline": timeline_name,
        "changed": bool(switch.get("changed")),
        "created": False,
        "switch": {key: value for key, value in switch.items() if key != "timeline"},
    }


def _resolve_sources(conn: Any, source_specs: list[str]) -> list[dict[str, Any]]:
    parsed = parse_source_specs(source_specs)
    resolved_sources: list[dict[str, Any]] = []
    for source in parsed:
        resolved = media_pool.resolve_append_media_entry(conn, source["entry"])
        resolved_sources.append(
            {
                **source,
                "clip": resolved["clip"],
                "name": resolved.get("name"),
                "folder": resolved.get("folder"),
                "source_path": resolved.get("source_path"),
            }
        )
    return resolved_sources


def _validate_reference(label: str | None, sources: list[dict[str, Any]]) -> str:
    labels = [str(source["label"]) for source in sources]
    reference = str(label).strip() if label else labels[0]
    if reference not in labels:
        raise ValidationError(
            "Reference label is not one of the sync sources.",
            details={"reference": reference, "source_labels": labels},
            recoverability="not_applicable",
        )
    return reference


def _compute_offsets(
    *,
    sources: list[dict[str, Any]],
    reference_label: str,
    sync_mode: str,
    manual_offsets: dict[str, int],
    fps: float,
) -> dict[str, int]:
    labels = [str(source["label"]) for source in sources]
    unknown_offsets = sorted(set(manual_offsets) - set(labels))
    if unknown_offsets:
        raise ValidationError(
            "--offset labels must match --source labels.",
            details={"unknown_labels": unknown_offsets, "source_labels": labels},
            recoverability="not_applicable",
        )

    normalized_mode = str(sync_mode or "").strip().lower()
    if normalized_mode not in SYNC_MODES:
        raise ValidationError(
            "Unsupported sync mode for timeline sync-clips.",
            details={"sync": sync_mode, "allowed": sorted(SYNC_MODES)},
            recoverability="not_applicable",
        )

    if normalized_mode == "manual":
        offsets = {label: int(manual_offsets.get(label, 0)) for label in labels}
        min_offset = min(offsets.values()) if offsets else 0
        return {label: int(offset - min_offset) for label, offset in offsets.items()}

    detailed = _compute_waveform_details(sources=sources, reference_label=reference_label, fps=fps)
    return {label: int(entry["offset_frames_int"]) for label, entry in detailed["normalized"].items()}


def _source_paths_for_analysis(
    sources: list[dict[str, Any]], reference_label: str
) -> tuple[list[str], dict[str, str]]:
    labels = [str(source["label"]) for source in sources]
    by_label = {str(source["label"]): source for source in sources}
    analysis_labels = [reference_label] + [label for label in labels if label != reference_label]
    paths: dict[str, str] = {}
    missing_paths: list[dict[str, Any]] = []
    for label in analysis_labels:
        source_path = by_label[label].get("source_path")
        if not source_path:
            missing_paths.append({"label": label, "name": by_label[label].get("name"), "folder": by_label[label].get("folder")})
        else:
            paths[label] = str(source_path)
    if missing_paths:
        raise ValidationError(
            "Waveform sync requires each source to expose a usable source_path.",
            details={"missing_source_paths": missing_paths},
            recoverability="manual",
        )
    return analysis_labels, paths


def _compute_waveform_details(
    *,
    sources: list[dict[str, Any]],
    reference_label: str,
    fps: float,
    use_timecode_prior: bool = False,
) -> dict[str, Any]:
    """Run the v2 estimator per source, group shared-clock sources, normalize.

    Returns {"results", "groups", "normalized", "min_offset_seconds"} where
    `normalized[label]` carries offset_seconds/offset_frames_float/
    offset_frames_int shifted so the earliest source lands at 0.
    """
    analysis_labels, paths = _source_paths_for_analysis(sources, reference_label)
    reference_path = paths[reference_label]

    results: dict[str, dict[str, Any]] = {}
    metadata: dict[str, dict[str, Any]] = {}
    for label in analysis_labels:
        try:
            metadata[label] = sync_metadata.read_sync_metadata(paths[label], fps=fps)
        except Exception:
            metadata[label] = {}
    for label in analysis_labels:
        if label == reference_label:
            results[label] = {
                "offset_seconds": 0.0,
                "offset_frames_float": 0.0,
                "offset_frames_int": 0,
                "subframe_residual_ms": 0.0,
                "drift_ppm": 0.0,
                "drift_span_ms": 0.0,
                "confidence": None,
                "warnings": [],
                "method": "reference",
            }
            continue
        prior = (
            sync_metadata.compute_metadata_prior(metadata[reference_label], metadata[label])
            if use_timecode_prior
            else None
        )
        if prior is None:
            results[label] = waveform_sync.estimate_offset(reference_path, paths[label], fps)
            continue
        try:
            result = waveform_sync.estimate_offset(
                reference_path, paths[label], fps, prior_offset_seconds=prior
            )
            result["metadata_prior_seconds"] = float(prior)
            result["metadata_prior_used"] = True
            results[label] = result
        except Exception as exc:
            result = waveform_sync.estimate_offset(reference_path, paths[label], fps)
            warnings = list(result.get("warnings") or [])
            warnings.append("metadata_timecode_prior_rejected")
            result["warnings"] = warnings
            result["metadata_prior_seconds"] = float(prior)
            result["metadata_prior_used"] = False
            result["metadata_prior_error"] = {
                "type": exc.__class__.__name__,
                "message": str(exc),
                "details": getattr(exc, "details", None),
            }
            results[label] = result

    # Shared-clock grouping: recorder identity from metadata, or a direct
    # pairwise measurement for targets that landed close together.
    recorder_ids = {label: (metadata[label] or {}).get("recorder_id") for label in analysis_labels}
    pairwise: dict[tuple[str, str], dict[str, Any]] = {}
    target_labels = [label for label in analysis_labels if label != reference_label]
    for index, label_a in enumerate(target_labels):
        for label_b in target_labels[index + 1:]:
            if recorder_ids.get(label_a) and recorder_ids.get(label_a) == recorder_ids.get(label_b):
                continue  # metadata already proves the group
            delta = results[label_b]["offset_seconds"] - results[label_a]["offset_seconds"]
            if abs(delta) > _GROUP_PRESCREEN_SECONDS:
                continue
            try:
                pairwise[(label_a, label_b)] = waveform_sync.estimate_offset(
                    paths[label_a], paths[label_b], fps, prior_offset_seconds=delta
                )
            except Exception:
                continue
    groups = waveform_sync.group_offsets(results, recorder_ids, pairwise, fps=fps)

    grouped_seconds = {label: float(groups[label]["offset_seconds"]) for label in analysis_labels}
    min_offset_seconds = min(grouped_seconds.values()) if grouped_seconds else 0.0
    normalized: dict[str, dict[str, Any]] = {}
    for label in analysis_labels:
        seconds = grouped_seconds[label] - min_offset_seconds
        frames_float = seconds * fps
        frames_int = int(round(frames_float))
        normalized[label] = {
            "offset_seconds": seconds,
            "offset_frames_float": frames_float,
            "offset_frames_int": frames_int,
            "subframe_residual_ms": (seconds - frames_int / fps) * 1000.0,
        }
    return {
        "results": results,
        "groups": groups,
        "normalized": normalized,
        "min_offset_seconds": min_offset_seconds,
        "metadata": metadata,
    }


def _is_audio_only_source(source_path: str | None) -> bool:
    if not source_path:
        return False
    try:
        probe = _run_ffprobe(
            [
                "-v", "error",
                "-select_streams", "v",
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0",
                str(source_path),
            ],
            check=False,
        )
    except Exception:
        return False
    if probe.returncode != 0:
        return False
    return not (probe.stdout or "").strip()


def _default_video_tracks(sources: list[dict[str, Any]], explicit: dict[str, int]) -> dict[str, int]:
    labels = [str(source["label"]) for source in sources]
    unknown = sorted(set(explicit) - set(labels))
    if unknown:
        raise ValidationError(
            "--video-track labels must match --source labels.",
            details={"unknown_labels": unknown, "source_labels": labels},
            recoverability="not_applicable",
        )
    return {label: int(explicit.get(label, index + 1)) for index, label in enumerate(labels)}


def _audio_labels(
    *,
    sources: list[dict[str, Any]],
    reference_label: str,
    audio_mode: str,
) -> list[str]:
    normalized = str(audio_mode or "").strip().lower()
    if normalized not in AUDIO_MODES:
        raise ValidationError(
            "Unsupported audio mode for timeline sync-clips.",
            details={"audio_mode": audio_mode, "allowed": sorted(AUDIO_MODES)},
            recoverability="not_applicable",
        )
    if normalized == "none":
        return []
    if normalized == "reference":
        return [reference_label]
    return [str(source["label"]) for source in sources]


def _default_audio_tracks(
    *,
    sources: list[dict[str, Any]],
    reference_label: str,
    audio_mode: str,
    explicit: dict[str, int],
) -> dict[str, int]:
    labels = [str(source["label"]) for source in sources]
    unknown = sorted(set(explicit) - set(labels))
    if unknown:
        raise ValidationError(
            "--audio-track labels must match --source labels.",
            details={"unknown_labels": unknown, "source_labels": labels},
            recoverability="not_applicable",
        )
    selected = _audio_labels(sources=sources, reference_label=reference_label, audio_mode=audio_mode)
    tracks: dict[str, int] = {}
    for index, label in enumerate(selected):
        default_track = 1 if str(audio_mode).strip().lower() == "reference" else index + 1
        tracks[label] = int(explicit.get(label, default_track))
    return tracks


def _source_public(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": source.get("index"),
        "label": source.get("label"),
        "input": source.get("input"),
        "name": source.get("name"),
        "folder": source.get("folder"),
        "source_path": source.get("source_path"),
        "entry": source.get("entry"),
    }


def _placement_public(placement: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in placement.items()
        if key not in {"clip"}
    }


def _clip_property_float(clip: Any, keys: list[str]) -> float | None:
    getter = getattr(clip, "GetClipProperty", None)
    if not callable(getter):
        return None
    props: dict[str, Any] = {}
    try:
        raw_props = getter()
        if isinstance(raw_props, dict):
            props = raw_props
    except Exception:
        props = {}
    for key in keys:
        values: list[Any] = []
        if props:
            values.append(props.get(key))
        try:
            values.append(getter(key))
        except Exception:
            pass
        for value in values:
            try:
                number = float(str(value).strip())
            except (TypeError, ValueError):
                continue
            if number > 0:
                return number
    return None


def _probe_video_fps(source_path: str | None) -> float | None:
    if not source_path:
        return None
    try:
        probe = _run_ffprobe(
            [
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=avg_frame_rate,r_frame_rate",
                "-of",
                "json",
                str(source_path),
            ],
            check=False,
        )
    except Exception:
        return None
    if probe.returncode != 0:
        return None
    try:
        payload = json.loads(probe.stdout or "{}")
    except json.JSONDecodeError:
        return None
    streams = payload.get("streams") if isinstance(payload, dict) else None
    if not isinstance(streams, list) or not streams:
        return None
    for key in ("avg_frame_rate", "r_frame_rate"):
        raw = str((streams[0] or {}).get(key) or "").strip()
        if not raw or raw == "0/0":
            continue
        if "/" in raw:
            numerator, denominator = raw.split("/", 1)
            try:
                value = float(numerator) / float(denominator)
            except (TypeError, ValueError, ZeroDivisionError):
                continue
        else:
            try:
                value = float(raw)
            except ValueError:
                continue
        if value > 0:
            return value
    return None


def _source_media_fps(source: dict[str, Any]) -> float | None:
    clip_fps = _clip_property_float(
        source.get("clip"),
        ["FPS", "Frame Rate", "Frame rate", "Video Frame Rate", "Video frame rate"],
    )
    if clip_fps:
        return clip_fps
    probed_fps = _probe_video_fps(source.get("source_path"))
    if probed_fps:
        return probed_fps
    return None


def _source_clip_name(source: dict[str, Any]) -> str:
    name = str(source.get("name") or "").strip()
    if name:
        return name
    source_path = str(source.get("source_path") or "").strip()
    if source_path:
        return Path(source_path).name
    entry = source.get("entry")
    if isinstance(entry, dict):
        for key in ("name", "path", "media_id"):
            value = str(entry.get(key) or "").strip()
            if value:
                return Path(value).name if key == "path" else value
    return str(source.get("label") or "").strip()


def _write_json_artifact(path: str, payload: dict[str, Any]) -> str:
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return str(output_path)


def _audio_offsets_artifact_payload(
    *,
    offsets_frames: dict[str, int],
    offsets_seconds: dict[str, float],
    timeline_fps: float,
    anchor: str | None = None,
    anchor_label: str | None = None,
    anchor_angle: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "fps": float(timeline_fps),
        "offsets": {str(label): int(value) for label, value in offsets_frames.items()},
        "offsets_seconds": {str(label): float(offsets_seconds[label]) for label in offsets_frames if label in offsets_seconds},
        "offset_domain": "timeline",
        "anchor": anchor,
        "anchor_label": anchor_label,
        "anchor_angle": anchor_angle,
    }


def build_multicam_artifacts(
    plan: dict[str, Any],
    *,
    write_multicam_job: str | None = None,
    write_audio_offsets_json: str | None = None,
    multicam_name: str | None = None,
    multicam_timeline_name: str | None = None,
    multicam_angle_specs: list[str] | None = None,
    multicam_audio_angle_map_specs: list[str] | None = None,
    multicam_audio_target_specs: list[str] | None = None,
    multicam_overlap_angle: str | None = None,
    multicam_default_video_angle: str | None = None,
    multicam_default_audio_angle: str | None = None,
    multicam_sync_anchor: str | None = None,
    multicam_switch_plan: str | None = None,
) -> dict[str, Any] | None:
    requested = any(
        [
            write_multicam_job,
            write_audio_offsets_json,
            multicam_name,
            multicam_timeline_name,
            multicam_angle_specs,
            multicam_audio_angle_map_specs,
            multicam_audio_target_specs,
            multicam_overlap_angle,
            multicam_default_video_angle,
            multicam_default_audio_angle,
            multicam_sync_anchor,
            multicam_switch_plan,
        ]
    )
    if not requested:
        return None

    sources = {str(source["label"]): source for source in list(plan.get("sources") or [])}
    sync = plan.get("sync") if isinstance(plan.get("sync"), dict) else {}
    offsets_seconds = {
        str(label): float(value)
        for label, value in dict(sync.get("offsets_seconds") or {}).items()
    }
    offsets_frames = {
        str(label): int(value)
        for label, value in dict(sync.get("offsets_frames") or {}).items()
    }
    timeline_fps = float(plan.get("fps") or plan.get("timeline_fps") or 0.0) or 24.0
    audio_labels = [
        str(placement["label"])
        for placement in list(plan.get("placements") or [])
        if str(placement.get("kind") or "") == "audio"
    ]
    video_labels = [
        str(placement["label"])
        for placement in list(plan.get("placements") or [])
        if str(placement.get("kind") or "") == "video"
    ]
    needs_multicam_job = any(
        [
            write_multicam_job,
            multicam_name,
            multicam_timeline_name,
            multicam_angle_specs,
            multicam_audio_angle_map_specs,
            multicam_audio_target_specs,
            multicam_overlap_angle,
            multicam_default_video_angle,
            multicam_default_audio_angle,
            multicam_sync_anchor,
            multicam_switch_plan,
        ]
    )

    if write_audio_offsets_json and not needs_multicam_job:
        audio_offsets = {
            label: int(round(float(offsets_seconds.get(label, offsets_frames.get(label, 0) / timeline_fps)) * timeline_fps))
            for label in audio_labels
        }
        audio_offsets_seconds = {
            label: float(offsets_seconds.get(label, offsets_frames.get(label, 0) / timeline_fps))
            for label in audio_labels
        }
        return {
            "schema_version": 1,
            "written": {
                "audio_offsets_json": _write_json_artifact(
                    write_audio_offsets_json,
                    _audio_offsets_artifact_payload(
                        offsets_frames=audio_offsets,
                        offsets_seconds=audio_offsets_seconds,
                        timeline_fps=timeline_fps,
                    ),
                )
            },
            "audio_offsets": audio_offsets,
            "audio_offsets_seconds": audio_offsets_seconds,
            "conversion": {
                "timeline_fps": timeline_fps,
                "video_source_offsets_frames": {},
                "details": {},
            },
            "commands": {},
        }

    angle_to_label = _parse_multicam_angle_specs(multicam_angle_specs, video_labels=video_labels)
    angle_order = list(angle_to_label.keys())
    if not angle_order:
        raise ValidationError(
            "Multicam artifact export requires at least one video placement.",
            details={
                "video_labels": video_labels,
                "requested": {
                    "write_multicam_job": bool(write_multicam_job),
                    "write_audio_offsets_json": bool(write_audio_offsets_json),
                    "multicam_options": bool(needs_multicam_job),
                },
            },
            recoverability="not_applicable",
        )
    if len(angle_order) < 2:
        raise ValidationError(
            "Multicam artifact export requires at least two video angles.",
            details={"angle_count": len(angle_order), "angle_order": angle_order, "video_labels": video_labels},
            recoverability="not_applicable",
        )

    timeline_name = str(multicam_timeline_name or plan.get("timeline") or "").strip()
    if not timeline_name:
        raise ValidationError(
            "Multicam artifact export requires a timeline name.",
            details={"timeline": plan.get("timeline"), "multicam_timeline_name": multicam_timeline_name},
            recoverability="not_applicable",
        )
    resolved_multicam_name = str(multicam_name or f"{timeline_name} Multicam").strip()
    if not resolved_multicam_name:
        raise ValidationError(
            "Multicam artifact export requires a non-empty multicam name.",
            details={"multicam_name": multicam_name},
            recoverability="not_applicable",
        )

    default_video_angle = str(multicam_default_video_angle or angle_order[0]).strip()
    default_audio_angle = str(multicam_default_audio_angle or default_video_angle).strip()
    for option_name, value in (
        ("--multicam-default-video-angle", default_video_angle),
        ("--multicam-default-audio-angle", default_audio_angle),
    ):
        if value not in angle_to_label:
            raise ValidationError(
                f"{option_name} must be one of the generated multicam angles.",
                details={"angle": value, "angle_order": angle_order},
                recoverability="not_applicable",
            )

    raw_anchor = str(multicam_sync_anchor or sync.get("reference") or default_video_angle).strip()
    if raw_anchor in angle_to_label:
        anchor_label = angle_to_label[raw_anchor]
        anchor_angle = raw_anchor
    elif raw_anchor in sources:
        anchor_label = raw_anchor
        anchor_angle = next((angle for angle, label in angle_to_label.items() if label == anchor_label), None)
    else:
        raise ValidationError(
            "--multicam-sync-anchor must be a sync source label or generated multicam angle.",
            details={
                "anchor": raw_anchor,
                "source_labels": sorted(sources),
                "angle_order": angle_order,
            },
            recoverability="not_applicable",
        )
    if anchor_label not in offsets_seconds and anchor_label not in offsets_frames:
        raise ValidationError(
            "--multicam-sync-anchor must have a sync offset in the timeline sync plan.",
            details={"anchor": raw_anchor, "anchor_label": anchor_label},
            recoverability="not_applicable",
        )
    anchor_seconds = float(offsets_seconds.get(anchor_label, offsets_frames.get(anchor_label, 0) / timeline_fps))

    video_source_offsets: dict[str, int] = {}
    conversion_details: dict[str, dict[str, Any]] = {}
    for angle, label in angle_to_label.items():
        source = sources.get(label)
        if source is None:
            raise ValidationError(
                "Generated multicam angle references an unknown sync source.",
                details={"angle": angle, "label": label},
                recoverability="not_applicable",
            )
        media_fps = _source_media_fps(source)
        if media_fps is None:
            raise ValidationError(
                "Multicam artifact export requires source media FPS for every video angle.",
                details={
                    "angle": angle,
                    "label": label,
                    "source_path": source.get("source_path"),
                    "timeline_fps": timeline_fps,
                    "reason": "missing_source_media_fps",
                },
                recoverability="manual",
            )
        offset_seconds = float(offsets_seconds.get(label, offsets_frames.get(label, 0) / timeline_fps))
        relative_seconds = anchor_seconds - offset_seconds
        source_offset = int(round(relative_seconds * media_fps))
        video_source_offsets[angle] = source_offset
        conversion_details[angle] = {
            "source_label": label,
            "anchor_label": anchor_label,
            "anchor_angle": anchor_angle,
            "anchor_offset_seconds": anchor_seconds,
            "timeline_offset_seconds": offset_seconds,
            "relative_seconds": relative_seconds,
            "media_fps": media_fps,
            "video_source_offset_frames": source_offset,
            "formula": "round((anchor_offset_seconds - timeline_offset_seconds) * source_media_fps)",
        }

    audio_angle_map = _parse_repeated_key_values(
        multicam_audio_angle_map_specs,
        option_name="--multicam-audio-angle-map",
    )
    unknown_audio = sorted(set(audio_angle_map) - set(sources))
    if unknown_audio:
        raise ValidationError(
            "--multicam-audio-angle-map references unknown sync source labels.",
            details={"unknown_labels": unknown_audio, "source_labels": sorted(sources)},
            recoverability="not_applicable",
        )
    unknown_angles = sorted(set(audio_angle_map.values()) - set(angle_to_label))
    if unknown_angles:
        raise ValidationError(
            "--multicam-audio-angle-map references unknown multicam angles.",
            details={"unknown_angles": unknown_angles, "angle_order": angle_order},
            recoverability="not_applicable",
        )

    audio_targets_raw = _parse_repeated_key_values(
        multicam_audio_target_specs,
        option_name="--multicam-audio-target",
    )
    audio_targets: dict[str, dict[str, Any]] = {}
    for source_id, raw_angles in audio_targets_raw.items():
        if source_id not in audio_angle_map:
            raise ValidationError(
                "--multicam-audio-target must reference an audio source from --multicam-audio-angle-map.",
                details={"source_id": source_id, "audio_sources": sorted(audio_angle_map)},
                recoverability="not_applicable",
            )
        target_angles = [part.strip() for part in raw_angles.split(",") if part.strip()]
        unknown_target_angles = sorted(set(target_angles) - set(angle_to_label))
        if unknown_target_angles:
            raise ValidationError(
                "--multicam-audio-target references unknown multicam angles.",
                details={"source_id": source_id, "unknown_angles": unknown_target_angles, "angle_order": angle_order},
                recoverability="not_applicable",
            )
        audio_targets[source_id] = {
            "angles": target_angles,
            "selection": "default" if len(target_angles) == 1 else "agent_decides",
        }

    audio_offsets = {
        source_id: int(
            round(
                (
                    float(offsets_seconds.get(source_id, offsets_frames.get(source_id, 0) / timeline_fps))
                    - anchor_seconds
                )
                * timeline_fps
            )
        )
        for source_id in audio_angle_map
    }
    audio_offsets_seconds = {
        source_id: float(offsets_seconds.get(source_id, offsets_frames.get(source_id, 0) / timeline_fps)) - anchor_seconds
        for source_id in audio_angle_map
    }
    audio_offsets_path = str(write_audio_offsets_json or "").strip()
    if not audio_offsets_path and write_multicam_job and audio_offsets:
        job_path = Path(write_multicam_job).expanduser()
        audio_offsets_path = str(job_path.with_name(f"{job_path.stem}.audio-offsets.json"))

    overlap: dict[str, Any] = {}
    if multicam_overlap_angle:
        overlap_angle = str(multicam_overlap_angle).strip()
        if overlap_angle not in angle_to_label:
            raise ValidationError(
                "--multicam-overlap-angle must be one of the generated multicam angles.",
                details={"overlap_angle": overlap_angle, "angle_order": angle_order},
                recoverability="not_applicable",
            )
        overlap = {"policy": "angle", "angle": overlap_angle}

    job: dict[str, Any] = {
        "sources": [
            {
                "angle": angle,
                "label": label,
                "clip_name": _source_clip_name(sources[label]),
                "folder": sources[label].get("folder"),
                "source_path": sources[label].get("source_path"),
            }
            for angle, label in angle_to_label.items()
        ],
        "selection_policy_result": {
            "strategy": "timeline_sync_artifact",
            "source": "timeline sync-clips",
            "sync_reference": sync.get("reference"),
            "sync_anchor": raw_anchor,
            "sync_anchor_label": anchor_label,
            "sync_anchor_angle": anchor_angle,
        },
        "timeline_settings": {
            "timeline_name": timeline_name,
        },
        "multicam_settings": {
            "timeline_name": timeline_name,
            "multicam_name": resolved_multicam_name,
            "sync_mode": "in",
            "angle_order": angle_order,
            "default_video_angle": default_video_angle,
            "default_audio_angle": default_audio_angle,
            "video_source_offsets_frames": video_source_offsets,
        },
    }
    if audio_angle_map:
        job["switch_by"] = "audio-activity"
        job["rule_program"] = {
            "kind": "audio_activity_v1",
            "audio_sources": [
                {
                    "id": source_id,
                    "path": str(sources[source_id].get("source_path") or _source_clip_name(sources[source_id])),
                }
                for source_id in audio_angle_map
            ],
            "audio_angle_map": audio_angle_map,
            "audio_targets": audio_targets,
            "audio_sync": {
                "mode": "offsets-json",
                "offsets": audio_offsets,
                "offsets_seconds": audio_offsets_seconds,
                "fps": timeline_fps,
                "offset_domain": "timeline",
                "anchor": raw_anchor,
                "anchor_label": anchor_label,
                "anchor_angle": anchor_angle,
            },
            "switching": dict(DEFAULT_MULTICAM_AUDIO_ACTIVITY_SWITCHING),
            "overlap": overlap,
            "allow_unresolved_targets": False,
        }
        job["verification_requirements"] = {
            "require_native_multicam": True,
            "require_native_multicam_segments": True,
            "require_switch_menu": True,
        }

    written: dict[str, str] = {}
    if write_multicam_job:
        written["multicam_job"] = _write_json_artifact(write_multicam_job, job)
    if audio_offsets_path:
        written["audio_offsets_json"] = _write_json_artifact(
            audio_offsets_path,
            _audio_offsets_artifact_payload(
                offsets_frames=audio_offsets,
                offsets_seconds=audio_offsets_seconds,
                timeline_fps=timeline_fps,
                anchor=raw_anchor,
                anchor_label=anchor_label,
                anchor_angle=anchor_angle,
            ),
        )

    job_arg = written.get("multicam_job") or str(write_multicam_job or "<multicam-job.json>")
    create_command = " ".join(
        [
            "cutagent",
            "--json",
            "multicam",
            "create",
            "--job",
            shlex.quote(job_arg),
        ]
    )
    commands = {"multicam_create": create_command}
    if isinstance(job.get("rule_program"), dict) or isinstance(job.get("segments"), list):
        switch_parts = [
            "cutagent",
            "--json",
            "multicam",
            "switch",
            "--multicam-name",
            shlex.quote(resolved_multicam_name),
            "--job",
            shlex.quote(job_arg),
            "--video-only",
            "--new-timeline",
        ]
        if multicam_switch_plan:
            switch_parts.extend(["--write-plan", shlex.quote(str(Path(multicam_switch_plan).expanduser()))])
        commands["multicam_switch_video_only"] = " ".join(switch_parts)

    return {
        "schema_version": 1,
        "written": written,
        "job": job,
        "audio_offsets": audio_offsets,
        "audio_offsets_seconds": audio_offsets_seconds,
        "conversion": {
            "timeline_fps": timeline_fps,
            "anchor": raw_anchor,
            "anchor_label": anchor_label,
            "anchor_angle": anchor_angle,
            "anchor_offset_seconds": anchor_seconds,
            "video_source_offsets_frames": video_source_offsets,
            "details": conversion_details,
        },
        "commands": commands,
    }


def _audio_placement_mode(
    *,
    subframe_mode: str,
    fractional_supported: bool,
    residual_ms: float,
    drift_span_ms: float,
    fps: float,
    audio_only: bool,
) -> str:
    """Pick how one audio placement achieves sub-frame accuracy.

    fractional — place at a float recordFrame (no media writes);
    conform    — bake residual/drift into a derived WAV (audio-only files);
    round      — integer frame (legacy ceiling, max ± half frame).
    """
    half_frame_ms = 500.0 / fps if fps > 0 else 20.0
    needs_subframe = abs(residual_ms) >= audio_conform.RESIDUAL_SKIP_MS
    needs_drift = abs(drift_span_ms) >= half_frame_ms
    if subframe_mode == "round":
        return "round"
    if subframe_mode == "conform":
        return "conform" if audio_only else ("fractional" if fractional_supported and needs_subframe else "round")
    if subframe_mode == "fractional":
        return "fractional" if needs_subframe else "round"
    # auto
    if needs_drift and audio_only:
        return "conform"
    if needs_subframe:
        if fractional_supported:
            return "fractional"
        if audio_only:
            return "conform"
    return "round"


def build_sync_plan(
    conn: Any,
    *,
    source_specs: list[str],
    sync_mode: str = "waveform",
    reference_label: str | None = None,
    offset_specs: list[str] | None = None,
    video_track_specs: list[str] | None = None,
    audio_track_specs: list[str] | None = None,
    audio_mode: str = "reference",
    record_frame: str | None = None,
    subframe_mode: str = "auto",
    subframe_support: dict[str, Any] | None = None,
    use_timecode_prior: bool = False,
) -> dict[str, Any]:
    normalized_subframe = str(subframe_mode or "auto").strip().lower()
    if normalized_subframe not in SUBFRAME_MODES:
        raise ValidationError(
            "Unsupported --subframe mode.",
            details={"subframe": subframe_mode, "allowed": sorted(SUBFRAME_MODES)},
            recoverability="not_applicable",
        )
    sources = _resolve_sources(conn, source_specs)
    reference = _validate_reference(reference_label, sources)
    manual_offsets = parse_offset_specs(offset_specs or [])
    fps = float(getattr(conn, "fps", 0) or 0)
    normalized_mode = str(sync_mode or "").strip().lower()
    if normalized_mode not in SYNC_MODES:
        raise ValidationError(
            "Unsupported sync mode for timeline sync-clips.",
            details={"sync": sync_mode, "allowed": sorted(SYNC_MODES)},
            recoverability="not_applicable",
        )

    detailed: dict[str, Any] | None = None
    if normalized_mode == "manual":
        offsets = _compute_offsets(
            sources=sources,
            reference_label=reference,
            sync_mode=sync_mode,
            manual_offsets=manual_offsets,
            fps=fps,
        )
        offsets_seconds = {label: offsets[label] / fps if fps > 0 else 0.0 for label in offsets}
        frames_float = {label: float(offsets[label]) for label in offsets}
        residuals_ms = {label: 0.0 for label in offsets}
    elif normalized_mode == "timecode":
        metadata = {
            str(source["label"]): sync_metadata.read_sync_metadata(
                str(source["source_path"]), fps=fps
            )
            for source in sources
        }
        absolute_seconds = {
            label: row.get("start_seconds_since_midnight")
            for label, row in metadata.items()
        }
        missing = sorted(label for label, value in absolute_seconds.items() if value is None)
        if missing:
            raise ValidationError(
                "Timecode sync requires readable source start timecode on every source.",
                details={"reason": "source_timecode_required", "sources": missing},
            )
        origin = min(float(value) for value in absolute_seconds.values())
        offsets_seconds = {
            label: float(value) - origin for label, value in absolute_seconds.items()
        }
        frames_float = {label: seconds * fps for label, seconds in offsets_seconds.items()}
        offsets = {label: int(round(value)) for label, value in frames_float.items()}
        residuals_ms = {
            label: ((frames_float[label] - offsets[label]) / fps) * 1000.0
            for label in frames_float
        }
    else:
        detailed = _compute_waveform_details(
            sources=sources,
            reference_label=reference,
            fps=fps,
            use_timecode_prior=use_timecode_prior,
        )
        normalized = detailed["normalized"]
        offsets = {label: int(entry["offset_frames_int"]) for label, entry in normalized.items()}
        offsets_seconds = {label: float(entry["offset_seconds"]) for label, entry in normalized.items()}
        frames_float = {label: float(entry["offset_frames_float"]) for label, entry in normalized.items()}
        residuals_ms = {label: float(entry["subframe_residual_ms"]) for label, entry in normalized.items()}

    base_record_frame = (
        parse_record_frame(str(record_frame), fps, _timeline_start_frame(conn))
        if record_frame is not None
        else _timeline_start_frame(conn)
    )
    by_label = {str(source["label"]): source for source in sources}
    audio_only_map = {
        str(source["label"]): (
            _is_audio_only_source(source.get("source_path")) if normalized_mode in {"waveform", "timecode"} else False
        )
        for source in sources
    }
    video_sources = [source for source in sources if not audio_only_map[str(source["label"])]]
    video_tracks = _default_video_tracks(
        video_sources or sources, parse_track_specs(video_track_specs or [], option_name="--video-track")
    )
    audio_tracks = _default_audio_tracks(
        sources=sources,
        reference_label=reference,
        audio_mode=audio_mode,
        explicit=parse_track_specs(audio_track_specs or [], option_name="--audio-track"),
    )

    fractional_supported = bool((subframe_support or {}).get("verified_render")) or (
        normalized_subframe == "fractional"
    )

    placements: list[dict[str, Any]] = []
    for source in video_sources:
        label = str(source["label"])
        record = int(base_record_frame + offsets[label])
        placements.append(
            {
                "label": label,
                "kind": "video",
                "track_type": "video",
                "track_index": int(video_tracks[label]),
                "record_frame": record,
                "offset_frames": int(offsets[label]),
                "placement_mode": "round",
                "clip": source["clip"],
                "name": source.get("name"),
                "folder": source.get("folder"),
                "source_path": source.get("source_path"),
            }
        )
    for label, track_index in audio_tracks.items():
        source = by_label[label]
        source_path = source.get("source_path")
        drift_span_ms = 0.0
        drift_ppm = 0.0
        if detailed is not None:
            label_result = detailed["results"].get(label) or {}
            drift_span_ms = float(label_result.get("drift_span_ms") or 0.0)
            drift_ppm = float(label_result.get("drift_ppm") or 0.0)
            group_entry = detailed["groups"].get(label) or {}
            # Shared-clock group members must receive identical drift
            # treatment, otherwise per-member measurement noise (fractions of
            # a ppm) would slowly pull sample-locked tracks apart.
            if int(group_entry.get("group_size") or 1) > 1 and group_entry.get("drift_ppm") is not None:
                drift_ppm = float(group_entry["drift_ppm"])
                drift_span_ms = float(group_entry.get("drift_span_ms") or drift_span_ms)
        audio_only = audio_only_map[label]
        placement_mode = (
            _audio_placement_mode(
                subframe_mode=normalized_subframe,
                fractional_supported=fractional_supported,
                residual_ms=residuals_ms[label],
                drift_span_ms=drift_span_ms,
                fps=fps,
                audio_only=audio_only,
            )
            if normalized_mode == "waveform"
            else "round"
        )
        if placement_mode == "fractional":
            record_value: float | int = base_record_frame + frames_float[label]
            if float(record_value).is_integer():
                record_value = int(record_value)
        else:
            record_value = int(base_record_frame + offsets[label])
        drift_midpoint_seconds = 0.0
        if detailed is not None:
            drift_midpoint_seconds = float(
                (detailed["results"].get(label) or {}).get("midpoint_seconds") or 0.0
            )
            group_entry = detailed["groups"].get(label) or {}
            if int(group_entry.get("group_size") or 1) > 1 and group_entry.get("drift_midpoint_seconds") is not None:
                drift_midpoint_seconds = float(group_entry["drift_midpoint_seconds"])
        placements.append(
            {
                "label": label,
                "kind": "audio",
                "track_type": "audio",
                "track_index": int(track_index),
                "record_frame": record_value,
                "offset_frames": int(offsets[label]),
                "offset_frames_float": frames_float[label],
                "offset_seconds_normalized": offsets_seconds[label],
                "min_offset_seconds": detailed["min_offset_seconds"] if detailed is not None else 0.0,
                "subframe_residual_ms": residuals_ms[label],
                "drift_ppm": drift_ppm,
                "drift_span_ms": drift_span_ms,
                "drift_midpoint_seconds": drift_midpoint_seconds,
                "placement_mode": placement_mode,
                "audio_only_source": audio_only,
                "clip": source["clip"],
                "name": source.get("name"),
                "folder": source.get("folder"),
                "source_path": source_path,
            }
        )

    sync_block: dict[str, Any] = {
        "mode": normalized_mode,
        "reference": reference,
        "offsets_frames": offsets,
        "offsets_seconds": offsets_seconds,
        "normalized_to_earliest": True,
        "analysis_engine": {"waveform": "waveform_sync", "timecode": "source_timecode", "manual": "manual"}[normalized_mode],
        "timecode_prior_enabled": bool(use_timecode_prior) if normalized_mode == "waveform" else False,
        "subframe": {
            "mode": normalized_subframe,
            "fractional_supported": fractional_supported,
            "probe": subframe_support,
        },
        "schema_version": SYNC_SCHEMA_VERSION,
    }
    if detailed is not None:
        sync_block["details"] = {
            label: {
                "offset_seconds": detailed["normalized"][label]["offset_seconds"],
                "offset_frames_float": detailed["normalized"][label]["offset_frames_float"],
                "subframe_residual_ms": detailed["normalized"][label]["subframe_residual_ms"],
                "drift_ppm": (detailed["results"].get(label) or {}).get("drift_ppm"),
                "drift_span_ms": (detailed["results"].get(label) or {}).get("drift_span_ms"),
                "confidence": (detailed["results"].get(label) or {}).get("confidence"),
                "warnings": (detailed["results"].get(label) or {}).get("warnings"),
                "method": (detailed["results"].get(label) or {}).get("method"),
                "metadata_prior_seconds": (detailed["results"].get(label) or {}).get("metadata_prior_seconds"),
                "metadata_prior_used": (detailed["results"].get(label) or {}).get("metadata_prior_used"),
                "metadata_prior_error": (detailed["results"].get(label) or {}).get("metadata_prior_error"),
                "group": (detailed["groups"].get(label) or {}).get("group"),
                "group_size": (detailed["groups"].get(label) or {}).get("group_size"),
            }
            for label in offsets
        }

    return {
        "timeline": _timeline_name(conn),
        "timeline_fps": fps,
        "timeline_start_frame": _timeline_start_frame(conn),
        "base_record_frame": int(base_record_frame),
        "sources": sources,
        "sync": sync_block,
        "video_tracks": video_tracks,
        "audio_mode": str(audio_mode).strip().lower(),
        "audio_tracks": audio_tracks,
        "placements": placements,
    }


def _ensure_track_count(conn: Any, track_type: str, target_count: int) -> dict[str, Any]:
    timeline = getattr(conn, "timeline", None)
    if timeline is None or target_count <= 0:
        return {"track_type": track_type, "requested_count": target_count, "pre_count": 0, "final_count": 0, "added": 0}
    try:
        count = int(timeline.GetTrackCount(track_type) or 0)
    except Exception:
        count = 0
    pre_count = count
    added = 0
    while count < target_count:
        timeline_ops.add_track(conn, track_type)
        added += 1
        try:
            count = int(timeline.GetTrackCount(track_type) or 0)
        except Exception:
            count += 1
        if added > target_count + 5:
            raise APICallFailed(
                "Could not verify required timeline track count.",
                details={"track_type": track_type, "requested_count": target_count, "current_count": count},
            )
    return {
        "track_type": track_type,
        "requested_count": int(target_count),
        "pre_count": int(pre_count),
        "final_count": int(count),
        "added": int(added),
    }


def _verify_append_readback(conn: Any, placements: list[dict[str, Any]]) -> dict[str, Any]:
    refresh = getattr(conn, "refresh", None)
    if callable(refresh):
        try:
            refresh()
        except Exception:
            pass
    rows: list[dict[str, Any]] = []
    all_verified = True
    quantized_labels: list[str] = []
    for placement in placements:
        track_type = str(placement["track_type"])
        track_index = int(placement["track_index"])
        expected_raw = placement["record_frame"]
        fractional = isinstance(expected_raw, float) and not float(expected_raw).is_integer()
        try:
            items = conn.timeline.GetItemListInTrack(track_type, track_index) or []
        except Exception:
            items = []
        matches = []
        subframe_applied: bool | None = None
        for item in items:
            start: float | int | None = None
            if fractional:
                # Sub-frame placements need GetStart(True); older builds fall
                # back to the integer getter and compare at frame tolerance.
                try:
                    start = float(item.GetStart(True))
                except Exception:
                    try:
                        start = float(item.GetStart())
                    except Exception:
                        continue
                exact = abs(start - float(expected_raw)) <= 0.05
                rounded = abs(start - round(float(expected_raw))) <= 0.05
                if not exact and not rounded:
                    continue
                # An integer-only match means DaVinci Resolve quantized the fractional
                # request — the clip is placed, but not sample-accurately.
                subframe_applied = exact
            else:
                try:
                    start = int(item.GetStart())
                except Exception:
                    continue
                if start != int(expected_raw):
                    continue
            name = None
            getter = getattr(item, "GetName", None)
            if callable(getter):
                try:
                    name = getter()
                except Exception:
                    name = None
            matches.append({"name": name, "start": start})
        verified = bool(matches)
        all_verified = all_verified and verified
        if fractional and verified and subframe_applied is False:
            quantized_labels.append(str(placement["label"]))
        row = {
            "label": placement["label"],
            "kind": placement["kind"],
            "track_type": track_type,
            "track_index": track_index,
            "expected_start": expected_raw,
            "match_count": len(matches),
            "matches": matches,
            "verified": verified,
        }
        if fractional:
            row["subframe_applied"] = bool(subframe_applied)
        rows.append(row)
    status = "verified" if all_verified and not quantized_labels else "partial"
    result: dict[str, Any] = {"status": status, "placements": rows}
    if quantized_labels:
        result["subframe_quantized_labels"] = quantized_labels
    return result


def _resolve_subframe_support(
    conn: Any,
    *,
    subframe_mode: str,
    apply: bool,
) -> dict[str, Any] | None:
    """Determine fractional-placement capability for this run.

    auto + apply: use the cached per-version probe verdict, probing once when no
    cache exists (the probe builds and removes a scratch timeline).
    auto + plan-only: cached verdict only — planning must not mutate anything.
    fractional: forced on without probing (explicit user override).
    round/conform: capability is irrelevant.
    """
    mode = str(subframe_mode or "auto").strip().lower()
    if mode in {"round", "conform"}:
        return None
    if mode == "fractional":
        return {"verified_render": True, "forced": True}
    version = subframe_probe._resolve_version(conn) if getattr(conn, "resolve", None) else "unknown"
    cached = subframe_probe.load_cached_probe(version)
    if cached is not None:
        return cached
    if not apply or getattr(conn, "resolve", None) is None:
        return None
    try:
        return subframe_probe.get_subframe_support(conn)
    except Exception:
        return None


def _conform_audio_placements(
    plan: dict[str, Any],
    conn: Any,
    *,
    derived_media_dir: str | None,
    max_derived_media_gb: float,
    apply: bool,
) -> list[dict[str, Any]]:
    """Render conform media for placements that chose the conform mode and
    swap their clips to the derived files. Refusals downgrade to round."""
    actions: list[dict[str, Any]] = []
    budget = audio_conform.ConformRunBudget(max_derived_media_gb)
    fps = float(getattr(conn, "fps", 0) or 0) or 24.0
    for placement in plan["placements"]:
        if placement.get("placement_mode") != "conform":
            continue
        source_path = placement.get("source_path")
        drift_ppm = float(placement.get("drift_ppm") or 0.0)
        drift_span_ms = float(placement.get("drift_span_ms") or 0.0)
        apply_drift = abs(drift_span_ms) >= (500.0 / fps)

        offset_norm = float(placement.get("offset_seconds_normalized") or 0.0)
        if apply_drift:
            # Stretching the file by -drift makes the offset constant, but the
            # constant differs from the midpoint value: with measured model
            # offset(t) = O_mid + s·(t − t_mid), the stretched file aligns at
            # O_const = t_mid − (t_mid − O_mid_raw) / (1 − s) in raw time.
            slope = drift_ppm * 1e-6
            t_mid = float(placement.get("drift_midpoint_seconds") or 0.0)
            min_offset = float(placement.get("min_offset_seconds") or 0.0)
            offset_raw = offset_norm + min_offset
            if abs(1.0 - slope) > 1e-9:
                offset_const_raw = t_mid - (t_mid - offset_raw) / (1.0 - slope)
            else:
                offset_const_raw = offset_raw
            offset_norm = offset_const_raw - min_offset
            frames_int = int(round(offset_norm * fps))
            placement["record_frame"] = int(plan["base_record_frame"] + frames_int)
            placement["offset_frames"] = frames_int
        residual_seconds = offset_norm - float(placement["offset_frames"]) / fps

        if not apply:
            actions.append(
                {
                    "label": placement["label"],
                    "source_path": source_path,
                    "would_conform": True,
                    "residual_ms": residual_seconds * 1000.0,
                    "drift_ppm": -drift_ppm if apply_drift else 0.0,
                }
            )
            continue
        # The conformed file counteracts the measured drift: stretching by
        # -drift cancels the slope against the reference clock.
        outcome = audio_conform.conform_audio(
            str(source_path),
            residual_seconds=residual_seconds,
            drift_ppm=-drift_ppm if apply_drift else 0.0,
            drift_span_ms=drift_span_ms,
            derived_media_dir=derived_media_dir,
            run_budget=budget,
        )
        actions.append({"label": placement["label"], "source_path": source_path, **outcome})
        if not outcome.get("conformed"):
            placement["placement_mode"] = "round"
            placement["conform"] = outcome
            continue
        imported = None
        try:
            imported = conn.media_pool.ImportMedia([outcome["path"]])
        except Exception:
            imported = None
        if imported:
            placement["clip"] = imported[0]
            placement["conformed_path"] = outcome["path"]
            placement["conform"] = outcome
        else:
            placement["placement_mode"] = "round"
            placement["conform"] = {**outcome, "import_failed": True}
    return actions


def execute_sync(
    conn: Any,
    *,
    source_specs: list[str],
    timeline_name: str | None = None,
    create_timeline: bool = False,
    sync_mode: str = "waveform",
    reference_label: str | None = None,
    offset_specs: list[str] | None = None,
    video_track_specs: list[str] | None = None,
    audio_track_specs: list[str] | None = None,
    audio_mode: str = "reference",
    record_frame: str | None = None,
    apply: bool = True,
    subframe_mode: str = "auto",
    derived_media_dir: str | None = None,
    max_derived_media_gb: float = audio_conform.DEFAULT_RUN_BUDGET_GB,
    write_multicam_job: str | None = None,
    write_audio_offsets_json: str | None = None,
    multicam_name: str | None = None,
    multicam_timeline_name: str | None = None,
    multicam_angle_specs: list[str] | None = None,
    multicam_audio_angle_map_specs: list[str] | None = None,
    multicam_audio_target_specs: list[str] | None = None,
    multicam_overlap_angle: str | None = None,
    multicam_default_video_angle: str | None = None,
    multicam_default_audio_angle: str | None = None,
    multicam_sync_anchor: str | None = None,
    multicam_switch_plan: str | None = None,
    use_timecode_prior: bool = False,
) -> dict[str, Any]:
    if apply:
        timeline_action = prepare_target_timeline(conn, timeline_name=timeline_name, create_timeline=create_timeline)
    elif create_timeline:
        timeline_action = {
            "mode": "would_create",
            "timeline": timeline_name,
            "changed": False,
            "created": False,
        }
    elif timeline_name:
        timeline_action = {
            "mode": "would_switch",
            "timeline": timeline_name,
            "changed": False,
            "created": False,
        }
    else:
        timeline_action = {
            "mode": "current",
            "timeline": _timeline_name(conn),
            "changed": False,
            "created": False,
        }
    subframe_support = _resolve_subframe_support(conn, subframe_mode=subframe_mode, apply=apply)
    plan = build_sync_plan(
        conn,
        source_specs=source_specs,
        sync_mode=sync_mode,
        reference_label=reference_label,
        offset_specs=offset_specs,
        video_track_specs=video_track_specs,
        audio_track_specs=audio_track_specs,
        audio_mode=audio_mode,
        record_frame=record_frame,
        subframe_mode=subframe_mode,
        subframe_support=subframe_support,
        use_timecode_prior=use_timecode_prior,
    )
    conform_actions = _conform_audio_placements(
        plan,
        conn,
        derived_media_dir=derived_media_dir,
        max_derived_media_gb=max_derived_media_gb,
        apply=apply,
    )
    if conform_actions:
        plan["sync"]["conform"] = conform_actions
    public_plan = {
        **plan,
        "sources": [_source_public(source) for source in plan["sources"]],
        "placements": [_placement_public(placement) for placement in plan["placements"]],
    }
    multicam_artifacts = build_multicam_artifacts(
        plan,
        write_multicam_job=write_multicam_job,
        write_audio_offsets_json=write_audio_offsets_json,
        multicam_name=multicam_name,
        multicam_timeline_name=multicam_timeline_name,
        multicam_angle_specs=multicam_angle_specs,
        multicam_audio_angle_map_specs=multicam_audio_angle_map_specs,
        multicam_audio_target_specs=multicam_audio_target_specs,
        multicam_overlap_angle=multicam_overlap_angle,
        multicam_default_video_angle=multicam_default_video_angle,
        multicam_default_audio_angle=multicam_default_audio_angle,
        multicam_sync_anchor=multicam_sync_anchor,
        multicam_switch_plan=multicam_switch_plan,
    )
    if not apply:
        result = {
            "changed": False,
            "applied": False,
            "timeline_action": timeline_action,
            "plan": public_plan,
            "append_results": [],
            "verification": {"status": "not_requested"},
        }
        if multicam_artifacts is not None:
            result["multicam_artifacts"] = multicam_artifacts
        return result

    max_video_track = max((int(item["track_index"]) for item in plan["placements"] if item["track_type"] == "video"), default=0)
    max_audio_track = max((int(item["track_index"]) for item in plan["placements"] if item["track_type"] == "audio"), default=0)
    track_preflight = [
        _ensure_track_count(conn, "video", max_video_track),
        _ensure_track_count(conn, "audio", max_audio_track),
    ]
    append_results = []
    for placement in plan["placements"]:
        record_value = placement["record_frame"]
        if placement.get("placement_mode") != "fractional":
            record_value = int(record_value)
        result = media_pool.append_resolved_clip_to_timeline(
            conn,
            placement["clip"],
            name=str(placement.get("name") or placement["label"]),
            folder=placement.get("folder"),
            track_type=str(placement["track_type"]),
            track_index=int(placement["track_index"]),
            absolute_record_frame=record_value,
            return_details=True,
        )
        append_results.append({"placement": _placement_public(placement), "append": result})

    verification = _verify_append_readback(conn, plan["placements"])
    result = {
        "changed": True,
        "applied": True,
        "timeline_action": timeline_action,
        "track_preflight": track_preflight,
        "plan": public_plan,
        "append_results": append_results,
        "verification": verification,
    }
    if multicam_artifacts is not None:
        result["multicam_artifacts"] = multicam_artifacts
    return result
