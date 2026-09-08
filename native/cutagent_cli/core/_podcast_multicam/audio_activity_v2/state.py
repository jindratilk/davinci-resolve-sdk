from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from cutagent_cli.core._podcast_multicam.audio_activity_v2.segments import _segment_duration


def _speaker_camera_lookup(speaker_map: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    for item in speaker_map or []:
        speaker_id = str(item.get("speaker_id") or item.get("speaker") or "").strip()
        if not speaker_id:
            continue
        lookup[speaker_id] = dict(item)
    return lookup


def _resolve_speaker_target(
    audio_file: str,
    speaker_map: Sequence[Dict[str, Any]],
    lookup: Dict[str, Dict[str, Any]],
) -> Tuple[Optional[str], str]:
    resolved_audio = str(Path(audio_file).expanduser())
    speaker_id = None

    for candidate in speaker_map or []:
        mic_path = str(candidate.get("mic_file") or candidate.get("audio_file") or "").strip()
        if mic_path and str(Path(mic_path).expanduser()) == resolved_audio:
            speaker_id = str(candidate.get("speaker_id") or "").strip()
            break

    if not speaker_id:
        for candidate in speaker_map or []:
            audio_path = str(candidate.get("audio_file") or "").strip()
            if audio_path and str(Path(audio_path).expanduser()) == resolved_audio:
                speaker_id = str(candidate.get("speaker_id") or "").strip()
                break

    speaker_info = lookup.get(speaker_id or "")
    target_id = None
    if speaker_info:
        target_id = (
            speaker_info.get("camera_file")
            or speaker_info.get("camera")
            or speaker_info.get("camera_name")
            or speaker_info.get("camera_asset_id")
            or speaker_info.get("camera_id")
        )
    if not target_id:
        target_id = speaker_id or resolved_audio
    return speaker_id, str(target_id)


def _suppress_short_interjection_segments(
    segments: List[Dict[str, Any]],
    *,
    short_interjection_max_seconds: float,
) -> Tuple[List[Dict[str, Any]], int]:
    stabilized = [dict(segment) for segment in segments]
    suppressed = 0
    if len(stabilized) < 3:
        return stabilized, suppressed

    for index in range(1, len(stabilized) - 1):
        current = stabilized[index]
        previous = stabilized[index - 1]
        following = stabilized[index + 1]
        if _segment_duration(current) > short_interjection_max_seconds:
            continue
        if str(previous.get("target_kind") or "") != "speaker" or str(following.get("target_kind") or "") != "speaker":
            continue
        if previous.get("target_id") != following.get("target_id"):
            continue
        if previous.get("speaker_id") != following.get("speaker_id"):
            continue
        if current.get("target_id") == previous.get("target_id") and current.get("speaker_id") == previous.get("speaker_id"):
            continue

        current["target_id"] = previous.get("target_id")
        current["target_kind"] = previous.get("target_kind")
        current["speaker_id"] = previous.get("speaker_id")
        current["reason"] = "suppressed_short_interjection"
        current["confidence"] = max(float(current.get("confidence") or 0.0), 0.55)
        suppressed += 1

    return stabilized, suppressed


def _collapse_unbalanced_wide_segments(
    segments: List[Dict[str, Any]],
    *,
    min_secondary_lead_share: float = 0.35,
) -> Tuple[List[Dict[str, Any]], int]:
    stabilized = [dict(segment) for segment in segments]
    collapsed = 0
    if not stabilized:
        return stabilized, collapsed

    for current in stabilized:
        if str(current.get("target_kind") or "") != "wide":
            continue
        if not (current.get("sources") or []):
            continue
        if str(current.get("reason") or "") not in {"overlap_pending_takeover", "overlap_wide"}:
            continue

        sources = list(current.get("sources") or [])
        if len(sources) < 2:
            continue

        leader_ids: List[str] = []
        for source_index in range(0, len(sources), 2):
            pair = sources[source_index : source_index + 2]
            if not pair:
                continue
            leader_id = str(pair[0].get("speaker_id") or pair[0].get("target_id") or "").strip()
            if leader_id:
                leader_ids.append(leader_id)

        if not leader_ids:
            continue

        counts = Counter(leader_ids)
        dominant_leader_id, _count = counts.most_common(1)[0]
        if len(counts) >= 2:
            total = sum(counts.values())
            minority_share = min(counts.values()) / float(total or 1)
            if minority_share >= min_secondary_lead_share:
                continue

        dominant_source = next(
            (
                source
                for source in sources
                if str(source.get("speaker_id") or source.get("target_id") or "").strip() == dominant_leader_id
            ),
            None,
        )
        if not dominant_source:
            continue

        dominant_target_id = str(dominant_source.get("target_id") or "").strip()
        dominant_speaker_id = str(dominant_source.get("speaker_id") or "").strip()
        if not dominant_target_id:
            continue

        current["target_id"] = dominant_target_id
        current["target_kind"] = "speaker"
        current["speaker_id"] = dominant_speaker_id or None
        current["reason"] = "collapsed_unbalanced_wide"
        current["confidence"] = max(float(current.get("confidence") or 0.0), 0.65)
        collapsed += 1

    return stabilized, collapsed
