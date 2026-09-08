"""Helpers for temporary track lock isolation during native Text+ insertion."""

from __future__ import annotations

import time
from typing import Any

LOCK_READBACK_ATTEMPTS = 8
LOCK_READBACK_DELAY_SECONDS = 0.1


def _track_count(timeline: Any, track_type: str) -> tuple[int, str | None]:
    try:
        return int(timeline.GetTrackCount(track_type) or 0), None
    except Exception as exc:
        return 0, str(exc)


def _read_track_lock(getter: Any, track_type: str, index: int) -> tuple[bool | None, str | None]:
    try:
        return bool(getter(track_type, index)), None
    except Exception as exc:
        return None, str(exc)


def _wait_for_track_lock_state(
    getter: Any,
    track_type: str,
    index: int,
    target_locked: bool,
    *,
    attempts: int = LOCK_READBACK_ATTEMPTS,
    delay_seconds: float = LOCK_READBACK_DELAY_SECONDS,
) -> tuple[bool | None, bool, list[dict[str, Any]], str | None]:
    readbacks: list[dict[str, Any]] = []
    last_value: bool | None = None
    last_error: str | None = None
    for attempt in range(1, max(1, int(attempts)) + 1):
        value, error = _read_track_lock(getter, track_type, index)
        last_value = value
        last_error = error
        readbacks.append({"attempt": attempt, "locked": value, "error": error})
        if error is None and value == bool(target_locked):
            return value, True, readbacks, None
        if attempt < attempts:
            time.sleep(max(0.0, float(delay_seconds)))
    return last_value, False, readbacks, last_error


def set_video_track_locks_for_textplus(
    conn: Any,
    selected_track: int,
    *,
    include_auxiliary_tracks: bool = False,
) -> dict[str, Any]:
    timeline = getattr(conn, "timeline", None)
    getter = getattr(timeline, "GetIsTrackLocked", None)
    setter = getattr(timeline, "SetTrackLock", None)
    if not callable(getter):
        return {
            "attempted": False,
            "verified": False,
            "restorable": False,
            "reason": "Timeline.GetIsTrackLocked unavailable",
            "tracks": [],
        }
    if not callable(setter):
        return {
            "attempted": False,
            "verified": False,
            "restorable": False,
            "reason": "Timeline.SetTrackLock unavailable",
            "tracks": [],
        }
    track_count, count_error = _track_count(timeline, "video")
    if count_error:
        return {
            "attempted": False,
            "verified": False,
            "restorable": False,
            "reason": count_error,
            "tracks": [],
        }
    if int(selected_track) < 1 or int(selected_track) > track_count:
        return {
            "attempted": False,
            "verified": False,
            "restorable": False,
            "reason": "Selected Text+ template track is outside the verified video track range.",
            "selected_track": int(selected_track),
            "track_count": track_count,
            "tracks": [],
        }

    lock_targets: list[tuple[str, int, bool]] = [("video", index, index != int(selected_track)) for index in range(1, track_count + 1)]
    auxiliary_counts: dict[str, int] = {}
    auxiliary_errors: dict[str, str] = {}
    for track_type in ("audio", "subtitle"):
        aux_count, aux_error = _track_count(timeline, track_type)
        auxiliary_counts[track_type] = aux_count
        if aux_error:
            auxiliary_errors[track_type] = aux_error
        elif include_auxiliary_tracks:
            lock_targets.extend((track_type, index, True) for index in range(1, aux_count + 1))

    rows: list[dict[str, Any]] = []
    for track_type, index, target_locked in lock_targets:
        try:
            previous = bool(getter(track_type, index))
        except Exception as exc:
            return {
                "attempted": bool(rows),
                "verified": False,
                "restorable": bool(rows) and all(row.get("previous_locked") is not None for row in rows),
                "reason": f"Unable to read current {track_type} track lock state.",
                "error": str(exc),
                "error_track_type": track_type,
                "error_track": index,
                "tracks": rows,
            }
        applied = None
        error = None
        readback = previous
        verified = previous == target_locked
        readback_attempts: list[dict[str, Any]] = [{"attempt": 0, "locked": previous, "error": None}]
        if previous is None or previous != target_locked:
            try:
                applied = setter(track_type, index, target_locked)
            except Exception as exc:
                error = str(exc)
            if error is None and applied is not False:
                readback, verified_readback, readback_attempts, read_error = _wait_for_track_lock_state(
                    getter,
                    track_type,
                    index,
                    target_locked,
                )
                if read_error:
                    error = read_error
                verified = bool(verified_readback and readback == target_locked)
            else:
                verified = False
        rows.append(
            {
                "track_type": track_type,
                "track": index,
                "previous_locked": previous,
                "target_locked": target_locked,
                "readback_locked": readback,
                "readback_attempt_count": len(readback_attempts),
                "readback_attempts": readback_attempts,
                "api_result": applied,
                "error": error,
                "changed": previous != target_locked,
                "verified": verified,
                "restorable": previous is not None,
            }
        )
    verified = all(bool(row.get("verified")) for row in rows)
    restorable = all(row.get("previous_locked") is not None for row in rows)
    return {
        "attempted": True,
        "verified": verified,
        "restorable": restorable,
        "selected_video_track": int(selected_track),
        "video_track_count": track_count,
        "auxiliary_track_counts": auxiliary_counts,
        "auxiliary_track_errors": auxiliary_errors,
        "auxiliary_tracks_locked": bool(include_auxiliary_tracks),
        "tracks": rows,
    }


def set_timeline_track_locks_for_textplus_batch(conn: Any, selected_track: int) -> dict[str, Any]:
    """Lock every non-target timeline track before direct Text+ batch insertion."""
    return set_video_track_locks_for_textplus(conn, selected_track, include_auxiliary_tracks=True)


def restore_video_track_locks(conn: Any, snapshot: dict[str, Any]) -> dict[str, Any]:
    snapshot_tracks = snapshot.get("tracks") or []
    if not snapshot.get("attempted") and not snapshot_tracks:
        return {"attempted": False, "restored": False, "tracks": []}
    timeline = getattr(conn, "timeline", None)
    getter = getattr(timeline, "GetIsTrackLocked", None)
    setter = getattr(timeline, "SetTrackLock", None)
    if not callable(setter):
        return {"attempted": True, "restored": False, "reason": "Timeline.SetTrackLock unavailable", "tracks": []}
    rows: list[dict[str, Any]] = []
    for row in snapshot_tracks:
        previous = row.get("previous_locked")
        track_type = str(row.get("track_type") or "video")
        if previous is None:
            rows.append(
                {
                    "track_type": track_type,
                    "track": int(row.get("track", 0) or 0),
                    "restored_locked": None,
                    "readback_locked": None,
                    "api_result": None,
                    "verified": False,
                    "error": "previous lock state unavailable",
                }
            )
            continue
        try:
            result = setter(track_type, int(row["track"]), bool(previous))
            readback = None
            readback_attempts: list[dict[str, Any]] = []
            read_error = None
            if callable(getter) and result is not False:
                readback, verified_readback, readback_attempts, read_error = _wait_for_track_lock_state(
                    getter,
                    track_type,
                    int(row["track"]),
                    bool(previous),
                )
                verified = bool(verified_readback and readback == bool(previous))
            else:
                verified = bool(result is not False)
            rows.append(
                {
                    "track_type": track_type,
                    "track": int(row["track"]),
                    "restored_locked": bool(previous),
                    "readback_locked": readback,
                    "readback_attempt_count": len(readback_attempts),
                    "readback_attempts": readback_attempts,
                    "api_result": result,
                    "verified": verified,
                    "error": None if verified else (read_error or "track lock restore readback mismatch"),
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "track_type": track_type,
                    "track": int(row["track"]),
                    "restored_locked": bool(previous),
                    "readback_locked": None,
                    "api_result": None,
                    "verified": False,
                    "error": str(exc),
                }
            )
    return {"attempted": True, "restored": bool(rows) and all(bool(row.get("verified")) for row in rows), "tracks": rows}


def track_lock_setup_errors(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if not snapshot.get("attempted"):
        errors.append({"reason": snapshot.get("reason") or "track lock setup was not attempted"})
        return errors
    if not snapshot.get("verified"):
        errors.append({"reason": "track lock setup did not verify"})
    if not snapshot.get("restorable"):
        errors.append({"reason": "track lock setup is not safely restorable"})
    for row in snapshot.get("tracks") or []:
        if not row.get("verified"):
            errors.append(
                {
                    "track_type": row.get("track_type") or "video",
                    "track": row.get("track"),
                    "reason": row.get("error") or "track lock readback mismatch",
                    "target_locked": row.get("target_locked"),
                    "readback_locked": row.get("readback_locked"),
                    "api_result": row.get("api_result"),
                }
            )
        if row.get("previous_locked") is None:
            errors.append(
                {
                    "track_type": row.get("track_type") or "video",
                    "track": row.get("track"),
                    "reason": "previous lock state unavailable",
                }
            )
    return errors
