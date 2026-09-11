"""Native source-channel mapping for the existing timeline-item SDK contract."""
from __future__ import annotations

import json
from typing import Any

from ..errors import APICallFailed, ValidationError
from ..output import set_execution_engine, set_verification_status


def parse_timeline_mapping(raw: Any) -> dict[str, Any]:
    """Parse and validate documented TimelineItem source-channel mapping JSON."""
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as exc:
        raise APICallFailed("DaVinci Resolve returned invalid audio channel mapping JSON.") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("track_mapping"), dict):
        raise APICallFailed("DaVinci Resolve returned no source-channel mapping.")
    embedded_channels = parsed.get("embedded_audio_channels")
    if embedded_channels is not None and (
        not isinstance(embedded_channels, int)
        or isinstance(embedded_channels, bool)
        or embedded_channels < 0
    ):
        raise APICallFailed("DaVinci Resolve returned an invalid embedded audio channel count.")
    if "linked_audio" in parsed and not isinstance(parsed["linked_audio"], dict):
        raise APICallFailed("DaVinci Resolve returned invalid linked audio mapping data.")
    for key, record in parsed["track_mapping"].items():
        if not isinstance(key, str) or not key.isdecimal() or int(key) < 1 or not isinstance(record, dict):
            raise APICallFailed("DaVinci Resolve returned an invalid source audio track mapping.")
        channel_indices = record.get("channel_idx")
        if (
            not isinstance(channel_indices, list)
            or any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in channel_indices)
            or not isinstance(record.get("mute"), bool)
            or not isinstance(record.get("type"), str)
            or not record["type"]
        ):
            raise APICallFailed("DaVinci Resolve returned invalid source audio channel routing data.")
    return parsed


def set_timeline_mapping(conn: Any, *, clip: str, mapping: dict[str, Any]) -> dict[str, Any]:
    matches = []
    for track in range(1, int(conn.timeline.GetTrackCount("audio")) + 1):
        for item in conn.timeline.GetItemListInTrack("audio", track) or []:
            if clip in (str(item.GetUniqueId()), item.GetName()):
                matches.append((item, track))
    if len(matches) != 1:
        raise ValidationError("Audio channel mapping requires one exact timeline item.", details={"matches": len(matches)})
    item, track = matches[0]
    def read():
        return parse_timeline_mapping(item.GetSourceAudioChannelMapping())
    before = read()
    track_mapping = {key: dict(value) for key, value in mapping["track_mapping"].items()}
    # The existing single-source stereo request means duplicate that source in
    # both outputs. The 21.1 setter requires exactly two entries for stereo.
    for record in track_mapping.values():
        channels = record.get("channel_idx", [])
        if record.get("type") == "stereo" and len(channels) == 1:
            record["channel_idx"] = channels * 2
    requested = {**before, "track_mapping": track_mapping}
    changed = before["track_mapping"] != requested["track_mapping"]
    if changed:
        setter = getattr(item, "SetSourceAudioChannelMapping", None)
        if not callable(setter) or setter(json.dumps(requested)) is not True:
            raise APICallFailed("DaVinci Resolve rejected the native source-channel mapping.")
    after = read()
    if after["track_mapping"] != requested["track_mapping"]:
        raise APICallFailed("Native source-channel mapping differs from the requested mapping.")
    set_execution_engine("api_native")
    set_verification_status("verified")
    return {"action": "fairlight.channel_map.set", "changed": changed,
        "timeline_name": conn.timeline.GetName(),
        "target": {"kind": "timeline_item", "clip": item.GetName(), "item_id": str(item.GetUniqueId()), "track_index": track},
        "previous_mapping": before, "mapping": after, "route": "api_native",
        "verification": {"status": "verified", "native_api": "TimelineItem.GetSourceAudioChannelMapping()", "native_readback": after}}
