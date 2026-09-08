from __future__ import annotations

from collections import OrderedDict
from typing import Any, Iterable

from ...errors import ValidationError
from ..fairlight_channel_map_db import _encode_media_pool_track_mapping, _encode_track_payload

_TYPE_CHANNEL_COUNTS = {
    "mono": 1,
    "stereo": 2,
    "5.1": 6,
    "5.1film": 6,
    "7.1": 8,
    "7.1film": 8,
    **{f"adaptive{channels}": channels for channels in range(1, 37)},
}


def _normalized_track_payload(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    track_type = str(raw.get("type") or "").strip().lower()
    channels = list(raw.get("channel_idx") or [])
    expected_count = _TYPE_CHANNEL_COUNTS.get(track_type)
    if expected_count is None or len(channels) != expected_count:
        return None
    normalized_channels: list[int | None] = []
    for value in channels:
        if value in (None, 0):
            normalized_channels.append(None)
            continue
        try:
            channel = int(value)
        except (TypeError, ValueError):
            return None
        if channel < 1:
            return None
        normalized_channels.append(channel)
    return {"type": track_type, "channel_idx": normalized_channels, "mute": bool(raw.get("mute", False))}


def source_audio_tracks(source_row: Any) -> list[dict[str, Any]]:
    mapping = getattr(source_row, "audio_mapping", None)
    raw_tracks = mapping.get("track_mapping") if isinstance(mapping, dict) else None
    if not isinstance(raw_tracks, dict):
        return []
    ordered: list[tuple[int, dict[str, Any]]] = []
    for raw_key, raw_track in raw_tracks.items():
        try:
            key = int(str(raw_key))
        except (TypeError, ValueError):
            continue
        normalized = _normalized_track_payload(raw_track)
        if key < 1 or normalized is None or normalized["mute"]:
            continue
        ordered.append((key, normalized))
    return [payload for _key, payload in sorted(ordered, key=lambda entry: entry[0])]


def _flattened_channel_count(tracks: Iterable[dict[str, Any]]) -> int:
    return sum(len(track["channel_idx"]) for track in tracks)


def _adaptive_track(channel_count: int) -> dict[str, Any]:
    count = max(1, min(36, int(channel_count)))
    return {
        "type": f"adaptive{count}",
        "channel_idx": list(range(1, count + 1)),
        "mute": False,
    }


def _representative_tracks_by_angle(
    source_rows: list[Any],
    source_angle_labels: list[str],
) -> OrderedDict[str, list[dict[str, Any]]]:
    by_angle: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for source_row, label in zip(source_rows, source_angle_labels):
        tracks = source_audio_tracks(source_row)
        existing = by_angle.setdefault(label, [])
        if _flattened_channel_count(tracks) > _flattened_channel_count(existing):
            by_angle[label] = tracks
    return by_angle


def build_audio_mode_plan(
    *,
    audio_mode: str,
    reference_audio_angle: str,
    source_rows: list[Any],
    source_angle_labels: list[str],
) -> dict[str, Any]:
    by_angle = _representative_tracks_by_angle(source_rows, source_angle_labels)
    has_explicit_source_audio_mapping = any(source_audio_tracks(row) for row in source_rows)
    if reference_audio_angle not in by_angle:
        raise ValidationError(
            "Reference audio angle is missing from the multicam audio topology.",
            details={"reference_audio_angle": reference_audio_angle, "angles": list(by_angle)},
        )

    channel_count_by_angle = {
        angle: max(1, _flattened_channel_count(tracks))
        for angle, tracks in by_angle.items()
    }
    track_subtype_by_angle = {
        angle: 256 + min(36, channel_count)
        for angle, channel_count in channel_count_by_angle.items()
    }

    if audio_mode == "reference_audio":
        media_tracks = by_angle[reference_audio_angle] or [_adaptive_track(1)]
    elif audio_mode == "adaptive_tracks":
        media_tracks = [_adaptive_track(max(channel_count_by_angle.values(), default=1))]
    elif audio_mode == "all_angles":
        media_tracks = []
        output_channel = 1
        for angle_tracks in by_angle.values():
            for track in angle_tracks or [_adaptive_track(1)]:
                count = len(track["channel_idx"])
                media_tracks.append(
                    {
                        "type": track["type"],
                        "channel_idx": list(range(output_channel, output_channel + count)),
                        "mute": False,
                    }
                )
                output_channel += count
    else:
        reference_tracks = by_angle[reference_audio_angle]
        max_track_count = max((len(tracks) for tracks in by_angle.values()), default=0)
        media_tracks = []
        output_channel = 1
        for track_index in range(max_track_count):
            candidates = [tracks[track_index] for tracks in by_angle.values() if track_index < len(tracks)]
            preferred = reference_tracks[track_index] if track_index < len(reference_tracks) else candidates[0]
            channel_count = max(len(track["channel_idx"]) for track in candidates)
            track_type = preferred["type"] if len(preferred["channel_idx"]) == channel_count else f"adaptive{channel_count}"
            media_tracks.append(
                {
                    "type": track_type,
                    "channel_idx": list(range(output_channel, output_channel + channel_count)),
                    "mute": False,
                }
            )
            output_channel += channel_count
        if not media_tracks:
            media_tracks = [_adaptive_track(1)]

    encoded_media_tracks = [
        {"number": index, "key": str(index), "payload": track}
        for index, track in enumerate(media_tracks, start=1)
    ]
    item_track_by_source_index: dict[int, dict[str, Any]] = {}
    for index, source_row in enumerate(source_rows):
        source_tracks = source_audio_tracks(source_row)
        item_track_by_source_index[index] = _adaptive_track(max(1, _flattened_channel_count(source_tracks)))

    return {
        "has_explicit_source_audio_mapping": has_explicit_source_audio_mapping,
        "media_virtual_audio_tracks_ba": _encode_media_pool_track_mapping(encoded_media_tracks),
        "media_track_mapping": {
            str(index): track
            for index, track in enumerate(media_tracks, start=1)
        },
        "item_track_by_source_index": item_track_by_source_index,
        "item_virtual_audio_track_ba_by_source_index": {
            index: _encode_track_payload(track)
            for index, track in item_track_by_source_index.items()
        },
        "track_subtype_by_angle": track_subtype_by_angle,
        "channel_count_by_angle": channel_count_by_angle,
        "audio_output_track_count": len(media_tracks),
        "audio_output_channel_count": sum(len(track["channel_idx"]) for track in media_tracks),
    }
