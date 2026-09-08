from __future__ import annotations

def _verify_imported_timeline_readback(conn, timeline, timeline_name: str) -> Dict[str, Any]:
    """Verify an imported EDL timeline is current enough to read tracks/items."""
    if not timeline:
        raise APICallFailed(
            "Imported EDL timeline is not available for verification.",
            details={"timeline": timeline_name},
        )

    active_timeline = getattr(conn, "timeline", None) or timeline
    active_name = None
    if active_timeline and hasattr(active_timeline, "GetName"):
        try:
            active_name = active_timeline.GetName()
        except Exception:
            active_name = None

    if timeline_name and active_name and active_name != timeline_name:
        setter = getattr(getattr(conn, "project", None), "SetCurrentTimeline", None)
        if callable(setter):
            try:
                setter(timeline)
                conn.wait_for_state(
                    lambda state: state["timeline"] == timeline_name,
                    description=f"silence-cut timeline '{timeline_name}' to become current",
                )
                active_timeline = getattr(conn, "timeline", None) or timeline
                active_name = active_timeline.GetName() if hasattr(active_timeline, "GetName") else timeline_name
            except Exception as exc:
                raise APICallFailed(
                    "Imported EDL timeline was created but could not be made current.",
                    details={
                        "timeline": timeline_name,
                        "active_timeline": active_name,
                        "error": str(exc),
                    },
                ) from exc

    track_counts: Dict[str, int] = {}
    item_counts: Dict[str, int] = {}
    for track_type in ("video", "audio"):
        try:
            track_count = int(active_timeline.GetTrackCount(track_type) or 0)
        except Exception as exc:
            raise APICallFailed(
                "Imported EDL timeline was created but track readback failed.",
                details={"timeline": timeline_name, "track_type": track_type, "error": str(exc)},
            ) from exc
        track_counts[track_type] = track_count
        item_total = 0
        for track_index in range(1, track_count + 1):
            try:
                item_total += len(active_timeline.GetItemListInTrack(track_type, track_index) or [])
            except Exception as exc:
                raise APICallFailed(
                    "Imported EDL timeline was created but item readback failed.",
                    details={
                        "timeline": timeline_name,
                        "track_type": track_type,
                        "track_index": track_index,
                        "error": str(exc),
                    },
                ) from exc
        item_counts[track_type] = item_total

    if item_counts.get("video", 0) <= 0 and item_counts.get("audio", 0) <= 0:
        raise APICallFailed(
            "Imported EDL timeline was created but contains no readable timeline items.",
            details={"timeline": timeline_name, "track_counts": track_counts, "item_counts": item_counts},
        )

    timeline_names: list[str] | None = None
    timeline_count: int | None = None
    timeline_list_visible: bool | None = None
    for _ in range(20):
        timeline_names, timeline_count = _project_timeline_names(conn)
        if timeline_names is None:
            break
        timeline_list_visible = timeline_name in timeline_names
        if timeline_list_visible or timeline_count == 0:
            break
        refresh = getattr(conn, "refresh", None)
        if callable(refresh):
            try:
                refresh()
            except Exception:
                pass
        time.sleep(0.25)
    if timeline_list_visible is False and (timeline_count or 0) > 0:
        raise APICallFailed(
            "Imported EDL timeline was created but project timeline list did not converge.",
            details={
                "timeline": timeline_name,
                "timeline_count": timeline_count,
                "timeline_names": timeline_names,
            },
        )

    return {
        "status": "verified",
        "current_timeline": active_name or timeline_name,
        "track_counts": track_counts,
        "item_counts": item_counts,
        "project_timeline_visible": timeline_list_visible,
        "project_timeline_count": timeline_count,
    }


# ---------------------------------------------------------------------------
# Additional TimelineItem Operations (API parity)
# ---------------------------------------------------------------------------

def get_linked_items(conn, position: str, track_type: str = "video", track_index: int = 0) -> list:
    """Get linked items for a timeline item at position."""
    frame = _record_frame_position(conn, position)
    clip = find_clip_at_position(conn, frame, track_type, track_index)
    if not clip:
        raise ClipNotFound(f"No clip at {position}")
    getter = getattr(clip, "GetLinkedItems", None)
    if not getter:
        raise APICallFailed("GetLinkedItems not available.")
    items = getter()
    result = []
    if items:
        for item in items:
            try:
                result.append({"name": item.GetName(), "duration": item.GetDuration()})
            except Exception:
                result.append({"name": str(item)})
    return result


def get_track_type_and_index(conn, position: str, track_type: str = "video", track_index: int = 0) -> Dict[str, Any]:
    """Get track type and index for a timeline item."""
    frame = _record_frame_position(conn, position)
    clip = find_clip_at_position(conn, frame, track_type, track_index)
    if not clip:
        raise ClipNotFound(f"No clip at {position}")
    getter = getattr(clip, "GetTrackTypeAndIndex", None)
    if not getter:
        raise APICallFailed("GetTrackTypeAndIndex not available.")
    result = getter()
    return {"track_type": result[0] if result else track_type, "track_index": result[1] if result else track_index}


def export_lut_from_clip(conn, position: str, export_type: int, path: str, track_type: str = "video", track_index: int = 0) -> Dict[str, Any]:
    """Export LUT from a timeline item."""
    frame = _record_frame_position(conn, position)
    clip = find_clip_at_position(conn, frame, track_type, track_index)
    if not clip:
        raise ClipNotFound(f"No clip at {position}")
    exporter = getattr(clip, "ExportLUT", None)
    if not exporter:
        raise APICallFailed("ExportLUT not available.")
    result = exporter(export_type, path)
    return {"exported": bool(result), "path": path, "type": export_type}


def get_source_audio_channel_mapping(conn, position: str, track_type: str = "video", track_index: int = 0) -> Dict[str, Any]:
    """Get source audio channel mapping for a timeline item."""
    frame = _record_frame_position(conn, position)
    clip = find_clip_at_position(conn, frame, track_type, track_index)
    if not clip:
        raise ClipNotFound(f"No clip at {position}")
    getter = getattr(clip, "GetSourceAudioChannelMapping", None)
    if not getter:
        raise APICallFailed("GetSourceAudioChannelMapping not available.")
    return {"mapping": getter()}


def get_cache_enabled(conn, position: str, cache_type: str = "color", track_type: str = "video", track_index: int = 0) -> Dict[str, Any]:
    """Check if color/fusion output cache is enabled for a timeline item."""
    frame = _record_frame_position(conn, position)
    clip = find_clip_at_position(conn, frame, track_type, track_index)
    if not clip:
        raise ClipNotFound(f"No clip at {position}")
    if cache_type == "color":
        getter = getattr(clip, "GetIsColorOutputCacheEnabled", None)
    else:
        getter = getattr(clip, "GetIsFusionOutputCacheEnabled", None)
    if not getter:
        raise APICallFailed(f"Get{cache_type.title()}OutputCacheEnabled not available.")
    return {"cache_type": cache_type, "enabled": bool(getter())}


def set_cache_enabled(conn, position: str, cache_type: str = "color", enabled: bool = True, track_type: str = "video", track_index: int = 0) -> Dict[str, Any]:
    """Set color/fusion output cache for a timeline item."""
    frame = _record_frame_position(conn, position)
    clip = find_clip_at_position(conn, frame, track_type, track_index)
    if not clip:
        raise ClipNotFound(f"No clip at {position}")
    if cache_type == "color":
        setter = getattr(clip, "SetColorOutputCache", None)
    else:
        setter = getattr(clip, "SetFusionOutputCache", None)
    if not setter:
        raise APICallFailed(f"Set{cache_type.title()}OutputCache not available.")
    result = setter(enabled)
    return {"cache_type": cache_type, "enabled": enabled, "success": bool(result)}
