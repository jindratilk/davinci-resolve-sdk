from __future__ import annotations

import sqlite3
from typing import Any

from ...errors import APICallFailed
from .row_mutation import _decode_frame_rate_blob, _encode_media_extents, _update_row


def _load_timeline_multicam_track_state(
    project_db_path: str,
    *,
    timeline_name: str,
    multicam_name: str,
    multicam_media_id: str | None = None,
    timeline_native_id: str | None = None,
) -> dict[str, Any]:
    connection = sqlite3.connect(project_db_path)
    try:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                container.Sm2SequenceContainer_id,
                seq.Sm2Sequence_id AS SequenceId,
                seq.FrameRate AS SequenceFrameRate,
                media.Sm2MpMedia_id AS MulticamMediaId,
                track.Sm2TiTrack_id AS TrackId,
                track.Type AS TrackType,
                rel_item.DbIndex AS ItemIndex,
                item.*
            FROM Sm2Timeline timeline
            JOIN Sm2Sequence seq ON seq.Sm2Timeline_id = timeline.Sm2Timeline_id
            JOIN Sm2SequenceContainer container ON container.Sm2Sequence_id = seq.Sm2Sequence_id
            JOIN Sm2MpMedia media ON media.Name = ? AND (? IS NULL OR media.Sm2MpMedia_id = ?)
            JOIN Sm2SequenceContainer_Sm2TiTrack rel_track ON rel_track.DbOwner = container.Sm2SequenceContainer_id
            JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = rel_track.DbAssociate
            LEFT JOIN Sm2TiItem_Sm2TiTrack rel_item
              ON rel_item.DbOwner = track.Sm2TiTrack_id
             AND rel_item.DbPropertyName = 'Items'
            LEFT JOIN Sm2TiItem item
              ON item.Sm2TiItem_id = rel_item.DbAssociate
             AND item.MediaRef = media.Sm2MpMedia_id
            WHERE timeline.Name = ?
              AND (? IS NULL OR timeline.Sm2Timeline_id = ?)
              AND track.Type IN (0, 1)
            ORDER BY track.Type, COALESCE(rel_item.DbIndex, 0), item.rowid
            """,
            (multicam_name, multicam_media_id, multicam_media_id, timeline_name, timeline_native_id, timeline_native_id),
        ).fetchall()
        if not rows:
            raise APICallFailed(
                "Could not locate the target timeline sequence in Project.db for native multicam switch write.",
                details={"timeline_name": timeline_name, "multicam_name": multicam_name},
            )

        grouped: dict[int, list[dict[str, Any]]] = {0: [], 1: []}
        container_id = str(rows[0]["Sm2SequenceContainer_id"])
        sequence_id = str(rows[0]["SequenceId"])
        sequence_frame_rate = rows[0]["SequenceFrameRate"]
        multicam_media_id = str(rows[0]["MulticamMediaId"])
        track_ids: dict[int, str | None] = {0: None, 1: None}
        for row in rows:
            item_row = dict(row)
            track_type = int(item_row.pop("TrackType"))
            track_id = str(item_row.pop("TrackId"))
            track_ids[track_type] = track_ids.get(track_type) or track_id
            item_index_raw = item_row.pop("ItemIndex")
            item_row.pop("Sm2SequenceContainer_id", None)
            item_row.pop("SequenceId", None)
            item_row.pop("SequenceFrameRate", None)
            item_row.pop("MulticamMediaId", None)
            if not item_row.get("Sm2TiItem_id"):
                continue
            item_index = int(item_index_raw or 0)
            grouped.setdefault(track_type, []).append(
                {
                    "track_id": track_id,
                    "item_index": item_index,
                    "item_row": item_row,
                }
            )
        return {
            "sequence_container_id": container_id,
            "sequence_id": sequence_id,
            "sequence_frame_rate": sequence_frame_rate,
            "multicam_media_id": multicam_media_id,
            "video_track_id": track_ids.get(0),
            "audio_track_id": track_ids.get(1),
            "video_items": grouped.get(0, []),
            "audio_items": grouped.get(1, []),
        }
    finally:
        connection.close()


def _build_fallback_multicam_item_row(
    *,
    item_id: str,
    multicam_name: str,
    multicam_media_id: str,
    track_id: str,
    track_type: int,
    start: str,
    duration: str,
    in_value: str | None,
    current_selector_idx: int,
    fields_blob: bytes,
    media_timemap_ba: bytes | None = None,
    effect_filters_ba: bytes | None = None,
    ops_module,
) -> dict[str, Any]:
    is_audio = track_type == 1
    return {
        "Sm2TiItem_id": item_id,
        "DbType": "Sm2TiAudioClip" if is_audio else "Sm2TiVideoClip",
        "Name": multicam_name,
        "Start": start,
        "Duration": duration,
        "Track": None,
        "LinkedItemSync": None,
        "MarkersBA": None,
        "UiMemento": 0,
        "Flags": 0,
        "PriorityIndex": 0,
        "In": in_value,
        "MediaRef": multicam_media_id,
        "MediaStartTime": 3600.0,
        "MediaFilePath": None,
        "MediaReelNumber": None,
        "MediaTimemapBA": media_timemap_ba if media_timemap_ba is not None else ops_module._TIMELINE_ITEM_MEDIA_TIMEMAP,
        "Group": None,
        "pLmVerTable": None,
        "pAuxLmVerTable": None,
        "Thumbnail": None,
        "ThumbnailDirtyFlag": 1,
        "RenderTextEnabled": 1,
        "RenderTextGanged": 1,
        "RenderTextPrefixed": 1,
        "TextRenderItemVec": None,
        "LastChangedTime": 0,
        "LastRenderedTime": 0,
        "IsMarkedForCaching": 0,
        "IsForceConformed": 1,
        "MatchConflictState": 0,
        "MediaTrackIdx": 0 if is_audio else None,
        "PrettyType": None,
        "Resolution": None,
        "EffectFiltersBA": effect_filters_ba,
        "IsPreConformed": 0,
        "PreConformMediaExtents": None if is_audio else ops_module._TIMELINE_ITEM_VIDEO_PRECONFORM_MEDIA_EXTENTS,
        "ImportExportMetadataBA": None,
        "MediaFrameRate": ops_module._TIMELINE_ITEM_MEDIA_FRAME_RATE,
        "Sm2TiTrack_id": track_id,
        "VirtualAudioTrackBA": ops_module._TIMELINE_ITEM_AUDIO_VIRTUAL_AUDIO_TRACK if is_audio else None,
        "MixedFrameRateAlignment": 0.0,
        "UseOppositeSrcForLeftEye": 0,
        "UseOppositeSrcForRightEye": 0,
        "WasDisbanded": 0,
        "CurrentSelectorIdx": current_selector_idx,
        "AlignmentType": None,
        "Position": None,
        "RenderCacheBA": None,
        "ClipGroup": None,
        "MediaMetadata": None,
        "FieldsBlob": fields_blob,
        "CompositionTable": None,
        "BlobLockSysId": "",
        "OriginalClip": None,
        "Sm2TiItem_Owner_id": None,
        "CompTableLockSysId": "",
        "VersionTableLockSysId": "",
    }


def _patch_timeline_multicam_bootstrap_metadata(
    cursor: sqlite3.Cursor,
    *,
    track_state: dict[str, Any],
    total_duration_frames: int,
) -> None:
    fps = _decode_frame_rate_blob(track_state.get("sequence_frame_rate")) or 24.0
    duration_seconds = max(0.0, float(total_duration_frames) / float(fps))
    sequence_id = track_state.get("sequence_id")
    if sequence_id:
        _update_row(
            cursor,
            "Sm2Sequence",
            "Sm2Sequence_id",
            sequence_id,
            {
                "MediaExtents": _encode_media_extents(0.0, duration_seconds),
            },
        )
    audio_track_id = track_state.get("audio_track_id")
    if audio_track_id:
        _update_row(
            cursor,
            "Sm2TiTrack",
            "Sm2TiTrack_id",
            audio_track_id,
            {"SubType": 1},
        )
