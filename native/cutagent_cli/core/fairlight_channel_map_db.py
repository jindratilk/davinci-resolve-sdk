"""DB-backed Fairlight audio channel mapping writes."""

from __future__ import annotations

import json
import sqlite3
import struct
from typing import Any

from ..errors import APICallFailed, ValidationError
from . import db_session

ROUTE = "db_workaround_fairlight_channel_map"

_AUDIO_TYPE_CODES = {
    "stereo": 0,
    "mono": 1,
    "5.1": 2,
    "7.1": 3,
    "5.1film": 4,
    "7.1film": 5,
    **{f"adaptive{channels}": 256 + channels for channels in range(1, 37)},
}
_AUDIO_TYPE_CHANNEL_COUNTS = {
    "mono": 1,
    "stereo": 2,
    "5.1": 6,
    "5.1film": 6,
    "7.1": 8,
    "7.1film": 8,
    **{f"adaptive{channels}": channels for channels in range(1, 37)},
}
_UNMAPPED_CHANNEL = 0x40000000


def set_channel_mapping(
    conn: Any,
    *,
    clip: str | None,
    media: str | None,
    mapping_json: str,
) -> dict[str, Any]:
    request = parse_channel_mapping_request(clip=clip, media=media, mapping_json=mapping_json)

    def writer(_connection: sqlite3.Connection, cursor: sqlite3.Cursor, session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        if request["source"] == "timeline_item":
            row = _select_timeline_item_row(cursor, str(request["target"]))
            blob = _encode_timeline_track_mapping(request["tracks"][0])
            cursor.execute(
                "UPDATE Sm2TiItem SET VirtualAudioTrackBA = ? WHERE rowid = ?",
                (blob, row["rowid"]),
            )
            session.steps.append("write_timeline_item_virtual_audio_track")
            return {
                "action": "fairlight.channel_map.set",
                "route": ROUTE,
                "source": "timeline_item",
                "target": {"clip": row["Name"], "rowid": row["rowid"], "id": row["Sm2TiItem_id"]},
                "requested_mapping": request["mapping"],
                "written": {
                    "table": "Sm2TiItem",
                    "column": "VirtualAudioTrackBA",
                    "rowid": row["rowid"],
                    "bytes": len(blob),
                },
            }

        row = _select_media_pool_row(cursor, str(request["target"]))
        blob = _encode_media_pool_track_mapping(request["tracks"])
        cursor.execute(
            "UPDATE Sm2MpMedia SET VirtualAudioTracksBA = ? WHERE rowid = ?",
            (blob, row["rowid"]),
        )
        session.steps.append("write_media_pool_virtual_audio_tracks")
        return {
            "action": "fairlight.channel_map.set",
            "route": ROUTE,
            "source": "media_pool_item",
            "target": {"media": row["Name"], "rowid": row["rowid"], "id": row["Sm2MpMedia_id"]},
            "requested_mapping": request["mapping"],
            "written": {
                "table": "Sm2MpMedia",
                "column": "VirtualAudioTracksBA",
                "rowid": row["rowid"],
                "bytes": len(blob),
            },
        }

    def verifier(fresh_conn: Any, mutation_result: dict[str, Any], _session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        if request["source"] == "timeline_item":
            mapping = _read_timeline_item_mapping(fresh_conn, str(mutation_result["target"]["clip"]))
            native_api = "TimelineItem.GetSourceAudioChannelMapping()"
        else:
            mapping = _read_media_pool_mapping(fresh_conn, str(mutation_result["target"]["media"]))
            native_api = "MediaPoolItem.GetAudioMapping()"
        parsed = _parse_mapping_payload(mapping)
        expected = request["mapping"]["track_mapping"]
        actual = parsed.get("track_mapping")
        verified = _mapping_matches(expected, actual)
        if not verified:
            raise APICallFailed(
                "Fairlight channel mapping DB write did not match DaVinci Resolve readback after reopen.",
                details={
                    "route": ROUTE,
                    "source": request["source"],
                    "expected": expected,
                    "actual": actual,
                    "native_api": native_api,
                },
                recoverability="manual",
            )
        return {
            "status": "verified",
            "native_api": native_api,
            "read_scope": "audio_channel_mapping",
            "readback": parsed,
        }

    result = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Fairlight channel mapping DB write",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    result["route"] = ROUTE
    result["db_session_route"] = "db_native"
    result["verified_set_scope"] = "source_audio_track_type_and_channel_indices"
    return result


def parse_channel_mapping_request(*, clip: str | None, media: str | None, mapping_json: str | None) -> dict[str, Any]:
    if bool(clip) == bool(media):
        raise ValidationError(
            "Fairlight channel-map set requires exactly one of --clip or --media.",
            details={"clip": clip, "media": media, "required_one_of": ["--clip", "--media"]},
            recoverability="not_applicable",
        )
    if not mapping_json:
        raise ValidationError(
            "Fairlight channel-map set requires --mapping-json.",
            details={"required": ["--mapping-json"]},
            recoverability="not_applicable",
        )
    try:
        mapping = json.loads(mapping_json)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "--mapping-json must be valid JSON.",
            details={"line": exc.lineno, "column": exc.colno, "message": exc.msg},
            recoverability="not_applicable",
        ) from exc
    if not isinstance(mapping, dict) or not isinstance(mapping.get("track_mapping"), dict):
        raise ValidationError(
            "--mapping-json must contain an object track_mapping field.",
            details={"expected_shape": {"track_mapping": {"1": {"type": "mono", "channel_idx": [1]}}}},
            recoverability="not_applicable",
        )
    tracks = _normalize_track_mapping(mapping["track_mapping"], source="timeline_item" if clip else "media_pool_item")
    return {
        "source": "timeline_item" if clip else "media_pool_item",
        "target": clip or media,
        "mapping": {"track_mapping": {track["key"]: track["payload"] for track in tracks}},
        "tracks": tracks,
    }


def _normalize_track_mapping(track_mapping: dict[str, Any], *, source: str) -> list[dict[str, Any]]:
    if not track_mapping:
        raise ValidationError(
            "Fairlight channel-map set requires at least one track mapping.",
            details={"track_mapping": track_mapping},
            recoverability="not_applicable",
        )
    if source == "timeline_item" and len(track_mapping) != 1:
        raise ValidationError(
            "Timeline item channel-map writes support exactly one source track mapping.",
            details={"source": source, "track_count": len(track_mapping)},
            recoverability="not_applicable",
        )
    keyed_entries = [(_normalize_track_key(key), key, raw) for key, raw in track_mapping.items()]
    keyed_entries.sort(key=lambda item: item[0])
    track_numbers = [number for number, _key, _raw in keyed_entries]
    if source == "timeline_item" and track_numbers != [1]:
        raise ValidationError(
            "Timeline item channel-map writes require track_mapping key '1'.",
            details={"source": source, "track_keys": [str(key) for _number, key, _raw in keyed_entries]},
            recoverability="not_applicable",
        )
    if source == "media_pool_item" and track_numbers != list(range(1, len(track_numbers) + 1)):
        raise ValidationError(
            "Media Pool channel-map writes require contiguous track_mapping keys starting at '1'.",
            details={
                "source": source,
                "track_keys": [str(key) for _number, key, _raw in keyed_entries],
                "expected_keys": [str(number) for number in range(1, len(track_numbers) + 1)],
            },
            recoverability="not_applicable",
        )
    tracks: list[dict[str, Any]] = []
    for track_number, key, raw in keyed_entries:
        if not isinstance(raw, dict):
            raise ValidationError(
                "Each track_mapping entry must be an object.",
                details={"track": key, "entry": raw},
                recoverability="not_applicable",
            )
        track_type = _normalize_audio_type(raw.get("type"))
        channels = _normalize_channel_indices(raw.get("channel_idx"), track_type=track_type, track=key)
        mute = raw.get("mute", False)
        if mute not in (False, None):
            raise ValidationError(
                "Fairlight channel-map set does not support writing muted channel mappings yet.",
                details={
                    "track": key,
                    "mute": mute,
                    "verified_set_scope": "type_and_channel_idx_only",
                },
                recoverability="not_applicable",
            )
        payload = {"type": track_type, "channel_idx": channels, "mute": False}
        tracks.append({"number": track_number, "key": str(track_number), "payload": payload})
    return tracks


def _normalize_track_key(value: Any) -> int:
    raw = str(value).strip()
    if not raw.isdigit():
        raise ValidationError(
            "Fairlight channel-map track_mapping keys must be positive 1-based integers.",
            details={"track": value},
            recoverability="not_applicable",
        )
    number = int(raw)
    if number < 1:
        raise ValidationError(
            "Fairlight channel-map track_mapping keys must be 1 or greater.",
            details={"track": value},
            recoverability="not_applicable",
        )
    return number


def _normalize_audio_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in _AUDIO_TYPE_CODES:
        raise ValidationError(
            "Unsupported Fairlight audio channel-map type.",
            details={"type": value, "supported": sorted(_AUDIO_TYPE_CODES)},
            recoverability="not_applicable",
        )
    return normalized


def _normalize_channel_indices(value: Any, *, track_type: str, track: str) -> list[int | None]:
    if not isinstance(value, list):
        raise ValidationError(
            "Fairlight channel-map channel_idx must be a JSON array.",
            details={"track": track, "channel_idx": value},
            recoverability="not_applicable",
        )
    expected_count = _AUDIO_TYPE_CHANNEL_COUNTS[track_type]
    if len(value) != expected_count:
        raise ValidationError(
            "Fairlight channel-map channel_idx length must match the requested audio type.",
            details={"track": track, "type": track_type, "expected_channels": expected_count, "actual_channels": len(value)},
            recoverability="not_applicable",
        )
    channels: list[int | None] = []
    for index, raw in enumerate(value, start=1):
        if raw in (None, 0):
            channels.append(None)
            continue
        try:
            channel = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "Fairlight channel-map source channel indices must be integers, null, or 0.",
                details={"track": track, "position": index, "value": raw},
                recoverability="not_applicable",
            ) from exc
        if channel < 1:
            raise ValidationError(
                "Fairlight channel-map source channel indices must be 1 or greater.",
                details={"track": track, "position": index, "value": raw},
                recoverability="not_applicable",
            )
        channels.append(channel)
    return channels


def _select_timeline_item_row(cursor: sqlite3.Cursor, clip_selector: str) -> sqlite3.Row:
    rows = cursor.execute(
        """
        SELECT rowid, Sm2TiItem_id, Name, VirtualAudioTrackBA
        FROM Sm2TiItem
        WHERE Name = ?
        ORDER BY Start, rowid
        """,
        (clip_selector,),
    ).fetchall()
    if not rows:
        raise ValidationError(
            "No timeline item matched the requested Fairlight channel-map clip.",
            details={"clip": clip_selector},
            recoverability="not_applicable",
        )
    if len(rows) > 1:
        raise ValidationError(
            "Fairlight channel-map clip selector is ambiguous.",
            details={"clip": clip_selector, "matches": len(rows)},
            recoverability="not_applicable",
        )
    return rows[0]


def _select_media_pool_row(cursor: sqlite3.Cursor, media_selector: str) -> sqlite3.Row:
    rows = cursor.execute(
        """
        SELECT rowid, Sm2MpMedia_id, Name, VirtualAudioTracksBA
        FROM Sm2MpMedia
        WHERE Name = ?
        ORDER BY rowid
        """,
        (media_selector,),
    ).fetchall()
    if not rows:
        raise ValidationError(
            "No Media Pool item matched the requested Fairlight channel-map media.",
            details={"media": media_selector},
            recoverability="not_applicable",
        )
    if len(rows) > 1:
        raise ValidationError(
            "Fairlight channel-map media selector is ambiguous.",
            details={"media": media_selector, "matches": len(rows)},
            recoverability="not_applicable",
        )
    return rows[0]


def _read_timeline_item_mapping(conn: Any, clip_name: str) -> str:
    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        raise APICallFailed("No active timeline is available for Fairlight channel mapping verification.")
    for track_index in range(1, int(timeline.GetTrackCount("audio") or 0) + 1):
        for item in timeline.GetItemListInTrack("audio", track_index) or []:
            if item.GetName() == clip_name:
                return item.GetSourceAudioChannelMapping()
    raise APICallFailed(
        "Fairlight channel mapping verification could not find the timeline item after reopen.",
        details={"clip": clip_name},
        recoverability="manual",
    )


def _read_media_pool_mapping(conn: Any, media_name: str) -> str:
    project = getattr(conn, "project", None)
    media_pool = project.GetMediaPool() if project is not None else getattr(conn, "media_pool", None)
    root = media_pool.GetRootFolder() if media_pool is not None and hasattr(media_pool, "GetRootFolder") else None
    folder = root or (media_pool.GetCurrentFolder() if media_pool is not None and hasattr(media_pool, "GetCurrentFolder") else None)
    for item in _iter_media_pool_items(folder):
        if item.GetName() == media_name:
            return item.GetAudioMapping()
    raise APICallFailed(
        "Fairlight channel mapping verification could not find the Media Pool item after reopen.",
        details={"media": media_name},
        recoverability="manual",
    )


def _iter_media_pool_items(folder: Any):
    if folder is None:
        return
    get_clip_list = getattr(folder, "GetClipList", None)
    for item in (get_clip_list() if callable(get_clip_list) else []) or []:
        yield item
    get_subfolder_list = getattr(folder, "GetSubFolderList", None)
    for subfolder in (get_subfolder_list() if callable(get_subfolder_list) else []) or []:
        yield from _iter_media_pool_items(subfolder)


def _parse_mapping_payload(raw_mapping: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_mapping)
    except json.JSONDecodeError as exc:
        raise APICallFailed(
            "DaVinci Resolve returned invalid channel mapping readback JSON.",
            details={"mapping": raw_mapping, "error": str(exc)},
            recoverability="manual",
        ) from exc
    if not isinstance(parsed, dict):
        raise APICallFailed(
            "DaVinci Resolve channel mapping readback was not an object.",
            details={"mapping": raw_mapping},
            recoverability="manual",
        )
    return parsed


def _mapping_matches(expected: dict[str, Any], actual: Any) -> bool:
    if not isinstance(actual, dict):
        return False
    for key, expected_track in expected.items():
        actual_track = actual.get(str(key))
        if not isinstance(actual_track, dict):
            return False
        if str(actual_track.get("type", "")).strip().lower() != str(expected_track["type"]).strip().lower():
            return False
        if list(actual_track.get("channel_idx") or []) != list(expected_track["channel_idx"]):
            return False
        if bool(actual_track.get("mute", False)) != bool(expected_track.get("mute", False)):
            return False
    return True


def canonical_timeline_track_mapping_blob(track_mapping: dict[str, Any]) -> bytes:
    """Encode the one-track native mapping used by a default timeline audio item."""
    tracks = _normalize_track_mapping(track_mapping, source="timeline_item")
    return _encode_timeline_track_mapping(tracks[0])


def _encode_timeline_track_mapping(track: dict[str, Any]) -> bytes:
    return _encode_track_payload(track["payload"])


def _encode_media_pool_track_mapping(tracks: list[dict[str, Any]]) -> bytes:
    payload = _u32(1) + _u32(len(tracks))
    for track in tracks:
        payload += _qstring(str(int(track["number"]) - 1))
        payload += _qvariant_byte_array(_encode_track_payload(track["payload"]))
    return payload


def _encode_track_payload(track: dict[str, Any]) -> bytes:
    channels_payload = _encode_channels_payload(track["channel_idx"])
    return (
        _u32(1)
        + _u32(2)
        + _qstring("ChannelsBA")
        + _qvariant_byte_array(channels_payload)
        + _qstring("AudioType")
        + _qvariant_int(_AUDIO_TYPE_CODES[track["type"]])
    )


def _encode_channels_payload(channels: list[int | None]) -> bytes:
    payload = _u32(2) + _u32(len(channels))
    for channel in channels:
        payload += _u32(_UNMAPPED_CHANNEL if channel is None else 0x4000 + int(channel))
    return payload


def _u32(value: int) -> bytes:
    return struct.pack(">I", int(value))


def _qstring(value: str) -> bytes:
    raw = value.encode("utf-16-be")
    return _u32(len(raw)) + raw


def _qvariant_int(value: int) -> bytes:
    return _u32(2) + b"\x00" + _u32(value)


def _qvariant_byte_array(payload: bytes) -> bytes:
    return _u32(12) + b"\x00" + _u32(len(payload)) + payload
