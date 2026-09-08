from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

from ...errors import ValidationError


SUPPORTED_SYNC_CHANNELS = ("auto", "mix")


def normalize_sync_channel(value: Any) -> str | int:
    if value in (None, ""):
        return "auto"
    if isinstance(value, bool):
        raise ValidationError(
            "Multicam sound sync channel must be auto, mix, or a one-based channel number.",
            details={"sync_channel": value},
        )
    if isinstance(value, int):
        channel = value
    else:
        normalized = str(value).strip().lower().replace("_", "-")
        aliases = {
            "automatic": "auto",
            "auto": "auto",
            "mix": "mix",
            "mixed": "mix",
        }
        if normalized in aliases:
            return aliases[normalized]
        try:
            channel = int(normalized)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "Multicam sound sync channel must be auto, mix, or a one-based channel number.",
                details={"sync_channel": value, "supported_sync_channels": ["auto", "mix", "1+"]},
            ) from exc
    if channel < 1:
        raise ValidationError(
            "Multicam sound sync channel number must be one or greater.",
            details={"sync_channel": channel},
        )
    return channel


def _source_duration(source: Any) -> int:
    value = getattr(source, "duration_frames", None)
    if value is None or int(value) <= 0:
        raise ValidationError(
            "Multicam synchronization requires a positive duration for every source.",
            details={
                "reason": "sync_source_duration_required",
                "angle": getattr(source, "label", None),
                "clip_name": getattr(source, "clip_name", None),
                "duration_frames": value,
            },
        )
    return int(value)


def _source_in(source: Any) -> int:
    explicit = getattr(source, "source_in_frame", None)
    return int(explicit) if explicit is not None else 0


def _item_duration(source: Any, *, source_in: int) -> int:
    explicit = getattr(source, "item_duration_frames", None)
    duration = int(explicit) if explicit is not None else _source_duration(source) - source_in
    if duration <= 0 or source_in + duration > _source_duration(source):
        raise ValidationError(
            "Multicam synchronized source range exceeds the available source media.",
            details={
                "reason": "sync_source_range_out_of_bounds",
                "angle": getattr(source, "label", None),
                "clip_name": getattr(source, "clip_name", None),
                "source_in_frame": source_in,
                "duration_frames": duration,
                "source_duration_frames": _source_duration(source),
            },
        )
    return duration


def _marker_frame(source: Any, *, marker_name: str | None) -> int:
    markers = list(getattr(source, "markers", None) or [])
    if marker_name:
        matches = [
            marker
            for marker in markers
            if str(marker.get("name") or "").strip().casefold() == marker_name.casefold()
        ]
    else:
        matches = markers
    if len(matches) != 1:
        raise ValidationError(
            "Marker sync requires exactly one matching marker on every source in the sync group.",
            details={
                "reason": "sync_marker_not_unique",
                "angle": getattr(source, "label", None),
                "clip_name": getattr(source, "clip_name", None),
                "marker_name": marker_name,
                "matching_markers": matches,
            },
        )
    return int(matches[0]["frame"])


def _sync_point(source: Any, *, sync_mode: str, marker_name: str | None) -> int:
    source_in = _source_in(source)
    duration = _item_duration(source, source_in=source_in)
    if sync_mode == "in":
        return int(getattr(source, "mark_in_frame", None) or source_in)
    if sync_mode == "out":
        mark_out = getattr(source, "mark_out_frame", None)
        return int(mark_out) if mark_out is not None else source_in + duration
    if sync_mode == "marker":
        return _marker_frame(source, marker_name=marker_name)
    raise ValidationError(
        "Unsupported point-based multicam sync mode.",
        details={"sync_mode": sync_mode},
    )


def _local_sync_point(source: Any, *, sync_mode: str, marker_name: str | None) -> int:
    """Return the sync point relative to the item's selected source range."""

    source_in = _source_in(source)
    point = _sync_point(source, sync_mode=sync_mode, marker_name=marker_name)
    duration = _item_duration(source, source_in=source_in)
    if point < source_in or point > source_in + duration:
        raise ValidationError(
            "The multicam synchronization point is outside the selected source range.",
            details={
                "reason": "sync_point_outside_source_range",
                "angle": getattr(source, "label", None),
                "clip_name": getattr(source, "clip_name", None),
                "sync_mode": sync_mode,
                "sync_point_frame": point,
                "source_in_frame": source_in,
                "duration_frames": duration,
            },
        )
    return point - source_in


def _grouped_sources(sources: list[Any]) -> list[tuple[int, list[tuple[int, Any]]]]:
    groups: dict[int, list[tuple[int, Any]]] = defaultdict(list)
    for source_index, source in enumerate(sources):
        groups[int(getattr(source, "item_index", 0) or 0)].append((source_index, source))
    return sorted(groups.items())


def _waveform_group_offsets(
    group: list[tuple[int, Any]],
    *,
    fps: float,
    sync_channel: str | int,
    waveform_offsets_fn: Callable[..., list[int]],
) -> list[int]:
    if len(group) <= 1:
        return [0]
    source_paths = [str(source.source_path) for _index, source in group]
    offsets = waveform_offsets_fn(source_paths, fps=fps, channel=sync_channel)
    if len(offsets) != len(group):
        raise ValidationError(
            "CutAgent waveform sync returned the wrong number of source offsets.",
            details={
                "reason": "waveform_offset_count_mismatch",
                "source_count": len(group),
                "offset_count": len(offsets),
            },
        )
    normalized = [int(value) for value in offsets]
    minimum = min(normalized)
    return [value - minimum for value in normalized]


def build_source_item_timing(
    sources: list[Any],
    *,
    sync_mode: str,
    fps: float,
    sync_channel: str | int = "auto",
    marker_name: str | None = None,
    full_clip_extents: bool = True,
    waveform_offsets_fn: Callable[..., list[int]] | None = None,
) -> dict[str, Any]:
    """Build exact per-source record/source timing with the CutAgent sync engine.

    Repeated clips are grouped by their per-angle item index. Point and waveform
    sync align each simultaneous group, then place the next group after the
    previous group. Timecode sync uses absolute source timecode deltas across all
    sources so real gaps between camera files are preserved.
    """

    normalized_mode = str(sync_mode or "in").strip().lower()
    if normalized_mode not in {"in", "out", "timecode", "sound", "marker"}:
        raise ValidationError(
            "Unsupported multicam sync mode.",
            details={"sync_mode": sync_mode},
        )
    if fps <= 0:
        raise ValidationError("Multicam synchronization requires a positive frame rate.", details={"fps": fps})
    normalized_channel = normalize_sync_channel(sync_channel)
    if normalized_mode == "sound" and waveform_offsets_fn is None:
        raise ValidationError(
            "CutAgent waveform sync is unavailable.",
            details={"reason": "waveform_sync_engine_missing"},
        )

    timing: list[dict[str, int] | None] = [None] * len(sources)
    sync_evidence: list[dict[str, Any]] = []

    if normalized_mode == "timecode":
        start_frames: list[int] = []
        for source in sources:
            media_start_time = getattr(source, "media_start_time", None)
            if media_start_time is None:
                raise ValidationError(
                    "Timecode sync requires readable source start timecode on every source.",
                    details={
                        "reason": "source_timecode_required",
                        "angle": getattr(source, "label", None),
                        "clip_name": getattr(source, "clip_name", None),
                    },
                )
            start_frames.append(int(round(float(media_start_time) * fps)))
        origin = min(start_frames)
        for source_index, (source, absolute_start) in enumerate(zip(sources, start_frames)):
            source_in = _source_in(source)
            duration = _item_duration(source, source_in=source_in)
            explicit_record_start = getattr(source, "record_start_frame", None)
            record_start = (
                int(explicit_record_start)
                if explicit_record_start is not None
                else absolute_start + source_in - origin
            )
            timing[source_index] = {
                "record_start_frame": record_start,
                "source_in_frame": source_in,
                "duration_frames": duration,
            }
            sync_evidence.append(
                {
                    "source_index": source_index,
                    "angle": source.label,
                    "item_index": int(source.item_index),
                    "absolute_timecode_frame": absolute_start,
                    "record_start_frame": record_start,
                }
            )
    else:
        next_group_start = 0
        for group_index, group in _grouped_sources(sources):
            if normalized_mode == "sound":
                relative_offsets = _waveform_group_offsets(
                    group,
                    fps=fps,
                    sync_channel=normalized_channel,
                    waveform_offsets_fn=waveform_offsets_fn,
                )
                sync_points: list[int | None] = [None] * len(group)
            else:
                sync_points = [
                    _local_sync_point(source, sync_mode=normalized_mode, marker_name=marker_name)
                    for _source_index, source in group
                ]
                anchor = max(int(value) for value in sync_points)
                relative_offsets = [anchor - int(value) for value in sync_points]

            group_end = next_group_start
            for group_position, ((source_index, source), relative_offset) in enumerate(zip(group, relative_offsets)):
                source_in = _source_in(source)
                duration = _item_duration(source, source_in=source_in)
                explicit_record_start = getattr(source, "record_start_frame", None)
                record_start = (
                    int(explicit_record_start)
                    if explicit_record_start is not None
                    else next_group_start + int(relative_offset)
                )
                timing[source_index] = {
                    "record_start_frame": record_start,
                    "source_in_frame": source_in,
                    "duration_frames": duration,
                }
                group_end = max(group_end, record_start + duration)
                sync_evidence.append(
                    {
                        "source_index": source_index,
                        "angle": source.label,
                        "item_index": int(source.item_index),
                        "sync_group": group_index,
                        "sync_group_position": group_position,
                        "sync_point_frame": sync_points[group_position],
                        "relative_offset_frame": int(relative_offset),
                        "record_start_frame": record_start,
                    }
                )
            next_group_start = group_end

    resolved_timing = [dict(item or {}) for item in timing]
    if not full_clip_extents and resolved_timing:
        # Match DaVinci Resolve's non-full-extents creation behavior by keeping
        # only the time span in which every logical angle has source coverage.
        # Multiple items on one angle are treated as a union; internal gaps are
        # intentionally retained and therefore cannot be hidden by this trim.
        coverage_by_angle: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for source, item in zip(sources, resolved_timing):
            start = int(item["record_start_frame"])
            coverage_by_angle[str(source.label)].append((start, start + int(item["duration_frames"])))
        overlap_start = max(min(start for start, _end in ranges) for ranges in coverage_by_angle.values())
        overlap_end = min(max(end for _start, end in ranges) for ranges in coverage_by_angle.values())
        if overlap_end <= overlap_start:
            raise ValidationError(
                "The synchronized multicam sources do not share an overlapping extent.",
                details={
                    "reason": "multicam_sources_do_not_overlap",
                    "coverage_by_angle": coverage_by_angle,
                },
            )
        trimmed: list[dict[str, int]] = []
        for source, item in zip(sources, resolved_timing):
            start = int(item["record_start_frame"])
            end = start + int(item["duration_frames"])
            clipped_start = max(start, overlap_start)
            clipped_end = min(end, overlap_end)
            if clipped_end <= clipped_start:
                raise ValidationError(
                    "A synchronized source item falls outside the common multicam extent.",
                    details={
                        "reason": "source_item_outside_common_extent",
                        "angle": source.label,
                        "clip_name": source.clip_name,
                    },
                )
            leading_trim = clipped_start - start
            trimmed.append(
                {
                    "record_start_frame": clipped_start - overlap_start,
                    "source_in_frame": int(item["source_in_frame"]) + leading_trim,
                    "duration_frames": clipped_end - clipped_start,
                }
            )
        resolved_timing = trimmed

    return {
        "sync_mode": normalized_mode,
        "sync_engine": "cutagent_waveform" if normalized_mode == "sound" else "cutagent_timing",
        "sync_channel": normalized_channel if normalized_mode == "sound" else None,
        "marker_name": marker_name if normalized_mode == "marker" else None,
        "full_clip_extents": bool(full_clip_extents),
        "source_item_timing": resolved_timing,
        "evidence": sync_evidence,
    }
