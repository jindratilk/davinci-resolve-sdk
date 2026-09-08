from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SwitchSegment:
    speaker_id: str
    angle: str
    clip_name: str
    start_frame: int
    end_frame: int
    start_tc: str
    end_tc: str
    text: str
    record_start_frame: int | None = None
    record_end_frame: int | None = None
    source_start_frame: int | None = None


@dataclass(frozen=True)
class ResolvedAngleClip:
    label: str
    clip_name: str
    source_path: str
    folder: str
    duration_frames: int | None = None
    fps: float | None = None
    media_start_time: float | None = None
    item_index: int = 0
    record_start_frame: int | None = None
    source_in_frame: int | None = None
    item_duration_frames: int | None = None
    mark_in_frame: int | None = None
    mark_out_frame: int | None = None
    markers: tuple[dict[str, Any], ...] = ()
    audio_mapping: dict[str, Any] | None = None


@dataclass(frozen=True)
class AngleSourceSpec:
    label: str
    clip_name: str
    folder: str | None = None
    source_path: str | None = None
    item_index: int = 0
    record_start_frame: int | None = None
    source_in_frame: int | None = None
    duration_frames: int | None = None


@dataclass(frozen=True)
class NativeSwitchSegmentTemplate:
    position: str
    angle_index: int | None
    start: str
    duration: str
    in_value: str | None
    current_selector_idx: int
    fields_blob: bytes
    media_timemap_ba: bytes | None = None
    effect_filters_ba: bytes | None = None


@dataclass(frozen=True)
class NativeSwitchReferenceFixture:
    schema_family: str
    fixture_version: int
    angle_count: int
    video_segments: list[NativeSwitchSegmentTemplate]
    audio_segments: list[NativeSwitchSegmentTemplate]


def _segment_record_start_frame(segment: SwitchSegment) -> int:
    value = getattr(segment, "record_start_frame", None)
    return int(value) if value is not None else int(segment.start_frame)


def _segment_record_end_frame(segment: SwitchSegment) -> int:
    value = getattr(segment, "record_end_frame", None)
    return int(value) if value is not None else int(segment.end_frame)
