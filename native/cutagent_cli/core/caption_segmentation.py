"""Deterministic transcript segmentation for designed captions."""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from ..errors import ValidationError


_SENTENCE_END_RE = re.compile(r"[.!?\u2026][\"'\u2019\u201d)\]}]*$")
_CLAUSE_END_RE = re.compile(r"[,;:][\"'\u2019\u201d)\]}]*$")
_NO_SPACE_BEFORE_RE = re.compile(r"^[,.;:!?%\u2026)\]}]")
_NO_SPACE_AFTER_RE = re.compile(r"[(\[{\u201c\u2018]$")
_TEXT_KEYS = ("text", "word")
_START_KEYS = ("start", "start_ms", "start_time_ms", "start_time", "startTime")
_END_KEYS = ("end", "end_ms", "end_time_ms", "end_time", "endTime")
_DURATION_KEYS = ("duration", "duration_ms", "durationMs")
_SPEAKER_KEYS = ("speaker_id", "speaker", "speaker_label", "speaker_name", "speakerId", "channel_index")


@dataclass(frozen=True)
class CaptionSegmentationConfig:
    unit: str
    target: int
    preferred_min: int
    preferred_max: int
    hard_max: int
    max_characters_per_line: int
    max_lines: int
    preferred_cps: float
    hard_cps: float
    minimum_duration_seconds: float
    pause_threshold_seconds: float


@dataclass(frozen=True)
class CaptionToken:
    text: str
    start: float
    end: float
    speaker_id: str
    timing_source: str
    source_index: int


@dataclass
class CaptionCue:
    token_start: int
    token_end: int
    start: float
    end: float
    text: str
    speaker_id: str
    boundary_reason: str
    word_count: int
    character_count: int
    cps: float
    timing_source: str
    warnings: list[str] = field(default_factory=list)


def _visible_length(value: str) -> int:
    return len(unicodedata.normalize("NFC", str(value or "")))


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _join_token_texts(values: list[str]) -> str:
    result = ""
    for raw in values:
        value = _clean_text(raw)
        if not value:
            continue
        if not result or _NO_SPACE_BEFORE_RE.search(value) or _NO_SPACE_AFTER_RE.search(result):
            result += value
        else:
            result += f" {value}"
    return result.strip()


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _seconds_from_row(row: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if key not in row:
            continue
        value = _finite_number(row.get(key))
        if value is None:
            continue
        if key.lower().endswith("ms") or key.lower().endswith("_ms"):
            value /= 1000.0
        return value
    return None


def _speaker_id(row: dict[str, Any]) -> str:
    for key in _SPEAKER_KEYS:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            return f"speaker_{int(value)}"
    return "speaker_0"


def _row_text(row: dict[str, Any]) -> str:
    for key in _TEXT_KEYS:
        if isinstance(row.get(key), str):
            return _clean_text(row[key])
    return ""


def _transcript_word_rows(payload: dict[str, Any]) -> list[Any]:
    rows = payload.get("words")
    if isinstance(rows, list) and rows:
        return rows

    nested: list[Any] = []
    for key in ("utterances", "segments", "speaker_turns"):
        parents = payload.get(key)
        if not isinstance(parents, list):
            continue
        for parent in parents:
            if not isinstance(parent, dict) or not isinstance(parent.get("words"), list):
                continue
            parent_speaker = _speaker_id(parent)
            for raw_word in parent["words"]:
                if not isinstance(raw_word, dict):
                    nested.append(raw_word)
                    continue
                word = dict(raw_word)
                if not any(word.get(speaker_key) is not None for speaker_key in _SPEAKER_KEYS):
                    word["speaker_id"] = parent_speaker
                nested.append(word)
        if nested:
            return nested
    return []


def _word_tokens(payload: dict[str, Any]) -> list[CaptionToken]:
    rows = _transcript_word_rows(payload)
    if not rows:
        return []
    entries: list[dict[str, Any]] = []
    for index, raw in enumerate(rows):
        if not isinstance(raw, dict):
            continue
        if str(raw.get("type") or "word").strip().lower() == "spacing":
            continue
        text = _row_text(raw)
        start = _seconds_from_row(raw, _START_KEYS)
        end = _seconds_from_row(raw, _END_KEYS)
        if not text:
            continue
        valid = start is not None and end is not None and end >= start
        entries.append(
            {
                "text": text,
                "start": max(0.0, start) if start is not None else None,
                "end": max(0.0, end) if end is not None else None,
                "valid": valid,
                "speaker_id": _speaker_id(raw),
                "source_index": index,
            }
        )
    if not entries:
        return []

    cursor = 0.0
    index = 0
    while index < len(entries):
        entry = entries[index]
        if entry["valid"]:
            cursor = max(cursor, float(entry["end"]))
            index += 1
            continue
        run_end = index + 1
        while run_end < len(entries) and not entries[run_end]["valid"]:
            run_end += 1
        run = entries[index:run_end]
        left = max(cursor, float(run[0]["start"])) if run[0]["start"] is not None else cursor
        next_start = float(entries[run_end]["start"]) if run_end < len(entries) else None
        right = next_start if next_start is not None and next_start > left else left + 0.3 * len(run)
        weights = [max(1, _visible_length(str(item["text"]))) for item in run]
        total_weight = sum(weights)
        elapsed = 0
        for item, weight in zip(run, weights):
            item["start"] = left + (right - left) * (elapsed / total_weight)
            elapsed += weight
            item["end"] = left + (right - left) * (elapsed / total_weight)
        cursor = right
        index = run_end

    tokens = [
        CaptionToken(
            text=str(entry["text"]),
            start=float(entry["start"]),
            end=float(entry["end"]),
            speaker_id=str(entry["speaker_id"]),
            timing_source="word" if entry["valid"] else "estimated",
            source_index=int(entry["source_index"]),
        )
        for entry in entries
    ]
    return sorted(tokens, key=lambda token: (token.start, token.end, token.source_index))


def _estimated_tokens(payload: dict[str, Any]) -> list[CaptionToken]:
    rows: list[Any] | None = None
    for key in ("utterances", "segments", "speaker_turns"):
        if isinstance(payload.get(key), list):
            rows = payload[key]
            break
    if rows is None:
        raise ValidationError(
            "Caption transcript must contain timed words, utterances, segments, or speaker turns.",
            details={"supported_keys": ["words", "utterances", "segments", "speaker_turns"]},
        )

    tokens: list[CaptionToken] = []
    source_index = 0
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        text = _row_text(raw)
        start = _seconds_from_row(raw, _START_KEYS)
        end = _seconds_from_row(raw, _END_KEYS)
        if end is None and start is not None:
            duration = _seconds_from_row(raw, _DURATION_KEYS)
            if duration is not None:
                end = start + duration
        if not text or start is None or end is None or end < start:
            continue
        words = text.split()
        if not words:
            continue
        weights = [max(1, _visible_length(word)) for word in words]
        total_weight = sum(weights)
        duration = max(0.0, end - start)
        elapsed_weight = 0
        for word, weight in zip(words, weights):
            token_start = start + duration * (elapsed_weight / total_weight)
            elapsed_weight += weight
            token_end = start + duration * (elapsed_weight / total_weight)
            tokens.append(
                CaptionToken(
                    text=word,
                    start=max(0.0, token_start),
                    end=max(0.0, token_end),
                    speaker_id=_speaker_id(raw),
                    timing_source="estimated",
                    source_index=source_index,
                )
            )
            source_index += 1
    if not tokens:
        raise ValidationError("Caption transcript contains no usable timed text.", details={})
    return sorted(tokens, key=lambda token: (token.start, token.end, token.source_index))


def normalize_caption_tokens(payload: dict[str, Any]) -> list[CaptionToken]:
    if not isinstance(payload, dict):
        raise ValidationError("Caption transcript must be a JSON object.", details={})
    tokens = _word_tokens(payload)
    return tokens if tokens else _estimated_tokens(payload)


def normalize_segmentation_config(raw: Any) -> CaptionSegmentationConfig:
    if not isinstance(raw, dict):
        raise ValidationError("Caption segmentation configuration is required.", details={"field": "segmentation"})
    required = (
        "unit",
        "target",
        "preferred_min",
        "preferred_max",
        "hard_max",
        "max_characters_per_line",
        "max_lines",
        "preferred_cps",
        "hard_cps",
        "minimum_duration_seconds",
        "pause_threshold_seconds",
    )
    missing = [key for key in required if raw.get(key) is None]
    if missing:
        raise ValidationError(
            "Caption segmentation configuration must be explicit.",
            details={"missing": missing},
        )
    unit = str(raw.get("unit") or "").strip().lower()
    if unit not in {"words", "characters"}:
        raise ValidationError(
            "Caption segmentation unit must be words or characters.",
            details={"unit": raw.get("unit")},
        )

    integer_values: dict[str, int] = {}
    for key in ("target", "preferred_min", "preferred_max", "hard_max", "max_characters_per_line", "max_lines"):
        value = _finite_number(raw.get(key))
        if value is None or int(value) != value or value < 1:
            raise ValidationError(
                "Caption segmentation integer values must be positive integers.",
                details={"field": key, "value": raw.get(key)},
            )
        integer_values[key] = int(value)
    if not (
        integer_values["preferred_min"]
        <= integer_values["target"]
        <= integer_values["preferred_max"]
        <= integer_values["hard_max"]
    ):
        raise ValidationError(
            "Caption segmentation lengths must satisfy preferred_min <= target <= preferred_max <= hard_max.",
            details={key: integer_values[key] for key in ("preferred_min", "target", "preferred_max", "hard_max")},
        )
    if unit == "characters" and integer_values["hard_max"] > (
        integer_values["max_characters_per_line"] * integer_values["max_lines"]
    ):
        raise ValidationError(
            "Character hard_max cannot exceed the configured line capacity.",
            details={
                "hard_max": integer_values["hard_max"],
                "line_capacity": integer_values["max_characters_per_line"] * integer_values["max_lines"],
            },
        )

    numeric_values: dict[str, float] = {}
    for key in ("preferred_cps", "hard_cps", "minimum_duration_seconds", "pause_threshold_seconds"):
        value = _finite_number(raw.get(key))
        if value is None or value <= 0:
            raise ValidationError(
                "Caption segmentation timing values must be greater than zero.",
                details={"field": key, "value": raw.get(key)},
            )
        numeric_values[key] = value
    if numeric_values["preferred_cps"] > numeric_values["hard_cps"]:
        raise ValidationError(
            "preferred_cps cannot exceed hard_cps.",
            details={"preferred_cps": numeric_values["preferred_cps"], "hard_cps": numeric_values["hard_cps"]},
        )

    return CaptionSegmentationConfig(
        unit=unit,
        target=integer_values["target"],
        preferred_min=integer_values["preferred_min"],
        preferred_max=integer_values["preferred_max"],
        hard_max=integer_values["hard_max"],
        max_characters_per_line=integer_values["max_characters_per_line"],
        max_lines=integer_values["max_lines"],
        preferred_cps=numeric_values["preferred_cps"],
        hard_cps=numeric_values["hard_cps"],
        minimum_duration_seconds=numeric_values["minimum_duration_seconds"],
        pause_threshold_seconds=numeric_values["pause_threshold_seconds"],
    )


def _measure(tokens: list[CaptionToken], unit: str) -> int:
    return len(tokens) if unit == "words" else _visible_length(_join_token_texts([token.text for token in tokens]))


def _line_wrap(tokens: list[CaptionToken], config: CaptionSegmentationConfig) -> tuple[str, list[str]]:
    plain = _join_token_texts([token.text for token in tokens])
    if config.max_lines == 1:
        warnings = ["single_token_exceeds_line_limit"] if _visible_length(plain) > config.max_characters_per_line else []
        return plain, warnings

    count = len(tokens)
    best: tuple[float, list[str]] | None = None

    def visit(start: int, lines: list[str]) -> None:
        nonlocal best
        if start == count:
            lengths = [_visible_length(line) for line in lines]
            if any(length > config.max_characters_per_line for length in lengths):
                return
            score = float(max(lengths, default=0)) + (max(lengths, default=0) - min(lengths, default=0)) * 0.25
            if best is None or score < best[0]:
                best = (score, lines)
            return
        if len(lines) >= config.max_lines:
            return
        for end in range(start + 1, count + 1):
            line = _join_token_texts([token.text for token in tokens[start:end]])
            if _visible_length(line) > config.max_characters_per_line:
                break
            visit(end, [*lines, line])

    visit(0, [])
    if best is not None:
        return "\n".join(best[1]), []
    return plain, ["line_wrap_limit_unmet"]


def _candidate_score(
    tokens: list[CaptionToken],
    end_index: int,
    config: CaptionSegmentationConfig,
    segment_end: int,
) -> tuple[float, str]:
    candidate = tokens[:end_index]
    measure = _measure(candidate, config.unit)
    last = candidate[-1]
    next_token = tokens[end_index] if end_index < len(tokens) else None
    sentence_end = bool(_SENTENCE_END_RE.search(last.text))
    clause_end = bool(_CLAUSE_END_RE.search(last.text))
    speaker_change = bool(next_token and next_token.speaker_id != last.speaker_id)
    pause = max(0.0, next_token.start - last.end) if next_token else 0.0
    pause_boundary = bool(next_token and pause >= config.pause_threshold_seconds)
    duration = max(0.001, last.end - candidate[0].start)
    cps = _visible_length(_join_token_texts([token.text for token in candidate])) / duration

    score = -abs(measure - config.target) * 5.0
    if config.preferred_min <= measure <= config.preferred_max:
        score += 24.0
    if sentence_end:
        score += 100.0
    elif clause_end:
        score += 55.0
    if pause_boundary:
        score += 50.0
    if speaker_change:
        score += 200.0
    if cps > config.preferred_cps:
        score -= min(60.0, (cps - config.preferred_cps) * 3.0)
    if cps > config.hard_cps:
        score -= 40.0
    if segment_end - end_index == 1:
        score -= 65.0
    if end_index == segment_end:
        score += 10.0

    if speaker_change:
        reason = "speaker_change"
    elif sentence_end:
        reason = "sentence_end"
    elif pause_boundary:
        reason = "pause"
    elif clause_end:
        reason = "clause_end"
    elif measure >= config.hard_max:
        reason = "hard_limit"
    else:
        reason = "target_length"
    return score, reason


def _next_cue(tokens: list[CaptionToken], start: int, config: CaptionSegmentationConfig) -> tuple[int, str, list[str]]:
    first = tokens[start]
    segment_end = start + 1
    while segment_end < len(tokens) and tokens[segment_end].speaker_id == first.speaker_id:
        segment_end += 1

    candidates: list[tuple[float, int, str]] = []
    warnings: list[str] = []
    for end in range(start + 1, segment_end + 1):
        candidate = tokens[start:end]
        measure = _measure(candidate, config.unit)
        chars = _visible_length(_join_token_texts([token.text for token in candidate]))
        line_capacity = config.max_characters_per_line * config.max_lines
        if len(candidate) > 1 and (measure > config.hard_max or chars > line_capacity):
            break
        if len(candidate) == 1 and (measure > config.hard_max or chars > line_capacity):
            warnings.append("single_token_exceeds_limit")
        score, reason = _candidate_score(tokens[start:segment_end], end - start, config, segment_end - start)
        if end == segment_end and segment_end < len(tokens) and tokens[segment_end].speaker_id != first.speaker_id:
            reason = "speaker_change"
        candidates.append((score, end, reason))
        if measure >= config.hard_max or chars >= line_capacity:
            break
    if not candidates:
        return start + 1, "hard_limit", ["single_token_exceeds_limit"]
    _, end, reason = max(candidates, key=lambda row: (row[0], row[1]))
    return end, reason, warnings


def segment_caption_payload(payload: dict[str, Any], raw_config: Any) -> dict[str, Any]:
    config = normalize_segmentation_config(raw_config)
    tokens = normalize_caption_tokens(payload)
    cues: list[CaptionCue] = []
    index = 0
    while index < len(tokens):
        end_index, reason, warnings = _next_cue(tokens, index, config)
        cue_tokens = tokens[index:end_index]
        text, wrap_warnings = _line_wrap(cue_tokens, config)
        warnings.extend(wrap_warnings)
        start = cue_tokens[0].start
        end = cue_tokens[-1].end
        timing_sources = {token.timing_source for token in cue_tokens}
        cue = CaptionCue(
            token_start=index,
            token_end=end_index - 1,
            start=start,
            end=end,
            text=text,
            speaker_id=cue_tokens[0].speaker_id,
            boundary_reason=reason,
            word_count=len(cue_tokens),
            character_count=_visible_length(text.replace("\n", " ")),
            cps=0.0,
            timing_source=next(iter(timing_sources)) if len(timing_sources) == 1 else "mixed",
            warnings=list(dict.fromkeys(warnings)),
        )
        cues.append(cue)
        index = end_index

    for cue_index, cue in enumerate(cues):
        next_start = cues[cue_index + 1].start if cue_index + 1 < len(cues) else math.inf
        desired_duration = max(
            config.minimum_duration_seconds,
            cue.character_count / config.hard_cps,
        )
        cue.end = max(cue.end, min(cue.start + desired_duration, next_start))
        duration = max(0.001, cue.end - cue.start)
        cue.cps = cue.character_count / duration
        if duration + 1e-6 < config.minimum_duration_seconds:
            cue.warnings.append("minimum_duration_unmet")
        if cue.cps > config.hard_cps + 1e-6:
            cue.warnings.append("high_cps")
        if cue.timing_source != "word":
            cue.warnings.append("estimated_timing")
        cue.warnings = list(dict.fromkeys(cue.warnings))

    cue_rows = [
        {
            "index": cue_index,
            "token_start": cue.token_start,
            "token_end": cue.token_end,
            "start": round(cue.start, 6),
            "end": round(cue.end, 6),
            "duration": round(cue.end - cue.start, 6),
            "text": cue.text,
            "speaker_id": cue.speaker_id,
            "boundary_reason": cue.boundary_reason,
            "word_count": cue.word_count,
            "character_count": cue.character_count,
            "cps": round(cue.cps, 3),
            "timing_source": cue.timing_source,
            "warnings": cue.warnings,
        }
        for cue_index, cue in enumerate(cues)
    ]
    return {
        "version": "caption_segmentation_v1",
        "config": {
            key: getattr(config, key)
            for key in CaptionSegmentationConfig.__dataclass_fields__
        },
        "token_count": len(tokens),
        "cue_count": len(cue_rows),
        "warning_count": sum(bool(cue["warnings"]) for cue in cue_rows),
        "cues": cue_rows,
    }


def caption_plan_to_batch_items(plan: dict[str, Any], fps: float) -> tuple[list[dict[str, Any]], list[str]]:
    if not math.isfinite(float(fps)) or float(fps) <= 0:
        raise ValidationError("Timeline FPS must be greater than zero.", details={"fps": fps})
    cues = list(plan.get("cues") or [])
    starts: list[int] = []
    warnings: list[str] = []
    for index, cue in enumerate(cues):
        requested = round(float(cue["start"]) * float(fps))
        minimum = starts[-1] + 1 if starts else 0
        start_frame = max(requested, minimum)
        if start_frame != requested:
            warnings.append(f"cue_{index}_start_adjusted_to_avoid_overlap")
        starts.append(start_frame)

    items: list[dict[str, Any]] = []
    for index, cue in enumerate(cues):
        requested_end = round(float(cue["end"]) * float(fps))
        next_start = starts[index + 1] if index + 1 < len(starts) else None
        end_frame = max(starts[index] + 1, requested_end)
        if next_start is not None and end_frame > next_start:
            end_frame = next_start
            warnings.append(f"cue_{index}_end_adjusted_to_avoid_overlap")
        items.append(
            {
                "name": f"Caption {index + 1:03d}",
                "text": str(cue["text"]),
                "at": f"{starts[index]}f",
                "duration": f"{max(1, end_frame - starts[index])}f",
            }
        )
    return items, list(dict.fromkeys(warnings))
