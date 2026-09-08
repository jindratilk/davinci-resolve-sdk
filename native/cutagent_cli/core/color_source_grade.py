"""Source/remote color grade workflow helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._clip_ops.lookup import cutagent_clip
from ..errors import APICallFailed, ValidationError


REMOTE_VERSION_TYPE = 1


def _call_optional(obj: Any, method_name: str, *args: Any) -> Any:
    method = getattr(obj, method_name, None)
    if not callable(method):
        return None
    try:
        return method(*args)
    except Exception:
        return None


def _dict_get_first(values: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in values and values[key] not in (None, ""):
            return values[key]
    lowered = {str(key).lower(): value for key, value in values.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value not in (None, ""):
            return value
    return None


def _clip_properties(media_pool_item: Any) -> dict[str, Any]:
    if media_pool_item is None:
        return {}
    getter = getattr(media_pool_item, "GetClipProperty", None)
    if not callable(getter):
        return {}
    try:
        props = getter() or {}
    except Exception:
        return {}
    return props if isinstance(props, dict) else {}


def _timeline_item_property(item: Any, key: str) -> Any:
    getter = getattr(item, "GetProperty", None)
    if not callable(getter):
        return None
    try:
        return getter(key)
    except Exception:
        return None


def _normalize_source_path(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return str(Path(text).expanduser())
    except Exception:
        return text


@dataclass(frozen=True)
class SourceIdentity:
    kind: str
    value: str

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.value}"

    def as_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "value": self.value, "key": self.key}


def _media_source_identity(item: Any) -> SourceIdentity:
    mpi = _call_optional(item, "GetMediaPoolItem")
    props = _clip_properties(mpi)

    media_unique_id = _call_optional(mpi, "GetUniqueId")
    if media_unique_id:
        return SourceIdentity("media_pool_unique_id", str(media_unique_id))

    source_path = _normalize_source_path(
        _dict_get_first(
            props,
            (
                "File Path",
                "FilePath",
                "Source File",
                "SourceFile",
                "Source Path",
                "SourcePath",
                "Path",
            ),
        )
        or _timeline_item_property(item, "File Path")
        or _timeline_item_property(item, "Source File")
    )
    if source_path:
        return SourceIdentity("source_path", source_path)

    media_name = _call_optional(mpi, "GetName") or _dict_get_first(props, ("Clip Name", "File Name", "Name"))
    if media_name:
        return SourceIdentity("media_pool_name", str(media_name))

    item_name = _call_optional(item, "GetName")
    if item_name:
        return SourceIdentity("timeline_item_name", str(item_name))

    raise ValidationError(
        "Timeline item does not expose enough media identity to build a source grade scope.",
        details={"required": ["TimelineItem.GetMediaPoolItem", "MediaPoolItem.GetClipProperty", "TimelineItem.GetName"]},
        recoverability="manual",
    )


def _item_summary(item: Any, *, track_index: int | None = None, index_in_track: int | None = None) -> dict[str, Any]:
    mpi = _call_optional(item, "GetMediaPoolItem")
    props = _clip_properties(mpi)
    identity = _media_source_identity(item)
    start = _call_optional(item, "GetStart")
    end = _call_optional(item, "GetEnd")
    duration = _call_optional(item, "GetDuration")
    name = _call_optional(item, "GetName")
    media_name = _call_optional(mpi, "GetName") or _dict_get_first(props, ("Clip Name", "File Name", "Name"))
    source_path = _normalize_source_path(
        _dict_get_first(
            props,
            (
                "File Path",
                "FilePath",
                "Source File",
                "SourceFile",
                "Source Path",
                "SourcePath",
                "Path",
            ),
        )
    )
    unique_id = _call_optional(item, "GetUniqueId")
    return {
        "name": str(name) if name is not None else None,
        "track_type": "video",
        "track_index": track_index,
        "index_in_track": index_in_track,
        "start": start,
        "end": end,
        "duration": duration,
        "unique_id": str(unique_id) if unique_id is not None else None,
        "media_pool_name": str(media_name) if media_name is not None else None,
        "source_path": source_path,
        "source_identity": identity.as_dict(),
    }


def _timeline_video_items(conn: Any) -> list[tuple[Any, int, int]]:
    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        raise ValidationError("No current timeline is available.", recoverability="manual")
    try:
        track_count = int(timeline.GetTrackCount("video") or 0)
    except Exception as exc:
        raise APICallFailed("Failed to read video track count.", details={"track_type": "video"}) from exc

    rows: list[tuple[Any, int, int]] = []
    for track_index in range(1, track_count + 1):
        try:
            items = timeline.GetItemListInTrack("video", track_index) or []
        except Exception as exc:
            raise APICallFailed(
                "Failed to read video timeline items.",
                details={"track_type": "video", "track_index": track_index},
            ) from exc
        for index_in_track, item in enumerate(items, 1):
            rows.append((item, track_index, index_in_track))
    return rows


def _version_names(item: Any, version_type: int) -> list[str]:
    getter = getattr(item, "GetVersionNameList", None)
    if not callable(getter):
        raise APICallFailed(
            "Timeline item does not support color version listing.",
            details={"method": "TimelineItem.GetVersionNameList", "version_type": version_type},
        )
    try:
        names = getter(version_type) or []
    except Exception as exc:
        raise APICallFailed(
            "Failed to list color versions on timeline item.",
            details={"method": "TimelineItem.GetVersionNameList", "version_type": version_type},
        ) from exc
    if isinstance(names, dict):
        names = names.values()
    return [str(name) for name in names if name is not None]


def _current_version(item: Any) -> dict[str, Any]:
    current = _call_optional(item, "GetCurrentVersion")
    if isinstance(current, dict):
        return dict(current)
    if current is not None:
        return {"value": current}
    name = _call_optional(item, "GetCurrentVersionName")
    return {"versionName": name} if name else {}


def _version_type_value(payload: dict[str, Any]) -> int | None:
    for key in ("versionType", "VersionType", "version_type", "type"):
        if key not in payload:
            continue
        value = payload.get(key)
        try:
            return int(value)
        except (TypeError, ValueError):
            text = str(value or "").strip().casefold()
            if text == "remote":
                return REMOTE_VERSION_TYPE
            if text == "local":
                return 0
    return None


def _version_name_value(payload: dict[str, Any]) -> str | None:
    for key in ("versionName", "VersionName", "version_name", "name", "current_version"):
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _is_active_remote_version(payload: dict[str, Any], name: str) -> bool:
    return _version_name_value(payload) == name and _version_type_value(payload) == REMOTE_VERSION_TYPE


def _add_remote_version(item: Any, name: str) -> bool:
    adder = getattr(item, "AddVersion", None)
    if not callable(adder):
        raise APICallFailed(
            "Timeline item does not support adding color versions.",
            details={"method": "TimelineItem.AddVersion", "version_type": REMOTE_VERSION_TYPE},
        )
    try:
        return bool(adder(name, REMOTE_VERSION_TYPE))
    except Exception as exc:
        raise APICallFailed(
            "Failed to add remote color version.",
            details={"method": "TimelineItem.AddVersion", "name": name, "version_type": REMOTE_VERSION_TYPE},
        ) from exc


def _load_remote_version(item: Any, name: str) -> bool:
    loader = getattr(item, "LoadVersionByName", None)
    if not callable(loader):
        raise APICallFailed(
            "Timeline item does not support loading color versions.",
            details={"method": "TimelineItem.LoadVersionByName", "version_type": REMOTE_VERSION_TYPE},
        )
    try:
        return bool(loader(name, REMOTE_VERSION_TYPE))
    except Exception as exc:
        raise APICallFailed(
            "Failed to load remote color version.",
            details={"method": "TimelineItem.LoadVersionByName", "name": name, "version_type": REMOTE_VERSION_TYPE},
        ) from exc


def plan_source_grade(
    conn: Any,
    *,
    clip_name: str | None = None,
    scope: str = "current-source",
    include_singletons: bool = False,
) -> dict[str, Any]:
    normalized_scope = str(scope or "").strip().lower()
    if normalized_scope not in {"current-source", "timeline-sources"}:
        raise ValidationError(
            "Unsupported source grade scope.",
            details={"scope": scope, "supported_scopes": ["current-source", "timeline-sources"]},
            recoverability="not_applicable",
        )

    target_item = cutagent_clip(conn, clip_name) if normalized_scope == "current-source" else None
    target_identity = _media_source_identity(target_item).key if target_item is not None else None

    groups: dict[str, dict[str, Any]] = {}
    for item, track_index, index_in_track in _timeline_video_items(conn):
        summary = _item_summary(item, track_index=track_index, index_in_track=index_in_track)
        key = summary["source_identity"]["key"]
        if target_identity is not None and key != target_identity:
            continue
        group = groups.setdefault(
            key,
            {
                "source_identity": summary["source_identity"],
                "media_pool_name": summary["media_pool_name"],
                "source_path": summary["source_path"],
                "instances": [],
            },
        )
        group["instances"].append(summary)

    planned_groups = []
    for group in groups.values():
        instance_count = len(group["instances"])
        if instance_count < 2 and not include_singletons:
            continue
        group = dict(group)
        group["instance_count"] = instance_count
        group["recommended_scope"] = "remote-source" if instance_count > 1 else "timeline-local"
        planned_groups.append(group)

    target_summary = _item_summary(target_item) if target_item is not None else None
    same_source_instance_count = sum(
        int(group["instance_count"])
        for group in planned_groups
        if int(group["instance_count"]) > 1
    )

    return {
        "scope": normalized_scope,
        "clip": clip_name,
        "target": target_summary,
        "group_count": len(planned_groups),
        "same_source_instance_count": same_source_instance_count,
        "groups": planned_groups,
        "recommendation": _recommendation(normalized_scope, planned_groups),
    }


def _recommendation(scope: str, groups: list[dict[str, Any]]) -> dict[str, Any]:
    if scope == "current-source":
        if not groups:
            return {
                "mode": "timeline-local",
                "reason": "The selected clip has no other timeline instances with the same media identity.",
            }
        if groups[0]["instance_count"] > 1:
            return {
                "mode": "remote-source",
                "reason": "Multiple timeline instances share the same source media identity.",
            }
    multi_instance_groups = [group for group in groups if group["instance_count"] > 1]
    if multi_instance_groups:
        return {
            "mode": "remote-source",
            "reason": "At least one source media identity appears multiple times on the timeline.",
        }
    return {"mode": "timeline-local", "reason": "No repeated source media identity was found."}


def prepare_remote_source_grade(
    conn: Any,
    *,
    name: str,
    clip_name: str | None = None,
    create: bool = True,
    load: bool = True,
    include_singletons: bool = False,
) -> dict[str, Any]:
    normalized_name = str(name or "").strip()
    if not normalized_name:
        raise ValidationError("Remote version name must not be empty.", details={"name": name}, recoverability="not_applicable")

    plan = plan_source_grade(conn, clip_name=clip_name, scope="current-source", include_singletons=include_singletons)
    groups = plan["groups"]
    if not groups:
        raise ValidationError(
            "No same-source timeline instances were found for remote source grading.",
            details={"clip": clip_name, "include_singletons": include_singletons, "recommendation": plan["recommendation"]},
            recoverability="manual",
        )

    target_item = cutagent_clip(conn, clip_name)
    before_target_versions = _version_names(target_item, REMOTE_VERSION_TYPE)
    created = False
    if normalized_name not in before_target_versions:
        if not create:
            raise ValidationError(
                "Remote color version does not exist on the selected source.",
                details={"name": normalized_name, "available_remote_versions": before_target_versions},
                recoverability="manual",
            )
        if not _add_remote_version(target_item, normalized_name):
            raise APICallFailed(
                "DaVinci Resolve did not create the remote color version.",
                details={"name": normalized_name, "version_type": REMOTE_VERSION_TYPE},
            )
        created = True

    target_identity_key = plan["target"]["source_identity"]["key"]
    instance_results = []
    shared_before_load = True
    loaded_count = 0
    for item, track_index, index_in_track in _timeline_video_items(conn):
        summary = _item_summary(item, track_index=track_index, index_in_track=index_in_track)
        if summary["source_identity"]["key"] != target_identity_key:
            continue
        remote_versions = _version_names(item, REMOTE_VERSION_TYPE)
        has_remote_version = normalized_name in remote_versions
        shared_before_load = shared_before_load and has_remote_version
        loaded = False
        active_remote_version = False
        current_after: dict[str, Any] = {}
        if load:
            if not has_remote_version:
                raise APICallFailed(
                    "Remote color version is not available on a same-source timeline instance.",
                    details={
                        "name": normalized_name,
                        "instance": summary,
                        "available_remote_versions": remote_versions,
                        "expected_shared_remote_version": True,
                    },
                )
            loaded = _load_remote_version(item, normalized_name)
            if not loaded:
                raise APICallFailed(
                    "DaVinci Resolve did not load the remote color version on a same-source timeline instance.",
                    details={"name": normalized_name, "instance": summary},
                )
            current_after = _current_version(item)
            active_remote_version = _is_active_remote_version(current_after, normalized_name)
            if not active_remote_version:
                raise APICallFailed(
                    "DaVinci Resolve reported that it loaded the remote color version, but readback did not make it active.",
                    details={
                        "name": normalized_name,
                        "instance": summary,
                        "current_after": current_after,
                        "expected": {"versionName": normalized_name, "versionType": REMOTE_VERSION_TYPE},
                    },
                )
            loaded_count += 1
        instance_results.append(
            {
                **summary,
                "remote_versions": remote_versions,
                "has_remote_version": has_remote_version,
                "loaded": loaded,
                "active_remote_version": active_remote_version,
                "current_after": current_after,
            }
        )

    if not instance_results:
        raise ValidationError(
            "No timeline instances matched the selected source after remote version creation.",
            details={"clip": clip_name, "source_identity": target_identity_key},
            recoverability="manual",
        )

    return {
        "name": normalized_name,
        "clip": clip_name,
        "scope": "current-source",
        "remote": True,
        "version_type": "remote",
        "version_type_id": REMOTE_VERSION_TYPE,
        "created": created,
        "loaded": load,
        "loaded_count": loaded_count,
        "same_source_instance_count": len(instance_results),
        "shared_remote_version_visible_on_all_instances": shared_before_load,
        "source_identity": plan["target"]["source_identity"],
        "instances": instance_results,
        "verification": {
            "status": "verified" if (not load or loaded_count == len(instance_results)) and shared_before_load else "failed",
            "method": "TimelineItem.GetVersionNameList/LoadVersionByName",
            "render_proof_status": "not_performed",
            "note": "This verifies shared remote version scope across matching timeline items, not the aesthetic grade payload. Run rendered proof on at least two same-source instances after applying grade controls.",
        },
    }
