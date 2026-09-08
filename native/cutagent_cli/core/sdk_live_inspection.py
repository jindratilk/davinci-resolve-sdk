"""Private, bounded live-state inspection used by the CutAgent SDK bridge."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
import re
import time
import unicodedata
from typing import Any, Callable, Dict, Iterator

from ..errors import APICallFailed, SdkMutationStaleRevision, ValidationError
from ..state_contracts import looks_like_project_manager_placeholder
from . import project_library_ops


SDK_LIVE_INSPECTION_OPERATIONS = {
    "color.current",
    "project.current",
    "project.context",
    "project.folder_context",
    "project.library_context",
    "timeline.current",
    "timeline.list",
    "timeline.retime",
    "timeline.snapshot",
    "fusion.compositions",
    "mediaPool.page",
    "multicam.inspect",
    "managed.protected",
    "storage.mattes",
}
SDK_LIVE_INSPECTION_MAX_DEADLINE_WINDOW_MS = 180_000
SDK_MEDIA_POOL_MAX_INVENTORY = 1_000_000
SDK_MARKER_GUARD_ENV = "CUTAGENT_SDK_MARKER_GUARD"
SDK_TIMELINE_GUARD_ENV = "CUTAGENT_SDK_TIMELINE_GUARD"
SDK_COLOR_GUARD_ENV = "CUTAGENT_SDK_COLOR_GUARD"
SDK_COLOR_NODE_STACK_LAYER_INDEX_ENV = "CUTAGENT_SDK_COLOR_NODE_STACK_LAYER_INDEX"
SDK_MUTATION_GUARD_ENV = "CUTAGENT_SDK_MUTATION_GUARD"
SDK_PROJECT_GUARD_ENV = "CUTAGENT_SDK_PROJECT_GUARD"
SDK_MEDIA_POOL_GUARD_ENV = "CUTAGENT_SDK_MEDIA_POOL_GUARD"
SDK_MEDIA_POOL_PRIVATE_PATHS_ENV = "CUTAGENT_SDK_MEDIA_POOL_PRIVATE_PATHS"
SDK_FUSION_INSPECTION_TARGET_ENV = "CUTAGENT_SDK_FUSION_INSPECTION_TARGET"
SDK_PUBLIC_SLASH_EFFECT_NAMES = frozenset({"ARRI CDL/LUT"})


class SdkLiveInspectionTimeout(APICallFailed):
    """Private machine-contract failure for the bounded SDK inspection path."""

    code = "SDK_LIVE_INSPECTION_TIMEOUT"
    recoverability = "retryable"


def _inspect_storage_mattes(conn: Any, native_ids: list[str], deadline_at_ms: int) -> dict[str, Any]:
    media_pool = getattr(conn, "media_pool", None)
    if media_pool is None:
        raise APICallFailed("DaVinci Resolve Media Pool is unavailable for Storage verification.")
    clip_getter = getattr(media_pool, "GetClipMatteList", None)
    timeline_getter = getattr(media_pool, "GetTimelineMatteList", None)
    current_folder_getter = getattr(media_pool, "GetCurrentFolder", None)
    root_getter = getattr(media_pool, "GetRootFolder", None)
    if not all(callable(value) for value in (clip_getter, timeline_getter, current_folder_getter, root_getter)):
        raise APICallFailed("DaVinci Resolve matte readback is unavailable.")
    wanted = set(native_ids)
    clip_mattes: dict[str, list[str]] = {}

    def visit(root: Any) -> None:
        stack = [root]
        visited: set[int] = set()
        rows = 0
        while stack:
            folder = stack.pop()
            if id(folder) in visited:
                raise APICallFailed("DaVinci Resolve returned a cyclic Media Pool folder graph.")
            visited.add(id(folder))
            rows += 1
            if rows > SDK_MEDIA_POOL_MAX_INVENTORY:
                raise ValidationError("Media Pool inventory exceeds the bounded SDK contract.")
            validate_deadline(deadline_at_ms)
            for clip in _required_list_call(folder, "GetClipList", deadline_at_ms):
                rows += 1
                if rows > SDK_MEDIA_POOL_MAX_INVENTORY:
                    raise ValidationError("Media Pool inventory exceeds the bounded SDK contract.")
                native_id = media_pool_native_id(clip)
                if native_id in wanted:
                    values = clip_getter(clip) or []
                    clip_mattes[native_id] = values if isinstance(values, list) else [values]
            children = _required_list_call(folder, "GetSubFolderList", deadline_at_ms)
            stack.extend(reversed(children))

    root = root_getter()
    if root is None:
        raise APICallFailed("DaVinci Resolve Media Pool root is unavailable for Storage verification.")
    visit(root)
    current_folder = current_folder_getter()
    if current_folder is None:
        raise APICallFailed("DaVinci Resolve current Media Pool folder is unavailable.")
    current_folder_native_id = media_pool_native_id(current_folder, folder=True)
    if not current_folder_native_id:
        raise APICallFailed("DaVinci Resolve current Media Pool folder identity is unavailable.")
    timeline_values = timeline_getter(current_folder) or []
    return {
        "clip_mattes": clip_mattes,
        "current_folder_native_id": current_folder_native_id,
        "timeline_mattes": timeline_values if isinstance(timeline_values, list) else [timeline_values],
    }


def documented_unique_id(native_object: Any) -> str | None:
    """Read an exact documented ``GetUniqueId`` string or reject it as unknown.

    DaVinci Resolve methods commonly return ``False`` when an API call fails.
    Durable identity must never stringify that failure (or any other non-string
    sentinel) into reusable identity truth.
    """

    getter = getattr(native_object, "GetUniqueId", None)
    if not callable(getter):
        return None
    try:
        value = getter()
    except Exception:
        return None
    if not isinstance(value, str) or not value or len(value) > 4096 or value != value.strip():
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        return None
    return value


def validate_deadline(deadline_at_ms: int | None) -> None:
    if deadline_at_ms is None:
        return
    now_ms = int(time.time() * 1000)
    if deadline_at_ms > now_ms + SDK_LIVE_INSPECTION_MAX_DEADLINE_WINDOW_MS:
        raise ValidationError(
            "SDK live inspection deadline exceeds the maximum control timeout window.",
            details={"maximum_deadline_window_ms": SDK_LIVE_INSPECTION_MAX_DEADLINE_WINDOW_MS},
            recoverability="not_applicable",
        )
    if now_ms >= deadline_at_ms:
        raise SdkLiveInspectionTimeout(
            "SDK live inspection exceeded its absolute deadline.",
            details={"deadline_at_ms": deadline_at_ms},
        )


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def fusion_graph_digest(graph: Any) -> str:
    """Digest native Fusion evidence in the Python runtime that produced it."""

    return f"sha256:{hashlib.sha256(_canonical_bytes(graph)).hexdigest()}"


def marker_mutation_guard(identity: Dict[str, Any], summary: Dict[str, Any] | None) -> str:
    """Bind timeline content and identity, excluding viewer navigation state."""

    # Render mode changes can move the playhead without editing the timeline.
    # Keep navigation in inspection responses, but not in a content precondition.
    structural_summary = summary
    if isinstance(summary, dict):
        structural_summary = {key: value for key, value in summary.items() if key != "current_items"}
        if isinstance(summary.get("window"), dict):
            structural_summary["window"] = {
                key: value for key, value in summary["window"].items() if key != "playhead"
            }
        if isinstance(summary.get("tracks"), list):
            structural_summary["tracks"] = [
                {key: value for key, value in track.items() if key != "items_at_playhead"}
                if isinstance(track, dict) else track
                for track in summary["tracks"]
            ]
    payload = {"identity": identity, "summary": structural_summary}
    return f"sha256:{hashlib.sha256(_canonical_bytes(payload)).hexdigest()}"


def color_mutation_guard(identity: Dict[str, Any], summary: Dict[str, Any] | None, color: Dict[str, Any] | None) -> str:
    """Digest the exact native target, placement, graph, LUT, and effect state used by SDK Color writes."""

    payload = {"identity": identity, "summary": summary, "color": color}
    return f"sha256:{hashlib.sha256(_canonical_bytes(payload)).hexdigest()}"


def project_mutation_guard(identity: Dict[str, Any]) -> str:
    """Digest the exact active project-library/project context used by SDK project writes."""

    return f"sha256:{hashlib.sha256(_canonical_bytes(identity)).hexdigest()}"


def media_pool_mutation_guard(identity: Dict[str, Any], pool_digest: str) -> str:
    """Digest the exact project context and complete Media Pool inventory used by SDK writes."""

    return f"sha256:{hashlib.sha256(_canonical_bytes({'identity': identity, 'pool_digest': pool_digest})).hexdigest()}"


_MEDIA_METADATA_KEYS = {
    "Description": "description",
    "Comments": "comments",
    "Keywords": "keywords",
    "Shot": "shot",
    "Scene": "scene",
    "Take": "take",
    "Angle": "angle",
    "Camera #": "camera",
    "Camera": "camera",
    "Reel Name": "reel",
    "Date Recorded": "dateRecorded",
    "Good Take": "goodTake",
    "Clip Color": "clipColor",
}


def _bounded_native_text(
    value: Any,
    *,
    field: str,
    maximum_code_units: int,
    allow_empty: bool = True,
    strip: bool = False,
) -> str | None:
    if value in (None, ""):
        if allow_empty:
            return None
        raise APICallFailed(f"DaVinci Resolve returned an empty {field} during SDK Media Pool inspection.")
    try:
        text = value if isinstance(value, str) else str(value)
    except Exception as exc:
        raise APICallFailed(
            f"DaVinci Resolve returned invalid text for {field} during SDK Media Pool inspection."
        ) from exc
    if strip:
        text = text.strip()
        if not text and allow_empty:
            return None
    if len(text) > maximum_code_units:
        raise APICallFailed(f"DaVinci Resolve returned an oversized {field} during SDK Media Pool inspection.")
    try:
        code_units = len(text.encode("utf-16-le")) // 2
    except UnicodeEncodeError as exc:
        raise APICallFailed(
            f"DaVinci Resolve returned malformed text for {field} during SDK Media Pool inspection."
        ) from exc
    if code_units > maximum_code_units:
        raise APICallFailed(f"DaVinci Resolve returned an oversized {field} during SDK Media Pool inspection.")
    if not allow_empty and not text.strip():
        raise APICallFailed(f"DaVinci Resolve returned an empty {field} during SDK Media Pool inspection.")
    return text


def _selected_media_metadata(metadata: dict[str, Any]) -> list[dict[str, str]]:
    """Return one bounded value per curated public key.

    DaVinci Resolve versions can expose both ``Camera #`` and ``Camera``. The
    public contract has one ``camera`` key, so the first non-empty native value
    wins deterministically instead of leaking duplicate semantic keys.
    """

    selected: list[dict[str, str]] = []
    seen: set[str] = set()
    for native_key, public_key in _MEDIA_METADATA_KEYS.items():
        value = metadata.get(native_key)
        if public_key in seen or value in (None, ""):
            continue
        bounded = _bounded_native_text(
            value,
            field=f"Media Pool metadata value ({public_key})",
            maximum_code_units=65_536,
        )
        if bounded is None:
            continue
        selected.append({"key": public_key, "value": bounded})
        seen.add(public_key)
    return selected


def _required_mapping_call(native_object: Any, method: str) -> dict[str, Any]:
    getter = getattr(native_object, method, None)
    if not callable(getter):
        raise APICallFailed(f"DaVinci Resolve does not expose {method} for SDK Media Pool inspection.")
    try:
        value = getter()
    except Exception as exc:
        raise APICallFailed(f"DaVinci Resolve {method} failed during SDK Media Pool inspection.") from exc
    if not isinstance(value, dict):
        raise APICallFailed(f"DaVinci Resolve {method} returned an invalid SDK Media Pool result.")
    return value


def _required_list_call(
    native_object: Any,
    method: str,
    deadline_at_ms: int | None = None,
) -> list[Any]:
    getter = getattr(native_object, method, None)
    if not callable(getter):
        raise APICallFailed(f"DaVinci Resolve does not expose {method} for SDK Media Pool inspection.")
    try:
        value = getter()
    except Exception as exc:
        raise APICallFailed(f"DaVinci Resolve {method} failed during SDK Media Pool inspection.") from exc
    if isinstance(value, list):
        if len(value) > SDK_MEDIA_POOL_MAX_INVENTORY:
            raise APICallFailed(f"DaVinci Resolve {method} exceeded the bounded SDK Media Pool inventory.")
        for _ in value:
            validate_deadline(deadline_at_ms)
        return value
    if isinstance(value, dict):
        iterable = value.values()
    elif isinstance(value, tuple):
        iterable = value
    else:
        raise APICallFailed(f"DaVinci Resolve {method} returned an invalid SDK Media Pool result.")
    result = []
    for item in iterable:
        validate_deadline(deadline_at_ms)
        if len(result) >= SDK_MEDIA_POOL_MAX_INVENTORY:
            raise APICallFailed(f"DaVinci Resolve {method} exceeded the bounded SDK Media Pool inventory.")
        result.append(item)
    return result


def _required_name(native_object: Any, *, field: str) -> str:
    getter = getattr(native_object, "GetName", None)
    if not callable(getter):
        raise APICallFailed("DaVinci Resolve does not expose GetName for SDK Media Pool inspection.")
    try:
        value = getter()
    except Exception as exc:
        raise APICallFailed("DaVinci Resolve GetName failed during SDK Media Pool inspection.") from exc
    bounded = _bounded_native_text(value, field=field, maximum_code_units=4096, allow_empty=False)
    assert bounded is not None
    return bounded


def media_pool_native_id(native_object: Any, *, folder: bool = False) -> str | None:
    """Read the canonical native identity used by authoritative Media Pool inspection."""
    methods = ("GetUniqueId",) if folder else ("GetMediaId", "GetUniqueId")
    for method in methods:
        getter = getattr(native_object, method, None)
        if not callable(getter):
            continue
        try:
            value = getter()
        except Exception:
            continue
        if (
            isinstance(value, str)
            and value
            and len(value) <= 4096
            and value == value.strip()
            and not any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            return value
    return None


def _media_asset_kind(properties: dict[str, Any]) -> str:
    raw = _bounded_native_text(
        properties.get("Type"),
        field="Media Pool asset type",
        maximum_code_units=256,
    )
    raw = (raw or "").casefold()
    if "multicam" in raw:
        return "multicam"
    if "compound" in raw:
        return "compound"
    if "timeline" in raw:
        return "timeline"
    if "fusion" in raw:
        return "fusion_composition"
    if "generator" in raw:
        return "generator"
    if any(token in raw for token in ("still", "image", "jpeg", "png", "tiff")):
        return "still"
    if any(token in raw for token in ("video", "movie", "clip")):
        return "video"
    if "audio" in raw:
        return "audio"
    return "unknown"


def _selected_media_identities(media_pool: Any, deadline_at_ms: int | None) -> tuple[set[int], set[str]]:
    getter = getattr(media_pool, "GetSelectedClips", None)
    if not callable(getter):
        raise APICallFailed("DaVinci Resolve does not expose GetSelectedClips for SDK Media Pool inspection.")
    try:
        selected_value = getter()
    except Exception as exc:
        raise APICallFailed("DaVinci Resolve GetSelectedClips failed during SDK Media Pool inspection.") from exc
    # DaVinci Resolve returns None when the Media Pool selection is empty.
    # That is an authoritative empty selection, not a failed collection read.
    if selected_value is None:
        selected: list[Any] = []
    elif isinstance(selected_value, list):
        selected = selected_value
    elif isinstance(selected_value, dict):
        selected = list(selected_value.values())
    elif isinstance(selected_value, tuple):
        selected = list(selected_value)
    else:
        raise APICallFailed("DaVinci Resolve GetSelectedClips returned an invalid SDK Media Pool result.")
    if len(selected) > SDK_MEDIA_POOL_MAX_INVENTORY:
        raise APICallFailed("DaVinci Resolve GetSelectedClips exceeded the bounded SDK Media Pool inventory.")
    object_ids: set[int] = set()
    native_ids: set[str] = set()
    for item in selected:
        validate_deadline(deadline_at_ms)
        object_ids.add(id(item))
        native_id = media_pool_native_id(item)
        if native_id:
            native_ids.add(native_id)
    return object_ids, native_ids


def _media_pool_rows(conn: Any, deadline_at_ms: int | None) -> Iterator[dict[str, Any]]:
    validate_deadline(deadline_at_ms)
    media_pool = getattr(conn, "media_pool", None)
    root_getter = getattr(media_pool, "GetRootFolder", None)
    if not callable(root_getter):
        raise APICallFailed("DaVinci Resolve does not expose GetRootFolder for SDK Media Pool inspection.")
    try:
        root = root_getter()
    except Exception as exc:
        raise APICallFailed("DaVinci Resolve GetRootFolder failed during SDK Media Pool inspection.") from exc
    validate_deadline(deadline_at_ms)
    if root is None:
        raise APICallFailed("Cannot inspect the current Media Pool root folder.")
    selected_objects, selected_native_ids = _selected_media_identities(media_pool, deadline_at_ms)
    row_count = 0

    def sort_key(pair: tuple[int, Any], field: str) -> tuple[str, int]:
        validate_deadline(deadline_at_ms)
        return (_required_name(pair[1], field=field).casefold(), pair[0])

    def visit(
        folder: Any,
        coordinate: tuple[int, ...],
        parent: tuple[int, ...] | None,
    ) -> Iterator[dict[str, Any]]:
        nonlocal row_count
        validate_deadline(deadline_at_ms)
        if len(coordinate) > 257:
            raise ValidationError("Media Pool folder depth exceeds the bounded SDK contract.")
        if row_count >= SDK_MEDIA_POOL_MAX_INVENTORY:
            raise ValidationError("Media Pool inventory exceeds the bounded SDK contract.")
        folder_name = _required_name(folder, field="Media Pool folder name")
        row_count += 1
        yield {
            "entry_kind": "folder",
            "coordinate": list(coordinate),
            "parent_coordinate": list(parent) if parent is not None else None,
            "native_id": media_pool_native_id(folder, folder=True),
            "name": folder_name,
            "depth": len(coordinate) - 1,
        }
        clips = _required_list_call(folder, "GetClipList", deadline_at_ms)
        decorated_clips = sorted(
            enumerate(clips),
            key=lambda pair: sort_key(pair, "Media Pool asset name"),
        )
        validate_deadline(deadline_at_ms)
        for clip_ordinal, (_, clip) in enumerate(decorated_clips):
            validate_deadline(deadline_at_ms)
            if row_count >= SDK_MEDIA_POOL_MAX_INVENTORY:
                raise ValidationError("Media Pool inventory exceeds the bounded SDK contract.")
            properties = _required_mapping_call(clip, "GetClipProperty")
            metadata = _required_mapping_call(clip, "GetMetadata")
            native_id = media_pool_native_id(clip)
            unique_id = documented_unique_id(clip)
            source_path = _bounded_native_text(
                properties.get("File Path") or properties.get("FilePath"),
                field="Media Pool source path",
                maximum_code_units=32_768,
                strip=True,
            )
            source_file_name = None
            if source_path:
                source_file_name = _bounded_native_text(
                    source_path.replace("\\", "/").rsplit("/", 1)[-1],
                    field="Media Pool source file name",
                    maximum_code_units=4096,
                )
            selected = id(clip) in selected_objects or bool(native_id and native_id in selected_native_ids)
            row_count += 1
            yield {
                "entry_kind": "asset",
                "coordinate": [*coordinate, clip_ordinal],
                "folder_coordinate": list(coordinate),
                "native_id": native_id,
                "unique_id": unique_id,
                "name": _required_name(clip, field="Media Pool asset name"),
                "kind": _media_asset_kind(properties),
                "selected": selected,
                # Private desktop inspection evidence. The bridge strips this
                # before the public SDK response; semantic multicam creation
                # uses it to select the exact already-imported source without
                # exposing a local path in public artifacts.
                "source_path": source_path,
                "source_file_name": source_file_name,
                "duration": _bounded_native_text(properties.get("Duration"), field="Media Pool duration", maximum_code_units=4096, strip=True),
                "resolution": _bounded_native_text(properties.get("Resolution"), field="Media Pool resolution", maximum_code_units=4096, strip=True),
                "frame_rate": _bounded_native_text(properties.get("FPS") or properties.get("Frame Rate"), field="Media Pool frame rate", maximum_code_units=256, strip=True),
                "start_timecode": _bounded_native_text(properties.get("Start TC") or properties.get("Start Timecode"), field="Media Pool start timecode", maximum_code_units=256, strip=True),
                "metadata": _selected_media_metadata(metadata),
            }
        children = _required_list_call(folder, "GetSubFolderList", deadline_at_ms)
        decorated_children = sorted(
            enumerate(children),
            key=lambda pair: sort_key(pair, "Media Pool folder name"),
        )
        validate_deadline(deadline_at_ms)
        for child_ordinal, (_, child) in enumerate(decorated_children):
            yield from visit(child, (*coordinate, child_ordinal), coordinate)

    yield from visit(root, (0,), None)


def _matches_media_search(row: dict[str, Any], search: dict[str, Any] | None) -> bool:
    if not search or row["entry_kind"] == "folder":
        return not search
    query = str(search["query"])
    exact = search["match"] == "exact"
    candidates: list[str] = []
    for field in search["fields"]:
        if field == "name":
            candidates.append(str(row["name"]))
        elif field == "sourceFileName":
            candidates.append(str(row.get("source_file_name") or ""))
        elif field == "metadata":
            candidates.extend(str(item["value"]) for item in row["metadata"])
    folded_query = query.lower()
    return any(
        candidate.lower() == folded_query if exact else folded_query in candidate.lower()
        for candidate in candidates
    )


def inspect_media_pool_page(
    conn: Any,
    *,
    deadline_at_ms: int | None,
    offset: int,
    page_size: int,
    search: dict[str, Any] | None,
    include_private_paths: bool = False,
) -> dict[str, Any]:
    if offset < 0 or offset > 1_000_000:
        raise ValidationError("Media Pool offset is outside the bounded range.", details={"offset": offset})
    if page_size < 1 or page_size > 32:
        raise ValidationError("Media Pool page size must be from 1 through 32.", details={"page_size": page_size})
    current_folder_getter = getattr(conn.media_pool, "GetCurrentFolder", None)
    current_folder = current_folder_getter() if callable(current_folder_getter) else None
    current_folder_native_id = media_pool_native_id(current_folder, folder=True) if current_folder is not None else None
    digest = hashlib.sha256()
    native_keys: set[bytes] = set()
    ambiguous_native_ids = False
    matching_count = 0
    page: list[dict[str, Any]] = []
    for row in _media_pool_rows(conn, deadline_at_ms):
        validate_deadline(deadline_at_ms)
        # Media Pool selection is transient UI state. DaVinci Resolve can
        # update it while fresh object references are acquired, including
        # immediately after import. Keep returning the fresh selected value,
        # but do not let selection-only drift invalidate the durable pool
        # revision used to bind asset and folder identities.
        revision_row = (
            {key: value for key, value in row.items() if key != "selected"}
            if row.get("entry_kind") == "asset"
            else row
        )
        encoded = json.dumps(
            revision_row,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        native_id = row.get("native_id")
        if native_id:
            native_key = hashlib.sha256(
                f"{row['entry_kind']}\0{native_id}".encode("utf-8")
            ).digest()
            if native_key in native_keys:
                ambiguous_native_ids = True
            native_keys.add(native_key)
        if _matches_media_search(row, search):
            if matching_count >= offset and len(page) < page_size:
                page.append(row)
            matching_count += 1
        validate_deadline(deadline_at_ms)
    if offset > matching_count:
        raise ValidationError(
            "Media Pool offset is beyond the current bounded result set.",
            details={"offset": offset, "total": matching_count},
        )
    validate_deadline(deadline_at_ms)
    next_offset = offset + len(page) if offset + len(page) < matching_count else None
    if not include_private_paths:
        page = [{key: value for key, value in row.items() if key != "source_path"} for row in page]
    return {
        "pool_digest": digest.hexdigest(),
        "ambiguous_native_ids": ambiguous_native_ids,
        "current_folder_native_id": current_folder_native_id,
        "offset": offset,
        "page_size": page_size,
        "search": search,
        "total": matching_count,
        "next_offset": next_offset,
        "entries": page,
    }
def _identity_state(
    conn: Any,
    *,
    include_timelines: bool,
    list_timelines: Callable[..., list[Dict[str, Any]]],
    include_project_folder: bool = False,
    include_project_libraries: bool = False,
    include_current_timeline_media_pool_item: bool = False,
) -> Dict[str, Any]:
    library = None
    current_database = getattr(getattr(conn, "project_manager", None), "GetCurrentDatabase", None)
    if callable(current_database):
        try:
            database = current_database()
        except Exception:
            database = None
        if isinstance(database, dict):
            database_name = database.get("DbName")
            database_type = database.get("DbType")
            if isinstance(database_name, str) and database_name.strip() and isinstance(database_type, str):
                normalized_type = database_type.strip().lower()
                if normalized_type in {"disk", "postgresql"}:
                    library = {"name": database_name.strip(), "kind": normalized_type}
                    if normalized_type == "postgresql":
                        address = database.get("IpAddress")
                        if isinstance(address, str) and address.strip():
                            library["address"] = address.strip()
    project_folder = (
        project_library_ops.current_project_folder_identity(conn)
        if include_project_folder
        else None
    )
    project_libraries = (
        project_library_ops.project_library_inventory_identity(conn)
        if include_project_libraries
        else None
    )
    project = getattr(conn, "project", None)
    if project is None:
        return {
            "library": library,
            "project": {
                "project_open": False,
                "context": "project_manager",
                "project_id": None,
                "name": None,
                "current_timeline": None,
            },
            **({"project_folder": project_folder} if include_project_folder else {}),
            **({"project_libraries": project_libraries} if include_project_libraries else {}),
            **({"timelines": []} if include_timelines else {}),
        }

    try:
        name = project.GetName()
    except Exception:
        name = None
    try:
        timeline_count = project.GetTimelineCount() or 0
    except Exception:
        timeline_count = None
    if looks_like_project_manager_placeholder(conn, name, timeline_count):
        return {
            "library": library,
            "project": {
                "project_open": False,
                "context": "project_manager",
                "project_id": None,
                "name": name,
                "current_timeline": None,
            },
            **({"project_folder": project_folder} if include_project_folder else {}),
            **({"project_libraries": project_libraries} if include_project_libraries else {}),
            **({"timelines": []} if include_timelines else {}),
        }

    timeline = getattr(conn, "timeline", None)
    try:
        current_timeline = timeline.GetName() if timeline is not None else None
    except Exception:
        current_timeline = None
    current_timeline_media_pool_item_id = None
    if include_current_timeline_media_pool_item and timeline is not None:
        getter = getattr(timeline, "GetMediaPoolItem", None)
        if callable(getter):
            try:
                media_pool_item = getter()
            except Exception:
                media_pool_item = None
            if media_pool_item is not None:
                current_timeline_media_pool_item_id = documented_unique_id(media_pool_item)
    project_id = documented_unique_id(project)
    return {
        "library": library,
        "project": {
            "project_open": True,
            "context": "project",
            "project_id": project_id,
            "name": name,
            "current_timeline": current_timeline,
        },
        **({"project_folder": project_folder} if include_project_folder else {}),
        **({"project_libraries": project_libraries} if include_project_libraries else {}),
        **({"timelines": list_timelines(conn, authoritative_ids=True)} if include_timelines else {}),
        **(
            {"current_timeline_media_pool_item_id": current_timeline_media_pool_item_id}
            if include_current_timeline_media_pool_item
            else {}
        ),
    }


def _safe_call(target: Any, method_name: str, *args: Any) -> tuple[bool, Any]:
    method = getattr(target, method_name, None)
    if not callable(method):
        return False, None
    try:
        return True, method(*args)
    except Exception:
        return False, None


def _color_capability(available: bool) -> Dict[str, str]:
    return {
        "status": "supported" if available else "unavailable",
        **({} if available else {"reason": "not_exposed_by_runtime"}),
    }


def _bounded_text(value: Any, *, maximum: int = 4096) -> str:
    if not isinstance(value, str):
        return ""
    return value[:maximum]


def _version_names(value: Any) -> tuple[bool, list[str]]:
    values = list(value.values()) if isinstance(value, dict) else value
    if not isinstance(values, (list, tuple)):
        return False, []
    if any(not isinstance(item, str) for item in values):
        return False, []
    return True, [item[:1024] for item in values if item]


def _looks_like_private_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    return (
        value.startswith(("/", "\\"))
        or value.lower().startswith("file:")
        or (len(value) >= 2 and value[0].isalpha() and value[1] == ":")
        or normalized.startswith("~")
        or ("/" in normalized and value not in SDK_PUBLIC_SLASH_EFFECT_NAMES)
    )


def _tool_names(value: Any) -> tuple[bool, list[str]]:
    values = list(value.values()) if isinstance(value, dict) else value
    if not isinstance(values, (list, tuple)):
        return False, []
    if any(not isinstance(item, str) for item in values):
        return False, []
    if any(
        len(item) > 512 or any(unicodedata.category(char).startswith("C") for char in item)
        for item in values
    ):
        return False, []
    raw_names = [item for item in values if item.strip()]
    names = [item.strip() for item in raw_names]
    if any(_looks_like_private_path(item) for item in names):
        return False, []
    return True, names


def _inspect_current_color_target(conn: Any, node_stack_layer_index: int = 1) -> Dict[str, Any] | None:
    """Inspect the active Color target without changing page or selection state."""

    if isinstance(node_stack_layer_index, bool) or not isinstance(node_stack_layer_index, int) or not 1 <= node_stack_layer_index <= 4096:
        raise ValidationError(
            "Node-stack layer index is outside the bounded SDK range.",
            details={"node_stack_layer_index": node_stack_layer_index, "minimum": 1, "maximum": 4096},
            recoverability="not_applicable",
        )

    setting_available, raw_layer_count = _safe_call(getattr(conn, "project", None), "GetSetting", "nodeStackLayers")
    if setting_available and raw_layer_count not in (None, ""):
        try:
            configured_layer_count = int(raw_layer_count)
        except (TypeError, ValueError) as exc:
            raise APICallFailed(
                "DaVinci Resolve returned an invalid configured Color node-stack layer count.",
                details={"node_stack_layers": raw_layer_count},
            ) from exc
        if configured_layer_count < 1 or configured_layer_count > 4096:
            raise APICallFailed(
                "DaVinci Resolve returned an invalid configured Color node-stack layer count.",
                details={"node_stack_layers": configured_layer_count},
            )
        if node_stack_layer_index > configured_layer_count:
            raise ValidationError(
                "Node-stack layer index exceeds the configured project layer count.",
                details={
                    "node_stack_layer_index": node_stack_layer_index,
                    "node_stack_layer_count": configured_layer_count,
                    "minimum": 1,
                    "maximum": configured_layer_count,
                },
                recoverability="not_applicable",
            )

    timeline = getattr(conn, "timeline", None)
    target_available, item = _safe_call(timeline, "GetCurrentVideoItem")
    if not target_available or not item:
        return None

    target_id = documented_unique_id(item)
    _, target_name = _safe_call(item, "GetName")
    graph_available, graph = (
        _safe_call(item, "GetNodeGraph")
        if node_stack_layer_index == 1
        else _safe_call(item, "GetNodeGraph", node_stack_layer_index)
    )
    graph_available = bool(graph_available and graph)
    count_available, raw_count = _safe_call(graph, "GetNumNodes") if graph_available else (False, None)
    try:
        if not isinstance(raw_count, int) or isinstance(raw_count, bool):
            raise TypeError
        node_count = raw_count if count_available else 0
    except (TypeError, ValueError):
        count_available = False
        node_count = 0
    if node_count < 0 or node_count > 4096:
        count_available = False
        node_count = 0

    graph_readable = bool(graph_available and count_available)
    node_capabilities = {
        "labels": _color_capability(bool(graph_readable and callable(getattr(graph, "GetNodeLabel", None)))),
        "enabledState": _color_capability(False),
        "luts": _color_capability(bool(graph_readable and callable(getattr(graph, "GetLUT", None)))),
        "effects": _color_capability(bool(graph_readable and callable(getattr(graph, "GetToolsInNode", None)))),
    }
    label_reads_ok = node_capabilities["labels"]["status"] == "supported"
    lut_reads_ok = node_capabilities["luts"]["status"] == "supported"
    effect_reads_ok = node_capabilities["effects"]["status"] == "supported"
    nodes: list[Dict[str, Any]] = []
    for index in range(1, node_count + 1):
        label_ok, label = _safe_call(graph, "GetNodeLabel", index)
        lut_ok, lut = _safe_call(graph, "GetLUT", index)
        effects_ok, effects = _safe_call(graph, "GetToolsInNode", index)
        label_ok = label_ok and isinstance(label, str)
        lut_ok = lut_ok and isinstance(lut, str)
        label_reads_ok = label_reads_ok and label_ok
        lut_reads_ok = lut_reads_ok and lut_ok
        effects_shape_ok, normalized_effects = _tool_names(effects) if effects_ok else (False, [])
        effect_reads_ok = effect_reads_ok and effects_ok and effects_shape_ok
        nodes.append({
            "index": index,
            "label": _bounded_text(label) if label_ok else None,
            "enabled": None,
            "lut": _bounded_text(lut) if lut_ok else None,
            "effects": normalized_effects,
        })

    node_capabilities["labels"] = _color_capability(label_reads_ok)
    node_capabilities["luts"] = _color_capability(lut_reads_ok)
    node_capabilities["effects"] = _color_capability(effect_reads_ok)

    local_ok, local_versions_raw = _safe_call(item, "GetVersionNameList", 0)
    remote_ok, remote_versions_raw = _safe_call(item, "GetVersionNameList", 1)
    local_shape_ok, local_versions = _version_names(local_versions_raw) if local_ok else (False, [])
    remote_shape_ok, remote_versions = _version_names(remote_versions_raw) if remote_ok else (False, [])
    current_ok, current_version = _safe_call(item, "GetCurrentVersion")
    current_name = None
    current_name_ok = False
    if current_ok and isinstance(current_version, dict):
        current_name = next((current_version.get(key) for key in ("versionName", "VersionName", "name", "Name") if isinstance(current_version.get(key), str) and current_version.get(key)), None)
        current_name_ok = current_name is not None
    elif current_ok and isinstance(current_version, str) and current_version:
        current_name = current_version
        current_name_ok = True
    if not current_name:
        current_name_ok, current_name_fallback = _safe_call(item, "GetCurrentVersionName")
        current_name_ok = current_name_ok and isinstance(current_name_fallback, str) and bool(current_name_fallback)
        if current_name_ok:
            current_name = current_name_fallback
    group_ok, group = _safe_call(item, "GetColorGroup")
    if group_ok and group is None:
        group_name_ok, group_name = True, None
    elif group_ok and group is not False:
        group_name_ok, group_name = _safe_call(group, "GetName")
        group_name_ok = group_name_ok and isinstance(group_name, str) and bool(group_name)
    else:
        group_name_ok, group_name = False, None
    versions_ok = bool(local_ok and local_shape_ok and remote_ok and remote_shape_ok and current_name_ok)
    if not versions_ok:
        current_name = None
        local_versions = []
        remote_versions = []

    grade_state = None
    try:
        if node_stack_layer_index != 1:
            raise LookupError("Project.db grade evidence is not node-stack-layer scoped.")
        from . import color_page_db

        grade_readback = color_page_db.read_color_grade_for_clip(conn, include_private_topology=True)
        signature = color_page_db._grade_state_signature(grade_readback)
        primary_names = {
            "contrast", "pivot", "temperature", "tint", "hue",
            "color_boost", "mid_detail", "shadows", "highlights",
        }
        primary_by_node: dict[str, dict[str, float]] = {}
        for param in (grade_readback.get("readback") or {}).get("raw_params") or []:
            if not isinstance(param, dict) or param.get("name") not in primary_names:
                continue
            node = param.get("node")
            value = param.get("value")
            if isinstance(node, int) and node > 0 and isinstance(value, (int, float)) and not isinstance(value, bool):
                primary_by_node.setdefault(str(node), {})[str(param["name"])] = round(float(value), 6)
        grade_state = {
            "sha256": str(signature["sha256"]),
            "has_grade": bool(signature["has_grade"]),
            "raw_param_count": int(signature["raw_param_count"]),
            "primary_by_node": primary_by_node,
            "topology": grade_readback.get("topology_state"),
            "resolvefx_by_node": grade_readback.get("resolvefx_by_node"),
        }
    except Exception:
        # PostgreSQL/Cloud projects and runtimes without readable Project.db
        # retain the native graph inspection contract without inventing DB truth.
        grade_state = None

    return {
        "target": {
            "timeline_item_unique_id": target_id,
            "name": _bounded_text(target_name),
        },
        "capabilities": {
            "nodeGraph": _color_capability(graph_readable),
            **node_capabilities,
            "versions": _color_capability(versions_ok),
            "colorGroup": _color_capability(bool(group_ok and group_name_ok)),
        },
        "node_graph": {
            "node_stack_layer_index": node_stack_layer_index,
            "node_count": node_count,
            "nodes": nodes,
        },
        "versions": {
            "current": _bounded_text(current_name) if current_name not in (None, "", False) else None,
            "local": local_versions,
            "remote": remote_versions,
        },
        "color_group": _bounded_text(group_name, maximum=1024) if group_ok and group_name_ok and group_name not in (None, False) else None,
        "grade_state": grade_state,
    }


def inspect_live_state(
    conn: Any,
    operation: str,
    *,
    deadline_at_ms: int | None,
    list_timelines: Callable[..., list[Dict[str, Any]]],
    summarize_timeline: Callable[..., Dict[str, Any]],
    list_markers: Callable[..., list[Dict[str, Any]]] | None = None,
    inspect_fairlight: Callable[[Any], Dict[str, Any]] | None = None,
    offset: int = 0,
    page_size: int = 100,
    search: dict[str, Any] | None = None,
    multicam_name: str | None = None,
    inspect_multicam: Callable[[Any, str], Dict[str, Any]] | None = None,
    managed_affected_native_ids: list[str] | None = None,
    managed_retained_database_native_ids: list[str] | None = None,
    retime_expected_targets: list[dict[str, Any]] | None = None,
    inspect_retime: Callable[[Any, list[dict[str, Any]]], Dict[str, Any]] | None = None,
    node_stack_layer_index: int = 1,
) -> Dict[str, Any]:
    """Return one bracketed SDK inspection from a single CutAgent CLI process."""

    if operation not in SDK_LIVE_INSPECTION_OPERATIONS:
        raise ValidationError(
            "Unsupported SDK live inspection operation.",
            details={"operation": operation},
            recoverability="not_applicable",
        )
    include_timelines = operation in {
        "project.context",
        "project.folder_context",
        "project.library_context",
        "timeline.current",
        "timeline.list",
        "timeline.retime",
        "timeline.snapshot",
        "color.current",
        "fusion.compositions",
        "managed.protected",
    }
    validate_deadline(deadline_at_ms)
    include_project_folder = operation == "project.folder_context"
    include_project_libraries = operation == "project.library_context"
    include_current_timeline_media_pool_item = operation == "timeline.current"
    before = _identity_state(
        conn,
        include_timelines=include_timelines,
        list_timelines=list_timelines,
        include_project_folder=include_project_folder,
        include_project_libraries=include_project_libraries,
        include_current_timeline_media_pool_item=include_current_timeline_media_pool_item,
    )
    validate_deadline(deadline_at_ms)
    summary = None
    summary_before = None
    summary_after = None
    color_before = None
    if operation in {"timeline.snapshot", "timeline.retime", "color.current", "fusion.compositions", "managed.protected"} and getattr(conn, "timeline", None) is not None and list_markers is None:
        raise ValidationError("SDK timeline inspection requires marker readback.")
    if operation in {"timeline.snapshot", "timeline.retime", "color.current", "managed.protected"} and getattr(conn, "timeline", None) is not None:
        inspected_summary = summarize_timeline(
            conn,
            window="all",
            max_runs=1,
            include_items=True,
            authoritative_track_state=True,
        )
        if operation in {"timeline.snapshot", "timeline.retime", "managed.protected"}:
            summary = {
                **inspected_summary,
                "markers": list_markers(conn),
                "fairlight": inspect_fairlight(conn) if inspect_fairlight is not None else None,
            }
            if operation == "timeline.retime":
                if inspect_retime is None or not retime_expected_targets:
                    raise ValidationError("SDK retime inspection requires exact native targets.")
                summary["retime"] = inspect_retime(conn, retime_expected_targets)
        else:
            summary_before = {
                **inspected_summary,
                "markers": list_markers(conn),
                "fairlight": inspect_fairlight(conn) if inspect_fairlight is not None else None,
            }
    elif operation == "fusion.compositions":
        inspected_timeline = summarize_timeline(
            conn,
            window="all",
            max_runs=1,
            include_items=True,
            authoritative_track_state=True,
        )
        summary = {
            "timeline": {
                **inspected_timeline,
                "markers": list_markers(conn),
                "fairlight": inspect_fairlight(conn) if inspect_fairlight is not None else None,
            },
            "fusion": inspect_fusion_compositions(conn, deadline_at_ms=deadline_at_ms, target=_fusion_inspection_target()),
        }
    elif operation == "mediaPool.page":
        summary = inspect_media_pool_page(
            conn,
            deadline_at_ms=deadline_at_ms,
            offset=offset,
            page_size=page_size,
            search=search,
            include_private_paths=os.environ.get(SDK_MEDIA_POOL_PRIVATE_PATHS_ENV) == "1",
        )
    elif operation == "storage.mattes":
        summary = _inspect_storage_mattes(conn, list(managed_affected_native_ids or []), deadline_at_ms)
    if operation == "color.current":
        color_before = _inspect_current_color_target(conn, node_stack_layer_index)
    elif operation == "multicam.inspect":
        if not multicam_name or inspect_multicam is None:
            raise ValidationError("SDK multicam inspection requires an exact multicam name.")
        summary = inspect_multicam(conn, multicam_name)
    validate_deadline(deadline_at_ms)
    conn.refresh()
    validate_deadline(deadline_at_ms)
    if operation == "color.current":
        color_after = _inspect_current_color_target(conn, node_stack_layer_index)
        if getattr(conn, "timeline", None) is not None:
            inspected_summary_after = summarize_timeline(
                conn,
                window="all",
                max_runs=1,
                include_items=True,
                authoritative_track_state=True,
            )
            summary_after = {
                **inspected_summary_after,
                "markers": list_markers(conn),
                "fairlight": inspect_fairlight(conn) if inspect_fairlight is not None else None,
            }
        validate_deadline(deadline_at_ms)
        after = _identity_state(conn, include_timelines=include_timelines, list_timelines=list_timelines, include_project_folder=include_project_folder, include_project_libraries=include_project_libraries, include_current_timeline_media_pool_item=include_current_timeline_media_pool_item)
        validate_deadline(deadline_at_ms)
        return {
            "before": before,
            "after": after,
            "summary": None,
            "summary_before": summary_before,
            "summary_after": summary_after,
            "color_before": color_before,
            "color_after": color_after,
            "mutation_guard": color_mutation_guard(after, summary_after, color_after),
        }

    after = _identity_state(conn, include_timelines=include_timelines, list_timelines=list_timelines, include_project_folder=include_project_folder, include_project_libraries=include_project_libraries, include_current_timeline_media_pool_item=include_current_timeline_media_pool_item)
    if operation == "mediaPool.page":
        summary_after = inspect_media_pool_page(
            conn,
            deadline_at_ms=deadline_at_ms,
            offset=offset,
            page_size=page_size,
            search=search,
            include_private_paths=os.environ.get(SDK_MEDIA_POOL_PRIVATE_PATHS_ENV) == "1",
        )
        validate_deadline(deadline_at_ms)
        if before != after or summary.get("pool_digest") != summary_after.get("pool_digest"):
            raise SdkMutationStaleRevision(
                "DaVinci Resolve Media Pool changed during SDK inspection.",
                details={"operation": operation},
            )
        summary = summary_after
    elif operation == "storage.mattes":
        summary_after = _inspect_storage_mattes(conn, list(managed_affected_native_ids or []), deadline_at_ms)
        validate_deadline(deadline_at_ms)
        if before != after or summary != summary_after:
            raise SdkMutationStaleRevision(
                "DaVinci Resolve matte associations changed during SDK inspection.",
                details={"operation": operation},
            )
        summary = summary_after
    if operation in {"timeline.snapshot", "timeline.retime", "managed.protected"} and getattr(conn, "timeline", None) is not None:
        summary_after = summarize_timeline(
            conn,
            window="all",
            max_runs=1,
            include_items=True,
            authoritative_track_state=True,
        )
        summary_after = {
            **summary_after,
            "markers": list_markers(conn),
            "fairlight": inspect_fairlight(conn) if inspect_fairlight is not None else None,
        }
        if operation == "timeline.retime":
            if inspect_retime is None or not retime_expected_targets:
                raise ValidationError("SDK retime inspection requires exact native targets.")
            summary_after["retime"] = inspect_retime(conn, retime_expected_targets)
        validate_deadline(deadline_at_ms)
        if before != after or summary != summary_after:
            raise SdkMutationStaleRevision(
                "DaVinci Resolve live state changed during the SDK timeline inspection.",
                details={"operation": operation},
            )
        summary = summary_after
        if operation == "managed.protected":
            from .managed_protected_state import attest_managed_protected_state

            attestation = attest_managed_protected_state(
                conn,
                affected_native_ids=list(managed_affected_native_ids or []),
                retained_database_native_ids=list(managed_retained_database_native_ids or managed_affected_native_ids or []),
            )
            return {"before": before, "after": after, "summary": summary, "attestation": attestation}
    elif operation == "multicam.inspect":
        summary_after = inspect_multicam(conn, multicam_name) if inspect_multicam is not None and multicam_name else None
        validate_deadline(deadline_at_ms)
        if before != after or summary != summary_after:
            raise SdkMutationStaleRevision(
                "DaVinci Resolve live state changed during the SDK multicam inspection.",
                details={"operation": operation},
            )
        summary = summary_after
    elif operation == "fusion.compositions" and getattr(conn, "timeline", None) is not None:
        inspected_timeline_after = summarize_timeline(
            conn,
            window="all",
            max_runs=1,
            include_items=True,
            authoritative_track_state=True,
        )
        summary_after = {
            "timeline": {
                **inspected_timeline_after,
                "markers": list_markers(conn),
                "fairlight": inspect_fairlight(conn) if inspect_fairlight is not None else None,
            },
            "fusion": inspect_fusion_compositions(conn, deadline_at_ms=deadline_at_ms, target=_fusion_inspection_target()),
        }
        validate_deadline(deadline_at_ms)
        if before != after or summary != summary_after:
            raise SdkMutationStaleRevision(
                "DaVinci Resolve live state changed during the SDK Fusion inspection.",
                details={"operation": operation},
            )
        summary = summary_after
    guard = marker_mutation_guard(after, summary) if operation == "timeline.snapshot" else project_mutation_guard(after) if operation in {"project.context", "project.folder_context", "project.library_context"} else media_pool_mutation_guard(after, summary["pool_digest"]) if operation == "mediaPool.page" else None
    return {"before": before, "after": after, "summary": summary, "mutation_guard": guard}


def require_project_mutation_guard(conn: Any, *, list_timelines: Callable[..., list[Dict[str, Any]]]) -> None:
    """Fail before mutation if the bridge-inspected project context has changed."""

    expected = os.environ.get(SDK_PROJECT_GUARD_ENV)
    if expected is None:
        return
    actual = project_mutation_guard(_identity_state(conn, include_timelines=True, list_timelines=list_timelines))
    if hmac.compare_digest(expected, actual):
        return
    folder_actual = project_mutation_guard(_identity_state(conn, include_timelines=True, list_timelines=list_timelines, include_project_folder=True))
    if not hmac.compare_digest(expected, folder_actual):
        raise SdkMutationStaleRevision("DaVinci Resolve project context changed after SDK inspection.")


def require_media_pool_mutation_guard(conn: Any) -> None:
    """Fail before mutation if the bridge-inspected Media Pool inventory has changed."""

    expected = os.environ.get(SDK_MEDIA_POOL_GUARD_ENV)
    if expected is None:
        return
    identity = _identity_state(conn, include_timelines=False, list_timelines=lambda *_args, **_kwargs: [])
    summary = inspect_media_pool_page(
        conn,
        deadline_at_ms=int(time.time() * 1000) + SDK_LIVE_INSPECTION_MAX_DEADLINE_WINDOW_MS,
        offset=0,
        page_size=1,
        search=None,
    )
    actual = media_pool_mutation_guard(identity, summary["pool_digest"])
    if not hmac.compare_digest(expected, actual):
        raise SdkMutationStaleRevision("DaVinci Resolve Media Pool changed after SDK inspection.")


def require_marker_mutation_guard(
    conn: Any,
    *,
    list_timelines: Callable[..., list[Dict[str, Any]]],
    summarize_timeline: Callable[..., Dict[str, Any]],
    list_markers: Callable[..., list[Dict[str, Any]]],
    inspect_fairlight: Callable[[Any], Dict[str, Any]],
) -> None:
    """Fail before mutation if the bridge-inspected state has changed."""

    expected = (
        os.environ.get(SDK_MUTATION_GUARD_ENV)
        or os.environ.get(SDK_TIMELINE_GUARD_ENV)
        or os.environ.get(SDK_MARKER_GUARD_ENV)
    )
    if expected is None:
        return
    inspected = inspect_live_state(
        conn,
        "timeline.snapshot",
        deadline_at_ms=int(time.time() * 1000) + SDK_LIVE_INSPECTION_MAX_DEADLINE_WINDOW_MS,
        list_timelines=list_timelines,
        summarize_timeline=summarize_timeline,
        list_markers=list_markers,
        inspect_fairlight=inspect_fairlight,
    )
    actual = inspected.get("mutation_guard")
    if inspected.get("before") != inspected.get("after") or not isinstance(actual, str) or not hmac.compare_digest(expected, actual):
        raise SdkMutationStaleRevision(
            "The SDK marker mutation precondition no longer matches live DaVinci Resolve state.",
            details={"expected_guard": expected, "actual_guard": actual},
        )
def require_color_mutation_guard(
    conn: Any,
    *,
    list_timelines: Callable[..., list[Dict[str, Any]]],
    summarize_timeline: Callable[..., Dict[str, Any]],
    list_markers: Callable[..., list[Dict[str, Any]]],
    inspect_fairlight: Callable[[Any], Dict[str, Any]] | None = None,
) -> None:
    """Fail inside the mutation process if the exact Color target or grade graph changed."""

    expected = os.environ.get(SDK_COLOR_GUARD_ENV)
    if expected is None:
        return
    raw_layer_index = os.environ.get(SDK_COLOR_NODE_STACK_LAYER_INDEX_ENV, "1")
    try:
        node_stack_layer_index = int(raw_layer_index)
    except ValueError as exc:
        raise ValidationError("SDK Color node-stack layer guard is invalid.") from exc
    inspected = inspect_live_state(
        conn,
        "color.current",
        deadline_at_ms=int(time.time() * 1000) + SDK_LIVE_INSPECTION_MAX_DEADLINE_WINDOW_MS,
        list_timelines=list_timelines,
        summarize_timeline=summarize_timeline,
        list_markers=list_markers,
        inspect_fairlight=inspect_fairlight,
        node_stack_layer_index=node_stack_layer_index,
    )
    actual = inspected.get("mutation_guard")
    if inspected.get("before") != inspected.get("after") or not isinstance(actual, str) or not hmac.compare_digest(expected, actual):
        raise SdkMutationStaleRevision(
            "The SDK Color mutation precondition no longer matches live DaVinci Resolve state.",
            details={"expected_guard": expected, "actual_guard": actual},
        )


def _fusion_public_value(value: Any, *, field: str = "value", depth: int = 0) -> Any:
    """Return complete bounded private revision evidence or fail closed."""

    if depth > 16:
        raise APICallFailed(f"DaVinci Resolve returned excessively nested Fusion {field} evidence.")
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise APICallFailed(f"DaVinci Resolve returned non-finite Fusion {field} evidence.")
        return 0 if value == 0 else value
    if isinstance(value, str):
        if len(value.encode("utf-8", "strict")) > 65_536:
            raise APICallFailed(f"DaVinci Resolve returned oversized Fusion {field} evidence.")
        return value
    if isinstance(value, (list, tuple)):
        if len(value) > 10_000:
            raise APICallFailed(f"DaVinci Resolve returned too many Fusion {field} values.")
        return [
            _fusion_public_value(item, field=f"{field}[{index}]", depth=depth + 1)
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        if len(value) > 10_000:
            raise APICallFailed(f"DaVinci Resolve returned too many Fusion {field} entries.")
        result: dict[str, Any] = {}
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
            text_key = str(key)
            if len(text_key.encode("utf-8", "strict")) > 1_024 or text_key in result:
                raise APICallFailed(f"DaVinci Resolve returned invalid Fusion {field} keys.")
            result[text_key] = _fusion_public_value(item, field=f"{field}.{text_key}", depth=depth + 1)
        return result
    try:
        native_id_getter = getattr(value, "GetID", None)
        native_id = native_id_getter() if callable(native_id_getter) else None
    except Exception as exc:
        raise APICallFailed(f"DaVinci Resolve returned unreadable Fusion {field} evidence.") from exc
    if native_id in {"Gradient", "ColorCurves", "Histogram"}:
        try:
            native_value = value.Value
        except Exception as exc:
            raise APICallFailed(f"DaVinci Resolve returned unreadable Fusion {field} evidence.") from exc
        if native_value is value:
            raise APICallFailed(f"DaVinci Resolve returned cyclic Fusion {field} evidence.")
        return {
            "fusionValueType": native_id,
            "value": _fusion_public_value(
                native_value,
                field=f"{field} {native_id}",
                depth=depth + 1,
            ),
        }
    raise APICallFailed(f"DaVinci Resolve returned unreadable Fusion {field} evidence.")


def _fusion_endpoint(native_output: Any) -> dict[str, str] | None:
    if native_output is None:
        return None
    try:
        output_attrs = native_output.GetAttrs() or {}
        source_tool = native_output.GetTool()
        tool_attrs = source_tool.GetAttrs() or {}
    except Exception as exc:
        raise APICallFailed("DaVinci Resolve could not inspect a Fusion connection endpoint.") from exc
    if not isinstance(output_attrs, dict) or not isinstance(tool_attrs, dict):
        raise APICallFailed("DaVinci Resolve returned invalid Fusion connection endpoint evidence.")
    tool_name = tool_attrs.get("TOOLS_Name")
    tool_type = tool_attrs.get("TOOLS_RegID")
    output_id = output_attrs.get("OUTS_ID")
    if not all(isinstance(value, str) and value for value in (tool_name, tool_type, output_id)):
        raise APICallFailed("DaVinci Resolve returned incomplete Fusion connection endpoint evidence.")
    return {"node": tool_name, "nodeType": tool_type, "port": output_id}


def _fusion_graph_evidence(comp: Any, deadline_at_ms: int | None) -> dict[str, Any]:
    try:
        tools = comp.GetToolList(False) or {}
    except Exception as exc:
        raise APICallFailed("DaVinci Resolve could not inspect the Fusion composition graph.") from exc
    if not isinstance(tools, dict) or len(tools) > 1_024:
        raise APICallFailed("DaVinci Resolve returned an invalid Fusion composition graph.")
    nodes: list[dict[str, Any]] = []
    for key, tool in sorted(tools.items(), key=lambda pair: str(pair[0])):
        validate_deadline(deadline_at_ms)
        try:
            attrs = tool.GetAttrs() or {}
            inputs = tool.GetInputList() or {}
        except Exception as exc:
            raise APICallFailed("DaVinci Resolve could not inspect a Fusion graph node.") from exc
        if not isinstance(attrs, dict) or not isinstance(inputs, dict) or len(inputs) > 4_096:
            raise APICallFailed("DaVinci Resolve returned invalid Fusion graph node evidence.")
        input_rows = []
        for input_key, native_input in sorted(inputs.items(), key=lambda pair: str(pair[0])):
            try:
                input_attrs = native_input.GetAttrs() or {}
                input_id = input_attrs.get("INPS_ID") if isinstance(input_attrs, dict) else None
                if not isinstance(input_id, str) or not input_id:
                    input_id = str(input_key)
                connected = _fusion_endpoint(native_input.GetConnectedOutput())
                expression = getattr(native_input, "Expression", None)
                keyframes_getter = getattr(native_input, "GetKeyFrames", None)
                keyframes = keyframes_getter() if callable(keyframes_getter) else {}
                current = None if connected is not None else tool.GetInput(input_id, 0)
            except APICallFailed:
                raise
            except Exception as exc:
                raise APICallFailed("DaVinci Resolve could not inspect a Fusion graph input.") from exc
            input_rows.append({
                "id": input_id,
                "value": _fusion_public_value(current, field=f"input {input_id}"),
                "connection": connected,
                "expression": _fusion_public_value(expression, field=f"expression {input_id}"),
                "keyframes": _fusion_public_value(keyframes or {}, field=f"keyframes {input_id}"),
            })
        tool_keyframes_getter = getattr(tool, "GetKeyFrames", None)
        try:
            tool_keyframes = tool_keyframes_getter() if callable(tool_keyframes_getter) else {}
        except Exception as exc:
            raise APICallFailed("DaVinci Resolve could not inspect Fusion tool keyframe curves.") from exc
        nodes.append({
            "key": str(key),
            "name": str(attrs.get("TOOLS_Name") or key),
            "type": str(attrs.get("TOOLS_RegID") or ""),
            "inputs": input_rows,
            "keyframes": _fusion_public_value(tool_keyframes or {}, field="tool keyframes"),
        })
    return {"nodes": nodes}


def _fusion_inspection_target() -> dict[str, str] | None:
    """Read the closed, private bridge selector; absent preserves full internal inspection."""
    raw = os.environ.get(SDK_FUSION_INSPECTION_TARGET_ENV)
    if raw is None:
        return None
    try:
        target = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError("SDK Fusion inspection target is malformed.") from exc
    if (not isinstance(target, dict) or set(target) != {"timelineId", "timelineItemId"}
            or not isinstance(target["timelineId"], str)
            or not re.fullmatch(r"timeline_f[A-Za-z0-9_-]{43}", target["timelineId"])
            or not isinstance(target["timelineItemId"], str)
            or not re.fullmatch(r"timeline_item_f[A-Za-z0-9_-]{43}", target["timelineItemId"])):
        raise ValidationError("SDK Fusion inspection requires exact public timeline and timeline-item identities.")
    return target


def _fusion_item_matches(native_id: str, target: dict[str, str]) -> bool:
    # Same canonical identity projection as the bridge. Native IDs remain private.
    payload = json.dumps({"nativeId": native_id, "timelineId": target["timelineId"]},
                         sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    opaque_id = "timeline_item_f" + base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).decode("ascii").rstrip("=")
    return hmac.compare_digest(opaque_id, target["timelineItemId"])


def inspect_fusion_compositions(conn: Any, *, deadline_at_ms: int | None,
                               target: dict[str, str] | None = None) -> dict[str, Any]:
    """Inspect complete graphs only for the exact requested item, or all for internal callers.

    Both live-inspection brackets retain full timeline inventories and graph evidence.
    Enumerate all IDs even after a match so duplicate identity remains detectable.
    """

    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        return {"items": []}
    items: list[dict[str, Any]] = []
    try:
        track_count = int(timeline.GetTrackCount("video") or 0)
    except Exception as exc:
        raise APICallFailed("DaVinci Resolve could not inspect video tracks for Fusion compositions.") from exc
    for track_index in range(1, track_count + 1):
        validate_deadline(deadline_at_ms)
        try:
            track_items = timeline.GetItemListInTrack("video", track_index) or []
        except Exception as exc:
            raise APICallFailed("DaVinci Resolve could not inspect timeline items for Fusion compositions.") from exc
        if not isinstance(track_items, list) or len(track_items) > SDK_MEDIA_POOL_MAX_INVENTORY:
            raise APICallFailed("DaVinci Resolve returned an invalid timeline-item inventory.")
        for item in track_items:
            validate_deadline(deadline_at_ms)
            item_id = documented_unique_id(item)
            if item_id is None:
                continue
            if target is not None and not _fusion_item_matches(item_id, target):
                continue
            try:
                count = int(item.GetFusionCompCount() or 0)
            except Exception as exc:
                raise APICallFailed("DaVinci Resolve could not inspect Fusion composition count.") from exc
            if count < 0 or count > 128:
                raise APICallFailed("DaVinci Resolve returned an invalid Fusion composition count.")
            compositions = []
            for index in range(1, count + 1):
                validate_deadline(deadline_at_ms)
                try:
                    comp = item.GetFusionCompByIndex(index)
                    attrs = comp.GetAttrs() if comp is not None else None
                except Exception as exc:
                    raise APICallFailed("DaVinci Resolve could not inspect a Fusion composition.") from exc
                if comp is None or not isinstance(attrs, dict):
                    raise APICallFailed("DaVinci Resolve returned an invalid Fusion composition reference.")
                name = attrs.get("COMPS_Name") or attrs.get("COMPN_Name") or f"Composition {index}"
                graph = _fusion_graph_evidence(comp, deadline_at_ms)
                compositions.append({
                    "index": index,
                    "name": str(name)[:1_024],
                    "graph": graph,
                    "graph_digest": fusion_graph_digest(graph),
                })
            items.append({"native_item_id": item_id, "compositions": compositions})
    return {"items": items}
require_mutation_guard = require_marker_mutation_guard
