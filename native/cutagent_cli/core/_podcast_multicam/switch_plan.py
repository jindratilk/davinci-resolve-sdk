from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ...errors import ValidationError
from .transcript import (
    SpeakerSegment,
    _coalesce_short_segments,
    _merge_adjacent_segments,
    _normalize_token,
    _token_set,
)


def parse_speaker_mapping(mapping: str | None) -> dict[str, str]:
    if not mapping:
        return {}
    parsed: dict[str, str] = {}
    for raw_entry in str(mapping).split(","):
        entry = raw_entry.strip()
        if not entry:
            continue
        if "=" not in entry:
            raise ValidationError(
                "Speaker mapping must use speaker=angle pairs.",
                details={"entry": entry, "mapping": mapping},
            )
        speaker_id, angle = [part.strip() for part in entry.split("=", 1)]
        if not speaker_id or not angle:
            raise ValidationError(
                "Speaker mapping must use non-empty speaker=angle pairs.",
                details={"entry": entry, "mapping": mapping},
            )
        parsed[speaker_id] = angle
    return parsed


def infer_speaker_camera_mapping(
    *,
    segments: list[dict[str, Any]] | list[SpeakerSegment],
    angle_map: dict[str, str],
) -> dict[str, Any]:
    speakers = []
    for item in segments:
        speaker_id = item.speaker_id if isinstance(item, SpeakerSegment) else str(item.get("speaker_id", "")).strip()
        if speaker_id and speaker_id not in speakers:
            speakers.append(speaker_id)

    angles = sorted(angle_map.keys())
    if not speakers:
        raise ValidationError("Transcript normalization produced no speakers.")
    if not angles:
        raise ValidationError("At least one multicam angle is required.")

    scored: list[tuple[float, str, str]] = []
    for speaker_id in speakers:
        speaker_tokens = _token_set(speaker_id)
        speaker_compact = _normalize_token(speaker_id)
        for angle in angles:
            clip_name = angle_map[angle]
            score = 0.0
            clip_tokens = _token_set(clip_name)
            angle_token = _normalize_token(angle)
            if speaker_compact == angle_token:
                score = 1.0
            elif speaker_compact and speaker_compact in _normalize_token(clip_name):
                score = 0.95
            elif speaker_tokens and clip_tokens:
                overlap = len(speaker_tokens & clip_tokens)
                if overlap:
                    score = 0.6 + min(0.3, overlap * 0.1)
            scored.append((score, speaker_id, angle))

    mapping: dict[str, str] = {}
    confidence = 1.0
    unresolved: list[str] = []
    used_angles: set[str] = set()

    for speaker_id in speakers:
        candidates = sorted(
            [(score, angle) for score, candidate_speaker, angle in scored if candidate_speaker == speaker_id],
            key=lambda item: (-item[0], item[1]),
        )
        best_score, best_angle = candidates[0]
        if best_score >= 0.9 and best_angle not in used_angles:
            mapping[speaker_id] = best_angle
            used_angles.add(best_angle)
            confidence = min(confidence, best_score)
        else:
            unresolved.append(speaker_id)

    if not unresolved and len(mapping) == len(speakers):
        return {
            "mapping": mapping,
            "confidence": round(confidence, 3),
            "needs_clarification": False,
            "candidate_mappings": [],
        }

    if len(speakers) == len(angles):
        default_mapping = {speaker_id: angle for speaker_id, angle in zip(sorted(speakers), angles)}
        return {
            "mapping": default_mapping,
            "confidence": 0.35,
            "needs_clarification": True,
            "candidate_mappings": [
                {
                    "strategy": "sorted_default",
                    "mapping": default_mapping,
                },
                {
                    "strategy": "sorted_reverse",
                    "mapping": {speaker_id: angle for speaker_id, angle in zip(sorted(speakers), list(reversed(angles)))},
                },
            ],
            "unresolved_speakers": unresolved or speakers,
        }

    raise ValidationError(
        "Could not infer a safe speaker-to-camera mapping.",
        details={
            "speakers": speakers,
            "angles": angles,
            "candidate_mappings": [
                {
                    "strategy": "identity_if_provided",
                    "mapping": {speaker_id: None for speaker_id in speakers},
                }
            ],
        },
    )


def build_switch_plan(
    *,
    conn,
    transcript_segments: list[dict[str, Any]],
    angle_map: dict[str, str],
    speaker_map: dict[str, str],
    switch_segment_cls: type,
    frames_to_timecode_fn,
    min_shot_ms: int,
    merge_gap_ms: int,
    max_end_frame: int | None = None,
) -> dict[str, Any]:
    base_start_frame = int(getattr(conn, "start_frame", 0) or 0)
    segments = [
        SpeakerSegment(
            speaker_id=str(row["speaker_id"]),
            start_ms=int(row["start_ms"]),
            end_ms=int(row["end_ms"]),
            text=str(row.get("text", "")),
        )
        for row in transcript_segments
    ]
    segments = _merge_adjacent_segments(segments, merge_gap_ms=merge_gap_ms)
    segments = _coalesce_short_segments(segments, min_shot_ms=min_shot_ms)

    planned = []
    for item in segments:
        angle = speaker_map.get(item.speaker_id)
        if not angle:
            raise ValidationError(
                "Missing speaker-to-angle mapping for transcript segment.",
                details={"speaker_id": item.speaker_id, "mapping": speaker_map},
            )
        clip_name = angle_map.get(angle)
        if not clip_name:
            raise ValidationError(
                "Speaker mapping points to an unknown multicam angle.",
                details={"speaker_id": item.speaker_id, "angle": angle, "angles": angle_map},
            )

        start_frame = base_start_frame + int(round(item.start_ms * conn.fps / 1000.0))
        end_frame = base_start_frame + int(round(item.end_ms * conn.fps / 1000.0))
        if max_end_frame is not None:
            start_frame = min(start_frame, max_end_frame)
            end_frame = min(end_frame, max_end_frame)
        if end_frame <= start_frame:
            continue
        planned.append(
            switch_segment_cls(
                speaker_id=item.speaker_id,
                angle=angle,
                clip_name=clip_name,
                start_frame=start_frame,
                end_frame=end_frame,
                start_tc=frames_to_timecode_fn(start_frame, conn.fps),
                end_tc=frames_to_timecode_fn(end_frame, conn.fps),
                text=item.text,
            )
        )

    if not planned:
        raise ValidationError("Transcript did not produce any usable switch segments.")

    return {
        "segment_count": len(planned),
        "segments": [asdict(item) for item in planned],
        "angle_order": list(angle_map.keys()),
        "base_start_frame": base_start_frame,
        "min_shot_ms": min_shot_ms,
        "merge_gap_ms": merge_gap_ms,
        "max_end_frame": max_end_frame,
    }
