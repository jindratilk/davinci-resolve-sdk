"""Verified native timeline duplication with a DRT fallback."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from ..errors import APICallFailed, CapabilityNegotiationFailed, ValidationError
from ..output import set_recoverability, set_verification_status


_TRACK_TYPES = ("video", "audio", "subtitle")
_VOLATILE_CLIP_PROPERTY_KEYS = frozenset({"Cloud Sync", "Usage"})
_DRT_RENAMED_MEDIA_TYPES = frozenset({"Multicam"})
_DRT_REQUIRED_SETTING_KEYS = frozenset(
    {
        "timelineFrameRate",
        "timelineResolutionWidth",
        "timelineResolutionHeight",
    }
)
_DRT_MATERIALIZED_SETTING_KEYS = frozenset(
    {
        "acesVersion",
        "colorAcesMidGray",
        "colorSpaceOutputGamutLimit",
        "hdrDolbyUseExternalCMU",
        "hdrVividControlsOn",
        "hdrVividMasterDisplay",
        "use203NitsReference",
        "useCustomSettings",
    }
)


def _timeline_name(timeline: Any) -> str | None:
    getter = getattr(timeline, "GetName", None)
    if not callable(getter):
        return None
    try:
        value = getter()
    except Exception:
        return None
    name = str(value or "").strip()
    return name or None


def _timeline_identity(timeline: Any) -> str | None:
    for method_name in ("GetUniqueId", "GetUniqueID", "GetId", "GetID"):
        getter = getattr(timeline, method_name, None)
        if not callable(getter):
            continue
        try:
            value = getter()
        except Exception:
            continue
        if value not in (None, ""):
            return f"{method_name}:{value}"
    return None


def _timeline_inventory(conn: Any) -> list[dict[str, Any]]:
    try:
        count = int(conn.project.GetTimelineCount() or 0)
    except Exception as exc:
        raise APICallFailed(
            "Timeline inventory could not be read before duplication.",
            details={"error": str(exc)},
        ) from exc
    rows: list[dict[str, Any]] = []
    for index in range(1, count + 1):
        timeline = conn.project.GetTimelineByIndex(index)
        name = _timeline_name(timeline)
        if timeline is None or not name:
            raise APICallFailed(
                "Timeline inventory returned an unreadable row.",
                details={"index": index, "timeline_count": count},
            )
        rows.append(
            {
                "index": index,
                "name": name,
                "timeline": timeline,
                "identity": _timeline_identity(timeline),
            }
        )
    stable_identities = [row["identity"] for row in rows if row.get("identity")]
    duplicates = sorted(identity for identity, count in Counter(stable_identities).items() if count > 1)
    if duplicates:
        raise APICallFailed(
            "Timeline inventory identities were not unique.",
            details={"duplicate_identities": duplicates},
        )
    return rows


def _resolve_source(rows: list[dict[str, Any]], current: Any, source_name: str | None) -> dict[str, Any]:
    if source_name is None:
        current_name = _timeline_name(current)
        matches = [row for row in rows if row["timeline"] is current or row["name"] == current_name]
    else:
        matches = [row for row in rows if row["name"] == source_name]
    if len(matches) != 1:
        raise ValidationError(
            "Timeline duplicate source must resolve to exactly one timeline.",
            details={"source_name": source_name, "match_count": len(matches)},
        )
    return matches[0]


def _switch_exact(conn: Any, timeline: Any, *, expected_name: str) -> None:
    setter = getattr(conn.project, "SetCurrentTimeline", None)
    if not callable(setter):
        raise APICallFailed("Project.SetCurrentTimeline is required for timeline duplication.")
    result = setter(timeline)
    current = conn.project.GetCurrentTimeline()
    expected_identity = _timeline_identity(timeline)
    current_identity = _timeline_identity(current)
    identity_verified = bool(
        current is timeline
        or (
            expected_identity is not None
            and current_identity is not None
            and current_identity == expected_identity
        )
    )
    if not identity_verified and _timeline_name(current) == expected_name:
        same_name_rows = [row for row in _timeline_inventory(conn) if row["name"] == expected_name]
        identity_verified = len(same_name_rows) == 1
    if not identity_verified:
        raise APICallFailed(
            "Timeline switch did not verify during duplication.",
            details={
                "expected_name": expected_name,
                "expected_identity": expected_identity,
                "actual_name": _timeline_name(current),
                "actual_identity": current_identity,
                "api_result": result,
            },
        )
    conn.timeline = current or timeline


def _playhead(timeline: Any) -> str | None:
    getter = getattr(timeline, "GetCurrentTimecode", None)
    if not callable(getter):
        return None
    try:
        value = getter()
    except Exception:
        return None
    return str(value) if value not in (None, "") else None


def _restore_original(conn: Any, timeline: Any, *, name: str, playhead: str | None) -> dict[str, Any]:
    result = {"timeline": False, "playhead": playhead is None, "errors": []}
    try:
        _switch_exact(conn, timeline, expected_name=name)
        result["timeline"] = True
    except Exception as exc:
        result["errors"].append({"step": "timeline", "type": exc.__class__.__name__, "message": str(exc)})
        return result
    if playhead is not None:
        setter = getattr(timeline, "SetCurrentTimecode", None)
        getter = getattr(timeline, "GetCurrentTimecode", None)
        if not callable(setter) or not callable(getter):
            result["errors"].append({"step": "playhead", "message": "playhead API unavailable"})
        else:
            try:
                api_result = setter(playhead)
                actual = getter()
                result["playhead"] = str(actual) == playhead
                if not result["playhead"]:
                    result["errors"].append(
                        {"step": "playhead", "expected": playhead, "actual": actual, "api_result": api_result}
                    )
            except Exception as exc:
                result["errors"].append({"step": "playhead", "type": exc.__class__.__name__, "message": str(exc)})
    result["ok"] = bool(result["timeline"] and result["playhead"] and not result["errors"])
    return result


def _fusion_graph(item: Any) -> dict[str, Any]:
    count_getter = getattr(item, "GetFusionCompCount", None)
    if not callable(count_getter):
        comp_getter = getattr(item, "GetFusionCompByIndex", None)
        if not callable(comp_getter):
            return {"count": 0, "comps": [], "readable": True}
        try:
            first_comp = comp_getter(1) or comp_getter(0)
        except Exception as exc:
            return {"count": None, "comps": [], "readable": False, "error": str(exc)}
        if first_comp is None:
            return {"count": 0, "comps": [], "readable": True}
        count = 1

        def comp_getter(_index):
            return first_comp
    else:
        try:
            count = int(count_getter() or 0)
        except Exception as exc:
            return {"count": None, "comps": [], "readable": False, "error": str(exc)}
        comp_getter = getattr(item, "GetFusionCompByIndex", None)
    comps: list[dict[str, Any]] = []
    if count and not callable(comp_getter):
        return {"count": count, "comps": [], "readable": False, "error": "GetFusionCompByIndex unavailable"}
    for index in range(1, count + 1):
        try:
            comp = comp_getter(index)
            tool_map = comp.GetToolList(False) if comp is not None and hasattr(comp, "GetToolList") else None
        except Exception as exc:
            return {"count": count, "comps": comps, "readable": False, "error": str(exc)}
        if not isinstance(tool_map, dict):
            return {"count": count, "comps": comps, "readable": False, "error": "Fusion tool list unreadable"}
        tools: list[dict[str, Any]] = []
        for key, tool in tool_map.items():
            try:
                attrs = tool.GetAttrs() if hasattr(tool, "GetAttrs") else {}
            except Exception:
                attrs = {}
            tool_name = str(attrs.get("TOOLS_Name") or getattr(tool, "Name", None) or key)
            reg_id = str(attrs.get("TOOLS_RegID") or "")
            edges: list[dict[str, str | None]] = []
            input_getter = getattr(tool, "GetInputList", None)
            if not callable(input_getter):
                return {"count": count, "comps": comps, "readable": False, "error": f"Fusion inputs unreadable for {tool_name}"}
            try:
                inputs = input_getter() or {}
            except Exception as exc:
                return {"count": count, "comps": comps, "readable": False, "error": str(exc)}
            if not isinstance(inputs, dict):
                return {"count": count, "comps": comps, "readable": False, "error": f"Fusion input list invalid for {tool_name}"}
            for input_key, input_obj in inputs.items():
                try:
                    input_attrs = input_obj.GetAttrs() if hasattr(input_obj, "GetAttrs") else {}
                except Exception as exc:
                    return {"count": count, "comps": comps, "readable": False, "error": str(exc)}
                connected_tool = None
                connected_output = None
                connector = getattr(input_obj, "GetConnectedOutput", None)
                if not callable(connector):
                    return {"count": count, "comps": comps, "readable": False, "error": "Fusion input connection unreadable"}
                try:
                    output = connector()
                    output_attrs = output.GetAttrs() if output is not None and hasattr(output, "GetAttrs") else {}
                    owner = output.GetTool() if output is not None and hasattr(output, "GetTool") else None
                    owner_attrs = owner.GetAttrs() if owner is not None and hasattr(owner, "GetAttrs") else {}
                    connected_tool = str(owner_attrs.get("TOOLS_Name") or getattr(owner, "Name", "")) or None
                    connected_output = str(output_attrs.get("OUTS_Name") or output_attrs.get("OUTS_ID") or "") or None
                except Exception as exc:
                    return {"count": count, "comps": comps, "readable": False, "error": str(exc)}
                edges.append(
                    {
                        "input": str(input_attrs.get("INPS_ID") or input_key),
                        "source_tool": connected_tool,
                        "source_output": connected_output,
                    }
                )
            tools.append({"name": tool_name, "type": reg_id, "inputs": sorted(edges, key=lambda row: row["input"])})
        comps.append({"index": index, "tools": sorted(tools, key=lambda row: (row["name"], row["type"]))})
    return {"count": count, "comps": comps, "readable": True}


def _timeline_structure(timeline: Any) -> dict[str, Any]:
    snapshot: dict[str, Any] = {"name": _timeline_name(timeline), "tracks": [], "errors": []}
    for method_name, key in (
        ("GetStartFrame", "start_frame"),
        ("GetEndFrame", "end_frame"),
        ("GetStartTimecode", "start_timecode"),
        ("GetSetting", "settings"),
        ("GetMarkers", "markers"),
    ):
        method = getattr(timeline, method_name, None)
        if not callable(method):
            continue
        try:
            snapshot[key] = method()
        except Exception as exc:
            snapshot["errors"].append({"method": method_name, "error": str(exc)})
    for track_type in _TRACK_TYPES:
        try:
            count = int(timeline.GetTrackCount(track_type) or 0)
        except Exception as exc:
            snapshot["errors"].append({"method": "GetTrackCount", "track_type": track_type, "error": str(exc)})
            continue
        for track_index in range(1, count + 1):
            try:
                items = list(timeline.GetItemListInTrack(track_type, track_index) or [])
            except Exception as exc:
                snapshot["errors"].append(
                    {"method": "GetItemListInTrack", "track_type": track_type, "track": track_index, "error": str(exc)}
                )
                continue
            track = {"type": track_type, "index": track_index, "items": []}
            track_name_getter = getattr(timeline, "GetTrackName", None)
            if callable(track_name_getter):
                try:
                    track["name"] = track_name_getter(track_type, track_index)
                except Exception:
                    pass
            for item in items:
                row: dict[str, Any] = {}
                for method_name, key in (
                    ("GetName", "name"),
                    ("GetStart", "start"),
                    ("GetEnd", "end"),
                    ("GetDuration", "duration"),
                ):
                    method = getattr(item, method_name, None)
                    if not callable(method):
                        snapshot["errors"].append(
                            {"item": row.get("name"), "method": method_name, "track_type": track_type, "track": track_index}
                        )
                        continue
                    try:
                        value = method()
                        row[key] = int(value) if key in {"start", "end", "duration"} else str(value)
                    except Exception as exc:
                        snapshot["errors"].append(
                            {"item": row.get("name"), "method": method_name, "track_type": track_type, "track": track_index, "error": str(exc)}
                        )
                media_getter = getattr(item, "GetMediaPoolItem", None)
                if callable(media_getter):
                    try:
                        media_item = media_getter()
                    except Exception as exc:
                        snapshot["errors"].append(
                            {
                                "item": row.get("name"),
                                "method": "GetMediaPoolItem",
                                "track_type": track_type,
                                "track": track_index,
                                "error": str(exc),
                            }
                        )
                        media_item = None
                    if media_item is not None:
                        media_name_getter = getattr(media_item, "GetName", None)
                        media_props_getter = getattr(media_item, "GetClipProperty", None)
                        try:
                            media_name = media_name_getter() if callable(media_name_getter) else None
                            media_props = media_props_getter() if callable(media_props_getter) else None
                        except Exception as exc:
                            snapshot["errors"].append(
                                {
                                    "item": row.get("name"),
                                    "method": "MediaPoolItemReadback",
                                    "track_type": track_type,
                                    "track": track_index,
                                    "error": str(exc),
                                }
                            )
                        else:
                            if not isinstance(media_props, dict):
                                snapshot["errors"].append(
                                    {
                                        "item": row.get("name"),
                                        "method": "GetClipProperty",
                                        "track_type": track_type,
                                        "track": track_index,
                                        "payload_type": type(media_props).__name__,
                                    }
                                )
                            else:
                                row["media_pool"] = {
                                    "name": str(media_name or media_props.get("Clip Name") or ""),
                                    "type": str(media_props.get("Type") or ""),
                                    "file_path": str(media_props.get("File Path") or ""),
                                }
                fusion = _fusion_graph(item)
                row["fusion"] = fusion
                if not fusion["readable"]:
                    snapshot["errors"].append(
                        {"item": row.get("name"), "method": "FusionGraph", "track_type": track_type, "track": track_index, "error": fusion.get("error")}
                    )
                track["items"].append(row)
            snapshot["tracks"].append(track)
    snapshot["ok"] = not snapshot["errors"]
    return snapshot


def _structure_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    return deepcopy({key: value for key, value in snapshot.items() if key != "name"})


def _drt_import_generation(name: str) -> tuple[str, int | None]:
    base, separator, suffix = str(name or "").rpartition(" import ")
    if separator and base and suffix.isdigit():
        return base, int(suffix)
    return str(name or ""), None


def _drt_settings_match(source_settings: Any, clone_settings: Any) -> bool:
    if not isinstance(source_settings, dict) or not isinstance(clone_settings, dict):
        return False
    source_keys = set(source_settings)
    clone_keys = set(clone_settings)
    if not _DRT_REQUIRED_SETTING_KEYS.issubset(source_keys & clone_keys):
        return False
    if clone_keys - source_keys - _DRT_MATERIALIZED_SETTING_KEYS:
        return False
    return all(source_settings[key] == clone_settings[key] for key in source_keys & clone_keys)


def _drt_structure_matches(source_snapshot: dict[str, Any], clone_snapshot: dict[str, Any]) -> bool:
    source_payload = _structure_payload(source_snapshot)
    clone_payload = _structure_payload(clone_snapshot)
    if not _drt_settings_match(source_payload.get("settings"), clone_payload.get("settings")):
        return False
    if source_payload == clone_payload:
        return True
    source_payload["settings"] = None
    clone_payload["settings"] = None
    source_tracks = source_payload.get("tracks")
    clone_tracks = clone_payload.get("tracks")
    if not isinstance(source_tracks, list) or not isinstance(clone_tracks, list) or len(source_tracks) != len(clone_tracks):
        return False
    for source_track, clone_track in zip(source_tracks, clone_tracks, strict=True):
        source_items = source_track.get("items")
        clone_items = clone_track.get("items")
        if not isinstance(source_items, list) or not isinstance(clone_items, list) or len(source_items) != len(clone_items):
            return False
        for source_item, clone_item in zip(source_items, clone_items, strict=True):
            if source_item == clone_item:
                continue
            source_media = source_item.get("media_pool")
            clone_media = clone_item.get("media_pool")
            if not isinstance(source_media, dict) or not isinstance(clone_media, dict):
                continue
            source_type = str(source_media.get("type") or "")
            clone_type = str(clone_media.get("type") or "")
            source_media_name = str(source_media.get("name") or "")
            clone_media_name = str(clone_media.get("name") or "")
            source_item_name = str(source_item.get("name") or "")
            clone_item_name = str(clone_item.get("name") or "")
            source_media_base, _source_generation = _drt_import_generation(source_media_name)
            clone_media_base, clone_generation = _drt_import_generation(clone_media_name)
            if (
                source_type not in _DRT_RENAMED_MEDIA_TYPES
                or clone_type != source_type
                or not source_media_name
                or clone_generation is None
                or clone_media_name == source_media_name
                or clone_media_base != source_media_base
                or not source_item_name.startswith(source_media_name)
                or not clone_item_name.startswith(clone_media_name)
                or source_item_name[len(source_media_name):] != clone_item_name[len(clone_media_name):]
            ):
                continue
            clone_item["name"] = source_item_name
            clone_media["name"] = source_media_name
    return source_payload == clone_payload


def _clip_identity(clip: Any) -> str | None:
    for method_name in ("GetUniqueId", "GetUniqueID", "GetMediaId", "GetMediaID", "GetId", "GetID"):
        getter = getattr(clip, method_name, None)
        if not callable(getter):
            continue
        try:
            value = getter()
        except Exception:
            continue
        if value not in (None, ""):
            return f"{method_name}:{value}"
    return None


def _folder_identity(folder: Any) -> str | None:
    for method_name in ("GetUniqueId", "GetUniqueID", "GetId", "GetID"):
        getter = getattr(folder, method_name, None)
        if not callable(getter):
            continue
        try:
            value = getter()
        except Exception:
            continue
        if value not in (None, ""):
            return f"{method_name}:{value}"
    return None


def _canonical_snapshot_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    if isinstance(value, dict):
        return {
            str(key): _canonical_snapshot_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_snapshot_value(item) for item in value]
    if isinstance(value, set):
        normalized = [_canonical_snapshot_value(item) for item in value]
        return sorted(normalized, key=repr)
    return str(value)


def _clip_description(clip: Any, folder_path: str) -> dict[str, Any]:
    name = None
    getter = getattr(clip, "GetName", None)
    if callable(getter):
        try:
            name = getter()
        except Exception:
            pass
    prop_getter = getattr(clip, "GetClipProperty", None)
    if not callable(prop_getter):
        raise APICallFailed(
            "Media Pool clip properties are required for safe DRT timeline duplication.",
            details={"folder": folder_path},
        )
    try:
        raw = prop_getter()
    except Exception as exc:
        raise APICallFailed(
            "Media Pool clip properties could not be read.",
            details={"folder": folder_path, "error": str(exc)},
        ) from exc
    if not isinstance(raw, dict):
        raise APICallFailed(
            "Media Pool clip properties returned an invalid payload.",
            details={"folder": folder_path, "payload_type": type(raw).__name__},
        )
    stable_raw = {
        key: value
        for key, value in raw.items()
        if str(key) not in _VOLATILE_CLIP_PROPERTY_KEYS
    }
    props = _canonical_snapshot_value(stable_raw)
    return {
        "name": str(name or props.get("Clip Name") or ""),
        "folder": folder_path,
        "type": str(props.get("Type") or ""),
        "file_path": str(props.get("File Path") or ""),
        # Preserve the complete canonical stable property map. `Cloud Sync` is
        # an asynchronous runtime state (queue/progress/success/failure), while
        # `Usage` is a derived count of timeline references and necessarily
        # changes while a DRT candidate exists. Neither is user metadata.
        "properties": props,
    }


def _media_pool_snapshot(conn: Any) -> dict[str, Any]:
    root_getter = getattr(conn.media_pool, "GetRootFolder", None)
    if not callable(root_getter):
        raise APICallFailed("Media Pool root is required for safe DRT timeline duplication.")
    root = root_getter()
    if root is None:
        raise APICallFailed("Media Pool root was unavailable for safe DRT timeline duplication.")
    clips: dict[str, dict[str, Any]] = {}
    unkeyed: list[dict[str, Any]] = []
    folders: dict[str, Any] = {}
    unkeyed_folders: list[dict[str, Any]] = []

    def walk(folder: Any, parent: str, ancestor_identities: tuple[str, ...] = ()) -> None:
        name_getter = getattr(folder, "GetName", None)
        try:
            name = str(name_getter() or "") if callable(name_getter) else ""
        except Exception as exc:
            raise APICallFailed("Media Pool folder name could not be read.", details={"parent": parent, "error": str(exc)}) from exc
        path = f"{parent}/{name}" if parent and name else (name or parent or "/")
        folder_identity = _folder_identity(folder)
        folder_row = {
            "object": folder,
            "identity": folder_identity,
            "path": path,
            "clip_ids": [],
            "unkeyed_clip_count": 0,
            "ancestor_identities": list(ancestor_identities),
        }
        if folder_identity is None:
            unkeyed_folders.append(folder_row)
        elif folder_identity in folders:
            raise APICallFailed(
                "Media Pool folder identities were not unique.",
                details={"identity": folder_identity, "first": folders[folder_identity]["path"], "second": path},
            )
        else:
            folders[folder_identity] = folder_row
        try:
            folder_clips = list(folder.GetClipList() or [])
            children = list(folder.GetSubFolderList() or [])
        except Exception as exc:
            raise APICallFailed("Media Pool dependency snapshot failed.", details={"folder": path, "error": str(exc)}) from exc
        for clip in folder_clips:
            description = _clip_description(clip, path)
            identity = _clip_identity(clip)
            if identity is None:
                unkeyed.append({"description": description, "object": clip})
                folder_row["unkeyed_clip_count"] += 1
            elif identity in clips:
                raise APICallFailed(
                    "Media Pool dependency identities were not unique.",
                    details={"identity": identity, "first": clips[identity]["description"], "second": description},
                )
            else:
                clips[identity] = {"description": description, "object": clip}
                folder_row["clip_ids"].append(identity)
        child_ancestors = ancestor_identities + ((folder_identity,) if folder_identity is not None else ())
        for child in children:
            walk(child, path, child_ancestors)

    walk(root, "")
    return {
        "clips": clips,
        "unkeyed": unkeyed,
        "folders": folders,
        "unkeyed_folders": unkeyed_folders,
    }


def _dependency_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_clip_ids = set(before["clips"])
    after_clip_ids = set(after["clips"])
    observed_added_clip_ids = sorted(after_clip_ids - before_clip_ids)
    removed_clip_ids = sorted(before_clip_ids - after_clip_ids)
    changed_clips = [
        {
            "identity": identity,
            "before": before["clips"][identity]["description"],
            "after": after["clips"][identity]["description"],
        }
        for identity in sorted(before_clip_ids & after_clip_ids)
        if before["clips"][identity]["description"] != after["clips"][identity]["description"]
    ]
    before_unkeyed = Counter(str(row["description"]) for row in before["unkeyed"])
    after_unkeyed = Counter(str(row["description"]) for row in after["unkeyed"])
    added_unkeyed = after_unkeyed - before_unkeyed
    removed_unkeyed = before_unkeyed - after_unkeyed
    unproven = list(added_unkeyed.elements())
    unproven.extend(after["clips"][identity]["description"] for identity in observed_added_clip_ids)
    unproven_existing_items = [
        {"change": "removed", "identity": identity, "before": before["clips"][identity]["description"]}
        for identity in removed_clip_ids
    ]
    unproven_existing_items.extend({"change": "changed", **row} for row in changed_clips)
    unproven_existing_items.extend(
        {"change": "removed_unkeyed", "description": description}
        for description in removed_unkeyed.elements()
    )
    before_folder_ids = set(before["folders"])
    after_folder_ids = set(after["folders"])
    observed_added_folder_ids = sorted(
        after_folder_ids - before_folder_ids,
        key=lambda value: after["folders"][value]["path"].count("/"),
        reverse=True,
    )
    removed_folder_ids = sorted(before_folder_ids - after_folder_ids)
    changed_folders = [
        {
            "identity": identity,
            "before_path": before["folders"][identity]["path"],
            "after_path": after["folders"][identity]["path"],
        }
        for identity in sorted(before_folder_ids & after_folder_ids)
        if before["folders"][identity]["path"] != after["folders"][identity]["path"]
    ]
    before_unkeyed_folders = Counter(row["path"] for row in before.get("unkeyed_folders", []))
    after_unkeyed_folders = Counter(row["path"] for row in after.get("unkeyed_folders", []))
    added_unkeyed_folders = after_unkeyed_folders - before_unkeyed_folders
    removed_unkeyed_folders = before_unkeyed_folders - after_unkeyed_folders
    unproven_folders = list(added_unkeyed_folders.elements())
    unproven_folders.extend(after["folders"][identity]["path"] for identity in observed_added_folder_ids)
    unproven_existing_folders = [
        {"change": "removed", "identity": identity, "before_path": before["folders"][identity]["path"]}
        for identity in removed_folder_ids
    ]
    unproven_existing_folders.extend({"change": "changed", **row} for row in changed_folders)
    unproven_existing_folders.extend(
        {"change": "removed_unkeyed", "path": path}
        for path in removed_unkeyed_folders.elements()
    )
    return {
        # A before/after delta proves novelty, not that DRT import caused it. Never
        # delete these objects during rollback without a direct API provenance handle.
        "added_clip_ids": [],
        "added_folder_ids": [],
        "added_folder_paths": [],
        "unproven_added_folders": unproven_folders,
        "unproven_added_items": unproven,
        "unproven_existing_folders": unproven_existing_folders,
        "unproven_existing_items": unproven_existing_items,
        "clip_count": len(observed_added_clip_ids) + sum(added_unkeyed.values()),
        "proven_clip_count": 0,
        "folder_count": len(observed_added_folder_ids) + sum(added_unkeyed_folders.values()),
        "proven_folder_count": 0,
        "sample": [after["clips"][identity]["description"] for identity in observed_added_clip_ids[:10]],
    }


def _delete_timeline(conn: Any, timeline: Any, *, name: str) -> dict[str, Any]:
    deleter = getattr(conn.media_pool, "DeleteTimelines", None)
    if not callable(deleter):
        return {"attempted": False, "verified": False, "error": "MediaPool.DeleteTimelines unavailable"}
    try:
        candidate_identity = _timeline_identity(timeline)
        before_rows = _timeline_inventory(conn)
        api_result = deleter([timeline])
        after_rows = _timeline_inventory(conn)
        verified_absent = not any(
            row["timeline"] is timeline
            or (candidate_identity is not None and row.get("identity") == candidate_identity)
            for row in after_rows
        )
        return {
            "attempted": True,
            "api_result": api_result,
            "verified": api_result is True and verified_absent,
            "candidate_identity": candidate_identity,
            "before_name_count": sum(1 for row in before_rows if row["name"] == name),
            "after_name_count": sum(1 for row in after_rows if row["name"] == name),
            "verified_absent": verified_absent,
        }
    except Exception as exc:
        return {"attempted": True, "verified": False, "error": str(exc)}


def _delete_dependencies(conn: Any, after: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    result = {
        "clips": [],
        "folders": [],
        "unproven_added_items": delta["unproven_added_items"],
        "unproven_added_folders": delta["unproven_added_folders"],
        "unproven_existing_items": delta["unproven_existing_items"],
        "unproven_existing_folders": delta["unproven_existing_folders"],
    }
    clip_deleter = getattr(conn.media_pool, "DeleteClips", None)
    for identity in delta["added_clip_ids"]:
        row = after["clips"][identity]
        if row["description"].get("type", "").casefold() == "timeline":
            result["clips"].append(
                {
                    "identity": identity,
                    "description": row["description"],
                    "deleted": True,
                    "cleanup_route": "MediaPool.DeleteTimelines",
                }
            )
            continue
        entry = {"identity": identity, "description": row["description"], "deleted": False}
        if callable(clip_deleter):
            try:
                entry["api_result"] = clip_deleter([row["object"]])
                entry["deleted"] = entry["api_result"] is not False
            except Exception as exc:
                entry["error"] = str(exc)
        else:
            entry["error"] = "MediaPool.DeleteClips unavailable"
        result["clips"].append(entry)
    folder_deleter = getattr(conn.media_pool, "DeleteFolders", None)
    for folder_identity in delta["added_folder_ids"]:
        folder_row = after["folders"][folder_identity]
        path = folder_row["path"]
        entry = {"identity": folder_identity, "path": path, "deleted": False}
        if callable(folder_deleter):
            try:
                entry["api_result"] = folder_deleter([folder_row["object"]])
                entry["deleted"] = entry["api_result"] is not False
            except Exception as exc:
                entry["error"] = str(exc)
        else:
            entry["error"] = "MediaPool.DeleteFolders unavailable"
        result["folders"].append(entry)
    try:
        post = _media_pool_snapshot(conn)
        for row in result["clips"]:
            row["verified_absent"] = row["identity"] not in post["clips"]
        for row in result["folders"]:
            row["verified_absent"] = row["identity"] not in post["folders"]
    except Exception as exc:
        result["readback_error"] = str(exc)
        for row in result["clips"]:
            row["verified_absent"] = False
        for row in result["folders"]:
            row["verified_absent"] = False
    result["verified"] = bool(
        not result["unproven_added_items"]
        and not result["unproven_added_folders"]
        and not result["unproven_existing_items"]
        and not result["unproven_existing_folders"]
        and all(row["deleted"] and row["verified_absent"] for row in result["clips"])
        and all(row["deleted"] and row["verified_absent"] for row in result["folders"])
    )
    return result


def _method_unavailable(exc: Exception) -> bool:
    if isinstance(exc, CapabilityNegotiationFailed):
        return True
    if isinstance(exc, AttributeError):
        return True
    if not isinstance(exc, APICallFailed):
        return False
    text = str(exc).strip().casefold()
    return (
        text == "unsupported embedded davinci resolve method: duplicatetimeline"
        or text.endswith("method not available: duplicatetimeline")
    )


def _identify_single_new_timeline(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    *,
    result_hint: Any = None,
) -> dict[str, Any]:
    new_rows = _new_timeline_rows(before, after)
    if result_hint is not None and result_hint is not False and result_hint is not True:
        hint_identity = _timeline_identity(result_hint)
        hinted = [
            row
            for row in after
            if row["timeline"] is result_hint
            or (hint_identity is not None and row.get("identity") == hint_identity)
        ]
        hint_was_existing = any(
            row["timeline"] is result_hint
            or (hint_identity is not None and row.get("identity") == hint_identity)
            for row in before
        )
        if len(hinted) == 1 and not hint_was_existing:
            return {**hinted[0], "provenance": "api_result_identity"}
    if len(new_rows) != 1:
        raise APICallFailed(
            "Timeline duplication did not create exactly one independently identifiable timeline.",
            details={"before": [row["name"] for row in before], "after": [row["name"] for row in after], "new_count": len(new_rows)},
        )
    return {**new_rows[0], "provenance": "exclusive_before_after_delta"}


def _new_timeline_rows(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[dict[str, Any]]:
    new_rows: list[dict[str, Any]] = []
    before_ids = {row["identity"] for row in before if row.get("identity")}
    stable_identity_reliable = bool(before) and all(row.get("identity") for row in before + after)
    object_identity_reliable = all(
        any(after_row["timeline"] is before_row["timeline"] for after_row in after)
        for before_row in before
    )
    if stable_identity_reliable:
        new_rows = [row for row in after if row["identity"] not in before_ids]
    elif object_identity_reliable:
        new_rows = [
            row
            for row in after
            if not any(row["timeline"] is before_row["timeline"] for before_row in before)
        ]
    else:
        before_names = Counter(row["name"] for row in before)
        after_names = Counter(row["name"] for row in after)
        independently_new_names = {
            name for name, count in after_names.items()
            if before_names[name] == 0 and count == 1
        }
        new_rows = [row for row in after if row["name"] in independently_new_names]
    return new_rows


def _rename_imported_timeline(conn: Any, timeline: Any, requested_name: str) -> None:
    if _timeline_name(timeline) != requested_name:
        setter = getattr(timeline, "SetName", None)
        if not callable(setter):
            raise APICallFailed(
                "Imported DRT timeline cannot be assigned the requested collision-safe name.",
                details={"requested_name": requested_name, "imported_name": _timeline_name(timeline)},
            )
        api_result = setter(requested_name)
        if _timeline_name(timeline) != requested_name:
            raise APICallFailed(
                "Imported DRT timeline rename did not verify.",
                details={"requested_name": requested_name, "actual_name": _timeline_name(timeline), "api_result": api_result},
            )
    _assert_unique_target_name(conn, timeline, requested_name)


def _assert_unique_target_name(conn: Any, timeline: Any, requested_name: str) -> None:
    matching = [row for row in _timeline_inventory(conn) if row["name"] == requested_name]
    timeline_identity = _timeline_identity(timeline)
    candidate_matches = [
        row
        for row in matching
        if row["timeline"] is timeline
        or (timeline_identity is not None and row.get("identity") == timeline_identity)
    ]
    if len(matching) != 1 or (timeline_identity is not None and len(candidate_matches) != 1):
        raise APICallFailed(
            "Timeline duplicate target name is no longer globally unique.",
            details={
                "requested_name": requested_name,
                "name_match_count": len(matching),
                "candidate_match_count": len(candidate_matches),
            },
        )
    if _timeline_name(timeline) != requested_name:
        raise APICallFailed(
            "Timeline duplicate candidate identity did not retain the requested name.",
            details={"requested_name": requested_name, "actual_name": _timeline_name(timeline)},
        )


def duplicate_timeline(conn: Any, new_name: str, source_name: str | None = None, *, allow_drt: bool = True) -> dict[str, Any]:
    """Duplicate a timeline through native API or a verified DRT fallback."""
    requested_name = str(new_name or "").strip()
    requested_source = str(source_name).strip() if source_name is not None else None
    if not requested_name:
        raise ValidationError("Timeline duplicate name is required.", details={"new_name": new_name})
    if requested_source == "":
        requested_source = None

    before_timelines = _timeline_inventory(conn)
    if requested_name in {row["name"] for row in before_timelines}:
        raise ValidationError(
            "Timeline duplicate target name already exists.",
            details={"new_name": requested_name},
        )
    original_timeline = conn.project.GetCurrentTimeline() or getattr(conn, "timeline", None)
    original_name = _timeline_name(original_timeline)
    if original_timeline is None or not original_name:
        raise APICallFailed("Timeline duplicate requires a readable current timeline.")
    original_playhead = _playhead(original_timeline)
    source_row = _resolve_source(before_timelines, original_timeline, requested_source)
    source_timeline = source_row["timeline"]
    source_name_resolved = source_row["name"]
    candidate: dict[str, Any] | None = None
    dependency_before: dict[str, Any] | None = None
    dependency_after: dict[str, Any] | None = None
    dependency_delta: dict[str, Any] = {
        "added_clip_ids": [], "added_folder_ids": [], "added_folder_paths": [], "unproven_added_folders": [], "unproven_added_items": [], "unproven_existing_folders": [], "unproven_existing_items": [], "clip_count": 0, "proven_clip_count": 0, "folder_count": 0, "proven_folder_count": 0, "sample": []
    }
    route = "timeline.DuplicateTimeline"
    native_error: dict[str, Any] | None = None

    source_before: dict[str, Any] | None = None
    try:
        _switch_exact(conn, source_timeline, expected_name=source_name_resolved)
        source_before = _timeline_structure(source_timeline)
        if not source_before["ok"]:
            raise APICallFailed(
                "Source timeline could not be deeply read before duplication.",
                details={"source": source_name_resolved, "readback": source_before},
            )
        duplicate_method = getattr(source_timeline, "DuplicateTimeline", None)
        use_drt = not callable(duplicate_method)
        if callable(duplicate_method):
            try:
                api_result = duplicate_method(requested_name)
                if hasattr(conn, "refresh"):
                    conn.refresh()
                candidate = _identify_single_new_timeline(
                    before_timelines,
                    _timeline_inventory(conn),
                    result_hint=api_result,
                )
                if candidate.get("provenance") != "api_result_identity":
                    raise APICallFailed(
                        "Native timeline duplicate did not return an independently attributable timeline.",
                        details={"provenance": candidate.get("provenance")},
                    )
                if _timeline_name(candidate["timeline"]) != requested_name:
                    raise APICallFailed(
                        "Native timeline duplicate did not use the requested name.",
                        details={"requested_name": requested_name, "actual_name": _timeline_name(candidate["timeline"]), "api_result": api_result},
                    )
                _assert_unique_target_name(conn, candidate["timeline"], requested_name)
            except Exception as exc:
                after_native = _timeline_inventory(conn)
                if (
                    Counter(row["name"] for row in after_native) != Counter(row["name"] for row in before_timelines)
                    or not _method_unavailable(exc)
                ):
                    raise
                native_error = {"type": exc.__class__.__name__, "message": str(exc)}
                use_drt = True

        if use_drt:
            if not allow_drt:
                raise CapabilityNegotiationFailed("This workflow requires native timeline duplication without DRT import.")
            route = "timeline.Export(DRT) -> media_pool.ImportTimelineFromFile -> timeline.SetName"
            dependency_before = _media_pool_snapshot(conn)
            with TemporaryDirectory(prefix="cutagent-timeline-duplicate-") as temp_dir:
                drt_path = Path(temp_dir) / "timeline-copy.drt"
                export_method = getattr(source_timeline, "Export", None)
                import_method = getattr(conn.media_pool, "ImportTimelineFromFile", None)
                if not callable(export_method) or not callable(import_method):
                    raise CapabilityNegotiationFailed(
                        "Timeline duplicate requires DuplicateTimeline or DRT export/import support.",
                        details={"DuplicateTimeline": callable(duplicate_method), "Timeline.Export": callable(export_method), "ImportTimelineFromFile": callable(import_method)},
                    )
                export_format = getattr(getattr(conn, "resolve", None), "EXPORT_DRT", 3)
                export_result = export_method(str(drt_path), export_format)
                if export_result is False or not drt_path.is_file() or drt_path.stat().st_size <= 0:
                    raise APICallFailed(
                        "Timeline DRT export did not produce a readable artifact.",
                        details={"api_result": export_result, "path_exists": drt_path.exists()},
                    )
                import_result = import_method(str(drt_path))
                if import_result is None or import_result is False:
                    raise APICallFailed("Timeline DRT import failed.")
                if hasattr(conn, "refresh"):
                    conn.refresh()
                candidate = _identify_single_new_timeline(
                    before_timelines,
                    _timeline_inventory(conn),
                    result_hint=import_result,
                )
                if candidate.get("provenance") != "api_result_identity":
                    raise APICallFailed(
                        "Timeline DRT import did not return an independently attributable timeline.",
                        details={"provenance": candidate.get("provenance")},
                    )
                dependency_after = _media_pool_snapshot(conn)
                dependency_delta = _dependency_delta(dependency_before, dependency_after)
                if dependency_delta["unproven_existing_items"] or dependency_delta["unproven_existing_folders"]:
                    raise APICallFailed(
                        "Timeline DRT import changed or removed pre-existing Media Pool objects.",
                        details={
                            "items": dependency_delta["unproven_existing_items"],
                            "folders": dependency_delta["unproven_existing_folders"],
                        },
                    )
                _rename_imported_timeline(conn, candidate["timeline"], requested_name)
                candidate["name"] = requested_name

        if candidate is None:
            raise APICallFailed("Timeline duplication did not expose a new timeline for verification.")
        _assert_unique_target_name(conn, candidate["timeline"], requested_name)
        _switch_exact(conn, candidate["timeline"], expected_name=requested_name)
        clone = _timeline_structure(candidate["timeline"])
        _switch_exact(conn, source_timeline, expected_name=source_name_resolved)
        source_after = _timeline_structure(source_timeline)
        structure_match = bool(
            clone["ok"]
            and source_after["ok"]
            and _drt_structure_matches(source_before, clone)
            and source_after == source_before
        )
        if not structure_match:
            raise APICallFailed(
                "Duplicated timeline failed deep structural verification.",
                details={"source_before": source_before, "source_after": source_after, "clone": clone},
            )
        _assert_unique_target_name(conn, candidate["timeline"], requested_name)
        restoration = _restore_original(conn, original_timeline, name=original_name, playhead=original_playhead)
        if not restoration.get("ok"):
            raise APICallFailed(
                "Duplicated timeline verified, but original timeline/playhead restoration failed.",
                details={"restoration": restoration},
            )
        set_verification_status("verified")
        set_recoverability("manual")
        return {
            "action": "timeline.duplicate",
            "changed": True,
            "source": {"kind": "timeline", "name": source_name_resolved, "index": source_row["index"]},
            "target": {"kind": "timeline", "name": requested_name},
            "route": route,
            "native_fallback_reason": native_error,
            "verification": {
                "verified": True,
                "deep_structure_match": True,
                "source_unchanged": True,
                "source": source_after,
                "clone": clone,
                "restoration": restoration,
            },
            "imported_dependencies": {
                "clip_count": dependency_delta["clip_count"],
                "proven_clip_count": dependency_delta["proven_clip_count"],
                "folder_count": dependency_delta["folder_count"],
                "proven_folder_count": dependency_delta["proven_folder_count"],
                "sample": dependency_delta["sample"],
                "unproven_added_items": dependency_delta["unproven_added_items"],
                "unproven_added_folders": dependency_delta["unproven_added_folders"],
                "unproven_existing_items": dependency_delta["unproven_existing_items"],
                "unproven_existing_folders": dependency_delta["unproven_existing_folders"],
            },
            "message": f"Duplicated timeline '{source_name_resolved}' to '{requested_name}'.",
        }
    except Exception as exc:
        restoration = _restore_original(conn, original_timeline, name=original_name, playhead=original_playhead)
        try:
            observed_new_timelines = _new_timeline_rows(before_timelines, _timeline_inventory(conn))
        except Exception:
            observed_new_timelines = []
        proven_candidate = candidate if candidate is not None and candidate.get("provenance") == "api_result_identity" else None
        created_timelines = [proven_candidate] if proven_candidate is not None else []
        proven_identity = proven_candidate.get("identity") if proven_candidate is not None else None
        unproven_timelines = [
            {"name": row.get("name"), "identity": row.get("identity")}
            for row in observed_new_timelines
            if proven_candidate is None
            or not (
                row["timeline"] is proven_candidate["timeline"]
                or (proven_identity is not None and row.get("identity") == proven_identity)
            )
        ]
        timeline_cleanup = [
            _delete_timeline(conn, row["timeline"], name=str(row.get("name") or _timeline_name(row["timeline"])))
            for row in reversed(created_timelines)
        ]
        if dependency_before is not None:
            try:
                dependency_after = _media_pool_snapshot(conn)
                dependency_delta = _dependency_delta(dependency_before, dependency_after)
            except Exception:
                dependency_after = None
        dependency_cleanup = (
            _delete_dependencies(conn, dependency_after, dependency_delta)
            if dependency_after is not None
            else {
                "verified": dependency_before is None,
                "clips": [],
                "folders": [],
                "unproven_added_folders": [],
                "unproven_added_items": ["post-import dependency snapshot unavailable"] if dependency_before is not None else [],
                "unproven_existing_folders": [],
                "unproven_existing_items": [],
            }
        )
        cleanup_verified = bool(
            restoration.get("ok")
            and not unproven_timelines
            and all(row.get("verified") for row in timeline_cleanup)
            and dependency_cleanup.get("verified")
        )
        set_verification_status("failed")
        raise APICallFailed(
            "Timeline duplication failed and was rolled back where new objects were independently proven.",
            details={
                "cause": {"type": exc.__class__.__name__, "message": str(exc), "details": getattr(exc, "details", None)},
                "route": route,
                "restoration": restoration,
                "timeline_cleanup": timeline_cleanup,
                "unproven_timelines": unproven_timelines,
                "dependency_cleanup": dependency_cleanup,
            },
            recoverability="retryable" if cleanup_verified else "manual",
        ) from exc
