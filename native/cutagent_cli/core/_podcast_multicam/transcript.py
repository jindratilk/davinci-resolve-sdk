from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
import re
from typing import Any, Iterable

from ...errors import ValidationError

_DEFAULT_MERGE_GAP_MS = 250


@dataclass(frozen=True)
class SpeakerSegment:
    speaker_id: str
    start_ms: int
    end_ms: int
    text: str


def _normalize_token(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def _token_set(text: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", str(text or "").lower())
        if token
    }


def _read_json_file(path: str) -> dict[str, Any]:
    expanded = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(expanded):
        raise ValidationError(
            "Transcript file not found.",
            details={"path": expanded},
        )

    try:
        with open(expanded, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "Transcript file is not valid JSON.",
            details={"path": expanded, "error": str(exc)},
        ) from exc

    if not isinstance(payload, dict):
        raise ValidationError(
            "Transcript JSON must be an object.",
            details={"path": expanded},
        )
    return payload


def _extract_speaker(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("speaker_id", "speaker", "speaker_label", "speaker_name", "speakerId"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
            if isinstance(candidate, (int, float)):
                return f"speaker_{int(candidate)}"
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (int, float)):
        return f"speaker_{int(value)}"
    return None


def _extract_ms(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            value = float(stripped)
        except ValueError:
            return None
    if not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    if numeric < 0:
        return None
    if numeric >= 1000:
        return int(round(numeric))
    return int(round(numeric * 1000.0))


def _segment_from_row(row: dict[str, Any]) -> SpeakerSegment | None:
    speaker_id = None
    for key in ("speaker_id", "speaker", "speaker_label", "speaker_name", "speakerId"):
        speaker_id = _extract_speaker(row.get(key))
        if speaker_id:
            break

    start_ms = None
    end_ms = None
    for key in ("start_ms", "start", "start_time_ms", "start_time", "startTime"):
        start_ms = _extract_ms(row.get(key))
        if start_ms is not None:
            break
    for key in ("end_ms", "end", "end_time_ms", "end_time", "endTime"):
        end_ms = _extract_ms(row.get(key))
        if end_ms is not None:
            break

    if end_ms is None:
        duration_ms = None
        for key in ("duration_ms", "duration", "durationMs"):
            duration_ms = _extract_ms(row.get(key))
            if duration_ms is not None:
                break
        if start_ms is not None and duration_ms is not None:
            end_ms = start_ms + duration_ms

    text_value = row.get("text")
    if text_value is None and isinstance(row.get("word"), str):
        text_value = row["word"]
    text = str(text_value or "").strip()

    if not speaker_id or start_ms is None or end_ms is None or end_ms <= start_ms:
        return None
    return SpeakerSegment(speaker_id=speaker_id, start_ms=start_ms, end_ms=end_ms, text=text)


def _segments_from_word_rows(rows: Iterable[dict[str, Any]]) -> list[SpeakerSegment]:
    segments: list[SpeakerSegment] = []
    current: SpeakerSegment | None = None

    for row in rows:
        segment = _segment_from_row(row)
        if segment is None:
            continue

        if current is None:
            current = segment
            continue

        if (
            segment.speaker_id == current.speaker_id
            and segment.start_ms <= current.end_ms + _DEFAULT_MERGE_GAP_MS
        ):
            merged_text = " ".join(part for part in (current.text, segment.text) if part).strip()
            current = SpeakerSegment(
                speaker_id=current.speaker_id,
                start_ms=current.start_ms,
                end_ms=max(current.end_ms, segment.end_ms),
                text=merged_text,
            )
            continue

        segments.append(current)
        current = segment

    if current is not None:
        segments.append(current)
    return segments


def normalize_scribe_v2_transcript(path: str) -> dict[str, Any]:
    """Normalize an ElevenLabs-style JSON transcript into speaker turns."""
    payload = _read_json_file(path)

    candidates: list[SpeakerSegment] = []
    source_key = None

    for key in ("utterances", "segments", "speaker_turns"):
        rows = payload.get(key)
        if isinstance(rows, list):
            candidates = [segment for row in rows if isinstance(row, dict) for segment in [_segment_from_row(row)] if segment]
            source_key = key
            if candidates:
                break

    if not candidates:
        words = payload.get("words")
        if isinstance(words, list):
            candidates = _segments_from_word_rows([row for row in words if isinstance(row, dict)])
            source_key = "words"

    if not candidates:
        raise ValidationError(
            "Transcript does not contain speaker-labelled timed segments.",
            details={
                "path": os.path.abspath(os.path.expanduser(path)),
                "expected_keys": ["utterances", "segments", "speaker_turns", "words"],
            },
        )

    candidates.sort(key=lambda item: (item.start_ms, item.end_ms, item.speaker_id))
    speakers = []
    seen = set()
    for item in candidates:
        if item.speaker_id not in seen:
            speakers.append(item.speaker_id)
            seen.add(item.speaker_id)

    return {
        "format": "elevenlabs_scribe_v2",
        "source_key": source_key,
        "segment_count": len(candidates),
        "speakers": speakers,
        "segments": [asdict(item) for item in candidates],
    }


def _merge_adjacent_segments(
    segments: list[SpeakerSegment],
    *,
    merge_gap_ms: int,
) -> list[SpeakerSegment]:
    merged: list[SpeakerSegment] = []
    for item in segments:
        if not merged:
            merged.append(item)
            continue

        previous = merged[-1]
        if item.speaker_id == previous.speaker_id and item.start_ms <= previous.end_ms + merge_gap_ms:
            merged[-1] = SpeakerSegment(
                speaker_id=previous.speaker_id,
                start_ms=previous.start_ms,
                end_ms=max(previous.end_ms, item.end_ms),
                text=" ".join(part for part in (previous.text, item.text) if part).strip(),
            )
            continue
        merged.append(item)
    return merged


def _coalesce_short_segments(
    segments: list[SpeakerSegment],
    *,
    min_shot_ms: int,
) -> list[SpeakerSegment]:
    if len(segments) < 2:
        return segments

    result: list[SpeakerSegment] = []
    for item in segments:
        duration_ms = item.end_ms - item.start_ms
        if result and duration_ms < min_shot_ms:
            previous = result[-1]
            result[-1] = SpeakerSegment(
                speaker_id=previous.speaker_id,
                start_ms=previous.start_ms,
                end_ms=max(previous.end_ms, item.end_ms),
                text=" ".join(part for part in (previous.text, item.text) if part).strip(),
            )
            continue
        result.append(item)
    return result
