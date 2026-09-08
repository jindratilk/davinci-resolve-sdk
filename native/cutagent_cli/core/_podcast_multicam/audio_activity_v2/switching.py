from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple


def _matches_target(
    segment: Optional[Dict[str, Any]],
    *,
    target_kind: str,
    target_id: Optional[str],
    speaker_id: Optional[str] = None,
) -> bool:
    if not segment:
        return False
    if str(segment.get("target_kind") or "") != str(target_kind or ""):
        return False
    if str(segment.get("target_id") or "") != str(target_id or ""):
        return False
    if target_kind == "speaker":
        return str(segment.get("speaker_id") or "") == str(speaker_id or "")
    return True


def _finalize_window_target(
    window: Dict[str, Any],
    *,
    target_kind: str,
    target_id: str,
    speaker_id: Optional[str],
    reason: str,
    confidence: float,
) -> Dict[str, Any]:
    finalized = dict(window)
    finalized["target_kind"] = target_kind
    finalized["target_id"] = target_id
    if speaker_id:
        finalized["speaker_id"] = speaker_id
    else:
        finalized.pop("speaker_id", None)
    finalized["reason"] = reason
    finalized["confidence"] = confidence
    return finalized


def _resolve_overlap_takeover_candidate(
    window: Dict[str, Any],
    current_target: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Optional[str]]]:
    if not current_target or str(current_target.get("target_kind") or "") != "speaker":
        return None

    current_speaker_id = str(current_target.get("speaker_id") or "").strip()
    current_target_id = str(current_target.get("target_id") or "").strip()
    if not current_speaker_id and not current_target_id:
        return None

    alternatives: Dict[Tuple[str, str], Dict[str, Optional[str]]] = {}
    for source in window.get("sources") or []:
        speaker_id = str(source.get("speaker_id") or "").strip()
        target_id = str(source.get("target_id") or "").strip()
        if not speaker_id and not target_id:
            continue
        if speaker_id and speaker_id == current_speaker_id:
            continue
        if target_id and target_id == current_target_id:
            continue
        key = (speaker_id, target_id)
        alternatives[key] = {
            "speaker_id": speaker_id or None,
            "target_id": target_id or None,
        }

    if len(alternatives) != 1:
        return None
    candidate = next(iter(alternatives.values()))
    if not candidate.get("target_id"):
        return None
    return candidate


def _peek_next_speaker_candidate(
    raw_windows: Sequence[Dict[str, Any]],
    start_index: int,
) -> Optional[Dict[str, Any]]:
    for lookahead_index in range(start_index + 1, len(raw_windows)):
        candidate = raw_windows[lookahead_index]
        candidate_kind = str(candidate.get("candidate_kind") or "")
        if candidate_kind == "hold":
            continue
        if candidate_kind != "speaker":
            return None
        return candidate
    return None


def _apply_switch_state_machine(
    raw_windows: Sequence[Dict[str, Any]],
    *,
    wide_camera_id: str,
    switch_delay_seconds: float,
    silence_transition_anticipation_seconds: float = 1.0,
    initial_confidence: float = 0.6,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    final_windows: List[Dict[str, Any]] = []
    metrics = {
        "delayed_switches": 0,
        "suppressed_interjections": 0,
        "backfilled_switch_windows": 0,
    }
    current_target: Optional[Dict[str, Any]] = None
    pending_target: Optional[Dict[str, Any]] = None

    for window_index, window in enumerate(raw_windows):
        candidate_kind = str(window.get("candidate_kind") or "")
        candidate_id = str(window.get("candidate_target_id") or "")
        candidate_speaker = str(window.get("candidate_speaker_id") or "") or None
        candidate_reason = str(window.get("candidate_reason") or "")
        candidate_confidence = float(window.get("candidate_confidence") or 0.0)

        if candidate_kind == "wide":
            overlap_takeover = _resolve_overlap_takeover_candidate(window, current_target)
            if overlap_takeover:
                takeover_target_id = str(overlap_takeover.get("target_id") or "")
                takeover_speaker_id = str(overlap_takeover.get("speaker_id") or "") or None
                if _matches_target(
                    pending_target,
                    target_kind="speaker",
                    target_id=takeover_target_id,
                    speaker_id=takeover_speaker_id,
                ):
                    pending_target["end"] = float(window.get("end") or pending_target.get("end") or 0.0)
                else:
                    pending_target = {
                        "target_kind": "speaker",
                        "target_id": takeover_target_id,
                        "speaker_id": takeover_speaker_id,
                        "start": float(window.get("start") or 0.0),
                        "end": float(window.get("end") or 0.0),
                        "start_index": len(final_windows),
                        "pending_mode": "overlap_takeover",
                    }

                final_windows.append(
                    _finalize_window_target(
                        window,
                        target_kind="wide",
                        target_id=wide_camera_id,
                        speaker_id=None,
                        reason="overlap_pending_takeover",
                        confidence=max(candidate_confidence, 0.7),
                    )
                )
                continue

            current_target = {
                "target_kind": "wide",
                "target_id": wide_camera_id,
                "speaker_id": None,
            }
            pending_target = None
            final_windows.append(
                _finalize_window_target(
                    window,
                    target_kind="wide",
                    target_id=wide_camera_id,
                    speaker_id=None,
                    reason=candidate_reason or "overlap_wide",
                    confidence=max(candidate_confidence, 0.7),
                )
            )
            continue

        if candidate_kind == "speaker":
            candidate_target = {
                "target_kind": "speaker",
                "target_id": candidate_id,
                "speaker_id": candidate_speaker,
            }
            if current_target is None:
                current_target = dict(candidate_target)
                pending_target = None
                final_windows.append(
                    _finalize_window_target(
                        window,
                        target_kind="speaker",
                        target_id=candidate_id,
                        speaker_id=candidate_speaker,
                        reason="initial_speaker_lock",
                        confidence=max(candidate_confidence, initial_confidence),
                    )
                )
                continue

            if _matches_target(current_target, target_kind="speaker", target_id=candidate_id, speaker_id=candidate_speaker):
                pending_target = None
                final_windows.append(
                    _finalize_window_target(
                        window,
                        target_kind="speaker",
                        target_id=candidate_id,
                        speaker_id=candidate_speaker,
                        reason=candidate_reason or "speaker_continues",
                        confidence=max(candidate_confidence, initial_confidence),
                    )
                )
                continue

            if _matches_target(pending_target, target_kind="speaker", target_id=candidate_id, speaker_id=candidate_speaker):
                pending_target["end"] = float(window.get("end") or pending_target.get("end") or 0.0)
            else:
                pending_target = {
                    "target_kind": "speaker",
                    "target_id": candidate_id,
                    "speaker_id": candidate_speaker,
                    "start": float(window.get("start") or 0.0),
                    "end": float(window.get("end") or 0.0),
                    "start_index": len(final_windows),
                }

            final_windows.append(
                _finalize_window_target(
                    window,
                    target_kind=str(current_target.get("target_kind") or "wide"),
                    target_id=str(current_target.get("target_id") or wide_camera_id),
                    speaker_id=current_target.get("speaker_id"),
                    reason="waiting_for_switch_delay",
                    confidence=max(float(window.get("candidate_confidence") or 0.0), 0.45),
                )
            )

            pending_duration = max(0.0, float(pending_target.get("end") or 0.0) - float(pending_target.get("start") or 0.0))
            if pending_duration >= switch_delay_seconds:
                start_index = max(0, int(pending_target.get("start_index") or len(final_windows) - 1))
                for pending_index in range(start_index, len(final_windows)):
                    final_windows[pending_index] = _finalize_window_target(
                        final_windows[pending_index],
                        target_kind="speaker",
                        target_id=candidate_id,
                        speaker_id=candidate_speaker,
                        reason="confirmed_speaker_switch_backfilled",
                        confidence=max(float(final_windows[pending_index].get("candidate_confidence") or 0.0), candidate_confidence, initial_confidence),
                    )
                current_target = dict(candidate_target)
                pending_target = None
                metrics["delayed_switches"] += 1
                metrics["backfilled_switch_windows"] += max(0, len(final_windows) - start_index)
            continue

        pending_target = None
        if current_target is not None:
            is_silence_hold = "silence" in candidate_reason.casefold()
            next_candidate = _peek_next_speaker_candidate(raw_windows, window_index)
            if (
                is_silence_hold
                and next_candidate is not None
                and str(current_target.get("target_kind") or "") == "speaker"
                and str(next_candidate.get("candidate_target_id") or "") != str(current_target.get("target_id") or "")
                and (
                    float(next_candidate.get("start") or 0.0) - float(window.get("start") or 0.0)
                    <= max(silence_transition_anticipation_seconds, 0.0)
                )
            ):
                next_target_id = str(next_candidate.get("candidate_target_id") or "")
                next_speaker_id = str(next_candidate.get("candidate_speaker_id") or "") or None
                final_windows.append(
                    _finalize_window_target(
                        window,
                        target_kind="speaker",
                        target_id=next_target_id,
                        speaker_id=next_speaker_id,
                        reason="anticipating_next_speaker_across_pause",
                        confidence=max(float(next_candidate.get("candidate_confidence") or 0.0), 0.5),
                    )
                )
                continue
            if not is_silence_hold:
                final_windows.append(
                    _finalize_window_target(
                        window,
                        target_kind=str(current_target.get("target_kind") or "wide"),
                        target_id=str(current_target.get("target_id") or wide_camera_id),
                        speaker_id=current_target.get("speaker_id"),
                        reason=candidate_reason or "hold_previous_target",
                        confidence=max(float(window.get("candidate_confidence") or 0.0), 0.45),
                    )
                )
                continue
            final_windows.append(
                _finalize_window_target(
                    window,
                    target_kind="wide",
                    target_id=wide_camera_id,
                    speaker_id=None,
                    reason=str(window.get("candidate_reason") or "silence"),
                    confidence=max(float(window.get("candidate_confidence") or 0.0), 0.45),
                )
            )
            continue

        final_windows.append(
            _finalize_window_target(
                window,
                target_kind="wide",
                target_id=wide_camera_id,
                speaker_id=None,
                reason=str(window.get("candidate_reason") or "initial_silence_wide"),
                confidence=max(float(window.get("candidate_confidence") or 0.0), 0.35),
            )
        )

    return final_windows, metrics
