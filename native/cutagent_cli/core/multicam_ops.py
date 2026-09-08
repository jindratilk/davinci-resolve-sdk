"""Deterministic multicam orchestration via timeline operations."""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import APICallFailed, ClipNotFound, ValidationError
from ..utils.time_ref import parse_record_frame
from . import edit_ops, timeline_ops


@dataclass(frozen=True)
class AngleSpec:
    label: str
    clip_name: str


@dataclass(frozen=True)
class SwitchSpec:
    frame: int
    label: str


def _split_csv_tokens(raw: str) -> list[str]:
    return [token.strip() for token in raw.split(",") if token.strip()]


def _timeline_start_frame(conn) -> int:
    if hasattr(conn.timeline, "GetStartFrame"):
        return int(conn.timeline.GetStartFrame())
    return 0


def parse_angles_spec(raw: str) -> list[AngleSpec]:
    if not raw or not raw.strip():
        raise ValidationError("Angles spec is required.", details={"angles": raw})

    out: list[AngleSpec] = []
    seen = set()
    for token in _split_csv_tokens(raw):
        if "=" not in token:
            raise ValidationError(
                "Invalid angles spec token. Expected format LABEL=clip_name.",
                details={"token": token},
            )
        label, clip_name = token.split("=", 1)
        label = label.strip()
        clip_name = clip_name.strip()
        if not label or not clip_name:
            raise ValidationError("Invalid angles spec token.", details={"token": token})
        if label in seen:
            raise ValidationError("Duplicate angle label.", details={"label": label})
        seen.add(label)
        out.append(AngleSpec(label=label, clip_name=clip_name))

    if len(out) < 2:
        raise ValidationError("Multicam requires at least 2 angles.", details={"count": len(out)})
    return out


def parse_switches_spec(raw: str, fps: float, start_frame: int) -> list[SwitchSpec]:
    if not raw or not raw.strip():
        raise ValidationError("Switches spec is required.", details={"switches": raw})

    out: list[SwitchSpec] = []
    for token in _split_csv_tokens(raw):
        if ":" not in token:
            raise ValidationError(
                "Invalid switches token. Expected <frame_or_time>:<label>.",
                details={"token": token},
            )
        frame_raw, label = token.rsplit(":", 1)
        label = label.strip()
        if not label:
            raise ValidationError("Switch label cannot be empty.", details={"token": token})
        frame = parse_record_frame(frame_raw.strip(), fps, start_frame)
        out.append(SwitchSpec(frame=frame, label=label))

    out = sorted(out, key=lambda s: s.frame)
    if not out:
        raise ValidationError("Switches spec produced no entries.")
    if out[0].frame < start_frame:
        raise ValidationError("Switch frame must not be before timeline start.")
    return out


def _search_folder(folder, name: str):
    clips = folder.GetClipList() or []
    for clip in clips:
        if hasattr(clip, "GetName") and clip.GetName() == name:
            return clip
    for sub in (folder.GetSubFolderList() or []):
        found = _search_folder(sub, name)
        if found:
            return found
    return None


def _find_media_pool_item(conn, name: str):
    root = conn.media_pool.GetRootFolder()
    return _search_folder(root, name)


def _ensure_video_track_count(conn, required_count: int) -> None:
    current = conn.timeline.GetTrackCount("video") or 0
    while current < required_count:
        added = conn.timeline.AddTrack("video")
        if added is False:
            raise APICallFailed(
                "Failed to add required video track for multicam orchestration.",
                details={"required": required_count, "current": current},
            )
        current += 1


def multicam_create(
    conn,
    *,
    timeline_name: str,
    angles: str,
    sync: str = "start",
    base_track: int = 2,
) -> dict:
    if sync != "start":
        raise ValidationError("Only --sync start is supported in P1.", details={"sync": sync})

    angle_specs = parse_angles_spec(angles)

    timeline_ops.create_timeline(conn, timeline_name)
    timeline_ops.switch_timeline(conn, name=timeline_name)

    _ensure_video_track_count(conn, base_track + len(angle_specs) - 1)

    created = []
    for idx, angle in enumerate(angle_specs):
        mpi = _find_media_pool_item(conn, angle.clip_name)
        if not mpi:
            raise ClipNotFound(f"Media pool clip '{angle.clip_name}' not found.")
        info = {
            "mediaPoolItem": mpi,
            "recordFrame": _timeline_start_frame(conn),
            "trackIndex": base_track + idx,
            "trackType": "video",
        }
        res = conn.media_pool.AppendToTimeline([info])
        if res is False:
            raise APICallFailed(
                "AppendToTimeline failed for multicam create.",
                details={"angle": angle.label, "clip": angle.clip_name, "track": base_track + idx},
            )
        created.append({"label": angle.label, "clip": angle.clip_name, "track": base_track + idx})

    return {
        "timeline": timeline_name,
        "sync": sync,
        "base_track": base_track,
        "angles": created,
        "program_track": 1,
    }


def _find_item_covering_frame(conn, *, track_index: int, frame: int):
    items = conn.timeline.GetItemListInTrack("video", track_index) or []
    for item in items:
        try:
            start = int(item.GetStart())
            end = int(item.GetEnd())
        except Exception:
            continue
        if start <= frame < end:
            return item
    return None


def _timeline_end_frame(conn, track_indices: list[int]) -> int:
    end_frame = _timeline_start_frame(conn)
    for idx in track_indices:
        items = conn.timeline.GetItemListInTrack("video", idx) or []
        for item in items:
            try:
                end_frame = max(end_frame, int(item.GetEnd()))
            except Exception:
                continue
    return end_frame


def multicam_switch(
    conn,
    *,
    switches: str,
    program_track: int = 1,
    angles_track_base: int = 2,
) -> dict:
    timeline_start = _timeline_start_frame(conn)
    switch_specs = parse_switches_spec(switches, conn.fps, timeline_start)

    # Deterministic mapping: first seen label -> base track + ordinal.
    label_to_track: dict[str, int] = {}
    for spec in switch_specs:
        if spec.label not in label_to_track:
            label_to_track[spec.label] = angles_track_base + len(label_to_track)

    max_source_track = max(label_to_track.values())
    _ensure_video_track_count(conn, max(max_source_track, program_track))

    end_frame = _timeline_end_frame(conn, list(label_to_track.values()))
    if end_frame <= switch_specs[0].frame:
        raise APICallFailed("Cannot determine multicam switch timeline end frame.")

    try:
        edit_ops.remove_range(
            conn,
            f"{switch_specs[0].frame}f",
            f"{end_frame}f",
            track_type="video",
            track_index=program_track,
        )
    except Exception:
        pass

    applied = []
    for idx, spec in enumerate(switch_specs):
        seg_start = spec.frame
        seg_end = switch_specs[idx + 1].frame if idx + 1 < len(switch_specs) else end_frame
        if seg_end <= seg_start:
            continue

        source_track = label_to_track[spec.label]
        src_item = _find_item_covering_frame(conn, track_index=source_track, frame=seg_start)
        if not src_item:
            raise APICallFailed(
                "No source angle clip covering switch frame.",
                details={"label": spec.label, "track": source_track, "frame": seg_start},
            )

        mpi = src_item.GetMediaPoolItem() if hasattr(src_item, "GetMediaPoolItem") else None
        if not mpi:
            raise APICallFailed(
                "Source angle clip has no media pool item.",
                details={"label": spec.label, "track": source_track},
            )

        src_start = int(src_item.GetStart())
        left_offset = int(src_item.GetLeftOffset()) if hasattr(src_item, "GetLeftOffset") else 0
        source_in = left_offset + (seg_start - src_start)
        source_out = source_in + (seg_end - seg_start)

        info = {
            "mediaPoolItem": mpi,
            "startFrame": source_in,
            "endFrame": source_out,
            "recordFrame": seg_start,
            "trackIndex": program_track,
            "trackType": "video",
        }
        result = conn.media_pool.AppendToTimeline([info])
        if result is False:
            raise APICallFailed(
                "AppendToTimeline failed during multicam switch.",
                details={
                    "label": spec.label,
                    "segment_start": seg_start,
                    "segment_end": seg_end,
                    "program_track": program_track,
                },
            )

        applied.append(
            {
                "label": spec.label,
                "source_track": source_track,
                "program_track": program_track,
                "record_start": seg_start,
                "record_end": seg_end,
            }
        )

    return {
        "switches": [{"frame": s.frame, "label": s.label} for s in switch_specs],
        "label_to_track": label_to_track,
        "program_track": program_track,
        "angles_track_base": angles_track_base,
        "applied_segments": applied,
    }
