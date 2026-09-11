"""Media Pool operations — Import, folders, search, metadata."""

from __future__ import annotations

import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Optional, List, Dict, Any

from ..errors import APICallFailed, CapabilityNegotiationFailed, FolderNotFound, InvalidTimeReference, MissingArgumentError, ValidationError
from ..policy import require_any_api_method, require_api_method
from ..utils.time_ref import parse_record_frame, parse_source_frame
from ..utils.timecode import parse_time_input, seconds_to_frames

_CANONICAL_SOURCE_KEYS = ("File Path", "Source File", "SourcePath")
_MEDIA_KIND_VALUES = {"media", "timeline", "subtitle"}
_APPEND_TRACK_TYPES = {"video", "audio"}
_CLIP_COLOR_VALUES = {
    "apricot": "Apricot",
    "beige": "Beige",
    "blue": "Blue",
    "brown": "Brown",
    "chocolate": "Chocolate",
    "green": "Green",
    "lime": "Lime",
    "navy": "Navy",
    "olive": "Olive",
    "orange": "Orange",
    "pink": "Pink",
    "purple": "Purple",
    "tan": "Tan",
    "teal": "Teal",
    "violet": "Violet",
    "yellow": "Yellow",
}
_FLAG_COLOR_VALUES = {
    "blue": "Blue",
    "cocoa": "Cocoa",
    "cream": "Cream",
    "cyan": "Cyan",
    "fuchsia": "Fuchsia",
    "green": "Green",
    "lavender": "Lavender",
    "lemon": "Lemon",
    "mint": "Mint",
    "pink": "Pink",
    "purple": "Purple",
    "red": "Red",
    "rose": "Rose",
    "sand": "Sand",
    "sky": "Sky",
    "yellow": "Yellow",
}

_AUDIO_SYNC_MODE_MAP = {
    "timecode": "AUDIO_SYNC_TIMECODE",
    "waveform": "AUDIO_SYNC_WAVEFORM",
}

_AUTO_CAPTION_LANGUAGE_MAP = {
    "auto": "AUTO_CAPTION_AUTO",
    "danish": "AUTO_CAPTION_DANISH",
    "dutch": "AUTO_CAPTION_DUTCH",
    "english": "AUTO_CAPTION_ENGLISH",
    "french": "AUTO_CAPTION_FRENCH",
    "german": "AUTO_CAPTION_GERMAN",
    "italian": "AUTO_CAPTION_ITALIAN",
    "japanese": "AUTO_CAPTION_JAPANESE",
    "korean": "AUTO_CAPTION_KOREAN",
    "mandarin-simplified": "AUTO_CAPTION_MANDARIN_SIMPLIFIED",
    "mandarin-traditional": "AUTO_CAPTION_MANDARIN_TRADITIONAL",
    "norwegian": "AUTO_CAPTION_NORWEGIAN",
    "portuguese": "AUTO_CAPTION_PORTUGUESE",
    "russian": "AUTO_CAPTION_RUSSIAN",
    "spanish": "AUTO_CAPTION_SPANISH",
    "swedish": "AUTO_CAPTION_SWEDISH",
}

_AUTO_CAPTION_PRESET_MAP = {
    "default": "AUTO_CAPTION_SUBTITLE_DEFAULT",
    "teletext": "AUTO_CAPTION_TELETEXT",
    "netflix": "AUTO_CAPTION_NETFLIX",
}

_AUTO_CAPTION_LINE_BREAK_MAP = {
    "single": "AUTO_CAPTION_LINE_SINGLE",
    "double": "AUTO_CAPTION_LINE_DOUBLE",
}


def _resolve_api_constant(conn, constant_name: str):
    value = getattr(conn.resolve, constant_name, None)
    if value is None:
        raise APICallFailed(
            "DaVinci Resolve constant not available.",
            details={"constant": constant_name},
        )
    return value


def _normalize_auto_caption_language(language: Optional[str]) -> Optional[str]:
    if language is None:
        return None
    key = str(language).strip().lower().replace("_", "-")
    if key not in _AUTO_CAPTION_LANGUAGE_MAP:
        raise ValidationError(
            "Unsupported auto-caption language.",
            details={"language": language, "allowed": sorted(_AUTO_CAPTION_LANGUAGE_MAP)},
        )
    return _AUTO_CAPTION_LANGUAGE_MAP[key]


def _normalize_auto_caption_preset(preset: Optional[str]) -> Optional[str]:
    if preset is None:
        return None
    key = str(preset).strip().lower()
    if key not in _AUTO_CAPTION_PRESET_MAP:
        raise ValidationError(
            "Unsupported auto-caption preset.",
            details={"preset": preset, "allowed": sorted(_AUTO_CAPTION_PRESET_MAP)},
        )
    return _AUTO_CAPTION_PRESET_MAP[key]


def _normalize_auto_caption_line_break(line_break: Optional[str]) -> Optional[str]:
    if line_break is None:
        return None
    key = str(line_break).strip().lower()
    if key not in _AUTO_CAPTION_LINE_BREAK_MAP:
        raise ValidationError(
            "Unsupported auto-caption line break mode.",
            details={"line_break": line_break, "allowed": sorted(_AUTO_CAPTION_LINE_BREAK_MAP)},
        )
    return _AUTO_CAPTION_LINE_BREAK_MAP[key]


def _normalize_audio_sync_mode(mode: Optional[str]) -> Optional[str]:
    if mode is None:
        return None
    key = str(mode).strip().lower()
    if key not in _AUDIO_SYNC_MODE_MAP:
        raise ValidationError(
            "Unsupported audio sync mode.",
            details={"mode": mode, "allowed": sorted(_AUDIO_SYNC_MODE_MAP)},
        )
    return _AUDIO_SYNC_MODE_MAP[key]


def _split_folder_path(root, path: str) -> list[str]:
    """Split a user folder path and ignore an explicit root-folder prefix."""
    segments = re.split(r"[/>]+", str(path or "").strip())
    segments = [s.strip() for s in segments if s.strip()]
    root_name = root.GetName() if root and hasattr(root, "GetName") else ""
    if segments and root_name and segments[0] == root_name:
        segments = segments[1:]
    return segments


def navigate_folder(conn, path: str, create: bool = False):
    """
    Navigate to a folder by path (A/B/C or A > B > C).
    
    Args:
        conn: ResolveConnection instance
        path: Folder path (slash or > separated)
        create: Create folders if they don't exist
    
    Returns:
        Folder object
    
    Raises:
        FolderNotFound: If folder doesn't exist and create=False
        APICallFailed: If folder creation fails
    """
    root = conn.media_pool.GetRootFolder()
    segments = _split_folder_path(root, path)
    current = root
    current_path = root.GetName() if root and hasattr(root, "GetName") else ""

    for seg in segments:
        subfolders = current.GetSubFolderList() or []
        found = None
        for sf in subfolders:
            if sf.GetName() == seg:
                found = sf
                break

        if found:
            current = found
        elif create:
            new_folder = conn.media_pool.AddSubFolder(current, seg)
            if not new_folder:
                raise APICallFailed(f"Failed to create subfolder '{seg}'.")
            current = new_folder
        else:
            raise FolderNotFound(
                f"Folder '{seg}' not found in '{current_path or 'Media Pool root'}'.",
                details={"path": path, "missing_segment": seg, "parent": current_path},
            )
        current_path = f"{current_path}/{seg}" if current_path else seg

    return current


def find_clip(conn, name: str):
    """
    Find a clip by name in current folder.
    
    Args:
        conn: ResolveConnection instance
        name: Clip name
    
    Returns:
        Clip object or None
    """
    match = find_clip_match(conn, name)
    return match["clip"] if match else None


def find_clip_match(conn, name: str) -> Optional[dict[str, Any]]:
    """Find a clip with folder context, preferring the current folder."""
    folder = conn.media_pool.GetCurrentFolder()
    if not folder:
        return None

    current_folder_path = _get_folder_path(conn.media_pool.GetRootFolder(), folder)
    clips = folder.GetClipList() or []
    current_matches = []
    for clip in clips:
        if hasattr(clip, "GetName") and clip.GetName() == name:
            current_matches.append(
                {
                    "clip": clip,
                    "name": name,
                    "folder": current_folder_path,
                }
            )
    if current_matches:
        return current_matches[0]

    root = conn.media_pool.GetRootFolder()
    if not root:
        return None

    matches: list[dict[str, Any]] = []
    _collect_clip_matches(root, name, "", matches)
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]

    raise ValidationError(
        "Clip name is ambiguous in Media Pool.",
        details={
            "clip": name,
            "candidates": [{"name": m["name"], "folder": m["folder"]} for m in matches],
        },
    )


def _collect_clip_object_matches(
    folder,
    matches: list[dict[str, Any]],
    path: str = "",
    *,
    current_path_override: str | None = None,
    recursive: bool = True,
) -> None:
    folder_name = folder.GetName() if hasattr(folder, "GetName") else ""
    current_path = current_path_override if current_path_override is not None else f"{path}/{folder_name}" if path else str(folder_name)
    for clip in folder.GetClipList() or []:
        props = _clip_properties(clip)
        matches.append(
            {
                "clip": clip,
                "name": clip.GetName() if hasattr(clip, "GetName") else "",
                "folder": current_path,
                "props": props,
                "media_id": _clip_media_id(clip, props),
                "source_path": _canonical_source_path(props, clip),
            }
        )
    if not recursive:
        return
    for subfolder in folder.GetSubFolderList() or []:
        _collect_clip_object_matches(subfolder, matches, current_path)


def _clip_media_id(clip, props: dict[str, Any]) -> str | None:
    for method_name in ("GetMediaId", "GetUniqueId"):
        getter = getattr(clip, method_name, None)
        if callable(getter):
            try:
                value = getter()
            except Exception:
                value = None
            if value:
                return str(value)
    for key in ("MediaId", "Media ID", "media_id", "Id", "ID"):
        value = props.get(key)
        if value:
            return str(value)
    return None


def _append_match_key(match: dict[str, Any]) -> tuple[int, str, str]:
    clip = match.get("clip")
    return (id(clip), str(match.get("folder") or ""), str(match.get("name") or ""))


def _dedupe_append_matches(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[int, str, str]] = set()
    for match in matches:
        key = _append_match_key(match)
        if key in seen:
            continue
        seen.add(key)
        unique.append(match)
    return unique


def _append_entry_target_folders(entries: list[dict[str, Any]] | None) -> list[str]:
    if not entries:
        return []
    folders: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            return []
        folder = str(entry.get("folder") or "").strip().strip("/")
        if not folder:
            return []
        folders.append(folder)
    return sorted(set(folders))


def _append_folder_is_root_prefixed(root, folder_path: str) -> bool:
    segments = re.split(r"[/>]+", str(folder_path or "").strip())
    segments = [s.strip() for s in segments if s.strip()]
    root_name = root.GetName() if root and hasattr(root, "GetName") else ""
    return bool(segments and root_name and segments[0] == root_name)


def _append_folder_path_matches(folder_path: str, requested_folder: str) -> bool:
    folder_text = str(requested_folder or "").strip().strip("/")
    candidate = str(folder_path or "").strip().strip("/")
    return bool(folder_text and (candidate == folder_text or candidate.endswith("/" + folder_text)))


def _collect_append_folder_matches(
    folder,
    requested_folders: list[str],
    folder_matches: list[tuple[Any, str]],
    path: str = "",
) -> None:
    folder_name = folder.GetName() if hasattr(folder, "GetName") else ""
    current_path = f"{path}/{folder_name}" if path else str(folder_name)
    if any(_append_folder_path_matches(current_path, requested) for requested in requested_folders):
        folder_matches.append((folder, current_path))
    for subfolder in folder.GetSubFolderList() or []:
        _collect_append_folder_matches(subfolder, requested_folders, folder_matches, current_path)


def _append_target_folder_matches(conn, root, target_folders: list[str]) -> list[tuple[Any, str]]:
    folder_matches: list[tuple[Any, str]] = []
    suffix_folders: list[str] = []

    for folder_path in target_folders:
        if not _append_folder_is_root_prefixed(root, folder_path):
            suffix_folders.append(folder_path)
            continue
        try:
            folder = navigate_folder(conn, folder_path, create=False)
        except FolderNotFound:
            continue
        actual_path = _get_folder_path(root, folder) or folder_path
        folder_matches.append((folder, actual_path))

    if suffix_folders:
        _collect_append_folder_matches(root, suffix_folders, folder_matches)

    unique: list[tuple[Any, str]] = []
    seen: set[tuple[int, str]] = set()
    for folder, folder_path in folder_matches:
        key = (id(folder), str(folder_path))
        if key in seen:
            continue
        seen.add(key)
        unique.append((folder, folder_path))
    return unique


def collect_append_media_matches(conn, entries: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Collect Media Pool items once for append batch planning."""
    root = conn.media_pool.GetRootFolder()
    if not root:
        raise APICallFailed("Cannot get Media Pool root folder.")
    matches: list[dict[str, Any]] = []
    target_folders = _append_entry_target_folders(entries)
    if target_folders:
        for folder, folder_path in _append_target_folder_matches(conn, root, target_folders):
            _collect_clip_object_matches(folder, matches, current_path_override=folder_path, recursive=False)
        return _dedupe_append_matches(matches)
    _collect_clip_object_matches(root, matches)
    return matches


def _source_path_match_keys(value: Any) -> set[str]:
    """Return comparable path variants for local paths surfaced by DaVinci Resolve."""
    text = str(value or "").strip()
    if not text:
        return set()

    expanded = os.path.expanduser(text)
    path_variants = {
        text,
        expanded,
        os.path.normpath(expanded),
        os.path.abspath(expanded),
        os.path.realpath(expanded),
    }

    keys: set[str] = set()
    for variant in path_variants:
        if not variant:
            continue
        normalized_path = os.path.normcase(os.path.normpath(str(variant)))
        keys.add(normalized_path)
        keys.add(unicodedata.normalize("NFC", normalized_path))
        keys.add(unicodedata.normalize("NFD", normalized_path))
    return keys


def _source_path_matches(candidate: Any, requested: Any) -> bool:
    """Compare DaVinci Resolve source paths across macOS path and Unicode variants."""
    candidate_keys = _source_path_match_keys(candidate)
    requested_keys = _source_path_match_keys(requested)
    return bool(candidate_keys and requested_keys and candidate_keys.intersection(requested_keys))


def _append_match_source_path(match: dict[str, Any]) -> str | None:
    value = match.get("source_path")
    if value:
        return str(value)
    props = match.get("props") or {}
    value = _canonical_source_path(props, match.get("clip"))
    if value:
        match["source_path"] = value
        return str(value)
    return None


def _append_match_source_total_frames(match: dict[str, Any], fps: float) -> Optional[int]:
    if "source_total_frames" not in match:
        match["source_total_frames"] = _source_total_frames_from_props(match.get("props") or {}, fps)
    value = match.get("source_total_frames")
    return int(value) if value is not None else None


def _append_index_add(index: dict[str, list[dict[str, Any]]], key: str | None, match: dict[str, Any]) -> None:
    if key is None:
        return
    text = str(key).strip()
    if not text:
        return
    index.setdefault(text, []).append(match)


def _intersect_append_matches(
    left: list[dict[str, Any]] | None,
    right: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if left is None:
        return list(right)
    allowed = {id(match) for match in right}
    return [match for match in left if id(match) in allowed]


def _filter_append_folder_matches(matches: list[dict[str, Any]], folder: Any) -> list[dict[str, Any]]:
    folder_text = str(folder or "").strip().strip("/")
    if not folder_text:
        return matches
    return [
        match
        for match in matches
        if str(match.get("folder", "")).strip("/") == folder_text
        or str(match.get("folder", "")).strip("/").endswith("/" + folder_text)
    ]


class AppendMediaLookupIndex:
    """In-memory lookup indexes for media append batch preflight."""

    def __init__(self, matches: list[dict[str, Any]]) -> None:
        self.matches = list(matches)
        self.by_media_id: dict[str, list[dict[str, Any]]] = {}
        self.by_name: dict[str, list[dict[str, Any]]] = {}
        self.by_path_key: dict[str, list[dict[str, Any]]] = {}
        for match in self.matches:
            _append_index_add(self.by_media_id, match.get("media_id") or _clip_media_id(match["clip"], match.get("props") or {}), match)
            _append_index_add(self.by_name, str(match.get("name") or ""), match)
            for path_key in _source_path_match_keys(_append_match_source_path(match)):
                _append_index_add(self.by_path_key, path_key, match)

    def lookup(self, entry: dict[str, Any]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] | None = None
        media_id = entry.get("media_id")
        path = entry.get("path")
        name = entry.get("name")
        if media_id:
            candidates = _intersect_append_matches(candidates, self.by_media_id.get(str(media_id), []))
        if path:
            path_matches: list[dict[str, Any]] = []
            seen: set[int] = set()
            for path_key in _source_path_match_keys(path):
                for match in self.by_path_key.get(path_key, []):
                    marker = id(match)
                    if marker in seen:
                        continue
                    seen.add(marker)
                    path_matches.append(match)
            candidates = _intersect_append_matches(candidates, path_matches)
        if name:
            candidates = _intersect_append_matches(candidates, self.by_name.get(str(name), []))
        if candidates is None:
            candidates = list(self.matches)
        return _filter_append_folder_matches(candidates, entry.get("folder"))


def build_append_media_lookup_index(matches: list[dict[str, Any]]) -> AppendMediaLookupIndex:
    return AppendMediaLookupIndex(matches)


def resolve_append_media_entry(conn, entry: dict[str, Any], media_matches: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Resolve a batch append entry to one deterministic Media Pool item."""
    media_id = entry.get("media_id")
    name = entry.get("name")
    path = entry.get("path")
    if not any(value for value in (media_id, name, path)):
        raise ValidationError("Media append batch entry requires name, media_id, or path.", details={"entry": entry})

    lookup_source = media_matches if media_matches is not None else collect_append_media_matches(conn, entries=[entry])
    lookup = lookup_source if isinstance(lookup_source, AppendMediaLookupIndex) else build_append_media_lookup_index(lookup_source)
    candidates = lookup.lookup(entry)

    if not candidates:
        raise APICallFailed("Media append batch target clip was not found.", details={"entry": entry})
    if len(candidates) != 1:
        raise ValidationError(
            "Media append batch target is ambiguous.",
            details={"entry": entry, "candidates": [{"name": m.get("name"), "folder": m.get("folder"), "source_path": _append_match_source_path(m)} for m in candidates]},
        )
    match = candidates[0]
    return {
        "clip": match["clip"],
        "name": match.get("name"),
        "folder": match.get("folder"),
        "media_id": match.get("media_id") or _clip_media_id(match["clip"], match.get("props") or {}),
        "source_path": _append_match_source_path(match),
        "source_total_frames": _append_match_source_total_frames(match, conn.fps),
    }


def _collect_clip_matches(folder, name: str, path: str, matches: list[dict[str, Any]]) -> None:
    """Recursively collect exact clip-name matches with folder paths."""
    folder_name = folder.GetName() if hasattr(folder, "GetName") else ""
    current_path = f"{path}/{folder_name}" if path else str(folder_name)

    clips = folder.GetClipList() or []
    for clip in clips:
        clip_name = clip.GetName() if hasattr(clip, "GetName") else ""
        if clip_name == name:
            matches.append({"clip": clip, "name": clip_name, "folder": current_path})

    subfolders = folder.GetSubFolderList() or []
    for sf in subfolders:
        _collect_clip_matches(sf, name, current_path, matches)


def normalize_media_kind(kind: Optional[str]) -> Optional[str]:
    """Normalize and validate media-kind filters."""
    if kind is None:
        return None
    normalized = str(kind).strip().lower()
    if not normalized:
        return None
    if normalized not in _MEDIA_KIND_VALUES:
        raise ValidationError(
            f"Unsupported media kind '{kind}'.",
            details={
                "kind": kind,
                "allowed_kinds": sorted(_MEDIA_KIND_VALUES),
            },
        )
    return normalized


def normalize_append_track_type(track_type: str) -> str:
    """Normalize and validate track types accepted by AppendToTimeline."""
    normalized = str(track_type or "").strip().lower()
    if normalized not in _APPEND_TRACK_TYPES:
        raise ValidationError(
            f"Unsupported append track type '{track_type}'.",
            details={"track_type": track_type, "allowed_track_types": sorted(_APPEND_TRACK_TYPES)},
    )
    return normalized


def normalize_clip_color(color: str) -> str:
    """Normalize and validate DaVinci Resolve Media Pool clip color names."""
    normalized = str(color or "").strip().lower()
    if normalized not in _CLIP_COLOR_VALUES:
        raise ValidationError(
            f"Unsupported clip color '{color}'.",
            details={"color": color, "allowed_colors": sorted(_CLIP_COLOR_VALUES.values())},
        )
    return _CLIP_COLOR_VALUES[normalized]


def normalize_flag_color(color: str) -> str:
    """Normalize and validate DaVinci Resolve Media Pool flag color names."""
    normalized = str(color or "").strip().lower()
    if normalized not in _FLAG_COLOR_VALUES:
        raise ValidationError(
            f"Unsupported flag color '{color}'.",
            details={"color": color, "allowed_colors": sorted(_FLAG_COLOR_VALUES.values())},
        )
    return _FLAG_COLOR_VALUES[normalized]


def validate_append_track_index(track_index: int) -> int:
    """Validate the 1-based timeline track index used by AppendToTimeline."""
    if track_index < 1:
        raise ValidationError(
            "Track index must be 1 or greater.",
            details={"track_index": track_index},
        )
    return track_index


def _timeline_start_frame(conn) -> int:
    """Return the active timeline start frame for record-domain references."""
    start_frame = getattr(conn, "start_frame", None)
    if start_frame is not None:
        try:
            return int(start_frame)
        except Exception:
            pass
    timeline = getattr(conn, "timeline", None)
    if timeline is not None and hasattr(timeline, "GetStartFrame"):
        try:
            return int(timeline.GetStartFrame())
        except Exception:
            pass
    return 0


def _parse_int_maybe(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except Exception:
        return None


def _source_total_frames_from_props(props: dict[str, Any], fps: float) -> Optional[int]:
    """Best-effort source clip duration in frames from a clip property dict."""
    if not isinstance(props, dict):
        return None

    for key in ("Frames", "DurationFrames", "SourceFrames"):
        parsed = _parse_int_maybe(props.get(key))
        if parsed is not None and parsed >= 0:
            return parsed

    duration = props.get("Duration")
    if duration is None:
        return None
    try:
        duration_text = str(duration).strip()
        if ":" in duration_text or duration_text.endswith(("f", "s")):
            return max(0, seconds_to_frames(parse_time_input(duration_text, fps), fps))
        parsed = _parse_int_maybe(duration_text)
        if parsed is not None and parsed >= 0:
            return parsed
    except Exception:
        return None
    return None


def _source_total_frames(media_pool_item, fps: float) -> Optional[int]:
    """Best-effort source clip duration in frames from Media Pool properties."""
    if not hasattr(media_pool_item, "GetClipProperty"):
        return None
    try:
        props = media_pool_item.GetClipProperty() or {}
    except Exception:
        return None
    return _source_total_frames_from_props(props, fps)


def _validate_append_source_bounds(
    *,
    clip_name: str,
    start_frame: Optional[int],
    end_frame: Optional[int],
    source_total_frames: Optional[int],
) -> None:
    effective_start = int(start_frame or 0)
    if end_frame is not None and int(end_frame) <= effective_start:
        raise InvalidTimeReference(
            "source end must be greater than source start.",
            details={
                "clip": clip_name,
                "startFrame": effective_start,
                "endFrame": int(end_frame),
            },
        )
    if source_total_frames is None:
        return
    if start_frame is not None and int(start_frame) > source_total_frames:
        raise InvalidTimeReference(
            "source start is out of source clip range.",
            details={
                "clip": clip_name,
                "startFrame": int(start_frame),
                "source_total_frames": source_total_frames,
            },
        )
    if end_frame is not None and int(end_frame) > source_total_frames:
        raise InvalidTimeReference(
            "source end is out of source clip range.",
            details={
                "clip": clip_name,
                "endFrame": int(end_frame),
                "source_total_frames": source_total_frames,
            },
        )


def _clip_properties(clip) -> Dict[str, Any]:
    """Safely read clip properties as a dictionary."""
    try:
        props = clip.GetClipProperty()
    except Exception:
        props = None
    return props if isinstance(props, dict) else {}


def _canonical_source_path(props: Dict[str, Any], clip=None) -> Optional[str]:
    """Return a normalized source path for a clip when DaVinci Resolve exposes one."""
    for key in _CANONICAL_SOURCE_KEYS:
        value = props.get(key)
        if not value and clip is not None:
            try:
                value = clip.GetClipProperty(key)
            except Exception:
                value = None
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _infer_clip_kind(name: str, clip_type: str) -> str:
    """Infer a stable clip kind for navigation and filtering."""
    lowered_type = str(clip_type or "").lower()
    lowered_name = str(name or "").lower()
    if "subtitle" in lowered_type or lowered_name.startswith("resolve_sub_"):
        return "subtitle"
    if "timeline" in lowered_type:
        return "timeline"
    return "media"


def _is_generated_asset(name: str, kind: str, clip_type: str) -> bool:
    """Best-effort detection of generated/internal Media Pool assets."""
    lowered_name = str(name or "").lower()
    lowered_type = str(clip_type or "").lower()
    if kind == "subtitle" and lowered_name.startswith("resolve_sub_"):
        return True
    return lowered_name.startswith("resolve_") or "generated" in lowered_type


def _serialize_clip_row(clip, folder_path: str) -> Dict[str, Any]:
    """Serialize a clip with canonical navigation fields."""
    name = clip.GetName() if hasattr(clip, "GetName") else "?"
    props = _clip_properties(clip)
    clip_type = props.get("Type", "")
    duration = props.get("Duration", "")
    resolution = props.get("Resolution", "")
    kind = _infer_clip_kind(name, clip_type)
    source_path = _canonical_source_path(props, clip)
    return {
        "name": name,
        "type": clip_type,
        "duration": duration,
        "resolution": resolution,
        "folder": folder_path,
        "source_path": source_path,
        "kind": kind,
        "is_generated": _is_generated_asset(name, kind, clip_type),
    }


def _matches_clip_filters(row: Dict[str, Any], kind: Optional[str], include_generated: bool) -> bool:
    """Check whether a serialized clip row passes navigation filters."""
    if kind and row.get("kind") != kind:
        return False
    if not include_generated and row.get("is_generated"):
        return False
    return True


def _collect_clip_rows(folder, path: str, recursive: bool, rows: list[Dict[str, Any]], *, kind: Optional[str], include_generated: bool) -> None:
    """Collect clip rows from a folder tree."""
    folder_name = folder.GetName() if hasattr(folder, "GetName") else ""
    current_path = path or str(folder_name)

    for clip in folder.GetClipList() or []:
        row = _serialize_clip_row(clip, current_path)
        if _matches_clip_filters(row, kind, include_generated):
            rows.append(row)

    if not recursive:
        return

    for subfolder in folder.GetSubFolderList() or []:
        subfolder_name = subfolder.GetName() if hasattr(subfolder, "GetName") else ""
        next_path = f"{current_path}/{subfolder_name}" if current_path else str(subfolder_name)
        _collect_clip_rows(subfolder, next_path, True, rows, kind=kind, include_generated=include_generated)


def _count_source_path_matches(folder, source_path: str) -> int:
    """Count Media Pool items that expose the same canonical source path."""
    count = 0
    for clip in folder.GetClipList() or []:
        if _canonical_source_path(_clip_properties(clip), clip) == source_path:
            count += 1
    for subfolder in folder.GetSubFolderList() or []:
        count += _count_source_path_matches(subfolder, source_path)
    return count


def _get_folder_path(folder, target_folder, path: str = "") -> str:
    """Resolve a folder object's path from the Media Pool root."""
    folder_name = folder.GetName() if hasattr(folder, "GetName") else ""
    current_path = f"{path}/{folder_name}" if path else str(folder_name)
    if folder is target_folder:
        return current_path
    # DaVinci Resolve can hand back distinct proxy objects for the root folder through
    # GetRootFolder() and GetCurrentFolder(). Treat matching top-level names as
    # the same root so root-context inspectors report "Master" instead of "".
    if not path and folder_name and hasattr(target_folder, "GetName") and target_folder.GetName() == folder_name:
        return current_path

    for subfolder in folder.GetSubFolderList() or []:
        found = _get_folder_path(subfolder, target_folder, current_path)
        if found:
            return found
    return ""


def list_clips(
    conn,
    recursive: bool = False,
    *,
    kind: Optional[str] = None,
    include_generated: bool = True,
) -> List[Dict[str, Any]]:
    """
    List clips in the current Media Pool folder.
    
    Args:
        conn: ResolveConnection instance
        recursive: Include subfolders
    
    Returns:
        List of clip info dicts
    
    Raises:
        APICallFailed: If cannot get current folder
    """
    folder = conn.media_pool.GetCurrentFolder()
    if not folder:
        raise APICallFailed("Cannot get current Media Pool folder.")

    normalized_kind = normalize_media_kind(kind)
    current_path = _get_folder_path(conn.media_pool.GetRootFolder(), folder)
    rows: list[Dict[str, Any]] = []
    _collect_clip_rows(
        folder,
        current_path,
        recursive,
        rows,
        kind=normalized_kind,
        include_generated=include_generated,
    )
    return rows


def get_clip_info(conn, name: str) -> Dict[str, Any]:
    """
    Get detailed clip information.
    
    Args:
        conn: ResolveConnection instance
        name: Clip name
    
    Returns:
        Dictionary of clip properties
    
    Raises:
        APICallFailed: If clip not found
    """
    match = find_clip_match(conn, name)
    if not match:
        raise APICallFailed(f"Clip '{name}' not found.")

    clip = match["clip"]
    props = _clip_properties(clip)
    row = _serialize_clip_row(clip, match["folder"])
    if props:
        enriched = dict(props)
        enriched.update({
            "name": row["name"],
            "folder": row["folder"],
            "source_path": row["source_path"],
            "kind": row["kind"],
            "is_generated": row["is_generated"],
        })
        return enriched
    return {
        "name": row["name"],
        "folder": row["folder"],
        "source_path": row["source_path"],
        "kind": row["kind"],
        "is_generated": row["is_generated"],
        "properties": str(clip.GetClipProperty()),
    }


def transcribe_audio(
    conn,
    *,
    clip_name: Optional[str] = None,
    folder_path: Optional[str] = None,
    language: Optional[str] = None,
) -> Dict[str, Any]:
    """Transcribe audio for an explicitly targeted clip or folder."""
    if clip_name and folder_path:
        raise ValidationError("Choose either clip transcription or folder transcription, not both.")
    if not clip_name and not folder_path:
        raise MissingArgumentError(
            "Choose a transcription target with --clip or --folder.",
            details={"required_one_of": ["--clip", "--folder"]},
        )

    if clip_name:
        clip = find_clip(conn, clip_name)
        if not clip:
            raise APICallFailed(f"Clip '{clip_name}' not found.")
        transcriber = require_api_method(
            clip,
            "TranscribeAudio",
            capability_id="media.transcription",
            runtime_object="media_pool_item",
        )
        if language:
            try:
                result = transcriber(language)
            except TypeError as exc:
                raise APICallFailed(
                    "DaVinci Resolve does not accept the requested transcription language.",
                    details={"clip": clip_name, "language": language},
                ) from exc
        else:
            result = transcriber()
        if result is False:
            raise APICallFailed("Clip transcription failed.", details={"clip": clip_name, "language": language})
        return {"target": "clip", "clip": clip_name, "language": language or "default"}

    if folder_path:
        folder = navigate_folder(conn, folder_path, create=False)
    else:
        folder = conn.media_pool.GetCurrentFolder()
    if not folder:
        raise APICallFailed("No folder selected for transcription.")

    transcriber = require_api_method(
        folder,
        "TranscribeAudio",
        capability_id="media.transcription",
        runtime_object="folder",
    )
    if language:
        try:
            result = transcriber(language)
        except TypeError as exc:
            raise APICallFailed(
                "DaVinci Resolve does not accept the requested transcription language.",
                details={"folder": folder_path or folder.GetName(), "language": language},
            ) from exc
    else:
        result = transcriber()
    if result is False:
        raise APICallFailed(
            "Folder transcription failed.",
            details={"folder": folder_path or folder.GetName(), "language": language},
        )
    return {"target": "folder", "folder": folder_path or folder.GetName(), "language": language or "default"}


_TRANSCRIPTION_MAX_SEGMENTS = 10_000
_TRANSCRIPTION_MAX_WORDS = 100_000
_TRANSCRIPTION_MAX_TEXT_BYTES = 16_384


def _transcription_text(
    value: Any,
    *,
    field: str,
    nullable: bool = False,
    max_bytes: int = _TRANSCRIPTION_MAX_TEXT_BYTES,
) -> Optional[str]:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise APICallFailed(
            "DaVinci Resolve returned malformed transcription data.",
            details={"field": field},
        )
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise APICallFailed(
            "DaVinci Resolve returned malformed transcription text.",
            details={"field": field},
        ) from exc
    if size > max_bytes:
        raise APICallFailed(
            "DaVinci Resolve returned transcription text outside the bounded contract.",
            details={"field": field, "max_bytes": max_bytes},
        )
    return value


def normalize_transcription(raw: Any) -> Dict[str, Any]:
    """Normalize the documented 21.1 transcription shape without guessing extensions."""
    if raw is None or raw is False or raw == {}:
        return {"available": False, "language": None, "segments": []}
    if not isinstance(raw, dict):
        raise APICallFailed("DaVinci Resolve returned malformed transcription data.")

    language = _transcription_text(raw.get("language"), field="language", nullable=True)
    raw_segments = raw.get("segments", [])
    if not isinstance(raw_segments, list) or len(raw_segments) > _TRANSCRIPTION_MAX_SEGMENTS:
        raise APICallFailed(
            "DaVinci Resolve returned transcription segments outside the bounded contract.",
            details={"max_segments": _TRANSCRIPTION_MAX_SEGMENTS},
        )

    segments: list[Dict[str, Any]] = []
    total_words = 0
    for segment_index, raw_segment in enumerate(raw_segments):
        if not isinstance(raw_segment, dict):
            raise APICallFailed(
                "DaVinci Resolve returned a malformed transcription segment.",
                details={"segment_index": segment_index},
            )
        raw_words = raw_segment.get("words", [])
        if not isinstance(raw_words, list):
            raise APICallFailed(
                "DaVinci Resolve returned malformed transcription words.",
                details={"segment_index": segment_index},
            )
        total_words += len(raw_words)
        if total_words > _TRANSCRIPTION_MAX_WORDS:
            raise APICallFailed(
                "DaVinci Resolve returned transcription words outside the bounded contract.",
                details={"max_words": _TRANSCRIPTION_MAX_WORDS},
            )
        words: list[Dict[str, Any]] = []
        for word_index, raw_word in enumerate(raw_words):
            if not isinstance(raw_word, dict):
                raise APICallFailed(
                    "DaVinci Resolve returned a malformed transcription word.",
                    details={"segment_index": segment_index, "word_index": word_index},
                )
            words.append({
                "start": _transcription_text(raw_word.get("start"), field="word.start", nullable=True, max_bytes=64),
                "end": _transcription_text(raw_word.get("end"), field="word.end", nullable=True, max_bytes=64),
                "text": _transcription_text(raw_word.get("text", ""), field="word.text"),
            })
        segments.append({
            "start": _transcription_text(raw_segment.get("start"), field="segment.start", nullable=True, max_bytes=64),
            "end": _transcription_text(raw_segment.get("end"), field="segment.end", nullable=True, max_bytes=64),
            "text": _transcription_text(raw_segment.get("text", ""), field="segment.text"),
            "speaker": _transcription_text(raw_segment.get("speaker"), field="segment.speaker", nullable=True),
            "words": words,
        })
    return {"available": True, "language": language, "segments": segments}


def get_transcription(
    conn,
    *,
    clip_name: str,
    use_nested_clip_transcription: bool = False,
) -> Dict[str, Any]:
    """Read persisted DaVinci Resolve transcription for one unambiguous clip name."""
    match = find_clip_match(conn, clip_name)
    if not match:
        raise APICallFailed(f"Clip '{clip_name}' not found.")
    getter = require_api_method(
        match["clip"],
        "GetTranscription",
        capability_id="media.transcription_readback",
        runtime_object="media_pool_item",
    )
    transcription = normalize_transcription(getter(bool(use_nested_clip_transcription)))
    return {
        "clip": clip_name,
        "folder": match["folder"],
        "use_nested_clip_transcription": bool(use_nested_clip_transcription),
        **transcription,
    }


def clear_transcription(
    conn,
    *,
    clip_name: Optional[str] = None,
    folder_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Clear transcription for a clip or folder (current folder when target omitted)."""
    if clip_name and folder_path:
        raise ValidationError("Choose either clip or folder clear operation, not both.")

    if clip_name:
        clip = find_clip(conn, clip_name)
        if not clip:
            raise APICallFailed(f"Clip '{clip_name}' not found.")
        clearer = require_api_method(
            clip,
            "ClearTranscription",
            capability_id="media.transcription",
            runtime_object="media_pool_item",
        )
        result = clearer()
        if result is False:
            raise APICallFailed("Failed to clear clip transcription.", details={"clip": clip_name})
        return {"target": "clip", "clip": clip_name, "cleared": True}

    if folder_path:
        folder = navigate_folder(conn, folder_path, create=False)
    else:
        folder = conn.media_pool.GetCurrentFolder()
    if not folder:
        raise APICallFailed("No folder selected for transcription clear.")

    clearer = require_api_method(
        folder,
        "ClearTranscription",
        capability_id="media.transcription",
        runtime_object="folder",
    )
    result = clearer()
    if result is False:
        raise APICallFailed("Failed to clear folder transcription.", details={"folder": folder_path or folder.GetName()})
    return {"target": "folder", "folder": folder_path or folder.GetName(), "cleared": True}
